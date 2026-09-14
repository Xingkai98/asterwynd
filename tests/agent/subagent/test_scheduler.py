"""DAG 调度器（change ``workflow-dsl-scheduler``，D3/D4/D6 + grill Q2/Q3/Q5/Q6/Q8）。

覆盖 tasks 2.1-2.4 与 3.1-3.4：

- ready 集合 + 依赖门控（required 上游全终态才派发），
- 准入背压（在途 < max_active + max_queued_runs，永不撞 ``queue_full``），
- 汇合语义 all_required / best_effort（超时臂 CancelSubagentRun + cancelled），
- 图级 recursion_limit（superstep 计数）→ GraphRecursionError，
- 节点执行：subagent / aggregate / route / foreach，
- workflow_id/node_id 在**调度器派发上下文**里 set，执行期可见（grill 决策 1/2）。
"""
import asyncio
import json

import pytest

from agent.config import AsterwyndConfig
from agent.llm import LLMResponse, Usage
from agent.run_config import AgentMode
from agent.subagent.manager import SubAgentManager
from agent.subagent.scheduler import (
    GraphRecursionError,
    WorkflowScheduler,
    aggregate_slots,
    extract_collection,
    matches_route,
    render_item_task,
)
from agent.subagent.workflow import WorkflowValidationError, parse_workflow_spec
from agent.workspace_policy import WorkspacePolicy


class StaticLLM:
    def __init__(self, content="worker result"):
        self.content = content
        self.calls = 0

    async def chat(self, messages, tools=None, model="gpt-4"):
        self.calls += 1
        return LLMResponse(content=self.content, stop_reason="end_turn", usage=Usage(5, 5))


class ScriptedLLM:
    def __init__(self, responses: list[str]):
        self.responses = responses
        self.calls = 0

    async def chat(self, messages, tools=None, model="gpt-4"):
        idx = min(self.calls, len(self.responses) - 1)
        self.calls += 1
        return LLMResponse(content=self.responses[idx], stop_reason="end_turn", usage=Usage(5, 5))


class ConcurrencyProbeLLM:
    """记录并发峰值，并让每个 run 短暂停留以制造真实重叠。"""

    def __init__(self, content="ok", hold=0.02):
        self.content = content
        self.hold = hold
        self.active = 0
        self.peak = 0

    async def chat(self, messages, tools=None, model="gpt-4"):
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            await asyncio.sleep(self.hold)
            return LLMResponse(content=self.content, stop_reason="end_turn", usage=Usage(5, 5))
        finally:
            self.active -= 1


class FailingLLM:
    """第 ``fail_on`` 次调用抛错，其余正常返回。"""

    def __init__(self, fail_on: int, content="ok"):
        self.fail_on = fail_on
        self.content = content
        self.calls = 0

    async def chat(self, messages, tools=None, model="gpt-4"):
        self.calls += 1
        if self.calls == self.fail_on:
            raise RuntimeError("boom")
        return LLMResponse(content=self.content, stop_reason="end_turn", usage=Usage(5, 5))


class ReviewLoopLLM:
    """peer-review 形状：reviewer 第一轮给 CRITIQUE、第二轮给 APPROVED。

    route 节点的判定来自「上游 reviewer 的产出」，所以脚本必须按任务文本而不是
    调用序号分派，否则重跑轮次的判定会错位。
    """

    def __init__(self):
        self.reviews = 0

    async def chat(self, messages, tools=None, model="gpt-4"):
        # 只按「任务首行」判角色：任务文本里还会带 goal 与上游产出，用子串匹配
        # 会把 producer/done 的任务误判成 review。
        first_line = messages[-1].content.splitlines()[0].strip().lower()
        if first_line.startswith("review"):
            self.reviews += 1
            verdict = "APPROVED looks good" if self.reviews >= 2 else "CRITIQUE needs work"
            return LLMResponse(content=verdict, stop_reason="end_turn", usage=Usage(5, 5))
        return LLMResponse(
            content=f"draft v{self.reviews + 1}", stop_reason="end_turn", usage=Usage(5, 5)
        )


class GatedLLM:
    """所有 run 都阻塞在 gate 上，直到 ``release()``；用于确定性地观察取消。"""

    def __init__(self):
        self.gate = asyncio.Event()
        self.started = asyncio.Event()

    def release(self) -> None:
        self.gate.set()

    async def chat(self, messages, tools=None, model="gpt-4"):
        self.started.set()
        await self.gate.wait()
        return LLMResponse(content="released", stop_reason="end_turn", usage=Usage(5, 5))


class MixedArmLLM:
    """一条臂立即失败、另一条臂长时间阻塞（用于 best_effort 的提前聚合）。"""

    def __init__(self, delay: float = 0.3):
        self.delay = delay

    async def chat(self, messages, tools=None, model="gpt-4"):
        if "dead" in messages[-1].content:
            raise RuntimeError("boom")
        await asyncio.sleep(self.delay)
        return LLMResponse(content="late arm", stop_reason="end_turn", usage=Usage(5, 5))


