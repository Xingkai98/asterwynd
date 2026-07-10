from __future__ import annotations

from typing import TYPE_CHECKING
from agent.tools.base import Tool, ToolCall
from agent.run_config import ModePolicy
from agent.tool_permissions import PermissionDecisionType

if TYPE_CHECKING:
    from agent.message import ContentBlock

class ToolRegistry:
    def __init__(self, mode_policy: ModePolicy | None = None):
        self._tools: dict[str, Tool] = {}
        self.mode_policy = mode_policy or ModePolicy()

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get_schema(self, name: str) -> dict:
        return self._tools[name].get_schema()

    def get_all_schemas(self) -> list[dict]:
        return [
            tool.get_schema()
            for tool in self._tools.values()
            if self.mode_policy.is_tool_allowed(tool)
        ]

    def get_sandbox(self, name: str) -> bool:
        return self._tools[name].dangerous

    async def execute(self, tool_call: ToolCall, *, approval_granted: bool = False) -> str | list["ContentBlock"]:
        tool = self._tools[tool_call.name]
        decision = self.mode_policy.decide_tool(tool)
        if decision.type is PermissionDecisionType.DENY:
            mode = self.mode_policy.mode.value
            return (
                f"[Permission denied: tool {tool_call.name} is not allowed "
                f"in {mode} mode: {decision.reason}]"
            )
        if decision.type is PermissionDecisionType.REQUIRE_APPROVAL and not approval_granted:
            return (
                f"[Approval required: tool {tool_call.name} requires approval "
                f"in {self.mode_policy.mode.value} mode]"
            )
        return await tool.execute(**tool_call.arguments)

    def get_tool(self, name: str) -> Tool:
        return self._tools[name]
