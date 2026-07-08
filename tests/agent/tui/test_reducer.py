"""TUI event reducer / state model 测试。

消费工具事件、planning 事件、final/trace/test summary、assistant streaming、
done、mode_changed、approval 事件、skill_activated、memory_compaction 和
run_started，产出可渲染的 TUI 状态。
"""

import pytest

from agent.tui.reducer import TUIState, TranscriptEntry, ToolEvent, reduce_tui_state


def _initial_state(session_id: str = "session-1") -> TUIState:
    return TUIState(session_id=session_id)


# ---------------------------------------------------------------------------
# run_started
# ---------------------------------------------------------------------------

def test_run_started_sets_run_id_and_mode():
    state = _initial_state()
    new_state = reduce_tui_state(state, "run_started", {
        "mode": "build",
        "run_id": "run-1",
        "session_id": "session-1",
    })
    assert new_state.run_id == "run-1"
    assert new_state.current_mode == "build"
    assert new_state.is_running is True


def test_run_started_clears_previous_run_state():
    state = _initial_state()
    state.run_id = "run-old"
    state.assistant_streaming = "old content"
    state.final_content = "old final"
    state.tool_events = [ToolEvent(name="old", status="done")]
    state.planning_state = {"items": []}

    new_state = reduce_tui_state(state, "run_started", {
        "mode": "build",
        "run_id": "run-2",
    })
    assert new_state.run_id == "run-2"
    assert new_state.assistant_streaming == ""
    assert new_state.final_content is None
    assert new_state.tool_events == []
    assert new_state.stop_reason is None


# ---------------------------------------------------------------------------
# assistant_delta / assistant_stream_complete
# ---------------------------------------------------------------------------

def test_assistant_delta_appends_streaming_content():
    state = _initial_state()
    state = reduce_tui_state(state, "assistant_delta", {"delta": "Hel", "content": "Hel"})
    state = reduce_tui_state(state, "assistant_delta", {"delta": "lo", "content": "Hello"})
    assert state.assistant_streaming == "Hello"


def test_assistant_stream_complete_adds_transcript_entry():
    state = _initial_state()
    state = reduce_tui_state(state, "assistant_delta", {"delta": "Hi", "content": "Hi"})
    state = reduce_tui_state(state, "assistant_stream_complete", {
        "content": "Hi",
        "stop_reason": "end_turn",
    })
    assert len(state.transcript) == 1
    assert state.transcript[0].role == "assistant"
    assert state.transcript[0].content == "Hi"
    assert state.assistant_streaming == ""


# ---------------------------------------------------------------------------
# llm_response
# ---------------------------------------------------------------------------

def test_llm_response_adds_transcript_when_not_streamed():
    state = _initial_state()
    state = reduce_tui_state(state, "llm_response", {
        "content": "Hello from LLM",
        "stop_reason": "end_turn",
        "tool_calls": [],
    })
    assert len(state.transcript) == 1
    assert state.transcript[0].role == "assistant"
    assert state.transcript[0].content == "Hello from LLM"


def test_llm_response_streamed_does_not_duplicate_transcript():
    """streamed=True 时 assistant_stream_complete 已添加 transcript，llm_response 不应重复。"""
    state = _initial_state()
    state = reduce_tui_state(state, "assistant_delta", {"delta": "Hi"})
    state = reduce_tui_state(state, "assistant_stream_complete", {
        "content": "Hi",
        "stop_reason": "end_turn",
    })
    entry_count = len(state.transcript)
    state = reduce_tui_state(state, "llm_response", {
        "content": "Hi",
        "stop_reason": "end_turn",
        "tool_calls": [],
        "streamed": True,
    })
    assert len(state.transcript) == entry_count
    assert state.assistant_streaming == ""


# ---------------------------------------------------------------------------
# tool_call / tool_result
# ---------------------------------------------------------------------------

def test_tool_call_creates_pending_event():
    state = _initial_state()
    state = reduce_tui_state(state, "tool_call", {
        "name": "Read",
        "arguments": {"path": "/tmp/x"},
    })
    assert len(state.tool_events) == 1
    assert state.tool_events[0].name == "Read"
    assert state.tool_events[0].status == "running"


def test_tool_result_updates_event_and_adds_transcript():
    state = _initial_state()
    state = reduce_tui_state(state, "tool_call", {
        "name": "Read",
        "arguments": {"path": "/tmp/x"},
    })
    state = reduce_tui_state(state, "tool_result", {
        "name": "Read",
        "result": "file content here",
        "display": {
            "char_count": 17,
            "line_count": 1,
            "collapsed": False,
            "preview": "file content here",
        },
    })
    assert state.tool_events[0].status == "done"
    assert state.tool_events[0].display is not None
    assert state.tool_events[0].display["char_count"] == 17


