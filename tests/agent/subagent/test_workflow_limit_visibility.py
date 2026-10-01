"""``DryRunWorkflow`` 报告的**结构闸可见性**契约（change ``workflow-limit-visibility``）。

本模块把 design.md 的 D1–D6 与 spec delta 的每条新 Scenario 固化成断言，分四组：

1. **`limits` 三段式**（D1）：报告顶层含 `recursion_limit` / `max_nodes` / `max_runs`
   的 `{declared, applied, clamped}`，与系统其余出口同源同形。dry run 不传 ceiling，
   故 `applied == declared`、`clamped is False`（**结构性事实**，非 bug）。
2. **`node_budget`（D2）**：`declared` / `graph_nodes` / `expanded_nodes` /
   `auto_inserted` / `limit` / `headroom`。`expanded_nodes` 取**闸门等价投影**
   （图节点数 + 各 foreach 展开项数）——撞闸图上它仍反映「展开完成后的计费规模」，
   故 `headroom < 0`（回归 `research/node_budget_probe.py` 的两个撞闸例）。
3. **route 条目（D3）+ diagnostics（D4）**：route 给出 `max_routes` 与 `gate_count`
   （同源 `_route_counts`），`runs` 结构性恒 0；`diagnostics` **无条件挂载**（未撞闸
   为 `{}`，镜像 `parent_envelope`）。
4. **调用级同源锁（D6）**：monkeypatch 既有函数返回**哨兵**，断言报告字段反映哨兵
   ——证明报告层**确实调用了**同源函数/读取了闸门字段，而非「值恰好相等」的假保护。
"""
import asyncio
import json

import pytest

import agent.subagent.scheduler as scheduler_module
from agent.config import AsterwyndConfig, SubagentsConfig, WorkflowLimitsConfig
from agent.llm import LLMResponse, Usage
from agent.run_config import AgentMode
from agent.subagent.manager import SubAgentManager
from agent.subagent.scheduler import WorkflowScheduler
from agent.tools.builtin.subagents import (
    DeclareWorkflowTool,
    DryRunWorkflowTool,
    parse_spec_for_manager,
)
from agent.workspace_policy import WorkspacePolicy

DEFAULT_MAX_NODES = 200


class _StubLLM:
    async def chat(self, messages, tools=None, model="gpt-4"):
        return LLMResponse(content="ok", stop_reason="end_turn", usage=Usage(5, 5))


def _manager(tmp_path, **workflow_overrides) -> SubAgentManager:
    cfg = AsterwyndConfig(
        subagents=SubagentsConfig(workflow=WorkflowLimitsConfig(**workflow_overrides))
    )
    return SubAgentManager(
        llm=_StubLLM(),
        config=cfg,
        parent_mode=AgentMode.BUILD,
        workspace_policy=WorkspacePolicy(workspace_root=tmp_path),
    )


@pytest.fixture
def manager(tmp_path) -> SubAgentManager:
    return _manager(tmp_path)


def _dry_run(manager, spec, **kwargs) -> dict:
    return json.loads(asyncio.run(DryRunWorkflowTool(manager).execute(spec=spec, **kwargs)))


# --- 语料 -------------------------------------------------------------------


def _foreach_spec(items: int) -> dict:
    """``fan(foreach) → agg(collect)``：展开项数 = items（可能触发自动汇合层）。"""
    return {
        "goal": "wide",
        "nodes": [
            {
                "id": "fan",
                "kind": "foreach",
                "items": [f"item-{i}" for i in range(items)],
                "task": "work {item}",
            },
            {"id": "agg", "kind": "aggregate", "strategy": "collect"},
        ],
        "edges": [{"from": "fan", "to": "agg", "reducer": "concat"}],
        "term": None,  # 占位，稍后删
        "terminal": ["agg"],
    }


def _clean(spec: dict) -> dict:
    return {key: value for key, value in spec.items() if key != "term"}


WIDE_FOREACH_SPEC = _clean(_foreach_spec(20))  # 20 项：触发自动插层（2 个 auto agg）
NARROW_FOREACH_SPEC = _clean(_foreach_spec(2))  # 2 项：不触发自动插层

#: 无 foreach、无自动插层：`expanded_nodes == graph_nodes`。
PLAIN_SPEC = {
    "goal": "plain",
    "nodes": [
        {"id": "a", "kind": "subagent", "task": "TASK-A"},
        {"id": "b", "kind": "subagent", "task": "TASK-B"},
    ],
    "edges": [{"from": "a", "to": "b"}],
    "terminal": ["b"],
}

