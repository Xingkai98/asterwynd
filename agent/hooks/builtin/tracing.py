# agent/hooks/builtin/tracing.py
import time
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from agent.message import Message
from agent.tools.base import ToolCall

if TYPE_CHECKING:
    from agent.result import RunResult
    from agent.llm import LLMResponse

logger = logging.getLogger("myagent.hooks.tracing")

@dataclass
class ToolCallTrace:
    tool_name: str
    arguments: dict
    duration_ms: float = 0.0
    success: bool = True

class TracingHook:
    def __init__(self):
        self.calls: list[ToolCallTrace] = []
        self._start: float = 0

    async def before_tool_execute(self, tool_call: ToolCall) -> None:
        self._start = time.perf_counter()
        trace = ToolCallTrace(
            tool_name=tool_call.name,
            arguments=tool_call.arguments,
        )
        self.calls.append(trace)

    async def after_tool_execute(self, tool_call: ToolCall, result: str) -> None:
        duration_ms = (time.perf_counter() - self._start) * 1000
        success = not result.startswith("[Error")
        # Update the trace created in before_tool_execute
        if self.calls:
            self.calls[-1].duration_ms = round(duration_ms, 2)
            self.calls[-1].success = success
        logger.debug(f"[Trace] {tool_call.name} took {duration_ms:.2f}ms success={success}")

    def get_summary(self) -> dict:
        if not self.calls:
            return {}
        total = len(self.calls)
        successful = sum(1 for c in self.calls if c.success)
        avg_ms = sum(c.duration_ms for c in self.calls) / total
        return {
            "total_calls": total,
            "successful": successful,
            "failed": total - successful,
            "avg_duration_ms": round(avg_ms, 2),
        }

    async def before_iteration(self, iteration: int, messages: list[Message]) -> None: pass
    async def after_llm_call(self, response: "LLMResponse") -> None: pass
    async def on_error(self, error: Exception) -> None: pass
    async def on_completion(self, result: "RunResult") -> None: pass