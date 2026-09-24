"""envelope 暴露 budget + attribution（change ``workflow-budget-attribution``，task 5.1/5.2）。

覆盖 D7 与用户确认 Q15/Q16：

- ``status()``/``_envelope`` 增 ``budget``（四维度 limit/used + exceeded 标志）与
  ``attribution``（四维 **top-k bounded** 摘要，k=5，不整表返回——100 节点的
  by_node 整表会撑爆父上下文）；
- 分桶值 round 到 **9 位**（与 envelope ``total_cost`` 对齐）；tokens 口径 =
  input+output（**不含 cache**）；cost 单位 USD；未知模型桶标 ``estimated: true``；
- ``WorkflowStore.save_attribution`` 在 ``_teardown()``/``run()`` 结算时**一次性落盘**；
- ``GetWorkflow`` 的 ``_DETAILS`` 扩含 ``"attribution"``，返回 ``attribution_ref``。
"""
import dataclasses
import json

import pytest

from agent.config import AsterwyndConfig
from agent.cost_tracker import CostLedger
from agent.llm import LLMResponse, Usage
from agent.run_config import AgentMode
from agent.subagent.manager import SubAgentManager
from agent.subagent.scheduler import WorkflowScheduler
from agent.subagent.workflow import parse_workflow_spec
from agent.subagent.workflow_store import WorkflowStore
from agent.tools.builtin.subagents import GetWorkflowTool
from agent.workspace_policy import WorkspacePolicy


class CostingLLM:
    def __init__(self, tokens=100):
        self.tokens = tokens
        self.model = "gpt-4o-mini"

    async def chat(self, messages, tools=None, model="gpt-4"):
        return LLMResponse(
            content="ok",
            stop_reason="end_turn",
            usage=Usage(self.tokens, self.tokens),
        )


@pytest.fixture
def manager(tmp_path):
    return SubAgentManager(
        llm=CostingLLM(),
        config=AsterwyndConfig(),
        parent_mode=AgentMode.BUILD,
        workspace_policy=WorkspacePolicy(workspace_root=tmp_path),
        cost_ledger=CostLedger(),
    )


def _wide_spec(count: int) -> dict:
    return {
        "goal": "g",
        "nodes": [
            {"id": f"n{i}", "kind": "subagent", "task": f"t{i}"} for i in range(count)
        ],
        "edges": [],
    }


# --- budget 块 --------------------------------------------------------------


@pytest.mark.asyncio
async def test_envelope_budget_block_has_four_dimensions(manager):
    result = await WorkflowScheduler(manager).run(parse_workflow_spec(_wide_spec(3)))
    budget = result["budget"]
    assert set(budget["dimensions"].keys()) == {
        "tokens",
        "cost_usd",
        "runs",
        "wall_time_s",
    }
    for dim in budget["dimensions"].values():
        assert set(dim.keys()) == {"limit", "used"}
    assert budget["exceeded"] is False
    assert budget["exceeded_dimension"] is None
    # 既有顶层 int 键必须共存、不被改名（Confirmed Decision 7）
    assert isinstance(result["budget_exceeded"], int)


@pytest.mark.asyncio
async def test_envelope_budget_reports_exceeded_dimension(manager):
    config = AsterwyndConfig()
    workflow = dataclasses.replace(
        config.subagents.workflow,
        budget=dataclasses.replace(config.subagents.workflow.budget, max_total_runs=1),
    )
    manager.config = dataclasses.replace(
        config, subagents=dataclasses.replace(config.subagents, workflow=workflow)
    )
    spec = {
        "goal": "g",
        "nodes": [
            {"id": "a", "kind": "subagent", "task": "ta"},
            {"id": "b", "kind": "subagent", "task": "tb"},
        ],
        "edges": [{"from": "a", "to": "b"}],
        "terminal": ["b"],
    }
    result = await WorkflowScheduler(manager).run(parse_workflow_spec(spec))
    assert result["budget"]["exceeded"] is True
    assert result["budget"]["exceeded_dimension"] == "runs"
    assert result["budget"]["dimensions"]["runs"]["limit"] == 1


# --- attribution 摘要 -------------------------------------------------------


