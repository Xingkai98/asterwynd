from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Literal

import yaml

from agent.code_intelligence.config import (
    DEFAULT_LSP_INITIALIZE_TIMEOUT_MS,
    DEFAULT_LSP_REQUEST_TIMEOUT_MS,
    CodeIntelligenceConfig,
    LspConfig,
    LspServerConfig,
)
from agent.run_config import AgentMode, parse_agent_mode
from agent.tool_permissions import (
    BUILTIN_PERMISSION_PROFILES,
    PermissionProfile,
    ToolCapability,
    ToolPermission,
    ToolOrigin,
    ToolRiskLevel,
)
from agent.tool_result_display import ToolResultDisplayConfig


CONFIG_FILENAME = "asterwynd.yaml"
SUPPORTED_SEARCH_PROVIDER_NAMES = frozenset(
    {"duckduckgo-html", "searxng", "brave", "tavily"}
)


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class AgentConfig:
    default_mode: AgentMode = AgentMode.BUILD


@dataclass(frozen=True)
class ModeConfig:
    deny_tools: tuple[str, ...] = ()
    permission_profile: str | None = None


@dataclass(frozen=True)
class PermissionsConfig:
    profiles: dict[str, PermissionProfile] = field(default_factory=dict)


@dataclass(frozen=True)
class SearchProviderConfig:
    name: str
    enabled: bool = True


@dataclass(frozen=True)
class WebSearchConfig:
    providers: tuple[SearchProviderConfig, ...] = ()


@dataclass(frozen=True)
class ToolsConfig:
    ignore_patterns: tuple[str, ...] = ()
    command_denylist: tuple[str, ...] = ()
    code_intelligence: CodeIntelligenceConfig = field(default_factory=CodeIntelligenceConfig)
    web_search: WebSearchConfig = field(default_factory=WebSearchConfig)
    display: ToolResultDisplayConfig = field(default_factory=ToolResultDisplayConfig)


@dataclass(frozen=True)
class McpHeaderValueConfig:
    value: str | None = None
    env: str | None = None


@dataclass(frozen=True)
class McpActionPermissionConfig:
    capabilities: tuple[ToolCapability, ...]
    risk_level: ToolRiskLevel

    def to_permission(self) -> ToolPermission:
        return ToolPermission(
            capabilities=frozenset(self.capabilities),
            risk_level=self.risk_level,
            origin=ToolOrigin.MCP,
        )


@dataclass(frozen=True)
class McpServerConfig:
    name: str
    type: Literal["stdio", "streamable_http"]
    enabled: bool = True
    required: bool = False
    command: str | None = None
    args: tuple[str, ...] = ()
    cwd: Path | None = None
    env: dict[str, str] = field(default_factory=dict)
    url: str | None = None
    headers: dict[str, McpHeaderValueConfig] = field(default_factory=dict)
    startup_timeout_seconds: int = 10
    tool_timeout_seconds: int = 30
    default_permission: McpActionPermissionConfig | None = None
    tools: dict[str, McpActionPermissionConfig] = field(default_factory=dict)
    prompts: dict[str, McpActionPermissionConfig] = field(default_factory=dict)
    resources: dict[str, McpActionPermissionConfig] = field(default_factory=dict)


@dataclass(frozen=True)
class McpConfig:
    default_timeout_seconds: int = 30
    servers: dict[str, McpServerConfig] = field(default_factory=dict)


@dataclass(frozen=True)
class BenchmarkConfig:
    parallel: int = 1
    timeout_seconds: int = 600


@dataclass(frozen=True)
class SkillsConfig:
    roots: tuple[Path, ...] = ()


