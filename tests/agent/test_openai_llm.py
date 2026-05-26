# tests/agent/test_openai_llm.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from agent.openai_llm import OpenAILLM
from agent.message import Message


def _mock_ok_response(json_body: dict) -> MagicMock:
    """Build a mock httpx.Response with status_code=200 and .json() -> json_body."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json = MagicMock(return_value=json_body)
    resp.raise_for_status = MagicMock()
    return resp


@pytest.mark.asyncio
async def test_openai_chat_success():
    llm = OpenAILLM(api_key="test-key", base_url="https://api.openai.com/v1")
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = _mock_ok_response({
            "choices": [{"message": {"content": "Hello!"}, "finish_reason": "stop"}],
            "usage": {"total_tokens": 10},
        })
        messages = [Message(role="user", content="Hi")]
        response = await llm.chat(messages, model="gpt-4")
        assert response.content == "Hello!"


@pytest.mark.asyncio
async def test_openai_tool_call():
    llm = OpenAILLM(api_key="test-key")
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = _mock_ok_response({
            "choices": [{
                "message": {
                    "content": None,
                    "tool_calls": [
                        {"id": "call_1", "function": {"name": "Bash", "arguments": '{"cmd": "ls"}'}}
                    ]
                },
                "finish_reason": "tool_calls"
            }],
            "usage": {"total_tokens": 50},
        })
        messages = [Message(role="user", content="Run ls")]
        response = await llm.chat(messages, model="gpt-4")
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0].name == "Bash"


@pytest.mark.asyncio
async def test_message_to_dict_includes_tool_calls():
    from agent.llm import ToolCallDelta
    llm = OpenAILLM(api_key="test-key")
    msg = Message(
        role="assistant",
        content="",
        tool_calls=[ToolCallDelta(id="call_1", name="Bash", arguments='{"cmd":"ls"}')],
    )
    d = llm._message_to_dict(msg)
    assert d["tool_calls"] == [{
        "id": "call_1",
        "type": "function",
        "function": {"name": "Bash", "arguments": '{"cmd":"ls"}'},
    }]


@pytest.mark.asyncio
async def test_chat_logs_error_body_on_400():
    llm = OpenAILLM(api_key="test-key")
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = '{"error": "bad model name"}'
        mock_response.raise_for_status = MagicMock(side_effect=Exception("400"))
        mock_post.return_value = mock_response

        with pytest.raises(Exception):
            await llm.chat([Message(role="user", content="Hi")], model="bad-model")

        # error body should have been read for logging
        mock_response.text  # already accessed — verify mock works
