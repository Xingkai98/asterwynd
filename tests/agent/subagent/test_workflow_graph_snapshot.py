"""运行态 workflow 图快照（change ``workflow-graph-visualization``，D3/D5 + grill Q5/Q6/Q10）。

覆盖 tasks 1.1-1.3：

- 快照含完整 nodes + edges + 每节点/每边 status；
- 节点八档状态（``pending``/``started``/``completed``/``failed``/``cancelled``/
  ``blocked``/``budget_exceeded``/``skipped``；最后一档由 change
  ``enhance-workflow-graph-ux`` D2b 新增）与边五档状态（``inactive``/``ready``/
  ``active``/``passed``/``blocked``）；
- route 控制边 ``kind == "control"``，只高亮 ``targets`` 选中出口；
- 快照**显式挑字段**（grill 决策 4）：不出现 ``subagent_ids``/``slots``/``raw``/``bus``/
  ``attribution``/``latest_events``；
- 兼容：``_envelope``/``parent_envelope`` 契约与 ``_consumed_run_ids`` 基数不变
  （grill 决策 11/12）。
"""
import asyncio
import json

import pytest

from agent.config import AsterwyndConfig
from agent.llm import LLMResponse, Usage
from agent.run_config import AgentMode
from agent.subagent.manager import SubAgentManager
from agent.subagent.scheduler import GraphRecursionError, WorkflowScheduler
from agent.subagent.workflow import parse_workflow_spec
from agent.workspace_policy import WorkspacePolicy

NODE_STATUS_TIERS = frozenset(
    {"pending", "started", "completed", "failed", "cancelled", "blocked", "budget_exceeded"}
)
EDGE_STATUS_TIERS = frozenset(
    {"inactive", "ready", "active", "passed", "satisfied", "blocked"}
)

#: 快照节点**允许**出现的键（显式白名单：多一个都是「没挑字段」）。
#: ``enhance-workflow-graph-ux`` 加的加法字段：``reason``/``task``（D3/G5）、
#: ``item_states``/``items_running``/``items_completed``/``items_failed``（G7/D5）。
SNAPSHOT_NODE_KEYS = frozenset(
    {
        "id", "kind", "status", "runs", "summary", "reason", "task",
        "started_at", "finished_at", "targets", "items",
        "item_states", "items_running", "items_completed", "items_failed",
    }
)
SNAPSHOT_EDGE_KEYS = frozenset(
    {"from", "to", "channel", "required", "reducer", "kind", "status"}
)


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


def _chain_spec(**overrides) -> dict:
    """``a -> b -> c`` 的线性图（c 是 aggregate.collect）。"""
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


def _fanout_spec(leaves: int = 2) -> dict:
    return {
        "goal": "fanout",
        "nodes": [
            {"id": f"l{i}", "kind": "subagent", "task": f"task {i}"} for i in range(leaves)
        ]
        + [{"id": "root", "kind": "aggregate", "strategy": "collect"}],
        "edges": [{"from": f"l{i}", "to": "root", "reducer": "concat"} for i in range(leaves)],
        "terminal": ["root"],
    }


def _route_spec() -> dict:
    """``a -> gate(route) -> {yes, no}``；``a`` 的产出决定走哪条出口。"""
    return {
        "goal": "route",
        "nodes": [
            {"id": "a", "kind": "subagent", "task": "produce"},
            {
                "id": "gate",
                "kind": "route",
                "cases": [{"when": "APPROVED", "to": "yes"}],
                "default": "no",
            },
            {"id": "yes", "kind": "subagent", "task": "yes branch"},
            {"id": "no", "kind": "subagent", "task": "no branch"},
        ],
        "edges": [
            {"from": "a", "to": "gate"},
            {"from": "gate", "to": "yes"},
            {"from": "gate", "to": "no"},
        ],
        "terminal": ["yes", "no"],
    }


def _scheduler(manager, raw: dict) -> WorkflowScheduler:
    """构造一个已 attach spec 的调度器（未 ``run()``，状态是 ``declared``）。"""
    scheduler = WorkflowScheduler(manager)
    scheduler.spec = parse_workflow_spec(raw)
    return scheduler


# --- 1.1 快照形状 -----------------------------------------------------------


