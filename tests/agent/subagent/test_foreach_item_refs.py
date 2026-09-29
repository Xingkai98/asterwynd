"""foreach 的 per-worker ref 通道（Q1，变化 ``workflow-builtin-templates``）。

``GetWorkflow(detail='nodes')`` 对 ``kind=="foreach"`` 节点读 ``state.item_runs``，
吐 ``item_refs: [{index, subagent_id, run_id, result_ref?}]``，并带
``items_total`` / ``item_refs_omitted``。

硬约束（R2）：
1. ``result_ref`` **仅成功项**出现——失败/取消/预算超限的 run 不落盘（``_complete_run``
   才写 ref），其信号以有界 ``reason`` / ``status`` 呈现（与 legacy ``_worker_entry``
   同口径）。
2. **跳过未派发的空槽**（预算 drain 前被拦时槽为默认 ``_ItemRunSlot()``）。
3. **自带界**——展开项数无上界（``workers=100000``），``item_refs`` 长度 ≤ 固定上限
   （复用 ``_PARENT_NODES_LIMIT``=200），超出进 ``item_refs_omitted``。

字段定义（钉死）：``items_total = len(state.item_runs)``（本轮展开项数，含空槽），
``item_refs_omitted = items_total - len(item_refs)``（涵盖空槽 + 超上限两类）。
``item_refs`` 只反映容器**最后一轮**展开。
"""
import json

import pytest

from agent.config import AsterwyndConfig
from agent.llm import LLMResponse, Usage
from agent.run_config import AgentMode
from agent.subagent.manager import SubAgentManager
from agent.subagent.scheduler import _PARENT_NODES_LIMIT, WorkflowScheduler
from agent.subagent.workflow import parse_workflow_spec
from agent.tools.builtin.subagents import GetWorkflowTool
from agent.workspace_policy import WorkspacePolicy


def _manager(tmp_path, llm) -> SubAgentManager:
    return SubAgentManager(
        llm=llm,
        config=AsterwyndConfig(),
        parent_mode=AgentMode.BUILD,
        workspace_policy=WorkspacePolicy(workspace_root=tmp_path),
    )


class OkLLM:
    async def chat(self, messages, tools=None, model="gpt-4"):
        return LLMResponse(content="Z" * 30000, stop_reason="end_turn", usage=Usage(5, 5))


class FailOneLLM:
    """第二个被调用的 worker 失败。"""

    def __init__(self):
        self.n = 0

    async def chat(self, messages, tools=None, model="gpt-4"):
        self.n += 1
        if self.n == 2:
            raise RuntimeError("simulated failure of item 1")
        return LLMResponse(content="ok-" + "x" * 30000, stop_reason="end_turn", usage=Usage(5, 5))


FOREACH_SPEC = {
    "goal": "g",
    "nodes": [
        {"id": "fan", "kind": "foreach", "task": "t", "items": [1, 2, 3]},
        {"id": "root", "kind": "aggregate", "strategy": "collect"},
    ],
    "edges": [{"from": "fan", "to": "root", "reducer": "concat"}],
    "terminal": ["root"],
}


async def _run(manager, spec_dict):
    spec = parse_workflow_spec(spec_dict)
    scheduler = WorkflowScheduler(manager)
    manager.register_workflow(scheduler)
    await scheduler.run(spec)
    out = json.loads(
        await GetWorkflowTool(manager).execute(
            workflow_id=scheduler.workflow_id, detail="nodes"
        )
    )
    return out, scheduler


@pytest.mark.asyncio
async def test_foreach_item_refs_present_for_success(tmp_path):
    out, _ = await _run(_manager(tmp_path, OkLLM()), FOREACH_SPEC)
    fan = next(node for node in out["nodes"] if node["id"] == "fan")
    assert fan["items_total"] == 3
    assert fan["item_refs_omitted"] == 0
    assert len(fan["item_refs"]) == 3
    for entry in fan["item_refs"]:
        assert set(entry) >= {"index", "subagent_id", "run_id", "result_ref"}
        assert entry["subagent_id"]
        assert entry["run_id"]
        assert entry["result_ref"].startswith("artifact://workflow/")
    assert [e["index"] for e in fan["item_refs"]] == [0, 1, 2]


