from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any


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

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}

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

    def write_json(self, path: str | Path) -> None:
        Path(path).write_text(
            json.dumps(asdict(self), indent=2, ensure_ascii=False) + "\n",
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
