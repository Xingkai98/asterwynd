from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any

# Capability layers used for evaluation aggregation. Tasks group into these
# layers; unknown or missing categories fall back to the default layer.
LAYERS: tuple[str, ...] = (
    "execution",
    "tool-usage",
    "context-planning",
    "multi-step-solving",
)
DEFAULT_LAYER = "execution"


def resolve_layer(category: str | None) -> str:
    """Map a task ``category`` to a capability layer.

    Unknown or missing categories fall back to the default layer so
    aggregation never fails on a missing label.
    """
    if category in LAYERS:
        return category
    return DEFAULT_LAYER


class BenchmarkReason(str, Enum):
    SETUP_ERROR = "setup_error"
    TOOL_ERROR = "tool_error"
    EDIT_VALIDATION = "edit_validation"
    TEST_FAILURE = "test_failure"
    TEST_TIMEOUT = "test_timeout"
    MAX_ITERATIONS = "max_iterations"
    NO_CHANGE = "no_change"
    OUT_OF_SCOPE_CHANGE = "out_of_scope_change"
    MODEL_FAILURE = "model_failure"
    DOCKER_UNAVAILABLE = "docker_unavailable"
    DOCKER_RUNTIME_ERROR = "docker_runtime_error"


@dataclass
class AgentRunResult:
    status: str = "completed"
    iterations: int = 0
    tool_calls: int = 0
    edit_count: int = 0
    test_runs: int = 0
    reason: str | None = None
    output: str = ""
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class TaskResult:
    task_id: str
    agent: str
    model: str = ""
    mode: str = "build"
    agent_run_id: str | None = None
    status: str = "error"
    test_exit_code: int | None = None
    duration_seconds: float = 0.0
    iterations: int = 0
    tool_calls: int = 0
    edit_count: int = 0
    test_runs: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    reason: str | None = None
    planning_summary: dict[str, Any] | None = None
    category: str | None = None
    run_round: int | None = None
    task_family: str | None = None
    # C2 evaluation-metrics: cache-aware cost, sampling, fault attribution.
    # All optional so old artifacts keep parsing and None values stay omitted.
    cache_read_tokens: int | None = None
    cache_write_tokens: int | None = None
    temperature: float | None = None
    seed: int | None = None
    fault_owner: str | None = None
    partial: dict[str, Any] | None = None

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict) -> "TaskResult":
        """Parse a ``result.json`` dict back into a TaskResult.

        Unknown keys are ignored and missing fields fall back to the
        dataclass defaults, so older or hand-crafted artifacts stay
        compatible.
        """
        field_names = set(cls.__dataclass_fields__.keys())
        return cls(**{k: v for k, v in data.items() if k in field_names})

    def write_json(self, path: str | Path) -> None:
        Path(path).write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n",
            errors="replace",
        )


@dataclass
class RunMetadata:
    run_id: str
    agent: str
    model: str = ""
    mode: str = "build"
    started_at: str = ""
    ended_at: str = ""
    task_count: int = 0
    passed: int = 0
    warnings: int = 0
    failed: int = 0
    unsupported: int = 0
    # C2 evaluation-metrics: report tuple fields (all optional, None omitted).
    task_set_hash: str | None = None
    max_iterations: int | None = None
    timeout_seconds: int | None = None
    network: str | None = None
    adapter_version: str | None = None
    prompt_version: str | None = None
    pricing_table_version: str | None = None
    temperature: float | None = None
    seed: int | None = None
    model_version: str | None = None
    swebench_dataset_version: str | None = None
    swebench_package_version: str | None = None

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}

    def write_json(self, path: str | Path) -> None:
        Path(path).write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n",
            errors="replace",
        )


def render_summary(results: list[TaskResult]) -> str:
    lines = [
        "# Benchmark Run",
        "",
        "| Task | Status | Time | Iterations | Tool Calls | Failure |",
        "|------|--------|------|------------|------------|---------|",
    ]
    for result in results:
        failure = result.reason or "-"
        lines.append(
            f"| {result.task_id} | {result.status} | {result.duration_seconds}s | "
            f"{result.iterations} | {result.tool_calls} | {failure} |"
        )
    return "\n".join(lines) + "\n"
