import pytest

from agent.tools.sandbox import SandboxExecutor, SandboxResult


@pytest.mark.asyncio
async def test_sandbox_run_simple_command():
    executor = SandboxExecutor()
    result = await executor.run("echo hello")
    assert isinstance(result, SandboxResult)
    assert result.exit_code == 0
    assert "hello" in result.stdout


@pytest.mark.asyncio
async def test_sandbox_run_with_timeout():
    executor = SandboxExecutor()
    result = await executor.run("sleep 0.1")
    assert isinstance(result, SandboxResult)
    assert result.exit_code == 0


@pytest.mark.asyncio
async def test_sandbox_run_timeout_flag():
    executor = SandboxExecutor()
    result = await executor.run("sleep 10", timeout=0.05)
    assert result.timed_out
    assert result.exit_code == -1


@pytest.mark.asyncio
async def test_sandbox_returns_error_on_failure():
    executor = SandboxExecutor()
    result = await executor.run("exit 1")
    assert isinstance(result, SandboxResult)
    assert result.exit_code == 1


def test_sandbox_str_backwards_compat():
    result = SandboxResult(exit_code=0, stdout="ok", stderr="", duration_ms=1.0, timed_out=False)
    assert str(result) == "ok"

    timeout_result = SandboxResult(exit_code=-1, stdout="", stderr="", duration_ms=5000, timed_out=True)
    assert "Timeout" in str(timeout_result)

    error_result = SandboxResult(exit_code=7, stdout="", stderr="fail", duration_ms=1.0, timed_out=False)
    assert "[Exit 7]" in str(error_result)
    assert "fail" in str(error_result)
