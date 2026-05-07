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