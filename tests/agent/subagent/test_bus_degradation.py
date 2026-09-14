"""bus 降级为非权威 + 100 leaf 端到端（tasks 3.3、5.2；D4）。

- bus 只做低延迟广播/非关键提示；权威状态、依赖完成、结果完整性进 workflow
  store/事件日志；
- **bus 丢消息不影响 workflow 完成与结果正确性**（spec delta Scenario）；
- 100 个 leaf 不把 100 个完整结果注入父上下文（spec delta Scenario）——
  验收覆盖父 agent 侧 envelope **与** ``_aggregate_task_text`` 的字符串上界
  （grill 风险「严重」：只验收父侧会在实现完成后依然复现）。
"""
import json

import pytest

from agent.config import AsterwyndConfig
from agent.llm import LLMResponse, Usage
from agent.run_config import AgentMode
from agent.subagent.bus import MessageBus
from agent.subagent.manager import SubAgentManager
from agent.subagent.scheduler import WorkflowScheduler
from agent.subagent.workflow import parse_workflow_spec
from agent.workspace_policy import WorkspacePolicy


class StaticLLM:
    def __init__(self, content="finding"):
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


# --- D4：bus 丢消息不影响结果 -----------------------------------------------


@pytest.mark.asyncio
async def test_dropped_bus_messages_do_not_affect_workflow(manager):
    """max_messages=1 的 bus 会丢弃几乎所有消息，workflow 仍必须正确完成。"""
    raw = {
        "goal": "g",
        "nodes": [
            {"id": "a", "kind": "subagent", "task": "task a"},
            {"id": "b", "kind": "subagent", "task": "task b"},
            {"id": "root", "kind": "aggregate", "strategy": "collect"},
        ],
        "edges": [
            {"from": "a", "to": "root", "reducer": "concat"},
            {"from": "b", "to": "root", "reducer": "concat"},
        ],
        "terminal": ["root"],
    }
    bus = MessageBus(max_messages=1)
    for i in range(20):
        bus.publish(sender="w", topic="finding", summary=f"msg {i}")
    assert bus.size == 1  # 19 条被丢

    scheduler = WorkflowScheduler(manager, bus=bus)
    result = await scheduler.run(parse_workflow_spec(raw))
    assert result["status"] == "completed"
    assert result["completed"] == 2
    # 结果正确性不受 bus 丢消息影响：root 仍是两个 leaf 的聚合
    root = next(node for node in result["nodes"] if node["id"] == "root")
    assert root["summary"].count("finding") == 2


@pytest.mark.asyncio
async def test_authoritative_events_land_in_workflow_store_not_bus(manager):
    """D4：权威事件（节点终态）进事件日志，bus 缺席也照样有。"""
    raw = {
        "goal": "g",
        "nodes": [{"id": "a", "kind": "subagent", "task": "task a"}],
        "edges": [],
    }
    scheduler = WorkflowScheduler(manager)  # 不传 bus
    result = await scheduler.run(parse_workflow_spec(raw))
    assert result["status"] == "completed"
    events = manager.workflow_store(scheduler.workflow_id).read_events()
    types = [event["type"] for event in events]
    assert "node_terminal" in types
    assert "workflow_terminal" in types
    assert result["latest_events"]


def test_bus_documents_itself_as_non_authoritative():
    """D4：bus 的模块文档必须明说它不是权威通道。"""
    import agent.subagent.bus as bus_module

    doc = bus_module.__doc__ or ""
    assert "not persisted" in doc
    assert "authoritative" in doc.lower() or "非权威" in doc


# --- 100 leaf 端到端（spec delta Scenario） ---------------------------------


