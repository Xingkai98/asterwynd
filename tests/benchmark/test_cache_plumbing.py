"""Tests for the evaluation-metrics (C2) cache token collection chain.

Covers Usage fields (agent/llm.py), the loop accumulation of cache tokens into
RunResult, the AgentRunResult surface (benchmarks/models.py) and the runner's
pass-through into TaskResult. Backward compatible: defaults stay 0/None.
"""
from __future__ import annotations

import pytest

from agent.llm import LLMResponse, Usage
from agent.loop import AgentLoop
from agent.tools.registry import ToolRegistry
from agent.hooks.manager import HookManager
from agent.message import Message
from benchmarks.models import AgentRunResult, TaskResult


class _ScriptedLLM:
    """Minimal LLM stub returning one fixed response (chat, not streaming)."""

    def __init__(self, response: LLMResponse):
        self._response = response

    async def chat(self, messages, tools=None, model="gpt-4") -> LLMResponse:
        return self._response


def test_usage_has_cache_fields_default_zero() -> None:
    usage = Usage()
    assert usage.cache_read_input_tokens == 0
    assert usage.cache_creation_input_tokens == 0


def test_usage_cache_fields_settable() -> None:
    usage = Usage(
        input_tokens=100,
        output_tokens=50,
        cache_read_input_tokens=80,
        cache_creation_input_tokens=10,
    )
    assert usage.cache_read_input_tokens == 80
    assert usage.cache_creation_input_tokens == 10


@pytest.mark.asyncio
async def test_loop_accumulates_cache_tokens() -> None:
    response = LLMResponse(
        content="done",
        stop_reason="end_turn",
        usage=Usage(
            input_tokens=100,
            output_tokens=50,
            cache_read_input_tokens=80,
            cache_creation_input_tokens=10,
        ),
    )
    loop = AgentLoop(
        llm=_ScriptedLLM(response),
        tool_registry=ToolRegistry(),
        hooks=HookManager(),
    )
    result = await loop.run([Message(role="user", content="hi")])
    assert result.input_tokens == 100
    assert result.output_tokens == 50
    assert result.cache_read_input_tokens == 80
    assert result.cache_creation_input_tokens == 10


def test_agent_run_result_has_cache_fields_default_zero() -> None:
    ar = AgentRunResult()
    assert ar.cache_read_tokens == 0
    assert ar.cache_write_tokens == 0


def test_agent_run_result_cache_fields_settable() -> None:
    ar = AgentRunResult(
        status="completed",
        input_tokens=100,
        output_tokens=50,
        cache_read_tokens=80,
        cache_write_tokens=10,
    )
    assert ar.cache_read_tokens == 80
    assert ar.cache_write_tokens == 10


def test_task_result_accepts_cache_tokens() -> None:
    result = TaskResult(
        task_id="t1",
        agent="fake",
        status="passed",
        input_tokens=100,
        output_tokens=50,
        cache_read_tokens=80,
        cache_write_tokens=10,
    )
    assert result.cache_read_tokens == 80
    assert result.cache_write_tokens == 10
