# web/debug_hook.py
"""Debug hook that captures iteration state and emits events for the debug UI."""
import os
import json
from agent.approval import redact_value
from agent.hooks.manager import Hook
from agent.message import Message
from agent.tools.base import ToolCall
from agent.llm import LLMResponse
from agent.result import RunResult


def debug_enabled() -> bool:
    return os.environ.get("ASTERWYND_DEBUG", "").lower() in ("1", "true", "enabled", "yes", "on")


class DebugHook:
    """Captures agent iteration state and emits structured debug events."""

    def __init__(self, emit=None, force_enabled: bool | None = None):
        self._emit = emit or (lambda event: None)
        self._enabled = force_enabled if force_enabled is not None else debug_enabled()
        self.iteration = 0

    def _send(self, phase: str, data: dict):
        if not self._enabled:
            return
        self._emit({"type": "debug", "phase": phase, "iteration": self.iteration, "data": data})

    async def before_iteration(self, iteration: int, messages: list[Message]) -> None:
        self.iteration = iteration
        self._send("before_iteration", {
            "messages": [m.to_dict() for m in messages],
            "message_count": len(messages),
        })

    async def after_llm_call(self, response: LLMResponse) -> None:
        self._send("after_llm_call", {
            "content": response.content,
            "stop_reason": response.stop_reason,
            "tool_calls": [
                {
                    "id": tc.id,
                    "name": tc.name,
                    "arguments": _redact_arguments(tc.arguments),
                }
                for tc in response.tool_calls
            ],
        })

    async def before_tool_execute(self, tool_call: ToolCall) -> None:
        self._send("before_tool_execute", {
            "tool_name": tool_call.name,
            "arguments": tool_call.arguments,
        })

    async def after_tool_execute(self, tool_call: ToolCall, result: str) -> None:
        self._send("after_tool_execute", {
            "tool_name": tool_call.name,
            "arguments": tool_call.arguments,
            "result": result,
        })

    async def on_error(self, error: Exception) -> None:
        self._send("on_error", {
            "error_type": type(error).__name__,
            "error_message": str(error),
        })

    async def on_completion(self, result: RunResult) -> None:
        self._send("on_completion", {
            "content": result.content,
            "stop_reason": result.stop_reason.value,
            "tool_calls_made": len(result.tool_calls_made),
            "total_tokens": result.total_tokens,
        })


def _redact_arguments(arguments: str):
    try:
        parsed = json.loads(arguments)
    except json.JSONDecodeError:
        return arguments
    return redact_value(parsed)
