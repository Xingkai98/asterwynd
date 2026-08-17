"""VerifierAdapter abstraction for benchmark evaluation frameworks.

The verification/score phase of a benchmark framework is pluggable: the
runner looks up an adapter by ``task_family`` from a registry and calls
``verify()``. Adding a new framework (SWE-bench, Harbor, ...) only requires a
new adapter + registration + contract test; the shared runner, statistics and
result-page pipeline stay unchanged.
"""
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, Protocol

from benchmarks.models import BenchmarkReason
from benchmarks.task_schema import LoadedTask


@dataclass
class Verdict:
    """Standardized result of a framework verification step."""

    status: str
    reason: str | None = None
    detail: str = ""
    score: float | None = None
    # SWE-bench strict resolved boolean (None when the framework does not
    # provide one). C2: passed-with-warnings handling and strict-resolved
    # pass-through for $/resolved-task denominators.
    resolved: bool | None = None
    # Partial-success fields (e.g. SWE-bench f2p_rate/p2p_rate/reward).
    partial: dict | None = None


class VerifierAdapter(Protocol):
    """Verify an agent's output for a task and produce a standardized Verdict."""

    def verify(
        self,
        loaded: LoadedTask,
        task_output,
        patch_text: str,
        log=None,
    ) -> Verdict:
        ...


class SwebenchAdapter:
    """SWE-bench Verified verification protocol.

    Converts the agent patch into a ``predictions.jsonl``, runs the official
    ``swebench.harness.run_evaluation`` Docker verifier, and judges
    ``report.json`` for ``resolved``.
    """

    def __init__(self, model: str = "", agent_name: str = "asterwynd") -> None:
        self.model = model
        self.agent_name = agent_name

    def _prediction_model_name(self) -> str:
        if self.model:
            return f"{self.agent_name}:{self.model}"
        return self.agent_name

    def verify(
        self,
        loaded: LoadedTask,
        task_output,
        patch_text: str,
        log=None,
    ) -> Verdict:
        task = loaded.task

        predictions_path = task_output / "predictions.jsonl"
        model_name = self._prediction_model_name()
        prediction = {
            "instance_id": task.instance_id,
            "model_name_or_path": model_name,
            "model_patch": patch_text,
        }
        predictions_path.write_text(json.dumps(prediction) + "\n", errors="replace")

        run_id = f"asterwynd-{task.id}"
        command = [
            sys.executable,
            "-m",
            "swebench.harness.run_evaluation",
            "--dataset_name",
            task.dataset_name or "",
            "--split",
            task.dataset_split or "",
            "--instance_ids",
            task.instance_id or "",
            "--predictions_path",
            str(predictions_path),
            "--max_workers",
            "1",
            "--run_id",
            run_id,
            "--timeout",
            str(task.timeout_seconds),
        ]
        proc = subprocess.run(
            command,
            cwd=task_output,
            capture_output=True,
            text=True,
            timeout=max(task.timeout_seconds + 300, 600),
        )
        detail = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
        if proc.returncode != 0:
            return Verdict(
                status="error",
                reason=BenchmarkReason.DOCKER_RUNTIME_ERROR.value,
                detail=detail,
            )

        report_path = (
            task_output
            / "logs"
            / "run_evaluation"
            / run_id
            / model_name.replace("/", "__")
            / (task.instance_id or "")
            / "report.json"
        )
        if not report_path.exists():
            return Verdict(
                status="error",
                reason=BenchmarkReason.DOCKER_RUNTIME_ERROR.value,
                detail=f"Missing SWE-bench report: {report_path}",
            )

        report = json.loads(report_path.read_text())
        instance_report = report.get(task.instance_id or "", {})
        resolved = bool(instance_report.get("resolved"))
        partial = {
            key: instance_report[key]
            for key in ("f2p_rate", "p2p_rate", "reward")
            if key in instance_report
        }
        return Verdict(
            status="passed" if resolved else "failed",
            reason=None if resolved else BenchmarkReason.TEST_FAILURE.value,
            detail=detail,
            resolved=resolved,
            partial=partial or None,
        )


_REGISTRY: dict[str, type[VerifierAdapter]] = {}


def register_verifier(task_family: str, adapter_cls: type[VerifierAdapter]) -> None:
    """Register an adapter class under a ``task_family`` key."""
    _REGISTRY[task_family] = adapter_cls


def get_verifier(task_family: str, **kwargs: Any) -> VerifierAdapter | None:
    """Return an adapter instance for ``task_family``, or None if unknown."""
    adapter_cls = _REGISTRY.get(task_family)
    if adapter_cls is None:
        return None
    return adapter_cls(**kwargs)


register_verifier("swebench", SwebenchAdapter)