class SlowThenFastLLM:
    """前 ``slow_calls`` 次调用阻塞在 gate 上，之后立即返回。"""

    def __init__(self, slow_calls: int, slow_content="slow arm", fast_content="fast arm"):
        self.slow_calls = slow_calls
        self.slow_content = slow_content
        self.fast_content = fast_content
        self.calls = 0
        self.gate = asyncio.Event()

    async def chat(self, messages, tools=None, model="gpt-4"):
        self.calls += 1
        if self.calls <= self.slow_calls:
            await self.gate.wait()
            return LLMResponse(
                content=self.slow_content, stop_reason="end_turn", usage=Usage(5, 5)
            )
        return LLMResponse(
            content=self.fast_content, stop_reason="end_turn", usage=Usage(5, 5)
        )


@pytest.fixture
def manager_for_scheduler(tmp_path) -> SubAgentManager:
    return _manager(tmp_path, StaticLLM())


def _manager(tmp_path, llm, **kwargs) -> SubAgentManager:
    return SubAgentManager(
        llm=llm,
        config=AsterwyndConfig(),
        parent_mode=AgentMode.BUILD,
        workspace_policy=WorkspacePolicy(workspace_root=tmp_path),
        **kwargs,
    )


def _fanout_spec(**overrides) -> dict:
    base = {
        "goal": "research",
        "nodes": [
            {"id": "a", "kind": "subagent", "task": "task a"},
            {"id": "b", "kind": "subagent", "task": "task b"},
            {"id": "c", "kind": "subagent", "task": "task c"},
            {
                "id": "join",
                "kind": "aggregate",
                "join": "all_required",
                "strategy": "collect",
            },
        ],
        "edges": [
            {"from": "a", "to": "join", "reducer": "concat"},
            {"from": "b", "to": "join", "reducer": "concat"},
            {"from": "c", "to": "join", "reducer": "concat"},
        ],
    }
    base.update(overrides)
    return base


async def _run(scheduler: WorkflowScheduler, spec: dict, **kwargs) -> dict:
    return await scheduler.run(parse_workflow_spec(spec), **kwargs)


# --- 2.1 fan-out + 依赖门控 -------------------------------------------------


@pytest.mark.asyncio
async def test_fan_out_then_join(manager_for_scheduler):
    result = await _run(
        WorkflowScheduler(manager_for_scheduler), _fanout_spec()
    )
    assert result["status"] == "completed"
    assert {node["id"] for node in result["nodes"]} == {"a", "b", "c", "join"}
    assert all(node["status"] == "completed" for node in result["nodes"])
    assert result["completed"] == 3  # a/b/c 三个 subagent run；collect aggregate 不产生 run
    assert result["failed"] == 0
    assert result["current_nodes"] == []
    assert result["diagnostics"] == {}


@pytest.mark.asyncio
async def test_downstream_runs_only_after_required_upstreams(manager_for_scheduler):
    """join 必须等 a/b/c 全终态：门控把上游产出喂给下游（collect 聚合三者）。"""
    manager_for_scheduler.llm = StaticLLM("finding")
    result = await _run(
        WorkflowScheduler(manager_for_scheduler), _fanout_spec()
    )
    assert result["status"] == "completed"
    join_node = next(node for node in result["nodes"] if node["id"] == "join")
    assert join_node["summary"].count("finding") == 3


@pytest.mark.asyncio
async def test_fan_out_is_actually_parallel(manager_for_scheduler):
    probe = ConcurrencyProbeLLM(hold=0.05)
    manager_for_scheduler.llm = probe
    manager_for_scheduler.max_active = 5
    manager_for_scheduler._permits._limit = 5  # type: ignore[attr-defined]
    result = await _run(
        WorkflowScheduler(manager_for_scheduler), _fanout_spec()
    )
    assert result["status"] == "completed"
    assert probe.peak >= 3, "三个 subagent 节点应当并发执行"
    assert result["peak_active"] >= 3


# --- 2.2 准入背压 -----------------------------------------------------------


@pytest.mark.asyncio
async def test_admission_backpressure_never_hits_queue_full(manager_for_scheduler):
    """Q2：调度器只在在途 < max_active + max_queued_runs 时派发。"""
    manager = manager_for_scheduler
    manager.max_active = 1
    manager.max_queued_runs = 1
    manager._permits._limit = 1  # type: ignore[attr-defined]
    nodes = [{"id": f"n{i}", "kind": "subagent", "task": f"t{i}"} for i in range(6)]
    nodes.append(
        {"id": "join", "kind": "aggregate", "join": "all_required", "strategy": "collect"}
    )
    edges = [{"from": f"n{i}", "to": "join", "reducer": "concat"} for i in range(6)]
    result = await _run(WorkflowScheduler(manager), {"goal": "g", "nodes": nodes, "edges": edges})
    assert result["status"] == "completed"
    assert result["failed"] == 0
    statuses = {node["status"] for node in result["nodes"]}
    assert "queue_full" not in statuses
    assert result["diagnostics"] == {}


