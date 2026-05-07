# agent/hooks/builtin/retry.py
import asyncio
import logging
from typing import TYPE_CHECKING, Callable, Awaitable
from agent.tools.base import ToolCall

if TYPE_CHECKING:
    from agent.result import RunResult
    from agent.message import Message
    from agent.llm import LLMResponse

logger = logging.getLogger("myagent.hooks.retry")

class RetryHook:
    """工具执行失败时自动重试"""

    def __init__(self, max_retries: int = 2, base_delay: float = 0.5):
        self.max_retries = max_retries
        self.base_delay = base_delay

    async def execute_with_retry(
        self,
        tool_call: ToolCall,
        execute_fn: Callable[[ToolCall], Awaitable[str]],
    ) -> str:
        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                return await execute_fn(tool_call)
            except Exception as e:
                last_error = e
                if attempt < self.max_retries:
                    delay = self.base_delay * (2 ** attempt)
                    logger.warning(
                        f"[RetryHook] {tool_call.name} failed (attempt {attempt + 1}), "
                        f"retrying in {delay}s: {e}"
                    )
                    await asyncio.sleep(delay)

        return f"[Error after {self.max_retries + 1} attempts: {last_error}]"

    async def before_tool_execute(self, tool_call: ToolCall) -> None: pass
    async def after_tool_execute(self, tool_call: ToolCall, result: str) -> None: pass
    async def before_iteration(self, iteration: int, messages: list["Message"]) -> None: pass
    async def after_llm_call(self, response: "LLMResponse") -> None: pass
    async def on_error(self, error: Exception) -> None: pass
    async def on_completion(self, result: "RunResult") -> None: pass