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


def test_clear_preserves_system_messages():
    mgr = MemoryManager(max_tokens=1000)
    mgr.messages = [
        Message(role="system", content="system"),
        Message(role="user", content="user"),
        Message(role="assistant", content="assistant"),
        Message(role="tool", content="tool", tool_call_id="call-1"),
    ]

    mgr.clear()

    assert [message.role for message in mgr.messages] == ["system"]
    assert mgr.messages[0].content == "system"


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
    # Summary is now injected as a user message (per design.md §5)
    assert [m.role for m in messages] == ["system", "user", "user", "assistant"]
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
    # Empty summary → middle dropped
    assert [m.role for m in messages] == ["system", "user", "assistant"]
    assert all("Previous conversation summary:" not in str(m.content) for m in messages)


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
    # Summary is now a user message (design.md §5), preserving the tool chain
    assert [m.role for m in messages] == ["system", "user", "assistant", "tool"]
    assert messages[2].tool_calls[0].id == messages[3].tool_call_id


@pytest.mark.asyncio
async def test_manual_compact_reports_noop_without_eligible_history():
    mgr = MemoryManager(recent_window=2)
    messages = [
        Message(role="system", content="system"),
        Message(role="user", content="recent question"),
        Message(role="assistant", content="recent answer"),
    ]

    result = await mgr.compact_manually(messages)

    assert result.compacted is False
    assert result.reason == "no_eligible_messages"
    assert result.before_messages == result.after_messages == 3
    assert [message.content for message in messages] == [
        "system",
        "recent question",
        "recent answer",
    ]


@pytest.mark.asyncio
async def test_manual_compact_forces_compaction_under_token_budget():
    mgr = MemoryManager(max_tokens=100_000_000, recent_window=2)
    messages = [
        Message(role="system", content="system"),
        Message(role="user", content="old one"),
        Message(role="assistant", content="old two"),
        Message(role="user", content="recent question"),
        Message(role="assistant", content="recent answer"),
    ]

    result = await mgr.compact_manually(messages)

    assert result.compacted is True
    assert result.reason == "compacted"
    assert result.before_messages == 5
    # Old: middle dropped → 3.  New: middle summarised → system + summary + 2 recent = 4
    assert result.after_messages == 4
    assert messages[0].content == "system"
    assert messages[3].content == "recent answer"


# ── Multimodal compact tests ────────────────────────────────────────

@pytest.mark.asyncio
async def test_compact_replaces_image_blocks_in_middle_messages():
    """middle 消息中的 ImageBlock 应降级为 [image: path] 文本引用"""
    from agent.message import TextBlock, ImageBlock, ImageUrl

    llm = SummaryLLM(content="older context summary")
    mgr = MemoryManager(max_tokens=1, recent_window=2, llm=llm)
    messages = [
        Message(role="system", content="system prompt"),
        Message(role="user", content=[
            TextBlock(text="old question with image " * 10),
            ImageBlock(
                image_url=ImageUrl(url="data:image/png;base64,abcdef"),
                file_path="/tmp/screenshot.png",
            ),
        ]),
        Message(role="assistant", content="old answer " * 10),
        Message(role="user", content="recent query"),
        Message(role="assistant", content="recent answer"),
    ]

    compacted = await mgr.compact_if_needed(messages)

    assert compacted is True
    assert len(llm.calls) == 1
    # Summary is now a user message (design.md §5)
    assert [m.role for m in messages] == ["system", "user", "user", "assistant"]
    # summary 包含 LLM 生成的内容
    assert "older context summary" in messages[1].content
    # recent window 完整保留（纯文本消息）
    assert messages[3].content == "recent answer"


def test_count_tokens_with_image_blocks():
    """ImageBlock 按 1000 token/张估算"""
    from agent.message import TextBlock, ImageBlock, ImageUrl

    mgr = MemoryManager(max_tokens=1000)
    messages = [
        Message(role="user", content=[
            TextBlock(text="hello"),
            ImageBlock(image_url=ImageUrl(url="data:image/png;base64,abc")),
        ]),
    ]
    tokens = mgr.count_tokens(messages)
    # "hello" tokens + 1000 for image
    assert tokens > 1000


# ── Incremental token counting (task 1.1) ────────────────────────────

def _count_calls_fixture(monkeypatch):
    """Monkeypatch the encoder so each tokenization call is observable."""
    import agent.memory.manager as manager_mod

    real = manager_mod._count_tokens
    calls = {"n": 0}

    def counting(text: str) -> int:
        calls["n"] += 1
        return real(text)

    monkeypatch.setattr(manager_mod, "_count_tokens", counting)
    return calls


