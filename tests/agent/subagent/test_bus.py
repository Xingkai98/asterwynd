"""Message bus token-budget semantics (issue 79, decision D5).

Covers tasks 3.1/3.2: bounded queue with drop-oldest, publish-side summaries,
consume-side token window, TTL, and compact snapshot summary.
"""
import pytest

from agent.subagent.bus import (
    BUS_MESSAGE_LIMIT,
    BUS_PUBLISH_MAX_TOKENS,
    BUS_SNAPSHOT_LIMIT,
    MessageBus,
    estimate_tokens,
)
from agent.subagent.manager import TRANSCRIPT_ITEM_LIMIT

#: 判别性输入：必须**真的**超过上限，否则「≤ 上限」恒真（#213 的参数教训）。
_OVERSIZED = 30_000


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


def test_read_returns_newest_when_single_message_exceeds_window():
    """Review M5: a message larger than the window still surfaces (not empty).

    输入 400 字**不越**单条上限（4000），故本测试只承担「超窗仍返回最新一条」这一条
    语义、断言仍是全文可见；截断语义由下面 ``test_read_truncates_oversized_message``
    单独承担（issue #224 Q5：两条测试各有判别力，400 字下 ``truncated`` 恒为 False，
    若把它混进来，删掉截断实现这条测试仍会绿）。
    """
    bus = MessageBus(max_read_tokens=10)
    bus.publish(sender="w", topic="t", summary="tiny")
    bus.publish(sender="w", topic="t", summary="x" * 400)  # ~100 tokens >> 10
    messages = bus.read(max_tokens=10)
    assert len(messages) == 1
    assert messages[0].summary == "x" * 400  # newest, even though over budget


# --- issue #224：bus 出口一律 bounded ---------------------------------------


def test_bus_message_limit_derives_from_transcript_item_limit():
    """D1/D7：单条上限**派生**自 ``TRANSCRIPT_ITEM_LIMIT``，不是第二个数。

    本测试锁的是「派生关系没被改成字面量」——单靠 ``==`` 锁不住（改成字面量 ``4000``
    时数值仍相等，小整数缓存下 ``is`` 也仍绿），故断言模块源码里 ``BUS_MESSAGE_LIMIT``
    的赋值右侧**就是** ``TRANSCRIPT_ITEM_LIMIT``（改字面量 → 本测试变红）。
    """
    import inspect
    import re

    import agent.subagent.bus as bus_module

    assert BUS_MESSAGE_LIMIT == TRANSCRIPT_ITEM_LIMIT
    src = inspect.getsource(bus_module)
    assert re.search(r"^BUS_MESSAGE_LIMIT\s*=\s*TRANSCRIPT_ITEM_LIMIT\s*$", src, re.M), (
        "BUS_MESSAGE_LIMIT 必须直接派生自 TRANSCRIPT_ITEM_LIMIT（不得写成字面量）"
    )
    assert BUS_SNAPSHOT_LIMIT == 20
    assert BUS_PUBLISH_MAX_TOKENS == BUS_MESSAGE_LIMIT // 4


def test_read_truncates_oversized_message_with_flag():
    """read() 单条截断 + 布尔标志（D3/D8）。"""
    bus = MessageBus()
    bus.publish(sender="w", topic="finding", summary="x" * _OVERSIZED)
    messages = bus.read()
    assert len(messages) == 1
    assert len(messages[0].summary) == BUS_MESSAGE_LIMIT
    assert messages[0].truncated is True
    assert messages[0].to_dict()["summary_truncated"] is True


def test_read_leaves_short_message_untouched():
    """未超限的消息不截、不带标志（截断器不能把「没截」报成「截了」）。"""
    bus = MessageBus()
    bus.publish(sender="w", topic="finding", summary="short")
    msg = bus.read()[0]
    assert msg.summary == "short"
    assert msg.truncated is False
    assert msg.to_dict()["summary_truncated"] is False


def test_read_recomputes_token_count_after_truncation():
    """D9/Q3：截断后 ``token_count`` 与返回体一致，不再是全文的记账值。"""
    bus = MessageBus()
    bus.publish(sender="w", topic="t", summary="x" * _OVERSIZED)
    full_tokens = estimate_tokens("x" * _OVERSIZED)
    msg = bus.read()[0]
    assert msg.token_count == estimate_tokens(msg.summary)
    assert msg.token_count < full_tokens


