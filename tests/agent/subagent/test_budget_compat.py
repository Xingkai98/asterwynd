"""兼容回归（change ``workflow-budget-attribution``，task 6.2）。

三条口径必须逐条锁定，防止 C4 静默改变既有语义：

1. ``CostLedger.record`` 不带归因键时三维账单（by_session/by_phase/by_tool）逐字节不变；
2. C2 的 ``max_runs`` 声明期校验不变（``parse_workflow_spec`` 照旧拒绝非法值）；
3. ``max_items>0`` 保留 C2 fail-fast（不静默删结构闸，既有的两条断言不破）。
"""
import dataclasses
import json

import pytest

from agent.config import AsterwyndConfig
from agent.cost_tracker import CostLedger
from agent.llm import LLMResponse, Usage
from agent.run_config import AgentMode
from agent.subagent.manager import SubAgentManager
from agent.subagent.scheduler import (
    TERMINAL_NODE_STATUSES,
    WorkflowScheduler,
)
from agent.subagent.workflow import (
    WorkflowValidationError,
    parse_workflow_spec,
)
from agent.workspace_policy import WorkspacePolicy


class StaticLLM:
    def __init__(self, content="ok"):
        self.content = content

    async def chat(self, messages, tools=None, model="gpt-4"):
        return LLMResponse(content=self.content, stop_reason="end_turn", usage=Usage(5, 5))


@pytest.fixture
def manager(tmp_path):
    return SubAgentManager(
        llm=StaticLLM(),
        config=AsterwyndConfig(),
        parent_mode=AgentMode.BUILD,
        workspace_policy=WorkspacePolicy(workspace_root=tmp_path),
    )


# --- 1. CostLedger 三维账单不变 ---------------------------------------------


def test_cost_ledger_three_dims_unchanged_without_attribution_keys():
    ledger = CostLedger()
    ledger.record("gpt-4o", 1000, 500, session_id="s1", phase="building", tool_name="Read")
    ledger.record("gpt-4o", 2000, 1000, session_id="s1", phase="building", tool_name="Bash")
    ledger.record("gpt-4o", 500, 250, session_id="s2", phase="planning", tool_name="Read")
    bill = ledger.bill()
    # 与改造前的期望值逐项相同（见 tests/benchmark/test_observability_quantification.py）
    assert bill["by_session"]["s1"]["tokens"] == 4500
    assert bill["by_session"]["s2"]["tokens"] == 750
    assert bill["by_phase"]["building"]["tokens"] == 4500
    assert bill["by_tool"]["Read"]["tokens"] == 2250
    assert bill["by_tool"]["Bash"]["tokens"] == 3000
    assert ledger.total() == pytest.approx(
        (1000 / 1e6) * 2.5
        + (500 / 1e6) * 10
        + (2000 / 1e6) * 2.5
        + (1000 / 1e6) * 10
        + (500 / 1e6) * 2.5
        + (250 / 1e6) * 10
    )


def test_unknown_model_still_records_zero_legacy_cost():
    """既有语义：未知模型的 legacy 三维账单记 tokens、cost 为 0（不静默估算）。"""
    ledger = CostLedger()
    ledger.record("future-model-99", 1000, 1000, session_id="s1", phase="building")
    bill = ledger.bill()
    assert bill["by_session"]["s1"]["tokens"] == 2000
    assert bill["by_session"]["s1"]["cost"] == 0.0
    assert ledger.total() == 0.0


# --- 2. C2 max_runs 声明期校验不变 ------------------------------------------


@pytest.mark.parametrize("value", [0, -1, "many", None, 1.5])
def test_max_runs_declaration_validation_unchanged(value):
    spec = {
        "goal": "g",
        "nodes": [{"id": "a", "kind": "subagent", "task": "t"}],
        "edges": [],
        "max_runs": value,
    }
    with pytest.raises(WorkflowValidationError):
        parse_workflow_spec(spec)


def test_max_nodes_and_recursion_limit_unchanged():
    for field in ("max_nodes", "recursion_limit"):
        spec = {
            "goal": "g",
            "nodes": [{"id": "a", "kind": "subagent", "task": "t"}],
            "edges": [],
            field: 0,
        }
        with pytest.raises(WorkflowValidationError):
            parse_workflow_spec(spec)


# --- 3. max_items>0 保留 C2 fail-fast ---------------------------------------


@pytest.mark.asyncio
async def test_max_items_positive_keeps_max_runs_fail_fast(manager):
    """既有断言 ``test_foreach_run_budget_reports_graph_recursion_exceeded`` 的口径。"""
    manager.llm = StaticLLM("ok")
    spec = {
        "goal": "budgeted fan out",
        "nodes": [
            {
                "id": "fan",
                "kind": "foreach",
                "task": "work {item}",
                "items": [f"item-{i}" for i in range(8)],
                "outputs": ["items"],
                # max_items 缺省 = 20（>0）：静态截断 + C2 fail-fast 都要保留
            }
        ],
        "edges": [],
        "max_runs": 3,
    }
    result = await WorkflowScheduler(manager).run(parse_workflow_spec(spec))
    assert result["status"] == "graph_recursion_exceeded"
    assert result["diagnostics"]["reason"] == "max_runs"


@pytest.mark.asyncio
async def test_auto_aggregates_consume_max_runs_unchanged(manager):
    """既有断言 ``test_auto_aggregates_consume_max_runs`` 的口径。"""
    manager.llm = StaticLLM("finding")
    leaves = [{"id": f"l{i}", "kind": "subagent", "task": f"task {i}"} for i in range(25)]
    nodes = list(leaves) + [{"id": "root", "kind": "aggregate", "strategy": "collect"}]
    edges = [{"from": f"l{i}", "to": "root", "reducer": "concat"} for i in range(25)]
    raw = {
        "goal": "g",
        "nodes": nodes,
        "edges": edges,
        "terminal": ["root"],
        "max_runs": 27,
    }
    result = await WorkflowScheduler(manager).run(parse_workflow_spec(raw))
    assert result["status"] == "graph_recursion_exceeded"
    assert result["diagnostics"]["reason"] == "max_runs"


# --- 4. 新增节点级终态不破坏既有终态集合 ------------------------------------


def test_terminal_node_statuses_extended_not_replaced():
    assert {"completed", "failed", "cancelled", "blocked"} <= TERMINAL_NODE_STATUSES
    assert "budget_exceeded" in TERMINAL_NODE_STATUSES


@pytest.mark.asyncio
async def test_default_budget_keeps_small_workflow_completed(manager):
    """默认预算下既有小图行为完全不变（status/completed/diagnostics 都不动）。"""
    spec = {
        "goal": "g",
        "nodes": [
            {"id": "a", "kind": "subagent", "task": "ta"},
            {"id": "b", "kind": "subagent", "task": "tb"},
        ],
        "edges": [],
    }
    result = await WorkflowScheduler(manager).run(parse_workflow_spec(spec))
    assert result["status"] == "completed"
    assert result["completed"] == 2
    assert result["diagnostics"] == {}
    assert result["budget_exceeded"] == 0
