# tests/agent/test_loop.py
import pytest
from agent.loop import AgentLoop
from agent.message import Message
from agent.llm import LLMResponse, ToolCallDelta
from agent.tools.base import Tool, tool_parameters, ToolCall
from agent.tools.registry import ToolRegistry
from agent.hooks.manager import HookManager

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

    # 验证消息链结构：user -> assistant(tool_calls) -> tool_result
    # 注意：agent.run() 在 LLM 返回纯文本时直接 return，不会追加最后的 assistant 消息
    assert len(messages) == 3
    assert messages[0].role == "user"          # 原始 user
    assert messages[1].role == "assistant"     # LLM 返回的 assistant（含 tool_calls）
    assert messages[1].tool_calls is not None
    assert len(messages[1].tool_calls) == 1
    assert messages[1].tool_calls[0].name == "Echo"
    assert messages[2].role == "tool"         # tool_result
    assert messages[2].tool_call_id == "c1"


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

    # 消息结构：user(1) -> assistant(1) -> tool(2) -> assistant(0, loop 直接返回)
    # 只有一条 assistant 消息（含两个 tool_calls）
    assistant_msgs = [m for m in messages if m.role == "assistant"]
    assert len(assistant_msgs) == 1
    assert len(assistant_msgs[0].tool_calls) == 2