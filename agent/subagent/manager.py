from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import deque
from contextlib import suppress
from contextvars import Context, copy_context
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable

from agent.message import Message, system_message, extract_text
from agent.result import RunResult, StopReason
from agent.run_config import AgentMode, AgentRunConfig, ModePolicy, parse_agent_mode
from agent.run_identity import new_run_id
from agent.tools.factory import build_default_tool_registry
from agent.workspace_policy import WorkspacePolicy
from agent.hooks.manager import HookManager
from agent.memory.manager import MemoryManager
from agent.hooks.builtin import TracingHook
from agent.trace_recorder import TraceRecorder
from agent.subagent.budget import BudgetExceededError, BudgetHook, BudgetTracker
from agent.subagent.context import (
    current_bus,
    current_graph_distance,
    current_node_id,
    current_run_id,
    current_spawn_depth,
    current_workflow_id,
    set_current_run_id,
    set_spawn_depth,
)
from agent.subagent.snapshot import SubagentSnapshotStore
from agent.subagent.workflow_store import WorkflowStore

if TYPE_CHECKING:
    from agent.config import AsterwyndConfig
    from agent.cost_tracker import CostLedger
    from agent.llm import LLM
    from agent.session import SessionSnapshot
    from agent.tools.sandbox import ExecutionBackend

logger = logging.getLogger("asterwynd.subagent")

#: 落盘 bounded summary 的字符预算。token 预算（四档）是**调度器**给节点 task 输入
#: 的口径；这里是 artifact 侧的摘要件，只保证「比全文短、够定位」。Q6：``run.summary``
#: 本身保留全文，裁剪只发生在落盘件与出口 projection。
BOUNDED_SUMMARY_CHARS = 2000


def _bounded_summary(text: str, max_tokens: int | None) -> str:
    """把全文裁成 bounded summary 落盘件（短文本 no-op，见 grill 风险「中」）。"""
    budget_chars = BOUNDED_SUMMARY_CHARS
    if max_tokens:
        budget_chars = max(budget_chars, max_tokens * 4)
    if len(text) <= budget_chars:
        return text
    return text[:budget_chars] + "\n…[truncated; full result in result_ref]"

# Run statuses that no longer change: a queued run cancelled before it ever
# executed must be skipped by the worker instead of being launched.
TERMINAL_RUN_STATUSES = frozenset(
    {"completed", "failed", "cancelled", "budget_exceeded"}
)


@dataclass
class SubagentArtifact:
    path: str
    kind: str = "file"


@dataclass
class SubagentRunUsage:
    total_tokens: int = 0
    tool_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class SubagentRunRecord:
    run_id: str
    task: str
    status: str
    summary: str = ""
    reason: str | None = None
    usage: SubagentRunUsage = field(default_factory=SubagentRunUsage)
    artifacts: list[SubagentArtifact] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    trace: dict | None = None
    # Per-run budget limits (issue 79, decision D3). Defaulted from config in
    # ``run_subagent`` unless overridden per run.
    max_tokens: int | None = None
    max_time_s: float | None = None
    # Explicit logical identity, fixed at spawn time (decision D6). A run that
    # waits in the queue past the end of its parent run still knows its
    # ``parent_run_id`` / ``depth`` / ``workflow_id`` from these fields.
    parent_run_id: str | None = None
    workflow_id: str | None = None
    node_id: str | None = None
    depth: int = 0
    # 成本归因四维的另两把键（change ``workflow-budget-attribution``，D3/Q8/Q13）：
    # ``edge`` = 实际触发本 run 的拓扑来源（调度器派发点算出后透传，见 Q8 规则）；
    # ``graph_distance`` = workflow 图距（0=leaf/1=shard/2=domain/3+=root），与
    # ``depth``（spawn 嵌套深度）是**两个独立字段**，图距绝不影响深度闸。
    edge: str | None = None
    graph_distance: int | None = None
    # Workflow result artifacts (change ``workflow-result-aggregation``, D1).
    # ``summary`` above stays the FULL text (Q6); these refs point at the
    # on-disk artifacts written when the run reaches a terminal state.
    result_ref: str | None = None
    summary_ref: str | None = None
    transcript_ref: str | None = None
    artifact_refs: list[str] = field(default_factory=list)
    # Internal: set by the time-budget monitor *before* it cancels so the
    # cancelled-task handler records ``budget_exceeded`` instead of ``cancelled``.
    _budget_kill_reason: str | None = field(default=None, repr=False)

    def to_result_dict(self) -> dict:
        """Parent/public run envelope（D7 的第三种表示，Q6）。

        ``summary`` 保留**全文**（Q6：改成裁剪版会经 ``state.summary`` 一路传导到
        下游）；父 agent / 普通工具消费的 bounded 版是独立的 ``bounded_summary``，
        与 ``summary_ref`` 落盘件同源。
        """
        return {
            "run_id": self.run_id,
            "status": self.status,
            "summary": self.summary,
            "bounded_summary": _bounded_summary(self.summary, self.max_tokens),
            "reason": self.reason,
            "max_tokens": self.max_tokens,
            "max_time_s": self.max_time_s,
            "usage": {
                "total_tokens": self.usage.total_tokens,
                "tool_calls": self.usage.tool_calls,
                "input_tokens": self.usage.input_tokens,
                "output_tokens": self.usage.output_tokens,
            },
            "artifacts": [
                {"path": artifact.path, "kind": artifact.kind}
                for artifact in self.artifacts
            ],
            "result_ref": self.result_ref,
            "summary_ref": self.summary_ref,
            "transcript_ref": self.transcript_ref,
            "artifact_refs": list(self.artifact_refs),
        }


@dataclass
class SubagentSessionRecord:
    subagent_id: str
    name: str
    description: str
    mode: AgentMode
    status: str
    created_at: float = field(default_factory=time.time)
    messages: list[Message] = field(default_factory=list)
    runs: list[SubagentRunRecord] = field(default_factory=list)
    active_run_id: str | None = None
    # Explicit parent/child identity, fixed at session creation (decision D6).
    parent_run_id: str | None = None
    workflow_id: str | None = None
    node_id: str | None = None
    depth: int = 0

    def to_summary_dict(self) -> dict:
        return {
            "subagent_id": self.subagent_id,
            "name": self.name,
            "mode": self.mode.value,
            "status": self.status,
            "created_at": self.created_at,
            "active_run_id": self.active_run_id,
            "run_count": len(self.runs),
            "parent_run_id": self.parent_run_id,
            "workflow_id": self.workflow_id,
            "node_id": self.node_id,
            "depth": self.depth,
        }


