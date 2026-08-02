from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from agent.tools.base import Tool, ToolCall
from agent.run_config import ModePolicy
from agent.tool_permissions import PermissionDecisionType
from agent.workspace_policy import WorkspacePolicy

if TYPE_CHECKING:
    from agent.message import ContentBlock
    from agent.tools.governance.dedup import SemanticDeduper
    from agent.tools.governance.lifecycle import ToolLifecycle
    from agent.tools.governance.quality import ToolQualityStore
    from agent.tools.governance.selector import ToolSelector


class ToolRegistry:
    def __init__(self, mode_policy: ModePolicy | None = None):
        self._tools: dict[str, Tool] = {}
        self.mode_policy = mode_policy or ModePolicy()
        self.workspace_policy: WorkspacePolicy | None = None
        # Governance components (optional, registry-level capability).
        self._lifecycle: ToolLifecycle | None = None
        self._selector: ToolSelector | None = None
        self._deduper: SemanticDeduper | None = None
        self._quality: ToolQualityStore | None = None
        self._hidden_filter: Callable[[str], bool] | None = None

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    # --- Governance wiring -------------------------------------------------

    def set_lifecycle(self, lifecycle: ToolLifecycle) -> None:
        self._lifecycle = lifecycle

    def set_selector(self, selector: ToolSelector) -> None:
        self._selector = selector

    def set_deduper(self, deduper: SemanticDeduper) -> None:
        self._deduper = deduper

    def set_quality(self, quality: ToolQualityStore) -> None:
        self._quality = quality

    @property
    def quality_store(self) -> ToolQualityStore | None:
        return self._quality

    def set_visibility_filter(
        self, predicate: Callable[[str], bool] | None
    ) -> None:
        """Hide tools matching ``predicate`` (e.g. degraded MCP server tools)."""
        self._hidden_filter = predicate

    def quality_notice(self, tool_name: str) -> str | None:
        if self._quality is None:
            return None
        return self._quality.quality_notice(tool_name)

    def _is_quality_degraded(self, tool_name: str) -> bool:
        if self._quality is None:
            return False
        return self._quality.is_degraded(tool_name)

    def _is_governance_visible(self, tool_name: str) -> bool:
        """Lifecycle-removed and hidden-filter tools are excluded from schemas."""
        if self._lifecycle is not None and not self._lifecycle.is_visible(tool_name):
            return False
        if self._hidden_filter is not None and self._hidden_filter(tool_name):
            return False
        return True

    def _sync_governance_indexes(self) -> None:
        """Index current tools into selector and deduper (registration sync)."""
        if self._selector is not None:
            for tool in self._tools.values():
                self._selector.index_tool(tool.name, tool.description)
        if self._deduper is not None:
            for tool in self._tools.values():
                self._deduper.add(tool.name, tool.description)

    def duplicate_of(self, tool_name: str) -> str | None:
        if self._deduper is None:
            return None
        return self._deduper.duplicate_of(tool_name)

    def deprecation_notice(self, tool_name: str) -> str | None:
        if self._lifecycle is None:
            return None
        return self._lifecycle.deprecation_notice(tool_name)

    def select_schemas(self, query: str, k: int = 5) -> list[dict]:
        """Top-K select schemas by relevance, stable layer first.

        Used at the loop injection seam (design Q3). Falls back to the stable
        layer / all visible tools when no selector is configured.
        """
        if self._selector is None:
            return self.get_all_schemas()
        selected = self._selector.select(query)
        # Keep only selected tools that are governance-visible and mode-allowed.
        # Quality-degraded tools leave the variable layer; stable-layer tools
        # always stay injected (soft degradation, batch-2 Q4).
        schemas: list[dict] = []
        for name in selected:
            tool = self._tools.get(name)
            if tool is None:
                continue
            if not self._is_governance_visible(name):
                continue
            if self._is_quality_degraded(name) and not self._selector.is_stable(name):
                continue
            if not self.mode_policy.is_tool_allowed(tool):
                continue
            schemas.append(tool.get_schema())
        return schemas

    # --- Original contract ------------------------------------------------

    def get_schema(self, name: str) -> dict:
        return self._tools[name].get_schema()

    def get_all_schemas(self) -> list[dict]:
        return [
            tool.get_schema()
            for tool in self._tools.values()
            if self.mode_policy.is_tool_allowed(tool)
            and self._is_governance_visible(tool.name)
        ]

    def get_sandbox(self, name: str) -> bool:
        return self._tools[name].dangerous

    async def execute(self, tool_call: ToolCall, *, approval_granted: bool = False) -> str | list["ContentBlock"]:
        tool = self._tools[tool_call.name]
        decision = self.mode_policy.decide_tool(tool)
        if decision.type is PermissionDecisionType.DENY:
            mode = self.mode_policy.mode.value
            return (
                f"[Permission denied: tool {tool_call.name} is not allowed "
                f"in {mode} mode: {decision.reason}]"
            )
        if decision.type is PermissionDecisionType.REQUIRE_APPROVAL and not approval_granted:
            return (
                f"[Approval required: tool {tool_call.name} requires approval "
                f"in {self.mode_policy.mode.value} mode]"
            )
        return await tool.execute(**tool_call.arguments)

    def get_tool(self, name: str) -> Tool:
        return self._tools[name]
