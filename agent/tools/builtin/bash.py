# agent/tools/builtin/bash.py
from agent.tools.base import Tool, tool_parameters
from agent.tools.sandbox import SandboxExecutor
from agent.workspace_policy import WorkspacePolicy

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

    def __init__(
        self,
        policy: WorkspacePolicy | None = None,
        sandbox: SandboxExecutor | None = None,
    ):
        self.policy = policy or WorkspacePolicy()
        self.sandbox = sandbox or SandboxExecutor()

    async def execute(self, cmd: str, timeout: float = 30.0, **kwargs) -> str:
        try:
            self.policy.assert_command_allowed(cmd)
        except PermissionError as e:
            return f"Error: {e}"
        return await self.sandbox.run(
            cmd,
            timeout=timeout,
            cwd=self.policy.workspace_root,
        )
