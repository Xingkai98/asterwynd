# tests/agent/test_openai_llm.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from agent.openai_llm import OpenAILLM
from agent.message import Message


def _mock_ok_response(json_body: dict) -> MagicMock:
    """Build a mock httpx.Response with status_code=200 and .json() -> json_body."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json = MagicMock(return_value=json_body)
    resp.raise_for_status = MagicMock()
    return resp


def _mock_sse_stream(lines: list[str]):
    class _StreamResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        async def aiter_lines(self):
            for line in lines:
                yield line

    class _StreamCtx:
        async def __aenter__(self):
            return _StreamResponse()

        async def __aexit__(self, *args):
            pass

    return _StreamCtx()


@pytest.mark.asyncio
async def test_openai_chat_success():
    llm = OpenAILLM(api_key="test-key", base_url="https://api.openai.com/v1")
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = _mock_ok_response({
            "choices": [{"message": {"content": "Hello!"}, "finish_reason": "stop"}],
            "usage": {"total_tokens": 10},
        })
        messages = [Message(role="user", content="Hi")]
        response = await llm.chat(messages, model="gpt-4")
        assert response.content == "Hello!"


@pytest.mark.asyncio
async def test_openai_tool_call():
    llm = OpenAILLM(api_key="test-key")
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = _mock_ok_response({
            "choices": [{
                "message": {
                    "content": None,
                    "tool_calls": [
                        {"id": "call_1", "function": {"name": "Bash", "arguments": '{"cmd": "ls"}'}}
                    ]
                },
                "finish_reason": "tool_calls"
            }],
            "usage": {"total_tokens": 50},
        })
        messages = [Message(role="user", content="Run ls")]
        response = await llm.chat(messages, model="gpt-4")
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0].name == "Bash"


@pytest.mark.asyncio
async def test_openai_stream_chat_yields_text_delta_and_complete_response():
    llm = OpenAILLM(api_key="test-key")

    with patch("httpx.AsyncClient.stream") as mock_stream:
        mock_stream.return_value = _mock_sse_stream([
            'data: {"choices":[{"delta":{"role":"assistant"},"finish_reason":null}]}',
            'data: {"choices":[{"delta":{"content":"Hel"},"finish_reason":null}]}',
            'data: {"choices":[{"delta":{"content":"lo"},"finish_reason":null}]}',
            'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}',
            "data: [DONE]",
        ])

        events = [event async for event in llm.stream_chat([Message(role="user", content="Hi")])]

    assert [event.type for event in events] == ["assistant_delta", "assistant_delta", "complete"]
    assert [event.delta for event in events[:2]] == ["Hel", "lo"]
    assert events[-1].response.content == "Hello"
    assert events[-1].response.stop_reason == "stop"


@pytest.mark.asyncio
async def test_openai_stream_chat_accumulates_tool_call_arguments():
    llm = OpenAILLM(api_key="test-key")

    with patch("httpx.AsyncClient.stream") as mock_stream:
        mock_stream.return_value = _mock_sse_stream([
            'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_1","function":{"name":"Bash","arguments":"{\\"cmd\\":"}}]},"finish_reason":null}]}',
            'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":" \\"ls\\"}"}}]},"finish_reason":null}]}',
            'data: {"choices":[{"delta":{},"finish_reason":"tool_calls"}]}',
            "data: [DONE]",
        ])

        events = [event async for event in llm.stream_chat([Message(role="user", content="Run ls")])]

    response = events[-1].response
    assert response.content is None
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].id == "call_1"
    assert response.tool_calls[0].name == "Bash"
    assert response.tool_calls[0].arguments == '{"cmd": "ls"}'


@pytest.mark.asyncio
async def test_message_to_dict_includes_tool_calls():
    from agent.llm import ToolCallDelta
    llm = OpenAILLM(api_key="test-key")
    msg = Message(
        role="assistant",
        content="",
        tool_calls=[ToolCallDelta(id="call_1", name="Bash", arguments='{"cmd":"ls"}')],
    )
    d = llm._message_to_dict(msg)
    assert d["tool_calls"] == [{
        "id": "call_1",
        "type": "function",
        "function": {"name": "Bash", "arguments": '{"cmd":"ls"}'},
    }]


@pytest.mark.asyncio
async def test_chat_logs_error_body_on_400():
    llm = OpenAILLM(api_key="test-key")
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = '{"error": "bad model name"}'
        mock_response.raise_for_status = MagicMock(side_effect=Exception("400"))
        mock_post.return_value = mock_response

        with pytest.raises(Exception):
            await llm.chat([Message(role="user", content="Hi")], model="bad-model")

        # error body should have been read for logging
        mock_response.text  # already accessed — verify mock works


# ── Multimodal content block tests ──────────────────────────────────

def _make_text_block(text="hello"):
    from agent.message import TextBlock
    return TextBlock(text=text)


def _make_image_block(data_url="data:image/png;base64,abc", file_path="/tmp/img.png"):
    from agent.message import ImageBlock, ImageUrl
    return ImageBlock(image_url=ImageUrl(url=data_url), file_path=file_path)


@pytest.mark.asyncio
async def test_multimodal_content_list_to_openai_format():
    """content list → OpenAI 多模态请求格式（视觉模型）"""
    llm = OpenAILLM(api_key="test-key")
    from agent.message import TextBlock, ImageBlock, ImageUrl

    messages = [Message(role="user", content=[
        TextBlock(text="What is this?"),
        ImageBlock(
            image_url=ImageUrl(url="data:image/png;base64,abc123"),
            file_path="/tmp/img.png",
        ),
    ])]

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = _mock_ok_response({
            "choices": [{"message": {"content": "It's a cat"}, "finish_reason": "stop"}],
            "usage": {"total_tokens": 10},
        })

        captured = {}
        async def capture(url, json=None, **kwargs):
            captured["json"] = json
            return mock_post.return_value
        mock_post.side_effect = capture

        await llm.chat(messages, model="gpt-4o")

        openai_msgs = captured["json"]["messages"]
        user_msg = openai_msgs[0]
        assert user_msg["role"] == "user"
        assert isinstance(user_msg["content"], list)
        assert user_msg["content"][0] == {"type": "text", "text": "What is this?"}
        assert user_msg["content"][1]["type"] == "image_url"
        assert user_msg["content"][1]["image_url"]["url"] == "data:image/png;base64,abc123"


@pytest.mark.asyncio
async def test_tool_message_image_injection():
    """tool 消息中 ImageBlock 被剥离并注入合成 user 消息（视觉模型）"""
    llm = OpenAILLM(api_key="test-key")
    from agent.message import TextBlock, ImageBlock, ImageUrl

    messages = [
        Message(role="user", content="read image"),
        Message(role="assistant", content="", tool_calls=[
            __import__("agent.llm", fromlist=["ToolCallDelta"]).ToolCallDelta(
                id="call_1", name="Read", arguments='{"path":"/tmp/img.png"}'
            ),
        ]),
        Message(role="tool", content=[
            TextBlock(text="[image: /tmp/img.png]"),
            ImageBlock(
                image_url=ImageUrl(url="data:image/png;base64,abc123"),
                file_path="/tmp/img.png",
            ),
        ], tool_call_id="call_1"),
    ]

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = _mock_ok_response({
            "choices": [{"message": {"content": "I see an image"}, "finish_reason": "stop"}],
            "usage": {"total_tokens": 20},
        })

        captured = {}
        async def capture(url, json=None, **kwargs):
            captured["json"] = json
            return mock_post.return_value
        mock_post.side_effect = capture

        await llm.chat(messages, model="gpt-4o")

        openai_msgs = captured["json"]["messages"]

        # 工具消息：text 保留，base64 已剥离
        tool_msg = [m for m in openai_msgs if m["role"] == "tool"]
        assert len(tool_msg) == 1
        assert isinstance(tool_msg[0]["content"], str)
        assert "[image:" in tool_msg[0]["content"]
        assert "base64" not in tool_msg[0]["content"]
        assert tool_msg[0]["tool_call_id"] == "call_1"

        # 合成 user 消息：包含图片 block，按在 tool 消息之后
        user_msgs = [m for m in openai_msgs if m["role"] == "user"]
        assert len(user_msgs) == 2  # 原始 user + 合成 user

        synthetic_user = user_msgs[1]
        assert isinstance(synthetic_user["content"], list)
        image_blocks = [b for b in synthetic_user["content"] if b.get("type") == "image_url"]
        assert len(image_blocks) == 1
        assert image_blocks[0]["image_url"]["url"] == "data:image/png;base64,abc123"
        # 合成 user 消息应在 tool 消息之后
        tool_idx = openai_msgs.index(tool_msg[0])
        synth_idx = openai_msgs.index(synthetic_user)
        assert synth_idx > tool_idx


@pytest.mark.asyncio
async def test_unknown_model_tries_vision_first():
    """未知模型先尝试发送图片（try-vision-first），成功则不再重试"""
    llm = OpenAILLM(api_key="test-key")
    from agent.message import TextBlock, ImageBlock, ImageUrl

    messages = [Message(role="user", content=[
        TextBlock(text="look at this"),
        ImageBlock(
            image_url=ImageUrl(url="data:image/png;base64,abc"),
            file_path="/tmp/img.png",
        ),
    ])]

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = _mock_ok_response({
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "usage": {"total_tokens": 5},
        })

        captured = {}
        async def capture(url, json=None, **kwargs):
            captured["json"] = json
            return mock_post.return_value
        mock_post.side_effect = capture

        await llm.chat(messages, model="gpt-4")  # 未知模型

        openai_msgs = captured["json"]["messages"]
        user_content = openai_msgs[0]["content"]
        # 未知模型首次尝试会发送图片（因为是 try_vision 模式）
        assert isinstance(user_content, list)
        assert user_content[0] == {"type": "text", "text": "look at this"}
        assert user_content[1]["type"] == "image_url"
        assert user_content[1]["image_url"]["url"] == "data:image/png;base64,abc"


@pytest.mark.asyncio
async def test_unknown_model_retries_without_images_on_400():
    """未知模型首次发送图片收到 400 后，降级重试不发送图片"""
    llm = OpenAILLM(api_key="test-key")
    from agent.message import TextBlock, ImageBlock, ImageUrl

    messages = [Message(role="user", content=[
        TextBlock(text="look at this"),
        ImageBlock(
            image_url=ImageUrl(url="data:image/png;base64,abc"),
            file_path="/tmp/img.png",
        ),
    ])]

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        # 第一次返回 400，第二次返回 200
        bad_response = MagicMock()
        bad_response.status_code = 400
        bad_response.text = '{"error": "model does not support images"}'
        bad_response.raise_for_status = MagicMock(side_effect=Exception("400"))

        ok_response = _mock_ok_response({
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "usage": {"total_tokens": 5},
        })

        call_count = [0]
        payloads = []

        async def capture(url, json=None, **kwargs):
            import copy
            payloads.append(copy.deepcopy(json))
            call_count[0] += 1
            if call_count[0] == 1:
                return bad_response
            return ok_response

        mock_post.side_effect = capture

        response = await llm.chat(messages, model="gpt-4")
        assert response.content == "ok"
        assert call_count[0] == 2

        # 首次请求：包含 image_url block
        first_msgs = payloads[0]["messages"]
        first_content = first_msgs[0]["content"]
        assert any(b.get("type") == "image_url" for b in first_content)

        # 重试请求：仅文本，无 image_url
        second_msgs = payloads[1]["messages"]
        second_content = second_msgs[0]["content"]
        assert isinstance(second_content, str) or all(
            b["type"] == "text" for b in second_content
        )


@pytest.mark.asyncio
async def test_done_sentinel_does_not_log_dropped_line_warning(caplog):
    """issue #251：[DONE] 是 OpenAI 协议的正常结束哨兵，不该被记成「丢弃坏行」。"""
    import logging

    llm = OpenAILLM(api_key="test-key")
    with patch("httpx.AsyncClient.stream") as mock_stream:
        mock_stream.return_value = _mock_sse_stream([
            'data: {"choices":[{"delta":{"content":"Hi"},"finish_reason":null}]}',
            'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}',
            "data: [DONE]",
        ])
        with caplog.at_level(logging.WARNING, logger="asterwynd.llm"):
            events = [event async for event in llm.stream_chat([Message(role="user", content="Hi")])]

    assert events[-1].response.content == "Hi"
    dropped = [r for r in caplog.records if "unparseable SSE data line" in r.getMessage()]
    assert dropped == [], f"[DONE] 不该触发丢弃告警，实际: {[r.getMessage() for r in dropped]}"