@pytest.mark.asyncio
async def test_hundred_leaves_do_not_blow_up_parent_context(manager):
    # 每个 leaf 产出 20k 字符，远超 leaf 档预算（300 token ≈ 1200 字符）：
    # 只有真被裁剪，下面的上界断言才有区分力。
    manager.llm = StaticLLM("R" * 20000)
    leaves = [{"id": f"l{i}", "kind": "subagent", "task": f"task {i}"} for i in range(100)]
    raw = {
        "goal": "research",
        "nodes": leaves + [{"id": "root", "kind": "aggregate", "strategy": "collect"}],
        "edges": [{"from": f"l{i}", "to": "root", "reducer": "concat"} for i in range(100)],
        "terminal": ["root"],
    }
    scheduler = WorkflowScheduler(manager)
    result = await scheduler.run(parse_workflow_spec(raw))

    assert result["status"] == "completed"
    # 层级汇聚真的发生了：10 个 auto shard，root 只吃 10 个上游
    assert len(scheduler._plan.inserted_nodes) == 10

    # ① 父 agent 侧：envelope 不含任何一份完整结果
    envelope_json = json.dumps(result)
    assert "R" * 20000 not in envelope_json
    node_summaries = [node["summary"] for node in result["nodes"]]
    assert all(len(summary) <= 400 for summary in node_summaries)

    # ② 下游侧（真正的爆点）：aggregate 的 task 文本按**预算**有界——
    # 上界是 O(上游数 × 档位预算)，而不是 O(上游数 × 原始长度)。
    # 无界实现会给 root 一份 100 × 20000 = 2,000,000 字符的拼接。
    plan = scheduler._plan
    leaf_cap = plan.char_budget_for("l0")
    shard_cap = plan.char_budget_for(plan.inserted_nodes[0])
    # 每个上游除正文外还有 "Input from <id> slot <s> (result_ref: <ref>):" 的前缀开销。
    per_edge_overhead = 400

    for node_id in plan.inserted_nodes:  # 每个 auto shard 吃 ≤10 个 leaf
        task = scheduler._aggregate_task_text(scheduler._states[node_id])
        assert len(task) <= 10 * (leaf_cap + per_edge_overhead)
    root_task = scheduler._aggregate_task_text(scheduler._states["root"])
    assert len(root_task) <= 10 * (shard_cap + per_edge_overhead)
    # 远远小于无界拼接（证明裁剪真的发生了）
    assert len(root_task) < 100 * 20000 / 10
    assert "R" * 20000 not in root_task


@pytest.mark.asyncio
async def test_single_upstream_collect_aggregate_is_still_bounded(manager):
    """Q3 的隐蔽场景：foreach 容器展开 100 项、只汇入**一个**上游的 collect aggregate。

    声明期只有 2 个节点、单个上游，所以不会被 fan-in 规则拆层。若汇聚器按「上游数
    < 2」提前返回，100 份结果的拼接会原样留在槽里并流向下游——正是要防的膨胀。
    """
    import json as _json

    class SeedThenBigLLM:
        """第一个 run（seed）吐出 items；其余 run 吐 20k 大结果。"""

        def __init__(self):
            self.calls = 0

        async def chat(self, messages, tools=None, model="gpt-4"):
            self.calls += 1
            content = (
                _json.dumps({"items": list(range(20))}) if self.calls == 1 else "S" * 20000
            )
            return LLMResponse(content=content, stop_reason="end_turn", usage=Usage(5, 5))

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
    manager.llm = SeedThenBigLLM()
    scheduler = WorkflowScheduler(manager)
    result = await scheduler.run(parse_workflow_spec(raw))

    assert result["status"] == "completed"
    assert scheduler._states["fan"].items == 20
    # 槽与下游文本都按预算有界，不随展开项数线性膨胀
    root_slot = scheduler._states["root"].slots.get("result", "")
    assert len(root_slot) < 20 * 20000, "single-upstream collect slot was not compressed"
    root_task = scheduler._aggregate_task_text(scheduler._states["root"])
    assert len(root_task) < 20 * 20000
    assert "S" * 20000 not in _json.dumps(result)


@pytest.mark.asyncio
async def test_hundred_leaves_still_produce_a_readable_root_result(manager):
    """bounded 不等于丢结果：root_result_ref 仍指向完整聚合正文。"""
    manager.llm = StaticLLM("R" * 2000)
    leaves = [{"id": f"l{i}", "kind": "subagent", "task": f"task {i}"} for i in range(100)]
    raw = {
        "goal": "research",
        "nodes": leaves + [{"id": "root", "kind": "aggregate", "strategy": "collect"}],
        "edges": [{"from": f"l{i}", "to": "root", "reducer": "concat"} for i in range(100)],
        "terminal": ["root"],
    }
    scheduler = WorkflowScheduler(manager)
    result = await scheduler.run(parse_workflow_spec(raw))
    store = manager.workflow_store(scheduler.workflow_id)
    body = store.load(result["root_result_ref"])
    assert body is not None
    assert "R" * 2000 in body
