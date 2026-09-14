"""workflow 运行期的成本归因四维（change ``workflow-budget-attribution``，task 2.2/2.3）。

覆盖 D3 与 grill 决策 3/4/5/6 及用户确认 Q7/Q8/Q12/Q13：

- 归因键从 ``session_id → SubagentSessionRecord`` **一次查表**得到（决策 4）；
- ``edge`` 在**调度器派发点**算出（决策 6），规则见 Q8（排序拼接 / foreach 共享 /
  入口哨兵 / route 控制边优先）；
- ``graph_distance`` 是**独立 contextvar + run 字段**（Q7/Q13），不复用 ``spawn_depth``；
- 记账在 loop 层、cost 是 cache-aware 四档（Q6 方案 B / Q12）。
"""
import dataclasses

import pytest

from agent.config import AsterwyndConfig
from agent.cost_tracker import CostLedger
from agent.llm import LLMResponse, Usage
from agent.run_config import AgentMode
from agent.subagent.manager import SubAgentManager
from agent.subagent.scheduler import WorkflowScheduler
from agent.subagent.workflow import parse_workflow_spec
from agent.workspace_policy import WorkspacePolicy


class CostingLLM:
    """每次调用产生可预测的 cache-aware usage。"""

    def __init__(self, input_tokens=1000, output_tokens=100):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.model = "gpt-4o-mini"

    async def chat(self, messages, tools=None, model="gpt-4"):
        return LLMResponse(
            content="ok",
            stop_reason="end_turn",
            usage=Usage(
                input_tokens=self.input_tokens,
                output_tokens=self.output_tokens,
                cache_read_input_tokens=0,
                cache_creation_input_tokens=0,
            ),
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


# --- edge 规则（Q8） --------------------------------------------------------


@pytest.mark.asyncio
async def test_edge_multi_incoming_sorted_join(manager):
    """多数据入边：按 source id **排序**拼接（两种声明序得到同一键）。

    join 用 ``strategy="llm"``（``collect`` 不产生 run，也就没有可归因的成本）。
    """
    spec = {
        "goal": "g",
        "nodes": [
            {"id": "b", "kind": "subagent", "task": "tb"},
            {"id": "a", "kind": "subagent", "task": "ta"},
            {"id": "join", "kind": "aggregate", "strategy": "llm"},
        ],
        "edges": [
            {"from": "b", "to": "join", "reducer": "concat"},
            {"from": "a", "to": "join", "reducer": "concat"},
        ],
        "terminal": ["join"],
    }
    await WorkflowScheduler(manager).run(parse_workflow_spec(spec))
    by_edge = manager.cost_ledger.bill()["by_edge"]
    assert "a|b->join" in by_edge
    # 排序保证不会出现 b|a->join 这个等价但不同的桶（声明序是 b→a）
    assert "b|a->join" not in by_edge


@pytest.mark.asyncio
async def test_edge_entry_node_uses_root_sentinel(manager):
    """入口节点（无数据上游）记 ``"<root>->node"``（Q8 场景 C）。"""
    spec = {
        "goal": "g",
        "nodes": [{"id": "l0", "kind": "subagent", "task": "t"}],
        "edges": [],
    }
    await WorkflowScheduler(manager).run(parse_workflow_spec(spec))
    assert "<root>->l0" in manager.cost_ledger.bill()["by_edge"]


@pytest.mark.asyncio
async def test_edge_foreach_items_share_container_edge(manager):
    """foreach 展开项共享容器节点的数据入边 ``planner->fan``（Q8 场景 B）。"""
    import json

    class PlannerLLM:
        def __init__(self):
            self.model = "gpt-4o-mini"

        async def chat(self, messages, tools=None, model="gpt-4"):
            first = messages[-1].content.splitlines()[0].strip().lower()
            content = '{"items": ["one", "two"]}' if first.startswith("plan") else "did it"
            return LLMResponse(
                content=content, stop_reason="end_turn", usage=Usage(10, 10)
            )

    manager.llm = PlannerLLM()
    spec = {
        "goal": "g",
        "nodes": [
            {"id": "planner", "kind": "subagent", "task": "plan", "outputs": ["plan"]},
            {
                "id": "fan",
                "kind": "foreach",
                "task": "work {item}",
                "source": "planner",
                "source_field": "items",
            },
        ],
        "edges": [{"from": "planner", "to": "fan"}],
        "terminal": ["fan"],
    }
    result = await WorkflowScheduler(manager).run(parse_workflow_spec(spec))
    assert result["status"] == "completed"
    by_edge = manager.cost_ledger.bill()["by_edge"]
    # planner 是入口（无数据入边）→ 记哨兵边
    assert "<root>->planner" in by_edge
    # 两个展开项共享容器节点的数据入边；planner 的调用记在它自己的入口边上
    assert by_edge["planner->fan"]["tokens"] == 40  # 2 次调用 × (10 in + 10 out)


# --- by_node / by_depth（D3/Q7/Q13） ---------------------------------------


@pytest.mark.asyncio
async def test_by_node_buckets_per_workflow_node(manager):
    """每个节点一个 by_node 桶，可定位「最贵节点」。"""
    manager.llm = CostingLLM(input_tokens=1000, output_tokens=0)
    spec = {
        "goal": "g",
        "nodes": [
            {"id": "cheap", "kind": "subagent", "task": "t1"},
            {"id": "pricey", "kind": "subagent", "task": "t2"},
        ],
        "edges": [],
    }
    # pricey 的 usage 更大：用按任务文本区分的 LLM。
    class SplitLLM:
        def __init__(self):
            self.model = "gpt-4o-mini"

        async def chat(self, messages, tools=None, model="gpt-4"):
            tokens = 5000 if "t2" in messages[-1].content else 100
            return LLMResponse(
                content="ok", stop_reason="end_turn", usage=Usage(tokens, 0)
            )

    manager.llm = SplitLLM()
    await WorkflowScheduler(manager).run(parse_workflow_spec(spec))
    by_node = manager.cost_ledger.bill()["by_node"]
    assert set(by_node.keys()) == {"cheap", "pricey"}
    priciest = max(by_node, key=lambda key: by_node[key]["tokens"])
    assert priciest == "pricey"


@pytest.mark.asyncio
async def test_by_depth_uses_graph_distance_not_spawn_depth(manager):
    """Q7/Q13：``by_depth`` 分桶是图距（leaf→shard→…），不是恒定的 spawn_depth。

    链 ``l0 → l1 → l2``：图距 0/1/2 三个桶；而 spawn_depth 在 workflow 内恒定，
    只会给一个桶（Confirmed Decision 5）。
    """
    spec = {
        "goal": "g",
        "nodes": [
            {"id": "l0", "kind": "subagent", "task": "t0"},
            {"id": "l1", "kind": "subagent", "task": "t1"},
            {"id": "l2", "kind": "subagent", "task": "t2"},
        ],
        "edges": [
            {"from": "l0", "to": "l1"},
            {"from": "l1", "to": "l2"},
        ],
        "terminal": ["l2"],
    }
    await WorkflowScheduler(manager).run(parse_workflow_spec(spec))
    by_depth = manager.cost_ledger.bill()["by_depth"]
    # 三个不同图距桶（不是单桶）
    assert set(by_depth.keys()) == {"0", "1", "2"}
    for bucket in by_depth.values():
        assert bucket["tokens"] > 0


@pytest.mark.asyncio
async def test_graph_distance_does_not_affect_spawn_depth_field(manager):
    """Q7：图距**不得**写进 ``depth``（否则会改 ``max_depth`` 深度闸行为）。"""
    spec = {
        "goal": "g",
        "nodes": [
            {"id": "l0", "kind": "subagent", "task": "t0"},
            {"id": "l1", "kind": "subagent", "task": "t1"},
            {"id": "l2", "kind": "subagent", "task": "t2"},
        ],
        "edges": [
            {"from": "l0", "to": "l1"},
            {"from": "l1", "to": "l2"},
        ],
        "terminal": ["l2"],
    }
    await WorkflowScheduler(manager).run(parse_workflow_spec(spec))
    depths = set()
    graph_distances = set()
    for session in manager._sessions.values():
        for run in session.runs:
            depths.add(run.depth)
            graph_distances.add(run.graph_distance)
    assert len(depths) == 1, "spawn depth must stay uniform inside a workflow"
    assert graph_distances == {0, 1, 2}, "graph distance must vary by node"


# --- route 控制边（Q8 场景 D） ---------------------------------------------


@pytest.mark.asyncio
async def test_edge_route_control_prefers_route_source(manager):
    """route 控制边触发的下游记 ``route->target``（控制激活优先）。"""
    spec = {
        "goal": "g",
        "nodes": [
            {"id": "producer", "kind": "subagent", "task": "produce"},
            {
                "id": "gate",
                "kind": "route",
                "cases": [{"when": "APPROVED", "to": "done"}],
                "default": "producer",
            },
            {"id": "done", "kind": "subagent", "task": "finish"},
        ],
        "edges": [
            {"from": "producer", "to": "gate"},
            {"from": "gate", "to": "done"},
            {"from": "gate", "to": "producer"},
        ],
        "entry": ["producer"],
        "terminal": ["done"],
    }

    class ApprovingLLM:
        def __init__(self):
            self.model = "gpt-4o-mini"

        async def chat(self, messages, tools=None, model="gpt-4"):
            first = messages[-1].content.splitlines()[0].strip().lower()
            content = "APPROVED ship it" if first.startswith("produce") else "done"
            return LLMResponse(content=content, stop_reason="end_turn", usage=Usage(10, 10))

    manager.llm = ApprovingLLM()
    result = await WorkflowScheduler(manager).run(parse_workflow_spec(spec))
    assert result["status"] == "completed"
    by_edge = manager.cost_ledger.bill()["by_edge"]
    # done 只被 route 控制边激活 → 记 gate->done（它的数据入边为空）
    assert "gate->done" in by_edge


# --- 兼容：根 loop 不记 workflow 预算 --------------------------------------


@pytest.mark.asyncio
async def test_root_loop_does_not_record_workflow_budget(manager):
    """根 loop（无 workflow 身份）不累加 workflow 预算，也不写归因键。"""
    from agent.hooks.manager import HookManager
    from agent.llm import LLMResponse as _Resp
    from agent.message import Message
    from agent.tools.registry import ToolRegistry

    from agent.loop import AgentLoop

    class OneShot:
        model = "gpt-4o-mini"

        async def chat(self, messages, tools=None, model="gpt-4"):
            return _Resp(content="hi", stop_reason="end_turn", usage=Usage(100, 50))

    loop = AgentLoop(
        llm=OneShot(),
        tool_registry=ToolRegistry(),
        hooks=HookManager(),
        subagent_manager=manager,
        cost_ledger=manager.cost_ledger,
    )
    await loop.run([Message(role="user", content="hi")])
    bill = manager.cost_ledger.bill()
    assert bill["by_workflow"] == {}  # 根 loop 无归因键
    assert bill["by_session"]  # 三维账单照常记账
