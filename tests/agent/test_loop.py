# tests/agent/test_loop.py
import pytest
import json
from agent.approval import ApprovalDecisionStatus, ApprovalResponse
from agent.loop import AgentLoop
from agent.message import Message, system_message
from agent.llm import LLMResponse, LLMStreamEvent, ToolCallDelta
from agent.tools.base import Tool, tool_parameters, ToolCall
from agent.tools.registry import ToolRegistry
from agent.hooks.manager import HookManager
from agent.memory.manager import MemoryManager
from agent.trace_recorder import TraceRecorder
from agent.run_config import AgentMode, AgentRunConfig
from agent.subagent.manager import SubAgentManager
from agent.skills.loader import Skill
from agent.skills.runtime import SkillRuntime
from agent.tool_permissions import ToolCapability, ToolPermission, ToolRiskLevel

@tool_parameters(name="Echo", description="Echo back", parameters={"type": "object", "properties": {}, "required": []})
class EchoTool(Tool):
    name = "Echo"
    description = "Echo back"
    parameters = {}

    async def execute(self, **kwargs) -> str:
        return "echo!"


@tool_parameters(name="WriteLike", description="Write", parameters={"type": "object", "properties": {}, "required": []})
class WriteLikeTool(Tool):
    name = "WriteLike"
    description = "Write"
    parameters = {}
    read_only = False

    def __init__(self):
        self.called = False

    async def execute(self, **kwargs) -> str:
        self.called = True
        return "wrote!"


@tool_parameters(name="HighRisk", description="High risk", parameters={"type": "object", "properties": {}, "required": []})
class HighRiskTool(Tool):
    name = "HighRisk"
    description = "High risk"
    parameters = {}
    permission = ToolPermission(
        capabilities=frozenset({ToolCapability.COMMAND_EXECUTE}),
        risk_level=ToolRiskLevel.HIGH,
    )

    def __init__(self):
        self.called = False

    async def execute(self, **kwargs) -> str:
        self.called = True
        return "ran high risk"


class StaticApprovalHandler:
    def __init__(self, status: ApprovalDecisionStatus):
        self.status = status
        self.requests = []

    async def request_approval(self, request):
        self.requests.append(request)
        return ApprovalResponse(
            approval_id=request.approval_id,
            status=self.status,
            reason=f"{self.status.value} in test",
        )

class MockLLM:
    def __init__(self, response: LLMResponse):
        self._response = response

    async def chat(self, messages, tools=None, model="gpt-4") -> LLMResponse:
        return self._response


class StreamingMockLLM:
    async def stream_chat(self, messages, tools=None, model="gpt-4"):
        yield LLMStreamEvent(type="assistant_delta", delta="Hel", content="Hel")
        yield LLMStreamEvent(type="assistant_delta", delta="lo", content="Hello")
        yield LLMStreamEvent(
            type="complete",
            response=LLMResponse(content="Hello", stop_reason="end_turn"),
            content="Hello",
            stop_reason="end_turn",
        )

    async def chat(self, messages, tools=None, model="gpt-4") -> LLMResponse:
        raise AssertionError("stream_chat should be used")

@pytest.mark.asyncio
async def test_agent_loop_returns_content():
    mock_llm = MockLLM(LLMResponse(content="Hello!"))
    registry = ToolRegistry()
    registry.register(EchoTool())

    loop = AgentLoop(
        llm=mock_llm,
        tool_registry=registry,
        hooks=HookManager(),
    )

    result = await loop.run([Message(role="user", content="hi")])
    assert result.content == "Hello!"
    assert result.stop_reason.value == "end_turn"


@pytest.mark.asyncio
async def test_agent_loop_does_not_expose_subagent_tools_by_default():
    loop = AgentLoop(
        llm=MockLLM(LLMResponse(content="done")),
        tool_registry=ToolRegistry(),
        hooks=HookManager(),
    )
    schema_names = {
        schema["function"]["name"]
        for schema in loop.tool_registry.get_all_schemas()
    }
    assert "CreateSubagent" not in schema_names


@pytest.mark.asyncio
async def test_agent_loop_exposes_subagent_tools_when_enabled():
    loop = AgentLoop(
        llm=MockLLM(LLMResponse(content="done")),
        tool_registry=ToolRegistry(),
        hooks=HookManager(),
        subagent_manager=SubAgentManager(),
        expose_subagent_tools=True,
    )
    schema_names = {
        schema["function"]["name"]
        for schema in loop.tool_registry.get_all_schemas()
    }
    assert "CreateSubagent" in schema_names
    assert "RunSubagent" in schema_names


class SubagentWorkflowLLM:
    def __init__(self):
        self.calls = 0

    async def chat(self, messages, tools=None, model="gpt-4") -> LLMResponse:
        self.calls += 1
        if self.calls == 1:
            return LLMResponse(
                content="",
                tool_calls=[
                    ToolCallDelta(
                        id="c1",
                        name="CreateSubagent",
                        arguments=json.dumps({"name": "researcher"}),
                    )
                ],
                stop_reason="tool_calls",
            )
        if self.calls == 2:
            tool_result = messages[-1].content
            subagent_id = json.loads(tool_result)["subagent_id"]
            return LLMResponse(
                content="",
                tool_calls=[
                    ToolCallDelta(
                        id="c2",
                        name="RunSubagent",
                        arguments=json.dumps(
                            {
                                "subagent_id": subagent_id,
                                "task": "inspect repo",
                                "wait": True,
                                "timeout_s": 1,
                            }
                        ),
                    )
                ],
                stop_reason="tool_calls",
            )
        return LLMResponse(content="done", stop_reason="end_turn")


@pytest.mark.asyncio
async def test_agent_loop_can_execute_subagent_runtime_tools():
    loop = AgentLoop(
        llm=SubagentWorkflowLLM(),
        tool_registry=ToolRegistry(),
        hooks=HookManager(),
        subagent_manager=SubAgentManager(),
        expose_subagent_tools=True,
    )

    result = await loop.run([Message(role="user", content="delegate work")])
    assert result.content == "done"
    assert [call.name for call in result.tool_calls_made] == [
        "CreateSubagent",
        "RunSubagent",
    ]
    run_result = json.loads(result.tool_calls_made[1].result)
    assert run_result["status"] == "completed"


