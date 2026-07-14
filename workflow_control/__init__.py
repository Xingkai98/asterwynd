from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
import subprocess
from typing import Any


class WorkflowValidationError(ValueError):
    pass


class ActorKind(str, Enum):
    AGENT = "agent"
    HUMAN = "human"
    SYSTEM = "system"


class EventType(str, Enum):
    WORKFLOW_STARTED = "workflow_started"
    WORK_COMPLETED = "work_completed"
    STATE_ADVANCED = "state_advanced"
    GATE_APPROVED = "gate_approved"
    REVIEW_RESULT_RECORDED = "review_result_recorded"


class ReviewResult(str, Enum):
    PASS = "pass"
    CHANGES_REQUESTED = "changes_requested"
    BLOCKED = "blocked"
    INCONCLUSIVE = "inconclusive"


class ApprovalDecision(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    ROLLBACK = "rollback"
    SKIPPED = "skipped"


class ActivationMode(str, Enum):
    MANAGED = "managed"
    BYPASS = "bypass"


class OutputStatus(str, Enum):
    DRAFT = "draft"
    PROPOSED = "proposed"
    DURABLE = "durable"


class AgingAction(str, Enum):
    KEEP = "keep"
    ABANDON = "abandon"


@dataclass(frozen=True)
class Actor:
    kind: ActorKind
    actor_id: str
    approval_capability: bool = False


@dataclass(frozen=True)
class StateSnapshot:
    phase: str
    sub_state: str


@dataclass(frozen=True)
class PhaseDefinition:
    phase: str
    sub_states: tuple[str, ...]
    commit_policy: str = "required_before_human_gate"

    def __post_init__(self) -> None:
        if not self.phase:
            raise WorkflowValidationError("phase name is required")
        if not self.sub_states:
            raise WorkflowValidationError(f"phase {self.phase!r} must define sub_states")

    @property
    def first_sub_state(self) -> str:
        return self.sub_states[0]

    @property
    def gate_sub_state(self) -> str | None:
        if "ready_for_review" in self.sub_states:
            return "ready_for_review"
        return None


@dataclass(frozen=True)
class PhaseTemplate:
    template_id: str
    phases: tuple[PhaseDefinition | tuple[str, tuple[str, ...], str], ...]
    initial_state: StateSnapshot
    _phase_definitions: tuple[PhaseDefinition, ...] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        definitions: list[PhaseDefinition] = []
        for raw_phase in self.phases:
            if isinstance(raw_phase, PhaseDefinition):
                definitions.append(raw_phase)
            else:
                phase, sub_states, commit_policy = raw_phase
                definitions.append(
                    PhaseDefinition(
                        phase=phase,
                        sub_states=sub_states,
                        commit_policy=commit_policy,
                    )
                )
        if not definitions:
            raise WorkflowValidationError("template must define phases")
        object.__setattr__(self, "_phase_definitions", tuple(definitions))
        self._validate_state(self.initial_state)

    def phase(self, phase: str) -> PhaseDefinition:
        for definition in self._phase_definitions:
            if definition.phase == phase:
                return definition
        raise WorkflowValidationError(f"unknown phase: {phase}")

    def next_state_after_work(self, state: StateSnapshot) -> StateSnapshot:
        definition = self.phase(state.phase)
        if state.sub_state == definition.gate_sub_state:
            raise WorkflowValidationError("work cannot advance while waiting at gate")

        current_index = self._sub_state_index(definition, state.sub_state)
        if current_index + 1 < len(definition.sub_states):
            return StateSnapshot(
                phase=definition.phase,
                sub_state=definition.sub_states[current_index + 1],
            )

        next_definition = self._next_phase(definition.phase)
        if next_definition is None:
            raise WorkflowValidationError("workflow has no next state")
        return StateSnapshot(
            phase=next_definition.phase,
            sub_state=next_definition.first_sub_state,
        )

    def next_state_after_gate_approval(self, state: StateSnapshot) -> StateSnapshot:
        definition = self.phase(state.phase)
        if state.sub_state != definition.gate_sub_state:
            raise WorkflowValidationError("gate approval requires ready_for_review state")
        next_definition = self._next_phase(definition.phase)
        if next_definition is None:
            raise WorkflowValidationError("workflow has no next phase after gate")
        return StateSnapshot(
            phase=next_definition.phase,
            sub_state=next_definition.first_sub_state,
        )

    def is_legal_transition(self, from_state: StateSnapshot, to_state: StateSnapshot) -> bool:
        try:
            return (
                self.next_state_after_work(from_state) == to_state
                or self.next_state_after_gate_approval(from_state) == to_state
            )
        except WorkflowValidationError:
            return False

    def _next_phase(self, phase: str) -> PhaseDefinition | None:
        for phase_index, definition in enumerate(self._phase_definitions):
            if definition.phase == phase:
                next_index = phase_index + 1
                if next_index < len(self._phase_definitions):
                    return self._phase_definitions[next_index]
                return None
        raise WorkflowValidationError(f"unknown phase: {phase}")

    def _sub_state_index(self, definition: PhaseDefinition, sub_state: str) -> int:
        try:
            return definition.sub_states.index(sub_state)
        except ValueError as exc:
            raise WorkflowValidationError(
                f"unknown sub_state {sub_state!r} for phase {definition.phase!r}"
            ) from exc

    def _validate_state(self, state: StateSnapshot) -> None:
        definition = self.phase(state.phase)
        self._sub_state_index(definition, state.sub_state)


@dataclass(frozen=True)
class WorkResult:
    output_refs: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    summary: str = ""


@dataclass(frozen=True)
class WorkflowEvent:
    event_id: str
    workflow_id: str
    event_type: EventType
    actor: Actor
    version: int = 0
    from_state: StateSnapshot | None = None
    to_state: StateSnapshot | None = None
    work_result: WorkResult | None = None
    review_result: ReviewResult | None = None
    executor_run_id: str | None = None
    raw_user_message: str | None = None


@dataclass(frozen=True)
class WorkflowSnapshot:
    workflow_id: str
    state: StateSnapshot
    version: int
    events_seen: int


@dataclass(frozen=True)
class Evidence:
    ref: str
    kind: str
    summary: str = ""


@dataclass(frozen=True)
class Approval:
    workflow_id: str
    gate_id: str
    phase: str
    state_version: int
    decision: ApprovalDecision
    actor: Actor
    client_id: str
    user_message_hash: str
    gate_summary_hash: str
    head_sha: str | None = None

    def matches_gate(self, gate: "Gate") -> bool:
        return (
            self.workflow_id == gate.workflow_id
            and self.gate_id == gate.gate_id
            and self.phase == gate.phase
            and self.state_version == gate.state_version
            and self.gate_summary_hash == gate.gate_summary_hash
            and self.head_sha == gate.head_sha
        )


@dataclass(frozen=True)
class Gate:
    gate_id: str
    workflow_id: str
    phase: str
    state_version: int
    gate_summary_hash: str
    head_sha: str | None = None

    def approve(
        self,
        actor: Actor,
        decision: ApprovalDecision,
        client_id: str,
        user_message_hash: str,
    ) -> Approval:
        if actor.kind != ActorKind.HUMAN or not actor.approval_capability:
            raise WorkflowValidationError("gate approval requires human approval capability")
        return Approval(
            workflow_id=self.workflow_id,
            gate_id=self.gate_id,
            phase=self.phase,
            state_version=self.state_version,
            decision=decision,
            actor=actor,
            client_id=client_id,
            user_message_hash=user_message_hash,
            gate_summary_hash=self.gate_summary_hash,
            head_sha=self.head_sha,
        )


@dataclass(frozen=True)
class WorkItem:
    work_item_id: str
    workflow_id: str
    state: StateSnapshot
    allowed_actions: tuple[str, ...] = ()
    required_evidence: tuple[Evidence, ...] = ()

    def allows(self, action: str) -> bool:
        return action in self.allowed_actions


@dataclass(frozen=True)
class Lease:
    lease_id: str
    work_item_id: str
    owner_id: str
    expires_at: datetime

    def is_active_at(self, now: datetime) -> bool:
        return now < self.expires_at

    def renew(self, expires_at: datetime) -> "Lease":
        if expires_at <= self.expires_at:
            raise WorkflowValidationError("renewed lease must extend expiration")
        return Lease(
            lease_id=self.lease_id,
            work_item_id=self.work_item_id,
            owner_id=self.owner_id,
            expires_at=expires_at,
        )


@dataclass(frozen=True)
class WorkspaceBinding:
    workflow_id: str
    branch: str
    worktree_path: Path
    head_sha: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "worktree_path", self.worktree_path.resolve())


