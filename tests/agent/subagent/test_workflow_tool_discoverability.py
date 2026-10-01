"""工具面可发现性：schema↔常量 parity + 描述内容 + route task warnings + 报错按实际 kind。

对应 change ``workflow-tool-discoverability``（issue #248）的 tasks 2.1–2.6。

本模块锁三件事，都是「模型可见面」的机械保障：

1. **T1**：``spec`` 的嵌套 schema 里每个 ``enum`` 与 ``agent/subagent/workflow.py``
   的源码常量**逐字相等**（元素 + 顺序）。顺序敏感——顺序是 enum 在模型侧的提示强度
   来源，用 ``set()`` 会让「常量顺序变了但 schema 没跟」静默通过。
2. **T2**：``DeclareWorkflow`` 描述的内容契约（``control`` 零命中 / ``cases`` 语义 /
   per-kind 字段表 / ``$ref:``）。
3. **T3**：route 节点带 ``task`` 时两条入口都给出**可行动** warning（D6 选 (b)）。
"""
import asyncio
import json

import pytest

from agent.config import AsterwyndConfig
from agent.llm import LLMResponse, Usage
from agent.run_config import AgentMode
from agent.subagent import workflow as workflow_dsl
from agent.subagent.manager import TRANSCRIPT_SCOPES, SubAgentManager
from agent.subagent.patterns import PATTERNS
from agent.subagent.workflow import (
    WorkflowValidationError,
    parse_workflow_spec,
)
from agent.tools.builtin.subagents import (
    CreateSubagentTool,
    DeclareWorkflowTool,
    GetWorkflowTool,
    InspectSubagentTranscriptTool,
    RunWorkflowTool,
    _GET_WORKFLOW_DETAILS,
    _workflow_spec_schema,
)
from agent.workspace_policy import WorkspacePolicy


class _StubLLM:
    async def chat(self, messages, tools=None, model="gpt-4"):
        return LLMResponse(content="APPROVED", stop_reason="end_turn", usage=Usage(5, 5))


@pytest.fixture
def manager(tmp_path) -> SubAgentManager:
    return SubAgentManager(
        llm=_StubLLM(),
        config=AsterwyndConfig(),
        parent_mode=AgentMode.BUILD,
        workspace_policy=WorkspacePolicy(workspace_root=tmp_path),
    )


def _declare(manager, spec: dict) -> dict:
    return json.loads(asyncio.run(DeclareWorkflowTool(manager).execute(spec=spec)))


# --- T1：schema ↔ 源码常量 parity -------------------------------------------

#: (schema 里的字段名, workflow.py 的常量名, 该字段所在的容器路径)
_SCHEMA_ENUM_BINDINGS = [
    ("kind", "NODE_KINDS", ("nodes", "items")),
    ("mode", "NODE_MODES", ("nodes", "items")),
    ("join", "JOIN_SEMANTICS", ("nodes", "items")),
    ("strategy", "AGGREGATE_STRATEGIES", ("nodes", "items")),
    ("channel", "CHANNELS", ("edges", "items")),
    ("reducer", "REDUCERS", ("edges", "items")),
]

_TOOLS = [DeclareWorkflowTool, RunWorkflowTool]


def _spec_schema(tool) -> dict:
    return tool.parameters["properties"]["spec"]


def _enum_owner(tool, section: str) -> dict:
    """取 ``spec.properties.<section>.items.properties``（节点或边的字段表）。"""
    return _spec_schema(tool)["properties"][section]["items"]["properties"]


@pytest.mark.parametrize("tool", _TOOLS, ids=lambda t: t.__name__)
@pytest.mark.parametrize(
    "field, const_name, path",
    _SCHEMA_ENUM_BINDINGS,
    ids=[f"{f}<-{c}" for f, c, _ in _SCHEMA_ENUM_BINDINGS],
)
def test_schema_enum_matches_source_constant(tool, field, const_name, path):
    """T1：每个 enum 与源码常量**逐字相等**（元组比较，顺序敏感，不用 set）。"""
    owner = _enum_owner(tool, path[0])
    enum = owner[field]["enum"]
    constant = getattr(workflow_dsl, const_name)
    assert tuple(enum) == tuple(constant), (
        f"{tool.__name__}.spec.{path[0]}[]: {field} enum {enum!r} "
        f"!= {const_name} {tuple(constant)!r}"
    )


