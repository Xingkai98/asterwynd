from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import yaml

from agent.workflow.models import DEFAULT_ROUTING, PhaseRouting
from agent.workflow.routing import (
    RoutingConfigError,
    _apply_degradation,
    _parse_routing_dict,
    build_routing_config_prompt,
    get_routing_for_phase,
    load_global_defaults,
    merge_routing,
    routing_to_dict,
)


class TestApplyDegradation:
    def test_degrade_same_session_non_inline(self):
        result = _apply_degradation(PhaseRouting(executor="subagent", session_mode="same"), "planning")
        assert result.executor == "subagent"
        assert result.session_mode == "new"

    def test_no_degradation_for_inline(self):
        result = _apply_degradation(PhaseRouting(executor="inline", session_mode="same"), "planning")
        assert result.session_mode == "same"

    def test_no_degradation_for_new(self):
        result = _apply_degradation(PhaseRouting(executor="subagent", session_mode="new"), "planning")
        assert result.session_mode == "new"


class TestParseRoutingDict:
    def test_empty_dict_falls_back_to_defaults(self):
        result = _parse_routing_dict({})
        # All active phases should be present with defaults
        for phase in ("wayfinding", "planning", "building", "closing"):
            assert phase in result
            assert isinstance(result[phase], PhaseRouting)

    def test_codex_executor(self):
        result = _parse_routing_dict({"planning": {"executor": "codex", "session_mode": "new"}})
        assert result["planning"].executor == "codex"
        assert result["planning"].session_mode == "new"

    def test_missing_phase_uses_default(self):
        result = _parse_routing_dict({"planning": {"executor": "codex", "session_mode": "new"}})
        assert result["building"] == DEFAULT_ROUTING["building"]

    def test_degradation_applied_during_parse(self):
        result = _parse_routing_dict({"building": {"executor": "codex", "session_mode": "same"}})
        assert result["building"].session_mode == "new"  # degraded

    def test_invalid_type_raises(self):
        with pytest.raises(RoutingConfigError, match="must be a mapping"):
            _parse_routing_dict({"planning": "not-a-dict"})


class TestLoadGlobalDefaults:
    def test_missing_file_returns_hardcoded(self):
        result = load_global_defaults("/nonexistent/path")
        for phase in ("wayfinding", "planning", "building", "closing"):
            assert phase in result

    def test_yaml_with_routing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            openspec_dir = Path(tmpdir) / "openspec"
            openspec_dir.mkdir()
            config = openspec_dir / "config.yaml"
            config.write_text(yaml.dump({
                "routing": {
                    "planning": {"executor": "codex", "session_mode": "new"},
                }
            }))
            result = load_global_defaults(tmpdir)
            assert result["planning"].executor == "codex"
            assert result["planning"].session_mode == "new"


class TestMergeRouting:
    def test_per_change_override(self):
        global_defaults = dict(DEFAULT_ROUTING)
        per_change = {"planning": {"executor": "subagent", "session_mode": "new"}}
        result = merge_routing(global_defaults, per_change)
        assert result["planning"].executor == "subagent"
        assert result["planning"].session_mode == "new"
        # other phases unchanged
        assert result["building"] == global_defaults["building"]

    def test_none_per_change_leaves_unchanged(self):
        result = merge_routing(dict(DEFAULT_ROUTING), None)
        assert result == dict(DEFAULT_ROUTING)

    def test_degradation_on_per_change(self):
        per_change = {"building": {"executor": "codex", "session_mode": "same"}}
        result = merge_routing(dict(DEFAULT_ROUTING), per_change)
        assert result["building"].session_mode == "new"


class TestGetRoutingForPhase:
    def test_valid_phase(self):
        routing = dict(DEFAULT_ROUTING)
        result = get_routing_for_phase(routing, "planning")
        assert isinstance(result, PhaseRouting)

    def test_terminal_phase_raises(self):
        with pytest.raises(RoutingConfigError):
            get_routing_for_phase(dict(DEFAULT_ROUTING), "blocked")
        with pytest.raises(RoutingConfigError):
            get_routing_for_phase(dict(DEFAULT_ROUTING), "done")


class TestRoutingToDict:
    def test_output_format(self):
        result = routing_to_dict(dict(DEFAULT_ROUTING))
        for phase in ("wayfinding", "planning", "building", "closing"):
            assert phase in result
            assert "executor" in result[phase]
            assert "session_mode" in result[phase]