@dataclass(frozen=True)
class AsterwyndConfig:
    path: Path | None = None
    agent: AgentConfig = field(default_factory=AgentConfig)
    modes: dict[AgentMode, ModeConfig] = field(default_factory=dict)
    permissions: PermissionsConfig = field(default_factory=PermissionsConfig)
    tools: ToolsConfig = field(default_factory=ToolsConfig)
    mcp: McpConfig = field(default_factory=McpConfig)
    skills: SkillsConfig = field(default_factory=SkillsConfig)
    benchmark: BenchmarkConfig = field(default_factory=BenchmarkConfig)

    def __post_init__(self) -> None:
        if not self.modes:
            object.__setattr__(self, "modes", _default_modes())
        if not self.skills.roots:
            base = self.path.parent if self.path else Path.cwd()
            object.__setattr__(self, "skills", SkillsConfig(roots=(base / "skills",)))
        self.permission_profiles_by_mode()

    def mode_config(self, mode: AgentMode) -> ModeConfig:
        return self.modes.get(mode, ModeConfig())

    def deny_tools_by_mode(self) -> dict[AgentMode, tuple[str, ...]]:
        return {
            mode: mode_config.deny_tools
            for mode, mode_config in self.modes.items()
            if mode_config.deny_tools
        }

    def permission_profiles_by_mode(self) -> dict[AgentMode, PermissionProfile]:
        profiles = {**BUILTIN_PERMISSION_PROFILES, **self.permissions.profiles}
        resolved: dict[AgentMode, PermissionProfile] = {}
        defaults = {
            AgentMode.BUILD: "build_default",
            AgentMode.READ_ONLY: "read_only_default",
            AgentMode.PLAN: "plan_default",
            AgentMode.BYPASS: "fail_closed",
        }
        for mode in AgentMode:
            profile_name = self.mode_config(mode).permission_profile or defaults[mode]
            try:
                resolved[mode] = profiles[profile_name]
            except KeyError as exc:
                raise ConfigError(
                    f"Unknown permission_profile {profile_name!r} for mode {mode.value}"
                ) from exc
        return resolved


@dataclass(frozen=True)
class ConfigOverrides:
    default_mode: str | AgentMode | None = None
    benchmark_parallel: int | None = None
    benchmark_timeout_seconds: int | None = None


def load_config(
    config_path: str | Path | None = None,
    *,
    start_dir: str | Path | None = None,
    cli_overrides: ConfigOverrides | None = None,
) -> AsterwyndConfig:
    path = _resolve_config_path(config_path, start_dir)
    config = _load_yaml_config(path, start_dir=start_dir)
    config = _apply_environment(config)
    if cli_overrides:
        config = _apply_cli_overrides(config, cli_overrides)
    return config


def _resolve_config_path(
    config_path: str | Path | None,
    start_dir: str | Path | None,
) -> Path | None:
    if config_path is not None:
        path = Path(config_path).expanduser().resolve()
        if not path.exists():
            raise ConfigError(f"Config file not found: {path}")
        if not path.is_file():
            raise ConfigError(f"Config path is not a file: {path}")
        return path
    return find_config_path(start_dir=start_dir)


def find_config_path(start_dir: str | Path | None = None) -> Path | None:
    current = Path(start_dir or Path.cwd()).resolve()
    if current.is_file():
        current = current.parent
    boundary = _find_git_root(current) or current

    while True:
        candidate = current / CONFIG_FILENAME
        if candidate.is_file():
            return candidate
        if current == boundary or current.parent == current:
            return None
        current = current.parent


def _find_git_root(start: Path) -> Path | None:
    current = start
    while True:
        if (current / ".git").exists():
            return current
        if current.parent == current:
            return None
        current = current.parent


def _load_yaml_config(
    path: Path | None,
    *,
    start_dir: str | Path | None = None,
) -> AsterwyndConfig:
    if path is None:
        base = Path(start_dir or Path.cwd()).resolve()
        if base.is_file():
            base = base.parent
        return AsterwyndConfig(skills=SkillsConfig(roots=(base / "skills",)))

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in {path}: {exc}") from exc

    if raw is None:
        return AsterwyndConfig(path=path)
    if not isinstance(raw, dict):
        raise ConfigError(f"{path}: top-level YAML value must be a mapping")

    return AsterwyndConfig(
        path=path,
        agent=_parse_agent_config(raw.get("agent", {}), path),
        modes=_parse_modes_config(raw.get("modes", {}), path),
        permissions=_parse_permissions_config(raw.get("permissions", {}), path),
        tools=_parse_tools_config(raw.get("tools", {}), path),
        mcp=_parse_mcp_config(raw.get("mcp", {}), path),
        skills=_parse_skills_config(raw.get("skills", {}), path),
        benchmark=_parse_benchmark_config(raw.get("benchmark", {}), path),
    )


