# agent/anthropic_llm.py
import asyncio
import json
import re
from typing import Optional

from agent.llm import BaseLLM, LLMResponse, ToolCallDelta
from agent.message import Message

# Python string 中不允许出现的 surrogate character (U+D800-U+DFFF)
SURROGATE_PATTERN = re.compile(r"[\ud800-\udfff]")


def _strip_surrogates(text: str) -> str:
    """移除字符串中的 surrogate character，避免 json.dumps() UTF-8 编码时崩溃"""
    return SURROGATE_PATTERN.sub("\ufffd", text)


class AnthropicLLM(BaseLLM):
    """Anthropic Messages API 实现"""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.anthropic.com",
        model: str = "claude-sonnet-4-20250514",
        max_tokens: int = 16384,
    ):
        super().__init__(api_key=api_key, base_url=base_url, model=model, max_tokens=max_tokens)

    def _get_headers(self) -> dict:
        return {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

    async def chat(
        self,
        messages: list[Message],
        tools: Optional[list[dict]] = None,
        model: Optional[str] = None,
    ) -> LLMResponse:
        model = model or self.model

        # 转换消息格式（流式/非流式共用）
        anthropic_messages = []
        system_content = []

        for msg in messages:
            if msg.role == "system":
                system_content.append({"type": "text", "text": _strip_surrogates(msg.content)})
            elif msg.role == "user":
                anthropic_messages.append({"role": "user", "content": _strip_surrogates(msg.content)})
            elif msg.role == "assistant":
                content_parts = []
                # text must come before tool_use blocks (required by DeepSeek Anthropic endpoint)
                if msg.content:
                    content_parts.append({"type": "text", "text": _strip_surrogates(msg.content)})
                for tc in msg.tool_calls:
                    input_dict = json.loads(tc.arguments) if isinstance(tc.arguments, str) else tc.arguments
                    content_parts.append({
                        "type": "tool_use",
                        "id": tc.id,
                        "name": tc.name,
                        "input": input_dict,
                    })
                anthropic_messages.append({"role": "assistant", "content": content_parts or [{"type": "text", "text": ""}]})
            elif msg.role == "tool":
                tool_result_block = {
                    "type": "tool_result",
                    "tool_use_id": msg.tool_call_id or "",
                    "content": _strip_surrogates(msg.content),
                }
                # Anthropic requires all tool_results for a single assistant turn
                # to be in one user message. Merge consecutive tool messages.
                if anthropic_messages and anthropic_messages[-1]["role"] == "user" and isinstance(anthropic_messages[-1].get("content"), list):
                    last_content = anthropic_messages[-1]["content"]
                    if last_content and last_content[0].get("type") == "tool_result":
                        last_content.append(tool_result_block)
                        continue
                anthropic_messages.append({
                    "role": "user",
                    "content": [tool_result_block],
                })

        payload: dict = {
            "model": model,
            "messages": anthropic_messages,
            "max_tokens": self.max_tokens,
        }
        if system_content:
            payload["system"] = system_content
        if tools:
            payload["tools"] = [self._convert_tool(tool) for tool in tools]

        if self.stream:
            return await self._chat_stream(payload)
        else:
            return await self._chat_nonstream(payload)

    async def _chat_stream(self, payload: dict) -> LLMResponse:
        """流式 SSE 解析"""
        payload["stream"] = True

        stop_reason_map = {
            "end_turn": "end_turn",
            "max_tokens": "max_tokens",
            "stop_sequence": "stop",
            "tool_use": "tool_calls",
        }

        blocks: dict = {}          # index -> {type, text_parts, json_parts, id, name}
        stop_reason = None

        async for event_type, data in self._stream_events(
            f"{self.base_url}/v1/messages",
            payload,
        ):
            if event_type == "content_block_start":
                block = data["content_block"]
                idx = data["index"]
                blocks[idx] = {
                    "type": block["type"],
                    "id": block.get("id"),
                    "name": block.get("name"),
                    "text_parts": [],
                    "json_parts": [],
                }

            elif event_type == "content_block_delta":
                idx = data["index"]
                delta = data["delta"]
                blk = blocks.get(idx)
                if blk is None:
                    continue
                if delta["type"] == "text_delta":
                    blk["text_parts"].append(delta["text"])
                elif delta["type"] == "input_json_delta":
                    blk["json_parts"].append(delta["partial_json"])

            elif event_type == "message_delta":
                raw_stop = data["delta"].get("stop_reason", "")
                stop_reason = stop_reason_map.get(raw_stop, raw_stop)

            elif event_type == "error":
                raise RuntimeError(f"Anthropic API error: {data}")

        return self._build_response(blocks, stop_reason)

    async def _chat_nonstream(self, payload: dict) -> LLMResponse:
        """非流式请求"""
        client = await self._get_client()
        response = await client.post(
            f"{self.base_url}/v1/messages",
            json=payload,
        )
        response.raise_for_status()
        raw = response.json()
        data = await raw if asyncio.iscoroutine(raw) else raw

        stop_reason_map = {
            "end_turn": "end_turn",
            "max_tokens": "max_tokens",
            "stop_sequence": "stop",
            "tool_use": "tool_calls",
        }
        api_stop_reason = stop_reason_map.get(data.get("stop_reason", ""), "end_turn")

        if data.get("content"):
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
                    content="\n".join(text_content) if text_content else None,
                    tool_calls=tool_calls,
                    stop_reason=api_stop_reason,
                )

            return LLMResponse(
                content="\n".join(text_content) if text_content else None,
                tool_calls=[],
                stop_reason=api_stop_reason,
            )

        return LLMResponse(
            content=None,
            tool_calls=[],
            stop_reason=api_stop_reason,
        )

    def _build_response(self, blocks: dict, stop_reason: str | None) -> LLMResponse:
        """将流式累积的 block 转换为 LLMResponse"""
        tool_calls = []
        text_content = []

        for blk in blocks.values():
            if blk["type"] == "text":
                text = _strip_surrogates("".join(blk["text_parts"]))
                if text:
                    text_content.append(text)
            elif blk["type"] == "tool_use":
                json_str = "".join(blk["json_parts"])
                args = json.loads(json_str) if json_str else {}
                tool_calls.append(ToolCallDelta(
                    id=blk["id"],
                    name=blk["name"],
                    arguments=json.dumps(args),
                ))

        if tool_calls:
            return LLMResponse(
                content="\n".join(text_content) if text_content else None,
                tool_calls=tool_calls,
                stop_reason=stop_reason or "tool_calls",
            )

        return LLMResponse(
            content="\n".join(text_content) if text_content else None,
            tool_calls=[],
            stop_reason=stop_reason or "end_turn",
        )

    def _convert_tool(self, tool: dict) -> dict:
        """将 OpenAI 格式工具转换为 Anthropic 格式"""
        func = tool.get("function", tool)
        return {
            "name": func["name"],
            "description": func.get("description", ""),
            "input_schema": func.get("parameters", {"type": "object", "properties": {}}),
        }