@dataclass(frozen=True)
class ManagedWorkspaceConfig:
    managed_roots: tuple[Path, ...]

    def canonical_roots(self) -> tuple[Path, ...]:
        return tuple(root.resolve() for root in self.managed_roots)


@dataclass(frozen=True)
class ActivationDecision:
    mode: ActivationMode
    reason: str
    managed_root: Path | None = None
    git_common_dir: Path | None = None
    workflow_prompt_enabled: bool = False
    model_call_allowed: bool = True


@dataclass(frozen=True)
class WorkflowOutput:
    ref: str
    status: OutputStatus


@dataclass(frozen=True)
class AgingPolicy:
    ttl: timedelta


@dataclass(frozen=True)
class AgingDecision:
    action: AgingAction
    reason: str


class WorkflowActivationGate:
    def __init__(self, config: ManagedWorkspaceConfig) -> None:
        self.config = config
        self._session_bypass: set[str] = set()

    def preflight(
        self,
        cwd: str | Path,
        session_id: str | None = None,
        attach_root: str | Path | None = None,
    ) -> ActivationDecision:
        canonical_cwd = Path(cwd).resolve()
        roots = self.config.canonical_roots()

        if attach_root is not None:
            canonical_attach_root = Path(attach_root).resolve()
            managed_root = self._matching_root(canonical_attach_root, roots)
            if managed_root is None:
                raise WorkflowValidationError("attach_root is not in managed roots")
            if session_id is not None:
                self._session_bypass.discard(session_id)
            return ActivationDecision(
                mode=ActivationMode.MANAGED,
                reason="explicit_attach",
                managed_root=managed_root,
                git_common_dir=_git_common_dir(canonical_cwd),
                workflow_prompt_enabled=True,
            )

        if session_id is not None and session_id in self._session_bypass:
            return ActivationDecision(
                mode=ActivationMode.BYPASS,
                reason="sticky_bypass",
                workflow_prompt_enabled=False,
            )

        managed_root = self._matching_root(canonical_cwd, roots)
        git_common_dir = _git_common_dir(canonical_cwd)
        if managed_root is None and git_common_dir is not None:
            managed_root = self._matching_root(git_common_dir, roots)

        if managed_root is None:
            if session_id is not None:
                self._session_bypass.add(session_id)
            return ActivationDecision(
                mode=ActivationMode.BYPASS,
                reason="cwd_not_in_managed_roots",
                workflow_prompt_enabled=False,
            )

        reason = "git_common_dir" if git_common_dir is not None and not _is_within(canonical_cwd, managed_root) else "managed_root"
        return ActivationDecision(
            mode=ActivationMode.MANAGED,
            reason=reason,
            managed_root=managed_root,
            git_common_dir=git_common_dir,
            workflow_prompt_enabled=True,
        )

    def _matching_root(self, path: Path, roots: tuple[Path, ...]) -> Path | None:
        for root in roots:
            if _is_within(path, root):
                return root
        return None