def _apply_environment(config: AsterwyndConfig) -> AsterwyndConfig:
    agent = config.agent
    if mode := os.environ.get("ASTERWYND_MODE"):
        try:
            agent = replace(agent, default_mode=parse_agent_mode(mode))
        except ValueError as exc:
            raise ConfigError(f"ASTERWYND_MODE: {exc}") from exc

    benchmark = config.benchmark
    if parallel := os.environ.get("ASTERWYND_BENCHMARK_PARALLEL"):
        benchmark = replace(
            benchmark,
            parallel=_parse_positive_int(parallel, "ASTERWYND_BENCHMARK_PARALLEL"),
        )
    if timeout := os.environ.get("ASTERWYND_BENCHMARK_TIMEOUT"):
        benchmark = replace(
            benchmark,
            timeout_seconds=_parse_positive_int(timeout, "ASTERWYND_BENCHMARK_TIMEOUT"),
        )

    return replace(config, agent=agent, benchmark=benchmark)


def _apply_cli_overrides(config: AsterwyndConfig, overrides: ConfigOverrides) -> AsterwyndConfig:
    agent = config.agent
    if overrides.default_mode is not None:
        mode = overrides.default_mode
        if not isinstance(mode, AgentMode):
            try:
                mode = parse_agent_mode(mode)
            except ValueError as exc:
                raise ConfigError(str(exc)) from exc
        agent = replace(agent, default_mode=mode)

    benchmark = config.benchmark
    if overrides.benchmark_parallel is not None:
        benchmark = replace(
            benchmark,
            parallel=_validate_positive_int(
                overrides.benchmark_parallel,
                "benchmark_parallel",
            ),
        )
    if overrides.benchmark_timeout_seconds is not None:
        benchmark = replace(
            benchmark,
            timeout_seconds=_validate_positive_int(
                overrides.benchmark_timeout_seconds,
                "benchmark_timeout_seconds",
            ),
        )

    return replace(config, agent=agent, benchmark=benchmark)


def _parse_agent_config(raw: Any, path: Path) -> AgentConfig:
    mapping = _expect_mapping(raw, path, "agent")
    raw_mode = mapping.get("default_mode", AgentMode.BUILD.value)
    if not isinstance(raw_mode, str):
        raise ConfigError(f"{path}: agent.default_mode must be a string")
    try:
        mode = parse_agent_mode(raw_mode)
    except ValueError as exc:
        raise ConfigError(f"{path}: agent.default_mode: {exc}") from exc
    return AgentConfig(default_mode=mode)


def _parse_modes_config(raw: Any, path: Path) -> dict[AgentMode, ModeConfig]:
    mapping = _expect_mapping(raw, path, "modes")
    modes = _default_modes()
    for raw_mode, raw_config in mapping.items():
        if not isinstance(raw_mode, str):
            raise ConfigError(f"{path}: modes keys must be strings")
        try:
            mode = parse_agent_mode(raw_mode)
        except ValueError as exc:
            raise ConfigError(f"{path}: modes.{raw_mode}: {exc}") from exc
        mode_mapping = _expect_mapping(raw_config, path, f"modes.{raw_mode}")
        modes[mode] = ModeConfig(
            deny_tools=_parse_string_list(
                mode_mapping.get("deny_tools", []),
                path,
                f"modes.{raw_mode}.deny_tools",
            ),
            permission_profile=_parse_optional_string(
                mode_mapping.get("permission_profile"),
                path,
                f"modes.{raw_mode}.permission_profile",
            ),
        )
    return modes


