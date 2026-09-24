"""Lightweight orchestration message bus for subagents (issue 79, decision D5).

A bus is created per orchestration run (by ``RunPattern``), exposed to the
orchestrating parent and every worker through a contextvar (``agent/subagent/
context.py``), and lives only for the duration of that run. It exchanges
*semantic summaries*, never raw transcripts, under a strict token budget to
prevent context explosion.

**The bus is a non-authoritative channel** (change ``workflow-result-aggregation``,
decision D4): it carries low-latency broadcasts and non-critical hints only.
Authoritative state — node/workflow terminal status, dependency completion,
result completeness, retries, replay — lives in the workflow store and its
event log (``agent/subagent/workflow_store.py``). Dropping a bus message
therefore cannot affect whether a workflow completes or whether its results are
correct: a full queue drops the oldest message and the graph never observes it.

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
from dataclasses import dataclass, field, replace

from agent.subagent.manager import TRANSCRIPT_ITEM_LIMIT, _clip

#: 模型面**单条 bus 消息**的字符上限。派生自 ``TRANSCRIPT_ITEM_LIMIT``（issue #213），
#: **不新造数字**：bus 消息的 ``summary`` 就是「子 agent 撰写的单条文本」，与 run envelope
#: 的 ``content`` / ``summary`` / ``arguments`` 在模型面是同一个概念，不该有两个数。
#:
#: 该上限**固定**、不随调用方传入的 ``max_tokens`` 浮动——否则被检视的子 agent 就能通过
#: 调大参数来决定父 agent 收到多少（issue #224 D1）。
BUS_MESSAGE_LIMIT = TRANSCRIPT_ITEM_LIMIT

#: 单次投影的**条数**上限（``read()`` 与 ``snapshot_payload()`` 同界）。总量维不是单条维的
#: 附属品：单条截到 4000 而条数无界时，``read(max_tokens=10**9)`` 仍能一次灌进约 300 万字符
#: （issue #224 Q1 实测）。
#:
#: 取值 20 的预算推导（D4/Q4）：20 × 4000 = **80,000 字符**；同仓库既有父面投影口径是图节点
#: ``_PARENT_NODES_LIMIT`` × ``_PARENT_FIELD_LIMIT`` = 200 × 200 = 40,000 字符（被
#: ``test_bounded_envelope.py`` 的 ``< 60_000`` 钉住）。两者合计 ≤ **120,000 字符**，低于
#: issue #213 实测的修复前量级 172,703 的 70%——即新增一条父面注入路径后，总量仍压回既有口径之内。
BUS_SNAPSHOT_LIMIT = 20

#: 发布侧 summarize 阈值（token）的上界。``BUS_MESSAGE_LIMIT // 4`` 是 ``estimate_tokens`` 的
#: 换算口径，故阈值不可能被调到单条上限之上——阈值高于上限时 summarize 分支不触发、原文直入
#: bus（issue #224 D5）。
#:
#: 注意：这只对齐了**阈值**。``_summarize`` 的 LLM 分支是 advisory、非硬界
#: （``agent/context/summarizer.py``：预算「not a hard guarantee」），单条的**硬保证**在消费侧
#: ``read()``——发布侧是「阈值对齐 + 消费侧兜底」，不是「发布侧也有硬界」。
BUS_PUBLISH_MAX_TOKENS = BUS_MESSAGE_LIMIT // 4


def estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 chars/token), used for envelope bookkeeping."""
    return max(1, len(text) // 4)


def _bounded_message(msg: BusMessage) -> BusMessage:
    """按 ``BUS_MESSAGE_LIMIT`` 截断一条消息，返回**新实例**（未超限则原样返回）。

    必须构造新实例而不是原地赋值：``read()`` 收集的正是队列里的那些对象，原地改会同步
    改写 ``self._messages``，把 ``compact_summary()`` 与 checkpoint 的 ``bus_summary`` 一起
    截短——即「队列保留全文」与「出口返回截断件」互相冲突（issue #224 D10）。
    """
    text, truncated = _clip(msg.summary, BUS_MESSAGE_LIMIT)
    if not truncated:
        return msg
    return replace(
        msg,
        summary=text,
        # 记账口径与返回体保持一致：一条 30,000 字消息原报 7500，截到 4000 后仍报 7500
        # 会让调用方按它累计预算时把 1000 token 的返回记成 7500（issue #224 D9）。
        token_count=estimate_tokens(text),
        truncated=True,
    )


@dataclass
class BusMessage:
    message_id: str
    sender: str
    topic: str
    summary: str
    token_count: int
    timestamp: float = field(default_factory=time.time)
    #: 该条的 ``summary`` 是否在**出口投影**时被截断。命名沿用 #213 的 ``<字段>_truncated``
    #: 家族（``content_truncated`` / ``summary_truncated`` / ``arguments_truncated``）。
    truncated: bool = False

    def to_dict(self) -> dict:
        return {
            "message_id": self.message_id,
            "sender": self.sender,
            "topic": self.topic,
            "summary": self.summary,
            "token_count": self.token_count,
            "timestamp": self.timestamp,
            "summary_truncated": self.truncated,
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

        ``max_tokens`` / ``limit`` 由调用方（模型）给出，故**两个维度都被钳到固定上界**
        （issue #224 D4b）：界不可被被检视对象影响。不钳则单条截断形同虚设——实测
        ``max_tokens=10**9`` 时本方法返回 100 条 / 3,000,000 字符，比修复前更大。

        返回的每条经 ``_bounded_message`` 投影（截断件是**新实例**，队列保留全文）。
        内部挑消息时的预算累计仍用**原始** ``token_count``（更保守）。
        """
        budget = max_tokens if max_tokens is not None else self.max_read_tokens
        budget = min(budget, BUS_SNAPSHOT_LIMIT * BUS_PUBLISH_MAX_TOKENS)
        effective_limit = BUS_SNAPSHOT_LIMIT if limit is None else min(limit, BUS_SNAPSHOT_LIMIT)
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
                # 但它同样受单条上限约束（issue #224 D3）——「最新状态可见」与
                # 「体量有界」同时成立。
                if not collected:
                    collected.append(msg)
                break
            collected.append(msg)
            used += msg.token_count
            if len(collected) >= effective_limit:
                break
        collected.reverse()
        return [_bounded_message(m) for m in collected]

    def compact_summary(self, max_chars: int = 2000) -> str:
        """Concise text view for snapshots / parent context injection."""
        lines = [f"[{m.sender}/{m.topic}] {m.summary}" for m in self._messages]
        text = "\n".join(lines)
        if len(text) > max_chars:
            return text[:max_chars] + "..."
        return text

    def snapshot_payload(self) -> dict:
        """Bounded projection for the model-facing ``RunPattern`` result.

        条数与单条**两个维度**都有界（issue #224 D4），且界施加在**方法本身**——
        ``RunPattern`` 与调度器 ``_envelope()`` 共用这一处，只加固某个调用点等于留一个
        同类漏口。超出条数上限时取**最近** ``BUS_SNAPSHOT_LIMIT`` 条（与 ``read()`` 的
        「取最近」和 ``max_messages`` 的 drop-oldest 一致），并用 ``messages_total`` /
        ``messages_omitted`` **显式报告**省略量——静默丢弃会把「没消息」与「消息被省略」
        报成同一件事（沿用 ``parent_envelope()`` 的 ``nodes_omitted`` 范式）。
        """
        total = len(self._messages)
        visible = list(self._messages)[-BUS_SNAPSHOT_LIMIT:]
        return {
            "messages": [_bounded_message(m).to_dict() for m in visible],
            "max_read_tokens": self.max_read_tokens,
            "messages_total": total,
            "messages_omitted": max(total - BUS_SNAPSHOT_LIMIT, 0),
        }
