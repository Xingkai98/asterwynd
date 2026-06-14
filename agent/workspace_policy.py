from __future__ import annotations

import fnmatch
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


class WorkspacePolicy:
    def __init__(
        self,
        workspace_root: str | Path | None = None,
        denied_patterns: tuple[str, ...] | list[str] | None = None,
    ):
        self.workspace_root = Path(workspace_root or Path.cwd()).resolve()
        self.denied_patterns = tuple(denied_patterns or DEFAULT_DENIED_PATTERNS)

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
        return self.assert_within_workspace(path)

    def assert_write_allowed(self, path: str | Path) -> Path:
        resolved = self.assert_within_workspace(path)
        if self.is_denied(resolved):
            rel = resolved.relative_to(self.workspace_root).as_posix()
            raise PermissionError(f"Write denied by workspace policy: {rel}")
        return resolved

    def assert_command_allowed(self, command: str) -> None:
        denied_fragments = (
            "rm -rf /",
            "mkfs.",
            "dd if=",
            ":(){ :|:& };:",
            "chmod 777 /",
            "> /dev/sda",
        )
        for fragment in denied_fragments:
            if fragment in command:
                raise PermissionError(f"Command denied by workspace policy: {fragment}")

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

