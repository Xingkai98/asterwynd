# tests/agent/test_openai_llm.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from agent.openai_llm import OpenAILLM
from agent.message import Message

@pytest.mark.asyncio
async def test_openai_chat_success():
    llm = OpenAILLM(api_key="test-key", base_url="https://api.openai.com/v1")
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_response = MagicMock()
        mock_response.json = AsyncMock(return_value={
            "choices": [{"message": {"content": "Hello!"}, "finish_reason": "stop"}],
            "usage": {"total_tokens": 10},
        })
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response
        messages = [Message(role="user", content="Hi")]
        response = await llm.chat(messages, model="gpt-4")
        assert response.content == "Hello!"

@pytest.mark.asyncio
async def test_openai_tool_call():
    llm = OpenAILLM(api_key="test-key")
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_response = MagicMock()
        mock_response.json = AsyncMock(return_value={
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
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response
        messages = [Message(role="user", content="Run ls")]
        response = await llm.chat(messages, model="gpt-4")
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0].name == "Bash"