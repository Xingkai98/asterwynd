from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from agent.workflow.manager import WorkflowManager
from agent.workflow.models import (
    Executor,
    Phase,
    PhaseRouting,
    RoleAgentType,
    SessionMode,
    StateSnapshot,
)
from agent.workflow.role_registry import build_subagent_task, get_role_config
from agent.workflow.routing import get_routing_for_phase

if TYPE_CHECKING:
    from agent.subagent.manager import SubAgentManager

logger = logging.getLogger(__name__)


@dataclass
class DispatchResult:
    """Result of dispatching a phase to the appropriate executor."""

    executor: Executor
    session_mode: SessionMode
    phase: Phase
    role_type: RoleAgentType
    task_prompt: str

    # subagent result (when executor == "subagent")
    subagent_id: str | None = None
    subagent_summary: dict | None = None

    # external executor hints (when executor in ("claude-code", "codex"))
    cli_command: str | None = None

    # inline hints (when executor == "inline")
    inline_context: dict | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "executor": self.executor,
            "session_mode": self.session_mode,
            "phase": self.phase,
            "role_type": self.role_type,
            "task_prompt": self.task_prompt,
        }
        if self.subagent_id:
            d["subagent_id"] = self.subagent_id
        if self.subagent_summary:
            d["subagent_summary"] = self.subagent_summary
        if self.cli_command:
            d["cli_command"] = self.cli_command
        if self.inline_context:
            d["inline_context"] = self.inline_context
        return d


class SubAgentManagerProtocol(Protocol):
    """Protocol for SubAgentManager so dispatcher doesn't require the real import."""

    def create_subagent(self, *, name: str, description: str, mode: str | Any | None = None) -> dict:
        ...

    def run_subagent(
        self, *, subagent_id: str, task: str, wait: bool = False, timeout_s: float | None = None
    ) -> Any:
        ...

    def configure_runtime(
        self, *, llm: Any = None, config: Any = None,
        workspace_policy: Any = None, parent_mode_provider: Any = None,
    ) -> None:
        ...


class WorkflowDispatcher:
    """Dispatches workflow phases to the configured executor.

    Reads routing config from handoff.json, determines the right role agent,
    and dispatches to the appropriate executor (inline / subagent / claude-code / codex).
    """

    def __init__(
        self,
        change_dir: str | Path,
        repo_root: str | Path = ".",
        subagent_manager: SubAgentManagerProtocol | None = None,
    ) -> None:
        self._workflow = WorkflowManager(change_dir, repo_root)
        self._subagent_manager = subagent_manager

    @property
    def workflow(self) -> WorkflowManager:
        return self._workflow

    def dispatch_current_phase(self) -> DispatchResult:
        """Read current state and dispatch based on routing config."""
        self._workflow.ensure_loaded()
        state = self._workflow.current_state
        phase = state.phase

        if phase in ("blocked", "done"):
            raise ValueError(f"cannot dispatch from terminal phase: {phase}")

        routing = self._workflow.routing_for_phase(phase)
        role_type = self._workflow.recommended_role
        if role_type is None:
            raise ValueError(f"no role type for phase: {phase}")

        task_prompt = build_subagent_task(
            role_type=role_type,
            change_id=self._workflow._data["change_id"],
            state_summary=self._workflow.snapshot(),
            handoff_note_path=_latest_handoff_note(self._workflow._data),
        )

        return self._build_result(phase, role_type, routing, task_prompt)

    def approve_and_dispatch(
        self,
        actor_id: str,
        reason: str | None = None,
    ) -> DispatchResult:
        """Human approves at gate, transitions to next phase, and dispatches it."""
        snap = self._workflow.human_approve(actor_id, reason)
        new_phase = snap["state"]["phase"]
        if new_phase in ("blocked", "done"):
            raise ValueError(f"workflow complete: phase is {new_phase}")
        return self.dispatch_current_phase()

    def skip_and_dispatch(
        self,
        actor_id: str,
        skip_reason: str,
    ) -> DispatchResult:
        """Human skips next phase at gate, transitions, and dispatches."""
        snap = self._workflow.human_skip(actor_id, skip_reason)
        new_phase = snap["state"]["phase"]
        if new_phase in ("blocked", "done"):
            raise ValueError(f"workflow complete: phase is {new_phase}")
        return self.dispatch_current_phase()

    def _build_result(
        self,
        phase: Phase,
        role_type: RoleAgentType,
        routing: PhaseRouting,
        task_prompt: str,
    ) -> DispatchResult:
        result = DispatchResult(
            executor=routing.executor,
            session_mode=routing.session_mode,
            phase=phase,
            role_type=role_type,
            task_prompt=task_prompt,
        )

        if routing.executor == "inline":
            result.inline_context = {
                "change_dir": str(self._workflow._change_dir),
                "state": self._workflow.snapshot()["state"],
            }
        elif routing.executor == "subagent":
            result = self._dispatch_to_subagent(result, routing)
        elif routing.executor in ("claude-code", "codex"):
            result = self._dispatch_to_external_cli(result, routing)

        return result

    def dispatch_phase(self, phase: Phase) -> DispatchResult:
        """Dispatch a specific phase (for future phases, e.g., at gate)."""
        self._workflow.ensure_loaded()
        routing = self._workflow.routing_for_phase(phase)

        from agent.workflow.models import PHASE_TO_ROLE
        role_type = PHASE_TO_ROLE.get(phase)
        if role_type is None:
            raise ValueError(f"no role type for phase: {phase}")

        task_prompt = build_subagent_task(
            role_type=role_type,
            change_id=self._workflow._data["change_id"],
            state_summary=self._workflow.snapshot(),
        )

        return self._build_result(phase, role_type, routing, task_prompt)

    def _dispatch_to_subagent(
        self,
        result: DispatchResult,
        routing: PhaseRouting,
    ) -> DispatchResult:
        if self._subagent_manager is None:
            logger.warning("no subagent manager configured, returning inline fallback")
            result.executor = "inline"
            result.inline_context = {"fallback_reason": "subagent_manager not configured"}
            return result

        config = get_role_config(result.role_type)
        summary = self._subagent_manager.create_subagent(
            name=config.name,
            description=config.description,
        )
        result.subagent_id = summary["subagent_id"]
        result.subagent_summary = summary
        return result

    def _dispatch_to_external_cli(
        self,
        result: DispatchResult,
        routing: PhaseRouting,
    ) -> DispatchResult:
        cli = routing.executor  # "claude-code" or "codex"
        result.cli_command = (
            f"cat prompt.txt | {cli} exec - "
            f"--cd {self._workflow._change_dir} "
            f"--sandbox workspace-write"
        )
        return result


def _latest_handoff_note(data: dict) -> str | None:
    """Extract the latest handoff note path from transitions."""
    transitions = data.get("transitions", [])
    for t in reversed(transitions):
        if t.get("handoff_note"):
            return t["handoff_note"]
    return None
