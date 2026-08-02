"""Benchmark regression gate — compare a benchmark run against a persisted baseline.

Pure logic module (no benchmark execution, no CLI): the CLI in ``agent/main.py``
runs the benchmark, this module reads results, computes metrics, compares them
against a baseline JSON, and returns a verdict with a non-zero exit code
signature. Threshold semantics follow design.md Decision 7/14/15:

- success rate uses an absolute drop in percentage points (strict ``>``);
- p95 latency uses a relative regression fraction with an absolute floor
  (``max(baseline * (1 + frac), baseline + ABS_P95_FLOOR_S)``) so sub-second
  baselines are not subject to meaningless relative jitter;
- p95 is computed over *passed* tasks only — failed/crashed tasks carry
  ``duration_seconds=0.0`` and would otherwise drag latency down and hide
  regressions.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from benchmarks.models import TaskResult
from benchmarks.report import PASS_STATUSES, collect_run_results, _percentile

DEFAULT_BASELINE_PATH = Path("benchmarks/baseline.json")
BASELINE_SCHEMA_VERSION = 1

# Absolute p95 floor (seconds): when the baseline p95 is below this, the
# relative fraction is meaningless (e.g. ±2.5ms on a 0.05s baseline), so the
# gate compares against ``baseline + ABS_P95_FLOOR_S`` instead.
ABS_P95_FLOOR_S = 1.0

DEFAULT_SUCCESS_RATE_DROP = 0.05
DEFAULT_P95_REGRESSION_FRAC = 0.05


def _git_short_sha() -> str | None:
    """Best-effort HEAD short sha for baseline auditability."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    sha = out.stdout.strip()
    return sha or None


def compute_run_metrics(results: list[TaskResult]) -> dict:
    """Compute gate metrics from a benchmark run's TaskResult list.

    ``success_rate`` follows ``report.PASS_STATUSES`` (passed /
    passed_with_warnings). ``p95_latency_s`` is the nearest-rank 95th
    percentile of *passed* tasks' ``duration_seconds`` only.
    """
    total = len(results)
    passed = [r for r in results if r.status in PASS_STATUSES]
    success_rate = len(passed) / total if total else 0.0
    passed_durations = sorted(r.duration_seconds for r in passed)
    p95 = _percentile(passed_durations, 0.95) if passed_durations else 0.0
    return {
        "success_rate": success_rate,
        "p95_latency_s": p95,
        "total_tasks": total,
        "passed_tasks": len(passed),
    }


@dataclass
class GateVerdict:
    """Result of comparing a run's metrics against a baseline."""

    ok: bool
    baseline_metrics: dict
    current_metrics: dict
    success_rate_delta: float
    p95_delta: float
    blocked_reasons: list[str] = field(default_factory=list)
    skipped: bool = False
    skip_reason: str = ""
    p95_skipped: bool = False

    def report(self) -> str:
        """Render a human-readable gate report (also used in CLI output)."""
        if self.skipped:
            return f"GATE SKIPPED: {self.skip_reason}"
        p95_line = (
            "  p95_latency_s: SKIPPED (deterministic task set)"
            if self.p95_skipped
            else (
                f"  p95_latency_s: baseline={self.baseline_metrics.get('p95_latency_s'):.4f} "
                f"current={self.current_metrics.get('p95_latency_s'):.4f} "
                f"delta={self.p95_delta:+.4f}"
            )
        )
        lines = [
            "BENCHMARK GATE",
            f"  success_rate: baseline={self.baseline_metrics.get('success_rate'):.4f} "
            f"current={self.current_metrics.get('success_rate'):.4f} "
            f"delta={self.success_rate_delta:+.4f}",
            p95_line,
        ]
        if self.ok:
            lines.append("  result: PASS")
        else:
            lines.append(
                "  result: FAIL — " + ", ".join(self.blocked_reasons)
            )
        return "\n".join(lines)


def compare(
    baseline: dict,
    current: dict,
    *,
    success_rate_drop: float = DEFAULT_SUCCESS_RATE_DROP,
    p95_regression_frac: float = DEFAULT_P95_REGRESSION_FRAC,
    check_p95: bool = True,
) -> GateVerdict:
    """Compare current metrics against a baseline dict.

    Returns an ``ok=True`` verdict when neither metric regressed beyond the
    thresholds. ``current`` may carry extra keys (``total_tasks`` etc.); only
    ``success_rate`` and ``p95_latency_s`` are compared.

    ``check_p95=False`` skips the p95 latency check entirely. It is meant for
    deterministic near-zero-IO task sets (gate-smoke) whose wall-clock is
    dominated by environment factors (worktree creation, cleanup) — observed
    variance 0.5s-20.5s on the same machine — so p95 is not a reliable
    regression signal there. The strict p95 semantics remain the default for
    real benchmark workflows.
    """
    base_sr = baseline["metrics"]["success_rate"]
    base_p95 = baseline["metrics"]["p95_latency_s"]
    cur_sr = current["success_rate"]
    cur_p95 = current["p95_latency_s"]

    sr_delta = cur_sr - base_sr
    p95_delta = cur_p95 - base_p95

    blocked: list[str] = []
    # Epsilon guards float precision: `1.0 - 0.95` is 0.050000000000000044,
    # which must NOT count as "more than 5pp". Boundary is strict >.
    eps = 1e-9
    if base_sr - cur_sr > success_rate_drop + eps:
        blocked.append("success_rate")
    if check_p95:
        p95_ceiling = max(base_p95 * (1 + p95_regression_frac), base_p95 + ABS_P95_FLOOR_S)
        if cur_p95 > p95_ceiling + eps:
            blocked.append("p95_latency")

    return GateVerdict(
        ok=not blocked,
        baseline_metrics=baseline["metrics"],
        current_metrics=current,
        success_rate_delta=sr_delta,
        p95_delta=p95_delta,
        blocked_reasons=blocked,
        p95_skipped=not check_p95,
    )


def load_baseline(path: str | Path) -> dict | None:
    """Load a baseline JSON; return ``None`` when the file is missing."""
    p = Path(path)
    if not p.exists():
        return None
    data = json.loads(p.read_text(encoding="utf-8"))
    if data.get("schema_version") != BASELINE_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported baseline schema_version {data.get('schema_version')}"
        )
    return data


def write_baseline(data: dict, path: str | Path) -> None:
    """Write a baseline dict to ``path`` (parents created)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def build_baseline(
    *,
    task_set: str,
    agent: str,
    model: str,
    metrics: dict,
    per_task: dict,
    git_sha: str | None = None,
    created_at: str | None = None,
) -> dict:
    """Assemble a baseline dict for ``write_baseline``."""
    from datetime import datetime, timezone

    return {
        "schema_version": BASELINE_SCHEMA_VERSION,
        "agent": agent,
        "model": model,
        "task_set": task_set,
        "created_at": created_at or datetime.now(timezone.utc).isoformat(),
        "git_sha": git_sha if git_sha is not None else _git_short_sha(),
        "metrics": metrics,
        "per_task": per_task,
    }


def compute_run_metrics_from_dir(run_dir: str | Path) -> dict:
    """Convenience: read a run directory via ``collect_run_results`` and compute metrics."""
    return compute_run_metrics(collect_run_results(Path(run_dir)))
