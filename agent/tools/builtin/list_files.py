from agent.tools.base import Tool, tool_parameters
from agent.workspace_policy import WorkspacePolicy

DEFAULT_IGNORE_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    "dist", "build", ".tox", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", ".coverage", "htmlcov",
}


@tool_parameters(
    name="ListFiles",
    description="列出目录内容（不递归列出子目录下的文件）",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "要列出的目录路径。默认为工作区根目录。",
                "default": ".",
            },
        },
        "required": [],
    },
)
class ListFilesTool(Tool):
    read_only = True

    def __init__(
        self,
        policy: WorkspacePolicy | None = None,
        ignore_patterns: tuple[str, ...] = (),
    ):
        self.policy = policy or WorkspacePolicy()
        self._ignore_dirs = set(DEFAULT_IGNORE_DIRS)
        self._ignore_dirs.update(ignore_patterns)

    async def execute(self, path: str = ".", **kwargs) -> str:
        try:
            resolved = self.policy.assert_read_allowed(path)
        except PermissionError as e:
            return f"Error: {e}"

        if not resolved.is_dir():
            return f"Error: not a directory: {path}"

        entries = []
        try:
            for entry in sorted(resolved.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower())):
                if entry.name in self._ignore_dirs:
                    continue
                suffix = "/" if entry.is_dir() else ""
                entries.append(f"{entry.name}{suffix}")
        except PermissionError:
            return f"Error: permission denied reading directory: {path}"

        if not entries:
            return "(empty directory)"
        return "\n".join(entries)
