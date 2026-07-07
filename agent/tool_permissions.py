from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ToolCapability(str, Enum):
    WORKSPACE_READ = "workspace_read"
    WORKSPACE_WRITE = "workspace_write"
    COMMAND_EXECUTE = "command_execute"
    NETWORK_READ = "network_read"
    EXTERNAL_SIDE_EFFECT = "external_side_effect"
    AGENT_STATE = "agent_state"
    SUBAGENT_CONTROL = "subagent_control"
    BROWSER_CONTROL = "browser_control"


class ToolRiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ToolOrigin(str, Enum):
    BUILTIN = "builtin"
    MCP = "mcp"
    PLUGIN = "plugin"
    SUBAGENT = "subagent"
    BROWSER = "browser"


class PermissionDecisionType(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"


_RISK_ORDER = {
    ToolRiskLevel.LOW: 0,
    ToolRiskLevel.MEDIUM: 1,
    ToolRiskLevel.HIGH: 2,
}


@dataclass(frozen=True)
class ToolPermission:
    capabilities: frozenset[ToolCapability]
    risk_level: ToolRiskLevel
    origin: ToolOrigin = ToolOrigin.BUILTIN


@dataclass(frozen=True)
class PermissionProfile:
    name: str
    allowed_capabilities: frozenset[ToolCapability]
    auto_approve_max_risk: ToolRiskLevel
    approval_required_max_risk: ToolRiskLevel
    denied_tools: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if risk_rank(self.approval_required_max_risk) < risk_rank(self.auto_approve_max_risk):
            raise ValueError(
                "approval_required_max_risk must be greater than or equal to "
                "auto_approve_max_risk"
            )


@dataclass(frozen=True)
class PermissionDecision:
    type: PermissionDecisionType
    reason: str
    profile_name: str
    tool_name: str
    permission: ToolPermission

    @property
    def is_visible(self) -> bool:
        return self.type is not PermissionDecisionType.DENY

    @property
    def can_execute_without_approval(self) -> bool:
        return self.type is PermissionDecisionType.ALLOW

    @property
    def requires_approval(self) -> bool:
        return self.type is PermissionDecisionType.REQUIRE_APPROVAL


def risk_rank(level: ToolRiskLevel) -> int:
    return _RISK_ORDER[level]


def risk_lte(left: ToolRiskLevel, right: ToolRiskLevel) -> bool:
    return risk_rank(left) <= risk_rank(right)


ALL_CAPABILITIES = frozenset(ToolCapability)
READ_ONLY_CAPABILITIES = frozenset({
    ToolCapability.WORKSPACE_READ,
    ToolCapability.NETWORK_READ,
})
PLAN_CAPABILITIES = frozenset({
    ToolCapability.WORKSPACE_READ,
    ToolCapability.NETWORK_READ,
    ToolCapability.AGENT_STATE,
})

WORKSPACE_READ_PERMISSION = ToolPermission(
    capabilities=frozenset({ToolCapability.WORKSPACE_READ}),
    risk_level=ToolRiskLevel.LOW,
)
WORKSPACE_WRITE_PERMISSION = ToolPermission(
    capabilities=frozenset({ToolCapability.WORKSPACE_WRITE}),
    risk_level=ToolRiskLevel.MEDIUM,
)
COMMAND_EXECUTE_PERMISSION = ToolPermission(
    capabilities=frozenset({ToolCapability.COMMAND_EXECUTE}),
    risk_level=ToolRiskLevel.HIGH,
)
NETWORK_READ_PERMISSION = ToolPermission(
    capabilities=frozenset({ToolCapability.NETWORK_READ}),
    risk_level=ToolRiskLevel.LOW,
)
AGENT_STATE_PERMISSION = ToolPermission(
    capabilities=frozenset({ToolCapability.AGENT_STATE}),
    risk_level=ToolRiskLevel.MEDIUM,
)
SUBAGENT_CONTROL_PERMISSION = ToolPermission(
    capabilities=frozenset({ToolCapability.SUBAGENT_CONTROL}),
    risk_level=ToolRiskLevel.MEDIUM,
)


BUILTIN_PERMISSION_PROFILES: dict[str, PermissionProfile] = {
    "build_default": PermissionProfile(
        name="build_default",
        allowed_capabilities=ALL_CAPABILITIES,
        auto_approve_max_risk=ToolRiskLevel.MEDIUM,
        approval_required_max_risk=ToolRiskLevel.HIGH,
    ),
    "build_legacy_auto_high_risk": PermissionProfile(
        name="build_legacy_auto_high_risk",
        allowed_capabilities=ALL_CAPABILITIES,
        auto_approve_max_risk=ToolRiskLevel.HIGH,
        approval_required_max_risk=ToolRiskLevel.HIGH,
    ),
    "read_only_default": PermissionProfile(
        name="read_only_default",
        allowed_capabilities=READ_ONLY_CAPABILITIES,
        auto_approve_max_risk=ToolRiskLevel.LOW,
        approval_required_max_risk=ToolRiskLevel.LOW,
    ),
    "plan_default": PermissionProfile(
        name="plan_default",
        allowed_capabilities=PLAN_CAPABILITIES,
        auto_approve_max_risk=ToolRiskLevel.MEDIUM,
        approval_required_max_risk=ToolRiskLevel.MEDIUM,
    ),
    "fail_closed": PermissionProfile(
        name="fail_closed",
        allowed_capabilities=frozenset(),
        auto_approve_max_risk=ToolRiskLevel.LOW,
        approval_required_max_risk=ToolRiskLevel.LOW,
    ),
}


def merge_denied_tools(
    profile: PermissionProfile,
    denied_tools: tuple[str, ...] | frozenset[str],
) -> PermissionProfile:
    if not denied_tools:
        return profile
    return PermissionProfile(
        name=profile.name,
        allowed_capabilities=profile.allowed_capabilities,
        auto_approve_max_risk=profile.auto_approve_max_risk,
        approval_required_max_risk=profile.approval_required_max_risk,
        denied_tools=profile.denied_tools | frozenset(denied_tools),
    )