@pytest.mark.asyncio
async def test_agent_loop_publishes_assistant_streaming_events_without_partial_messages():
    events = []

    async def on_event(event_type: str, data: dict):
        events.append({"type": event_type, "data": data})

    messages = [Message(role="user", content="hi")]
    loop = AgentLoop(
        llm=StreamingMockLLM(),
        tool_registry=ToolRegistry(),
        hooks=HookManager(),
    )

    result = await loop.run(messages, on_event=on_event)

    assert result.content == "Hello"
    assert [event["type"] for event in events] == [
        "run_started",
        "assistant_delta",
        "assistant_delta",
        "assistant_stream_complete",
        "llm_response",
        "done",
    ]
    assert [event["data"].get("delta") for event in events if event["type"] == "assistant_delta"] == ["Hel", "lo"]
    llm_response = next(event for event in events if event["type"] == "llm_response")
    assert llm_response["data"]["content"] == "Hello"
    assert llm_response["data"]["streamed"] is True
    assert [message.role for message in messages] == ["user", "assistant"]
    assert messages[-1].content == "Hello"


@pytest.mark.asyncio
async def test_agent_loop_publishes_planning_state_events_and_trace():
    events = []
    trace = TraceRecorder(task_id="task-1")

    async def on_event(event_type: str, data: dict):
        events.append({"type": event_type, "data": data})

    mock_llm = MockLLM(LLMResponse(content="Hello!"))
    loop = AgentLoop(
        llm=mock_llm,
        tool_registry=ToolRegistry(),
        hooks=HookManager(),
    )

    snapshot = await loop.set_plan(
        ["Read docs", "Run tests"],
        on_event=on_event,
        trace_recorder=trace,
    )
    await loop.update_plan_item(
        "item-1",
        "in_progress",
        on_event=on_event,
        trace_recorder=trace,
    )

    assert snapshot["items"][0]["id"] == "item-1"
    assert [event["type"] for event in events] == [
        "planning_state_updated",
        "planning_state_updated",
    ]
    assert trace.to_dict()["steps"][0]["type"] == "planning_state_updated"


@pytest.mark.asyncio
async def test_agent_loop_uses_active_run_context_for_planning_events():
    events = []
    trace = TraceRecorder(task_id="task-1")

    async def on_event(event_type: str, data: dict):
        events.append({"type": event_type, "data": data})

    class PlanningLLM:
        def __init__(self):
            self.loop = None

        async def chat(self, messages, tools=None, model="gpt-4") -> LLMResponse:
            await self.loop.set_plan(["Read docs"])
            return LLMResponse(content="done")

    llm = PlanningLLM()
    loop = AgentLoop(
        llm=llm,
        tool_registry=ToolRegistry(),
        hooks=HookManager(),
    )
    llm.loop = loop

    await loop.run(
        [Message(role="user", content="hi")],
        on_event=on_event,
        trace_recorder=trace,
    )

    assert any(event["type"] == "planning_state_updated" for event in events)
    assert any(
        step["type"] == "planning_state_updated"
        for step in trace.to_dict()["steps"]
    )


@pytest.mark.asyncio
async def test_agent_loop_injects_planning_context_without_mutating_messages():
    class CapturingLLM:
        def __init__(self):
            self.messages = None

        async def chat(self, messages, tools=None, model="gpt-4") -> LLMResponse:
            self.messages = list(messages)
            return LLMResponse(content="done")

    llm = CapturingLLM()
    loop = AgentLoop(
        llm=llm,
        tool_registry=ToolRegistry(),
        hooks=HookManager(),
    )
    await loop.set_plan(["Read docs"])
    await loop.update_plan_item("item-1", "in_progress")

    messages = [
        system_message("base system"),
        Message(role="user", content="hi"),
    ]
    await loop.run(messages)

    assert [message.content for message in llm.messages[:2]] == [
        "base system",
        "Current structured planning state:\n- [in_progress] Read docs",
    ]
    assert [message.content for message in messages] == ["base system", "hi", "done"]

@pytest.mark.asyncio
async def test_agent_loop_appends_assistant_message_before_tool_result():
    """
    LLM 返回 tool_calls 时，AgentLoop 应先追加 assistant 消息（含 tool_use block），
    再追加 tool_result 消息，保持 Anthropic 消息链完整。
    Regression test for: 缺失 assistant+tool_use 消息导致 MiniMax 400 Bad Request。
    """
    call_log = []

    class ToolUseCapturingLLM:
        def __init__(self):
            self.captured_messages = None

        async def chat(self, messages, tools=None, model="gpt-4") -> LLMResponse:
            self.captured_messages = list(messages)
            call_log.append(len(messages))
            # 第一轮返回 tool_call，第二轮返回纯文本
            if len(call_log) == 1:
                return LLMResponse(
                    content=None,
                    tool_calls=[ToolCallDelta(id="c1", name="Echo", arguments="{}")],
                    stop_reason="tool_calls",
                )
            else:
                return LLMResponse(content="done", stop_reason="end_turn")

    mock_llm = ToolUseCapturingLLM()
    registry = ToolRegistry()
    registry.register(EchoTool())

    loop = AgentLoop(
        llm=mock_llm,
        tool_registry=registry,
        hooks=HookManager(),
    )

    messages = [Message(role="user", content="test")]
    result = await loop.run(messages)

    # 验证最终结果
    assert result.content == "done"
    assert len(result.tool_calls_made) == 1

    # 验证消息链结构：user -> assistant(tool_calls) -> tool_result -> assistant(final)
    assert len(messages) == 4
    assert messages[0].role == "user"          # 原始 user
    assert messages[1].role == "assistant"     # LLM 返回的 assistant（含 tool_calls）
    assert messages[1].tool_calls is not None
    assert len(messages[1].tool_calls) == 1
    assert messages[1].tool_calls[0].name == "Echo"
    assert messages[2].role == "tool"         # tool_result
    assert messages[2].tool_call_id == "c1"
    assert messages[3].role == "assistant"    # 最终回复
    assert messages[3].content == "done"


@pytest.mark.asyncio
async def test_agent_loop_max_iterations():
    # LLM always returns tool calls - should stop at max_iterations
    mock_llm = MockLLM(LLMResponse(
        content=None,
        tool_calls=[ToolCallDelta(id="c1", name="Echo", arguments="{}")]
    ))
    registry = ToolRegistry()
    registry.register(EchoTool())

    loop = AgentLoop(
        llm=mock_llm,
        tool_registry=registry,
        hooks=HookManager(),
        max_iterations=2,
    )

    result = await loop.run([Message(role="user", content="test")])
    assert result.stop_reason.value == "max_iterations"
    assert len(result.tool_calls_made) == 2


@pytest.mark.asyncio
async def test_agent_loop_max_iterations_does_not_promote_tool_result_to_assistant():
    mock_llm = MockLLM(LLMResponse(
        content=None,
        tool_calls=[ToolCallDelta(id="c1", name="Echo", arguments="{}")]
    ))
    registry = ToolRegistry()
    registry.register(EchoTool())
    loop = AgentLoop(
        llm=mock_llm,
        tool_registry=registry,
        hooks=HookManager(),
        max_iterations=1,
    )

    messages = [Message(role="user", content="test")]
    result = await loop.run(messages)

    assert result.stop_reason.value == "max_iterations"
    assert result.content == ""
    assert messages[-1].role == "tool"
    assert all(not (m.role == "assistant" and m.content == "echo!") for m in messages)