def test_read_does_not_mutate_queued_message():
    """D10/R1：read() 返回的是**新实例**，队列里的原文与 compact 视图不受影响。"""
    bus = MessageBus()
    bus.publish(sender="w", topic="t", summary="x" * _OVERSIZED)
    before_compact = bus.compact_summary()
    got = bus.read()
    assert got[0] is not bus._messages[0]  # 新实例，不是队列里的同一对象
    assert len(bus._messages[0].summary) == _OVERSIZED  # 队列保留全文
    assert bus._messages[0].truncated is False
    assert bus.compact_summary() == before_compact


def test_read_total_is_clamped_regardless_of_caller_params():
    """D4b/Q1：总量维。调用方给的 max_tokens / limit 不能把父上下文撑爆。"""
    bus = MessageBus()
    for i in range(100):
        bus.publish(sender=f"w{i}", topic="t", summary="z" * _OVERSIZED)
    messages = bus.read(max_tokens=10**9, limit=10**9)
    assert len(messages) <= BUS_SNAPSHOT_LIMIT
    assert sum(len(m.summary) for m in messages) <= (
        BUS_SNAPSHOT_LIMIT * BUS_MESSAGE_LIMIT
    )
    # 每一条自身也受单条上限约束
    assert all(len(m.summary) <= BUS_MESSAGE_LIMIT for m in messages)


def test_read_clamps_token_window_not_just_count():
    """Q1 的两个钳制各自独立：``max_tokens`` 钳不住时**条数**也会被撑大。

    上一条断言「总量 ≤ 上界」由 ``limit`` 钳制即可满足；本条单独锁 ``max_tokens``：
    超大窗口必须与「钳到上界的窗口」**逐条等价**（spec Scenario：「结果 SHALL NOT 随
    传入参数增大而无限增大」）。每条原始 ``token_count`` 是 7500，钳后的窗口
    ``BUS_SNAPSHOT_LIMIT * BUS_PUBLISH_MAX_TOKENS`` = 20000 只装得下 2 条——不钳
    ``max_tokens`` 时会返回 20 条，两条路径立刻分叉。
    """
    bus = MessageBus()
    for i in range(BUS_SNAPSHOT_LIMIT):
        bus.publish(sender=f"w{i}", topic="t", summary="z" * _OVERSIZED)
    huge = bus.read(max_tokens=10**9, limit=10**9)
    clamped = bus.read(
        max_tokens=BUS_SNAPSHOT_LIMIT * BUS_PUBLISH_MAX_TOKENS,
        limit=BUS_SNAPSHOT_LIMIT,
    )
    assert [m.message_id for m in huge] == [m.message_id for m in clamped]
    assert len(huge) < BUS_SNAPSHOT_LIMIT, "token 窗口应比条数上限更早截停"


def test_read_total_clamp_keeps_newest():
    """总量钳制取**最近**的，不是最早的（与 drop-oldest / read 的取最近语义一致）。"""
    bus = MessageBus()
    for i in range(30):
        bus.publish(sender="w", topic="t", summary=f"m{i} " + "z" * 20)
    messages = bus.read(max_tokens=10**9, limit=10**9)
    assert messages[-1].summary.startswith("m29")


def test_snapshot_payload_caps_count_and_reports_omitted():
    """D4：条数上限 + 显式报告（不静默丢弃）。"""
    bus = MessageBus()
    for i in range(100):
        bus.publish(sender=f"w{i}", topic="t", summary=f"msg {i}")
    payload = bus.snapshot_payload()
    assert len(payload["messages"]) == BUS_SNAPSHOT_LIMIT
    assert payload["messages_total"] == 100
    assert payload["messages_omitted"] == 100 - BUS_SNAPSHOT_LIMIT
    # 取最近：保留的是最后 BUS_SNAPSHOT_LIMIT 条
    assert payload["messages"][-1]["summary"] == "msg 99"


def test_snapshot_payload_caps_single_message():
    """D4：快照的单条维同样有界（与 read() 走同一条截断路径）。"""
    bus = MessageBus()
    bus.publish(sender="w", topic="t", summary="x" * _OVERSIZED)
    entry = bus.snapshot_payload()["messages"][0]
    assert len(entry["summary"]) == BUS_MESSAGE_LIMIT
    assert entry["summary_truncated"] is True

    payload = bus.snapshot_payload()
    assert payload["messages_total"] == 1
    assert payload["messages_omitted"] == 0


def test_snapshot_payload_preserves_queue_after_projection():
    """快照是只读投影：调用两次结果一致，队列原文不变。"""
    bus = MessageBus()
    bus.publish(sender="w", topic="t", summary="x" * _OVERSIZED)
    first = bus.snapshot_payload()
    second = bus.snapshot_payload()
    assert first == second
    assert len(bus._messages[0].summary) == _OVERSIZED


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
