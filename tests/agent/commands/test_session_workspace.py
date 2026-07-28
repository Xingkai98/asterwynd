"""Tests for /session-workspace slash command handler.

Covers add, remove, list, and error paths.
"""
import pytest
from pathlib import Path

from agent.commands.registry import (
    CommandContext,
    build_default_slash_command_registry,
)
from agent.workspace_policy import WorkspacePolicy


class FakeToolRegistry:
    """Minimal ToolRegistry stub with a workspace_policy attribute."""

    def __init__(self, policy=None):
        self.workspace_policy = policy
        self._tools = {}

    def set_tool(self, name, tool):
        self._tools[name] = tool

    def get_tool(self, name):
        return self._tools[name]


class FakeAgent:
    """Minimal agent with a tool_registry for session-workspace tests."""

    def __init__(self, policy=None):
        self.tool_registry = FakeToolRegistry(policy=policy)


def _make_ctx(workspace_root, policy=None):
    """Create a FakeAgent + CommandContext wired to the given root/policy."""
    if policy is None:
        policy = WorkspacePolicy(workspace_root)
    agent = FakeAgent(policy=policy)
    return CommandContext(
        agent=agent,
        messages=[],
        session_id="test-session",
        provider="test",
        model="test",
    ), policy


async def _get_handler():
    """Return the session-workspace handler from the default registry."""
    registry = build_default_slash_command_registry()
    return registry._commands["session-workspace"].handler


# ---- add subcommand --------------------------------------------------------

@pytest.mark.asyncio
async def test_session_workspace_add_valid_path(tmp_path):
    """Adding a valid directory path succeeds."""
    ctx, policy = _make_ctx(tmp_path)
    extra = Path("/tmp") / f"extra_ws_{tmp_path.name}"
    extra.mkdir(exist_ok=True)
    handler = await _get_handler()

    result = await handler(ctx, f"add {extra}")

    assert "已添加 workspace" in result.message
    assert str(extra.resolve()) in result.message
    assert extra.resolve() in policy.additional_roots


@pytest.mark.asyncio
async def test_session_workspace_add_missing_arg(tmp_path):
    """Missing argument shows usage."""
    ctx, _ = _make_ctx(tmp_path)
    handler = await _get_handler()

    result = await handler(ctx, "add")

    assert result.message == "用法: /session-workspace add <path>"


@pytest.mark.asyncio
async def test_session_workspace_add_nonexistent_path(tmp_path):
    """Adding an ancestor of the workspace root raises ValueError.
    The handler passes create=True, so non-existent paths are auto-created.
    What fails: paths that are ancestors of the workspace root, which would
    grant access outside the workspace."""
    ctx, _ = _make_ctx(tmp_path)
    # /tmp is an ancestor of tmp_path
    handler = await _get_handler()

    result = await handler(ctx, "add /tmp")

    assert "无法添加" in result.message
    assert "祖先" in result.message


@pytest.mark.asyncio
async def test_session_workspace_add_create_true(tmp_path):
    """When handler passes create=True (the current implementation), the path
    is auto-created by policy.add_root(path, create=True)."""
    ctx, policy = _make_ctx(tmp_path)
    new_dir = Path("/tmp") / f"new_created_{tmp_path.name}"
    if new_dir.exists():
        new_dir.rmdir()
    assert not new_dir.exists()
    handler = await _get_handler()

    result = await handler(ctx, f"add {new_dir}")

    assert "已添加 workspace" in result.message
    assert new_dir.exists()
    assert new_dir.resolve() in policy.additional_roots


# ---- remove subcommand -----------------------------------------------------

@pytest.mark.asyncio
async def test_session_workspace_remove_valid(tmp_path):
    """Removing a previously added path succeeds."""
    ctx, policy = _make_ctx(tmp_path)
    extra = Path("/tmp") / f"to_remove_{tmp_path.name}"
    extra.mkdir(exist_ok=True)
    policy.add_root(str(extra))
    assert extra.resolve() in policy.additional_roots
    handler = await _get_handler()

    result = await handler(ctx, f"remove {extra}")

    assert "已移除 workspace" in result.message
    assert extra.resolve() not in policy.additional_roots


@pytest.mark.asyncio
async def test_session_workspace_remove_missing_arg(tmp_path):
    """Missing argument shows usage."""
    ctx, _ = _make_ctx(tmp_path)
    handler = await _get_handler()

    result = await handler(ctx, "remove")

    assert result.message == "用法: /session-workspace remove <path>"


@pytest.mark.asyncio
async def test_session_workspace_remove_workspace_root(tmp_path):
    """Removing the workspace root silently no-ops."""
    ctx, policy = _make_ctx(tmp_path)
    root = tmp_path.resolve()
    handler = await _get_handler()

    result = await handler(ctx, f"remove {root}")

    # Still succeeds (no error), root not actually removed
    assert "已移除 workspace" in result.message
    assert list(policy.list_roots()) == [root]


# ---- list subcommand --------------------------------------------------------

@pytest.mark.asyncio
async def test_session_workspace_list_no_extras(tmp_path):
    """List with only the main workspace shows no additional roots."""
    ctx, policy = _make_ctx(tmp_path)
    handler = await _get_handler()

    result = await handler(ctx, "list")

    assert "主 workspace" in result.message
    assert "(无附加 workspace)" in result.message


@pytest.mark.asyncio
async def test_session_workspace_list_with_extras(tmp_path):
    """List shows main workspace plus all additional roots."""
    ctx, policy = _make_ctx(tmp_path)
    extra1 = Path("/tmp") / f"extra1_{tmp_path.name}"
    extra1.mkdir(exist_ok=True)
    extra2 = Path("/tmp") / f"extra2_{tmp_path.name}"
    extra2.mkdir(exist_ok=True)
    policy.add_root(str(extra1))
    policy.add_root(str(extra2))
    handler = await _get_handler()

    result = await handler(ctx, "list")

    assert "主 workspace" in result.message
    assert "附加 workspace 1" in result.message
    assert str(extra1.resolve()) in result.message
    assert "附加 workspace 2" in result.message
    assert str(extra2.resolve()) in result.message
    assert "(无附加 workspace)" not in result.message


# ---- no / invalid subcommand ------------------------------------------------

@pytest.mark.asyncio
async def test_session_workspace_no_subcommand(tmp_path):
    """Empty args shows usage message."""
    ctx, _ = _make_ctx(tmp_path)
    handler = await _get_handler()

    result = await handler(ctx, "")

    assert "用法: /session-workspace add <path> | remove <path> | list" == result.message


@pytest.mark.asyncio
async def test_session_workspace_invalid_subcommand(tmp_path):
    """Unknown subcommand shows usage message."""
    ctx, _ = _make_ctx(tmp_path)
    handler = await _get_handler()

    result = await handler(ctx, "foobar")

    assert "用法: /session-workspace add <path> | remove <path> | list" == result.message


# ---- policy fallback --------------------------------------------------------

@pytest.mark.asyncio
async def test_session_workspace_policy_none(tmp_path):
    """When agent has no workspace_policy and no Read tool with a policy,
    falls through to the error message."""
    agent = FakeAgent(policy=None)
    ctx = CommandContext(
        agent=agent,
        messages=[],
        session_id="test-session",
        provider="test",
        model="test",
    )
    handler = await _get_handler()

    result = await handler(ctx, "list")

    assert "Workspace policy is not available" in result.message
