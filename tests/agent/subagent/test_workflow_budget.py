"""`WorkflowBudget` 四维度账本 + 超限状态机（change ``workflow-budget-attribution``，§1）。

覆盖 D1/D2 与 grill 决策 2/7 及用户确认 Q4/Q5/Q6/Q11：

- 四维度 tokens / cost_usd / runs / wall_time_s，任一维度 `0 = 不限`；
- token/cost 是**完成后累加**判定（记账点在 loop 层，见 Q6 方案 B）；
- runs 维度**复用调度器 `self._runs`**，C4 检查置于 C2 `max_runs` **之前**；
- 超限 → stop_new + 取消 queued + drain 在跑 + 根节点 `budget_exceeded`；
- `WorkflowBudgetExceeded` **不得逃出 `run()`**（映射为 envelope）。
"""
import asyncio
import dataclasses

import pytest

from agent.config import AsterwyndConfig, WorkflowBudgetConfig
from agent.llm import LLMResponse, Usage
from agent.run_config import AgentMode
from agent.subagent.manager import SubAgentManager
from agent.subagent.scheduler import WorkflowScheduler, _budget_config
from agent.subagent.workflow import parse_workflow_spec
from agent.subagent.workflow_budget import (
    WorkflowBudget,
    WorkflowBudgetExceeded,
)
from agent.workspace_policy import WorkspacePolicy


# --- 纯账本单测 -------------------------------------------------------------


def _budget(**overrides) -> WorkflowBudget:
    return WorkflowBudget(WorkflowBudgetConfig(**overrides), started_at=0.0)


def test_defaults_come_from_config():
    budget = WorkflowBudget()
    assert budget.max_tokens == 200000
    assert budget.max_cost_usd == 5.0
    assert budget.max_runs == 300
    assert budget.max_wall_time_s == 1800.0


def test_record_llm_call_accumulates_tokens_and_cache_aware_cost():
    """Q6/Q12：记账点从 ``response.usage`` 四档全算 cache-aware cost。"""
    budget = _budget(max_total_tokens=1_000_000, max_total_cost_usd=1000.0)
    budget.record_llm_call(
        model="claude-opus-4",
        input_tokens=1_000_000,
        output_tokens=0,
        cache_read_tokens=1_000_000,
        cache_write_tokens=1_000_000,
    )
    # tokens 口径 = input + output（Q16：不含 cache）
    assert budget.tokens == 1_000_000
    # 1M fresh * 15 + 1M read * 1.50 + 1M write * 18.75 = 35.25
    assert budget.cost_usd == pytest.approx(35.25)


def test_zero_limit_means_dimension_disabled():
    """Q11：四个维度 `0 = 不限`；Q14：`max_total_runs=0` 只解除 C4 的 runs 维度。"""
    budget = _budget(
        max_total_tokens=0,
        max_total_cost_usd=0,
        max_total_runs=0,
        max_wall_time_s=0,
    )
    for _ in range(50):
        budget.record_llm_call(
            model="claude-opus-4", input_tokens=1_000_000, output_tokens=1_000_000
        )
    assert budget.exceeded_dimension(runs=10_000, now=10_000_000.0) is None


def test_token_dimension_exceeded():
    budget = _budget(max_total_tokens=100)
    budget.record_llm_call(model="gpt-4o-mini", input_tokens=80, output_tokens=30)
    assert budget.exceeded_dimension(runs=0) == "tokens"


def test_cost_dimension_exceeded():
    budget = _budget(max_total_tokens=0, max_total_cost_usd=0.001)
    budget.record_llm_call(model="claude-opus-4", input_tokens=1_000_000, output_tokens=0)
    assert budget.exceeded_dimension(runs=0) == "cost_usd"


def test_runs_dimension_exceeded_and_reserve_raises():
    budget = _budget(max_total_runs=3)
    budget.reserve_runs(3)  # 恰好到上限：不超
    with pytest.raises(WorkflowBudgetExceeded) as excinfo:
        budget.reserve_runs(4)
    assert excinfo.value.dimension == "runs"
    assert budget.exceeded_dimension(runs=4) == "runs"


def test_wall_time_dimension_exceeded():
    budget = _budget(max_wall_time_s=60)
    assert budget.exceeded_dimension(runs=0, now=59.0) is None
    assert budget.exceeded_dimension(runs=0, now=60.5) == "wall_time_s"


def test_dimensions_snapshot_shape():
    budget = _budget(max_total_tokens=100, max_total_runs=7)
    budget.record_llm_call(model="gpt-4o-mini", input_tokens=10, output_tokens=5)
    dims = budget.dimensions(runs=2)
    assert dims["tokens"] == {"limit": 100, "used": 15}
    assert dims["runs"] == {"limit": 7, "used": 2}
    assert dims["cost_usd"]["limit"] == 5.0
    assert dims["wall_time_s"]["limit"] == 1800.0


# --- 调度器接线 -------------------------------------------------------------


