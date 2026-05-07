# tests/agent/tools/test_sandbox.py
import pytest
import asyncio
from agent.tools.sandbox import SandboxExecutor

@pytest.mark.asyncio
async def test_sandbox_run_simple_command():
    executor = SandboxExecutor()
    result = await executor.run("echo hello")
    assert "hello" in result

@pytest.mark.asyncio
async def test_sandbox_run_with_timeout():
    executor = SandboxExecutor()
    result = await executor.run("sleep 0.1")
    assert result == ""  # should complete without error

@pytest.mark.asyncio
async def test_sandbox_returns_error_on_failure():
    executor = SandboxExecutor()
    result = await executor.run("exit 1")
    # Should return error indicator, not raise
    assert result is not None