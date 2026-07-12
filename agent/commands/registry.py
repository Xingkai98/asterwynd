from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any, Awaitable, Callable

from agent.message import Message
from agent.skills.runtime import SkillRuntime
from agent.tools.base import Tool
from agent.tool_permissions import PermissionDecisionType, ToolPermission
from agent.commands.init import write_aster_md


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
    source: str = "builtin"
    kind: str = "local"

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

    def unregister_source(self, source: str) -> None:
        self._commands = {
            name: command
            for name, command in self._commands.items()
            if command.source != source
        }

    def catalog(self) -> list[dict[str, Any]]:
        return [
            {
                "name": command.canonical_name,
                "command": f"/{command.canonical_name}",
                "usage": command.usage,
                "description": command.description,
                "aliases": [alias.lstrip("/").lower() for alias in command.aliases],
                "argument_hint": command.argument_hint,
                "source": command.source,
                "kind": command.kind,
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
        result.metadata.setdefault("source", command.source)
        result.metadata.setdefault("kind", command.kind)
        return result

    def _parse(self, stripped_input: str) -> tuple[str, str]:
        without_slash = stripped_input[1:]
        if not without_slash:
            return "", ""
        parts = without_slash.split(maxsplit=1)
        command_name = parts[0].lower()
        args = parts[1].strip() if len(parts) == 2 else ""
        return command_name, args


def build_default_slash_command_registry(
    skill_runtime: SkillRuntime | None = None,
) -> SlashCommandRegistry:
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

    async def skills_handler(ctx: CommandContext, args: str) -> CommandResult:
        runtime = getattr(ctx.agent, "skill_runtime", None) or skill_runtime
        if runtime is None:
            return CommandResult(
                message="Skills runtime is unavailable.",
                metadata={"skills_available": False},
            )
        subcommand = args.strip().lower()
        if subcommand == "reload":
            outcome = runtime.reload()
            _register_skill_commands(registry, runtime)
            return CommandResult(
                message=(
                    f"Reloaded {len(outcome.skills)} skills. "
                    f"Diagnostics: {len(outcome.diagnostics)}."
                ),
                metadata={
                    "skills_available": True,
                    "reloaded": True,
                    "skill_count": len(outcome.skills),
                    "diagnostics": [
                        {
                            "level": diagnostic.level,
                            "message": diagnostic.message,
                            "path": str(diagnostic.path) if diagnostic.path else "",
                        }
                        for diagnostic in outcome.diagnostics
                    ],
                },
            )
        lines = [f"Loaded skills: {len(runtime.skills)}"]
        for skill in runtime.skills:
            flags = []
            if skill.always:
                flags.append("always")
            if skill.user_invocable:
                flags.append("user-invocable")
            suffix = f" ({', '.join(flags)})" if flags else ""
            source = f" - {skill.source_path}" if skill.source_path else ""
            lines.append(f"- {skill.name}{suffix}: {skill.description}{source}")
        if runtime.diagnostics:
            lines.append("")
            lines.append(f"Diagnostics: {len(runtime.diagnostics)}")
            for diagnostic in runtime.diagnostics:
                path = f" [{diagnostic.path}]" if diagnostic.path else ""
                lines.append(f"- {diagnostic.level}: {diagnostic.message}{path}")
        return CommandResult(
            message="\n".join(lines),
            metadata={
                "skills_available": True,
                "skill_count": len(runtime.skills),
                "diagnostic_count": len(runtime.diagnostics),
            },
        )

    async def init_handler(ctx: CommandContext, args: str) -> CommandResult:
        try:
            msg = write_aster_md()
            return CommandResult(message=msg, metadata={"aster_md_created": True})
        except Exception as exc:
            return CommandResult(
                message=f"创建 ASTER.md 失败: {exc}",
                metadata={"aster_md_created": False, "error": str(exc)},
            )

    async def mcp_handler(ctx: CommandContext, args: str) -> CommandResult:
        manager = getattr(ctx.agent, "mcp_manager", None)
        if manager is None:
            return CommandResult(
                message="MCP is unavailable.",
                metadata={"mcp_available": False},
            )
        lines = ["MCP servers:"]
        statuses = manager.status()
        if not statuses:
            lines.append("- none configured")
        for status in statuses:
            if status.ready:
                lines.append(
                    f"- {status.name}: ready, tools={status.tools}, "
                    f"prompts={status.prompts}, resources={status.resources}"
                )
            else:
                lines.append(f"- {status.name}: failed, error={status.error or 'unknown'}")
        return CommandResult(
            message="\n".join(lines),
            metadata={"mcp_available": True, "server_count": len(statuses)},
        )

    async def mcp_prompt_handler(ctx: CommandContext, args: str) -> CommandResult:
        manager = getattr(ctx.agent, "mcp_manager", None)
        if manager is None:
            return CommandResult(message="MCP is unavailable.")
        try:
            server_name, prompt_name, raw_args = _parse_mcp_named_args(args, "prompt")
            prompt_args = json.loads(raw_args) if raw_args else {}
            if not isinstance(prompt_args, dict):
                raise ValueError("json args must be an object")
        except ValueError as exc:
            return CommandResult(message=f"Error: {exc}")

        permission = manager.get_prompt_permission(server_name, prompt_name)
        decision = _decide_mcp_action(ctx, f"mcp__{server_name}__prompt__{prompt_name}", permission)
        if decision.type is PermissionDecisionType.DENY:
            return CommandResult(message=f"[Permission denied: {decision.reason}]")
        if decision.type is PermissionDecisionType.REQUIRE_APPROVAL:
            return CommandResult(message=f"[Approval required: MCP prompt {server_name}/{prompt_name}]")

        try:
            injected = await manager.get_prompt(server_name, prompt_name, prompt_args)
        except Exception as exc:
            return CommandResult(message=f"[MCP prompt error: {type(exc).__name__}: {exc}]")
        ctx.messages.append(Message(role="system", content=injected))
        _sync_memory_messages(ctx)
        return CommandResult(
            message=f"Injected MCP prompt: {server_name}/{prompt_name}",
            metadata={
                "mcp_server": server_name,
                "mcp_kind": "prompt",
                "mcp_name": prompt_name,
                "permission_decision": decision.type.value,
                "injected_messages": 1,
            },
        )

    async def mcp_resource_handler(ctx: CommandContext, args: str) -> CommandResult:
        manager = getattr(ctx.agent, "mcp_manager", None)
        if manager is None:
            return CommandResult(message="MCP is unavailable.")
        try:
            server_name, uri = _parse_mcp_resource_args(args)
        except ValueError as exc:
            return CommandResult(message=f"Error: {exc}")

        permission = manager.get_resource_permission(server_name, uri)
        decision = _decide_mcp_action(ctx, f"mcp__{server_name}__resource", permission)
        if decision.type is PermissionDecisionType.DENY:
            return CommandResult(message=f"[Permission denied: {decision.reason}]")
        if decision.type is PermissionDecisionType.REQUIRE_APPROVAL:
            return CommandResult(message=f"[Approval required: MCP resource {server_name} {uri}]")

        try:
            injected = await manager.read_resource(server_name, uri)
        except Exception as exc:
            return CommandResult(message=f"[MCP resource error: {type(exc).__name__}: {exc}]")
        ctx.messages.append(Message(role="system", content=injected))
        _sync_memory_messages(ctx)
        return CommandResult(
            message=f"Injected MCP resource: {server_name} {uri}",
            metadata={
                "mcp_server": server_name,
                "mcp_kind": "resource",
                "uri": uri,
                "permission_decision": decision.type.value,
                "injected_messages": 1,
            },
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
    registry.register(
        SlashCommand(
            name="skills",
            usage="/skills [reload]",
            description="List or reload loaded skills.",
            argument_hint="[reload]",
            handler=skills_handler,
        )
    )
    registry.register(
        SlashCommand(
            name="init",
            usage="/init",
            description="Generate ASTER.md with project instructions for the current directory.",
            handler=init_handler,
        )
    )
    registry.register(
        SlashCommand(
            name="mcp",
            usage="/mcp",
            description="Show MCP server status.",
            source="builtin",
            kind="local",
            handler=mcp_handler,
        )
    )
    registry.register(
        SlashCommand(
            name="mcp-prompt",
            usage="/mcp-prompt <server> <prompt> [json args]",
            description="Read an MCP prompt and inject it as session context.",
            argument_hint="<server> <prompt> [json args]",
            source="builtin",
            kind="local",
            handler=mcp_prompt_handler,
        )
    )
    registry.register(
        SlashCommand(
            name="mcp-resource",
            usage="/mcp-resource <server> <uri>",
            description="Read an MCP resource and inject it as session context.",
            argument_hint="<server> <uri>",
            source="builtin",
            kind="local",
            handler=mcp_resource_handler,
        )
    )
    if skill_runtime is not None:
        _register_skill_commands(registry, skill_runtime)
    return registry


def _sync_memory_messages(ctx: CommandContext) -> None:
    memory = getattr(ctx.agent, "memory", None)
    if memory is not None and hasattr(memory, "messages"):
        memory.messages = list(ctx.messages)


def _register_skill_commands(registry: SlashCommandRegistry, runtime: SkillRuntime) -> None:
    registry.unregister_source("skill")
    for skill in runtime.skills:
        if not skill.user_invocable:
            continue

        async def skill_handler(
            ctx: CommandContext,
            args: str,
            *,
            skill_name: str = skill.name,
        ) -> CommandResult:
            return CommandResult(
                message=f"Activated skill: {skill_name}",
                metadata={
                    "run_agent": True,
                    "agent_input": args,
                    "skill_name": skill_name,
                    "activation_source": "slash_command",
                },
            )

        registry.register(
            SlashCommand(
                name=skill.name,
                usage=f"/{skill.name} {skill.argument_hint}".rstrip(),
                description=skill.description or f"Run skill {skill.name}.",
                argument_hint=skill.argument_hint,
                source="skill",
                kind="prompt",
                handler=skill_handler,
            )
        )


class _PermissionProbeTool(Tool):
    def __init__(self, name: str, permission: ToolPermission):
        self.name = name
        self.description = ""
        self.parameters = {"type": "object", "properties": {}}
        self.permission = permission

    async def execute(self, **kwargs: Any) -> str:
        return ""


def _decide_mcp_action(ctx: CommandContext, name: str, permission: ToolPermission):
    return ctx.agent.tool_registry.mode_policy.decide_tool(
        _PermissionProbeTool(name, permission)
    )


def _parse_mcp_named_args(args: str, kind: str) -> tuple[str, str, str]:
    parts = args.strip().split(maxsplit=2)
    if len(parts) < 2:
        raise ValueError(f"usage /mcp-{kind} <server> <{kind}> [json args]")
    return parts[0], parts[1], parts[2] if len(parts) == 3 else ""


def _parse_mcp_resource_args(args: str) -> tuple[str, str]:
    parts = args.strip().split(maxsplit=1)
    if len(parts) < 2:
        raise ValueError("usage /mcp-resource <server> <uri>")
    return parts[0], parts[1]