#: ``producer → reviewer → gate(route) → [回边到 producer | done]``（S3 形态）：
#: route 读**直接上游** ``reviewer`` 的产出，``script`` 打在 reviewer 上让它按轮收敛。
ROUTE_SPEC = {
    "goal": "route",
    "nodes": [
        {"id": "producer", "kind": "subagent", "task": "TASK-PRODUCE"},
        {"id": "reviewer", "kind": "subagent", "task": "TASK-REVIEW"},
        {
            "id": "gate",
            "kind": "route",
            "max_routes": 4,
            "cases": [{"when": "GAPS", "to": "producer"}],
            "default": "done",
        },
        {"id": "done", "kind": "aggregate", "strategy": "collect"},
    ],
    "edges": [
        {"from": "producer", "to": "reviewer"},
        {"from": "reviewer", "to": "gate"},
        {"from": "gate", "to": "producer"},
        {"from": "gate", "to": "done"},
    ],
    "entry": ["producer"],
    "terminal": ["done"],
}


def _node(report: dict, node_id: str) -> dict:
    return next(n for n in report["nodes"] if n["id"] == node_id)


# --- 1. limits 三段式（D1） --------------------------------------------------


def test_report_exposes_three_gate_limits_in_three_part_shape(manager):
    report = _dry_run(manager, PLAIN_SPEC)
    limits = report["limits"]
    assert set(limits) == {"recursion_limit", "max_nodes", "max_runs"}
    for field, entry in limits.items():
        assert set(entry) == {"declared", "applied", "clamped"}, field
        assert isinstance(entry["declared"], int)
        assert isinstance(entry["applied"], int)


def test_dry_run_reports_applied_equal_to_declared_without_a_ceiling(manager):
    """dry run 构造 scheduler 不传 ceiling（结构性事实）：``applied == declared``。

    这不是 bug——它如实报「你这张图在当前会话直接运行时会生效的值」；钳制只发生在
    资产加载路径（见 ``notes`` 说明句）。
    """
    report = _dry_run(manager, PLAIN_SPEC)
    for entry in report["limits"].values():
        assert entry["applied"] == entry["declared"]
        assert entry["clamped"] is False


def test_clamp_is_real_when_a_ceiling_is_applied(manager):
    """钳制场景：直接构造带 ceiling 的 scheduler，``applied != declared``、``clamped`` True。

    证明三段式不是「永远同值」的装饰——同一函数在资产加载路径会真的钳。
    """
    spec = parse_spec_for_manager(manager, PLAIN_SPEC)
    scheduler = WorkflowScheduler(manager, limit_ceiling={"max_nodes": 1})
    scheduler.spec = spec
    limits = scheduler._limits_report()
    assert limits["max_nodes"]["declared"] == DEFAULT_MAX_NODES
    assert limits["max_nodes"]["applied"] == 1
    assert limits["max_nodes"]["clamped"] is True
    # 未钳的两项仍如实报 clamped False
    assert limits["recursion_limit"]["clamped"] is False
    assert limits["max_runs"]["clamped"] is False


# --- 2. node_budget（D2） ----------------------------------------------------


def test_node_budget_counts_foreach_items_in_the_expanded_projection(manager):
    """宽扇入图（20 项）：``expanded_nodes == graph_nodes + 20``（闸门计费口径）。"""
    report = _dry_run(manager, WIDE_FOREACH_SPEC)
    budget = report["node_budget"]
    assert budget["graph_nodes"] == 4  # fan + agg + 2 个自动汇合层
    assert budget["auto_inserted"] == 2
    assert budget["declared"] == 2  # fan + agg（模型声明的节点）
    assert budget["expanded_nodes"] == budget["graph_nodes"] + 20
    assert budget["expanded_nodes"] == 24
    assert budget["limit"] == DEFAULT_MAX_NODES
    assert budget["headroom"] == budget["limit"] - budget["expanded_nodes"]
    assert budget["headroom"] == DEFAULT_MAX_NODES - 24


def test_node_budget_narrow_foreach_expands_but_does_not_insert(manager):
    """窄扇入图（2 项）：``expanded_nodes != graph_nodes``（含 foreach 项，无自动插层）。"""
    report = _dry_run(manager, NARROW_FOREACH_SPEC)
    budget = report["node_budget"]
    assert budget["graph_nodes"] == 2
    assert budget["auto_inserted"] == 0
    assert budget["expanded_nodes"] == budget["graph_nodes"] + 2
    assert budget["headroom"] == DEFAULT_MAX_NODES - 4


