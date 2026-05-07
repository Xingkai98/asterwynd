# agent/hooks/builtin/token_budget.py
import logging
from typing import TYPE_CHECKING
from agent.message import Message
from agent.tools.base import ToolCall

if TYPE_CHECKING:
    from agent.result import RunResult
    from agent.llm import LLMResponse

logger = logging.getLogger("myagent.hooks.token_budget")

class TokenBudgetHook:
    """监控 token 使用，超预算时记录警告"""

    def __init__(self, budget: int = 100_000, warn_threshold: float = 0.8):
        self.budget = budget
        self.warn_threshold = warn_threshold
        self.total_tokens = 0

    async def after_llm_call(self, response: "LLMResponse") -> None:
        pass

    async def after_tool_execute(self, tool_call: ToolCall, result: str) -> None:
        estimated = len(result) // 4
        self.total_tokens += estimated
        if self.total_tokens > self.budget * self.warn_threshold:
            logger.warning(
                f"[TokenBudget] 使用 {self.total_tokens}/{self.budget} "
                f"({self.total_tokens/self.budget*100:.1f}%)"
            )

    def get_usage(self) -> dict:
        return {
            "total_tokens": self.total_tokens,
            "budget": self.budget,
            "usage_ratio": self.total_tokens / self.budget if self.budget else 0,
        }

    async def before_iteration(self, iteration: int, messages: list[Message]) -> None: pass
    async def before_tool_execute(self, tool_call: ToolCall) -> None: pass
    async def on_error(self, error: Exception) -> None: pass
    async def on_completion(self, result: "RunResult") -> None: pass