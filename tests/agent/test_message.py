# tests/agent/test_message.py
import pytest
from agent.message import Message

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

def test_message_serialization_without_tool_calls():
    """tool_calls 为空时，to_dict 不应包含该字段"""
    msg = Message(role="assistant", content="hello")
    data = msg.to_dict()
    assert "tool_calls" not in data