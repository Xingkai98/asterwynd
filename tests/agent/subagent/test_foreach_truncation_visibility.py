"""foreach 截断可见性（issue #279 静态截断 + issue #286 预算截断）。

覆盖**两条截断路径**、**三/四条模型可见出口**：

- **#279 静态截断**（change ``foreach-truncation-visibility``）：`max_items`（默认 20）
  静默截断 ``items``（``_resolve_items`` 的 ``items[:max_items]``）。
- **#286 预算截断**（change ``foreach-budget-truncation-visibility``）：``max_items=0``
  时 ``_resolve_items`` 把集合切到 ``_remaining_expansion_capacity()`` **恰好合身**，
  使后续 ``_check_foreach_budget`` 的 ``runs+delta>limit`` 刚好不触发 ⇒ 超预算项静默丢弃。
  两条路径共用 ``_foreach_visibility_fields``，成因由 ``items_omitted_cause`` 区分
  （``"max_items"`` / ``"budget"``）。

这两条路径此前都静默。本模块把 delta spec 的每条 Scenario 固化成断言，覆盖**模型
可见出口**：

- **声明期**（``DeclareWorkflow`` / ``RunWorkflow(spec=...)`` 的 ``warnings``）：只报
  **字面** ``items`` 的**静态**截断；``source`` 驱动声明期**完全静默**（D3）；预算截断
  声明期不适用（运行期现象）。
- **dry run**（``DryRunWorkflow`` 的 foreach 条目）：补 ``items_declared`` /
  ``items_omitted`` / ``items_omitted_cause``（与既有 ``items_expanded`` 三元）；
  ``source`` 驱动的集合数标**模拟/不可信**（Q5）。
- **运行期 `GetWorkflow(detail='nodes')`**（foreach 节点）：暴露截断信号 + 成因，
  且按 ``_attach_item_refs`` 式**后写**绕过 ``_bounded_node`` 白名单（D3）。
- **运行期 `RunWorkflow` 结果信封**（``nodes`` 里的 foreach 节点，#286 OQ2=(b) 新增
  出口）：同源后写，使「跑完图直接读返回信封」也可见（并补 #279 静态字段缺口）。

字段名（D2）：扁平 ``items_declared``（声明集合大小）/ ``items_omitted``
（= ``max(items_declared - items_expanded, 0)``）。**绝不复用**既有 ``items_total``
（= 展开数，spec:858 钉死 + `test_foreach_item_refs.py` 硬断言；同 dict 同键会覆盖）。
``items_omitted``（``max_items`` 丢弃数）与既有 ``item_refs_omitted``（ref 列表界）
是**两件事**，SHALL NOT 混（D4）。

Q4：空集合 / ``source`` 无产出 ⇒ foreach 静默跑 0 项，须在 dry-run 与运行期**显式**
标 ``empty_collection``，区别于「正常展开 0 项」。
"""
import asyncio
import json

import pytest

import agent.tools.builtin.subagents as subagents_module
from agent.config import AsterwyndConfig
from agent.llm import LLMResponse, Usage
from agent.run_config import AgentMode
from agent.subagent.manager import SubAgentManager
from agent.subagent.scheduler import WorkflowScheduler
from agent.subagent.workflow import parse_workflow_spec
from agent.tools.builtin.subagents import (
    DeclareWorkflowTool,
    DryRunWorkflowTool,
    GetWorkflowTool,
    RunWorkflowTool,
)
from agent.workspace_policy import WorkspacePolicy


class OkLLM:
    async def chat(self, messages, tools=None, model="gpt-4"):
        return LLMResponse(content="ok", stop_reason="end_turn", usage=Usage(5, 5))


class ScriptedLLM:
    """按调用序号返回脚本内容（第一个调用供 source 节点产出集合）。"""

    def __init__(self, responses) -> None:
        self.responses = responses
        self.calls = 0

    async def chat(self, messages, tools=None, model="gpt-4"):
        index = min(self.calls, len(self.responses) - 1)
        self.calls += 1
        return LLMResponse(
            content=self.responses[index], stop_reason="end_turn", usage=Usage(5, 5)
        )


@pytest.fixture
def manager(tmp_path) -> SubAgentManager:
    return SubAgentManager(
        llm=OkLLM(),
        config=AsterwyndConfig(),
        parent_mode=AgentMode.BUILD,
        workspace_policy=WorkspacePolicy(workspace_root=tmp_path),
    )