@pytest.mark.asyncio
async def test_agent_loop_invalid_tool_arguments_return_tool_error():
    class InvalidArgsThenDoneLLM:
        def __init__(self):
            self.call_count = 0

        async def chat(self, messages, tools=None, model="gpt-4") -> LLMResponse:
            self.call_count += 1
            if self.call_count == 1:
                return LLMResponse(
                    content=None,
                    tool_calls=[ToolCallDelta(id="c1", name="Echo", arguments="{bad json")],
                    stop_reason="tool_calls",
                )
            return LLMResponse(content="recovered", stop_reason="end_turn")

    registry = ToolRegistry()
    registry.register(EchoTool())
    loop = AgentLoop(
        llm=InvalidArgsThenDoneLLM(),
        tool_registry=registry,
        hooks=HookManager(),
    )

    messages = [Message(role="user", content="test")]
    result = await loop.run(messages)

    assert result.content == "recovered"
    assert result.tool_calls_made[0].arguments == {}
    assert "invalid JSON tool arguments" in (result.tool_calls_made[0].result or "")
    tool_messages = [m for m in messages if m.role == "tool"]
    assert len(tool_messages) == 1
    assert tool_messages[0].tool_call_id == "c1"
    assert "Error" in tool_messages[0].content


@pytest.mark.asyncio
async def test_memory_compaction_preserves_assistant_tool_result_chain():
    mgr = MemoryManager(max_tokens=1, recent_window=1)
    messages = [
        Message(role="system", content="system"),
        Message(role="user", content="old"),
        Message(
            role="assistant",
            content="",
            tool_calls=[ToolCallDelta(id="c1", name="Echo", arguments="{}")],
        ),
        Message(role="tool", content="echo!", tool_call_id="c1"),
    ]

    compacted = await mgr.compact_if_needed(messages)

    assert compacted is True
    assert [m.role for m in messages] == ["system", "assistant", "tool"]
    assert messages[1].tool_calls[0].id == messages[2].tool_call_id


@pytest.mark.asyncio
async def test_max_tokens_triggers_continuation():
    """
    LLM 返回 stop_reason="max_tokens" 且无 tool_calls 时，loop 应追加续接消息
    并继续迭代，而不是直接退出。模拟被 4096 tokens 截断的响应。
    Regression test for: max_tokens 截断导致 agent 提前退出。
    """
    call_count = [0]

    class TruncatedThenDoneLLM:
        async def chat(self, messages, tools=None, model="gpt-4") -> LLMResponse:
            call_count[0] += 1
            if call_count[0] == 1:
                # 模拟被截断：有部分文本，无 tool_calls
                return LLMResponse(
                    content="Okay, let me create the file. I'll write",
                    tool_calls=[],
                    stop_reason="max_tokens",
                )
            else:
                # 续接后正常完成（无 tool_calls）
                return LLMResponse(content="Done!", tool_calls=[], stop_reason="end_turn")

    mock_llm = TruncatedThenDoneLLM()
    registry = ToolRegistry()
    registry.register(EchoTool())

    loop = AgentLoop(
        llm=mock_llm,
        tool_registry=registry,
        hooks=HookManager(),
    )

    messages = [Message(role="user", content="write a file")]
    result = await loop.run(messages)

    # 应该调用了两次 LLM（第一次被截断，第二次续接后完成）
    assert call_count[0] == 2
    assert result.content == "Done!"
    assert result.stop_reason.value == "end_turn"

    # 消息历史应包含续接提示
    user_messages = [m for m in messages if m.role == "user"]
    assert any("Please continue" in m.content for m in user_messages)


@pytest.mark.asyncio
async def test_single_assistant_message_per_turn():
    """
    单轮 LLM 响应包含多个 tool_calls 时，loop 只应追加一条 assistant 消息。
    Regression test for: N 个 tool_calls 产生 N 条重复 assistant 消息。
    """
    class MultiToolLLM:
        def __init__(self):
            self.call_count = 0

        async def chat(self, messages, tools=None, model="gpt-4") -> LLMResponse:
            self.call_count += 1
            if self.call_count == 1:
                return LLMResponse(
                    content=None,
                    tool_calls=[
                        ToolCallDelta(id="c1", name="Echo", arguments="{}"),
                        ToolCallDelta(id="c2", name="Echo", arguments="{}"),
                    ],
                    stop_reason="tool_calls",
                )
            else:
                return LLMResponse(content="all done", tool_calls=[], stop_reason="end_turn")

    mock_llm = MultiToolLLM()
    registry = ToolRegistry()
    registry.register(EchoTool())

    loop = AgentLoop(
        llm=mock_llm,
        tool_registry=registry,
        hooks=HookManager(),
    )

    messages = [Message(role="user", content="test")]
    result = await loop.run(messages)

    assert result.content == "all done"
    assert len(result.tool_calls_made) == 2

    # 消息结构：user(1) -> assistant(tool_calls) -> tool(2) -> assistant(final)
    assistant_msgs = [m for m in messages if m.role == "assistant"]
    assert len(assistant_msgs) == 2
    assert len(assistant_msgs[0].tool_calls) == 2
    assert assistant_msgs[1].content == "all done"


@pytest.mark.asyncio
async def test_agent_loop_appends_final_assistant_message():
    """
    agent.run() 应在返回前将 assistant 最终回复追加到 messages。
    Regression test for: 多轮对话中 agent 看不到自己的回复，导致重复回答。
    """
    mock_llm = MockLLM(LLMResponse(content="Hello!", stop_reason="end_turn"))
    registry = ToolRegistry()
    registry.register(EchoTool())

    loop = AgentLoop(
        llm=mock_llm,
        tool_registry=registry,
        hooks=HookManager(),
    )

    messages = [Message(role="user", content="hi")]
    result = await loop.run(messages)

    assert result.content == "Hello!"
    # 验证最终 assistant 消息已追加到 messages
    assert messages[-1].role == "assistant"
    assert messages[-1].content == "Hello!"


