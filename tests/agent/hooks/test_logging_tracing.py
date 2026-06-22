# tests/agent/hooks/test_builtin.py
import logging

import pytest
from agent.run_config import AgentRunConfig, AgentMode
from agent.hooks.builtin.logging import LoggingHook
from agent.hooks.builtin.tracing import TracingHook
from agent.message import Message
from agent.tools.base import ToolCall


@pytest.mark.asyncio
async def test_logging_hook_no_crash():
    hook = LoggingHook(verbose=False)
    await hook.before_iteration(0, [Message(role="user", content="test")])


@pytest.mark.asyncio
async def test_logging_hook_records_run_mode(caplog):
    hook = LoggingHook(verbose=False)

    with caplog.at_level(logging.INFO, logger="myagent.hooks.logging"):
        await hook.on_run_started(AgentRunConfig(mode=AgentMode.READ_ONLY))

    assert "[Run] mode=read_only" in caplog.text


@pytest.mark.asyncio
async def test_tracing_hook_record():
    hook = TracingHook()
    await hook.before_tool_execute(ToolCall(id="c1", name="Read", arguments={"path": "a.txt"}))
    assert len(hook.calls) == 1
    assert hook.calls[0].tool_name == "Read"
