"""Dynamic resource guardrails for benchmark concurrency.

Instead of hard-coding a parallel limit, derive a safe concurrency value from
the current machine's available memory and CPU count, leaving headroom so we
do not saturate memory/CPU (SWE-bench Docker verification and repeated runs
are memory-hungry). Low-resource environments degrade to a serial run.
"""
from __future__ import annotations

import os
import subprocess

try:
    import psutil
except Exception:  # pragma: no cover - psutil is an optional convenience
    psutil = None

# Base memory estimate per concurrent task instance (512 MiB).
_DEFAULT_PER_TASK_BYTES = 512 * 1024 * 1024


def _mem_available_bytes() -> int:
    """Return available memory in bytes (0 when psutil is unavailable)."""
    if psutil is not None:
        try:
            return int(psutil.virtual_memory().available)
        except Exception:
            return 0
    return 0


def _cpu_count() -> int:
    """Return the logical CPU count (falls back to 1)."""
    return os.cpu_count() or 1


def suggest_parallel(
    mem_available_bytes: int | None = None,
    cpu_count: int | None = None,
    *,
    per_task_bytes: int = _DEFAULT_PER_TASK_BYTES,
) -> int:
    """Derive a safe parallel concurrency from available memory and CPU.

    Both values default to the current machine
    (``psutil.virtual_memory().available`` and ``os.cpu_count()``). The result
    never exceeds ``cpu_count`` and is always >= 1; low-resource environments
    return 1.
    """
    mem = mem_available_bytes if mem_available_bytes is not None else _mem_available_bytes()
    cpu = cpu_count if cpu_count is not None else _cpu_count()
    if cpu <= 0 or mem <= 0 or per_task_bytes <= 0:
        return 1
    # A concurrent instance (agent process + test runs, possibly Docker
    # verification) is conservatively estimated at 4x the base per-task
    # footprint. Halve the resulting memory budget again for headroom so the
    # machine is never saturated.
    per_instance_bytes = per_task_bytes * 4
    mem_budget = mem // per_instance_bytes // 2
    return max(1, min(cpu, mem_budget))


def is_docker_available() -> bool:
    """Probe whether the Docker daemon is reachable.

    Runs ``docker info``; any failure (missing binary, timeout, non-zero
    exit code) returns False.
    """
    try:
        proc = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except Exception:
        return False
    return proc.returncode == 0


def suggest_parallel_default() -> int:
    """Convenience wrapper for the current machine."""
    return suggest_parallel()
