"""Statistical helpers for benchmark evaluation aggregation.

Pure Python (no numpy/scipy). Bootstrap confidence intervals use a fixed
random seed so results are reproducible.
"""
from __future__ import annotations

import logging
import random
import statistics as _stats
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from math import comb

from agent.cost_tracker import compute_cost_cached
from benchmarks.models import DEFAULT_LAYER, LAYERS, TaskResult, resolve_layer

__all__ = [
    "DEFAULT_LAYER",
    "FAULT_OWNERS",
    "LAYERS",
    "PassKSummary",
    "PairedComparison",
    "bootstrap_ci",
    "cohen_kappa",
    "cost_per_resolved",
    "effective_pass_rate",
    "fault_owner_cross",
    "is_valid_round",
    "layer_pass_rate",
    "mean_std",
    "mcnemar_exact",
    "paired_comparison",
    "pass_at_k",
    "process_efficiency",
    "pass_k_success_rate",
    "resolve_layer",
    "swebench_versions",
    "valid_round_count",
]

_logger = logging.getLogger("asterwynd.benchmark.statistics")

# Orthogonal failure attribution dimension (C1 spec: agent/task/environment/unknown).
FAULT_OWNERS: tuple[str, ...] = ("agent", "task", "environment", "unknown")

# Reasons whose rounds carry no signal about the agent's ability: the task
# never ran, so the round is neither a pass nor a failure. These rounds are
# excluded before any pass-rate denominator is computed (C1 spec: invalid
# rounds SHALL NOT count into pass@1 / pass^k denominators).
# Note: approval_unavailable currently has no producer in the benchmark
# path (agent-loop reports it as a tool error_type); the predicate keeps it
# defensive so a future fail-closed producer slots in without spec change.
INVALID_ROUND_REASONS = frozenset(
    {"docker_unavailable", "task_family_unsupported", "approval_unavailable"}
)


def is_valid_round(status: str | None, reason: str | None = None) -> bool:
    """Whether a benchmark round carries pass/fail signal.

    A round is invalid when the task never actually ran: ``unsupported``
    status (preflight/task-family failures) or an ``approval_unavailable``
    reason. All other statuses (passed / failed / error) count as valid.
    """
    if status == "unsupported":
        return False
    if reason in INVALID_ROUND_REASONS:
        return False
    return True


def effective_pass_rate(valid_pass_flags: Sequence[bool]) -> float:
    """pass@1: empirical pass rate over the *valid* rounds of a task/layer.

    Invalid rounds are expected to have been removed upstream; empty input
    yields 0.0.
    """
    if not valid_pass_flags:
        return 0.0
    return sum(1 for ok in valid_pass_flags if ok) / len(valid_pass_flags)


def valid_round_count(results: Sequence[TaskResult]) -> int:
    """Number of valid rounds in a result set.

    Exposes the sample size N for per-task CI small-N declarations; the
    rendering layer (C3) decides how to phrase the disclaimer.
    """
    return sum(1 for r in results if is_valid_round(r.status, r.reason))


def mean_std(values: Sequence[float]) -> tuple[float, float]:
    """Return (mean, sample standard deviation) of ``values``.

    Empty input yields (0.0, 0.0); a single value yields (value, 0.0).
    """
    if not values:
        return (0.0, 0.0)
    mean = _stats.mean(values)
    if len(values) > 1:
        return (mean, _stats.stdev(values))
    return (mean, 0.0)


def bootstrap_ci(
    values: Sequence[float],
    seed: int = 0,
    n_resamples: int = 2000,
    ci: float = 0.95,
) -> tuple[float, float]:
    """Percentile-method bootstrap confidence interval for the mean.

    Returns (lo, hi) for the requested confidence level. Reproducible for a
    fixed ``seed``. Empty input yields (0.0, 0.0); a single value yields
    (value, value).
    """
    if not values:
        return (0.0, 0.0)
    rng = random.Random(seed)
    n = len(values)
    sample_means = [
        _stats.mean(values[rng.randrange(n)] for _ in range(n))
        for _ in range(n_resamples)
    ]
    sample_means.sort()
    alpha = (1.0 - ci) / 2.0
    lo_idx = max(0, int(alpha * n_resamples))
    hi_idx = max(lo_idx, int((1.0 - alpha) * n_resamples) - 1)
    return (sample_means[lo_idx], sample_means[hi_idx])


def _comb(n: int, k: int) -> int:
    """Binomial coefficient C(n, k) as an exact integer."""
    if k < 0 or k > n:
        return 0
    k = min(k, n - k)
    result = 1
    for i in range(1, k + 1):
        result = result * (n - k + i) // i
    return result


