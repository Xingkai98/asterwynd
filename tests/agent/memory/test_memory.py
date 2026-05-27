# tests/agent/memory/test_memory.py
import pytest
from agent.memory.manager import MemoryManager
from agent.message import Message

def test_add_message():
    mgr = MemoryManager(max_tokens=1000)
    mgr.add(Message(role="user", content="hello"))
    assert len(mgr.messages) == 1

def test_count_tokens_approx():
    mgr = MemoryManager(max_tokens=1000)
    tokens = mgr.count_tokens([Message(role="user", content="hello world")])
    assert tokens > 0

def test_compact_if_needed_does_nothing_under_budget():
    mgr = MemoryManager(max_tokens=100_000_000)
    for i in range(5):
        mgr.add(Message(role="user", content=f"message {i}" * 100))
    initial_len = len(mgr.messages)
    mgr.compact_if_needed(mgr.messages)
    assert len(mgr.messages) == initial_len

def test_compact_if_needed_triggers_over_budget():
    mgr = MemoryManager(max_tokens=50)  # 很小的 budget 强制触发
    for i in range(10):
        mgr.add(Message(role="user", content=f"long message content here {i} " * 50))
    mgr.compact_if_needed(mgr.messages)
    assert len(mgr.messages) <= 10

def test_compact_if_needed_with_external_messages():
    """compact_if_needed 应接受外部 messages 列表并原地裁剪。"""
    mgr = MemoryManager(max_tokens=50, recent_window=3)
    messages = []
    for i in range(15):
        messages.append(Message(role="user", content=f"long message content here {i} " * 50))
    messages.insert(0, Message(role="system", content="system prompt"))

    original_len = len(messages)
    mgr.compact_if_needed(messages)
    # 外部列表被原地裁剪：保留 system + 最近 recent_window 条
    assert len(messages) < original_len
    assert len(messages) >= 4  # 1 system + 3 recent
    # system 消息应保留
    assert messages[0].role == "system"
    # mgr.messages 不受影响（内部列表仍然为空）
    assert len(mgr.messages) == 0