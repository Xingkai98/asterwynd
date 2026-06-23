from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import yaml

from agent.run_config import AgentMode, parse_agent_mode
from agent.tool_result_display import ToolResultDisplayConfig


CONFIG_FILENAME = "myagent.yaml"


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class AgentConfig:
    default_mode: AgentMode = AgentMode.BUILD


@dataclass(frozen=True)
class ModeConfig:
    deny_tools: tuple[str, ...] = ()


@dataclass(frozen=True)
class ToolsConfig:
    ignore_patterns: tuple[str, ...] = ()
    command_denylist: tuple[str, ...] = ()
    display: ToolResultDisplayConfig = field(default_factory=ToolResultDisplayConfig)


@dataclass(frozen=True)
class BenchmarkConfig:
    parallel: int = 1
    timeout_seconds: int = 600


@dataclass(frozen=True)
class MyAgentConfig:
    path: Path | None = None
    agent: AgentConfig = field(default_factory=AgentConfig)
    modes: dict[AgentMode, ModeConfig] = field(default_factory=dict)
    tools: ToolsConfig = field(default_factory=ToolsConfig)
    benchmark: BenchmarkConfig = field(default_factory=BenchmarkConfig)

    def __post_init__(self) -> None:
        if not self.modes:
            object.__setattr__(self, "modes", _default_modes())

    def mode_config(self, mode: AgentMode) -> ModeConfig:
        return self.modes.get(mode, ModeConfig())

    def deny_tools_by_mode(self) -> dict[AgentMode, tuple[str, ...]]:
        return {
            mode: mode_config.deny_tools
            for mode, mode_config in self.modes.items()
            if mode_config.deny_tools
        }


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
) -> MyAgentConfig:
    path = _resolve_config_path(config_path, start_dir)
    config = _load_yaml_config(path)
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


def _load_yaml_config(path: Path | None) -> MyAgentConfig:
    if path is None:
        return MyAgentConfig()

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in {path}: {exc}") from exc

    if raw is None:
        return MyAgentConfig(path=path)
    if not isinstance(raw, dict):
        raise ConfigError(f"{path}: top-level YAML value must be a mapping")

    return MyAgentConfig(
        path=path,
        agent=_parse_agent_config(raw.get("agent", {}), path),
        modes=_parse_modes_config(raw.get("modes", {}), path),
        tools=_parse_tools_config(raw.get("tools", {}), path),
        benchmark=_parse_benchmark_config(raw.get("benchmark", {}), path),
    )


def _apply_environment(config: MyAgentConfig) -> MyAgentConfig:
    agent = config.agent
    if mode := os.environ.get("MYAGENT_MODE"):
        try:
            agent = replace(agent, default_mode=parse_agent_mode(mode))
        except ValueError as exc:
            raise ConfigError(f"MYAGENT_MODE: {exc}") from exc

    benchmark = config.benchmark
    if parallel := os.environ.get("MYAGENT_BENCHMARK_PARALLEL"):
        benchmark = replace(
            benchmark,
            parallel=_parse_positive_int(parallel, "MYAGENT_BENCHMARK_PARALLEL"),
        )
    if timeout := os.environ.get("MYAGENT_BENCHMARK_TIMEOUT"):
        benchmark = replace(
            benchmark,
            timeout_seconds=_parse_positive_int(timeout, "MYAGENT_BENCHMARK_TIMEOUT"),
        )

    return replace(config, agent=agent, benchmark=benchmark)


def _apply_cli_overrides(config: MyAgentConfig, overrides: ConfigOverrides) -> MyAgentConfig:
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
            )
        )
    return modes


def _parse_tools_config(raw: Any, path: Path) -> ToolsConfig:
    mapping = _expect_mapping(raw, path, "tools")
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
        display=_parse_tool_display_config(mapping.get("display", {}), path),
    )


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
