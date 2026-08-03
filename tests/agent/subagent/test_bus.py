"""Message bus token-budget semantics (issue 79, decision D5).

Covers tasks 3.1/3.2: bounded queue with drop-oldest, publish-side summaries,
consume-side token window, TTL, and compact snapshot summary.
"""
import pytest

from agent.subagent.bus import MessageBus, estimate_tokens


def test_publish_and_read_roundtrip():
    bus = MessageBus()
    msg = bus.publish(sender="worker-1", topic="finding", summary="found bug in x")
    assert bus.size == 1
    messages = bus.read()
    assert len(messages) == 1
    assert messages[0].message_id == msg.message_id
    assert messages[0].summary == "found bug in x"


def test_drop_oldest_when_full():
    bus = MessageBus(max_messages=3)
    for i in range(5):
        bus.publish(sender=f"w{i}", topic="t", summary=f"msg {i}")
    assert bus.size == 3
    summaries = [m.summary for m in bus.read()]
    # oldest two dropped, newest three retained
    assert summaries == ["msg 2", "msg 3", "msg 4"]


def test_read_token_window_keeps_most_recent():
    bus = MessageBus(max_read_tokens=50)
    # each summary ~ "m" + i => ~1-2 tokens
    for i in range(10):
        bus.publish(sender="w", topic="t", summary=f"m{i}")
    messages = bus.read(max_tokens=5)
    # newest messages that fit 5 tokens; at least the newest is present
    assert len(messages) >= 1
    assert messages[-1].summary == "m9"
    assert sum(m.token_count for m in messages) <= 5


def test_topic_filter():
    bus = MessageBus()
    bus.publish(sender="a", topic="finding", summary="f1")
    bus.publish(sender="b", topic="proposal", summary="p1")
    findings = bus.read(topics=["finding"])
    assert [m.summary for m in findings] == ["f1"]


def test_ttl_drops_stale():
    bus = MessageBus(ttl_s=-1.0)  # everything already stale
    bus.publish(sender="a", topic="t", summary="old")
    assert bus.read() == []
    assert bus.size == 1  # still retained in the queue, filtered on read


def test_compact_summary_and_snapshot_payload():
    bus = MessageBus(max_messages=2)
    bus.publish(sender="w1", topic="finding", summary="short")
    bus.publish(sender="w2", topic="proposal", summary="longer summary here")
    compact = bus.compact_summary()
    assert "[w1/finding]" in compact
    assert "[w2/proposal]" in compact
    payload = bus.snapshot_payload()
    assert len(payload["messages"]) == 2
    assert payload["max_read_tokens"] == bus.max_read_tokens


def test_compact_summary_truncated():
    bus = MessageBus()
    bus.publish(sender="w", topic="t", summary="x" * 500)
    compact = bus.compact_summary(max_chars=50)
    assert len(compact) == 50 + len("...")  # truncated with ellipsis


def test_estimate_tokens():
    assert estimate_tokens("") == 1
    assert estimate_tokens("abcd") == 1  # 4 chars / 4
    assert estimate_tokens("abcdefgh") == 2


def test_publish_explicit_token_count_wins():
    bus = MessageBus()
    msg = bus.publish(sender="w", topic="t", summary="hello", token_count=99)
    assert msg.token_count == 99
