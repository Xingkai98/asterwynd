# tests/web/test_session.py
"""Unit tests for SessionManager and DebugHook with fake LLM."""
import asyncio
import os
import pytest
from unittest.mock import MagicMock

from agent.loop import AgentLoop
from agent.message import Message
from agent.llm import LLMResponse, ToolCallDelta
from agent.tools.base import Tool, tool_parameters
from agent.tools.registry import ToolRegistry
from agent.hooks.manager import HookManager
from agent.run_config import AgentMode
from agent.tool_permissions import ToolCapability, ToolPermission, ToolRiskLevel

from web.session import SessionManager, AgentSession, WebApprovalHandler
from web.debug_hook import DebugHook, debug_enabled
from tests.support.llm_harness import ScriptedLLM, stream_script


@tool_parameters(name="Echo", description="Echo tool", parameters={"type": "object", "properties": {}, "required": []})
class EchoTool(Tool):
    name = "Echo"
    description = "Echo tool"
    parameters = {}

    async def execute(self, **kwargs) -> str:
        return "echo!"


@tool_parameters(name="HighRisk", description="High risk", parameters={"type": "object", "properties": {}, "required": []})
class HighRiskTool(Tool):
    name = "HighRisk"
    description = "High risk"
    parameters = {}
    permission = ToolPermission(
        capabilities=frozenset({ToolCapability.COMMAND_EXECUTE}),
        risk_level=ToolRiskLevel.HIGH,
    )

    async def execute(self, **kwargs) -> str:
        return "approved high risk"


def make_session(agent):
    session = AgentSession("test-session", agent)
    session.init_messages()
    return session


@pytest.mark.asyncio
async def test_create_session():
    """Session manager creates a session with unique ID."""
    mock_llm = ScriptedLLM([LLMResponse(content="Hello")])
    manager = SessionManager()
    session = manager.create_session(mock_llm, tools=[EchoTool()])
    assert len(session.session_id) == 12
    assert session.messages[0].role == "system"


@pytest.mark.asyncio
async def test_create_session_uses_normalized_mode():
    """Session manager normalizes mode when constructing AgentLoop."""
    mock_llm = ScriptedLLM([LLMResponse(content="Hello")])
    manager = SessionManager(mode="read-only")
    session = manager.create_session(mock_llm, tools=[EchoTool()])

    assert session.agent.run_config.mode is AgentMode.READ_ONLY


@pytest.mark.asyncio
async def test_chat_simple_text_response():
    """Mock LLM returns text → run_session yields llm_response and done events."""
    mock_llm = ScriptedLLM([LLMResponse(content="Hello, user!")])
    manager = SessionManager()
    session = make_session(AgentLoop(
        llm=mock_llm, tool_registry=ToolRegistry(),
        hooks=HookManager(),
    ))

    events = []

    async def collect(e):
        events.append(e)

    await manager.run_session(session, "hi", ws_send=collect)

    event_types = [e["type"] for e in events]
    assert "run_started" in event_types
    assert "llm_response" in event_types
    assert "done" in event_types
    # Verify llm_response has content
    llm_resp = next(e for e in events if e["type"] == "llm_response")
    assert llm_resp["data"]["content"] == "Hello, user!"


@pytest.mark.asyncio
async def test_run_session_forwards_assistant_delta_and_streamed_response():
    manager = SessionManager()
    session = make_session(AgentLoop(
        llm=ScriptedLLM([stream_script("Hel", "lo")], stream=True),
        tool_registry=ToolRegistry(),
        hooks=HookManager(),
    ))

    events = []

    async def collect(e):
        events.append(e)

    await manager.run_session(session, "hi", ws_send=collect)

    event_types = [event["type"] for event in events]
    assert event_types == [
        "run_started",
        "assistant_delta",
        "assistant_delta",
        "assistant_stream_complete",
        "llm_response",
        "done",
    ]
    assert [event["data"].get("delta") for event in events if event["type"] == "assistant_delta"] == ["Hel", "lo"]
    llm_response = next(event for event in events if event["type"] == "llm_response")
    assert llm_response["data"]["streamed"] is True


@pytest.mark.asyncio
async def test_run_session_emits_error_event_when_agent_run_fails():
    manager = SessionManager()
    session = make_session(AgentLoop(
        llm=ScriptedLLM([RuntimeError("provider unavailable")]),
        tool_registry=ToolRegistry(),
        hooks=HookManager(),
    ))

    events = []

    async def collect(e):
        events.append(e)

    await manager.run_session(session, "hi", ws_send=collect)

    error = next(e for e in events if e["type"] == "error")
    done = events[-1]
    assert error["data"]["message"] == "RuntimeError: provider unavailable"
    assert done["type"] == "done"
    assert done["data"]["stop_reason"] == "error"