def test_node_budget_expanded_equals_graph_nodes_without_foreach(manager):
    """无 foreach、无插层：三项相等（避免模型在大图上学到「差值恒存在」）。"""
    report = _dry_run(manager, PLAIN_SPEC)
    budget = report["node_budget"]
    assert budget["graph_nodes"] == 2
    assert budget["auto_inserted"] == 0
    assert budget["expanded_nodes"] == budget["graph_nodes"]
    assert budget["headroom"] == budget["limit"] - budget["graph_nodes"]


@pytest.mark.parametrize("max_nodes", [5, 23])
def test_node_budget_headroom_is_negative_on_a_tripped_graph(tmp_path, max_nodes):
    """撞闸图（``max_nodes`` 配成 5 与 23，20 项 foreach）：``headroom < 0``。

    回归 ``research/node_budget_probe.py`` 的两个撞闸例：两个既有计数
    （``len(plan.nodes)`` 与 ``_expanded_nodes``）在撞闸图上都报**正**余量，正是本
    change 要消灭的假面。``expanded_nodes`` 取闸门投影后必须如实报「超了」。
    """
    manager = _manager(tmp_path, max_nodes=max_nodes)
    report = _dry_run(manager, WIDE_FOREACH_SPEC)
    assert report["run_status"] == "graph_recursion_exceeded"
    budget = report["node_budget"]
    assert budget["expanded_nodes"] == 24, "撞闸后仍须反映展开完成后的计费规模"
    assert budget["limit"] == max_nodes
    assert budget["headroom"] == max_nodes - 24
    assert budget["headroom"] < 0, "一张已经撞闸的图不得显示出「还有余量」"


@pytest.mark.parametrize("max_nodes", [2, 3])
def test_headroom_negative_when_auto_insert_layer_trips_the_gate(tmp_path, max_nodes):
    """**自动插层**这一步就撞 ``max_nodes`` 时，``headroom`` 仍为负。

    这条路径在 ``_expand_plan`` 处 raise，早于 ``_check_foreach_budget``——若投影只在
    后者记录，此图会报出正余量（``max_nodes=3`` → 报 1），与「撞闸图不得显示余量」矛盾。
    """
    manager = _manager(tmp_path, max_nodes=max_nodes)
    report = _dry_run(manager, WIDE_FOREACH_SPEC)
    assert report["run_status"] == "graph_recursion_exceeded"
    assert report["diagnostics"].get("reason") == "max_nodes"
    budget = report["node_budget"]
    assert budget["expanded_nodes"] == 24, "自动插层撞闸也要如实报展开后的计费规模"
    assert budget["headroom"] == max_nodes - 24
    assert budget["headroom"] < 0


def test_node_budget_baseline_differs_when_auto_layer_is_rejected(tmp_path):
    """自动插层撞闸图（review Issue 1）：``graph_nodes``/``auto_inserted`` 反映**已落地**
    计划，``expanded_nodes`` 反映**投影**，二者基线不同——``expanded`` 可大于
    ``graph_nodes + Σitems``（差额 = 被拒的自动层）。

    回归 ``max_nodes=3`` + 20 项：落地计划停在 ``graph_nodes=2 / auto_inserted=0``，
    但投影为 ``2 + 2 + 20 = 24``。``notes`` 与 spec delta 必须承认这一差额，不得声称
    无条件等式 ``expanded == graph_nodes + Σitems``（那会构成新的模型误读面）。
    """
    manager = _manager(tmp_path, max_nodes=3)
    report = _dry_run(manager, WIDE_FOREACH_SPEC)
    assert report["run_status"] == "graph_recursion_exceeded"
    budget = report["node_budget"]
    assert budget["graph_nodes"] == 2, "被拒的自动层从未落地"
    assert budget["auto_inserted"] == 0
    assert budget["expanded_nodes"] == 24
    # 无条件等式在此路径上不成立（2 + 20 = 22 ≠ 24）——差额正是被拒的 2 个自动层
    assert budget["expanded_nodes"] != budget["graph_nodes"] + 20
    assert budget["headroom"] == 3 - 24
    assert budget["headroom"] < 0
    # 已落地计划下（max_nodes=200）等式成立，作为对照
    ok = _dry_run(_manager(tmp_path), WIDE_FOREACH_SPEC)["node_budget"]
    assert ok["expanded_nodes"] == ok["graph_nodes"] + 20


# --- 3. route 条目（D3）+ diagnostics（D4） ---------------------------------