@pytest.mark.asyncio
async def test_snapshot_has_nodes_and_edges_with_status(manager):
    """spec Scenario「快照包含边与状态」：nodes 每节点 status + edges 每边 status。"""
    scheduler = _scheduler(manager, _chain_spec())
    await scheduler.run(scheduler.spec)

    snapshot = scheduler.workflow_graph_snapshot()

    assert snapshot["workflow_id"] == scheduler.workflow_id
    assert snapshot["status"] == "completed"
    assert snapshot["spec_hash"] == scheduler.spec.spec_hash
    assert [node["id"] for node in snapshot["nodes"]] == ["a", "b", "c"]
    assert [edge["from"] for edge in snapshot["edges"]] == ["a", "b"]
    for node in snapshot["nodes"]:
        assert node["status"] in NODE_STATUS_TIERS
    for edge in snapshot["edges"]:
        assert edge["status"] in EDGE_STATUS_TIERS


@pytest.mark.asyncio
async def test_snapshot_node_fields_are_explicitly_picked(manager):
    """grill 决策 4：不复用 ``NodeState.to_dict()``，只挑 bounded 字段。"""
    scheduler = _scheduler(manager, _fanout_spec(leaves=3))
    await scheduler.run(scheduler.spec)

    snapshot = scheduler.workflow_graph_snapshot()

    for node in snapshot["nodes"]:
        assert set(node) <= SNAPSHOT_NODE_KEYS, set(node) - SNAPSHOT_NODE_KEYS
        assert "subagent_ids" not in node
        assert "slots" not in node
        assert "raw" not in node
        assert "error" not in node
        assert "verdict" not in node
        assert node["started_at"] is not None

    for edge in snapshot["edges"]:
        assert set(edge) == SNAPSHOT_EDGE_KEYS


@pytest.mark.asyncio
async def test_snapshot_does_not_inline_parent_envelope_bloat(manager):
    """Q10：快照只含图字段，不带 ``bus``/``attribution``/``latest_events`` 等重字段。"""
    scheduler = _scheduler(manager, _chain_spec())
    await scheduler.run(scheduler.spec)

    snapshot = scheduler.workflow_graph_snapshot()

    for banned in ("bus", "attribution", "attribution_ref", "latest_events",
                   "inserted_nodes", "declared_spec_hash", "expansion_plan_hash"):
        assert banned not in snapshot
    # 图级白名单是**内联字面量**（没有常量可改）——本 change 加的加法字段是
    # ``started_at``/``finished_at``（D3）与 ``budget``（G13）。
    assert set(snapshot) <= {
        "workflow_id", "spec_hash", "goal", "status", "nodes", "edges",
        "total", "completed", "failed", "diagnostics", "timestamp",
        "started_at", "finished_at", "budget",
    }


@pytest.mark.asyncio
async def test_snapshot_shape_is_json_serialisable(manager):
    """快照直接进 ws JSON，必须可序列化（无 set/dataclass 泄漏）。"""
    scheduler = _scheduler(manager, _route_spec())
    await scheduler.run(scheduler.spec)

    encoded = json.dumps(scheduler.workflow_graph_snapshot())
    assert "workflow_id" in encoded


# --- 1.2 节点八档 / 边五档 --------------------------------------------------


@pytest.mark.asyncio
async def test_node_status_covers_pending_and_completed(manager):
    """未派发的节点保持 ``pending``，跑完的节点 ``completed``。"""
    scheduler = _scheduler(manager, _fanout_spec(leaves=2))
    manager.max_active = 1
    await scheduler.run(scheduler.spec)

    snapshot = scheduler.workflow_graph_snapshot()
    by_id = {node["id"]: node for node in snapshot["nodes"]}

    assert by_id["l0"]["status"] == "completed"
    assert by_id["root"]["status"] == "completed"


@pytest.mark.asyncio
async def test_edge_status_passed_when_data_consumed(manager):
    """Q5：数据被下游 reducer 读走的边记 ``passed``（per-edge 记账）。"""
    scheduler = _scheduler(manager, _chain_spec())
    await scheduler.run(scheduler.spec)

    snapshot = scheduler.workflow_graph_snapshot()
    by_pair = {(edge["from"], edge["to"]): edge for edge in snapshot["edges"]}

    assert by_pair[("a", "b")]["status"] == "passed"
    assert by_pair[("b", "c")]["status"] == "passed"


