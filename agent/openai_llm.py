# agent/openai_llm.py
import json as _json
import logging
from typing import Optional

from agent.llm import BaseLLM, LLMResponse, LLMStreamEvent, ToolCallDelta
from agent.message import Message

logger = logging.getLogger("asterwynd.llm.openai")


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

        logger.debug(
            "LLM request:\n"
            "  model=%s  messages=%d  tools=%d\n"
            "  payload=%s",
            model, len(messages), len(tools) if tools else 0,
            _json.dumps(payload, ensure_ascii=False),
        )

        response = await client.post(
            f"{self.base_url}/chat/completions",
            json=payload,
        )

        if response.status_code >= 400:
            error_body = ""
            try:
                error_body = response.text
            except Exception:
                pass
            logger.error(
                f"HTTP {response.status_code} from {self.base_url}"
                f"\nRequest payload: {_json.dumps(payload, ensure_ascii=False)}"
                f"\nResponse body: {error_body}"
            )

        response.raise_for_status()
        data = response.json()

        choice = data["choices"][0]
        message = choice["message"]

        logger.debug(
            "LLM response:\n"
            "  stop_reason=%s  content_len=%d  tool_calls=%d\n"
            "  raw=%s",
            choice.get("finish_reason"),
            len(message.get("content") or ""),
            len(message.get("tool_calls") or []),
            _json.dumps(data, ensure_ascii=False),
        )

        reasoning_content = message.get("reasoning_content")

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
                reasoning_content=reasoning_content,
            )

        return LLMResponse(
            content=message.get("content"),
            tool_calls=[],
            stop_reason=choice.get("finish_reason"),
            reasoning_content=reasoning_content,
        )

    async def stream_chat(
        self,
        messages: list[Message],
        tools: Optional[list[dict]] = None,
        model: Optional[str] = None,
    ):
        model = model or self.model
        payload: dict = {
            "model": model,
            "messages": [self._message_to_dict(m) for m in messages],
            "stream": True,
        }
        if tools:
            payload["tools"] = tools

        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        tool_buffers: dict[int, dict[str, str]] = {}
        stop_reason = None

        async for _event_type, data in self._stream_events(
            f"{self.base_url}/chat/completions",
            payload,
        ):
            choices = data.get("choices") or []
            if not choices:
                continue
            choice = choices[0]
            stop_reason = choice.get("finish_reason") or stop_reason
            delta = choice.get("delta") or {}

            if delta.get("reasoning_content"):
                reasoning_parts.append(delta["reasoning_content"])

            if delta.get("content"):
                text_delta = delta["content"]
                content_parts.append(text_delta)
                yield LLMStreamEvent(
                    type="assistant_delta",
                    delta=text_delta,
                    content="".join(content_parts),
                )

            for tool_delta in delta.get("tool_calls") or []:
                index = int(tool_delta.get("index", 0))
                current = tool_buffers.setdefault(index, {"id": "", "name": "", "arguments": ""})
                if tool_delta.get("id"):
                    current["id"] = tool_delta["id"]
                function = tool_delta.get("function") or {}
                if function.get("name"):
                    current["name"] = function["name"]
                if function.get("arguments"):
                    current["arguments"] += function["arguments"]

        tool_calls = [
            ToolCallDelta(
                id=tool["id"],
                name=tool["name"],
                arguments=tool["arguments"],
            )
            for _, tool in sorted(tool_buffers.items())
            if tool["id"] and tool["name"]
        ]
        response = LLMResponse(
            content="".join(content_parts) or None,
            tool_calls=tool_calls,
            stop_reason=stop_reason,
            reasoning_content="".join(reasoning_parts) or None,
        )
        yield LLMStreamEvent(
            type="complete",
            response=response,
            content=response.content or "",
            stop_reason=response.stop_reason,
        )

    def _message_to_dict(self, msg: Message) -> dict:
        d: dict = {"role": msg.role, "content": msg.content}
        if msg.tool_call_id:
            d["tool_call_id"] = msg.tool_call_id
        if msg.tool_calls:
            d["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": tc.arguments},
                }
                for tc in msg.tool_calls
            ]
        if msg.reasoning_content:
            d["reasoning_content"] = msg.reasoning_content
        return d