@pytest.mark.asyncio
async def test_genuinely_bad_sse_line_still_logs_warning(caplog):
    """issue #251 反向守护：真正的坏行仍须告警（修复不能把可观测性一起关掉）。"""
    import logging

    llm = OpenAILLM(api_key="test-key")
    with patch("httpx.AsyncClient.stream") as mock_stream:
        mock_stream.return_value = _mock_sse_stream([
            'data: {"choices":[{"delta":{"content":"Hi"},"finish_reason":null}]}',
            "data: {this is not json",
            'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}',
            "data: [DONE]",
        ])
        with caplog.at_level(logging.WARNING, logger="asterwynd.llm"):
            events = [event async for event in llm.stream_chat([Message(role="user", content="Hi")])]

    assert events[-1].response.content == "Hi"
    dropped = [r for r in caplog.records if "unparseable SSE data line" in r.getMessage()]
    assert len(dropped) == 1, "真正的坏行必须仍产生一条告警"


@pytest.mark.asyncio
async def test_legal_json_containing_done_literal_is_parsed_not_skipped(caplog):
    """issue #251 spec Scenario 3：合法 JSON 含 `[DONE]` 字面量时按正常 JSON 解析，
    不得因「包含该字面量」而被当作结束哨兵跳过。

    spec 举例用 `{"text":"[DONE]"}`；此处喂 OpenAI chunk 形态
    `{"choices":[{"delta":{"content":"[DONE]"}}]}`（语义等价，且是真实上游形态）。
    """
    import logging

    llm = OpenAILLM(api_key="test-key")
    with patch("httpx.AsyncClient.stream") as mock_stream:
        mock_stream.return_value = _mock_sse_stream([
            'data: {"choices":[{"delta":{"content":"[DONE]"},"finish_reason":null}]}',
            'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}',
            "data: [DONE]",
        ])
        with caplog.at_level(logging.WARNING, logger="asterwynd.llm"):
            events = [event async for event in llm.stream_chat([Message(role="user", content="Hi")])]

    # 字面量所在行必须被正常解析成 content delta（而非被当哨兵丢掉）
    assert [e.type for e in events] == ["assistant_delta", "complete"]
    assert events[0].delta == "[DONE]"
    assert events[-1].response.content == "[DONE]"
    assert [r for r in caplog.records if "unparseable" in r.getMessage()] == []


