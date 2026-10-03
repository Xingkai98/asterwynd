# agent/memory/manager.py
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Literal, Optional, TYPE_CHECKING

from agent.message import Message, TextBlock, count_tokens_for_content, extract_text
from agent.memory.tool_result_policy import (
    READ_PROGRESS_RE as _READ_PROGRESS_RE,
    content_bytes as _content_bytes,
    exceeds_single_threshold as _exceeds_single_threshold,
    make_preview as _make_preview,
)

if TYPE_CHECKING:
    from agent.llm import LLM
    from agent.message import Message
    from agent.context.summarizer import Summarizer

logger = logging.getLogger("asterwynd.memory")

_enc = None

#: 硬上限（D7）：token 维度 = ``max_tokens × HARD_CEILING_MULTIPLIER``。仅防抖的
#: ``compaction_gap`` SHALL NOT 成为无界增长的许可证——超硬限即无视 gap 强压。
HARD_CEILING_MULTIPLIER = 2

#: 硬上限（D7）字节维度 = ``max(HARD_CEILING_MIN_BYTES, max_tokens × HARD_CEILING_BYTES_PER_TOKEN)``。
#: 图片等内容块的 token 估算（1000/张）远低于实际字节，纯 token 判据会放行已失控的字节，
#: 故字节维度独立生效。下限（``HARD_CEILING_MIN_BYTES``）与 token 侧的 ``TOKEN_MIN``
#: 同款作用：小预算 loop（单测 / 小 ``max_tokens``）不被普通文本误触发——那种规模的
#: 常驻由 token 维度约束即可，字节维度只在真正「字节远超 token 估算」时兜底。
HARD_CEILING_BYTES_PER_TOKEN = 8
HARD_CEILING_MIN_BYTES = 512 * 1024


def _result_ref_present(content) -> bool:
    """工具结果正文是否已是「预览 + ref」形态（幂等判据）。"""
    return isinstance(content, str) and "[truncated" in content


def _message_bytes(message: "Message") -> int:
    """一条消息的常驻字节：正文 **+** assistant ``tool_calls[].arguments``（D6b）。

    一次 ``Write`` 带 300KB 正文时，300KB 住在 assistant 消息的 ``tool_calls[].arguments``
    里（不在 ``content``），只算 ``content`` 会漏掉整条大参数通道。消息侧 assistant
    ``arguments`` 至少**计入字节预算**（D6b：剪 result 不触及它，靠字节维度让硬顶/
    压缩把它带走）。
    """
    total = _content_bytes(message.content)
    for tool_call in getattr(message, "tool_calls", None) or []:
        args = getattr(tool_call, "arguments", None)
        if args:
            total += len(str(args).encode("utf-8"))
    return total


