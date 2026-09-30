"""BashTool routes a guard `ask` to the approval layer (design D3, tasks 3.2-3.5).

`ask` must never be interpreted by the guard as "allow": when the approval layer
refuses (no UI handler, `FailClosedApprovalHandler`, non-TTY CLI) the command
must not run.
"""
from __future__ import annotations

import pytest

from agent.approval import (
    ApprovalDecisionStatus,
    ApprovalHandler,
    ApprovalRequest,
    ApprovalResponse,
    FailClosedApprovalHandler,
)
from agent.tools.builtin.bash import BashTool
from agent.tools.command_guard import CommandGuard, CommandVerdict
from agent.workspace_policy import WorkspacePolicy


class _RecordingHandler:
    """An approval handler that records the request and replies as configured."""

    def __init__(self, status: ApprovalDecisionStatus) -> None:
        self.status = status
        self.requests: list[ApprovalRequest] = []

    async def request_approval(self, request: ApprovalRequest) -> ApprovalResponse:
        self.requests.append(request)
        return ApprovalResponse(approval_id=request.approval_id, status=self.status)


class _OkSandbox:
    """A sandbox that records the commands it was asked to run."""

    timeout_seconds = 30.0

    def __init__(self) -> None:
        self.commands: list[str] = []

    async def run(self, command: str, *, timeout=None, cwd=None):
        self.commands.append(command)
        from agent.tools.sandbox.base import SandboxResult

        return SandboxResult(
            exit_code=0, stdout="ok", stderr="", duration_ms=1.0, timed_out=False,
        )


def _tool(tmp_path, handler) -> tuple[BashTool, _OkSandbox]:
    sandbox = _OkSandbox()
    tool = BashTool(policy=WorkspacePolicy(tmp_path), sandbox=sandbox)  # type: ignore[arg-type]
    tool.set_approval_cb(handler)
    return tool, sandbox


def test_guard_would_ask_for_this_command(tmp_path):
    """Sanity: pick a command the guard actually answers ASK for."""
    guard = CommandGuard(workspace=str(tmp_path))
    assert guard.check("cp $SRC $DST") is CommandVerdict.ASK


@pytest.mark.asyncio
async def test_ask_approved_runs_command(tmp_path):
    handler = _RecordingHandler(ApprovalDecisionStatus.APPROVED)
    tool, sandbox = _tool(tmp_path, handler)

    result = await tool.execute("cp $SRC $DST")

    assert sandbox.commands == ["cp $SRC $DST"], "approved ask should execute"
    assert len(handler.requests) == 1
    assert "cp $SRC $DST" in str(result) or "ok" in str(result)


@pytest.mark.asyncio
async def test_ask_denied_does_not_run(tmp_path):
    handler = _RecordingHandler(ApprovalDecisionStatus.DENIED)
    tool, sandbox = _tool(tmp_path, handler)

    result = await tool.execute("cp $SRC $DST")

    assert sandbox.commands == [], "denied ask must not execute"
    assert "approval" in str(result).lower()
    assert getattr(result, "error_type", None) == "permission_denied"


@pytest.mark.asyncio
async def test_ask_unavailable_does_not_run(tmp_path):
    """Fail-closed: no UI -> the command must not run (design D3)."""
    tool, sandbox = _tool(tmp_path, FailClosedApprovalHandler())

    result = await tool.execute("cp $SRC $DST")

    assert sandbox.commands == []
    assert "approval" in str(result).lower()


@pytest.mark.asyncio
async def test_ask_without_handler_does_not_run(tmp_path):
    """No approval callback configured at all -> fail closed, do not run."""
    sandbox = _OkSandbox()
    tool = BashTool(policy=WorkspacePolicy(tmp_path), sandbox=sandbox)  # type: ignore[arg-type]

    result = await tool.execute("cp $SRC $DST")

    assert sandbox.commands == []
    assert "approval" in str(result).lower()


@pytest.mark.asyncio
async def test_deny_still_denies_without_asking(tmp_path):
    handler = _RecordingHandler(ApprovalDecisionStatus.APPROVED)
    tool, sandbox = _tool(tmp_path, handler)

    result = await tool.execute("rm -rf /")

    assert sandbox.commands == []
    assert handler.requests == [], "a hard deny must not consult the user"
    assert getattr(result, "error_type", None) == "permission_denied"


@pytest.mark.asyncio
async def test_allow_does_not_ask(tmp_path):
    handler = _RecordingHandler(ApprovalDecisionStatus.DENIED)
    tool, sandbox = _tool(tmp_path, handler)

    await tool.execute("ls -la")

    assert handler.requests == []
    assert sandbox.commands == ["ls -la"]
