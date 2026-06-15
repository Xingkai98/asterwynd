import json

import pytest

from agent.tools.builtin.bash import BashTool
from agent.workspace_policy import WorkspacePolicy


@pytest.mark.asyncio
async def test_structured_output_contains_all_fields(tmp_path):
    tool = BashTool(policy=WorkspacePolicy(tmp_path))

    result = await tool.execute("echo hello")
    data = json.loads(result)

    assert "exit_code" in data
    assert "stdout" in data
    assert "stderr" in data
    assert "duration_ms" in data
    assert "timed_out" in data


@pytest.mark.asyncio
async def test_structured_output_values(tmp_path):
    tool = BashTool(policy=WorkspacePolicy(tmp_path))

    result = await tool.execute("echo hello")
    data = json.loads(result)

    assert data["exit_code"] == 0
    assert data["stdout"] == "hello"
    assert data["stderr"] == ""
    assert data["timed_out"] is False
    assert isinstance(data["duration_ms"], float)
    assert data["duration_ms"] > 0


@pytest.mark.asyncio
async def test_structured_output_exit_code_nonzero(tmp_path):
    tool = BashTool(policy=WorkspacePolicy(tmp_path))

    result = await tool.execute("exit 1")
    data = json.loads(result)

    assert data["exit_code"] == 1


@pytest.mark.asyncio
async def test_structured_output_stderr_separate(tmp_path):
    tool = BashTool(policy=WorkspacePolicy(tmp_path))

    result = await tool.execute("echo ok && echo err >&2")
    data = json.loads(result)

    assert data["stdout"] == "ok"
    assert data["stderr"] == "err"


@pytest.mark.asyncio
async def test_structured_output_on_timeout(tmp_path):
    tool = BashTool(policy=WorkspacePolicy(tmp_path))

    result = await tool.execute("sleep 60", timeout=0.1)
    data = json.loads(result)

    assert data["timed_out"] is True
    assert data["exit_code"] == -1
    assert data["duration_ms"] > 0


@pytest.mark.asyncio
async def test_structured_output_valid_json_always(tmp_path):
    tool = BashTool(policy=WorkspacePolicy(tmp_path))

    result = await tool.execute("rm -rf /")

    assert "Command denied" in result
