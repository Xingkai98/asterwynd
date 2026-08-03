"""Lightweight orchestration message bus for subagents (issue 79, decision D5).

A bus is created per orchestration run (by ``RunPattern``), exposed to the
orchestrating parent and every worker through a contextvar (``agent/subagent/
context.py``), and lives only for the duration of that run. It exchanges
*semantic summaries*, never raw transcripts, under a strict token budget to
prevent context explosion.

The three budget layers from the design:
1. bounded queue — ``max_messages`` with drop-oldest when full (NATS DiscardOld
   semantics; ``ttl_s`` optionally drops stale entries);
2. publish-side summarization — callers (the ``PublishBusMessage`` tool) fold
   content into a summary under ``max_tokens`` before publishing;
3. consume-side token window — ``read()`` returns only the most recent messages
   that fit ``max_tokens`` (LangGraph ``trim_messages`` semantics).

The bus is not persisted across runs; the orchestration snapshot keeps a
compact ``snapshot_payload()`` so a resumed run sees what was exchanged.
"""
from __future__ import annotations

import time
import uuid
from collections import deque
from dataclasses import dataclass, field


def estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 chars/token), used for envelope bookkeeping."""
    return max(1, len(text) // 4)


@dataclass
class BusMessage:
    message_id: str
    sender: str
    topic: str
    summary: str
    token_count: int
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "message_id": self.message_id,
            "sender": self.sender,
            "topic": self.topic,
            "summary": self.summary,
            "token_count": self.token_count,
            "timestamp": self.timestamp,
        }


class MessageBus:
    def __init__(
        self,
        *,
        max_messages: int = 100,
        max_read_tokens: int = 2000,
        ttl_s: float | None = None,
    ) -> None:
        self.max_messages = max_messages
        self.max_read_tokens = max_read_tokens
        self.ttl_s = ttl_s
        self._messages: deque[BusMessage] = deque()

    @property
    def size(self) -> int:
        return len(self._messages)

    def publish(
        self,
        *,
        sender: str,
        topic: str,
        summary: str,
        token_count: int | None = None,
    ) -> BusMessage:
        if len(self._messages) >= self.max_messages:
            self._messages.popleft()  # drop-oldest
        msg = BusMessage(
            message_id=uuid.uuid4().hex[:8],
            sender=sender,
            topic=topic,
            summary=summary,
            token_count=(
                token_count if token_count is not None else estimate_tokens(summary)
            ),
        )
        self._messages.append(msg)
        return msg

    def read(
        self,
        *,
        topics: list[str] | None = None,
        max_tokens: int | None = None,
        limit: int | None = None,
    ) -> list[BusMessage]:
        """Return the most recent messages that fit the token window.

        Iterates newest-first, accumulating until the budget (default
        ``max_read_tokens``) is exhausted; results are returned oldest-first.
        ``topics`` filters by topic; ``limit`` bounds the count.
        """
        budget = max_tokens if max_tokens is not None else self.max_read_tokens
        collected: list[BusMessage] = []
        used = 0
        now = time.time()
        for msg in reversed(self._messages):
            if topics and msg.topic not in topics:
                continue
            if self.ttl_s is not None and now - msg.timestamp > self.ttl_s:
                continue
            if used + msg.token_count > budget:
                # A single message larger than the window still surfaces (the
                # newest) so the consumer is never blind to the latest state.
                if not collected:
                    collected.append(msg)
                break
            collected.append(msg)
            used += msg.token_count
            if limit is not None and len(collected) >= limit:
                break
        collected.reverse()
        return collected

    def compact_summary(self, max_chars: int = 2000) -> str:
        """Concise text view for snapshots / parent context injection."""
        lines = [f"[{m.sender}/{m.topic}] {m.summary}" for m in self._messages]
        text = "\n".join(lines)
        if len(text) > max_chars:
            return text[:max_chars] + "..."
        return text

    def snapshot_payload(self) -> dict:
        return {
            "messages": [m.to_dict() for m in self._messages],
            "max_read_tokens": self.max_read_tokens,
        }
