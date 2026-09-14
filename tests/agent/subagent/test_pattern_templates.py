"""pattern → DSL 模板 + run_pattern 兼容 adapter（tasks 5.1/5.2；D7/Q9）。

覆盖：

- 4 个 pattern 编译成合法 WorkflowSpec 模板（compile_pattern），
- bidding 的 selector 是**真实子 agent 节点**（grill 决策 5），
- 聚合语义是「每节点取最新一次 run」（grill 决策 4）——peer-review 跨轮复用
  同一会话，``completed`` 只数终态的真实节点，
- run_pattern 返回字段兼容 + 新增 workflow_id / workflow_spec_hash /
  critical_path_s / peak_active / total_cost。
"""
import asyncio

import pytest

from agent.config import AsterwyndConfig
from agent.llm import LLMResponse, Usage
from agent.run_config import AgentMode
from agent.subagent.manager import SubAgentManager
from agent.subagent.patterns import PATTERNS, compile_pattern, run_pattern
from agent.subagent.workflow import WorkflowSpec, parse_workflow_spec
from agent.workspace_policy import WorkspacePolicy


class StaticLLM:
    async def chat(self, messages, tools=None, model="gpt-4"):
        return LLMResponse(content="worker result", stop_reason="end_turn", usage=Usage(5, 5))


class ScriptedLLM:
    def __init__(self, responses: list[str]):
        self.responses = responses
        self.calls = 0

    async def chat(self, messages, tools=None, model="gpt-4"):
        idx = min(self.calls, len(self.responses) - 1)
        self.calls += 1
        return LLMResponse(
            content=self.responses[idx], stop_reason="end_turn", usage=Usage(5, 5)
        )


class FirstLineScriptedLLM:
    """按任务首行角色返回脚本内容（跨轮重跑时不会错位）。"""

    def __init__(self, by_role: dict[str, list[str]]):
        self.by_role = {role: list(values) for role, values in by_role.items()}
        self.calls = 0

    async def chat(self, messages, tools=None, model="gpt-4"):
        self.calls += 1
        first = messages[-1].content.splitlines()[0].strip().lower()
        for role, values in self.by_role.items():
            if first.startswith(role):
                return LLMResponse(
                    content=values.pop(0) if len(values) > 1 else values[0],
                    stop_reason="end_turn",
                    usage=Usage(5, 5),
                )
        return LLMResponse(content="ok", stop_reason="end_turn", usage=Usage(5, 5))


@pytest.fixture
def manager(tmp_path) -> SubAgentManager:
    return SubAgentManager(
        llm=StaticLLM(),
        config=AsterwyndConfig(),
        parent_mode=AgentMode.BUILD,
        workspace_policy=WorkspacePolicy(workspace_root=tmp_path),
        max_active=5,
    )


# --- 5.1 compile_pattern ----------------------------------------------------


def test_compile_orchestrator_worker():
    spec = compile_pattern("orchestrator-worker", task="research", params={"workers": 3})
    assert isinstance(spec, WorkflowSpec)
    foreach = spec.node("workers")
    assert foreach.kind == "foreach"
    assert len(foreach.items) == 3
    assert spec.node("aggregate").kind == "aggregate"
    assert spec.node("aggregate").join == "all_required"


def test_compile_bidding_uses_a_real_selector_subagent_node():
    """grill 决策 5：selector 必须是真实子 agent 节点，不是 aggregate 内联 LLM。"""
    spec = compile_pattern("bidding", task="solve", params={"proposers": 3})
    selector = spec.node("selector")
    assert selector.kind == "subagent"
    assert len(spec.node("proposers").items) == 3
    # selector 从 proposers 取输入，再汇入 aggregate
    assert spec.edge_between("proposers", "selector") is not None
    assert spec.edge_between("selector", "aggregate") is not None


def test_compile_peer_review_has_a_bounded_route_loop():
    spec = compile_pattern("peer-review", task="write", params={"max_rounds": 2})
    gate = spec.node("gate")
    assert gate.kind == "route"
    assert gate.max_routes == 2
    # 未 APPROVED 时回到 producer（复用同一会话）
    assert gate.default == "producer"
    assert gate.cases[0].when == "APPROVED"


def test_compile_hierarchical_uses_managers_that_may_spawn():
    spec = compile_pattern("hierarchical", task="build", params={"teams": 2})
    assert spec.node("managers").kind == "foreach"
    assert len(spec.node("managers").items) == 2


def test_every_pattern_compiles_to_a_valid_spec():
    for name in PATTERNS:
        spec = compile_pattern(name, task="t", params=None)
        # 编译结果必须能过一遍 schema 校验（round-trip）
        assert parse_workflow_spec(spec.to_dict()).spec_hash == spec.spec_hash


def test_compile_pattern_rejects_unknown_name():
    with pytest.raises(KeyError, match="unknown pattern"):
        compile_pattern("nope", task="t")


