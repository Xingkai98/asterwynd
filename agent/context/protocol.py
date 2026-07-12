# agent/context/protocol.py
"""ContextBuilder protocol types."""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from agent.run_config import AgentMode


@dataclass
class BuildContext:
    """Environment-level info available to every ContextSource during render.

    Specific dependencies (persistent_memory, skill_runtime, etc.) should be
    injected via the source's constructor, not through BuildContext.
    """
    cwd: str
    mode: AgentMode
    context_window: int     # Model total context window size (e.g. 100_000)
    total_budget: int       # Injection-layer budget allocated to this source
    user_system_prompt: str = ""  # Optional user-provided --system append


@runtime_checkable
class ContextSource(Protocol):
    """A source of context content with a priority for ordering and a budget.

    Sources are registered statically at AgentLoop init time.  Each is rendered
    in priority order (0 = highest, 6 = lowest).  When the total injection-layer
    output exceeds the overall budget, layers are truncated from the lowest
    priority tail-first.
    """
    priority: int           # 0-6, 0 = highest (P0)
    name: str               # Human-readable name for debugging/logging
    budget: int             # Target token budget (advisory)
    critical: bool          # True = never truncate

    async def render(self, context: BuildContext) -> str:
        """Return this source's rendered content for the given build context.

        Return an empty string if the source has nothing to contribute.
        """
        ...
