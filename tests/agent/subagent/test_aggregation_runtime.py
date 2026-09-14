"""调度器运行期的分层汇聚 + 三 hash + bounded 任务文本（tasks 2.1/2.2/2.3、3.1）。

覆盖 grill 决策 5/6 与 Q3/Q4/Q5/Q6/Q7：

- 自动兜底插入的 aggregate **必须进 `_expanded_nodes` 记账并复检 max_nodes**
  （声明期校验在 parse 时一次算完，自动插层发生在 parse 之后）；
- auto aggregate 用 ``strategy="llm"`` → 计 ``max_runs``；
- foreach 展开期复检（声明期 1 个节点 → 展开 100 项时必须插层）；
- ``runtime_graph_hash`` / ``expansion_plan_hash`` / ``declared_spec_hash`` 三 hash 分离；
- **真正的爆点在 ``_node_task_text``/``_aggregate_task_text``**：层级中间节点消费
  bounded summary/ref 而不是 concat 全文；
- envelope 保留 ``nodes``（C2 的 24 处断言依赖它）+ 新增逻辑执行单元计数。
"""
import json

import pytest

from agent.config import AsterwyndConfig
from agent.llm import LLMResponse, Usage
from agent.run_config import AgentMode
from agent.subagent.manager import SubAgentManager
from agent.subagent.scheduler import WorkflowScheduler
from agent.subagent.workflow import parse_workflow_spec
from agent.workspace_policy import WorkspacePolicy


class RecordingLLM:
    """记录每次 run 收到的 task 文本（下游输入构造的观测点）。"""

    def __init__(self, content="worker result"):
        self.content = content
        self.tasks: list[str] = []

    async def chat(self, messages, tools=None, model="gpt-4"):
        for message in messages:
            content = message.content
            if message.role == "user" and isinstance(content, str):
                self.tasks.append(content)
                break
        return LLMResponse(content=self.content, stop_reason="end_turn", usage=Usage(5, 5))


@pytest.fixture
def manager(tmp_path):
    return SubAgentManager(
        llm=RecordingLLM(),
        config=AsterwyndConfig(),
        parent_mode=AgentMode.BUILD,
        workspace_policy=WorkspacePolicy(workspace_root=tmp_path),
    )


def _spec_with_leaves(count: int, aggregate_edges: bool = True) -> dict:
    leaves = [{"id": f"l{i}", "kind": "subagent", "task": f"task {i}"} for i in range(count)]
    nodes = list(leaves) + [{"id": "root", "kind": "aggregate", "strategy": "collect"}]
    edges = [{"from": f"l{i}", "to": "root", "reducer": "concat"} for i in range(count)]
    return {"goal": "g", "nodes": nodes, "edges": edges, "terminal": ["root"]}


# --- 2.1 自动兜底插层 -------------------------------------------------------


@pytest.mark.asyncio
async def test_auto_inserted_layers_execute_and_aggregate(manager):
    manager.llm = RecordingLLM("finding")
    scheduler = WorkflowScheduler(manager)
    spec = parse_workflow_spec(_spec_with_leaves(25))
    result = await scheduler.run(spec)

    assert result["status"] == "completed"
    # 25 个 leaf → ceil(25/10)=3 个 auto shard；root 上游 3 ≤ 10
    assert len(scheduler._plan.inserted_nodes) == 3
    # auto aggregate 是 llm → 真实 run，计入 completed
    assert result["completed"] == 25 + 3
    # 自动插入的节点出现在 envelope 的 nodes 里（C2 断言兼容）
    ids = {node["id"] for node in result["nodes"]}
    assert set(scheduler._plan.inserted_nodes) <= ids
    # root 的 summary 仍然是聚合结果
    root = next(node for node in result["nodes"] if node["id"] == "root")
    assert root["status"] == "completed"


@pytest.mark.asyncio
async def test_no_insertion_at_or_below_threshold(manager):
    scheduler = WorkflowScheduler(manager)
    spec = parse_workflow_spec(_spec_with_leaves(10))
    result = await scheduler.run(spec)
    assert scheduler._plan.inserted_nodes == ()
    assert result["completed"] == 10