@pytest.mark.asyncio
async def test_run_session_forwards_planning_events():
    """Planning state updates are forwarded through the WebSocket event queue."""
    class PlanningLLM:
        def __init__(self):
            self.loop = None

        async def chat(self, messages, tools=None, model="gpt-4"):
            await self.loop.set_plan(["Read docs"])
            await self.loop.update_plan_item("item-1", "in_progress")
            return LLMResponse(content="planned")

    mock_llm = PlanningLLM()
    manager = SessionManager()
    agent = AgentLoop(
        llm=mock_llm,
        tool_registry=ToolRegistry(),
        hooks=HookManager(),
    )
    mock_llm.loop = agent
    session = make_session(agent)

    events = []

    async def collect(e):
        events.append(e)

    await manager.run_session(session, "hi", ws_send=collect)

    planning_events = [
        event for event in events
        if event["type"] == "planning_state_updated"
    ]
    assert len(planning_events) == 2
    assert planning_events[-1]["data"]["summary"]["current_item"]["id"] == "item-1"


@pytest.mark.asyncio
async def test_chat_with_tool_calls():
    """Mock LLM returns tool_calls → run_session yields tool events."""
    mock_llm = ScriptedLLM([
        LLMResponse(
            content=None,
            tool_calls=[ToolCallDelta(id="c1", name="Echo", arguments="{}")],
            stop_reason="tool_calls",
        ),
        LLMResponse(content="Done after tool", stop_reason="end_turn"),
    ])
    registry = ToolRegistry()
    registry.register(EchoTool())
    manager = SessionManager()
    session = make_session(AgentLoop(
        llm=mock_llm, tool_registry=registry, hooks=HookManager(),
    ))

    events = []

    async def collect(e):
        events.append(e)

    await manager.run_session(session, "echo test", ws_send=collect)

    event_types = [e["type"] for e in events]
    assert "llm_response" in event_types
    assert "tool_call" in event_types
    assert "tool_result" in event_types or any(
        e["type"] == "llm_response" and e["data"].get("tool_calls")
        for e in events
    )
    assert "done" in event_types


@pytest.mark.asyncio
async def test_run_session_accepts_web_approval_response_for_high_risk_tool():
    mock_llm = ScriptedLLM([
        LLMResponse(
            content=None,
            tool_calls=[ToolCallDelta(id="c1", name="HighRisk", arguments="{}")],
            stop_reason="tool_calls",
        ),
        LLMResponse(content="Done after tool", stop_reason="end_turn"),
    ])
    registry = ToolRegistry()
    registry.register(HighRiskTool())
    manager = SessionManager()
    agent = AgentLoop(
        llm=mock_llm,
        tool_registry=registry,
        hooks=HookManager(),
    )
    session = make_session(agent)
    agent.approval_handler = session.approval_handler
    events = []
    incoming = asyncio.Queue()

    async def collect(event):
        events.append(event)
        if event["type"] == "approval_request":
            await incoming.put({
                "type": "approval_response",
                "approval_id": event["data"]["approval_id"],
                "decision": "approved",
            })

    async def receive():
        return await incoming.get()

    await manager.run_session(
        session,
        "run high risk",
        ws_send=collect,
        ws_receive=receive,
    )

    event_types = [event["type"] for event in events]
    assert "approval_request" in event_types
    assert any(
        event["type"] == "approval_response"
        and event["data"]["status"] == "approved"
        for event in events
    )
    tool_result = next(event for event in events if event["type"] == "tool_result")
    assert tool_result["data"]["result"] == "approved high risk"


@pytest.mark.asyncio
async def test_web_approval_handler_isolates_sessions():
    first = WebApprovalHandler("session-1")
    second = WebApprovalHandler("session-2")
    request = _web_approval_request("approval-1")

    pending = asyncio.create_task(first.request_approval(request))
    await asyncio.sleep(0)

    assert second.submit_response("approval-1", "approved") is False
    assert first.submit_response("approval-1", "approved") is True
    response = await pending
    assert response.status.value == "approved"


@pytest.mark.asyncio
async def test_web_approval_handler_fail_pending_returns_unavailable():
    handler = WebApprovalHandler("session-1")
    pending = asyncio.create_task(handler.request_approval(_web_approval_request("approval-1")))
    await asyncio.sleep(0)

    handler.fail_pending("session reset")
    response = await pending

    assert response.status.value == "unavailable"
    assert response.reason == "session reset"


def _web_approval_request(approval_id: str):
    from agent.approval import ApprovalRequest

    return ApprovalRequest(
        approval_id=approval_id,
        tool_call_id="call-1",
        tool_name="HighRisk",
        mode="build",
        capability=["command_execute"],
        risk="high",
        origin="builtin",
        reason="test",
        profile_name="build_default",
        redacted_args={},
        args_summary="{}",
        session_id="session-1",
        run_id="run-1",
    )