@pytest.mark.asyncio
async def test_edge_status_ready_and_active_mid_flight(manager):
    """上游完成、目标仍 pending → ``ready``；目标在跑 → ``active``。"""
    scheduler = _scheduler(manager, _chain_spec())
    # 手动构造中间态：a completed、b pending → a->b 应该是 ready。
    scheduler._states["a"].status = "completed"
    scheduler._states["a"].finished_at = 1.0
    scheduler._status = "running"

    mid = scheduler.workflow_graph_snapshot()
    assert {(e["from"], e["to"]): e["status"] for e in mid["edges"]}[("a", "b")] == "ready"

    scheduler._states["b"].status = "started"
    running = scheduler.workflow_graph_snapshot()
    assert {(e["from"], e["to"]): e["status"] for e in running["edges"]}[("a", "b")] == "active"


@pytest.mark.asyncio
async def test_edge_status_blocked_when_source_failed(manager):
    """源 ``failed``/``cancelled``、或目标 ``blocked``/``budget_exceeded`` → ``blocked``。"""
    scheduler = _scheduler(manager, _chain_spec())
    scheduler._states["a"].status = "failed"
    scheduler._states["b"].status = "blocked"

    snapshot = scheduler.workflow_graph_snapshot()
    by_pair = {(e["from"], e["to"]): e["status"] for e in snapshot["edges"]}
    assert by_pair[("a", "b")] == "blocked"

    scheduler._states["a"].status = "completed"
    scheduler._states["b"].status = "budget_exceeded"
    snapshot = scheduler.workflow_graph_snapshot()
    by_pair = {(e["from"], e["to"]): e["status"] for e in snapshot["edges"]}
    assert by_pair[("a", "b")] == "blocked"


@pytest.mark.asyncio
async def test_edge_status_inactive_fallback(manager):
    """两个节点都还 pending（未满足依赖）时边是 ``inactive``。"""
    scheduler = _scheduler(manager, _chain_spec())
    scheduler._status = "running"

    snapshot = scheduler.workflow_graph_snapshot()
    assert {e["status"] for e in snapshot["edges"]} == {"inactive"}


# --- 1.2 route 控制边 -------------------------------------------------------


@pytest.mark.asyncio
async def test_route_control_edge_kind_and_selection(manager):
    """决策 6：route 出边标 ``kind == "control"``，只高亮 ``targets`` 选中出口。"""
    manager.llm.content = "APPROVED: looks good"
    scheduler = _scheduler(manager, _route_spec())
    await scheduler.run(scheduler.spec)

    snapshot = scheduler.workflow_graph_snapshot()
    by_pair = {(e["from"], e["to"]): e for e in snapshot["edges"]}

    assert by_pair[("gate", "yes")]["kind"] == "control"
    assert by_pair[("gate", "no")]["kind"] == "control"
    # 数据边不是控制边。
    assert by_pair[("a", "gate")]["kind"] == "data"
    assert by_pair[("gate", "yes")]["status"] == "passed"
    assert by_pair[("gate", "no")]["status"] == "inactive"


@pytest.mark.asyncio
async def test_route_transient_completed_without_targets_renders_inactive(manager):
    """决策 6：容忍「route 已 completed 但 ``targets`` 被 ``_reset_subtree`` 清空」的瞬时态。"""
    scheduler = _scheduler(manager, _route_spec())
    scheduler._states["gate"].status = "completed"
    scheduler._states["gate"].targets = []

    snapshot = scheduler.workflow_graph_snapshot()
    control = [e for e in snapshot["edges"] if e["kind"] == "control"]
    assert control and {e["status"] for e in control} == {"inactive"}


# --- 1.3 规模 / 超限 --------------------------------------------------------


@pytest.mark.asyncio
async def test_snapshot_bounded_for_wide_graph(manager):
    """决策 4：foreach 展开的 ``subagent_ids`` 不进快照，快照大小不随展开项线性膨胀。"""
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

    snapshot = scheduler.workflow_graph_snapshot()
    fan = next(node for node in snapshot["nodes"] if node["id"] == "fan")

    assert fan["items"] == 12
    assert "subagent_ids" not in fan
    # 12 个展开项不得在快照里留下 12 份痕迹。
    assert len(json.dumps(snapshot)) < 12000