# --- 5.2 run_pattern 兼容 adapter ------------------------------------------


@pytest.mark.asyncio
async def test_run_pattern_keeps_legacy_fields_and_adds_new_ones(manager):
    result = await run_pattern(
        manager, pattern="orchestrator-worker", task="research", params={"workers": 3}
    )
    # 兼容字段
    assert result["pattern"] == "orchestrator-worker"
    assert result["task"] == "research"
    assert result["completed"] == 3
    assert result["failed"] == 0
    assert len(result["workers"]) == 3
    assert result["summary"]
    assert "bus" in result
    # 新增字段（Q9）
    assert result["workflow_id"].startswith("wf_")
    assert result["workflow_spec_hash"]
    assert result["critical_path_s"] >= 0
    assert result["peak_active"] >= 1
    assert result["total_cost"] == 0
    # spec_hash 是 WorkflowSpec 的哈希，不与 OpenSpec artifact hash 混用（低危项）
    assert "spec_hash" not in result


@pytest.mark.asyncio
async def test_bidding_keeps_selector_shape(manager):
    manager.llm = ScriptedLLM(
        ["proposal A", "proposal B", "proposal C", "SELECTED 2: proposal B is most complete"]
    )
    result = await run_pattern(
        manager, pattern="bidding", task="solve X", params={"proposers": 3}
    )
    assert result["pattern"] == "bidding"
    assert result["completed"] == 3  # 只数 proposers（grill 决策 5）
    assert "SELECTED 2" in result["selected"]
    assert result["selector"]["status"] == "completed"
    assert result["selector"]["subagent_id"]


@pytest.mark.asyncio
async def test_peer_review_reuses_sessions_across_rounds(manager):
    """grill 决策 4：每节点取最新一次 run —— completed 只数终态节点。"""
    manager.llm = FirstLineScriptedLLM(
        {
            "review": ["CRITIQUE missing rationale", "APPROVED now complete"],
            "draft": ["draft v1", "draft v2"],
            "finalize": ["final"],
        }
    )
    result = await run_pattern(manager, pattern="peer-review", task="write proposal")
    assert result["pattern"] == "peer-review"
    assert result["completed"] == 2  # producer + reviewer，各自终态一次
    assert result["failed"] == 0
    for worker in result["workers"]:
        assert worker["status"] == "completed"
        assert worker["subagent_id"] in manager._sessions


@pytest.mark.asyncio
async def test_peer_review_max_rounds_falls_back_to_real_runs(manager):
    manager.llm = FirstLineScriptedLLM(
        {"review": ["CRITIQUE needs work"], "draft": ["draft v1"]}
    )
    result = await run_pattern(
        manager, pattern="peer-review", task="write proposal", params={"max_rounds": 2}
    )
    assert result["completed"] == 2
    for worker in result["workers"]:
        assert worker["status"] == "completed"
        assert "reached max review rounds" not in worker.get("summary", "")
        assert worker["subagent_id"] in manager._sessions


@pytest.mark.asyncio
async def test_worker_failure_is_not_fail_fast(manager):
    class FailingWorkerLLM:
        def __init__(self):
            self.calls = 0

        async def chat(self, messages, tools=None, model="gpt-4"):
            self.calls += 1
            if self.calls == 2:
                raise RuntimeError("boom")
            return LLMResponse(content="ok", stop_reason="end_turn", usage=Usage(5, 5))

    manager.llm = FailingWorkerLLM()
    result = await run_pattern(
        manager, pattern="orchestrator-worker", task="research", params={"workers": 2}
    )
    assert result["completed"] + result["failed"] == 2
    assert result["failed"] >= 1


@pytest.mark.asyncio
async def test_run_pattern_sets_and_resets_bus_context(manager):
    from agent.subagent.context import current_bus

    assert current_bus() is None
    result = await run_pattern(
        manager, pattern="orchestrator-worker", task="t", params={"workers": 1}
    )
    assert current_bus() is None
    assert "messages" in result["bus"]


@pytest.mark.asyncio
async def test_hierarchical_pattern_runs_managers(manager):
    result = await run_pattern(
        manager, pattern="hierarchical", task="build", params={"teams": 2}
    )
    assert result["completed"] == 2
    assert len(result["workers"]) == 2


@pytest.mark.asyncio
async def test_run_pattern_unknown_pattern_still_raises(manager):
    with pytest.raises(KeyError, match="unknown pattern"):
        await run_pattern(manager, pattern="nope", task="t")


@pytest.mark.asyncio
async def test_run_pattern_is_driven_by_the_scheduler(manager):
    """run_pattern 内部编译成 WorkflowSpec 并走统一调度器（D7）。"""
    result = await run_pattern(
        manager, pattern="orchestrator-worker", task="research", params={"workers": 2}
    )
    scheduler = manager.get_workflow(result["workflow_id"])
    assert scheduler is not None
    assert scheduler.spec is not None
