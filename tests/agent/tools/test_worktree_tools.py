"""EnterWorktree / ExitWorktree 工具测试（add-worktree-tool change）。

覆盖：参数校验、错误路径、keep 语义、分支名派生（分支名 = name）、
目录约定（.asterwynd/worktrees/<name>）、policy root 重绑定、
文件工具路径边界、AgentLoop 层 registry 调用、失败回滚。
"""
import json
import subprocess

import pytest

from agent.run_config import ModePolicy
from agent.tools.base import ToolCall, ToolResult
from agent.tools.builtin.read import ReadTool
from agent.tools.builtin.worktree import EnterWorktreeTool, ExitWorktreeTool
from agent.tools.registry import ToolRegistry
from agent.tool_permissions import ToolCapability, ToolRiskLevel
from agent.workspace_policy import WorkspacePolicy

WT_DIR = ".asterwynd/worktrees"


def _run_git(repo, *args, check=True):
    return subprocess.run(
        ["git", *args], cwd=repo, check=check, capture_output=True, text=True
    )


@pytest.fixture
def git_repo(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=tmp_path, check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"], cwd=tmp_path, check=True
    )
    (tmp_path / "app.py").write_text("old\n")
    _run_git(tmp_path, "add", "app.py")
    _run_git(tmp_path, "commit", "-m", "init")
    return tmp_path


@pytest.fixture
def policy(git_repo):
    return WorkspacePolicy(git_repo)


def _main_workspace(repo) -> str:
    out = _run_git(repo, "worktree", "list", "--porcelain").stdout
    return out.splitlines()[0].removeprefix("worktree ")


def _linked_worktrees(repo) -> list[str]:
    out = _run_git(repo, "worktree", "list", "--porcelain").stdout
    lines = out.splitlines()
    return [
        lines[i].removeprefix("worktree ")
        for i, line in enumerate(lines)
        if line.startswith("worktree ")
    ][1:]


def _create_linked_worktree(git_repo, name: str = "linked"):
    """手动创建一个 linked worktree（模拟编排层 worktree），返回其路径。"""
    path = git_repo / "linked-wt" / name
    path.parent.mkdir(parents=True)
    _run_git(git_repo, "worktree", "add", "-b", f"wt-{name}", str(path))
    return path


# --- 主模式 deny patterns（Q2 用户确认） ----------------------------------


def test_deny_pattern_blocks_worktree_subdir(git_repo):
    """主模式工具不可直接读写 .asterwynd/worktrees/** 内文件。"""
    from agent.workspace_policy import DEFAULT_DENIED_PATTERNS

    assert ".asterwynd/worktrees/**" in DEFAULT_DENIED_PATTERNS
    policy = WorkspacePolicy(git_repo)
    wt_file = git_repo / ".asterwynd" / "worktrees" / "x" / "file.txt"
    wt_file.parent.mkdir(parents=True)
    wt_file.write_text("secret\n")
    with pytest.raises(PermissionError):
        policy.assert_read_allowed(wt_file)
    with pytest.raises(PermissionError):
        policy.assert_write_allowed(wt_file)


# --- Schema / 权限元数据 ------------------------------------------------


def test_enter_worktree_schema():
    tool = EnterWorktreeTool()
    params = tool.parameters["properties"]
    assert "name" in params
    assert "base_branch" in params
    assert "name" in tool.parameters["required"]


def test_exit_worktree_schema():
    tool = ExitWorktreeTool()
    params = tool.parameters["properties"]
    assert "keep" in params


def test_permission_metadata():
    # 用户确认：dangerous=False + WORKSPACE_WRITE（MEDIUM），不限制 allowed_modes
    for tool in (EnterWorktreeTool(), ExitWorktreeTool()):
        assert tool.dangerous is False
        assert tool.allowed_modes is None
        permission = tool.get_permission()
        assert permission.capabilities == frozenset({ToolCapability.WORKSPACE_WRITE})
        assert permission.risk_level is ToolRiskLevel.MEDIUM


# --- EnterWorktree ------------------------------------------------------


@pytest.mark.asyncio
async def test_enter_worktree_creates_and_rebinds(git_repo, policy):
    tool = EnterWorktreeTool(policy=policy)

    result = await tool.execute(name="test-wt")

    assert isinstance(result, ToolResult)
    assert result.error_type is None
    payload = json.loads(result.text)
    wt_path = git_repo / WT_DIR / "test-wt"
    assert payload == {"worktree": str(wt_path), "branch": "test-wt"}
    # policy root 重绑定到 worktree
    assert policy.workspace_root == wt_path.resolve()
    # 真实 worktree 存在，分支名为 name
    assert _linked_worktrees(git_repo) == [str(wt_path.resolve())]
    assert _run_git(wt_path, "branch", "--show-current").stdout.strip() == "test-wt"


