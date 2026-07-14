from __future__ import annotations

import pytest

from workflow_control import (
    Actor,
    ActorKind,
    CommandReviewAdapter,
    ExecutorLane,
    ExecutorMode,
    PhaseDefinition,
    PhaseTemplate,
    ReviewLane,
    ReviewerDefinition,
    ReviewerMode,
    RunnerProfile,
    SQLiteEventStore,
    SQLiteEventStoreConfig,
    StateSnapshot,
    WorkflowOrchestrator,
    WorkflowOrchestratorConfig,
    WorkflowValidationError,
    default_coding_agent_template,
)


def test_default_template_declares_executor_and_review_lanes() -> None:
    template = default_coding_agent_template()

    building = template.phase("building")
    code_review = template.phase("code-review")

    assert building.executor_lane.mode == ExecutorMode.SELF
    assert code_review.executor_lane.mode == ExecutorMode.RUNNER
    assert code_review.review_lane.reviewers[0].mode == ReviewerMode.RUNNER
    assert code_review.review_lane.reviewers[0].fresh_context is True


def test_review_lane_rejects_self_reviewer() -> None:
    with pytest.raises(WorkflowValidationError, match="reviewer cannot use self"):
        ReviewLane(
            reviewers=(
                ReviewerDefinition(
                    name="bad-self-reviewer",
                    mode="self",
                ),
            ),
        )


def test_runner_profile_captures_command_permissions_and_timeout() -> None:
    profile = RunnerProfile(
        name="codex-reviewer",
        command="codex",
        args=("exec", "--json"),
        prompt_mode="stdin",
        permissions="read-only",
        timeout_seconds=300,
    )

    assert profile.command == "codex"
    assert profile.permissions == "read-only"
    assert profile.timeout_seconds == 300


def test_phase_template_exposes_runner_profiles_by_name() -> None:
    profile = RunnerProfile(
        name="command-reviewer",
        command="python3",
        args=("scripts/check.py",),
        prompt_mode="none",
        permissions="read-only",
        timeout_seconds=60,
    )
    template = PhaseTemplate(
        template_id="with-runners",
        phases=(
            PhaseDefinition(
                phase="design",
                sub_states=("writing", "ready_for_review"),
                executor_lane=ExecutorLane(mode=ExecutorMode.SELF),
                review_lane=ReviewLane(
                    reviewers=(
                        ReviewerDefinition(
                            name="checker",
                            mode=ReviewerMode.COMMAND,
                            runner_profile="command-reviewer",
                        ),
                    ),
                ),
            ),
        ),
        initial_state=StateSnapshot(phase="design", sub_state="writing"),
        runner_profiles=(profile,),
    )

    assert template.runner_profile("command-reviewer") == profile


def test_command_review_adapter_records_fresh_review_result(tmp_path) -> None:
    orchestrator = WorkflowOrchestrator(
        WorkflowOrchestratorConfig(
            store=SQLiteEventStore(SQLiteEventStoreConfig(db_path=tmp_path / "workflow.sqlite3")),
            template=default_coding_agent_template(),
        )
    )
    actor = Actor(kind=ActorKind.AGENT, actor_id="agent")
    orchestrator.enter("workflow-1", actor)
    orchestrator.rollback("workflow-1", actor, "code-review", "reviewing_code")
    profile = RunnerProfile(
        name="command-reviewer",
        command="python3",
        args=("-c", "print('pass')"),
        permissions="read-only",
    )

    result = CommandReviewAdapter(orchestrator, profile).run("workflow-1", prompt="review")

    assert result.snapshot.state.phase == "code-review"
    assert result.snapshot.state.sub_state == "ready_for_review"


def test_command_review_adapter_requires_read_only_profile(tmp_path) -> None:
    orchestrator = WorkflowOrchestrator(
        WorkflowOrchestratorConfig(
            store=SQLiteEventStore(SQLiteEventStoreConfig(db_path=tmp_path / "workflow.sqlite3")),
            template=default_coding_agent_template(),
        )
    )

    with pytest.raises(WorkflowValidationError, match="read-only"):
        CommandReviewAdapter(
            orchestrator,
            RunnerProfile(
                name="writer",
                command="python3",
                permissions="workspace-write",
            ),
        )
