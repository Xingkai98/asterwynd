from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from threading import Lock

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


class AgentRuntimeState:
    def __init__(self, initial_mode: AgentMode = AgentMode.BUILD):
        self.initial_mode = initial_mode
        self._current_mode = initial_mode
        self._lock = Lock()

    @property
    def current_mode(self) -> AgentMode:
        return self._current_mode

    def set_mode(
        self,
        value: str | AgentMode,
        *,
        source: str,
        reason: str | None = None,
    ) -> dict[str, str]:
        new_mode = value if isinstance(value, AgentMode) else parse_agent_mode(value)
        with self._lock:
            old_mode = self._current_mode
            self._current_mode = new_mode
        transition = {
            "old_mode": old_mode.value,
            "new_mode": new_mode.value,
            "source": source,
        }
        if reason is not None:
            transition["reason"] = reason
        return transition


class ModePolicy:
    def __init__(
        self,
        run_config: AgentRunConfig | None = None,
        deny_tools_by_mode: dict[AgentMode, tuple[str, ...]] | None = None,
        runtime_state: AgentRuntimeState | None = None,
    ):
        self.run_config = run_config or AgentRunConfig()
        self.deny_tools_by_mode = deny_tools_by_mode or {}
        self.runtime_state = runtime_state

    @property
    def mode(self) -> AgentMode:
        if self.runtime_state is not None:
            return self.runtime_state.current_mode
        return self.run_config.mode

    def is_tool_allowed(self, tool: Tool) -> bool:
        allowed_modes = getattr(tool, "allowed_modes", None)
        if allowed_modes is not None and self.mode.value not in allowed_modes:
            return False
        if tool.name in self.deny_tools_by_mode.get(self.mode, ()):
            return False
        if self.mode is AgentMode.BUILD:
            return True
        if self.mode in {AgentMode.READ_ONLY, AgentMode.PLAN}:
            return tool.read_only and not tool.dangerous
        return False

    def validate_known_tools(self, tool_names: list[str] | tuple[str, ...]) -> None:
        known = set(tool_names)
        unknown = sorted(
            tool_name
            for deny_tools in self.deny_tools_by_mode.values()
            for tool_name in deny_tools
            if tool_name not in known
        )
        if unknown:
            joined = ", ".join(unknown)
            raise ValueError(f"Unknown deny_tools: {joined}")
