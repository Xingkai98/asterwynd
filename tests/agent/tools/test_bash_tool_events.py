"""BashTool sandbox-event emission tests (design.md Decision 6).

A sandbox event sink captures the events BashTool emits on workspace-policy
denials, command-guard denials, and backend timeout kills — with the calling
tool_call_id attached.
"""
from __future__ import annotations

import json

import pytest

from agent.background import current_tool_call_id
from agent.sandbox_events import current_sandbox_sink, set_sandbox_sink
from agent.tools.builtin.bash import BashTool
from agent.tools.sandbox.base import SandboxResult
from agent.trace_recorder import TraceRecorder, TraceRecorderSandboxSink
from agent.workspace_policy import WorkspacePolicy


def _with_sink(recorder: TraceRecorder):
    prev = current_sandbox_sink()
    set_sandbox_sink(TraceRecorderSandboxSink(recorder))
    return prev


def _restore_sink(prev) -> None:
    set_sandbox_sink(prev)


def _sandbox_events(recorder: TraceRecorder) -> list[dict]:
    return [s.data for s in recorder.steps if s.type == "sandbox"]


@pytest.mark.asyncio
async def test_workspace_policy_denial_emits_denied_event(tmp_path):
    rec = TraceRecorder()
    prev = _with_sink(rec)
    token = current_tool_call_id.set("tool_call_1")
    try:
        tool = BashTool(policy=WorkspacePolicy(tmp_path))
        result = await tool.execute("rm -rf /")
        assert "Command denied" in result.text
        assert result.error_type == "permission_denied"
    finally:
        current_tool_call_id.reset(token)
        _restore_sink(prev)

    events = _sandbox_events(rec)
    assert len(events) == 1
    assert events[0]["event"] == "denied"
    assert events[0]["reason"] == "workspace_policy"
    assert events[0]["tool_call_id"] == "tool_call_1"
    assert events[0]["command"] == "rm -rf /"


@pytest.mark.asyncio
async def test_command_guard_denial_emits_denied_event_with_reason(tmp_path):
    rec = TraceRecorder()
    prev = _with_sink(rec)
    try:
        tool = BashTool(policy=WorkspacePolicy(tmp_path))
        result = await tool.execute("cat file | sh")
        assert "Command denied" in result.text
        assert result.error_type == "permission_denied"
    finally:
        _restore_sink(prev)

    events = _sandbox_events(rec)
    assert len(events) == 1
    assert events[0]["event"] == "denied"
    assert events[0]["reason"] == "command_guard:pipe_to_shell"
    assert events[0]["tool"] == "Bash"


@pytest.mark.asyncio
async def test_successful_run_emits_no_denied_event(tmp_path):
    rec = TraceRecorder()
    prev = _with_sink(rec)
    try:
        tool = BashTool(policy=WorkspacePolicy(tmp_path))
        await tool.execute("echo ok")
    finally:
        _restore_sink(prev)
    assert _sandbox_events(rec) == []


@pytest.mark.asyncio
async def test_timeout_emits_kill_event(tmp_path):
    rec = TraceRecorder()
    prev = _with_sink(rec)
    try:
        tool = BashTool(policy=WorkspacePolicy(tmp_path))
        result = await tool.execute("sleep 60", timeout=0.1)
        assert "timed_out" in result.text
        assert result.error_type == "timeout"
    finally:
        _restore_sink(prev)

    events = _sandbox_events(rec)
    assert len(events) == 1
    assert events[0]["event"] == "kill"
    assert events[0]["reason"] == "timeout"
    assert events[0]["backend"] == "process"


@pytest.mark.asyncio
async def test_backend_default_timeout_used_when_none_passed(tmp_path):
    """Regression: BashTool with no explicit timeout must use the backend's
    configured timeout, not a hardcoded 30s (sandbox.timeout_seconds must take
    effect)."""
    from agent.tools.sandbox.process_backend import ProcessBackend

    # A backend whose default timeout is tiny → `sleep 60` times out fast.
    tool = BashTool(
        policy=WorkspacePolicy(tmp_path),
        sandbox=ProcessBackend(timeout=0.2),
    )
    result = await tool.execute("sleep 60")
    data = json.loads(result.text)
    assert data["timed_out"] is True
    assert data["duration_ms"] < 5000
    assert result.error_type == "timeout"


@pytest.mark.asyncio
async def test_oom_killed_marks_resource_exhausted(tmp_path):
    """回归：Bash OOM（SandboxResult.oom_killed=True）打标 resource_exhausted。"""
    class OomSandbox:
        def is_available(self) -> bool:
            return True

        async def run(self, command, *, timeout=None, cwd=None) -> "SandboxResult":
            return SandboxResult(
                exit_code=-1,
                stdout="",
                stderr="memory limit exceeded",
                duration_ms=50.0,
                timed_out=False,
                oom_killed=True,
            )

        async def run_background(self, command, *, cwd=None):
            raise NotImplementedError

    tool = BashTool(
        policy=WorkspacePolicy(tmp_path),
        sandbox=OomSandbox(),  # type: ignore[arg-type]
    )
    result = await tool.execute("stress --vm 1")
    data = json.loads(result.text)
    assert data["oom_killed"] is True
    assert result.error_type == "resource_exhausted"


@pytest.mark.asyncio
async def test_background_unavailable_marks_unavailable(tmp_path):
    """回归：后台执行不可用（无 run_in_background_cb）打标 unavailable。"""
    tool = BashTool(policy=WorkspacePolicy(tmp_path))
    result = await tool.execute("sleep 60", run_in_background=True)
    assert "Background task execution is not available" in result.text
    assert result.error_type == "unavailable"
