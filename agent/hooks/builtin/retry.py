# agent/hooks/builtin/retry.py
from __future__ import annotations

import asyncio
import logging
import re
from typing import TYPE_CHECKING, Callable, Awaitable
from agent.tools.base import ToolCall, ToolResult

if TYPE_CHECKING:
    from agent.result import RunResult
    from agent.message import Message, ContentBlock
    from agent.llm import LLMResponse

logger = logging.getLogger("asterwynd.hooks.retry")

RETRYABLE_PATTERN = re.compile(
    r"timeout|timed out|connection|rate limit|429|503|temporary",
    re.IGNORECASE,
)


def _is_retryable(error_message: str) -> bool:
    return bool(RETRYABLE_PATTERN.search(error_message))


def _exception_error_type(exc: Exception) -> str | None:
    """Map a raised exception to a structured error_type.

    Retryable transport failures get explicit tags (timeout/network_error);
    everything else returns None so the loop's text-fallback classifies it.
    """
    if isinstance(exc, asyncio.TimeoutError):
        return "timeout"
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return "network_error"
    return None


class RetryHook:
    """工具执行失败时自动重试"""

    def __init__(self, max_retries: int = 3, base_delay: float = 1.0):
        self.max_retries = max_retries
        self.base_delay = base_delay

    async def execute_with_retry(
        self,
        tool_call: ToolCall,
        execute_fn: Callable[[ToolCall], Awaitable[str | list["ContentBlock"] | "ToolResult"]],
    ) -> str | list["ContentBlock"] | "ToolResult":
        last_error_msg = None
        last_error_type: str | None = None
        for attempt in range(self.max_retries + 1):
            try:
                return await execute_fn(tool_call)
            except Exception as e:
                last_error_msg = str(e)
                last_error_type = _exception_error_type(e)
                if not _is_retryable(last_error_msg):
                    return ToolResult(text=f"[Error: {last_error_msg}]", error_type=last_error_type)
                if attempt < self.max_retries:
                    delay = self.base_delay * (2 ** attempt)
                    logger.warning(
                        f"[RetryHook] {tool_call.name} failed (attempt {attempt + 1}), "
                        f"retrying in {delay}s: {last_error_msg}"
                    )
                    await asyncio.sleep(delay)

        return ToolResult(
            text=f"[Error after {self.max_retries + 1} attempts: {last_error_msg}]",
            error_type=last_error_type,
        )

    async def before_tool_execute(self, tool_call: ToolCall) -> None: pass
    async def after_tool_execute(
        self,
        tool_call: ToolCall,
        result: str | list["ContentBlock"],
        error_type: str | None = None,
    ) -> None: pass
    async def before_iteration(self, iteration: int, messages: list["Message"]) -> None: pass
    async def after_llm_call(self, response: "LLMResponse") -> None: pass
    async def on_error(self, error: Exception) -> None: pass
    async def on_completion(self, result: "RunResult") -> None: pass
