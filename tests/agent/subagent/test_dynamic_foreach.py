"""动态 foreach：跨层 source 递归 + ``max_items=0``（change ``workflow-budget-attribution``，task 3.2/3.3）。

覆盖 D5 与 grill 决策 9 及用户确认 Q9/Q10：

- **跨层 source**（Q10）：只沿**数据边**递归；优先读 source 节点自身 ``result`` 槽，
  没有才在**唯一数据上游**时继续向上；多入边无物化 result = schema 歧义拒绝；递归在
  无上游/已访问/环处终止；环检测复用 Tarjan SCC（``parse_workflow_spec`` 校验期）；
  ``source_field`` **只应用一次**。
- **max_items=0**（Q9）：单独的**非负**解析函数放行 0（不改全局 ``_positive_int`` 语义）；
  预检**按剩余容量截断**而非抛 C2 异常，且**只对 max_items==0 生效**（>0 保留
  C2 fail-fast）；截断发生在 ``_expand_plan`` **之前**；可展开数取
  「C4 max_total_runs / C2 max_runs / C2 max_nodes」三者剩余上限的**最小值**。
"""
import json

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


class RecordingLLM:
    def __init__(self, content="ok"):
        self.content = content
        self.tasks: list[str] = []

    async def chat(self, messages, tools=None, model="gpt-4"):
        for message in messages:
            if message.role == "user" and isinstance(message.content, str):
                self.tasks.append(message.content)
                break
        return LLMResponse(content=self.content, stop_reason="end_turn", usage=Usage(5, 5))


class ScriptedLLM:
    """按调用序号返回脚本内容（用于让 planner 产出集合、其余返回普通文本）。"""

    def __init__(self, responses):
        self.responses = responses
        self.calls = 0

    async def chat(self, messages, tools=None, model="gpt-4"):
        idx = min(self.calls, len(self.responses) - 1)
        self.calls += 1
        return LLMResponse(content=self.responses[idx], stop_reason="end_turn", usage=Usage(5, 5))


@pytest.fixture
def manager(tmp_path):
    return SubAgentManager(
        llm=RecordingLLM(),
        config=AsterwyndConfig(),
        parent_mode=AgentMode.BUILD,
        workspace_policy=WorkspacePolicy(workspace_root=tmp_path),
    )


# --- max_items 解析（Q9） ---------------------------------------------------


def test_max_items_zero_is_accepted():
    """Q9：``max_items=0`` 表示「不静态截断、展开到预算耗尽」——必须放行 0。"""
    spec = {
        "goal": "g",
        "nodes": [
            {
                "id": "fan",
                "kind": "foreach",
                "task": "do {item}",
                "items": ["a"],
                "max_items": 0,
            }
        ],
        "edges": [],
    }
    parsed = parse_workflow_spec(spec)
    assert parsed.node("fan").max_items == 0


def test_max_items_negative_rejected():
    spec = {
        "goal": "g",
        "nodes": [
            {"id": "fan", "kind": "foreach", "task": "do {item}", "items": ["a"], "max_items": -1}
        ],
        "edges": [],
    }
    with pytest.raises(WorkflowValidationError):
        parse_workflow_spec(spec)


def test_global_positive_int_semantics_unchanged():
    """Q9 边界：放行 max_items=0 不得改 ``_positive_int`` 的全局语义（max_nodes 仍拒 0）。"""
    spec = {
        "goal": "g",
        "nodes": [{"id": "a", "kind": "subagent", "task": "t"}],
        "edges": [],
        "max_nodes": 0,
    }
    with pytest.raises(WorkflowValidationError):
        parse_workflow_spec(spec)


# --- 跨层 source（Q10） -----------------------------------------------------


def test_source_cycle_is_rejected_at_validation():
    """Q10：``source`` 在 route 参与的环里 → 校验期拒绝（复用 Tarjan SCC）。"""
    spec = {
        "goal": "g",
        "nodes": [
            {"id": "fan", "kind": "foreach", "task": "do {item}", "source": "loopback", "source_field": "items"},
            {
                "id": "gate",
                "kind": "route",
                "cases": [{"when": "MORE", "to": "loopback"}],
                "default": "done",
            },
            {"id": "loopback", "kind": "aggregate", "strategy": "collect"},
            {"id": "done", "kind": "subagent", "task": "finish"},
        ],
        "edges": [
            {"from": "fan", "to": "loopback"},
            {"from": "loopback", "to": "gate"},
            {"from": "gate", "to": "loopback"},
            {"from": "gate", "to": "done"},
        ],
        "entry": ["fan"],
        "terminal": ["done"],
    }
    with pytest.raises(WorkflowValidationError, match="cycle|环|circular"):
        parse_workflow_spec(spec)


