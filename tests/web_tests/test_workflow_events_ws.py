"""web 层 workflow 图事件通道（change ``workflow-graph-visualization``，Q1/Q2/Q4/Q8/Q9/Q11）。

覆盖 tasks 2.1-2.3 的 web 半边：

- session 级 forwarder（Q1 方案 A）：sender 持有 **session** 而非某次 run 的 queue，
  ``wait=false`` 的后台 workflow 在父 run 结束后仍能推事件（决策 3）；
- 时间窗合并（Q4）：≥100ms 窗内按 workflow 保留最新快照，终态立即 flush；
- ws 重连补发（Q2/Q9）：从 manager 注册表按 ``started`` 过滤 declared 图，补
  「当前 running + 最近 5 张终态」；
- 事件形状（Q8）：``{"type": ..., "data": {...}}`` 两层，``data`` 带
  ``workflow_id``/``session_id``/``timestamp``；
- 推送失败隔离（Q11）：ws 已断时 sender 静默丢弃，不打断 workflow。
"""
import asyncio

import pytest

from agent.config import AsterwyndConfig
from agent.llm import LLMResponse, Usage
from agent.run_config import AgentMode
from agent.subagent.manager import SubAgentManager
from agent.subagent.scheduler import WorkflowScheduler
from agent.subagent.workflow import parse_workflow_spec
from agent.workspace_policy import WorkspacePolicy

from web.session import GraphEventForwarder, SessionManager, build_workflow_resume_payloads


class StaticLLM:
    def __init__(self, content="worker result"):
        self.content = content

    async def chat(self, messages, tools=None, model="gpt-4"):
        return LLMResponse(content=self.content, stop_reason="end_turn", usage=Usage(5, 5))


def _chain_spec(**overrides) -> dict:
    spec = {
        "goal": "chain",
        "nodes": [
            {"id": "a", "kind": "subagent", "task": "task a"},
            {"id": "b", "kind": "subagent", "task": "task b"},
            {"id": "c", "kind": "aggregate", "strategy": "collect"},
        ],
        "edges": [{"from": "a", "to": "b"}, {"from": "b", "to": "c"}],
        "terminal": ["c"],
    }
    spec.update(overrides)
    return spec


def _manager(tmp_path) -> SubAgentManager:
    return SubAgentManager(
        llm=StaticLLM(),
        config=AsterwyndConfig(),
        parent_mode=AgentMode.BUILD,
        workspace_policy=WorkspacePolicy(workspace_root=tmp_path),
    )


class Collector:
    """异步 ws_send 替身；可选在每次发送时抛错（模拟 ws 已断）。"""

    def __init__(self, *, explode: bool = False, delay: float = 0.0):
        self.events: list[dict] = []
        self.explode = explode
        self.delay = delay

    async def __call__(self, event: dict) -> None:
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.explode:
            raise RuntimeError("websocket disconnected")
        self.events.append(event)

    def types(self) -> list[str]:
        return [event["type"] for event in self.events]


# --- Q1：session 级 forwarder 生命周期 --------------------------------------


@pytest.mark.asyncio
async def test_forwarder_sends_events_through_ws_send():
    collector = Collector()
    forwarder = GraphEventForwarder(session_id="s1", ws_send=collector)

    forwarder("workflow_started", {"workflow_id": "wf_1", "status": "running"})
    await forwarder.flush()

    assert collector.types() == ["workflow_started"]
    assert collector.events[0]["data"]["workflow_id"] == "wf_1"
    assert collector.events[0]["data"]["session_id"] == "s1"
    assert collector.events[0]["data"]["timestamp"] > 0


@pytest.mark.asyncio
async def test_forwarder_outlives_a_single_run_queue():
    """决策 3：父 run 结束后（queue drain 退出），forwarder 仍在推。

    这里用一个「队列已关」的等价形态：sender 不持有任何 per-run queue，
    事件从独立任务里推出来也能到达 ws。
    """
    collector = Collector()
    forwarder = GraphEventForwarder(session_id="s1", ws_send=collector)

    # 模拟「父 run 已经结束」之后，后台 workflow 的节点任务继续调 sink。
    async def background_workflow():
        await asyncio.sleep(0)
        forwarder("workflow_snapshot", {"workflow_id": "wf_bg", "status": "running"})

    forwarder("workflow_started", {"workflow_id": "wf_bg", "status": "running"})
    await asyncio.ensure_future(background_workflow())
    await forwarder.flush()

    assert "workflow_snapshot" in collector.types()