@pytest.mark.asyncio
async def test_tool_result_event_includes_display_metadata_for_long_result():
    @tool_parameters(name="LongTool", description="Long tool", parameters={"type": "object", "properties": {}, "required": []})
    class LongTool(Tool):
        name = "LongTool"
        description = "Long tool"
        parameters = {}

        async def execute(self, **kwargs) -> str:
            return "x" * 5000

    mock_llm = ScriptedLLM([
        LLMResponse(
            content=None,
            tool_calls=[ToolCallDelta(id="c1", name="LongTool", arguments="{}")],
            stop_reason="tool_calls",
        ),
        LLMResponse(content="Done after tool", stop_reason="end_turn"),
    ])
    registry = ToolRegistry()
    registry.register(LongTool())
    manager = SessionManager()
    session = make_session(AgentLoop(
        llm=mock_llm, tool_registry=registry, hooks=HookManager(),
    ))

    events = []

    async def collect(e):
        events.append(e)

    await manager.run_session(session, "long test", ws_send=collect)

    tool_result = next(e for e in events if e["type"] == "tool_result")
    display = tool_result["data"]["display"]
    assert tool_result["data"]["result"] == "x" * 5000
    assert display["collapsed"] is True
    assert display["char_count"] == 5000
    assert display["preview"] == "x" * 1200


@pytest.mark.asyncio
async def test_chat_max_iterations():
    """Loop stops at max_iterations."""
    mock_llm = ScriptedLLM([
        LLMResponse(
            content=None,
            tool_calls=[ToolCallDelta(id="c1", name="Echo", arguments="{}")],
            stop_reason="tool_calls",
        ),
    ] * 10)
    registry = ToolRegistry()
    registry.register(EchoTool())
    agent = AgentLoop(
        llm=mock_llm, tool_registry=registry, hooks=HookManager(),
        max_iterations=2,
    )
    session = make_session(agent)

    events = []

    async def collect(e):
        events.append(e)

    manager = SessionManager()
    await manager.run_session(session, "test", ws_send=collect)

    done_events = [e for e in events if e["type"] == "done"]
    assert len(done_events) == 1
    assert done_events[0]["data"]["stop_reason"] == "max_iterations"


@pytest.mark.asyncio
async def test_session_message_history():
    """Messages accumulate correctly across turns."""
    mock_llm = ScriptedLLM([LLMResponse(content="Response 1"), LLMResponse(content="Response 2")])
    manager = SessionManager()
    session = make_session(AgentLoop(
        llm=mock_llm, tool_registry=ToolRegistry(), hooks=HookManager(),
    ))

    async def collect(e):
        pass

    await manager.run_session(session, "msg 1", ws_send=collect)
    assert len([m for m in session.messages if m.role == "user"]) >= 1

    await manager.run_session(session, "msg 2", ws_send=collect)
    user_msgs = [m for m in session.messages if m.role == "user"]
    assert len(user_msgs) >= 2


@pytest.mark.asyncio
async def test_session_messages_include_assistant_response():
    """run_session 后 session.messages 应包含 assistant 最终回复。
    Regression test for: loop.py 返回前未 append 导致多轮对话失忆。
    """
    mock_llm = ScriptedLLM([LLMResponse(content="Response 1")])
    manager = SessionManager()
    session = make_session(AgentLoop(
        llm=mock_llm, tool_registry=ToolRegistry(), hooks=HookManager(),
    ))

    async def collect(e):
        pass

    await manager.run_session(session, "msg 1", ws_send=collect)

    assistant_msgs = [m for m in session.messages if m.role == "assistant"]
    assert len(assistant_msgs) >= 1, "assistant response should be in session.messages"
    assert assistant_msgs[-1].content == "Response 1"


@pytest.mark.asyncio
async def test_session_message_history_with_tool():
    """多轮对话含工具调用时，assistant 回复应完整记录。"""
    mock_llm = ScriptedLLM([
        LLMResponse(
            content=None,
            tool_calls=[ToolCallDelta(id="c1", name="Echo", arguments="{}")],
            stop_reason="tool_calls",
        ),
        LLMResponse(content="Done after tool", stop_reason="end_turn"),
        LLMResponse(content="Second response", stop_reason="end_turn"),
    ])
    registry = ToolRegistry()
    registry.register(EchoTool())
    manager = SessionManager()
    session = make_session(AgentLoop(
        llm=mock_llm, tool_registry=registry, hooks=HookManager(),
    ))

    async def collect(e):
        pass

    await manager.run_session(session, "echo test", ws_send=collect)
    await manager.run_session(session, "second msg", ws_send=collect)

    assistant_msgs = [m for m in session.messages if m.role == "assistant"]
    assert len(assistant_msgs) >= 2, f"Expected >=2 assistant msgs, got {len(assistant_msgs)}"
    assert assistant_msgs[-1].content == "Second response"


