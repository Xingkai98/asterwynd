from agent.tools.base import Tool, ToolCall
from agent.run_config import ModePolicy

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

    async def execute(self, tool_call: ToolCall) -> str:
        tool = self._tools[tool_call.name]
        if not self.mode_policy.is_tool_allowed(tool):
            mode = self.mode_policy.mode.value
            return (
                f"[Permission denied: tool {tool_call.name} is not allowed "
                f"in {mode} mode]"
            )
        return await tool.execute(**tool_call.arguments)

    def get_tool(self, name: str) -> Tool:
        return self._tools[name]
