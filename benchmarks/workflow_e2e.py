"""端到端 record → replay 可比性断言（change ``benchmark-workflow-replay``，D6）。

口径（grill Q6 推荐「乙：fake 定可比」）：

- **fake LLM 场景**做全等断言：``spec_hash`` / ``node_count`` / ``run_count`` /
  ``status`` 全等。前提是 record 臂与 replay 臂各喂一份**专门编排的 script**
  （``ScriptedLLM`` 按调用序消费，replay 省掉的那次规划调用会让朴素复用错位）。
  fake 下 ``cost`` 恒 0，是 0 == 0 的平凡断言，不作为有信息量的验证。
- **真实 LLM 场景**只硬断言 ``spec_hash`` 相等 + record/replay 无异常完成；
  ``cost`` / ``run_count`` / ``peak_active`` / ``critical_path_s`` **只报不判**
  （wall-clock 与 token 噪声会 flaky）。不设 ±容差——容差解决不了必然不等。

降级（Q7 落点 A）：真实 LLM 不可用时降级为 fake round-trip，并在每个任务的
``result.json`` 写机器可读事实（``e2e_llm_verified: false`` 等），**不静默当已验证**。
"""
from __future__ import annotations

from typing import Any

from benchmarks.workflow_replay import OBSERVED_FIELDS

#: ``e2e_verification_mode`` 的取值。
MODE_REAL_LLM = "real_llm_round_trip"
MODE_FAKE = "fake_round_trip"
MODE_NOT_EXECUTED = "not_executed"

#: 真实 LLM 下**只报不判**的字段（Q6）。
REPORT_ONLY_FIELDS: tuple[str, ...] = (
    "cost_usd",
    "run_count",
    "peak_active",
    "critical_path_s",
)


def compare_record_and_replay(
    record_entry: dict,
    replay_entry: dict,
    *,
    fake_llm: bool,
    extra_observed: dict | None = None,
) -> dict[str, Any]:
    """比对 record 那次与 replay 那次的编排字段（Q6）。

    ``fake_llm=True`` 时对 :data:`OBSERVED_FIELDS` 做全等断言；``False`` 时只硬断言
    ``workflow_spec_hash``，其余字段放进 ``reported`` 只报不判。
    """
    observed = dict(record_entry.get("observed") or {})
    if extra_observed:
        observed.update(extra_observed)
    spec_hash_expected = record_entry.get("workflow_spec_hash")
    spec_hash_actual = replay_entry.get("workflow_spec_hash")
    comparisons: dict[str, Any] = {
        "workflow_spec_hash": _compare(spec_hash_expected, spec_hash_actual),
    }
    hard_asserted = ["workflow_spec_hash"]
    if fake_llm:
        for field in OBSERVED_FIELDS:
            if field == "status":
                continue
            comparisons[field] = _compare(
                observed.get(field), replay_entry.get(field)
            )
            hard_asserted.append(field)
    reported = {
        field: {
            "record": observed.get(field),
            "replay": replay_entry.get(field),
        }
        for field in REPORT_ONLY_FIELDS
    }
    return {
        "hard_asserted": hard_asserted,
        "comparisons": comparisons,
        "reported_only": reported,
        "all_hard_assertions_passed": all(
            comparisons[field]["equal"] for field in hard_asserted
        ),
    }


def e2e_fields(
    *,
    llm_available: bool,
    assertions: dict | None = None,
    skip_reason: str | None = None,
    fake_llm: bool = False,
) -> dict[str, Any]:
    """组装写进 ``TaskResult`` 的 e2e 机器可读事实（Q7 落点 A）。"""
    if not llm_available:
        # 降级：真实 LLM 不可用 → fake round-trip + 显式记录缺口，不静默当已验证。
        return {
            "e2e_llm_verified": False,
            "e2e_verification_mode": MODE_FAKE,
            "e2e_skip_reason": skip_reason
            or "real LLM unavailable; fell back to fake round-trip",
            "e2e_assertions": assertions,
        }
    return {
        "e2e_llm_verified": not fake_llm,
        "e2e_verification_mode": MODE_FAKE if fake_llm else MODE_REAL_LLM,
        "e2e_skip_reason": skip_reason,
        "e2e_assertions": assertions,
    }


def _compare(expected: Any, actual: Any) -> dict[str, Any]:
    return {"expected": expected, "actual": actual, "equal": expected == actual}