def _literal_spec(count: int, *, max_items: int | None = None) -> dict:
    """字面 ``items`` 的 foreach（terminal 即自身，无下游）。"""
    node: dict = {
        "id": "fan",
        "kind": "foreach",
        "task": "work {item}",
        "items": [f"item-{i}" for i in range(count)],
    }
    if max_items is not None:
        node["max_items"] = max_items
    return {"goal": "g", "nodes": [node], "edges": [], "terminal": ["fan"]}


def _source_spec(*, max_items: int | None = None) -> dict:
    node: dict = {
        "id": "fan",
        "kind": "foreach",
        "task": "work {item}",
        "source": "planner",
        "source_field": "items",
    }
    if max_items is not None:
        node["max_items"] = max_items
    return {
        "goal": "g",
        "nodes": [{"id": "planner", "kind": "subagent", "task": "plan"}, node],
        "edges": [{"from": "planner", "to": "fan"}],
        "terminal": ["fan"],
    }


def _budget_spec(count: int, *, max_items: int = 0, max_runs: int | None = None) -> dict:
    """预算截断（#286）的确定性图：**字面** N 项 foreach + 上游 planner（占 1 run）。

    为什么加 planner：``max_items=0`` 的展开上限 = ``_remaining_expansion_capacity()``
    = 剩余 ``max_runs`` 等的最小值。上游 planner 先吃掉 1 个 run，使 ``count`` 项被切成
    ``max_runs - 1`` 项 ⇒ 确定性得到「声明 60 / 展开 24 / 省略 36」（``max_runs=25``），
    **零假 LLM 脚本**（字面 items 不读数、planner 用默认 OkLLM 回 "ok"）。这是用户拍板
    OQ5 的 T1 构造（对抗实测确认裸字面 60 只会给 25/35、拿不到 spec 声明的 24）。
    """
    spec: dict = {
        "goal": "g",
        "nodes": [
            {"id": "planner", "kind": "subagent", "task": "plan"},
            {
                "id": "fan",
                "kind": "foreach",
                "task": "work {item}",
                "items": [f"item-{i}" for i in range(count)],
                "max_items": max_items,
            },
        ],
        "edges": [{"from": "planner", "to": "fan"}],
        "terminal": ["fan"],
    }
    if max_runs is not None:
        spec["max_runs"] = max_runs
    return spec


def _declare(manager: SubAgentManager, spec: dict) -> dict:
    return json.loads(asyncio.run(DeclareWorkflowTool(manager).execute(spec=spec)))


def _dry_run(manager: SubAgentManager, spec: dict) -> dict:
    return json.loads(asyncio.run(DryRunWorkflowTool(manager).execute(spec=spec)))


def _run_spec(manager: SubAgentManager, spec: dict) -> dict:
    return json.loads(
        asyncio.run(RunWorkflowTool(manager).execute(spec=spec, wait=True))
    )


async def _get_nodes(manager: SubAgentManager, spec: dict) -> dict:
    parsed = parse_workflow_spec(spec)
    scheduler = WorkflowScheduler(manager)
    manager.register_workflow(scheduler)
    await scheduler.run(parsed)
    return json.loads(
        await GetWorkflowTool(manager).execute(
            workflow_id=scheduler.workflow_id, detail="nodes"
        )
    )


def _node(report: dict, node_id: str) -> dict:
    return next(node for node in report["nodes"] if node["id"] == node_id)


# --- T1/T2：声明期 warnings（两条入口） -------------------------------------


def test_declare_warns_on_literal_foreach_truncation(manager):
    """T1：60 项字面 foreach + 默认 max_items ⇒ DeclareWorkflow warnings 报截断。"""
    report = _declare(manager, _literal_spec(60))
    joined = " ".join(report["warnings"])
    assert report["warnings"], "60 项 > 默认 max_items 却零 warning（静默截断）"
    assert "60" in joined and "20" in joined, joined
    # 措辞可行动：给出展开全部的途径（含 max_items: 0）
    assert "max_items: 0" in joined, joined
    # SHALL NOT 声称 20 是「默认值」（_parse_max_items 不保留是否显式）
    assert "default" not in joined.lower(), joined


def test_declare_warning_absent_without_truncation(manager):
    """T5：items ≤ max_items ⇒ 不产生截断警告（零噪声）。"""
    report = _declare(manager, _literal_spec(3))
    assert report["warnings"] == []


