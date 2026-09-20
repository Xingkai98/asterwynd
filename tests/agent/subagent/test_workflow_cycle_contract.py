"""循环契约：声明期「环必须能启动」校验 + 可操作报错 + 提示面（issue #219）。

对应 change ``workflow-cycle-contract`` 的 tasks 1.x / 3.x / 4.x。

判据（design D1，经独立 grill 实测重写）：环（SCC）内**任一节点可证明永不派发**即拒绝。
「可派发」按调度器真实派发语义（``_ready_nodes`` / ``_data_deps_satisfied`` / ``_is_entry``）
的最小不动点静态判定——取最小集，故只拒绝可证明跑不起来的环，不误报。

被拒的初版判据（实测证伪，见 ``reviews/grill-design.md``）：

- 「环内无产出节点」漏报：环内有两个 subagent 但互相 required 等待时通过声明、实跑全 blocked；
- 「route 有同环内 required 数据入边」误报：会拒绝官方 ``peer-review`` pattern。
"""
import asyncio
import json

import pytest

from agent.config import AsterwyndConfig
from agent.llm import LLMResponse, Usage
from agent.run_config import AgentMode
from agent.subagent.manager import SubAgentManager
from agent.subagent.patterns import compile_pattern
from agent.subagent.workflow import (
    WorkflowCycleError,
    WorkflowValidationError,
    parse_workflow_spec,
)
from agent.tools.builtin.subagents import DeclareWorkflowTool
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


# --- 1.1 #219 原始形态：route + collect 体，环内 required 数据边 --------------


def _spin_spec() -> dict:
    """#219 形态：``body`` 是 collect 聚合、唯一数据入参来自不产数据的 route。

    环 ``{cycle_gate, body}`` 内：``body`` 等 ``cycle_gate`` 的 required 数据、
    ``cycle_gate`` 等 ``body``——没有任何节点能先跑起来。当前（master）能声明成功，
    实跑环内节点全 ``blocked``、图报 ``completed``（见 tasks 1.1）。
    """
    return {
        "goal": "spin",
        "nodes": [
            {"id": "cycle_gate", "kind": "route", "task": "route",
             "cases": [{"when": "CONTINUE", "to": "body"}], "default": "end",
             "max_routes": 3},
            {"id": "body", "kind": "aggregate", "strategy": "collect",
             "join": "all_required"},
            {"id": "end", "kind": "aggregate", "strategy": "collect",
             "join": "all_required"},
        ],
        "edges": [
            {"from": "cycle_gate", "to": "body"},
            {"from": "cycle_gate", "to": "end"},
            {"from": "body", "to": "cycle_gate"},
        ],
        "entry": ["cycle_gate"],
        "terminal": ["end"],
    }


def test_unstartable_cycle_is_rejected_at_declaration():
    """1.1 环内无任何节点能先跑起来 → 声明期拒绝，且不再返回 workflow_id。"""
    with pytest.raises(WorkflowCycleError):
        parse_workflow_spec(_spin_spec())


def test_rejection_message_names_the_cycle_members():
    """D5-要素一「哪个环」：错误信息必须点名环成员节点 id。"""
    with pytest.raises(WorkflowCycleError) as excinfo:
        parse_workflow_spec(_spin_spec())
    message = str(excinfo.value)
    assert "body" in message and "cycle_gate" in message


# --- 1.2 反向：环内有 subagent 但全部互等（grill Q1 场景） --------------------


def _inner_lock_spec() -> dict:
    """grill Q1 场景：环内**有**两个 subagent（``a``/``c``），但 ``b``/``c`` 互相 required 等待。

    被推翻的「环内无产出节点」判据会**放行**这张图（环内有产出节点），实跑 ``b``/``c``
    双双永久 ``blocked``、图报 ``completed``、``diagnostics`` 为空——正是 #219 要消灭的现象。
    """
    return {
        "goal": "inner lock",
        "recursion_limit": 100,
        "nodes": [
            {"id": "g", "kind": "route", "max_routes": 4,
             "cases": [{"when": "GO", "to": "a"}], "default": "a"},
            {"id": "a", "kind": "subagent", "task": "a"},
            {"id": "b", "kind": "aggregate", "strategy": "collect",
             "join": "all_required"},
            {"id": "c", "kind": "subagent", "task": "c"},
            {"id": "end", "kind": "aggregate", "strategy": "collect",
             "join": "all_required"},
        ],
        "edges": [
            {"from": "g", "to": "a"},
            {"from": "a", "to": "b", "reducer": "concat"},
            {"from": "b", "to": "c"},
            {"from": "c", "to": "b", "reducer": "concat"},
            {"from": "c", "to": "g", "required": False},
            {"from": "g", "to": "end"},
        ],
        "entry": ["g"],
        "terminal": ["end"],
    }


