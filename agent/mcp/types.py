from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from agent.tool_permissions import (
    ToolCapability,
    ToolOrigin,
    ToolPermission,
    ToolRiskLevel,
)


DEFAULT_MCP_PERMISSION = ToolPermission(
    capabilities=frozenset({ToolCapability.EXTERNAL_SIDE_EFFECT}),
    risk_level=ToolRiskLevel.HIGH,
    origin=ToolOrigin.MCP,
)


class McpActionKind(str, Enum):
    TOOL = "tool"
    PROMPT = "prompt"
    RESOURCE = "resource"


@dataclass(frozen=True)
class McpToolMetadata:
    server_name: str
    tool_name: str
    callable_name: str
    description: str
    input_schema: dict[str, Any]
    permission: ToolPermission


@dataclass(frozen=True)
class McpPromptMetadata:
    server_name: str
    prompt_name: str
    callable_name: str
    description: str
    arguments_schema: dict[str, Any] = field(default_factory=dict)
    permission: ToolPermission = DEFAULT_MCP_PERMISSION


@dataclass(frozen=True)
class McpResourceMetadata:
    server_name: str
    uri: str
    callable_name: str
    name: str
    description: str
    mime_type: str | None = None
    permission: ToolPermission = DEFAULT_MCP_PERMISSION


@dataclass(frozen=True)
class McpServerStatus:
    name: str
    ready: bool
    tools: int = 0
    prompts: int = 0
    resources: int = 0
    error: str | None = None
