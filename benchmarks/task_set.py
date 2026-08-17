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
from dataclasses import dataclass
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


@dataclass(frozen=True)
class CoverageReport:
    """Result of the suite-level coverage check."""

    missing_capabilities: list[str]
    missing_scenarios: list[str]
    unknown_task_ids: list[str]

    def is_complete(self) -> bool:
        return not (self.missing_capabilities or self.missing_scenarios)


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

        return CoverageReport(
            missing_capabilities=missing_capabilities,
            missing_scenarios=missing_scenarios,
            unknown_task_ids=unknown_task_ids,
        )