@dataclass
class _QueueItem:
    """A queued run plus the context captured at enqueue time.

    ``context`` is the enqueuing context (``copy_context()``), not the
    execution task's: the child loop must observe the spawning parent's
    ``spawn_depth`` and message bus even though the parent task's contextvars
    are already reset by the time the queue drains (grill decision 2 / risk
    "contextvars 丢失").
    """

    session: SubagentSessionRecord
    run: SubagentRunRecord
    context: Context
    resume_snapshot: "SessionSnapshot | None" = None


class _ExecutionPermits:
    """Bounded pool of execution permits (decision D1).

    A permit is held while a subagent loop actually runs LLM/tool calls. A run
    that blocks waiting on another run *suspends* its permit for the duration
    of the wait and resumes it afterwards, so a parent never occupies an
    execution slot while waiting on its children — without that, a saturated
    pool (``max_active=1``, or a hierarchical manager waiting on workers it
    itself saturated) would deadlock instead of just queueing.

    Bookkeeping is plain synchronous code, which under asyncio's cooperative
    scheduling is atomic; only ``resume`` awaits (for a slot to free up).
    """

    def __init__(self, limit: int):
        self._limit = limit
        self._in_use = 0
        self._holders: set[str] = set()
        self._suspended: set[str] = set()
        # Insertion-ordered: a resumer's position is its place in line.
        self._resuming: list[str] = []
        self._notices: deque[asyncio.Future[None]] = deque()

    @property
    def limit(self) -> int:
        return self._limit

    @property
    def in_use(self) -> int:
        return self._in_use

    @property
    def holders(self) -> frozenset[str]:
        return frozenset(self._holders)

    @property
    def available(self) -> int:
        """Slots the queue may fill.

        Runs that are resuming (a wait just ended) have priority over new
        queue starts, so their pending claim is subtracted here; otherwise the
        pump could starve a parent that already suspended its permit.
        """
        return self._limit - self._in_use - len(self._resuming)

    def try_acquire(self, run_id: str) -> bool:
        if self.available <= 0:
            return False
        self._in_use += 1
        self._holders.add(run_id)
        return True

    def suspend(self, run_id: str | None) -> bool:
        """Give up a permit for the duration of a wait (idempotent).

        Returns whether a permit was actually released, so the caller knows to
        resume afterwards.
        """
        if run_id is None or run_id not in self._holders:
            return False
        self._holders.discard(run_id)
        self._suspended.add(run_id)
        self._in_use -= 1
        self._wake()
        return True

    async def resume(self, run_id: str) -> None:
        """Take a permit back after a wait, waiting for a slot if needed.

        Resumers queue in arrival order: a run waits while the slots taken by
        executing runs plus the runs *ahead of it* in line fill the pool.
        """
        if run_id not in self._suspended:
            return
        self._suspended.discard(run_id)
        self._resuming.append(run_id)
        try:
            while self._in_use + self._resuming.index(run_id) >= self._limit:
                await self._wait_notice()
        finally:
            with suppress(ValueError):
                self._resuming.remove(run_id)
            # Later resumers' positions in line just improved.
            self._wake()
        self._in_use += 1
        self._holders.add(run_id)

    def release(self, run_id: str) -> None:
        if run_id in self._holders:
            self._holders.discard(run_id)
            self._in_use -= 1
        self._suspended.discard(run_id)
        self._wake()

    def _wake(self) -> None:
        """Wake every waiting resumer; each rechecks the slot count itself.

        Waking all (rather than one) keeps the pool free of per-waiter
        bookkeeping races: the herd is at most the number of active runs.
        """
        while self._notices:
            notice = self._notices.popleft()
            if not notice.done():
                notice.set_result(None)

    async def _wait_notice(self) -> None:
        notice: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self._notices.append(notice)
        try:
            await notice
        finally:
            with suppress(ValueError):
                self._notices.remove(notice)


# Spawn-class tools withdrawn from a child agent once its depth reaches
# ``max_depth`` (decision D4): the child does the work itself instead of
# hitting a RuntimeError that invites retrying under a different name.
# ``StartWorkflow``/``RunWorkflow`` joined the list in ``workflow-dsl-scheduler``
# (grill decision 6): they are spawn entry points that would otherwise let a
# depth-capped child raise a whole graph past the depth gate.
SPAWN_TOOL_NAMES = (
    "CreateSubagent",
    "RunSubagent",
    "RunPattern",
    "ResumeSubagent",
    "StartWorkflow",
    "RunWorkflow",
)