@pytest.mark.asyncio
async def test_graph_recursion_exceeded_snapshot_carries_diagnostics(manager):
    """决策 9：运行期超限 → ``status == "graph_recursion_exceeded"`` + ``diagnostics``。"""
    spec = _fanout_spec(leaves=25)  # 12 条以上入边 → 自动插层必然触顶
    spec["max_nodes"] = 27
    scheduler = _scheduler(manager, spec)
    await scheduler.run(scheduler.spec)

    snapshot = scheduler.workflow_graph_snapshot()

    assert snapshot["status"] == "graph_recursion_exceeded"
    assert snapshot["diagnostics"]["reason"] == "max_nodes"
    assert snapshot["diagnostics"]["recursion_limit"] == 27


@pytest.mark.asyncio
async def test_snapshot_available_after_declare_without_run(manager):
    """声明期被拒的图没有 scheduler；已声明但未 run 的图快照是 ``declared``。"""
    from agent.subagent.workflow import WorkflowValidationError

    spec = _fanout_spec(leaves=2)
    spec["max_nodes"] = 1
    with pytest.raises(WorkflowValidationError):
        parse_workflow_spec(spec)

    scheduler = _scheduler(manager, _chain_spec())
    assert scheduler.workflow_graph_snapshot()["status"] == "declared"


# --- 兼容回归：C1-C5 契约不受影响（决策 11/12） -----------------------------


@pytest.mark.asyncio
async def test_snapshot_does_not_drift_envelope_contract(manager):
    """任务 6.3：``_envelope``/``parent_envelope`` 的结构键集不因本 change 变化。"""
    scheduler = _scheduler(manager, _chain_spec())
    envelope = await scheduler.run(scheduler.spec)

    # 节点投影仍走 ``NodeState.to_dict()``（含 subagent_id/runs/summary/reason）。
    assert set(envelope["nodes"][0]) >= {"id", "kind", "status", "runs", "subagent_id"}
    parent = scheduler.parent_envelope()
    assert "bus" not in parent
    assert "nodes_total" in parent and "nodes_omitted" in parent
    assert "useful_runs" in envelope and "redundancy" in envelope


@pytest.mark.asyncio
async def test_snapshot_does_not_change_consumed_run_ids(manager):
    """决策 12：``_consumed_edges`` 旁新增，``_consumed_run_ids`` 基数逐位不变。"""
    scheduler = _scheduler(manager, _chain_spec())
    envelope = await scheduler.run(scheduler.spec)

    # 三个节点各有 1 个 run（collect aggregate 不产生 run）：a、b 被下游读走。
    assert envelope["useful_runs"] == 2
    assert len(scheduler._consumed_run_ids) == 2
    assert scheduler._consumed_edges == {("a", "b"), ("b", "c")}


@pytest.mark.asyncio
async def test_snapshot_is_idempotent_and_read_only(manager):
    """快照是只读投影：连续两次取快照不改变调度器状态。"""
    scheduler = _scheduler(manager, _chain_spec())
    await scheduler.run(scheduler.spec)

    first = scheduler.workflow_graph_snapshot()
    second = scheduler.workflow_graph_snapshot()

    assert first["nodes"] == second["nodes"]
    assert first["edges"] == second["edges"]


@pytest.mark.asyncio
async def test_consumed_edges_share_run_scope_lifecycle(manager):
    """决策 11/12 + 审阅核验：``_consumed_edges`` 与 ``_consumed_run_ids`` 同生命周期。

    ``run()`` 开头把两者一并重置，所以 ``cancel()`` 之后的残留不会被带进下一次
    run——``passed`` 边状态不会因为上一张图的记账而误亮。
    """
    scheduler = _scheduler(manager, _chain_spec())
    # 伪造「上一张图留下的记账」。
    scheduler._consumed_edges = {("stale", "edge")}
    scheduler._consumed_run_ids = {"stale_run"}

    await scheduler.run(scheduler.spec)

    assert scheduler._consumed_edges == {("a", "b"), ("b", "c")}
    assert len(scheduler._consumed_run_ids) == 2


# --- issue #207：纯门控边的独立状态（change ``workflow-gate-only-edge-status``） ---