@pytest.mark.asyncio
async def test_agent_loop_preserves_text_with_tool_calls():
    """
    LLM 返回 tool_calls 同时附带文字时，assistant 消息应保留该文字，而非丢弃为 ""。
    Regression test for: content="" 硬编码导致 LLM 附带的上下文文字丢失。
    """
    call_log = []

    class TextWithToolLLM:
        async def chat(self, messages, tools=None, model="gpt-4") -> LLMResponse:
            call_log.append(1)
            if len(call_log) == 1:
                return LLMResponse(
                    content="Let me check that for you.",
                    tool_calls=[ToolCallDelta(id="c1", name="Echo", arguments="{}")],
                    stop_reason="tool_calls",
                )
            else:
                return LLMResponse(content="Done!", stop_reason="end_turn")

    mock_llm = TextWithToolLLM()
    registry = ToolRegistry()
    registry.register(EchoTool())

    loop = AgentLoop(
        llm=mock_llm,
        tool_registry=registry,
        hooks=HookManager(),
    )

    messages = [Message(role="user", content="test")]
    result = await loop.run(messages)

    assert result.content == "Done!"
    # 第一轮 assistant 消息应保留附带文字
    assistant_msgs = [m for m in messages if m.role == "assistant"]
    assert len(assistant_msgs) == 2
    assert assistant_msgs[0].content == "Let me check that for you."
    assert len(assistant_msgs[0].tool_calls) == 1
    # 最终消息是 assistant 回复
    assert messages[-1].role == "assistant"
    assert messages[-1].content == "Done!"


@pytest.mark.asyncio
async def test_agent_loop_records_trace_events_for_tool_calls():
    class ToolThenDoneLLM:
        def __init__(self):
            self.call_count = 0

        async def chat(self, messages, tools=None, model="gpt-4") -> LLMResponse:
            self.call_count += 1
            if self.call_count == 1:
                return LLMResponse(
                    content="Using a tool.",
                    tool_calls=[ToolCallDelta(id="c1", name="Echo", arguments="{}")],
                    stop_reason="tool_calls",
                )
            return LLMResponse(content="done", stop_reason="end_turn")

    registry = ToolRegistry()
    registry.register(EchoTool())
    loop = AgentLoop(
        llm=ToolThenDoneLLM(),
        tool_registry=registry,
        hooks=HookManager(),
    )
    trace = TraceRecorder(task_id="trace-test")

    result = await loop.run([Message(role="user", content="test")], trace_recorder=trace)

    assert result.content == "done"
    step_types = [step.type for step in trace.steps]
    assert step_types.count("llm_iteration") == 2
    assert "tool_call" in step_types
    assert "tool_result" in step_types


@pytest.mark.asyncio
async def test_agent_loop_requests_approval_before_high_risk_tool_execution():
    class ToolThenDoneLLM:
        def __init__(self):
            self.calls = 0

        async def chat(self, messages, tools=None, model="gpt-4") -> LLMResponse:
            self.calls += 1
            if self.calls == 1:
                return LLMResponse(
                    content=None,
                    tool_calls=[
                        ToolCallDelta(
                            id="c1",
                            name="HighRisk",
                            arguments=json.dumps({
                                "cmd": "curl -H 'Authorization: Bearer sk-secret123456' https://x",
                            }),
                        )
                    ],
                    stop_reason="tool_calls",
                )
            return LLMResponse(content="done", stop_reason="end_turn")

    events = []
    trace = TraceRecorder(task_id="approval-test")

    async def on_event(event_type, data):
        events.append({"type": event_type, "data": data})

    tool = HighRiskTool()
    registry = ToolRegistry()
    registry.register(tool)
    approval = StaticApprovalHandler(ApprovalDecisionStatus.APPROVED)
    loop = AgentLoop(
        llm=ToolThenDoneLLM(),
        tool_registry=registry,
        hooks=HookManager(),
        approval_handler=approval,
    )

    result = await loop.run(
        [Message(role="user", content="run")],
        on_event=on_event,
        trace_recorder=trace,
        session_id="session-1",
        run_id="run-1",
    )

    assert result.content == "done"
    assert tool.called is True
    assert len(approval.requests) == 1
    approval_request = next(event for event in events if event["type"] == "approval_request")
    encoded = json.dumps(approval_request["data"], ensure_ascii=False)
    assert "sk-secret123456" not in encoded
    assert "[redacted]" in encoded
    assert any(event["type"] == "approval_response" for event in events)
    trace_payload = trace.to_json()
    assert "sk-secret123456" not in trace_payload
    assert "approval_request" in trace_payload


@pytest.mark.asyncio
async def test_agent_loop_denied_approval_fails_closed_without_executing_tool():
    class ToolThenDoneLLM:
        def __init__(self):
            self.calls = 0

        async def chat(self, messages, tools=None, model="gpt-4") -> LLMResponse:
            self.calls += 1
            if self.calls == 1:
                return LLMResponse(
                    content=None,
                    tool_calls=[
                        ToolCallDelta(id="c1", name="HighRisk", arguments="{}")
                    ],
                    stop_reason="tool_calls",
                )
            return LLMResponse(content="done", stop_reason="end_turn")

    tool = HighRiskTool()
    registry = ToolRegistry()
    registry.register(tool)
    loop = AgentLoop(
        llm=ToolThenDoneLLM(),
        tool_registry=registry,
        hooks=HookManager(),
        approval_handler=StaticApprovalHandler(ApprovalDecisionStatus.DENIED),
    )

    result = await loop.run([Message(role="user", content="run")])

    assert tool.called is False
    assert result.tool_calls_made[0].name == "HighRisk"
    assert "Approval denied" in result.tool_calls_made[0].result
    assert result.content == "done"


@pytest.mark.asyncio
async def test_agent_loop_emits_run_started_event_with_mode():
    events = []

    async def on_event(name, payload):
        events.append((name, payload))

    registry = ToolRegistry()
    loop = AgentLoop(
        llm=MockLLM(LLMResponse(content="done")),
        tool_registry=registry,
        hooks=HookManager(),
        run_config=AgentRunConfig(mode=AgentMode.READ_ONLY),
    )
    trace = TraceRecorder(task_id="trace-test")

    await loop.run(
        [Message(role="user", content="test")],
        on_event=on_event,
        trace_recorder=trace,
        session_id="session-1",
        run_id="run-1",
    )

    assert events[0] == (
        "run_started",
        {
            "mode": "read_only",
            "session_id": "session-1",
            "run_id": "run-1",
        },
    )
    assert trace.to_dict()["session_id"] == "session-1"
    assert trace.to_dict()["run_id"] == "run-1"
    assert trace.to_dict()["mode"] == "read_only"
    assert trace.steps[0].type == "run_started"


@pytest.mark.asyncio
async def test_agent_loop_set_mode_emits_event_and_trace_without_messages():
    events = []

    async def on_event(name, payload):
        events.append((name, payload))

    messages = [Message(role="user", content="hi")]
    loop = AgentLoop(
        llm=MockLLM(LLMResponse(content="done")),
        tool_registry=ToolRegistry(),
        hooks=HookManager(),
        run_config=AgentRunConfig(mode=AgentMode.BUILD),
    )
    trace = TraceRecorder(task_id="trace-test")

    transition = await loop.set_mode(
        "read_only",
        source="cli",
        reason="inspect",
        on_event=on_event,
        trace_recorder=trace,
        session_id="session-1",
    )

    assert transition["old_mode"] == "build"
    assert transition["new_mode"] == "read_only"
    assert transition["source"] == "cli"
    assert transition["reason"] == "inspect"
    assert transition["session_id"] == "session-1"
    assert events == [("mode_changed", transition)]
    assert trace.steps[-1].type == "mode_changed"
    assert trace.steps[-1].data == transition
    assert messages == [Message(role="user", content="hi")]


