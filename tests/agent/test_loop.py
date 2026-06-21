# tests/agent/test_loop.py
import pytest
from agent.loop import AgentLoop
from agent.message import Message
from agent.llm import LLMResponse, ToolCallDelta
from agent.tools.base import Tool, tool_parameters, ToolCall
from agent.tools.registry import ToolRegistry
from agent.hooks.manager import HookManager
from agent.memory.manager import MemoryManager
from agent.trace_recorder import TraceRecorder

@tool_parameters(name="Echo", description="Echo back", parameters={"type": "object", "properties": {}, "required": []})
class EchoTool(Tool):
    name = "Echo"
    description = "Echo back"
    parameters = {}

    async def execute(self, **kwargs) -> str:
        return "echo!"

class MockLLM:
    def __init__(self, response: LLMResponse):
        self._response = response

    async def chat(self, messages, tools=None, model="gpt-4") -> LLMResponse:
        return self._response

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
