"""Sandbox event emission — a neutral seam between sandbox execution and the
trace layer.

The command guard and execution backends emit structured sandbox events
(``denied`` / ``kill`` / ``oom`` / ``degraded``) without knowing who consumes
them. A contextvar holds the active ``SandboxEventSink`` for the current run
(set by ``AgentLoop.run`` when a ``TraceRecorder`` is active), and
``emit_sandbox_event`` dispatches to it. This keeps tools/backends (built once
at startup) decoupled from the per-run trace recorder.

Events carry the calling tool's ``tool_call_id`` (read from the existing
contextvar in ``agent.background``) and a command truncated to a bounded length,
so parallel/background executions can be correlated in a trace.

``emit`` must be non-blocking — it is invoked from async execution paths and
must never do I/O.
"""
from __future__ import annotations

from contextvars import ContextVar
from typing import Any, Protocol

MAX_COMMAND_LEN = 300


class SandboxEventSink(Protocol):
    def emit(self, event: str, **data: Any) -> None:
        """Record a sandbox event. MUST be non-blocking (no I/O in adapter)."""


class NoopSandboxSink:
    def emit(self, event: str, **data: Any) -> None:
        pass


_NOOP = NoopSandboxSink()
_current_sink: ContextVar[SandboxEventSink] = ContextVar(
    "sandbox_event_sink", default=_NOOP
)


def current_sandbox_sink() -> SandboxEventSink:
    return _current_sink.get()


def set_sandbox_sink(sink: SandboxEventSink) -> None:
    """Set the active sink for the current execution context.

    Callers are responsible for save/restore (mirror the loop's
    ``_active_trace_recorder`` pattern) so nested runs and runs without a
    recorder do not leak events into the wrong trace.
    """
    _current_sink.set(sink)


def _truncate_command(command: str, max_len: int = MAX_COMMAND_LEN) -> str:
    """Collapse whitespace/newlines and cap the command at ``max_len`` chars."""
    collapsed = " ".join(command.split())
    if len(collapsed) <= max_len:
        return collapsed
    return collapsed[: max_len - 3] + "..."


def emit_sandbox_event(event: str, **data: Any) -> None:
    """Emit a structured sandbox event to the current sink (no-op by default).

    Attaches the calling tool's ``tool_call_id`` and truncates a ``command``
    field if present. The sink lookup is contextual, so a shared backend
    emitting from any run/background task lands in that execution's recorder.
    """
    # Deferred import avoids a cycle: agent.background imports agent.tools.sandbox,
    # whose backends import this module.
    from agent.background import current_tool_call_id

    tool_call_id = current_tool_call_id.get()
    if tool_call_id:
        data.setdefault("tool_call_id", tool_call_id)
    command = data.get("command")
    if isinstance(command, str):
        data["command"] = _truncate_command(command)
    current_sandbox_sink().emit(event, **data)
