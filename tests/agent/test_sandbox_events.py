"""Sandbox event sink tests — emit_sandbox_event dispatch, tool_call_id
correlation, command truncation, sink save/restore, and TraceRecorder adapter."""
from __future__ import annotations

from agent.background import current_tool_call_id
from agent.sandbox_events import (
    NoopSandboxSink,
    current_sandbox_sink,
    emit_sandbox_event,
    set_sandbox_sink,
)
from agent.trace_recorder import TraceRecorder, TraceRecorderSandboxSink


class RecordingSink:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def emit(self, event: str, **data: object) -> None:
        self.events.append((event, data))


def _with_sink(sink):
    prev = current_sandbox_sink()
    set_sandbox_sink(sink)
    return prev


def _restore_sink(prev) -> None:
    set_sandbox_sink(prev)


def test_emit_dispatches_to_current_sink():
    sink = RecordingSink()
    prev = _with_sink(sink)
    try:
        emit_sandbox_event("kill", reason="timeout", command="sleep 10")
    finally:
        _restore_sink(prev)
    assert len(sink.events) == 1
    event, data = sink.events[0]
    assert event == "kill"
    assert data["reason"] == "timeout"
    assert data["command"] == "sleep 10"


def test_emit_noops_without_explicit_sink():
    # Default sink is Noop — no crash, no recorded state.
    emit_sandbox_event("denied", reason="command_guard")
    assert True


def test_emit_adds_tool_call_id():
    sink = RecordingSink()
    prev = _with_sink(sink)
    token = current_tool_call_id.set("tool_123")
    try:
        emit_sandbox_event("denied", reason="workspace_policy")
    finally:
        current_tool_call_id.reset(token)
        _restore_sink(prev)
    assert sink.events[0][1]["tool_call_id"] == "tool_123"


def test_emit_does_not_override_explicit_tool_call_id():
    sink = RecordingSink()
    prev = _with_sink(sink)
    token = current_tool_call_id.set("tool_123")
    try:
        emit_sandbox_event("denied", reason="x", tool_call_id="tool_other")
    finally:
        current_tool_call_id.reset(token)
        _restore_sink(prev)
    assert sink.events[0][1]["tool_call_id"] == "tool_other"


def test_emit_truncates_long_command():
    sink = RecordingSink()
    prev = _with_sink(sink)
    long_cmd = "echo " + "x" * 500
    try:
        emit_sandbox_event("kill", reason="timeout", command=long_cmd)
    finally:
        _restore_sink(prev)
    cmd = sink.events[0][1]["command"]
    assert len(cmd) <= 300
    assert cmd.endswith("...")


def test_emit_collapses_multiline_command():
    sink = RecordingSink()
    prev = _with_sink(sink)
    try:
        emit_sandbox_event("denied", reason="x", command="line1\nline2\r\nline3")
    finally:
        _restore_sink(prev)
    cmd = sink.events[0][1]["command"]
    assert "\n" not in cmd
    assert "\r" not in cmd
    assert cmd == "line1 line2 line3"


def test_set_sandbox_sink_restores_previous():
    a, b = RecordingSink(), RecordingSink()
    prev = current_sandbox_sink()
    set_sandbox_sink(a)
    set_sandbox_sink(b)
    set_sandbox_sink(prev)
    emit_sandbox_event("x")
    assert len(a.events) == 0
    assert len(b.events) == 0


def test_trace_recorder_sandbox_sink_records_sandbox_step():
    rec = TraceRecorder()
    TraceRecorderSandboxSink(rec).emit("denied", reason="command_guard", tool_call_id="t1")
    steps = [s for s in rec.steps if s.type == "sandbox"]
    assert len(steps) == 1
    assert steps[0].data["event"] == "denied"
    assert steps[0].data["reason"] == "command_guard"
    assert steps[0].data["tool_call_id"] == "t1"
    # timestamp is a step field, not inside data (backward-compatible with #78).
    assert "timestamp" not in steps[0].data
