"""Task-set manifest: track grouping + suite-level capability coverage matrix.

G1/D2: capability layering lives at suite level (OpenHands-style coverage
matrix), not as per-task orthogonal tags. The manifest declares which tasks
cover which capability columns; ``track`` stays in each task.json as the
single source of truth (OQ-1). ``validate_coverage`` mechanically enforces
"every declared capability column and every scenario column has at least one
local A/B task" (D2 / OQ-2: Verified-track tasks are excluded from the matrix
so their bug-fix bias cannot saturate the scenario columns).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from benchmarks.task_schema import LoadedTask

# D2: 7 capability columns declared at suite level.
CAPABILITIES = [
    "tool-usage",
    "context-planning",
    "multi-step-solving",
    "error-recovery",
    "safety-boundary",
    "long-term-memory",
    "long-context",
]

# G1/D1: scenario 5 枚举，规范顺序保证机械校验输出稳定。
SCENARIO_ORDER = ("bug-fix", "feature-dev", "refactor", "debug", "integration")

# OQ-2: 覆盖矩阵只统计本地 A+B 任务；verified 子集单独披露。
_LOCAL_TRACKS = {None, "A", "B"}

# Q6: spec delta「context-planning 列 SHALL 有 B 轨任务登记」的机械强制。
# 只对声明的缺口能力列生效：该能力列必须至少有一个指定 track 的任务登记，
# 其余能力列维持 A+B 聚合校验（evaluation-btrack-expansion OQ-6）。
REQUIRED_TRACK_COVERAGE: dict[str, set[str]] = {
    "context-planning": {"B"},
    "long-term-memory": {"B"},
    "long-context": {"B"},
}


@dataclass(frozen=True)
class CoverageReport:
    """Result of the suite-level coverage check."""

    missing_capabilities: list[str]
    missing_scenarios: list[str]
    unknown_task_ids: list[str]
    # Q6: e.g. "context-planning@B" —— 能力列缺指定 track 的任务登记。
    missing_track_coverage: list[str] = field(default_factory=list)

    def is_complete(self) -> bool:
        return not (
            self.missing_capabilities
            or self.missing_scenarios
            or self.missing_track_coverage
        )


@dataclass
class Manifest:
    path: Path
    version: int
    capabilities: list[str]
    coverage: dict[str, list[str]]  # task_id -> capability columns

    @classmethod
    def load(cls, path: str | Path) -> "Manifest":
        manifest_path = Path(path)
        data = json.loads(manifest_path.read_text())
        return cls(
            path=manifest_path,
            version=data.get("version", 1),
            capabilities=data.get("capabilities", list(CAPABILITIES)),
            coverage=data.get("coverage", {}),
        )

    def validate_coverage(self, loaded: list[LoadedTask]) -> CoverageReport:
        """Return missing columns/unknown ids for the local A/B task subset.

        Capability columns come from the manifest's ``coverage`` map, counted
        only for task ids that actually exist as local A/B tasks. Scenario
        columns come from each local A/B task's ``scenario`` field.
        """
        known_ids = {
            t.task.id
            for t in loaded
            if t.task.task_family == "local" and t.task.track in _LOCAL_TRACKS
        }
        unknown_task_ids = sorted(set(self.coverage) - known_ids)

        covered_capabilities = {
            cap
            for task_id, caps in self.coverage.items()
            if task_id in known_ids
            for cap in caps
        }
        missing_capabilities = [
            cap for cap in self.capabilities if cap not in covered_capabilities
        ]

        covered_scenarios = {
            t.task.scenario
            for t in loaded
            if t.task.task_family == "local"
            and t.task.track in _LOCAL_TRACKS
            and t.task.scenario is not None
        }
        missing_scenarios = [s for s in SCENARIO_ORDER if s not in covered_scenarios]

        # Q6: per-track 能力列缺口——能力列必须有指定 track 的任务登记。
        loaded_by_id = {t.task.id: t.task for t in loaded}
        covered_capability_tracks = {
            (cap, loaded_by_id[task_id].track)
            for task_id, caps in self.coverage.items()
            if task_id in known_ids
            for cap in caps
        }
        missing_track_coverage = sorted(
            f"{cap}@{track}"
            for cap, required_tracks in REQUIRED_TRACK_COVERAGE.items()
            for track in sorted(required_tracks)
            if (cap, track) not in covered_capability_tracks
        )

        return CoverageReport(
            missing_capabilities=missing_capabilities,
            missing_scenarios=missing_scenarios,
            unknown_task_ids=unknown_task_ids,
            missing_track_coverage=missing_track_coverage,
        )
