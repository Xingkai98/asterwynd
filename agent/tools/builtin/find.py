import fnmatch
import os
from pathlib import Path

from agent.tools.base import Tool, tool_parameters
from agent.tool_permissions import WORKSPACE_READ_PERMISSION
from agent.workspace_policy import WorkspacePolicy

DEFAULT_IGNORE_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    "dist", "build", ".tox", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", ".coverage", "htmlcov",
}

MAX_ENTRIES = 500


@tool_parameters(
    name="Find",
    description="按 glob 模式递归搜索文件。例如 pattern: '*.py' 或 '**/test_*.py'。",
    parameters={
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "要匹配的 Glob 模式（如 '*.py' 或 '**/test_*.py'）",
            },
            "path": {
                "type": "string",
                "description": "搜索起始目录。默认为工作区根目录。",
                "default": ".",
            },
            "max_entries": {
                "type": "number",
                "description": "最大返回结果数，默认 200",
                "default": 200,
            },
        },
        "required": ["pattern"],
    },
)
class FindTool(Tool):
    read_only = True
    parallelizable = True
    permission = WORKSPACE_READ_PERMISSION

    def __init__(
        self,
        policy: WorkspacePolicy | None = None,
        ignore_patterns: tuple[str, ...] = (),
    ):
        self.policy = policy or WorkspacePolicy()
        self._ignore_dirs = set(DEFAULT_IGNORE_DIRS)
        self._ignore_dirs.update(ignore_patterns)

    async def execute(
        self,
        pattern: str,
        path: str = ".",
        max_entries: int = 200,
        **kwargs,
    ) -> str:
        try:
            resolved = self.policy.assert_read_allowed(path)
        except PermissionError as e:
            return f"Error: {e}"

        root = resolved if resolved.is_dir() else resolved.parent
        if not root.exists():
            return f"Error: path not found: {path}"

        cap = min(max_entries, MAX_ENTRIES)
        results = []
        truncated = False

        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(d for d in dirnames if d not in self._ignore_dirs)
            current = Path(dirpath)
            for filename in sorted(filenames):
                rel = current.relative_to(root) / filename
                rel_str = rel.as_posix()
                if fnmatch.fnmatch(rel_str, pattern) or fnmatch.fnmatch(filename, pattern):
                    if results:
                        results.append(rel_str)
                    else:
                        results.append(rel_str)
                if len(results) >= cap:
                    truncated = True
                    break
            if truncated:
                break

        if not results:
            return f"(no files matching '{pattern}')"

        output = "\n".join(results[:cap])
        if truncated:
            output += f"\n... (truncated, showing first {cap} of {len(results)}+ results)"
        return output
