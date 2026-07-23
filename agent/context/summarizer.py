# agent/context/summarizer.py
"""Pluggable summarization strategies for context compression.

The Summarizer protocol decouples *how* messages are compressed from *when*
compression is triggered by MemoryManager.
"""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable, TYPE_CHECKING

from agent.message import Message, TextBlock, ImageBlock

if TYPE_CHECKING:
    from agent.llm import LLM

logger = logging.getLogger("asterwynd.context")


_MAX_TOOL_OUTPUT_CHARS = 500


@runtime_checkable
class Summarizer(Protocol):
    """Compress a list of non-system messages into a summary string.

    *budget* is an advisory token target — the summarizer should aim to
    produce output that fits within it, but it is not a hard guarantee.
    """

    name: str

    async def summarize(self, messages: list[Message], budget: int = 0) -> str:
        """Return a summary string for the given messages.

        Returns an empty string if there is nothing worth summarising.
        """
        ...

    async def merge(self, previous: str, new_events: str, budget: int = 0) -> str | None:
        """Merge a previous running summary with a new events summary.

        Return the merged summary string, or ``None`` if merging is not
        supported (the caller should fall back to concatenation).
        """
        ...


# ---------------------------------------------------------------------------
# LLMSummarizer
# ---------------------------------------------------------------------------

_LLM_SUMMARY_SYSTEM_PROMPT = (
    "You are a coding-agent memory compressor. "
    "Your output is injected as prior-conversation context for the same agent. "
    "Preserve every file path, function name, tool name, error message, "
    "unresolved question, and key decision. "
    "Output ONLY the four-section Markdown block described in the user prompt."
)

_MERGE_SYSTEM_PROMPT = (
    "You are merging two conversation summaries for a coding agent. "
    "Synthesize them into ONE coherent four-section Markdown summary "
    "while preserving all critical context: every file path, function "
    "name, tool name, error message, unresolved question, and key "
    "decision must survive."
)

_LLM_SUMMARY_USER_TEMPLATE = """\
Summarise the following conversation segment for a coding agent.
Produce a structured Markdown summary with exactly four sections.

## 已完成
- (completed tasks — one bullet per item)

## 关键决策
- (decisions made, rationale — one bullet per item)

## 进行中
- (tasks in progress — one bullet per item)

## 阻塞与待办
- (blockers and next steps — one bullet per item)

Conversation segment:
---
{messages_text}
---"""


def _format_messages_for_summary(messages: list[Message]) -> str:
    """Render messages as a compact text block for the summariser prompt."""
    lines: list[str] = []
    for index, message in enumerate(messages, start=1):
        label = message.role
        if message.role == "tool" and message.tool_call_id:
            label = f"tool[{message.tool_call_id}]"
        content = _message_text(message)
        if not content:
            content = "<empty>"
        lines.append(f"{index}. {label}: {content}")
        if message.tool_calls:
            calls = ", ".join(
                f"{getattr(c, 'name', '<unknown>')}({getattr(c, 'id', '<no-id>')})"
                for c in message.tool_calls
            )
            lines.append(f"   tool_calls: {calls}")
    return "\n".join(lines)


def _message_text(message: Message) -> str:
    """Extract plain-text representation, replacing images with file refs."""
    content = message.content
    if isinstance(content, str):
        return content.strip()
    parts: list[str] = []
    for block in content:
        if isinstance(block, TextBlock):
            parts.append(block.text.strip())
        elif isinstance(block, ImageBlock):
            ref = block.file_path or "pasted image"
            parts.append(f"[image: {ref}]")
    return " ".join(parts)


class LLMSummarizer:
    """Four-section structured summary produced by an LLM.

    The summary is designed to be injected as a **user** message so the
    agent treats it as prior-conversation context rather than a system
    constraint.
    """

    name = "llm"

    def __init__(self, llm: "LLM") -> None:
        self._llm = llm

    async def summarize(self, messages: list[Message], budget: int = 0) -> str:
        if not messages:
            return ""

        text = _format_messages_for_summary(messages)
        budget_hint = (
            f"\n\nKeep the summary under approximately {budget} tokens."
            if budget > 0
            else ""
        )
        try:
            response = await self._llm.chat(
                messages=[
                    Message(role="system", content=_LLM_SUMMARY_SYSTEM_PROMPT),
                    Message(
                        role="user",
                        content=_LLM_SUMMARY_USER_TEMPLATE.format(messages_text=text) + budget_hint,
                    ),
                ],
                tools=None,
            )
        except Exception:
            logger.warning("LLMSummarizer: LLM call failed", exc_info=True)
            return ""

        return (response.content or "").strip()

    async def merge(self, previous: str, new_events: str, budget: int = 0) -> str | None:
        """Merge a running summary with a new events summary via LLM."""
        if not previous and not new_events:
            return None

        user_text = (
            f"## Previous Summary\n\n{previous}\n\n"
            f"## New Events Summary\n\n{new_events}"
        )

        budget_hint = (
            f"\n\nKeep the merged summary under approximately {budget} tokens."
            if budget > 0
            else ""
        )

        try:
            response = await self._llm.chat(
                messages=[
                    Message(role="system", content=_MERGE_SYSTEM_PROMPT),
                    Message(role="user", content=user_text + budget_hint),
                ],
                tools=None,
            )
        except Exception:
            logger.warning("LLMSummarizer: merge LLM call failed", exc_info=True)
            return None

        return (response.content or "").strip() or None


# ---------------------------------------------------------------------------
# TruncationSummarizer — no-LLM fallback
# ---------------------------------------------------------------------------

_TRUNCATION_WARNING = (
    "[上下文压缩警告] 无 LLM 可用，已采用截断降级策略。"
    "旧对话轮次已丢弃，工具输出已截断至前 {max_chars} 字符。"
)


def _truncate_tool_outputs(messages: list[Message], max_chars: int) -> str:
    """Build a minimal summary by truncating tool outputs."""
    lines: list[str] = []
    for msg in messages:
        if msg.role == "user":
            text = _message_text(msg)
            if len(text) > 200:
                text = text[:200] + "…"
            lines.append(f"[用户] {text}")
        elif msg.role == "assistant":
            text = _message_text(msg)
            if text:
                if len(text) > 200:
                    text = text[:200] + "…"
                lines.append(f"[助手] {text}")
            if msg.tool_calls:
                names = [getattr(c, 'name', '?') for c in msg.tool_calls]
                lines.append(f"[工具调用] {', '.join(names)}")
        elif msg.role == "tool":
            text = _message_text(msg)
            if len(text) > max_chars:
                text = text[:max_chars] + "…[截断]"
            lines.append(f"[工具结果] {text}")
    return "\n".join(lines)


class TruncationSummarizer:
    """Fallback summarizer when no LLM is available.

    Tool outputs are truncated to 500 characters; old non-system
    messages are discarded.  A warning is logged on first use.
    """

    name = "truncation"
    _warned: bool = False

    def __init__(self, max_tool_output_chars: int = _MAX_TOOL_OUTPUT_CHARS) -> None:
        self._max_chars = max_tool_output_chars

    async def summarize(self, messages: list[Message], budget: int = 0) -> str:
        if not TruncationSummarizer._warned:
            logger.warning(
                _TRUNCATION_WARNING.format(max_chars=self._max_chars),
            )
            TruncationSummarizer._warned = True
        return _truncate_tool_outputs(messages, self._max_chars)

    async def merge(self, previous: str, new_events: str, budget: int = 0) -> str | None:
        """Return None — merge is not supported; the caller falls back to concatenation."""
        return None
