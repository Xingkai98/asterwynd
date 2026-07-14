from __future__ import annotations

import json

import pytest

from workflow_control import (
    Actor,
    ActorKind,
    CommandReviewAdapter,
    CommandWorkflowExecutor,
    ExecutorLane,
    ExecutorMode,
    PhaseDefinition,
    PhaseTemplate,
    ReviewContext,
    ReviewDispatchPlan,
    ReviewLane,
    ReviewResult,
    ReviewerDefinition,
    ReviewerMode,
    RunnerProfile,
    SQLiteEventStore,
    SQLiteEventStoreConfig,
    StateSnapshot,
    WorkflowOrchestrator,
    WorkflowOrchestratorConfig,
    WorkflowValidationError,
    build_executor_prompt,
    build_review_dispatch_plan,
    build_review_prompt,
    default_coding_agent_template,
    dispatch_review,
    sanitized_executor_env,
)


def test_default_template_declares_executor_and_review_lanes() -> None:
    template = default_coding_agent_template()

    building = template.phase("building")
    code_review = template.phase("code-review")

    assert building.executor_lane.mode == ExecutorMode.SELF
    assert code_review.executor_lane.mode == ExecutorMode.RUNNER
    assert code_review.review_lane.reviewers[0].mode == ReviewerMode.RUNNER
    assert code_review.review_lane.reviewers[0].fresh_context is True
    assert template.runner_profile("codex-reviewer").permissions == "read-only"
    assert template.runner_profile("claude-code-reviewer").permissions == "read-only"
    assert template.runner_profile("command-reviewer").permissions == "read-only"
    assert template.runner_profile("codex-reviewer").approval_policy == "never"
    assert template.runner_profile("claude-code-reviewer").approval_policy == "never"
    assert template.runner_profile("command-reviewer").approval_policy == "never"


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


def test_command_review_adapter_requires_never_approval_policy(tmp_path) -> None:
    store = SQLiteEventStore(SQLiteEventStoreConfig(db_path=tmp_path / "workflow.sqlite3"))
    orchestrator = WorkflowOrchestrator(
        WorkflowOrchestratorConfig(store=store, template=default_coding_agent_template()),
    )

    with pytest.raises(WorkflowValidationError, match="approval policy"):
        CommandReviewAdapter(
            orchestrator,
            RunnerProfile(
                name="command-reviewer",
                command="python3",
                permissions="read-only",
                approval_policy="on-request",
            ),
        )


def test_sanitized_executor_env_removes_approval_capability() -> None:
    env = sanitized_executor_env(
        {
            "ASTERWYND_WORKFLOW_TRUSTED_HOST": "1",
            "ASTERWYND_WORKFLOW_APPROVAL_SECRET": "secret",
            "KEEP": "value",
        },
    )

    assert env["ASTERWYND_WORKFLOW_AGENT_CONTEXT"] == "1"
    assert env["KEEP"] == "value"
    assert "ASTERWYND_WORKFLOW_TRUSTED_HOST" not in env
    assert "ASTERWYND_WORKFLOW_APPROVAL_SECRET" not in env


def test_review_prompt_contains_minimal_fresh_context() -> None:
    context = ReviewContext(
        workflow_id="workflow-1",
        state=StateSnapshot(phase="code-review", sub_state="reviewing_code"),
        design_refs=("openspec/changes/x/design.md",),
        diff_summary="diff --stat",
        test_summary="pytest passed",
        evidence_refs=("test_result",),
        workflow_context="building gate passed",
    )

    prompt = build_review_prompt(context)

    assert "openspec/changes/x/design.md" in prompt
    assert "diff --stat" in prompt
    assert "pytest passed" in prompt
    assert "test_result" in prompt
    assert "building gate passed" in prompt


