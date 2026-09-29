"""pattern → DSL 模板编译 + 统一入口的模板执行（tasks 5.1/5.2；D7/Q9）。

覆盖：

- 4 个 pattern 编译成合法 WorkflowSpec 模板（compile_pattern），
- bidding 的 selector 是**真实子 agent 节点**（grill 决策 5），
- 聚合语义是「每节点取最新一次 run」（grill 决策 4）——peer-review 跨轮复用
  同一会话，
- 统一入口 ``RunWorkflow(template=…)`` 的执行语义（变化 ``workflow-builtin-templates``：
  ``run_pattern`` 退役，语义改经有界 envelope 断言）。

5.2 段（原 ``run_pattern`` 兼容 adapter）已迁移：形状断言在
``test_run_workflow_template.py``，此处只保留**执行语义**（worker 预算到达 runs、
peer-review 跨轮会话复用、层级/失败不 fail-fast）。
"""
import asyncio
import json

import pytest

from agent.config import AsterwyndConfig
from agent.llm import LLMResponse, Usage
from agent.run_config import AgentMode
from agent.subagent.manager import SubAgentManager
from agent.subagent.patterns import PATTERNS, compile_pattern, compile_recipe
from agent.subagent.workflow import WorkflowSpec, WorkflowValidationError, parse_workflow_spec
from agent.tools.builtin.subagents import RunWorkflowTool
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


def test_compile_pattern_threads_worker_budget_params_into_nodes():
    """building-review Issue 6：文档化的 worker 预算参数不能被静默丢弃。"""
    for pattern, params in (
        ("orchestrator-worker", {"workers": 2}),
        ("hierarchical", {"teams": 2}),
        ("bidding", {"proposers": 2}),
        ("peer-review", {"max_rounds": 2}),
    ):
        spec = compile_pattern(
            pattern,
            task="t",
            params={**params, "worker_max_tokens": 123, "worker_max_time_s": 7.5},
        )
        budgeted = [
            node
            for node in spec.nodes
            if node.kind in ("subagent", "foreach")
            and node.kind != "route"
            and node.id != "selector"
        ]
        assert budgeted, pattern
        for node in budgeted:
            assert node.max_tokens == 123, (pattern, node.id)
            assert node.max_time_s == 7.5, (pattern, node.id)


@pytest.mark.asyncio
async def test_template_worker_budget_params_reach_the_runs(manager):
    out = json.loads(
        await RunWorkflowTool(manager).execute(
            template="orchestrator-worker",
            task="research",
            params={"workers": 2, "worker_max_tokens": 321, "worker_max_time_s": 9.0},
        )
    )
    assert out["status"] == "completed"
    runs = [session.runs[-1] for session in manager._sessions.values() if session.runs]
    assert runs, "workers must have produced runs"
    for run in runs:
        assert run.max_tokens == 321
        assert run.max_time_s == 9.0


# --- 5.2 统一入口的执行语义（形状断言见 test_run_workflow_template.py） -----


@pytest.mark.asyncio
async def test_template_peer_review_reuses_sessions_across_rounds(manager):
    """grill 决策 4：peer-review 跨轮复用同一会话（producer/reviewer 各一 session）。"""
    manager.llm = FirstLineScriptedLLM(
        {
            "review": ["CRITIQUE missing rationale", "APPROVED now complete"],
            "draft": ["draft v1", "draft v2"],
            "finalize": ["final"],
        }
    )
    out = json.loads(
        await RunWorkflowTool(manager).execute(template="peer-review", task="write proposal")
    )
    assert out["status"] == "completed"
    # producer 与 reviewer 的会话都在（跨轮复用；会话按 subagent_id 键，name 是节点名）
    names = {session.name for session in manager._sessions.values()}
    assert "producer" in names
    assert "reviewer" in names


@pytest.mark.asyncio
async def test_template_peer_review_max_rounds_falls_back_to_real_runs(manager):
    manager.llm = FirstLineScriptedLLM(
        {"review": ["CRITIQUE needs work"], "draft": ["draft v1"]}
    )
    out = json.loads(
        await RunWorkflowTool(manager).execute(
            template="peer-review", task="write proposal", params={"max_rounds": 2}
        )
    )
    # 撞 max_rounds 后图仍收敛，产出的是真实 run（不是合成的摘要条目）
    assert out["status"] in ("completed", "completed_with_failures", "graph_recursion_exceeded")
    assert any(session.name == "producer" for session in manager._sessions.values())


@pytest.mark.asyncio
async def test_template_worker_failure_is_not_fail_fast(manager):
    class FailingWorkerLLM:
        def __init__(self):
            self.calls = 0

        async def chat(self, messages, tools=None, model="gpt-4"):
            self.calls += 1
            if self.calls == 2:
                raise RuntimeError("boom")
            return LLMResponse(content="ok", stop_reason="end_turn", usage=Usage(5, 5))

    manager.llm = FailingWorkerLLM()
    out = json.loads(
        await RunWorkflowTool(manager).execute(
            template="orchestrator-worker", task="research", params={"workers": 2}
        )
    )
    assert out["completed"] + out["failed"] == 2
    assert out["failed"] >= 1


@pytest.mark.asyncio
async def test_template_sets_and_resets_bus_context(manager):
    from agent.subagent.context import current_bus

    assert current_bus() is None
    await RunWorkflowTool(manager).execute(
        template="orchestrator-worker", task="t", params={"workers": 1}
    )
    assert current_bus() is None


@pytest.mark.asyncio
async def test_template_hierarchical_runs_managers(manager):
    out = json.loads(
        await RunWorkflowTool(manager).execute(
            template="hierarchical", task="build", params={"teams": 2}
        )
    )
    assert out["status"] == "completed"
    assert out["completed"] == 2


@pytest.mark.asyncio
async def test_compile_recipe_unknown_name_raises_validation_error(manager):
    """D4：共享配方编译把未知模板名统一成 WorkflowValidationError（不再是 KeyError）。"""
    with pytest.raises(WorkflowValidationError, match="unknown template"):
        compile_recipe("nope", task="t")
    assert compile_recipe("orchestrator-worker", task="t") is not None


@pytest.mark.asyncio
async def test_template_run_is_driven_by_the_scheduler(manager):
    """统一入口的 template 路径编译成 WorkflowSpec 并走统一调度器。"""
    out = json.loads(
        await RunWorkflowTool(manager).execute(
            template="orchestrator-worker", task="research", params={"workers": 2}
        )
    )
    scheduler = manager.get_workflow(out["workflow_id"])
    assert scheduler is not None
    assert scheduler.spec is not None