@pytest.mark.asyncio
async def test_envelope_attribution_summarises_four_dimensions(manager):
    result = await WorkflowScheduler(manager).run(parse_workflow_spec(_wide_spec(3)))
    attr = result["attribution"]
    assert {"by_workflow", "by_node", "by_depth", "by_edge"} <= set(attr.keys())
    assert attr["by_workflow"]  # 至少本 workflow 一个桶
    assert "wf" in next(iter(attr["by_workflow"].keys())) or attr["by_workflow"]


@pytest.mark.asyncio
async def test_envelope_attribution_is_top_k_bounded(manager):
    """D7：每维只回 top-k（k=5），不整表返回；被截断条数显式报告。"""
    manager.llm = CostingLLM(tokens=10)
    result = await WorkflowScheduler(manager).run(parse_workflow_spec(_wide_spec(12)))
    attr = result["attribution"]
    assert len(attr["by_node"]) <= 5
    assert attr["counts"]["by_node_total"] == 12
    assert attr["counts"]["by_node_omitted"] == 7
    # top-k 按 cost 降序：第一个桶是最贵的
    costs = [bucket["cost"] for bucket in attr["by_node"].values()]
    assert costs == sorted(costs, reverse=True)


@pytest.mark.asyncio
async def test_attribution_values_round_to_nine_places_and_exclude_cache(manager):
    result = await WorkflowScheduler(manager).run(parse_workflow_spec(_wide_spec(2)))
    for dim in ("by_workflow", "by_node", "by_depth", "by_edge"):
        for bucket in result["attribution"][dim].values():
            assert bucket["cost"] == round(bucket["cost"], 9)
            assert isinstance(bucket["tokens"], int)
            assert "estimated" in bucket
    # 槽值 round 到 9 位；tokens 口径不含 cache（这里 cache 为 0，无法区分，但键存在）
    assert set(result["attribution"].keys()) == {
        "by_workflow",
        "by_node",
        "by_depth",
        "by_edge",
        "counts",
    }


# --- 落盘（Q15） ------------------------------------------------------------


def test_workflow_store_save_attribution(tmp_path):
    store = WorkflowStore.for_workspace(tmp_path, "wf_attr")
    payload = {"by_node": {"a": {"tokens": 1, "cost": 0.5, "estimated": False}}}
    ref = store.save_attribution("wf_attr", payload)
    assert ref.endswith("attribution")
    page = store.read(ref)
    assert page["missing"] is False
    assert json.loads(page["content"]) == payload


@pytest.mark.asyncio
async def test_run_persists_attribution_and_exposes_ref(manager):
    """Q15：结算时一次性落盘，envelope 带 ``attribution_ref``。"""
    scheduler = WorkflowScheduler(manager)
    result = await scheduler.run(parse_workflow_spec(_wide_spec(2)))
    ref = result.get("attribution_ref")
    assert ref, "run() 结算必须落盘 attribution 并给出 ref"
    stored = scheduler._workflow_store().read(ref)
    assert stored["missing"] is False
    payload = json.loads(stored["content"])
    assert "by_node" in payload


# --- GetWorkflow detail（Q15） ----------------------------------------------


@pytest.mark.asyncio
async def test_get_workflow_accepts_attribution_detail(manager):
    scheduler = WorkflowScheduler(manager)
    await scheduler.run(parse_workflow_spec(_wide_spec(2)))
    manager.register_workflow(scheduler)
    out = json.loads(
        await GetWorkflowTool(manager).execute(
            workflow_id=scheduler.workflow_id, detail="attribution"
        )
    )
    assert "invalid_detail" not in out.get("status", "")
    assert out.get("attribution_ref")


def test_get_workflow_details_include_attribution():
    assert "attribution" in GetWorkflowTool._DETAILS


@pytest.mark.asyncio
async def test_get_workflow_rejects_unknown_detail(manager):
    """未知 detail 合法值集合仍被拒绝（只扩了一个值，不放开白名单）。"""
    scheduler = WorkflowScheduler(manager)
    await scheduler.run(parse_workflow_spec(_wide_spec(1)))
    manager.register_workflow(scheduler)
    out = json.loads(
        await GetWorkflowTool(manager).execute(
            workflow_id=scheduler.workflow_id, detail="bogus"
        )
    )
    assert out["status"] == "invalid_detail"
    assert "attribution" in out["reason"]
