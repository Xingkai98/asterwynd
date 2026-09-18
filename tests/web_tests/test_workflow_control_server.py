"""控制面与下钻路由的服务器级验收（change ``enhance-workflow-graph-ux``，M3.3/M3.7）。

- transcript 只读路由：三态 union、内存口径 session 校验、未知 node 优雅降级；
- ``cancel_workflow``：走 **WS**（G18 判定的省法），与既有 ``{"type":"cancel"}``
  的语义**划清边界**（后者只让待审批失败、run 照跑）；``reset`` 先 cancel 所有图。

G18 的现状更要紧：``reset`` 只 ``fail_pending`` + ``remove_session`` + 重建，
**从不调 ``cancel()``**——而图是 ``ensure_future(scheduler.run(spec))`` 起的后台任务、
``manager._workflows`` **永不注销**，于是图继续跑、继续烧预算，而 forwarder 已被
detach，用户彻底看不到。
"""
import json

import pytest
from fastapi.testclient import TestClient

from agent.llm import LLMResponse
from agent.subagent.scheduler import WorkflowScheduler
from agent.subagent.workflow import parse_workflow_spec
from tests.support.llm_harness import ScriptedLLM
from web.server import create_app


def _chain_spec() -> dict:
    return {
        "goal": "chain",
        "nodes": [
            {"id": "a", "kind": "subagent", "task": "task a"},
            {"id": "c", "kind": "aggregate", "strategy": "collect"},
        ],
        "edges": [{"from": "a", "to": "c"}],
        "terminal": ["c"],
    }


def _running_scheduler(manager, status: str = "running") -> WorkflowScheduler:
    """造一张「在图里」的图：attach spec + 置状态 + 注册进 manager（不真跑）。"""
    scheduler = WorkflowScheduler(manager)
    scheduler.spec = parse_workflow_spec(_chain_spec())
    scheduler._status = status
    manager.register_workflow(scheduler)
    return scheduler


# --- transcript 只读路由 ----------------------------------------------------


def test_transcript_route_requires_a_loaded_session(tmp_path):
    """grill 决策 9：session 校验是**内存口径**——与 ``/api/sessions/{id}/timeline``
    同口径（``session_manager.get_session`` 只查内存字典）。

    这不是缺陷，但要写进测试：进程重启后同名 session 会被 404，这是最容易被
    误判成 bug 的场景。
    """
    mock_llm = ScriptedLLM([LLMResponse(content="unused")])
    app = create_app(mock_llm, workspace_root=tmp_path)

    with TestClient(app) as client:
        response = client.get(
            "/api/sessions/never-loaded/workflows/wf1/nodes/a/transcript")
        assert response.status_code == 404
        assert "session" in response.json()["error"]


def test_transcript_route_404s_for_unknown_workflow(tmp_path):
    mock_llm = ScriptedLLM([LLMResponse(content="unused")])
    app = create_app(mock_llm, workspace_root=tmp_path)

    with TestClient(app) as client:
        with client.websocket_connect("/ws/new") as ws:
            session_id = ws.receive_json()["session_id"]
        response = client.get(
            f"/api/sessions/{session_id}/workflows/nope/nodes/a/transcript")
        assert response.status_code == 404


def test_transcript_route_returns_payload_for_a_live_workflow(tmp_path):
    """正常路径：路由把 session 里的 scheduler 交给载荷构造器并回 JSON。"""
    mock_llm = ScriptedLLM([LLMResponse(content="unused")])
    app = create_app(mock_llm, workspace_root=tmp_path)

    with TestClient(app) as client:
        with client.websocket_connect("/ws/new") as ws:
            session_id = ws.receive_json()["session_id"]
        session = app.state.session_manager.get_session(session_id)
        scheduler = _running_scheduler(session.agent.subagent_manager)

        response = client.get(
            f"/api/sessions/{session_id}/workflows/{scheduler.workflow_id}"
            f"/nodes/a/transcript")
        assert response.status_code == 200
        payload = response.json()
        assert payload["node_id"] == "a"
        # 未派发的节点不产生 run → 优雅降级为 ``none``，且**不编造** transcript。
        assert payload["kind"] == "none"
        assert json.dumps(payload)


def test_transcript_route_never_touches_the_llm(tmp_path):
    mock_llm = ScriptedLLM([LLMResponse(content="unused")])
    app = create_app(mock_llm, workspace_root=tmp_path)

    with TestClient(app) as client:
        with client.websocket_connect("/ws/new") as ws:
            session_id = ws.receive_json()["session_id"]
        session = app.state.session_manager.get_session(session_id)
        scheduler = _running_scheduler(session.agent.subagent_manager)

        client.get(f"/api/sessions/{session_id}/workflows/{scheduler.workflow_id}"
                   f"/nodes/a/transcript")
    assert mock_llm.calls == [], "transcript 路由不得触发任何 LLM 调用"


