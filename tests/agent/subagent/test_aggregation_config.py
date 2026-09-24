"""``AggregationConfig`` 配置落点（task 4.1；D6/Q8）。

grill 决策 7 的核心教训：**只加 dataclass 默认值不会让 yaml 生效**——
``_parse_workflow_limits`` 逐字段显式取值，所以每个新字段都必须在
``_parse_aggregation`` 里出现一次。

Q8 口径：

- 嵌套 ``AggregationConfig``（``thresholds`` + ``token_budgets`` 两个子 dataclass，
  均 frozen + ``field(default_factory)``）挂在 ``WorkflowLimitsConfig.aggregation``；
- 四档预算校验**非递减（允许相等）**，拒绝严格递减；
- 阈值与预算都走正整数的口径。
"""
import pytest

from agent.config import AsterwyndConfig, load_config


def _write(tmp_path, text: str):
    (tmp_path / "asterwynd.yaml").write_text(text, encoding="utf-8")
    return load_config(start_dir=tmp_path)


# --- 默认值 -----------------------------------------------------------------


def test_aggregation_defaults_match_documented_values():
    config = AsterwyndConfig()
    agg = config.subagents.workflow.aggregation
    assert agg.thresholds.max_fan_in == 10
    assert agg.token_budgets.leaf == 300
    assert agg.token_budgets.shard == 800
    assert agg.token_budgets.domain == 1500
    assert agg.token_budgets.root == 3000


def test_aggregation_subconfigs_are_frozen_with_default_factory():
    import dataclasses

    agg = AsterwyndConfig().subagents.workflow.aggregation
    for sub in (agg.thresholds, agg.token_budgets):
        assert dataclasses.is_dataclass(sub)
        assert sub.__dataclass_params__.frozen  # type: ignore[attr-defined]
    assert dataclasses.is_dataclass(agg)
    assert agg.__dataclass_params__.frozen  # type: ignore[attr-defined]


# --- yaml 逐字段落地（grill 决策 7） ----------------------------------------


def test_aggregation_values_load_from_yaml(tmp_path, monkeypatch):
    monkeypatch.delenv("ASTERWYND_MODE", raising=False)
    config = _write(
        tmp_path,
        """
subagents:
  workflow:
    recursion_limit: 7
    aggregation:
      thresholds:
        max_fan_in: 4
      token_budgets:
        leaf: 500
        shard: 900
        domain: 1600
        root: 3200
""",
    )
    agg = config.subagents.workflow.aggregation
    assert agg.thresholds.max_fan_in == 4
    assert agg.token_budgets.leaf == 500
    assert agg.token_budgets.shard == 900
    assert agg.token_budgets.domain == 1600
    assert agg.token_budgets.root == 3200
    # 同级的既有三闸不受影响
    assert config.subagents.workflow.recursion_limit == 7


def test_partial_aggregation_keeps_other_defaults(tmp_path, monkeypatch):
    monkeypatch.delenv("ASTERWYND_MODE", raising=False)
    config = _write(
        tmp_path,
        "subagents:\n  workflow:\n    aggregation:\n      thresholds:\n        max_fan_in: 3\n",
    )
    agg = config.subagents.workflow.aggregation
    assert agg.thresholds.max_fan_in == 3
    assert agg.token_budgets.root == 3000


def test_absent_aggregation_section_uses_defaults(tmp_path, monkeypatch):
    monkeypatch.delenv("ASTERWYND_MODE", raising=False)
    config = _write(tmp_path, "subagents:\n  workflow:\n    max_nodes: 30\n")
    assert config.subagents.workflow.aggregation.thresholds.max_fan_in == 10


# --- 校验 -------------------------------------------------------------------


def test_strictly_decreasing_budgets_are_rejected(tmp_path, monkeypatch):
    """Q8：非递减（允许相等），拒绝严格递减。leaf 500 > shard 300 必须报错。"""
    monkeypatch.delenv("ASTERWYND_MODE", raising=False)
    with pytest.raises(Exception):
        _write(
            tmp_path,
            """
subagents:
  workflow:
    aggregation:
      token_budgets:
        leaf: 500
        shard: 300
""",
        )


def test_equal_budgets_are_allowed(tmp_path, monkeypatch):
    """非递减允许相等：leaf == shard == domain == root 合法。"""
    monkeypatch.delenv("ASTERWYND_MODE", raising=False)
    config = _write(
        tmp_path,
        """
subagents:
  workflow:
    aggregation:
      token_budgets:
        leaf: 400
        shard: 400
        domain: 400
        root: 400
""",
    )
    assert config.subagents.workflow.aggregation.token_budgets.leaf == 400


def test_non_positive_aggregation_values_are_rejected(tmp_path, monkeypatch):
    monkeypatch.delenv("ASTERWYND_MODE", raising=False)
    for field in ("max_fan_in",):
        with pytest.raises(Exception):
            _write(
                tmp_path,
                f"subagents:\n  workflow:\n    aggregation:\n      thresholds:\n        {field}: 0\n",
            )
    with pytest.raises(Exception):
        _write(
            tmp_path,
            "subagents:\n  workflow:\n    aggregation:\n      token_budgets:\n        root: 0\n",
        )


def test_aggregation_must_be_mapping(tmp_path, monkeypatch):
    monkeypatch.delenv("ASTERWYND_MODE", raising=False)
    with pytest.raises(Exception):
        _write(tmp_path, "subagents:\n  workflow:\n    aggregation: 5\n")
