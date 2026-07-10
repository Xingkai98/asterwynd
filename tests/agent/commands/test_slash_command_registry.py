import pytest

from agent.commands import (
    CommandContext,
    CommandResult,
    SlashCommand,
    SlashCommandRegistry,
    build_default_slash_command_registry,
)
from agent.memory.manager import MemoryManager
from agent.message import Message
from agent.skills import Skill, SkillRuntime


class FakeAgent:
    def __init__(self, skill_runtime=None):
        self.llm = type("FakeLLM", (), {"model": "fake-model"})()
        self.current_mode = "build"
        self.memory = MemoryManager(recent_window=2)
        self.mode_changes = []
        self.skill_runtime = skill_runtime

    async def set_mode(self, mode, *, source, session_id=None, **kwargs):
        if mode == "bypass":
            raise ValueError("bypass mode is reserved for internal use")
        old_mode = self.current_mode
        self.current_mode = mode
        transition = {
            "old_mode": old_mode,
            "new_mode": mode,
            "source": source,
            "session_id": session_id,
        }
        self.mode_changes.append(transition)
        return transition


@pytest.mark.asyncio
async def test_registry_dispatches_registered_command_and_alias():
    async def handler(ctx: CommandContext, args: str) -> CommandResult:
        return CommandResult(message=f"hello {args}")

    registry = SlashCommandRegistry()
    registry.register(
        SlashCommand(
            name="hello",
            usage="/hello <name>",
            description="Say hello.",
            aliases=("hi",),
            handler=handler,
        )
    )
    ctx = CommandContext(
        agent=FakeAgent(),
        messages=[],
        session_id="session-1",
        provider="openai",
        model="fake-model",
    )

    result = await registry.try_execute("/hi world", ctx)

    assert result == CommandResult(
        message="hello world",
        metadata={
            "command": "hello",
            "known": True,
            "source": "builtin",
            "kind": "local",
        },
    )


@pytest.mark.asyncio
async def test_registry_preserves_args_for_skill_shaped_command_names():
    seen_args = []

    async def handler(ctx: CommandContext, args: str) -> CommandResult:
        seen_args.append(args)
        return CommandResult(message="skill queued")

    registry = SlashCommandRegistry()
    registry.register(
        SlashCommand(
            name="review-skill",
            usage="/review-skill <request>",
            description="Run review skill.",
            argument_hint="<request>",
            source="skill",
            kind="prompt",
            handler=handler,
        )
    )
    ctx = CommandContext(
        agent=FakeAgent(),
        messages=[],
        session_id="session-1",
        provider="openai",
        model="fake-model",
    )

    result = await registry.try_execute("/review-skill 帮我审一下这个 change", ctx)

    assert result is not None
    assert seen_args == ["帮我审一下这个 change"]
    assert result.metadata["command"] == "review-skill"
    assert result.metadata["source"] == "skill"
    assert result.metadata["kind"] == "prompt"


@pytest.mark.asyncio
async def test_registry_returns_none_for_normal_user_text():
    registry = SlashCommandRegistry()
    ctx = CommandContext(
        agent=FakeAgent(),
        messages=[],
        session_id="session-1",
        provider="openai",
        model="fake-model",
    )

    assert await registry.try_execute("explain /tmp", ctx) is None


@pytest.mark.asyncio
async def test_registry_intercepts_unknown_slash_command():
    registry = SlashCommandRegistry()
    ctx = CommandContext(
        agent=FakeAgent(),
        messages=[],
        session_id="session-1",
        provider="openai",
        model="fake-model",
    )

    result = await registry.try_execute("/unknown", ctx)

    assert result is not None
    assert result.continue_session is True
    assert "Unknown command: /unknown" in result.message
    assert "/help" in result.message


@pytest.mark.asyncio
async def test_default_help_lists_registered_commands():
    registry = build_default_slash_command_registry()
    ctx = CommandContext(
        agent=FakeAgent(),
        messages=[],
        session_id="session-1",
        provider="openai",
        model="fake-model",
    )

    result = await registry.try_execute("/help", ctx)

    assert result is not None
    assert "/help" in result.message
    assert "/clear" in result.message
    assert "/compact" in result.message


