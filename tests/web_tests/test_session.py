# tests/web/test_session.py
"""Unit tests for SessionManager and DebugHook with fake LLM."""
import asyncio
import os
import pytest
from unittest.mock import MagicMock

from agent.approval import ApprovalDecisionStatus
from agent.loop import AgentLoop
from agent.message import Message
from agent.llm import LLMResponse, ToolCallDelta
from agent.tools.base import Tool, tool_parameters
from agent.tools.registry import ToolRegistry
from agent.hooks.manager import HookManager
from agent.run_config import AgentMode
from agent.tool_permissions import ToolCapability, ToolPermission, ToolRiskLevel

from web.session import (
    AgentSession,
    ConnectionHandle,
    SessionManager,
    WebApprovalHandler,
)
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
    # System prompt is now injected dynamically by ContextBuilder at LLM call
    # time, not stored as a static message in session.messages.
    assert session.messages == []


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
    # before_iteration now fires with contextualized messages (including
    # ContextBuilder output: SystemPrompt, ASTER.md, memory, skills, etc.).
    assert len(msgs) >= 2  # system (context block) + user
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


@pytest.mark.asyncio
async def test_run_session_survives_ws_send_failure_after_disconnect():
    """ws 关闭后 ws_send 抛异常时，run_session 应正常返回、不抛、不悬空（issue #193）。

    新语义（change web-reconnect-pending-interaction D3/D9）：send 失败不再 ``break``
    掉 drain，而是只摘掉该连接——run **继续跑完**，agent 调用次数与无断连时一致，
    run 正常结束后释放锁。断言从「断连即收尾」升级为「断连不打断 run」。
    """
    mock_llm = ScriptedLLM([
        stream_script(LLMResponse(content="Hello, user!", stop_reason="end_turn")),
    ])
    manager = SessionManager()
    registry = ToolRegistry()
    session = AgentSession(
        session_id="ws-disconnect",
        agent=AgentLoop(
            llm=mock_llm,
            tool_registry=registry,
            hooks=HookManager(),
        ),
        approval_handler=WebApprovalHandler("ws-disconnect"),
        question_handler=None,
    )
    session.init_messages()

    sent = []

    async def fail_after_first(event):
        sent.append(event)
        raise RuntimeError("Unexpected ASGI message 'websocket.send'")

    # 不应抛异常：ws_send 失败应被吞掉，run 继续跑到 sentinel 后正常收尾。
    await manager.run_session(session, "hi", ws_send=fail_after_first)

    assert len(sent) >= 1
    # run 正常跑完（未被断连打断）：agent 走完了脚本里的全部调用。
    assert mock_llm.call_count == 1
    # 正常结束（未悬空）：锁已释放，可再次 run。
    assert not session.run_lock.locked()
    # 失败的连接已被摘掉，不残留在出口上。
    assert session.event_channel.handles == ()


@pytest.mark.asyncio
async def test_run_session_continues_after_send_failure_and_broadcasts_to_survivor():
    """一条连接 send 失败不影响另一条：run 继续跑并把后续事件广播给存活连接。"""
    mock_llm = ScriptedLLM([
        stream_script(LLMResponse(content="Hello, user!", stop_reason="end_turn")),
    ])
    manager = SessionManager()
    session = AgentSession(
        session_id="ws-multi",
        agent=AgentLoop(llm=mock_llm, tool_registry=ToolRegistry(), hooks=HookManager()),
        approval_handler=WebApprovalHandler("ws-multi"),
        question_handler=None,
    )
    session.init_messages()

    survivor_events: list[dict] = []

    async def dead_send(event):
        raise RuntimeError("Unexpected ASGI message 'websocket.send'")

    async def survivor_send(event):
        survivor_events.append(event)

    # 死连接先绑定；run_session 的 ``handle`` 指向它，但广播会同时投给存活连接。
    dead_handle = session.event_channel.attach(ConnectionHandle(dead_send, label="dead"))
    session.event_channel.attach(ConnectionHandle(survivor_send, label="survivor"))

    await manager.run_session(session, "hi", ws_receive=None, handle=dead_handle)

    assert mock_llm.call_count == 1
    assert not session.run_lock.locked()
    # 死连接被摘掉，存活连接完整收到 run 的事件流。
    assert [h.label for h in session.event_channel.handles] == ["survivor"]
    assert any(e["type"] == "done" for e in survivor_events), survivor_events


