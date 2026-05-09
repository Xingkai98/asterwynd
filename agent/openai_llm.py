# agent/openai_llm.py
from typing import Optional

from agent.llm import BaseLLM, LLMResponse, ToolCallDelta
from agent.message import Message

class OpenAILLM(BaseLLM):
    """OpenAI Chat Completions API 实现"""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4",
    ):
        super().__init__(api_key=api_key, base_url=base_url, model=model)

    def _get_headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}"}

    async def chat(
        self,
        messages: list[Message],
        tools: Optional[list[dict]] = None,
        model: Optional[str] = None,
    ) -> LLMResponse:
        model = model or self.model
        client = await self._get_client()

        payload: dict = {
            "model": model,
            "messages": [self._message_to_dict(m) for m in messages],
        }
        if tools:
            payload["tools"] = tools

        response = await client.post(
            f"{self.base_url}/chat/completions",
            json=payload,
        )
        response.raise_for_status()
        data = await response.json()

        choice = data["choices"][0]
        message = choice["message"]

        if "tool_calls" in message and message["tool_calls"]:
            tool_calls = [
                ToolCallDelta(
                    id=tc["id"],
                    name=tc["function"]["name"],
                    arguments=tc["function"]["arguments"],
                )
                for tc in message["tool_calls"]
            ]
            return LLMResponse(
                content=message.get("content"),
                tool_calls=tool_calls,
                stop_reason=choice.get("finish_reason"),
            )

        return LLMResponse(
            content=message.get("content"),
            tool_calls=[],
            stop_reason=choice.get("finish_reason"),
        )

    def _message_to_dict(self, msg: Message) -> dict:
        d: dict = {"role": msg.role, "content": msg.content}
        if msg.tool_call_id:
            d["tool_call_id"] = msg.tool_call_id
        return d