@pytest.mark.parametrize("tool", _TOOLS, ids=lambda t: t.__name__)
def test_declare_and_run_share_the_same_spec_schema(tool):
    """两条入口的 spec 嵌套结构与 enum 集合一致（同一份派生结果）。"""
    assert _spec_schema(tool) == _spec_schema(DeclareWorkflowTool)


@pytest.mark.parametrize("field, const_name, _path", _SCHEMA_ENUM_BINDINGS)
def test_schema_enum_is_derived_live(field, const_name, _path, monkeypatch):
    """T1a：派生是**活的**——改常量后重新取 schema，enum 必须跟着变。

    这条断言把「恒真断言」堵死：若实现者把 schema 写成硬编码字面量，改常量不会
    影响已构造的 schema，本测试必红（与手动变异验证同效，但常驻 CI）。
    """
    monkeypatch.setattr(workflow_dsl, const_name, ("__mutated__",))
    schema = _workflow_spec_schema()
    if field in ("channel", "reducer"):
        owner = schema["properties"]["edges"]["items"]["properties"]
    else:
        owner = schema["properties"]["nodes"]["items"]["properties"]
    assert owner[field]["enum"] == ["__mutated__"]


def test_spec_schema_is_nested_not_bare_object():
    """spec 不再是裸的 {"type":"object"}——必须带 properties。"""
    schema = _spec_schema(DeclareWorkflowTool)
    assert schema["type"] == "object"
    assert "properties" in schema
    assert {"nodes", "edges"} <= set(schema["properties"])


@pytest.mark.parametrize("tool", _TOOLS, ids=lambda t: t.__name__)
def test_tool_schema_matches_freshly_derived_schema(tool):
    """**闭死「手写 schema 但值与常量恰好相同」这一缺口。**

    T1 比的是工具**已烘焙**的 ``parameters`` 与常量——若实现者手写一份与常量当前值
    完全相同的字面量，T1 会过；T1a 测的是 helper 是活的，也测不到烘焙值。本条把
    烘焙值与**测试期现算**的派生结果对比：任何与 helper 分叉的手写副本都会现形。
    三条合起来才是「派生」而非「手写字面量」的完整机械保障。
    """
    from agent.tools.builtin.subagents import _workflow_spec_schema

    assert _spec_schema(tool) == _workflow_spec_schema()


# --- T1b：spec **之外**的模型可见 enum 也纳入 parity ------------------------
#
# 审阅闭环（改后修订）抓到的缺口：T1 的 ``_SCHEMA_ENUM_BINDINGS`` 只覆盖 ``spec``
# **嵌套内**的 enum（``spec.properties.nodes/edges.items.properties``）。而
# ``CreateSubagent.mode`` 是**顶层参数**（``parameters.properties.mode``）——Q6 的
# 「一并派生」在代码里成立了，却**没有任何测试保护**：把它的 enum 改回手写字面量
# （漏掉 ``plan``）36 个测试全绿。以下把 spec 外的每个模型可见 enum 也钉到各自
# 的单一来源上，并加一条清单守卫防未来再出现无守卫的 enum。


def test_create_subagent_mode_enum_matches_node_modes():
    """Q6：``CreateSubagent.mode`` 的 enum 必须与 ``workflow.NODE_MODES`` 逐字相等。

    这是审阅闭环发现的**假保护**缺口：``mode`` 在 ``CreateSubagent`` 的**顶层参数**
    上，不在 ``spec`` 嵌套里，故 T1 的绑定表够不到它。改成手写 ``["build","read_only"]``
    （漏 ``plan``）时本断言必红。
    """
    enum = CreateSubagentTool.parameters["properties"]["mode"]["enum"]
    assert tuple(enum) == tuple(workflow_dsl.NODE_MODES)


def test_run_workflow_template_enum_matches_pattern_registry():
    """``RunWorkflow.template`` 的 enum 从 ``patterns.PATTERNS`` 派生（单一来源）。

    模板注册表加/删模板时，schema 必须自动跟；手写副本会漂移。
    """
    enum = RunWorkflowTool.parameters["properties"]["template"]["enum"]
    assert tuple(enum) == tuple(PATTERNS)