def pass_at_k(n_success: int, n_total: int, k: int | None = None) -> float:
    """Task-level Pass@k using the combinatorial estimator (Chen et al. 2021).

    ``pass@k = 1 - C(n - c, k) / C(n, k)`` where ``n`` is the total number of
    rounds sampled, ``c`` is the number that passed, and ``k`` is the size of
    the subset whose at-least-one-pass probability we estimate. When ``k`` is
    omitted it defaults to ``n`` (the number of rounds run for this task).
    """
    if n_total <= 0:
        return 0.0
    if k is None:
        k = n_total
    if k <= 0 or n_success <= 0:
        return 0.0
    c = min(n_success, n_total)
    k = min(k, n_total)
    return 1.0 - _comb(n_total - c, k) / _comb(n_total, k)


def layer_pass_rate(layer_results: Sequence[bool]) -> float:
    """Mean pass rate across the rounds that belong to a layer."""
    if not layer_results:
        return 0.0
    return sum(1 for ok in layer_results if ok) / len(layer_results)


@dataclass
class PassKSummary:
    """Task-level pass^k aggregation result.

    ``rate`` is None when no task has enough valid rounds to estimate pass^k
    (sample is too small to be meaningful). Tasks whose valid-round count is
    below ``min_valid_rounds`` are excluded from both the numerator and the
    denominator.
    """

    rate: float | None
    passed_tasks: int
    valid_tasks: int
    excluded_tasks: int
    min_valid_rounds: int


def pass_k_success_rate(
    task_rounds: Sequence[Sequence[bool]],
    min_valid_rounds: int = 3,
) -> PassKSummary:
    """Task-level pass^k reliability: share of tasks that pass all valid rounds.

    Each element of ``task_rounds`` is one task's pass flags over its *valid*
    rounds (invalid rounds excluded upstream by the caller). A task counts as a
    pass when every valid round passed; tasks with fewer than
    ``min_valid_rounds`` valid rounds (or none) are excluded from both sides.
    Returns a :class:`PassKSummary`; ``rate`` is None when ``valid_tasks`` is
    zero.
    """
    passed_tasks = 0
    valid_tasks = 0
    excluded_tasks = 0
    for flags in task_rounds:
        if len(flags) < min_valid_rounds:
            excluded_tasks += 1
            continue
        valid_tasks += 1
        if all(flags):
            passed_tasks += 1
    rate = passed_tasks / valid_tasks if valid_tasks else None
    return PassKSummary(
        rate=rate,
        passed_tasks=passed_tasks,
        valid_tasks=valid_tasks,
        excluded_tasks=excluded_tasks,
        min_valid_rounds=min_valid_rounds,
    )


# ---------------------------------------------------------------------------
# Cost and failure attribution
# ---------------------------------------------------------------------------

_RESOLVED_STATUSES = frozenset({"passed", "passed_with_warnings"})
_FAILURE_STATUSES = frozenset({"failed", "error"})


def cost_per_resolved(
    results: Sequence[TaskResult],
) -> tuple[float | None, float, int]:
    """$/resolved-task over a layer's runs.

    Numerator: total LLM token cost across *all* runs, including failed ones
    (cache-aware, via ``compute_cost_cached``). Denominator: resolved count
    (``passed`` + ``passed_with_warnings``). Returns ``(per_resolved, total_cost,
    resolved_count)``; ``per_resolved`` is None when no task resolved. Only LLM
    token billing is included — no sandbox / CI / compute cost.
    """
    total_cost = 0.0
    resolved = 0
    for result in results:
        estimate = compute_cost_cached(
            result.model,
            input_tokens=result.input_tokens or 0,
            cache_read_tokens=result.cache_read_tokens or 0,
            cache_write_tokens=result.cache_write_tokens or 0,
            output_tokens=result.output_tokens or 0,
        )
        total_cost += estimate.cost
        if result.status in _RESOLVED_STATUSES:
            resolved += 1
    per_resolved = total_cost / resolved if resolved else None
    return (per_resolved, total_cost, resolved)


def fault_owner_cross(
    results: Sequence[TaskResult],
) -> dict[str, dict[str, int]]:
    """reason x fault_owner cross-tab over failure samples.

    Only ``failed`` / ``error`` results contribute (unsupported rounds are not
    failures, and passed results are not attribution samples). Unlabelled or
    invalid ``fault_owner`` strings fall back to ``unknown``.
    """
    cross: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for result in results:
        if result.status not in _FAILURE_STATUSES:
            continue
        owner = result.fault_owner
        if owner not in FAULT_OWNERS:
            if owner is not None:
                _logger.warning(
                    "Invalid fault_owner %r on task %s; falling back to unknown",
                    owner,
                    result.task_id,
                )
            owner = "unknown"
        cross[result.reason or "unknown_reason"][owner] += 1
    return {reason: dict(counts) for reason, counts in cross.items()}