class StaticLLM:
    def __init__(self, content="worker result", usage=None):
        self.content = content
        self.usage = usage or Usage(5, 5)
        self.model = "gpt-4o-mini"

    async def chat(self, messages, tools=None, model="gpt-4"):
        return LLMResponse(content=self.content, stop_reason="end_turn", usage=self.usage)


class GatedLLM:
    """所有 run 阻塞在 gate 上；用于验证 drain 语义（不取消在跑 run）。"""

    def __init__(self):
        self.gate = asyncio.Event()
        self.started = asyncio.Event()
        self.model = "gpt-4o-mini"

    def release(self) -> None:
        self.gate.set()

    async def chat(self, messages, tools=None, model="gpt-4"):
        self.started.set()
        await self.gate.wait()
        return LLMResponse(content="done", stop_reason="end_turn", usage=Usage(5, 5))


def _config_with_budget(**budget_overrides) -> AsterwyndConfig:
    config = AsterwyndConfig()
    workflow = dataclasses.replace(
        config.subagents.workflow,
        budget=dataclasses.replace(config.subagents.workflow.budget, **budget_overrides),
    )
    return dataclasses.replace(
        config, subagents=dataclasses.replace(config.subagents, workflow=workflow)
    )


def _manager(tmp_path, llm, **budget_overrides) -> SubAgentManager:
    return SubAgentManager(
        llm=llm,
        config=_config_with_budget(**budget_overrides),
        parent_mode=AgentMode.BUILD,
        workspace_policy=WorkspacePolicy(workspace_root=tmp_path),
    )


def _leaf_spec(count: int, **overrides) -> dict:
    """``count`` 个互不依赖的 leaf（同一 superstep 一起派发）。"""
    base = {
        "goal": "g",
        "nodes": [{"id": f"n{i}", "kind": "subagent", "task": f"t{i}"} for i in range(count)],
        "edges": [],
    }
    base.update(overrides)
    return base


def _chain_spec(count: int, **overrides) -> dict:
    """``n0 → n1 → …`` 链式图：每个节点独占一个 superstep，才能观察 stop_new。"""
    base = {
        "goal": "g",
        "nodes": [{"id": f"n{i}", "kind": "subagent", "task": f"t{i}"} for i in range(count)],
        "edges": [{"from": f"n{i}", "to": f"n{i + 1}"} for i in range(count - 1)],
        "terminal": [f"n{count - 1}"],
    }
    base.update(overrides)
    return base


def test_budget_config_helper_reads_nested_config():
    config = _config_with_budget(max_total_runs=11)
    assert _budget_config(config).max_total_runs == 11


@pytest.mark.asyncio
async def test_token_budget_stops_dispatch_and_reports_budget_exceeded(tmp_path):
    """token 超限 → stop_new + drain；envelope status=budget_exceeded。"""
    manager = _manager(tmp_path, StaticLLM(usage=Usage(90, 90)), max_total_tokens=100)
    result = await WorkflowScheduler(manager).run(parse_workflow_spec(_chain_spec(6)))

    assert result["status"] == "budget_exceeded"
    assert result["budget"]["exceeded"] is True
    assert result["budget"]["exceeded_dimension"] == "tokens"
    assert result["budget"]["dimensions"]["tokens"]["used"] > 100
    # 不是 C2 的结构闸出口
    assert result["diagnostics"] == {}
    # stop_new 确实生效：远未跑完全部 6 个节点
    assert result["completed"] < 6


@pytest.mark.asyncio
async def test_cost_budget_stops_dispatch(tmp_path):
    manager = _manager(
        tmp_path,
        StaticLLM(usage=Usage(1_000_000, 0)),
        max_total_tokens=0,
        max_total_cost_usd=0.01,
    )
    result = await WorkflowScheduler(manager).run(parse_workflow_spec(_chain_spec(5)))
    assert result["status"] == "budget_exceeded"
    assert result["budget"]["exceeded_dimension"] == "cost_usd"
    assert result["budget"]["dimensions"]["cost_usd"]["used"] > 0.01


@pytest.mark.asyncio
async def test_runs_budget_preempts_c2_max_runs_at_same_value(tmp_path):
    """Q4：C4 检查置于 C2 之前——同值 300（此处同为 2）时由 C4 触发 budget_exceeded。"""
    manager = _manager(tmp_path, StaticLLM(), max_total_runs=2)
    spec = _chain_spec(5, max_runs=2)
    result = await WorkflowScheduler(manager).run(parse_workflow_spec(spec))
    assert result["status"] == "budget_exceeded"
    assert result["budget"]["exceeded_dimension"] == "runs"
    assert result["diagnostics"] == {}  # 不是 max_runs 的 graph_recursion_exceeded


@pytest.mark.asyncio
async def test_c2_max_runs_still_wins_when_explicitly_smaller(tmp_path):
    """C2 显式更小时仍走结构闸（D2 语义边界：不删 C2 的 max_runs）。"""
    manager = _manager(tmp_path, StaticLLM(), max_total_runs=50)
    spec = _chain_spec(5, max_runs=2)
    result = await WorkflowScheduler(manager).run(parse_workflow_spec(spec))
    assert result["status"] == "graph_recursion_exceeded"
    assert result["diagnostics"]["reason"] == "max_runs"


