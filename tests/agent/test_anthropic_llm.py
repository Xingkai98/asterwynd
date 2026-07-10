# tests/agent/test_anthropic_llm.py
"""AnthropicLLM 专项测试：非流式解析、SSE 流式、surrogate 过滤、tool_use block"""
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
    """创建 mock httpx stream context manager，返回 SSE lines。"""
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


def _mock_sse_http_error(status_code: int = 400):
    """创建会在 raise_for_status 抛出 HTTPStatusError 的 stream context。"""
    import httpx

    class _StreamResponse:
        def __init__(self):
            self.status_code = status_code
            self.request = MagicMock()
        def raise_for_status(self):
            raise httpx.HTTPStatusError(
                str(status_code),
                request=self.request,
                response=MagicMock(status_code=status_code),
            )
        async def aiter_lines(self):
            return
            yield

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
    MiniMax 代理返回的 response.json() 是同步 dict，不是 coroutine。
    AnthropicLLM 应该能正确处理（不报 'object dict can't be used in await'）。
    """
    llm = AnthropicLLM(api_key="test-key", base_url="https://api.minimaxi.com/anthropic")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_response = MagicMock()
        mock_response.json = MagicMock(return_value={
            "id": "msg_test",
            "type": "message",
            "role": "assistant",
            "content": [{"type": "text", "text": "Hello from MiniMax!"}],
            "stop_reason": "end_turn",
        })
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        messages = [Message(role="user", content="hi")]
        response = await llm.chat(messages, model="MiniMax/Abab6.5s")

        assert response.content == "Hello from MiniMax!"
        assert response.stop_reason == "end_turn"
        assert response.tool_calls == []


@pytest.mark.asyncio
async def test_anthropic_llm_async_json_response():
    """
    标准 Anthropic API 的 response.json() 是 async coroutine。
    验证两种模式共存都正常工作。
    """
    llm = AnthropicLLM(api_key="test-key")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_response = MagicMock()
        mock_response.json = AsyncMock(return_value={
            "id": "msg_test",
            "type": "message",
            "role": "assistant",
            "content": [{"type": "text", "text": "Hello from Anthropic!"}],
            "stop_reason": "end_turn",
        })
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

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

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        captured_payload = {}

        async def capture_post(url, json=None, **kwargs):
            captured_payload["json"] = json
            mock_response = MagicMock()
            mock_response.json = AsyncMock(return_value={
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": "received"}],
                "stop_reason": "end_turn",
            })
            mock_response.raise_for_status = MagicMock()
            return mock_response

        mock_post.side_effect = capture_post

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
    API 返回的 text block 含 surrogate 字符时，应该被正确过滤。
    """
    llm = AnthropicLLM(api_key="test-key")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_response = MagicMock()
        mock_response.json = MagicMock(return_value={
            "id": "msg_test",
            "type": "message",
            "role": "assistant",
            "content": [
                {"type": "text", "text": "normal text\udce4with surrogates"}
            ],
            "stop_reason": "end_turn",
        })
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

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

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        captured_payload = {}

        async def capture_post(url, json=None, **kwargs):
            captured_payload["json"] = json
            mock_response = MagicMock()
            mock_response.json = AsyncMock(return_value={
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": "done"}],
                "stop_reason": "end_turn",
            })
            mock_response.raise_for_status = MagicMock()
            return mock_response

        mock_post.side_effect = capture_post

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


@pytest.mark.asyncio
async def test_anthropic_llm_nonstream_text_and_tool_use_stop_reason():
    """Non-stream tool_use responses should map to stop_reason=tool_calls."""
    llm = AnthropicLLM(api_key="test-key")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_response = MagicMock()
        mock_response.json = MagicMock(return_value={
            "id": "msg_test",
            "type": "message",
            "role": "assistant",
            "content": [
                {"type": "text", "text": "I will run a command."},
                {"type": "tool_use", "id": "tool_1", "name": "Bash", "input": {"cmd": "pwd"}},
            ],
            "stop_reason": "tool_use",
        })
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        response = await llm.chat([Message(role="user", content="where am I?")])

        assert response.content == "I will run a command."
        assert response.stop_reason == "tool_calls"
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0].id == "tool_1"
        assert response.tool_calls[0].name == "Bash"
        assert _json.loads(response.tool_calls[0].arguments) == {"cmd": "pwd"}


