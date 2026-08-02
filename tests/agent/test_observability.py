"""Tests for agent/observability.py — ErrorClassifier + ErrorCategory + phase mapping.

Covers design.md 第二/三轮：异常分类用"结构化字段优先 + 文本兜底"（对齐业界
OTel GenAI 做法，非关键词猜测）；phase 映射 AgentMode 到 runtime 语义。
"""
from __future__ import annotations

import pytest

from agent.observability import (
    ErrorCategory,
    ErrorClassifier,
    PHASE_BY_MODE,
    resolve_phase,
)


class TestPhaseMapping:
    def test_resolve_phase_build(self) -> None:
        assert resolve_phase("build") == "building"

    def test_resolve_phase_read_only(self) -> None:
        assert resolve_phase("read_only") == "review"

    def test_resolve_phase_plan(self) -> None:
        assert resolve_phase("plan") == "planning"

    def test_resolve_phase_bypass(self) -> None:
        assert resolve_phase("bypass") == "bypass"

    def test_resolve_phase_unknown_defaults_to_building(self) -> None:
        assert resolve_phase("unknown_mode") == "building"

    def test_phase_by_mode_has_all_agent_modes(self) -> None:
        assert set(PHASE_BY_MODE.keys()) == {"build", "read_only", "plan", "bypass"}


class TestErrorClassifierStructured:
    def test_error_type_permission_denied(self) -> None:
        assert ErrorClassifier().classify(error_type="permission_denied") is ErrorCategory.PERMISSION_DENIED

    def test_error_type_timeout(self) -> None:
        assert ErrorClassifier().classify(error_type="timeout") is ErrorCategory.NETWORK_TIMEOUT

    def test_error_type_parse_error(self) -> None:
        assert ErrorClassifier().classify(error_type="parse_error") is ErrorCategory.PARAMETER_ERROR

    def test_finish_reason_max_tokens(self) -> None:
        assert ErrorClassifier().classify(finish_reason="max_tokens") is ErrorCategory.MODEL_ERROR

    def test_no_fields_returns_unknown(self) -> None:
        assert ErrorClassifier().classify() is ErrorCategory.UNKNOWN


class TestErrorClassifierTextFallback:
    def test_permission_text(self) -> None:
        assert ErrorClassifier().classify(text="[Permission denied: tool not allowed]") is ErrorCategory.PERMISSION_DENIED

    def test_timeout_text(self) -> None:
        assert ErrorClassifier().classify(text="timed out after 30s") is ErrorCategory.NETWORK_TIMEOUT

    def test_rate_limit_text(self) -> None:
        assert ErrorClassifier().classify(text="rate limit exceeded") is ErrorCategory.NETWORK_TIMEOUT

    def test_generic_error_text(self) -> None:
        assert ErrorClassifier().classify(text="[Error: something failed]") is ErrorCategory.PARAMETER_ERROR

    def test_structured_field_wins_over_text(self) -> None:
        """结构化字段优先于文本兜底"""
        assert ErrorClassifier().classify(
            error_type="timeout", text="[Permission denied]"
        ) is ErrorCategory.NETWORK_TIMEOUT


class TestErrorClassifierAlertPolicy:
    def test_alert_levels_defined(self) -> None:
        """每类都有告警策略"""
        assert ErrorClassifier().alert_level(ErrorCategory.PERMISSION_DENIED) == "immediate"
        assert ErrorClassifier().alert_level(ErrorCategory.NETWORK_TIMEOUT) == "warn"
        assert ErrorClassifier().alert_level(ErrorCategory.PARAMETER_ERROR) == "record"