def test_declare_warning_absent_for_max_items_zero(manager):
    """T6：max_items=0（不静态截断）⇒ 不报静态截断。"""
    report = _declare(manager, _literal_spec(60, max_items=0))
    assert report["warnings"] == []


def test_declare_silent_for_source_driven_foreach(manager):
    """D3：source 驱动声明期完全静默（不猜展开/截断数）。"""
    report = _declare(manager, _source_spec())
    assert report["warnings"] == []


def test_declare_emits_one_warning_per_truncated_node(manager):
    """M1（D6 选 (b)）：声明期警告**每截断节点一条、不切片**——上界 = 节点数，不漏项。

    ``DeclareWorkflow`` 的 warnings 不引用 dry-run 报告构造器才有的 ``warnings_omitted``
    界（`subagents.py` 的 dry-run 段落）；这里用 3 个截断节点锁「三节点 ⇒ 三条警告」。
    """
    spec = {
        "goal": "g",
        "nodes": [
            {"id": f"f{i}", "kind": "foreach", "task": "work {item}",
             "items": [f"x{j}" for j in range(30)]}
            for i in range(3)
        ],
        "edges": [],
        "terminal": ["f0", "f1", "f2"],
    }
    report = _declare(manager, spec)
    assert sum(1 for w in report["warnings"] if "foreach items" in w) == 3


def test_run_workflow_spec_warns_like_declare(manager):
    """T2：RunWorkflow(spec=...) 的 warnings 与 DeclareWorkflow 一致。"""
    manager.llm = OkLLM()
    envelope = _run_spec(manager, _literal_spec(60))
    joined = " ".join(envelope["warnings"])
    assert "60" in joined and "20" in joined, envelope["warnings"]
    assert "max_items: 0" in joined, envelope["warnings"]


# --- T3：dry run 三元 -------------------------------------------------------


def test_dry_run_reports_declared_expanded_omitted(manager):
    """T3：dry run foreach 条目 = items_declared=60 / items_expanded=20 / items_omitted=40。

    附带断言静态路径的成因判别字段（delta MODIFIED Scenario「dry run 报告集合总数与省略数」
    新增的「成因判别字段 SHALL 标为 `max_items`」）——dry-run 出口也直接锁静态成因。
    """
    report = _dry_run(manager, _literal_spec(60))
    fan = _node(report, "fan")
    assert fan["items_declared"] == 60
    assert fan["items_expanded"] == 20
    assert fan["items_omitted"] == 40
    assert fan["items_expanded"] + fan["items_omitted"] == fan["items_declared"]
    assert fan["items_omitted_cause"] == "max_items"


def test_dry_run_omits_fields_without_truncation(manager):
    """T5：不截断 ⇒ dry run 条目无截断字段（既有 items_expanded 除外）。"""
    report = _dry_run(manager, _literal_spec(3))
    fan = _node(report, "fan")
    assert fan["items_expanded"] == 3
    assert "items_declared" not in fan
    assert "items_omitted" not in fan
    assert "empty_collection" not in fan


def test_dry_run_omits_static_fields_for_max_items_zero(manager):
    """T6：max_items=0 ⇒ dry run 不报静态截断。"""
    report = _dry_run(manager, _literal_spec(60, max_items=0))
    fan = _node(report, "fan")
    assert "items_declared" not in fan
    assert "items_omitted" not in fan


def test_dry_run_marks_source_driven_count_as_simulated(manager):
    """Q5：source 驱动的集合数是模拟产物，须标注不可信。"""
    report = _dry_run(manager, _source_spec())
    fan = _node(report, "fan")
    assert fan["items_declared_simulated"] is True
    assert "items_declared" in fan
    # 模拟的 0 不得被读成「确认空集合」（与 Q4 的空集合同形，M2）
    assert "empty_collection" not in fan


# --- T4：运行期投影（后写绕过 _bounded_node） -------------------------------


def test_get_workflow_exposes_static_truncation(manager):
    """T4：运行后 GetWorkflow(detail='nodes') 真能看到静态截断信号。"""
    report = asyncio.run(_get_nodes(manager, _literal_spec(60)))
    fan = _node(report, "fan")
    assert fan["items_declared"] == 60
    assert fan["items_omitted"] == 40
    # 既有 items_total（=展开数）语义不变、与新字段共存（D2）
    assert fan["items_total"] == 20
    assert fan["items"] == 20