@pytest.mark.asyncio
async def test_runs_budget_zero_disables_c4_but_keeps_c2_structural_gate(tmp_path):
    """Q14：`max_total_runs=0` 只解除 C4 的 runs 维度，C2 `max_runs` 仍兜底。"""
    manager = _manager(tmp_path, StaticLLM(), max_total_runs=0)
    spec = _chain_spec(5, max_runs=2)
    result = await WorkflowScheduler(manager).run(parse_workflow_spec(spec))
    assert result["status"] == "graph_recursion_exceeded"
    assert result["diagnostics"]["reason"] == "max_runs"


@pytest.mark.asyncio
async def test_wall_time_budget_stops_new_but_drains_in_flight(tmp_path):
    """wall_time 超限也不取消在跑 run——只停止派发（D2）。"""
    llm = GatedLLM()
    manager = _manager(tmp_path, llm, max_wall_time_s=1)
    scheduler = WorkflowScheduler(manager)
    spec = parse_workflow_spec(_chain_spec(4, recursion_limit=10))
    task = asyncio.create_task(scheduler.run(spec))
    await asyncio.sleep(0.05)
    # 第一个节点已派发并在 gate 上阻塞；把账本挂钟起点推回过去，令 wall_time 立刻超限。
    scheduler._budget.started_at = scheduler._budget.started_at - 100
    llm.release()
    result = await asyncio.wait_for(task, timeout=5)
    assert result["status"] == "budget_exceeded"
    assert result["budget"]["exceeded_dimension"] == "wall_time_s"
    # drain 语义：在跑的 run 跑完才收敛（completed 计数 >= 1）
    assert result["completed"] >= 1


@pytest.mark.asyncio
async def test_root_nodes_marked_budget_exceeded(tmp_path):
    """Q5：根节点（``plan.terminal``）未完成则改 `budget_exceeded`，已完成不覆盖。"""
    manager = _manager(tmp_path, StaticLLM(usage=Usage(90, 90)), max_total_tokens=100)
    result = await WorkflowScheduler(manager).run(parse_workflow_spec(_chain_spec(6)))
    assert result["status"] == "budget_exceeded"
    statuses = {node["id"]: node["status"] for node in result["nodes"]}
    # 链尾 n5 是唯一 terminal，被预算停下时是 pending → 必须改标 budget_exceeded
    assert statuses["n5"] == "budget_exceeded"
    assert result["budget_exceeded"] >= 1


@pytest.mark.asyncio
async def test_completed_root_is_not_overwritten(tmp_path):
    """Q5：已完成的 terminal 不被 ``budget_exceeded`` 覆盖（fan-out 图多个 terminal）。

    图上两条臂：``done`` 是短的（第 1 个 superstep 就完成），``c0 → c1`` 是长的。
    token 预算被第 1 个 superstep 打爆后，``c1`` 停下未派发——它未完成，必须改标
    ``budget_exceeded``；而 ``done`` 已完成，**不许**被覆盖。
    """
    manager = _manager(tmp_path, StaticLLM(usage=Usage(90, 90)), max_total_tokens=100)
    spec = {
        "goal": "g",
        "nodes": [
            {"id": "done", "kind": "subagent", "task": "short arm"},
            {"id": "c0", "kind": "subagent", "task": "long arm 0"},
            {"id": "c1", "kind": "subagent", "task": "long arm 1"},
        ],
        "edges": [{"from": "c0", "to": "c1"}],
    }
    result = await WorkflowScheduler(manager).run(parse_workflow_spec(spec))
    assert result["status"] == "budget_exceeded"
    statuses = {node["id"]: node["status"] for node in result["nodes"]}
    assert statuses["done"] == "completed"  # 已完成的 terminal 不被覆盖
    assert statuses["c1"] == "budget_exceeded"  # 未完成的 terminal 改标
    assert result["budget_exceeded"] == 1


@pytest.mark.asyncio
async def test_budget_exceeded_does_not_escape_run(tmp_path):
    """spec Scenario「超限出口不逃出 run」：返回 envelope，不抛未捕获异常。"""
    manager = _manager(tmp_path, StaticLLM(usage=Usage(90, 90)), max_total_tokens=100)
    # 不抛异常即为通过；返回的必须是 envelope
    result = await WorkflowScheduler(manager).run(parse_workflow_spec(_chain_spec(6)))
    assert isinstance(result, dict)
    assert result["status"] == "budget_exceeded"
    assert result["workflow_id"]


@pytest.mark.asyncio
async def test_budget_not_configured_is_noop_for_existing_behavior(tmp_path):
    """默认预算（200k tokens / $5 / 300 runs / 1800s）不得改变小图的既有行为。"""
    manager = _manager(tmp_path, StaticLLM())
    result = await WorkflowScheduler(manager).run(parse_workflow_spec(_leaf_spec(4)))
    assert result["status"] == "completed"
    assert result["budget"]["exceeded"] is False
    assert result["budget"]["exceeded_dimension"] is None
