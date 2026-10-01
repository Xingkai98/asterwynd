"""``DryRunWorkflow``：零 token 模拟执行 workflow 的报告契约（change ``workflow-dry-run``）。

本模块把 design.md 的 D1–D10 与 spec delta 的每条 Scenario 固化成断言，分三组：

1. **隔离**（T-1…T-4、T-2a）：模拟不得碰调用方的 workspace / 注册表 / 真实 LLM / 图事件
   sink，且不产生 workflow 级 artifact。**隔离断言都是一次性 manager + 一次性
   ``workspace_root`` 的结果，不是实现约定**——所以每条都配了「变异验证」：把喂给模拟
   的依赖改坏，断言必须变红（见 ``test_isolation_assertions_are_discriminating`` /
   ``test_zero_token_assertion_is_discriminating`` / ``test_pollution_guard_is_discriminating``）。
2. **数据流**（T-5…T-9b）：``received`` 按 ``(node_id, item_index)`` 寻址、route 的
   ``input_seen`` 与 ``input_sources``、``script`` 注入、回边不投递文本、聚合产出不被
   替身污染。
3. **契约**（T-10…T-14）：有界性、边界声明、schema parity、工具面、``script`` 数组按
   调用次序消费。

**为什么这些断言不是「恒真的结构性断言」**（grill I9 的教训）：真实 manager 从不被交给
调度器，所以单看 ``real.llm.chat == 0`` 无法区分「隔离生效」与「实现根本没碰 llm」。本模块
用「变异」把它变成可证的：变异体确实会让断言变红（``_mutant_manager_factory``）。
"""
import asyncio
import json
from pathlib import Path

import pytest

import agent.tools.builtin.subagents as subagents_module
from agent.config import AsterwyndConfig
from agent.llm import LLMResponse, Usage
from agent.run_config import AgentMode
from agent.subagent.context import current_node_id
from agent.subagent.manager import SPAWN_TOOL_NAMES, SubAgentManager
from agent.workspace_policy import WorkspacePolicy
from agent.tools.builtin.subagents import (
    DRY_RUN_DEFAULT_MAX_REPORT_CHARS,
    DRY_RUN_HARD_CALL_LIMIT,
    DRY_RUN_SOFT_CALL_HINT,
    DeclareWorkflowTool,
    DryRunWorkflowTool,
    _workflow_spec_schema,
)


class _RecordingLLM:
    """真实 manager 的 LLM：只用来数「有没有被碰到」。"""

    def __init__(self) -> None:
        self.chat_calls = 0

    async def chat(self, messages, tools=None, model="gpt-4"):
        self.chat_calls += 1
        return LLMResponse(content="real-model", stop_reason="end_turn", usage=Usage(5, 5))


@pytest.fixture
def llm() -> _RecordingLLM:
    return _RecordingLLM()


@pytest.fixture
def manager(tmp_path, llm) -> SubAgentManager:
    return SubAgentManager(
        llm=llm,
        config=AsterwyndConfig(),
        parent_mode=AgentMode.BUILD,
        workspace_policy=WorkspacePolicy(workspace_root=tmp_path),
    )


def _dry_run(manager, spec, **kwargs) -> dict:
    return json.loads(asyncio.run(DryRunWorkflowTool(manager).execute(spec=spec, **kwargs)))


def _node(report: dict, node_id: str) -> dict:
    return next(n for n in report["nodes"] if n["id"] == node_id)


def _snapshot(root: Path) -> dict:
    return {
        str(p.relative_to(root)): p.stat().st_size
        for p in sorted(Path(root).rglob("*"))
        if p.is_file()
    }


# --- 图（每条 Scenario 一张） ----------------------------------------------

#: S1：``a → mid → gate(route)``——gate 的直接上游是 subagent，其上游无 ``result`` 槽。
S1_SPEC = {
    "goal": "review a design",
    "nodes": [
        {"id": "a", "kind": "subagent", "task": "TASK-A"},
        {"id": "mid", "kind": "subagent", "task": "TASK-MID"},
        {
            "id": "gate",
            "kind": "route",
            "cases": [{"when": "GAPS", "to": "rework"}],
            "default": "report",
        },
        {"id": "rework", "kind": "subagent", "task": "TASK-REWORK"},
        {"id": "report", "kind": "subagent", "task": "TASK-REPORT"},
    ],
    "edges": [
        {"from": "a", "to": "mid"},
        {"from": "mid", "to": "gate"},
        {"from": "gate", "to": "rework"},
        {"from": "gate", "to": "report"},
    ],
    "entry": ["a"],
    "terminal": ["report"],
}

#: S2：``w1,w2 → merge(collect) → critic → gate``——route 的上游 critic 是 subagent，但
#: 它的上游 merge 物化了 ``result`` 槽，于是 route 读到**聚合槽值**而非 critic 的 summary。
S2_SPEC = {
    "goal": "review a design",
    "nodes": [
        {"id": "w1", "kind": "subagent", "task": "TASK-W1"},
        {"id": "w2", "kind": "subagent", "task": "TASK-W2"},
        {"id": "merge", "kind": "aggregate", "strategy": "collect", "outputs": ["result"]},
        {"id": "critic", "kind": "subagent", "task": "TASK-CRITIC"},
        {
            "id": "gate",
            "kind": "route",
            "cases": [{"when": "GAPS", "to": "rework"}],
            "default": "report",
        },
        {"id": "rework", "kind": "subagent", "task": "TASK-REWORK"},
        {"id": "report", "kind": "subagent", "task": "TASK-REPORT"},
    ],
    "edges": [
        {"from": "w1", "to": "merge", "reducer": "concat"},
        {"from": "w2", "to": "merge", "reducer": "concat"},
        {"from": "merge", "to": "critic"},
        {"from": "critic", "to": "gate"},
        {"from": "gate", "to": "rework"},
        {"from": "gate", "to": "report"},
    ],
    "entry": ["w1", "w2"],
    "terminal": ["report"],
}

