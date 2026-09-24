"""图快照的**加法字段**（change ``enhance-workflow-graph-ux``，M2.4/M2.5/M2.6/M2.13）。

覆盖 D3/D9：

- 节点 ``reason``（**投影层截断**——``state.reason`` 是 ``_envelope`` 字段、本体
  不能改）、节点 ``task``（详情面板「任务」tab 的数据源，G5）；
- 图级 ``started_at``/``finished_at``（**哨兵统一成 ``null``**，D3/grill 决策 2）；
- 图级 ``budget``（G13；``declared`` 态返回 ``{}``）；
- ``queued`` 的**投影层**省法（G3：不动状态机、不动 ``_dispatch_capacity``）；
- 白名单同步（grill 决策 4：图级白名单是内联字面量，不是常量）。

``_envelope``/``parent_envelope`` 的结构契约必须逐字不变——新字段只进快照这条出口。
"""
import asyncio

import pytest

from agent.config import AsterwyndConfig
from agent.llm import LLMResponse, Usage
from agent.run_config import AgentMode
from agent.subagent.manager import SubAgentManager
from agent.subagent.scheduler import _SUMMARY_LIMIT, WorkflowScheduler
from agent.subagent.workflow import parse_workflow_spec
from agent.workspace_policy import WorkspacePolicy

#: 快照节点**允许**出现的键（与 ``test_workflow_graph_snapshot.py`` 同步维护）。
SNAPSHOT_NODE_KEYS = frozenset(
    {
        "id", "kind", "status", "runs", "summary", "reason", "task",
        "started_at", "finished_at", "targets", "items",
        "item_states", "items_running", "items_completed", "items_failed",
        #: ``fix-issue-215`` 加的加法字段：失败计数（三态 ``None``/``0``/``N``）。
        #: 快照只给**有界整数**线索，证据正文在 transcript 载荷里（懒加载）。
        "failure_count",
    }
)

#: 快照**图级**允许出现的键（原为内联 set 字面量，本 change 抽出常量便于两处共用）。
SNAPSHOT_TOP_KEYS = frozenset(
    {
        "workflow_id", "spec_hash", "goal", "status", "nodes", "edges",
        "timestamp", "started_at", "finished_at", "budget",
        "total", "completed", "failed", "diagnostics",
    }
)


class _LLM:
    def __init__(self, content="worker result"):
        self.content = content

    async def chat(self, messages, tools=None, model="gpt-4"):
        return LLMResponse(content=self.content, stop_reason="end_turn", usage=Usage(5, 5))


class _BoomLLM(_LLM):
    async def chat(self, messages, tools=None, model="gpt-4"):
        raise RuntimeError("x" * 3000)


@pytest.fixture
def manager(tmp_path):
    return SubAgentManager(
        llm=_LLM(),
        config=AsterwyndConfig(),
        parent_mode=AgentMode.BUILD,
        workspace_policy=WorkspacePolicy(workspace_root=tmp_path),
    )


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


def _scheduler(manager, raw: dict) -> WorkflowScheduler:
    scheduler = WorkflowScheduler(manager)
    scheduler.spec = parse_workflow_spec(raw)
    return scheduler


# --- M2.4：节点 reason / task ------------------------------------------------


@pytest.mark.asyncio
async def test_node_reason_is_projected_and_bounded(manager):
    """``reason`` 进快照，但**在投影层截断**——它可能取到完整异常文本。"""
    manager.llm = _BoomLLM()
    scheduler = _scheduler(manager, _chain_spec())
    await scheduler.run(scheduler.spec)

    snapshot = scheduler.workflow_graph_snapshot()
    node = next(n for n in snapshot["nodes"] if n["id"] == "a")

    assert node["reason"], "失败节点的 reason 必须进快照（G27：之前是 None）"
    assert len(node["reason"]) <= _SUMMARY_LIMIT
    # 本体不能被截断——它是 ``_envelope`` 的字段，父 agent 面另有口径。
    assert len(scheduler._states["a"].reason) > _SUMMARY_LIMIT


