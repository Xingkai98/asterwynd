"""BashTool sandbox-event emission tests (design.md Decision 6).

A sandbox event sink captures the events BashTool emits on workspace-policy
denials, command-guard denials, and backend timeout kills — with the calling
tool_call_id attached.
"""
from __future__ import annotations

import pytest

from agent.background import current_tool_call_id
from agent.sandbox_events import current_sandbox_sink, set_sandbox_sink
from agent.tools.builtin.bash import BashTool
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
        assert "Command denied" in result
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
        assert "Command denied" in result
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
        assert "timed_out" in result
    finally:
        _restore_sink(prev)

    events = _sandbox_events(rec)
    assert len(events) == 1
    assert events[0]["event"] == "kill"
    assert events[0]["reason"] == "timeout"
    assert events[0]["backend"] == "process"
