"""动态 route 条件源 ``$ref:node:slot``（change ``workflow-budget-attribution``，task 3.1）。

覆盖 D4 与 grill 决策 9 及用户确认 Q1/Q2/Q3：

- 判定语义（Q1/Q2 联合）：``$ref`` 解析出槽值 → **取首个非空行**作**期望标签** →
  传入 ``matches_route(上游数据文本, 该标签)`` 做行首匹配；
- 判定前**不调** ``WorkflowAggregator.bounded``（它追加 ``…[bounded...]`` 并可能
  截断首行，让标签永远不命中；``bounded`` 只用于诊断展示）；
- 运行时解析**只读 ``NodeState.slots``**（spec D4：不落盘、不读文件、不做
  ``_node_output`` 的跨节点回退）；
- 校验强度（Q3）：**节点存在 + 槽已声明**（含隐式 ``result`` 槽），不把数据可达性
  作 schema 硬条件；
- 运行时槽缺失**静默视为未命中走 default**（不报错），diagnostics 记录未命中原因。
"""
import pytest

from agent.config import AsterwyndConfig
from agent.llm import LLMResponse, Usage
from agent.run_config import AgentMode
from agent.subagent.manager import SubAgentManager
from agent.subagent.scheduler import WorkflowScheduler
from agent.subagent.workflow import (
    WorkflowValidationError,
    parse_workflow_spec,
)
from agent.workspace_policy import WorkspacePolicy

_LONG_SUFFIX = "\n".join(f"detail line {i}: " + "x" * 120 for i in range(40))


class VerdictLLM:
    """``producer`` 产出一段长评审文本（首行 ``APPROVED`` 或 ``CRITIQUE``）。"""

    def __init__(self, verdict="APPROVED", long_form=True):
        self.verdict = verdict
        self.long_form = long_form

    async def chat(self, messages, tools=None, model="gpt-4"):
        first_line = messages[-1].content.splitlines()[0].strip().lower()
        if first_line.startswith("produce"):
            content = (
                f"{self.verdict} — 但有几点建议\n{_LONG_SUFFIX}"
                if self.long_form
                else self.verdict
            )
        elif first_line.startswith("finish"):
            content = "finished"
        else:
            content = "draft"
        return LLMResponse(content=content, stop_reason="end_turn", usage=Usage(5, 5))


@pytest.fixture
def manager(tmp_path):
    return SubAgentManager(
        llm=VerdictLLM(),
        config=AsterwyndConfig(),
        parent_mode=AgentMode.BUILD,
        workspace_policy=WorkspacePolicy(workspace_root=tmp_path),
    )


def _ref_route_spec(when: str) -> dict:
    """``producer``（写 result 槽）→ ``collector``（collect 聚合，物化 verdict 槽）→
    ``gate``（route，数据上游是 collector）。``gate`` 的判定文本即 collector 的产出。"""
    return {
        "goal": "review gate",
        "nodes": [
            {"id": "producer", "kind": "subagent", "task": "produce a draft", "outputs": ["result", "verdict"]},
            {"id": "collector", "kind": "aggregate", "strategy": "collect", "outputs": ["verdict", "result"]},
            {
                "id": "gate",
                "kind": "route",
                "cases": [{"when": when, "to": "finish"}],
                "default": "producer",
            },
            {"id": "finish", "kind": "subagent", "task": "finish the work"},
        ],
        "edges": [
            {"from": "producer", "to": "collector"},
            {"from": "collector", "to": "gate"},
            {"from": "gate", "to": "finish"},
            {"from": "gate", "to": "producer"},
        ],
        "entry": ["producer"],
        "terminal": ["finish"],
    }


def _gate(result: dict) -> dict:
    return next(node for node in result["nodes"] if node["id"] == "gate")


# --- 校验期（Q3） -----------------------------------------------------------


def test_ref_node_must_exist():
    with pytest.raises(WorkflowValidationError, match="nonexistent"):
        parse_workflow_spec(_ref_route_spec("$ref:nonexistent:verdict"))


def test_ref_slot_must_be_declared():
    """``producer`` 声明 ``["result", "verdict"]``；引用未声明的 ``items`` 必须拒绝。"""
    with pytest.raises(WorkflowValidationError, match="items"):
        parse_workflow_spec(_ref_route_spec("$ref:producer:items"))


