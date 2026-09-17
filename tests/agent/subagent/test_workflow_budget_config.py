"""``WorkflowBudgetConfig`` 配置落点（change ``workflow-budget-attribution`` task 4.1；
默认值语义由 ``workflow-budget-unbounded-default`` 修订，issue #196）。

口径（C4 Q11 + 本 change D1/D7）：

- 四字段（``max_total_tokens`` / ``max_total_cost_usd`` / ``max_total_runs`` /
  ``max_wall_time_s``）嵌套挂在 ``subagents.workflow.budget`` 下，**默认值全为 0
  （不限）**——未配置就不设上限，只有显式写下数值才设闸（参照 #192）；
- 四字段**均 ``0 = 不限``**，需要 workflow-budget 专用的非负解析函数——
  全局 ``_validate_positive_int`` / ``_parse_positive_float`` 在数值层拒绝 0，
  不能改它们的语义（``subagents.budget.*`` 等既有键依赖原口径）；
- 字段级显式 ``null`` **拒绝**；段落级 ``null``（``subagents`` / ``subagents.workflow``
  / ``subagents.workflow.budget``）同样**拒绝**（D7，避免空段静默关闸）；
- 逐字段 ``mapping.get``（grill 决策 7：只给 dataclass 默认值不会让 yaml 生效）。
"""
import dataclasses

import pytest

from agent.config import AsterwyndConfig, ConfigError, load_config


def _write(tmp_path, text: str):
    (tmp_path / "asterwynd.yaml").write_text(text, encoding="utf-8")
    return load_config(start_dir=tmp_path)


# --- 默认值 -----------------------------------------------------------------


def test_budget_defaults_are_unlimited():
    """issue #196 / D1：四维默认全为 0（不限）——未配置就不设上限。"""
    budget = AsterwyndConfig().subagents.workflow.budget
    assert budget.max_total_tokens == 0
    assert budget.max_total_cost_usd == 0.0
    assert budget.max_total_runs == 0
    assert budget.max_wall_time_s == 0.0


def test_budget_config_is_frozen_dataclass_nested_under_workflow():
    limits = AsterwyndConfig().subagents.workflow
    assert dataclasses.is_dataclass(limits.budget)
    assert limits.budget.__dataclass_params__.frozen  # type: ignore[attr-defined]


def test_budget_default_does_not_disable_c2_structural_max_runs():
    """issue #196 / D5：预算默认不限，但 C2 的 ``max_runs`` 结构闸仍是 300——
    「预算 0」只解除本层运行期预算，不解除声明期结构闸（C4 Q14）。"""
    limits = AsterwyndConfig().subagents.workflow
    assert limits.budget.max_total_runs == 0
    assert limits.max_runs == 300


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


def test_partial_budget_leaves_other_dimensions_unlimited(tmp_path, monkeypatch):
    """D1/D7：逐维 opt-in——只写一维时其余三维保持 0（不限），不是「互相校准的默认组」。"""
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
    assert budget.max_total_cost_usd == 0.0
    assert budget.max_total_runs == 0
    assert budget.max_wall_time_s == 0.0


def test_missing_budget_section_uses_unlimited_defaults(tmp_path, monkeypatch):
    monkeypatch.delenv("ASTERWYND_MODE", raising=False)
    config = _write(tmp_path, "subagents:\n  workflow:\n    max_runs: 12\n")
    assert config.subagents.workflow.budget.max_total_tokens == 0
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


# --- 段落级 null 拒绝（D7 / grill Q2，issue #196） ---------------------------


@pytest.mark.parametrize(
    "text",
    [
        "subagents:\n",  # subagents 段整段 null
        "subagents:\n  workflow:\n",  # subagents.workflow 段整段 null
        "subagents:\n  workflow:\n    budget:\n",  # subagents.workflow.budget 段整段 null
    ],
)
def test_section_level_null_is_rejected(tmp_path, monkeypatch, text):
    """D7：段落级显式 null 不得静默当成「未配置」。

    默认值改成 0（不限）后，静默放行会让用户写下空段时四闸全无——与字段级 null
    的明确拒绝口径也必须一致。用户原则：不写该字段 = 无上限；写了且有值 = 设上限；
    写了但不给值 = 报错。"""
    monkeypatch.delenv("ASTERWYND_MODE", raising=False)
    with pytest.raises(ConfigError):
        _write(tmp_path, text)


def test_absent_sections_still_reload_as_unlimited(tmp_path, monkeypatch):
    """对照组：**不写**这些段落（键缺失）不是错误，按 D1 落到「不限」。"""
    monkeypatch.delenv("ASTERWYND_MODE", raising=False)
    # subagents 段存在但完全不提 workflow / budget
    config = _write(tmp_path, "subagents:\n  max_spawns: 5\n")
    budget = config.subagents.workflow.budget
    assert budget.max_total_tokens == 0
    assert budget.max_total_runs == 0
    assert config.subagents.max_spawns == 5
    # 顶层 yaml 完全为空 → 全部默认
    empty = _write(tmp_path, "")
    assert empty.subagents.workflow.budget.max_total_cost_usd == 0.0