@pytest.mark.asyncio
async def test_backpressure_dispatches_at_most_the_queue_budget(manager_for_scheduler):
    """在途上限 = max_active + max_queued_runs；超出部分留在 ready 集合。"""
    manager = manager_for_scheduler
    manager.max_active = 1
    manager.max_queued_runs = 2
    manager._permits._limit = 1  # type: ignore[attr-defined]
    in_flight_peak = 0

    class IdleLLM:
        async def chat(self, messages, tools=None, model="gpt-4"):
            nonlocal in_flight_peak
            await asyncio.sleep(0.05)
            in_flight_peak = max(
                in_flight_peak,
                len(manager._sessions) - sum(
                    1 for s in manager._sessions.values() if s.status == "idle"
                ),
            )
            return LLMResponse(content="ok", stop_reason="end_turn", usage=Usage(1, 1))

    manager.llm = IdleLLM()
    nodes = [{"id": f"n{i}", "kind": "subagent", "task": f"t{i}"} for i in range(5)]
    nodes.append(
        {"id": "join", "kind": "aggregate", "join": "all_required", "strategy": "collect"}
    )
    edges = [{"from": f"n{i}", "to": "join", "reducer": "concat"} for i in range(5)]
    result = await _run(WorkflowScheduler(manager), {"goal": "g", "nodes": nodes, "edges": edges})
    assert result["status"] == "completed"
    assert result["peak_active"] <= 1  # 物理并发仍受 max_active 约束


# --- 2.3 汇合语义 -----------------------------------------------------------


@pytest.mark.asyncio
async def test_all_required_waits_and_records_failure(manager_for_scheduler):
    """失败不 fail-fast：一条臂失败仍等其余完成，失败记录保留。"""
    manager_for_scheduler.llm = FailingLLM(fail_on=2)
    result = await _run(
        WorkflowScheduler(manager_for_scheduler), _fanout_spec()
    )
    assert result["status"] == "completed"
    statuses = {node["id"]: node["status"] for node in result["nodes"]}
    assert statuses["join"] == "completed"  # 仍汇合
    assert "failed" in {statuses["a"], statuses["b"], statuses["c"]}
    assert result["failed"] >= 1
    assert result["completed"] >= 2


@pytest.mark.asyncio
async def test_best_effort_times_out_and_cancels_slow_arm(tmp_path):
    """Q3：超时臂 CancelSubagentRun + status=cancelled，aggregate 仍消费已完成结果。"""
    llm = SlowThenFastLLM(slow_calls=2)
    manager = _manager(tmp_path, llm, max_active=5)
    spec = {
        "goal": "best effort",
        "nodes": [
            {"id": "slow1", "kind": "subagent", "task": "slow one"},
            {"id": "slow2", "kind": "subagent", "task": "slow two"},
            {"id": "quick", "kind": "subagent", "task": "quick"},
            {
                "id": "join",
                "kind": "aggregate",
                "join": "best_effort",
                "deadline_s": 0.2,
                "strategy": "collect",
            },
        ],
        "edges": [
            {"from": "slow1", "to": "join", "reducer": "concat"},
            {"from": "slow2", "to": "join", "reducer": "concat"},
            {"from": "quick", "to": "join", "reducer": "concat"},
        ],
    }
    result = await _run(WorkflowScheduler(manager), spec)
    assert result["status"] == "completed"
    statuses = {node["id"]: node["status"] for node in result["nodes"]}
    assert statuses["quick"] == "completed"
    assert statuses["join"] == "completed"
    assert {statuses["slow1"], statuses["slow2"]} == {"cancelled"}
    join_node = next(node for node in result["nodes"] if node["id"] == "join")
    assert "fast arm" in join_node["summary"]
    assert "slow arm" not in join_node["summary"]
    # 超时臂的 run 被真正取消（不留 running 的后台 run）
    for node_id in ("slow1", "slow2"):
        subagent_id = next(
            node["subagent_id"]
            for node in result["nodes"]
            if node["id"] == node_id
        )
        session = manager._sessions[subagent_id]
        assert session.active_run_id is None
        assert session.runs[-1].status == "cancelled"