@pytest.mark.asyncio
async def test_done_like_variant_is_not_treated_as_sentinel(caplog):
    """issue #251 审阅 Issue 1：锁定 D2 的精确匹配设计意图。

    `[DONE]extra` 不是哨兵（哨兵须 strip() 后**恰好**等于），须仍按坏行告警。
    这条断言拦住「把 == 改成 startswith」的变异——那种写法会把 `[DONE]extra`
    这类真坏行静默吞掉（design.md D2 已否决 startswith，此前无测试锁定）。
    """
    import logging

    llm = OpenAILLM(api_key="test-key")
    with patch("httpx.AsyncClient.stream") as mock_stream:
        mock_stream.return_value = _mock_sse_stream([
            'data: {"choices":[{"delta":{"content":"Hi"},"finish_reason":null}]}',
            "data: [DONE]extra",
            'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}',
        ])
        with caplog.at_level(logging.WARNING, logger="asterwynd.llm"):
            events = [event async for event in llm.stream_chat([Message(role="user", content="Hi")])]

    assert events[-1].response.content == "Hi"
    dropped = [r for r in caplog.records if "unparseable SSE data line" in r.getMessage()]
    assert len(dropped) == 1, "`[DONE]extra` 不是哨兵，须仍按坏行告警（恰好 1 条）"


