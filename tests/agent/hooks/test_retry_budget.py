# tests/agent/hooks/test_retry_and_budget.py
import pytest
import asyncio
from agent.hooks.builtin.retry import RetryHook, _is_retryable
from agent.hooks.builtin.token_budget import TokenBudgetHook
from agent.message import Message
from agent.llm import LLMResponse
from agent.tools.base import ToolCall


class RetryableTool:
    name = "RetryableTool"
    call_count = 0

    async def execute(self, **kwargs) -> str:
        RetryableTool.call_count += 1
        if RetryableTool.call_count < 3:
            raise ConnectionError("connection timed out")
        return "success"


class NonRetryableTool:
    name = "NonRetryableTool"
    call_count = 0

    async def execute(self, **kwargs) -> str:
        NonRetryableTool.call_count += 1
        raise ValueError("invalid arguments")


@pytest.mark.asyncio
async def test_retry_hook_succeeds_after_retries():
    hook = RetryHook(max_retries=3, base_delay=0.01)
    RetryableTool.call_count = 0
    tool_call = ToolCall(id="c1", name="RetryableTool", arguments={})

    async def executor(tc):
        return await RetryableTool().execute(**tc.arguments)

    result = await hook.execute_with_retry(tool_call, executor)
    assert RetryableTool.call_count == 3
    assert result == "success"


@pytest.mark.asyncio
async def test_non_retryable_error_not_retried():
    hook = RetryHook(max_retries=3, base_delay=0.01)
    NonRetryableTool.call_count = 0
    tool_call = ToolCall(id="c2", name="NonRetryableTool", arguments={})

    async def executor(tc):
        return await NonRetryableTool().execute(**tc.arguments)

    result = await hook.execute_with_retry(tool_call, executor)
    assert NonRetryableTool.call_count == 1
    assert result.startswith("[Error")


@pytest.mark.asyncio
async def test_retry_exhausted_returns_error():
    hook = RetryHook(max_retries=2, base_delay=0.01)
    call_count = [0]

    class AlwaysTimeout:
        name = "AlwaysTimeout"
        async def execute(self, **kwargs):
            call_count[0] += 1
            raise TimeoutError("timeout")

    tool_call = ToolCall(id="c3", name="AlwaysTimeout", arguments={})

    async def executor(tc):
        return await AlwaysTimeout().execute(**tc.arguments)

    result = await hook.execute_with_retry(tool_call, executor)
    assert call_count[0] == 3  # 1 initial + 2 retries
    assert "Error after" in result


def test_is_retryable_patterns():
    assert _is_retryable("connection timed out")
    assert _is_retryable("Connection refused")
    assert _is_retryable("rate limit exceeded")
    assert _is_retryable("HTTP 429")
    assert _is_retryable("503 Service Unavailable")
    assert _is_retryable("temporary failure")
    assert not _is_retryable("permission denied")
    assert not _is_retryable("file not found")
    assert not _is_retryable("invalid arguments")
    assert not _is_retryable("no such file or directory")


def test_retry_hook_defaults():
    hook = RetryHook()
    assert hook.max_retries == 3
    assert hook.base_delay == 1.0


def test_token_budget_hook_init():
    hook = TokenBudgetHook(budget=100_000)
    assert hook.budget == 100_000
    assert hook.total_tokens == 0