@pytest.mark.asyncio
async def test_forwarder_rebinds_on_reconnect():
    """A 的实现细节：ws 重连把新的 ``ws_send`` 绑到同一个 forwarder。"""
    first = Collector()
    forwarder = GraphEventForwarder(session_id="s1", ws_send=first)

    second = Collector()
    forwarder.rebind(second)
    forwarder("workflow_snapshot", {"workflow_id": "wf_1", "status": "running"})
    await forwarder.flush()

    assert first.events == []
    assert second.types() == ["workflow_snapshot"]


@pytest.mark.asyncio
async def test_forwarder_detach_drops_events_silently():
    """``reset`` 路径摘掉 sender：之后的事件不推、也不报错。"""
    collector = Collector()
    forwarder = GraphEventForwarder(session_id="s1", ws_send=collector)

    forwarder.detach()
    forwarder("workflow_snapshot", {"workflow_id": "wf_1"})
    await forwarder.flush()

    assert collector.events == []


# --- Q4：时间窗合并 ---------------------------------------------------------


@pytest.mark.asyncio
async def test_forwarder_coalesces_snapshots_within_window():
    """Q4：同一 workflow 在窗口内多次快照只发最后一帧。"""
    collector = Collector()
    forwarder = GraphEventForwarder(session_id="s1", ws_send=collector, window_s=0.05)

    for runs in (1, 2, 3):
        forwarder("workflow_snapshot", {"workflow_id": "wf_1", "runs": runs})
    await forwarder.flush()

    assert [event["data"]["runs"] for event in collector.events] == [3]


@pytest.mark.asyncio
async def test_forwarder_coalesces_per_workflow():
    """Q4：合并缓冲**按 workflow_id 分桶**，一张图不挤掉另一张。"""
    collector = Collector()
    forwarder = GraphEventForwarder(session_id="s1", ws_send=collector, window_s=0.05)

    forwarder("workflow_snapshot", {"workflow_id": "wf_a", "runs": 1})
    forwarder("workflow_snapshot", {"workflow_id": "wf_b", "runs": 1})
    forwarder("workflow_snapshot", {"workflow_id": "wf_a", "runs": 2})
    await forwarder.flush()

    assert sorted(event["data"]["workflow_id"] for event in collector.events) == ["wf_a", "wf_b"]
    assert {e["data"]["workflow_id"]: e["data"]["runs"] for e in collector.events} == {
        "wf_a": 2,
        "wf_b": 1,
    }


@pytest.mark.asyncio
async def test_forwarder_flushes_terminal_snapshot_immediately():
    """Q4：终态**绕过时间窗**立即发（``window_s=10`` 也不会把它压住）。"""
    collector = Collector()
    forwarder = GraphEventForwarder(session_id="s1", ws_send=collector, window_s=10.0)

    forwarder("workflow_snapshot", {"workflow_id": "wf_1", "status": "running", "runs": 1})
    forwarder("workflow_snapshot", {"workflow_id": "wf_1", "status": "completed", "runs": 2})
    await forwarder.flush()

    # running 帧被终态帧覆盖，且终态没有被 10s 窗口拖住。
    assert [event["data"]["status"] for event in collector.events] == ["completed"]


@pytest.mark.asyncio
async def test_forwarder_started_event_is_never_coalesced():
    """``workflow_started`` 是「开一张新图」信号，不能被合并吃掉。"""
    collector = Collector()
    forwarder = GraphEventForwarder(session_id="s1", ws_send=collector, window_s=10.0)

    forwarder("workflow_started", {"workflow_id": "wf_1"})
    forwarder("workflow_snapshot", {"workflow_id": "wf_1", "status": "running"})
    await forwarder.flush()

    assert collector.types() == ["workflow_started", "workflow_snapshot"]


