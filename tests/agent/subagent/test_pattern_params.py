"""内置模板的 ``params`` 校验（Q3 键封闭 / Q5 值类型 / Q6 fan-out 上界 / Q7 rounds）。

校验落在 ``compile_pattern`` 这一唯一 choke point（统一入口与资产路径共用）。

- **键名**（Q3）：按模板各自的封闭子集，跨模板键结构化拒绝（`peer-review` 不接受
  `workers`）。
- **值类型**（Q5）：计数/轮数键必须是整数（拒绝布尔/浮点/字符串/null）；预算键须
  是数值。**clamp 保留**——`workers=0/-5` 仍按既有语义落到下界，不报错。
- **fan-out 上界**（Q6）：`workers`/`teams`/`proposers` 超过模板 foreach 节点的
  ``max_items``（默认 20）时拒绝——理由是「静默截断」+「**编译期内存放大**」（实测
  `workers=100000` 会在编译期真的造出 10 万个 item 对象）。
- **rounds**（Q7 方案 A）：``max_rounds`` **不做静态上界**（换算比依赖拓扑）；仅当
  明显荒谬（> 图级 ``recursion_limit``，任何拓扑下都不可能跑满）时拒绝。
"""
import pytest

from agent.subagent.patterns import PATTERNS, compile_pattern
from agent.subagent.workflow import (
    DEFAULT_RECURSION_LIMIT,
    WorkflowNode,
    WorkflowValidationError,
)

_FANOUT_CAP = WorkflowNode.__dataclass_fields__["max_items"].default


# --- 键名：按模板封闭（Q3） -------------------------------------------------


def test_cross_template_key_is_rejected():
    """把 orchestrator-worker 的键记混到 peer-review —— 今天静默忽略，必须拒绝。"""
    with pytest.raises(WorkflowValidationError, match="does not accept"):
        compile_pattern("peer-review", task="t", params={"workers": 7})


def test_unknown_key_is_rejected():
    with pytest.raises(WorkflowValidationError, match="does not accept"):
        compile_pattern("orchestrator-worker", task="t", params={"bogus": 1})


def test_rejection_lists_available_keys():
    with pytest.raises(WorkflowValidationError) as exc:
        compile_pattern("peer-review", task="t", params={"workers": 7})
    # reason 自足：列出该模板可用的键
    assert "max_rounds" in str(exc.value)


# --- 值类型（Q5） -----------------------------------------------------------


@pytest.mark.parametrize(
    "pattern,params",
    [
        ("orchestrator-worker", {"workers": "abc"}),
        ("orchestrator-worker", {"workers": None}),
        ("orchestrator-worker", {"workers": 2.5}),
        ("hierarchical", {"teams": [1, 2]}),
        ("bidding", {"proposers": {}}),
        ("peer-review", {"max_rounds": "many"}),
    ],
)
def test_non_integer_count_value_is_rejected(pattern, params):
    with pytest.raises(WorkflowValidationError):
        compile_pattern(pattern, task="t", params=params)


def test_bool_is_not_accepted_as_a_count():
    """``isinstance(True, int)`` 为真——布尔必须在显式排除之列。"""
    with pytest.raises(WorkflowValidationError):
        compile_pattern("orchestrator-worker", task="t", params={"workers": True})


def test_budget_keys_require_numeric_values():
    with pytest.raises(WorkflowValidationError):
        compile_pattern("orchestrator-worker", task="t", params={"worker_max_tokens": "big"})


def test_budget_keys_accept_int_and_float():
    spec = compile_pattern(
        "orchestrator-worker",
        task="t",
        params={"workers": 2, "worker_max_tokens": 123, "worker_max_time_s": 7.5},
    )
    assert spec.node("workers").max_tokens == 123
    assert spec.node("workers").max_time_s == 7.5


def test_budget_key_none_means_unset_not_rejected():
    """``None`` 对预算键是既有「未设置」语义（``_worker_budget`` 的 ``is not None``）。"""
    spec = compile_pattern(
        "orchestrator-worker", task="t", params={"workers": 2, "worker_max_tokens": None}
    )
    assert spec.node("workers").max_tokens is None


# --- clamp 保留（Q5） -------------------------------------------------------


