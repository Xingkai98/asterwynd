import subprocess

import pytest

from agent.tools.builtin.bash import BashTool
from agent.workspace_policy import WorkspacePolicy


@pytest.mark.asyncio
async def test_bash_tool_runs_in_workspace(tmp_path):
    (tmp_path / "marker.txt").write_text("workspace-marker\n")
    tool = BashTool(policy=WorkspacePolicy(tmp_path))

    result = await tool.execute("cat marker.txt")

    assert result == "workspace-marker"


@pytest.mark.asyncio
async def test_bash_tool_applies_command_policy(tmp_path):
    tool = BashTool(policy=WorkspacePolicy(tmp_path))

    result = await tool.execute("rm -rf /")

    assert "Command denied" in result