@pytest.mark.asyncio
async def test_forwarder_window_flush_task_emits_pending():
    """带定时 flush 的形态：等待超过窗口后待发快照自动送出。"""
    collector = Collector()
    forwarder = GraphEventForwarder(session_id="s1", ws_send=collector, window_s=0.01)

    forwarder("workflow_snapshot", {"workflow_id": "wf_1", "runs": 1})
    await asyncio.sleep(0.05)

    assert [event["data"]["runs"] for event in collector.events] == [1]


# --- Q11：推送失败隔离 ------------------------------------------------------


@pytest.mark.asyncio
async def test_forwarder_swallows_send_errors():
    """Q11：ws 已断时 sender 内部吞异常，对 scheduler 侧表现为「调用不抛」。"""
    collector = Collector(explode=True)
    forwarder = GraphEventForwarder(session_id="s1", ws_send=collector)

    forwarder("workflow_snapshot", {"workflow_id": "wf_1", "status": "completed"})
    await forwarder.flush()  # 不抛


@pytest.mark.asyncio
async def test_forwarder_does_not_raise_to_scheduler(tmp_path):
    """Q11 端到端：sink 是 forwarder 时，workflow 状态不受 ws 断开影响。"""
    sweep = Collector(explode=True)
    session = _FakeSession("s1", _manager(tmp_path))
    forwarder = GraphEventForwarder(session_id="s1", ws_send=sweep)
    session.agent.subagent_manager.graph_sink = forwarder

    scheduler = WorkflowScheduler(session.agent.subagent_manager)
    scheduler.spec = parse_workflow_spec(_chain_spec())
    result = await scheduler.run(scheduler.spec)

    assert result["status"] == "completed"


class _FakeSession:
    def __init__(self, session_id, manager):
        self.session_id = session_id
        self.agent = type("A", (), {"subagent_manager": manager})()


# --- Q2/Q9：重连补发 --------------------------------------------------------


def _register(manager, spec: dict, *, status: str) -> WorkflowScheduler:
    scheduler = WorkflowScheduler(manager)
    scheduler.spec = parse_workflow_spec(spec)
    scheduler._status = status
    manager.register_workflow(scheduler)
    return scheduler


def test_resume_payloads_skip_declared_only_graphs(tmp_path):
    """Q2：注册表里的 ``declared`` 图（只声明未启动）不得出现在补发列表里。"""
    manager = _manager(tmp_path)
    _register(manager, _chain_spec(), status="declared")
    running = _register(manager, _chain_spec(), status="running")

    payloads = build_workflow_resume_payloads(manager, session_id="s1")

    assert [p["data"]["workflow_id"] for p in payloads] == [running.workflow_id]


def test_resume_payloads_keep_running_plus_recent_five_terminal(tmp_path):
    """Q2/Q9：补发「当前 running + 最近 5 张终态」，按入表序取最后 5 张。"""
    manager = _manager(tmp_path)
    for _ in range(7):
        _register(manager, _chain_spec(), status="completed")
    running = _register(manager, _chain_spec(), status="running")

    payloads = build_workflow_resume_payloads(manager, session_id="s1")

    ids = [p["data"]["workflow_id"] for p in payloads]
    assert running.workflow_id in ids
    assert len(ids) == 6  # 1 running + 5 terminal
    # 终态按入表序取**最后** 5 张：最早的两张被淘汰。
    all_ids = list(manager._workflows)
    assert all_ids[0] not in ids and all_ids[1] not in ids


def test_resume_payloads_shape(tmp_path):
    """Q8/Q9：补发帧沿用 ``workflow_snapshot`` 形状 + 归属字段。"""
    manager = _manager(tmp_path)
    scheduler = _register(manager, _chain_spec(), status="running")

    [payload] = build_workflow_resume_payloads(manager, session_id="s1")

    assert payload["type"] == "workflow_snapshot"
    data = payload["data"]
    assert data["workflow_id"] == scheduler.workflow_id
    assert data["session_id"] == "s1"
    assert data["timestamp"] > 0
    assert [node["id"] for node in data["nodes"]] == ["a", "b", "c"]
    assert len(data["edges"]) == 2


def test_resume_payloads_without_graphs_is_empty(tmp_path):
    manager = _manager(tmp_path)
    assert build_workflow_resume_payloads(manager, session_id="s1") == []