def test_get_workflow_omits_fields_without_truncation(manager):
    """T5（运行期）：不截断 ⇒ 无截断字段。"""
    report = asyncio.run(_get_nodes(manager, _literal_spec(3)))
    fan = _node(report, "fan")
    assert "items_declared" not in fan
    assert "items_omitted" not in fan
    assert "empty_collection" not in fan


def test_get_workflow_omits_static_fields_for_max_items_zero(manager):
    """T6（运行期）：max_items=0 ⇒ 不报静态截断。"""
    report = asyncio.run(_get_nodes(manager, _literal_spec(60, max_items=0)))
    fan = _node(report, "fan")
    assert "items_declared" not in fan
    assert "items_omitted" not in fan


# --- T7：与 item_refs_omitted 不混 ------------------------------------------


def test_items_omitted_is_independent_of_item_refs_omitted(manager, monkeypatch):
    """T7：``items_omitted``（max_items 丢弃）≠ ``item_refs_omitted``（ref 列表界）。

    为把两个界缩到同一张小图上（真实 ``_PARENT_NODES_LIMIT``=200 会要求 200+ 展开项，
    测试代价过大），把 ref 列表界 monkeypatch 到 5：12 项 / ``max_items=10`` ⇒ 静态
    省略 2；ref 界 5 ⇒ ref 省略 5。两者同 >0、来源与取值都不同，证明互不折叠。
    """
    monkeypatch.setattr(subagents_module, "_PARENT_NODES_LIMIT", 5)
    report = asyncio.run(_get_nodes(manager, _literal_spec(12, max_items=10)))
    fan = _node(report, "fan")
    assert fan["items_declared"] == 12
    assert fan["items"] == 10  # 运行期投影的展开数（= 既有 ``items`` 字段）
    assert fan["items_omitted"] == 2  # 被 max_items 丢弃
    assert fan["items_total"] == 10  # 既有语义：展开数
    assert len(fan["item_refs"]) == 5
    assert fan["item_refs_omitted"] == 5  # 被 ref 列表界截断
    # 两个 omitted 独立：不同来源、不同值，不得折叠
    assert fan["items_omitted"] != fan["item_refs_omitted"]


# --- T9（Q4）：空集合 / source 无产出不静默 ---------------------------------


def test_dry_run_flags_empty_literal_collection(manager):
    """T9：字面空集合 ⇒ dry run 显式标 empty_collection，而非裸 items_expanded:0。"""
    report = _dry_run(manager, _literal_spec(0))
    fan = _node(report, "fan")
    assert fan["items_expanded"] == 0
    assert fan["empty_collection"] is True


def test_get_workflow_flags_empty_literal_collection(manager):
    """T9：字面空集合 ⇒ 运行期投影显式标 empty_collection。"""
    report = asyncio.run(_get_nodes(manager, _literal_spec(0)))
    fan = _node(report, "fan")
    assert fan["items"] == 0
    assert fan["empty_collection"] is True


def test_get_workflow_flags_source_with_no_output(manager):
    """T9：source 无产出（planner 产出取不到 source_field）⇒ 运行期标 empty_collection。"""
    manager.llm = ScriptedLLM(["plain text without the field"])
    report = asyncio.run(_get_nodes(manager, _source_spec()))
    fan = _node(report, "fan")
    assert fan["items_expanded" if "items_expanded" in fan else "items"] == 0
    assert fan["empty_collection"] is True


def test_get_workflow_source_driven_truncation_is_reported_at_runtime(manager):
    """D1/D3：source 驱动的截断由运行期报告（声明期静默）。"""
    manager.llm = ScriptedLLM(['{"items": [' + ",".join(f'"i{i}"' for i in range(60)) + "]}"])
    report = asyncio.run(_get_nodes(manager, _source_spec()))
    fan = _node(report, "fan")
    assert fan["items_declared"] == 60
    assert fan["items"] == 20
    assert fan["items_omitted"] == 40


# --- #286（预算截断）：T1/T2/T2b/T3/T4/T5 -------------------------------------
# `max_items=0` 的预算截断（`_resolve_items` 切到 `_remaining_expansion_capacity()`
# 恰好合身 ⇒ `_check_foreach_budget` 不触发）此前静默。三出口都要报「声明 N / 展开 M /
# 省略 K」+ 成因 `items_omitted_cause="budget"`（用户拍板 OQ1/OQ2=(b)）。


