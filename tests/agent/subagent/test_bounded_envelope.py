"""父 agent envelope 必须**真的** bounded（D3；review Issue 4）。

D3 的措辞是「父 agent **永远** bounded envelope」，但原实现的 envelope 有三处随
内容/节点数线性膨胀：

1. ``payload["bus"] = bus.snapshot_payload()`` 把**非权威**的 bus 全量消息塞进权威
   envelope（与 D4 自相矛盾），实测 100 条 1600 字消息 → envelope 237 KB；
2. ``nodes`` 是全量列表，且 ``reason``/``error`` 等字段无裁剪；
3. ``foreach`` 的 ``subagent_ids``/``run_ids`` 随展开项数线性增长。

修复口径（review 建议）：权威 ``_envelope()`` 不再内联 bus；父 agent 面向的
``parent_envelope()`` 做节点级投影——每节点只留 bounded 摘要、省略无界数组、并对
节点条数设硬上限（``nodes_omitted`` 报告被省略的数量）。
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
from agent.tools.builtin.subagents import (
    DeclareWorkflowTool,
    GetWorkflowTool,
    RunWorkflowTool,
    StartWorkflowTool,
)
from agent.workspace_policy import WorkspacePolicy


class StaticLLM:
    def __init__(self, content="worker result"):
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


def _fanout(leaves: int) -> dict:
    return {
        "goal": "research",
        "nodes": [{"id": f"l{i}", "kind": "subagent", "task": f"task {i}"} for i in range(leaves)]
        + [{"id": "root", "kind": "aggregate", "strategy": "collect"}],
        "edges": [{"from": f"l{i}", "to": "root", "reducer": "concat"} for i in range(leaves)],
        "terminal": ["root"],
    }


def _filled_bus(messages: int = 100, size: int = 1600) -> MessageBus:
    bus = MessageBus()
    for i in range(messages):
        bus.publish(sender=f"w{i}", topic="finding", summary="M" * size)
    return bus


# --- 权威 envelope 不内联非权威 bus（D4） -----------------------------------


@pytest.mark.asyncio
async def test_authoritative_envelope_does_not_inline_bus(manager):
    """D4：bus 是非权威通道，不能出现在**父 agent 面向**的 envelope 里。

    ``run()`` 自己的返回值保留 ``bus``（C2 断言依赖，grill 决策 4 明确不替换）；
    父投影（工具返回、``GetWorkflow``）必须把它摘掉。
    """
    scheduler = WorkflowScheduler(manager, bus=_filled_bus())
    await scheduler.run(parse_workflow_spec(_fanout(3)))

    parent = scheduler.parent_envelope()
    assert "bus" not in parent
    assert "M" * 1600 not in json.dumps(parent)
    # 父投影仍带全部权威信息（计数 + 事件 + ref），只是不含非权威 blob
    assert parent["status"] == "completed"
    assert parent["latest_events"]
    assert parent["total"] == 4
    assert parent["root_result_ref"]


# --- 父面向投影：节点级 + 硬上限 --------------------------------------------


@pytest.mark.asyncio
async def test_parent_envelope_bounds_nodes_and_drops_unbounded_arrays(manager):
    """父投影每节点只留 bounded 摘要，不展开 subagent_ids/run_ids 等无界数组。"""
    manager.llm = StaticLLM("ok")
    scheduler = WorkflowScheduler(manager, bus=_filled_bus())
    await scheduler.run(parse_workflow_spec(_fanout(3)))
    payload = scheduler.parent_envelope()

    assert "bus" not in payload
    for node in payload["nodes"]:
        assert len(node["summary"]) <= 200
        assert "subagent_ids" not in node
        assert "run_ids" not in node
        assert "slots" not in node
    # 被省略的节点数显式报告（不静默截断）
    assert payload["nodes_omitted"] == 0
    assert payload["nodes_total"] == 4


@pytest.mark.asyncio
async def test_parent_envelope_hard_caps_node_count(manager):
    """节点数超上限时按上限截断并报告 omitted（对用户配置的大图也成立）。"""
    manager.llm = StaticLLM("ok")
    spec = _fanout(300)
    spec["max_nodes"] = 400
    spec["max_runs"] = 400
    scheduler = WorkflowScheduler(manager)
    await scheduler.run(parse_workflow_spec(spec))

    payload = scheduler.parent_envelope()
    assert payload["nodes_total"] > 200
    assert len(payload["nodes"]) == 200
    assert payload["nodes_omitted"] == payload["nodes_total"] - 200


@pytest.mark.asyncio
async def test_parent_envelope_truncates_unbounded_node_fields(manager):
    """``reason``/``error`` 也是无界字段（异常串可能很长），父投影里一并裁剪。"""
    scheduler = WorkflowScheduler(manager)
    scheduler.spec = parse_workflow_spec(_fanout(1))
    state = scheduler._states["l0"]
    state.status = "failed"
    state.reason = "E" * 5000
    state.error = "X" * 5000

    payload = scheduler.parent_envelope()
    node = next(node for node in payload["nodes"] if node["id"] == "l0")
    assert len(node["reason"]) <= 200
    assert len(node["error"]) <= 200


# --- 工具出口（模型可控面）真的 bounded -------------------------------------


@pytest.mark.asyncio
async def test_start_workflow_tool_returns_bounded_envelope(manager):
    """review 实测场景：100 leaves + bus 满载，工具返回必须有上界。"""
    bus = _filled_bus()
    declared = json.loads(await DeclareWorkflowTool(manager).execute(spec=_fanout(100)))
    scheduler = manager.get_workflow(declared["workflow_id"])
    scheduler.bus = bus

    started = json.loads(
        await StartWorkflowTool(manager).execute(workflow_id=declared["workflow_id"])
    )
    assert started["status"] == "completed"
    # 100 个 leaf 自动插 10 个 llm aggregate → completed 是 run 口径（100+10）
    assert started["completed"] == 110
    assert started["nodes_omitted"] == 0  # 111 个节点 < 上限 200
    assert "bus" not in started
    assert len(json.dumps(started)) < 60_000, len(json.dumps(started))
    assert "M" * 1600 not in json.dumps(started)

    got = json.loads(
        await GetWorkflowTool(manager).execute(workflow_id=declared["workflow_id"])
    )
    assert len(json.dumps(got)) < 60_000, len(json.dumps(got))


@pytest.mark.asyncio
async def test_get_workflow_detail_nodes_stays_bounded(manager):
    """detail='nodes' 合并 result_ref 后仍然 bounded。"""
    declared = json.loads(await DeclareWorkflowTool(manager).execute(spec=_fanout(100)))
    scheduler = manager.get_workflow(declared["workflow_id"])
    scheduler.bus = _filled_bus()
    await StartWorkflowTool(manager).execute(workflow_id=declared["workflow_id"])

    out = json.loads(
        await GetWorkflowTool(manager).execute(
            workflow_id=declared["workflow_id"], detail="nodes"
        )
    )
    assert len(json.dumps(out)) < 80_000, len(json.dumps(out))
    assert out["detail"] == "nodes"
    node = next(node for node in out["nodes"] if node["id"] == "l0")
    assert node["result_ref"]


@pytest.mark.asyncio
async def test_run_workflow_tool_returns_bounded_envelope(manager):
    """RunWorkflow 同属父 agent 工具出口，口径与 StartWorkflow 一致。"""
    out = json.loads(
        await RunWorkflowTool(manager).execute(spec=_fanout(100))
    )
    assert out["status"] == "completed"
    assert len(json.dumps(out)) < 60_000, len(json.dumps(out))
    assert out["nodes_omitted"] == 0  # 111 个节点 < 上限 200


@pytest.mark.asyncio
async def test_bus_is_still_reachable_through_its_own_channel(manager):
    """去掉内联不等于抹掉能力：bus 仍可经 RunPattern/ReadBus 读取（非权威通道）。"""
    from agent.subagent.patterns import run_pattern

    result = await run_pattern(
        manager, pattern="orchestrator-worker", task="t", params={"workers": 1}
    )
    assert "messages" in result["bus"]