@pytest.mark.asyncio
async def test_best_effort_degrades_to_partial_results_without_raising(manager_for_scheduler):
    """Q3/Q8：即使只剩失败臂，best_effort 也按已有记录聚合，不抛异常。"""
    manager = manager_for_scheduler
    manager.llm = MixedArmLLM(delay=0.5)
    spec = {
        "goal": "g",
        "nodes": [
            {"id": "dead", "kind": "subagent", "task": "dead arm"},
            {"id": "live", "kind": "subagent", "task": "live arm"},
            {
                "id": "join",
                "kind": "aggregate",
                "join": "best_effort",
                "deadline_s": 0.05,
                "strategy": "collect",
            },
        ],
        "edges": [
            {"from": "dead", "to": "join", "reducer": "concat"},
            {"from": "live", "to": "join", "reducer": "concat"},
        ],
    }
    result = await _run(WorkflowScheduler(manager), spec)
    assert result["status"] == "completed"
    statuses = {node["id"]: node["status"] for node in result["nodes"]}
    assert statuses["dead"] == "failed"  # 失败臂保留记录
    assert statuses["live"] == "cancelled"  # 超时臂被取消
    assert statuses["join"] == "completed"  # 仍按已有记录聚合


# --- 2.4 图级 recursion_limit ----------------------------------------------


@pytest.mark.asyncio
async def test_recursion_limit_reports_graph_recursion_exceeded(manager_for_scheduler):
    """Q8：超限走 envelope status=graph_recursion_exceeded + 诊断，不是异常文本。"""
    spec = {
        "goal": "loop forever",
        "nodes": [
            {"id": "producer", "kind": "subagent", "task": "draft"},
            {
                "id": "gate",
                "kind": "route",
                "task": "route on verdict",
                "cases": [{"when": "APPROVED", "to": "done"}],
                "default": "producer",
                "max_routes": 50,
            },
            {"id": "done", "kind": "subagent", "task": "finish"},
        ],
        "entry": ["producer"],
        "edges": [
            {"from": "producer", "to": "gate"},
            {"from": "gate", "to": "done"},
            {"from": "gate", "to": "producer"},
        ],
        "recursion_limit": 3,
    }
    manager_for_scheduler.llm = StaticLLM("CRITIQUE please revise")
    result = await _run(WorkflowScheduler(manager_for_scheduler), spec)
    assert result["status"] == "graph_recursion_exceeded"
    diag = result["diagnostics"]
    assert diag["recursion_limit"] == 3
    assert diag["steps"] >= 3
    assert diag["current_nodes"]


@pytest.mark.asyncio
async def test_recursion_exceeded_raises_only_when_asked(manager_for_scheduler):
    spec = {
        "goal": "loop",
        "nodes": [
            {"id": "producer", "kind": "subagent", "task": "draft"},
            {
                "id": "gate",
                "kind": "route",
                "task": "route",
                "cases": [{"when": "APPROVED", "to": "done"}],
                "default": "producer",
                "max_routes": 50,
            },
            {"id": "done", "kind": "subagent", "task": "finish"},
        ],
        "entry": ["producer"],
        "edges": [
            {"from": "producer", "to": "gate"},
            {"from": "gate", "to": "done"},
            {"from": "gate", "to": "producer"},
        ],
        "recursion_limit": 2,
    }
    manager_for_scheduler.llm = StaticLLM("CRITIQUE")
    scheduler = WorkflowScheduler(manager_for_scheduler)
    with pytest.raises(GraphRecursionError):
        await scheduler.run(parse_workflow_spec(spec), raise_on_recursion=True)


@pytest.mark.asyncio
async def test_recursion_error_carries_diagnostics(manager_for_scheduler):
    exc = GraphRecursionError(steps=25, limit=25, current_nodes=["a"], message="boom")
    payload = exc.to_dict()
    assert payload["steps"] == 25
    assert payload["limit"] == 25
    assert payload["current_nodes"] == ["a"]


@pytest.mark.asyncio
async def test_max_routes_caps_a_single_route_node(manager_for_scheduler):
    """max_routes 是 route 节点自身的预算，先于图级 recursion_limit 触发。"""
    spec = {
        "goal": "route cap",
        "nodes": [
            {"id": "producer", "kind": "subagent", "task": "draft"},
            {
                "id": "gate",
                "kind": "route",
                "task": "route",
                "cases": [{"when": "APPROVED", "to": "done"}],
                "default": "producer",
                "max_routes": 1,
            },
            {"id": "done", "kind": "subagent", "task": "finish"},
        ],
        "entry": ["producer"],
        "edges": [
            {"from": "producer", "to": "gate"},
            {"from": "gate", "to": "done"},
            {"from": "gate", "to": "producer"},
        ],
        "recursion_limit": 25,
    }
    manager_for_scheduler.llm = StaticLLM("CRITIQUE")
    result = await _run(WorkflowScheduler(manager_for_scheduler), spec)
    assert result["status"] == "graph_recursion_exceeded"
    assert result["diagnostics"]["reason"] == "max_routes"


