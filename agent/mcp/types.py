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


class McpCallError(Exception):
    """Typed MCP tool-call error carrying a structured ``error_type``.

    Raised by ``McpManager.call_tool`` on the exception path so the caller
    (``McpTool.execute``) can produce a ``ToolResult(text, error_type)`` at the
    error source instead of guessing from a formatted string. ``__str__``
    returns the user-facing text (keeps RetryHook's retryable-token matching
    and logging readable).
    """

    def __init__(self, text: str, error_type: str = "mcp_error"):
        super().__init__(text)
        self.text = text
        self.error_type = error_type

    def __str__(self) -> str:
        return self.text


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
    # Runtime health (batch-2, design Decision 5): populated by McpManager.
    health_ok: bool | None = None
    last_health_check: float | None = None
    calls: int = 0
    failures: int = 0
    failure_rate: float | None = None
    degraded: bool = False