def test_second_count_is_all_cache_hits(monkeypatch):
    mgr = MemoryManager(max_tokens=1000)
    calls = _count_calls_fixture(monkeypatch)
    msgs = [Message(role="user", content="hello world " * 10) for _ in range(5)]
    mgr.count_tokens(msgs)
    first = calls["n"]
    assert first == 5  # each message tokenized once
    mgr.count_tokens(msgs)
    assert calls["n"] == first  # all hits, no re-tokenization


def test_newly_appended_message_counts_once(monkeypatch):
    mgr = MemoryManager(max_tokens=1000)
    calls = _count_calls_fixture(monkeypatch)
    msgs = [Message(role="user", content="alpha " * 20) for _ in range(3)]
    mgr.count_tokens(msgs)
    first = calls["n"]
    msgs.append(Message(role="user", content="beta " * 20))
    mgr.count_tokens(msgs)
    assert calls["n"] == first + 1  # only the new message tokenized


@pytest.mark.asyncio
async def test_fresh_message_recomputes_after_compaction(monkeypatch):
    """compact() creates a fresh summary message whose tokens are recomputed."""
    mgr = MemoryManager(max_tokens=1, recent_window=1, llm=SummaryLLM("sum"),
                        compaction_gap=0)
    calls = _count_calls_fixture(monkeypatch)
    messages = [
        Message(role="system", content="sys"),
        Message(role="user", content="old " * 20),
        Message(role="assistant", content="done"),
    ]
    mgr.count_tokens(messages)
    calls_before_compact = calls["n"]
    await mgr.compact(messages)
    # The summary message is new -> counted once on next count.
    mgr.count_tokens(messages)
    assert calls["n"] >= calls_before_compact + 1


@pytest.mark.asyncio
async def test_message_tokens_field_not_serialized():
    from agent.message import Message as M
    msg = M(role="user", content="hi")
    assert msg.to_dict()["content"] == "hi"
    assert "_tokens" not in msg.to_dict()
    roundtrip = M.from_dict({"role": "user", "content": "hi"})
    assert roundtrip._tokens is None


# ── Pending tool-call annotation (task 1.4) ───────────────────────────

class RecordingSummarizer:
    """Summarizer that records the messages passed to summarize()."""
    name = "recording"

    def __init__(self):
        self.summarize_calls = []

    async def summarize(self, messages, budget=0):
        self.summarize_calls.append(list(messages))
        return "summary"

    async def merge(self, previous, new_events, budget=0):
        return None

    async def compress(self, tier_summaries, budget=0):
        return "L2 conclusion"


def _format_prompt(messages):
    from agent.context.summarizer import _format_messages_for_summary
    return _format_messages_for_summary(messages)


@pytest.mark.asyncio
async def test_pending_call_annotated_in_summarizer_input():
    recorder = RecordingSummarizer()
    mgr = MemoryManager(max_tokens=1, recent_window=1, summarizer=recorder, compaction_gap=0)
    messages = [
        Message(role="system", content="sys"),
        Message(role="user", content="old"),
        Message(role="assistant", content="", tool_calls=[
            ToolCallDelta(id="c1", name="Read", arguments="{}"),
        ]),
        Message(role="user", content="recent"),
    ]
    await mgr.compact(messages)
    assert recorder.summarize_calls
    prompt = _format_prompt(recorder.summarize_calls[0])
    assert "[call#1: c1 pending]" in prompt


@pytest.mark.asyncio
async def test_completed_middle_chain_not_marked_pending():
    recorder = RecordingSummarizer()
    mgr = MemoryManager(max_tokens=1, recent_window=1, summarizer=recorder, compaction_gap=0)
    messages = [
        Message(role="system", content="sys"),
        Message(role="user", content="old"),
        Message(role="assistant", content="", tool_calls=[
            ToolCallDelta(id="c1", name="Read", arguments="{}"),
        ]),
        Message(role="tool", content="result", tool_call_id="c1"),
        Message(role="user", content="recent"),
    ]
    await mgr.compact(messages)
    prompt = _format_prompt(recorder.summarize_calls[0])
    assert "pending" not in prompt


@pytest.mark.asyncio
async def test_multiple_pending_calls_numbered_sequentially():
    recorder = RecordingSummarizer()
    mgr = MemoryManager(max_tokens=1, recent_window=1, summarizer=recorder, compaction_gap=0)
    messages = [
        Message(role="system", content="sys"),
        Message(role="user", content="old"),
        Message(role="assistant", content="", tool_calls=[
            ToolCallDelta(id="c1", name="Read", arguments="{}"),
            ToolCallDelta(id="c2", name="Grep", arguments="{}"),
        ]),
        Message(role="tool", content="result", tool_call_id="c1"),  # only c1 complete
        Message(role="user", content="recent"),
    ]
    await mgr.compact(messages)
    prompt = _format_prompt(recorder.summarize_calls[0])
    assert "[call#1: c1 pending]" not in prompt
    assert "[call#2: c2 pending]" in prompt