def test_review_dispatch_plan_supports_subagent_runner_and_command_modes() -> None:
    context = ReviewContext(
        workflow_id="workflow-1",
        state=StateSnapshot(phase="code-review", sub_state="reviewing_code"),
    )
    profile = RunnerProfile(
        name="command-reviewer",
        command="python3",
        permissions="read-only",
    )

    subagent_plan = build_review_dispatch_plan(
        ReviewerDefinition(name="subagent", mode=ReviewerMode.SUBAGENT),
        profiles=(profile,),
        context=context,
    )
    command_plan = build_review_dispatch_plan(
        ReviewerDefinition(
            name="command",
            mode=ReviewerMode.COMMAND,
            runner_profile="command-reviewer",
        ),
        profiles=(profile,),
        context=context,
    )

    assert isinstance(subagent_plan, ReviewDispatchPlan)
    assert subagent_plan.mode == ReviewerMode.SUBAGENT
    assert subagent_plan.runner_profile is None
    assert command_plan.mode == ReviewerMode.COMMAND
    assert command_plan.runner_profile == profile
    assert command_plan.fresh_context is True


def test_dispatch_review_records_subagent_result_with_fresh_context(tmp_path) -> None:
    store = SQLiteEventStore(SQLiteEventStoreConfig(db_path=tmp_path / "workflow.sqlite3"))
    template = PhaseTemplate(
        template_id="review-only",
        phases=(
            PhaseDefinition(
                phase="code-review",
                sub_states=("reviewing_code", "ready_for_review"),
            ),
        ),
        initial_state=StateSnapshot(phase="code-review", sub_state="reviewing_code"),
    )
    orchestrator = WorkflowOrchestrator(
        WorkflowOrchestratorConfig(store=store, template=template),
    )
    workflow_id = "workflow-1"
    orchestrator.enter(workflow_id, Actor(kind=ActorKind.AGENT, actor_id="executor"))

    result = dispatch_review(
        orchestrator,
        ReviewerDefinition(name="subagent-reviewer", mode=ReviewerMode.SUBAGENT),
        profiles=(),
        context=ReviewContext(
            workflow_id=workflow_id,
            state=StateSnapshot(phase="code-review", sub_state="reviewing_code"),
        ),
        result=ReviewResult.PASS,
    )

    assert result.snapshot.state == StateSnapshot(phase="code-review", sub_state="ready_for_review")


def test_executor_prompt_contains_work_item_context(tmp_path) -> None:
    store = SQLiteEventStore(SQLiteEventStoreConfig(db_path=tmp_path / "workflow.sqlite3"))
    orchestrator = WorkflowOrchestrator(
        WorkflowOrchestratorConfig(store=store, template=default_coding_agent_template()),
    )
    actor = Actor(kind=ActorKind.AGENT, actor_id="executor")
    entered = orchestrator.enter("workflow-1", actor)

    prompt = build_executor_prompt(
        workflow_id="workflow-1",
        snapshot=entered.snapshot,
        work_item=entered.work_item,
        user_message="用户消息",
    )

    payload = json.loads(prompt)
    assert payload["workflow_id"] == "workflow-1"
    assert payload["version"] == 1
    assert payload["work_item"]["work_item_id"] == "workflow-1:1"
    assert payload["work_item"]["next_action"]
    assert payload["user_message"] == "用户消息"


def test_command_workflow_executor_runs_in_workspace_with_work_item_prompt(tmp_path) -> None:
    store = SQLiteEventStore(SQLiteEventStoreConfig(db_path=tmp_path / "workflow.sqlite3"))
    orchestrator = WorkflowOrchestrator(
        WorkflowOrchestratorConfig(store=store, template=default_coding_agent_template()),
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    profile = RunnerProfile(
        name="command-executor",
        command="python3",
        args=(
            "-c",
            "import json, os, pathlib, sys; "
            "payload=json.loads(sys.stdin.read()); "
            "assert payload['work_item']['workspace_path'] == os.getcwd(); "
            "assert payload['work_item']['branch'] is None; "
            "pathlib.Path('prompt-workflow.txt').write_text(payload['workflow_id']); "
            "print(os.getcwd())",
        ),
        permissions="workspace-write",
    )

    result = CommandWorkflowExecutor(
        orchestrator,
        profile,
        actor=Actor(kind=ActorKind.AGENT, actor_id="executor"),
        workspace=workspace,
    ).run_once("workflow-1", prompt="hello")

    assert result.summary == str(workspace)
    assert (workspace / "prompt-workflow.txt").read_text() == "workflow-1"
    assert result.snapshot.state == StateSnapshot(phase="requirements", sub_state="drafting")
