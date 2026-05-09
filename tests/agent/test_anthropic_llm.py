# tests/agent/test_anthropic_llm.py
"""AnthropicLLM 专项测试：SSE 流式解析、surrogate 过滤、tool_use block"""
import json as _json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from agent.anthropic_llm import AnthropicLLM, _strip_surrogates
from agent.message import Message
from agent.llm import ToolCallDelta


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _text_sse_lines(text: str, stop_reason: str = "end_turn") -> list[str]:
    """构建简单文本响应的 SSE 行。"""
    return [
        "event: message_start",
        'data: {"type":"message_start","message":{"id":"msg_1","role":"assistant","model":"claude","content":[]}}',
        "event: content_block_start",
        'data: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}',
        "event: content_block_delta",
        f'data: {{"type":"content_block_delta","index":0,"delta":{{"type":"text_delta","text":"{text}"}}}}',
        "event: content_block_stop",
        'data: {"type":"content_block_stop","index":0}',
        "event: message_delta",
        f'data: {{"type":"message_delta","delta":{{"stop_reason":"{stop_reason}"}},"usage":{{"output_tokens":1}}}}',
        "event: message_stop",
        'data: {"type":"message_stop"}',
    ]


def _mock_sse_stream(lines: list[str]):
    """创建 mock httpx stream context manager，返回 SSE lines。

    用法: mock_stream.return_value = _mock_sse_stream(lines)
    用法: mock_stream.side_effect = lambda url, json=None, **kw: (_capture(json), _mock_sse_stream(lines))[1]
    """
    class _StreamResponse:
        def __init__(self):
            self.status_code = 200
        def raise_for_status(self):
            pass
        async def aiter_lines(self):
            for line in lines:
                yield line

    class _StreamCtx:
        async def __aenter__(self):
            return _StreamResponse()
        async def __aexit__(self, *a):
            pass

    return _StreamCtx()


# ---------------------------------------------------------------------------
# _strip_surrogates 单元测试
# ---------------------------------------------------------------------------

def test_strip_surrogates_removes_high_and_low():
    """高代理和低代理字符都应该被替换为 U+FFFD"""
    assert _strip_surrogates("hello\ud800world") == "hello\ufffdworld"
    assert _strip_surrogates("test\udfffend") == "test\ufffdend"
    assert _strip_surrogates("\udc00\udc01\udc02") == "\ufffd\ufffd\ufffd"


def test_strip_surrogates_preserves_normal_text():
    """正常 Unicode 文本不受影响"""
    assert _strip_surrogates("你好世界") == "你好世界"
    assert _strip_surrogates("Hello, 世界! 🎉") == "Hello, 世界! 🎉"
    assert _strip_surrogates("") == ""


def test_strip_surrogates_empty():
    """空字符串返回空字符串"""
    assert _strip_surrogates("") == ""


# ---------------------------------------------------------------------------
# AnthropicLLM.chat 集成测试（mock httpx stream）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_anthropic_llm_sync_json_response():
    """
    流式 SSE 返回文本响应，应正确解析出 content 和 stop_reason。
    """
    llm = AnthropicLLM(api_key="test-key", base_url="https://api.minimaxi.com/anthropic")

    with patch("httpx.AsyncClient.stream") as mock_stream:
        mock_stream.return_value = _mock_sse_stream(
            _text_sse_lines("Hello from MiniMax!")
        )

        messages = [Message(role="user", content="hi")]
        response = await llm.chat(messages, model="MiniMax/Abab6.5s")

        assert response.content == "Hello from MiniMax!"
        assert response.stop_reason == "end_turn"
        assert response.tool_calls == []


@pytest.mark.asyncio
async def test_anthropic_llm_async_json_response():
    """
    标准 Anthropic API 流式 SSE 返回文本响应。
    """
    llm = AnthropicLLM(api_key="test-key")

    with patch("httpx.AsyncClient.stream") as mock_stream:
        mock_stream.return_value = _mock_sse_stream(
            _text_sse_lines("Hello from Anthropic!")
        )

        messages = [Message(role="user", content="hi")]
        response = await llm.chat(messages, model="claude-sonnet-4-20250514")

        assert response.content == "Hello from Anthropic!"


