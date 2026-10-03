"""泛化后的回读入口（change ``tool-result-lifecycle``，D5）。

``ReadWorkflowResult`` 按 ref 前缀分派：workflow ref → workflow store；agent ref →
agent artifact store。工具名/schema 不变（不新增工具）。
"""
import json
from pathlib import Path

import pytest

from agent.artifact_store import AGENT_REF_PREFIX, AgentArtifactStore, ArtifactResolver
from agent.subagent.manager import SubAgentManager
from agent.subagent.workflow_store import WorkflowStore


def _resolver(tmp_path, manager):
    return ArtifactResolver(
        tmp_path, workflow_store=lambda wid: manager.workflow_store(wid)
    )


def test_resolver_routes_workflow_ref(tmp_path):
    store = WorkflowStore.for_workspace(tmp_path, "wf_1")
    ref = store.save_result("root", "workflow body")
    manager = SubAgentManager(workspace_policy=_policy(tmp_path))
    page = _resolver(tmp_path, manager).read(ref)
    assert page["missing"] is False
    assert page["content"] == "workflow body"


def test_resolver_routes_agent_ref(tmp_path):
    store = AgentArtifactStore.for_workspace(tmp_path, "s-abc")
    ref = store.save_result("result-1", "agent body")
    manager = SubAgentManager(workspace_policy=_policy(tmp_path))
    page = _resolver(tmp_path, manager).read(ref)
    assert page["missing"] is False
    assert page["content"] == "agent body"


def test_resolver_missing_agent_ref_is_self_describing(tmp_path):
    manager = SubAgentManager(workspace_policy=_policy(tmp_path))
    page = _resolver(tmp_path, manager).read(f"{AGENT_REF_PREFIX}s-abc/absent")
    assert page["missing"] is True
    assert page["content"] == ""


def test_resolver_rejects_malformed_ref(tmp_path):
    manager = SubAgentManager(workspace_policy=_policy(tmp_path))
    page = _resolver(tmp_path, manager).read("not-a-ref")
    assert page["missing"] is True
    assert page["reason"]


@pytest.mark.asyncio
async def test_read_workflow_result_tool_reads_agent_ref(tmp_path):
    from agent.tools.builtin.subagents import ReadWorkflowResultTool
    from agent.workspace_policy import WorkspacePolicy

    store = AgentArtifactStore.for_workspace(tmp_path, "s-abc")
    ref = store.save_result("result-1", "spilled body verbatim")
    manager = SubAgentManager(workspace_policy=_policy(tmp_path))
    tool = ReadWorkflowResultTool(manager)
    raw = await tool.execute(ref=ref)
    page = json.loads(raw)
    assert page["missing"] is False
    assert page["content"] == "spilled body verbatim"
    assert page["total_chars"] == len("spilled body verbatim")


def _policy(tmp_path):
    from agent.workspace_policy import WorkspacePolicy

    return WorkspacePolicy(workspace_root=Path(tmp_path))
