"""routing.py 的活面测试 + 已删符号的负向回归（issue #239）。

四阶段状态机退役（`retire-4phase-state-machine`）后，`routing` 概念随之消失
（其 `路由配置` Requirement 已 REMOVED）。本文件覆盖清理后的真实状态：

- **活面**：`load_workflow_methods` / `is_workflow_enabled`（`resume_audit.py` 与
  `workflow_state.py` 在用）。
- **负向回归**：已删的 routing 符号必须真的不存在——它们只服务已退役的四阶段
  路由，恢复任何一个都意味着清理被回退。
"""

from __future__ import annotations

import json

import pytest

from agent.workflow import routing
from agent.workflow.routing import is_workflow_enabled, load_workflow_methods

REMOVED_ROUTING_SYMBOLS = (
    "load_global_defaults",
    "merge_routing",
    "get_routing_for_phase",
    "build_routing_config_prompt",
    "RoutingConfigError",
    "routing_to_dict",
    "_parse_routing_dict",
    "_parse_phase_routing",
    "_apply_degradation",
    "FALLBACK_CONFIG_PATH",
    "ROUTING_CONFIG_KEY",
    "_get_openspec_config_path",
    "_ACTIVE_PHASES",
)


class TestLoadWorkflowMethods:
    def test_missing_file_returns_empty_dict(self, tmp_path):
        assert load_workflow_methods(tmp_path) == {}

    def test_malformed_json_returns_empty_dict(self, tmp_path):
        p = tmp_path / "scripts" / "workflow_methods.json"
        p.parent.mkdir(parents=True)
        p.write_text("{ not json", encoding="utf-8")
        assert load_workflow_methods(tmp_path) == {}

    def test_non_dict_payload_returns_empty_dict(self, tmp_path):
        p = tmp_path / "scripts" / "workflow_methods.json"
        p.parent.mkdir(parents=True)
        p.write_text(json.dumps(["not", "a", "dict"]), encoding="utf-8")
        assert load_workflow_methods(tmp_path) == {}

    def test_loads_real_payload(self, tmp_path):
        p = tmp_path / "scripts" / "workflow_methods.json"
        p.parent.mkdir(parents=True)
        p.write_text(json.dumps({"workflow": {"enabled": False}}), encoding="utf-8")
        assert load_workflow_methods(tmp_path) == {"workflow": {"enabled": False}}


class TestIsWorkflowEnabled:
    def test_default_true_when_missing(self, tmp_path):
        assert is_workflow_enabled(tmp_path) is True

    def test_false_when_disabled(self, tmp_path):
        p = tmp_path / "scripts" / "workflow_methods.json"
        p.parent.mkdir(parents=True)
        p.write_text(json.dumps({"workflow": {"enabled": False}}), encoding="utf-8")
        assert is_workflow_enabled(tmp_path) is False

    def test_non_dict_workflow_section_defaults_true(self, tmp_path):
        p = tmp_path / "scripts" / "workflow_methods.json"
        p.parent.mkdir(parents=True)
        p.write_text(json.dumps({"workflow": "nonsense"}), encoding="utf-8")
        assert is_workflow_enabled(tmp_path) is True


class TestRemovedRoutingSymbols:
    """判别性：任一符号被恢复（即清理回退）时本类必须变红。"""

    @pytest.mark.parametrize("symbol", REMOVED_ROUTING_SYMBOLS)
    def test_symbol_is_gone(self, symbol):
        assert not hasattr(routing, symbol), (
            f"routing.{symbol} 应已在 issue #239 清理中删除——"
            "它只服务已退役的四阶段路由（`路由配置` Requirement 已 REMOVED）"
        )
