from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class TraceStep:
    step: int
    type: str
    data: dict[str, Any] = field(default_factory=dict)


class TraceRecorder:
    def __init__(self, task_id: str = "", full_trace: bool = False):
        self.task_id = task_id
        self.full_trace = full_trace  # retained for serialization compat only
        self.steps: list[TraceStep] = []
        self.started_at = time.time()

    def record(self, step_type: str, **data: Any) -> None:
        self.steps.append(
            TraceStep(step=len(self.steps) + 1, type=step_type, data=data)
        )

    def record_iteration(
        self,
        iteration: int,
        assistant_preview: str = "",
        tool_calls: list[dict[str, Any]] | None = None,
    ) -> None:
        self.record(
            "llm_iteration",
            iteration=iteration,
            assistant_preview=assistant_preview,
            tool_calls=tool_calls or [],
        )

    def record_tool_call(self, tool_name: str, arguments: dict[str, Any]) -> None:
        self.record("tool_call", tool_name=tool_name, arguments=arguments)

    def record_tool_result(
        self,
        tool_name: str,
        status: str,
        duration_ms: float,
        observation: str,
    ) -> None:
        self.record(
            "tool_result",
            tool_name=tool_name,
            status=status,
            duration_ms=round(duration_ms, 1),
            observation=observation,
        )

    def record_edit(self, path: str, status: str, summary: str) -> None:
        self.record("edit", tool_name="Edit", path=path, status=status, summary=summary)

    def record_diff(self, diff_path: str, summary: str) -> None:
        self.record("diff", diff_path=diff_path, summary=summary)

    def record_test(
        self,
        command: str,
        exit_code: int,
        duration_ms: float,
        output: str,
    ) -> None:
        self.record(
            "test",
            command=command,
            exit_code=exit_code,
            duration_ms=round(duration_ms, 1),
            output=output,
        )

    def record_completion(self, status: str, content: str = "") -> None:
        self.record(
            "completion",
            status=status,
            content=content,
            duration_seconds=round(time.time() - self.started_at, 1),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "full_trace": self.full_trace,
            "duration_seconds": round(time.time() - self.started_at, 1),
            "steps": [asdict(step) for step in self.steps],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    def write_to_file(self, path: str | Path) -> None:
        Path(path).write_text(self.to_json() + "\n", errors="replace")