# ── reasoning 事件隔离与回传（issue #256）───────────────────────────────

@pytest.mark.asyncio
async def test_openai_reasoning_delta_is_separate_event():
    """思维链增量必须走 reasoning_delta，绝不混入 assistant_delta（issue #256 D5）。

    这条守护 OpenAI 路径的事件隔离——审查 M5 变异（把 reasoning 混入
    assistant_delta + content_parts）此前能全身而过。
    """
    llm = OpenAILLM(api_key="test-key")
    with patch("httpx.AsyncClient.stream") as mock_stream:
        mock_stream.return_value = _mock_sse_stream([
            'data: {"choices":[{"delta":{"reasoning_content":"想A"},"finish_reason":null}]}',
            'data: {"choices":[{"delta":{"reasoning_content":"想B"},"finish_reason":null}]}',
            'data: {"choices":[{"delta":{"content":"回答"},"finish_reason":null}]}',
            'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}',
            "data: [DONE]",
        ])
        events = [event async for event in llm.stream_chat([Message(role="user", content="Hi")])]

    types = [e.type for e in events]
    assert types == ["reasoning_delta", "reasoning_delta", "assistant_delta", "complete"], types
    # 思维链内容不得出现在正文 delta 里
    assistant_deltas = [e.delta for e in events if e.type == "assistant_delta"]
    assert assistant_deltas == ["回答"], assistant_deltas
    # complete 的 content 只含正文，reasoning 单独承载
    final = events[-1].response
    assert final.content == "回答"
    assert "".join(b.text for b in final.reasoning) == "想A想B"


@pytest.mark.asyncio
async def test_openai_reasoning_content_sent_back_on_replay():
    """历史 assistant 消息的 reasoning 必须回传为 reasoning_content（D3 回归）。"""
    llm = OpenAILLM(api_key="test-key")
    from agent.message import ReasoningBlock

    msg = Message(role="assistant", content="ok", reasoning=[ReasoningBlock(text="之前在想")])
    messages = llm._build_openai_messages([msg])

    assistant_msgs = [m for m in messages if m["role"] == "assistant"]
    assert assistant_msgs[0]["reasoning_content"] == "之前在想", "reasoning 未回传"


@pytest.mark.asyncio
async def test_openai_no_reasoning_omits_field():
    """无 reasoning 时请求体不含 reasoning_content（回归保护）。"""
    llm = OpenAILLM(api_key="test-key")
    msg = Message(role="assistant", content="ok")
    messages = llm._build_openai_messages([msg])
    assistant_msgs = [m for m in messages if m["role"] == "assistant"]
    assert "reasoning_content" not in assistant_msgs[0]
