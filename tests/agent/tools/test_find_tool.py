import pytest

from agent.tools.builtin.find import FindTool
from agent.workspace_policy import WorkspacePolicy


@pytest.fixture
def nested_repo(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("")
    (tmp_path / "src" / "utils.py").write_text("")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_main.py").write_text("")
    (tmp_path / "README.md").write_text("")
    (tmp_path / ".git").mkdir()
    return tmp_path


@pytest.mark.asyncio
async def test_finds_files_by_extension(nested_repo):
    tool = FindTool(policy=WorkspacePolicy(nested_repo))

    result = await tool.execute("*.py")

    lines = result.split("\n")
    assert "src/main.py" in lines
    assert "src/utils.py" in lines
    assert "tests/test_main.py" in lines
    assert "README.md" not in lines


@pytest.mark.asyncio
async def test_finds_files_by_pattern_with_path(nested_repo):
    tool = FindTool(policy=WorkspacePolicy(nested_repo))

    result = await tool.execute("*.py", path="src")

    lines = result.split("\n")
    assert "main.py" in lines
    assert "utils.py" in lines
    assert "test_main.py" not in lines


@pytest.mark.asyncio
async def test_no_matches(nested_repo):
    tool = FindTool(policy=WorkspacePolicy(nested_repo))

    result = await tool.execute("*.rs")

    assert "no files matching" in result


@pytest.mark.asyncio
async def test_ignores_sensitive_directories(nested_repo):
    (nested_repo / "node_modules").mkdir()
    (nested_repo / "node_modules" / "package.json").write_text("")
    tool = FindTool(policy=WorkspacePolicy(nested_repo))

    result = await tool.execute("*")

    assert "node_modules" not in result


@pytest.mark.asyncio
async def test_rejects_path_outside_workspace(tmp_path):
    tool = FindTool(policy=WorkspacePolicy(tmp_path))

    result = await tool.execute("*", path="/etc")

    assert "Error" in result


@pytest.mark.asyncio
async def test_truncates_at_max_entries(nested_repo, monkeypatch):
    monkeypatch.setattr("agent.tools.builtin.find.MAX_ENTRIES", 2)
    tool = FindTool(policy=WorkspacePolicy(nested_repo))

    result = await tool.execute("*", max_entries=2)

    assert "truncated" in result.lower()


@pytest.mark.asyncio
async def test_custom_ignore_patterns_env(nested_repo, monkeypatch):
    monkeypatch.setenv("MYAGENT_IGNORE_PATTERNS", "src")
    tool = FindTool(policy=WorkspacePolicy(nested_repo))

    result = await tool.execute("*")

    assert "src/main.py" not in result
    assert "tests/test_main.py" in result
