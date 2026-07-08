from types import SimpleNamespace

import pytest

from agent.commands import CommandContext, build_default_slash_command_registry
from agent.message import system_message
from agent.run_config import AgentMode, AgentRunConfig, ModePolicy
from agent.tool_permissions import (
    ToolCapability,
    ToolOrigin,
    ToolPermission,
    ToolRiskLevel,
)
from agent.tools.factory import build_default_tool_registry


class FakeMcpManager:
    def status(self):
        return [
            SimpleNamespace(
                name="docs",
                ready=True,
                tools=1,
                prompts=1,
                resources=1,
                error=None,
            )
        ]

    def get_prompt_permission(self, server_name, prompt_name):
        return ToolPermission(
            capabilities=frozenset({ToolCapability.NETWORK_READ}),
            risk_level=ToolRiskLevel.LOW,
            origin=ToolOrigin.MCP,
        )

    def get_resource_permission(self, server_name, uri):
        return ToolPermission(
            capabilities=frozenset({ToolCapability.NETWORK_READ}),
            risk_level=ToolRiskLevel.LOW,
            origin=ToolOrigin.MCP,
        )

    async def get_prompt(self, server_name, prompt_name, arguments):
        return (
            f"[MCP prompt: {server_name}/{prompt_name}]\n"
            f"Arguments: {arguments}\n\n"
            "user: Review PR."
        )

    async def read_resource(self, server_name, uri):
        return f"[MCP resource: {server_name} {uri}]\n\nAgentLoop docs."


def _context(mode=AgentMode.READ_ONLY):
    agent = SimpleNamespace(
        mcp_manager=FakeMcpManager(),
        tool_registry=build_default_tool_registry(
            mode_policy=ModePolicy(AgentRunConfig(mode=mode))
        ),
    )
    return CommandContext(
        agent=agent,
        messages=[system_message("base")],
        session_id="session-1",
        provider="fake",
        model="fake",
    )


@pytest.mark.asyncio
async def test_mcp_command_lists_server_status():
    registry = build_default_slash_command_registry()

    result = await registry.try_execute("/mcp", _context())

    assert result is not None
    assert "- docs: ready, tools=1, prompts=1, resources=1" in result.message


@pytest.mark.asyncio
async def test_mcp_prompt_injects_system_context():
    registry = build_default_slash_command_registry()
    ctx = _context()

    result = await registry.try_execute(
        '/mcp-prompt docs review_pr {"repo":"asterwynd"}',
        ctx,
    )

    assert result is not None
    assert result.message == "Injected MCP prompt: docs/review_pr"
    assert ctx.messages[-1].role == "system"
    assert "[MCP prompt: docs/review_pr]" in ctx.messages[-1].content
    assert result.metadata["mcp_kind"] == "prompt"


@pytest.mark.asyncio
async def test_mcp_resource_injects_system_context():
    registry = build_default_slash_command_registry()
    ctx = _context()

    result = await registry.try_execute(
        "/mcp-resource docs docs://architecture/agent-loop",
        ctx,
    )

    assert result is not None
    assert result.message == "Injected MCP resource: docs docs://architecture/agent-loop"
    assert ctx.messages[-1].role == "system"
    assert "[MCP resource: docs docs://architecture/agent-loop]" in ctx.messages[-1].content