def test_cycle_with_producing_node_but_all_waiting_is_rejected():
    """1.2「环内有产出节点」不构成可启动性 → 仍须拒绝。"""
    with pytest.raises(WorkflowCycleError) as excinfo:
        parse_workflow_spec(_inner_lock_spec())
    message = str(excinfo.value)
    assert "b" in message and "c" in message


# --- 1.3 正向：环内有能自启动的 entry --------------------------------------


def _startable_loop_spec() -> dict:
    """peer-review 形态：``producer`` 是 entry 且 required 输入来自环外（无）→ 能先跑起来。"""
    return {
        "goal": "startable loop",
        "nodes": [
            {"id": "producer", "kind": "subagent", "task": "produce",
             "outputs": ["result"]},
            {"id": "reviewer", "kind": "subagent", "task": "review",
             "outputs": ["result"]},
            {"id": "gate", "kind": "route", "task": "route on the verdict",
             "cases": [{"when": "APPROVED", "to": "done"}], "default": "producer",
             "max_routes": 5},
            {"id": "done", "kind": "subagent", "task": "done", "outputs": ["result"]},
        ],
        "edges": [
            {"from": "producer", "to": "reviewer"},
            {"from": "reviewer", "to": "gate"},
            {"from": "gate", "to": "done"},
            {"from": "gate", "to": "producer"},
        ],
        "entry": ["producer"],
        "terminal": ["done"],
    }


def test_startable_cycle_is_accepted():
    """1.3 环内有能自启动的节点 → 通过。"""
    spec = parse_workflow_spec(_startable_loop_spec())
    assert spec.entry == ("producer",)


# --- 1.4 / 1.5 正向：环内的 aggregate(llm) 与 foreach 只要可启动就通过 --------


def _loop_through_node(inner: dict, inner_outputs: list[str]) -> dict:
    """``kick``（环外 entry）→ ``inner`` → ``gate``(route) → ``inner`` 的回边环。

    ``inner`` 必须**同时**是 entry：它有来自 ``gate`` 的控制入边，若不显式列进
    ``spec.entry``，调度器就要求 ``gate`` 先激活它——而 ``gate`` 又在等它，环便启动不了
    （这正是契约要讲清的那一点）。
    """
    return {
        "goal": "loop through node",
        "nodes": [
            {"id": "kick", "kind": "subagent", "task": "kick",
             "outputs": ["seed"]},
            {**inner, "outputs": inner_outputs},
            {"id": "gate", "kind": "route", "task": "route",
             "cases": [{"when": "STOP", "to": "done"}], "default": "inner",
             "max_routes": 3},
            {"id": "done", "kind": "subagent", "task": "done", "outputs": ["result"]},
        ],
        "edges": [
            {"from": "kick", "to": "inner", "reducer": "concat"},
            {"from": "inner", "to": "gate"},
            {"from": "gate", "to": "done"},
            {"from": "gate", "to": "inner"},
        ],
        "entry": ["kick", "inner"],
        "terminal": ["done"],
    }


def test_cycle_with_llm_aggregate_is_accepted():
    """1.4 环内是 ``aggregate(strategy="llm")`` 且能启动 → 通过。"""
    spec = parse_workflow_spec(
        _loop_through_node(
            {"id": "inner", "kind": "aggregate", "strategy": "llm",
             "join": "all_required"},
            ["result"],
        )
    )
    assert spec.node("inner").strategy == "llm"


def test_cycle_with_foreach_is_accepted():
    """1.5 环内是 ``foreach`` 且能启动 → 通过。"""
    spec = parse_workflow_spec(
        _loop_through_node(
            {"id": "inner", "kind": "foreach", "task": "work {item}",
             "items": [{"name": "one"}]},
            ["result"],
        )
    )
    assert spec.node("inner").kind == "foreach"


