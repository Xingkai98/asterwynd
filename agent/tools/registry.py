# agent/tools/registry.py
from typing import Optional
from agent.tools.base import Tool, ToolCall

class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get_schema(self, name: str) -> dict:
        return self._tools[name].get_schema()

    def get_all_schemas(self) -> list[dict]:
        return [tool.get_schema() for tool in self._tools.values()]

    def get_sandbox(self, name: str) -> bool:
        return self._tools[name].dangerous

    async def execute(self, tool_call: ToolCall) -> str:
        tool = self._tools[tool_call.name]
        return await tool.execute(**tool_call.arguments)

    def get_tool(self, name: str) -> Tool:
        return self._tools[name]