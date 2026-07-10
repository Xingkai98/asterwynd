import json

import pytest

from agent.llm import LLMResponse, ToolCallDelta
from agent.message import Message
from tests.support.llm_harness import ScriptedLLM, stream_script, tool_response


@pytest.mark.asyncio
async def test_scripted_llm_returns_text_and_records_calls():
    llm = ScriptedLLM([LLMResponse(content="Hello", stop_reason="end_turn")])
    messages = [Message(role="user", content="hi")]

    response = await llm.chat(messages, tools=[{"name": "Echo"}], model="test-model")

    assert response.content == "Hello"
    assert llm.call_count == 1
    assert llm.calls[0].method == "chat"
    assert llm.calls[0].messages == messages
    assert llm.calls[0].tools == [{"name": "Echo"}]
    assert llm.calls[0].model == "test-model"


@pytest.mark.asyncio
async def test_scripted_llm_streams_deltas_and_completion():
    llm = ScriptedLLM([stream_script("Hel", "lo")], stream=True)

    events = [
        event
        async for event in llm.stream_chat([Message(role="user", content="hi")])
    ]

    assert [event.type for event in events] == [
        "assistant_delta",
        "assistant_delta",
        "complete",
    ]
    assert [event.delta for event in events[:2]] == ["Hel", "lo"]
    assert events[-1].response == LLMResponse(content="Hello", stop_reason="end_turn")
    assert llm.calls[0].method == "stream_chat"


@pytest.mark.asyncio
async def test_scripted_llm_supports_tool_call_response():
    tool_call = ToolCallDelta(
        id="call-1",
        name="Echo",
        arguments=json.dumps({"value": "ok"}),
    )
    llm = ScriptedLLM([tool_response(tool_calls=[tool_call])])

    response = await llm.chat([Message(role="user", content="use tool")])

    assert response.stop_reason == "tool_calls"
    assert response.tool_calls == [tool_call]


@pytest.mark.asyncio
async def test_scripted_llm_raises_provider_like_errors():
    llm = ScriptedLLM([RuntimeError("provider unavailable")])

    with pytest.raises(RuntimeError, match="provider unavailable"):
        await llm.chat([Message(role="user", content="hi")])

    assert llm.call_count == 1


@pytest.mark.asyncio
async def test_scripted_llm_uses_default_response_after_script_exhausted():
    llm = ScriptedLLM([LLMResponse(content="first")])

    first = await llm.chat([Message(role="user", content="one")])
    second = await llm.chat([Message(role="user", content="two")])

    assert first.content == "first"
    assert second.content == "default response"
    assert llm.call_count == 2