@pytest.mark.asyncio
async def test_source_reads_own_result_slot_first(manager):
    """Q10：优先读 source 节点自身 ``result`` 槽（一层，不向上递归）。"""
    manager.llm = ScriptedLLM(['{"items": ["one", "two"]}', "worked"])
    spec = {
        "goal": "g",
        "nodes": [
            {"id": "planner", "kind": "subagent", "task": "plan"},
            {"id": "fan", "kind": "foreach", "task": "work {item}", "source": "planner", "source_field": "items"},
        ],
        "edges": [{"from": "planner", "to": "fan"}],
        "terminal": ["fan"],
    }
    result = await WorkflowScheduler(manager).run(parse_workflow_spec(spec))
    fan = next(node for node in result["nodes"] if node["id"] == "fan")
    assert fan["items"] == 2


@pytest.mark.asyncio
async def test_source_recurses_to_unique_upstream(manager):
    """Q10：source 自身没物化 result 槽时，沿**唯一数据上游**继续向上解析。

    ``planner → holder(collect aggregate, 但不物化 source_field) → fan``：
    source = holder，holder 的 result 槽是 concat 的上游产出 → 取 ``source_field``
    展开。这正是 spec Scenario「跨层 source 递归解析」。
    """
    manager.llm = ScriptedLLM(['{"items": ["one", "two", "three"]}', "worked"])
    spec = {
        "goal": "g",
        "nodes": [
            {"id": "planner", "kind": "subagent", "task": "plan"},
            {"id": "holder", "kind": "aggregate", "strategy": "collect", "outputs": ["result"]},
            {"id": "fan", "kind": "foreach", "task": "work {item}", "source": "holder", "source_field": "items"},
        ],
        "edges": [
            {"from": "planner", "to": "holder"},
            {"from": "holder", "to": "fan"},
        ],
        "terminal": ["fan"],
    }
    result = await WorkflowScheduler(manager).run(parse_workflow_spec(spec))
    fan = next(node for node in result["nodes"] if node["id"] == "fan")
    assert fan["items"] == 3


@pytest.mark.asyncio
async def test_source_field_applied_exactly_once(manager):
    """Q10：``source_field`` 只应用一次——二次取字段会把 ``items`` 再取一层变空。"""
    manager.llm = ScriptedLLM([json.dumps({"items": {"items": ["nested-only"]}}), "worked"])
    spec = {
        "goal": "g",
        "nodes": [
            {"id": "planner", "kind": "subagent", "task": "plan"},
            {"id": "fan", "kind": "foreach", "task": "work {item}", "source": "planner", "source_field": "items"},
        ],
        "edges": [{"from": "planner", "to": "fan"}],
        "terminal": ["fan"],
    }
    result = await WorkflowScheduler(manager).run(parse_workflow_spec(spec))
    fan = next(node for node in result["nodes"] if node["id"] == "fan")
    # 只应用一次 source_field → 取到 {"items": [...]} 这个 dict → extract_collection
    # 挑其中的 "items" 键 → 1 项。若二次应用会退化成空集或错误展开。
    assert fan["items"] == 1


# --- max_items=0（Q9） ------------------------------------------------------


@pytest.mark.asyncio
async def test_max_items_zero_expands_all_when_budget_plenty(manager):
    """Q9：预算充足时 ``max_items=0`` 展开全部集合项（不静态截断）。"""
    manager.llm = ScriptedLLM([json.dumps({"items": list(range(25))}), "worked"])
    spec = {
        "goal": "g",
        "nodes": [
            {"id": "planner", "kind": "subagent", "task": "plan"},
            {"id": "fan", "kind": "foreach", "task": "work {item}", "source": "planner", "source_field": "items", "max_items": 0},
        ],
        "edges": [{"from": "planner", "to": "fan"}],
        "terminal": ["fan"],
    }
    result = await WorkflowScheduler(manager).run(parse_workflow_spec(spec))
    fan = next(node for node in result["nodes"] if node["id"] == "fan")
    assert fan["items"] == 25


