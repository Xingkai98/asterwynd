from __future__ import annotations

import pytest

from workflow_control import (
    ExecutorLane,
    ExecutorMode,
    PhaseDefinition,
    PhaseTemplate,
    ReviewLane,
    ReviewerDefinition,
    ReviewerMode,
    RunnerProfile,
    StateSnapshot,
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