#: S3：``producer → reviewer → gate(route) → [回边到 producer | done]``。
S3_SPEC = {
    "goal": "iterate",
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

#: 占位符是 ``{item}``（不是 ``$item``）：``render_item_task``，scheduler.py:369。
FOREACH_SPEC = {
    "goal": "propose",
    "nodes": [
        {
            "id": "fan",
            "kind": "foreach",
            "items": ["alpha", "beta", "gamma"],
            "task": "propose {item}",
        },
        {"id": "critic", "kind": "subagent", "task": "TASK-CRITIC"},
    ],
    "edges": [{"from": "fan", "to": "critic"}],
    "terminal": ["critic"],
}

#: 20 项 foreach 会触发自动汇合层插入（``fan_in > MAX_FAN_IN``）——system 插入 2 个
#: ``__auto_agg__*`` 节点，它们会真的跑，但**不在 spec.nodes 里**。
WIDE_FOREACH_SPEC = {
    "goal": "wide",
    "nodes": [
        {
            "id": "fan",
            "kind": "foreach",
            "items": [f"item-{i}" for i in range(20)],
            "task": "work {item}",
        },
        {"id": "agg", "kind": "aggregate", "strategy": "collect"},
    ],
    "edges": [{"from": "fan", "to": "agg", "reducer": "concat"}],
    "terminal": ["agg"],
}

#: 非正常结束：5 项 foreach 撞上 spec 的 ``max_runs: 3``。
FAILING_SPEC = {
    "goal": "will not finish",
    "max_runs": 3,
    "nodes": [
        {
            "id": "fan",
            "kind": "foreach",
            "items": [f"item-{i}" for i in range(5)],
            "task": "work {item}",
        },
        {"id": "gate", "kind": "route", "default": "done", "max_routes": 2},
        {"id": "done", "kind": "aggregate", "strategy": "collect"},
    ],
    "edges": [{"from": "fan", "to": "gate"}, {"from": "gate", "to": "done"}],
    "entry": ["fan"],
    "terminal": ["done"],
}


# --- T-1…T-4：隔离 ---------------------------------------------------------


def test_simulation_writes_nothing_to_the_callers_workspace(manager):
    """T-1（F1/F6）：真实 workspace 零新增文件。"""
    root = manager.workspace_policy.workspace_root
    (root / "sentinel.txt").write_text("keep me\n", encoding="utf-8")
    before = _snapshot(root)

    report = _dry_run(manager, S1_SPEC)

    assert report["simulated"] is True
    assert _snapshot(root) == before, "dry run 往调用方 workspace 落了盘"
    assert (root / "sentinel.txt").read_text(encoding="utf-8") == "keep me\n"


def test_simulation_leaves_the_callers_registry_empty(manager):
    """T-2（F3/F6）：真实 manager 的 workflow 注册表 / store 表保持为空。"""
    _dry_run(manager, S1_SPEC)

    assert list(manager._workflows) == []
    assert list(manager._workflow_stores) == []


def test_simulation_keeps_workflow_artifacts_out_of_the_throwaway_dir(manager, tmp_path):
    """T-2a（Q2=B / G2）：模拟不产生 workflow 级 artifact（``events.jsonl``/``root.txt``）。

    一次性临时目录里**仍有** W1（``manager._write_result_artifacts``）写的 per-run 文件
    ——那是隔离机制的实现细节，随 ``TemporaryDirectory`` 清理；``_store`` 替换只影响
    W2（``events.jsonl``/``root.txt``/归因）这两个/三个文件。所以本用例断言的是
    「W2 的产物一个都没有」，不是「临时目录是空的」。
    """
    seen: list[str] = []
    real_temporary_directory = subagents_module.tempfile.TemporaryDirectory

    def _spy(*args, **kwargs):
        handle = real_temporary_directory(*args, **kwargs)
        seen.append(handle.name)
        return handle

    subagents_module.tempfile.TemporaryDirectory = _spy
    try:
        _dry_run(manager, S1_SPEC)
    finally:
        subagents_module.tempfile.TemporaryDirectory = real_temporary_directory

    assert seen, "模拟没有走一次性临时目录"
    leftovers = sorted(Path(seen[0]).rglob("*"))
    names = {p.name for p in leftovers if p.is_file()}
    assert "events.jsonl" not in names, f"W2 的事件日志被写出了：{sorted(names)}"
    assert "root.txt" not in names, f"W2 的根结果被写出了：{sorted(names)}"
    assert not list(Path(seen[0]).rglob("*.attribution"))


def test_simulation_makes_no_real_llm_calls(manager, llm):
    """T-3（F4）：真实 ``manager.llm.chat`` 调用数 = 0。

    这条断言的**变异验证**见 ``test_zero_token_assertion_is_discriminating``。
    """
    report = _dry_run(manager, S2_SPEC)

    assert report["llm_calls"] > 0, "模拟本身一次替身调用都没有——说明图根本没跑"
    assert llm.chat_calls == 0


def test_simulation_never_touches_the_callers_graph_sink(manager):
    """T-4（F2）：真实 manager 的 ``graph_sink`` 未被调用。"""
    frames: list[tuple[str, dict]] = []
    manager.graph_sink = lambda event_type, data: frames.append((event_type, data))

    _dry_run(manager, S2_SPEC)

    assert frames == []


def test_zero_token_assertion_is_discriminating(manager, llm, monkeypatch):
    """T-3 的**变异验证**（grill I9 订正后的正确形态），常驻 CI。

    「把假 LLM 换回真 LLM」证明不了什么——真实 manager 从不被交给调度器，所以
    ``real.llm.chat == 0`` 会**结构性恒真**。正确的变异是**让模拟 manager 复用真实
    manager 的 ``llm`` 对象**：此时真实 LLM 立刻被调用，T-3 的断言必然变红。
    """
    _mutant_manager_factory(monkeypatch, manager, llm=llm)

    _dry_run(manager, S1_SPEC)

    assert llm.chat_calls > 0, (
        "变异体没有碰到真实 LLM——T-3 的断言无法区分「隔离生效」与「根本没接线」"
    )


def test_isolation_assertions_are_discriminating(manager, monkeypatch):
    """T-1 的**变异验证**：把一次性 ``workspace_root`` 换成真实 workspace。

    变异点正是隔离的**独立充分条件**（D4/F9）：写入口有两个，但都以
    ``workspace_policy.workspace_root`` 为路径根。这里把喂给模拟 manager 的
    workspace_policy 换成真实的那一份——磁盘上必然出现新增文件，T-1 的断言变红。
    """
    root = manager.workspace_policy.workspace_root
    before = _snapshot(root)
    _mutant_manager_factory(monkeypatch, manager, workspace_policy=manager.workspace_policy)

    _dry_run(manager, S1_SPEC)

    assert _snapshot(root) != before, (
        "变异体没有往真实 workspace 落盘——T-1 的断言无法证明隔离真的在起作用"
    )


def _mutant_manager_factory(monkeypatch, manager, **overrides):
    """把 ``subagents`` 模块里的 ``SubAgentManager`` 换成「忽略传入依赖」的变异体。

    ``overrides`` 里的键会**覆盖**模拟驱动传进去的实参（如 ``llm`` / ``workspace_policy``）
    ——这正是「隔离失效」那一类 bug 的形态。
    """
    original = subagents_module.SubAgentManager

    def _mutant(**kwargs):
        kwargs.update(overrides)
        return original(**kwargs)

    monkeypatch.setattr(subagents_module, "SubAgentManager", _mutant)


# --- T-5…T-9b：数据流 ------------------------------------------------------


def test_received_shows_each_foreach_item_with_its_own_task(manager):
    """T-5/T-5a（G1）：foreach 展开项各自的 prompt 分别可见，且互不坍缩。

    ``current_node_id()`` 对每个展开项返回**同一个** id（实测 G1），所以若 ``received``
    按 node id 单键建表，3 项会坍缩成 1 项（``research/foreach_gap.py`` 实证）。
    **变异验证**：把 ``received`` 改回 ``received[node_id]`` 单键写法 → 本条必红。
    """
    report = _dry_run(manager, FOREACH_SPEC)

    fan = _node(report, "fan")
    prompts = [entry["prompt"] for entry in fan["received"]]
    assert len(prompts) == 3, f"foreach 的三项坍缩了：{prompts}"
    assert sorted(prompts) == [
        "propose alpha",
        "propose beta",
        "propose gamma",
    ]
    # 占位符是 ``{item}``：替换真的发生了（不是原样留着 "propose {item}"）。
    assert all("{item}" not in prompt for prompt in prompts)


def test_received_shows_upstream_text_delivered_to_a_downstream_node(manager):
    """T-5（续）：下游节点的 prompt 含上游投递的文本。"""
    report = _dry_run(manager, FOREACH_SPEC)

    critic = _node(report, "critic")
    assert len(critic["received"]) == 1
    prompt = critic["received"][0]["prompt"]
    assert "Input from fan" in prompt
    assert "TASK-CRITIC" in prompt


def test_report_lists_auto_inserted_merge_layers(manager):
    """T-5b（G3）：报告基于**执行计划**，自动插入的汇合层可见且可区分。

    **变异验证**：把节点枚举从 ``scheduler._plan.nodes`` 改回 ``spec.nodes`` → 本条必红
    （``research/extra_calls.py`` 实证：20 项 foreach 实际跑 4 个节点，``spec.nodes`` 只有 2 个）。
    """
    report = _dry_run(manager, WIDE_FOREACH_SPEC)

    declared = {node["id"] for node in WIDE_FOREACH_SPEC["nodes"]}
    auto = [n for n in report["nodes"] if n["auto_inserted"]]
    assert auto, "自动插入的汇合层没有进报告：调用方会以为「只有我声明的节点会跑」"
    assert all(n["id"] not in declared for n in auto)
    assert all(n["kind"] == "aggregate" for n in auto)
    # 声明节点不被误标。
    assert all(not _node(report, node_id)["auto_inserted"] for node_id in declared)
    # 自动层真的跑了（它们会调 LLM）。
    assert any(n["runs"] >= 1 for n in auto)


def test_route_input_seen_is_the_direct_upstream_output(manager):
    """T-6（S1）：``a → mid → gate`` 时 gate 读的是 ``mid`` 自身的产出。"""
    report = _dry_run(manager, S1_SPEC, script={"mid": "MID-SAYS-GAPS"})

    gate = _node(report, "gate")
    mid = _node(report, "mid")
    assert mid["produced"] == "MID-SAYS-GAPS"
    assert gate["input_seen"] == mid["produced"]
    assert "TASK-A" not in gate["input_seen"]


def test_route_input_seen_falls_back_to_the_aggregate_slot(manager):
    """T-7（S2）：``merge(collect) → critic → gate`` 时 gate 读到的是**聚合槽值**。

    **本用例断言的是「报告如实反映现状」，不是「现状是对的」**（design D2 / R9）：
    ``_node_output``（scheduler.py:2478-2486）先查上游自己的槽（仅非 subagent），
    否则沿数据入边向上找第一个有该槽的上游——merge 物化了 ``result`` 槽、critic 是
    subagent 永不写自己的槽，于是 route 读到的「critic 的产出」实际是 merge 的聚合结果。
    S2 是一条**没有测试保护的现存语义**；把它写成断言有两个作用：(1) 锁住 dry run 的
    报告正确性；(2) 让它显式化——未来改 ``_node_output`` 会立刻看到「这会影响报告」。
    """
    report = _dry_run(manager, S2_SPEC)

    gate = _node(report, "gate")
    merge = _node(report, "merge")
    critic = _node(report, "critic")
    assert gate["input_seen"] == merge["produced"]
    assert gate["input_seen"] != critic["produced"]


def test_route_input_is_attributable_to_a_source_node(manager):
    """T-7a（Q6）：判定输入带**来源节点 id**，调用方不必拿文本去比对推断。

    这是 S2 机制导致的报告缺口：只给文本时，截断后可能比对不出它来自哪个节点。
    """
    report = _dry_run(manager, S2_SPEC)

    gate = _node(report, "gate")
    assert gate["input_sources"] == [{"from": "critic", "resolved_to": "merge"}], (
        "边的 source 是 critic，但判定文本来自 merge 的聚合槽——报告必须把归属说清"
    )
    # S1 形态下归属就是直接上游自己。
    s1 = _node(_dry_run(manager, S1_SPEC), "gate")
    assert s1["input_sources"] == [{"from": "mid", "resolved_to": "mid"}]


def test_route_input_sources_concatenate_to_input_seen(manager):
    """T-7a 的一致性断言：``resolved_to`` 各节点的产出按序拼接 SHALL 等于 ``input_seen``。

    这条让「第二份真相漂移」无法悄悄发生：实现若复制了 ``_node_output`` 的取值逻辑，
    拼接结果就会与调度器真正用的判定文本分叉。（``_route_verdict`` 用 ``"\\n".join``
    把各数据入边的判定文本拼起来——本用例复刻的是同一个拼接方式。）
    """
    for spec in (S1_SPEC, S2_SPEC):
        report = _dry_run(manager, spec)
        gate = _node(report, "gate")
        joined = "\n".join(
            _node(report, source["resolved_to"])["produced"]
            for source in gate["input_sources"]
        )
        assert joined == gate["input_seen"]


def test_route_input_sources_cover_every_data_edge_in_order(manager):
    """T-7a（多数据入边）：列表按 ``input_seen`` 的拼接顺序给每条数据入边一项。"""
    spec = {
        "goal": "two inputs",
        "nodes": [
            {"id": "left", "kind": "subagent", "task": "TASK-L"},
            {"id": "right", "kind": "subagent", "task": "TASK-R"},
            {
                "id": "gate",
                "kind": "route",
                "cases": [{"when": "NOPE", "to": "end"}],
                "default": "end",
            },
            {"id": "end", "kind": "aggregate", "strategy": "collect"},
        ],
        "edges": [
            {"from": "left", "to": "gate", "reducer": "concat"},
            {"from": "right", "to": "gate", "reducer": "concat"},
            {"from": "gate", "to": "end"},
        ],
        "entry": ["left", "right"],
        "terminal": ["end"],
    }
    report = _dry_run(manager, spec, script={"left": "L-OUT", "right": "R-OUT"})

    gate = _node(report, "gate")
    assert gate["input_sources"] == [
        {"from": "left", "resolved_to": "left"},
        {"from": "right", "resolved_to": "right"},
    ]
    assert gate["input_seen"] == "L-OUT\nR-OUT"
    assert "\n".join(
        _node(report, s["resolved_to"])["produced"] for s in gate["input_sources"]
    ) == gate["input_seen"]


def test_script_injection_steers_the_route(manager):
    """T-8（S4）：不传 ``script`` → route 走 default；注入命中 case → 走对应分支。

    **图形态必须是 ``a(subagent) → mid(subagent) → gate(route)``**（不是
    ``agg → critic → gate``）：后者的 route 读的是聚合槽（S2），``script:{"critic": ...}``
    根本不会改变走向（grill I3 的实测结论）。
    """
    blind = _dry_run(manager, S1_SPEC)
    blind_gate = _node(blind, "gate")
    assert blind_gate["matched"] is None
    assert blind_gate["used_default"] is True
    assert blind_gate["walked_to"] == ["report"]

    steered = _dry_run(manager, S1_SPEC, script={"mid": "GAPS: missing tests"})
    gate = _node(steered, "gate")
    assert gate["matched"] == "GAPS"
    assert gate["used_default"] is False
    assert gate["walked_to"] == ["rework"]
    assert _node(steered, "rework")["status"] == "completed"
    assert _node(steered, "report")["status"] != "completed"


def test_unscripted_nodes_are_marked_as_stand_in_output(manager):
    """未注入的节点产出可被识别为**模拟占位**，不会被当成真实模型产出。"""
    report = _dry_run(manager, S1_SPEC)
    produced = _node(report, "mid")["produced"]
    # 占位文本带节点名 + 显式的 stand-in 标记。
    assert "mid" in produced
    assert "auto" in produced
    assert produced != _node(report, "a")["produced"]


def test_failed_nodes_carry_an_explainable_reason(manager):
    """T-8a：非正常结束的节点带可解释原因，且不被读成「拓扑本来如此」。"""
    report = _dry_run(manager, FAILING_SPEC)

    fan = _node(report, "fan")
    assert fan["status"] == "failed"
    assert fan.get("reason"), "失败节点只给了 status，调用方无从判断是图的问题还是模拟的问题"
    assert "max_runs" in fan["reason"]

    # 图没跑完这件事本身也必须在报告里可见。
    assert report["run_status"] == "graph_recursion_exceeded"
    assert report["warnings"], "图级未完成却没有一条 warning"

    # gate 从未判定过，所以它**不**报告成「走 default」——不会把失败读成拓扑答案。
    gate = _node(report, "gate")
    assert gate["status"] != "completed"
    assert gate.get("reason"), "被图级闸门挡住的节点也必须给原因"
    assert gate["evaluated"] is False
    assert gate["used_default"] is None, (
        "route 没跑到却报了 used_default——调用方会把「失败」读成「本来就该走 default」"
    )
    assert gate["walked_to"] == []

    # blocked/cancelled 的节点同样带原因（可能是调度器自己的中文因由）。
    done = _node(report, "done")
    assert done["status"] in {"blocked", "cancelled", "budget_exceeded", "failed"}
    assert done.get("reason")


def test_back_edge_delivers_no_new_text(manager):
    """T-9（S3）：回边重跑时被重派发节点每轮收到的 prompt **逐字相同**。

    这是那 17 条探针里最反直觉的一条（``research/rounds.py`` 实证），也是 ``script``
    数组形态存在的理由——只有第二轮才观察得到。
    """
    report = _dry_run(
        manager,
        S3_SPEC,
        script={"reviewer": ["GAPS: tests", "GAPS: docs", "APPROVED"]},
    )

    producer = _node(report, "producer")
    prompts = [entry["prompt"] for entry in producer["received"]]
    assert len(prompts) >= 3, f"环没有转起来（producer 只被调用 {len(prompts)} 次）"
    assert len(set(prompts)) == 1, f"回边向 producer 投递了新文本：{prompts}"
    assert producer["runs"] >= 3

    gate = _node(report, "gate")
    assert gate["matched"] is None and gate["used_default"] is True
    assert gate["walked_to"] == ["done"]
    # 回边是控制边：它不承载数据。
    back = next(e for e in report["edges"] if e["from"] == "gate" and e["to"] == "producer")
    assert back["control"] is True


def test_collect_aggregate_output_is_a_bounded_projection(manager):
    """T-9a（F4/F4a）：``collect`` 聚合的产出是有界投影，不是替身回复。

    **变异验证**（``test_pollution_guard_is_discriminating``）：不切断 summarizer 路径时，
    ``root.summary`` 会变成替身的回应（``research/summarizer_pollution.py`` 实证）。
    """
    long_output = "L" * 9000  # 远超聚合节点预算（root 档 3000 token ≈ 12000 字符 × 2 份）
    report = _dry_run(
        manager,
        {
            "goal": "aggregate",
            "nodes": [
                {"id": "a", "kind": "subagent", "task": "TASK-A"},
                {"id": "b", "kind": "subagent", "task": "TASK-B"},
                {"id": "root", "kind": "aggregate", "strategy": "collect"},
            ],
            "edges": [
                {"from": "a", "to": "root", "reducer": "concat"},
                {"from": "b", "to": "root", "reducer": "concat"},
            ],
            "terminal": ["root"],
        },
        script={"a": long_output, "b": long_output},
        max_report_chars=200,
    )

    root = _node(report, "root")
    produced = root["produced"]
    assert produced.startswith("L"), f"聚合产出不是上游投影：{produced[:60]!r}"
    assert "STAND-IN" not in produced
    # 有界：超长产出被截断并带可见标记。
    assert "[+" in produced
    assert report["unattributed_llm_calls"] == 0


def test_pollution_guard_is_discriminating(manager, monkeypatch):
    """T-9a 的**变异验证**：把真正的 LLM summarizer 装回聚合器，产出必须被污染。

    这是**最忠实**的变异形态（building-review 的 M3 教训）：审阅者指出「替换
    ``TruncationSummarizer``」只是代理变异——若哪天 ``WorkflowAggregator`` 不再走
    summarizer 路径，那版变异未必变红。真正要模拟的坏世界是**实现没有切断聚合路径**：
    此时 ``WorkflowScheduler._build_summarizer()`` 会给出 ``LLMSummarizer(manager.llm)``
    ——也就是**假 LLM**。所以这里直接让假 LLM 在「无节点身份」（= 压缩调用）时回一句
    显眼的占位文本，并把真正的 ``LLMSummarizer`` 装回去。
    """
    from agent.context.summarizer import LLMSummarizer

    # 「忘记切断」的世界里，``_build_summarizer()`` 会返回
    # ``LLMSummarizer(manager.llm)``——而模拟 manager 的 llm 正是假 LLM。所以变异
    # 必须把**那一个**假 LLM 装回 summarizer（不是调用方的真 LLM，那会让断言测错对象）。
    holder: dict = {}
    original_llm_cls = subagents_module._DryRunLLM

    class _PollutingDryRunLLM(original_llm_cls):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            holder["llm"] = self

        async def chat(self, messages, tools=None, model="gpt-4"):
            response = await super().chat(messages, tools=tools, model=model)
            if current_node_id() is None:  # 压缩调用：归不到节点
                response.content = "[SUMMARY-PLACEHOLDER]"
            return response

    monkeypatch.setattr(subagents_module, "_DryRunLLM", _PollutingDryRunLLM)

    original_aggregator_cls = subagents_module.WorkflowAggregator

    def _unpatched_aggregator(*args, **kwargs):
        return original_aggregator_cls(summarizer=LLMSummarizer(holder["llm"]))

    monkeypatch.setattr(subagents_module, "WorkflowAggregator", _unpatched_aggregator)

    report = _dry_run(
        manager,
        {
            "goal": "aggregate",
            "nodes": [
                {"id": "a", "kind": "subagent", "task": "TASK-A"},
                {"id": "b", "kind": "subagent", "task": "TASK-B"},
                {"id": "root", "kind": "aggregate", "strategy": "collect"},
            ],
            "edges": [
                {"from": "a", "to": "root", "reducer": "concat"},
                {"from": "b", "to": "root", "reducer": "concat"},
            ],
            "terminal": ["root"],
        },
        script={"a": "L" * 9000, "b": "L" * 9000},
        max_report_chars=200,
    )

    assert "[SUMMARY-PLACEHOLDER]" in json.dumps(report), (
        "不切断聚合路径时也没被污染——主用例的「有界投影」断言无法区分「切断生效」与「没走到」"
    )
    # 污染同时留下不可归因调用——这正是 F4a 的第二个症状。
    assert report["unattributed_llm_calls"] >= 1


def test_report_has_no_unattributable_calls(manager):
    """T-9b（F4a）：报告里不出现归不到任何节点的调用。"""
    report = _dry_run(manager, S2_SPEC)

    assert report["unattributed_llm_calls"] == 0
    assert report["llm_calls"] > 0
    for node in report["nodes"]:
        assert node["id"] not in (None, "", "?")
        for entry in node["received"]:
            assert entry["prompt"] is not None


# --- T-10…T-14：报告契约 ---------------------------------------------------


def test_text_fields_are_bounded_with_a_visible_marker(manager):
    """T-10（D5）：超长产出被截断到 ``max_report_chars``，且截断可见。"""
    # 缺省上界是一个**明确的正整数常量**（Q3 拍板：800），不是随手写的魔数。
    assert isinstance(DRY_RUN_DEFAULT_MAX_REPORT_CHARS, int)
    assert DRY_RUN_DEFAULT_MAX_REPORT_CHARS > 0
    assert _dry_run(manager, S1_SPEC)["max_report_chars"] == DRY_RUN_DEFAULT_MAX_REPORT_CHARS

    limit = 60
    report = _dry_run(
        manager,
        S1_SPEC,
        script={"mid": "M" * 5000},
        max_report_chars=limit,
    )

    produced = _node(report, "mid")["produced"]
    assert produced.startswith("M" * limit)
    assert f"[+{5000 - limit} chars]" in produced
    assert "result_ref" not in produced, (
        "dry run 没有任何可读的 ref，不能复用调度器的 bounded 标记（它会承诺一个不存在的 ref）"
    )
    assert report["max_report_chars"] == limit


def test_a_single_warning_is_clipped_too(manager):
    """N-3（Round 3）：warnings 的**每条截断**这一半此前无测试守护。

    审阅实测：删掉 ``warnings = [_clip_text(w, limit) ...]`` 后 41 条**全绿**，而
    warnings 块会涨到 1.17 MB。节点 id 由调用方给、长度不受 ``max_nodes`` 约束
    （那管的是条数），所以「一条超长 id → 一条超长 warning」是可达的。
    **变异验证**：去掉逐条 `_clip_text` → 本条必红。
    """
    limit = 120
    long_id = "x" * 3000
    spec = {
        "goal": "long node id",
        "max_runs": 1,
        "nodes": [
            {"id": long_id, "kind": "subagent", "task": "T0"},
            {"id": "later", "kind": "subagent", "task": "T1"},
        ],
        "edges": [{"from": long_id, "to": "later"}],
        "entry": [long_id],
        "terminal": ["later"],
    }
    report = _dry_run(manager, spec, max_report_chars=limit)

    assert report["warnings"], "该图应当产出至少一条 warning"
    assert all(len(w) <= limit + 32 for w in report["warnings"]), (
        "单条 warning 未被截断——节点 id 长度不受 max_nodes 约束，warnings 块会无界"
    )
    assert any("[+" in w for w in report["warnings"]), "截断必须带可见标记，不静默丢弃"


def _many_failed_nodes_spec(count: int) -> dict:
    """一张 ``max_runs=1`` 的长链：只有 ``n0`` 能跑，其余全部以非 completed 收尾——

    每一条都会推一条 warning（这正是 N-2 里把报告撑到 20 万字符的那类图）。
    """
    return {
        "goal": "many failed nodes",
        "max_runs": 1,
        "nodes": [
            {"id": f"n{i}", "kind": "subagent", "task": f"T{i}"} for i in range(count)
        ],
        "edges": [{"from": f"n{i}", "to": f"n{i + 1}"} for i in range(count - 1)],
        "entry": ["n0"],
        "terminal": [f"n{count - 1}"],
    }


def test_the_warning_list_is_bounded_too(manager):
    """N-2（Round 2 审阅）：``warnings`` 也必须受 ``max_report_chars`` 的界约束。

    此前 warnings 不受任何界管辖——一张 60 节点的图能把它撑到 20 万字符，与「报告的
    每个文本字段都有界」的承诺直接冲突。**变异验证**：去掉条数裁剪 → 本条必红。
    """
    from agent.tools.builtin.subagents import _WARNINGS_CHARS_PER_ITEM, _WARNINGS_MAX

    limit = 200
    report = _dry_run(manager, _many_failed_nodes_spec(60), max_report_chars=limit)

    bound = max(1, min(_WARNINGS_MAX, limit * _WARNINGS_CHARS_PER_ITEM // 200))
    # 底层确实产出了远超上界的条数——这条断言保证上界不是"因为没东西可截"而恒真。
    assert len(report["warnings"]) == bound, report["warnings"]
    assert report["warnings_omitted"] > 0, "被省略的条数必须显式报告，不能静默截断"
    assert report["warnings_omitted"] == 60 - bound
    assert all(len(w) <= limit + 32 for w in report["warnings"]), (
        "单条 warning 也被单个截断（标记留一点余量）"
    )
    # warnings 块**本身**有界——这才是 N-2 的病灶。节点条目随图规模线性增长是
    # 预期的（受 `max_nodes` 结构闸管辖），不可与 warnings 混为一谈。
    warnings_size = len(json.dumps(report["warnings"], ensure_ascii=False))
    assert warnings_size < bound * (limit + 40), f"warnings 块膨胀到 {warnings_size} 字符"


def test_report_declares_the_simulation_and_returns_no_runnable_handle(manager):
    """T-11（D6/D8）：返回体含模拟标记与边界文案；**不含** ``workflow_id``。"""
    report = _dry_run(manager, S1_SPEC)

    assert report["simulated"] is True
    assert report["status"] == "simulated"
    assert report["tokens_spent"] == 0
    body = json.dumps(report, ensure_ascii=False)
    assert "workflow_id" not in body, "返回了运行句柄：模型可能拿它去 StartWorkflow/GetWorkflow"
    assert report["spec_hash"], "spec_hash 是图的指纹（可接受），不是运行句柄"
    notes = " ".join(report["notes"]).lower()
    assert "simulation" in notes or "simulated" in notes
    assert "no model calls" in notes or "makes no model calls" in notes


def test_report_separates_answerable_from_unanswerable(manager):
    """T-11a（R10/D6）：区分「结构闸可答」与「token/成本预算不可答」。"""
    report = _dry_run(manager, S1_SPEC)

    text = " ".join(report["notes"]).lower()
    assert "token" in text and "cost" in text
    assert "budget" in text
    assert "max_nodes" in text or "structural" in text
    # 边界声明必须留在**工具描述**里（不只写在返回体）。
    desc = DryRunWorkflowTool.description.lower()
    assert "no model calls" in desc
    assert "nothing" in desc


def test_dry_run_schema_matches_declare_workflow_exactly():
    """T-12：``spec`` 参数用同一份派生 schema（逐字相等），不新建第二份定义。"""
    own = DryRunWorkflowTool.parameters["properties"]["spec"]
    assert own == DeclareWorkflowTool.parameters["properties"]["spec"]
    assert own == _workflow_spec_schema()
    assert DryRunWorkflowTool.parameters["required"] == ["spec"]


def test_script_schema_avoids_top_level_one_of():
    """``script`` 的两种形态用「并列类型」表达，且**顶层**不出现 ``oneOf``/``anyOf``/``allOf``。

    Anthropic API 拒绝顶层判别联合的 ``input_schema``（#246 RIR 实测），而本仓
    ``parameters`` 是逐字透传 ``input_schema``——所以 ``oneOf`` 绝不能出现在顶层。
    """
    schema = DryRunWorkflowTool.parameters
    # 顶层三条禁令：任何一条都足以让 Anthropic 直接拒绝整份 input_schema。
    assert not ({"oneOf", "anyOf", "allOf"} & set(schema))

    value_schema = schema["properties"]["script"]["additionalProperties"]
    assert {"type": "string"} in value_schema["anyOf"]
    assert {"type": "array", "items": {"type": "string"}} in value_schema["anyOf"]


def test_script_schema_uses_no_anyof_outside_the_one_union():
    """I-2（building-review）：``anyOf`` 的**唯一**允许位置是 ``script`` 的值那儿。

    审阅指出「顶层禁令」这条纪律容易被读成「任何地方都不许 anyOf」，而实现里
    ``script.additionalProperties`` 确实用了嵌套 ``anyOf``（标量 or 数组——这是
    schema 层表达「两种类型并列」的自然写法，且 Anthropic 的限制只针对**顶层**）。
    本用例把这个**有意为之的例外**钉成单点：多出第二个 ``anyOf`` 就会红，
    逼迫后来者显式决定「是不是又要引入一个判别联合」。
    """
    def _anyof_paths(node, path=()):
        found = []
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "anyOf":
                    found.append(".".join((*path, key)))
                found.extend(_anyof_paths(value, (*path, str(key))))
        elif isinstance(node, list):
            for index, item in enumerate(node):
                found.extend(_anyof_paths(item, (*path, str(index))))
        return found

    paths = _anyof_paths(DryRunWorkflowTool.parameters)
    assert paths == ["properties.script.additionalProperties.anyOf"], (
        f"`anyOf` 只允许出现在 script 的值类型处，实际出现在：{paths}"
    )


def test_tool_surface_keeps_dry_run_out_of_the_spawn_gate(manager):
    """T-13：``DryRunWorkflow`` 不进 ``SPAWN_TOOL_NAMES``；深度撤工具时不撤它。"""
    assert "DryRunWorkflow" not in SPAWN_TOOL_NAMES

    loop = manager._build_subagent_loop(AgentMode.BUILD, depth=manager.max_depth)
    names = {tool["function"]["name"] for tool in loop.tool_registry.get_all_schemas()}
    assert "DryRunWorkflow" in names
    assert "DeclareWorkflow" in names  # 既有的同档工具仍在
    assert "RunWorkflow" not in names  # 同档的**深度闸**没被本 change 放松


def test_description_budget_and_declare_pointer():
    """D10（Q4）：两个描述都在预算内，且声明入口有一句指向 dry run 的短指针。"""
    assert len(DryRunWorkflowTool.description) <= 2000
    declare = DeclareWorkflowTool.description
    assert len(declare) <= 6000
    assert "DryRunWorkflow" in declare
    # 既有循环契约条款不因插入指针而丢失。
    assert "defaults to 1" in declare and "per route node" in declare


# --- T-14：``script`` 数组按调用次序消费（Q1） ------------------------------


def test_script_array_is_consumed_in_call_order(manager):
    """T-14（Q1）：数组按「该节点被调用的次序」消费，用尽后沿用最后一个元素。"""
    report = _dry_run(
        manager,
        S3_SPEC,
        script={"reviewer": ["GAPS: one", "GAPS: two"]},
    )

    reviewer = _node(report, "reviewer")
    outputs = [entry["output"] for entry in reviewer["received"]]
    # 环转了 5 圈（entry 起 1 圈 + 4 次回边），数组只有 2 个元素。
    assert len(outputs) == 5
    assert outputs[:2] == ["GAPS: one", "GAPS: two"], "数组没有按调用次序消费"
    assert set(outputs[2:]) == {"GAPS: two"}, (
        f"数组用尽后没有沿用末元素（按调用次序消费被破坏）：{outputs}"
    )
    assert reviewer["runs"] == len(outputs)

    # 末元素一直是 GAPS ⇒ 回边转到 max_routes 用尽，图在**结构闸**上停住——
    # 这是模拟**答得了**的那类问题（计数器在调度器自己手里），报告如实报出。
    assert report["run_status"] == "graph_recursion_exceeded"
    gate = _node(report, "gate")
    assert gate["evaluated"] is False, "route 没跑到判定点，却报成了判定结果"
    assert "max_routes" in gate["reason"]


def test_script_array_covers_each_foreach_item(manager):
    """T-14（Q1）：同一个机制同时覆盖 foreach 各展开项（统一为「调用次序」）。"""
    report = _dry_run(manager, FOREACH_SPEC, script={"fan": ["out-a", "out-b", "out-c"]})

    fan = _node(report, "fan")
    assert sorted(entry["output"] for entry in fan["received"]) == [
        "out-a",
        "out-b",
        "out-c",
    ]
    assert len(fan["received"]) == 3


def test_script_for_a_node_that_runs_no_model_is_reported_as_ineffective(manager):
    """改进项 I-1（building-review）：``script`` 对不产生 run 的节点**不得**被标成生效。

    报告自己的 ``notes`` 明说 ``script`` 对 route / ``collect`` 聚合无效——若 ``script_applied``
    仍标 ``true``，两处自相矛盾，模型会以为注入生效了（D3/R5 要防的正是这个）。
    **变异验证**：把判定改回 ``node.id in scripted_nodes``（不看是否真被调用）→ 本条必红。
    """
    report = _dry_run(
        manager,
        S1_SPEC,
        script={
            "mid": "GAPS",  # 真的跑了 → 生效
            "gate": "whatever",  # route：不产生 run → 无效
            "nonexistent": "nope",  # 图里根本没有这个节点 → 无效
        },
    )

    # 生效的照常标记。
    assert _node(report, "mid")["script_applied"] is True
    assert _node(report, "mid")["produced_kind"] == "script"
    # 没生效的**不**标 script_applied，且产出不被标成 script。
    gate = _node(report, "gate")
    assert "script_applied" not in gate
    assert gate["produced_kind"] == "stand_in"
    # 两条无效注入都要在 warnings 里说清原因（不是静默）。
    joined = " ".join(report["warnings"])
    assert "'gate'" in joined and "runs no model" in joined
    assert "'nonexistent'" in joined and "no node with that id" in joined

    # collect 聚合同理：它只搬文本，注入无效。
    collect = _dry_run(
        manager,
        {
            "goal": "g",
            "nodes": [
                {"id": "a", "kind": "subagent", "task": "TASK-A"},
                {"id": "root", "kind": "aggregate", "strategy": "collect"},
            ],
            "edges": [{"from": "a", "to": "root", "reducer": "concat"}],
            "terminal": ["root"],
        },
        script={"root": "IGNORED"},
    )
    root = _node(collect, "root")
    assert "script_applied" not in root
    assert root["produced_kind"] == "bounded_projection"
    assert any("'root'" in w and "runs no model" in w for w in collect["warnings"])


def test_script_for_an_llm_aggregate_does_apply(manager):
    """``llm`` 策略的聚合会真的跑模型——``script`` 对它**是**生效的（并入 I-1 的判据）。"""
    report = _dry_run(
        manager,
        {
            "goal": "g",
            "nodes": [
                {"id": "a", "kind": "subagent", "task": "TASK-A"},
                {"id": "b", "kind": "subagent", "task": "TASK-B"},
                {"id": "sum", "kind": "aggregate", "strategy": "llm"},
            ],
            "edges": [
                {"from": "a", "to": "sum", "reducer": "concat"},
                {"from": "b", "to": "sum", "reducer": "concat"},
            ],
            "terminal": ["sum"],
        },
        script={"sum": "SYNTHESISED"},
    )
    node = _node(report, "sum")
    assert node["script_applied"] is True
    assert node["produced"] == "SYNTHESISED"


def test_a_scripted_llm_aggregate_that_never_ran_is_not_called_model_less(manager):
    """N-1（Round 2 审阅：变异存活）：未跑到的 ``llm`` 聚合，原因必须是「没跑到」。

    ``_node_runs_a_model`` 的 ``aggregate/llm`` 分支此前无测试守护——把它改成
    ``return False`` 时 39 条全绿。后果不是小事：对**会跑模型**的节点，报告会改口
    说「这类节点永远不产生输出」，那是一句关于拓扑的假陈述。
    **变异验证**：把 ``_node_runs_a_model`` 的 aggregate 分支改成 ``return False``
    （或直接短路成 False）→ 本条必红。
    """
    report = _dry_run(
        manager,
        {
            "goal": "g",
            "nodes": [
                {"id": "a", "kind": "subagent", "task": "TASK-A"},
                {
                    "id": "gate",
                    "kind": "route",
                    "cases": [{"when": "GO", "to": "sum"}],
                    "default": "end",
                },
                # 会跑模型的聚合（strategy=llm）——但本图走 default，它永远到不了。
                {"id": "sum", "kind": "aggregate", "strategy": "llm"},
                {"id": "end", "kind": "aggregate", "strategy": "collect"},
            ],
            "edges": [
                {"from": "a", "to": "gate"},
                {"from": "gate", "to": "sum"},
                {"from": "gate", "to": "end"},
            ],
            "entry": ["a"],
            "terminal": ["end"],
        },
        script={"sum": "SYNTHESISED"},
    )

    sum_node = _node(report, "sum")
    assert sum_node["status"] != "completed"  # 它确实没跑到
    assert "script_applied" not in sum_node
    warning = next(w for w in report["warnings"] if "`script` for node 'sum'" in w)
    assert "never ran" in warning, warning
    assert "runs no model" not in warning, (
        f"把「没跑到」错报成「这类节点永远不跑」——一句关于拓扑的假陈述：{warning}"
    )


def test_script_forms_are_validated_at_runtime():
    """``script`` 的形态在运行期判别（schema 表达不了），非法形态给结构化拒绝。"""
    spec = S1_SPEC
    bad_object = _dry_run(
        DryRunWorkflowTool(_FakeManager()), spec, script={"mid": {"laps": ["x"]}}
    )
    assert bad_object["status"] == "invalid_input"
    assert "script" in bad_object["reason"]


class _FakeManager:
    """只为拿 ``spec_bounds`` 用的最小 manager 桩（``script`` 校验在解析之后发生不了）。"""

    config = AsterwyndConfig()


def test_invalid_spec_is_reported_without_a_simulation_claim(manager):
    """非法 spec 走既有 ``invalid_spec`` 通道：**不**冒充一次模拟结果。"""
    report = _dry_run(manager, {"goal": "broken", "nodes": [], "edges": []})

    assert report["status"] == "invalid_spec"
    assert report["reason"]
    assert "workflow_id" not in json.dumps(report)


def test_call_count_is_bounded_and_hinted(manager):
    """D7（Q5=A+C）：软提醒 ~10 次、硬上限 ~40 次并给可读原因与提高路径。"""
    tool = DryRunWorkflowTool(manager)

    for _ in range(DRY_RUN_SOFT_CALL_HINT):
        report = json.loads(asyncio.run(tool.execute(spec=S1_SPEC)))
        assert "notes" in report

    nudged = json.loads(asyncio.run(tool.execute(spec=S1_SPEC)))
    assert any(
        "dry run" in note.lower() and str(DRY_RUN_SOFT_CALL_HINT) in note
        for note in nudged["notes"]
    ), "第 10 次之后没有再提醒"
    assert nudged["simulated"] is True, "软提醒不得阻断调用"

    for _ in range(DRY_RUN_HARD_CALL_LIMIT - DRY_RUN_SOFT_CALL_HINT - 1):
        asyncio.run(tool.execute(spec=S1_SPEC))

    blocked = json.loads(asyncio.run(tool.execute(spec=S1_SPEC)))
    assert blocked["status"] == "dry_run_limit_reached"
    assert blocked["reason"]
    assert "hint" in blocked
    assert "simulated" not in blocked


def test_call_counter_lives_on_the_tool_instance(manager):
    """计数点必须**跨调用存活**——``DryRunWorkflow`` 不持有 session，故挂在工具实例上。"""
    first = DryRunWorkflowTool(manager)
    asyncio.run(first.execute(spec=S1_SPEC))
    asyncio.run(first.execute(spec=S1_SPEC))
    second = DryRunWorkflowTool(manager)

    assert json.loads(asyncio.run(first.execute(spec=S1_SPEC)))[
        "dry_run_calls_this_session"
    ] == 3
    assert json.loads(asyncio.run(second.execute(spec=S1_SPEC)))[
        "dry_run_calls_this_session"
    ] == 1


def test_slots_are_returned_only_when_a_route_reads_them(manager):
    """Q4：聚合槽以**独立顶层字段**返回、单独截断，且只在被 route 实际读到时展开。"""
    report = _dry_run(manager, S2_SPEC)
    assert "merge" in report["slots"]
    slot_value = report["slots"]["merge"]["result"]
    # 槽里的值是两份上游产出的 concat——它就是 route 判定时读到的东西。
    assert "w1 produced" in slot_value and "w2 produced" in slot_value
    assert slot_value == _node(report, "gate")["input_seen"]
    # 单独截断：槽与 received/produced 不在同一层，且有自己的上界。
    bounded = _dry_run(manager, S2_SPEC, max_report_chars=20)
    assert len(bounded["slots"]["merge"]["result"]) < len(slot_value)

    # 未被任何 route 读取的聚合槽不展开（S3 的 done 是终点聚合，route 没读它）。
    other = _dry_run(manager, S3_SPEC)
    assert "done" not in other["slots"]