@pytest.mark.asyncio
async def test_drain_keeps_consuming_after_all_connections_detached():
    """drain 永远消费 queue（M2）：没有观察者时事件被丢弃，run 仍跑到收尾。

    审阅 Issue 3 修正：原版用 ``ScriptedLLM`` 一口气跑完，断言对「drain 是否提前
    退出」不敏感（把 drain 改回「无观察者即 break」测试照样绿）。这里从**第一条事件
    起**出口就是空的（run_session 不传 ws_send/handle），并且 LLM 会阻塞到测试放行——
    提前退出的 drain 会在 run_started 处 break 并 cancel 掉 agent_task，run 就永远
    到不了 ``finished``。
    """
    release = asyncio.Event()
    llm = _GatedLLM(release)
    manager = SessionManager()
    session = AgentSession(
        session_id="ws-nobody",
        agent=AgentLoop(llm=llm, tool_registry=ToolRegistry(), hooks=HookManager()),
        approval_handler=WebApprovalHandler("ws-nobody"),
        question_handler=None,
    )
    session.init_messages()
    assert session.event_channel.handles == ()

    run_task = asyncio.create_task(manager.run_session(session, "hi"))
    # run 已经开始（agent_task 已被调度、锁已持有）但还没跑完。
    await asyncio.wait_for(llm.started.wait(), timeout=2.0)
    assert session.run_lock.locked()
    assert not llm.finished.is_set()

    release.set()
    await asyncio.wait_for(run_task, timeout=5.0)

    # run 跑完了：drain 没有因为「没人收」就退出并 cancel 掉 agent_task。
    assert llm.finished.is_set(), "drain 在无观察者时提前退出，run 被打断"
    assert llm.call_count == 1
    assert not session.run_lock.locked()


@pytest.mark.asyncio
async def test_event_channel_broadcast_without_connections_is_noop():
    """出口没有绑定连接时广播是安全空操作（run 不在且无人连接时不得报错）。"""
    from web.session import SessionEventChannel

    channel = SessionEventChannel("s-empty")
    assert await channel.broadcast({"type": "done"}) == 0
    assert await channel.send_to(None, {"type": "done"}) is False


@pytest.mark.asyncio
async def test_event_channel_detach_one_keeps_others():
    """摘掉一条连接不影响其他连接继续收事件（D7）。"""
    from web.session import ConnectionHandle, SessionEventChannel

    channel = SessionEventChannel("s-multi")
    first_seen: list[dict] = []
    second_seen: list[dict] = []

    async def first_send(event):
        first_seen.append(event)

    async def second_send(event):
        second_seen.append(event)

    first = channel.attach(ConnectionHandle(first_send, label="first"))
    channel.attach(ConnectionHandle(second_send, label="second"))
    await channel.broadcast({"type": "a"})
    first.detach()
    await channel.broadcast({"type": "b"})

    assert [e["type"] for e in first_seen] == ["a"]
    assert [e["type"] for e in second_seen] == ["a", "b"]
    assert len(channel) == 1


@pytest.mark.asyncio
async def test_receive_disconnect_does_not_fail_pending():
    """断连（ws_receive 抛异常）不再 fail_pending（D2）。"""
    manager = SessionManager()
    session = AgentSession(
        session_id="ws-pending",
        agent=AgentLoop(
            llm=ScriptedLLM([LLMResponse(content="ok")]),
            tool_registry=ToolRegistry(),
            hooks=HookManager(),
        ),
    )
    session.init_messages()

    request = _web_approval_request("approval-1")
    pending = asyncio.create_task(session.approval_handler.request_approval(request))
    await asyncio.sleep(0)

    async def broken_receive():
        raise RuntimeError("websocket disconnected")

    await manager._receive_interactions(
        session, broken_receive, session.event_channel, None
    )

    # pending 仍然有效：future 未 resolve，可补发、可作答。
    assert session.approval_handler.pending_approval_id == "approval-1"
    assert session.approval_handler.submit_response("approval-1", "approved") is True
    assert (await pending).status is ApprovalDecisionStatus.APPROVED


@pytest.mark.asyncio
async def test_reset_during_run_fails_pending_but_run_continues():
    """D8：run 期间 reset 立即失败 pending，但不会终止 run（run 仍跑完、锁仍释放）。"""
    class GatedLLM(ScriptedLLM):
        """第一次调用卡在 gate 上，让「run 仍在执行」成为确定状态而不是抢时序。"""

        def __init__(self, responses):
            super().__init__(responses)
            self.gate = asyncio.Event()
            self.started = asyncio.Event()

        async def chat(self, messages, tools=None, model="gpt-4"):
            self.started.set()
            await self.gate.wait()
            return await super().chat(messages, tools, model)

    mock_llm = GatedLLM([LLMResponse(content="finished anyway", stop_reason="end_turn")])
    manager = SessionManager()
    session = AgentSession(
        session_id="ws-reset",
        agent=AgentLoop(llm=mock_llm, tool_registry=ToolRegistry(), hooks=HookManager()),
    )
    session.init_messages()

    incoming: asyncio.Queue = asyncio.Queue()

    async def receive():
        return await incoming.get()

    run_task = asyncio.create_task(
        manager.run_session(session, "hi", ws_receive=receive)
    )
    await asyncio.wait_for(mock_llm.started.wait(), timeout=2.0)
    assert session.run_lock.locked()

    # run 期间建立 pending，再投 reset：pending 立即失败（既有语义）。
    request = _web_approval_request("approval-reset")
    pending = asyncio.create_task(session.approval_handler.request_approval(request))
    await asyncio.sleep(0)
    await incoming.put({"type": "reset"})
    response = await asyncio.wait_for(pending, timeout=1.0)
    assert response.status is ApprovalDecisionStatus.UNAVAILABLE
    assert response.reason == "reset received"

    mock_llm.gate.set()
    await asyncio.wait_for(run_task, timeout=5.0)
    # run 没有被 reset 终止：跑完并释放锁。
    assert mock_llm.call_count == 1
    assert not session.run_lock.locked()


