# agent/anthropic_llm.py
import asyncio
import json
import re
from typing import Optional, TYPE_CHECKING

from agent.llm import BaseLLM, LLMResponse, LLMStreamEvent, ToolCallDelta, Usage, supports_vision, vision_mode, _messages_have_images, _is_400_error, sanitize_payload_for_logging
from agent.message import Message, TextBlock, ImageBlock

if TYPE_CHECKING:
    from agent.message import ContentBlock

# Python string 中不允许出现的 surrogate character (U+D800-U+DFFF)
SURROGATE_PATTERN = re.compile(r"[\ud800-\udfff]")


def _strip_surrogates(text: str) -> str:
    """移除字符串中的 surrogate character，避免 json.dumps() UTF-8 编码时崩溃"""
    return SURROGATE_PATTERN.sub("\ufffd", text)


class AnthropicLLM(BaseLLM):
    """Anthropic Messages API 实现"""

    STOP_REASON_MAP: dict[str, str] = {
        "end_turn": "end_turn",
        "max_tokens": "max_tokens",
        "stop_sequence": "stop",
        "tool_use": "tool_calls",
    }

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
        resolved_model = model or self.model
        mode = vision_mode(resolved_model)
        has_images = _messages_have_images(messages)
        try_vision = mode == "try_vision" and has_images
        force_vision = try_vision or mode == "vision"

        payload = self._build_payload(messages, tools, model, force_vision=force_vision)
        try:
            if self.stream:
                return await self._chat_stream(payload)
            else:
                return await self._chat_nonstream(payload)
        except Exception as e:
            if not try_vision:
                raise
            if not _is_400_error(e):
                raise
            logger = __import__("logging").getLogger("asterwynd.llm.anthropic")
            logger.info(
                "First attempt with images failed (400) for model=%s, retrying without images",
                resolved_model,
            )
            payload = self._build_payload(messages, tools, model, force_vision=False)
            if self.stream:
                return await self._chat_stream(payload)
            else:
                return await self._chat_nonstream(payload)

    def _build_payload(
        self,
        messages: list[Message],
        tools: Optional[list[dict]] = None,
        model: Optional[str] = None,
        force_vision: bool = True,
    ) -> dict:
        # 转换消息格式（流式/非流式共用）
        anthropic_messages = []
        system_content = []

        resolved_model = model or self.model
        for msg in messages:
            if msg.role == "system":
                system_content.extend(self._system_content_to_anthropic(msg.content))
            elif msg.role == "user":
                anthropic_messages.append({"role": "user", "content": self._content_to_anthropic(msg.content, resolved_model, force_vision=force_vision)})
            elif msg.role == "assistant":
                content_parts = []
                # text must come before tool_use blocks (required by DeepSeek Anthropic endpoint)
                if msg.content:
                    assistant_text = _strip_surrogates(msg.content) if isinstance(msg.content, str) else ""
                    if assistant_text:
                        content_parts.append({"type": "text", "text": assistant_text})
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
                    "content": self._content_to_anthropic(msg.content, resolved_model, force_vision=force_vision),
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
            "model": resolved_model,
            "messages": anthropic_messages,
            "max_tokens": self.max_tokens,
        }
        if system_content:
            payload["system"] = system_content
        if tools:
            payload["tools"] = [self._convert_tool(tool) for tool in tools]

        return payload

    async def stream_chat(
        self,
        messages: list[Message],
        tools: Optional[list[dict]] = None,
        model: Optional[str] = None,
    ):
        """流式输出 assistant text delta，并在末尾返回完整响应。"""
        resolved_model = model or self.model
        mode = vision_mode(resolved_model)
        has_images = _messages_have_images(messages)
        try_vision = mode == "try_vision" and has_images
        force_vision = try_vision or mode == "vision"

        try:
            async for event in self._stream_chat_impl(
                messages,
                tools,
                resolved_model,
                force_vision=force_vision,
            ):
                yield event
        except Exception as e:
            if not try_vision:
                raise
            if not _is_400_error(e):
                raise
            logger = __import__("logging").getLogger("asterwynd.llm.anthropic")
            logger.info(
                "First stream attempt with images failed (400) for model=%s, retrying without images",
                resolved_model,
            )
            async for event in self._stream_chat_impl(
                messages,
                tools,
                resolved_model,
                force_vision=False,
            ):
                yield event

    async def _stream_chat_impl(
        self,
        messages: list[Message],
        tools: Optional[list[dict]] = None,
        model: Optional[str] = None,
        force_vision: bool = True,
    ):
        payload = self._build_payload(messages, tools, model, force_vision=force_vision)
        payload["stream"] = True

        blocks: dict = {}
        stop_reason = None
        text_content = ""
        usage = None

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
                    text_delta = _strip_surrogates(delta["text"])
                    blk["text_parts"].append(text_delta)
                    text_content += text_delta
                    if text_delta:
                        yield LLMStreamEvent(
                            type="assistant_delta",
                            delta=text_delta,
                            content=text_content,
                        )
                elif delta["type"] == "input_json_delta":
                    blk["json_parts"].append(delta["partial_json"])

            elif event_type == "message_delta":
                raw_stop = data["delta"].get("stop_reason", "")
                stop_reason = self.STOP_REASON_MAP.get(raw_stop, raw_stop)
                stream_usage = data.get("usage", {})
                if stream_usage:
                    usage = Usage(output_tokens=stream_usage.get("output_tokens", 0))

            elif event_type == "error":
                raise RuntimeError(f"Anthropic API error: {data}")

        response = self._build_response(blocks, stop_reason, usage=usage)
        yield LLMStreamEvent(
            type="complete",
            response=response,
            content=response.content or "",
            stop_reason=response.stop_reason,
        )

    async def _chat_stream(self, payload: dict) -> LLMResponse:
        """流式 SSE 解析"""
        payload["stream"] = True

        blocks: dict = {}          # index -> {type, text_parts, json_parts, id, name}
        stop_reason = None
        usage = None

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
                stop_reason = self.STOP_REASON_MAP.get(raw_stop, raw_stop)
                stream_usage = data.get("usage", {})
                if stream_usage:
                    usage = Usage(output_tokens=stream_usage.get("output_tokens", 0))

            elif event_type == "error":
                raise RuntimeError(f"Anthropic API error: {data}")

        return self._build_response(blocks, stop_reason, usage=usage)

    async def _chat_nonstream(self, payload: dict) -> LLMResponse:
        """非流式请求"""
        client = await self._get_client()
        response = await client.post(
            f"{self.base_url}/v1/messages",
            json=payload,
        )
        status = response.status_code
        if isinstance(status, int) and status >= 400:
            error_body = ""
            try:
                error_body = response.text
            except Exception:
                pass
            import logging as _logging
            _logger = _logging.getLogger("asterwynd.llm.anthropic")
            _logger.error(
                "HTTP %s from %s\nResponse body: %s\nSanitized payload: %s",
                status,
                f"{self.base_url}/v1/messages",
                error_body,
                json.dumps(sanitize_payload_for_logging(payload), ensure_ascii=False),
            )
        response.raise_for_status()
        raw = response.json()
        data = await raw if asyncio.iscoroutine(raw) else raw

        usage_data = data.get("usage", {})
        usage = Usage(
            input_tokens=usage_data.get("input_tokens", 0),
            output_tokens=usage_data.get("output_tokens", 0),
        ) if usage_data else None

        api_stop_reason = self.STOP_REASON_MAP.get(data.get("stop_reason", ""), "end_turn")

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
                    usage=usage,
                )

            return LLMResponse(
                content="\n".join(text_content) if text_content else None,
                tool_calls=[],
                stop_reason=api_stop_reason,
                usage=usage,
            )

        return LLMResponse(
            content=None,
            tool_calls=[],
            stop_reason=api_stop_reason,
            usage=usage,
        )

    def _build_response(self, blocks: dict, stop_reason: str | None, usage: Usage | None = None) -> LLMResponse:
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
                usage=usage,
            )

        return LLMResponse(
            content="\n".join(text_content) if text_content else None,
            tool_calls=[],
            stop_reason=stop_reason or "end_turn",
            usage=usage,
        )

    def _convert_tool(self, tool: dict) -> dict:
        """将 OpenAI 格式工具转换为 Anthropic 格式"""
        func = tool.get("function", tool)
        return {
            "name": func["name"],
            "description": func.get("description", ""),
            "input_schema": func.get("parameters", {"type": "object", "properties": {}}),
        }

    def _content_to_anthropic(self, content: str | list["ContentBlock"], model: str = "", force_vision: bool = True):
        """将 Message.content 转换为 Anthropic API 格式"""
        if isinstance(content, str):
            return _strip_surrogates(content)
        is_vision = force_vision
        result = []
        for block in content:
            if isinstance(block, TextBlock):
                result.append({"type": "text", "text": _strip_surrogates(block.text)})
            elif isinstance(block, ImageBlock):
                if is_vision:
                    result.append(self._image_to_anthropic(block))
                else:
                    ref = block.file_path or "pasted image"
                    result.append({"type": "text", "text": f"[image: {ref}]"})
        return result

    def _system_content_to_anthropic(self, content: str | list["ContentBlock"]) -> list[dict]:
        """将 system content 转换为 Anthropic 格式（始终返回列表）"""
        if isinstance(content, str):
            return [{"type": "text", "text": _strip_surrogates(content)}]
        result = []
        for block in content:
            if isinstance(block, TextBlock):
                result.append({"type": "text", "text": _strip_surrogates(block.text)})
        return result or [{"type": "text", "text": ""}]

    def _image_to_anthropic(self, block: ImageBlock) -> dict:
        """将 ImageBlock 转换为 Anthropic image source 格式"""
        data_url = block.image_url.url
        # data:image/png;base64,ABC...
        if data_url.startswith("data:"):
            header, b64 = data_url.split(",", 1)
            mime = header.split(":")[1].split(";")[0] if ":" in header else "image/png"
        else:
            mime = "image/png"
            b64 = data_url
        return {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": mime,
                "data": b64,
            },
        }