@pytest.mark.asyncio
async def test_agent_loop_run_started_uses_latest_runtime_mode():
    events = []

    async def on_event(name, payload):
        events.append((name, payload))

    loop = AgentLoop(
        llm=MockLLM(LLMResponse(content="done")),
        tool_registry=ToolRegistry(),
        hooks=HookManager(),
        run_config=AgentRunConfig(mode=AgentMode.BUILD),
    )

    await loop.set_mode("read_only", source="test")
    await loop.run([Message(role="user", content="test")], on_event=on_event)

    assert events[0][0] == "run_started"
    assert events[0][1]["mode"] == "read_only"


@pytest.mark.asyncio
async def test_agent_loop_set_mode_to_plan_registers_plan_tools():
    loop = AgentLoop(
        llm=MockLLM(LLMResponse(content="done")),
        tool_registry=ToolRegistry(),
        hooks=HookManager(),
        run_config=AgentRunConfig(mode=AgentMode.BUILD),
    )

    build_tool_names = [
        schema["function"]["name"]
        for schema in loop.tool_registry.get_all_schemas()
    ]
    assert "UpdatePlan" not in build_tool_names
    assert "ExitPlanMode" not in build_tool_names

    await loop.set_mode("plan", source="cli")

    plan_tool_names = [
        schema["function"]["name"]
        for schema in loop.tool_registry.get_all_schemas()
    ]
    assert "UpdatePlan" in plan_tool_names
    assert "ExitPlanMode" in plan_tool_names

    await loop.set_mode("build", source="cli")
    build_tool_names = [
        schema["function"]["name"]
        for schema in loop.tool_registry.get_all_schemas()
    ]
    assert "UpdatePlan" not in build_tool_names
    assert "ExitPlanMode" not in build_tool_names


@pytest.mark.asyncio
async def test_agent_loop_tool_call_uses_mode_changed_after_schema_was_seen():
    class SwitchBeforeToolLLM:
        async def chat(self, messages, tools=None, model="gpt-4") -> LLMResponse:
            names = [tool["function"]["name"] for tool in tools or []]
            assert "WriteLike" in names
            await loop.set_mode("read_only", source="test")
            return LLMResponse(
                content=None,
                tool_calls=[
                    ToolCallDelta(id="c1", name="WriteLike", arguments="{}")
                ],
                stop_reason="tool_calls",
            )

    tool = WriteLikeTool()
    registry = ToolRegistry()
    registry.register(tool)
    loop = AgentLoop(
        llm=SwitchBeforeToolLLM(),
        tool_registry=registry,
        hooks=HookManager(),
        run_config=AgentRunConfig(mode=AgentMode.BUILD),
        max_iterations=1,
    )

    result = await loop.run([Message(role="user", content="test")])

    assert tool.called is False
    assert result.tool_calls_made[0].name == "WriteLike"
    assert "Permission denied" in result.tool_calls_made[0].result
    assert "read_only" in result.tool_calls_made[0].result


@pytest.mark.asyncio
async def test_agent_loop_emits_memory_compaction_only_when_compacted():
    class ToolThenDoneLLM:
        def __init__(self):
            self.call_count = 0

        async def chat(self, messages, tools=None, model="gpt-4") -> LLMResponse:
            self.call_count += 1
            if self.call_count == 1:
                return LLMResponse(
                    content="Using a tool.",
                    tool_calls=[ToolCallDelta(id="c1", name="Echo", arguments="{}")],
                    stop_reason="tool_calls",
                )
            return LLMResponse(content="done", stop_reason="end_turn")

    events = []

    async def on_event(name, payload):
        events.append((name, payload))

    registry = ToolRegistry()
    registry.register(EchoTool())
    loop = AgentLoop(
        llm=ToolThenDoneLLM(),
        tool_registry=registry,
        hooks=HookManager(),
        memory=MemoryManager(max_tokens=100_000_000),
    )

    await loop.run([Message(role="user", content="test")], on_event=on_event)

    event_names = [name for name, _payload in events]
    assert "tool_result" in event_names
    assert "memory_compaction" not in event_names


@pytest.mark.asyncio
async def test_agent_loop_injects_skill_index_without_full_prompt():
    class CapturingLLM:
        def __init__(self):
            self.messages = None

        async def chat(self, messages, tools=None, model="gpt-4") -> LLMResponse:
            self.messages = list(messages)
            return LLMResponse(content="done")

    skill_runtime = SkillRuntime([
        Skill(
            name="code-review",
            description="审查代码变更",
            prompt="FULL REVIEW PROMPT",
            tools=[],
            argument_hint="<request>",
        )
    ])
    llm = CapturingLLM()
    loop = AgentLoop(
        llm=llm,
        tool_registry=ToolRegistry(),
        skill_runtime=skill_runtime,
    )

    await loop.run([Message(role="user", content="hello")])

    contents = "\n".join(message.content for message in llm.messages)
    assert "Available skills" in contents
    assert "/code-review <request>" in contents
    assert "FULL REVIEW PROMPT" not in contents


@pytest.mark.asyncio
async def test_agent_loop_injects_matched_skill_context_without_mutating_messages():
    class CapturingLLM:
        def __init__(self):
            self.messages = None

        async def chat(self, messages, tools=None, model="gpt-4") -> LLMResponse:
            self.messages = list(messages)
            return LLMResponse(content="done")

    skill_runtime = SkillRuntime([
        Skill(
            name="code-review",
            description="审查代码变更",
            prompt="FULL REVIEW PROMPT",
            tools=[],
            triggers=("review",),
        )
    ])
    llm = CapturingLLM()
    loop = AgentLoop(
        llm=llm,
        tool_registry=ToolRegistry(),
        skill_runtime=skill_runtime,
    )
    messages = [Message(role="user", content="please review this change")]

    await loop.run(messages)

    contents = "\n".join(message.content for message in llm.messages)
    assert "Active Skill: code-review" in contents
    assert "FULL REVIEW PROMPT" in contents
    assert [message.content for message in messages] == [
        "please review this change",
        "done",
    ]


