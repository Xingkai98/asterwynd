from __future__ import annotations

from typing import Any

from agent.mcp.manager import McpManager
from agent.mcp.types import McpToolMetadata
from agent.tools.base import Tool


class McpTool(Tool):
    def __init__(self, metadata: McpToolMetadata, manager: McpManager):
        self.name = metadata.callable_name
        self.description = metadata.description or (
            f"MCP tool {metadata.server_name}/{metadata.tool_name}"
        )
        self.parameters = metadata.input_schema
        self.permission = metadata.permission
        self.server_name = metadata.server_name
        self.tool_name = metadata.tool_name
        self._manager = manager

    async def execute(self, **kwargs: Any) -> str:
        return await self._manager.call_tool(self.server_name, self.tool_name, kwargs)
