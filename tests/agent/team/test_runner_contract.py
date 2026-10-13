# tests/agent/team/test_runner_contract.py
"""SessionRunner 的四态契约与静默哨兵（tasks 2.4 / 3.7）。

四态映射的**完整**验证（含「同 session 并发被拒时不复用陈旧文本」）在
``tests/web_tests/test_group_chat_team.py``——那里才有真实的 ``AgentSession``。
"""
import pytest

from agent.team.runner import (
    DEFAULT_TURN_TIMEOUT_SECONDS,
    SILENT_MARKER,
    TurnOutcome,
    is_silent,
)


class TestTurnOutcome:
    def test_four_states_constructible(self):
        for status in ("text", "silent", "failed", "timeout"):
            assert TurnOutcome(status=status).status == status

    def test_unknown_state_rejected(self):
        with pytest.raises(ValueError):
            TurnOutcome(status="ok")

    def test_only_text_counts_as_spoken(self):
        assert TurnOutcome(status="text", text="hi").spoke is True
        for status in ("silent", "failed", "timeout"):
            assert TurnOutcome(status=status).spoke is False

    def test_failure_carries_code_and_message(self):
        outcome = TurnOutcome(status="failed", code="run_in_progress", message="busy")
        assert outcome.code == "run_in_progress"
        assert outcome.message == "busy"

    def test_default_timeout_matches_reference_order_of_magnitude(self):
        assert DEFAULT_TURN_TIMEOUT_SECONDS == 240.0


class TestConstantsStayInSync:
    """review I11：常量必须与真实来源一致（否则就是没人用的死值）。"""

    def test_persona_modes_match_agent_mode(self):
        from agent.run_config import AgentMode
        from agent.team.models import PERSONA_MODES

        assert PERSONA_MODES == tuple(mode.value for mode in AgentMode)

    def test_default_persona_mode_is_a_member(self):
        from agent.team.models import DEFAULT_PERSONA_MODE, PERSONA_MODES

        assert DEFAULT_PERSONA_MODE in PERSONA_MODES

    def test_default_reply_mode_is_a_member(self):
        from agent.team.models import DEFAULT_REPLY_MODE, REPLY_MODES

        assert DEFAULT_REPLY_MODE in REPLY_MODES

    def test_runner_status_constants_are_the_four_states(self):
        from agent.team import runner

        assert runner.STATUSES == (
            runner.STATUS_TEXT, runner.STATUS_SILENT,
            runner.STATUS_FAILED, runner.STATUS_TIMEOUT,
        )


class TestSilentMarker:
    @pytest.mark.parametrize("text", [
        "[PASS]", " [pass] ", "【PASS】", "(pass)", "（Pass）", "", "   ",
        # 裸哨兵：模型常把提示词里的 ``[PASS]`` 写成 ``PASS``，与参照同形接受。
        "PASS", "pass.",
    ])
    def test_silent_forms(self, text):
        assert is_silent(text) is True

    @pytest.mark.parametrize("text", [
        "I have nothing to add.", "[PASS] but here is my take",
        "Sure, [PASS]",
    ])
    def test_non_silent_forms(self, text):
        assert is_silent(text) is False

    def test_marker_value_is_the_documented_sentinel(self):
        assert SILENT_MARKER == "[PASS]"
