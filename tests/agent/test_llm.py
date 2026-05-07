# tests/agent/test_llm.py
import pytest
from agent.llm import LLMResponse, ToolCallDelta
from agent.message import Message

def test_llm_response():
    response = LLMResponse(content="Hello!", tool_calls=[])
    assert response.content == "Hello!"

def test_llm_response_with_tool_calls():
    response = LLMResponse(
        content="",
        tool_calls=[
            ToolCallDelta(id="call_1", name="Bash", arguments='{"cmd": "ls"}')
        ],
    )
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].name == "Bash"

def test_llm_response_no_content():
    response = LLMResponse(content=None, tool_calls=[])
    assert response.content is None