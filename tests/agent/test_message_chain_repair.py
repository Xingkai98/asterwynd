"""tool-call 配对自愈纯函数（issue #304）。

覆盖 design Decision 3/4/9：末尾悬空、并行/连续多个、Case B 不重复合成、
幂等字节一致、正常链零改动、spill preview 视为结果。
"""
import pytest

from agent.llm import ToolCallDelta
from agent.message import (
    SYNTHETIC_TOOL_RESULT_PREFIX,
    Message,
    repair_tool_call_pairing,
)


def _call(tool_id: str, name: str = "Echo") -> ToolCallDelta:
    return ToolCallDelta(id=tool_id, name=name, arguments="{}")


def _assistant(*calls: ToolCallDelta, content: str = "") -> Message:
    return Message(role="assistant", content=content, tool_calls=list(calls))


def _tool(tool_id: str, content: str = "ok") -> Message:
    return Message(role="tool", content=content, tool_call_id=tool_id)


def _user(content: str) -> Message:
    return Message(role="user", content=content)


def _dicts(messages):
    return [m.to_dict() for m in messages]


def test_repairs_trailing_dangling_call():
    messages = [_user("go"), _assistant(_call("c1"))]

    report = repair_tool_call_pairing(messages)

    assert report.changed
    assert [r.tool_call_id for r in report.repaired] == ["c1"]
    repaired = report.messages
    assert len(repaired) == 3
    assert repaired[-1].role == "tool"
    assert repaired[-1].tool_call_id == "c1"
    assert str(repaired[-1].content).startswith(SYNTHETIC_TOOL_RESULT_PREFIX)
    assert "interrupted" in str(repaired[-1].content).lower()
    # 原始消息对象不被修改
    assert messages[-1].role == "assistant"


def test_repairs_only_missing_parallel_calls_in_order():
    messages = [
        _user("go"),
        _assistant(_call("c1"), _call("c2"), _call("c3")),
        _tool("c1", "real"),
    ]

    report = repair_tool_call_pairing(messages)

    repaired = report.messages
    tool_msgs = [m for m in repaired if m.role == "tool"]
    assert [m.tool_call_id for m in tool_msgs] == ["c1", "c2", "c3"]
    assert tool_msgs[0].content == "real"
    assert [r.tool_call_id for r in report.repaired] == ["c2", "c3"]
    assert str(tool_msgs[1].content).startswith(SYNTHETIC_TOOL_RESULT_PREFIX)


def test_repairs_consecutive_dangling_assistants():
    messages = [
        _user("go"),
        _assistant(_call("c1")),
        _user("again"),
        _assistant(_call("c2")),
    ]

    report = repair_tool_call_pairing(messages)

    repaired = report.messages
    assert [m.role for m in repaired] == [
        "user", "assistant", "tool", "user", "assistant", "tool",
    ]
    assert repaired[2].tool_call_id == "c1"
    assert repaired[5].tool_call_id == "c2"
    assert [r.tool_call_id for r in report.repaired] == ["c1", "c2"]


def test_synthetic_result_inserted_before_following_user_text():
    messages = [_assistant(_call("c1")), _user("next")]

    report = repair_tool_call_pairing(messages)

    assert [m.role for m in report.messages] == ["assistant", "tool", "user"]
    assert report.messages[1].tool_call_id == "c1"


def test_valid_history_is_byte_identical_and_unchanged():
    messages = [
        _user("go"),
        _assistant(_call("c1")),
        _tool("c1"),
        _user("next"),
    ]
    before = _dicts(messages)

    report = repair_tool_call_pairing(messages)

    assert not report.changed
    assert report.messages is messages
    assert _dicts(report.messages) == before
    assert all(m is orig for m, orig in zip(report.messages, messages))


def test_repair_is_idempotent_and_byte_stable():
    messages = [_assistant(_call("c1"), _call("c2"))]

    first = repair_tool_call_pairing(messages)
    assert first.changed
    first_bytes = _dicts(first.messages)

    second = repair_tool_call_pairing(first.messages)

    assert not second.changed
    assert second.messages is first.messages
    assert _dicts(second.messages) == first_bytes


def test_orphan_before_is_not_duplicated():
    messages = [_tool("c1", "real"), _assistant(_call("c1"))]
    before = _dicts(messages)

    report = repair_tool_call_pairing(messages)

    assert not report.changed
    assert report.messages is messages
    assert _dicts(report.messages) == before
    assert len([m for m in report.messages if m.role == "tool"]) == 1


