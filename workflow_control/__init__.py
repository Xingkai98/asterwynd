from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from enum import Enum
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
from typing import Any


class WorkflowValidationError(ValueError):
    pass


class WorkflowStoreConflict(WorkflowValidationError):
    pass


class WorkflowHistoryCorrupt(WorkflowValidationError):
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
    WORKFLOW_ABANDONED = "workflow_abandoned"


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


class GateEventType(str, Enum):
    REACHED = "gate_reached"
    APPROVED = "gate_approved"
    REJECTED = "gate_rejected"
    REVISION_REQUESTED = "gate_revision_requested"
    STALE = "gate_stale"


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


class PhaseCommitPolicy(str, Enum):
    NONE = "none"
    REQUIRED_BEFORE_HUMAN_GATE = "required_before_human_gate"


class ExecutorMode(str, Enum):
    SELF = "self"
    RUNNER = "runner"
    SUBAGENT = "subagent"
    COMMAND = "command"
    ASK = "ask"


class ReviewerMode(str, Enum):
    RUNNER = "runner"
    SUBAGENT = "subagent"
    COMMAND = "command"


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
class ExecutorLane:
    mode: ExecutorMode
    runner_profile: str | None = None


@dataclass(frozen=True)
class ReviewerDefinition:
    name: str
    mode: ReviewerMode | str
    runner_profile: str | None = None
    fresh_context: bool = True

    def __post_init__(self) -> None:
        try:
            mode = ReviewerMode(self.mode)
        except ValueError as exc:
            raise WorkflowValidationError("reviewer cannot use self") from exc
        object.__setattr__(self, "mode", mode)


@dataclass(frozen=True)
class ReviewLane:
    reviewers: tuple[ReviewerDefinition, ...] = ()


@dataclass(frozen=True)
class RunnerProfile:
    name: str
    command: str
    args: tuple[str, ...] = ()
    prompt_mode: str = "stdin"
    permissions: str = "read-only"
    timeout_seconds: int = 300


@dataclass(frozen=True)
class PhaseDefinition:
    phase: str
    sub_states: tuple[str, ...]
    commit_policy: PhaseCommitPolicy | str = PhaseCommitPolicy.REQUIRED_BEFORE_HUMAN_GATE
    executor_lane: ExecutorLane = field(
        default_factory=lambda: ExecutorLane(mode=ExecutorMode.SELF),
    )
    review_lane: ReviewLane = field(default_factory=ReviewLane)

    def __post_init__(self) -> None:
        if not self.phase:
            raise WorkflowValidationError("phase name is required")
        if not self.sub_states:
            raise WorkflowValidationError(f"phase {self.phase!r} must define sub_states")
        object.__setattr__(self, "commit_policy", PhaseCommitPolicy(self.commit_policy))

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
    runner_profiles: tuple[RunnerProfile, ...] = ()
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

    def runner_profile(self, name: str) -> RunnerProfile:
        for profile in self.runner_profiles:
            if profile.name == name:
                return profile
        raise WorkflowValidationError(f"unknown runner profile: {name}")

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
    approval: Approval | None = None
    occurred_at: datetime | None = None
    workspace_binding: WorkspaceBinding | None = None


@dataclass(frozen=True)
class WorkflowSnapshot:
    workflow_id: str
    state: StateSnapshot
    version: int
    events_seen: int


@dataclass(frozen=True)
class RequirementsDraft:
    goal: str = ""
    scope: str = ""
    acceptance: str = ""
    test_strategy: str = ""
    version: int = 1
    frozen: bool = False
    approved_snapshot_version: int | None = None
    approved_snapshot_hash: str | None = None

    @classmethod
    def empty(cls) -> "RequirementsDraft":
        return cls()

    def update_goal(self, goal: str) -> "RequirementsDraft":
        if self.frozen:
            raise ValueError("requirements draft is frozen")
        return replace(self, goal=goal, version=self.version + 1)

    def freeze(self) -> "RequirementsDraft":
        return replace(self, frozen=True, version=self.version + 1)

    @classmethod
    def from_markdown(
        cls,
        markdown: str,
        approved_snapshot_version: int | None = None,
    ) -> "RequirementsDraft":
        draft = cls(
            goal=_section_from_markdown(markdown, "Goal"),
            scope=_section_from_markdown(markdown, "Scope"),
            acceptance=_section_from_markdown(markdown, "Acceptance"),
            test_strategy=_section_from_markdown(markdown, "Test Strategy"),
            frozen=True,
            version=1,
        )
        return replace(
            draft,
            approved_snapshot_version=approved_snapshot_version,
            approved_snapshot_hash=_hash_text(draft.to_markdown()),
        )

    def to_markdown(self) -> str:
        return "\n".join([
            "# Requirements",
            "",
            f"## Goal\n{self.goal}",
            "",
            f"## Scope\n{self.scope}",
            "",
            f"## Acceptance\n{self.acceptance}",
            "",
            f"## Test Strategy\n{self.test_strategy}",
        ])


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
class GateBinding:
    phase: str
    state_version: int
    branch: str
    head_sha: str
    evidence_hash: str
    gate_summary_hash: str


@dataclass(frozen=True)
class GateApprovalTokenMatcher:
    allowed_tokens: tuple[str, ...] = ("ok",)

    def matches(self, raw_message: str) -> bool:
        return raw_message in self.allowed_tokens


@dataclass(frozen=True)
class CapabilityPolicy:
    can_approve_gate: bool
    allowed_commands: tuple[str, ...]

    @classmethod
    def for_agent(cls) -> "CapabilityPolicy":
        return cls(
            can_approve_gate=False,
            allowed_commands=("workflow enter", "workflow status", "workflow report"),
        )

    @classmethod
    def for_host(cls) -> "CapabilityPolicy":
        return cls(
            can_approve_gate=True,
            allowed_commands=(
                "workflow enter",
                "workflow status",
                "workflow report",
                "workflow gate approve",
            ),
        )


@dataclass(frozen=True)
class HostApprovalResult:
    consumed: bool
    event_type: GateEventType
    approval: Approval | None = None


class HostApprovalService:
    def __init__(self, matcher: GateApprovalTokenMatcher) -> None:
        self.matcher = matcher

    def try_approve(
        self,
        gate: Gate,
        raw_message: str,
        user_id: str,
        client_id: str,
    ) -> HostApprovalResult:
        if not self.matcher.matches(raw_message):
            return HostApprovalResult(consumed=False, event_type=GateEventType.REACHED)
        approval = gate.approve(
            actor=Actor(kind=ActorKind.HUMAN, actor_id=user_id, approval_capability=True),
            decision=ApprovalDecision.APPROVED,
            client_id=client_id,
            user_message_hash=_hash_text(raw_message),
        )
        return HostApprovalResult(
            consumed=True,
            event_type=GateEventType.APPROVED,
            approval=approval,
        )

    @staticmethod
    def validate_approval_for_gate(approval: Approval, gate: Gate) -> None:
        if not approval.matches_gate(gate):
            raise WorkflowValidationError("stale approval")


