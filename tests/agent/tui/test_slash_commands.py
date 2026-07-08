"""TUI slash command suggestion tests."""

import pytest

from agent.commands.registry import build_default_slash_command_registry
from agent.tui.commands import filter_commands_by_prefix


@pytest.fixture
def catalog():
    """Return the default slash command catalog."""
    registry = build_default_slash_command_registry(skill_runtime=None)
    return registry.catalog()


# ---------------------------------------------------------------------------
# prefix filtering
# ---------------------------------------------------------------------------

def test_filter_empty_prefix_returns_all(catalog):
    results = filter_commands_by_prefix(catalog, "")
    assert len(results) == len(catalog)
    for cmd in results:
        assert "name" in cmd
        assert "insert_text" in cmd


def test_filter_exact_match(catalog):
    results = filter_commands_by_prefix(catalog, "help")
    assert len(results) == 1
    assert results[0]["name"] == "help"
    assert results[0]["insert_text"] == "/help"


def test_filter_partial_prefix(catalog):
    results = filter_commands_by_prefix(catalog, "st")
    names = {result["name"] for result in results}
    assert "status" in names
    for cmd in results:
        assert "st" in cmd["name"]


def test_filter_no_match_returns_empty(catalog):
    results = filter_commands_by_prefix(catalog, "zzz_nonexistent")
    assert len(results) == 0


# ---------------------------------------------------------------------------
# alias filtering
# ---------------------------------------------------------------------------

def test_filter_matches_alias(catalog):
    results = filter_commands_by_prefix(catalog, "qu")
    names = {r["name"] for r in results}
    assert "exit" in names  # via alias "quit"


def test_filter_exact_alias(catalog):
    results = filter_commands_by_prefix(catalog, "quit")
    names = {r["name"] for r in results}
    assert "exit" in names  # quit is alias of exit


# ---------------------------------------------------------------------------
# insert_text
# ---------------------------------------------------------------------------

def test_insert_text_no_args(catalog):
    results = filter_commands_by_prefix(catalog, "exit")
    assert len(results) == 1
    assert results[0]["insert_text"] == "/exit"


def test_insert_text_with_args(catalog):
    results = filter_commands_by_prefix(catalog, "mode")
    assert len(results) >= 1
    mode_cmd = [r for r in results if r["name"] == "mode"][0]
    assert mode_cmd["insert_text"] == "/mode "


# ---------------------------------------------------------------------------
# skill commands
# ---------------------------------------------------------------------------

def test_skill_commands_in_catalog():
    from agent.skills.runtime import Skill, SkillRuntime

    runtime = SkillRuntime(skills=[
        Skill(
            name="code-review",
            description="Review code changes",
            prompt="Review instructions",
            tools=[],
            argument_hint="<request>",
            user_invocable=True,
        )
    ])
    registry = build_default_slash_command_registry(skill_runtime=runtime)
    cat = registry.catalog()

    skill_cmds = [c for c in cat if c.get("source") == "skill"]
    assert len(skill_cmds) >= 1
    code_review = skill_cmds[0]
    assert code_review["name"] == "code-review"
    assert code_review["kind"] == "prompt"


def test_filter_skill_command_by_prefix():
    from agent.skills.runtime import Skill, SkillRuntime

    runtime = SkillRuntime(skills=[
        Skill(
            name="code-review",
            description="Review code changes",
            prompt="Review instructions",
            tools=[],
            argument_hint="<request>",
            user_invocable=True,
        )
    ])
    registry = build_default_slash_command_registry(skill_runtime=runtime)
    cat = registry.catalog()

    results = filter_commands_by_prefix(cat, "code")
    assert len(results) >= 1
    assert any(r["name"] == "code-review" for r in results)


def test_non_user_invocable_skills_not_in_catalog():
    from agent.skills.runtime import Skill, SkillRuntime

    runtime = SkillRuntime(skills=[
        Skill(
            name="hidden-skill",
            description="Hidden",
            prompt="Hidden",
            tools=[],
            user_invocable=False,
        )
    ])
    registry = build_default_slash_command_registry(skill_runtime=runtime)
    cat = registry.catalog()

    skill_names = {c["name"] for c in cat if c.get("source") == "skill"}
    assert "hidden-skill" not in skill_names


# ---------------------------------------------------------------------------
# prefix without slash
# ---------------------------------------------------------------------------

def test_filter_takes_prefix_without_leading_slash(catalog):
    results = filter_commands_by_prefix(catalog, "/help")
    names = {r["name"] for r in results}
    assert "help" in names


# ---------------------------------------------------------------------------
# command execution through controller (via handle_slash_command)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_skill_slash_command_runs_agent_turn():
    from agent.skills.runtime import Skill, SkillRuntime
    from agent.run_identity import new_session_id
    from agent.tui.controller import TUIController
    from agent.result import RunResult, StopReason

    runtime = SkillRuntime(skills=[
        Skill(
            name="code-review",
            description="Review code changes",
            prompt="Review instructions",
            tools=[],
            argument_hint="<request>",
            user_invocable=True,
        )
    ])
    registry = build_default_slash_command_registry(skill_runtime=runtime)

    class FakeLoop:
        def __init__(self):
            self.run_count = 0
            self.tool_registry = type("FakeTR", (), {"mode_policy": type("FakeP", (), {"runtime_state": type("FakeS", (), {"current_mode": type("FakeM", (), {"value": "build"})()})()})()})()
            self.runtime_state = type("FakeRS", (), {"current_mode": type("FakeM", (), {"value": "build"})()})()
            self.memory = type("FakeMem", (), {"messages": []})()
            self.max_iterations = 20
            self.skill_runtime = runtime

        async def run(self, messages, on_event=None, session_id=None, run_id=None):
            self.run_count += 1
            if on_event:
                await on_event("run_started", {"mode": "build", "run_id": run_id, "session_id": session_id})
                await on_event("llm_response", {"content": "review done", "stop_reason": "end_turn", "tool_calls": []})
                await on_event("done", {"content": "review done", "stop_reason": "end_turn"})
            return RunResult(content="review done", stop_reason=StopReason.END_TURN, tool_calls_made=[])

    fake = FakeLoop()
    ctrl = TUIController(agent=fake, session_id=new_session_id(), command_registry=registry)

    result = await ctrl.handle_slash_command_async("/code-review please review")

    assert result is True
    assert fake.run_count == 1
    assert [m.content for m in ctrl.messages if m.role == "user"] == ["please review"]
