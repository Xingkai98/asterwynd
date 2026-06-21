# tests/agent/memory/test_memory.py
import pytest
from agent.memory.manager import MemoryManager
from agent.message import Message
from agent.llm import LLMResponse, ToolCallDelta


class SummaryLLM:
    def __init__(self, content: str | None = "middle summary"):
        self.content = content
        self.calls = []

    async def chat(self, messages, tools=None, model="gpt-4") -> LLMResponse:
        self.calls.append(list(messages))
        return LLMResponse(content=self.content)

def test_add_message():
    mgr = MemoryManager(max_tokens=1000)
    mgr.add(Message(role="user", content="hello"))
    assert len(mgr.messages) == 1

def test_count_tokens_approx():
    mgr = MemoryManager(max_tokens=1000)
    tokens = mgr.count_tokens([Message(role="user", content="hello world")])
    assert tokens > 0

@pytest.mark.asyncio
async def test_compact_if_needed_does_nothing_under_budget():
    mgr = MemoryManager(max_tokens=100_000_000)
    for i in range(5):
        mgr.add(Message(role="user", content=f"message {i}" * 100))
    initial_len = len(mgr.messages)
    compacted = await mgr.compact_if_needed(mgr.messages)
    assert len(mgr.messages) == initial_len
    assert compacted is False


@pytest.mark.asyncio
async def test_compact_if_needed_triggers_over_budget():
    mgr = MemoryManager(max_tokens=50)  # 很小的 budget 强制触发
    for i in range(10):
        mgr.add(Message(role="user", content=f"long message content here {i} " * 50))
    compacted = await mgr.compact_if_needed(mgr.messages)
    assert len(mgr.messages) <= 10
    assert compacted is True


@pytest.mark.asyncio
async def test_compact_if_needed_with_external_messages():
    """compact_if_needed 应接受外部 messages 列表并原地裁剪。"""
    mgr = MemoryManager(max_tokens=50, recent_window=3)
    messages = []
    for i in range(15):
        messages.append(Message(role="user", content=f"long message content here {i} " * 50))
    messages.insert(0, Message(role="system", content="system prompt"))

    original_len = len(messages)
    compacted = await mgr.compact_if_needed(messages)
    # 外部列表被原地裁剪：保留 system + 最近 recent_window 条
    assert len(messages) < original_len
    assert len(messages) >= 4  # 1 system + 3 recent
    assert compacted is True
    # system 消息应保留
    assert messages[0].role == "system"
    # mgr.messages 不受影响（内部列表仍然为空）
    assert len(mgr.messages) == 0


@pytest.mark.asyncio
async def test_compact_if_needed_with_llm_inserts_summary_message():
    llm = SummaryLLM(content="user chose the requests bug and pytest passed")
    mgr = MemoryManager(max_tokens=20, recent_window=2, llm=llm)
    messages = [
        Message(role="system", content="system prompt"),
        Message(role="user", content="old user goal " * 30),
        Message(role="assistant", content="old investigation " * 30),
        Message(role="user", content="recent question"),
        Message(role="assistant", content="recent answer"),
    ]

    compacted = await mgr.compact_if_needed(messages)

    assert compacted is True
    assert len(llm.calls) == 1
    assert [m.role for m in messages] == ["system", "system", "user", "assistant"]
    assert messages[1].content.startswith("Previous conversation summary:\n")
    assert "user chose the requests bug and pytest passed" in messages[1].content
    assert messages[2].content == "recent question"
    assert messages[3].content == "recent answer"


@pytest.mark.asyncio
async def test_compact_if_needed_with_empty_llm_summary_falls_back_to_trim():
    llm = SummaryLLM(content="")
    mgr = MemoryManager(max_tokens=20, recent_window=2, llm=llm)
    messages = [
        Message(role="system", content="system prompt"),
        Message(role="user", content="old user goal " * 30),
        Message(role="assistant", content="old investigation " * 30),
        Message(role="user", content="recent question"),
        Message(role="assistant", content="recent answer"),
    ]

    compacted = await mgr.compact_if_needed(messages)

    assert compacted is True
    assert len(llm.calls) == 1
    assert [m.role for m in messages] == ["system", "user", "assistant"]
    assert all("Previous conversation summary:" not in m.content for m in messages)


@pytest.mark.asyncio
async def test_compact_if_needed_with_llm_preserves_recent_tool_chain():
    llm = SummaryLLM(content="older context summary")
    mgr = MemoryManager(max_tokens=1, recent_window=1, llm=llm)
    messages = [
        Message(role="system", content="system"),
        Message(role="user", content="old context " * 30),
        Message(
            role="assistant",
            content="",
            tool_calls=[ToolCallDelta(id="c1", name="Echo", arguments="{}")],
        ),
        Message(role="tool", content="echo!", tool_call_id="c1"),
    ]

    compacted = await mgr.compact_if_needed(messages)

    assert compacted is True
    assert [m.role for m in messages] == ["system", "system", "assistant", "tool"]
    assert messages[2].tool_calls[0].id == messages[3].tool_call_id