# ---------------------------------------------------------------------------
# 流式 SSE 测试（stream=True）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_anthropic_llm_stream_sse_text():
    """stream=True 时，SSE 流式返回文本响应。"""
    llm = AnthropicLLM(api_key="test-key")
    llm.stream = True

    with patch("httpx.AsyncClient.stream") as mock_stream:
        mock_stream.return_value = _mock_sse_stream(
            _text_sse_lines("Hello via SSE!")
        )

        messages = [Message(role="user", content="hi")]
        response = await llm.chat(messages)

        assert response.content == "Hello via SSE!"
        assert response.stop_reason == "end_turn"
        assert response.tool_calls == []


@pytest.mark.asyncio
async def test_anthropic_llm_stream_chat_yields_text_delta_and_complete_response():
    """stream_chat 应暴露文本 delta，同时保留完整 LLMResponse。"""
    llm = AnthropicLLM(api_key="test-key")
    llm.stream = True

    with patch("httpx.AsyncClient.stream") as mock_stream:
        mock_stream.return_value = _mock_sse_stream(
            _text_sse_lines("Hello via SSE!")
        )

        messages = [Message(role="user", content="hi")]
        events = [event async for event in llm.stream_chat(messages)]

        assert [event.type for event in events] == ["assistant_delta", "complete"]
        assert events[0].delta == "Hello via SSE!"
        assert events[0].content == "Hello via SSE!"
        assert events[-1].response.content == "Hello via SSE!"
        assert events[-1].stop_reason == "end_turn"


@pytest.mark.asyncio
async def test_anthropic_stream_chat_unknown_model_retries_without_images_on_400():
    """Anthropic stream_chat 未知模型带图 400 后应降级无图重试。"""
    llm = AnthropicLLM(api_key="test-key")
    llm.stream = True
    from agent.message import TextBlock, ImageBlock, ImageUrl

    messages = [Message(role="user", content=[
        TextBlock(text="check this out"),
        ImageBlock(
            image_url=ImageUrl(url="data:image/png;base64,abc"),
            file_path="/tmp/img.png",
        ),
    ])]

    with patch("httpx.AsyncClient.stream") as mock_stream:
        payloads = []

        def capture(method, url, json=None, **kwargs):
            import copy
            payloads.append(copy.deepcopy(json))
            if len(payloads) == 1:
                return _mock_sse_http_error(400)
            return _mock_sse_stream(_text_sse_lines("ok"))

        mock_stream.side_effect = capture
        events = [event async for event in llm.stream_chat(messages, model="unknown-model")]

        assert events[-1].response.content == "ok"
        assert len(payloads) == 2
        first_blocks = payloads[0]["messages"][0]["content"]
        assert any(block["type"] == "image" for block in first_blocks)
        second_blocks = payloads[1]["messages"][0]["content"]
        assert all(block["type"] == "text" for block in second_blocks)


@pytest.mark.asyncio
async def test_anthropic_llm_stream_sse_tool_use():
    """stream=True 时，SSE 流式应正确解析 tool_use block。"""
    llm = AnthropicLLM(api_key="test-key")
    llm.stream = True

    lines = [
        "event: message_start",
        'data: {"type":"message_start","message":{"id":"m1","role":"assistant","model":"claude","content":[]}}',
        "event: content_block_start",
        'data: {"type":"content_block_start","index":0,"content_block":{"type":"tool_use","id":"tool_001","name":"Bash","input":{}}}',
        "event: content_block_delta",
        'data: {"type":"content_block_delta","index":0,"delta":{"type":"input_json_delta","partial_json":"{\\"cmd\\": \\"ls\\"}"}}',
        "event: content_block_stop",
        'data: {"type":"content_block_stop","index":0}',
        "event: message_delta",
        'data: {"type":"message_delta","delta":{"stop_reason":"tool_use"},"usage":{"output_tokens":1}}',
        "event: message_stop",
        'data: {"type":"message_stop"}',
    ]

    with patch("httpx.AsyncClient.stream") as mock_stream:
        mock_stream.return_value = _mock_sse_stream(lines)

        messages = [Message(role="user", content="hi")]
        response = await llm.chat(messages)

        assert response.content is None
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0].name == "Bash"
        assert response.tool_calls[0].id == "tool_001"
        assert response.stop_reason == "tool_calls"


# ── Multimodal content block tests ──────────────────────────────────