@pytest.mark.asyncio
async def test_max_runs_caps_total_runs(manager_for_scheduler):
    manager = manager_for_scheduler
    spec = {
        "goal": "too many runs",
        "nodes": [{"id": f"n{i}", "kind": "subagent", "task": f"t{i}"} for i in range(4)],
        "edges": [],
        "max_runs": 2,
    }
    result = await _run(WorkflowScheduler(manager), spec)
    assert result["status"] == "graph_recursion_exceeded"
    assert result["diagnostics"]["reason"] == "max_runs"


# --- 3.1/3.2 subagent + aggregate 节点 -------------------------------------


@pytest.mark.asyncio
async def test_subagent_node_records_session_identity(manager_for_scheduler):
    manager = manager_for_scheduler
    result = await _run(WorkflowScheduler(manager), _fanout_spec())
    node = next(node for node in result["nodes"] if node["id"] == "a")
    session = manager._sessions[node["subagent_id"]]
    assert session.workflow_id == result["workflow_id"]
    assert session.node_id == "a"
    assert session.runs[-1].workflow_id == result["workflow_id"]


@pytest.mark.asyncio
async def test_workflow_and_node_identity_visible_inside_the_run(manager_for_scheduler):
    """grill 决策 1/2：身份在调度器派发上下文 set，子 run 执行期读得到。"""
    from agent.subagent.context import current_node_id, current_workflow_id

    seen: list[tuple] = []

    class IdentityProbeLLM:
        async def chat(self, messages, tools=None, model="gpt-4"):
            seen.append((current_workflow_id(), current_node_id()))
            return LLMResponse(content="ok", stop_reason="end_turn", usage=Usage(1, 1))

    manager_for_scheduler.llm = IdentityProbeLLM()
    result = await _run(WorkflowScheduler(manager_for_scheduler), _fanout_spec())
    workflow_id = result["workflow_id"]
    assert (workflow_id, "a") in seen
    assert (workflow_id, "b") in seen
    # 调度器退出后不残留身份
    assert current_workflow_id() is None
    assert current_node_id() is None


@pytest.mark.asyncio
async def test_aggregate_concat_reducer_joins_summaries(manager_for_scheduler):
    manager_for_scheduler.llm = StaticLLM("finding")
    result = await _run(WorkflowScheduler(manager_for_scheduler), _fanout_spec())
    join_node = next(node for node in result["nodes"] if node["id"] == "join")
    assert join_node["summary"].count("finding") == 3


@pytest.mark.asyncio
async def test_aggregate_merge_dict_reducer(manager_for_scheduler):
    manager_for_scheduler.llm = StaticLLM('{"alpha": 1}')
    spec = {
        "goal": "merge",
        "nodes": [
            {"id": "a", "kind": "subagent", "task": "t", "outputs": ["slots"]},
            {"id": "b", "kind": "subagent", "task": "t", "outputs": ["slots"]},
            {
                "id": "join",
                "kind": "aggregate",
                "join": "all_required",
                "strategy": "collect",
                "outputs": ["merged"],
            },
        ],
        "edges": [
            {"from": "a", "to": "join", "reducer": "merge_dict"},
            {"from": "b", "to": "join", "reducer": "merge_dict"},
        ],
    }
    result = await _run(WorkflowScheduler(manager_for_scheduler), spec)
    join_node = next(node for node in result["nodes"] if node["id"] == "join")
    assert json.loads(join_node["slots"]["merged"]) == {"alpha": 1}


@pytest.mark.asyncio
async def test_reducer_helpers_are_restricted_enum_only():
    assert aggregate_slots(["a", "b"], "concat") == "a\nb"
    assert aggregate_slots(["", "b"], "first_non_empty") == "b"
    assert aggregate_slots(["a", "b"], "last") == "b"
    assert aggregate_slots(['{"x": 1}', '{"y": 2}'], "merge_dict") == '{"x": 1, "y": 2}'
    with pytest.raises(WorkflowValidationError):
        aggregate_slots(["a"], "exec")


# --- 3.3 route 节点 ---------------------------------------------------------


def test_matches_route_is_case_insensitive_structured_labels():
    assert matches_route("APPROVED looks good", "APPROVED")
    assert matches_route("approved", "APPROVED")
    assert not matches_route("CRITIQUE: fix it", "APPROVED")
    assert not matches_route("", "APPROVED")


def test_matches_route_requires_a_label_at_the_start_of_the_line():
    """building-review Issue 7：子串包含会让 `NOT APPROVED` 命中 APPROVED 分支。"""
    assert not matches_route("NOT APPROVED at all", "APPROVED")
    assert not matches_route("DISAPPROVED", "APPROVED")
    assert not matches_route("This is not APPROVED yet", "APPROVED")
    # 结构化标签（行首）仍然命中，含后随标点/空白
    assert matches_route("APPROVED.", "APPROVED")
    assert matches_route("APPROVED\nlooks good", "APPROVED")
    assert matches_route("  APPROVED looks good", "APPROVED")


