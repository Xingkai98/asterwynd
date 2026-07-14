from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
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


__all__ = [
    "Actor",
    "ActorKind",
    "EventType",
    "PhaseDefinition",
    "PhaseTemplate",
    "ReviewResult",
    "StateSnapshot",
    "WorkResult",
    "WorkflowEvent",
    "WorkflowSnapshot",
    "WorkflowValidationError",
    "default_coding_agent_template",
    "record_gate_approved",
    "record_review_result",
    "record_work_completed",
    "reduce_events",
    "start_workflow",
]
