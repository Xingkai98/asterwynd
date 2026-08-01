"""Tool governance — registry-level capability for managing many tools.

Contains the lifecycle state machine, semantic dedup, and Top-K selector.
Quality scoring (a later batch) will live here as ``quality.py``.
"""
from __future__ import annotations

from agent.tools.governance.dedup import SemanticDeduper
from agent.tools.governance.lifecycle import LifecycleState, ToolLifecycle
from agent.tools.governance.selector import ToolSelector

__all__ = [
    "LifecycleState",
    "ToolLifecycle",
    "SemanticDeduper",
    "ToolSelector",
]
