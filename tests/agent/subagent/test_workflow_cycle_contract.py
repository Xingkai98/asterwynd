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


# --- 误报防线（building-review Issue 1/2）：判据必须过近似真实派发规则 -------


def _best_effort_cycle_spec() -> dict:
    """环内是 ``best_effort`` 聚合：调度器对 ``deadline_fired`` 的节点**直接放行**。

    ``_ready_nodes`` 在 ``state.deadline_fired`` 为真时既不看数据门控也不看
    ``activations``（``scheduler.py`` 的 ``_ready_nodes``）。所以即使 ``body`` 不是
    entry、且被 ``gate`` 控制，它也会在截止到点时被派发——这张图在 master 上声明成功
    且真能循环（``gate`` 派发 3 次、``body`` completed）。
    """
    return {
        "goal": "best effort cycle",
        "recursion_limit": 20,
        "max_runs": 60,
        "nodes": [
            {"id": "seed", "kind": "subagent", "task": "seed", "outputs": ["result"]},
            {"id": "gate", "kind": "route", "task": "gate", "max_routes": 3,
             "cases": [{"when": "GO", "to": "body"}], "default": "body"},
            {"id": "body", "kind": "aggregate", "strategy": "collect",
             "join": "best_effort", "deadline_s": 0.05, "outputs": ["result"]},
        ],
        "edges": [
            {"from": "seed", "to": "body", "required": False, "reducer": "concat"},
            {"from": "gate", "to": "body"},
            {"from": "body", "to": "gate", "reducer": "concat"},
        ],
        "entry": ["seed"],
        "terminal": ["gate"],
    }


def test_best_effort_aggregate_in_cycle_is_not_a_false_positive():
    """Issue 1：``deadline_fired`` 短路是真派发路径，判据不得据此拒绝能跑的图。"""
    spec = parse_workflow_spec(_best_effort_cycle_spec())
    assert spec.node("body").join == "best_effort"


def _route_target_without_edge_spec() -> dict:
    """``route`` 的 ``default`` 指向环内节点，但**没有声明这条边**。

    调度器 ``_execute_route`` 按 ``cases[].to`` / ``node.default`` 的 **target id**
    直接 ``activations += 1``，从不检查有没有对应声明边；``_validate_kind_specific``
    也只要求目标是已知节点。所以这条激活路径真实存在，判据必须算上它。
    """
    return {
        "goal": "route target without edge",
        "recursion_limit": 20,
        "max_runs": 60,
        "nodes": [
            {"id": "B", "kind": "route", "task": "B", "max_routes": 3,
             "cases": [], "default": "n0"},
            {"id": "n0", "kind": "subagent", "task": "n0", "outputs": ["result"]},
            {"id": "n1", "kind": "route", "task": "n1", "max_routes": 3,
             "cases": [], "default": "n0"},
        ],
        "edges": [
            {"from": "n0", "to": "n1", "reducer": "concat"},
            {"from": "n1", "to": "n0"},
        ],
        "entry": ["B"],
        "terminal": ["n1"],
    }


def test_route_activation_without_declared_edge_is_not_a_false_positive():
    """Issue 2：``default`` 目标无声明边也是一条真实激活路径，不得据此拒绝。"""
    parse_workflow_spec(_route_target_without_edge_spec())


def test_self_loop_route_is_accepted():
    """自环（``route`` 指向自己）走 ``_cycle_members`` 的自环分支：entry 能自启动 → 通过。"""
    spec = parse_workflow_spec({
        "goal": "self loop",
        "nodes": [{"id": "g", "kind": "route", "cases": [], "default": "g",
                   "max_routes": 3}],
        "edges": [{"from": "g", "to": "g"}],
        "entry": ["g"],
        "terminal": ["g"],
    })
    assert spec.node("g").kind == "route"


