from __future__ import annotations

import asyncio
import logging
import time
import uuid
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
from agent.subagent.context import current_spawn_depth, set_spawn_depth, reset_spawn_depth
from agent.subagent.snapshot import SubagentSnapshotStore

if TYPE_CHECKING:
    from agent.config import AsterwyndConfig
    from agent.cost_tracker import CostLedger
    from agent.llm import LLM
    from agent.session import SessionSnapshot
    from agent.tools.sandbox import ExecutionBackend

logger = logging.getLogger("asterwynd.subagent")


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
    # Internal: set by the time-budget monitor *before* it cancels so the
    # cancelled-task handler records ``budget_exceeded`` instead of ``cancelled``.
    _budget_kill_reason: str | None = field(default=None, repr=False)

    def to_result_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "summary": self.summary,
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

    def to_summary_dict(self) -> dict:
        return {
            "subagent_id": self.subagent_id,
            "name": self.name,
            "mode": self.mode.value,
            "status": self.status,
            "created_at": self.created_at,
            "active_run_id": self.active_run_id,
            "run_count": len(self.runs),
        }


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
        max_concurrent_runs: int | None = None,
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
        # Concurrency / nesting-depth guardrails (decision D4; reference:
        # Codex max_threads/max_depth, Claude Code #68110 unbounded burn).
        guardrails = getattr(config, "subagents", None) if config is not None else None
        self.max_concurrent_runs = (
            max_concurrent_runs
            if max_concurrent_runs is not None
            else getattr(guardrails, "max_concurrent_runs", 4)
        )
        self.max_depth = (
            max_depth
            if max_depth is not None
            else getattr(guardrails, "max_depth", 3)
        )
        self._snapshot_store_impl: SubagentSnapshotStore | None = None

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
        )
        self._sessions[subagent_id] = session
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

    async def run_subagent(
        self,
        *,
        subagent_id: str,
        task: str,
        wait: bool = False,
        timeout_s: float | None = None,
        max_tokens: int | None = None,
        max_time_s: float | None = None,
    ) -> dict:
        session = self._require_session(subagent_id)
        if session.active_run_id is not None:
            raise RuntimeError(f"subagent {subagent_id} already has an active run")
        self._check_guardrails()

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
        await self._launch_run(session, run, wait=wait, timeout_s=timeout_s)
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
        snapshot = self._snapshot_store().load(run_id)
        if snapshot is None:
            raise KeyError(f"no checkpoint found for run {run_id}")
        self._check_guardrails()

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
        # checkpoint and ``_launch_run`` appends the continue task.
        session.messages = [
            system_message("你是一个受限的子 agent。按任务目标完成工作并汇报结果。")
        ]
        await self._launch_run(
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
    ) -> SubagentRunRecord:
        """Create and register a new run record for a session."""
        run_id = new_run_id()
        run = SubagentRunRecord(
            run_id=run_id,
            task=task,
            status="running",
            started_at=time.time(),
            max_tokens=max_tokens,
            max_time_s=max_time_s,
        )
        session.runs.append(run)
        return run

    async def _launch_run(
        self,
        session: SubagentSessionRecord,
        run: SubagentRunRecord,
        *,
        wait: bool = False,
        timeout_s: float | None = None,
        resume_snapshot: "SessionSnapshot | None" = None,
    ) -> None:
        """Start the background run task (optionally from a checkpoint).

        ``resume_snapshot`` is only passed through when resuming; a fresh run
        leaves it ``None`` and the loop starts from the session transcript.
        The time-budget monitor is only started when the run has a limit.
        """
        session.active_run_id = run.run_id
        session.status = "running"
        session.messages.append(Message(role="user", content=run.task))
        waiter = asyncio.Event()
        self._run_waiters[run.run_id] = waiter

        depth_token = set_spawn_depth(current_spawn_depth() + 1)
        try:
            bg_task = asyncio.create_task(
                self._execute_run(session, run, resume_snapshot)
            )
        finally:
            reset_spawn_depth(depth_token)
        self._active_tasks[run.run_id] = bg_task
        bg_task.add_done_callback(
            lambda _: self._active_tasks.pop(run.run_id, None)
        )

        if run.max_time_s is not None:
            asyncio.create_task(self._monitor_run_timeout(session, run))

        if wait:
            await asyncio.wait_for(waiter.wait(), timeout=timeout_s)

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
        if wait and run.status == "running":
            waiter = self._run_waiters[run.run_id]
            await asyncio.wait_for(waiter.wait(), timeout=timeout_s)
        return self._format_run_envelope(session.subagent_id, run)

    async def cancel_subagent_run(
        self,
        *,
        subagent_id: str,
        run_id: str | None = None,
    ) -> dict:
        session = self._require_session(subagent_id)
        run = self._find_run(session, run_id)
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
            latest = session.runs[-1].summary if session.runs else ""
            return {
                "subagent_id": subagent_id,
                "run_id": run_id,
                "scope": "summary",
                "summary": latest,
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
        if self.llm is None:
            raise RuntimeError("subagent manager LLM is not configured")
        trace = TraceRecorder(task_id=session.subagent_id)
        tracker = BudgetTracker(
            max_tokens=run.max_tokens,
            max_time_s=run.max_time_s,
            started_at=run.started_at,
        )
        try:
            loop = self._build_subagent_loop(session.mode, budget=tracker)
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
            self._mark_budget_exceeded(session, run, exc.dimension, trace)
        except asyncio.CancelledError:
            self._write_checkpoint(session, run)
            if run._budget_kill_reason is not None:
                self._mark_budget_exceeded(
                    session, run, run._budget_kill_reason, trace
                )
            else:
                self._mark_cancelled(session, run, trace)
            raise
        except Exception as exc:
            self._write_checkpoint(session, run)
            self._mark_failed(session, run, str(exc), trace)
        finally:
            waiter = self._run_waiters.pop(run.run_id, None)
            if waiter is not None:
                waiter.set()

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
        return AgentLoop(
            llm=self.llm,
            tool_registry=registry,
            hooks=hooks,
            memory=MemoryManager(max_tokens=80_000),
            run_config=AgentRunConfig(mode=mode),
            subagent_manager=self,
            expose_subagent_tools=True,
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
        if run.status != "running":
            return  # budget_exceeded / failed / completed already terminal
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
    ) -> None:
        if run.status != "running":
            return  # already terminal
        run.status = "budget_exceeded"
        run.reason = f"budget exceeded ({dimension})"
        run.finished_at = time.time()
        run.trace = trace.to_dict() if trace is not None else None
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
        """Snapshot the run before an interrupt/kill so it can be resumed."""
        try:
            store = self._snapshot_store()
            store.save(store.snapshot_for_run(session, run))
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

        The monitor marks ``_budget_kill_reason`` and snapshots *before*
        cancelling so the cancelled-task handler records ``budget_exceeded``
        (and the checkpoint is resumable) rather than a plain ``cancelled``.
        """
        await asyncio.sleep(run.max_time_s)
        task = self._active_tasks.get(run.run_id)
        if task is None or task.done():
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

    def _check_guardrails(self) -> None:
        """Reject a spawn that would exceed concurrency or nesting-depth limits.

        Pure pre-spawn guard: called before any run record is created, so a
        rejected spawn leaves no trace in the session (``run_subagent`` raises
        before appending to ``session.runs``).
        """
        depth = current_spawn_depth() + 1
        if depth > self.max_depth:
            raise RuntimeError(
                f"subagent nesting depth limit exceeded: depth {depth} > "
                f"max_depth {self.max_depth}"
            )
        active = len(self._active_tasks)
        if active >= self.max_concurrent_runs:
            raise RuntimeError(
                f"subagent concurrency limit exceeded: {active} active runs >= "
                f"max_concurrent_runs {self.max_concurrent_runs}"
            )