def default_coding_agent_template() -> PhaseTemplate:
    return PhaseTemplate(
        template_id="coding-agent-conversation-delivery-v1",
        phases=(
            ("exploring", ("chatting",), "none"),
            ("requirements", ("drafting", "ready_for_review"), "none"),
            ("design", ("writing_design", "ready_for_review"), "required_before_human_gate"),
            ("building", ("writing_tests", "implementing", "ready_for_review"), "required_before_human_gate"),
            ("code-review", ("reviewing_code", "ready_for_review"), "required_before_human_gate"),
            ("closing", ("archiving", "ready_for_review"), "required_before_human_gate"),
        ),
        initial_state=StateSnapshot(phase="exploring", sub_state="chatting"),
    )


def start_workflow(workflow_id: str, template: PhaseTemplate) -> WorkflowEvent:
    return WorkflowEvent(
        event_id="event-1",
        workflow_id=workflow_id,
        event_type=EventType.WORKFLOW_STARTED,
        actor=Actor(kind=ActorKind.SYSTEM, actor_id="workflow-control"),
        to_state=template.initial_state,
        version=1,
    )


def record_work_completed(
    workflow_id: str,
    actor: Actor,
    work_result: WorkResult,
) -> WorkflowEvent:
    return WorkflowEvent(
        event_id="work-completed",
        workflow_id=workflow_id,
        event_type=EventType.WORK_COMPLETED,
        actor=actor,
        work_result=work_result,
    )


def record_gate_approved(
    workflow_id: str,
    actor: Actor,
    raw_user_message: str | None = None,
) -> WorkflowEvent:
    return WorkflowEvent(
        event_id="gate-approved",
        workflow_id=workflow_id,
        event_type=EventType.GATE_APPROVED,
        actor=actor,
        raw_user_message=raw_user_message,
    )


def record_review_result(
    workflow_id: str,
    actor: Actor,
    review_result: ReviewResult,
    executor_run_id: str,
) -> WorkflowEvent:
    if actor.actor_id == executor_run_id:
        raise WorkflowValidationError("self review is not allowed")
    return WorkflowEvent(
        event_id="review-result-recorded",
        workflow_id=workflow_id,
        event_type=EventType.REVIEW_RESULT_RECORDED,
        actor=actor,
        review_result=review_result,
        executor_run_id=executor_run_id,
    )