@pytest.mark.asyncio
async def test_default_registry_lists_skills_and_registers_skill_commands():
    runtime = SkillRuntime(skills=[
        Skill(
            name="code-review",
            description="审查代码变更",
            prompt="Review instructions",
            tools=[],
            triggers=("review",),
            argument_hint="<request>",
            user_invocable=True,
        ),
        Skill(
            name="internal",
            description="Internal skill",
            prompt="Internal instructions",
            tools=[],
            user_invocable=False,
        ),
    ])
    registry = build_default_slash_command_registry(runtime)
    ctx = CommandContext(
        agent=FakeAgent(skill_runtime=runtime),
        messages=[],
        session_id="session-1",
        provider="openai",
        model="fake-model",
    )

    skills_result = await registry.try_execute("/skills", ctx)
    skill_result = await registry.try_execute("/code-review 帮我审一下这个 change", ctx)

    assert skills_result is not None
    assert "Loaded skills: 2" in skills_result.message
    assert "code-review" in skills_result.message
    assert "internal" in skills_result.message
    assert skill_result is not None
    assert skill_result.message == "Activated skill: code-review"
    assert skill_result.metadata["run_agent"] is True
    assert skill_result.metadata["agent_input"] == "帮我审一下这个 change"
    assert skill_result.metadata["skill_name"] == "code-review"
    assert skill_result.metadata["activation_source"] == "slash_command"

    catalog = registry.catalog()
    skill_command = next(command for command in catalog if command["name"] == "code-review")
    assert skill_command["source"] == "skill"
    assert skill_command["kind"] == "prompt"
    assert skill_command["argument_hint"] == "<request>"
    assert "internal" not in {command["name"] for command in catalog}


@pytest.mark.asyncio
async def test_skills_reload_refreshes_dynamic_skill_commands(tmp_path):
    skills_root = tmp_path / "skills"
    review_dir = skills_root / "review"
    review_dir.mkdir(parents=True)
    (review_dir / "SKILL.md").write_text(
        "---\n"
        "name: review\n"
        "description: Review code\n"
        "user_invocable: true\n"
        "---\n"
        "Review instructions\n",
        encoding="utf-8",
    )
    runtime = SkillRuntime.from_roots([skills_root])
    registry = build_default_slash_command_registry(runtime)
    ctx = CommandContext(
        agent=FakeAgent(skill_runtime=runtime),
        messages=[],
        session_id="session-1",
        provider="openai",
        model="fake-model",
    )

    assert await registry.try_execute("/review first", ctx) is not None
    (review_dir / "SKILL.md").unlink()
    docs_dir = skills_root / "docs"
    docs_dir.mkdir()
    (docs_dir / "SKILL.md").write_text(
        "---\n"
        "name: docs\n"
        "description: Update docs\n"
        "user_invocable: true\n"
        "---\n"
        "Docs instructions\n",
        encoding="utf-8",
    )

    reload_result = await registry.try_execute("/skills reload", ctx)
    old_result = await registry.try_execute("/review second", ctx)
    new_result = await registry.try_execute("/docs update docs", ctx)

    assert reload_result is not None
    assert reload_result.metadata["reloaded"] is True
    assert reload_result.metadata["skill_count"] == 1
    assert old_result is not None
    assert old_result.metadata["known"] is False
    assert new_result is not None
    assert new_result.metadata["run_agent"] is True
    assert new_result.metadata["skill_name"] == "docs"


@pytest.mark.asyncio
async def test_default_clear_preserves_system_messages_and_syncs_memory():
    registry = build_default_slash_command_registry()
    agent = FakeAgent()
    messages = [
        Message(role="system", content="system"),
        Message(role="user", content="old user"),
        Message(role="assistant", content="old answer"),
    ]
    agent.memory.messages = list(messages)
    ctx = CommandContext(
        agent=agent,
        messages=messages,
        session_id="session-1",
        provider="openai",
        model="fake-model",
    )

    result = await registry.try_execute("/clear", ctx)

    assert result is not None
    assert result.metadata["preserved_system_messages"] == 1
    assert [message.role for message in messages] == ["system"]
    assert [message.role for message in agent.memory.messages] == ["system"]


@pytest.mark.asyncio
async def test_default_compact_reports_noop_without_eligible_history():
    registry = build_default_slash_command_registry()
    agent = FakeAgent()
    messages = [
        Message(role="system", content="system"),
        Message(role="user", content="recent user"),
        Message(role="assistant", content="recent answer"),
    ]
    ctx = CommandContext(
        agent=agent,
        messages=messages,
        session_id="session-1",
        provider="openai",
        model="fake-model",
    )

    result = await registry.try_execute("/compact", ctx)

    assert result is not None
    assert result.metadata["compacted"] is False
    assert "Nothing to compact" in result.message
    assert [message.content for message in messages] == [
        "system",
        "recent user",
        "recent answer",
    ]