def test_get_workflow_detail_enum_matches_runtime_validator():
    """``GetWorkflow.detail`` 的 enum 与运行期校验的 ``_DETAILS`` 同源（单一来源）。"""
    enum = GetWorkflowTool.parameters["properties"]["detail"]["enum"]
    assert tuple(enum) == tuple(GetWorkflowTool._DETAILS)


#: 全部**模型可见**的顶层 enum 参数：(工具, 参数名, 期望的单一来源 callable)。
#: 新增任何带 enum 的工具参数时，必须在这里登记一个来源——否则清单守卫会红。
_TOP_LEVEL_ENUM_BINDINGS = [
    (CreateSubagentTool, "mode", lambda: workflow_dsl.NODE_MODES),
    (RunWorkflowTool, "template", lambda: PATTERNS),
    (GetWorkflowTool, "detail", lambda: _GET_WORKFLOW_DETAILS),
    (InspectSubagentTranscriptTool, "scope", lambda: TRANSCRIPT_SCOPES),
]


@pytest.mark.parametrize(
    "tool, field, source",
    _TOP_LEVEL_ENUM_BINDINGS,
    ids=[f"{t.__name__}.{f}" for t, f, _ in _TOP_LEVEL_ENUM_BINDINGS],
)
def test_top_level_enum_matches_source(tool, field, source):
    enum = tool.parameters["properties"][field]["enum"]
    assert tuple(enum) == tuple(source())


def test_no_unguarded_model_visible_enum():
    """清单守卫：subagents.py 里**每个**模型可见的顶层 enum 都已被登记。

    扫描每个工具 ``parameters.properties.*.enum``，若出现一个不在
    ``_TOP_LEVEL_ENUM_BINDINGS``（顶层）也不在嵌套 spec 绑定表里的 enum，本条变红——
    逼迫新增 enum 时同补一条 parity，杜绝再一次「代码对了但没有测试保护」。
    """
    import inspect

    from agent.tools.base import Tool
    from agent.tools.builtin import subagents as mod

    # 顶层已守卫的 (工具名, 字段)
    guarded_top = {(t.name, f) for t, f, _ in _TOP_LEVEL_ENUM_BINDINGS}
    # spec 嵌套内的字段（由 _SCHEMA_ENUM_BINDINGS 经 T1 守卫）；`spec` 参数名本身不算顶层 enum
    spec_nested_fields = {f for f, _, _ in _SCHEMA_ENUM_BINDINGS}

    unguarded: list[str] = []
    for _name, cls in inspect.getmembers(mod, inspect.isclass):
        if not (issubclass(cls, Tool) and cls.__module__ == mod.__name__):
            continue
        if not getattr(cls, "name", None):
            continue
        for field, schema in (cls.parameters.get("properties") or {}).items():
            if not isinstance(schema, dict) or "enum" not in schema:
                continue
            if field == "spec":
                continue  # 嵌套 spec 由 T1 单独覆盖
            if field in spec_nested_fields:
                continue
            if (cls.name, field) not in guarded_top:
                unguarded.append(f"{cls.name}.{field}")
    assert not unguarded, (
        f"model-visible enum(s) without a parity guard: {unguarded}; "
        f"add them to _TOP_LEVEL_ENUM_BINDINGS (or the spec-nested table)."
    )


# --- T2：描述内容断言 --------------------------------------------------------


def test_description_has_no_control_token():
    """T2：``control`` 在 DeclareWorkflow 描述中零命中（两条断言都要）。

    R-A：只断言原样会漏掉 ``Control`` 一类大写变体；只断言 ``.lower()`` 会让中文
    「控制边」绕过。两条叠加才封住两处自伤面。
    """
    desc = DeclareWorkflowTool.description
    assert "control" not in desc
    assert "control" not in desc.lower()