def test_route_entry_exposes_max_routes_and_gate_count(manager):
    """route 条目给出生效 ``max_routes`` 与闸门计数 ``gate_count``。

    无 ``script``：route 恰好被判定一次（reviewer 的替身产出不匹配 GAPS）。
    """
    report = _dry_run(manager, ROUTE_SPEC)
    gate = _node(report, "gate")
    assert gate["max_routes"] == 4
    assert gate["gate_count"] == 1
    assert gate["evaluated"] is True


def test_route_gate_count_coexists_with_structurally_zero_runs(manager):
    """route 的 ``runs`` 结构性恒 0（它不跑模型），``gate_count`` 才是闸门计数。

    两者并列**不是矛盾**：``notes`` 须说明这一点（R3）。这里 route 走了多轮
    （``script`` 让 reviewer 先两轮 GAPS、再收敛），故 ``gate_count > 1``。
    """
    report = _dry_run(manager, ROUTE_SPEC, script={"reviewer": ["GAPS", "GAPS"]})
    gate = _node(report, "gate")
    assert gate["runs"] == 0
    assert gate["gate_count"] > 1, "多轮 route 的闸门计数应当累计"


def test_diagnostics_is_mounted_unconditionally_even_when_empty(manager):
    """未撞闸图：``diagnostics`` 仍**存在**且为空对象（镜像 ``parent_envelope``）。"""
    report = _dry_run(manager, PLAIN_SPEC)
    assert "diagnostics" in report
    assert report["diagnostics"] == {}
    assert report["run_status"] == "completed"


def test_diagnostics_carries_the_gate_name_on_a_trip(tmp_path):
    """撞闸图：``diagnostics`` 结构化地报出闸名（不只在散文 warning 里）。"""
    manager = _manager(tmp_path, max_nodes=5)
    report = _dry_run(manager, WIDE_FOREACH_SPEC)
    assert report["run_status"] == "graph_recursion_exceeded"
    assert report["diagnostics"].get("reason") == "max_nodes"
    assert report["diagnostics"].get("limit") == 5


def test_notes_explain_the_new_fields(manager):
    """D1/D2/D3/D4 的口径说明句进 ``notes``（避免模型误读新字段）。"""
    text = " ".join(_dry_run(manager, PLAIN_SPEC)["notes"]).lower()
    assert "clamp" in text  # clamped 恒 false 的原因
    assert "expanded_nodes" in text or "expanded" in text  # expanded vs graph_nodes
    assert "gate_count" in text  # route runs 恒 0 与 gate_count
    assert "diagnostic" in text  # 诊断非空 != 撞闸
    # review Issue 1：撞闸图上 graph_nodes/auto_inserted 与 expanded_nodes 基线不同
    assert "landed" in text or "reject" in text


# --- 4. 调用级同源锁（D6，非值相等） ----------------------------------------


def test_limits_are_read_from_the_shared_reporter_not_recomputed(manager, monkeypatch):
    """哨兵锁：报告 ``limits`` **确实调用** ``limits_report``，而非自己重算。

    「值相等」是假保护（无 ceiling 时重算恰好同值）；哨兵能证明调用确实发生。
    """
    sentinel = {
        "recursion_limit": {"declared": -7, "applied": -8, "clamped": True},
        "max_nodes": {"declared": -9, "applied": -10, "clamped": True},
        "max_runs": {"declared": -11, "applied": -12, "clamped": True},
    }
    calls: list = []

    def _fake(spec, ceiling):
        calls.append(spec)
        return sentinel

    monkeypatch.setattr(scheduler_module, "limits_report", _fake)
    report = _dry_run(manager, PLAIN_SPEC)
    assert report["limits"] == sentinel
    assert calls, "报告没有调用 limits_report——它是自己重算的"


def test_expanded_nodes_reads_the_gate_projection_field(manager, monkeypatch):
    """哨兵锁：``expanded_nodes`` 取自闸门记录的投影字段，不在报告层重算。

    把闸门投影字段强制成哨兵后，报告必须反映哨兵——重算会得到 24 而与哨兵不符。
    """
    sentinel = 987654
    original = WorkflowScheduler._check_foreach_budget

    def _patched(self, node, state):
        original(self, node, state)
        self._projected_expanded_nodes = sentinel

    monkeypatch.setattr(WorkflowScheduler, "_check_foreach_budget", _patched)
    report = _dry_run(manager, WIDE_FOREACH_SPEC)
    assert report["node_budget"]["expanded_nodes"] == sentinel