@pytest.mark.asyncio
async def test_node_reason_is_none_when_absent(manager):
    """没有因由的节点发 ``None``（不是空串）——前端据此判断「有没有因由」。"""
    scheduler = _scheduler(manager, _chain_spec())
    await scheduler.run(scheduler.spec)

    snapshot = scheduler.workflow_graph_snapshot()
    assert all(node["reason"] is None for node in snapshot["nodes"])


@pytest.mark.asyncio
async def test_node_task_is_projected(manager):
    """G5：节点 task 模板进快照，否则详情面板「任务」tab 没有数据源。"""
    scheduler = _scheduler(manager, _chain_spec())
    await scheduler.run(scheduler.spec)

    snapshot = scheduler.workflow_graph_snapshot()
    by_id = {node["id"]: node for node in snapshot["nodes"]}
    assert by_id["a"]["task"] == "task a"
    assert by_id["b"]["task"] == "task b"


# --- M2.4：图级时间戳的哨兵语义 ---------------------------------------------


@pytest.mark.asyncio
async def test_graph_timestamps_are_null_before_run(manager):
    """``declared`` 态：``started_at`` == 0.0 是构造期哨兵，必须投影成 ``null``。

    直接把 ``0.0`` 交给前端会被渲染成 epoch 0（「56 年前」）或算出天文耗时。
    """
    scheduler = _scheduler(manager, _chain_spec())
    snapshot = scheduler.workflow_graph_snapshot()

    assert snapshot["status"] == "declared"
    assert snapshot["started_at"] is None
    assert snapshot["finished_at"] is None


@pytest.mark.asyncio
async def test_graph_timestamps_are_set_when_running_and_finished(manager):
    """运行中 ``finished_at`` 是 ``null``；收敛后才给值（不复用 ``or time.time()``）。"""
    scheduler = _scheduler(manager, _chain_spec())
    scheduler._status = "running"
    scheduler._started_at = 1000.0

    running = scheduler.workflow_graph_snapshot()
    assert running["started_at"] == 1000.0
    assert running["finished_at"] is None

    await scheduler.run(scheduler.spec)
    done = scheduler.workflow_graph_snapshot()
    assert done["started_at"] is not None
    assert done["finished_at"] is not None
    assert done["finished_at"] >= done["started_at"]


# --- M2.5：图级预算 ---------------------------------------------------------


@pytest.mark.asyncio
async def test_graph_budget_is_empty_dict_before_run(manager):
    """G13 边界 (a)：``declared`` 态 ``self._budget is None`` → ``{}``。"""
    scheduler = _scheduler(manager, _chain_spec())
    assert scheduler.workflow_graph_snapshot()["budget"] == {}


@pytest.mark.asyncio
async def test_graph_budget_carries_dimensions_and_used(manager):
    """G13：预算停在快照里给得出「用掉多少 / 上限多少」，不只一个维度名。"""
    scheduler = _scheduler(manager, _chain_spec())
    await scheduler.run(scheduler.spec)

    budget = scheduler.workflow_graph_snapshot()["budget"]
    assert budget["exceeded"] is False
    assert set(budget["dimensions"]) == {"tokens", "cost_usd", "runs", "wall_time_s"}
    # runs 维度是调度器自己记的：这张图派发了 a、b 两个 run。
    assert budget["dimensions"]["runs"]["used"] == 2
    for dim in budget["dimensions"].values():
        assert "limit" in dim and "used" in dim


# --- M2.6：queued 的投影层省法 ----------------------------------------------


@pytest.mark.asyncio
async def test_started_run_is_projected_as_queued_while_waiting_for_slot(manager):
    """G3：``started`` 但 run record 还是 ``queued`` → 投影成 ``queued``。

    ``_dispatch_capacity`` 是 25，而真正在执行只有 ``max_active`` → 不区分的话
    最多 25 个节点同时显示 running，其中 20 个其实在排队。
    """
    scheduler = _scheduler(manager, _chain_spec())
    state = scheduler._states["a"]
    state.status = "started"
    state.subagent_id = "sa"
    state.run_id = "r1"

    class _FakeRun:
        status = "queued"

    manager.find_run = lambda subagent_id, run_id: _FakeRun()  # type: ignore[assignment]
    assert scheduler.workflow_graph_snapshot()["nodes"][0]["status"] == "queued"


