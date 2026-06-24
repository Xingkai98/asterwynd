from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable

from agent.message import Message, system_message
from agent.result import RunResult, StopReason
from agent.run_config import AgentMode, AgentRunConfig, ModePolicy, parse_agent_mode
from agent.run_identity import new_run_id
from agent.tools.factory import build_default_tool_registry
from agent.workspace_policy import WorkspacePolicy
from agent.hooks.manager import HookManager
from agent.memory.manager import MemoryManager
from agent.hooks.builtin import TracingHook
from agent.trace_recorder import TraceRecorder

if TYPE_CHECKING:
    from agent.config import MyAgentConfig
    from agent.llm import LLM


@dataclass
class SubagentArtifact:
    path: str
    kind: str = "file"


@dataclass
class SubagentRunUsage:
    total_tokens: int = 0
    tool_calls: int = 0


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

    def to_result_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "summary": self.summary,
            "reason": self.reason,
            "usage": {
                "total_tokens": self.usage.total_tokens,
                "tool_calls": self.usage.tool_calls,
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
        config: "MyAgentConfig | None" = None,
        workspace_policy: WorkspacePolicy | None = None,
        parent_mode: AgentMode = AgentMode.BUILD,
        parent_mode_provider: Callable[[], AgentMode] | None = None,
    ):
        self.llm = llm
        self.config = config
        self.workspace_policy = workspace_policy or WorkspacePolicy()
        self.parent_mode = parent_mode
        self.parent_mode_provider = parent_mode_provider
        self._sessions: dict[str, SubagentSessionRecord] = {}
        self._active_tasks: dict[str, asyncio.Task[None]] = {}
        self._run_waiters: dict[str, asyncio.Event] = {}

    def configure_runtime(
        self,
        *,
        llm: "LLM | None" = None,
        config: "MyAgentConfig | None" = None,
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
    ) -> dict:
        session = self._require_session(subagent_id)
        if session.active_run_id is not None:
            raise RuntimeError(f"subagent {subagent_id} already has an active run")

        run_id = new_run_id()
        run = SubagentRunRecord(
            run_id=run_id,
            task=task,
            status="running",
            started_at=time.time(),
        )
        session.runs.append(run)
        session.active_run_id = run_id
        session.status = "running"
        session.messages.append(Message(role="user", content=task))
        waiter = asyncio.Event()
        self._run_waiters[run_id] = waiter

        bg_task = asyncio.create_task(self._execute_run(session, run))
        self._active_tasks[run_id] = bg_task
        bg_task.add_done_callback(lambda _: self._active_tasks.pop(run_id, None))

        if wait:
            await asyncio.wait_for(waiter.wait(), timeout=timeout_s)
        return self._format_run_envelope(session.subagent_id, run)

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
                {"role": msg.role, "content": msg.content, "tool_call_id": msg.tool_call_id}
                for msg in tail
            ],
            "truncated": len(messages) > limit,
            "included_tool_results": include_tool_results,
        }

    async def _execute_run(
        self,
        session: SubagentSessionRecord,
        run: SubagentRunRecord,
    ) -> None:
        if self.llm is None:
            raise RuntimeError("subagent manager LLM is not configured")
        trace = TraceRecorder(task_id=session.subagent_id)
        try:
            loop = self._build_subagent_loop(session.mode)
            result = await loop.run(
                session.messages,
                trace_recorder=trace,
                session_id=session.subagent_id,
                run_id=run.run_id,
            )
            self._complete_run(session, run, result, trace)
        except asyncio.CancelledError:
            self._mark_cancelled(session, run, trace)
            raise
        except Exception as exc:
            self._mark_failed(session, run, str(exc), trace)
        finally:
            waiter = self._run_waiters.pop(run.run_id, None)
            if waiter is not None:
                waiter.set()

    def _build_subagent_loop(self, mode: AgentMode) -> AgentLoop:
        from agent.loop import AgentLoop

        config = self.config
        registry = build_default_tool_registry(
            policy=self.workspace_policy,
            mode_policy=ModePolicy(
                AgentRunConfig(mode=mode),
                deny_tools_by_mode=config.deny_tools_by_mode() if config else None,
            ),
            ignore_patterns=config.tools.ignore_patterns if config else (),
            code_intelligence_config=config.tools.code_intelligence if config else None,
            web_search_config=config.tools.web_search if config else None,
        )
        return AgentLoop(
            llm=self.llm,
            tool_registry=registry,
            hooks=HookManager([TracingHook()]),
            memory=MemoryManager(max_tokens=80_000),
            run_config=AgentRunConfig(mode=mode),
            subagent_manager=self,
            tool_result_display=config.tools.display if config else None,
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
        run.status = "cancelled"
        run.reason = "cancelled"
        run.finished_at = time.time()
        run.trace = trace.to_dict()
        session.active_run_id = None
        session.status = "idle"

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