@pytest.mark.asyncio
async def test_debug_events_emitted():
    """DebugHook emits structured debug events when enabled."""
    mock_llm = ScriptedLLM([LLMResponse(content="Hello")])
    manager = SessionManager(debug_enabled=True)
    session = make_session(AgentLoop(
        llm=mock_llm, tool_registry=ToolRegistry(), hooks=HookManager(),
    ))

    events = []

    async def collect(e):
        events.append(e)

    await manager.run_session(session, "hi", ws_send=collect)

    debug_events = [e for e in events if e["type"] == "debug"]
    phases = [e["phase"] for e in debug_events]
    assert "before_iteration" in phases
    assert "after_llm_call" in phases
    assert "on_completion" in phases


@pytest.mark.asyncio
async def test_debug_events_contain_full_messages():
    """before_iteration event contains the full message snapshot."""
    mock_llm = ScriptedLLM([LLMResponse(content="Hello")])
    manager = SessionManager(debug_enabled=True)
    session = make_session(AgentLoop(
        llm=mock_llm, tool_registry=ToolRegistry(), hooks=HookManager(),
    ))

    events = []

    async def collect(e):
        events.append(e)

    await manager.run_session(session, "hi", ws_send=collect)

    before_iter = [e for e in events if e["type"] == "debug" and e["phase"] == "before_iteration"]
    assert len(before_iter) >= 1
    msgs = before_iter[0]["data"]["messages"]
    assert len(msgs) >= 2  # system + user
    for msg in msgs:
        assert "role" in msg
        assert "content" in msg
    system_msgs = [m for m in msgs if m["role"] == "system"]
    assert len(system_msgs) >= 1
    assert len(system_msgs[0]["content"]) > 0


@pytest.mark.asyncio
async def test_debug_events_include_incrementing_turns_across_chat_runs():
    mock_llm = ScriptedLLM([LLMResponse(content="One"), LLMResponse(content="Two")])
    manager = SessionManager(debug_enabled=True)
    session = make_session(AgentLoop(
        llm=mock_llm, tool_registry=ToolRegistry(), hooks=HookManager(),
    ))

    events = []

    async def collect(e):
        events.append(e)

    await manager.run_session(session, "first", ws_send=collect)
    await manager.run_session(session, "second", ws_send=collect)

    before_iter_events = [
        e for e in events
        if e["type"] == "debug" and e["phase"] == "before_iteration"
    ]
    assert [e["turn"] for e in before_iter_events] == [1, 2]
    assert [e["iteration"] for e in before_iter_events] == [0, 0]


@pytest.mark.asyncio
async def test_debug_disabled_no_events():
    """When debug is disabled, no debug events are emitted."""
    mock_llm = ScriptedLLM([LLMResponse(content="Hello")])
    manager = SessionManager(debug_enabled=False)
    session = make_session(AgentLoop(
        llm=mock_llm, tool_registry=ToolRegistry(), hooks=HookManager(),
    ))

    events = []

    async def collect(e):
        events.append(e)

    await manager.run_session(session, "hi", ws_send=collect)

    debug_events = [e for e in events if e["type"] == "debug"]
    assert len(debug_events) == 0


@pytest.mark.asyncio
async def test_debug_hook_standalone():
    """DebugHook correctly captures iteration state as a standalone Hook."""
    events = []

    def emit(e):
        events.append(e)

    hook = DebugHook(emit=emit)
    assert hook._enabled == debug_enabled()

    messages = [Message(role="system", content="test prompt"), Message(role="user", content="hello")]
    await hook.before_iteration(0, messages)
    assert len(events) >= (1 if hook._enabled else 0)

    if hook._enabled:
        assert events[0]["phase"] == "before_iteration"
        assert events[0]["data"]["messages"][0]["content"] == "test prompt"


def test_debug_enabled_with_env():
    """debug_enabled() respects ASTERWYND_DEBUG env var."""
    # Save
    old = os.environ.get("ASTERWYND_DEBUG", "")
    try:
        os.environ["ASTERWYND_DEBUG"] = "enabled"
        assert debug_enabled() is True
        os.environ["ASTERWYND_DEBUG"] = "1"
        assert debug_enabled() is True
        os.environ["ASTERWYND_DEBUG"] = "true"
        assert debug_enabled() is True
        os.environ["ASTERWYND_DEBUG"] = "0"
        assert debug_enabled() is False
        del os.environ["ASTERWYND_DEBUG"]
        assert debug_enabled() is False
    finally:
        os.environ["ASTERWYND_DEBUG"] = old
