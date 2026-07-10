# agent/hooks/manager.py
from __future__ import annotations

from typing import Protocol, runtime_checkable, TYPE_CHECKING, Callable
from agent.message import Message
from agent.tools.base import ToolCall
from agent.llm import LLMResponse

if TYPE_CHECKING:
    from agent.result import RunResult
    from agent.run_config import AgentRunConfig
    from agent.message import ContentBlock

@runtime_checkable
class Hook(Protocol):
    async def on_run_started(self, run_config: "AgentRunConfig") -> None: ...
    async def before_iteration(self, iteration: int, messages: list[Message]) -> None: ...
    async def after_llm_call(self, response: LLMResponse) -> None: ...
    async def before_tool_execute(self, tool_call: ToolCall) -> None: ...
    async def after_tool_execute(self, tool_call: ToolCall, result: str | list["ContentBlock"]) -> None: ...
    async def on_error(self, error: Exception) -> None: ...
    async def on_completion(self, result: "RunResult") -> None: ...

class HookManager:
    def __init__(self, hooks: list[Hook] | None = None):
        self.hooks: list[Hook] = hooks or []

    async def on_run_started(self, run_config: "AgentRunConfig") -> None:
        for hook in self.hooks:
            handler = getattr(hook, "on_run_started", None)
            if handler:
                await handler(run_config)

    async def before_iteration(self, iteration: int, messages: list[Message]) -> None:
        for hook in self.hooks:
            await hook.before_iteration(iteration, messages)

    async def after_llm_call(self, response: LLMResponse) -> None:
        for hook in self.hooks:
            await hook.after_llm_call(response)

    async def before_tool_execute(self, tool_call: ToolCall) -> None:
        for hook in self.hooks:
            await hook.before_tool_execute(tool_call)

    async def after_tool_execute(self, tool_call: ToolCall, result: str | list["ContentBlock"]) -> None:
        for hook in self.hooks:
            await hook.after_tool_execute(tool_call, result)

    async def on_error(self, error: Exception) -> None:
        for hook in self.hooks:
            await hook.on_error(error)

    async def on_completion(self, result: "RunResult") -> None:
        for hook in self.hooks:
            await hook.on_completion(result)
