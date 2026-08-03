"""Per-orchestration execution context for subagents.

A child subagent run executes in a new asyncio task whose context is copied
from the spawning parent, so a ``ContextVar`` set just before ``create_task``
is visible to every nested subagent loop below it. This module owns the two
contextual values the subagent system needs:

- ``spawn_depth`` — nesting depth of the current run (root loop = 0, a child
  run = parent depth + 1). ``SubAgentManager.run_subagent`` increments it and
  rejects spawns beyond ``max_depth``.
- ``bus`` — the active orchestration message bus (created by ``RunPattern``),
  shared by the orchestrating parent and every worker spawned beneath it.

The contextvar pattern mirrors ``agent/sandbox_events.py`` / ``agent/background.py``.
"""
from __future__ import annotations

from contextvars import ContextVar
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent.subagent.bus import MessageBus

_spawn_depth: ContextVar[int] = ContextVar("subagent_spawn_depth", default=0)
_bus: ContextVar["MessageBus | None"] = ContextVar("subagent_bus", default=None)


def current_spawn_depth() -> int:
    return _spawn_depth.get()


def set_spawn_depth(depth: int) -> Any:
    return _spawn_depth.set(depth)


def reset_spawn_depth(token: Any) -> None:
    _spawn_depth.reset(token)


def current_bus() -> "MessageBus | None":
    return _bus.get()


def set_bus(bus: "MessageBus | None") -> Any:
    return _bus.set(bus)


def reset_bus(token: Any) -> None:
    _bus.reset(token)