def _parse_permissions_config(raw: Any, path: Path) -> PermissionsConfig:
    mapping = _expect_mapping(raw, path, "permissions")
    profiles_mapping = _expect_mapping(
        mapping.get("profiles", {}),
        path,
        "permissions.profiles",
    )
    profiles: dict[str, PermissionProfile] = {}
    for profile_name, raw_profile in profiles_mapping.items():
        if not isinstance(profile_name, str) or not profile_name.strip():
            raise ConfigError(f"{path}: permissions.profiles keys must be non-empty strings")
        profile_name = profile_name.strip()
        if profile_name in BUILTIN_PERMISSION_PROFILES:
            raise ConfigError(
                f"{path}: permissions.profiles.{profile_name} cannot override a built-in profile"
            )
        profile_mapping = _expect_mapping(
            raw_profile,
            path,
            f"permissions.profiles.{profile_name}",
        )
        try:
            profiles[profile_name] = PermissionProfile(
                name=profile_name,
                allowed_capabilities=frozenset(
                    _parse_capabilities(
                        profile_mapping.get("allowed_capabilities", []),
                        path,
                        f"permissions.profiles.{profile_name}.allowed_capabilities",
                    )
                ),
                auto_approve_max_risk=_parse_risk_level(
                    profile_mapping.get("auto_approve_max_risk"),
                    path,
                    f"permissions.profiles.{profile_name}.auto_approve_max_risk",
                ),
                approval_required_max_risk=_parse_risk_level(
                    profile_mapping.get("approval_required_max_risk"),
                    path,
                    f"permissions.profiles.{profile_name}.approval_required_max_risk",
                ),
                denied_tools=frozenset(
                    _parse_string_list(
                        profile_mapping.get("denied_tools", []),
                        path,
                        f"permissions.profiles.{profile_name}.denied_tools",
                    )
                ),
            )
        except ValueError as exc:
            raise ConfigError(f"{path}: permissions.profiles.{profile_name}: {exc}") from exc
    return PermissionsConfig(profiles=profiles)


def _parse_tools_config(raw: Any, path: Path) -> ToolsConfig:
    mapping = _expect_mapping(raw, path, "tools")
    if "mcp" in mapping:
        raise ConfigError(f"{path}: tools.mcp is unsupported; use top-level mcp.servers")
    return ToolsConfig(
        ignore_patterns=_parse_string_list(
            mapping.get("ignore_patterns", []),
            path,
            "tools.ignore_patterns",
        ),
        command_denylist=_parse_string_list(
            mapping.get("command_denylist", []),
            path,
            "tools.command_denylist",
        ),
        code_intelligence=_parse_code_intelligence_config(
            mapping.get("code_intelligence", {}),
            path,
        ),
        web_search=_parse_web_search_config(mapping.get("web_search", {}), path),
        display=_parse_tool_display_config(mapping.get("display", {}), path),
    )


def _parse_mcp_config(raw: Any, path: Path) -> McpConfig:
    mapping = _expect_mapping(raw, path, "mcp")
    default_timeout_seconds = _validate_positive_int(
        mapping.get("default_timeout_seconds", 30),
        "mcp.default_timeout_seconds",
        path=path,
    )
    servers_mapping = _expect_mapping(mapping.get("servers", {}), path, "mcp.servers")
    servers: dict[str, McpServerConfig] = {}
    base_dir = path.parent
    for server_name, raw_server in servers_mapping.items():
        if not isinstance(server_name, str) or not server_name.strip():
            raise ConfigError(f"{path}: mcp.servers keys must be non-empty strings")
        server_name = server_name.strip()
        field_name = f"mcp.servers.{server_name}"
        server_mapping = _expect_mapping(raw_server, path, field_name)
        server_type = server_mapping.get("type")
        if server_type not in {"stdio", "streamable_http"}:
            raise ConfigError(
                f"{path}: {field_name}.type must be 'stdio' or 'streamable_http'"
            )
        enabled = _parse_bool(server_mapping.get("enabled", True), path, f"{field_name}.enabled")
        required = _parse_bool(server_mapping.get("required", False), path, f"{field_name}.required")
        startup_timeout = _validate_positive_int(
            server_mapping.get("startup_timeout_seconds", default_timeout_seconds),
            f"{field_name}.startup_timeout_seconds",
            path=path,
        )
        tool_timeout = _validate_positive_int(
            server_mapping.get("tool_timeout_seconds", default_timeout_seconds),
            f"{field_name}.tool_timeout_seconds",
            path=path,
        )
        common = {
            "name": server_name,
            "type": server_type,
            "enabled": enabled,
            "required": required,
            "startup_timeout_seconds": startup_timeout,
            "tool_timeout_seconds": tool_timeout,
            "default_permission": _parse_optional_mcp_permission(
                server_mapping.get("default_permission"),
                path,
                f"{field_name}.default_permission",
            ),
            "tools": _parse_mcp_permission_map(
                server_mapping.get("tools", {}),
                path,
                f"{field_name}.tools",
            ),
            "prompts": _parse_mcp_permission_map(
                server_mapping.get("prompts", {}),
                path,
                f"{field_name}.prompts",
            ),
            "resources": _parse_mcp_permission_map(
                server_mapping.get("resources", {}),
                path,
                f"{field_name}.resources",
            ),
        }
        if server_type == "stdio":
            command = _parse_optional_string(
                server_mapping.get("command"),
                path,
                f"{field_name}.command",
            )
            if command is None:
                raise ConfigError(f"{path}: {field_name}.command is required for stdio")
            cwd = _parse_optional_path(server_mapping.get("cwd"), path, f"{field_name}.cwd")
            if cwd is not None and not cwd.is_absolute():
                cwd = base_dir / cwd
            servers[server_name] = McpServerConfig(
                **common,
                command=command,
                args=_parse_string_list(
                    server_mapping.get("args", []),
                    path,
                    f"{field_name}.args",
                ),
                cwd=cwd,
                env=_parse_string_mapping(server_mapping.get("env", {}), path, f"{field_name}.env"),
            )
        else:
            url = _parse_optional_string(server_mapping.get("url"), path, f"{field_name}.url")
            if url is None:
                raise ConfigError(f"{path}: {field_name}.url is required for streamable_http")
            servers[server_name] = McpServerConfig(
                **common,
                url=url,
                headers=_parse_mcp_headers(
                    server_mapping.get("headers", {}),
                    path,
                    f"{field_name}.headers",
                ),
            )
    return McpConfig(
        default_timeout_seconds=default_timeout_seconds,
        servers=servers,
    )