@pytest.mark.asyncio
async def test_foreach_failed_item_has_no_result_ref(tmp_path):
    """失败项无 result_ref（不落盘），但 status/reason 可用；成功项仍有 ref。"""
    out, _ = await _run(_manager(tmp_path, FailOneLLM()), FOREACH_SPEC)
    fan = next(node for node in out["nodes"] if node["id"] == "fan")
    by_index = {e["index"]: e for e in fan["item_refs"]}
    # 成功项有 ref
    assert by_index[0]["result_ref"]
    assert by_index[2]["result_ref"]
    # 失败项：result_ref 键缺失或为 None（不承诺），但其条目仍可定位
    assert by_index[1]["subagent_id"]
    assert not by_index[1].get("result_ref")


@pytest.mark.asyncio
async def test_foreach_empty_slots_are_skipped_on_budget_drain(tmp_path):
    """容器被预算 drain 拦在派发前：槽为空，item_refs 跳过它们。"""
    spec_dict = dict(FOREACH_SPEC, max_runs=1, max_nodes=50)
    manager = _manager(tmp_path, OkLLM())
    out, _ = await _run(manager, spec_dict)
    fan = next(node for node in out["nodes"] if node["id"] == "fan")
    # 展开 3 项（items_total=3）但未派发或只派发部分；omitted 计未进入 item_refs 的项
    assert fan["items_total"] == 3
    assert fan["item_refs_omitted"] == fan["items_total"] - len(fan["item_refs"])
    # 空槽不出现在 item_refs 里（无 subagent_id 的条目）
    for entry in fan["item_refs"]:
        assert entry["subagent_id"]


@pytest.mark.asyncio
async def test_foreach_item_refs_capped(tmp_path):
    """展开项超过固定上限时，item_refs 被截到上限并显式报告 omitted。"""
    class CountingLLM:
        async def chat(self, messages, tools=None, model="gpt-4"):
            return LLMResponse(content="ok", stop_reason="end_turn", usage=Usage(5, 5))

    n = _PARENT_NODES_LIMIT + 10
    spec_dict = {
        "goal": "g",
        "nodes": [
            {"id": "fan", "kind": "foreach", "task": "t",
             "items": list(range(n)), "max_items": 0},
            {"id": "root", "kind": "aggregate", "strategy": "collect"},
        ],
        "edges": [{"from": "fan", "to": "root", "reducer": "concat"}],
        "terminal": ["root"],
        "max_runs": n + 5,
        # 自动插层（fan-in>10 时按 fan-in 分组）会额外插入聚合节点——留足余量。
        "max_nodes": n + 200,
        "recursion_limit": 60,
    }
    # 并发拉满，让 210 项在少数 superstep 内完成（避免撞 recursion_limit）。
    manager = SubAgentManager(
        llm=CountingLLM(),
        config=AsterwyndConfig(),
        parent_mode=AgentMode.BUILD,
        workspace_policy=WorkspacePolicy(workspace_root=tmp_path),
        max_active=n + 5,
    )
    out, _ = await _run(manager, spec_dict)
    fan = next(node for node in out["nodes"] if node["id"] == "fan")
    assert fan["items_total"] == n
    assert len(fan["item_refs"]) == _PARENT_NODES_LIMIT
    assert fan["item_refs_omitted"] == n - _PARENT_NODES_LIMIT


@pytest.mark.asyncio
async def test_non_foreach_node_has_no_item_refs(tmp_path):
    """对照路径：subagent 节点照旧只有节点级 result_ref，不塞 item_refs。"""
    spec_dict = {
        "goal": "g",
        "nodes": [{"id": "a", "kind": "subagent", "task": "t"},
                  {"id": "root", "kind": "aggregate", "strategy": "collect"}],
        "edges": [{"from": "a", "to": "root", "reducer": "concat"}],
        "terminal": ["root"],
    }
    out, _ = await _run(_manager(tmp_path, OkLLM()), spec_dict)
    node_a = next(node for node in out["nodes"] if node["id"] == "a")
    assert "item_refs" not in node_a
    assert node_a["result_ref"]


@pytest.mark.asyncio
async def test_summary_detail_has_no_item_refs(tmp_path):
    """detail=summary（默认）不展开 item_refs——保持既有 bounded 语义。"""
    spec = parse_workflow_spec(FOREACH_SPEC)
    manager = _manager(tmp_path, OkLLM())
    scheduler = WorkflowScheduler(manager)
    manager.register_workflow(scheduler)
    await scheduler.run(spec)
    out = json.loads(
        await GetWorkflowTool(manager).execute(workflow_id=scheduler.workflow_id)
    )
    assert out["detail"] == "summary"
    assert "item_refs" not in json.dumps(out["nodes"])