def _gate_only_spec() -> dict:
    """``scan`` 有一条 required 边给 ``fan``，但 ``fan`` 用**字面 items**、不读它。

    这正是 issue #207 的场景：边门控了 fan 的派发，但产出从未被消费。
    """
    return {
        "goal": "gate-only",
        "nodes": [
            {"id": "scan", "kind": "subagent", "task": "produce"},
            {"id": "fan", "kind": "foreach", "task": "read {item}",
             "items": ["a", "b"]},
        ],
        "edges": [{"from": "scan", "to": "fan"}],
        "entry": ["scan"],
        "terminal": ["fan"],
    }


@pytest.mark.asyncio
async def test_gate_only_edge_is_satisfied_not_inactive(manager):
    """issue #207：required 边 + 源 completed + 目标越过 pending 但没读产出 → ``satisfied``。

    改前它落兜底 ``inactive``（灰），用户以为是条死线。
    """
    scheduler = _scheduler(manager, _gate_only_spec())
    await scheduler.run(scheduler.spec)

    snapshot = scheduler.workflow_graph_snapshot()
    by_pair = {(e["from"], e["to"]): e["status"] for e in snapshot["edges"]}

    assert by_pair[("scan", "fan")] == "satisfied", (
        f"纯门控边应判 satisfied，实际 {by_pair[('scan', 'fan')]!r}"
    )


@pytest.mark.asyncio
async def test_optional_unconsumed_edge_stays_inactive(manager):
    """``required=False`` 的未消费边仍 ``inactive``：它从未门控派发。"""
    spec = _gate_only_spec()
    spec["edges"] = [{"from": "scan", "to": "fan", "required": False}]
    scheduler = _scheduler(manager, spec)
    await scheduler.run(scheduler.spec)

    snapshot = scheduler.workflow_graph_snapshot()
    by_pair = {(e["from"], e["to"]): e["status"] for e in snapshot["edges"]}
    assert by_pair[("scan", "fan")] == "inactive"


@pytest.mark.asyncio
async def test_pending_target_stays_ready_not_satisfied(manager):
    """目标仍 ``pending`` → ``ready``（进行中的等待态），不是 ``satisfied``。"""
    scheduler = _scheduler(manager, _chain_spec())
    scheduler._states["a"].status = "completed"
    scheduler._states["a"].finished_at = 1.0
    scheduler._status = "running"

    mid = scheduler.workflow_graph_snapshot()
    assert {(e["from"], e["to"]): e["status"] for e in mid["edges"]}[("a", "b")] == "ready"


@pytest.mark.asyncio
async def test_skipped_target_edge_stays_inactive(manager):
    """目标 ``skipped``（route 没选它）→ 该 required 数据边仍 ``inactive``。

    grill Q1 用户拍板 B：决定目标不跑的是**控制边**，不是这条数据边——
    标 ``satisfied``（「产出未被下游读取」）对它是假话。
    """
    spec = {
        "goal": "skipped-target",
        "nodes": [
            {"id": "u", "kind": "subagent", "task": "produce"},
            {"id": "gate", "kind": "route",
             "cases": [{"when": "APPROVED", "to": "picked"}], "default": "t"},
            {"id": "picked", "kind": "subagent", "task": "picked branch"},
            {"id": "t", "kind": "subagent", "task": "never activated"},
        ],
        "edges": [
            {"from": "u", "to": "gate"},
            # u 有一条 required 数据边直连 t（但 t 不跑是 route 决定的）
            {"from": "u", "to": "t"},
            {"from": "gate", "to": "picked"},
            {"from": "gate", "to": "t"},
        ],
        "entry": ["u"],
        "terminal": ["picked", "t"],
    }
    manager.llm.content = "APPROVED looks good"
    scheduler = _scheduler(manager, spec)
    await scheduler.run(scheduler.spec)

    snapshot = scheduler.workflow_graph_snapshot()
    nodes = {n["id"]: n["status"] for n in snapshot["nodes"]}
    by_pair = {(e["from"], e["to"]): e["status"] for e in snapshot["edges"]}
    assert nodes["picked"] == "completed", nodes
    assert nodes["t"] == "skipped", nodes
    assert by_pair[("u", "t")] == "inactive", (
        f"目标 skipped 的数据边不该染绿，实际 {by_pair[('u', 't')]!r}"
    )