def test_node_budget_limit_reads_the_effective_limit(manager, monkeypatch):
    """哨兵锁：``node_budget.limit`` 取自 ``_eff_limit('max_nodes')``。"""
    sentinel = 123456
    original = WorkflowScheduler._eff_limit

    def _patched(self, field):
        return sentinel if field == "max_nodes" else original(self, field)

    monkeypatch.setattr(WorkflowScheduler, "_eff_limit", _patched)
    report = _dry_run(manager, NARROW_FOREACH_SPEC)
    assert report["node_budget"]["limit"] == sentinel
    assert report["node_budget"]["headroom"] == sentinel - report["node_budget"]["expanded_nodes"]


def test_gate_count_reads_the_scheduler_route_counter(manager, monkeypatch):
    """哨兵锁（review Issue 2）：route ``gate_count`` 取自 ``scheduler._route_counts``。

    与同文件另三处同源锁口径一致——证明报告**读取了**闸门计数，而非在报告层重算。
    """
    sentinel = 424242
    original = WorkflowScheduler._execute_route

    async def _patched(self, state):
        await original(self, state)
        # route 只执行一次（本语料不循环）；执行后把闸门计数替换成哨兵，
        # 报告若重算会得到真实值（1），若读取该字段则得到哨兵。
        self._route_counts = {state.node.id: sentinel}

    monkeypatch.setattr(WorkflowScheduler, "_execute_route", _patched)
    report = _dry_run(manager, ROUTE_SPEC)
    assert _node(report, "gate")["gate_count"] == sentinel


# --- 5. scheduler 侧：投影字段与判定行为 ------------------------------------


def _run_scheduler(manager, spec_dict):
    spec = parse_spec_for_manager(manager, spec_dict)
    scheduler = WorkflowScheduler(manager)
    result = asyncio.run(scheduler.run(spec))
    return scheduler, result


@pytest.mark.parametrize(
    "max_nodes, tripped, expanded",
    [(200, False, True), (5, True, True), (24, False, True), (23, True, True), (3, True, False)],
)
def test_projected_expanded_nodes_matches_gate_billing(
    tmp_path, max_nodes, tripped, expanded
):
    """闸门投影字段 == 图节点数 + Σ foreach items（撞闸时也如实）。

    ``max_nodes=3`` 走 ``_expand_plan``（自动插层就超限）这条早于
    ``_check_foreach_budget`` 的撞闸路径——自动插层从未落地（``plan.nodes`` 停在 2），
    但投影仍须为「展开完成后的计费规模」= 2 声明 + 2 自动 + 20 项 = 24。
    """
    manager = _manager(tmp_path, max_nodes=max_nodes)
    scheduler, result = _run_scheduler(manager, WIDE_FOREACH_SPEC)
    assert scheduler._projected_expanded_nodes == 24
    if expanded:
        assert scheduler._projected_expanded_nodes == len(scheduler._plan.nodes) + 20
    else:
        # 自动插层撞闸：plan 未落地新层，图节点数停在声明值
        assert len(scheduler._plan.nodes) == 2
    assert (result["status"] == "graph_recursion_exceeded") is tripped


def test_projected_field_does_not_change_max_nodes_rejection(tmp_path):
    """只增字段、不改判定：既有 ``max_nodes`` 拒绝行为逐字不变。"""
    manager = _manager(tmp_path, max_nodes=5)
    scheduler, result = _run_scheduler(manager, WIDE_FOREACH_SPEC)
    assert result["status"] == "graph_recursion_exceeded"
    assert scheduler._diagnostics.get("reason") == "max_nodes"
    assert scheduler._diagnostics.get("limit") == 5
    # 既有的高水位计数字段语义不变：撞闸时仍停在展开前的值
    assert scheduler._expanded_nodes == len(scheduler._plan.nodes) == 4


def test_declare_description_discloses_graph_level_gate_defaults():
    """D5：``DeclareWorkflow`` 描述披露图级三闸**模块默认值**（值，非示例）。"""
    desc = DeclareWorkflowTool.description
    lowered = desc.lower()
    for field in ("recursion_limit", "max_nodes", "max_runs"):
        assert field in lowered, field
    assert "100" in desc
    assert "200" in desc
    assert "300" in desc
    assert "default" in lowered
    # 限定为「图级」并指向报告生效值（避免与路由级 max_routes 默认 1 混淆、避免与
    # 运行期配置分叉）
    assert "graph-level" in lowered or "图级" in desc
    assert "effective" in lowered
