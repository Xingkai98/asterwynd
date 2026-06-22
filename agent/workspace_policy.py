from __future__ import annotations

import fnmatch
import re
import subprocess
from pathlib import Path


DEFAULT_DENIED_PATTERNS = (
    ".git",
    ".git/**",
    ".env",
    ".env.*",
    "**/.env",
    "**/.env.*",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "id_rsa",
    "id_ed25519",
    "id_ecdsa",
    "**/id_rsa",
    "**/id_ed25519",
    "**/id_ecdsa",
    "__pycache__",
    "__pycache__/**",
    "**/__pycache__/**",
    "*.pyc",
    "node_modules",
    "node_modules/**",
    "**/node_modules/**",
    ".venv",
    ".venv/**",
    "venv",
    "venv/**",
    ".mypy_cache",
    ".mypy_cache/**",
    ".pytest_cache",
    ".pytest_cache/**",
    ".ruff_cache",
    ".ruff_cache/**",
    "benchmarks/runs",
    "benchmarks/runs/**",
)

def _match_allowlist(command: str) -> bool:
    """检查命令是否匹配允许列表前缀。支持子命令匹配。"""
    safe_prefixes = [
        # 版本控制 — 只允许读操作
        "git status", "git log", "git diff", "git show", "git branch",
        "git stash list", "git stash show",
        # 测试和构建
        "pytest", "python -m pytest", "python3 -m pytest",
        "uv run pytest", "uv run python -m pytest", "uv run python3 -m pytest",
        "uv", "pip",
        "npm test", "npm run", "npx", "yarn", "cargo", "make",
        # 文件查看
        "cat", "head", "tail", "wc", "sort", "uniq", "ls", "tree",
        "find", "fd", "rg", "grep",
        # 基本工具
        "echo", "pwd", "which", "env", "df", "du", "ps",
        # 文件操作（只允许低风险操作）
        "mkdir", "touch",
        # 包管理
        "pip install", "pip list", "pip show", "pip freeze",
    ]
    cmd_stripped = command.strip()
    for prefix in safe_prefixes:
        if cmd_stripped.startswith(prefix):
            return True
    return False

DEFAULT_DENYLIST = (
    r"rm\s+-rf\s+/",
    r"rm\s+-r[f]?\s+/",
    r"rm\s+--recursive\s+/",
    r"del\s+/[fF]\s+/",
    r"rmdir\s+/[sS]\s+/",
    r"format\s",
    r"mkfs\.",
    r"dd\s+if=",
    r">\s*/dev/sd[a-z]",
    r"dd\s+of=/dev/",
    r"shutdown",
    r"reboot",
    r"halt",
    r"poweroff",
    r"init\s+[06]",
    r"systemctl\s+(stop|restart|disable)\s",
    r"service\s+\w+\s+(stop|restart)",
    r"kill\s+-9\s",
    r"killall\s",
    r"pkill\s",
    r":\(\)\s*\{",  # fork bomb
    r"perl\s+-e\s",
    r"ruby\s+-e\s",
    r"php\s+-r\s",
    r"python3?\s+-c\b",
    r"python3?\s+-\s*<<",
    r"curl.*\|\s*(ba)?sh",
    r"wget.*\|\s*(ba)?sh",
    r"curl.*\|\s*(ba)?sh",
    r"find\s+.*-exec\s+rm\s",
    r"find\s+.*-delete\b",
    r"xargs\s+rm\s",
    r"git\s+reset\s+--hard",
    r"git\s+push\s+--force",
    r"git\s+branch\s+-D",
    r"chmod\s+777\s+/",
    r"chmod\s+-R\s+777",
    r"chown\s+-R\s+root",
    r">\s*/etc/",
    r">\s*/proc/",
    r">\s*/sys/",
    r"tee\s+/etc/",
    r"tee\s+/proc/",
    r"sed\s+-i.*/(etc|proc|sys)/",
    r"\bcp\s+(/etc/|/proc/|/sys/|\.env\b|\.env\.|\S*/\.env\b|\.git/|\S*/\.git/)",
    r"\bmv\s+(/etc/|/proc/|/sys/|\.env\b|\.env\.|\S*/\.env\b|\.git/|\S*/\.git/)",
    r"sudo\s",
    r"su\s+-",
    r"mount\s",
    r"umount\s",
    r"iptables\s",
    r"nft\s",
    r"docker\s+rm\s",
    r"docker\s+system\s+prune",
    r"kubectl\s+delete\s",
    r"DROP\s+(TABLE|DATABASE)",
    r"DELETE\s+FROM\s+\w+\s*;",  # no WHERE
)


class WorkspacePolicy:
    def __init__(
        self,
        workspace_root: str | Path | None = None,
        denied_patterns: tuple[str, ...] | list[str] | None = None,
        command_denylist: tuple[str, ...] | list[str] | None = None,
    ):
        self.workspace_root = Path(workspace_root or Path.cwd()).resolve()
        self.denied_patterns = tuple(denied_patterns or DEFAULT_DENIED_PATTERNS)

        denylist = list(DEFAULT_DENYLIST)
        if command_denylist:
            denylist.extend(command_denylist)
        self._denylist = tuple(denylist)

    def resolve(self, path: str | Path) -> Path:
        raw_path = Path(path)
        if raw_path.is_absolute():
            return raw_path.resolve()
        return (self.workspace_root / raw_path).resolve()

    def assert_within_workspace(self, path: str | Path) -> Path:
        resolved = self.resolve(path)
        try:
            resolved.relative_to(self.workspace_root)
        except ValueError as exc:
            raise PermissionError(
                f"Path is outside workspace: {path} -> {resolved}"
            ) from exc
        return resolved

    def relative_path(self, path: str | Path) -> str:
        resolved = self.assert_within_workspace(path)
        return resolved.relative_to(self.workspace_root).as_posix()

    def is_denied(self, path: str | Path) -> bool:
        resolved = self.assert_within_workspace(path)
        rel = resolved.relative_to(self.workspace_root).as_posix()
        parts = rel.split("/")
        candidates = {rel, resolved.name, *parts}
        for pattern in self.denied_patterns:
            normalized = pattern.strip("/")
            if any(fnmatch.fnmatchcase(candidate, normalized) for candidate in candidates):
                return True
            if fnmatch.fnmatchcase(rel, normalized):
                return True
        return False

    def assert_read_allowed(self, path: str | Path) -> Path:
        resolved = self.assert_within_workspace(path)
        if self.is_denied(resolved):
            rel = resolved.relative_to(self.workspace_root).as_posix()
            raise PermissionError(f"Read denied by workspace policy: {rel}")
        return resolved

    def assert_write_allowed(self, path: str | Path) -> Path:
        resolved = self.assert_within_workspace(path)
        if self.is_denied(resolved):
            rel = resolved.relative_to(self.workspace_root).as_posix()
            raise PermissionError(f"Write denied by workspace policy: {rel}")
        return resolved

    def assert_command_allowed(self, command: str) -> None:
        cmd_stripped = command.strip()

        for pattern in self._denylist:
            if re.search(pattern, cmd_stripped):
                raise PermissionError("Command denied by workspace policy")

        if _match_allowlist(cmd_stripped):
            return

    def snapshot_git_diff(self, stat: bool = False, timeout: float = 10.0) -> str:
        args = ["git", "diff", "--stat"] if stat else ["git", "diff"]
        result = subprocess.run(
            args,
            cwd=self.workspace_root,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = (result.stdout or result.stderr).strip()
        return output or "(no changes)"
