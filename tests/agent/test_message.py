# tests/agent/test_message.py
import pytest
from agent.message import (
    Message,
    TextBlock,
    ImageBlock,
    ImageUrl,
    content_block_to_dict,
    content_block_from_dict,
    extract_text,
    count_tokens_for_content,
    tool_result_message,
    system_message,
)


def test_message_creation():
    msg = Message(role="user", content="Hello")
    assert msg.role == "user"
    assert msg.content == "Hello"

def test_message_with_tool():
    msg = Message(
        role="tool",
        content="file contents",
        tool_call_id="call_abc123",
    )
    assert msg.role == "tool"
    assert msg.tool_call_id == "call_abc123"

def test_message_serialization():
    msg = Message(role="assistant", content="test")
    data = msg.to_dict()
    assert data["role"] == "assistant"
    assert data["content"] == "test"
    restored = Message(**data)
    assert restored.content == msg.content

def test_message_with_tool_calls():
    """assistant 消息携带 tool_calls 字段（tool_use block）"""
    from agent.llm import ToolCallDelta
    msg = Message(
        role="assistant",
        content="",
        tool_calls=[
            ToolCallDelta(id="call_1", name="Bash", arguments='{"cmd":"ls"}'),
            ToolCallDelta(id="call_2", name="Read", arguments='{"path":"/tmp"}'),
        ],
    )
    assert len(msg.tool_calls) == 2
    assert msg.tool_calls[0].name == "Bash"

def test_message_serialization_with_tool_calls():
    """tool_calls 字段应正确出现在序列化结果中"""
    from agent.llm import ToolCallDelta
    msg = Message(
        role="assistant",
        content="",
        tool_calls=[ToolCallDelta(id="call_x", name="Grep", arguments='{"pattern":"TODO"}')],
    )
    data = msg.to_dict()
    assert "tool_calls" in data
    assert len(data["tool_calls"]) == 1
    assert data["tool_calls"][0]["id"] == "call_x"
    assert data["tool_calls"][0]["name"] == "Grep"


def test_message_from_dict_restores_tool_calls():
    """Message.from_dict 应将 tool_calls 还原为 ToolCallDelta 对象。"""
    from agent.llm import ToolCallDelta

    msg = Message(
        role="assistant",
        content="",
        tool_calls=[ToolCallDelta(id="call_x", name="Grep", arguments='{"pattern":"TODO"}')],
    )
    restored = Message.from_dict(msg.to_dict())

    assert isinstance(restored.tool_calls[0], ToolCallDelta)
    assert restored.tool_calls[0].id == "call_x"
    assert restored.to_dict() == msg.to_dict()


def test_message_serialization_without_tool_calls():
    """tool_calls 为空时，to_dict 不应包含该字段"""
    msg = Message(role="assistant", content="hello")
    data = msg.to_dict()
    assert "tool_calls" not in data


# ── Multimodal content block tests ──────────────────────────────────

def test_message_with_content_blocks():
    """Message.content 可以是 list[ContentBlock]"""
    msg = Message(role="user", content=[
        TextBlock(text="Look at this image:"),
        ImageBlock(
            image_url=ImageUrl(url="data:image/png;base64,abc123"),
            file_path="/tmp/test.png",
        ),
    ])
    assert isinstance(msg.content, list)
    assert len(msg.content) == 2
    assert isinstance(msg.content[0], TextBlock)
    assert msg.content[0].text == "Look at this image:"
    assert isinstance(msg.content[1], ImageBlock)
    assert msg.content[1].file_path == "/tmp/test.png"


def test_content_blocks_roundtrip():
    """多模态 content blocks 序列化/反序列化正确"""
    msg = Message(role="user", content=[
        TextBlock(text="hello"),
        ImageBlock(
            image_url=ImageUrl(url="data:image/png;base64,aaa"),
            file_path="/tmp/img.png",
        ),
    ])
    data = msg.to_dict()
    assert isinstance(data["content"], list)
    assert len(data["content"]) == 2
    assert data["content"][0] == {"type": "text", "text": "hello"}
    assert data["content"][1]["type"] == "image_url"
    assert data["content"][1]["file_path"] == "/tmp/img.png"
    assert data["content"][1]["image_url"]["url"] == "data:image/png;base64,aaa"

    restored = Message.from_dict(data)
    assert isinstance(restored.content, list)
    assert isinstance(restored.content[0], TextBlock)
    assert isinstance(restored.content[1], ImageBlock)
    assert restored.content[1].file_path == "/tmp/img.png"


def test_content_blocks_roundtrip_without_file_path():
    """ImageBlock 不包含 file_path 时反序列化也不应有"""
    msg = Message(role="user", content=[
        ImageBlock(image_url=ImageUrl(url="data:image/png;base64,bbb")),
    ])
    data = msg.to_dict()
    assert "file_path" not in data["content"][0]

    restored = Message.from_dict(data)
    assert restored.content[0].file_path is None


def test_pure_text_content_serialization_unchanged():
    """纯文本 content 序列化/反序列化行为不变"""
    msg = Message(role="user", content="plain text")
    data = msg.to_dict()
    assert data["content"] == "plain text"
    restored = Message.from_dict(data)
    assert restored.content == "plain text"


def test_extract_text_from_str():
    assert extract_text("hello") == "hello"


def test_extract_text_from_blocks():
    content = [
        TextBlock(text="first"),
        ImageBlock(image_url=ImageUrl(url="data:image/png;base64,xxx")),
        TextBlock(text="second"),
    ]
    assert extract_text(content) == "first\nsecond"


def test_extract_text_all_images():
    content = [
        ImageBlock(image_url=ImageUrl(url="data:image/png;base64,xxx")),
        ImageBlock(image_url=ImageUrl(url="data:image/png;base64,yyy")),
    ]
    assert extract_text(content) == ""


def test_count_tokens_text_only():
    def char_counter(s):
        return len(s)
    content = [TextBlock(text="hello")]
    assert count_tokens_for_content(content, char_counter) == 5


def test_count_tokens_with_images():
    def char_counter(s):
        return len(s)
    content = [
        TextBlock(text="abc"),
        ImageBlock(image_url=ImageUrl(url="data:image/png;base64,xxx")),
        TextBlock(text="def"),
    ]
    # 3 chars + 1000 (image) + 3 chars = 1006
    assert count_tokens_for_content(content, char_counter) == 1006


def test_count_tokens_str_fallback():
    def char_counter(s):
        return len(s)
    assert count_tokens_for_content("hello world", char_counter) == 11


def test_content_block_from_dict_unknown_type():
    block = content_block_from_dict({"type": "unknown", "text": "fallback"})
    assert isinstance(block, TextBlock)
    assert block.text == "fallback"


def test_tool_result_message_with_blocks():
    block = TextBlock(text="result")
    msg = tool_result_message("call_1", [block])
    assert msg.role == "tool"
    assert msg.tool_call_id == "call_1"
    assert msg.content == [block]


def test_system_message_shortcut():
    msg = system_message("you are helpful")
    assert msg.role == "system"
    assert msg.content == "you are helpful"
