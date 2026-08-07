# agent/tools/builtin/worktree.py
"""EnterWorktree / ExitWorktree 工具：agent 运行时自主创建、进入和退出 git worktree。

工作区级隔离：进入后仅重绑定共享 WorkspacePolicy 实例的 ``workspace_root``
（Bash 子进程 cwd 与全部文件工具路径边界自动跟随），不做进程级 os.chdir，
避免子 agent/后台任务同进程下的全局副作用。

工具仅对主 checkout 会话有效：在编排层 worktree 内（building 强制、
benchmark runner）EnterWorktree 前置条件不满足，恒被拒。
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from agent.tools.base import Tool, ToolResult, tool_parameters
from agent.workspace_policy import WorkspacePolicy

# 目录约定（用户确认，design.md D2）：主工作区仓库内 .asterwynd/worktrees/<name>
WORKTREE_SUBDIR = ".asterwynd/worktrees"

# 错误码（用户确认，design.md D6）
ERROR_NOT_A_GIT_REPO = "not_a_git_repo"
ERROR_ALREADY_IN_WORKTREE = "already_in_worktree"
ERROR_WORKTREE_CREATE_FAILED = "worktree_create_failed"
ERROR_NOT_IN_WORKTREE = "not_in_worktree"
ERROR_WORKTREE_REMOVE_FAILED = "worktree_remove_failed"


def _run_git(cwd: Path, *args: str, timeout: float = 10.0) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _is_git_repo(repo: Path) -> bool:
    result = _run_git(repo, "rev-parse", "--is-inside-work-tree")
    return result.returncode == 0 and result.stdout.strip() == "true"


def _toplevel(repo: Path) -> Path | None:
    result = _run_git(repo, "rev-parse", "--show-toplevel")
    if result.returncode != 0:
        return None
    return Path(result.stdout.strip()).resolve()


def _main_workspace(repo: Path) -> Path | None:
    """porcelain 首条目恒为主工作区（grill 实测），resolve 归一化后比较。"""
    result = _run_git(repo, "worktree", "list", "--porcelain")
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            return Path(line[len("worktree "):]).resolve()
    return None


def _in_worktree(repo: Path) -> bool:
    """当前 cwd 是否位于某个 linked worktree 中（禁止嵌套的判定）。"""
    toplevel = _toplevel(repo)
    main = _main_workspace(repo)
    if toplevel is None or main is None:
        return False
    return toplevel != main


def _current_branch(repo: Path) -> str:
    result = _run_git(repo, "branch", "--show-current")
    branch = result.stdout.strip()
    return branch or "HEAD"  # detached HEAD 时以 HEAD 为基准


@tool_parameters(
    name="EnterWorktree",
    description=(
        "创建 git worktree 隔离工作区并将会话工作目录切换到该 worktree；"
        "目录为 .asterwynd/worktrees/<name>，分支名为 <name>，仅主 checkout 会话可用"
    ),
    parameters={
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "worktree 名：用作分支名并派生目录 .asterwynd/worktrees/<name>",
            },
            "base_branch": {
                "type": "string",
                "description": "基础分支，缺省为当前分支",
            },
        },
        "required": ["name"],
    },
)
class EnterWorktreeTool(Tool):
    def __init__(self, policy: WorkspacePolicy | None = None):
        self.policy = policy or WorkspacePolicy()

    async def execute(
        self,
        name: str,
        base_branch: str | None = None,
        **kwargs,
    ) -> ToolResult:
        repo = self.policy.workspace_root
        if not _is_git_repo(repo):
            return ToolResult(
                text="Error: 当前工作区不是 git 仓库，无法创建 worktree",
                error_type=ERROR_NOT_A_GIT_REPO,
            )
        if _in_worktree(repo):
            return ToolResult(
                text="Error: 当前已在 worktree 中，禁止嵌套 worktree",
                error_type=ERROR_ALREADY_IN_WORKTREE,
            )

        wt_path = (repo / WORKTREE_SUBDIR / name).resolve()
        wt_path.parent.mkdir(parents=True, exist_ok=True)
        base = base_branch or _current_branch(repo)
        result = _run_git(repo, "worktree", "add", "-b", name, str(wt_path), base)
        if result.returncode != 0:
            # git 自清理（branch 冲突 exit 255 无残留注册）；目录残留由
            # .asterwynd/ 约定忽略，text 区分 branch/path 冲突两类原因
            return ToolResult(
                text=f"Error: worktree 创建失败: {result.stderr.strip()}",
                error_type=ERROR_WORKTREE_CREATE_FAILED,
            )

        try:
            self._rebind_workspace(wt_path)
        except Exception as exc:
            _run_git(repo, "worktree", "remove", str(wt_path))
            return ToolResult(
                text=f"Error: worktree 创建失败（切换失败，已回滚）: {exc}",
                error_type=ERROR_WORKTREE_CREATE_FAILED,
            )
        return ToolResult(
            text=json.dumps({"worktree": str(wt_path), "branch": name}, ensure_ascii=False)
        )

    def _rebind_workspace(self, path: Path) -> None:
        self.policy.workspace_root = Path(path).resolve()


@tool_parameters(
    name="ExitWorktree",
    description=(
        "离开当前 worktree 回到主工作区；keep=false 时删除该 worktree"
        "（含未提交改动时拒绝删除，不使用 --force，分支保留）"
    ),
    parameters={
        "type": "object",
        "properties": {
            "keep": {
                "type": "boolean",
                "description": "是否保留 worktree，缺省 true；false 时删除",
                "default": True,
            },
        },
    },
)
class ExitWorktreeTool(Tool):
    def __init__(self, policy: WorkspacePolicy | None = None):
        self.policy = policy or WorkspacePolicy()

    async def execute(self, keep: bool = True, **kwargs) -> ToolResult:
        repo = self.policy.workspace_root
        if not _is_git_repo(repo):
            return ToolResult(
                text="Error: 当前工作区不是 git 仓库",
                error_type=ERROR_NOT_A_GIT_REPO,
            )
        current = self.policy.workspace_root
        main = _main_workspace(repo)
        if main is None or _toplevel(repo) == main:
            return ToolResult(
                text="Error: 当前不在任何 worktree 中",
                error_type=ERROR_NOT_IN_WORKTREE,
            )

        # 执行顺序（design.md D3）：预检 → 切出 → 删除。必须先切出再删除
        # （删掉 cwd 所在目录后 os.getcwd() 崩溃）。
        if not keep:
            status = _run_git(current, "status", "--porcelain")
            if status.returncode == 0 and status.stdout.strip():
                return ToolResult(
                    text=(
                        "Error: worktree 内有未提交改动，拒绝删除（不使用 --force；"
                        "可先提交/stash 改动，或 keep=true 保留 worktree）"
                    ),
                    error_type=ERROR_WORKTREE_REMOVE_FAILED,
                )

        self.policy.workspace_root = main

        removed = False
        if not keep:
            result = _run_git(repo, "worktree", "remove", str(current))
            if result.returncode != 0:
                # 部分成功：已切回主工作区但删除未完成，text 明示避免误判
                return ToolResult(
                    text=(
                        f"Error: worktree 删除失败（已切回主工作区，worktree 保留）: "
                        f"{result.stderr.strip()}"
                    ),
                    error_type=ERROR_WORKTREE_REMOVE_FAILED,
                )
            removed = True

        return ToolResult(
            text=json.dumps(
                {"workspace": str(main), "removed": removed}, ensure_ascii=False
            )
        )