def cohen_kappa(annotator_a: Sequence[str], annotator_b: Sequence[str]) -> float:
    """Cohen's kappa for two annotators' categorical labels.

    ``kappa = (Po - Pe) / (1 - Pe)`` where Po is the observed agreement and Pe
    the expected agreement under independence. Returns 0.0 for empty input.
    """
    if len(annotator_a) != len(annotator_b):
        raise ValueError("annotator label sequences must have equal length")
    n = len(annotator_a)
    if n == 0:
        return 0.0
    agreed = sum(1 for a, b in zip(annotator_a, annotator_b) if a == b)
    po = agreed / n
    counts_a = Counter(annotator_a)
    counts_b = Counter(annotator_b)
    pe = sum(
        (counts_a[label] / n) * (counts_b[label] / n) for label in set(counts_a) | set(counts_b)
    )
    if pe >= 1.0:
        return 1.0 if po == 1.0 else 0.0
    return (po - pe) / (1.0 - pe)


# ---------------------------------------------------------------------------
# Paired comparison
# ---------------------------------------------------------------------------

@dataclass
class PairedComparison:
    """Per-task delta + paired-bootstrap CI + win-rate + McNemar summary."""

    per_task_deltas: dict[str, float]
    delta_ci: tuple[float, float] | None
    win_rate: dict[str, int]
    mcnemar: dict | None


def _pass1_by_task(results: Sequence[TaskResult]) -> dict[str, tuple[float, int]]:
    """task_id -> (pass@1 over valid rounds, valid round count)."""
    buckets: dict[str, list[int]] = defaultdict(list)
    for result in results:
        if not is_valid_round(result.status, result.reason):
            continue
        buckets[result.task_id].append(
            1 if result.status in _RESOLVED_STATUSES else 0
        )
    return {
        task_id: (sum(flags) / len(flags), len(flags))
        for task_id, flags in buckets.items()
        if flags
    }


def _passk_bool_by_task(results: Sequence[TaskResult]) -> dict[str, bool]:
    """task_id -> all-valid-rounds-passed boolean, only for tasks with >= 3 valid rounds."""
    buckets: dict[str, list[bool]] = defaultdict(list)
    for result in results:
        if is_valid_round(result.status, result.reason):
            buckets[result.task_id].append(
                result.status in _RESOLVED_STATUSES
            )
    return {
        task_id: all(flags)
        for task_id, flags in buckets.items()
        if len(flags) >= 3
    }


def _paired_delta_ci(
    common_tasks: Sequence[str],
    a_pass1: dict[str, tuple[float, int]],
    b_pass1: dict[str, tuple[float, int]],
    seed: int,
    n_resamples: int = 2000,
    ci: float = 0.95,
) -> tuple[float, float]:
    rng = random.Random(seed)
    n = len(common_tasks)
    sample_means = []
    for _ in range(n_resamples):
        # Paired bootstrap: draw a task index once and read BOTH runs' pass@1
        # for that same task, so the resampled delta preserves the pairing.
        # Drawing A and B independently would inflate the variance (unpaired
        # variance Var(A)+Var(B) vs paired Var(A-B)) and understate significance.
        mean = 0.0
        for _ in range(n):
            task = common_tasks[rng.randrange(n)]
            mean += a_pass1[task][0] - b_pass1[task][0]
        sample_means.append(mean / n)
    sample_means.sort()
    alpha = (1.0 - ci) / 2.0
    lo = sample_means[max(0, int(alpha * n_resamples))]
    hi = sample_means[max(lo, int((1.0 - alpha) * n_resamples) - 1)]
    return (lo, hi)


def mcnemar_exact(b: int, c: int) -> dict:
    """Exact-binomial McNemar test on discordant pairs.

    ``b`` = pairs where A passed pass^k and B did not; ``c`` = the reverse.
    H0: b and c are equally likely. Two-sided p-value from the exact binomial
    distribution. No discordant pairs -> p=1.0, not significant.
    """
    n = b + c
    if n == 0:
        return {"p_value": 1.0, "b": b, "c": c, "significant": False, "n_discordant": 0}
    m = max(b, c)
    tail = sum(comb(n, i) for i in range(m, n + 1)) / (2**n)
    p = min(1.0, 2.0 * tail)
    return {
        "p_value": p,
        "b": b,
        "c": c,
        "significant": p < 0.05,
        "n_discordant": n,
    }


