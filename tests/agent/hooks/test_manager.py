# tests/agent/hooks/test_manager.py
import pytest
import asyncio
from agent.hooks.manager import HookManager, Hook
from agent.message import Message
from agent.llm import LLMResponse
from agent.tools.base import ToolCall

class MockHook(Hook):
    def __init__(self):
        self.before_iteration_called = False
        self.after_tool_execute_called = False

    async def before_iteration(self, iteration: int, messages: list[Message]) -> None:
        self.before_iteration_called = True

    async def after_llm_call(self, response: LLMResponse) -> None:
        pass

    async def before_tool_execute(self, tool_call: ToolCall) -> None:
        pass

    async def after_tool_execute(self, tool_call: ToolCall, result: str) -> None:
        self.after_tool_execute_called = True

    async def on_error(self, error: Exception) -> None:
        pass

    async def on_completion(self, result: "RunResult") -> None:
        pass

@pytest.mark.asyncio
async def test_hook_manager_calls_all_hooks():
    hook1 = MockHook()
    hook2 = MockHook()
    manager = HookManager([hook1, hook2])
    messages = [Message(role="user", content="test")]

    await manager.before_iteration(0, messages)

    assert hook1.before_iteration_called is True
    assert hook2.before_iteration_called is True

@pytest.mark.asyncio
async def test_hook_manager_empty():
    manager = HookManager([])
    messages = [Message(role="user", content="test")]
    # Should not raise
    await manager.before_iteration(0, messages)