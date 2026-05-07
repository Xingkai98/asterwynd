# agent/anthropic_llm.py
import asyncio
import json
import re
from typing import Optional
import httpx

from agent.llm import LLM, LLMResponse, ToolCallDelta
from agent.message import Message

# Python string 中不允许出现的 surrogate character (U+D800-U+DFFF)
SURROGATE_PATTERN = re.compile(r"[\ud800-\udfff]")


def _strip_surrogates(text: str) -> str:
    """移除字符串中的 surrogate character，避免 json.dumps() UTF-8 编码时崩溃"""
    return SURROGATE_PATTERN.sub("\ufffd", text)


class AnthropicLLM:
    """Anthropic Messages API 实现"""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.anthropic.com",
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                timeout=60.0,
            )
        return self._client

    async def chat(
        self,
        messages: list[Message],
        tools: Optional[list[dict]] = None,
        model: str = "claude-sonnet-4-20250514",
    ) -> LLMResponse:
        client = await self._get_client()

        # 转换消息格式
        anthropic_messages = []
        system_content = []

        for msg in messages:
            if msg.role == "system":
                system_content.append({"type": "text", "text": _strip_surrogates(msg.content)})
            elif msg.role == "user":
                anthropic_messages.append({"role": "user", "content": _strip_surrogates(msg.content)})
            elif msg.role == "assistant":
                content_parts = []
                # 如果有 tool_calls，转换为 tool_use content block
                for tc in msg.tool_calls:
                    input_dict = json.loads(tc.arguments) if isinstance(tc.arguments, str) else tc.arguments
                    content_parts.append({
                        "type": "tool_use",
                        "id": tc.id,
                        "name": tc.name,
                        "input": input_dict,
                    })
                if msg.content:
                    content_parts.append({"type": "text", "text": _strip_surrogates(msg.content)})
                anthropic_messages.append({"role": "assistant", "content": content_parts or [{"type": "text", "text": ""}]})
            elif msg.role == "tool":
                anthropic_messages.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": msg.tool_call_id or "",
                            "content": _strip_surrogates(msg.content),
                        }
                    ],
                })

        payload: dict = {
            "model": model,
            "messages": anthropic_messages,
            "max_tokens": 4096,
        }
        if system_content:
            payload["system"] = system_content
        if tools:
            payload["tools"] = [self._convert_tool(tool) for tool in tools]

        response = await client.post(
            f"{self.base_url}/v1/messages",
            json=payload,
        )
        response.raise_for_status()
        # response.json() 在标准 httpx 中是 async coroutine，但某些代理（如 MiniMax）返回同步 dict
        raw = response.json()
        data = await raw if asyncio.iscoroutine(raw) else raw

        # Anthropic 的 stop_reason: end_turn, max_tokens, stop_sequence
        stop_reason_map = {
            "end_turn": "end_turn",
            "max_tokens": "max_tokens",
            "stop_sequence": "stop",
        }

        if data.get("content"):
            # 检查是否有 tool_use 类型的 content block
            tool_calls = []
            text_content = []

            for block in data["content"]:
                if block["type"] == "tool_use":
                    tool_calls.append(ToolCallDelta(
                        id=block["id"],
                        name=block["name"],
                        arguments=json.dumps(block["input"]) if isinstance(block["input"], dict) else str(block["input"]),
                    ))
                elif block["type"] == "text":
                    text_content.append(_strip_surrogates(block["text"]))

            if tool_calls:
                return LLMResponse(
                    content=None,
                    tool_calls=tool_calls,
                    stop_reason="tool_calls",
                )

            return LLMResponse(
                content="\n".join(text_content) if text_content else None,
                tool_calls=[],
                stop_reason=stop_reason_map.get(data.get("stop_reason", ""), "end_turn"),
            )

        return LLMResponse(
            content=None,
            tool_calls=[],
            stop_reason=stop_reason_map.get(data.get("stop_reason", ""), "end_turn"),
        )

    def _convert_tool(self, tool: dict) -> dict:
        """将 OpenAI 格式工具转换为 Anthropic 格式"""
        func = tool.get("function", tool)
        return {
            "name": func["name"],
            "description": func.get("description", ""),
            "input_schema": func.get("parameters", {"type": "object", "properties": {}}),
        }

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None
