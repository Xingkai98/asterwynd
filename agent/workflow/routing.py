from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from agent.workflow.models import (
    DEFAULT_ROUTING,
    EXECUTORS,
    SESSION_MODES,
    Executor,
    Phase,
    PhaseRouting,
    SessionMode,
)

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = "openspec/config.yaml"
ROUTING_CONFIG_KEY = ("openspec", "routing")


class RoutingConfigError(ValueError):
    pass


def load_global_defaults(
    repo_root: str | Path = ".",
) -> dict[Phase, PhaseRouting]:
    """Load global routing defaults from openspec/config.yaml.

    If the config file or routing section is missing, falls back to DEFAULT_ROUTING.
    """
    config_path = Path(repo_root) / DEFAULT_CONFIG_PATH
    if not config_path.exists():
        logger.debug("no openspec/config.yaml found, using hardcoded defaults")
        return dict(DEFAULT_ROUTING)

    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        logger.warning("failed to parse openspec/config.yaml: %s, using hardcoded defaults", exc)
        return dict(DEFAULT_ROUTING)

    if raw is None or not isinstance(raw, dict):
        return dict(DEFAULT_ROUTING)

    routing_raw = raw.get("routing")
    if routing_raw is None or not isinstance(routing_raw, dict):
        logger.debug("no routing section in config.yaml, using hardcoded defaults")
        return dict(DEFAULT_ROUTING)

    return _parse_routing_dict(routing_raw)


def _parse_routing_dict(raw: dict[str, Any]) -> dict[Phase, PhaseRouting]:
    result: dict[Phase, PhaseRouting] = {}
    for phase_key in ("planning", "reviewing", "building", "code-review", "closing"):
        entry = raw.get(phase_key)
        if entry is None:
            result[phase_key] = DEFAULT_ROUTING[phase_key]
            continue
        if not isinstance(entry, dict):
            raise RoutingConfigError(
                f"routing.{phase_key} must be a mapping, got {type(entry).__name__}"
            )
        result[phase_key] = _parse_phase_routing(phase_key, entry)
    return result


def _parse_phase_routing(phase: str, raw: dict[str, Any]) -> PhaseRouting:
    executor = raw.get("executor", "inline")
    if executor not in EXECUTORS:
        raise RoutingConfigError(
            f"routing.{phase}.executor: invalid executor {executor!r}, "
            f"expected one of {EXECUTORS}"
        )
    session_mode = raw.get("session_mode", "same")
    if session_mode not in SESSION_MODES:
        raise RoutingConfigError(
            f"routing.{phase}.session_mode: invalid session_mode {session_mode!r}, "
            f"expected one of {SESSION_MODES}"
        )

    routing = PhaseRouting(executor=executor, session_mode=session_mode)
    routing = _apply_degradation(routing, phase)
    return routing


def _apply_degradation(routing: PhaseRouting, phase: str) -> PhaseRouting:
    """Apply degradation rules: non-inline executor + session_mode=same degrades to new."""
    if routing.executor != "inline" and routing.session_mode == "same":
        logger.warning(
            "routing.%s: session_mode=same is invalid for executor=%s, degrading to new",
            phase,
            routing.executor,
        )
        return PhaseRouting(executor=routing.executor, session_mode="new")
    return routing


def merge_routing(
    global_defaults: dict[Phase, PhaseRouting],
    per_change: dict[str, Any] | None,
) -> dict[Phase, PhaseRouting]:
    """Merge per-change routing overrides into global defaults.

    Per-change values take precedence; missing phases fall back to global defaults.
    """
    result: dict[Phase, PhaseRouting] = dict(global_defaults)

    if per_change is None:
        return result

    for phase_key in result:
        entry = per_change.get(phase_key)
        if entry is None:
            continue
        if not isinstance(entry, dict):
            continue
        executor = entry.get("executor")
        session_mode = entry.get("session_mode")
        if executor is not None and executor in EXECUTORS:
            current = result[phase_key]
            sm = session_mode if (session_mode is not None and session_mode in SESSION_MODES) else current.session_mode
            candidate = PhaseRouting(executor=executor, session_mode=sm)
            result[phase_key] = _apply_degradation(candidate, phase_key)

    return result


def get_routing_for_phase(
    routing: dict[Phase, PhaseRouting],
    phase: Phase,
) -> PhaseRouting:
    """Get the routing config for a specific phase."""
    if phase in ("blocked", "done"):
        raise RoutingConfigError(f"no routing for terminal phase: {phase}")
    r = routing.get(phase)
    if r is None:
        return DEFAULT_ROUTING.get(phase, PhaseRouting(executor="inline", session_mode="same"))
    return r


def routing_to_dict(routing: dict[Phase, PhaseRouting]) -> dict[str, dict[str, str]]:
    return {phase: r.to_dict() for phase, r in routing.items()}


def build_routing_config_prompt(
    routing: dict[Phase, PhaseRouting] | None = None,
    repo_root: str | Path = ".",
) -> str:
    """Build a prompt for the user to review and optionally adjust routing config.

    Used when creating a new change — shows the defaults and asks if changes are needed.
    """
    if routing is None:
        routing = load_global_defaults(repo_root)

    phase_descriptions = {
        "planning": "方案设计与任务拆解",
        "reviewing": "设计独立评审",
        "building": "代码实现",
        "code-review": "代码审查",
        "closing": "收尾归档",
    }

    executor_labels = {
        "inline": "当前会话直接处理",
        "subagent": "创建子 agent 会话",
        "claude-code": "外部 Claude Code CLI",
        "codex": "外部 Codex CLI",
    }

    session_labels = {
        "same": "复用当前会话",
        "new": "新建会话",
        "ask": "每次询问",
    }

    table_lines = []
    for phase in ("planning", "reviewing", "building", "code-review", "closing"):
        r = routing.get(phase)
        if r is None:
            r = DEFAULT_ROUTING.get(phase, PhaseRouting(executor="inline", session_mode="same"))
        table_lines.append(
            f"| {phase} | {phase_descriptions[phase]} | "
            f"`{r.executor}` ({executor_labels.get(r.executor, r.executor)}) | "
            f"`{r.session_mode}` ({session_labels.get(r.session_mode, r.session_mode)}) |"
        )

    table = "\n".join([
        "| 阶段 | 说明 | Executor | Session Mode |",
        "|------|------|----------|-------------|",
        *table_lines,
    ])

    return f"""## 路由配置确认

当前 change 将使用以下默认路由配置：

{table}

如果需要调整某个阶段的 executor 或 session_mode，请告知具体修改。可用选项：

- **Executor**: `inline`（当前会话）、`subagent`（子 agent 会话）、`claude-code`（外部 Claude Code CLI）、`codex`（外部 Codex CLI）
- **Session Mode**: `same`（复用当前会话）、`new`（新建会话）、`ask`（每次询问）

回复「确认」使用默认值，或指定要修改的阶段和参数。"""
