"""Tests for the session timeline shaping and the TracingHook success fix.

Covers ``web.session.build_timeline_payload`` (desc sort, bar_pct, in-flight
filter, original index preservation) and the TracingHook ``after_tool_execute``
success semantics (``[Error`` / ``[Permission denied`` prefixes and non-string
results).
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from agent.hooks.builtin import TracingHook
from agent.hooks.builtin.tracing import ToolCallTrace
from agent.tools.base import ToolCall
from web.session import AgentSession, build_timeline_payload


def _session_with_hook(hook: TracingHook) -> AgentSession:
    agent = MagicMock()
    agent.hooks.hooks = [hook]
    return AgentSession("test-session", agent)


def test_timeline_sorts_desc_and_computes_bar_pct() -> None:
    hook = TracingHook()
    hook.calls = [
        ToolCallTrace("Bash", {"cmd": "sleep 1"}, duration_ms=1000.0, success=True),
        ToolCallTrace("Read", {"path": "a.py"}, duration_ms=250.0, success=False),
    ]
    payload = build_timeline_payload(_session_with_hook(hook))
    assert payload["session_id"] == "test-session"
    assert payload["total_calls"] == 2
    assert payload["max_duration_ms"] == 1000.0
    assert [c["tool_name"] for c in payload["calls"]] == ["Bash", "Read"]
    # Original execution order is preserved via ``index``.
    assert [c["index"] for c in payload["calls"]] == [0, 1]
    assert payload["calls"][0]["bar_pct"] == 100.0
    assert payload["calls"][1]["bar_pct"] == 25.0
    assert payload["calls"][1]["success"] is False
    assert payload["calls"][0]["arguments"] == {"cmd": "sleep 1"}


def test_timeline_filters_inflight_duration_zero() -> None:
    hook = TracingHook()
    hook.calls = [
        ToolCallTrace("Bash", {}, duration_ms=0.0, success=True),  # in-flight
        ToolCallTrace("Read", {}, duration_ms=500.0, success=True),
    ]
    payload = build_timeline_payload(_session_with_hook(hook))
    assert payload["total_calls"] == 1
    assert payload["calls"][0]["tool_name"] == "Read"
    assert payload["calls"][0]["index"] == 1  # original execution index


def test_timeline_no_calls() -> None:
    hook = TracingHook()
    payload = build_timeline_payload(_session_with_hook(hook))
    assert payload["total_calls"] == 0
    assert payload["calls"] == []
    assert payload["max_duration_ms"] == 0.0


def test_timeline_missing_hook_returns_empty() -> None:
    agent = MagicMock()
    agent.hooks.hooks = []  # no TracingHook
    session = AgentSession("test-session", agent)
    payload = build_timeline_payload(session)
    assert payload["total_calls"] == 0


def test_timeline_index_reflects_position_after_filter() -> None:
    hook = TracingHook()
    hook.calls = [
        ToolCallTrace("A", {}, duration_ms=0.0, success=True),   # filtered
        ToolCallTrace("B", {}, duration_ms=100.0, success=True),  # index 1
        ToolCallTrace("C", {}, duration_ms=50.0, success=True),   # index 2
    ]
    payload = build_timeline_payload(_session_with_hook(hook))
    assert [c["tool_name"] for c in payload["calls"]] == ["B", "C"]
    assert [c["index"] for c in payload["calls"]] == [1, 2]


# ---------------------------------------------------------------------------
# TracingHook success semantics (grill Decision 16)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tracing_hook_error_prefix_is_failure() -> None:
    hook = TracingHook()
    tc = ToolCall(id="1", name="Bash", arguments={})
    await hook.before_tool_execute(tc)
    await hook.after_tool_execute(tc, "[Error: boom]")
    assert hook.calls[0].success is False


@pytest.mark.asyncio
async def test_tracing_hook_permission_denied_is_failure() -> None:
    hook = TracingHook()
    tc = ToolCall(id="2", name="Bash", arguments={})
    await hook.before_tool_execute(tc)
    await hook.after_tool_execute(tc, "[Permission denied: /etc]")
    assert hook.calls[0].success is False


@pytest.mark.asyncio
async def test_tracing_hook_normal_text_is_success() -> None:
    hook = TracingHook()
    tc = ToolCall(id="3", name="Read", arguments={})
    await hook.before_tool_execute(tc)
    await hook.after_tool_execute(tc, "file content")
    assert hook.calls[0].success is True


@pytest.mark.asyncio
async def test_tracing_hook_list_result_is_success() -> None:
    hook = TracingHook()
    tc = ToolCall(id="4", name="Read", arguments={})
    await hook.before_tool_execute(tc)
    # Content-block list result must not raise AttributeError (grill Decision 16).
    await hook.after_tool_execute(tc, [{"type": "text", "text": "hi"}])
    assert hook.calls[0].success is True


@pytest.mark.asyncio
async def test_tracing_hook_get_summary_counts_permission_denied_as_failed() -> None:
    hook = TracingHook()
    for i, result in enumerate(
        ["ok", "[Error: x]", "[Permission denied: y]", "fine"]
    ):
        tc = ToolCall(id=f"s{i}", name="Bash", arguments={})
        await hook.before_tool_execute(tc)
        await hook.after_tool_execute(tc, result)
    summary = hook.get_summary()
    assert summary["failed"] == 2
    assert summary["successful"] == 2
