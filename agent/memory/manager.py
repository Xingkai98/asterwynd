# agent/memory/manager.py
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal, Optional, TYPE_CHECKING

from agent.message import Message, TextBlock, count_tokens_for_content

if TYPE_CHECKING:
    from agent.llm import LLM
    from agent.message import Message
    from agent.context.summarizer import Summarizer

logger = logging.getLogger("asterwynd.memory")

_enc = None


def _count_tokens(text: str) -> int:
    global _enc
    if _enc is None:
        try:
            import tiktoken
            _enc = tiktoken.get_encoding("cl100k_base")
        except ImportError:
            _enc = False  # sentinel: tiktoken not available
    if _enc is False:
        return len(text) // 4
    return len(_enc.encode(text))


@dataclass
class SummaryTier:
    """A tier record in the hierarchical running summary (L1 / L2)."""

    tier: Literal["L1", "L2"]
    content: str
    source_range: str = ""
    generated_at: str = ""

    def to_metadata(self) -> dict:
        return {
            "tier": self.tier,
            "source_range": self.source_range,
            "generated_at": self.generated_at,
        }


@dataclass(frozen=True)
class ManualCompactResult:
    compacted: bool
    before_messages: int
    after_messages: int
    before_tokens: int
    after_tokens: int
    reason: str

    def to_metadata(self) -> dict:
        return {
            "compacted": self.compacted,
            "before_messages": self.before_messages,
            "after_messages": self.after_messages,
            "before_tokens": self.before_tokens,
            "after_tokens": self.after_tokens,
            "reason": self.reason,
        }


