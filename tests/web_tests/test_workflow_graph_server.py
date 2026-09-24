"""服务器级 workflow 图事件链路（change ``workflow-graph-visualization``，tasks 2.2/2.3）。

覆盖：

- scheduler 的图事件经 session 级 forwarder 到达真实 WebSocket（``run_session``
  路径 + 后台 ``wait=false`` 路径）；
- ws 重连后从 manager 注册表补发当前快照（Q2/Q9），且只补发 ``started`` 的图；
- 事件形状（Q8）与归属字段；
- 既有无 workflow 会话不受影响（兼容回归）。
"""
import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from agent.config import AsterwyndConfig
from agent.llm import LLMResponse
from agent.run_config import AgentMode
from agent.subagent.bus import MessageBus
from agent.subagent.manager import SubAgentManager
from agent.subagent.scheduler import WorkflowScheduler
from agent.subagent.workflow import parse_workflow_spec
from tests.support.llm_harness import ScriptedLLM
from web.server import create_app


def _chain_spec() -> dict:
    return {
        "goal": "chain",
        "nodes": [
            {"id": "a", "kind": "subagent", "task": "task a"},
            {"id": "b", "kind": "subagent", "task": "task b"},
            {"id": "c", "kind": "aggregate", "strategy": "collect"},
        ],
        "edges": [{"from": "a", "to": "b"}, {"from": "b", "to": "c"}],
        "terminal": ["c"],
    }


def _drain_until(ws, wanted: set[str], limit: int = 200) -> list[dict]:
    """读到 ``wanted`` 里的类型出现为止（避免死等）。"""
    events: list[dict] = []
    for _ in range(limit):
        event = ws.receive_json()
        events.append(event)
        if event.get("type") in wanted:
            return events
    raise AssertionError(f"never saw {wanted}; got {[e.get('type') for e in events]}")


def test_workflow_snapshot_reaches_websocket(tmp_path):
    """tasks 2.2：scheduler 的 sink → session forwarder → ws 到达前端。

    这里直接以 manager 的 ``graph_sink`` 形态调用（调度器在节点迁移处的调用方式），
    验证 web 链路本身；scheduler 侧的调用点由
    ``tests/agent/subagent/test_workflow_graph_events.py`` 覆盖。
    """
    mock_llm = ScriptedLLM([LLMResponse(content="unused")])
    app = create_app(mock_llm, workspace_root=tmp_path)

    with TestClient(app) as client:
        with client.websocket_connect("/ws/new") as ws:
            created = ws.receive_json()
            assert created["type"] == "session_created"
            session = app.state.session_manager.get_session(created["session_id"])
            manager = session.agent.subagent_manager
            assert manager.graph_sink is not None, "session 创建时必须已装 sink"

            scheduler = WorkflowScheduler(manager)
            scheduler.spec = parse_workflow_spec(_chain_spec())
            scheduler._status = "running"

            # sink 在真实系统里由**服务端事件循环线程**的节点任务调用；测试线程直接调
            # 会因为 forwarder 的 ``ensure_future`` 跨线程调度而挂起，所以用 portal
            # 把调用投回服务端循环（与生产调用上下文一致）。
            def emit():
                manager.graph_sink("workflow_started", {
                    "workflow_id": scheduler.workflow_id,
                    "spec_hash": scheduler.spec.spec_hash,
                    "goal": scheduler.spec.goal,
                    "status": "running",
                    "timestamp": 0.0,
                })
                manager.graph_sink("workflow_snapshot", scheduler.workflow_graph_snapshot())

            client.portal.call(emit)

            events = _drain_until(ws, {"workflow_snapshot"}, limit=20)

    workflow_events = [e for e in events if e["type"].startswith("workflow_")]
    types = [e["type"] for e in workflow_events]
    assert types == ["workflow_started", "workflow_snapshot"]

    snapshot = workflow_events[-1]
    assert snapshot["data"]["workflow_id"] == scheduler.workflow_id
    assert snapshot["data"]["session_id"] == created["session_id"]
    assert snapshot["data"]["status"] == "running"
    assert [node["id"] for node in snapshot["data"]["nodes"]] == ["a", "b", "c"]
    assert len(snapshot["data"]["edges"]) == 2


def test_workflow_events_not_sent_for_plain_run(tmp_path):
    """兼容回归：没有 workflow 的会话只发既有事件，不冒 workflow 事件。"""
    mock_llm = ScriptedLLM([LLMResponse(content="plain")])
    app = create_app(mock_llm, workspace_root=tmp_path)

    with TestClient(app) as client:
        with client.websocket_connect("/ws/new") as ws:
            ws.receive_json()
            ws.send_json({"type": "chat", "content": "hi"})
            events = _drain_until(ws, {"done"}, limit=50)

    assert [e["type"] for e in events] == ["run_started", "llm_response", "done"]