@pytest.mark.asyncio
async def test_node_state_status_is_never_written_queued(manager):
    """G3 的红线：``NodeState.status`` 不得出现 ``queued`` 赋值点。

    全仓 ``"queued"`` 只在读取侧判据出现，加赋值点会让它们同时激活——其中一处
    参与 ``_in_flight_nodes`` 类收敛判断，而预算 drain 正靠「在跑的 run 归零」
    落终态。所以 ``queued`` 只存在于**投影**里。
    """
    from pathlib import Path

    source = Path(__file__).parents[3] / "agent" / "subagent" / "scheduler.py"
    text = source.read_text()
    assert 'state.status = "queued"' not in text
    assert "state.status = 'queued'" not in text


@pytest.mark.asyncio
async def test_projected_queued_does_not_leak_into_envelope(manager):
    """投影只影响快照这条出口：``_envelope`` 里的节点 status 仍是 ``started``。"""
    scheduler = _scheduler(manager, _chain_spec())
    state = scheduler._states["a"]
    state.status = "started"
    state.subagent_id = "sa"
    state.run_id = "r1"

    class _FakeRun:
        status = "queued"

    manager.find_run = lambda subagent_id, run_id: _FakeRun()  # type: ignore[assignment]
    envelope = scheduler.status()
    assert envelope["nodes"][0]["status"] == "started"


# --- 白名单与契约 -----------------------------------------------------------


@pytest.mark.asyncio
async def test_snapshot_top_level_keys_are_whitelisted(manager):
    """图级白名单（原内联字面量）：新增键必须是有意识的。"""
    scheduler = _scheduler(manager, _chain_spec())
    await scheduler.run(scheduler.spec)

    snapshot = scheduler.workflow_graph_snapshot()
    assert set(snapshot) <= SNAPSHOT_TOP_KEYS, set(snapshot) - SNAPSHOT_TOP_KEYS


@pytest.mark.asyncio
async def test_snapshot_node_keys_are_whitelisted(manager):
    """节点白名单：多一个键都是「没挑字段」。"""
    spec = {
        "goal": "fan",
        "nodes": [
            {"id": "fan", "kind": "foreach", "task": "item {item}",
             "items": [f"item-{i}" for i in range(3)]},
            {"id": "root", "kind": "aggregate", "strategy": "collect"},
        ],
        "edges": [{"from": "fan", "to": "root", "reducer": "concat"}],
        "terminal": ["root"],
    }
    scheduler = _scheduler(manager, spec)
    await scheduler.run(scheduler.spec)

    for node in scheduler.workflow_graph_snapshot()["nodes"]:
        assert set(node) <= SNAPSHOT_NODE_KEYS, set(node) - SNAPSHOT_NODE_KEYS
        for banned in ("subagent_ids", "slots", "raw", "error", "verdict"):
            assert banned not in node


@pytest.mark.asyncio
async def test_envelope_contract_does_not_drift(manager):
    """本 change 只动快照这条出口：``_envelope``/``parent_envelope`` 结构不变。"""
    scheduler = _scheduler(manager, _chain_spec())
    envelope = await scheduler.run(scheduler.spec)

    assert set(envelope["nodes"][0]) >= {"id", "kind", "status", "runs", "subagent_id"}
    assert "reason" in envelope["nodes"][0]
    assert "useful_runs" in envelope and "redundancy" in envelope
    parent = scheduler.parent_envelope()
    assert "bus" not in parent
    assert "nodes_total" in parent and "nodes_omitted" in parent


@pytest.mark.asyncio
async def test_snapshot_stays_bounded_for_wide_foreach(manager):
    """12 项 foreach 的快照仍远小于「每项一份痕迹」的规模。"""
    import json

    spec = {
        "goal": "fan",
        "nodes": [
            {"id": "fan", "kind": "foreach", "task": "item {item}",
             "items": [f"item-{i}" for i in range(12)]},
            {"id": "root", "kind": "aggregate", "strategy": "collect"},
        ],
        "edges": [{"from": "fan", "to": "root", "reducer": "concat"}],
        "terminal": ["root"],
    }
    scheduler = _scheduler(manager, spec)
    await scheduler.run(scheduler.spec)

    assert len(json.dumps(scheduler.workflow_graph_snapshot())) < 14000
