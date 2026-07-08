from __future__ import annotations

import pytest

from agent.workflow.role_registry import (
    ROLE_SYSTEM_PROMPTS,
    RoleAgentConfig,
    build_role_configs,
    build_subagent_task,
    get_role_config,
)


class TestBuildRoleConfigs:
    def test_all_five_roles_registered(self):
        configs = build_role_configs()
        assert set(configs.keys()) == {"planner", "reviewer", "builder", "code-reviewer", "closer"}

    def test_each_config_has_system_prompt(self):
        configs = build_role_configs()
        for role_type, config in configs.items():
            assert config.system_prompt, f"{role_type} has empty system prompt"
            assert len(config.system_prompt) > 50, f"{role_type} system prompt too short"

    def test_each_config_has_description(self):
        configs = build_role_configs()
        for role_type, config in configs.items():
            assert config.description, f"{role_type} has empty description"

    def test_each_config_has_executor_hints(self):
        configs = build_role_configs()
        for role_type, config in configs.items():
            assert isinstance(config.executor_hints, dict), f"{role_type} executor_hints not a dict"

    def test_config_type_matches_key(self):
        configs = build_role_configs()
        for role_type, config in configs.items():
            assert config.type == role_type


class TestGetRoleConfig:
    def test_returns_config_for_valid_role(self):
        config = get_role_config("planner")
        assert config.type == "planner"
        assert config.name == "Planner"

    def test_raises_for_invalid_role(self):
        with pytest.raises(ValueError, match="unknown role agent type"):
            get_role_config("invalid")


class TestSystemPrompts:
    def test_planner_mentions_planning_docs(self):
        prompt = ROLE_SYSTEM_PROMPTS["planner"]
        assert "proposal.md" in prompt
        assert "design.md" in prompt
        assert "tasks.md" in prompt

    def test_reviewer_mentions_review_report(self):
        prompt = ROLE_SYSTEM_PROMPTS["reviewer"]
        assert "review-report" in prompt

    def test_builder_mentions_tdd(self):
        prompt = ROLE_SYSTEM_PROMPTS["builder"]
        assert "writing_tests" in prompt
        assert "test_failing" in prompt

    def test_code_reviewer_mentions_diff(self):
        prompt = ROLE_SYSTEM_PROMPTS["code-reviewer"]
        assert "reading_diff" in prompt

    def test_closer_mentions_archive(self):
        prompt = ROLE_SYSTEM_PROMPTS["closer"]
        assert "archiving" in prompt


class TestBuildSubagentTask:
    def test_includes_change_id(self):
        task = build_subagent_task(
            "planner",
            "my-change",
            {"state": {"phase": "planning", "sub_state": "exploring"}},
        )
        assert "my-change" in task

    def test_includes_current_state(self):
        task = build_subagent_task(
            "builder",
            "test-change",
            {"state": {"phase": "building", "sub_state": "writing_tests"}},
        )
        assert "building" in task
        assert "writing_tests" in task

    def test_includes_handoff_note_when_provided(self):
        task = build_subagent_task(
            "reviewer",
            "test-change",
            {"state": {"phase": "reviewing", "sub_state": "reading_docs"}},
            handoff_note_path=".handoff/test/planning-to-reviewing.md",
        )
        assert ".handoff/test/planning-to-reviewing.md" in task

    def test_includes_role_system_prompt(self):
        task = build_subagent_task(
            "code-reviewer",
            "test-change",
            {"state": {"phase": "code-review", "sub_state": "reading_diff"}},
        )
        assert "reading_diff" in task
        assert "analyzing_tests" in task