@pytest.mark.asyncio
async def test_auto_inserted_nodes_are_charged_against_max_nodes(manager):
    """grill 决策 6：自动插层绕过 parse 期校验 → 运行期必须记账并复检。"""
    raw = _spec_with_leaves(25)
    # 25 leaf + 1 root = 26 声明节点；插 3 个 auto 后 29 > max_nodes 28 → 必须报限
    raw["max_nodes"] = 28
    # 上限低于声明节点数时 parse 期就拒绝；这里把上限设在「声明通过、插层后超限」的缝里。
    raw["max_nodes"] = 27
    spec = parse_workflow_spec(raw)
    scheduler = WorkflowScheduler(manager)
    result = await scheduler.run(spec)
    assert result["status"] == "graph_recursion_exceeded"
    assert result["diagnostics"]["reason"] == "max_nodes"


@pytest.mark.asyncio
async def test_auto_aggregates_consume_max_runs(manager):
    """auto aggregate 默认 llm → 每个都是一个真实 run，必须计入 max_runs。"""
    raw = _spec_with_leaves(25)
    raw["max_runs"] = 27  # 25 leaf + 3 auto = 28 > 27
    scheduler = WorkflowScheduler(manager)
    result = await scheduler.run(parse_workflow_spec(raw))
    assert result["status"] == "graph_recursion_exceeded"
    assert result["diagnostics"]["reason"] == "max_runs"


# --- 2.1 展开期复检（Q3） ---------------------------------------------------


@pytest.mark.asyncio
async def test_foreach_expansion_triggers_layer_insertion(manager):
    """声明期 2 个节点，运行时 foreach 展开 25 项 → 必须插层。"""
    raw = {
        "goal": "g",
        "nodes": [
            {"id": "seed", "kind": "subagent", "task": "seed"},
            {
                "id": "fan",
                "kind": "foreach",
                "task": "do {item}",
                "source": "seed",
                "source_field": "items",
                "max_items": 50,
            },
            {"id": "root", "kind": "aggregate", "strategy": "collect"},
        ],
        "edges": [
            {"from": "seed", "to": "fan"},
            {"from": "fan", "to": "root", "reducer": "concat"},
        ],
        "terminal": ["root"],
    }
    manager.llm = RecordingLLM(json.dumps({"items": list(range(25))}))
    scheduler = WorkflowScheduler(manager)
    result = await scheduler.run(parse_workflow_spec(raw))

    assert result["status"] == "completed"
    # fan 展开 25 项 → ceil(25/10)=3 个自动 shard（max_items 默认 20 会截断，故显式放大）
    assert len(scheduler._plan.inserted_nodes) == 3
    assert scheduler._plan.expansion_plan_hash != scheduler._plan.declared_spec_hash


@pytest.mark.asyncio
async def test_foreach_expansion_is_charged_against_max_nodes(manager):
    raw = {
        "goal": "g",
        "nodes": [
            {"id": "seed", "kind": "subagent", "task": "seed"},
            {
                "id": "fan",
                "kind": "foreach",
                "task": "do {item}",
                "source": "seed",
                "source_field": "items",
            },
            {"id": "root", "kind": "aggregate", "strategy": "collect"},
        ],
        "edges": [
            {"from": "seed", "to": "fan"},
            {"from": "fan", "to": "root", "reducer": "concat"},
        ],
        "terminal": ["root"],
        "max_nodes": 20,
    }
    manager.llm = RecordingLLM(json.dumps({"items": list(range(15))}))
    scheduler = WorkflowScheduler(manager)
    result = await scheduler.run(parse_workflow_spec(raw))
    # 15 个展开项 + 2 个 auto shard = 17，加声明 3 个 = 20；不超限
    assert result["status"] == "completed"

    manager2 = SubAgentManager(
        llm=RecordingLLM(json.dumps({"items": list(range(15))})),
        config=AsterwyndConfig(),
        parent_mode=AgentMode.BUILD,
        workspace_policy=manager.workspace_policy,
    )
    scheduler2 = WorkflowScheduler(manager2)
    raw["max_nodes"] = 5
    result2 = await scheduler2.run(parse_workflow_spec(raw))
    assert result2["status"] == "graph_recursion_exceeded"
    assert result2["diagnostics"]["reason"] == "max_nodes"


# --- 三 hash 分离 -----------------------------------------------------------


