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


class FakeAgent:
    def __init__(self):
        self.llm = type("FakeLLM", (), {"model": "fake-model"})()
        self.current_mode = "build"
        self.memory = MemoryManager(recent_window=2)
        self.mode_changes = []

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

    assert result == CommandResult(message="hello world")


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
