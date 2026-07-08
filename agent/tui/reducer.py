"""TUI event reducer and state model.

Textual widgets read this state and do not parse AgentLoop internals directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any


@dataclass(frozen=True)
class TranscriptEntry:
    """One transcript entry: user message, assistant message, or event marker."""

    role: str  # "user", "assistant", "event"
    content: str
    event_type: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def user(cls, content: str) -> TranscriptEntry:
        return cls(role="user", content=content)

    @classmethod
    def assistant(cls, content: str) -> TranscriptEntry:
        return cls(role="assistant", content=content)

    @classmethod
    def event(cls, event_type: str, content: str, **metadata: Any) -> TranscriptEntry:
        return cls(role="event", content=content, event_type=event_type, metadata=metadata)


@dataclass
class ToolEvent:
    """Renderable state for one tool call."""

    name: str
    status: str  # "running", "done", "error"
    arguments: dict[str, Any] = field(default_factory=dict)
    display: dict[str, Any] | None = None
    approval: dict[str, Any] | None = None


@dataclass
class TUIState:
    """Renderable TUI state produced by reduce_tui_state."""

    session_id: str = ""
    run_id: str | None = None
    current_mode: str = "build"
    transcript: list[TranscriptEntry] = field(default_factory=list)
    planning_state: dict[str, Any] | None = None
    planning_document: dict[str, Any] | None = None
    tool_events: list[ToolEvent] = field(default_factory=list)
    pending_approval: dict[str, Any] | None = None
    assistant_streaming: str = ""
    is_running: bool = False
    final_content: str | None = None
    stop_reason: str | None = None
    trace_path: str | None = None
    error_message: str | None = None

    def add_user_message(self, content: str) -> TUIState:
        """Append a user message to the transcript."""
        return replace(self, transcript=[*self.transcript, TranscriptEntry.user(content)])


def reduce_tui_state(state: TUIState, event_type: str, data: dict[str, Any]) -> TUIState:
    """Reduce one AgentLoop event into a new TUI state."""

    if event_type == "run_started":
        return _on_run_started(state, data)

    if event_type == "assistant_delta":
        return _on_assistant_delta(state, data)

    if event_type == "assistant_stream_complete":
        return _on_assistant_stream_complete(state, data)

    if event_type == "llm_response":
        return _on_llm_response(state, data)

    if event_type == "tool_call":
        return _on_tool_call(state, data)

    if event_type == "tool_result":
        return _on_tool_result(state, data)

    if event_type == "planning_state_updated":
        return replace(state, planning_state=data.get("items") is not None and data or data)

    if event_type in ("plan_document_updated", "plan_document_submitted"):
        return replace(state, planning_document=data)

    if event_type == "approval_request":
        return replace(state, pending_approval=data)

    if event_type == "approval_response":
        return replace(state, pending_approval=None)

    if event_type == "mode_changed":
        return replace(state, current_mode=data.get("new_mode", state.current_mode))

    if event_type == "done":
        return _on_done(state, data)

    if event_type == "error":
        error_msg = data.get("message", "unknown error")
        return replace(
            state,
            is_running=False,
            error_message=error_msg,
            transcript=[
                *state.transcript,
                TranscriptEntry.event("error", f"Error: {error_msg}"),
            ],
        )

    if event_type == "memory_compaction":
        return replace(
            state,
            transcript=[
                *state.transcript,
                TranscriptEntry.event(
                    "memory_compaction",
                    f"Memory compacted ({data.get('total_messages', 0)} messages)",
                    total_messages=data.get("total_messages", 0),
                ),
            ],
        )

    if event_type == "skill_activated":
        return replace(
            state,
            transcript=[
                *state.transcript,
                TranscriptEntry.event(
                    "skill_activated",
                    f"Skill activated: {data.get('skill_name', 'unknown')}",
                    skill_name=data.get("skill_name", ""),
                    source=data.get("source", ""),
                ),
            ],
        )

    return state


# ---------------------------------------------------------------------------
# private event handlers
# ---------------------------------------------------------------------------


def _on_run_started(state: TUIState, data: dict[str, Any]) -> TUIState:
    return replace(
        state,
        run_id=data.get("run_id"),
        current_mode=data.get("mode", state.current_mode),
        is_running=True,
        assistant_streaming="",
        final_content=None,
        stop_reason=None,
        tool_events=[],
        planning_state=None,
        planning_document=None,
        pending_approval=None,
        error_message=None,
    )


def _on_assistant_delta(state: TUIState, data: dict[str, Any]) -> TUIState:
    delta = data.get("delta", "")
    return replace(state, assistant_streaming=state.assistant_streaming + delta)


def _on_assistant_stream_complete(state: TUIState, data: dict[str, Any]) -> TUIState:
    content = data.get("content", state.assistant_streaming) or state.assistant_streaming
    return replace(
        state,
        assistant_streaming="",
        transcript=[
            *state.transcript,
            TranscriptEntry.assistant(content),
        ],
    )


def _on_llm_response(state: TUIState, data: dict[str, Any]) -> TUIState:
    streamed = data.get("streamed", False)
    content = data.get("content", "")
    if streamed:
        return replace(state, assistant_streaming="")
    if content:
        return replace(
            state,
            transcript=[
                *state.transcript,
                TranscriptEntry.assistant(content),
            ],
        )
    return state


def _on_tool_call(state: TUIState, data: dict[str, Any]) -> TUIState:
    event = ToolEvent(
        name=data.get("name", "unknown"),
        status="running",
        arguments=data.get("arguments", {}),
        approval=data.get("approval"),
    )
    return replace(state, tool_events=[*state.tool_events, event])


def _on_tool_result(state: TUIState, data: dict[str, Any]) -> TUIState:
    tool_name = data.get("name", "")
    display = data.get("display")
    updated: list[ToolEvent] = []
    for event in state.tool_events:
        if event.name == tool_name and event.status == "running":
            event = ToolEvent(
                name=event.name,
                status="done",
                arguments=event.arguments,
                display=display,
                approval=event.approval,
            )
        updated.append(event)
    return replace(state, tool_events=updated)


def _on_done(state: TUIState, data: dict[str, Any]) -> TUIState:
    return replace(
        state,
        is_running=False,
        final_content=data.get("content", ""),
        stop_reason=data.get("stop_reason", ""),
    )