@pytest.mark.asyncio
async def test_anthropic_llm_surrogate_in_user_message():
    """
    消息中包含 surrogate character 时，不应抛出 UnicodeEncodeError。
    Regression test for: UnicodeEncodeError: surrogate not allowed
    """
    llm = AnthropicLLM(api_key="test-key")

    with patch("httpx.AsyncClient.stream") as mock_stream:
        captured_payload = {}

        def capture_stream(*args, **kwargs):
            captured_payload["json"] = kwargs.get("json")
            return _mock_sse_stream(_text_sse_lines("received"))

        mock_stream.side_effect = capture_stream

        messages = [
            Message(role="user", content="hello\udce4world"),  # 含 surrogate
        ]
        # 不应抛出 UnicodeEncodeError
        response = await llm.chat(messages, model="MiniMax/Abab6.5s")

        # payload 中的 content 应该是干净文本（surrogate 被替换）
        user_content = captured_payload["json"]["messages"][0]["content"]
        assert "\udce4" not in user_content
        assert "hello" in user_content
        assert response.content == "received"


@pytest.mark.asyncio
async def test_anthropic_llm_surrogate_in_response_text():
    """
    API 返回的 text_delta 含 surrogate 字符时，应该被正确过滤。
    """
    llm = AnthropicLLM(api_key="test-key")

    with patch("httpx.AsyncClient.stream") as mock_stream:
        # 直接构造含 surrogates 的 SSE delta
        surr_text = "normal text\udce4with surrogates"
        mock_stream.return_value = _mock_sse_stream(
            _text_sse_lines(surr_text)
        )

        messages = [Message(role="user", content="hi")]
        response = await llm.chat(messages, model="MiniMax/Abab6.5s")

        # surrogate 已被替换为 U+FFFD
        assert "\udce4" not in (response.content or "")
        assert "normal text" in (response.content or "")


@pytest.mark.asyncio
async def test_anthropic_llm_tool_use_block_conversion():
    """
    assistant 消息的 tool_calls 字段应该被转换为 Anthropic tool_use content block。
    Regression test for: 消息链缺少 assistant+tool_use 导致 400 Bad Request。
    """
    llm = AnthropicLLM(api_key="test-key")

    with patch("httpx.AsyncClient.stream") as mock_stream:
        captured_payload = {}

        def capture_stream(*args, **kwargs):
            captured_payload["json"] = kwargs.get("json")
            return _mock_sse_stream(_text_sse_lines("done"))

        mock_stream.side_effect = capture_stream

        # 模拟 AgentLoop 发来的消息结构：user -> assistant(tool_calls) -> tool_result
        messages = [
            Message(role="user", content="list files"),
            Message(
                role="assistant",
                content="",
                tool_calls=[
                    ToolCallDelta(id="call_abc", name="Bash", arguments='{"cmd": "ls"}')
                ],
            ),
            Message(role="tool", content="file1.txt\nfile2.txt", tool_call_id="call_abc"),
        ]

        response = await llm.chat(messages, tools=[], model="MiniMax/Abab6.5s")

        payload = captured_payload["json"]
        anthropic_msgs = payload["messages"]

        # 找到 assistant 那条消息
        assistant_msg = anthropic_msgs[1]
        assert assistant_msg["role"] == "assistant"

        # content 中应该包含 tool_use block
        content_blocks = assistant_msg["content"]
        tool_use_blocks = [b for b in content_blocks if b["type"] == "tool_use"]
        assert len(tool_use_blocks) == 1
        assert tool_use_blocks[0]["id"] == "call_abc"
        assert tool_use_blocks[0]["name"] == "Bash"
        assert tool_use_blocks[0]["input"] == {"cmd": "ls"}

        # tool_result 消息应该是 role=user，含 tool_result block
        tool_result_msg = anthropic_msgs[2]
        assert tool_result_msg["role"] == "user"
        assert tool_result_msg["content"][0]["type"] == "tool_result"
        assert tool_result_msg["content"][0]["tool_use_id"] == "call_abc"
