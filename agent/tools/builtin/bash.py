# agent/tools/builtin/bash.py
import os
from collections.abc import Awaitable, Callable
from typing import Any

from agent.background import current_tool_call_id
from agent.sandbox_events import emit_sandbox_event
from agent.tools.base import Tool, tool_parameters, ToolResult
from agent.tools.command_guard import CommandGuard, CommandVerdict
from agent.tools.sandbox import ExecutionBackend, build_execution_backend
from agent.tool_permissions import COMMAND_EXECUTE_PERMISSION
from agent.workspace_policy import WorkspacePolicy

RunInBackgroundCb = Callable[[str, str, float | None, str], Awaitable[str]]


async def _build_guard_approval_request(
    request: object,
    *,
    tool_call_id: str,
    command: str,
    reason: str | None,
) -> object:
    """Fill in the tool-specific fields of an ``ApprovalRequest``.

    The loop builds the request for its own (pre-execution) approvals; a guard
    `ask` happens *during* execution, so BashTool builds one itself. The handler
    only reads the fields it needs, so a partially-populated request is fine.
    """
    import uuid

    from agent.approval import ApprovalRequest

    return ApprovalRequest(
        approval_id=str(uuid.uuid4()),
        tool_call_id=tool_call_id,
        tool_name="Bash",
        mode=getattr(request, "mode", "build"),
        capability=["command_execute"],
        risk="high",
        origin="command_guard",
        reason=reason or "command guard cannot decide statically",
        profile_name=getattr(request, "profile_name", "command_guard"),
        redacted_args={"cmd": command},
        args_summary=command,
    )


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
        approval_handler: object | None = None,
    ):
        self.policy = policy or WorkspacePolicy()
        self.sandbox = sandbox or build_execution_backend(backend_name)
        self._guard = CommandGuard(workspace=self.policy.workspace_root)
        self._run_in_background_cb = run_in_background_cb
        self._approval_handler = approval_handler

    def set_run_in_background_cb(self, cb: RunInBackgroundCb | None) -> None:
        self._run_in_background_cb = cb

    def set_approval_cb(self, handler: object | None) -> None:
        """Wire the approval handler used when the guard cannot decide (`ask`)."""
        self._approval_handler = handler

    async def execute(
        self,
        cmd: str,
        timeout: float | None = None,
        run_in_background: bool = False,
        **kwargs,
    ) -> str | ToolResult:
        try:
            self.policy.assert_command_allowed(cmd)
        except PermissionError as e:
            emit_sandbox_event("denied", reason="workspace_policy", command=cmd, tool="Bash")
            return ToolResult(text=f"Error: {e}", error_type="permission_denied")
        # Command guard (guardrail, not boundary) — argv semantic checks.
        verdict = self._guard.check(cmd)
        if verdict is CommandVerdict.DENY:
            reason = f"command_guard:{self._guard.last_reason or 'denied'}"
            emit_sandbox_event("denied", reason=reason, command=cmd, tool="Bash")
            return ToolResult(
                text="Error: Command denied by sandbox command guard",
                error_type="permission_denied",
            )
        # The guard could not decide statically: route to the approval layer
        # (design D3). `ask` is NEVER interpreted here as "allow" -- without a
        # handler, or when the handler refuses, the command does not run.
        #
        # This is a *second* approval, taken during execution, so the loop's
        # pre-execution `approval_required`/`approval_granted` events do not
        # cover it (design D3 point 4). Emit guard-specific events so the
        # decision is visible in the trace.
        if verdict is CommandVerdict.ASK:
            guard_reason = self._guard.last_reason or "ask"
            emit_sandbox_event(
                "guard_approval_requested", reason=guard_reason, command=cmd, tool="Bash"
            )
            allowed = await self._request_guard_approval(cmd)
            emit_sandbox_event(
                "guard_approval_resolved",
                reason=guard_reason,
                approved=allowed,
                command=cmd,
                tool="Bash",
            )
            if not allowed:
                reason = f"command_guard:{guard_reason}"
                emit_sandbox_event("denied", reason=f"approval:{reason}", command=cmd, tool="Bash")
                return ToolResult(
                    text="Error: Command requires approval and was not approved",
                    error_type="permission_denied",
                )

        if run_in_background:
            return await self._execute_background(cmd, timeout)

        # Pass timeout through (None → backend's configured default). The old
        # `timeout or 30.0` silently overrode sandbox.timeout_seconds, so the
        # config value never took effect.
        result = await self.sandbox.run(
            cmd,
            timeout=timeout,
            cwd=self.policy.workspace_root,
        )
        if result.timed_out:
            # Structured signal at the source: the JSON text is indistinguishable
            # from a normal result, so only error_type can tell the loop apart.
            return ToolResult(text=result.to_json(), error_type="timeout")
        if result.oom_killed:
            return ToolResult(text=result.to_json(), error_type="resource_exhausted")
        return result.to_json()

    async def _request_guard_approval(self, cmd: str) -> bool:
        """Ask the approval layer about a guard `ask`. False means do not run."""
        from agent.approval import ApprovalDecisionStatus, FailClosedApprovalHandler

        handler = self._approval_handler
        if handler is None:
            handler = FailClosedApprovalHandler()
        request = await _build_guard_approval_request(
            self,
            tool_call_id=current_tool_call_id.get() or "",
            command=cmd,
            reason=self._guard.last_reason,
        )
        try:
            response = await handler.request_approval(request)  # type: ignore[attr-defined]
        except Exception:                                     # pragma: no cover - defensive
            return False
        return bool(getattr(response, "approved", False)) and (
            getattr(response, "status", None) is ApprovalDecisionStatus.APPROVED
        )

    async def _execute_background(self, cmd: str, timeout: float | None) -> str | ToolResult:
        if self._run_in_background_cb is None:
            return ToolResult(
                text="Error: Background task execution is not available (no manager configured).",
                error_type="unavailable",
            )
        tc_id = current_tool_call_id.get()
        task_id = await self._run_in_background_cb(cmd, str(self.policy.workspace_root), timeout, tc_id)
        return f"Task started: {task_id}. Use TaskOutput to check status."
