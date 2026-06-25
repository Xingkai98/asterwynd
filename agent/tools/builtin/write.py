# agent/tools/builtin/write.py
from __future__ import annotations

from pathlib import Path

from agent.lsp.client import LspClientManager
from agent.tools.base import Tool, tool_parameters
from agent.tools.builtin._lsp_diagnostics import collect_diagnostics_feedback
from agent.workspace_policy import WorkspacePolicy

@tool_parameters(
    name="Write",
    description=(
        "Create a new file. This refuses to overwrite existing files; use Edit "
        "for modifying existing files."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径"},
            "content": {"type": "string", "description": "写入内容"},
        },
        "required": ["path", "content"],
    },
)
class WriteTool(Tool):
    read_only = False

    def __init__(
        self,
        policy: WorkspacePolicy | None = None,
        lsp_manager: LspClientManager | None = None,
    ):
        # Keep direct WriteTool() backwards-compatible for existing tests and
        # callers. Agent tool sets inject a workspace-rooted policy explicitly.
        self.policy = policy or WorkspacePolicy(Path("/"))
        self.lsp_manager = lsp_manager

    async def execute(
        self,
        path: str,
        content: str,
        **kwargs,
    ) -> str:
        try:
            p = self.policy.assert_write_allowed(path)
            if p.exists() and p.is_dir():
                return f"Error: cannot write file because path is a directory: {path}"
            if p.exists():
                return (
                    f"Error: file already exists: {path}. "
                    "Use Edit for modifications instead of overwriting existing files."
                )
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, errors="replace")
            base = f"已写入 {len(content)} 字符到 {path}"
            diagnostics = await collect_diagnostics_feedback(self.lsp_manager, p)
            if diagnostics:
                return base + diagnostics
            return base
        except PermissionError as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Error: {e}"