# --- G18：WS cancel_workflow -------------------------------------------------


def _cancel_via_ws(client, ws, session_id, workflow_id):
    ws.send_json({"type": "cancel_workflow", "workflow_id": workflow_id})
    for _ in range(20):
        event = ws.receive_json()
        if event.get("type") in {"workflow_cancelled", "error"}:
            return event
    raise AssertionError("no cancel_workflow response")


def test_cancel_workflow_over_websocket(tmp_path):
    """G18：后端 ``scheduler.cancel()`` 早就绪，缺的是**入口**——WS handler 手里
    有 session，``get_workflow`` 就能拿到 scheduler；``cancel()`` 内部
    ``ensure_future`` 需要的 running loop 是 WS 天然满足的。"""
    mock_llm = ScriptedLLM([LLMResponse(content="unused")])
    app = create_app(mock_llm, workspace_root=tmp_path)

    with TestClient(app) as client:
        with client.websocket_connect("/ws/new") as ws:
            session_id = ws.receive_json()["session_id"]
            session = app.state.session_manager.get_session(session_id)
            scheduler = _running_scheduler(session.agent.subagent_manager)

            event = _cancel_via_ws(client, ws, session_id, scheduler.workflow_id)

    assert event["type"] == "workflow_cancelled"
    assert event["data"]["workflow_id"] == scheduler.workflow_id
    assert scheduler._cancelled is True, "取消没有真的落到 scheduler 上"


def test_cancel_workflow_rejects_unknown_workflow(tmp_path):
    mock_llm = ScriptedLLM([LLMResponse(content="unused")])
    app = create_app(mock_llm, workspace_root=tmp_path)

    with TestClient(app) as client:
        with client.websocket_connect("/ws/new") as ws:
            ws.receive_json()
            event = _cancel_via_ws(client, ws, None, "nope")

    assert event["type"] == "error"
    assert "workflow" in event["data"]["message"].lower()


def test_cancel_workflow_is_distinct_from_legacy_cancel(tmp_path):
    """**必须划清的边界**：``web/session.py`` 已有 ``if msg_type in {"reset","cancel"}``
    → ``fail_pending_interactions``。前端今天发 ``{"type":"cancel"}`` 只会让待审批
    失败、**run 照跑**。新的 ``cancel_workflow`` 必须与之区分：它真的停图。"""
    mock_llm = ScriptedLLM([LLMResponse(content="unused")])
    app = create_app(mock_llm, workspace_root=tmp_path)

    with TestClient(app) as client:
        with client.websocket_connect("/ws/new") as ws:
            ws.receive_json()
            session_id = None
        with client.websocket_connect("/ws/new") as ws:
            created = ws.receive_json()
            session_id = created["session_id"]
            session = app.state.session_manager.get_session(session_id)
            scheduler = _running_scheduler(session.agent.subagent_manager)

            # 旧的 cancel：不动 scheduler。
            ws.send_json({"type": "cancel"})
            ws.send_json({"type": "ping"})
            for _ in range(10):
                if ws.receive_json().get("type") == "pong":
                    break
            assert scheduler._cancelled is False, (
                "既有 cancel 的语义是「只让待审批失败，run 照跑」——本 change 不改它"
            )

            event = _cancel_via_ws(client, ws, session_id, scheduler.workflow_id)

    assert event["type"] == "workflow_cancelled"
    assert scheduler._cancelled is True


def test_reset_cancels_running_workflows(tmp_path):
    """G18 的连带修正：``reset`` 在 ``remove_session`` 之前必须逐个 ``cancel()``。

    否则后台 workflow 继续跑、继续烧预算，而 forwarder 已被 detach——用户彻底
    看不到，也管不着。"""
    mock_llm = ScriptedLLM([LLMResponse(content="unused")])
    app = create_app(mock_llm, workspace_root=tmp_path)

    with TestClient(app) as client:
        with client.websocket_connect("/ws/new") as ws:
            created = ws.receive_json()
            session = app.state.session_manager.get_session(created["session_id"])
            manager = session.agent.subagent_manager
            first = _running_scheduler(manager)
            second = _running_scheduler(manager)
            second.workflow_id = "wf-second"

            ws.send_json({"type": "reset"})
            for _ in range(20):
                event = ws.receive_json()
                if event.get("type") == "session_created":
                    break

    assert first._cancelled is True, "reset 没有 cancel 掉第一张图"
    assert second._cancelled is True, "reset 没有 cancel 掉第二张图"
