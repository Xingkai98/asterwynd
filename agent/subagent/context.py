"""Per-orchestration execution context for subagents.

A child subagent run executes in a new asyncio task whose context is copied
from the spawning parent, so a ``ContextVar`` set just before ``create_task``
is visible to every nested subagent loop below it. This module owns the two
contextual values the subagent system needs:

- ``spawn_depth`` — nesting depth of the current run (root loop = 0, a child
  run = parent depth + 1). ``SubAgentManager.run_subagent`` increments it and
  rejects spawns beyond ``max_depth``.
- ``bus`` — the active orchestration message bus (created by the Workflow entry,
  installed at the scheduler dispatch point), shared by the orchestrating parent
  and every worker spawned beneath it.
- ``current_run_id`` — run id of the subagent run whose loop is executing in
  this context, so a spawn can record its logical ``parent_run_id`` before it
  is queued (decision D6).
- ``workflow_id`` / ``node_id`` — optional orchestration identity of the
  current context (reserved for the workflow-DSL follow-up, C2), recorded on
  the session so delayed runs stay attributable.
- ``mode_ceiling`` — the **effective mode upper bound** of the current
  execution unit (change ``fix-issue-255-mode-ceiling``). A workflow node's
  effective mode is ``min(declared mode, mode_ceiling)``; the ceiling is
  installed at the run start (snapshot of the session mode) and narrowed at the
  scheduler's dispatch point, then inherited by every nested spawn because each
  asyncio task carries its own copy of the context. Reading it instead of a
  shared mutable field is what keeps concurrent siblings from overwriting each
  other's bound (issue #255).

The contextvar pattern mirrors ``agent/sandbox_events.py`` / ``agent/background.py``.
"""
from __future__ import annotations

from contextvars import ContextVar
from typing import TYPE_CHECKING, Any

from agent.run_config import AgentMode

if TYPE_CHECKING:
    from agent.subagent.bus import MessageBus

_spawn_depth: ContextVar[int] = ContextVar("subagent_spawn_depth", default=0)
_bus: ContextVar["MessageBus | None"] = ContextVar("subagent_bus", default=None)
_current_run_id: ContextVar[str | None] = ContextVar("subagent_current_run_id", default=None)
_workflow_id: ContextVar[str | None] = ContextVar("subagent_workflow_id", default=None)
_node_id: ContextVar[str | None] = ContextVar("subagent_node_id", default=None)
#: workflow 图距（0=leaf / 1=shard / 2=domain / 3+=root）。**独立于** ``spawn_depth``
#: ——调度器按执行计划给每个节点 set，绝不用它驱动 ``max_depth`` 深度闸（change
#: ``workflow-budget-attribution``，Q7/Q13：by_depth 的图距口径）。
_graph_distance: ContextVar[int | None] = ContextVar("subagent_graph_distance", default=None)
#: 当前执行单元的 mode 上限（change ``fix-issue-255-mode-ceiling``）。``None`` = 未 set，
#: 调用方 SHALL 回落一个**保守**的静态下界（会话初始 mode），**绝不**把它当成「不限」。
#: 该量是**执行作用域**量：并发兄弟各持一份 context 副本，互不覆盖。
_mode_ceiling: ContextVar[AgentMode | None] = ContextVar("subagent_mode_ceiling", default=None)


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


def current_run_id() -> str | None:
    return _current_run_id.get()


def set_current_run_id(run_id: str | None) -> Any:
    return _current_run_id.set(run_id)


def reset_current_run_id(token: Any) -> None:
    _current_run_id.reset(token)


def current_workflow_id() -> str | None:
    return _workflow_id.get()


def set_workflow_id(workflow_id: str | None) -> Any:
    return _workflow_id.set(workflow_id)


def reset_workflow_id(token: Any) -> None:
    _workflow_id.reset(token)


def current_node_id() -> str | None:
    return _node_id.get()


def set_node_id(node_id: str | None) -> Any:
    return _node_id.set(node_id)


def reset_node_id(token: Any) -> None:
    _node_id.reset(token)


def current_graph_distance() -> int | None:
    return _graph_distance.get()


def set_graph_distance(distance: int | None) -> Any:
    return _graph_distance.set(distance)


def reset_graph_distance(token: Any) -> None:
    _graph_distance.reset(token)


def current_mode_ceiling() -> AgentMode | None:
    """当前执行单元的 mode 上限，未设置时为 ``None``。

    ``None`` 表示「本执行单元没有声明上限」，调用方 SHALL 回落到一个保守的
    静态下界（``SubAgentManager.parent_mode``），SHALL NOT 把它当作「不限」——
    「读不到」不得退化成 fail-open（issue #255 / change 的 O3）。
    """
    return _mode_ceiling.get()


def set_mode_ceiling(mode: AgentMode | None) -> Any:
    return _mode_ceiling.set(mode)


def reset_mode_ceiling(token: Any) -> None:
    _mode_ceiling.reset(token)