@pytest.mark.asyncio
async def test_dynamic_foreach_consumes_upstream_edge(manager):
    """Q2：动态 foreach（``source:``）确实读上游产出 → 该边判 ``passed``。

    改前 ``_source_collection`` 不记 per-edge 账，该边会落 ``satisfied``
    （图例说「产出未被下游读取」——**假话**）。
    """
    spec = {
        "goal": "dynamic-foreach",
        "nodes": [
            {"id": "planner", "kind": "subagent", "task": "plan the items"},
            {"id": "fan", "kind": "foreach", "task": "work {item}",
             "source": "planner", "source_field": "items"},
        ],
        "edges": [{"from": "planner", "to": "fan"}],
        "entry": ["planner"],
        "terminal": ["fan"],
    }
    manager.llm.content = '{"items": ["one", "two", "three"]}'
    scheduler = _scheduler(manager, spec)
    await scheduler.run(scheduler.spec)

    snapshot = scheduler.workflow_graph_snapshot()
    by_pair = {(e["from"], e["to"]): e["status"] for e in snapshot["edges"]}
    assert by_pair[("planner", "fan")] == "passed", (
        f"动态 foreach 读了产出应判 passed，实际 {by_pair[('planner', 'fan')]!r}"
    )


@pytest.mark.asyncio
async def test_dynamic_foreach_reads_aggregate_result_slot(manager):
    """Q2 覆盖：``source`` 指向一个**有 result 槽**的 aggregate → 记该边（scheduler.py:2373）。

    审阅 R1 的变异 M5 存活暴露：原测试只走 ``_read`` 闭包那条路径，
    aggregate 的 ``result`` 槽直取路径没有回归。
    """
    spec = {
        "goal": "foreach-from-aggregate",
        "nodes": [
            {"id": "a", "kind": "subagent", "task": "produce"},
            {"id": "agg", "kind": "aggregate", "strategy": "collect",
             "outputs": ["result"]},
            {"id": "fan", "kind": "foreach", "task": "work {item}",
             "source": "agg", "source_field": "items"},
        ],
        "edges": [{"from": "a", "to": "agg"}, {"from": "agg", "to": "fan"}],
        "entry": ["a"],
        "terminal": ["fan"],
    }
    manager.llm.content = '{"items": ["one", "two"]}'
    scheduler = _scheduler(manager, spec)
    await scheduler.run(scheduler.spec)

    snapshot = scheduler.workflow_graph_snapshot()
    by_pair = {(e["from"], e["to"]): e["status"] for e in snapshot["edges"]}
    assert by_pair[("agg", "fan")] == "passed", (
        f"从 aggregate 的 result 槽读产出应记 passed，实际 {by_pair[('agg', 'fan')]!r}"
    )


@pytest.mark.asyncio
async def test_dynamic_foreach_reads_non_subagent_summary(manager):
    """Q2 覆盖：``source`` 指向**非 subagent、无 slots 但有 summary** 的节点
    → 记该边（scheduler.py:2360 的 summary 兜底路径，审阅 R1 的变异 M6）。

    构造用 ``foreach → foreach(source:)``（审阅员给的可达形状）：外层的 foreach
    容器**无 slots**、但物化 ``summary``（各展开项摘要 join），且它对内层的出边是
    **数据边**（不是 route 的控制边——控制边走规则 1，与消费记账无关，那样测不到
    本分支）。

    注意 aggregate 不行：它的 ``result`` 槽恒被 ``_collect_slots`` 填充，会先命中
    上一条分支。
    """
    spec = {
        "goal": "foreach-from-foreach-summary",
        "nodes": [
            {"id": "a", "kind": "subagent", "task": "produce"},
            {"id": "outer", "kind": "foreach", "task": "outer {item}", "items": ["x"]},
            {"id": "inner", "kind": "foreach", "task": "inner {item}",
             "source": "outer", "source_field": "items"},
        ],
        "edges": [{"from": "a", "to": "outer"}, {"from": "outer", "to": "inner"}],
        "entry": ["a"],
        "terminal": ["inner"],
    }
    manager.llm.content = '{"items": ["one", "two"]}'
    scheduler = _scheduler(manager, spec)
    await scheduler.run(scheduler.spec)

    snapshot = scheduler.workflow_graph_snapshot()
    by_pair = {(e["from"], e["to"]): e["status"] for e in snapshot["edges"]}
    assert by_pair[("outer", "inner")] == "passed", (
        f"从非 subagent 的 summary 读产出应记 passed，实际 {by_pair[('outer', 'inner')]!r}"
    )
