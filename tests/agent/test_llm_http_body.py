"""LLM HTTP 错误 body 保留与 trace detail（issue #304）。"""
import json

import httpx
import pytest

from agent.anthropic_llm import AnthropicLLM, _http_error_text
from agent.llm import HTTP_BODY_ATTRIBUTE, raise_for_status_with_body
from agent.message import Message
from agent.openai_llm import OpenAILLM
from agent.trace_recorder import TraceRecorder

BODY = json.dumps({
    "type": "error",
    "error": {"type": "invalid_request_error", "message": "provider body sentinel"},
})


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _anthropic(handler, *, stream):
    llm = AnthropicLLM(api_key="fake", base_url="http://fake.invalid", model="claude-test")
    llm.stream = stream
    llm._client = _client(handler)
    return llm


@pytest.mark.asyncio
async def test_raise_for_status_with_body_attaches_body():
    async def handler(request):
        return httpx.Response(400, content=BODY.encode())

    async with _client(handler) as client:
        response = await client.post("http://fake.invalid/v1/messages")
        with pytest.raises(httpx.HTTPStatusError) as caught:
            await raise_for_status_with_body(response)

    assert getattr(caught.value, HTTP_BODY_ATTRIBUTE) == BODY
    assert _http_error_text(caught.value) == BODY


@pytest.mark.asyncio
async def test_anthropic_streaming_400_keeps_body():
    async def handler(request):
        return httpx.Response(400, content=BODY.encode())

    llm = _anthropic(handler, stream=True)
    try:
        with pytest.raises(httpx.HTTPStatusError) as caught:
            await llm.chat([Message(role="user", content="hi")])
    finally:
        await llm._client.aclose()

    assert getattr(caught.value, HTTP_BODY_ATTRIBUTE) == BODY
    assert _http_error_text(caught.value) == BODY


@pytest.mark.asyncio
async def test_anthropic_nonstream_400_keeps_body():
    async def handler(request):
        return httpx.Response(400, content=BODY.encode())

    llm = _anthropic(handler, stream=False)
    try:
        with pytest.raises(httpx.HTTPStatusError) as caught:
            await llm.chat([Message(role="user", content="hi")])
    finally:
        await llm._client.aclose()

    assert getattr(caught.value, HTTP_BODY_ATTRIBUTE) == BODY


@pytest.mark.asyncio
async def test_openai_nonstream_400_keeps_body():
    async def handler(request):
        return httpx.Response(400, content=BODY.encode())

    llm = OpenAILLM(api_key="fake", base_url="http://fake.invalid", model="gpt-4")
    llm.stream = False
    llm._client = _client(handler)
    try:
        with pytest.raises(httpx.HTTPStatusError) as caught:
            await llm.chat([Message(role="user", content="hi")])
    finally:
        await llm._client.aclose()

    assert getattr(caught.value, HTTP_BODY_ATTRIBUTE) == BODY


def test_trace_llm_error_detail_is_bounded():
    trace = TraceRecorder()
    trace.record_llm_error("model_error", "boom", detail="x" * 10_000)
    step = next(s for s in trace.steps if s.type == "llm_error")
    assert step.data["error_type"] == "model_error"
    assert step.data["message"] == "boom"
    assert len(step.data["detail"]) < 10_000
    assert step.data["detail"].endswith("…[truncated]")


def test_trace_llm_error_without_detail_keeps_old_shape():
    trace = TraceRecorder()
    trace.record_llm_error("network_timeout", "boom")
    step = next(s for s in trace.steps if s.type == "llm_error")
    assert step.data == {"error_type": "network_timeout", "message": "boom"}