# ---------------------------------------------------------------------------
# pending 交互跨连接存活（change web-reconnect-pending-interaction, tasks 1.x/5.1）
# ---------------------------------------------------------------------------


def _web_question(question_id: str = "q-1") -> "Question":
    from agent.question import Question

    return Question(
        question_id=question_id,
        title="选择分支",
        body="要走哪条路？",
        options=["a", "b"],
    )


@pytest.mark.asyncio
async def test_web_approval_handler_keeps_replayable_payload():
    """tasks 1.2：pending 审批保留 ``to_event_data()`` 载荷，访问器一次返回 (id, payload)。"""
    handler = WebApprovalHandler("session-1")
    request = _web_approval_request("approval-1")
    pending = asyncio.create_task(handler.request_approval(request))
    await asyncio.sleep(0)

    snapshot = handler.pending_approval_payload()
    assert snapshot is not None
    approval_id, payload = snapshot
    assert approval_id == "approval-1"
    assert payload == request.to_event_data()

    handler.submit_response("approval-1", "approved")
    await pending
    # 作答后（future 已 done）不再处于 pending 集合 → 不补发。
    assert handler.pending_approval_payload() is None


@pytest.mark.asyncio
async def test_web_question_handler_keeps_replayable_payload():
    """tasks 1.1：pending 提问保留载荷；访问器原子返回 (question_id, payload)。"""
    from web.session import WebQuestionHandler

    handler = WebQuestionHandler("session-1")
    question = _web_question("q-1")
    pending = asyncio.create_task(handler.ask_question(question))
    await asyncio.sleep(0)

    snapshot = handler.pending_question_payload()
    assert snapshot is not None
    question_id, payload = snapshot
    assert question_id == "q-1"
    assert payload == question.to_event_data()

    handler.submit_answer("q-1", "a")
    await pending
    assert handler.pending_question_payload() is None


@pytest.mark.asyncio
async def test_pending_payload_accessors_return_none_when_idle():
    """无 pending 时访问器返回 None（防补发凭空造卡片）。"""
    from web.session import WebQuestionHandler

    assert WebApprovalHandler("s").pending_approval_payload() is None
    assert WebQuestionHandler("s").pending_question_payload() is None


@pytest.mark.asyncio
async def test_web_approval_handler_times_out_fail_closed():
    """tasks 1.3：审批超时一律 fail-closed（UNAVAILABLE），不再无限等待（Q1）。"""
    handler = WebApprovalHandler("session-1", timeout_seconds=0.05)

    response = await handler.request_approval(_web_approval_request("approval-1"))

    assert response.approval_id == "approval-1"
    assert response.status is ApprovalDecisionStatus.UNAVAILABLE
    assert "timed out" in response.reason
    # 超时后槽位释放，下一个审批可以建立。
    assert handler.pending_approval_payload() is None


@pytest.mark.asyncio
async def test_web_question_handler_times_out():
    """tasks 1.3：提问超时走配置值，返回 [Error: ... timed out ...]。"""
    from web.session import WebQuestionHandler

    handler = WebQuestionHandler("session-1", timeout_seconds=0.05)

    answer = await handler.ask_question(_web_question("q-1"))

    assert answer.question_id == "q-1"
    assert answer.answer.startswith("[Error:")
    assert "timed out" in answer.answer
    assert handler.pending_question_payload() is None


@pytest.mark.asyncio
async def test_handler_timeout_does_not_reset_on_disconnect():
    """tasks 1.3 / 5.1：超时是「总等待时长」，连接断开不重置计时。

    用「先等一段时间再重连/无重连」的最短路径固化：pending 建立后即使没人作答，
    到期即失败，不会因为「期间发生过一次未知的断连」而延长。
    """
    handler = WebApprovalHandler("session-1", timeout_seconds=0.05)
    pending = asyncio.create_task(handler.request_approval(_web_approval_request("approval-1")))
    await asyncio.sleep(0.02)
    # 断连语义在这个 change 里退化为「什么都不做」（不 fail、不重置计时）。
    await asyncio.sleep(0.05)

    response = await pending
    assert response.status is ApprovalDecisionStatus.UNAVAILABLE

class _GatedLLM(ScriptedLLM):
    """在 run 中途阻塞的 LLM：把「run 仍在执行」变成确定状态而不是抢时序。"""

    def __init__(self, release: asyncio.Event, response: str = "finished"):
        super().__init__([LLMResponse(content=response, stop_reason="end_turn")])
        self._release = release
        self.started = asyncio.Event()
        self.finished = asyncio.Event()

    async def chat(self, messages, tools=None, model="gpt-4"):
        self.started.set()
        await self._release.wait()
        response = await super().chat(messages, tools, model)
        self.finished.set()
        return response
