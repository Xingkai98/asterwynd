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


#: Workflow 编排字段（change ``benchmark-workflow-replay``，D3）。两个 dataclass
#: 必须**成对**携带（grill Confirmed Decision 2）：一个是 ``AsterwyndRunner.run``
#: 的返回类型、一个是 ``runner.py`` 侧构造的落盘类型，中间没有别的通道。
#: 全部默认 ``None``——Fake/Shell/ClaudeCode 三个 runner 不建 manager，没有默认值
#: 会立刻构造失败。
WORKFLOW_FIELD_NAMES: tuple[str, ...] = (
    "workflow_mode",
    "workflow_spec_hash",
    "scheduler_version",
    "workflow_node_count",
    "workflow_run_count",
    "workflow_peak_active",
    "workflow_queue_wait_s",
    "workflow_critical_path_s",
    "workflow_cost_usd",
    # 编排质量指标与采集状态（C5 tasks 3.1-3.3 / 5.2）：同样成对、同样默认 None。
    "workflow_count",
    "workflow_steps",
    "workflow_spawn_count",
    "workflow_redundancy",
    "workflow_rejected_runs",
    "workflow_depth_capped_runs",
    "workflow_queue_cancelled_runs",
    "workflow_queue_full_runs",
    "workflow_collection_status",
    "workflow_envelope",
    # 端到端真实 LLM 验证的机器可读事实（grill Q7 落点 A）：降级时不得静默当已验证。
    "e2e_llm_verified",
    "e2e_verification_mode",
    "e2e_skip_reason",
    "e2e_assertions",
)


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
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    # Workflow orchestration fields (C5, D3). All optional.
    workflow_mode: str | None = None
    workflow_spec_hash: str | None = None
    scheduler_version: str | None = None
    workflow_node_count: int | None = None
    workflow_run_count: int | None = None
    workflow_peak_active: int | None = None
    workflow_queue_wait_s: float | None = None
    workflow_critical_path_s: float | None = None
    workflow_cost_usd: float | None = None
    workflow_count: int | None = None
    workflow_steps: int | None = None
    workflow_spawn_count: int | None = None
    workflow_redundancy: float | None = None
    workflow_rejected_runs: int | None = None
    workflow_depth_capped_runs: int | None = None
    workflow_queue_cancelled_runs: int | None = None
    workflow_queue_full_runs: int | None = None
    workflow_collection_status: str | None = None
    workflow_envelope: dict | None = None
    e2e_llm_verified: bool | None = None
    e2e_verification_mode: str | None = None
    e2e_skip_reason: str | None = None
    e2e_assertions: dict | None = None


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
    # Workflow orchestration fields (C5, D3) + e2e verification facts (D6/Q7).
    workflow_mode: str | None = None
    workflow_spec_hash: str | None = None
    scheduler_version: str | None = None
    workflow_node_count: int | None = None
    workflow_run_count: int | None = None
    workflow_peak_active: int | None = None
    workflow_queue_wait_s: float | None = None
    workflow_critical_path_s: float | None = None
    workflow_cost_usd: float | None = None
    workflow_count: int | None = None
    workflow_steps: int | None = None
    workflow_spawn_count: int | None = None
    workflow_redundancy: float | None = None
    workflow_rejected_runs: int | None = None
    workflow_depth_capped_runs: int | None = None
    workflow_queue_cancelled_runs: int | None = None
    workflow_queue_full_runs: int | None = None
    workflow_collection_status: str | None = None
    workflow_envelope: dict | None = None
    e2e_llm_verified: bool | None = None
    e2e_verification_mode: str | None = None
    e2e_skip_reason: str | None = None
    e2e_assertions: dict | None = None

    def apply_agent_run(self, run: "AgentRunResult") -> "TaskResult":
        """Carry an ``AgentRunResult``'s shared fields onto this result.

        ``runner.py`` rebuilds the ``TaskResult`` wholesale at several points
        (docker no-change early return, docker verifier branch, local
        test-command branch, dynamic-replay branch). Each rebuild only lists
        the fields it knows about, so the workflow fields would be silently
        dropped (grill Confirmed Decision 3). Every rebuild calls this.
        """
        self.iterations = run.iterations
        self.tool_calls = run.tool_calls
        self.edit_count = run.edit_count
        self.input_tokens = run.input_tokens
        self.output_tokens = run.output_tokens
        self.cache_read_tokens = run.cache_read_tokens
        self.cache_write_tokens = run.cache_write_tokens
        for name in WORKFLOW_FIELD_NAMES:
            setattr(self, name, getattr(run, name, None))
        return self

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
    # C3 protocol-reporting: model provider + budget-truncation flag.
    provider: str | None = None
    truncated: bool | None = None

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict) -> "RunMetadata":
        """Parse a ``run.json`` dict back into a RunMetadata.

        Unknown keys are ignored and missing fields fall back to defaults, so
        older or hand-crafted run artifacts stay compatible.
        """
        field_names = set(cls.__dataclass_fields__.keys())
        return cls(**{k: v for k, v in data.items() if k in field_names})

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
