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


# ── reasoning 结构化段（issue #256）─────────────────────────────────────

def test_reasoning_block_roundtrip_preserves_opaque():
    """opaque 载荷（如 Anthropic signature）必须在序列化往返中逐字节不变。"""
    from agent.message import ReasoningBlock

    sig = "dc864e96-18e0-424e-9e8f-17a2e5d1f64a"
    msg = Message(
        role="assistant",
        content="done",
        reasoning=[ReasoningBlock(text="先看文件A", opaque=sig)],
    )
    d = msg.to_dict()
    restored = Message.from_dict(d)

    assert len(restored.reasoning) == 1
    assert restored.reasoning[0].text == "先看文件A"
    assert restored.reasoning[0].opaque == sig


def test_reasoning_block_without_opaque_roundtrip():
    """OpenAI 路径的 reasoning_content 没有 opaque 载荷。"""
    from agent.message import ReasoningBlock

    msg = Message(role="assistant", content="x", reasoning=[ReasoningBlock(text="想想")])
    restored = Message.from_dict(msg.to_dict())

    assert restored.reasoning[0].text == "想想"
    assert restored.reasoning[0].opaque is None


def test_reasoning_multiple_segments_preserve_order():
    """多段 thinking 必须保序（Anthropic interleaved thinking）。"""
    from agent.message import ReasoningBlock

    msg = Message(role="assistant", content="x", reasoning=[
        ReasoningBlock(text="A", opaque="sig-a"),
        ReasoningBlock(text="B", opaque="sig-b"),
    ])
    restored = Message.from_dict(msg.to_dict())

    assert [r.text for r in restored.reasoning] == ["A", "B"]
    assert [r.opaque for r in restored.reasoning] == ["sig-a", "sig-b"]


def test_legacy_reasoning_content_read_as_single_segment():
    """旧会话的 reasoning_content 字段读入时包成单段（Q1 保留旧字段只读）。"""
    legacy = {"role": "assistant", "content": "x", "reasoning_content": "我之前在想"}
    msg = Message.from_dict(legacy)

    assert len(msg.reasoning) == 1
    assert msg.reasoning[0].text == "我之前在想"
    assert msg.reasoning[0].opaque is None


def test_no_reasoning_omits_field():
    """无 reasoning 时不产生该字段（保持既有 'None/空则不写' 约定）。"""
    msg = Message(role="assistant", content="hi")
    d = msg.to_dict()

    assert "reasoning" not in d
    assert "reasoning_content" not in d


def test_opaque_with_lone_surrogate_degrades_not_crash():
    """含 lone surrogate 的 opaque 无法持久化，应降级丢弃而非让保存崩溃（审阅 S-3）。

    lone surrogate 不是合法 Unicode 文本，json.dump(ensure_ascii=False) 会抛
    UnicodeEncodeError。真实端点签名都是 ASCII，此路径只作防御。
    """
    import json as _json
    from agent.message import ReasoningBlock

    msg = Message(role="assistant", content="x", reasoning=[
        ReasoningBlock(text="文本保留", opaque="sig\ud800tail"),
    ])
    d = msg.to_dict()
    # 不崩，且能序列化
    encoded = _json.dumps(d, ensure_ascii=False).encode("utf-8")
    assert encoded  # 没抛异常
    # text 保留、非法的 opaque 被丢弃
    assert d["reasoning"][0]["text"] == "文本保留"
    assert "opaque" not in d["reasoning"][0]


def test_opaque_without_surrogate_still_preserved():
    """正常 opaque（含非 ASCII）仍逐字节保留（不变量在合法输入上成立）。"""
    from agent.message import ReasoningBlock

    sig = "签名-with-非ASCII-中文"
    msg = Message(role="assistant", content="x", reasoning=[ReasoningBlock(text="t", opaque=sig)])
    d = msg.to_dict()

    assert d["reasoning"][0]["opaque"] == sig
