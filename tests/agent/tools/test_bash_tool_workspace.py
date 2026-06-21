import json

import pytest

from agent.tools.builtin.bash import BashTool
from agent.workspace_policy import WorkspacePolicy


@pytest.mark.asyncio
async def test_bash_tool_runs_in_workspace(tmp_path):
    (tmp_path / "marker.txt").write_text("workspace-marker\n")
    tool = BashTool(policy=WorkspacePolicy(tmp_path))

    result = await tool.execute("cat marker.txt")

    data = json.loads(result)
    assert data["exit_code"] == 0
    assert data["stdout"] == "workspace-marker"
    assert not data["timed_out"]
    assert data["duration_ms"] > 0


@pytest.mark.asyncio
async def test_bash_tool_applies_command_policy(tmp_path):
    tool = BashTool(policy=WorkspacePolicy(tmp_path))

    result = await tool.execute("rm -rf /")

    assert "Command denied" in result


@pytest.mark.asyncio
async def test_bash_tool_rejects_arbitrary_python_execution(tmp_path):
    tool = BashTool(policy=WorkspacePolicy(tmp_path))

    result = await tool.execute("python -c \"print('arbitrary')\"")

    assert "Command denied" in result


@pytest.mark.asyncio
async def test_bash_tool_rejects_sensitive_copy(tmp_path):
    tool = BashTool(policy=WorkspacePolicy(tmp_path))

    result = await tool.execute("cp /etc/passwd ./passwd.copy")

    assert "Command denied" in result


@pytest.mark.asyncio
async def test_bash_tool_reports_timeout(tmp_path):
    tool = BashTool(policy=WorkspacePolicy(tmp_path))

    result = await tool.execute("sleep 60", timeout=0.1)

    data = json.loads(result)
    assert data["timed_out"]
    assert data["exit_code"] == -1


@pytest.mark.asyncio
async def test_bash_tool_reports_exit_code(tmp_path):
    tool = BashTool(policy=WorkspacePolicy(tmp_path))

    result = await tool.execute("exit 42")

    data = json.loads(result)
    assert data["exit_code"] == 42
