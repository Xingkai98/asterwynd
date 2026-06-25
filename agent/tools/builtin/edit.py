from __future__ import annotations

from agent.lsp.client import LspClientManager
from agent.tools.base import Tool, tool_parameters
from agent.tools.builtin._lsp_diagnostics import collect_diagnostics_feedback
from agent.workspace_policy import WorkspacePolicy


@tool_parameters(
    name="Edit",
    description=(
        "Replace exact text in a file. old_string must match exactly. "
        "By default exactly one match is required."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to edit"},
            "old_string": {"type": "string", "description": "Exact text to replace"},
            "new_string": {"type": "string", "description": "Replacement text"},
            "replace_all": {
                "type": "boolean",
                "description": "Replace every occurrence instead of requiring one match",
                "default": False,
            },
        },
        "required": ["path", "old_string", "new_string"],
    },
)
class EditTool(Tool):
    read_only = False

    def __init__(
        self,
        policy: WorkspacePolicy | None = None,
        lsp_manager: LspClientManager | None = None,
    ):
        self.policy = policy or WorkspacePolicy()
        self.lsp_manager = lsp_manager

    async def execute(
        self,
        path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
        **kwargs,
    ) -> str:
        if old_string == "":
            return "Error: old_string must not be empty"

        try:
            resolved = self.policy.assert_write_allowed(path)
        except PermissionError as exc:
            return f"Error: {exc}"

        if not resolved.exists():
            return f"Error: File not found: {path}"
        if not resolved.is_file():
            return f"Error: Not a file: {path}"

        try:
            content = resolved.read_text(errors="replace")
        except Exception as exc:
            return f"Error reading file: {exc}"

        match_count = content.count(old_string)
        if match_count == 0:
            return f"Error: old_string not found in {path}"
        if match_count > 1 and not replace_all:
            return (
                f"Error: old_string matched {match_count} times in {path}; "
                "provide a more specific old_string or set replace_all=true"
            )

        new_content = content.replace(old_string, new_string)
        try:
            resolved.write_text(new_content, errors="replace")
        except Exception as exc:
            return f"Error writing file: {exc}"

        replaced = match_count if replace_all else 1
        base = (
            f"Replaced {replaced} occurrence{'s' if replaced != 1 else ''} in {path} "
            f"(size change: {len(new_content) - len(content):+d} chars)"
        )
        diagnostics = await collect_diagnostics_feedback(self.lsp_manager, resolved)
        if diagnostics:
            return base + diagnostics
        return base