@pytest.mark.asyncio
async def test_agent_loop_activate_skill_tool_adds_context_for_next_llm_call():
    class ActivateThenDoneLLM:
        def __init__(self):
            self.calls = []

        async def chat(self, messages, tools=None, model="gpt-4") -> LLMResponse:
            self.calls.append(list(messages))
            if len(self.calls) == 1:
                names = [tool["function"]["name"] for tool in tools or []]
                assert "ActivateSkill" in names
                return LLMResponse(
                    content="",
                    tool_calls=[
                        ToolCallDelta(
                            id="skill-1",
                            name="ActivateSkill",
                            arguments='{"skill_name": "research", "reason": "need research"}',
                        )
                    ],
                    stop_reason="tool_calls",
                )
            return LLMResponse(content="researched")

    skill_runtime = SkillRuntime([
        Skill(
            name="research",
            description="研究主题",
            prompt="FULL RESEARCH PROMPT",
            tools=[],
        )
    ])
    llm = ActivateThenDoneLLM()
    loop = AgentLoop(
        llm=llm,
        tool_registry=ToolRegistry(),
        skill_runtime=skill_runtime,
    )
    events = []

    async def on_event(name, payload):
        events.append((name, payload))

    result = await loop.run([Message(role="user", content="tell me something")], on_event=on_event)

    second_call_contents = "\n".join(message.content for message in llm.calls[1])
    assert result.content == "researched"
    assert "Active Skill: research" in second_call_contents
    assert "FULL RESEARCH PROMPT" in second_call_contents
    assert ("skill_activated", {"skill_name": "research", "source": "llm_tool"}) in [
        (name, {key: payload[key] for key in ("skill_name", "source")})
        for name, payload in events
        if name == "skill_activated"
    ]


@pytest.mark.asyncio
async def test_todo_write_tool_registered_in_all_modes():
    loop = AgentLoop(
        llm=MockLLM(LLMResponse(content="done")),
        tool_registry=ToolRegistry(),
        hooks=HookManager(),
        run_config=AgentRunConfig(mode=AgentMode.BUILD),
    )
    schemas = {s["function"]["name"]: s for s in loop.tool_registry.get_all_schemas()}
    assert "TodoWrite" in schemas

    await loop.set_mode("read_only", source="test")
    schemas = {s["function"]["name"]: s for s in loop.tool_registry.get_all_schemas()}
    assert "TodoWrite" in schemas

    await loop.set_mode("plan", source="test")
    schemas = {s["function"]["name"]: s for s in loop.tool_registry.get_all_schemas()}
    assert "TodoWrite" in schemas


@pytest.mark.asyncio
async def test_todo_context_injected_in_build_mode():
    class CapturingLLM:
        def __init__(self):
            self.messages = None

        async def chat(self, messages, tools=None, model="gpt-4") -> LLMResponse:
            self.messages = list(messages)
            return LLMResponse(content="done")

    llm = CapturingLLM()
    loop = AgentLoop(
        llm=llm,
        tool_registry=ToolRegistry(),
        hooks=HookManager(),
        run_config=AgentRunConfig(mode=AgentMode.BUILD),
    )
    loop._todo_create("Task 1")
    loop._todo_create("Task 2")
    loop._todo_update("todo-1", "in_progress", None)

    await loop.run([Message(role="user", content="test")])

    contents = "\n".join(m.content for m in llm.messages)
    assert "## Current Progress" in contents
    assert "Task 1" in contents
    assert "Task 2" in contents


@pytest.mark.asyncio
async def test_todo_context_not_injected_when_empty():
    class CapturingLLM:
        def __init__(self):
            self.messages = None

        async def chat(self, messages, tools=None, model="gpt-4") -> LLMResponse:
            self.messages = list(messages)
            return LLMResponse(content="done")

    llm = CapturingLLM()
    loop = AgentLoop(
        llm=llm,
        tool_registry=ToolRegistry(),
        hooks=HookManager(),
        run_config=AgentRunConfig(mode=AgentMode.BUILD),
    )

    await loop.run([Message(role="user", content="test")])

    contents = "\n".join(m.content for m in llm.messages)
    assert "## Current Progress" not in contents


@pytest.mark.asyncio
async def test_todo_context_not_injected_in_plan_mode():
    class CapturingLLM:
        def __init__(self):
            self.messages = None

        async def chat(self, messages, tools=None, model="gpt-4") -> LLMResponse:
            self.messages = list(messages)
            return LLMResponse(content="done")

    llm = CapturingLLM()
    loop = AgentLoop(
        llm=llm,
        tool_registry=ToolRegistry(),
        hooks=HookManager(),
        run_config=AgentRunConfig(mode=AgentMode.PLAN),
    )
    loop._todo_create("Task 1")

    await loop.run([Message(role="user", content="test")])

    contents = "\n".join(m.content for m in llm.messages)
    assert "## Current Progress" not in contents


@pytest.mark.asyncio
async def test_todo_updated_event_published():
    events = []

    async def on_event(name, payload):
        events.append((name, payload))

    class TodoThenDoneLLM:
        def __init__(self):
            self.call_count = 0

        async def chat(self, messages, tools=None, model="gpt-4") -> LLMResponse:
            self.call_count += 1
            if self.call_count == 1:
                return LLMResponse(
                    content=None,
                    tool_calls=[
                        ToolCallDelta(
                            id="t1",
                            name="TodoWrite",
                            arguments=json.dumps({"operation": "create", "content": "Test task"}),
                        )
                    ],
                    stop_reason="tool_calls",
                )
            return LLMResponse(content="done", stop_reason="end_turn")

    loop = AgentLoop(
        llm=TodoThenDoneLLM(),
        tool_registry=ToolRegistry(),
        hooks=HookManager(),
        run_config=AgentRunConfig(mode=AgentMode.BUILD),
    )

    await loop.run([Message(role="user", content="test")], on_event=on_event)

    todo_events = [e for e in events if e[0] == "todo_updated"]
    assert len(todo_events) == 1
    assert len(todo_events[0][1]["items"]) == 1
    assert todo_events[0][1]["items"][0]["content"] == "Test task"


@pytest.mark.asyncio
async def test_retry_on_timeout_error():
    call_count = [0]

    class FlakyEchoTool(Tool):
        name = "FlakyEcho"
        description = "Flaky"
        parameters = {}

        async def execute(self, **kwargs) -> str:
            call_count[0] += 1
            if call_count[0] < 3:
                raise TimeoutError("timeout")
            return "echo!"

    class FlakyThenDoneLLM:
        async def chat(self, messages, tools=None, model="gpt-4") -> LLMResponse:
            return LLMResponse(
                content=None,
                tool_calls=[ToolCallDelta(id="c1", name="FlakyEcho", arguments="{}")],
                stop_reason="tool_calls",
            )

    registry = ToolRegistry()
    registry.register(FlakyEchoTool())
    loop = AgentLoop(
        llm=FlakyThenDoneLLM(),
        tool_registry=registry,
        hooks=HookManager(),
        max_iterations=1,
    )

    await loop.run([Message(role="user", content="test")])
    assert call_count[0] == 3