class WorkspaceWritePolicy:
    def can_write(self, phase: str, sub_state: str, has_active_lease: bool) -> bool:
        return has_active_lease and sub_state != "ready_for_review"


@dataclass(frozen=True)
class WorkItem:
    work_item_id: str
    workflow_id: str
    state: StateSnapshot
    allowed_actions: tuple[str, ...] = ()
    required_evidence: tuple[Evidence, ...] = ()
    next_action: str = ""

    def allows(self, action: str) -> bool:
        return action in self.allowed_actions


@dataclass(frozen=True)
class SessionBinding:
    session_id: str
    workflow_id: str


class SessionBindingRegistry:
    def __init__(self) -> None:
        self._bindings: dict[str, SessionBinding] = {}

    def bind(self, session_id: str, workflow_id: str) -> SessionBinding:
        existing = self._bindings.get(session_id)
        if existing is not None:
            if existing.workflow_id != workflow_id:
                raise WorkflowValidationError("session already bound to another workflow")
            return existing
        binding = SessionBinding(session_id=session_id, workflow_id=workflow_id)
        self._bindings[session_id] = binding
        return binding

    def get(self, session_id: str) -> SessionBinding | None:
        return self._bindings.get(session_id)


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
    base_branch: str | None = None
    base_commit: str | None = None
    base_check: str | None = None
    fetch_failure: str | None = None
    override_reason: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "worktree_path", self.worktree_path.resolve())


@dataclass(frozen=True)
class PhaseCommit:
    head_sha: str


@dataclass(frozen=True)
class BaseBranchCheck:
    ok: bool
    reason: str = ""
    base_commit: str | None = None
    remote_commit: str | None = None
    fetch_failure: str | None = None
    override_reason: str | None = None


@dataclass(frozen=True)
class WorktreeCoordinatorConfig:
    canonical_repo: Path
    worktrees_root: Path


