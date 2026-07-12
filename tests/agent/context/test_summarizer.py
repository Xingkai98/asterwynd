"""Tests for summarizer strategies and MemoryManager compression refactoring.

Phase 4: context compression with pluggable summarizers.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agent.context.summarizer import (
    LLMSummarizer,
    Summarizer,
    TruncationSummarizer,
    _format_messages_for_summary,
    _message_text,
    _truncate_tool_outputs,
    _MAX_TOOL_OUTPUT_CHARS,
)
from agent.llm import LLMResponse
from agent.llm import ToolCallDelta
from agent.message import Message


# ---------------------------------------------------------------------------
# Summarizer protocol
# ---------------------------------------------------------------------------

class TestSummarizerProtocol:
    """LLMSummarizer and TruncationSummarizer satisfy the Summarizer protocol."""

    def test_llm_summarizer_is_summarizer(self):
        llm = MagicMock()
        assert isinstance(LLMSummarizer(llm), Summarizer)

    def test_truncation_summarizer_is_summarizer(self):
        assert isinstance(TruncationSummarizer(), Summarizer)


# ---------------------------------------------------------------------------
# LLMSummarizer
# ---------------------------------------------------------------------------

class TestLLMSummarizer:
    async def test_returns_empty_for_no_messages(self):
        llm = MagicMock()
        summarizer = LLMSummarizer(llm)
        result = await summarizer.summarize([])
        assert result == ""

    async def test_produces_four_section_summary(self):
        llm = MagicMock()
        llm.chat = AsyncMock(return_value=LLMResponse(
            content="""## 已完成
- created file.py

## 关键决策
- used pytest

## 进行中
- writing tests

