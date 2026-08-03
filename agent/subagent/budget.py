"""Per-run token budget enforcement for subagents (issue 79, decision D3).

The token budget is a *run* budget (not session/global): each subagent run can
carry its own ``max_tokens`` / ``max_time_s``, defaulting to ``subagents.budget``
from config. The two kill paths the design distinguishes:

- **token overrun** — detected inside the loop at the LLM-call boundary by
  ``BudgetHook.after_llm_call``, which raises ``BudgetExceededError``. The loop
  unwinds, ``_execute_run`` snapshots + marks ``budget_exceeded``, the task ends
  without an external cancel.
- **time overrun** — if a child is stuck inside a long tool call (e.g. a hung
  Bash), no hook fires; ``SubAgentManager`` runs a monitor task that cancels the
  run. The manager marks ``run._budget_kill_reason`` *before* cancelling so the
  cancelled-task handler records ``budget_exceeded`` instead of ``cancelled``.

Both paths snapshot first, so a budget kill is always resumable.
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING

from agent.hooks.manager import Hook
from agent.tools.base import ToolCall

if TYPE_CHECKING:
    from agent.llm import LLMResponse
    from agent.message import ContentBlock, Message
    from agent.result import RunResult
    from agent.run_config import AgentRunConfig


class BudgetExceededError(RuntimeError):
    """Raised inside the loop when a run crosses its token budget."""

    def __init__(self, dimension: str, used: int, limit: int):
        super().__init__(f"subagent budget exceeded ({dimension}): {used} > {limit}")
        self.dimension = dimension
        self.used = used
        self.limit = limit


class BudgetTracker:
    """Accumulates per-run token usage and answers budget checks."""

    def __init__(
        self,
        max_tokens: int | None = None,
        max_time_s: float | None = None,
        started_at: float | None = None,
    ) -> None:
        self.max_tokens = max_tokens
        self.max_time_s = max_time_s
        self.tokens = 0
        self.started_at = started_at if started_at is not None else time.time()

    def add(self, input_tokens: int, output_tokens: int) -> None:
        self.tokens += input_tokens + output_tokens

    def token_overrun(self) -> bool:
        return self.max_tokens is not None and self.tokens > self.max_tokens

    def time_overrun(self) -> bool:
        if self.max_time_s is None:
            return False
        return time.time() - self.started_at > self.max_time_s


class BudgetHook(Hook):
    """Loop hook that accumulates token usage and raises on overrun.

    Instantiated per run (in ``_execute_run``) so the tracker is not shared
    across runs. Must implement every ``Hook`` method because ``HookManager``
    dispatches by attribute access.
    """

    def __init__(self, tracker: BudgetTracker) -> None:
        self.tracker = tracker

    async def on_run_started(self, run_config: "AgentRunConfig") -> None:
        pass

    async def before_iteration(self, iteration: int, messages: list["Message"]) -> None:
        pass

    async def after_llm_call(self, response: "LLMResponse") -> None:
        if response.usage is not None:
            self.tracker.add(response.usage.input_tokens, response.usage.output_tokens)
            if self.tracker.token_overrun():
                raise BudgetExceededError(
                    "token",
                    used=self.tracker.tokens,
                    limit=self.tracker.max_tokens or 0,
                )

    async def before_tool_execute(self, tool_call: ToolCall) -> None:
        pass

    async def after_tool_execute(
        self, tool_call: ToolCall, result: str | list["ContentBlock"]
    ) -> None:
        pass

    async def on_error(self, error: Exception) -> None:
        pass

    async def on_completion(self, result: "RunResult") -> None:
        pass