@pytest.mark.parametrize("tool", _TOOLS, ids=lambda t: t.__name__)
def test_model_visible_surface_has_no_control_token(tool):
    """T2（审阅闭环 R1 补强）：``control`` 在整个**模型可见面**零命中。

    模型每次 API 调用拿到的不只是 ``description``，还有 ``parameters``（= 逐字透传的
    ``input_schema``）。D3 承诺「模型可见面不再出现诱导性 token」，故零命中断言必须覆盖
    **描述 + schema 的每一层 description**——只在 ``description`` 上断言会漏掉 schema 里的
    措辞（审阅实测漏掉了 edge ``required`` 的字段描述）。
    """
    import json

    surfaces = [tool.description, json.dumps(tool.parameters, ensure_ascii=False)]
    for surface in surfaces:
        assert "control" not in surface
        assert "control" not in surface.lower()


def test_description_covers_cases_semantics():
    """T2：cases 匹配语义（行首前缀 + 声明顺序 first-match + 具体在前的正例）。"""
    desc = DeclareWorkflowTool.description
    lowered = desc.lower()
    # 行首前缀匹配，不是子串包含
    assert "startswith" in lowered or "prefix" in lowered
    # 声明顺序 first-match-wins
    assert "first-match" in lowered or "first match" in lowered
    # 具体/更长模式排在宽泛模式之前的正例（D4）
    assert "GAPS: none" in desc
    assert "GAPS" in desc
    # when 的两种形态之一：$ref 动态条件源
    assert "$ref:" in desc


def test_description_has_per_kind_field_table():
    """T2：per-kind 字段适用表存在（join/items/source 作为**字段名**出现，D5）。"""
    desc = DeclareWorkflowTool.description
    lowered = desc.lower()
    for field in ("join", "items", "source", "strategy", "max_routes"):
        assert field in lowered, field
    # 字段到 kind 的归属必须写明，而不是只出现字段名
    assert "aggregate" in lowered
    assert "route" in lowered
    assert "foreach" in lowered


def test_description_keeps_the_existing_cycle_contract():
    """T2a 回归：既有循环契约断言全部保持绿（只插入与纠错，不删既有文字）。"""
    text = DeclareWorkflowTool.description
    lowered = text.lower()
    assert "max_routes" in lowered
    assert "required" in lowered
    assert "entry" in lowered
    assert "defaults to 1" in lowered
    assert "per route node" in lowered
    assert "reset" in lowered
    assert "correct cycle" in lowered
    assert "rejected cycle" in lowered
    assert "gate->producer" in text
    assert "body->gate" in text


def test_description_length_within_budget():
    """T5：描述长度守卫（宽松上界），防分节演变成无节制扩张。不设下界。"""
    assert len(DeclareWorkflowTool.description) <= 6000


def test_description_discloses_graph_level_gate_defaults():
    """T6（change ``workflow-limit-visibility``，D5）：描述披露图级三闸**模块默认值**。

    **宽松匹配**：只断言「三闸名 + 三个数值」出现，不绑定运行时配置（描述是静态
    文本，而生效值随配置变化——R4/Q6 要防的正是「描述说 200、报告说 777」的分叉）。
    断言限定词「graph-level」与「以报告为准」也在，把静态默认值与运行期生效值分开。
    """
    desc = DeclareWorkflowTool.description
    lowered = desc.lower()
    for field in ("recursion_limit", "max_nodes", "max_runs"):
        assert field in lowered, field
    for value in ("100", "200", "300"):
        assert value in desc, value
    assert "graph-level" in lowered, "须限定为「图级」以区别于路由级 max_routes"
    assert "default" in lowered
    assert "effective" in lowered, "须指向报告的生效值（避免与运行期配置分叉）"
    # 既有的路由级披露不被挤掉（回归）
    assert "defaults to 1" in lowered


# --- T3：route 节点的 ``task`` → 可行动 warnings（Q1 选 (b)） -----------------


def _route_task_spec() -> dict:
    """route 带 task 的声明——今天被静默忽略（``_execute_route`` 不读它）。

    非环：``gate`` 默认选 ``done``（一个终态 aggregate），保证跑起来能收敛到终态
    （本用例验的是 warning，不是环语义）。
    """
    return {
        "goal": "g",
        "nodes": [
            {"id": "a", "kind": "subagent", "task": "t"},
            {
                "id": "gate",
                "kind": "route",
                "task": "decide whether to redo",
                "default": "done",
            },
            {"id": "done", "kind": "aggregate", "strategy": "collect"},
        ],
        "edges": [
            {"from": "a", "to": "gate"},
            {"from": "gate", "to": "done"},
        ],
        "entry": ["a"],
        "terminal": ["done"],
    }