@pytest.mark.asyncio
async def test_enter_worktree_base_branch(git_repo, policy):
    _run_git(git_repo, "checkout", "-b", "feature-base")
    tool = EnterWorktreeTool(policy=policy)

    result = await tool.execute(name="test-wt", base_branch="feature-base")

    payload = json.loads(result.text)
    wt_path = git_repo / WT_DIR / "test-wt"
    assert payload["branch"] == "test-wt"
    # 新分支基于 feature-base
    base_sha = _run_git(git_repo, "rev-parse", "feature-base").stdout.strip()
    wt_sha = _run_git(wt_path, "rev-parse", "HEAD").stdout.strip()
    assert wt_sha == base_sha


@pytest.mark.asyncio
async def test_enter_worktree_not_a_git_repo(tmp_path):
    # 注意：不依赖 git_repo fixture（否则 tmp_path 已被 git init）
    policy = WorkspacePolicy(tmp_path)
    tool = EnterWorktreeTool(policy=policy)

    result = await tool.execute(name="test-wt")

    assert isinstance(result, ToolResult)
    assert result.error_type == "not_a_git_repo"
    assert policy.workspace_root == tmp_path.resolve()


@pytest.mark.asyncio
async def test_enter_worktree_nested_rejected(git_repo, policy):
    linked = _create_linked_worktree(git_repo)
    policy.workspace_root = linked.resolve()
    tool = EnterWorktreeTool(policy=policy)

    result = await tool.execute(name="nested")

    assert isinstance(result, ToolResult)
    assert result.error_type == "already_in_worktree"
    assert policy.workspace_root == linked.resolve()


@pytest.mark.asyncio
async def test_enter_worktree_branch_conflict(git_repo, policy):
    _run_git(git_repo, "branch", "test-wt")  # 分支已存在
    tool = EnterWorktreeTool(policy=policy)

    result = await tool.execute(name="test-wt")

    assert isinstance(result, ToolResult)
    assert result.error_type == "worktree_create_failed"
    # 失败回滚：无残留 worktree、policy root 不变
    assert _linked_worktrees(git_repo) == []
    assert policy.workspace_root == git_repo.resolve()


@pytest.mark.asyncio
async def test_enter_worktree_invalid_name_rejected(git_repo, policy):
    tool = EnterWorktreeTool(policy=policy)

    for bad in ("", "..", "a/b", "a b", "-leading"):
        result = await tool.execute(name=bad)

        assert isinstance(result, ToolResult)
        assert result.error_type == "worktree_create_failed"
        assert _linked_worktrees(git_repo) == []
    assert policy.workspace_root == git_repo.resolve()


@pytest.mark.asyncio
async def test_exit_worktree_rejects_non_tool_created(git_repo, policy):
    """编排层/benchmark 任务 worktree（非 .asterwynd/worktrees/ 下）拒绝退出。"""
    linked = _create_linked_worktree(git_repo)
    policy.workspace_root = linked.resolve()
    exit_tool = ExitWorktreeTool(policy=policy)

    result = await exit_tool.execute(keep=False)

    assert isinstance(result, ToolResult)
    assert result.error_type == "not_in_worktree"
    # 状态不变：policy root 未切回主工作区、任务 worktree 未被删除
    assert policy.workspace_root == linked.resolve()
    assert _linked_worktrees(git_repo) == [str(linked.resolve())]


@pytest.mark.asyncio
async def test_enter_worktree_detached_head(git_repo, policy):
    _run_git(git_repo, "checkout", "--detach")
    tool = EnterWorktreeTool(policy=policy)

    result = await tool.execute(name="test-wt")

    assert isinstance(result, ToolResult)
    assert result.error_type is None
    wt_path = git_repo / WT_DIR / "test-wt"
    assert policy.workspace_root == wt_path.resolve()


@pytest.mark.asyncio
async def test_enter_worktree_rollback_on_post_add_failure(git_repo, policy, monkeypatch):
    tool = EnterWorktreeTool(policy=policy)

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated post-add failure")

    monkeypatch.setattr(tool, "_rebind_workspace", _boom)

    result = await tool.execute(name="test-wt")

    assert isinstance(result, ToolResult)
    assert result.error_type == "worktree_create_failed"
    # 回滚：worktree 已删除、policy root 不变
    assert _linked_worktrees(git_repo) == []
    assert policy.workspace_root == git_repo.resolve()


# --- ExitWorktree -------------------------------------------------------