def test_anthropic_serializes_synthetic_tool_result_as_is_error():
    from agent.llm import ToolCallDelta
    from agent.message import SYNTHETIC_TOOL_RESULT_PREFIX

    llm = AnthropicLLM(api_key="fake", base_url="http://fake.invalid", model="claude-test")
    payload = llm._build_payload([
        Message(role="user", content="go"),
        Message(role="assistant", content="", tool_calls=[
            ToolCallDelta(id="c1", name="Echo", arguments="{}"),
        ]),
        Message(role="tool", content=f"{SYNTHETIC_TOOL_RESULT_PREFIX} interrupted",
                tool_call_id="c1"),
        Message(role="tool", content="real ok", tool_call_id="c2"),
    ])

    tool_result_message = next(
        m for m in payload["messages"]
        if m["role"] == "user"
        and isinstance(m["content"], list)
        and m["content"]
        and m["content"][0].get("type") == "tool_result"
    )
    blocks = tool_result_message["content"]
    assert blocks[0]["type"] == "tool_result"
    assert blocks[0]["is_error"] is True
    assert blocks[1]["type"] == "tool_result"
    assert "is_error" not in blocks[1]


def test_openai_serializes_synthetic_tool_result_with_error_prefix():
    from agent.llm import ToolCallDelta
    from agent.message import SYNTHETIC_TOOL_RESULT_PREFIX

    llm = OpenAILLM(api_key="fake", base_url="http://fake.invalid", model="gpt-4")
    messages = llm._build_openai_messages([
        Message(role="user", content="go"),
        Message(role="assistant", content="", tool_calls=[
            ToolCallDelta(id="c1", name="Echo", arguments="{}"),
        ]),
        Message(role="tool", content=f"{SYNTHETIC_TOOL_RESULT_PREFIX} interrupted",
                tool_call_id="c1"),
        Message(role="assistant", content="", tool_calls=[
            ToolCallDelta(id="c2", name="Echo", arguments="{}"),
        ]),
        Message(role="tool", content="real ok", tool_call_id="c2"),
    ])

    assistant_messages = [m for m in messages if m["role"] == "assistant"]
    call_ids = [
        tc["id"] for message in assistant_messages for tc in message["tool_calls"]
    ]
    tool_messages = [m for m in messages if m["role"] == "tool"]
    tool_ids = [m["tool_call_id"] for m in tool_messages]
    assert sorted(call_ids) == sorted(tool_ids)
    assert len(tool_ids) == len(set(tool_ids))
    assert tool_messages[0]["content"].startswith(SYNTHETIC_TOOL_RESULT_PREFIX)
    assert not tool_messages[1]["content"].startswith(SYNTHETIC_TOOL_RESULT_PREFIX)
    assert "is_error" not in tool_messages[0]


@pytest.mark.asyncio
async def test_empty_error_body_does_not_crash_or_add_detail():
    async def handler(request):
        return httpx.Response(400, content=b"")

    async with _client(handler) as client:
        response = await client.post("http://fake.invalid/v1/messages")
        with pytest.raises(httpx.HTTPStatusError) as caught:
            await raise_for_status_with_body(response)

    assert getattr(caught.value, HTTP_BODY_ATTRIBUTE) == ""
    assert _http_error_text(caught.value) == ""


def test_real_result_colliding_with_synthetic_prefix_is_known_limitation():
    from agent.llm import ToolCallDelta
    from agent.message import SYNTHETIC_TOOL_RESULT_PREFIX

    llm = AnthropicLLM(api_key="fake", base_url="http://fake.invalid", model="claude-test")
    payload = llm._build_payload([
        Message(role="user", content="go"),
        Message(role="assistant", content="", tool_calls=[
            ToolCallDelta(id="c1", name="Echo", arguments="{}"),
        ]),
        Message(role="tool", content=f"{SYNTHETIC_TOOL_RESULT_PREFIX} a real result",
                tool_call_id="c1"),
    ])
    tool_result_message = next(
        m for m in payload["messages"]
        if m["role"] == "user"
        and isinstance(m["content"], list)
        and m["content"]
        and m["content"][0].get("type") == "tool_result"
    )
    assert tool_result_message["content"][0]["is_error"] is True  # documented collision