def _assert_actionable_warning(warnings: list[str]) -> None:
    """warning 必须**可行动**：既说哪里错了，也说改到哪里去（用户 Q1 追加要求）。"""
    assert warnings, "expected a warning for route `task`"
    hit = next(w for w in warnings if "gate" in w)
    lowered = hit.lower()
    # 哪里错了：route 的 task 不会被执行
    assert "route" in lowered
    assert "task" in lowered
    assert "never execute" in lowered or "not execute" in lowered or "ignored" in lowered
    # 改到哪里去：判定逻辑写在 cases[].when
    assert "cases" in lowered and "when" in lowered


def test_declare_warns_on_route_task(manager):
    """T3：DeclareWorkflow 的 declared 返回体含可行动 warnings。"""
    out = _declare(manager, _route_task_spec())
    assert out["status"] == "declared"
    _assert_actionable_warning(out["warnings"])


@pytest.mark.asyncio
async def test_run_workflow_spec_warns_on_route_task(manager):
    """T3 + C8：RunWorkflow(spec=...) 走**另一条路径**，同样必须拿到 warning。"""
    out = json.loads(await RunWorkflowTool(manager).execute(spec=_route_task_spec()))
    assert out["status"] in ("completed", "failed", "blocked")
    _assert_actionable_warning(out["warnings"])


def test_no_warning_when_route_has_no_task(manager):
    """负向：route 不带 task 时 ``warnings`` 为空——不无中生有。"""
    spec = _route_task_spec()
    spec["nodes"][1].pop("task")
    out = _declare(manager, spec)
    assert out["status"] == "declared"
    assert out["warnings"] == []


# --- T4：负向路径的报错按**实际** kind 命名（D7） ----------------------------


def test_kind_mismatch_error_names_the_actual_kind():
    """T4：``{"kind":"route","strategy":"concat"}`` 的拒绝信息须按实际 kind 命名。

    今天是 ``aggregate node 'g' strategy must be one of [...]``——节点是 route，
    报的却是 aggregate。
    """
    with pytest.raises(WorkflowValidationError) as excinfo:
        parse_workflow_spec(
            {
                "goal": "g",
                "nodes": [{"id": "g", "kind": "route", "strategy": "concat"}],
                "edges": [],
                "entry": ["g"],
                "terminal": ["g"],
            }
        )
    message = str(excinfo.value)
    assert "route node 'g'" in message
    assert not message.startswith("aggregate node")
    # 且指出该字段真正属于哪个 kind
    assert "aggregate" in message


def test_kind_mismatch_error_stays_accurate_for_the_owning_kind():
    """对照：字段用在**正确** kind 上时，文案仍按该 kind 命名（不引入噪音）。"""
    with pytest.raises(WorkflowValidationError) as excinfo:
        parse_workflow_spec(
            {
                "goal": "g",
                "nodes": [{"id": "g", "kind": "aggregate", "strategy": "concat"}],
                "edges": [],
                "entry": ["g"],
                "terminal": ["g"],
            }
        )
    assert str(excinfo.value).startswith("aggregate node 'g'")


# --- T6：描述里的修正后正例可逐字声明 ---------------------------------------


def test_description_positive_example_declares(manager):
    """T6：用描述里给出的修正后正例逐字声明，SHALL 成功。"""
    spec = {
        "goal": "review loop",
        "nodes": [
            {"id": "producer", "kind": "subagent", "task": "produce a draft"},
            {"id": "reviewer", "kind": "subagent", "task": "review the draft"},
            {"id": "gate", "kind": "route", "max_routes": 3, "default": "join"},
            {"id": "join", "kind": "aggregate", "strategy": "collect"},
        ],
        "edges": [
            {"from": "producer", "to": "reviewer"},
            {"from": "reviewer", "to": "gate"},
            {"from": "gate", "to": "join"},
            {"from": "gate", "to": "producer"},
        ],
        "entry": ["producer"],
        "terminal": ["join"],
    }
    out = _declare(manager, spec)
    assert out["status"] == "declared", out.get("reason")
