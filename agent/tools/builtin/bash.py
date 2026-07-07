# agent/tools/builtin/bash.py
import os
from agent.tools.base import Tool, tool_parameters
from agent.tools.sandbox import SandboxExecutor
from agent.tool_permissions import COMMAND_EXECUTE_PERMISSION
from agent.workspace_policy import WorkspacePolicy


def _load_env_list(env_var: str) -> list[str]:
    value = os.environ.get(env_var, "")
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


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
    permission = COMMAND_EXECUTE_PERMISSION

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
        result = await self.sandbox.run(
            cmd,
            timeout=timeout,
            cwd=self.policy.workspace_root,
        )
        return result.to_json()
