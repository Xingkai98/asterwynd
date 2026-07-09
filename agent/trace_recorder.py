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
    def __init__(
        self,
        task_id: str = "",
        full_trace: bool = False,
        mode: str = "build",
        session_id: str | None = None,
        run_id: str | None = None,
    ):
        self.task_id = task_id
        self.full_trace = full_trace  # retained for serialization compat only
        self.mode = mode
        self.session_id = session_id
        self.run_id = run_id
        self.steps: list[TraceStep] = []
        self.started_at = time.time()

    def set_run_identity(
        self,
        *,
        session_id: str | None = None,
        run_id: str | None = None,
    ) -> None:
        if session_id is not None:
            self.session_id = session_id
        if run_id is not None:
            self.run_id = run_id

    def record(self, step_type: str, **data: Any) -> None:
        self.steps.append(
            TraceStep(step=len(self.steps) + 1, type=step_type, data=data)
        )

    def record_run_started(self, mode: str | None = None) -> None:
        if mode is not None:
            self.mode = mode
        data: dict[str, Any] = {"mode": self.mode}
        if self.session_id is not None:
            data["session_id"] = self.session_id
        if self.run_id is not None:
            data["run_id"] = self.run_id
        self.record("run_started", **data)

    def record_mode_changed(self, transition: dict[str, Any]) -> None:
        new_mode = transition.get("new_mode")
        if isinstance(new_mode, str):
            self.mode = new_mode
        self.record("mode_changed", **transition)

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

    def record_approval_request(self, request: dict[str, Any]) -> None:
        self.record("approval_request", **request)

    def record_approval_response(self, response: dict[str, Any]) -> None:
        self.record("approval_response", **response)

    def record_edit(self, path: str, status: str, summary: str) -> None:
        self.record("edit", tool_name="Edit", path=path, status=status, summary=summary)

    def record_parallel_execution(self, group: list[str]) -> None:
        self.record("parallel_execution_start", tools=group)

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

    def record_planning_state(self, snapshot: dict[str, Any]) -> None:
        self.record("planning_state_updated", **snapshot)

    def record_plan_document(
        self,
        event_type: str,
        document: dict[str, Any],
    ) -> None:
        self.record(event_type, **document)

    def latest_planning_summary(self) -> dict[str, Any] | None:
        for step in reversed(self.steps):
            if step.type == "planning_state_updated":
                summary = step.data.get("summary")
                return summary if isinstance(summary, dict) else None
        return None

    def record_completion(self, status: str, content: str = "") -> None:
        self.record(
            "completion",
            status=status,
            content=content,
            duration_seconds=round(time.time() - self.started_at, 1),
        )

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "task_id": self.task_id,
            "mode": self.mode,
            "full_trace": self.full_trace,
            "duration_seconds": round(time.time() - self.started_at, 1),
        }
        if self.session_id is not None:
            data["session_id"] = self.session_id
        if self.run_id is not None:
            data["run_id"] = self.run_id
        data["steps"] = [asdict(step) for step in self.steps]
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    def write_to_file(self, path: str | Path) -> None:
        Path(path).write_text(self.to_json() + "\n", errors="replace")