def test_one_stuck_cycle_among_startable_ones_is_rejected():
    """多个环并存：只要其中一个跑不起来就拒绝，且报错只点名那个环。

    ``live`` 是 entry（能自启动）→ 它的环 ``{live, glive}`` 没问题；``dead`` 不是
    entry 且被 ``gdead`` 控制、而 ``gdead`` 又在等它 → 环 ``{dead, gdead}`` 跑不起来。
    """
    with pytest.raises(WorkflowCycleError) as excinfo:
        parse_workflow_spec({
            "goal": "two cycles",
            "nodes": [
                {"id": "live", "kind": "subagent", "task": "live",
                 "outputs": ["result"]},
                {"id": "glive", "kind": "route", "cases": [], "default": "live",
                 "max_routes": 2},
                {"id": "dead", "kind": "aggregate", "strategy": "collect",
                 "join": "all_required"},
                {"id": "gdead", "kind": "route", "cases": [], "default": "dead",
                 "max_routes": 2},
            ],
            "edges": [
                {"from": "live", "to": "glive", "reducer": "concat"},
                {"from": "glive", "to": "live"},
                {"from": "gdead", "to": "dead"},
                {"from": "dead", "to": "gdead", "reducer": "concat"},
            ],
            "entry": ["live"],
            "terminal": ["glive"],
        })
    message = str(excinfo.value)
    # 能启动的环 {live, glive} 不该被点名
    assert "live" not in message
    # 跑不起来的环必须被点名
    assert "gdead" in message and "dead" in message


def test_error_message_is_bounded_for_a_large_cycle():
    """Issue 4：大环的报错不得无界增长；截断处要注明还剩几项。"""
    n = 58
    # route 必须在环内（否则先被 ``_validate_cycles`` 的「环上必须有 route」拦下）。
    raw = {
        "goal": "big cycle",
        "max_nodes": 200,
        "nodes": [
            {"id": f"n{i}", "kind": "aggregate", "strategy": "collect",
             "join": "all_required"}
            for i in range(n)
        ] + [{"id": "g", "kind": "route", "cases": [], "default": "n0",
              "max_routes": 2}],
        "edges": [{"from": f"n{i}", "to": f"n{(i + 1) % n}", "reducer": "concat"}
                  for i in range(n)]
        + [{"from": f"n{n - 1}", "to": "g", "reducer": "concat"},
           {"from": "g", "to": "n0"}],
        "entry": ["g"],
        "terminal": ["g"],
    }
    with pytest.raises(WorkflowCycleError) as excinfo:
        parse_workflow_spec(raw)
    message = str(excinfo.value)
    assert "more)" in message, "截断必须注明剩余条数"
    assert len(message) < 2500, f"报错过长（{len(message)} 字符）"


# --- 2.x / 3.x 报错三要素：哪个环 / 缺什么 / 怎么改 --------------------------


def test_reason_says_what_is_missing():
    """D5-要素二「缺什么」：逐条说清谁在等谁（具体到节点与边类型）。"""
    with pytest.raises(WorkflowCycleError) as excinfo:
        parse_workflow_spec(_spin_spec())
    message = str(excinfo.value)
    assert "waiting on:" in message
    # 具体到「谁在等谁」，且说明是 required 数据等待
    assert "'cycle_gate' waits for required data from 'body' (same cycle)" in message


def test_reason_does_not_blame_the_control_edge():
    """Issue 3：``route`` 出边是控制边、不门控——不得把它说成 required 数据等待。

    模型能做的动作是「给这条边加 required: false」，而对控制边做这件事**没有任何效果**
    （实跑：照做后图仍被拒）。报错把模型指向无效动作，正是本 change 要消灭的那类假话。
    """
    with pytest.raises(WorkflowCycleError) as excinfo:
        parse_workflow_spec(_spin_spec())
    message = str(excinfo.value)
    assert "'body' waits for required data from 'cycle_gate'" not in message


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
    """4.3 描述附最小正例与反例——断言**具体节点串**，删掉任一段都会变红。"""
    text = _declare_description()
    lowered = text.lower()
    assert "correct cycle" in lowered
    assert "rejected cycle" in lowered
    # 正例的骨架：route 回边（控制边）
    assert "gate->producer" in text
    # 反例的骨架：数据回边 + 修法
    assert "body->gate" in text
    assert "required" in lowered


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
