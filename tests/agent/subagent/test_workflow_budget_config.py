"""``WorkflowBudgetConfig`` 配置落点（change ``workflow-budget-attribution``，task 4.1）。

Q11 口径（grill 决策 8 + 用户确认）：

- 四字段（``max_total_tokens`` / ``max_total_cost_usd`` / ``max_total_runs`` /
  ``max_wall_time_s``）嵌套挂在 ``subagents.workflow.budget`` 下，默认值
  200000 / 5.0 / 300 / 1800；
- 四字段**均 ``0 = 不限``**，需要 workflow-budget 专用的非负解析函数——
  全局 ``_validate_positive_int`` / ``_parse_positive_float`` 在数值层拒绝 0，
  不能改它们的语义（``subagents.budget.*`` 等既有键依赖原口径）；
- 显式 ``null`` **拒绝**（避免 YAML 缺值意外关闭安全闸）；
- 逐字段 ``mapping.get``（grill 决策 7：只给 dataclass 默认值不会让 yaml 生效）。
"""
import dataclasses

import pytest

from agent.config import AsterwyndConfig, ConfigError, load_config


def _write(tmp_path, text: str):
    (tmp_path / "asterwynd.yaml").write_text(text, encoding="utf-8")
    return load_config(start_dir=tmp_path)


# --- 默认值 -----------------------------------------------------------------


def test_budget_defaults_match_documented_values():
    budget = AsterwyndConfig().subagents.workflow.budget
    assert budget.max_total_tokens == 200000
    assert budget.max_total_cost_usd == 5.0
    assert budget.max_total_runs == 300
    assert budget.max_wall_time_s == 1800.0


def test_budget_config_is_frozen_dataclass_nested_under_workflow():
    limits = AsterwyndConfig().subagents.workflow
    assert dataclasses.is_dataclass(limits.budget)
    assert limits.budget.__dataclass_params__.frozen  # type: ignore[attr-defined]


def test_max_total_runs_default_matches_structural_max_runs():
    """D6/Q4：默认值必须与 C2 的 ``max_runs`` 一致，否则会出现「声明期 300、
    运行期 200」的误伤。"""
    limits = AsterwyndConfig().subagents.workflow
    assert limits.budget.max_total_runs == limits.max_runs == 300


# --- yaml 逐字段落地（grill 决策 7） ----------------------------------------


def test_budget_values_load_from_yaml(tmp_path, monkeypatch):
    monkeypatch.delenv("ASTERWYND_MODE", raising=False)
    config = _write(
        tmp_path,
        """
subagents:
  workflow:
    budget:
      max_total_tokens: 1234
      max_total_cost_usd: 1.5
      max_total_runs: 7
      max_wall_time_s: 60
""",
    )
    budget = config.subagents.workflow.budget
    assert budget.max_total_tokens == 1234
    assert budget.max_total_cost_usd == 1.5
    assert budget.max_total_runs == 7
    assert budget.max_wall_time_s == 60.0
    # 同级既有键不受影响
    assert config.subagents.workflow.max_runs == 300


def test_partial_budget_keeps_other_defaults(tmp_path, monkeypatch):
    monkeypatch.delenv("ASTERWYND_MODE", raising=False)
    config = _write(
        tmp_path,
        """
subagents:
  workflow:
    budget:
      max_total_tokens: 999
""",
    )
    budget = config.subagents.workflow.budget
    assert budget.max_total_tokens == 999
    assert budget.max_total_cost_usd == 5.0
    assert budget.max_total_runs == 300
    assert budget.max_wall_time_s == 1800.0


def test_missing_budget_section_uses_defaults(tmp_path, monkeypatch):
    monkeypatch.delenv("ASTERWYND_MODE", raising=False)
    config = _write(tmp_path, "subagents:\n  workflow:\n    max_runs: 12\n")
    assert config.subagents.workflow.budget.max_total_tokens == 200000
    assert config.subagents.workflow.max_runs == 12


# --- 0 = 不限（Q11） --------------------------------------------------------


def test_zero_means_unlimited_for_all_four_dimensions(tmp_path, monkeypatch):
    monkeypatch.delenv("ASTERWYND_MODE", raising=False)
    config = _write(
        tmp_path,
        """
subagents:
  workflow:
    budget:
      max_total_tokens: 0
      max_total_cost_usd: 0
      max_total_runs: 0
      max_wall_time_s: 0
""",
    )
    budget = config.subagents.workflow.budget
    assert budget.max_total_tokens == 0
    assert budget.max_total_cost_usd == 0.0
    assert budget.max_total_runs == 0
    assert budget.max_wall_time_s == 0.0


def test_zero_does_not_leak_into_global_positive_validators(tmp_path, monkeypatch):
    """专用非负解析函数不得改全局 ``_validate_positive_int``/``_parse_positive_float``
    的语义：``subagents.budget.max_tokens: 0`` 仍然被拒。"""
    monkeypatch.delenv("ASTERWYND_MODE", raising=False)
    with pytest.raises(ConfigError):
        _write(tmp_path, "subagents:\n  budget:\n    max_tokens: 0\n")


# --- 显式 null 拒绝（Q11） --------------------------------------------------


@pytest.mark.parametrize(
    "key",
    ["max_total_tokens", "max_total_cost_usd", "max_total_runs", "max_wall_time_s"],
)
def test_explicit_null_is_rejected(tmp_path, monkeypatch, key):
    monkeypatch.delenv("ASTERWYND_MODE", raising=False)
    with pytest.raises(ConfigError):
        _write(tmp_path, f"subagents:\n  workflow:\n    budget:\n      {key}: null\n")


def test_negative_values_are_rejected(tmp_path, monkeypatch):
    monkeypatch.delenv("ASTERWYND_MODE", raising=False)
    with pytest.raises(ConfigError):
        _write(tmp_path, "subagents:\n  workflow:\n    budget:\n      max_total_tokens: -1\n")
    with pytest.raises(ConfigError):
        _write(tmp_path, "subagents:\n  workflow:\n    budget:\n      max_wall_time_s: -0.5\n")


def test_non_numeric_values_are_rejected(tmp_path, monkeypatch):
    monkeypatch.delenv("ASTERWYND_MODE", raising=False)
    with pytest.raises(ConfigError):
        _write(tmp_path, "subagents:\n  workflow:\n    budget:\n      max_total_tokens: many\n")
    with pytest.raises(ConfigError):
        _write(tmp_path, "subagents:\n  workflow:\n    budget:\n      max_total_cost_usd: [1]\n")
