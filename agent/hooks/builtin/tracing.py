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

logger = logging.getLogger("asterwynd.hooks.tracing")

@dataclass
class ToolCallTrace:
    tool_name: str
    arguments: dict
    duration_ms: float = 0.0
    success: bool = True

class TracingHook:
    def __init__(self):
        self.calls: list[ToolCallTrace] = []
        self._pending: dict[str, tuple[ToolCallTrace, float]] = {}

    async def before_tool_execute(self, tool_call: ToolCall) -> None:
        trace = ToolCallTrace(
            tool_name=tool_call.name,
            arguments=tool_call.arguments,
        )
        self.calls.append(trace)
        self._pending[tool_call.id] = (trace, time.perf_counter())

    async def after_tool_execute(self, tool_call: ToolCall, result: str) -> None:
        entry = self._pending.pop(tool_call.id, None)
        if entry is None:
            return
        trace, start = entry
        duration_ms = (time.perf_counter() - start) * 1000
        trace.duration_ms = round(duration_ms, 2)
        trace.success = not result.startswith("[Error")
        logger.debug(f"[Trace] {tool_call.name} took {duration_ms:.2f}ms success={trace.success}")

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