def test_reconnect_resends_running_snapshot(tmp_path):
    """tasks 2.3：ws 重连后补发当前 running 图（Q2）。"""
    mock_llm = ScriptedLLM([LLMResponse(content="unused")])
    app = create_app(mock_llm, workspace_root=tmp_path)
    session_id = None
    workflow_id = None

    with TestClient(app) as client:
        with client.websocket_connect("/ws/new") as ws:
            created = ws.receive_json()
            session_id = created["session_id"]
            session = app.state.session_manager.get_session(session_id)
            manager = session.agent.subagent_manager

            scheduler = WorkflowScheduler(manager)
            scheduler.spec = parse_workflow_spec(_chain_spec())
            # 造一个「正在跑」的图：只 attach spec + 置 running（不真跑节点）。
            scheduler._status = "running"
            manager.register_workflow(scheduler)
            workflow_id = scheduler.workflow_id

        # 第一条连接关闭后重连同一个 session id（内存命中 → 同一个 AgentSession）。
        with client.websocket_connect(f"/ws/{session_id}") as ws:
            resumed = ws.receive_json()
            assert resumed["type"] == "session_resumed"
            history = ws.receive_json()
            assert history["type"] == "session_history"
            events = _drain_until(ws, {"workflow_snapshot"}, limit=20)

    snapshot = [e for e in events if e["type"] == "workflow_snapshot"][0]
    assert snapshot["data"]["workflow_id"] == workflow_id
    assert snapshot["data"]["status"] == "running"
    assert snapshot["data"]["session_id"] == session_id


def test_reconnect_skips_declared_only_graph(tmp_path):
    """Q2：只 ``DeclareWorkflow`` 未启动的图不得被补发。"""
    mock_llm = ScriptedLLM([LLMResponse(content="unused")])
    app = create_app(mock_llm, workspace_root=tmp_path)
    session_id = None

    with TestClient(app) as client:
        with client.websocket_connect("/ws/new") as ws:
            created = ws.receive_json()
            session_id = created["session_id"]
            session = app.state.session_manager.get_session(session_id)
            manager = session.agent.subagent_manager

            declared = WorkflowScheduler(manager)
            declared.spec = parse_workflow_spec(_chain_spec())
            manager.register_workflow(declared)  # status 仍是 "declared"

        with client.websocket_connect(f"/ws/{session_id}") as ws:
            ws.receive_json()  # session_resumed
            ws.receive_json()  # session_history
            ws.send_json({"type": "ping"})
            pong = ws.receive_json()

    assert pong["type"] == "pong"


def test_background_workflow_snapshot_after_parent_run(tmp_path):
    """决策 3：``wait=false`` 的后台图在父 run 结束后仍推快照。

    这里直接验证「出口不是 per-run queue」：父 run 走完之后，用一个独立任务调
    scheduler 的迁移点，事件仍能到达 ws。
    """
    mock_llm = ScriptedLLM([LLMResponse(content="parent done")])
    app = create_app(mock_llm, workspace_root=tmp_path)

    with TestClient(app) as client:
        with client.websocket_connect("/ws/new") as ws:
            created = ws.receive_json()
            ws.send_json({"type": "chat", "content": "hi"})
            _drain_until(ws, {"done"}, limit=50)

            session = app.state.session_manager.get_session(created["session_id"])
            manager = session.agent.subagent_manager
            forwarder = session.graph_forwarder

            # 父 run 已经结束（done 已收到），此时后台 workflow 才推一帧。
            # 同样经 portal 投回服务端循环（生产里 sink 由节点任务在该循环里调）。
            client.portal.call(
                lambda: forwarder("workflow_snapshot", {"workflow_id": "wf_bg", "status": "running"})
            )

            events = _drain_until(ws, {"workflow_snapshot"}, limit=20)

    snapshot = [e for e in events if e["type"] == "workflow_snapshot"][0]
    assert snapshot["data"]["workflow_id"] == "wf_bg"
    assert snapshot["data"]["session_id"] == created["session_id"]


def test_reset_detaches_graph_channel(tmp_path):
    """Q1：``reset`` 走 ``remove_session`` → 旧 forwarder 被摘掉。"""
    mock_llm = ScriptedLLM([LLMResponse(content="unused")])
    app = create_app(mock_llm, workspace_root=tmp_path)

    with TestClient(app) as client:
        with client.websocket_connect("/ws/new") as ws:
            created = ws.receive_json()
            old = app.state.session_manager.get_session(created["session_id"])
            old_forwarder = old.graph_forwarder

            ws.send_json({"type": "reset"})
            events = _drain_until(ws, {"session_created"}, limit=20)

    assert old_forwarder._detached is True
    assert old_forwarder._ws_send is None
    assert app.state.session_manager.get_session(created["session_id"]) is None

