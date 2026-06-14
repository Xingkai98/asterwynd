import pytest

from agent.tools.builtin.write import WriteTool
from agent.workspace_policy import WorkspacePolicy


@pytest.mark.asyncio
async def test_write_tool_uses_workspace_policy(tmp_path):
    tool = WriteTool(policy=WorkspacePolicy(tmp_path))

    result = await tool.execute(".env", "SECRET=1")

    assert "Write denied" in result
    assert not (tmp_path / ".env").exists()