@pytest.mark.asyncio
async def test_max_items_zero_truncates_to_remaining_run_budget(manager):
    """Q9：``max_items=0`` 在图级 run 预算不足时按**剩余容量截断**（不抛 C2 异常）。"""
    manager.llm = ScriptedLLM([json.dumps({"items": list(range(50))}), "worked"])
    # producer 1 run + fan 展开项；max_runs=10 → 展开上限 = 10 - 1(planner) = 9
    spec = {
        "goal": "g",
        "nodes": [
            {"id": "planner", "kind": "subagent", "task": "plan"},
            {"id": "fan", "kind": "foreach", "task": "work {item}", "source": "planner", "source_field": "items", "max_items": 0},
        ],
        "edges": [{"from": "planner", "to": "fan"}],
        "terminal": ["fan"],
        "max_runs": 10,
    }
    result = await WorkflowScheduler(manager).run(parse_workflow_spec(spec))
    fan = next(node for node in result["nodes"] if node["id"] == "fan")
    assert fan["items"] < 50
    assert fan["items"] <= 9
    # 不报 C2 结构闸（max_items=0 走截断退化）
    assert result["status"] == "completed"


@pytest.mark.asyncio
async def test_max_items_zero_expands_to_c2_bound_when_budget_unlimited(manager):
    """issue #196：默认预算不限（max_total_runs=0）时，``max_items=0`` 的展开容量
    退化为 **C2 两闸的最小值**，而不是 0。

    grill 标注的暗雷：``_remaining_expansion_capacity`` 在三个候选上限全为 0/缺失时
    返回 0，调用方 ``items[:0]`` 是空集——若 C4 维度被默认关掉后没写到 C2 兜底，
    这里会静默展开成 0 项。本测试锁住「预算不限 ⇒ 仍按 C2 max_runs 展开」。"""
    manager.llm = ScriptedLLM([json.dumps({"items": list(range(50))}), "worked"])
    spec = {
        "goal": "g",
        "nodes": [
            {"id": "planner", "kind": "subagent", "task": "plan"},
            {"id": "fan", "kind": "foreach", "task": "work {item}", "source": "planner", "source_field": "items", "max_items": 0},
        ],
        "edges": [{"from": "planner", "to": "fan"}],
        "terminal": ["fan"],
        "max_runs": 12,
    }
    # manager 用默认配置 → C4 max_total_runs=0（不限）
    assert manager.config.subagents.workflow.budget.max_total_runs == 0
    result = await WorkflowScheduler(manager).run(parse_workflow_spec(spec))
    fan = next(node for node in result["nodes"] if node["id"] == "fan")
    # C2 max_runs=12：planner 占 1 → 展开应为 11，而不是空集 0
    assert fan["items"] == 11
    assert result["status"] == "completed"


@pytest.mark.asyncio
async def test_max_items_zero_respects_c4_max_total_runs(manager):
    """Q9：可展开数取「C4 max_total_runs / C2 max_runs / C2 max_nodes」最小值。"""
    manager.llm = ScriptedLLM([json.dumps({"items": list(range(50))}), "worked"])
    spec = {
        "goal": "g",
        "nodes": [
            {"id": "planner", "kind": "subagent", "task": "plan"},
            {"id": "fan", "kind": "foreach", "task": "work {item}", "source": "planner", "source_field": "items", "max_items": 0},
        ],
        "edges": [{"from": "planner", "to": "fan"}],
        "terminal": ["fan"],
    }
    config = AsterwyndConfig()
    import dataclasses

    workflow = dataclasses.replace(
        config.subagents.workflow,
        budget=dataclasses.replace(config.subagents.workflow.budget, max_total_runs=8),
    )
    constrained = dataclasses.replace(
        config, subagents=dataclasses.replace(config.subagents, workflow=workflow)
    )
    manager.config = constrained
    result = await WorkflowScheduler(manager).run(parse_workflow_spec(spec))
    fan = next(node for node in result["nodes"] if node["id"] == "fan")
    # C4 上限 8：planner 占 1 → 展开最多 7；C2 max_runs 默认 300 不构成约束
    assert fan["items"] <= 7


@pytest.mark.asyncio
async def test_max_items_positive_keeps_c2_fail_fast(manager):
    """Q9：``max_items>0`` 保留 C2 fail-fast（不静默删结构闸）。"""
    manager.llm = RecordingLLM("ok")
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
    result = await WorkflowScheduler(manager).run(parse_workflow_spec(spec))
    assert result["status"] == "graph_recursion_exceeded"
    assert result["diagnostics"]["reason"] == "max_runs"