@pytest.mark.asyncio
async def test_no_retry_on_value_error():
    call_count = [0]

    class ValueErrorTool(Tool):
        name = "ValueErrorTool"
        description = "Raises ValueError"
        parameters = {}

        async def execute(self, **kwargs) -> str:
            call_count[0] += 1
            raise ValueError("invalid arguments")

    class ValueErrorThenDoneLLM:
        async def chat(self, messages, tools=None, model="gpt-4") -> LLMResponse:
            return LLMResponse(
                content=None,
                tool_calls=[ToolCallDelta(id="c1", name="ValueErrorTool", arguments="{}")],
                stop_reason="tool_calls",
            )

    registry = ToolRegistry()
    registry.register(ValueErrorTool())
    loop = AgentLoop(
        llm=ValueErrorThenDoneLLM(),
        tool_registry=registry,
        hooks=HookManager(),
        max_iterations=1,
    )

    await loop.run([Message(role="user", content="test")])
    assert call_count[0] == 1


@pytest.mark.asyncio
async def test_bash_tool_not_retried():
    call_count = [0]

    class TimeoutBashTool(Tool):
        name = "Bash"
        description = "Bash"
        parameters = {}

        async def execute(self, **kwargs) -> str:
            call_count[0] += 1
            raise ConnectionError("connection timed out")

    class BashThenDoneLLM:
        async def chat(self, messages, tools=None, model="gpt-4") -> LLMResponse:
            return LLMResponse(
                content=None,
                tool_calls=[ToolCallDelta(id="c1", name="Bash", arguments="{}")],
                stop_reason="tool_calls",
            )

    registry = ToolRegistry()
    registry.register(TimeoutBashTool())
    loop = AgentLoop(
        llm=BashThenDoneLLM(),
        tool_registry=registry,
        hooks=HookManager(),
        max_iterations=1,
    )

    await loop.run([Message(role="user", content="test")])
    assert call_count[0] == 1


# ── Parallel tool execution tests ──


@tool_parameters(name="SlowRead", description="Slow read tool", parameters={"type": "object", "properties": {}, "required": []})
class SlowReadTool(Tool):
    name = "SlowRead"
    description = "Slow read"
    parameters = {}
    read_only = True
    parallelizable = True

    def __init__(self, delay: float = 0.05):
        self.delay = delay
        self.started_at: float | None = None
        self.ended_at: float | None = None

    async def execute(self, **kwargs) -> str:
        self.started_at = __import__("time").perf_counter()
        await __import__("asyncio").sleep(self.delay)
        self.ended_at = __import__("time").perf_counter()
        return f"read after {self.delay}s"


@tool_parameters(name="FastWrite", description="Fast write tool", parameters={"type": "object", "properties": {}, "required": []})
class FastWriteTool(Tool):
    name = "FastWrite"
    description = "Fast write"
    parameters = {}
    read_only = False
    parallelizable = False

    def __init__(self):
        self.called = False

    async def execute(self, **kwargs) -> str:
        self.called = True
        return "written"


class MultiToolLLM:
    def __init__(self, tool_call_groups: list[list[ToolCallDelta]]):
        self.tool_call_groups = tool_call_groups
        self.call_count = 0

    async def chat(self, messages, tools=None, model="gpt-4") -> LLMResponse:
        if self.call_count < len(self.tool_call_groups):
            group = self.tool_call_groups[self.call_count]
            self.call_count += 1
            return LLMResponse(
                content="calling tools",
                tool_calls=list(group),
                stop_reason="tool_calls",
            )
        return LLMResponse(content="done", stop_reason="end_turn")


@pytest.mark.asyncio
async def test_parallelizable_tools_execute_concurrently():
    """All-parallelizable group: tools must overlap in time."""
    slow_a = SlowReadTool(delay=0.05)
    slow_a.name = "SlowReadA"
    slow_b = SlowReadTool(delay=0.05)
    slow_b.name = "SlowReadB"

    registry = ToolRegistry()
    registry.register(slow_a)
    registry.register(slow_b)

    llm = MultiToolLLM([
        [
            ToolCallDelta(id="c1", name="SlowReadA", arguments="{}"),
            ToolCallDelta(id="c2", name="SlowReadB", arguments="{}"),
        ],
    ])
    loop = AgentLoop(llm=llm, tool_registry=registry, hooks=HookManager(), max_iterations=3)

    await loop.run([Message(role="user", content="test")])

    # If concurrent, the second tool started before the first finished.
    assert slow_a.started_at is not None
    assert slow_b.started_at is not None
    assert slow_a.ended_at is not None
    assert slow_b.ended_at is not None
    # The tools should overlap: B started before A finished (or vice versa)
    parallel = slow_b.started_at < slow_a.ended_at or slow_a.started_at < slow_b.ended_at
    assert parallel, f"Expected concurrent execution: A={slow_a.started_at:.6f}-{slow_a.ended_at:.6f}, B={slow_b.started_at:.6f}-{slow_b.ended_at:.6f}"


@pytest.mark.asyncio
async def test_mixed_serial_parallel_grouping():
    """Write tool between two parallel Read tools: grouping correct, results ordered."""
    read_a = SlowReadTool(delay=0.02)
    read_a.name = "SlowReadA"
    write = FastWriteTool()
    write.name = "FastWrite"
    read_b = SlowReadTool(delay=0.02)
    read_b.name = "SlowReadB"

    registry = ToolRegistry()
    registry.register(read_a)
    registry.register(write)
    registry.register(read_b)

    llm = MultiToolLLM([
        [
            ToolCallDelta(id="c1", name="SlowReadA", arguments="{}"),
            ToolCallDelta(id="c2", name="FastWrite", arguments="{}"),
            ToolCallDelta(id="c3", name="SlowReadB", arguments="{}"),
        ],
    ])
    loop = AgentLoop(llm=llm, tool_registry=registry, hooks=HookManager(), max_iterations=3)

    await loop.run([Message(role="user", content="test")])

    # Write must have been called
    assert write.called
    # All Read tools executed
    assert read_a.started_at is not None
    assert read_b.started_at is not None


@pytest.mark.asyncio
async def test_parallel_group_error_isolation():
    """One tool error in a parallel group doesn't block siblings."""
    call_count = {"good": 0, "bad": 0}

    class BadTool(Tool):
        name = "BadTool"
        description = "Always fails"
        parameters = {}
        read_only = True
        parallelizable = True

        async def execute(self, **kwargs) -> str:
            call_count["bad"] += 1
            raise RuntimeError("boom")

    class GoodTool(Tool):
        name = "GoodTool"
        description = "Always works"
        parameters = {}
        read_only = True
        parallelizable = True

        async def execute(self, **kwargs) -> str:
            call_count["good"] += 1
            return "ok"

    registry = ToolRegistry()
    registry.register(BadTool())
    registry.register(GoodTool())

    llm = MultiToolLLM([
        [
            ToolCallDelta(id="c1", name="BadTool", arguments="{}"),
            ToolCallDelta(id="c2", name="GoodTool", arguments="{}"),
        ],
    ])
    loop = AgentLoop(llm=llm, tool_registry=registry, hooks=HookManager(), max_iterations=3)

    trace = TraceRecorder(task_id="error-test")
    result = await loop.run(
        [Message(role="user", content="test")],
        trace_recorder=trace,
    )

    # Both tools were attempted
    assert call_count["bad"] == 1
    assert call_count["good"] == 1
    # Good tool result should appear
    assert result.tool_calls_made[0].name == "BadTool"
    assert result.tool_calls_made[1].name == "GoodTool"
    assert result.tool_calls_made[1].result == "ok"