class MemoryManager:
    def __init__(
        self,
        max_tokens: int = 100_000,
        recent_window: int = 10,
        llm: Optional["LLM"] = None,
        summarizer: Optional["Summarizer"] = None,
        compaction_gap: int = 5,
        compact_trigger_tokens: int | None = None,
        l2_trigger_tokens: int = 6_000,
    ):
        self.messages: list["Message"] = []
        self.max_tokens = max_tokens
        self.recent_window = recent_window
        self.llm = llm
        self._summarizer = summarizer
        self._compaction_gap = compaction_gap
        self.compact_trigger_tokens = compact_trigger_tokens
        self._last_compaction_iteration: int = -compaction_gap  # allow first
        self._running_summary: str = ""
        self._last_compaction_end_index: int = 0
        # L1/L2 hierarchical state (design Decision 3)
        self.l2_trigger_tokens = l2_trigger_tokens
        self._l1_chunks: list[str] = []          # accumulated L1 summaries since last L2
        self._l1_chunk_ranges: list[str] = []    # source ranges for tier metadata
        self._l2_summary: str | None = None
        self._tiers: list[SummaryTier] = []      # full tier trail

    # ------------------------------------------------------------------
    # Summarizer (lazy init for backwards compatibility)
    # ------------------------------------------------------------------

    def _get_summarizer(self) -> "Summarizer | None":
        if self._summarizer is not None:
            return self._summarizer
        if self.llm is not None:
            from agent.context.summarizer import LLMSummarizer
            self._summarizer = LLMSummarizer(self.llm)
        else:
            from agent.context.summarizer import TruncationSummarizer
            self._summarizer = TruncationSummarizer()
        return self._summarizer

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add(self, message: "Message") -> None:
        self.messages.append(message)

    def count_tokens(self, messages: list["Message"]) -> int:
        return sum(self._count_message_tokens(m) for m in messages)

    def _count_message_tokens(self, message: "Message") -> int:
        """Count a single message's tokens, caching the result on the message.

        The cache lives in the non-serialized ``Message._tokens`` field, so
        repeated ``count_tokens`` calls across iterations are O(1) for
        unchanged messages.  Compaction creates a fresh summary message and
        resume reload creates fresh messages, both with ``_tokens=None`` —
        they are recomputed on first touch.
        """
        if message._tokens is None:
            message._tokens = count_tokens_for_content(message.content, _count_tokens)
        return message._tokens

    async def compact_if_needed(
        self,
        messages: Optional[list["Message"]] = None,
        iteration: int = 0,
    ) -> bool:
        """Trigger compaction when token count reaches the threshold.

        The threshold is `compact_trigger_tokens` if configured, otherwise
        defaults to ``max_tokens - 15_000`` (reserving 15K tokens for the LLM
        response).  Minimum *compaction_gap* iterations must pass between
        compactions to avoid thrashing.
        """
        msgs = messages if messages is not None else self.messages
        total = self.count_tokens(msgs)
        threshold = self.compact_trigger_tokens if self.compact_trigger_tokens is not None else max(1, self.max_tokens - 15_000)
        if total >= threshold:
            if iteration - self._last_compaction_iteration >= self._compaction_gap:
                logger.info(
                    "[Memory] %d tokens >= %d (threshold, %d max budget), compacting",
                    total, threshold, self.max_tokens,
                )
                await self.compact(msgs)
                self._last_compaction_iteration = iteration
                return True
            else:
                logger.info(
                    "[Memory] %d tokens >= %d but compaction skipped "
                    "(last compaction at iteration %d, gap=%d, max budget=%d)",
                    total, threshold,
                    self._last_compaction_iteration, self._compaction_gap,
                    self.max_tokens,
                )
        return False

    async def compact(self, messages: Optional[list["Message"]] = None) -> bool:
        """Compress conversation history using the configured summarizer.

        On the first compaction, the entire middle message segment is
        summarised and stored as a running summary.  On subsequent
        compactions only **new** messages since the last compaction are
        summarised, and the result is merged with the existing running
        summary.

        System messages and recent messages (with their tool chains) are
        preserved.  The merged summary is injected as a **user** message
        so the agent treats it as prior-conversation context rather than
        a constraint.
        """
        msgs = messages if messages is not None else self.messages
        system = [m for m in msgs if m.role == "system"]
        non_system = [m for m in msgs if m.role != "system"]
        recent = self._recent_with_tool_chains(non_system)
        recent_boundary = max(0, len(non_system) - len(recent))

        if self._running_summary:
            # Subsequent compaction: only summarise new messages since
            # the last compaction, then merge with the running summary.
            middle = non_system[self._last_compaction_end_index : recent_boundary]
        else:
            # First compaction: summarise the full middle segment.
            middle = non_system[:recent_boundary]

        if not middle:
            # No new middle messages to summarise — still apply the
            # running summary + recent window.
            if self._running_summary:
                summary_msg = Message(role="user", content=self._running_summary)
                msgs[:] = system + [summary_msg] + recent
                self._last_compaction_end_index = 1  # summary is at non_system[0]
                logger.info(
                    "[Memory] Compacted to %d messages (no new middle, reused running summary)",
                    len(msgs),
                )
                return True
            msgs[:] = system + recent
            logger.info("[Memory] Compacted to %d messages", len(msgs))
            return True

        summarizer = self._get_summarizer()
        if summarizer is None:
            if self._running_summary:
                summary_msg = Message(role="user", content=self._running_summary)
                msgs[:] = system + [summary_msg] + recent
                self._last_compaction_end_index = 1  # summary is at non_system[0]
                logger.info(
                    "[Memory] Compacted to %d messages (no summarizer, reused running summary)",
                    len(msgs),
                )
                return True
            msgs[:] = system + recent
            logger.info("[Memory] Compacted to %d messages (no summarizer available)", len(msgs))
            return True

        # Compute advisory budget: 30% of the middle messages' token count
        # (target 20-30% of P6 per design.md §5).
        middle_tokens = self.count_tokens(middle)
        summary_budget = int(middle_tokens * 0.30)

        # Annotate incomplete tool calls in the middle segment as
        # `[call#<i>: <tool_call_id> pending]` so both LLM and truncation
        # summarizers carry the marker (design Decision: tool-call pairing).
        annotated_middle = self._annotate_pending_calls(middle, recent)

        new_summary = await summarizer.summarize(annotated_middle, budget=summary_budget)
        if not new_summary:
            if self._running_summary:
                summary_msg = Message(role="user", content=self._running_summary)
                msgs[:] = system + [summary_msg] + recent
                self._last_compaction_end_index = 1  # summary is at non_system[0]
                logger.info(
                    "[Memory] Compacted to %d messages (summary unavailable, reused running summary)",
                    len(msgs),
                )
                return True
            msgs[:] = system + recent
            logger.info("[Memory] Compacted to %d messages (summary unavailable)", len(msgs))
            return True

        if self._running_summary:
            merged = await self._merge_summaries(self._running_summary, new_summary)
            self._running_summary = merged
        else:
            self._running_summary = new_summary

        # L1/L2 hierarchical bookkeeping (design Decision 3).
        now = datetime.now(timezone.utc).isoformat()
        middle_range = (
            f"non_system[{self._last_compaction_end_index}:{recent_boundary}]"
            if self._running_summary and self._last_compaction_end_index
            else f"non_system[0:{recent_boundary}]"
        )
        self._l1_chunks.append(new_summary)
        self._l1_chunk_ranges.append(middle_range)
        self._tiers.append(SummaryTier(
            tier="L1", content=new_summary, source_range=middle_range, generated_at=now,
        ))
        accumulated = sum(_count_tokens(chunk) for chunk in self._l1_chunks)
        if len(self._l1_chunks) >= 2 and accumulated >= self.l2_trigger_tokens:
            # Compress the accumulated L1 summaries together with any earlier
            # L2 base so top-level conclusions never lose prior context.
            compress_input = ([self._l2_summary] if self._l2_summary else []) + self._l1_chunks
            l2 = await self._compress_to_l2(compress_input, budget=int(accumulated * 0.30))
            if l2:
                self._running_summary = l2
                self._l2_summary = l2
                self._tiers.append(SummaryTier(
                    tier="L2", content=l2,
                    source_range="accumulated L1", generated_at=now,
                ))
                self._l1_chunks = []
                self._l1_chunk_ranges = []
                logger.info("[Memory] L2 compression applied (%d tokens -> L2 conclusion)", accumulated)

        self._last_compaction_end_index = 1  # summary is at non_system[0]

        summary_message = Message(
            role="user",
            content=self._running_summary,
        )
        msgs[:] = system + [summary_message] + recent
        logger.info("[Memory] Compacted to %d messages with summary", len(msgs))
        return True

    async def compact_manually(
        self,
        messages: Optional[list["Message"]] = None,
    ) -> ManualCompactResult:
        msgs = messages if messages is not None else self.messages
        before_messages = len(msgs)
        before_tokens = self.count_tokens(msgs)
        non_system = [m for m in msgs if m.role != "system"]
        recent = self._recent_with_tool_chains(non_system)
        middle_count = max(0, len(non_system) - len(recent))

        if middle_count == 0:
            return ManualCompactResult(
                compacted=False,
                before_messages=before_messages,
                after_messages=before_messages,
                before_tokens=before_tokens,
                after_tokens=before_tokens,
                reason="no_eligible_messages",
            )

        await self.compact(msgs)
        return ManualCompactResult(
            compacted=True,
            before_messages=before_messages,
            after_messages=len(msgs),
            before_tokens=before_tokens,
            after_tokens=self.count_tokens(msgs),
            reason="compacted",
        )

    async def _merge_summaries(self, previous: str, new_events: str) -> str:
        """Merge a running summary with new events into one coherent summary.

        For small outputs a simple concatenation is used to avoid an LLM
        call.  Otherwise the summarizer's ``merge`` method is tried; if
        it is not supported the method falls back to concatenation.
        """
        if len(previous) + len(new_events) < 1000:
            return previous + "\n\n---\n\n" + new_events

        summarizer = self._get_summarizer()
        if summarizer is None:
            return previous + "\n\n---\n\n" + new_events

        if hasattr(summarizer, "merge"):
            try:
                result = await summarizer.merge(previous, new_events)
                if result is not None:
                    return result
            except Exception:
                logger.warning(
                    "[Memory] merge() failed, falling back to concatenation",
                    exc_info=True,
                )

        return previous + "\n\n---\n\n" + new_events

    # ------------------------------------------------------------------
    # Tool chain protection
    # ------------------------------------------------------------------

    def _recent_with_tool_chains(self, messages: list["Message"]) -> list["Message"]:
        if self.recent_window <= 0:
            return []

        start = max(0, len(messages) - self.recent_window)
        while start > 0:
            expanded = False
            for index in range(start, len(messages)):
                message = messages[index]
                if message.role != "tool" or not message.tool_call_id:
                    continue
                assistant_index = self._find_tool_call_assistant(messages, message.tool_call_id, before=index)
                if assistant_index is not None and assistant_index < start:
                    start = assistant_index
                    expanded = True
                    break
            if not expanded:
                break
        return messages[start:]

    def _find_tool_call_assistant(
        self,
        messages: list["Message"],
        tool_call_id: str,
        before: int,
    ) -> Optional[int]:
        for index in range(before - 1, -1, -1):
            message = messages[index]
            if message.role != "assistant":
                continue
            if any(getattr(tool_call, "id", None) == tool_call_id for tool_call in message.tool_calls):
                return index
        return None

    # ------------------------------------------------------------------
    # Tool-call pending annotation + L2 compression
    # ------------------------------------------------------------------

    def _annotate_pending_calls(
        self,
        messages: list["Message"],
        recent: list["Message"],
    ) -> list["Message"]:
        """Return a copy of *messages* with incomplete tool calls annotated.

        A tool call is pending when no ``tool`` result in *messages* or
        *recent* carries its ``tool_call_id``.  Each pending call is marked
        ``[call#<i>: <tool_call_id> pending]`` where ``<i>`` is its 1-based
        position within the assistant message.  The annotation is appended to
        the assistant message content so both LLMSummarizer and
        TruncationSummarizer see it.
        """
        result_ids: set[str] = set()
        for m in (*messages, *recent):
            if m.role == "tool" and m.tool_call_id:
                result_ids.add(m.tool_call_id)

        annotated: list["Message"] = []
        for m in messages:
            if m.role != "assistant" or not m.tool_calls:
                annotated.append(m)
                continue
            pending = [
                (i, tc)
                for i, tc in enumerate(m.tool_calls, 1)
                if getattr(tc, "id", None) and tc.id not in result_ids
            ]
            if not pending:
                annotated.append(m)
                continue
            markers = " ".join(f"[call#{i}: {tc.id} pending]" for i, tc in pending)
            content = m.content
            if isinstance(content, str):
                content = f"{content}\n\n{markers}" if content else markers
            else:
                content = [*content, TextBlock(text=markers)]
            annotated.append(Message(
                role=m.role,
                content=content,
                tool_call_id=m.tool_call_id,
                reasoning_content=m.reasoning_content,
                tool_calls=m.tool_calls,
            ))
        return annotated

    async def _compress_to_l2(
        self,
        tier_summaries: list[str],
        budget: int = 0,
    ) -> str | None:
        """Second-level compression of accumulated L1 summaries.

        Uses the summarizer's ``compress`` when available; falls back to
        concatenation when unsupported or on failure.
        """
        if not tier_summaries:
            return None
        summarizer = self._get_summarizer()
        if summarizer is not None and hasattr(summarizer, "compress"):
            try:
                result = await summarizer.compress(tier_summaries, budget=budget)
                if result:
                    return result
            except Exception:
                logger.warning(
                    "[Memory] L2 compress() failed, falling back to concatenation",
                    exc_info=True,
                )
        return "\n\n---\n\n".join(tier_summaries)

    def tier_metadata(self) -> list[dict]:
        """Tier trail of the hierarchical running summary (for trace/report)."""
        return [tier.to_metadata() for tier in self._tiers]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def get_messages(self) -> list["Message"]:
        return self.messages

    def clear(self) -> None:
        self.messages = [m for m in self.messages if m.role == "system"]
        self._running_summary = ""
        self._last_compaction_end_index = 0
        self._l1_chunks = []
        self._l1_chunk_ranges = []
        self._l2_summary = None
        self._tiers = []