def test_ref_implicit_result_slot_is_declared():
    """``result`` 是隐式槽（``outputs`` 缺省值），引用它必须通过校验。"""
    spec = _ref_route_spec("$ref:producer:result")
    assert parse_workflow_spec(spec).has_node("gate")


def test_ref_does_not_require_data_reachability():
    """Q3：不把数据可达性作 schema 硬条件——ref 目标不必是 route 的数据上游。"""
    spec = _ref_route_spec("$ref:producer:verdict")
    # producer 与 gate 之间隔着 collector（不是直接数据上游），仍应通过校验
    parse_workflow_spec(spec)


def test_literal_label_still_validates_as_before():
    """C2 字面标签语义保留：纯文本 ``when`` 不做 ``$ref`` 解析。"""
    parse_workflow_spec(_ref_route_spec("APPROVED"))


# --- 运行期判定（Q1/Q2） ----------------------------------------------------


@pytest.mark.asyncio
async def test_ref_hits_case_when_slot_first_line_matches_upstream_text(manager):
    """Q2：槽值是多行长文时取**首个非空行**作标签——整段当标签会必然判不中。"""
    manager.llm = VerdictLLM("APPROVED", long_form=True)
    result = await WorkflowScheduler(manager).run(
        parse_workflow_spec(_ref_route_spec("$ref:collector:verdict"))
    )
    gate = _gate(result)
    assert gate["targets"] == ["finish"]
    # verdict 记命中的标签 = 槽值首个非空行（不是整段长文）
    assert gate["verdict"] == "APPROVED — 但有几点建议"


@pytest.mark.asyncio
async def test_ref_label_mismatch_uses_default(manager):
    """真实 miss：``$ref`` 槽首行与 route 判定文本的行首完全不同源。

    图：``producer → gate``（判定文本 = producer 的 "APPROVED looks good"）；
    ``other → holder``（collect 物化 verdict 槽 = "SOMETHING-ELSE entirely"）；
    ``holder → gate`` 也是数据边——两条边一起进判定文本，所以要用 default 分支验证。
    """
    spec = {
        "goal": "review gate",
        "nodes": [
            {"id": "producer", "kind": "subagent", "task": "produce a draft", "outputs": ["result"]},
            {"id": "other", "kind": "subagent", "task": "produce a draft other", "outputs": ["result"]},
            {"id": "holder", "kind": "aggregate", "strategy": "collect", "outputs": ["verdict"]},
            {
                "id": "gate",
                "kind": "route",
                # 标签来自 holder 的 verdict 槽（首行 SOMETHING-ELSE…），
                # 判定文本 = producer 的 APPROVED… + holder 的 SOMETHING-ELSE…
                # 行首匹配角度：SOMETHING-ELSE 确实是判定文本里某行的行首 → 命中。
                # 这里改为引用一个**首行不会出现**的标签来构造 miss。
                "cases": [{"when": "$ref:holder:verdict", "to": "finish"}],
                "default": "noop",
            },
            {"id": "finish", "kind": "subagent", "task": "finish the work"},
            {"id": "noop", "kind": "subagent", "task": "finish nothing"},
        ],
        "edges": [
            {"from": "producer", "to": "gate"},
            {"from": "other", "to": "holder"},
            {"from": "holder", "to": "gate"},
            {"from": "gate", "to": "finish"},
            {"from": "gate", "to": "noop"},
        ],
        "entry": ["producer", "other"],
        "terminal": ["finish", "noop"],
    }

    class MismatchLLM:
        async def chat(self, messages, tools=None, model="gpt-4"):
            first = messages[-1].content.splitlines()[0].lower()
            content = "OTHER-BRANCH-PAYLOAD" if "other" in first else "APPROVED looks good"
            return LLMResponse(content=content, stop_reason="end_turn", usage=Usage(5, 5))

    manager.llm = MismatchLLM()
    result = await WorkflowScheduler(manager).run(parse_workflow_spec(spec))
    # 判定文本含 "OTHER-BRANCH-PAYLOAD" 行 → 标签命中 finish。这条断言锁定 Q1
    # 读法 A 的语义：标签匹配的是**判定文本全文**（含所有数据上游产出），不是
    # 「ref 源节点自己的文本」。
    assert _gate(result)["targets"] == ["finish"]