@pytest.mark.asyncio
async def test_route_takes_matching_case(manager_for_scheduler):
    manager_for_scheduler.llm = ScriptedLLM(["draft", "APPROVED looks good", "final"])
    spec = {
        "goal": "review",
        "nodes": [
            {"id": "producer", "kind": "subagent", "task": "draft"},
            {"id": "reviewer", "kind": "subagent", "task": "review"},
            {
                "id": "gate",
                "kind": "route",
                "task": "route on the reviewer verdict",
                "cases": [{"when": "APPROVED", "to": "done"}],
                "default": "producer",
                "max_routes": 2,
            },
            {"id": "done", "kind": "subagent", "task": "finalize"},
        ],
        "entry": ["producer"],
        "edges": [
            {"from": "producer", "to": "reviewer"},
            {"from": "reviewer", "to": "gate"},
            {"from": "gate", "to": "done"},
            {"from": "gate", "to": "producer"},
        ],
    }
    result = await _run(WorkflowScheduler(manager_for_scheduler), spec)
    assert result["status"] == "completed"
    assert {node["id"] for node in result["nodes"]} == {"producer", "reviewer", "gate", "done"}
    route_node = next(node for node in result["nodes"] if node["id"] == "gate")
    assert route_node["verdict"] == "APPROVED"  # 命中的结构化标签
    assert "APPROVED looks good" in route_node["raw"]  # 上游原文（诊断用）
    assert route_node["targets"] == ["done"]


@pytest.mark.asyncio
async def test_route_default_branch_loops_back(manager_for_scheduler):
    manager = manager_for_scheduler
    manager.llm = ReviewLoopLLM()
    spec = {
        "goal": "review",
        "nodes": [
            {"id": "producer", "kind": "subagent", "task": "draft the proposal"},
            {"id": "reviewer", "kind": "subagent", "task": "review proposal"},
            {
                "id": "gate",
                "kind": "route",
                "task": "route on review verdict",
                "cases": [{"when": "APPROVED", "to": "done"}],
                "default": "producer",
                "max_routes": 3,
            },
            {"id": "done", "kind": "subagent", "task": "finalize"},
        ],
        "entry": ["producer"],
        "edges": [
            {"from": "producer", "to": "reviewer"},
            {"from": "reviewer", "to": "gate"},
            {"from": "gate", "to": "done"},
            {"from": "gate", "to": "producer"},
        ],
    }
    result = await _run(WorkflowScheduler(manager), spec)
    assert result["status"] == "completed"
    producer = next(node for node in result["nodes"] if node["id"] == "producer")
    assert producer["runs"] == 2  # 第二轮真的重跑了 producer（复用同一 session）
    # 复用 session：producer 只建了一个 subagent 会话，跑了 2 次
    assert len(manager._sessions[producer["subagent_id"]].runs) == 2


# --- 3.4 foreach 节点 -------------------------------------------------------


def test_extract_collection_from_structured_sources():
    assert extract_collection(["a", "b"], None) == ["a", "b"]
    assert extract_collection('{"items": ["x", "y"]}', "items") == ["x", "y"]
    assert extract_collection("x\ny\nz", None) == ["x", "y", "z"]
    assert extract_collection({"results": [1, 2]}, "results") == [1, 2]
    assert extract_collection("plain text", None) == ["plain text"]


def test_render_item_task_substitutes_placeholders():
    assert render_item_task("review {item}", "alpha") == "review alpha"
    assert render_item_task("review {item}", {"name": "alpha"}) == "review alpha"
    assert render_item_task("count {index}: {item}", 5, index=2) == "count 2: 5"
    assert render_item_task("no placeholder", "x") == "no placeholder"


@pytest.mark.asyncio
async def test_foreach_expands_items_into_parallel_nodes(manager_for_scheduler):
    manager_for_scheduler.llm = StaticLLM("item done")
    spec = {
        "goal": "fan out over items",
        "nodes": [
            {
                "id": "fan",
                "kind": "foreach",
                "task": "review {item}",
                "items": ["alpha", "beta", "gamma"],
                "outputs": ["items"],
            },
            {
                "id": "join",
                "kind": "aggregate",
                "join": "all_required",
                "strategy": "collect",
            },
        ],
        "edges": [{"from": "fan", "to": "join", "reducer": "concat"}],
    }
    result = await _run(WorkflowScheduler(manager_for_scheduler), spec)
    assert result["status"] == "completed"
    ids = {node["id"] for node in result["nodes"]}
    assert ids == {"fan", "join"}
    fan = next(node for node in result["nodes"] if node["id"] == "fan")
    assert fan["status"] == "completed"
    assert fan["items"] == 3
    assert len(fan["subagent_ids"]) == 3
    assert fan["subagent_id"] is None
    assert fan["summary"].count("item done") == 3
    # 展开的 run 都带 node 身份
    for subagent_id in fan["subagent_ids"]:
        assert manager_for_scheduler._sessions[subagent_id].node_id == "fan"


