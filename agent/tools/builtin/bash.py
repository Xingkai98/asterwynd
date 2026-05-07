# agent/tools/builtin/bash.py
from agent.tools.base import Tool, tool_parameters
from agent.tools.sandbox import SandboxExecutor

_sandbox = SandboxExecutor()

@tool_parameters(
    name="Bash",
    description="执行 shell 命令（危险工具，在沙箱中运行）",
    parameters={
        "type": "object",
        "properties": {
            "cmd": {"type": "string", "description": "要执行的命令"},
            "timeout": {"type": "number", "description": "超时时间（秒）", "default": 30},
        },
        "required": ["cmd"],
    },
)
class BashTool(Tool):
    dangerous = True

    async def execute(self, cmd: str, timeout: float = 30.0, **kwargs) -> str:
        return await _sandbox.run(cmd, timeout=timeout)