from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from agent.workflow.models import PhaseRouting
from agent.workflow.routing import (
    RoutingConfigError,
    _apply_degradation,
    _parse_routing_dict,
    build_routing_config_prompt,
    get_routing_for_phase,
    load_global_defaults,
    merge_routing,
)


class TestDegradation:
    def test_non_inline_same_degrades_to_new(self):
        r = PhaseRouting(executor="subagent", session_mode="same")
        result = _apply_degradation(r, "reviewing")
        assert result.executor == "subagent"
        assert result.session_mode == "new"

    def test_inline_same_is_fine(self):
        r = PhaseRouting(executor="inline", session_mode="same")
        result = _apply_degradation(r, "planning")
        assert result.executor == "inline"
        assert result.session_mode == "same"

    def test_non_inline_new_is_fine(self):
        r = PhaseRouting(executor="subagent", session_mode="new")
        result = _apply_degradation(r, "reviewing")
        assert result.executor == "subagent"
        assert result.session_mode == "new"

    def test_non_inline_ask_is_fine(self):
        r = PhaseRouting(executor="codex", session_mode="ask")
        result = _apply_degradation(r, "code-review")
        assert result.executor == "codex"
        assert result.session_mode == "ask"


class TestParseRoutingDict:
    def test_valid_routing(self):
        raw = {
            "planning": {"executor": "inline", "session_mode": "same"},
            "reviewing": {"executor": "subagent", "session_mode": "new"},
            "building": {"executor": "inline", "session_mode": "same"},
            "code-review": {"executor": "codex", "session_mode": "new"},
            "closing": {"executor": "inline", "session_mode": "same"},
        }
        result = _parse_routing_dict(raw)
        assert result["planning"].executor == "inline"
        assert result["code-review"].executor == "codex"

    def test_invalid_executor(self):
        raw = {"planning": {"executor": "gpt-chat", "session_mode": "same"}}
        with pytest.raises(RoutingConfigError, match="invalid executor"):
            _parse_routing_dict(raw)

    def test_invalid_session_mode(self):
        raw = {"planning": {"executor": "inline", "session_mode": "reuse"}}
        with pytest.raises(RoutingConfigError, match="invalid session_mode"):
            _parse_routing_dict(raw)

    def test_missing_phase_uses_default(self):
        raw = {"planning": {"executor": "inline", "session_mode": "same"}}
        result = _parse_routing_dict(raw)
        assert result["reviewing"].executor == "subagent"

    def test_non_dict_entry_raises(self):
        raw = {"planning": "inline"}
        with pytest.raises(RoutingConfigError, match="must be a mapping"):
            _parse_routing_dict(raw)

    def test_degradation_applied_during_parse(self):
        raw = {"reviewing": {"executor": "subagent", "session_mode": "same"}}
        result = _parse_routing_dict(raw)
        assert result["reviewing"].session_mode == "new"


class TestLoadGlobalDefaults:
    def test_missing_file_returns_hardcoded(self):
        result = load_global_defaults("/nonexistent/path")
        assert result["planning"].executor == "inline"
        assert result["reviewing"].executor == "subagent"

    def test_empty_yaml_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp) / "openspec"
            config_dir.mkdir()
            (config_dir / "config.yaml").write_text("")
            result = load_global_defaults(tmp)
            assert result["planning"].executor == "inline"

    def test_yaml_with_routing(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp) / "openspec"
            config_dir.mkdir()
            (config_dir / "config.yaml").write_text("""
routing:
  planning:
    executor: inline
    session_mode: same
  reviewing:
    executor: codex
    session_mode: new
""")
            result = load_global_defaults(tmp)
            assert result["reviewing"].executor == "codex"
            assert result["building"].executor == "inline"  # default


class TestMergeRouting:
    def test_per_change_overrides_global(self):
        global_defaults = {
            "planning": PhaseRouting(executor="inline", session_mode="same"),
            "reviewing": PhaseRouting(executor="subagent", session_mode="new"),
        }
        per_change = {"reviewing": {"executor": "codex"}}
        result = merge_routing(global_defaults, per_change)
        assert result["reviewing"].executor == "codex"
        assert result["reviewing"].session_mode == "new"  # preserved from global

    def test_none_per_change_returns_global(self):
        global_defaults = {
            "planning": PhaseRouting(executor="inline", session_mode="same"),
        }
        result = merge_routing(global_defaults, None)
        assert result["planning"].executor == "inline"

    def test_invalid_executor_in_per_change_is_ignored(self):
        global_defaults = {
            "planning": PhaseRouting(executor="inline", session_mode="same"),
        }
        per_change = {"planning": {"executor": "invalid"}}
        result = merge_routing(global_defaults, per_change)
        assert result["planning"].executor == "inline"  # unchanged

    def test_degradation_applied_on_merge(self):
        global_defaults = {
            "planning": PhaseRouting(executor="inline", session_mode="same"),
        }
        per_change = {"planning": {"executor": "subagent", "session_mode": "same"}}
        result = merge_routing(global_defaults, per_change)
        assert result["planning"].executor == "subagent"
        assert result["planning"].session_mode == "new"


class TestBuildRoutingConfigPrompt:
    def test_generates_prompt_with_all_phases(self):
        prompt = build_routing_config_prompt()
        for phase in ("planning", "reviewing", "building", "code-review", "closing"):
            assert phase in prompt

    def test_includes_executor_and_session_mode(self):
        prompt = build_routing_config_prompt()
        assert "inline" in prompt
        assert "subagent" in prompt

    def test_accepts_custom_routing(self):
        custom = {
            "planning": PhaseRouting(executor="inline", session_mode="same"),
        }
        prompt = build_routing_config_prompt(custom)
        assert "inline" in prompt


class TestGetRoutingForPhase:
    def test_returns_routing_for_phase(self):
        routing = {
            "planning": PhaseRouting(executor="inline", session_mode="same"),
        }
        result = get_routing_for_phase(routing, "planning")
        assert result.executor == "inline"

    def test_raises_for_blocked(self):
        with pytest.raises(RoutingConfigError, match="no routing for terminal phase"):
            get_routing_for_phase({}, "blocked")

    def test_raises_for_done(self):
        with pytest.raises(RoutingConfigError, match="no routing for terminal phase"):
            get_routing_for_phase({}, "done")
