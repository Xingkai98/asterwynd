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

from agent.cost_tracker import compute_cost_cached
from benchmarks.models import DEFAULT_LAYER, LAYERS, TaskResult, resolve_layer

__all__ = [
    "DEFAULT_LAYER",
    "FAULT_OWNERS",
    "LAYERS",
    "PassKSummary",
    "bootstrap_ci",
    "cohen_kappa",
    "cost_per_resolved",
    "effective_pass_rate",
    "fault_owner_cross",
    "is_valid_round",
    "layer_pass_rate",
    "mean_std",
    "pass_at_k",
    "pass_k_success_rate",
    "resolve_layer",
]

_logger = logging.getLogger("asterwynd.benchmark.statistics")

# Orthogonal failure attribution dimension (C1 spec: agent/task/environment/unknown).
FAULT_OWNERS: tuple[str, ...] = ("agent", "task", "environment", "unknown")

# Reasons whose rounds carry no signal about the agent's ability: the task
# never ran, so the round is neither a pass nor a failure. These rounds are
# excluded before any pass-rate denominator is computed (C1 spec: invalid
# rounds SHALL NOT count into pass@1 / pass^k denominators).
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