## 阻塞与待办
- need CI config""",
            tool_calls=[],
            stop_reason="end_turn",
        ))
        summarizer = LLMSummarizer(llm)
        messages = [
            Message(role="user", content="write tests"),
            Message(role="assistant", content="ok, let me create the test file"),
        ]
        result = await summarizer.summarize(messages)
        assert "已完成" in result
        assert "关键决策" in result
        assert "进行中" in result
        assert "阻塞与待办" in result

    async def test_llm_call_receives_formatted_messages(self):
        llm = MagicMock()
        llm.chat = AsyncMock(
            return_value=LLMResponse(
                content="## 已完成\n- ok\n\n## 关键决策\n- none\n\n"
                        "## 进行中\n- wip\n\n## 阻塞与待办\n- none",
                tool_calls=[],
                stop_reason="end_turn",
            )
        )
        summarizer = LLMSummarizer(llm)
        messages = [Message(role="user", content="hello world")]
        await summarizer.summarize(messages)

        call_args = llm.chat.call_args
        user_message = call_args[1]["messages"][1]
        prompt_text = user_message.content
        assert "hello world" in prompt_text
        assert "已完成" in prompt_text
        assert "关键决策" in prompt_text

    async def test_returns_empty_on_llm_failure(self):
        llm = MagicMock()
        llm.chat = AsyncMock(side_effect=RuntimeError("API error"))
        summarizer = LLMSummarizer(llm)
        result = await summarizer.summarize([Message(role="user", content="hi")])
        assert result == ""

    async def test_returns_empty_on_empty_response(self):
        llm = MagicMock()
        llm.chat = AsyncMock(return_value=LLMResponse(
            content="", tool_calls=[], stop_reason="end_turn",
        ))
        summarizer = LLMSummarizer(llm)
        result = await summarizer.summarize([Message(role="user", content="hi")])
        assert result == ""


# ---------------------------------------------------------------------------
# Format helpers
# ---------------------------------------------------------------------------

class TestFormatMessagesForSummary:
    def test_formats_user_message(self):
        messages = [Message(role="user", content="hello")]
        text = _format_messages_for_summary(messages)
        assert "1. user: hello" in text

    def test_formats_assistant_with_tool_calls(self):
        messages = [
            Message(
                role="assistant",
                content="let me check",
                tool_calls=[ToolCallDelta(id="c1", name="Read", arguments="{}")],
            ),
        ]
        text = _format_messages_for_summary(messages)
        assert "assistant: let me check" in text
        assert "tool_calls: Read(c1)" in text

    def test_formats_tool_message_with_call_id(self):
        messages = [Message(role="tool", content="result", tool_call_id="c1")]
        text = _format_messages_for_summary(messages)
        assert "tool[c1]" in text

    def test_formats_empty_message(self):
        messages = [Message(role="assistant", content="")]
        text = _format_messages_for_summary(messages)
        assert "<empty>" in text


class TestMessageText:
    def test_string_content(self):
        msg = Message(role="user", content="hello")
        assert _message_text(msg) == "hello"

    def test_list_content_with_text_blocks(self):
        from agent.message import TextBlock
        msg = Message(role="user", content=[TextBlock(text="hello")])
        assert _message_text(msg) == "hello"

    def test_list_content_with_image_blocks(self):
        from agent.message import ImageBlock
        msg = Message(role="user", content=[ImageBlock(file_path="img.png")])
        assert "img.png" in _message_text(msg)


# ---------------------------------------------------------------------------
# TruncationSummarizer
# ---------------------------------------------------------------------------

class TestTruncationSummarizer:
    async def test_truncates_long_tool_output(self):
        summarizer = TruncationSummarizer(max_tool_output_chars=10)
        messages = [
            Message(role="user", content="run the build"),
            Message(role="assistant", content="", tool_calls=[
                ToolCallDelta(id="c1", name="Bash", arguments="{}"),
            ]),
            Message(role="tool", content="a" * 200, tool_call_id="c1"),
        ]
        result = await summarizer.summarize(messages)
        # Tool output should be truncated to 10 chars
        assert "a" * 10 + "…[截断]" in result
        assert "a" * 200 not in result  # original long content not present

    async def test_truncates_long_user_message(self):
        summarizer = TruncationSummarizer(max_tool_output_chars=500)
        messages = [Message(role="user", content="x" * 300)]
        result = await summarizer.summarize(messages)
        assert "…" in result
        assert len(result) < 300

    async def test_truncates_long_assistant_message(self):
        summarizer = TruncationSummarizer(max_tool_output_chars=500)
        messages = [Message(role="assistant", content="y" * 300)]
        result = await summarizer.summarize(messages)
        assert "…" in result

    async def test_logs_warning_only_once(self, caplog):
        caplog.set_level("WARNING")
        # Reset class-level flag so we get a fresh warning
        TruncationSummarizer._warned = False
        summarizer = TruncationSummarizer()
        await summarizer.summarize([Message(role="user", content="hi")])
        await summarizer.summarize([Message(role="user", content="again")])
        # Warning should appear exactly once
        truncation_warnings = [r for r in caplog.records if "截断降级" in r.message]
        assert len(truncation_warnings) == 1
        TruncationSummarizer._warned = False

    async def test_returns_empty_for_no_messages(self):
        summarizer = TruncationSummarizer()
        result = await summarizer.summarize([])
        assert result == ""

    async def test_includes_tool_call_names(self):
        summarizer = TruncationSummarizer(max_tool_output_chars=500)
        messages = [
            Message(role="assistant", content="ok", tool_calls=[
                ToolCallDelta(id="c1", name="Read", arguments="{}"),
                ToolCallDelta(id="c2", name="Bash", arguments="{}"),
            ]),
        ]
        result = await summarizer.summarize(messages)
        assert "Read" in result
        assert "Bash" in result

    async def test_respects_custom_max_chars(self):
        summarizer = TruncationSummarizer(max_tool_output_chars=50)
        messages = [Message(role="tool", content="z" * 200, tool_call_id="c1")]
        result = await summarizer.summarize(messages)
        assert "z" * 50 + "…[截断]" in result


# ---------------------------------------------------------------------------
# _truncate_tool_outputs helper
# ---------------------------------------------------------------------------

class TestTruncateToolOutputs:
    def test_empty_messages(self):
        assert _truncate_tool_outputs([], 500) == ""

    def test_handles_assistant_with_no_tool_calls(self):
        messages = [Message(role="assistant", content="simple reply")]
        result = _truncate_tool_outputs(messages, 500)
        assert "simple reply" in result

    def test_handles_tool_with_short_output(self):
        messages = [Message(role="tool", content="ok", tool_call_id="c1")]
        result = _truncate_tool_outputs(messages, 500)
        assert "ok" in result


# ---------------------------------------------------------------------------
# MemoryManager compression integration tests
# ---------------------------------------------------------------------------

class TestMemoryManagerCompact:
    """2.14-2.18: MemoryManager delegates to Summarizer, respects threshold + gap."""

    @pytest.mark.asyncio
    async def test_summary_injected_as_user_message(self):
        """2.16: summary is a user message, not system."""
        from agent.memory.manager import MemoryManager

        mgr = MemoryManager(max_tokens=1, recent_window=1, compaction_gap=0)
        messages = [
            Message(role="system", content="sys"),
            Message(role="user", content="old message"),
            Message(role="assistant", content="done"),
        ]
        await mgr.compact(messages)
        # Summary should be a user message
        non_system = [m for m in messages if m.role != "system"]
        assert len(non_system) >= 1
        assert non_system[0].role == "user"

    @pytest.mark.asyncio
    async def test_compact_preserves_system_messages(self):
        """System messages pass through compaction unchanged."""
        from agent.memory.manager import MemoryManager

        mgr = MemoryManager(max_tokens=1, recent_window=1, compaction_gap=0)
        messages = [
            Message(role="system", content="sys1"),
            Message(role="system", content="sys2"),
            Message(role="user", content="old1"),
            Message(role="user", content="old2"),
            Message(role="assistant", content="done"),
        ]
        await mgr.compact(messages)
        system_msgs = [m for m in messages if m.role == "system"]
        assert len(system_msgs) == 2
        assert system_msgs[0].content == "sys1"
        assert system_msgs[1].content == "sys2"

    @pytest.mark.asyncio
    async def test_compact_preserves_tool_chain_integrity(self):
        """2.18: tool chain (assistant call + tool result) stays intact.

        The tool chain spans across the recent-window boundary — the
        tool result is in the recent window, which causes
        _recent_with_tool_chains to expand backwards and include the
        matching assistant call.
        """
        from agent.memory.manager import MemoryManager

        mgr = MemoryManager(max_tokens=1, recent_window=1, compaction_gap=0)
        messages = [
            Message(role="system", content="sys"),
            Message(role="user", content="old question"),
            Message(role="assistant", content="let me check",
                    tool_calls=[ToolCallDelta(id="c1", name="Read", arguments="{}")]),
            Message(role="tool", content="file content", tool_call_id="c1"),
        ]
        await mgr.compact(messages)
        # Tool chain should be intact (assistant call + tool result preserved)
        roles = [m.role for m in messages]
        assert "tool" in roles
        tool_idx = roles.index("tool")
        assert tool_idx > 0
        assert messages[tool_idx - 1].role == "assistant"
        # The assistant before tool should have the matching tool_call
        assert any(
            getattr(tc, "id", None) == messages[tool_idx].tool_call_id
            for tc in messages[tool_idx - 1].tool_calls
        )

    @pytest.mark.asyncio
    async def test_compact_if_needed_triggers_at_90_percent_threshold(self):
        """2.17: compaction triggers when tokens >= 90% of max_tokens."""
        from agent.memory.manager import MemoryManager

        # Use a budget that we can easily exceed with verbose text
        mgr = MemoryManager(max_tokens=1000, recent_window=10, compaction_gap=0)
        # Generate ~2000+ tokens using word-heavy text
        long_text = " ".join(
            ["the quick brown fox jumps over the lazy dog"] * 200
        )
        messages = [
            Message(role="system", content="sys"),
            Message(role="user", content=long_text),
        ]
        compacted = await mgr.compact_if_needed(messages)
        assert compacted is True

    @pytest.mark.asyncio
    async def test_compact_if_needed_skips_when_under_threshold(self):
        """No compaction when tokens are well under 90% of budget."""
        from agent.memory.manager import MemoryManager

        mgr = MemoryManager(max_tokens=100_000, recent_window=10, compaction_gap=0)
        messages = [
            Message(role="system", content="sys"),
            Message(role="user", content="short message"),
        ]
        compacted = await mgr.compact_if_needed(messages)
        assert compacted is False

    @pytest.mark.asyncio
    async def test_compact_if_needed_respects_gap(self):
        """2.17: minimum iteration gap between compactions."""
        from agent.memory.manager import MemoryManager

        mgr = MemoryManager(max_tokens=1000, recent_window=10, compaction_gap=5)
        long_text = " ".join(
            ["the quick brown fox jumps over the lazy dog"] * 200
        )
        messages = [
            Message(role="system", content="sys"),
            Message(role="user", content=long_text),
        ]

        # First compaction at iteration 0 — should trigger
        compacted = await mgr.compact_if_needed(messages, iteration=0)
        assert compacted is True

        # Reset messages and try at iteration 2 (< gap of 5) — should skip
        messages[:] = [
            Message(role="system", content="sys"),
            Message(role="user", content=long_text),
        ]
        compacted = await mgr.compact_if_needed(messages, iteration=2)
        assert compacted is False

        # At iteration 7 (7 - 0 = 7 >= 5) — should trigger again
        compacted = await mgr.compact_if_needed(messages, iteration=7)
        assert compacted is True

    @pytest.mark.asyncio
    async def test_compact_if_needed_noop_when_no_eligible_messages(self):
        """Compaction is triggered but preserves system-only message lists."""
        from agent.memory.manager import MemoryManager

        mgr = MemoryManager(max_tokens=1, recent_window=10, compaction_gap=0)
        messages = [Message(role="system", content="only system")]
        compacted = await mgr.compact_if_needed(messages)
        # Compaction triggers (above 90% threshold) but there's nothing
        # to summarise — system messages pass through unchanged.
        assert compacted is True
        assert len(messages) == 1
        assert messages[0].role == "system"

    @pytest.mark.asyncio
    async def test_compact_with_custom_summarizer(self):
        """MemoryManager uses an externally-provided Summarizer."""
        from agent.memory.manager import MemoryManager
        from agent.context.summarizer import Summarizer

        class FakeSummarizer:
            name = "fake"

            async def summarize(self, messages, budget=0):
                return "custom summary"

        fake = FakeSummarizer()
        assert isinstance(fake, Summarizer)

        mgr = MemoryManager(max_tokens=1, recent_window=1, summarizer=fake, compaction_gap=0)
        messages = [
            Message(role="system", content="sys"),
            Message(role="user", content="old1"),
            Message(role="user", content="old2"),
            Message(role="assistant", content="done"),
        ]
        await mgr.compact(messages)
        non_system = [m for m in messages if m.role != "system"]
        assert non_system[0].role == "user"
        assert non_system[0].content == "custom summary"
