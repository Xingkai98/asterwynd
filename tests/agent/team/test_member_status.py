# tests/agent/team/test_member_status.py
"""成员运行状态纯 reducer（change web-agent-group-member-status）。

覆盖优先级（tool > typing > thinking > running > idle）、按 tool_call.id 记账的并发/
同名工具、``iteration_started`` 清理残留、显式降级、无变化返回 None、未配对 finish。
"""
import pytest

from agent.team.member_status import (
    PHASE_IDLE,
    PHASE_PRIORITY,
    PHASE_RUNNING,
    PHASE_THINKING,
    PHASE_TOOL,
    PHASE_TYPING,
    MemberStatus,
    reduce_signal,
)


def _apply(status, *signals):
    for kind, data in signals:
        nxt = reduce_signal(status, kind, data)
        if nxt is not None:
            status = nxt
    return status


def test_priority_constants_cover_all_phases():
    assert set(PHASE_PRIORITY) == {
        PHASE_IDLE, PHASE_RUNNING, PHASE_THINKING, PHASE_TYPING, PHASE_TOOL,
    }
    assert PHASE_PRIORITY[PHASE_TOOL] > PHASE_PRIORITY[PHASE_TYPING]
    assert PHASE_PRIORITY[PHASE_TYPING] > PHASE_PRIORITY[PHASE_THINKING]
    assert PHASE_PRIORITY[PHASE_THINKING] > PHASE_PRIORITY[PHASE_RUNNING]
    assert PHASE_PRIORITY[PHASE_RUNNING] > PHASE_PRIORITY[PHASE_IDLE]


def test_slot_started_only_raises_idle():
    assert reduce_signal(None, "slot_started").phase == PHASE_RUNNING
    thinking = MemberStatus(PHASE_THINKING)
    assert reduce_signal(thinking, "slot_started") is None


def test_tool_has_priority_over_typing_and_thinking():
    status = _apply(
        None,
        ("slot_started", {}),
        ("iteration_started", {}),
        ("assistant_delta", {}),
    )
    assert status.phase == PHASE_TYPING

    started = reduce_signal(status, "tool_started", {"tool_id": "t1", "tool_name": "Bash"})
    assert started.phase == PHASE_TOOL
    assert started.tool_names == ["Bash"]

    # 工具执行期间的低优先级信号不得降级。
    assert reduce_signal(started, "assistant_delta", {}) is None
    assert reduce_signal(started, "iteration_started", {}) is not None  # 显式清空工具
    # iteration_started 是「新 LLM 调用」信号，会清空工具并转 thinking。
    after_iteration = reduce_signal(started, "iteration_started", {})
    assert after_iteration.phase == PHASE_THINKING
    assert after_iteration.tools == ()


def test_tool_finished_falls_back_to_running_then_next_iteration_thinks():
    status = MemberStatus(PHASE_TOOL, (("t1", "Bash"),))
    done = reduce_signal(status, "tool_finished", {"tool_id": "t1", "tool_name": "Bash"})
    assert done.phase == PHASE_RUNNING
    assert done.tools == ()
    thinking = reduce_signal(done, "iteration_started", {})
    assert thinking.phase == PHASE_THINKING


def test_concurrent_tools_are_aggregated_by_id():
    status = MemberStatus(PHASE_THINKING)
    status = reduce_signal(status, "tool_started", {"tool_id": "t1", "tool_name": "Bash"})
    status = reduce_signal(status, "tool_started", {"tool_id": "t2", "tool_name": "Read"})
    assert status.phase == PHASE_TOOL
    assert status.tool_names == ["Bash", "Read"]
    assert status.tool_count == 2

    still = reduce_signal(status, "tool_finished", {"tool_id": "t1", "tool_name": "Bash"})
    assert still.phase == PHASE_TOOL
    assert still.tool_names == ["Read"]
    done = reduce_signal(still, "tool_finished", {"tool_id": "t2", "tool_name": "Read"})
    assert done.phase == PHASE_RUNNING


def test_same_name_tools_do_not_cancel_each_other():
    status = MemberStatus(PHASE_THINKING)
    status = reduce_signal(status, "tool_started", {"tool_id": "a", "tool_name": "Bash"})
    status = reduce_signal(status, "tool_started", {"tool_id": "b", "tool_name": "Bash"})
    assert status.tool_count == 2
    assert status.tool_names == ["Bash"]

    one = reduce_signal(status, "tool_finished", {"tool_id": "a", "tool_name": "Bash"})
    assert one.phase == PHASE_TOOL
    assert one.tool_count == 1
    zero = reduce_signal(one, "tool_finished", {"tool_id": "b", "tool_name": "Bash"})
    assert zero.phase == PHASE_RUNNING


def test_iteration_started_clears_stale_tools_after_exception():
    # 模拟非 Bash 工具异常跳过 after_tool_execute：工具仍在集合里。
    stuck = MemberStatus(PHASE_TOOL, (("t1", "Read"),))
    cleared = reduce_signal(stuck, "iteration_started", {})
    assert cleared.phase == PHASE_THINKING
    assert cleared.tools == ()


def test_stream_complete_downgrades_typing_or_thinking_to_running():
    typing = MemberStatus(PHASE_TYPING)
    assert reduce_signal(typing, "stream_complete").phase == PHASE_RUNNING
    thinking = MemberStatus(PHASE_THINKING)
    assert reduce_signal(thinking, "stream_complete").phase == PHASE_RUNNING
    running = MemberStatus(PHASE_RUNNING)
    assert reduce_signal(running, "stream_complete") is None


def test_run_completed_waits_for_active_tools():
    tool = MemberStatus(PHASE_TOOL, (("t1", "Bash"),))
    assert reduce_signal(tool, "run_completed") is None
    assert reduce_signal(MemberStatus(PHASE_TYPING), "run_completed").phase == PHASE_RUNNING


def test_no_change_returns_none():
    thinking = MemberStatus(PHASE_THINKING)
    assert reduce_signal(thinking, "reasoning_delta") is None
    typing = MemberStatus(PHASE_TYPING)
    assert reduce_signal(typing, "assistant_delta") is None
    assert reduce_signal(typing, "run_started") is None
    assert reduce_signal(typing, "unknown_signal") is None


def test_unmatched_tool_finished_is_noop():
    assert reduce_signal(None, "tool_finished", {"tool_id": "x", "tool_name": "Bash"}) is None
    tool = MemberStatus(PHASE_TOOL, (("t1", "Bash"),))
    assert reduce_signal(tool, "tool_finished", {"tool_id": "x", "tool_name": "Read"}) is None


def test_tool_finished_name_fallback_for_mismatched_id():
    tool = MemberStatus(PHASE_TOOL, (("t1", "Bash"), ("t2", "Read")))
    done = reduce_signal(
        tool, "tool_finished", {"tool_id": "observed-copy", "tool_name": "Bash"}
    )
    assert done.phase == PHASE_TOOL
    assert done.tool_names == ["Read"]


def test_as_dict_shape():
    tool = MemberStatus(PHASE_TOOL, (("a", "Bash"), ("b", "Bash"), ("c", "Read")))
    assert tool.as_dict("p1") == {
        "persona_id": "p1",
        "phase": PHASE_TOOL,
        "tools": ["Bash", "Read"],
        "tool_count": 3,
    }


def test_unknown_phase_rejected():
    with pytest.raises(ValueError):
        MemberStatus("busy")