@pytest.mark.asyncio
async def test_foreach_respects_max_items(manager_for_scheduler):
    manager_for_scheduler.llm = StaticLLM("done")
    spec = {
        "goal": "cap the fan out",
        "nodes": [
            {
                "id": "fan",
                "kind": "foreach",
                "task": "review {item}",
                "items": ["a", "b", "c", "d", "e"],
                "max_items": 2,
            }
        ],
        "edges": [],
    }
    result = await _run(WorkflowScheduler(manager_for_scheduler), spec)
    fan = result["nodes"][0]
    assert fan["items"] == 2
    assert len(fan["subagent_ids"]) == 2


@pytest.mark.asyncio
async def test_foreach_consumes_upstream_collection(manager_for_scheduler):
    manager_for_scheduler.llm = StaticLLM('{"items": ["one", "two"]}')
    spec = {
        "goal": "dynamic fan out",
        "nodes": [
            {"id": "planner", "kind": "subagent", "task": "plan", "outputs": ["plan"]},
            {
                "id": "fan",
                "kind": "foreach",
                "task": "work on {item}",
                "source": "planner",
                "source_field": "items",
                "outputs": ["items"],
            },
            {
                "id": "join",
                "kind": "aggregate",
                "join": "all_required",
                "strategy": "collect",
            },
        ],
        "edges": [
            {"from": "planner", "to": "fan"},
            {"from": "fan", "to": "join", "reducer": "concat"},
        ],
    }
    result = await _run(WorkflowScheduler(manager_for_scheduler), spec)
    fan = next(node for node in result["nodes"] if node["id"] == "fan")
    assert fan["items"] == 2


# --- foreach 并发（building-review Issue 1） --------------------------------


@pytest.mark.asyncio
async def test_foreach_expands_items_concurrently(manager_for_scheduler):
    """foreack 是「并行展开」原语：展开项必须真并发，而不是逐项串行等待。"""
    probe = ConcurrencyProbeLLM(hold=0.05)
    manager_for_scheduler.llm = probe
    spec = {
        "goal": "fan out concurrently",
        "nodes": [
            {
                "id": "fan",
                "kind": "foreach",
                "task": "review {item}",
                "items": [f"item-{i}" for i in range(4)],
                "outputs": ["items"],
            }
        ],
        "edges": [],
    }
    result = await _run(WorkflowScheduler(manager_for_scheduler), spec)
    assert result["status"] == "completed"
    assert probe.peak > 1, f"foreach 展开项应并发执行，实测 LLM 并发峰值 {probe.peak}"
    assert result["peak_active"] > 1


@pytest.mark.asyncio
async def test_foreach_concurrency_is_bounded_by_max_active(tmp_path):
    """并发展开仍受 max_active 背压约束：峰值不越过物理并发上限。"""
    probe = ConcurrencyProbeLLM(hold=0.05)
    manager = _manager(tmp_path, probe, max_active=2)
    manager._permits._limit = 2  # type: ignore[attr-defined]
    spec = {
        "goal": "bounded fan out",
        "nodes": [
            {
                "id": "fan",
                "kind": "foreach",
                "task": "work {item}",
                "items": [f"item-{i}" for i in range(6)],
                "outputs": ["items"],
            }
        ],
        "edges": [],
    }
    result = await _run(WorkflowScheduler(manager), spec)
    assert result["status"] == "completed"
    assert probe.peak > 1, "展开项应当并发"
    assert probe.peak <= 2, f"并发峰值 {probe.peak} 越过了 max_active=2"


# --- foreach 三闸（building-review Issue 2 / Issue 4） ---------------------


@pytest.mark.asyncio
async def test_foreach_run_budget_reports_graph_recursion_exceeded(manager_for_scheduler):
    """foreach 展开项也受 max_runs 约束，超限走 envelope 而非 spawn 桶文案。"""
    manager_for_scheduler.llm = StaticLLM("ok")
    spec = {
        "goal": "budgeted fan out",
        "nodes": [
            {
                "id": "fan",
                "kind": "foreach",
                "task": "work {item}",
                "items": [f"item-{i}" for i in range(8)],
                "outputs": ["items"],
            }
        ],
        "edges": [],
        "max_runs": 3,
    }
    result = await _run(WorkflowScheduler(manager_for_scheduler), spec)
    assert result["status"] == "graph_recursion_exceeded"
    assert result["diagnostics"]["reason"] == "max_runs"
    # 不是「图报 completed 但节点死在 spawn budget」
    fan = next(node for node in result["nodes"] if node["id"] == "fan")
    assert "spawn budget" not in (fan.get("error") or "")


