"""读取通道：ReadWorkflowResult + GetWorkflow(detail)（tasks 3.2、5.1；Q1）。

Q1 拍板：新增只读工具 ``ReadWorkflowResult(ref, offset, limit)`` 分页读回 artifact
正文；``GetWorkflow(detail)`` 只返回**节点级摘要列表**，不展开正文。

关键约束（Q1 的评估项）：只读工具**不进** ``SPAWN_TOOL_NAMES``（它不拉起新工作），
但必须在 ``agent/loop.py`` 的注册表里对父 agent 可见。
"""
import json

import pytest

from agent.config import AsterwyndConfig
from agent.llm import LLMResponse, Usage
from agent.run_config import AgentMode
from agent.subagent.manager import SPAWN_TOOL_NAMES, SubAgentManager
from agent.subagent.scheduler import WorkflowScheduler
from agent.subagent.workflow import parse_workflow_spec
from agent.tools.builtin.subagents import (
    GetWorkflowTool,
    ReadWorkflowResultTool,
)
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


SPEC = {
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


# --- 工具面元数据（Q1） -----------------------------------------------------


def test_read_workflow_result_metadata():
    assert ReadWorkflowResultTool.read_only is True
    assert ReadWorkflowResultTool.parallelizable is False
    # 只读工具不进 spawn 名单（Q1：它不拉起新工作）
    assert "ReadWorkflowResult" not in SPAWN_TOOL_NAMES


def test_read_workflow_result_is_registered_for_parent(tmp_path):
    manager = SubAgentManager(
        llm=StaticLLM(),
        config=AsterwyndConfig(),
        workspace_policy=WorkspacePolicy(workspace_root=tmp_path),
    )
    loop = manager._build_subagent_loop(AgentMode.BUILD, depth=manager.max_depth)
    names = {tool["function"]["name"] for tool in loop.tool_registry.get_all_schemas()}
    assert "ReadWorkflowResult" in names
    # 深度到限的子 agent 仍能读结果（只读，不 spawn）
    assert "GetWorkflow" in names


# --- ReadWorkflowResult 分页 -------------------------------------------------


@pytest.mark.asyncio
async def test_read_workflow_result_paginates_root_ref(manager):
    scheduler = WorkflowScheduler(manager)
    result = await scheduler.run(parse_workflow_spec(SPEC))
    ref = result["root_result_ref"]
    assert ref

    page = json.loads(
        await ReadWorkflowResultTool(manager).execute(ref=ref, offset=0, limit=4)
    )
    assert page["missing"] is False
    assert page["ref"] == ref
    assert len(page["content"]) <= 4

    full = json.loads(await ReadWorkflowResultTool(manager).execute(ref=ref))
    assert full["total_chars"] == len(full["content"]) or full["truncated"]


@pytest.mark.asyncio
async def test_read_workflow_result_reports_unknown_ref(manager):
    out = json.loads(
        await ReadWorkflowResultTool(manager).execute(
            ref="artifact://workflow/wf_nope/absent"
        )
    )
    assert out["missing"] is True
    assert out["content"] == ""


@pytest.mark.asyncio
async def test_read_workflow_result_rejects_malformed_ref(manager):
    out = json.loads(
        await ReadWorkflowResultTool(manager).execute(ref="../../etc/passwd")
    )
    assert out["missing"] is True
    assert "reason" in out


@pytest.mark.asyncio
async def test_read_workflow_result_rejects_dot_segment_escape(manager, tmp_path):
    """安全边界（review Issue 2）：模型可控的 ref 不能靠 ``..`` 跳到 subtree 之外。"""
    leak_dir = tmp_path / ".asterwynd" / "results"
    leak_dir.mkdir(parents=True)
    (leak_dir / "leak.txt").write_text("LEAKED-OTHER-CONTENT", encoding="utf-8")

    for bad_ref in ("artifact://workflow/../leak", "artifact://workflow/sub/../../leak"):
        out = json.loads(
            await ReadWorkflowResultTool(manager).execute(ref=bad_ref)
        )
        assert out["missing"] is True, bad_ref
        assert "LEAKED-OTHER-CONTENT" not in out["content"], bad_ref


# --- GetWorkflow(detail) -----------------------------------------------------


@pytest.mark.asyncio
async def test_get_workflow_default_detail_is_summary(manager):
    scheduler = WorkflowScheduler(manager)
    manager.register_workflow(scheduler)
    await scheduler.run(parse_workflow_spec(SPEC))
    out = json.loads(
        await GetWorkflowTool(manager).execute(workflow_id=scheduler.workflow_id)
    )
    assert out["detail"] == "summary"
    # bounded：节点级摘要，不展开正文
    assert all("summary" in node for node in out["nodes"])
    assert "result_ref" not in json.dumps(out["nodes"])


@pytest.mark.asyncio
async def test_get_workflow_detail_nodes_lists_refs(manager):
    """detail=nodes 返回节点级摘要 + 各自的 result_ref（不返回正文）。"""
    scheduler = WorkflowScheduler(manager)
    manager.register_workflow(scheduler)
    await scheduler.run(parse_workflow_spec(SPEC))
    out = json.loads(
        await GetWorkflowTool(manager).execute(
            workflow_id=scheduler.workflow_id, detail="nodes"
        )
    )
    assert out["detail"] == "nodes"
    node_a = next(node for node in out["nodes"] if node["id"] == "a")
    assert node_a["result_ref"]
    # 摘要仍然是 bounded 的（没有把正文塞进节点项）
    assert len(node_a["summary"]) <= 400


@pytest.mark.asyncio
async def test_get_workflow_detail_events_returns_ring_buffer(manager):
    scheduler = WorkflowScheduler(manager)
    manager.register_workflow(scheduler)
    await scheduler.run(parse_workflow_spec(SPEC))
    out = json.loads(
        await GetWorkflowTool(manager).execute(
            workflow_id=scheduler.workflow_id, detail="events"
        )
    )
    assert out["detail"] == "events"
    assert out["latest_events"]
    # ring buffer 只收终态迁移：节点终态带 node_id，workflow 终态带 status。
    node_events = [event for event in out["latest_events"] if event["type"] == "node_terminal"]
    assert node_events
    assert all("node_id" in event for event in node_events)
    assert any(event["type"] == "workflow_terminal" for event in out["latest_events"])


@pytest.mark.asyncio
async def test_get_workflow_rejects_unknown_detail(manager):
    scheduler = WorkflowScheduler(manager)
    manager.register_workflow(scheduler)
    await scheduler.run(parse_workflow_spec(SPEC))
    out = json.loads(
        await GetWorkflowTool(manager).execute(
            workflow_id=scheduler.workflow_id, detail="nope"
        )
    )
    assert out["status"] == "invalid_detail"
    assert "summary" in out["reason"]


@pytest.mark.asyncio
async def test_get_workflow_detail_nodes_is_not_the_full_result(manager):
    """detail=nodes 不得把 artifact 正文展开（否则 bounded envelope 白做）。"""
    manager.llm = StaticLLM("Z" * 3000)
    scheduler = WorkflowScheduler(manager)
    manager.register_workflow(scheduler)
    await scheduler.run(parse_workflow_spec(SPEC))
    out = json.loads(
        await GetWorkflowTool(manager).execute(
            workflow_id=scheduler.workflow_id, detail="nodes"
        )
    )
    assert "Z" * 3000 not in json.dumps(out)