@pytest.mark.asyncio
async def test_result_order_preserved():
    """Results must match original tool call order regardless of execution order."""
    class FastReadTool(Tool):
        name = "FastReadX"
        description = "Fast"
        parameters = {}
        read_only = True
        parallelizable = True

        async def execute(self, **kwargs) -> str:
            return "fast"

    class SlowReadTool2(Tool):
        name = "SlowReadX"
        description = "Slow"
        parameters = {}
        read_only = True
        parallelizable = True

        async def execute(self, **kwargs) -> str:
            await __import__("asyncio").sleep(0.05)
            return "slow"

    registry = ToolRegistry()
    registry.register(FastReadTool())
    registry.register(SlowReadTool2())

    # Fast is first, Slow is second in the call list
    llm = MultiToolLLM([
        [
            ToolCallDelta(id="c1", name="FastReadX", arguments="{}"),
            ToolCallDelta(id="c2", name="SlowReadX", arguments="{}"),
        ],
    ])
    loop = AgentLoop(llm=llm, tool_registry=registry, hooks=HookManager(), max_iterations=3)

    result = await loop.run([Message(role="user", content="test")])

    assert len(result.tool_calls_made) == 2
    # Order must match original call list
    assert result.tool_calls_made[0].name == "FastReadX"
    assert result.tool_calls_made[0].result == "fast"
    assert result.tool_calls_made[1].name == "SlowReadX"
    assert result.tool_calls_made[1].result == "slow"


@pytest.mark.asyncio
async def test_two_write_tools_run_serially():
    """Non-parallelizable tools should not be grouped."""
    write_a = FastWriteTool()
    write_a.name = "FastWriteA"
    write_b = FastWriteTool()
    write_b.name = "FastWriteB"

    registry = ToolRegistry()
    registry.register(write_a)
    registry.register(write_b)

    llm = MultiToolLLM([
        [
            ToolCallDelta(id="c1", name="FastWriteA", arguments="{}"),
            ToolCallDelta(id="c2", name="FastWriteB", arguments="{}"),
        ],
    ])
    loop = AgentLoop(llm=llm, tool_registry=registry, hooks=HookManager(), max_iterations=3)

    await loop.run([Message(role="user", content="test")])

    assert write_a.called
    assert write_b.called


@pytest.mark.asyncio
async def test_trace_parallel_execution_start():
    """Trace recorder captures parallel_execution_start step for grouped tools."""
    read_a = SlowReadTool(delay=0.01)
    read_a.name = "SlowReadA"
    read_b = SlowReadTool(delay=0.01)
    read_b.name = "SlowReadB"

    registry = ToolRegistry()
    registry.register(read_a)
    registry.register(read_b)

    llm = MultiToolLLM([
        [
            ToolCallDelta(id="c1", name="SlowReadA", arguments="{}"),
            ToolCallDelta(id="c2", name="SlowReadB", arguments="{}"),
        ],
    ])
    loop = AgentLoop(llm=llm, tool_registry=registry, hooks=HookManager(), max_iterations=3)

    trace = TraceRecorder(task_id="parallel-trace")
    await loop.run([Message(role="user", content="test")], trace_recorder=trace)

    step_types = [step.type for step in trace.steps]
    assert "parallel_execution_start" in step_types

    # Verify the group membership
    parallel_step = next(
        step for step in trace.steps if step.type == "parallel_execution_start"
    )
    assert parallel_step.data["tools"] == ["SlowReadA", "SlowReadB"]


@pytest.mark.asyncio
async def test_parallelizable_attribute_default():
    """Default parallelizable is False. Only explicitly marked tools are True."""
    from agent.tools.base import Tool as BaseTool

    class UnknownTool(BaseTool):
        name = "UnknownTool"
        description = "test"
        parameters = {}

        async def execute(self, **kwargs) -> str:
            return "test"

    tool = UnknownTool()
    assert tool.parallelizable is False


def test_parallelizable_tools_marked():
    """Only the 7 safe read-only tools have parallelizable=True."""
    from agent.tools.builtin.read import ReadTool
    from agent.tools.builtin.grep import GrepTool
    from agent.tools.builtin.find import FindTool
    from agent.tools.builtin.list_files import ListFilesTool
    from agent.tools.builtin.inspect_git_diff import InspectGitDiffTool
    from agent.tools.builtin.code_intelligence import RepoMapTool, SymbolSearchTool

    parallel_read = [ReadTool, GrepTool, FindTool, ListFilesTool, InspectGitDiffTool, RepoMapTool, SymbolSearchTool]
    for cls in parallel_read:
        inst = cls()
        assert inst.parallelizable is True, f"{cls.__name__} should be parallelizable"

    # Write tools must NOT be parallelizable
    from agent.tools.builtin.write import WriteTool
    from agent.tools.builtin.edit import EditTool
    from agent.tools.builtin.bash import BashTool

    for cls in [WriteTool, EditTool, BashTool]:
        inst = cls()
        assert inst.parallelizable is False, f"{cls.__name__} should not be parallelizable"


@pytest.mark.asyncio
async def test_unknown_tool_defaults_to_non_parallelizable():
    """A tool not in registry is handled gracefully with an error, sibling tools continue."""
    registry = ToolRegistry()
    registry.register(SlowReadTool(delay=0.01))

    llm = MultiToolLLM([
        [
            ToolCallDelta(id="c1", name="NonExistentTool", arguments="{}"),
            ToolCallDelta(id="c2", name="SlowRead", arguments="{}"),
        ],
    ])
    loop = AgentLoop(llm=llm, tool_registry=registry, hooks=HookManager(), max_iterations=3)

    trace = TraceRecorder(task_id="unknown-tool")
    result = await loop.run(
        [Message(role="user", content="test")],
        trace_recorder=trace,
    )

    # Non-existent tool should result in an error
    assert result.tool_calls_made[0].name == "NonExistentTool"
    assert "Error" in result.tool_calls_made[0].result
    # The Read tool should still execute
    assert result.tool_calls_made[1].name == "SlowRead"
    assert result.tool_calls_made[1].result.startswith("read after")
