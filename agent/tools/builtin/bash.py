# agent/tools/builtin/bash.py
import os
from collections.abc import Awaitable, Callable
from typing import Any

from agent.background import current_tool_call_id
from agent.sandbox_events import emit_sandbox_event
from agent.tools.base import Tool, tool_parameters
from agent.tools.command_guard import CommandGuard, CommandVerdict
from agent.tools.sandbox import ExecutionBackend, build_execution_backend
from agent.tool_permissions import COMMAND_EXECUTE_PERMISSION
from agent.workspace_policy import WorkspacePolicy

RunInBackgroundCb = Callable[[str, str, float | None, str], Awaitable[str]]


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
            "run_in_background": {
                "type": "boolean",
                "description": "设为 True 时后台执行，立即返回 task_id。使用 TaskOutput 检查结果。",
                "default": False,
            },
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
        sandbox: ExecutionBackend | None = None,
        run_in_background_cb: RunInBackgroundCb | None = None,
        backend_name: str = "process",
    ):
        self.policy = policy or WorkspacePolicy()
        self.sandbox = sandbox or build_execution_backend(backend_name)
        self._guard = CommandGuard(workspace=self.policy.workspace_root)
        self._run_in_background_cb = run_in_background_cb

    def set_run_in_background_cb(self, cb: RunInBackgroundCb | None) -> None:
        self._run_in_background_cb = cb

    async def execute(
        self,
        cmd: str,
        timeout: float | None = None,
        run_in_background: bool = False,
        **kwargs,
    ) -> str:
        try:
            self.policy.assert_command_allowed(cmd)
        except PermissionError as e:
            emit_sandbox_event("denied", reason="workspace_policy", command=cmd, tool="Bash")
            return f"Error: {e}"
        # Command guard (guardrail, not boundary) — argv semantic checks.
        if self._guard.check(cmd) is CommandVerdict.DENY:
            reason = f"command_guard:{self._guard.last_reason or 'denied'}"
            emit_sandbox_event("denied", reason=reason, command=cmd, tool="Bash")
            return "Error: Command denied by sandbox command guard"

        if run_in_background:
            return await self._execute_background(cmd, timeout)

        result = await self.sandbox.run(
            cmd,
            timeout=timeout or 30.0,
            cwd=self.policy.workspace_root,
        )
        return result.to_json()

    async def _execute_background(self, cmd: str, timeout: float | None) -> str:
        if self._run_in_background_cb is None:
            return "Error: Background task execution is not available (no manager configured)."
        tc_id = current_tool_call_id.get()
        task_id = await self._run_in_background_cb(cmd, str(self.policy.workspace_root), timeout, tc_id)
        return f"Task started: {task_id}. Use TaskOutput to check status."