def paired_comparison(
    run_a: Sequence[TaskResult],
    run_b: Sequence[TaskResult],
    seed: int = 0,
) -> PairedComparison:
    """Paired comparison of two runs over a shared task set.

    Per-task delta uses pass@1 (effective pass rate over valid rounds). The
    difference CI is a paired bootstrap over tasks (fixed seed, reproducible).
    Win-rate counts tasks by whether A's pass@1 exceeds B's. McNemar uses the
    task-level pass^k booleans (all valid rounds passed, >= 3 valid rounds).
    """
    a_pass1 = _pass1_by_task(run_a)
    b_pass1 = _pass1_by_task(run_b)
    common = sorted(set(a_pass1) & set(b_pass1))
    deltas = {
        task_id: a_pass1[task_id][0] - b_pass1[task_id][0] for task_id in common
    }
    a_wins = sum(1 for d in deltas.values() if d > 0)
    b_wins = sum(1 for d in deltas.values() if d < 0)
    ties = len(deltas) - a_wins - b_wins

    delta_ci = (
        _paired_delta_ci(common, a_pass1, b_pass1, seed=seed) if common else None
    )

    a_pk = _passk_bool_by_task(run_a)
    b_pk = _passk_bool_by_task(run_b)
    common_pk = sorted(set(a_pk) & set(b_pk))
    b_cnt = sum(1 for t in common_pk if a_pk[t] and not b_pk[t])
    c_cnt = sum(1 for t in common_pk if b_pk[t] and not a_pk[t])
    mcnemar = mcnemar_exact(b_cnt, c_cnt) if common_pk else None

    return PairedComparison(
        per_task_deltas=deltas,
        delta_ci=delta_ci,
        win_rate={"a_wins": a_wins, "b_wins": b_wins, "ties": ties},
        mcnemar=mcnemar,
    )


# ---------------------------------------------------------------------------
# Process efficiency (D10) + SWE-bench pollution disclosure (D11)
# ---------------------------------------------------------------------------

def process_efficiency(trace_events: Sequence[dict]) -> dict:
    """Process-efficiency metrics from a trace's event list.

    ``time_to_first_successful_edit``: seconds from the run start to the first
    edit event whose status is success (``ok``/``success``); None when no
    successful edit exists. ``exploration_fraction``: share of tool-call wall
    time spent on non-Edit tools (0.0 when there are no tool calls). Rendering
    of both as result-page options belongs to C3.
    """
    if not trace_events:
        return {"time_to_first_successful_edit": None, "exploration_fraction": 0.0}
    run_start = min(ev.get("timestamp", 0.0) for ev in trace_events)

    first_edit_ts: float | None = None
    for ev in trace_events:
        if ev.get("type") == "edit":
            status = (ev.get("data") or {}).get("status")
            if status in ("ok", "success"):
                first_edit_ts = ev.get("timestamp")
                break
    time_to_first = (
        (first_edit_ts - run_start) if first_edit_ts is not None else None
    )

    open_calls: list[tuple[str | None, float]] = []
    total_duration = 0.0
    edit_duration = 0.0
    for ev in trace_events:
        etype = ev.get("type")
        data = ev.get("data") or {}
        if etype == "tool_call":
            open_calls.append((data.get("tool_name"), ev.get("timestamp", 0.0)))
        elif etype == "tool_result" and open_calls:
            name, start_ts = open_calls.pop(0)
            duration = ev.get("timestamp", 0.0) - start_ts
            if duration > 0:
                total_duration += duration
                if name == "Edit":
                    edit_duration += duration
    exploration = (
        (total_duration - edit_duration) / total_duration
        if total_duration > 0
        else 0.0
    )
    return {
        "time_to_first_successful_edit": time_to_first,
        "exploration_fraction": exploration,
    }


def swebench_versions(
    loaded_tasks: Sequence["LoadedTask"],
) -> tuple[str | None, str | None]:
    """(dataset_version, swebench_package_version) for run metadata (D11).

    Dataset version is the SWE-bench dataset identifier, built from the first
    SWE-bench task's ``dataset_name``/``dataset_split`` (e.g.
    ``princeton-nlp/SWE-bench_Verified@test``); the package version comes from
    ``importlib.metadata`` (None when swebench is not installed). Rendering of
    pollution disclosures belongs to C3.
    """
    import importlib.metadata as _metadata

    dataset_version: str | None = None
    for loaded in loaded_tasks:
        if getattr(loaded.task, "task_family", None) != "swebench":
            continue
        name = getattr(loaded.task, "dataset_name", None)
        split = getattr(loaded.task, "dataset_split", None)
        if name:
            dataset_version = f"{name}@{split}" if split else name
            break
    package_version: str | None = None
    try:
        package_version = _metadata.version("swebench")
    except Exception:
        package_version = None
    return dataset_version, package_version