# --- 1.6 正向：回边从 route 出发（控制边） ---------------------------------


def test_control_back_edge_from_route_is_accepted():
    """1.6 ``route`` 出边是控制边、不参与门控 → 不构成互等。"""
    spec = parse_workflow_spec(_startable_loop_spec())
    assert spec.is_control_edge(spec.edge_between("gate", "producer"))


# --- 1.7 正向：回边 required:false 且环能启动 -------------------------------


def _open_back_edge_spec() -> dict:
    """#220 形态：``gate``(route) 是 entry，回边 ``body → gate`` 显式 ``required: false``。

    这条回边**从非 route 节点出发**，故是数据边；``required: false`` 让它不参与门控
    （``_data_deps_satisfied`` 对 required 为假的边 ``continue``），环因此能启动。
    """
    return {
        "goal": "open back edge",
        "nodes": [
            {"id": "gate", "kind": "route", "max_routes": 3,
             "cases": [{"when": "CONTINUE", "to": "body"}], "default": "body"},
            {"id": "body", "kind": "aggregate", "strategy": "collect",
             "join": "all_required"},
            {"id": "end", "kind": "aggregate", "strategy": "collect",
             "join": "all_required"},
        ],
        "edges": [
            {"from": "gate", "to": "body"},
            {"from": "gate", "to": "end"},
            {"from": "body", "to": "gate", "required": False},
        ],
        "entry": ["gate"],
        "terminal": ["end"],
    }


def test_required_false_back_edge_on_startable_cycle_is_accepted():
    """1.7 ``required: false`` 的回边不门控上游 → 环能启动则通过。"""
    spec = parse_workflow_spec(_open_back_edge_spec())
    assert spec.entry == ("gate",)


# --- 1.8 反向：环外 required 数据边喂进环、环内无 entry ---------------------


def _fed_from_outside_spec() -> dict:
    """``kick``（环外）以 required 数据边喂 ``body``，但 ``body``/``gate`` 都没法先跑。

    ``body`` 不是 entry、有控制入边（来自 ``gate``），而 ``gate`` 又在等 ``body``
    的 required 数据——不动点只有 ``kick``，环内零节点可派发。
    """
    return {
        "goal": "fed from outside",
        "nodes": [
            {"id": "kick", "kind": "subagent", "task": "kick", "outputs": ["raw"]},
            {"id": "body", "kind": "aggregate", "strategy": "collect",
             "join": "all_required", "outputs": ["result"]},
            {"id": "gate", "kind": "route", "task": "route",
             "cases": [{"when": "STOP", "to": "done"}], "default": "body",
             "max_routes": 3},
            {"id": "done", "kind": "subagent", "task": "done", "outputs": ["result"]},
        ],
        "edges": [
            {"from": "kick", "to": "body", "reducer": "concat"},
            {"from": "body", "to": "gate"},
            {"from": "gate", "to": "done"},
            {"from": "gate", "to": "body"},
        ],
        "entry": ["kick"],
        "terminal": ["done"],
    }


def test_cycle_fed_from_outside_without_entry_is_rejected():
    """1.8 环外的 required 数据边救不了没有启动点的环 → 拒绝。"""
    with pytest.raises(WorkflowCycleError):
        parse_workflow_spec(_fed_from_outside_spec())


# --- 1.9 回归红线：官方 4 pattern 全部仍能声明通过 --------------------------


@pytest.mark.parametrize(
    "pattern,params",
    [
        ("orchestrator-worker", {"workers": 3}),
        ("peer-review", {"max_rounds": 3}),
        ("hierarchical", {"teams": 2}),
        ("bidding", {"proposers": 3}),
    ],
)
def test_builtin_patterns_still_declare(pattern, params, manager):
    """1.9 ``peer-review`` 是本项目唯一能工作的多轮审阅循环，绝不能被误杀。"""
    spec = compile_pattern(pattern, task="do the task", params=params)
    out = _declare(manager, spec.to_dict())
    assert out["status"] == "declared", out


# --- 2.x / 3.x 报错三要素：哪个环 / 缺什么 / 怎么改 --------------------------