def test_tool_result_with_approval_marks_approved():
    state = _initial_state()
    state = reduce_tui_state(state, "tool_call", {
        "name": "Bash",
        "arguments": {"cmd": "ls"},
        "approval": {"tool_name": "Bash", "approval_id": "a1"},
    })
    state = reduce_tui_state(state, "approval_request", {
        "approval_id": "a1",
        "tool_name": "Bash",
        "mode": "build",
    })
    state = reduce_tui_state(state, "tool_result", {
        "name": "Bash",
        "result": "ok",
        "display": {"char_count": 2, "line_count": 1, "collapsed": False, "preview": "ok"},
    })
    assert state.tool_events[0].status == "done"


# ---------------------------------------------------------------------------
# planning_state_updated
# ---------------------------------------------------------------------------

def test_planning_state_updated_stores_snapshot():
    state = _initial_state()
    snapshot = {"items": [{"id": "1", "content": "step 1", "status": "pending"}]}
    state = reduce_tui_state(state, "planning_state_updated", snapshot)
    assert state.planning_state == snapshot


# ---------------------------------------------------------------------------
# plan_document_updated / plan_document_submitted
# ---------------------------------------------------------------------------

def test_plan_document_updated_stores_document():
    state = _initial_state()
    doc = {"title": "Plan", "markdown": "# Plan", "status": "draft"}
    state = reduce_tui_state(state, "plan_document_updated", doc)
    assert state.planning_document == doc
    assert state.planning_document["status"] == "draft"


def test_plan_document_submitted_stores_document():
    state = _initial_state()
    doc = {"title": "Plan", "markdown": "# Plan", "status": "submitted"}
    state = reduce_tui_state(state, "plan_document_submitted", doc)
    assert state.planning_document == doc
    assert state.planning_document["status"] == "submitted"


# ---------------------------------------------------------------------------
# approval_request / approval_response
# ---------------------------------------------------------------------------

def test_approval_request_stores_pending():
    state = _initial_state()
    req_data = {
        "approval_id": "a1",
        "tool_name": "Bash",
        "mode": "build",
        "redacted_args": {"cmd": "ls"},
        "args_summary": '{"cmd":"ls"}',
        "reason": "high risk",
    }
    state = reduce_tui_state(state, "approval_request", req_data)
    assert state.pending_approval is not None
    assert state.pending_approval["approval_id"] == "a1"
    assert state.pending_approval["tool_name"] == "Bash"


def test_approval_response_clears_pending():
    state = _initial_state()
    state.pending_approval = {
        "approval_id": "a1",
        "tool_name": "Bash",
    }
    resp_data = {
        "approval_id": "a1",
        "tool_name": "Bash",
        "status": "approved",
        "reason": "approved by user",
    }
    state = reduce_tui_state(state, "approval_response", resp_data)
    assert state.pending_approval is None


# ---------------------------------------------------------------------------
# done
# ---------------------------------------------------------------------------

def test_done_sets_final_state():
    state = _initial_state()
    state = reduce_tui_state(state, "done", {
        "content": "final answer",
        "stop_reason": "end_turn",
    })
    assert state.is_running is False
    assert state.final_content == "final answer"
    assert state.stop_reason == "end_turn"


# ---------------------------------------------------------------------------
# mode_changed
# ---------------------------------------------------------------------------

def test_mode_changed_updates_current_mode():
    state = _initial_state()
    state.current_mode = "build"
    state = reduce_tui_state(state, "mode_changed", {
        "old_mode": "build",
        "new_mode": "read_only",
        "source": "tui",
    })
    assert state.current_mode == "read_only"


# ---------------------------------------------------------------------------
# memory_compaction
# ---------------------------------------------------------------------------

def test_memory_compaction_adds_event_transcript():
    state = _initial_state()
    state = reduce_tui_state(state, "memory_compaction", {"total_messages": 5})
    assert any(
        entry.role == "event" and "memory_compaction" in entry.event_type
        for entry in state.transcript
    )


# ---------------------------------------------------------------------------
# skill_activated
# ---------------------------------------------------------------------------

def test_skill_activated_adds_event_transcript():
    state = _initial_state()
    state = reduce_tui_state(state, "skill_activated", {
        "skill_name": "code-review",
        "source": "slash_command",
    })
    assert any(
        entry.role == "event" and "code-review" in entry.content
        for entry in state.transcript
    )


# ---------------------------------------------------------------------------
# user message (via add_user_message helper)
# ---------------------------------------------------------------------------

def test_add_user_message():
    state = _initial_state()
    state = state.add_user_message("hello world")
    assert len(state.transcript) == 1
    assert state.transcript[0].role == "user"
    assert state.transcript[0].content == "hello world"


def test_add_user_message_appends_to_existing():
    state = _initial_state()
    state = state.add_user_message("first")
    state = state.add_user_message("second")
    assert len(state.transcript) == 2
    assert state.transcript[1].content == "second"


# ---------------------------------------------------------------------------
# error event
# ---------------------------------------------------------------------------

def test_error_event_adds_transcript_and_stops():
    state = _initial_state()
    state.is_running = True
    state = reduce_tui_state(state, "error", {"message": "something went wrong"})
    assert any(
        entry.role == "event" and "error" in entry.content.lower()
        for entry in state.transcript
    )
    assert "something went wrong" in state.transcript[-1].content
    assert state.is_running is False
