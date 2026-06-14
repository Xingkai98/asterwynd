import subprocess

import pytest

from agent.tools.builtin.inspect_git_diff import InspectGitDiffTool
from agent.workspace_policy import WorkspacePolicy


@pytest.fixture
def git_repo(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    (tmp_path / "app.py").write_text("old\n")
    subprocess.run(["git", "add", "app.py"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, check=True, capture_output=True)
    return tmp_path


@pytest.mark.asyncio
async def test_inspect_git_diff_shows_file_diff(git_repo):
    (git_repo / "app.py").write_text("new\n")
    tool = InspectGitDiffTool(policy=WorkspacePolicy(git_repo))

    result = await tool.execute(path="app.py")

    assert "Diff for app.py" in result
    assert "-old" in result
    assert "+new" in result


@pytest.mark.asyncio
async def test_inspect_git_diff_rejects_outside_path(git_repo, tmp_path):
    tool = InspectGitDiffTool(policy=WorkspacePolicy(git_repo))

    result = await tool.execute(path=str(tmp_path / ".." / "outside.py"))

    assert "outside workspace" in result


@pytest.mark.asyncio
async def test_inspect_git_diff_lists_untracked(git_repo):
    (git_repo / "new.py").write_text("print('new')\n")
    tool = InspectGitDiffTool(policy=WorkspacePolicy(git_repo))

    result = await tool.execute(include_untracked=True)

    assert "Untracked files" in result
    assert "new.py" in result