def test_reason_says_what_is_missing():
    """D5-要素二「缺什么」：逐条说清谁在等谁。"""
    with pytest.raises(WorkflowCycleError) as excinfo:
        parse_workflow_spec(_spin_spec())
    message = str(excinfo.value).lower()
    assert "wait" in message
    assert "required" in message


def test_reason_gives_an_actionable_fix():
    """D5-要素三「怎么改」：给出可照做的动作，不只陈述规则。"""
    with pytest.raises(WorkflowCycleError) as excinfo:
        parse_workflow_spec(_spin_spec())
    message = str(excinfo.value).lower()
    assert "how to fix" in message
    # 同环 required 数据边 → 点名建议 required: false（D2 的诊断价值并入）
    assert '"required": false' in str(excinfo.value)


def test_reason_points_at_the_required_edges_inside_the_cycle():
    """D2 并入：被拒环内的同环 required 数据边必须在报错里点名。"""
    with pytest.raises(WorkflowCycleError) as excinfo:
        parse_workflow_spec(_spin_spec())
    message = str(excinfo.value)
    assert "body" in message and "cycle_gate" in message
    assert "same cycle" in message.lower()


def test_declare_failure_is_self_sufficient_for_the_model(manager):
    """3.4「模型视角」：``reason`` + ``hint`` 合起来必须回答「哪里错 / 为什么 / 怎么改」。

    ``_invalid_spec`` 的返回体**没有 workflow_id**，模型拿不到可运行的图——这两个字段是
    它唯一的信息来源，必须自足。
    """
    out = _declare(manager, _spin_spec())
    assert out["status"] == "invalid_spec"
    reason, hint = out["reason"], out["hint"]

    # 哪里错：点名环成员
    assert "body" in reason and "cycle_gate" in reason
    # 为什么：说清谁在等谁
    assert "wait" in reason.lower()
    # 怎么改：给出可照做的动作
    assert "required" in reason.lower() or "entry" in reason.lower()
    # hint 必须指向「这次调用没有 workflow_id」这个关键事实
    assert "workflow_id" in hint


def test_declare_success_still_returns_workflow_id(manager):
    """反例对照：能启动的环照常拿到 workflow_id（拒绝路径没有伤到正向路径）。"""
    out = _declare(manager, _startable_loop_spec())
    assert out["status"] == "declared"
    assert out["workflow_id"].startswith("wf_")


# --- 4.x 提示面：DeclareWorkflow 描述暴露循环契约 ---------------------------


def _declare_description() -> str:
    return DeclareWorkflowTool.description


def test_description_states_the_start_rule():
    """4.1 核心规则：环里必须有个节点先跑起来，且不能反过来等环里的节点。"""
    text = _declare_description().lower()
    assert "start on its own" in text or "starts on its own" in text


def test_description_covers_the_four_cycle_contracts():
    """4.2 回边方向 / required:false / max_routes 默认值、配置位置与累加语义。"""
    text = _declare_description().lower()
    assert "max_routes" in text
    assert "required" in text
    assert "entry" in text
    # 默认值 1 + 逐（route）节点配置 + 跨轮累加不重置
    assert "defaults to 1" in text
    assert "per route node" in text
    assert "reset" in text


def test_description_has_a_positive_example_and_a_counterexample():
    """4.3 描述附最小正例与反例，而不是只罗列规则。"""
    text = _declare_description().lower()
    assert "correct" in text or "valid" in text or "works" in text
    assert "wrong" in text or "rejected" in text or "bad" in text


# --- 6.1 声明期拒绝不得伤及运行期诊断（Q5：terminal_honesty 改造后仍覆盖） ---


def test_runtime_diagnosis_survives_declaration_rejection():
    """本 change 只拦**声明期入口**：运行期互等诊断由 terminal_honesty 套件继续覆盖。

    这里只锁住「校验发生在 parse_workflow_spec 内、且抛的是可识别的循环错误」，
    以保证运行期测试知道该绕过哪一个入口。
    """
    try:
        parse_workflow_spec(_spin_spec())
    except WorkflowValidationError as exc:
        assert isinstance(exc, WorkflowCycleError)
    else:  # pragma: no cover - 校验缺失时给出明确失败
        pytest.fail("unstartable cycle must be rejected at declaration")