class SubAgentManager:
    def __init__(
        self,
        *,
        llm: "LLM | None" = None,
        config: "AsterwyndConfig | None" = None,
        workspace_policy: WorkspacePolicy | None = None,
        parent_mode: AgentMode = AgentMode.BUILD,
        parent_mode_provider: Callable[[], AgentMode] | None = None,
        cost_ledger: "CostLedger | None" = None,
        sandbox: "ExecutionBackend | None" = None,
        max_active: int | None = None,
        max_concurrent_runs: int | None = None,
        max_queued_runs: int | None = None,
        max_spawns: int | None = None,
        max_depth: int | None = None,
    ):
        self.llm = llm
        self.config = config
        self.workspace_policy = workspace_policy or WorkspacePolicy()
        self.parent_mode = parent_mode
        self.parent_mode_provider = parent_mode_provider
        self.cost_ledger = cost_ledger
        self.sandbox = sandbox
        self._sessions: dict[str, SubagentSessionRecord] = {}
        self._active_tasks: dict[str, asyncio.Task[None]] = {}
        self._run_waiters: dict[str, asyncio.Event] = {}
        self._pending: deque[_QueueItem] = deque()
        # Concurrency / nesting-depth / cumulative-spawn guardrails (decisions
        # D2/D5; reference: Codex max_threads queueing, Claude Code #68110 /
        # #69206 unbounded burn). ``max_concurrent_runs`` stays accepted as a
        # legacy alias for ``max_active``.
        guardrails = getattr(config, "subagents", None) if config is not None else None
        self.max_active = max_active if max_active is not None else (
            max_concurrent_runs
            if max_concurrent_runs is not None
            else getattr(guardrails, "max_active", 5)
        )
        self.max_queued_runs = (
            max_queued_runs
            if max_queued_runs is not None
            else getattr(guardrails, "max_queued_runs", 20)
        )
        self.max_spawns = (
            max_spawns
            if max_spawns is not None
            else getattr(guardrails, "max_spawns", 200)
        )
        self.max_depth = (
            max_depth
            if max_depth is not None
            else getattr(guardrails, "max_depth", 3)
        )
        self._permits = _ExecutionPermits(self.max_active)
        self._spawn_count = 0
        # Workflow identity (change ``workflow-dsl-scheduler``, D8/Q6): a workflow
        # run owns its own cumulative-spawn bucket, so a long-lived manager no
        # longer accumulates every spawn into one lifetime counter. Runs with no
        # workflow in context keep the C1 manager-lifetime semantics.
        self._workflow_spawn_counts: dict[str, int] = {}
        self._workflow_spawn_limits: dict[str, int] = {}
        # Guardrail rejection/degradation counters (change
        # ``benchmark-workflow-replay``, D4/Q3). Same bucketing as the spawn
        # counts: a workflow in context owns the entry, otherwise the counts
        # fall back to the manager lifetime. Instrumentation only — the
        # counters sit inside existing branches, they do not add execution
        # paths. Kinds: ``depth_capped`` (spawn tools withdrawn at max_depth)
        # and ``spawn_budget`` (``_check_spawn_budget`` rejected a spawn).
        self._workflow_rejection_counts: dict[str, dict[str, int]] = {}
        self._rejection_counts: dict[str, int] = {}
        # Workflow registry (grill Q1: manager-scoped, in-memory; persistence for
        # benchmark replay belongs to C5).
        self._workflows: dict[str, object] = {}
        self._snapshot_store_impl: SubagentSnapshotStore | None = None
        # Workflow result stores, keyed by workflow_id (change
        # ``workflow-result-aggregation``): results live in their own subtree,
        # never in the checkpoint namespace (grill decision 1).
        self._workflow_stores: dict[str, WorkflowStore] = {}

    @property
    def max_concurrent_runs(self) -> int:
        """Legacy alias for ``max_active`` (pre-queue attribute name)."""
        return self.max_active

    @property
    def _permit_holders(self) -> frozenset[str]:
        """Run ids currently holding an execution permit (introspection/tests)."""
        return self._permits.holders

    def configure_runtime(
        self,
        *,
        llm: "LLM | None" = None,
        config: "AsterwyndConfig | None" = None,
        workspace_policy: WorkspacePolicy | None = None,
        parent_mode_provider: Callable[[], AgentMode] | None = None,
    ) -> None:
        if llm is not None:
            self.llm = llm
        if config is not None:
            self.config = config
        if workspace_policy is not None:
            self.workspace_policy = workspace_policy
        if parent_mode_provider is not None:
            self.parent_mode_provider = parent_mode_provider

    def create_subagent(
        self,
        *,
        name: str,
        description: str = "",
        mode: str | AgentMode | None = None,
    ) -> dict:
        # Only the cumulative spawn budget rejects session creation: the depth
        # guard stays on the run paths (defensive fail-fast, decision D4 —
        # normally the spawn tools are already withdrawn at max depth), and
        # counting from creation is what stops 空建 session 刷爆 (decision Q5).
        self._check_spawn_budget()
        requested_mode = self._parent_mode() if mode is None else (
            mode if isinstance(mode, AgentMode) else parse_agent_mode(mode)
        )
        effective_mode = self._clamp_mode(requested_mode)
        subagent_id = uuid.uuid4().hex[:8]
        session = SubagentSessionRecord(
            subagent_id=subagent_id,
            name=name,
            description=description,
            mode=effective_mode,
            status="idle",
            messages=[system_message("你是一个受限的子 agent。按任务目标完成工作并汇报结果。")],
            parent_run_id=current_run_id(),
            workflow_id=current_workflow_id(),
            node_id=current_node_id(),
            depth=current_spawn_depth() + 1,
        )
        self._sessions[subagent_id] = session
        self._count_spawn()
        return session.to_summary_dict()

    def list_subagents(self) -> list[dict]:
        return [session.to_summary_dict() for session in self._sessions.values()]

    def get_subagent(self, subagent_id: str) -> dict | None:
        session = self._sessions.get(subagent_id)
        if session is None:
            return None
        data = session.to_summary_dict()
        data["description"] = session.description
        return data

    def find_run(self, subagent_id: str, run_id: str) -> SubagentRunRecord | None:
        """Look up a run record without raising (used for live status polling)."""
        session = self._sessions.get(subagent_id)
        if session is None:
            return None
        for run in session.runs:
            if run.run_id == run_id:
                return run
        return None

    def active_run(self, subagent_id: str) -> SubagentRunRecord | None:
        """该 session 当前 active 的 run 记录（无则 None）。"""
        session = self._sessions.get(subagent_id)
        if session is None or session.active_run_id is None:
            return None
        return self.find_run(subagent_id, session.active_run_id)

    def attribution_for(self, subagent_id: str) -> dict | None:
        """loop 层 cost 记账的归因键（grill 决策 4：一次查表）。

        ``session_id`` 传的就是 ``session.subagent_id``，而 ``SubagentSessionRecord``
        自带 ``workflow_id``/``node_id``；图距与 edge 是**run 级**事实，从当前活跃 run
        读（``current_run_id()`` 在 run 执行上下文里可用，取的是本 run 的记录）。

        不是 workflow 内的调用（根 loop / 普通 spawn）返回 ``None``——归因键全缺省时
        ``CostLedger.record`` 的三维账单行为与改造前逐字节一致。
        """
        session = self._sessions.get(subagent_id)
        if session is None or session.workflow_id is None:
            return None
        run = self.active_run(subagent_id)
        if run is None:
            run_id = current_run_id()
            run = self.find_run(subagent_id, run_id) if run_id else None
        return {
            "workflow_id": session.workflow_id,
            "node_id": session.node_id,
            "graph_distance": getattr(run, "graph_distance", None),
            "edge": getattr(run, "edge", None),
        }

    def record_workflow_llm_usage(
        self,
        *,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
    ) -> None:
        """把一次 LLM 调用累加进当前 workflow 的四维度预算账本（Q6 方案 B）。

        根 loop（``current_workflow_id()`` 为 None）不记——workflow 预算只对 workflow
        run 生效。workflow 身份经 ``copy_context()`` 随入队快照固定，执行期读取正确。
        """
        workflow_id = current_workflow_id()
        if workflow_id is None:
            return
        scheduler = self._workflows.get(workflow_id)
        record = getattr(scheduler, "record_llm_usage", None)
        if record is None:
            return
        record(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_write_tokens=cache_write_tokens,
        )

    # -- workflow registry / spawn buckets (change workflow-dsl-scheduler) ---

    def register_workflow(self, scheduler: object) -> None:
        self._workflows[getattr(scheduler, "workflow_id")] = scheduler

    def get_workflow(self, workflow_id: str) -> object | None:
        return self._workflows.get(workflow_id)

    def list_workflows(self) -> list[str]:
        return list(self._workflows)

    def register_workflow_bucket(self, workflow_id: str, limit: int) -> None:
        """Open the cumulative-spawn bucket owned by one workflow run (Q6).

        ``limit`` is calibrated by the scheduler to ``max_runs * 2`` so the
        spawn bucket (1 create + 1 run per subagent run) can never fire before
        the workflow's own run gate — otherwise a graph could die of
        "spawn budget exceeded" while still inside its declared run budget.
        """
        self._workflow_spawn_counts[workflow_id] = 0
        self._workflow_spawn_limits[workflow_id] = limit

    def release_workflow_bucket(self, workflow_id: str) -> None:
        self._workflow_spawn_counts.pop(workflow_id, None)
        self._workflow_spawn_limits.pop(workflow_id, None)
        # Rejection counts are snapshotted into the envelope before this runs
        # (same reason as the spawn counts — the bucket is gone afterwards).
        self._workflow_rejection_counts.pop(workflow_id, None)

    def spawn_count(self) -> int:
        """Spawns charged in the current context's bucket (introspection/tests)."""
        workflow_id = current_workflow_id()
        if workflow_id is None:
            return self._spawn_count
        return self._workflow_spawn_counts.get(workflow_id, 0)

    def spawn_count_for(self, workflow_id: str) -> int:
        """Spawns charged to an explicit workflow bucket (no ambient context).

        The benchmark collector reads this *inside* ``scheduler.run()``, before
        the bucket is released — afterwards ``spawn_count()`` would fall back to
        the manager-lifetime counter, a different quantity entirely.
        """
        return self._workflow_spawn_counts.get(workflow_id, 0)

    def _count_rejection(self, kind: str) -> None:
        """Record one guardrail rejection/degradation (change C5, D4/Q3).

        Mirrors :meth:`_count_spawn`'s bucketing so a per-workflow figure exists
        without a new execution path: the increment sits inside the branch that
        already decided to reject or withdraw.
        """
        workflow_id = current_workflow_id()
        if workflow_id is None:
            self._rejection_counts[kind] = self._rejection_counts.get(kind, 0) + 1
            return
        bucket = self._workflow_rejection_counts.setdefault(workflow_id, {})
        bucket[kind] = bucket.get(kind, 0) + 1

    def rejection_counts_for(self, workflow_id: str) -> dict[str, int]:
        """Per-workflow rejection counts, keyed by kind (``depth_capped`` etc.)."""
        return dict(self._workflow_rejection_counts.get(workflow_id, {}))

    async def run_subagent(
        self,
        *,
        subagent_id: str,
        task: str,
        wait: bool = False,
        timeout_s: float | None = None,
        max_tokens: int | None = None,
        max_time_s: float | None = None,
        edge: str | None = None,
    ) -> dict:
        session = self._require_session(subagent_id)
        # 准入层（仍 fail-fast）：同 session 已有 active run → 拒绝并等待或取消
        # 当前 run；不进入跨 session 队列（spec delta MODIFIED requirement）。
        if session.active_run_id is not None:
            raise RuntimeError(f"subagent {subagent_id} already has an active run")
        self._check_admission()

        budget_defaults = getattr(self.config, "subagents", None) if self.config else None
        run = self._new_run(
            session,
            task,
            max_tokens=(
                max_tokens
                if max_tokens is not None
                else getattr(budget_defaults, "default_max_tokens", None)
            ),
            max_time_s=(
                max_time_s
                if max_time_s is not None
                else getattr(budget_defaults, "default_max_time_s", None)
            ),
            edge=edge,
        )
        await self._enqueue_run(session, run, wait=wait, timeout_s=timeout_s)
        return self._format_run_envelope(session.subagent_id, run)

    async def resume_subagent(
        self,
        *,
        subagent_id: str,
        task: str,
        run_id: str,
        wait: bool = False,
        timeout_s: float | None = None,
        max_tokens: int | None = None,
        max_time_s: float | None = None,
    ) -> dict:
        """Resume a previously interrupted run from its checkpoint.

        The snapshot is loaded and passed to ``AgentLoop.run(resume_snapshot=...)``
        which rebuilds the transcript and appends a continue marker. The in-flight
        tool call (if any) is retried by the model — resume is transcript-level,
        not stack-level (issue 79, decision D2).
        """
        session = self._require_session(subagent_id)
        if session.active_run_id is not None:
            raise RuntimeError(f"subagent {subagent_id} already has an active run")
        # 累计 spawn 预算最后检查（在快照检查之后，见 Q5 计数语义）。
        snapshot = self._snapshot_store().load(run_id)
        if snapshot is None:
            raise KeyError(f"no checkpoint found for run {run_id}")
        self._check_admission()

        budget_defaults = getattr(self.config, "subagents", None) if self.config else None
        run = self._new_run(
            session,
            task,
            max_tokens=(
                max_tokens
                if max_tokens is not None
                else getattr(budget_defaults, "default_max_tokens", None)
            ),
            max_time_s=(
                max_time_s
                if max_time_s is not None
                else getattr(budget_defaults, "default_max_time_s", None)
            ),
        )
        # Reset the session transcript to system + the continue prompt; the
        # loop's resume path folds the snapshot history back in from the
        # checkpoint and the run worker appends the continue task.
        session.messages = [
            system_message("你是一个受限的子 agent。按任务目标完成工作并汇报结果。")
        ]
        await self._enqueue_run(
            session,
            run,
            wait=wait,
            timeout_s=timeout_s,
            resume_snapshot=snapshot,
        )
        return self._format_run_envelope(session.subagent_id, run)

    def _new_run(
        self,
        session: SubagentSessionRecord,
        task: str,
        *,
        max_tokens: int | None,
        max_time_s: float | None,
        edge: str | None = None,
    ) -> SubagentRunRecord:
        """Create and register a new run record for a session.

        The run starts in ``queued``; ``started_at`` is assigned when the
        queue worker actually begins executing it (decision Q3: queue time is
        not billed against the time budget). ``depth`` and ``parent_run_id``
        are fixed here — at spawn time, in the *spawning* context — so the
        delayed execution of a queued run still knows its logical nesting
        (decision D6).
        """
        run_id = new_run_id()
        run = SubagentRunRecord(
            run_id=run_id,
            task=task,
            status="queued",
            max_tokens=max_tokens,
            max_time_s=max_time_s,
            parent_run_id=current_run_id(),
            workflow_id=current_workflow_id(),
            node_id=current_node_id(),
            depth=current_spawn_depth() + 1,
            # 图距从 contextvar 读（Q13 路径 X）；``edge`` 从调度器派发点透传
            # （决策 6：``_new_run`` 时没有「上游节点」contextvar，推不出来）。
            graph_distance=current_graph_distance(),
            edge=edge,
        )
        session.runs.append(run)
        return run

    async def _enqueue_run(
        self,
        session: SubagentSessionRecord,
        run: SubagentRunRecord,
        *,
        wait: bool = False,
        timeout_s: float | None = None,
        resume_snapshot: "SessionSnapshot | None" = None,
    ) -> None:
        """Queue a run for execution, optionally blocking until it terminates.

        ``session.active_run_id`` is claimed here — at enqueue, not at
        execution — so a session cannot be queued twice while it waits (grill
        decision 4). When an execution slot is free the run starts immediately
        and ``run.status`` is ``running`` on return; otherwise it stays
        ``queued`` until a slot frees up. The spawning context is captured at
        enqueue time so a delayed run still sees the parent's ``spawn_depth``
        and message bus (grill decision 2).
        """
        session.active_run_id = run.run_id
        session.status = "running"
        session.messages.append(Message(role="user", content=run.task))
        waiter = asyncio.Event()
        self._run_waiters[run.run_id] = waiter

        self._pending.append(
            _QueueItem(
                session=session,
                run=run,
                context=copy_context(),
                resume_snapshot=resume_snapshot,
            )
        )
        self._pump_queue()
        if self._take_back_if_queue_full(session, run):
            return
        # 计数在真正接单之后：被 queue_full 拒绝的 spawn 不消耗预算。
        self._count_spawn()
        if wait:
            await self._wait_for_run(waiter, timeout_s)

    async def _wait_for_run(
        self,
        waiter: asyncio.Event,
        timeout_s: float | None,
    ) -> None:
        """Block until a run terminates, releasing the waiter's own permit.

        Decision D1 applied to the waiting window itself: the run that is
        blocked here (identified by ``current_run_id``) hands its execution
        permit back for the duration of the wait and reacquires it afterwards,
        so a parent waiting on children it saturated cannot self-starve.
        """
        waiting_run_id = current_run_id()
        suspended = self._permits.suspend(waiting_run_id)
        if suspended:
            # The freed slot is exactly what a queued run was waiting for.
            self._pump_queue()
        try:
            await asyncio.wait_for(waiter.wait(), timeout=timeout_s)
        finally:
            if suspended:
                await self._permits.resume(waiting_run_id)
        if waiter.is_set():
            # 被等的 run 可能刚被惰性跳过（取消/预算），或从未真正入队：
            # 只泵一次，把该 run 从队列中清掉并让出槽位（wait=false 路径的泵
            # 覆盖不到 queue_full 未触发的情形）。
            self._pump_queue()

    def _pump_queue(self) -> None:
        """Start queued runs while execution permits are available.

        Called on every enqueue and on every permit release; both are the only
        state transitions that can unblock the queue, so no background worker
        (and no lost-wakeup race) is needed. Cancelled queued runs are skipped
        lazily here — they keep their queue slot (decision Q7: conservative
        bound) but never execute.
        """
        while self._pending:
            item = self._pending[0]
            if item.run.status in TERMINAL_RUN_STATUSES:
                self._pending.popleft()
                self._cleanup_queued_item(item)
                continue
            if not self._permits.try_acquire(item.run.run_id):
                return
            self._pending.popleft()
            self._start_task(item)

    def _start_task(self, item: _QueueItem) -> None:
        """Mark a run as executing and spawn its task in the captured context.

        The permit was reserved by ``_pump_queue`` immediately before, and the
        run is published to ``_active_tasks`` synchronously, so a cancellation
        always sees a consistent state. ``run.status`` flips to ``running``
        here (not inside the task) so ``run_subagent(wait=false)`` returns
        ``running`` whenever a slot was free at spawn time (decision Q8).

        Permit release (plus waiter wake-up and the queue pump) is bound to the
        *task* via this done-callback, not only to the coroutine body: a task
        cancelled before its first step never enters ``_execute_run``, so its
        ``finally`` never runs. ``release`` is idempotent, so the normal path —
        where ``_execute_run``'s ``finally`` already released — stays a no-op.
        """
        run = item.run
        run.status = "running"
        run.started_at = time.time()
        bg_task = asyncio.create_task(
            self._execute_run_in_context(item), context=item.context
        )
        self._active_tasks[run.run_id] = bg_task
        bg_task.add_done_callback(lambda _: self._on_run_task_done(run.run_id))
        if run.max_time_s is not None:
            # The time budget starts counting at execution, not at enqueue
            # (decision Q3): while queued the run burns no budget. The monitor
            # runs in the run's captured context so its checkpoint can still
            # see the orchestration bus.
            asyncio.create_task(
                self._monitor_run_timeout(item.session, run), context=item.context
            )

    def _on_run_task_done(self, run_id: str) -> None:
        """Task-lifetime teardown for a run (idempotent with ``_execute_run``).

        Runs for every terminal state of the task — including tasks cancelled
        before their first step, where the coroutine body (and its ``finally``)
        never executed. Releasing a permit already released by ``_execute_run``
        is a no-op, so both paths are safe.
        """
        self._active_tasks.pop(run_id, None)
        self._permits.release(run_id)
        waiter = self._run_waiters.pop(run_id, None)
        if waiter is not None:
            waiter.set()
        self._pump_queue()

    async def _execute_run_in_context(self, item: _QueueItem) -> None:
        """Execute a run inside the context captured when it was enqueued.

        The spawning context is replayed as the execution context, then the
        run's explicit ``depth`` and run id are installed (decision D6) so
        nested spawns and the depth-based tool gate read the run's own values
        instead of a possibly-stale contextvar.

        No tokens are reset: the task owns a private copy of the captured
        context, so the values die with the task — and a reset in ``finally``
        would itself raise when the task is torn down outside its context
        (``GeneratorExit`` during ``Task.__del__``).
        """
        set_spawn_depth(item.run.depth)
        set_current_run_id(item.run.run_id)
        await self._execute_run(item.session, item.run, item.resume_snapshot)

    def _take_back_if_queue_full(
        self,
        session: SubagentSessionRecord,
        run: SubagentRunRecord,
    ) -> bool:
        """Queue overflow (Q1): drop the pending run and report ``queue_full``.

        Checked *after* the pump, so a spawn that started executing (or was
        skipped as cancelled) is never turned into ``queue_full``. A dropped
        run leaves no record — matching the old fail-fast guard — so the
        session is immediately re-runnable.
        """
        if run.status in TERMINAL_RUN_STATUSES:
            return True
        if len(self._pending) <= self.max_queued_runs:
            return False
        for item in list(self._pending):
            if item.run is run:
                self._pending.remove(item)
                break
        run.status = "queue_full"
        run.reason = (
            f"subagent queue is full ({self.max_queued_runs}/{self.max_queued_runs}); "
            "wait for queued runs to finish (GetSubagentRun with wait=true) "
            "before spawning more"
        )
        if session.runs and session.runs[-1] is run:
            session.runs.pop()
        session.active_run_id = None
        session.status = "idle"
        if (
            session.messages
            and session.messages[-1].role == "user"
            and session.messages[-1].content == run.task
        ):
            session.messages.pop()
        waiter = self._run_waiters.pop(run.run_id, None)
        if waiter is not None:
            waiter.set()
        return True

    def _cleanup_queued_item(self, item: _QueueItem) -> None:
        """Release a skipped queue item's bookkeeping (waiter already set)."""
        waiter = self._run_waiters.pop(item.run.run_id, None)
        if waiter is not None:
            waiter.set()

    async def get_subagent_run(
        self,
        *,
        subagent_id: str,
        run_id: str | None = None,
        wait: bool = False,
        timeout_s: float | None = None,
    ) -> dict:
        session = self._require_session(subagent_id)
        run = self._find_run(session, run_id)
        if wait and run.status not in TERMINAL_RUN_STATUSES:
            # .get() + 状态复查：waiter 可能已被 _execute_run 的 finally pop 掉
            # （grill 风险：下标访问会 KeyError）。
            waiter = self._run_waiters.get(run.run_id)
            if waiter is not None:
                await self._wait_for_run(waiter, timeout_s)
        return self._format_run_envelope(session.subagent_id, run)

    async def cancel_subagent_run(
        self,
        *,
        subagent_id: str,
        run_id: str | None = None,
    ) -> dict:
        session = self._require_session(subagent_id)
        run = self._find_run(session, run_id)
        if run.status in TERMINAL_RUN_STATUSES:
            return self._format_run_envelope(session.subagent_id, run)
        if run.status == "queued":
            # Q7：排队 run 不在 _active_tasks，惰性取消——标记终态 + 唤醒 waiter；
            # 该 run 仍占队列名额，worker 出队时跳过。
            self._mark_cancelled(session, run, TraceRecorder(task_id=session.subagent_id))
            waiter = self._run_waiters.pop(run.run_id, None)
            if waiter is not None:
                waiter.set()
            return self._format_run_envelope(session.subagent_id, run)
        task = self._active_tasks.get(run.run_id)
        if task is None or task.done():
            return self._format_run_envelope(session.subagent_id, run)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        if run.status == "running":
            self._mark_cancelled(session, run, TraceRecorder(task_id=session.subagent_id))
            waiter = self._run_waiters.pop(run.run_id, None)
            if waiter is not None:
                waiter.set()
        return self._format_run_envelope(session.subagent_id, run)

    def inspect_transcript(
        self,
        *,
        subagent_id: str,
        scope: str = "summary",
        run_id: str | None = None,
        limit: int = 5,
        include_tool_results: bool = False,
    ) -> dict:
        session = self._require_session(subagent_id)
        if scope == "summary":
            latest_run = session.runs[-1] if session.runs else None
            # ``summary`` is empty for a run that has not produced output yet;
            # the run status tells the caller whether that means "still queued"
            # or "already terminal without output" (queueing makes the queued
            # window a common state, so the two must be distinguishable).
            return {
                "subagent_id": subagent_id,
                "run_id": run_id,
                "scope": "summary",
                "status": latest_run.status if latest_run is not None else None,
                "summary": latest_run.summary if latest_run is not None else "",
                "truncated": False,
                "included_tool_results": include_tool_results,
            }

        messages = session.messages
        if not include_tool_results:
            messages = [msg for msg in messages if msg.role != "tool"]
        tail = messages[-limit:]
        return {
            "subagent_id": subagent_id,
            "run_id": run_id,
            "scope": "recent_messages",
            "messages": [
                {"role": msg.role, "content": extract_text(msg.content), "tool_call_id": msg.tool_call_id}
                for msg in tail
            ],
            "truncated": len(messages) > limit,
            "included_tool_results": include_tool_results,
        }

    async def _execute_run(
        self,
        session: SubagentSessionRecord,
        run: SubagentRunRecord,
        resume_snapshot: "SessionSnapshot | None" = None,
    ) -> None:
        trace = TraceRecorder(task_id=session.subagent_id)
        try:
            # The execution permit covers exactly this loop run (decision D1).
            # It is released in the ``finally`` below, the only block every
            # cancel/timeout path is guaranteed to execute — releasing it at
            # the call site would leak a slot whenever the task is cancelled.
            # The slot was reserved synchronously by the queue pump before this
            # task was created; the release is idempotent either way.
            await self._run_loop(session, run, trace, resume_snapshot)
        finally:
            self._permits.release(run.run_id)
            waiter = self._run_waiters.pop(run.run_id, None)
            if waiter is not None:
                waiter.set()
            # A permit just freed up: start the next queued run.
            self._pump_queue()

    async def _run_loop(
        self,
        session: SubagentSessionRecord,
        run: SubagentRunRecord,
        trace: TraceRecorder,
        resume_snapshot: "SessionSnapshot | None",
    ) -> None:
        tracker = BudgetTracker(
            max_tokens=run.max_tokens,
            max_time_s=run.max_time_s,
            started_at=run.started_at,
        )
        try:
            if self.llm is None:
                raise RuntimeError("subagent manager LLM is not configured")
            loop = self._build_subagent_loop(session.mode, budget=tracker, depth=run.depth)
            result = await loop.run(
                session.messages,
                trace_recorder=trace,
                session_id=session.subagent_id,
                run_id=run.run_id,
                resume_snapshot=resume_snapshot,
            )
            self._complete_run(session, run, result, trace)
        except BudgetExceededError as exc:
            self._write_checkpoint(session, run)
            self._mark_budget_exceeded(
                session,
                run,
                exc.dimension,
                trace,
                tokens=tracker.tokens,
                input_tokens=tracker.input_tokens,
                output_tokens=tracker.output_tokens,
            )
        except asyncio.CancelledError:
            self._write_checkpoint(session, run)
            if run._budget_kill_reason is not None:
                self._mark_budget_exceeded(
                    session,
                    run,
                    run._budget_kill_reason,
                    trace,
                    tokens=tracker.tokens,
                    input_tokens=tracker.input_tokens,
                    output_tokens=tracker.output_tokens,
                )
            else:
                self._mark_cancelled(session, run, trace)
            raise
        except Exception as exc:
            self._write_checkpoint(session, run)
            self._mark_failed(session, run, str(exc), trace)

    def _resolve_sandbox(self) -> "ExecutionBackend | None":
        """Return the sandbox for sub-agent registries.

        Prefers an explicitly-provided sandbox; otherwise self-heals from
        ``config.sandbox`` (cached) so every construction site — CLI, web, or
        benchmark — runs sub-agents in the same sandbox as the parent.
        """
        if self.sandbox is not None:
            return self.sandbox
        config = self.config
        if config is None:
            return None
        from agent.tools.sandbox import build_execution_backend

        self.sandbox = build_execution_backend(
            config.sandbox.backend,
            image=config.sandbox.image,
            memory_mb=config.sandbox.memory_mb,
            cpus=config.sandbox.cpus,
            timeout=config.sandbox.timeout_seconds,
        )
        return self.sandbox

    def _build_subagent_loop(
        self,
        mode: AgentMode,
        budget: BudgetTracker | None = None,
        depth: int | None = None,
    ) -> AgentLoop:
        from agent.loop import AgentLoop

        config = self.config
        registry = build_default_tool_registry(
            policy=self.workspace_policy,
            mode_policy=ModePolicy(
                AgentRunConfig(mode=mode),
                deny_tools_by_mode=config.deny_tools_by_mode() if config else None,
                permission_profiles_by_mode=(
                    config.permission_profiles_by_mode() if config else None
                ),
            ),
            ignore_patterns=config.tools.ignore_patterns if config else (),
            code_intelligence_config=config.tools.code_intelligence if config else None,
            browser_config=config.tools.browser if config else None,
            web_search_config=config.tools.web_search if config else None,
            sandbox=self._resolve_sandbox(),
        )
        hooks = HookManager([TracingHook()])
        if budget is not None:
            hooks.hooks.append(BudgetHook(budget))
        # Depth gate (decision D4): at ``max_depth`` the child keeps the
        # read/cancel/bus tools but loses the four spawn-class tools. The gate
        # reads the run's *explicit* depth (``depth=None`` keeps the historical
        # behavior of exposing everything), never the ambient contextvar — a
        # delayed queue run cannot rely on it.
        if depth is not None and depth >= self.max_depth:
            hidden_tools = SPAWN_TOOL_NAMES
            # Instrumentation (C5 Q3): one count per *construction*, so
            # ``depth_capped_runs`` means "runs whose capability was degraded",
            # not "times the model hit the guardrail". ``depth is None`` keeps
            # the historical un-gated behaviour and is deliberately not counted.
            self._count_rejection("depth_capped")
        else:
            hidden_tools = ()
        return AgentLoop(
            llm=self.llm,
            tool_registry=registry,
            hooks=hooks,
            memory=MemoryManager(max_tokens=80_000),
            run_config=AgentRunConfig(mode=mode),
            subagent_manager=self,
            expose_subagent_tools=True,
            unregistered_subagent_tools=hidden_tools,
            tool_result_display=config.tools.display if config else None,
            cost_ledger=self.cost_ledger,
            ledger_tool_name="subagent",
        )

    def _complete_run(
        self,
        session: SubagentSessionRecord,
        run: SubagentRunRecord,
        result: RunResult,
        trace: TraceRecorder,
    ) -> None:
        run.status = "completed" if result.stop_reason is not StopReason.ERROR else "failed"
        run.summary = result.content
        run.reason = result.error
        run.usage = SubagentRunUsage(
            total_tokens=result.total_tokens,
            tool_calls=len(result.tool_calls_made),
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
        )
        run.finished_at = time.time()
        run.trace = trace.to_dict()
        session.active_run_id = None
        session.status = "idle"
        self._write_result_artifacts(session, run)

    def _write_result_artifacts(
        self,
        session: SubagentSessionRecord,
        run: SubagentRunRecord,
    ) -> None:
        """落盘一个成功 workflow run 的完整结果（D1，grill 决策 2/3）。

        这是**新增写点**：``_write_checkpoint`` 只在异常/取消分支调用，正常收尾
        走 ``_complete_run``，它今天只把 ``result.content`` 写进 ``run.summary``。
        没有这一步，spec delta 的「完整结果落盘、内存只持摘要」在成功路径下不成立。

        内存里仍只持 bounded summary + ref：``run.summary`` 保留全文（Q6），
        落盘的 ``summary_ref`` 是裁剪件，下游消费它而不是全文。

        workflow store 不可用（无 workflow 身份 / 落盘失败）时保持 refs 为空——
        落盘是**尽力而为的可观测性**，不能让它把一次成功的 run 变成失败。
        """
        workflow_id = run.workflow_id
        if not workflow_id:
            return
        try:
            store = self._workflow_store(workflow_id)
            refs: list[str] = []
            result_ref = store.save_result(run.run_id, run.summary)
            refs.append(result_ref)
            transcript_ref = store.save_transcript(
                run.run_id, [message.to_dict() for message in session.messages]
            )
            refs.append(transcript_ref)
            summary_ref = store.save_summary(
                run.run_id, _bounded_summary(run.summary, run.max_tokens)
            )
            refs.append(summary_ref)
            run.result_ref = result_ref
            run.transcript_ref = transcript_ref
            run.summary_ref = summary_ref
            run.artifact_refs = refs
        except Exception:
            logger.warning(
                "Failed to persist workflow result artifacts run_id=%s", run.run_id,
                exc_info=True,
            )

    def _workflow_store(self, workflow_id: str) -> WorkflowStore:
        """本 workflow run 的结果 store（独立 subtree，grill 决策 1）。"""
        store = self._workflow_stores.get(workflow_id)
        if store is None:
            store = WorkflowStore.for_workspace(
                self.workspace_policy.workspace_root, workflow_id
            )
            self._workflow_stores[workflow_id] = store
        return store

    def workflow_store(self, workflow_id: str) -> WorkflowStore:
        """公开只读入口：``ReadWorkflowResult`` 工具与 scheduler 事件日志共用。"""
        return self._workflow_store(workflow_id)

    def _mark_failed(
        self,
        session: SubagentSessionRecord,
        run: SubagentRunRecord,
        reason: str,
        trace: TraceRecorder,
    ) -> None:
        run.status = "failed"
        run.reason = reason
        run.finished_at = time.time()
        run.trace = trace.to_dict()
        session.active_run_id = None
        session.status = "idle"

    def _mark_cancelled(
        self,
        session: SubagentSessionRecord,
        run: SubagentRunRecord,
        trace: TraceRecorder,
    ) -> None:
        if run.status in TERMINAL_RUN_STATUSES:
            return  # already terminal
        run.status = "cancelled"
        run.reason = "cancelled"
        run.finished_at = time.time()
        run.trace = trace.to_dict()
        session.active_run_id = None
        session.status = "idle"

    def _mark_budget_exceeded(
        self,
        session: SubagentSessionRecord,
        run: SubagentRunRecord,
        dimension: str,
        trace: TraceRecorder | None,
        tokens: int | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
    ) -> None:
        if run.status in TERMINAL_RUN_STATUSES:
            return  # already terminal
        run.status = "budget_exceeded"
        run.reason = f"budget exceeded ({dimension})"
        run.finished_at = time.time()
        run.trace = trace.to_dict() if trace is not None else None
        # Backfill cost summary (review M1): the run consumed real tokens even
        # though it never reached a normal completion, so the failure/cost
        # summary must reflect them for benchmark cost attribution.
        #
        # C4 task 2.4：过去这里把 input/output 直接写 0，`CostLedger` 按 run.usage
        # 报的 cost 因此系统性偏低、与 workflow 账本打架（Q12）。现在补填 tracker
        # 实际累计的分量；调用方拿不到分量时退化为「全部记在 input」并**保留
        # total**——宁可粗粒度，也不能报 0。
        if tokens:
            if input_tokens is None and output_tokens is None:
                # 调用方拿不到分量：退化为「全部记在 input」并保留 total——
                # 宁可粗粒度，也不能报 0。
                resolved_input, resolved_output = tokens, 0
            else:
                resolved_input = input_tokens or 0
                resolved_output = output_tokens or 0
            run.usage = SubagentRunUsage(
                total_tokens=tokens,
                input_tokens=resolved_input,
                output_tokens=resolved_output,
            )
        session.active_run_id = None
        session.status = "idle"

    def _snapshot_store(self) -> SubagentSnapshotStore:
        if self._snapshot_store_impl is None:
            self._snapshot_store_impl = SubagentSnapshotStore.for_workspace(
                self.workspace_policy.workspace_root
            )
        return self._snapshot_store_impl

    def _write_checkpoint(
        self,
        session: SubagentSessionRecord,
        run: SubagentRunRecord,
    ) -> None:
        """Snapshot the run before an interrupt/kill so it can be resumed.

        A compact view of the active orchestration bus (if any) is folded into
        the snapshot so a resumed run can still see what was exchanged even
        though the in-memory bus does not survive the run (design D5).
        """
        try:
            store = self._snapshot_store()
            bus_summary = ""
            bus = current_bus()
            if bus is not None:
                bus_summary = bus.compact_summary()
            store.save(store.snapshot_for_run(session, run, bus_summary))
        except Exception:
            logger.warning(
                "Failed to write subagent checkpoint run_id=%s", run.run_id,
                exc_info=True,
            )

    async def _monitor_run_timeout(
        self,
        session: SubagentSessionRecord,
        run: SubagentRunRecord,
    ) -> None:
        """Time-budget kill path: cancel a run stuck past ``max_time_s``.

        Started only when the run *begins executing* (decision Q3: queue time
        is not billed), so ``started_at`` is always set here. The monitor marks
        ``_budget_kill_reason`` and snapshots *before* cancelling so the
        cancelled-task handler records ``budget_exceeded`` (and the checkpoint
        is resumable) rather than a plain ``cancelled``. Should the monitor
        still find the run queued (a slot freed but the task not yet
        scheduled), the kill applies to the queued run: it is marked terminal
        and skipped lazily by the queue pump.
        """
        await asyncio.sleep(run.max_time_s)
        task = self._active_tasks.get(run.run_id)
        if task is None:
            # No task: either the run already terminated, or (defensively) it is
            # still queued — the latter is marked terminal directly, with no
            # task to cancel; the queue pump skips it lazily.
            if run.status == "queued":
                self._write_checkpoint(session, run)
                self._mark_budget_exceeded(session, run, "time", None)
                waiter = self._run_waiters.pop(run.run_id, None)
                if waiter is not None:
                    waiter.set()
            return
        if task.done():
            return
        run._budget_kill_reason = "time"
        self._write_checkpoint(session, run)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    def _format_run_envelope(
        self,
        subagent_id: str,
        run: SubagentRunRecord,
    ) -> dict:
        payload = {"subagent_id": subagent_id}
        payload.update(run.to_result_dict())
        return payload

    def _require_session(self, subagent_id: str) -> SubagentSessionRecord:
        session = self._sessions.get(subagent_id)
        if session is None:
            raise KeyError(f"unknown subagent_id: {subagent_id}")
        return session

    def _find_run(
        self,
        session: SubagentSessionRecord,
        run_id: str | None,
    ) -> SubagentRunRecord:
        if run_id is None:
            if not session.runs:
                raise KeyError(f"subagent {session.subagent_id} has no runs")
            return session.runs[-1]
        for run in session.runs:
            if run.run_id == run_id:
                return run
        raise KeyError(f"unknown run_id: {run_id}")

    def _clamp_mode(self, requested: AgentMode) -> AgentMode:
        parent_mode = self._parent_mode()
        order = {
            AgentMode.READ_ONLY: 0,
            AgentMode.PLAN: 0,
            AgentMode.BUILD: 1,
            AgentMode.BYPASS: 2,
        }
        if order[requested] > order[parent_mode]:
            return parent_mode
        return requested

    def _parent_mode(self) -> AgentMode:
        if self.parent_mode_provider is not None:
            return self.parent_mode_provider()
        return self.parent_mode

    def _check_admission(self) -> None:
        """Fail-fast admission layer before any run record exists (decision D2).

        Instantaneous concurrency is *not* checked here — saturation queues
        instead (bounded by ``max_queued_runs``). What still rejects a spawn
        outright:

        - nesting depth beyond ``max_depth`` (defensive: the depth gate in
          ``_build_subagent_loop`` already withdraws the spawn tools),
        - the per-orchestration cumulative spawn budget ``max_spawns``.

        Called before the run record is created so a rejected spawn leaves no
        trace in the session.
        """
        depth = current_spawn_depth() + 1
        if depth > self.max_depth:
            raise RuntimeError(
                f"subagent nesting depth limit exceeded: depth {depth} > "
                f"max_depth {self.max_depth}"
            )
        self._check_spawn_budget()

    def _check_spawn_budget(self) -> None:
        workflow_id = current_workflow_id()
        if workflow_id is None:
            # 无 workflow 的主 loop：沿用 C1 的 manager 生命周期保守语义
            # （Q6 已确认「每 turn 复位」归后续 change）。
            if self._spawn_count >= self.max_spawns:
                self._count_rejection("spawn_budget")
                raise RuntimeError(
                    f"subagent spawn budget exceeded: {self._spawn_count} spawns >= "
                    f"max_spawns {self.max_spawns} (per orchestration)"
                )
            return
        used = self._workflow_spawn_counts.get(workflow_id, 0)
        limit = self._workflow_spawn_limits.get(workflow_id, self.max_spawns)
        if used >= limit:
            self._count_rejection("spawn_budget")
            raise RuntimeError(
                f"subagent spawn budget exceeded: {used} spawns >= "
                f"max_spawns {limit} (workflow {workflow_id})"
            )

    def _count_spawn(self) -> None:
        """Cumulative spawn accounting (decision D5; D8 workflow bucket).

        Both ``create_subagent`` and every run launch count once, so empty
        session creation cannot bypass the cap. With a workflow in context the
        count lands in that workflow run's bucket (two ``foreach`` nodes share
        one bucket; a nested workflow gets its own); without one it falls back
        to the manager-lifetime counter.
        """
        workflow_id = current_workflow_id()
        if workflow_id is None:
            self._spawn_count += 1
            return
        self._workflow_spawn_counts[workflow_id] = (
            self._workflow_spawn_counts.get(workflow_id, 0) + 1
        )
