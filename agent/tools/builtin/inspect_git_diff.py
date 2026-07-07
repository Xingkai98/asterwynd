from __future__ import annotations

import subprocess

from agent.tools.base import Tool, tool_parameters
from agent.tool_permissions import WORKSPACE_READ_PERMISSION
from agent.workspace_policy import WorkspacePolicy


@tool_parameters(
    name="InspectGitDiff",
    description="Inspect the current git diff in the workspace.",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Optional workspace-relative file path to inspect",
            },
            "include_untracked": {
                "type": "boolean",
                "description": "Whether to list untracked files",
                "default": False,
            },
        },
    },
)
class InspectGitDiffTool(Tool):
    read_only = True
    permission = WORKSPACE_READ_PERMISSION

    def __init__(self, policy: WorkspacePolicy | None = None):
        self.policy = policy or WorkspacePolicy()

    async def execute(
        self,
        path: str | None = None,
        include_untracked: bool = False,
        **kwargs,
    ) -> str:
        args = ["git", "diff", "--stat"]
        rel_path = None
        if path:
            try:
                resolved = self.policy.assert_read_allowed(path)
                rel_path = resolved.relative_to(self.policy.workspace_root).as_posix()
            except PermissionError as exc:
                return f"Error: {exc}"
            args = ["git", "diff", "--", rel_path]

        parts: list[str] = []
        try:
            result = subprocess.run(
                args,
                cwd=self.policy.workspace_root,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except Exception as exc:
            return f"Error running git diff: {exc}"

        output = result.stdout.strip()
        if output:
            title = f"--- Diff for {rel_path} ---" if rel_path else "--- Changed files ---"
            parts.append(title)
            parts.append(_truncate(output, 4000))
        else:
            parts.append("No changes in tracked files.")

        if include_untracked:
            try:
                untracked = subprocess.run(
                    ["git", "ls-files", "--others", "--exclude-standard"],
                    cwd=self.policy.workspace_root,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                untracked_output = untracked.stdout.strip()
            except Exception as exc:
                untracked_output = f"[Error listing untracked files: {exc}]"
            if untracked_output:
                parts.append("--- Untracked files ---")
                parts.append(_truncate_lines(untracked_output, 30))

        return "\n".join(parts)


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + f"\n... (truncated, {len(value) - limit} more chars)"


def _truncate_lines(value: str, limit: int) -> str:
    lines = value.splitlines()
    if len(lines) <= limit:
        return value
    return "\n".join(lines[:limit]) + f"\n... ({len(lines) - limit} more lines)"
