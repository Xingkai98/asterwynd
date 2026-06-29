# agent/hooks/builtin/logging.py
import logging
from typing import TYPE_CHECKING
from agent.message import Message
from agent.tools.base import ToolCall

if TYPE_CHECKING:
    from agent.result import RunResult
    from agent.llm import LLMResponse
    from agent.run_config import AgentRunConfig

logger = logging.getLogger("asterwynd.hooks.logging")

class LoggingHook:
    def __init__(self, verbose: bool = False):
        self.verbose = verbose

    async def on_run_started(self, run_config: "AgentRunConfig") -> None:
        logger.info(f"[Run] mode={run_config.mode.value}")

    async def before_iteration(self, iteration: int, messages: list[Message]) -> None:
        logger.info(f"[Iteration {iteration}] messages={len(messages)}")

    async def after_llm_call(self, response: "LLMResponse") -> None:
        if self.verbose:
            logger.debug(f"LLM response: content={response.content!r}, tools={len(response.tool_calls)}")

    async def before_tool_execute(self, tool_call: ToolCall) -> None:
        logger.info(f"[Tool] executing {tool_call.name}({tool_call.arguments})")

    async def after_tool_execute(self, tool_call: ToolCall, result: str) -> None:
        preview = result[:200] + "..." if len(result) > 200 else result
        logger.info(f"[Tool] {tool_call.name} -> {preview!r}")

    async def on_error(self, error: Exception) -> None:
        logger.error(f"Error: {error}")

    async def on_completion(self, result: "RunResult") -> None:
        logger.info(f"[Done] reason={result.stop_reason}, tools={len(result.tool_calls_made)}")
