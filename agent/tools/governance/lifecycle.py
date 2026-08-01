"""Tool lifecycle state machine.

Four states: ``low_traffic`` → ``deprecation`` → ``grace`` → ``removed``.

Observable model: a new tool defaults to ``LOW_TRAFFIC``. ``mark_deprecated``
triggers deprecation and grace begins immediately (the tool stays visible during
grace with a deprecation notice — a soft prompt, not a hard removal). Once the
grace period elapses (via ``advance_time``), the tool transitions to
``REMOVED`` and is excluded from selection. ``mark_removed`` forces removal.

Explicitly driven, not dependent on quality score (which is a later batch).
"""
from __future__ import annotations

import time
from datetime import timedelta
from enum import Enum


class LifecycleState(str, Enum):
    LOW_TRAFFIC = "low_traffic"
    DEPRECATION = "deprecation"
    GRACE = "grace"
    REMOVED = "removed"


class ToolLifecycle:
    """Per-tool lifecycle tracking keyed by tool name."""

    def __init__(self, grace_period: timedelta = timedelta(days=7)) -> None:
        self._grace_period = grace_period
        # tool_name -> (state, grace_start_epoch_seconds or None)
        self._states: dict[str, tuple[LifecycleState, float | None]] = {}

    def mark_deprecated(self, tool_name: str) -> None:
        """Trigger deprecation; grace begins immediately.

        A tool with a zero grace period transitions straight to REMOVED.
        """
        if self._grace_period <= timedelta(0):
            self._states[tool_name] = (LifecycleState.REMOVED, None)
            return
        self._states[tool_name] = (LifecycleState.GRACE, time.time())

    def mark_removed(self, tool_name: str) -> None:
        """Force-remove a tool regardless of current state."""
        self._states[tool_name] = (LifecycleState.REMOVED, None)

    def advance_time(self, delta: timedelta) -> None:
        """Advance the clock by ``delta``, transitioning expired grace tools.

        Exposed for tests and for a periodic cleanup sweep: any tool in GRACE
        whose grace period has elapsed (relative to its recorded start) moves
        to REMOVED.
        """
        now = time.time()
        for tool_name, (state, grace_start) in list(self._states.items()):
            if state is not LifecycleState.GRACE or grace_start is None:
                continue
            if now + delta.total_seconds() - grace_start >= self._grace_period.total_seconds():
                self._states[tool_name] = (LifecycleState.REMOVED, None)

    def get_state(self, tool_name: str) -> LifecycleState:
        state, _ = self._states.get(tool_name, (LifecycleState.LOW_TRAFFIC, None))
        return state

    def is_visible(self, tool_name: str) -> bool:
        """Removed tools are hidden; grace tools remain visible (soft deprecation)."""
        return self.get_state(tool_name) is not LifecycleState.REMOVED

    def deprecation_notice(self, tool_name: str) -> str | None:
        """Return a deprecation notice for a tool in grace, else None."""
        if self.get_state(tool_name) is LifecycleState.GRACE:
            return f"deprecated: {tool_name} is in a {self._grace_period.days}-day grace period"
        return None
