from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from agent.message import Message


@dataclass
class CommandResult:
    message: str = ""
    continue_session: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CommandContext:
    agent: Any
    messages: list[Message]
    session_id: str
    provider: str
    model: str


CommandHandler = Callable[[CommandContext, str], Awaitable[CommandResult]]


@dataclass(frozen=True)
class SlashCommand:
    name: str
    usage: str
    description: str
    handler: CommandHandler
    aliases: tuple[str, ...] = ()
    argument_hint: str = ""

    @property
    def canonical_name(self) -> str:
        return self.name.lstrip("/").lower()


class SlashCommandRegistry:
    def __init__(self) -> None:
        self._commands: dict[str, SlashCommand] = {}

    def register(self, command: SlashCommand) -> None:
        names = [command.canonical_name, *(alias.lstrip("/").lower() for alias in command.aliases)]
        for name in names:
            if not name:
                raise ValueError("slash command name cannot be empty")
            if name in self._commands:
                raise ValueError(f"duplicate slash command: /{name}")
            self._commands[name] = command

    def commands(self) -> list[SlashCommand]:
        seen: set[str] = set()
        commands: list[SlashCommand] = []
        for command in self._commands.values():
            if command.canonical_name in seen:
                continue
            seen.add(command.canonical_name)
            commands.append(command)
        return commands

    def catalog(self) -> list[dict[str, Any]]:
        return [
            {
                "name": command.canonical_name,
                "command": f"/{command.canonical_name}",
                "usage": command.usage,
                "description": command.description,
                "aliases": [alias.lstrip("/").lower() for alias in command.aliases],
                "argument_hint": command.argument_hint,
                "insert_text": (
                    f"/{command.canonical_name} "
                    if command.argument_hint
                    else f"/{command.canonical_name}"
                ),
            }
            for command in self.commands()
        ]

    async def try_execute(
        self,
        user_input: str,
        context: CommandContext,
    ) -> CommandResult | None:
        stripped = user_input.strip()
        if not stripped.startswith("/"):
            return None

        command_name, args = self._parse(stripped)
        command = self._commands.get(command_name)
        if command is None:
            return CommandResult(
                message=f"Unknown command: /{command_name}. Type /help for available commands.",
                metadata={"command": command_name, "known": False},
            )
        result = await command.handler(context, args)
        result.metadata.setdefault("command", command.canonical_name)
        result.metadata.setdefault("known", True)
        return result

    def _parse(self, stripped_input: str) -> tuple[str, str]:
        without_slash = stripped_input[1:]
        if not without_slash:
            return "", ""
        parts = without_slash.split(maxsplit=1)
        command_name = parts[0].lower()
        args = parts[1].strip() if len(parts) == 2 else ""
        return command_name, args


def build_default_slash_command_registry() -> SlashCommandRegistry:
    registry = SlashCommandRegistry()

    async def help_handler(ctx: CommandContext, args: str) -> CommandResult:
        lines = ["Available commands:"]
        for command in registry.commands():
            aliases = ", ".join(f"/{alias}" for alias in command.aliases)
            alias_text = f" (aliases: {aliases})" if aliases else ""
            lines.append(f"{command.usage}{alias_text} - {command.description}")
        return CommandResult(message="\n".join(lines))

    async def exit_handler(ctx: CommandContext, args: str) -> CommandResult:
        return CommandResult(message="再见！", continue_session=False)

    async def status_handler(ctx: CommandContext, args: str) -> CommandResult:
        mode = getattr(ctx.agent, "current_mode", None)
        runtime_state = getattr(ctx.agent, "runtime_state", None)
        if runtime_state is not None:
            mode = getattr(runtime_state, "current_mode", mode)
        if hasattr(mode, "value"):
            mode = mode.value
        mode = mode or "unavailable"
        memory = getattr(ctx.agent, "memory", None)
        token_count = None
        if memory is not None and hasattr(memory, "count_tokens"):
            token_count = memory.count_tokens(ctx.messages)
        lines = [
            f"Session ID: {ctx.session_id}",
            f"Mode: {mode}",
            f"Provider: {ctx.provider}",
            f"Model: {ctx.model}",
            f"Messages: {len(ctx.messages)}",
        ]
        if token_count is not None:
            lines.append(f"Estimated tokens: {token_count}")
        return CommandResult(message="\n".join(lines))

    async def mode_handler(ctx: CommandContext, args: str) -> CommandResult:
        if not args:
            return CommandResult(message="Error: usage /mode <build|read_only|plan>")
        try:
            transition = await ctx.agent.set_mode(
                args,
                source="cli",
                session_id=ctx.session_id,
            )
        except ValueError as exc:
            return CommandResult(message=f"Error: {exc}")
        return CommandResult(
            message=f"Mode changed: {transition['old_mode']} -> {transition['new_mode']}",
            metadata={"transition": transition},
        )

    async def clear_handler(ctx: CommandContext, args: str) -> CommandResult:
        preserved = [message for message in ctx.messages if message.role == "system"]
        removed = len(ctx.messages) - len(preserved)
        ctx.messages[:] = preserved
        _sync_memory_messages(ctx)
        return CommandResult(
            message=(
                "Cleared conversation history. "
                f"Preserved {len(preserved)} system message"
                f"{'' if len(preserved) == 1 else 's'}."
            ),
            metadata={
                "removed_messages": removed,
                "preserved_system_messages": len(preserved),
            },
        )

    async def compact_handler(ctx: CommandContext, args: str) -> CommandResult:
        memory = getattr(ctx.agent, "memory", None)
        if memory is None or not hasattr(memory, "compact_manually"):
            return CommandResult(
                message="Memory compaction is unavailable.",
                metadata={"compacted": False, "reason": "memory_unavailable"},
            )
        result = await memory.compact_manually(ctx.messages)
        _sync_memory_messages(ctx)
        if not result.compacted:
            return CommandResult(
                message=(
                    "Nothing to compact. "
                    f"Messages: {result.before_messages}; estimated tokens: {result.before_tokens}."
                ),
                metadata=result.to_metadata(),
            )
        return CommandResult(
            message=(
                "Compacted conversation history. "
                f"Messages: {result.before_messages} -> {result.after_messages}; "
                f"estimated tokens: {result.before_tokens} -> {result.after_tokens}."
            ),
            metadata=result.to_metadata(),
        )

    registry.register(
        SlashCommand(
            name="help",
            usage="/help",
            description="List available slash commands.",
            handler=help_handler,
        )
    )
    registry.register(
        SlashCommand(
            name="exit",
            usage="/exit",
            description="Exit the interactive session.",
            aliases=("quit",),
            handler=exit_handler,
        )
    )
    registry.register(
        SlashCommand(
            name="status",
            usage="/status",
            description="Show current session, mode, model, and context status.",
            handler=status_handler,
        )
    )
    registry.register(
        SlashCommand(
            name="mode",
            usage="/mode <build|read_only|plan>",
            description="Switch the current agent mode.",
            argument_hint="<build|read_only|plan>",
            handler=mode_handler,
        )
    )
    registry.register(
        SlashCommand(
            name="clear",
            usage="/clear",
            description="Clear conversation history while preserving system context.",
            handler=clear_handler,
        )
    )
    registry.register(
        SlashCommand(
            name="compact",
            usage="/compact",
            description="Compact eligible older conversation history.",
            handler=compact_handler,
        )
    )
    return registry


def _sync_memory_messages(ctx: CommandContext) -> None:
    memory = getattr(ctx.agent, "memory", None)
    if memory is not None and hasattr(memory, "messages"):
        memory.messages = list(ctx.messages)