@pytest.mark.asyncio
async def test_exit_worktree_keep_true(git_repo, policy):
    enter = EnterWorktreeTool(policy=policy)
    await enter.execute(name="test-wt")
    exit_tool = ExitWorktreeTool(policy=policy)

    result = await exit_tool.execute(keep=True)

    assert isinstance(result, ToolResult)
    assert result.error_type is None
    payload = json.loads(result.text)
    assert payload == {"workspace": str(git_repo.resolve()), "removed": False}
    assert policy.workspace_root == git_repo.resolve()
    # worktree 与分支保留（--format 避免 worktree 检出的 `+ ` 前缀）
    assert len(_linked_worktrees(git_repo)) == 1
    branches = _run_git(git_repo, "branch", "--format=%(refname:short)").stdout.splitlines()
    assert "test-wt" in branches


@pytest.mark.asyncio
async def test_exit_worktree_keep_false_removes(git_repo, policy):
    enter = EnterWorktreeTool(policy=policy)
    await enter.execute(name="test-wt")
    exit_tool = ExitWorktreeTool(policy=policy)

    result = await exit_tool.execute(keep=False)

    assert isinstance(result, ToolResult)
    assert result.error_type is None
    payload = json.loads(result.text)
    assert payload == {"workspace": str(git_repo.resolve()), "removed": True}
    assert policy.workspace_root == git_repo.resolve()
    assert _linked_worktrees(git_repo) == []
    # 分支保留（用户确认：keep=false 不删分支）
    assert _run_git(git_repo, "branch", "--list", "test-wt").stdout.strip() == "test-wt"


@pytest.mark.asyncio
async def test_exit_worktree_dirty_rejected_state_unchanged(git_repo, policy):
    enter = EnterWorktreeTool(policy=policy)
    await enter.execute(name="test-wt")
    wt_path = policy.workspace_root
    (wt_path / "dirty.txt").write_text("uncommitted\n")
    exit_tool = ExitWorktreeTool(policy=policy)

    result = await exit_tool.execute(keep=False)

    assert isinstance(result, ToolResult)
    assert result.error_type == "worktree_remove_failed"
    # 状态不变：仍在 worktree 内、worktree 未删除、文件还在
    assert policy.workspace_root == wt_path
    assert _linked_worktrees(git_repo) == [str(wt_path)]
    assert (wt_path / "dirty.txt").exists()


@pytest.mark.asyncio
async def test_exit_worktree_dirty_tracked_modification_rejected(git_repo, policy):
    enter = EnterWorktreeTool(policy=policy)
    await enter.execute(name="test-wt")
    wt_path = policy.workspace_root
    (wt_path / "app.py").write_text("modified\n")
    exit_tool = ExitWorktreeTool(policy=policy)

    result = await exit_tool.execute(keep=False)

    assert isinstance(result, ToolResult)
    assert result.error_type == "worktree_remove_failed"
    assert policy.workspace_root == wt_path


@pytest.mark.asyncio
async def test_exit_worktree_not_in_worktree(git_repo, policy):
    exit_tool = ExitWorktreeTool(policy=policy)

    result = await exit_tool.execute()

    assert isinstance(result, ToolResult)
    assert result.error_type == "not_in_worktree"
    assert policy.workspace_root == git_repo.resolve()


# --- 文件工具路径边界（工作区级隔离） ------------------------------------


@pytest.mark.asyncio
async def test_file_tool_boundary_rebound_into_worktree(git_repo, policy):
    enter = EnterWorktreeTool(policy=policy)
    await enter.execute(name="test-wt")
    wt_path = policy.workspace_root
    (wt_path / "app.py").write_text("inside worktree\n")
    # 主工作区专属文件（只在主 checkout 存在）
    (git_repo / "main_only.txt").write_text("main only\n")

    read = ReadTool(policy=policy)
    # worktree 内文件可读
    ok = await read.execute(path="app.py")
    assert "inside worktree" in ok
    # 主工作区文件越界被拒（policy root 已重绑定到 worktree）
    denied = await read.execute(path="../main_only.txt")
    assert "outside workspace" in denied


# --- AgentLoop 层（registry 调用后状态断言） ------------------------------


@pytest.mark.asyncio
async def test_registry_enter_exit_updates_policy_root(git_repo, policy):
    registry = ToolRegistry(mode_policy=ModePolicy())
    registry.register(EnterWorktreeTool(policy=policy))
    registry.register(ExitWorktreeTool(policy=policy))
    registry.workspace_policy = policy

    enter_result = await registry.execute(
        ToolCall(id="1", name="EnterWorktree", arguments={"name": "test-wt"})
    )
    assert enter_result.error_type is None
    wt_path = policy.workspace_root
    assert wt_path == (git_repo / WT_DIR / "test-wt").resolve()

    exit_result = await registry.execute(
        ToolCall(id="2", name="ExitWorktree", arguments={"keep": True})
    )
    assert exit_result.error_type is None
    assert policy.workspace_root == git_repo.resolve()