@pytest.mark.asyncio
async def test_three_hashes_are_distinct_for_inserted_graphs(manager):
    scheduler = WorkflowScheduler(manager)
    await scheduler.run(parse_workflow_spec(_spec_with_leaves(25)))
    plan = scheduler._plan
    assert plan.declared_spec_hash != plan.runtime_graph_hash
    assert plan.declared_spec_hash == scheduler.spec.spec_hash  # 原始 spec 未变


# --- 真正爆点：任务文本构造 -------------------------------------------------


@pytest.mark.asyncio
async def test_aggregate_task_text_is_bounded_for_many_leaves(manager):
    """100 个 leaf 的长结果不能整段拼进 aggregate 的 task（grill 决策 5）。"""
    long_text = "y" * 4000
    manager.llm = RecordingLLM(long_text)
    scheduler = WorkflowScheduler(manager)
    await scheduler.run(parse_workflow_spec(_spec_with_leaves(100)))

    aggregate_tasks = [
        task
        for task in manager.llm.tasks
        if "auto-aggregate" in task or "Aggregate the results" in task
    ]
    assert aggregate_tasks
    # 每个 auto shard 的输入上界：10 个上游 × bounded summary
    for task in aggregate_tasks:
        assert len(task) < 10 * 4000, "aggregate task must not concatenate full results"


@pytest.mark.asyncio
async def test_node_task_text_uses_bounded_upstream_output(manager):
    """下游 subagent 消费上游 bounded 产出，不是完整 summary 原文。"""
    long_text = "z" * 8000
    manager.llm = RecordingLLM(long_text)
    raw = {
        "goal": "g",
        "nodes": [
            {"id": "a", "kind": "subagent", "task": "produce"},
            {"id": "b", "kind": "subagent", "task": "consume"},
        ],
        "edges": [{"from": "a", "to": "b"}],
    }
    scheduler = WorkflowScheduler(manager)
    await scheduler.run(parse_workflow_spec(raw))
    downstream_task = next(task for task in manager.llm.tasks if task.startswith("consume"))
    assert long_text not in downstream_task
    assert len(downstream_task) < len(long_text)


# --- 3.1 bounded envelope ---------------------------------------------------


@pytest.mark.asyncio
async def test_envelope_reports_logical_execution_units(manager):
    scheduler = WorkflowScheduler(manager)
    result = await scheduler.run(parse_workflow_spec(_spec_with_leaves(10)))
    # Q2：分母 = 逻辑执行单元；普通节点 1、collect aggregate 也是 1 个执行单元
    assert result["total"] == 11
    assert result["completed"] == 10        # 旧字段：真实 run 数（兼容）
    assert result["failed"] == 0
    assert result["cancelled"] == 0
    assert result["budget_exceeded"] == 0
    assert result["blocked"] == 0
    assert result["pending"] == 0
    # C2 兼容：nodes / current_nodes / spec_hash 都还在
    assert len(result["nodes"]) == 11
    assert result["current_nodes"] == []
    assert result["declared_spec_hash"] == result["spec_hash"]


@pytest.mark.asyncio
async def test_envelope_root_result_ref_points_at_artifacts(manager, tmp_path):
    manager.llm = RecordingLLM("final answer")
    scheduler = WorkflowScheduler(manager)
    result = await scheduler.run(parse_workflow_spec(_spec_with_leaves(3)))
    assert result["root_result_ref"]
    store = manager.workflow_store(scheduler.workflow_id)
    assert store.load(result["root_result_ref"]) is not None


@pytest.mark.asyncio
async def test_latest_events_records_terminal_transitions(manager):
    scheduler = WorkflowScheduler(manager)
    result = await scheduler.run(parse_workflow_spec(_spec_with_leaves(3)))
    events = result["latest_events"]
    assert events
    assert len(events) <= 5
    node_events = [event for event in events if event["type"] == "node_terminal"]
    assert node_events
    for event in node_events:
        # Q5 的字段集：node_id + status + summary_preview（外加事件类型）
        assert {"node_id", "status", "summary_preview"} <= set(event)
        assert len(event["summary_preview"]) <= 80
    assert {event["node_id"] for event in node_events} <= {"l0", "l1", "l2", "root"}


@pytest.mark.asyncio
async def test_latest_events_keeps_only_the_last_five(manager):
    scheduler = WorkflowScheduler(manager)
    await scheduler.run(parse_workflow_spec(_spec_with_leaves(12)))
    assert len(scheduler._latest_events) == 5