class WorktreeCoordinator:
    def __init__(self, config: WorktreeCoordinatorConfig) -> None:
        self.config = config
        self.config.worktrees_root.mkdir(parents=True, exist_ok=True)
        self._bindings: dict[str, WorkspaceBinding] = {}

    def create_or_reuse_worktree(
        self,
        change_id: str,
        date: str,
        force_new: bool = False,
    ) -> WorkspaceBinding:
        branch = f"{change_id}/{date}"
        if branch in self._bindings:
            if force_new:
                raise WorkflowValidationError("worktree already bound")
            binding = self._bindings[branch]
            if self.current_branch(binding.worktree_path) != branch:
                raise WorkflowValidationError("worktree branch drift")
            return binding
        worktree_path = (self.config.worktrees_root / change_id).resolve()
        if worktree_path.exists():
            if force_new:
                raise WorkflowValidationError("worktree already bound")
            if self.current_branch(worktree_path) != branch:
                raise WorkflowValidationError("worktree branch drift")
        else:
            _git(self.config.canonical_repo, "worktree", "add", "-b", branch, str(worktree_path))
        binding = WorkspaceBinding(
            workflow_id=change_id,
            branch=branch,
            worktree_path=worktree_path,
            head_sha=self._head_sha(worktree_path),
        )
        self._bindings[branch] = binding
        return binding

    def promote_requirements(
        self,
        change_id: str,
        approved_requirements: RequirementsDraft,
        date: str,
        base_branch: str = "master",
        allow_local_base: bool = False,
    ) -> WorkspaceBinding:
        base_check = self.check_base_branch(
            self.config.canonical_repo,
            base_branch=base_branch,
            allow_local_base=allow_local_base,
        )
        if not base_check.ok:
            raise WorkflowValidationError(f"base branch blocked: {base_check.reason}")
        binding = self.create_or_reuse_worktree(change_id, date)
        binding = replace(
            binding,
            base_branch=base_branch,
            base_commit=base_check.base_commit or self._head_sha(self.config.canonical_repo),
            base_check=base_check.reason or "synced",
            fetch_failure=base_check.fetch_failure,
            override_reason=base_check.override_reason,
        )
        self._bindings[binding.branch] = binding
        try:
            change_dir = binding.worktree_path / "openspec" / "changes" / change_id
            change_dir.mkdir(parents=True, exist_ok=True)
            (change_dir / "proposal.md").write_text(approved_requirements.to_markdown(), encoding="utf-8")
            spec_dir = change_dir / "specs" / "conversation-delivery-workflow"
            spec_dir.mkdir(parents=True, exist_ok=True)
            (spec_dir / "spec.md").write_text(
                _requirements_to_spec_delta(approved_requirements),
                encoding="utf-8",
            )
            (change_dir / "workflow-manifest.json").write_text(
                json.dumps(
                    {
                        "change_id": change_id,
                        "branch": binding.branch,
                        "base_branch": binding.base_branch,
                        "base_commit": binding.base_commit,
                        "base_check": binding.base_check,
                        "fetch_failure": binding.fetch_failure,
                        "override_reason": binding.override_reason,
                        "approved_snapshot_version": approved_requirements.approved_snapshot_version,
                        "approved_snapshot_hash": approved_requirements.approved_snapshot_hash,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        except Exception:
            self.cleanup_worktree(binding.worktree_path, force=True)
            raise
        return binding

    def write_design_artifacts(
        self,
        worktree_path: Path,
        change_id: str,
        design: str,
        tasks: str,
    ) -> None:
        change_dir = worktree_path / "openspec" / "changes" / change_id
        change_dir.mkdir(parents=True, exist_ok=True)
        (change_dir / "design.md").write_text(design, encoding="utf-8")
        (change_dir / "tasks.md").write_text(tasks, encoding="utf-8")

    def commit_phase(self, worktree_path: Path, message: str) -> PhaseCommit:
        _git(worktree_path, "add", ".")
        if self._is_dirty(worktree_path):
            _git(worktree_path, "commit", "-m", message)
        return PhaseCommit(head_sha=self._head_sha(worktree_path))

    def build_phase_gate_binding(
        self,
        worktree_path: Path,
        phase: str,
        state_version: int,
        evidence_hash: str,
    ) -> GateBinding:
        if self._is_dirty(worktree_path):
            raise WorkflowValidationError("dirty worktree blocks gate binding")
        return build_gate_binding(
            policy=PhaseCommitPolicy.REQUIRED_BEFORE_HUMAN_GATE,
            phase=phase,
            state_version=state_version,
            branch=self.current_branch(worktree_path),
            head_sha=self._head_sha(worktree_path),
            evidence_hash=evidence_hash,
            clean_worktree=True,
        )

    def verify_gate_binding(self, worktree_path: Path, binding: GateBinding) -> None:
        _validate_worktree_matches_gate_binding(worktree_path, binding)

    def check_base_branch(
        self,
        repo: Path,
        base_branch: str,
        allow_local_base: bool,
        remote: str = "origin",
    ) -> BaseBranchCheck:
        if self._is_dirty(repo):
            return BaseBranchCheck(ok=False, reason="dirty_base")
        if not _git(repo, "branch", "--list", base_branch):
            return BaseBranchCheck(ok=False, reason="missing_base_branch")
        base_commit = _git(repo, "rev-parse", base_branch)
        remote_ref = f"refs/remotes/{remote}/{base_branch}"
        has_remote = bool(_git_optional(repo, "remote", "get-url", remote))
        if not has_remote:
            if allow_local_base:
                return BaseBranchCheck(
                    ok=True,
                    reason="local_base_override",
                    base_commit=base_commit,
                    fetch_failure="missing_remote",
                    override_reason="explicit_local_base_override",
                )
            return BaseBranchCheck(ok=False, reason="remote_unavailable", base_commit=base_commit, fetch_failure="missing_remote")
        if _git_optional(repo, "fetch", remote, base_branch) is None:
            if allow_local_base:
                return BaseBranchCheck(
                    ok=True,
                    reason="local_base_override",
                    base_commit=base_commit,
                    fetch_failure="fetch_failed",
                    override_reason="explicit_local_base_override",
                )
            return BaseBranchCheck(ok=False, reason="remote_unavailable", base_commit=base_commit, fetch_failure="fetch_failed")
        if _git_optional(repo, "rev-parse", "--verify", remote_ref) is None:
            if allow_local_base:
                return BaseBranchCheck(
                    ok=True,
                    reason="local_base_override",
                    base_commit=base_commit,
                    fetch_failure="missing_remote_base",
                    override_reason="explicit_local_base_override",
                )
            return BaseBranchCheck(ok=False, reason="missing_remote_base", base_commit=base_commit, fetch_failure="missing_remote_base")
        remote_commit = _git(repo, "rev-parse", remote_ref)
        if base_commit == remote_commit:
            return BaseBranchCheck(ok=True, base_commit=base_commit, remote_commit=remote_commit)
        if _is_ancestor(repo, base_commit, remote_commit):
            self._fast_forward_branch(repo, base_branch, remote_commit)
            return BaseBranchCheck(ok=True, reason="fast_forwarded", base_commit=remote_commit, remote_commit=remote_commit)
        return BaseBranchCheck(
            ok=False,
            reason="diverged_base",
            base_commit=base_commit,
            remote_commit=remote_commit,
        )

    def cleanup_worktree(self, worktree_path: Path, force: bool = False) -> None:
        if worktree_path.exists():
            if self._is_dirty(worktree_path) and not force:
                raise WorkflowValidationError("dirty worktree cleanup blocked")
            args = ["worktree", "remove"]
            if force:
                args.append("--force")
            args.append(str(worktree_path))
            _git(self.config.canonical_repo, *args)
        resolved_path = worktree_path.resolve()
        for branch, binding in list(self._bindings.items()):
            if binding.worktree_path == resolved_path:
                del self._bindings[branch]

    def binding_for_branch(self, branch: str) -> WorkspaceBinding | None:
        return self._bindings.get(branch)

    def current_branch(self, worktree_path: Path) -> str:
        return _git(worktree_path, "branch", "--show-current")

    def _is_dirty(self, repo: Path) -> bool:
        return bool(_git(repo, "status", "--porcelain"))

    def _head_sha(self, repo: Path) -> str:
        return _git(repo, "rev-parse", "HEAD")

    def _fast_forward_branch(self, repo: Path, base_branch: str, remote_commit: str) -> None:
        if self.current_branch(repo) == base_branch:
            _git(repo, "merge", "--ff-only", remote_commit)
        else:
            _git(repo, "update-ref", f"refs/heads/{base_branch}", remote_commit)


@dataclass(frozen=True)
class SQLiteEventStoreConfig:
    db_path: Path


class SQLiteEventStore:
    def __init__(self, config: SQLiteEventStoreConfig) -> None:
        self.config = config
        self.config.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def append(
        self,
        workflow_id: str,
        event: WorkflowEvent,
        expected_version: int,
    ) -> WorkflowEvent:
        if event.workflow_id != workflow_id:
            raise WorkflowValidationError("workflow id mismatch")
        with sqlite3.connect(self.config.db_path) as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("BEGIN IMMEDIATE")
            current_version = self._current_version(connection, workflow_id)
            if current_version != expected_version:
                raise WorkflowStoreConflict(
                    f"expected version {expected_version}, actual version {current_version}"
                )
            stored_event = replace(
                event,
                version=current_version + 1,
                occurred_at=event.occurred_at or datetime.now(timezone.utc),
            )
            connection.execute(
                """
                INSERT INTO workflow_events (workflow_id, version, payload)
                VALUES (?, ?, ?)
                """,
                (
                    workflow_id,
                    stored_event.version,
                    json.dumps(_event_to_payload(stored_event), sort_keys=True),
                ),
            )
            return stored_event

    def list_events(self, workflow_id: str) -> list[WorkflowEvent]:
        with sqlite3.connect(self.config.db_path) as connection:
            rows = connection.execute(
                """
                SELECT payload FROM workflow_events
                WHERE workflow_id = ?
                ORDER BY version ASC
                """,
                (workflow_id,),
            ).fetchall()
        return [_event_from_payload(json.loads(row[0])) for row in rows]

    def current_version(self, workflow_id: str) -> int:
        with sqlite3.connect(self.config.db_path) as connection:
            return self._current_version(connection, workflow_id)

    def list_workflow_ids(self) -> list[str]:
        with sqlite3.connect(self.config.db_path) as connection:
            rows = connection.execute(
                "SELECT DISTINCT workflow_id FROM workflow_events ORDER BY workflow_id ASC"
            ).fetchall()
        return [str(row[0]) for row in rows]

    def get_lease(self, work_item_id: str) -> Lease | None:
        with sqlite3.connect(self.config.db_path) as connection:
            row = connection.execute(
                """
                SELECT work_item_id, owner_id, expires_at
                FROM workflow_leases
                WHERE work_item_id = ?
                """,
                (work_item_id,),
            ).fetchone()
        if row is None:
            return None
        return Lease(
            lease_id=f"lease:{row[0]}:{row[1]}",
            work_item_id=str(row[0]),
            owner_id=str(row[1]),
            expires_at=datetime.fromisoformat(str(row[2])),
        )

    def save_lease(self, lease: Lease) -> None:
        with sqlite3.connect(self.config.db_path) as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                INSERT INTO workflow_leases (work_item_id, owner_id, expires_at)
                VALUES (?, ?, ?)
                ON CONFLICT(work_item_id) DO UPDATE SET
                    owner_id = excluded.owner_id,
                    expires_at = excluded.expires_at
                """,
                (lease.work_item_id, lease.owner_id, lease.expires_at.isoformat()),
            )

    def delete_lease(self, work_item_id: str) -> None:
        with sqlite3.connect(self.config.db_path) as connection:
            connection.execute(
                "DELETE FROM workflow_leases WHERE work_item_id = ?",
                (work_item_id,),
            )

    def save_requirements_snapshot(
        self,
        workflow_id: str,
        state_version: int,
        draft: RequirementsDraft,
    ) -> RequirementsDraft:
        frozen = draft.freeze() if not draft.frozen else draft
        approved = replace(
            frozen,
            approved_snapshot_version=state_version,
            approved_snapshot_hash=_hash_text(frozen.to_markdown()),
        )
        with sqlite3.connect(self.config.db_path) as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                INSERT INTO workflow_requirements_snapshots
                    (workflow_id, state_version, snapshot_hash, markdown)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(workflow_id, state_version) DO UPDATE SET
                    snapshot_hash = excluded.snapshot_hash,
                    markdown = excluded.markdown
                """,
                (
                    workflow_id,
                    state_version,
                    approved.approved_snapshot_hash,
                    approved.to_markdown(),
                ),
            )
        return approved

    def get_requirements_snapshot(
        self,
        workflow_id: str,
        state_version: int,
    ) -> RequirementsDraft | None:
        with sqlite3.connect(self.config.db_path) as connection:
            row = connection.execute(
                """
                SELECT markdown, snapshot_hash
                FROM workflow_requirements_snapshots
                WHERE workflow_id = ? AND state_version = ?
                """,
                (workflow_id, state_version),
            ).fetchone()
        if row is None:
            return None
        draft = RequirementsDraft.from_markdown(
            str(row[0]),
            approved_snapshot_version=state_version,
        )
        if draft.approved_snapshot_hash != row[1]:
            raise WorkflowValidationError("requirements snapshot hash mismatch")
        return draft

    def _initialize(self) -> None:
        with sqlite3.connect(self.config.db_path) as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA user_version = 1")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS workflow_events (
                    workflow_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    payload TEXT NOT NULL,
                    PRIMARY KEY (workflow_id, version)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS workflow_leases (
                    work_item_id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS workflow_requirements_snapshots (
                    workflow_id TEXT NOT NULL,
                    state_version INTEGER NOT NULL,
                    snapshot_hash TEXT NOT NULL,
                    markdown TEXT NOT NULL,
                    PRIMARY KEY (workflow_id, state_version)
                )
                """
            )

    def _current_version(
        self,
        connection: sqlite3.Connection,
        workflow_id: str,
    ) -> int:
        row = connection.execute(
            "SELECT COALESCE(MAX(version), 0) FROM workflow_events WHERE workflow_id = ?",
            (workflow_id,),
        ).fetchone()
        return int(row[0])


@dataclass(frozen=True)
class WorkflowStatus:
    snapshot: WorkflowSnapshot


@dataclass(frozen=True)
class EnterResult:
    snapshot: WorkflowSnapshot
    work_item: WorkItem | None = None
    lease: Lease | None = None
    waiting_for_human: bool = False
    blocked_reason: str | None = None


@dataclass(frozen=True)
class ReportResult:
    snapshot: WorkflowSnapshot


@dataclass(frozen=True)
class WorkflowOrchestratorConfig:
    store: SQLiteEventStore
    template: PhaseTemplate
    worktree_coordinator: WorktreeCoordinator | None = None


class WorkflowOrchestrator:
    def __init__(self, config: WorkflowOrchestratorConfig) -> None:
        self.config = config
        self._leases: dict[str, Lease] = {}
        self._active_workflows: set[str] = set()

    def status(self, workflow_id: str) -> WorkflowStatus:
        return WorkflowStatus(snapshot=self._snapshot(workflow_id))

    def run_lazy_aging_scan(
        self,
        workflow_id: str,
        outputs: tuple[WorkflowOutput, ...] = (),
        now: datetime | None = None,
        policy: AgingPolicy | None = None,
    ) -> AgingDecision:
        events = self.config.store.list_events(workflow_id)
        if not events:
            return AgingDecision(action=AgingAction.KEEP, reason="workflow_missing")
        already_abandoned = any(event.event_type == EventType.WORKFLOW_ABANDONED for event in events)
        snapshot = replay_history(events, self.config.template)
        last_activity_at = max(
            (event.occurred_at for event in events if event.occurred_at is not None),
            default=now or datetime.now(timezone.utc),
        )
        decision = lazy_aging_scan(
            snapshot=snapshot,
            outputs=outputs,
            last_activity_at=last_activity_at,
            now=now or datetime.now(timezone.utc),
            policy=policy or AgingPolicy(),
            already_abandoned=already_abandoned,
        )
        if decision.action == AgingAction.ABANDON:
            self.config.store.append(
                workflow_id,
                record_workflow_abandoned(workflow_id, reason=decision.reason),
                expected_version=snapshot.version,
            )
        return decision

    def resolve_active_workflow(
        self,
        explicit_workflow_id: str | None = None,
        create_if_missing: bool = False,
    ) -> str:
        if explicit_workflow_id is not None:
            return explicit_workflow_id
        if not self._active_workflows and create_if_missing:
            workflow_id = "exploration-1"
            self.enter(workflow_id, Actor(kind=ActorKind.SYSTEM, actor_id="workflow-control"))
            return workflow_id
        if len(self._active_workflows) == 1:
            return next(iter(self._active_workflows))
        if len(self._active_workflows) > 1:
            raise WorkflowValidationError("multiple active workflows require explicit choice")
        raise WorkflowValidationError("no active workflow")

    def enter(
        self,
        workflow_id: str,
        actor: Actor,
        now: datetime | None = None,
        lease_ttl: timedelta = timedelta(minutes=15),
    ) -> EnterResult:
        if self.config.store.current_version(workflow_id) == 0:
            self.config.store.append(
                workflow_id,
                start_workflow(workflow_id, self.config.template),
                expected_version=0,
            )
        self._active_workflows.add(workflow_id)

        snapshot = self._snapshot(workflow_id)
        if snapshot.state.phase in {"blocked", "abandoned", "done"}:
            return EnterResult(
                snapshot=snapshot,
                waiting_for_human=False,
                blocked_reason=snapshot.state.sub_state,
            )
        phase = self.config.template.phase(snapshot.state.phase)
        if snapshot.state.sub_state == phase.gate_sub_state:
            return EnterResult(
                snapshot=snapshot,
                waiting_for_human=True,
            )

        work_item_id = f"{workflow_id}:{snapshot.version}"
        now = now or datetime.now(timezone.utc)
        existing_lease = self._leases.get(work_item_id) or self.config.store.get_lease(work_item_id)
        if existing_lease is not None and existing_lease.is_active_at(now):
            if existing_lease.owner_id != actor.actor_id:
                return EnterResult(
                    snapshot=snapshot,
                    work_item=None,
                    lease=existing_lease,
                    waiting_for_human=False,
                    blocked_reason="work_item_already_leased",
                )

        lease = Lease(
            lease_id=f"lease:{work_item_id}:{actor.actor_id}",
            work_item_id=work_item_id,
            owner_id=actor.actor_id,
            expires_at=now + lease_ttl,
        )
        self._leases[work_item_id] = lease
        self.config.store.save_lease(lease)
        return EnterResult(
            snapshot=snapshot,
            work_item=WorkItem(
                work_item_id=work_item_id,
                workflow_id=workflow_id,
                state=snapshot.state,
                allowed_actions=("report_work",),
                required_evidence=self._required_evidence(snapshot.state),
                next_action=self._next_action(snapshot.state),
            ),
            lease=lease,
            waiting_for_human=False,
        )

    def block(
        self,
        workflow_id: str,
        actor: Actor,
        reason: str,
    ) -> ReportResult:
        snapshot = self._snapshot(workflow_id)
        self.config.store.append(
            workflow_id,
            WorkflowEvent(
                event_id="workflow-blocked",
                workflow_id=workflow_id,
                event_type=EventType.STATE_ADVANCED,
                actor=actor,
                from_state=snapshot.state,
                to_state=StateSnapshot(phase="blocked", sub_state="blocked"),
                work_result=WorkResult(summary=reason),
            ),
            expected_version=snapshot.version,
        )
        return ReportResult(snapshot=self._snapshot(workflow_id))

    def rollback(
        self,
        workflow_id: str,
        actor: Actor,
        phase: str,
        sub_state: str,
    ) -> ReportResult:
        snapshot = self._snapshot(workflow_id)
        self.config.store.append(
            workflow_id,
            WorkflowEvent(
                event_id="workflow-rollback",
                workflow_id=workflow_id,
                event_type=EventType.STATE_ADVANCED,
                actor=actor,
                from_state=snapshot.state,
                to_state=StateSnapshot(phase=phase, sub_state=sub_state),
            ),
            expected_version=snapshot.version,
        )
        return ReportResult(snapshot=self._snapshot(workflow_id))

    def skip(self, workflow_id: str, actor: Actor) -> ReportResult:
        snapshot = self._snapshot(workflow_id)
        self.config.store.append(
            workflow_id,
            record_work_completed(workflow_id, actor, WorkResult(summary="skip")),
            expected_version=snapshot.version,
        )
        return ReportResult(snapshot=self._snapshot(workflow_id))

    def release_lease(self, lease_id: str) -> None:
        for work_item_id, lease in list(self._leases.items()):
            if lease.lease_id == lease_id:
                del self._leases[work_item_id]
                self.config.store.delete_lease(work_item_id)
                return

    def record_review_result(
        self,
        workflow_id: str,
        actor: Actor,
        review_result: ReviewResult,
        executor_run_id: str,
    ) -> ReportResult:
        snapshot = self._snapshot(workflow_id)
        if snapshot.state.phase != "code-review" or snapshot.state.sub_state != "reviewing_code":
            raise WorkflowValidationError("review result requires review state")
        self.config.store.append(
            workflow_id,
            record_review_result(workflow_id, actor, review_result, executor_run_id),
            expected_version=snapshot.version,
        )
        return ReportResult(snapshot=self._snapshot(workflow_id))

    def report(
        self,
        workflow_id: str,
        actor: Actor,
        work_item_id: str,
        result: WorkResult,
        expected_version: int,
    ) -> ReportResult:
        expected_work_item_id = f"{workflow_id}:{expected_version}"
        if work_item_id != expected_work_item_id:
            raise WorkflowValidationError("stale work item")
        lease = self._leases.get(work_item_id)
        lease = lease or self.config.store.get_lease(work_item_id)
        if lease is None or not lease.is_active_at(datetime.now(timezone.utc)):
            raise WorkflowValidationError("active lease required")
        if lease.owner_id != actor.actor_id:
            raise WorkflowValidationError("lease owner mismatch")
        try:
            self.config.store.append(
                workflow_id,
                record_work_completed(workflow_id, actor, result),
                expected_version=expected_version,
            )
        except WorkflowStoreConflict as exc:
            raise WorkflowValidationError("stale work item") from exc
        self.config.store.delete_lease(work_item_id)
        self._leases.pop(work_item_id, None)
        snapshot = self._snapshot(workflow_id)
        if snapshot.state.phase not in {"blocked", "abandoned"}:
            phase = self.config.template.phase(snapshot.state.phase)
            if snapshot.state.sub_state != phase.gate_sub_state:
                next_lease = Lease(
                    lease_id=f"lease:{workflow_id}:{snapshot.version}:{actor.actor_id}",
                    work_item_id=f"{workflow_id}:{snapshot.version}",
                    owner_id=actor.actor_id,
                    expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
                )
                self._leases[next_lease.work_item_id] = next_lease
                self.config.store.save_lease(next_lease)
        return ReportResult(snapshot=snapshot)

    def current_gate(self, workflow_id: str) -> Gate:
        snapshot = self._snapshot(workflow_id)
        phase = self.config.template.phase(snapshot.state.phase)
        if snapshot.state.sub_state != phase.gate_sub_state:
            raise WorkflowValidationError("workflow is not at a gate")
        return _gate_for_state(workflow_id, snapshot.state, snapshot.version)

    def current_gate_for_binding(self, workflow_id: str, binding: GateBinding) -> Gate:
        snapshot = self._snapshot(workflow_id)
        phase = self.config.template.phase(snapshot.state.phase)
        if snapshot.state.sub_state != phase.gate_sub_state:
            raise WorkflowValidationError("workflow is not at a gate")
        if binding.phase != snapshot.state.phase or binding.state_version != snapshot.version:
            raise WorkflowValidationError("gate binding does not match current state")
        return Gate(
            gate_id=f"{workflow_id}:{snapshot.state.phase}:{snapshot.version}",
            workflow_id=workflow_id,
            phase=snapshot.state.phase,
            state_version=snapshot.version,
            gate_summary_hash=binding.gate_summary_hash,
            head_sha=binding.head_sha,
        )

    def approve_gate(
        self,
        workflow_id: str,
        expected_version: int,
        actor: Actor | None = None,
        raw_user_message: str | None = None,
        approval: Approval | None = None,
        gate_binding: GateBinding | None = None,
        worktree_path: Path | None = None,
        requirements_draft: RequirementsDraft | None = None,
        change_id: str | None = None,
        date: str | None = None,
        base_branch: str = "master",
        allow_local_base: bool = False,
    ) -> ReportResult:
        if self.config.store.current_version(workflow_id) != expected_version:
            raise WorkflowStoreConflict(
                f"expected version {expected_version}, actual version {self.config.store.current_version(workflow_id)}"
            )
        snapshot = self._snapshot(workflow_id)
        phase = self.config.template.phase(snapshot.state.phase)
        if phase.commit_policy != PhaseCommitPolicy.NONE:
            if gate_binding is None or worktree_path is None:
                raise WorkflowValidationError("gate approval requires committed gate binding")
            _validate_worktree_matches_gate_binding(worktree_path, gate_binding)
        gate = (
            self.current_gate_for_binding(workflow_id, gate_binding)
            if gate_binding is not None
            else self.current_gate(workflow_id)
        )
        if approval is None:
            if actor is None or raw_user_message is None:
                raise WorkflowValidationError("gate approval requires approval or actor/message")
            approval = gate.approve(
                actor=actor,
                decision=ApprovalDecision.APPROVED,
                client_id="trusted-host",
                user_message_hash=_hash_text(raw_user_message),
            )
        HostApprovalService.validate_approval_for_gate(approval, gate)
        try:
            workspace_binding = self._promote_requirements_gate(
                snapshot=snapshot,
                requirements_draft=requirements_draft,
                change_id=change_id,
                date=date,
                base_branch=base_branch,
                allow_local_base=allow_local_base,
            )
        except Exception as exc:
            if snapshot.state.phase != "requirements":
                raise
            self.config.store.append(
                workflow_id,
                WorkflowEvent(
                    event_id="workflow-blocked",
                    workflow_id=workflow_id,
                    event_type=EventType.STATE_ADVANCED,
                    actor=Actor(kind=ActorKind.SYSTEM, actor_id="workflow-control"),
                    from_state=snapshot.state,
                    to_state=StateSnapshot(phase="blocked", sub_state="blocked"),
                    work_result=WorkResult(summary=str(exc)),
                ),
                expected_version=expected_version,
            )
            return ReportResult(snapshot=self._snapshot(workflow_id))
        try:
            self.config.store.append(
                workflow_id,
                record_gate_approved(
                    workflow_id,
                    approval.actor,
                    raw_user_message=raw_user_message,
                    approval=approval,
                    workspace_binding=workspace_binding,
                ),
                expected_version=expected_version,
            )
        except Exception:
            if workspace_binding is not None and self.config.worktree_coordinator is not None:
                self.config.worktree_coordinator.cleanup_worktree(workspace_binding.worktree_path, force=True)
            raise
        if snapshot.state.phase == "closing" and worktree_path is not None and self.config.worktree_coordinator is not None:
            self.config.worktree_coordinator.cleanup_worktree(worktree_path, force=True)
        return ReportResult(snapshot=self._snapshot(workflow_id))

    def _promote_requirements_gate(
        self,
        snapshot: WorkflowSnapshot,
        requirements_draft: RequirementsDraft | None,
        change_id: str | None,
        date: str | None,
        base_branch: str,
        allow_local_base: bool,
    ) -> WorkspaceBinding | None:
        if snapshot.state.phase != "requirements":
            return None
        if self.config.worktree_coordinator is None:
            return None
        if requirements_draft is None or change_id is None or date is None:
            raise WorkflowValidationError("requirements gate approval requires promotion inputs")
        if (
            requirements_draft.approved_snapshot_version != snapshot.version
            or requirements_draft.approved_snapshot_hash is None
        ):
            raise WorkflowValidationError("requirements gate approval requires approved snapshot binding")
        stored_snapshot = self.config.store.get_requirements_snapshot(
            snapshot.workflow_id,
            snapshot.version,
        )
        if stored_snapshot is None:
            raise WorkflowValidationError("approved requirements snapshot not found")
        if stored_snapshot.approved_snapshot_hash != requirements_draft.approved_snapshot_hash:
            raise WorkflowValidationError("approved requirements snapshot mismatch")
        return self.config.worktree_coordinator.promote_requirements(
            change_id=change_id,
            approved_requirements=stored_snapshot,
            date=date,
            base_branch=base_branch,
            allow_local_base=allow_local_base,
        )

    def _snapshot(self, workflow_id: str) -> WorkflowSnapshot:
        events = self.config.store.list_events(workflow_id)
        if not events:
            raise WorkflowValidationError("workflow has no events")
        return replay_history(events, self.config.template)

    def _required_evidence(self, state: StateSnapshot) -> tuple[Evidence, ...]:
        if state.phase == "exploring":
            return (Evidence(ref="goal_candidate", kind="workflow_output"),)
        if state.phase == "building":
            return (Evidence(ref="test_result", kind="test_result"),)
        return ()

    def _next_action(self, state: StateSnapshot) -> str:
        if state.phase == "exploring":
            return "chat_until_goal_candidate"
        if state.sub_state == "ready_for_review":
            return "wait_for_human"
        return "execute_sub_state"


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


def retain_output(output: WorkflowOutput) -> WorkflowOutput:
    return replace(output, status=OutputStatus.DURABLE)


def accept_outputs(
    outputs: tuple[WorkflowOutput, ...],
    refs: tuple[str, ...],
) -> tuple[WorkflowOutput, ...]:
    accepted_refs = set(refs)
    return tuple(
        retain_output(output) if output.ref in accepted_refs else output
        for output in outputs
    )


@dataclass(frozen=True)
class AgingPolicy:
    ttl: timedelta = timedelta(hours=24)


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
    codex_reviewer = RunnerProfile(
        name="codex-reviewer",
        command="codex",
        args=("exec", "--json"),
        prompt_mode="stdin",
        permissions="read-only",
        timeout_seconds=600,
    )
    return PhaseTemplate(
        template_id="coding-agent-conversation-delivery-v1",
        phases=(
            ("exploring", ("chatting",), PhaseCommitPolicy.NONE.value),
            ("requirements", ("drafting", "ready_for_review"), PhaseCommitPolicy.NONE.value),
            ("design", ("writing_design", "ready_for_review"), PhaseCommitPolicy.REQUIRED_BEFORE_HUMAN_GATE.value),
            ("building", ("writing_tests", "implementing", "ready_for_review"), PhaseCommitPolicy.REQUIRED_BEFORE_HUMAN_GATE.value),
            PhaseDefinition(
                phase="code-review",
                sub_states=("reviewing_code", "ready_for_review"),
                commit_policy=PhaseCommitPolicy.REQUIRED_BEFORE_HUMAN_GATE,
                executor_lane=ExecutorLane(
                    mode=ExecutorMode.RUNNER,
                    runner_profile="codex-reviewer",
                ),
                review_lane=ReviewLane(
                    reviewers=(
                        ReviewerDefinition(
                            name="codex-reviewer",
                            mode=ReviewerMode.RUNNER,
                            runner_profile="codex-reviewer",
                            fresh_context=True,
                        ),
                    ),
                ),
            ),
            ("closing", ("archiving", "ready_for_review"), PhaseCommitPolicy.REQUIRED_BEFORE_HUMAN_GATE.value),
            ("done", ("done",), PhaseCommitPolicy.NONE.value),
        ),
        initial_state=StateSnapshot(phase="exploring", sub_state="chatting"),
        runner_profiles=(codex_reviewer,),
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
    approval: Approval | None = None,
    workspace_binding: WorkspaceBinding | None = None,
) -> WorkflowEvent:
    return WorkflowEvent(
        event_id="gate-approved",
        workflow_id=workflow_id,
        event_type=EventType.GATE_APPROVED,
        actor=actor,
        raw_user_message=raw_user_message,
        approval=approval,
        workspace_binding=workspace_binding,
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


def record_workflow_abandoned(
    workflow_id: str,
    reason: str,
    now: datetime | None = None,
) -> WorkflowEvent:
    return WorkflowEvent(
        event_id="workflow-abandoned",
        workflow_id=workflow_id,
        event_type=EventType.WORKFLOW_ABANDONED,
        actor=Actor(kind=ActorKind.SYSTEM, actor_id="workflow-control"),
        work_result=WorkResult(summary=reason),
        occurred_at=now,
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
            _validate_gate_approval(event, current_state, workflow_id, version)
            current_state = _advance_from_gate(current_state, template)
        elif event.event_type == EventType.REVIEW_RESULT_RECORDED:
            if event.executor_run_id == event.actor.actor_id:
                raise WorkflowValidationError("self review is not allowed")
            if current_state is None:
                raise WorkflowValidationError("workflow must start before review result")
            if current_state.phase != "code-review" or current_state.sub_state != "reviewing_code":
                raise WorkflowValidationError("review result requires review state")
            if event.review_result == ReviewResult.CHANGES_REQUESTED:
                current_state = StateSnapshot(
                    phase="building",
                    sub_state=template.phase("building").first_sub_state,
                )
        elif event.event_type == EventType.WORKFLOW_ABANDONED:
            if current_state is None:
                raise WorkflowValidationError("workflow must start before abandonment")
            if current_state.phase != "exploring":
                raise WorkflowValidationError("only exploration workflow can be abandoned")
            current_state = StateSnapshot(phase="abandoned", sub_state="abandoned")
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


def replay_history(
    events: list[WorkflowEvent],
    template: PhaseTemplate,
) -> WorkflowSnapshot:
    for expected_version, event in enumerate(events, start=1):
        if event.version != expected_version:
            raise WorkflowHistoryCorrupt("event stream has non-contiguous versions")
    return reduce_events(events, template)


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
    if event.to_state.phase == "blocked" or current_state.phase == "blocked":
        return event.to_state
    if event.event_id == "workflow-rollback":
        target_phase = template.phase(event.to_state.phase)
        if event.to_state.sub_state not in target_phase.sub_states:
            raise WorkflowValidationError("rollback target sub_state is not in phase")
        return event.to_state
    if not template.is_legal_transition(current_state, event.to_state):
        raise WorkflowValidationError("illegal transition")
    return event.to_state


def _validate_gate_approval(
    event: WorkflowEvent,
    current_state: StateSnapshot | None,
    workflow_id: str | None,
    version: int,
) -> None:
    if event.actor.kind != ActorKind.HUMAN or not event.actor.approval_capability:
        raise WorkflowValidationError("gate approval requires human approval capability")
    if current_state is None or workflow_id is None:
        raise WorkflowValidationError("workflow must start before gate approval")
    if event.approval is None:
        raise WorkflowValidationError("missing gate approval binding")
    state_gate = _gate_for_state(workflow_id, current_state, version)
    if event.approval.matches_gate(state_gate):
        return
    if (
        event.approval.workflow_id != workflow_id
        or event.approval.gate_id != state_gate.gate_id
        or event.approval.phase != current_state.phase
        or event.approval.state_version != version
        or not event.approval.gate_summary_hash.startswith("sha256:")
    ):
        raise WorkflowValidationError("stale approval")


def _event_to_payload(event: WorkflowEvent) -> dict[str, Any]:
    return {
        "event_id": event.event_id,
        "workflow_id": event.workflow_id,
        "event_type": event.event_type.value,
        "actor": {
            "kind": event.actor.kind.value,
            "actor_id": event.actor.actor_id,
            "approval_capability": event.actor.approval_capability,
        },
        "version": event.version,
        "from_state": _state_to_payload(event.from_state),
        "to_state": _state_to_payload(event.to_state),
        "work_result": _work_result_to_payload(event.work_result),
        "review_result": event.review_result.value if event.review_result is not None else None,
        "executor_run_id": event.executor_run_id,
        "raw_user_message": event.raw_user_message,
        "approval": _approval_to_payload(event.approval),
        "occurred_at": event.occurred_at.isoformat() if event.occurred_at is not None else None,
        "workspace_binding": _workspace_binding_to_payload(event.workspace_binding),
    }


def _event_from_payload(payload: dict[str, Any]) -> WorkflowEvent:
    review_result = payload.get("review_result")
    return WorkflowEvent(
        event_id=payload["event_id"],
        workflow_id=payload["workflow_id"],
        event_type=EventType(payload["event_type"]),
        actor=Actor(
            kind=ActorKind(payload["actor"]["kind"]),
            actor_id=payload["actor"]["actor_id"],
            approval_capability=payload["actor"]["approval_capability"],
        ),
        version=payload["version"],
        from_state=_state_from_payload(payload.get("from_state")),
        to_state=_state_from_payload(payload.get("to_state")),
        work_result=_work_result_from_payload(payload.get("work_result")),
        review_result=ReviewResult(review_result) if review_result else None,
        executor_run_id=payload.get("executor_run_id"),
        raw_user_message=payload.get("raw_user_message"),
        approval=_approval_from_payload(payload.get("approval")),
        occurred_at=(
            datetime.fromisoformat(payload["occurred_at"])
            if payload.get("occurred_at") is not None
            else None
        ),
        workspace_binding=_workspace_binding_from_payload(payload.get("workspace_binding")),
    )


def _state_to_payload(state: StateSnapshot | None) -> dict[str, str] | None:
    if state is None:
        return None
    return {"phase": state.phase, "sub_state": state.sub_state}


def _state_from_payload(payload: dict[str, str] | None) -> StateSnapshot | None:
    if payload is None:
        return None
    return StateSnapshot(phase=payload["phase"], sub_state=payload["sub_state"])


def _work_result_to_payload(work_result: WorkResult | None) -> dict[str, Any] | None:
    if work_result is None:
        return None
    return {
        "output_refs": list(work_result.output_refs),
        "evidence_refs": list(work_result.evidence_refs),
        "summary": work_result.summary,
    }


def _work_result_from_payload(payload: dict[str, Any] | None) -> WorkResult | None:
    if payload is None:
        return None
    return WorkResult(
        output_refs=tuple(payload["output_refs"]),
        evidence_refs=tuple(payload["evidence_refs"]),
        summary=payload["summary"],
    )


def _approval_to_payload(approval: Approval | None) -> dict[str, Any] | None:
    if approval is None:
        return None
    return {
        "workflow_id": approval.workflow_id,
        "gate_id": approval.gate_id,
        "phase": approval.phase,
        "state_version": approval.state_version,
        "decision": approval.decision.value,
        "actor": {
            "kind": approval.actor.kind.value,
            "actor_id": approval.actor.actor_id,
            "approval_capability": approval.actor.approval_capability,
        },
        "client_id": approval.client_id,
        "user_message_hash": approval.user_message_hash,
        "gate_summary_hash": approval.gate_summary_hash,
        "head_sha": approval.head_sha,
    }


def _approval_from_payload(payload: dict[str, Any] | None) -> Approval | None:
    if payload is None:
        return None
    return Approval(
        workflow_id=payload["workflow_id"],
        gate_id=payload["gate_id"],
        phase=payload["phase"],
        state_version=payload["state_version"],
        decision=ApprovalDecision(payload["decision"]),
        actor=Actor(
            kind=ActorKind(payload["actor"]["kind"]),
            actor_id=payload["actor"]["actor_id"],
            approval_capability=payload["actor"]["approval_capability"],
        ),
        client_id=payload["client_id"],
        user_message_hash=payload["user_message_hash"],
        gate_summary_hash=payload["gate_summary_hash"],
        head_sha=payload.get("head_sha"),
    )


def _workspace_binding_to_payload(binding: WorkspaceBinding | None) -> dict[str, Any] | None:
    if binding is None:
        return None
    return {
        "workflow_id": binding.workflow_id,
        "branch": binding.branch,
        "worktree_path": str(binding.worktree_path),
        "head_sha": binding.head_sha,
        "base_branch": binding.base_branch,
        "base_commit": binding.base_commit,
        "base_check": binding.base_check,
        "fetch_failure": binding.fetch_failure,
        "override_reason": binding.override_reason,
    }


def _workspace_binding_from_payload(payload: dict[str, Any] | None) -> WorkspaceBinding | None:
    if payload is None:
        return None
    return WorkspaceBinding(
        workflow_id=payload["workflow_id"],
        branch=payload["branch"],
        worktree_path=Path(payload["worktree_path"]),
        head_sha=payload["head_sha"],
        base_branch=payload.get("base_branch"),
        base_commit=payload.get("base_commit"),
        base_check=payload.get("base_check"),
        fetch_failure=payload.get("fetch_failure"),
        override_reason=payload.get("override_reason"),
    )


def _section_from_markdown(markdown: str, heading: str) -> str:
    marker = f"## {heading}"
    lines = markdown.splitlines()
    for index, line in enumerate(lines):
        if line.strip() != marker:
            continue
        collected: list[str] = []
        for section_line in lines[index + 1:]:
            if section_line.startswith("## "):
                break
            collected.append(section_line)
        return "\n".join(collected).strip()
    return ""


def _requirements_to_spec_delta(draft: RequirementsDraft) -> str:
    title = draft.goal.strip() or "Approved Requirements Snapshot"
    body = draft.acceptance.strip() or draft.scope.strip() or draft.test_strategy.strip()
    if not body:
        body = "The system SHALL implement the approved requirements snapshot for this change."
    return "\n".join([
        "## ADDED Requirements",
        "",
        f"### Requirement: {title}",
        "",
        body,
        "",
        "#### Scenario: Approved Snapshot Is Materialized",
        "",
        f"- **GIVEN** approved requirements snapshot `{draft.approved_snapshot_hash}`",
        "- **WHEN** the requirements gate is approved",
        "- **THEN** the change artifacts SHALL be materialized from that snapshot",
        "",
    ])


def project_event_store_path(repo_root: Path, data_root: Path) -> Path:
    canonical_repo = repo_root.resolve()
    digest = hashlib.sha256(str(canonical_repo).encode("utf-8")).hexdigest()[:16]
    return data_root.resolve() / digest / "workflow.sqlite3"


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


def lazy_aging_scan(
    snapshot: WorkflowSnapshot,
    outputs: tuple[WorkflowOutput, ...],
    last_activity_at: datetime,
    now: datetime,
    policy: AgingPolicy,
    already_abandoned: bool,
) -> AgingDecision:
    if already_abandoned:
        return AgingDecision(action=AgingAction.KEEP, reason="already_abandoned")
    return evaluate_exploration_aging(
        snapshot=snapshot,
        outputs=outputs,
        last_activity_at=last_activity_at,
        now=now,
        policy=policy,
    )


def build_gate_binding(
    policy: PhaseCommitPolicy | str,
    phase: str,
    state_version: int,
    branch: str,
    head_sha: str,
    evidence_hash: str,
    clean_worktree: bool,
) -> GateBinding | None:
    resolved_policy = PhaseCommitPolicy(policy)
    if resolved_policy == PhaseCommitPolicy.NONE:
        return None
    if not clean_worktree:
        raise WorkflowValidationError("phase gate requires clean worktree")
    payload = {
        "branch": branch,
        "evidence_hash": evidence_hash,
        "head_sha": head_sha,
        "phase": phase,
        "state_version": state_version,
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return GateBinding(
        phase=phase,
        state_version=state_version,
        branch=branch,
        head_sha=head_sha,
        evidence_hash=evidence_hash,
        gate_summary_hash=f"sha256:{digest}",
    )


def _validate_worktree_matches_gate_binding(worktree_path: Path, binding: GateBinding) -> None:
    if bool(_git(worktree_path, "status", "--porcelain")):
        raise WorkflowValidationError("dirty worktree blocks gate approval")
    current_branch = _git(worktree_path, "branch", "--show-current")
    if current_branch != binding.branch:
        raise WorkflowValidationError("worktree branch drift")
    head_sha = _git(worktree_path, "rev-parse", "HEAD")
    if head_sha != binding.head_sha:
        raise WorkflowValidationError("worktree head drift")


def _gate_for_state(workflow_id: str, state: StateSnapshot, state_version: int) -> Gate:
    gate_summary_hash = _hash_text(
        json.dumps(
            {
                "workflow_id": workflow_id,
                "phase": state.phase,
                "sub_state": state.sub_state,
                "state_version": state_version,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return Gate(
        gate_id=f"{workflow_id}:{state.phase}:{state_version}",
        workflow_id=workflow_id,
        phase=state.phase,
        state_version=state_version,
        gate_summary_hash=gate_summary_hash,
    )


def _hash_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


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


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.stdout.strip()


def _git_optional(cwd: Path, *args: str) -> str | None:
    try:
        return _git(cwd, *args)
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None


def _is_ancestor(cwd: Path, ancestor: str, descendant: str) -> bool:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.returncode == 0


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
    "BaseBranchCheck",
    "CapabilityPolicy",
    "Evidence",
    "EventType",
    "ExecutorLane",
    "ExecutorMode",
    "Gate",
    "GateBinding",
    "GateEventType",
    "GateApprovalTokenMatcher",
    "HostApprovalResult",
    "HostApprovalService",
    "Lease",
    "ManagedWorkspaceConfig",
    "OutputStatus",
    "PhaseCommit",
    "PhaseCommitPolicy",
    "PhaseDefinition",
    "PhaseTemplate",
    "ReviewResult",
    "ReviewLane",
    "ReviewerDefinition",
    "ReviewerMode",
    "RequirementsDraft",
    "EnterResult",
    "ReportResult",
    "RunnerProfile",
    "SessionBinding",
    "SessionBindingRegistry",
    "SQLiteEventStore",
    "SQLiteEventStoreConfig",
    "StateSnapshot",
    "WorkResult",
    "WorkItem",
    "WorktreeCoordinator",
    "WorktreeCoordinatorConfig",
    "WorkflowEvent",
    "WorkflowActivationGate",
    "WorkflowOutput",
    "WorkflowOrchestrator",
    "WorkflowOrchestratorConfig",
    "WorkflowSnapshot",
    "WorkflowStatus",
    "WorkflowHistoryCorrupt",
    "WorkspaceWritePolicy",
    "WorkspaceBinding",
    "WorkflowStoreConflict",
    "WorkflowValidationError",
    "accept_outputs",
    "build_gate_binding",
    "default_coding_agent_template",
    "evaluate_exploration_aging",
    "lazy_aging_scan",
    "project_event_store_path",
    "record_gate_approved",
    "record_review_result",
    "record_work_completed",
    "reduce_events",
    "replay_history",
    "retain_output",
    "start_workflow",
]
