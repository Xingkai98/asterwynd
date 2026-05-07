# tests/agent/test_result.py
import pytest
from agent.result import RunResult, StopReason, ToolCallMade

def test_run_result():
    result = RunResult(
        content="Hello world",
        stop_reason=StopReason.END_TURN,
        tool_calls_made=[],
        total_tokens=100,
    )
    assert result.content == "Hello world"
    assert result.stop_reason == StopReason.END_TURN

def test_stop_reason_values():
    assert StopReason.END_TURN.value == "end_turn"
    assert StopReason.MAX_ITERATIONS.value == "max_iterations"
    assert StopReason.ERROR.value == "error"

def test_tool_call_made():
    tcm = ToolCallMade(name="Read", arguments={"path": "a.txt"}, result="file content")
    assert tcm.name == "Read"
    assert tcm.result == "file content"
