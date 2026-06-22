from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from agent.tools.base import Tool


class AgentMode(str, Enum):
    BUILD = "build"
    READ_ONLY = "read_only"
    PLAN = "plan"
    BYPASS = "bypass"


def parse_agent_mode(value: str, *, allow_bypass: bool = False) -> AgentMode:
    normalized = value.strip().lower().replace("-", "_")
    if normalized == AgentMode.BYPASS.value and not allow_bypass:
        raise ValueError("bypass mode is reserved for internal use")

    try:
        return AgentMode(normalized)
    except ValueError as exc:
        supported = ["build", "read_only", "read-only", "plan"]
        if allow_bypass:
            supported.append("bypass")
        raise ValueError(
            f"unsupported agent mode {value!r}; expected one of {supported}"
        ) from exc


@dataclass(frozen=True)
class AgentRunConfig:
    mode: AgentMode = AgentMode.BUILD


class ModePolicy:
    def __init__(self, run_config: AgentRunConfig | None = None):
        self.run_config = run_config or AgentRunConfig()

    @property
    def mode(self) -> AgentMode:
        return self.run_config.mode

    def is_tool_allowed(self, tool: Tool) -> bool:
        if self.mode is AgentMode.BUILD:
            return True
        if self.mode in {AgentMode.READ_ONLY, AgentMode.PLAN}:
            return tool.read_only and not tool.dangerous
        return False