@pytest.mark.asyncio
async def test_multimodal_content_to_anthropic_format():
    """content list → Anthropic 多模态格式（image_url → image source）"""
    llm = AnthropicLLM(api_key="test-key")
    from agent.message import TextBlock, ImageBlock, ImageUrl

    messages = [Message(role="user", content=[
        TextBlock(text="Look at this:"),
        ImageBlock(
            image_url=ImageUrl(url="data:image/png;base64,iVBORw0KGgo="),
            file_path="/tmp/img.png",
        ),
    ])]

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        captured = {}

        async def capture(url, json=None, **kwargs):
            captured["json"] = json
            mock_response = MagicMock()
            mock_response.json = AsyncMock(return_value={
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": "I see it"}],
                "stop_reason": "end_turn",
            })
            mock_response.raise_for_status = MagicMock()
            return mock_response

        mock_post.side_effect = capture
        await llm.chat(messages, model="claude-sonnet-4-20250514")

        anthropic_msgs = captured["json"]["messages"]
        user_content = anthropic_msgs[0]["content"]
        assert isinstance(user_content, list)
        assert user_content[0]["type"] == "text"
        assert user_content[0]["text"] == "Look at this:"
        assert user_content[1]["type"] == "image"
        assert user_content[1]["source"]["type"] == "base64"
        assert user_content[1]["source"]["media_type"] == "image/png"
        assert user_content[1]["source"]["data"] == "iVBORw0KGgo="


@pytest.mark.asyncio
async def test_unknown_model_tries_vision_first():
    """未知 Anthropic 模型先尝试发送图片，成功则不再重试"""
    llm = AnthropicLLM(api_key="test-key")
    from agent.message import TextBlock, ImageBlock, ImageUrl

    messages = [Message(role="user", content=[
        TextBlock(text="check this out"),
        ImageBlock(
            image_url=ImageUrl(url="data:image/png;base64,abc"),
            file_path="/tmp/img.png",
        ),
    ])]

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        captured = {}

        async def capture(url, json=None, **kwargs):
            captured["json"] = json
            mock_response = MagicMock()
            mock_response.json = AsyncMock(return_value={
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": "ok"}],
                "stop_reason": "end_turn",
            })
            mock_response.raise_for_status = MagicMock()
            return mock_response

        mock_post.side_effect = capture
        await llm.chat(messages, model="unknown-model")

        anthropic_msgs = captured["json"]["messages"]
        user_content = anthropic_msgs[0]["content"]
        # 未知模型首次尝试发送图片
        assert isinstance(user_content, list)
        assert user_content[0] == {"type": "text", "text": "check this out"}
        assert user_content[1]["type"] == "image"
        assert user_content[1]["source"]["data"] == "abc"


@pytest.mark.asyncio
async def test_unknown_model_retries_without_images_on_400():
    """未知 Anthropic 模型首次发送图片收到 400 后，降级重试不发送图片"""
    llm = AnthropicLLM(api_key="test-key")
    from agent.message import TextBlock, ImageBlock, ImageUrl
    import httpx

    messages = [Message(role="user", content=[
        TextBlock(text="check this out"),
        ImageBlock(
            image_url=ImageUrl(url="data:image/png;base64,abc"),
            file_path="/tmp/img.png",
        ),
    ])]

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        call_count = [0]
        payloads = []

        ok_response = MagicMock()
        ok_response.json = AsyncMock(return_value={
            "id": "msg_test",
            "type": "message",
            "role": "assistant",
            "content": [{"type": "text", "text": "ok"}],
            "stop_reason": "end_turn",
        })
        ok_response.raise_for_status = MagicMock()

        async def capture(url, json=None, **kwargs):
            import copy
            payloads.append(copy.deepcopy(json))
            call_count[0] += 1
            if call_count[0] == 1:
                raise httpx.HTTPStatusError("400", request=MagicMock(), response=MagicMock(status_code=400))
            return ok_response

        mock_post.side_effect = capture

        response = await llm.chat(messages, model="unknown-model")
        assert response.content == "ok"
        assert call_count[0] == 2

        # 首次请求：包含 image block
        first_msgs = payloads[0]["messages"]
        first_blocks = first_msgs[0]["content"]
        assert any(b["type"] == "image" for b in first_blocks)

        # 重试请求：仅文本，无 image
        second_msgs = payloads[1]["messages"]
        second_content = second_msgs[0]["content"]
        if isinstance(second_content, list):
            assert all(b["type"] == "text" for b in second_content)
        else:
            assert isinstance(second_content, str)