@pytest.mark.parametrize("value", [0, -5])
def test_count_zero_or_negative_still_clamps(value):
    """既有语义：``max(1, ...)`` / ``max(2, ...)`` clamp 到有效下界，不报错。"""
    spec = compile_pattern("orchestrator-worker", task="t", params={"workers": value})
    assert len(spec.node("workers").items) == 1


def test_proposers_zero_clamps_to_two():
    spec = compile_pattern("bidding", task="t", params={"proposers": 0})
    assert len(spec.node("proposers").items) == 2


# --- fan-out 上界（Q6） -----------------------------------------------------


@pytest.mark.parametrize("value", [_FANOUT_CAP + 1, 50, 100000])
@pytest.mark.parametrize(
    "pattern,key", [("orchestrator-worker", "workers"), ("hierarchical", "teams"), ("bidding", "proposers")]
)
def test_fanout_count_over_cap_is_rejected(pattern, key, value):
    with pytest.raises(WorkflowValidationError, match="max_items"):
        compile_pattern(pattern, task="t", params={key: value})


def test_fanout_count_at_cap_is_accepted():
    """对照的合法路径：正好等于上界必须成功（防假保护）。"""
    spec = compile_pattern("orchestrator-worker", task="t", params={"workers": _FANOUT_CAP})
    assert len(spec.node("workers").items) == _FANOUT_CAP


def test_fanout_rejection_names_the_bound_source():
    """Q6：reason 须写明界来源（``max_items``）。"""
    with pytest.raises(WorkflowValidationError) as exc:
        compile_pattern("orchestrator-worker", task="t", params={"workers": 100000})
    assert "max_items" in str(exc.value)


def test_fanout_over_cap_rejected_before_building_items():
    """编译期放大的证据：超界必须在**造出 item 对象之前**被拒，不能先 build 再查。"""
    with pytest.raises(WorkflowValidationError):
        # 若校验晚于 build，这会先分配 100000 个 dict 再抛——测试用内存不可观测，
        # 但用「非法 params 不应进到 build」的等价断言：捕获到的是校验异常而非 OOM。
        compile_pattern("orchestrator-worker", task="t", params={"workers": 200000})


# --- rounds（Q7 方案 A） ----------------------------------------------------


def test_max_rounds_within_recursion_limit_is_accepted():
    """Q7 方案 A：``max_rounds`` 在界内（含恰好等于 recursion_limit）必须成功。"""
    spec = compile_pattern("peer-review", task="t", params={"max_rounds": DEFAULT_RECURSION_LIMIT})
    assert spec.node("gate").max_routes == DEFAULT_RECURSION_LIMIT


def test_max_rounds_absurdly_over_recursion_limit_is_rejected():
    """声明值连 superstep 数都超过 —— 任何拓扑下都不可能跑满。"""
    with pytest.raises(WorkflowValidationError, match="recursion_limit"):
        compile_pattern(
            "peer-review", task="t", params={"max_rounds": DEFAULT_RECURSION_LIMIT + 1}
        )
    with pytest.raises(WorkflowValidationError, match="recursion_limit"):
        compile_pattern("peer-review", task="t", params={"max_rounds": 100000})


def test_max_rounds_not_rejected_by_fanout_cap():
    """``max_rounds`` 不属于 fan-out 键，不受 ``max_items`` 上界约束。"""
    # 21 > max_items(20) 但远低于 recursion_limit(25) —— 合法。
    spec = compile_pattern("peer-review", task="t", params={"max_rounds": _FANOUT_CAP + 1})
    assert spec.node("gate").max_routes == _FANOUT_CAP + 1


# --- 合法路径不回归 ---------------------------------------------------------


@pytest.mark.parametrize(
    "pattern,params",
    [
        ("orchestrator-worker", {"workers": 3}),
        ("hierarchical", {"teams": 2}),
        ("bidding", {"proposers": 4}),
        ("peer-review", {"max_rounds": 5}),
        ("orchestrator-worker", None),
        ("peer-review", {}),
    ],
)
def test_legal_params_still_compile(pattern, params):
    spec = compile_pattern(pattern, task="t", params=params)
    assert spec is not None


def test_all_patterns_still_round_trip():
    """每个模板的默认编译仍可 round-trip（校验不得改变默认路径）。"""
    from agent.subagent.workflow import parse_workflow_spec

    for name in PATTERNS:
        spec = compile_pattern(name, task="t")
        assert parse_workflow_spec(spec.to_dict()).spec_hash == spec.spec_hash