@pytest.mark.asyncio
async def test_foreach_expansion_counts_toward_max_nodes(manager_for_scheduler):
    """Q5：max_nodes 是「节点数（含 foreach 展开）」，展开后必须复检。"""
    manager_for_scheduler.llm = StaticLLM("ok")
    spec = {
        "goal": "too wide",
        "nodes": [
            {
                "id": "fan",
                "kind": "foreach",
                "task": "work {item}",
                "items": [f"item-{i}" for i in range(20)],
                "outputs": ["items"],
            }
        ],
        "edges": [],
        "max_nodes": 5,
    }
    result = await _run(WorkflowScheduler(manager_for_scheduler), spec)
    assert result["status"] == "graph_recursion_exceeded"
    assert result["diagnostics"]["reason"] == "max_nodes"
    # 拒绝在展开建 session 之前发生
    created = [
        session
        for session in manager_for_scheduler._sessions.values()
        if session.name.startswith("fan-")
    ]
    assert created == []


# --- queue_full 可观测性（building-review Issue 3） ------------------------


@pytest.mark.asyncio
async def test_queue_full_is_diagnosable_and_does_not_raise_index_error(tmp_path):
    """Q2 兜底分支：queue_full 时 run record 已被 manager 弹掉，不能索引 runs[-1]。"""
    gated = GatedLLM()
    manager = _manager(tmp_path, gated, max_active=1, max_queued_runs=0)
    manager._permits._limit = 1  # type: ignore[attr-defined]
    # 一个非 workflow 的 run 占住唯一许可，使调度器的派发必然撞 queue_full
    foreign = manager.create_subagent(name="foreign")
    await manager.run_subagent(subagent_id=foreign["subagent_id"], task="hold", wait=False)

    spec = {"goal": "blocked", "nodes": [{"id": "a", "kind": "subagent", "task": "t"}], "edges": []}
    result = await _run(WorkflowScheduler(manager), spec)
    node = result["nodes"][0]
    assert node["status"] == "failed"
    assert "IndexError" not in (node.get("error") or "")
    assert "queue" in (node.get("reason") or "").lower()
    gated.release()


# --- 生命周期 / 取消 --------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_marks_workflow_and_stops_dispatch(manager_for_scheduler):
    manager = manager_for_scheduler
    scheduler = WorkflowScheduler(manager)
    blocked = GatedLLM()  # 所有 run 都卡在 gate 上，取消必然命中 in-flight
    manager.llm = blocked
    spec = _fanout_spec()
    task = asyncio.create_task(scheduler.run(parse_workflow_spec(spec)))
    await blocked.started.wait()
    envelope = scheduler.cancel()
    assert envelope["status"] == "cancelling"
    assert envelope["workflow_id"] == scheduler.workflow_id
    result = await asyncio.wait_for(task, timeout=5)
    assert result["status"] == "cancelled"
    # 未派发的节点标 blocked，in-flight 的标 cancelled；都不允许「已完成」
    assert all(
        node["status"] in ("cancelled", "failed", "blocked") for node in result["nodes"]
    )


@pytest.mark.asyncio
async def test_get_status_reports_bounded_node_summaries(manager_for_scheduler):
    manager = manager_for_scheduler
    scheduler = WorkflowScheduler(manager)
    result = await scheduler.run(parse_workflow_spec(_fanout_spec()))
    status = scheduler.status()
    assert status["status"] == "completed"
    assert status["workflow_id"] == result["workflow_id"]
    assert status["spec_hash"] == result["spec_hash"]
    assert len(status["nodes"]) == 4
    for node in status["nodes"]:
        assert "summary" in node
        assert len(node["summary"]) <= 400


@pytest.mark.asyncio
async def test_bus_is_available_inside_workflow_nodes(manager_for_scheduler):
    """节点内 PublishBusMessage 必须拿得到 bus（在派发上下文里装入）。"""
    from agent.subagent.context import current_bus

    manager = manager_for_scheduler
    seen: list[bool] = []

    class BusProbeLLM:
        async def chat(self, messages, tools=None, model="gpt-4"):
            seen.append(current_bus() is not None)
            return LLMResponse(content="ok", stop_reason="end_turn", usage=Usage(1, 1))

    manager.llm = BusProbeLLM()
    result = await _run(WorkflowScheduler(manager), _fanout_spec())
    assert result["status"] == "completed"
    assert seen and all(seen)
    assert "bus" in result
    # workflow 结束后 bus 不残留
    assert current_bus() is None


@pytest.mark.asyncio
async def test_totals_and_metrics(manager_for_scheduler):
    result = await _run(WorkflowScheduler(manager_for_scheduler), _fanout_spec())
    assert result["total_cost"] == 0
    assert result["peak_active"] >= 1
    assert result["critical_path_s"] > 0
    assert result["started_at"] <= result["finished_at"]
