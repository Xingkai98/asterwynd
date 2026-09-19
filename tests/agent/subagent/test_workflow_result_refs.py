"""成功路径的完整结果落盘 + run record 的 refs 字段（tasks 1.1/1.2）。

grill 决策 2 的核心回归：正常完成的 run **今天不写 checkpoint**（``_write_checkpoint``
只在异常/取消分支），所以「完整结果落盘」是**新增写点**——必须在 ``_complete_run``
的成功分支显式触发，否则 spec delta 的 Scenario「完整结果落盘、内存只持摘要」在正常
路径下直接不成立。

grill 决策 3：``artifact_refs`` 本 change 定义填充时机（此前全仓零生产者）。
Q6：``run.summary`` 保留全文，bounded summary 是**落盘的裁剪件**（``summary_ref``），
不是把 ``run.summary`` 改短。
"""
import json

import pytest

from agent.config import AsterwyndConfig
from agent.llm import LLMResponse, Usage
from agent.run_config import AgentMode
from agent.subagent.manager import SubAgentManager
from agent.subagent.workflow_store import WorkflowStore
from agent.workspace_policy import WorkspacePolicy


class StaticLLM:
    def __init__(self, content="worker result"):
        self.content = content

    async def chat(self, messages, tools=None, model="gpt-4"):
        return LLMResponse(content=self.content, stop_reason="end_turn", usage=Usage(5, 5))


@pytest.fixture
def manager(tmp_path) -> SubAgentManager:
    return SubAgentManager(
        llm=StaticLLM(),
        config=AsterwyndConfig(),
        parent_mode=AgentMode.BUILD,
        workspace_policy=WorkspacePolicy(workspace_root=tmp_path),
    )


def _workflow_store(tmp_path, workflow_id) -> WorkflowStore:
    return WorkflowStore.for_workspace(tmp_path, workflow_id)


# --- 1.2 refs 字段 ----------------------------------------------------------


def test_to_result_dict_exposes_refs_without_breaking_existing_keys():
    from agent.subagent.manager import SubagentRunRecord

    payload = SubagentRunRecord(run_id="r1", task="t", status="completed", summary="s").to_result_dict()
    # 既有键一个不少（C1/C2 断言依赖这些键）
    for key in ("run_id", "status", "summary", "reason", "max_tokens", "max_time_s", "usage", "artifacts"):
        assert key in payload
    assert payload["summary"] == "s"
    # D7/Q6 的 parent bounded 表示是独立字段：短文本与全文一致（no-op）
    assert payload["bounded_summary"] == "s"
    # 新增 refs：非 workflow run 无落盘件，保持 None/[]
    assert payload["result_ref"] is None
    assert payload["summary_ref"] is None
    assert payload["transcript_ref"] is None
    assert payload["artifact_refs"] == []


# --- 1.1/1.2 成功路径落盘 ---------------------------------------------------


@pytest.mark.asyncio
async def test_successful_workflow_run_writes_result_artifacts(tmp_path):
    """正常完成（无 checkpoint）也必须落盘完整结果 + transcript + bounded summary。"""
    manager = SubAgentManager(
        llm=StaticLLM("the full research notes"),
        config=AsterwyndConfig(),
        parent_mode=AgentMode.BUILD,
        workspace_policy=WorkspacePolicy(workspace_root=tmp_path),
    )
    from agent.subagent.scheduler import WorkflowScheduler
    from agent.subagent.workflow import parse_workflow_spec

    scheduler = WorkflowScheduler(manager)
    spec = parse_workflow_spec(
        {
            "goal": "g",
            "nodes": [{"id": "a", "kind": "subagent", "task": "do it"}],
            "edges": [],
        }
    )
    await scheduler.run(spec)

    store = _workflow_store(tmp_path, scheduler.workflow_id)
    # 完整结果正文落盘，内容与 run.summary 一致（Q6：summary 保留全文）
    events = store.read_events()
    assert [event["type"] for event in events if event["type"] == "node_terminal"]

    node = scheduler._states["a"]
    run = manager.find_run(node.subagent_id, node.run_id)
    assert run is not None
    assert run.result_ref is not None
    assert store.load(run.result_ref) == "the full research notes"
    assert run.summary == "the full research notes"

    # transcript 落盘（完整 messages 序列）
    assert run.transcript_ref is not None
    transcript = json.loads(store.load(run.transcript_ref))
    assert any(msg["role"] == "user" for msg in transcript)

    # bounded summary 落盘件（裁剪版，单独文件）
    assert run.summary_ref is not None
    assert store.load(run.summary_ref) is not None

    # artifact_refs 有真实生产者（不再恒为 []）
    assert run.artifact_refs
    assert run.result_ref in run.artifact_refs
    assert run.transcript_ref in run.artifact_refs

    # envelope 出口带 refs（to_result_dict 是唯一出口）
    envelope = manager._format_run_envelope(node.subagent_id, run)
    assert envelope["result_ref"] == run.result_ref
    assert envelope["artifact_refs"] == run.artifact_refs


@pytest.mark.asyncio
async def test_bounded_summary_is_truncated_but_run_summary_is_not(tmp_path):
    """Q6：出口/落盘是 bounded，``run.summary`` 保留全文。"""
    long_text = "x" * 5000
    manager = SubAgentManager(
        llm=StaticLLM(long_text),
        config=AsterwyndConfig(),
        parent_mode=AgentMode.BUILD,
        workspace_policy=WorkspacePolicy(workspace_root=tmp_path),
    )
    from agent.subagent.scheduler import WorkflowScheduler
    from agent.subagent.workflow import parse_workflow_spec

    scheduler = WorkflowScheduler(manager)
    spec = parse_workflow_spec(
        {
            "goal": "g",
            "nodes": [{"id": "a", "kind": "subagent", "task": "do it"}],
            "edges": [],
        }
    )
    await scheduler.run(spec)
    node = scheduler._states["a"]
    run = manager.find_run(node.subagent_id, node.run_id)
    store = _workflow_store(tmp_path, scheduler.workflow_id)
    assert run.summary == long_text
    assert store.load(run.result_ref) == long_text
    assert len(store.load(run.summary_ref)) < len(long_text)


@pytest.mark.asyncio
async def test_non_workflow_run_writes_no_refs(tmp_path):
    """没有 workflow 身份的 run 没有 workflow store，refs 保持空（C1 入口不回归）。"""
    manager = SubAgentManager(
        llm=StaticLLM("plain"),
        config=AsterwyndConfig(),
        parent_mode=AgentMode.BUILD,
        workspace_policy=WorkspacePolicy(workspace_root=tmp_path),
    )
    created = manager.create_subagent(name="w")
    result = await manager.run_subagent(subagent_id=created["subagent_id"], task="t", wait=True)
    assert result["status"] == "completed"
    assert result["summary"] == "plain"
    assert result["result_ref"] is None
    assert result["artifact_refs"] == []
