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

#: ``status`` 的两侧口径不同，**不能**直接等值比较：
#: record 侧是 scheduler envelope 的图级状态（``completed``），replay 侧是
#: ``TaskResult.status`` 的 benchmark 状态（``replayed``）——后者被 Q10 读法 A
#: 固定成专值，永远不可能等于前者。fake 场景的 status 断言因此收敛为
#: 「两侧都**无异常完成**」，矛盾（record 无异常 / replay 异常）才算失败。
#:
#: **本集合是唯一源**：``benchmarks/runner._replay_completed_cleanly`` 直接复用它
#: （此前两处各写一份字面表，靠人工保持同步——本 change 就漏过一次：``stalled``
#: 只加进了 runner 那份，两份同名谓词对同一输入给出相反答案）。新增图级档位时
#: **只改这里**。
#:
#: 为何是「黑名单」而不是「白名单（只认 ``completed``）」：``failed`` /
#: ``completed_with_failures`` 的回放**确实执行过节点**（LLM 被真实调用过），
#: 所以仍算「无异常完成」（只是没成功）；``stalled`` 则是**零节点成功**
#: （图根本没跑起来），回放没验证到任何东西，故必须列入异常。
UNHEALTHY_WORKFLOW_STATUSES = frozenset(
    {"graph_recursion_exceeded", "cancelled", "error", "declared", "stalled"}
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
                # 两侧 status 的**口径不同**（record 侧是图级状态、replay 侧是
                # benchmark 的 ``replayed`` 专值），等值比较恒假；断言收敛为
                # 「两侧都无异常完成」，矛盾才算失败。
                record_status = observed.get(field)
                replay_status = replay_entry.get("workflow_status")
                comparisons["status"] = {
                    "record": record_status,
                    "replay": replay_status,
                    "equal": _status_comparable(record_status, replay_status),
                }
                hard_asserted.append(field)
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


def _workflow_completed_cleanly(status: Any) -> bool:
    """图级状态是否「无异常完成」（与 ``runner._replay_completed_cleanly`` 同源）。"""
    return bool(status) and status not in UNHEALTHY_WORKFLOW_STATUSES


def _status_comparable(record_status: Any, replay_status: Any) -> bool:
    """record 与 replay 的图级状态是否可比（见 :data:`UNHEALTHY_WORKFLOW_STATUSES`）。

    - 两侧都无异常完成 → 可比；
    - 两侧都异常完成 → 要求**同一个**异常状态（回放复现了同一种失败）；
    - 一侧正常一侧异常 → 不可比（回放没复现 record 的行为）。
    """
    record_ok = _workflow_completed_cleanly(record_status)
    replay_ok = _workflow_completed_cleanly(replay_status)
    if record_ok != replay_ok:
        return False
    if record_ok:
        return True
    return record_status == replay_status


def _compare(expected: Any, actual: Any) -> dict[str, Any]:
    return {"expected": expected, "actual": actual, "equal": expected == actual}