def _parse_optional_path(raw: Any, path: Path, field_name: str) -> Path | None:
    if raw is None:
        return None
    if not isinstance(raw, str) or not raw.strip():
        raise ConfigError(f"{path}: {field_name} must be a non-empty string")
    return Path(os.path.expandvars(raw.strip())).expanduser()


def _parse_string_mapping(raw: Any, path: Path, field_name: str) -> dict[str, str]:
    mapping = _expect_mapping(raw, path, field_name)
    parsed: dict[str, str] = {}
    for key, value in mapping.items():
        if not isinstance(key, str) or not key.strip():
            raise ConfigError(f"{path}: {field_name} keys must be non-empty strings")
        if not isinstance(value, str):
            raise ConfigError(f"{path}: {field_name}.{key} must be a string")
        parsed[key.strip()] = os.path.expandvars(value)
    return parsed


def _parse_mcp_headers(raw: Any, path: Path, field_name: str) -> dict[str, McpHeaderValueConfig]:
    mapping = _expect_mapping(raw, path, field_name)
    parsed: dict[str, McpHeaderValueConfig] = {}
    for key, value in mapping.items():
        if not isinstance(key, str) or not key.strip():
            raise ConfigError(f"{path}: {field_name} keys must be non-empty strings")
        header_name = key.strip()
        if isinstance(value, str):
            parsed[header_name] = McpHeaderValueConfig(value=os.path.expandvars(value))
            continue
        value_mapping = _expect_mapping(value, path, f"{field_name}.{header_name}")
        direct_value = value_mapping.get("value")
        env_value = value_mapping.get("env")
        if direct_value is not None and env_value is not None:
            raise ConfigError(
                f"{path}: {field_name}.{header_name} must use either value or env"
            )
        if direct_value is None and env_value is None:
            raise ConfigError(
                f"{path}: {field_name}.{header_name} must define value or env"
            )
        parsed[header_name] = McpHeaderValueConfig(
            value=_parse_optional_string(direct_value, path, f"{field_name}.{header_name}.value"),
            env=_parse_optional_string(env_value, path, f"{field_name}.{header_name}.env"),
        )
    return parsed


def _parse_optional_mcp_permission(
    raw: Any, path: Path, field_name: str
) -> McpActionPermissionConfig | None:
    if raw is None:
        return None
    return _parse_mcp_permission(raw, path, field_name)


