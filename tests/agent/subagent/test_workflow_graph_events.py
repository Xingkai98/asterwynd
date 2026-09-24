"""scheduler 侧的 workflow 图事件发射（change ``workflow-graph-visualization``，D4 + Q1/Q3/Q11）。

覆盖 tasks 2.1/2.2 的 scheduler 半边：

- ``workflow_started`` 的触发点是 ``scheduler.run()`` 的启动 hook，不是工具层；
  ``DeclareWorkflow`` 只注册不运行 → 一条都不发（grill 决策 1）；
- 节点迁移处发 ``workflow_snapshot``（``_dispatch`` / ``_run_node`` 终态 / 取消 /
  预算停止 / 图级超限 / ``run()`` 收尾）；
- 无 sink（benchmark / 纯后端调用）→ 静默不报错（Q3 的「按有没有 sink 分」）；
- **sink 调用永不抛**（Q11）：sink 抛异常不得改变节点终态或 envelope。
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


class StaticLLM:
    def __init__(self, content="worker result"):
        self.content = content

    async def chat(self, messages, tools=None, model="gpt-4"):
        return LLMResponse(content=self.content, stop_reason="end_turn", usage=Usage(5, 5))


@pytest.fixture
def manager(tmp_path):
    return SubAgentManager(
        llm=StaticLLM(),
        config=AsterwyndConfig(),
        parent_mode=AgentMode.BUILD,
        workspace_policy=WorkspacePolicy(workspace_root=tmp_path),
    )


class RecordingSink:
    """同步 sink：只追加，绝不阻塞（scheduler 侧约定 sink 是同步可调用对象）。"""

    def __init__(self):
        self.events: list[tuple[str, dict]] = []

    def __call__(self, event_type: str, data: dict) -> None:
        self.events.append((event_type, data))

    def types(self) -> list[str]:
        return [event_type for event_type, _ in self.events]

    def snapshots(self) -> list[dict]:
        return [data for event_type, data in self.events if event_type == "workflow_snapshot"]


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


def _scheduler(manager, raw: dict) -> WorkflowScheduler:
    scheduler = WorkflowScheduler(manager)
    scheduler.spec = parse_workflow_spec(raw)
    return scheduler


# --- 2.1 启动触发点 ---------------------------------------------------------


@pytest.mark.asyncio
async def test_workflow_started_emitted_at_run_hook(manager):
    """决策 1：``run()`` 的启动 hook 发 ``workflow_started``（不是工具层）。"""
    sink = RecordingSink()
    manager.graph_sink = sink
    scheduler = _scheduler(manager, _chain_spec())

    await scheduler.run(scheduler.spec)

    started = [data for event_type, data in sink.events if event_type == "workflow_started"]
    assert len(started) == 1
    assert started[0]["workflow_id"] == scheduler.workflow_id
    assert started[0]["status"] == "running"
    assert started[0]["spec_hash"] == scheduler.spec.spec_hash


@pytest.mark.asyncio
async def test_declare_only_scheduler_emits_nothing(manager):
    """决策 1：``DeclareWorkflow`` 只 ``register_workflow`` 不调 ``run()`` → 零事件。"""
    sink = RecordingSink()
    manager.graph_sink = sink
    scheduler = _scheduler(manager, _chain_spec())
    manager.register_workflow(scheduler)

    await asyncio.sleep(0)

    assert sink.events == []


@pytest.mark.asyncio
async def test_snapshot_emitted_on_node_transitions(manager):
    """任务 2.2：节点迁移处发 ``workflow_snapshot``，含首帧与终帧。"""
    sink = RecordingSink()
    manager.graph_sink = sink
    scheduler = _scheduler(manager, _chain_spec())

    await scheduler.run(scheduler.spec)

    snapshots = sink.snapshots()
    assert snapshots, "run() 必须至少发一帧快照"
    # 首帧在开跑前（图结构可见、节点全 pending），终帧是终态。
    assert {node["status"] for node in snapshots[0]["nodes"]} == {"pending"}
    assert snapshots[-1]["status"] == "completed"
    assert snapshots[-1]["workflow_id"] == scheduler.workflow_id


@pytest.mark.asyncio
async def test_snapshot_carries_edges_every_frame(manager):
    """每一帧都是完整可重放的图（D4：发完整快照，不发局部 patch）。"""
    sink = RecordingSink()
    manager.graph_sink = sink
    scheduler = _scheduler(manager, _chain_spec())

    await scheduler.run(scheduler.spec)

    for snapshot in sink.snapshots():
        assert [node["id"] for node in snapshot["nodes"]] == ["a", "b", "c"]
        assert len(snapshot["edges"]) == 2


@pytest.mark.asyncio
async def test_cancel_emits_terminal_snapshot(manager):
    """取消路径也发快照：前端要能看到 ``cancelled``。"""
    sink = RecordingSink()
    manager.graph_sink = sink
    scheduler = _scheduler(manager, _chain_spec())
    scheduler._status = "running"  # 只有跑过的图才发快照（见下一条测试）

    scheduler.cancel()

    assert sink.snapshots(), "cancel() 必须发一帧"
    assert sink.snapshots()[-1]["status"] == "cancelled"


@pytest.mark.asyncio
async def test_cancel_on_declared_only_scheduler_keeps_declared(manager):
    """``DeclareWorkflow`` 的图被 ``CancelWorkflow`` 取消时**不得**变成 ``started``。

    回归：``cancel()`` 曾无条件写 ``_status = "cancelled"``，而 ``started`` property
    是 ``_status != "declared"``——于是一张从未 ``run()`` 的图会被 C5 的
    ``collect_workflow_records`` 记进 ``workflows`` 列表（父 run 结束后凭空多出
    一条没有 ``observed`` 的 record）。也没有图可发，不该推快照。
    """
    sink = RecordingSink()
    manager.graph_sink = sink
    scheduler = _scheduler(manager, _chain_spec())
    manager.register_workflow(scheduler)  # DeclareWorkflow：只注册不 run
    assert scheduler.started is False

    result = scheduler.cancel()

    assert result["status"] == "cancelling"
    assert scheduler.started is False, "声明期取消不得把图变成「跑过」"
    assert scheduler._status == "declared"
    assert sink.events == [], "从未开跑的图没有快照可发"


@pytest.mark.asyncio
async def test_graph_recursion_exceeded_emits_snapshot_with_diagnostics(manager):
    """图级超限：``_mark_graph_recursion_exceeded`` 发带 diagnostics 的快照。"""
    sink = RecordingSink()
    manager.graph_sink = sink
    # 25 声明节点 + 1 root = 26 ≤ 27 通过声明期闸；自动插层后 29 > 27 运行期触顶。
    scheduler = _scheduler(manager, _fanout(25, max_nodes=27))

    await scheduler.run(scheduler.spec)

    last = sink.snapshots()[-1]
    assert last["status"] == "graph_recursion_exceeded"
    assert last["diagnostics"]["reason"] == "max_nodes"


def _fanout(leaves: int, **overrides) -> dict:
    spec = {
        "goal": "fanout",
        "nodes": [
            {"id": f"l{i}", "kind": "subagent", "task": f"task {i}"} for i in range(leaves)
        ]
        + [{"id": "root", "kind": "aggregate", "strategy": "collect"}],
        "edges": [{"from": f"l{i}", "to": "root", "reducer": "concat"} for i in range(leaves)],
        "terminal": ["root"],
    }
    spec.update(overrides)
    return spec


@pytest.mark.asyncio
async def test_budget_stop_emits_snapshot(manager):
    """预算停止路径发快照（D4 列举的迁移点之一）。

    直接驱动迁移点：完整跑一张预算超限图在不同闸门下的收敛状态不同
    （``max_runs`` 走后端 C4 drain，``max_nodes`` 走图级超限），这里只锁
    「``_mark_budget_stop`` 这个迁移点自己会推快照」。
    """
    sink = RecordingSink()
    manager.graph_sink = sink
    scheduler = _scheduler(manager, _chain_spec())
    scheduler._status = "running"

    scheduler._mark_budget_stop("tokens")

    assert sink.snapshots(), "_mark_budget_stop 必须推一帧"
    assert sink.snapshots()[-1]["status"] == "running"
    assert scheduler._budget_stop is True


@pytest.mark.asyncio
async def test_run_finally_always_emits_terminal_snapshot(manager):
    """``run()`` 的 finally 必发终帧，状态就是 envelope 的 status（不依赖异常路径）。"""
    sink = RecordingSink()
    manager.graph_sink = sink
    scheduler = _scheduler(manager, _chain_spec())

    result = await scheduler.run(scheduler.spec)

    assert sink.snapshots()[-1]["status"] == result["status"] == "completed"


# --- 无 sink / Q3：按「有没有 sink」分 --------------------------------------


@pytest.mark.asyncio
async def test_no_sink_is_silent(manager):
    """Q3：没有 sink（benchmark 路径）→ 静默，不影响执行。"""
    assert getattr(manager, "graph_sink", None) is None

    scheduler = _scheduler(manager, _chain_spec())
    result = await scheduler.run(scheduler.spec)

    assert result["status"] == "completed"


# --- Q11：推送失败隔离 ------------------------------------------------------


@pytest.mark.asyncio
async def test_sink_exception_does_not_break_workflow(manager):
    """Q11：sink 抛异常（ws 已断）**不得**把节点吞成 failed。"""

    def exploding_sink(event_type: str, data: dict) -> None:
        raise RuntimeError("websocket disconnected")

    manager.graph_sink = exploding_sink
    scheduler = _scheduler(manager, _chain_spec())

    result = await scheduler.run(scheduler.spec)

    assert result["status"] == "completed"
    assert {node["id"]: node["status"] for node in result["nodes"]} == {
        "a": "completed",
        "b": "completed",
        "c": "completed",
    }


@pytest.mark.asyncio
async def test_sink_exception_does_not_change_consumed_metrics(manager):
    """Q11 + 决策 12：sink 炸了也不改 C5 消费口径与冗余度。"""

    def exploding_sink(event_type: str, data: dict) -> None:
        raise RuntimeError("boom")

    manager.graph_sink = exploding_sink
    scheduler = _scheduler(manager, _chain_spec())

    result = await scheduler.run(scheduler.spec)

    assert result["useful_runs"] == 2
    assert len(scheduler._consumed_run_ids) == 2


@pytest.mark.asyncio
async def test_sink_exception_on_cancel_does_not_break_cancel(manager):
    """Q11：取消路径的 sink 异常同样被吞（``cancel()`` 仍返回 cancelling）。"""

    def exploding_sink(event_type: str, data: dict) -> None:
        raise RuntimeError("boom")

    manager.graph_sink = exploding_sink
    scheduler = _scheduler(manager, _chain_spec())
    scheduler._status = "running"

    result = scheduler.cancel()

    assert result["status"] == "cancelling"
    assert scheduler._status == "cancelled"


@pytest.mark.asyncio
async def test_graph_sink_absent_attribute_tolerated(manager):
    """sink 未配置（老 manager 形态）不能因 getattr 缺失而报错。"""
    del manager.graph_sink  # 属性被删掉的极端形态

    scheduler = _scheduler(manager, _chain_spec())
    result = await scheduler.run(scheduler.spec)

    assert result["status"] == "completed"