def test_misplaced_after_is_not_duplicated():
    messages = [
        _assistant(_call("c1")),
        _user("next"),
        _tool("c1", "real"),
    ]
    before = _dicts(messages)

    report = repair_tool_call_pairing(messages)

    assert not report.changed
    assert report.messages is messages
    assert _dicts(report.messages) == before
    assert len([m for m in report.messages if m.role == "tool"]) == 1


def test_empty_tool_call_id_is_skipped():
    messages = [_assistant(_call(""))]

    report = repair_tool_call_pairing(messages)

    assert not report.changed
    assert report.messages is messages
    assert not [m for m in report.messages if m.role == "tool"]


def test_spilled_preview_counts_as_result():
    preview = Message(role="tool", content="[truncated] full result at artifact://x", tool_call_id="c1")
    messages = [_assistant(_call("c1")), preview]

    report = repair_tool_call_pairing(messages)

    assert not report.changed
    assert report.messages is messages


def test_assistant_text_and_reasoning_preserved():
    from agent.message import ReasoningBlock

    assistant = Message(
        role="assistant",
        content="I will call the tool",
        tool_calls=[_call("c1")],
        reasoning=[ReasoningBlock(text="thinking")],
    )
    messages = [assistant]

    report = repair_tool_call_pairing(messages)

    repaired_assistant = report.messages[0]
    assert repaired_assistant is assistant
    assert repaired_assistant.content == "I will call the tool"
    assert repaired_assistant.reasoning[0].text == "thinking"


def test_synthetic_content_bounds_huge_name_and_id():
    messages = [_assistant(_call("i" * 500, "n" * 500))]

    report = repair_tool_call_pairing(messages)

    synthetic = report.messages[1]
    content = str(synthetic.content)
    assert len(content) < 1000
    assert "i" * 500 not in content
    assert "n" * 500 not in content


class _Counter:
    def __call__(self, text: str) -> int:
        return max(1, len(text) // 4)


def test_spiller_does_not_rewrite_small_synthetic_result():
    from agent.memory.tool_result_spiller import ToolResultSpiller

    report = repair_tool_call_pairing([_assistant(_call("c1"))])
    messages = report.messages
    spiller = ToolResultSpiller(max_tokens=100_000, recent_window=2, counter=_Counter())
    spiller.reset(messages)

    stats = spiller.spill(messages, current_iteration=1)

    assert stats.messages_spilled == 0
    assert str(messages[-1].content).startswith(SYNTHETIC_TOOL_RESULT_PREFIX)


def test_annotate_pending_calls_does_not_mark_repaired_call_pending():
    from agent.memory.manager import MemoryManager

    report = repair_tool_call_pairing([_assistant(_call("c1"))])
    memory = MemoryManager(max_tokens=100_000, recent_window=10)
    annotated = memory._annotate_pending_calls(report.messages, [])

    assert all("pending" not in str(m.content).lower() for m in annotated)


@pytest.mark.asyncio
async def test_compaction_keeps_repaired_tool_chain_paired():
    from agent.context.summarizer import TruncationSummarizer
    from agent.memory.manager import MemoryManager

    messages = [
        _user("old question"),
        _assistant(content="old answer"),
        _user("please call"),
        _assistant(_call("c1")),
        _tool("c1"),
    ]
    memory = MemoryManager(
        max_tokens=1_000, recent_window=2, summarizer=TruncationSummarizer(),
    )

    await memory.compact(messages)

    assistant_ids = {
        tc.id
        for m in messages
        if m.role == "assistant"
        for tc in m.tool_calls
    }
    result_ids = {
        m.tool_call_id
        for m in messages
        if m.role == "tool" and m.tool_call_id
    }
    assert assistant_ids == result_ids


def test_duplicate_tool_call_ids_synthesize_once_and_do_not_claim_full_repair():
    messages = [_assistant(_call("c1"), _call("c1"))]

    report = repair_tool_call_pairing(messages)

    assert report.changed
    assert len(report.repaired) == 1
    assert len([m for m in report.messages if m.role == "tool"]) == 1
    # 重复 id 本身仍是畸形输入；本函数只保证不新增第二条合成结果。