def _parse_mcp_permission_map(
    raw: Any, path: Path, field_name: str
) -> dict[str, McpActionPermissionConfig]:
    mapping = _expect_mapping(raw, path, field_name)
    parsed: dict[str, McpActionPermissionConfig] = {}
    for action_name, raw_permission in mapping.items():
        if not isinstance(action_name, str) or not action_name.strip():
            raise ConfigError(f"{path}: {field_name} keys must be non-empty strings")
        parsed[action_name.strip()] = _parse_mcp_permission(
            raw_permission,
            path,
            f"{field_name}.{action_name}",
        )
    return parsed


def _parse_mcp_permission(
    raw: Any, path: Path, field_name: str
) -> McpActionPermissionConfig:
    mapping = _expect_mapping(raw, path, field_name)
    return McpActionPermissionConfig(
        capabilities=_parse_capabilities(
            mapping.get("capabilities", []),
            path,
            f"{field_name}.capabilities",
        ),
        risk_level=_parse_risk_level(
            mapping.get("risk_level"),
            path,
            f"{field_name}.risk_level",
        ),
    )


def _parse_code_intelligence_config(raw: Any, path: Path) -> CodeIntelligenceConfig:
    mapping = _expect_mapping(raw, path, "tools.code_intelligence")
    defaults = CodeIntelligenceConfig()
    return CodeIntelligenceConfig(
        tree_sitter_max_file_bytes=_validate_positive_int(
            mapping.get(
                "tree_sitter_max_file_bytes",
                defaults.tree_sitter_max_file_bytes,
            ),
            "tools.code_intelligence.tree_sitter_max_file_bytes",
            path=path,
        ),
        lsp=_parse_lsp_config(mapping.get("lsp", {}), path),
    )


def _parse_lsp_config(raw: Any, path: Path) -> LspConfig:
    mapping = _expect_mapping(raw, path, "tools.code_intelligence.lsp")
    defaults = LspConfig()

    servers_raw = mapping.get("servers", [])
    if servers_raw is None:
        servers: tuple[LspServerConfig, ...] = ()
    else:
        if not isinstance(servers_raw, list):
            raise ConfigError(
                f"{path}: tools.code_intelligence.lsp.servers must be a list"
            )
        parsed_servers: list[LspServerConfig] = []
        for index, raw_server in enumerate(servers_raw):
            field_name = f"tools.code_intelligence.lsp.servers[{index}]"
            parsed_servers.append(
                _parse_lsp_server_config(raw_server, path, field_name)
            )
        servers = tuple(parsed_servers)

    return LspConfig(
        servers=servers,
        default_request_timeout_ms=_validate_positive_int(
            mapping.get(
                "default_request_timeout_ms",
                defaults.default_request_timeout_ms,
            ),
            "tools.code_intelligence.lsp.default_request_timeout_ms",
            path=path,
        ),
        max_diagnostics_per_file=_validate_positive_int(
            mapping.get(
                "max_diagnostics_per_file",
                defaults.max_diagnostics_per_file,
            ),
            "tools.code_intelligence.lsp.max_diagnostics_per_file",
            path=path,
        ),
        max_references=_validate_positive_int(
            mapping.get("max_references", defaults.max_references),
            "tools.code_intelligence.lsp.max_references",
            path=path,
        ),
        max_workspace_symbols=_validate_positive_int(
            mapping.get(
                "max_workspace_symbols",
                defaults.max_workspace_symbols,
            ),
            "tools.code_intelligence.lsp.max_workspace_symbols",
            path=path,
        ),
        diagnostic_message_max_chars=_validate_positive_int(
            mapping.get(
                "diagnostic_message_max_chars",
                defaults.diagnostic_message_max_chars,
            ),
            "tools.code_intelligence.lsp.diagnostic_message_max_chars",
            path=path,
        ),
    )


