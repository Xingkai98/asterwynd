# tests/agent/tools/test_worktree_benchmark_smoke.py
"""benchmark smoke：EnterWorktree/ExitWorktree 注册 + schema + 边界（Q7 形态）。

不做实现修改，只验证已实现行为：
1. 工具在 default/coding registry 注册，schema 可从 get_all_schemas() 获取
2. 权限元数据 dangerous=False + WORKSPACE_WRITE(MEDIUM)
3. 编排层 worktree 内（非工具自建）Enter/Exit 均被拒，边界不越权
"""
import subprocess

import pytest

from agent.tools.base import ToolCall, ToolResult
from agent.tools.factory import build_coding_tool_registry, build_default_tool_registry
from agent.tools.registry import ToolRegistry
from agent.tool_permissions import ToolCapability, ToolRiskLevel
from agent.workspace_policy import WorkspacePolicy

WT_DIR = ".asterwynd/worktrees"


@pytest.fixture
def git_repo(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@e.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path, check=True)
    (tmp_path / "a.py").write_text("x\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, check=True, capture_output=True)
    return tmp_path


def _tool_names(registry: ToolRegistry) -> set[str]:
    return {s["function"]["name"] for s in registry.get_all_schemas()}


def test_registered_and_schema_exposed(git_repo):
    policy = WorkspacePolicy(git_repo)
    for build in (build_default_tool_registry, build_coding_tool_registry):
        registry = build(policy=policy)
        names = _tool_names(registry)
        assert "EnterWorktree" in names
        assert "ExitWorktree" in names
    # schema 参数完整
    schema = build_default_tool_registry(policy=policy).get_schema("EnterWorktree")
    assert "name" in schema["function"]["parameters"]["properties"]


def test_permission_metadata():
    from agent.tools.builtin.worktree import EnterWorktreeTool, ExitWorktreeTool

    for tool in (EnterWorktreeTool(), ExitWorktreeTool()):
        assert tool.dangerous is False
        permission = tool.get_permission()
        assert permission.capabilities == frozenset({ToolCapability.WORKSPACE_WRITE})
        assert permission.risk_level is ToolRiskLevel.MEDIUM


@pytest.mark.asyncio
async def test_rejected_in_orchestration_worktree(git_repo):
    """编排层 worktree（非工具自建）内 Enter 被拒、Exit 被拒且不越权。"""
    wt = git_repo / "task-wt"
    subprocess.run(["git", "worktree", "add", "-b", "task-branch", str(wt)],
                   cwd=git_repo, check=True, capture_output=True)
    policy = WorkspacePolicy(wt)
    registry = build_default_tool_registry(policy=policy)

    enter = await registry.execute(
        ToolCall(id="1", name="EnterWorktree", arguments={"name": "nested"})
    )
    assert isinstance(enter, ToolResult)
    assert enter.error_type == "already_in_worktree"

    exit_res = await registry.execute(
        ToolCall(id="2", name="ExitWorktree", arguments={"keep": False})
    )
    assert isinstance(exit_res, ToolResult)
    assert exit_res.error_type == "not_in_worktree"
    # 状态不变：policy root 未被切回、任务 worktree 未被删除
    assert policy.workspace_root == wt.resolve()
    assert wt.exists()