@pytest.mark.asyncio
async def test_pending_annotation_visible_to_truncation_summarizer():
    from agent.context.summarizer import TruncationSummarizer
    recorder = TruncationSummarizer(max_tool_output_chars=500)
    mgr = MemoryManager(max_tokens=1, recent_window=1, summarizer=recorder, compaction_gap=0)
    messages = [
        Message(role="system", content="sys"),
        Message(role="user", content="old"),
        Message(role="assistant", content="", tool_calls=[
            ToolCallDelta(id="c1", name="Read", arguments="{}"),
        ]),
        Message(role="user", content="recent"),
    ]
    await mgr.compact(messages)
    assert "[call#1: c1 pending]" in mgr._running_summary


# ── L1/L2 hierarchical compaction (task 1.5) ──────────────────────────

@pytest.mark.asyncio
async def test_l2_compression_triggered_and_metadata_recorded():
    recorder = RecordingSummarizer()
    mgr = MemoryManager(max_tokens=1, recent_window=1, summarizer=recorder,
                        compaction_gap=0, l2_trigger_tokens=1)
    messages = [
        Message(role="system", content="sys"),
        Message(role="user", content="old1"),
        Message(role="assistant", content="a1"),
        Message(role="user", content="recent1"),
    ]
    await mgr.compact(messages)
    assert mgr._l2_summary is None  # only one L1 chunk so far

    messages.append(Message(role="user", content="old2"))
    messages.append(Message(role="user", content="recent2"))
    await mgr.compact(messages)

    assert mgr._l2_summary == "L2 conclusion"
    assert mgr._running_summary == "L2 conclusion"
    tiers = mgr.tier_metadata()
    assert any(t["tier"] == "L2" for t in tiers)
    assert any(t["tier"] == "L1" for t in tiers)
    # L2 conclusion survives clear-independent state; chunks reset.
    assert mgr._l1_chunks == []


@pytest.mark.asyncio
async def test_no_l2_below_threshold():
    recorder = RecordingSummarizer()
    mgr = MemoryManager(max_tokens=1, recent_window=1, summarizer=recorder,
                        compaction_gap=0, l2_trigger_tokens=100_000)
    messages = [
        Message(role="system", content="sys"),
        Message(role="user", content="old1"),
        Message(role="assistant", content="a1"),
        Message(role="user", content="recent1"),
    ]
    await mgr.compact(messages)
    messages.append(Message(role="user", content="old2"))
    messages.append(Message(role="user", content="recent2"))
    await mgr.compact(messages)
    assert mgr._l2_summary is None
    assert "L2 conclusion" not in mgr._running_summary


@pytest.mark.asyncio
async def test_resume_roundtrip_keeps_pending_marker():
    """Unfinished tool_call survives message serialization + re-compaction (resume).

    SessionSnapshot reload re-runs compaction on the deserialized messages;
    the pending marker must be re-detected from the fresh Message objects
    (tool_calls preserved by to_dict/from_dict, _tokens reset to None).
    """
    recorder = RecordingSummarizer()
    mgr = MemoryManager(max_tokens=1, recent_window=1, summarizer=recorder, compaction_gap=0)
    messages = [
        Message(role="system", content="sys"),
        Message(role="user", content="old"),
        Message(role="assistant", content="", tool_calls=[
            ToolCallDelta(id="c1", name="Read", arguments="{}"),
        ]),
        Message(role="user", content="recent"),
    ]
    # Simulate session save/load: serialize to dict and back.
    reloaded = [Message.from_dict(m.to_dict()) for m in messages]
    await mgr.compact(reloaded)
    prompt = _format_prompt(recorder.summarize_calls[0])
    assert "[call#1: c1 pending]" in prompt


@pytest.mark.asyncio
async def test_clear_resets_tier_state():
    recorder = RecordingSummarizer()
    mgr = MemoryManager(max_tokens=1, recent_window=1, summarizer=recorder,
                        compaction_gap=0, l2_trigger_tokens=1)
    messages = [Message(role="user", content="old")]
    await mgr.compact(messages)
    mgr.clear()
    assert mgr._l1_chunks == []
    assert mgr._l2_summary is None
    assert mgr._tiers == []