def _parse_lsp_server_config(
    raw: Any, path: Path, field_name: str
) -> LspServerConfig:
    mapping = _expect_mapping(raw, path, field_name)

    language = mapping.get("language")
    if not isinstance(language, str) or not language.strip():
        raise ConfigError(
            f"{path}: {field_name}.language must be a non-empty string"
        )

    command_raw = mapping.get("command")
    if isinstance(command_raw, str):
        command = (command_raw,)
    elif isinstance(command_raw, list):
        command = tuple(
            _validate_string_item(item, path, f"{field_name}.command")
            for item in command_raw
        )
    else:
        raise ConfigError(
            f"{path}: {field_name}.command must be a string or list of strings"
        )
    if not command:
        raise ConfigError(f"{path}: {field_name}.command must not be empty")

    args_raw = mapping.get("args", [])
    if isinstance(args_raw, str):
        args = (args_raw,)
    elif isinstance(args_raw, list):
        args = tuple(
            _validate_string_item(item, path, f"{field_name}.args")
            for item in args_raw
        )
    else:
        raise ConfigError(
            f"{path}: {field_name}.args must be a string or list of strings"
        )

    root_markers_raw = mapping.get("root_markers", ["pyproject.toml"])
    if not isinstance(root_markers_raw, list):
        raise ConfigError(
            f"{path}: {field_name}.root_markers must be a list of strings"
        )
    root_markers = tuple(
        _validate_string_item(item, path, f"{field_name}.root_markers")
        for item in root_markers_raw
    )
    if not root_markers:
        raise ConfigError(
            f"{path}: {field_name}.root_markers must not be empty"
        )

    return LspServerConfig(
        language=language.strip(),
        command=command,
        args=args,
        root_markers=root_markers,
        initialize_timeout_ms=_validate_positive_int(
            mapping.get("initialize_timeout_ms", DEFAULT_LSP_INITIALIZE_TIMEOUT_MS),
            f"{field_name}.initialize_timeout_ms",
            path=path,
        ),
        request_timeout_ms=_validate_positive_int(
            mapping.get("request_timeout_ms", DEFAULT_LSP_REQUEST_TIMEOUT_MS),
            f"{field_name}.request_timeout_ms",
            path=path,
        ),
        enabled=bool(mapping.get("enabled", True)),
    )


def _validate_string_item(item: Any, path: Path, field_name: str) -> str:
    if not isinstance(item, str) or not item:
        raise ConfigError(
            f"{path}: {field_name} must contain only non-empty strings"
        )
    return item


def _parse_optional_string(raw: Any, path: Path, field_name: str) -> str | None:
    if raw is None:
        return None
    if not isinstance(raw, str) or not raw.strip():
        raise ConfigError(f"{path}: {field_name} must be a non-empty string")
    return raw.strip()


def _parse_capabilities(raw: Any, path: Path, field_name: str) -> tuple[ToolCapability, ...]:
    values = _parse_string_list(raw, path, field_name)
    if not values:
        raise ConfigError(f"{path}: {field_name} must not be empty")
    parsed = []
    for value in values:
        try:
            parsed.append(ToolCapability(value))
        except ValueError as exc:
            supported = ", ".join(capability.value for capability in ToolCapability)
            raise ConfigError(
                f"{path}: {field_name} unsupported capability {value!r}; "
                f"expected one of: {supported}"
            ) from exc
    return tuple(parsed)


def _parse_risk_level(raw: Any, path: Path, field_name: str) -> ToolRiskLevel:
    if not isinstance(raw, str) or not raw.strip():
        raise ConfigError(f"{path}: {field_name} must be a non-empty string")
    try:
        return ToolRiskLevel(raw.strip())
    except ValueError as exc:
        supported = ", ".join(level.value for level in ToolRiskLevel)
        raise ConfigError(
            f"{path}: {field_name} unsupported risk level {raw!r}; "
            f"expected one of: {supported}"
        ) from exc