@pytest.mark.asyncio
async def test_ref_label_absent_from_verdict_text_falls_back_to_default(manager):
    """标签在判定文本的任何行首都不出现 → miss → default。"""
    spec = {
        "goal": "review gate",
        "nodes": [
            {"id": "producer", "kind": "subagent", "task": "produce a draft", "outputs": ["result"]},
            {"id": "other", "kind": "subagent", "task": "produce a draft other", "outputs": ["result"]},
            {"id": "holder", "kind": "aggregate", "strategy": "collect", "outputs": ["verdict"]},
            {
                "id": "gate",
                "kind": "route",
                "cases": [{"when": "$ref:holder:verdict", "to": "finish"}],
                "default": "noop",
            },
            {"id": "finish", "kind": "subagent", "task": "finish the work"},
            {"id": "noop", "kind": "subagent", "task": "finish nothing"},
        ],
        "edges": [
            # holder 不是 gate 的数据上游 → 它的产出不进判定文本
            {"from": "producer", "to": "gate"},
            {"from": "other", "to": "holder"},
            {"from": "gate", "to": "finish"},
            {"from": "gate", "to": "noop"},
        ],
        "entry": ["producer", "other"],
        "terminal": ["finish", "noop"],
    }

    class SplitLLM:
        async def chat(self, messages, tools=None, model="gpt-4"):
            first = messages[-1].content.splitlines()[0].lower()
            content = "UNRELATED-PAYLOAD" if "other" in first else "APPROVED looks good"
            return LLMResponse(content=content, stop_reason="end_turn", usage=Usage(5, 5))

    manager.llm = SplitLLM()
    result = await WorkflowScheduler(manager).run(parse_workflow_spec(spec))
    gate = _gate(result)
    assert gate["targets"] == ["noop"]
    assert gate.get("error") is None


@pytest.mark.asyncio
async def test_ref_missing_slot_silently_uses_default(manager):
    """Q3：运行时槽缺失 → 不报错、走 default，diagnostics 记录未命中原因。

    ``producer`` 是 subagent：它自己从不物化 ``state.slots``，所以
    ``$ref:producer:verdict`` 在运行期是「槽缺失」。
    """
    spec = {
        "goal": "review gate",
        "nodes": [
            {"id": "producer", "kind": "subagent", "task": "produce a draft", "outputs": ["result", "verdict"]},
            {
                "id": "gate",
                "kind": "route",
                "cases": [{"when": "$ref:producer:verdict", "to": "finish"}],
                "default": "noop",
            },
            {"id": "finish", "kind": "subagent", "task": "finish the work"},
            {"id": "noop", "kind": "subagent", "task": "finish nothing"},
        ],
        "edges": [
            {"from": "producer", "to": "gate"},
            {"from": "gate", "to": "finish"},
            {"from": "gate", "to": "noop"},
        ],
        "entry": ["producer"],
        "terminal": ["finish", "noop"],
    }
    manager.llm = VerdictLLM("APPROVED")
    result = await WorkflowScheduler(manager).run(parse_workflow_spec(spec))
    gate = _gate(result)
    assert gate["targets"] == ["noop"]  # 未命中走 default
    assert gate.get("error") is None  # 静默，不报错
    assert result["diagnostics"].get("route_ref_misses"), (
        "diagnostics 必须记录 $ref 未命中原因"
    )
    miss = result["diagnostics"]["route_ref_misses"]
    assert any("producer" in str(entry) and "verdict" in str(entry) for entry in miss)


@pytest.mark.asyncio
async def test_literal_case_still_matches_upstream_text(manager):
    """C2 语义保留回归：字面标签 case 仍按行首匹配上游产出。"""
    manager.llm = VerdictLLM("APPROVED", long_form=False)
    result = await WorkflowScheduler(manager).run(
        parse_workflow_spec(_ref_route_spec("APPROVED"))
    )
    assert _gate(result)["targets"] == ["finish"]