def test_dry_run_reports_budget_truncation(manager):
    """T1：dry run 报预算截断三元 + 成因（字面 60 + planner，max_items=0，max_runs=25）。"""
    report = _dry_run(manager, _budget_spec(60, max_items=0, max_runs=25))
    fan = _node(report, "fan")
    assert fan["items_declared"] == 60
    assert fan["items_expanded"] == 24
    assert fan["items_omitted"] == 36
    assert fan["items_omitted_cause"] == "budget"
    assert fan["items_expanded"] + fan["items_omitted"] == fan["items_declared"]


def test_get_workflow_reports_budget_truncation(manager):
    """T2：运行期 `GetWorkflow(detail='nodes')` 报预算截断三元 + 成因（后写可见）。"""
    report = asyncio.run(_get_nodes(manager, _budget_spec(60, max_items=0, max_runs=25)))
    fan = _node(report, "fan")
    assert fan["items"] == 24
    assert fan["items_declared"] == 60
    assert fan["items_omitted"] == 36
    assert fan["items_omitted_cause"] == "budget"
    # 既有 items_total（=展开数）语义不变、与新字段共存
    assert fan["items_total"] == 24


def test_run_workflow_envelope_reports_budget_truncation(manager):
    """T2b（OQ2=(b) 新增出口）：`RunWorkflow(spec=...)` **结果信封** 的 fan 节点也带三元 + 成因。

    实测（grill/对抗）该信封此前**连 #279 的静态字段都没有**——模型跑完图最自然的读法
    会全静默。本 change 把后写挂到 `_drive_scheduler`，使该出口补上（并顺带补 #279 静态字段）。
    """
    envelope = _run_spec(manager, _budget_spec(60, max_items=0, max_runs=25))
    fan = _node(envelope, "fan")
    assert fan["items_declared"] == 60
    assert fan["items"] == 24
    assert fan["items_omitted"] == 36
    assert fan["items_omitted_cause"] == "budget"


def test_run_workflow_envelope_reports_static_truncation(manager):
    """T2b 的 #279 静态孪生：`RunWorkflow` 信封对 `max_items>0` 静态截断也报（补 #279 缺口）。"""
    envelope = _run_spec(manager, _literal_spec(60, max_items=20))
    fan = _node(envelope, "fan")
    assert fan["items_declared"] == 60
    assert fan["items"] == 20
    assert fan["items_omitted"] == 40
    assert fan["items_omitted_cause"] == "max_items"


def test_omitted_cause_distinguishes_static_from_budget(manager):
    """T3：`max_items>0` 静态 ⇒ `"max_items"`；`max_items=0` 预算 ⇒ `"budget"`（取值不同）。"""
    static = asyncio.run(_get_nodes(manager, _literal_spec(60, max_items=20)))
    budget = asyncio.run(_get_nodes(manager, _budget_spec(60, max_items=0, max_runs=25)))
    static_fan = _node(static, "fan")
    budget_fan = _node(budget, "fan")
    assert static_fan["items_omitted_cause"] == "max_items"
    assert budget_fan["items_omitted_cause"] == "budget"
    assert static_fan["items_omitted_cause"] != budget_fan["items_omitted_cause"]


def test_budget_zero_noise_when_no_truncation(manager):
    """T4：`max_items=0` 且预算充足（declared == expanded）⇒ 无任何截断字段。"""
    # 60 项字面、max_items=0、预算充足（默认 max_runs 远大于 60）⇒ 完整展开。
    report = asyncio.run(_get_nodes(manager, _budget_spec(60, max_items=0, max_runs=500)))
    fan = _node(report, "fan")
    assert fan["items"] == 60
    assert "items_omitted" not in fan
    assert "items_omitted_cause" not in fan
    assert "items_declared" not in fan
    assert "empty_collection" not in fan


def test_static_path_values_unchanged_with_cause(manager):
    """T5：#279 静态路径的既有字段**值**不变（`items_declared`/`items_omitted`），仅新增成因键。

    对抗字节 diff（C4/M4）确认：`max_items>0` 场景唯一差异是新增 `items_omitted_cause`。
    """
    report = asyncio.run(_get_nodes(manager, _literal_spec(60, max_items=30)))
    fan = _node(report, "fan")
    assert fan["items_declared"] == 60  # 值不变
    assert fan["items_omitted"] == 30  # 值不变
    assert fan["items"] == 30
    assert fan["items_omitted_cause"] == "max_items"  # 唯一新增