def _parse_web_search_config(raw: Any, path: Path) -> WebSearchConfig:
    mapping = _expect_mapping(raw, path, "tools.web_search")
    providers_raw = mapping.get("providers", [])
    if providers_raw is None:
        return WebSearchConfig()
    if not isinstance(providers_raw, list):
        raise ConfigError(f"{path}: tools.web_search.providers must be a list")

    providers = []
    for index, raw_provider in enumerate(providers_raw):
        field_name = f"tools.web_search.providers[{index}]"
        if isinstance(raw_provider, str):
            name = raw_provider.strip()
            enabled = True
        else:
            provider_mapping = _expect_mapping(raw_provider, path, field_name)
            raw_name = provider_mapping.get("name")
            if not isinstance(raw_name, str) or not raw_name.strip():
                raise ConfigError(f"{path}: {field_name}.name must be a non-empty string")
            name = raw_name.strip()
            raw_enabled = provider_mapping.get("enabled", True)
            if not isinstance(raw_enabled, bool):
                raise ConfigError(f"{path}: {field_name}.enabled must be a boolean")
            enabled = raw_enabled
        if name not in SUPPORTED_SEARCH_PROVIDER_NAMES:
            supported = ", ".join(sorted(SUPPORTED_SEARCH_PROVIDER_NAMES))
            raise ConfigError(
                f"{path}: {field_name}.name unsupported search provider "
                f"{name!r}; expected one of: {supported}"
            )
        providers.append(SearchProviderConfig(name=name, enabled=enabled))
    return WebSearchConfig(providers=tuple(providers))


def _parse_tool_display_config(raw: Any, path: Path) -> ToolResultDisplayConfig:
    mapping = _expect_mapping(raw, path, "tools.display")
    defaults = ToolResultDisplayConfig()
    return ToolResultDisplayConfig(
        max_result_chars=_validate_positive_int(
            mapping.get("max_result_chars", defaults.max_result_chars),
            "tools.display.max_result_chars",
            path=path,
        ),
        max_result_lines=_validate_positive_int(
            mapping.get("max_result_lines", defaults.max_result_lines),
            "tools.display.max_result_lines",
            path=path,
        ),
        preview_chars=_validate_positive_int(
            mapping.get("preview_chars", defaults.preview_chars),
            "tools.display.preview_chars",
            path=path,
        ),
    )


def _parse_skills_config(raw: Any, path: Path) -> SkillsConfig:
    mapping = _expect_mapping(raw, path, "skills")
    base = path.parent
    roots = [base / "skills"]
    for item in _parse_string_list(mapping.get("roots", []), path, "skills.roots"):
        expanded = os.path.expandvars(item)
        candidate = Path(expanded).expanduser()
        if not candidate.is_absolute():
            candidate = base / candidate
        roots.append(candidate.resolve())
    normalized = []
    seen = set()
    for root in roots:
        resolved = root.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        normalized.append(resolved)
    return SkillsConfig(roots=tuple(normalized))


def _parse_benchmark_config(raw: Any, path: Path) -> BenchmarkConfig:
    mapping = _expect_mapping(raw, path, "benchmark")
    return BenchmarkConfig(
        parallel=_validate_positive_int(
            mapping.get("parallel", 1),
            "benchmark.parallel",
            path=path,
        ),
        timeout_seconds=_validate_positive_int(
            mapping.get("timeout_seconds", 600),
            "benchmark.timeout_seconds",
            path=path,
        ),
    )


def _expect_mapping(raw: Any, path: Path, field_name: str) -> dict[str, Any]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ConfigError(f"{path}: {field_name} must be a mapping")
    return raw


def _parse_string_list(raw: Any, path: Path, field_name: str) -> tuple[str, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ConfigError(f"{path}: {field_name} must be a list of strings")
    values = []
    for item in raw:
        if not isinstance(item, str):
            raise ConfigError(f"{path}: {field_name} must be a list of strings")
        stripped = item.strip()
        if stripped:
            values.append(stripped)
    return tuple(values)


def _parse_bool(raw: Any, path: Path, field_name: str) -> bool:
    if not isinstance(raw, bool):
        raise ConfigError(f"{path}: {field_name} must be a boolean")
    return raw


def _parse_positive_int(raw: str, field_name: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{field_name} must be a positive integer") from exc
    return _validate_positive_int(value, field_name)


def _validate_positive_int(
    raw: Any,
    field_name: str,
    *,
    path: Path | None = None,
) -> int:
    if not isinstance(raw, int) or raw < 1:
        prefix = f"{path}: " if path else ""
        raise ConfigError(f"{prefix}{field_name} must be a positive integer")
    return raw


def _default_modes() -> dict[AgentMode, ModeConfig]:
    return {mode: ModeConfig() for mode in AgentMode}