def reduce_events(
    events: list[WorkflowEvent],
    template: PhaseTemplate,
) -> WorkflowSnapshot:
    if not events:
        raise WorkflowValidationError("event stream is empty")

    workflow_id: str | None = None
    current_state: StateSnapshot | None = None
    version = 0

    for event in events:
        if workflow_id is None:
            workflow_id = event.workflow_id
        elif event.workflow_id != workflow_id:
            raise WorkflowValidationError("event stream contains multiple workflows")

        if event.event_type == EventType.WORKFLOW_STARTED:
            if current_state is not None:
                raise WorkflowValidationError("workflow already started")
            if event.to_state != template.initial_state:
                raise WorkflowValidationError("workflow start state does not match template")
            current_state = event.to_state
        elif event.event_type == EventType.WORK_COMPLETED:
            current_state = _advance_from_work(current_state, template)
        elif event.event_type == EventType.STATE_ADVANCED:
            current_state = _advance_from_explicit_event(current_state, event, template)
        elif event.event_type == EventType.GATE_APPROVED:
            _validate_gate_approval(event)
            current_state = _advance_from_gate(current_state, template)
        elif event.event_type == EventType.REVIEW_RESULT_RECORDED:
            if event.executor_run_id == event.actor.actor_id:
                raise WorkflowValidationError("self review is not allowed")
        else:
            raise WorkflowValidationError(f"unsupported event type: {event.event_type}")
        version += 1

    if workflow_id is None or current_state is None:
        raise WorkflowValidationError("workflow did not start")
    return WorkflowSnapshot(
        workflow_id=workflow_id,
        state=current_state,
        version=version,
        events_seen=len(events),
    )


def _advance_from_work(
    current_state: StateSnapshot | None,
    template: PhaseTemplate,
) -> StateSnapshot:
    if current_state is None:
        raise WorkflowValidationError("workflow must start before work is completed")
    return template.next_state_after_work(current_state)


def _advance_from_gate(
    current_state: StateSnapshot | None,
    template: PhaseTemplate,
) -> StateSnapshot:
    if current_state is None:
        raise WorkflowValidationError("workflow must start before gate approval")
    return template.next_state_after_gate_approval(current_state)


def _advance_from_explicit_event(
    current_state: StateSnapshot | None,
    event: WorkflowEvent,
    template: PhaseTemplate,
) -> StateSnapshot:
    if current_state is None:
        raise WorkflowValidationError("workflow must start before state advancement")
    if event.from_state != current_state:
        raise WorkflowValidationError("event from_state does not match current state")
    if event.to_state is None:
        raise WorkflowValidationError("state advancement requires to_state")
    if not template.is_legal_transition(current_state, event.to_state):
        raise WorkflowValidationError("illegal transition")
    return event.to_state


def _validate_gate_approval(event: WorkflowEvent) -> None:
    if event.actor.kind != ActorKind.HUMAN or not event.actor.approval_capability:
        raise WorkflowValidationError("gate approval requires human approval capability")


def evaluate_exploration_aging(
    snapshot: WorkflowSnapshot,
    outputs: tuple[WorkflowOutput, ...],
    last_activity_at: datetime,
    now: datetime,
    policy: AgingPolicy,
) -> AgingDecision:
    if snapshot.state.phase != "exploring":
        return AgingDecision(action=AgingAction.KEEP, reason="not_exploration")
    if any(output.status == OutputStatus.DURABLE for output in outputs):
        return AgingDecision(action=AgingAction.KEEP, reason="durable_output_present")
    if now - last_activity_at < policy.ttl:
        return AgingDecision(action=AgingAction.KEEP, reason="ttl_not_expired")
    return AgingDecision(action=AgingAction.ABANDON, reason="empty_exploration_expired")


def _git_common_dir(cwd: Path) -> Path | None:
    try:
        common_dir_result = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            cwd=cwd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None

    raw_common_dir = common_dir_result.stdout.strip()
    if not raw_common_dir:
        return None
    common_dir = Path(raw_common_dir)
    if common_dir.is_absolute():
        return common_dir.resolve()

    try:
        top_level_result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cwd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return (cwd / common_dir).resolve()
    top_level = Path(top_level_result.stdout.strip())
    if not top_level.is_absolute():
        top_level = (cwd / top_level).resolve()
    return (top_level / common_dir).resolve()


def _is_within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


__all__ = [
    "Actor",
    "ActorKind",
    "ActivationDecision",
    "ActivationMode",
    "Approval",
    "ApprovalDecision",
    "AgingAction",
    "AgingDecision",
    "AgingPolicy",
    "Evidence",
    "EventType",
    "Gate",
    "Lease",
    "ManagedWorkspaceConfig",
    "OutputStatus",
    "PhaseDefinition",
    "PhaseTemplate",
    "ReviewResult",
    "StateSnapshot",
    "WorkResult",
    "WorkItem",
    "WorkflowEvent",
    "WorkflowActivationGate",
    "WorkflowOutput",
    "WorkflowSnapshot",
    "WorkspaceBinding",
    "WorkflowValidationError",
    "default_coding_agent_template",
    "evaluate_exploration_aging",
    "record_gate_approved",
    "record_review_result",
    "record_work_completed",
    "reduce_events",
    "start_workflow",
]
