"""ToolQualityStore — per-tool quality scoring and soft degradation (batch 2).

Consumes call outcomes fed from the agent loop tool-execution point
(``agent/loop.py`` Phase 3) and produces a per-tool quality score from success
rate, average duration factor and user approval rate (design Decision 3).
Scores below ``degrade_threshold`` soft-degrade the tool: it leaves the
variable-layer selection candidates but stays visible in ``get_all_schemas``
and remains callable, so the permission model is untouched.
"""
from __future__ import annotations

import json
from collections import deque
from pathlib import Path
from typing import Any


class ToolQualityStore:
    """Sliding-window per-tool quality store with optional JSON persistence."""

    def __init__(
        self,
        *,
        window_size: int = 50,
        success_weight: float = 0.5,
        duration_weight: float = 0.3,
        approval_weight: float = 0.2,
        duration_ceiling_ms: float = 30_000.0,
        degrade_threshold: float = 0.4,
        min_samples: int = 5,
        store_path: str | Path | None = None,
    ) -> None:
        if window_size <= 0:
            raise ValueError("window_size must be positive")
        if min_samples <= 0:
            raise ValueError("min_samples must be positive")
        self.window_size = window_size
        self.success_weight = success_weight
        self.duration_weight = duration_weight
        self.approval_weight = approval_weight
        self.duration_ceiling_ms = duration_ceiling_ms
        self.degrade_threshold = degrade_threshold
        self.min_samples = min_samples
        self.store_path = Path(store_path) if store_path else None
        self._windows: dict[str, deque] = {}
        if self.store_path is not None and self.store_path.exists():
            self.load()

    def record(
        self,
        tool_name: str,
        *,
        success: bool,
        duration_ms: float,
        approval_required: bool = False,
        approval_granted: bool = False,
        executed: bool = True,
    ) -> None:
        """Record one tool-call observation.

        ``executed=False`` marks an approval-denied call: it contributes to the
        approval signal but not to success/duration stats (the tool never ran).
        """
        window = self._windows.setdefault(tool_name, deque(maxlen=self.window_size))
        window.append(
            {
                "success": bool(success),
                "duration_ms": float(duration_ms),
                "approval_required": bool(approval_required),
                "approval_granted": bool(approval_granted),
                "executed": bool(executed),
            }
        )

    def score(self, tool_name: str) -> float | None:
        """Weighted quality score in [0, 1]; ``None`` when data is insufficient."""
        window = self._windows.get(tool_name)
        if not window:
            return None
        executed = [r for r in window if r["executed"]]
        if len(executed) < self.min_samples:
            return None
        success_rate = sum(r["success"] for r in executed) / len(executed)
        avg_duration = sum(r["duration_ms"] for r in executed) / len(executed)
        duration_factor = max(
            0.0, min(1.0, 1.0 - avg_duration / self.duration_ceiling_ms)
        )

        required = [r for r in window if r["approval_required"]]
        weights = [self.success_weight, self.duration_weight]
        terms = [success_rate, duration_factor]
        if required:
            approval_rate = (
                sum(r["approval_granted"] for r in required) / len(required)
            )
            weights.append(self.approval_weight)
            terms.append(approval_rate)
        total_weight = sum(weights)
        if total_weight <= 0:
            return None
        return sum(w * t for w, t in zip(weights, terms)) / total_weight

    def is_degraded(self, tool_name: str) -> bool:
        score = self.score(tool_name)
        return score is not None and score < self.degrade_threshold

    def degraded_tools(self) -> set[str]:
        return {name for name in self._windows if self.is_degraded(name)}

    def quality_notice(self, tool_name: str) -> str | None:
        """Soft degradation notice; ``None`` when the tool is not degraded."""
        score = self.score(tool_name)
        if score is None or score >= self.degrade_threshold:
            return None
        return (
            f"[quality degraded] {tool_name} quality {score:.2f} below "
            f"{self.degrade_threshold}; consider an alternative."
        )

    def record_run_end(self) -> None:
        """Flush accumulated window state to the JSON store."""
        self.save()

    def save(self, path: str | Path | None = None) -> None:
        target = Path(path) if path is not None else self.store_path
        if target is None:
            return
        payload: dict[str, list[dict[str, Any]]] = {
            name: list(window) for name, window in self._windows.items()
        }
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2))

    def load(self, path: str | Path | None = None) -> None:
        target = Path(path) if path is not None else self.store_path
        if target is None or not target.exists():
            return
        data = json.loads(target.read_text())
        for name, records in data.items():
            window = deque(maxlen=self.window_size)
            window.extend(records)
            self._windows[name] = window
