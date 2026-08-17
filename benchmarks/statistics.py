"""Statistical helpers for benchmark evaluation aggregation.

Pure Python (no numpy/scipy). Bootstrap confidence intervals use a fixed
random seed so results are reproducible.
"""
from __future__ import annotations

import random
import statistics as _stats
from collections.abc import Sequence
from dataclasses import dataclass

from benchmarks.models import DEFAULT_LAYER, LAYERS, resolve_layer

__all__ = [
    "DEFAULT_LAYER",
    "LAYERS",
    "PassKSummary",
    "bootstrap_ci",
    "effective_pass_rate",
    "is_valid_round",
    "layer_pass_rate",
    "mean_std",
    "pass_at_k",
    "pass_k_success_rate",
    "resolve_layer",
]

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