def _flatten(content) -> str:
    """``str | list[ContentBlock]`` → 文本（图片 → ``[image: <file_path|ref>]``）。"""
    from agent.memory.tool_result_policy import flatten_content

    return flatten_content(content)



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
class PruneStats:
    """``prune_tool_results`` 的可观测产出（D9：剪枝不静默）。"""

    messages_spilled: int = 0
    bytes_released: int = 0

    def to_metadata(self) -> dict:
        return {
            "messages_spilled": self.messages_spilled,
            "bytes_released": self.bytes_released,
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
        self._l1_accumulated_tokens: int = 0     # incremental L1 token accumulator
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

    def is_oversized_result(self, content) -> bool:
        """D3 单条阈判定（traffic through the manager so there is one counter）。

        The loop uses this instead of importing the private ``_count_tokens`` —
        a single counter source keeps threshold semantics consistent and lets
        tests substitute the counter in one place.
        """
        return _exceeds_single_threshold(
            content, max_tokens=self.max_tokens, counter=_count_tokens,
        )

    # ------------------------------------------------------------------
    # Tool-result spill (change tool-result-lifecycle, D3/D10)
    # ------------------------------------------------------------------

    def prune_tool_results(
        self,
        messages: Optional[list["Message"]] = None,
        *,
        current_iteration: int,
        added_iterations: dict[str, int],
        save: Optional[Callable[[str], str]] = None,
    ) -> PruneStats:
        """把陈旧的工具结果 ``messages`` 正文换成「有界预览 + ref」（D3/D10）。

        剪枝判据 = **已消费一轮** ∩（**滑出近期窗口** ∪ **单条超阈**）：

        - **已消费一轮**：``added_iterations[tool_call_id] <= current_iteration - 1``
          （A1 已拍板 ``-1``）。结果在 iteration k 入库、同轮末尾 ``_call_llm`` 已发一次、
          k+1 轮再发一次 ⇒ k+1 末尾即可剪。两个 append 点（错误 / 正常路径）都记
          ``added_iteration``，未标记的结果**不剪**（保守）。
        - **滑出窗口**：消息索引 < ``len(messages) - recent_window``（窗口按**消息条数**，
          非轮数）。
        - **单条超阈**：token 或字节任一超阈（``tool_result_policy``），**不受窗口保护**
          ——超阈结果即使新鲜、仍在窗内也替换（穿透窗口），但受「已消费一轮」保护。

        ``save(text) -> ref`` 由调用方注入（``loop.py`` 在 ``run()`` 期构造 store 与
        scope）；返回 ``None`` 或抛异常时**不谎称可回读**（D8）——仍替换正文使内存有界，
        但标记 ``[truncated]``。本方法**不碰 I/O**，只调注入的回调与判据纯函数。

        任何替换后 MUST 置 ``message._tokens = None``（D10），否则 ``count_tokens``
        返旧值、反复误触发压缩。
        """
        msgs = messages if messages is not None else self.messages
        stats_spilled = 0
        stats_bytes = 0
        window_start = len(msgs) - self.recent_window
        for index, message in enumerate(msgs):
            if message.role != "tool" or not message.tool_call_id:
                continue
            if _result_ref_present(message.content):
                continue  # already a preview — idempotent
            added = added_iterations.get(message.tool_call_id)
            if added is None or added > current_iteration - 1:
                continue  # fresh / never-marked ⇒ keep full text
            slid_out = index < window_start
            oversized = _exceeds_single_threshold(
                message.content, max_tokens=self.max_tokens, counter=_count_tokens,
            )
            if not (slid_out or oversized):
                continue
            before = _content_bytes(message.content)
            ref: str | None = None
            if save is not None:
                try:
                    ref = save(_flatten(message.content))
                except Exception:
                    logger.warning("[Memory] tool result spill failed", exc_info=True)
                    ref = None
            preview = _make_preview(message.content, ref=ref)
            message.content = preview
            message._tokens = None
            stats_spilled += 1
            stats_bytes += max(0, before - _content_bytes(preview))
        if stats_spilled:
            logger.info(
                "[Memory] spilled %d tool result(s), released %d bytes",
                stats_spilled, stats_bytes,
            )
        return PruneStats(messages_spilled=stats_spilled, bytes_released=stats_bytes)

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

        ``compaction_gap`` is anti-thrash only, NOT a license for unbounded
        growth (D7): when usage reaches a **hard ceiling** (``max_tokens × 2``
        tokens, or ``max_tokens × 8`` resident bytes), compaction is forced
        regardless of the gap.
        """
        msgs = messages if messages is not None else self.messages
        total = self.count_tokens(msgs)
        hard = self._hard_ceiling_reached(msgs, total)
        threshold = self.compact_trigger_tokens if self.compact_trigger_tokens is not None else max(1, self.max_tokens - 15_000)
        if total >= threshold:
            if hard or iteration - self._last_compaction_iteration >= self._compaction_gap:
                if hard and iteration - self._last_compaction_iteration < self._compaction_gap:
                    logger.info(
                        "[Memory] %d tokens at hard ceiling (%d max budget), compacting "
                        "despite gap",
                        total, self.max_tokens,
                    )
                else:
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
        elif hard:
            # Token estimate is low (e.g. content blocks) but resident bytes are
            # out of control — the byte dimension alone forces compaction.
            logger.info(
                "[Memory] resident bytes at hard ceiling (%d max budget), compacting "
                "despite token estimate %d",
                self.max_tokens, total,
            )
            await self.compact(msgs)
            self._last_compaction_iteration = iteration
            return True
        return False

    def _hard_ceiling_reached(self, messages: list["Message"], total_tokens: int) -> bool:
        """D7 的双维度硬上限：token **或** 常驻字节任一超限即真。"""
        if total_tokens >= self.max_tokens * HARD_CEILING_MULTIPLIER:
            return True
        byte_budget = max(
            HARD_CEILING_MIN_BYTES,
            self.max_tokens * HARD_CEILING_BYTES_PER_TOKEN,
        )
        return sum(_message_bytes(m) for m in messages) >= byte_budget

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

        # Decorate the middle segment before summarization: annotate incomplete
        # tool calls as `[call#<i>: <tool_call_id> pending]` and carry the last
        # Read pagination progress (file, offset, total) so both LLM and
        # truncation summarizers see them (design Decision: tool-call pairing +
        # pagination progress preservation).
        annotated_middle = self._decorate_for_summary(middle, recent)

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
        # Incremental L1 accumulator (avoids re-encoding all chunks each compact).
        self._l1_accumulated_tokens += _count_tokens(new_summary)
        accumulated = self._l1_accumulated_tokens
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
                self._l1_accumulated_tokens = 0
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
                reasoning=list(m.reasoning),
                tool_calls=m.tool_calls,
            ))
        return annotated

    def _extract_read_progress(
        self, messages: list["Message"]
    ) -> list[tuple[str, int, int]]:
        """Last non-truncated ``[ReadProgress ...]`` per file.

        Only tool results carry ``total``, so the scan reads tool-result
        content and keeps the last match per file (last-window semantics —
        the resume candidate for a paged large-file read).

        A note flagged ``truncated=true`` at ``offset=0`` is the default output
        bound cutting a plain read short — it is NOT a resume position, so it is
        skipped: otherwise it would overwrite the resume position of a genuine
        paged read of the same file (last-wins would regress to offset 0). A
        truncated note at a non-zero offset comes from an explicit ``offset``
        read, which is a real paging position and is kept.
        """
        per_file: dict[str, tuple[int, int]] = {}
        for m in messages:
            if m.role != "tool" or not m.content:
                continue
            text = m.content if isinstance(m.content, str) else extract_text(m.content)
            for match in _READ_PROGRESS_RE.finditer(text):
                if match.group("truncated") and int(match.group(2)) == 0:
                    continue
                per_file[match.group(1)] = (int(match.group(2)), int(match.group(3)))
        return [(path, offset, total) for path, (offset, total) in per_file.items()]

    def _decorate_for_summary(
        self,
        middle: list["Message"],
        recent: list["Message"],
    ) -> list["Message"]:
        """Apply pending-call annotations and pagination-progress hints.

        The decorated list is passed to the summarizer; the original messages
        are untouched (pending/progress are shallow copies or appended hints).
        """
        annotated = self._annotate_pending_calls(middle, recent)
        progress = self._extract_read_progress([*middle, *recent])
        if progress:
            lines = [
                f"- {path}: offset={offset}, total={total}"
                for path, offset, total in progress
            ]
            hint = Message(
                role="user",
                content=(
                    "当前分页读取进度（大文件续读用，请在「当前进行中」中保留 (file, offset, total)）:\n"
                    + "\n".join(lines)
                ),
            )
            annotated = [*annotated, hint]
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
        self._l1_accumulated_tokens = 0
        self._l2_summary = None
        self._tiers = []
