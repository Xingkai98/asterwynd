# agent/openai_llm.py
import json as _json
import logging
from typing import Optional, TYPE_CHECKING

from agent.llm import BaseLLM, LLMResponse, LLMStreamEvent, ToolCallDelta, Usage, supports_vision, vision_mode, _messages_have_images, _is_400_error, sanitize_payload_for_logging
from agent.message import Message, TextBlock, ImageBlock, ContentBlock, extract_text

if TYPE_CHECKING:
    pass

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
        mode = vision_mode(model)
        has_images = _messages_have_images(messages)
        try_vision = mode == "try_vision" and has_images
        force_vision = try_vision or mode == "vision"

        openai_messages = self._build_openai_messages(messages, model, force_vision=force_vision)
        payload: dict = {
            "model": model,
            "messages": openai_messages,
        }
        if tools:
            payload["tools"] = tools

        logger.debug(
            "LLM request:\n"
            "  model=%s  messages=%d  tools=%d\n"
            "  payload=%s",
            model, len(openai_messages), len(tools) if tools else 0,
            _json.dumps(sanitize_payload_for_logging(payload), ensure_ascii=False),
        )

        response = await client.post(
            f"{self.base_url}/chat/completions",
            json=payload,
        )

        if response.status_code == 400 and try_vision:
            logger.info(
                "First attempt with images failed (400) for model=%s, retrying without images",
                model,
            )
            openai_messages = self._build_openai_messages(messages, model, force_vision=False)
            payload["messages"] = openai_messages
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
                f"\nRequest payload: {_json.dumps(sanitize_payload_for_logging(payload), ensure_ascii=False)}"
                f"\nResponse body: {error_body}"
            )

        response.raise_for_status()
        data = response.json()

        usage_data = data.get("usage", {})
        usage = Usage(
            input_tokens=usage_data.get("prompt_tokens", 0),
            output_tokens=usage_data.get("completion_tokens", 0),
        ) if usage_data else None

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
                usage=usage,
            )

        return LLMResponse(
            content=message.get("content"),
            tool_calls=[],
            stop_reason=choice.get("finish_reason"),
            reasoning_content=reasoning_content,
            usage=usage,
        )

    async def stream_chat(
        self,
        messages: list[Message],
        tools: Optional[list[dict]] = None,
        model: Optional[str] = None,
    ):
        model = model or self.model
        mode = vision_mode(model)
        has_images = _messages_have_images(messages)
        try_vision = mode == "try_vision" and has_images
        force_vision = try_vision or mode == "vision"

        try:
            async for event in self._stream_chat_impl(messages, tools, model, force_vision):
                yield event
        except Exception as e:
            if not try_vision:
                raise
            if not _is_400_error(e):
                raise
            logger.info(
                "First stream attempt with images failed (400) for model=%s, retrying without images",
                model,
            )
            async for event in self._stream_chat_impl(messages, tools, model, force_vision=False):
                yield event

    async def _stream_chat_impl(
        self,
        messages: list[Message],
        tools: Optional[list[dict]] = None,
        model: Optional[str] = None,
        force_vision: bool = True,
    ):
        model = model or self.model
        openai_messages = self._build_openai_messages(messages, model, force_vision=force_vision)
        payload: dict = {
            "model": model,
            "messages": openai_messages,
            "stream": True,
        }
        if tools:
            payload["tools"] = tools

        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        tool_buffers: dict[int, dict[str, str]] = {}
        stop_reason = None
        usage = None

        async for _event_type, data in self._stream_events(
            f"{self.base_url}/chat/completions",
            payload,
        ):
            choices = data.get("choices") or []
            if not choices:
                # usage may arrive in a separate chunk without choices
                stream_usage = data.get("usage")
                if stream_usage:
                    usage = Usage(
                        input_tokens=stream_usage.get("prompt_tokens", 0),
                        output_tokens=stream_usage.get("completion_tokens", 0),
                    )
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
            usage=usage,
        )
        yield LLMStreamEvent(
            type="complete",
            response=response,
            content=response.content or "",
            stop_reason=response.stop_reason,
        )

    def _message_to_dict(self, msg: Message, is_vision: bool = True) -> dict:
        d: dict = {"role": msg.role, "content": self._content_to_openai(msg.content, msg.role, is_vision=is_vision)}
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

    def _build_openai_messages(
        self, messages: list[Message], model: str | None = None, force_vision: bool = True
    ) -> list[dict]:
        """构建 OpenAI 消息列表，处理 tool 消息中的图片注入"""
        resolved_model = model or self.model
        is_vision = force_vision
        image_buffer: list[ContentBlock] = []
        result: list[dict] = []

        for msg in messages:
            if msg.role == "tool" and isinstance(msg.content, list):
                text_blocks = [b for b in msg.content if isinstance(b, TextBlock)]
                image_blocks = [b for b in msg.content if isinstance(b, ImageBlock)]
                content = "\n".join(b.text for b in text_blocks) if text_blocks else ""
                if image_blocks:
                    if is_vision:
                        image_buffer.extend(image_blocks)
                    else:
                        # 非视觉模型：立即将图片降级为文本引用，附加到当前 tool 消息
                        refs = [self._degrade_image_to_text(b) for b in image_blocks if isinstance(b, ImageBlock)]
                        content = content + "\n" + "\n".join(refs)
                # tool 消息只保留文本
                result.append({
                    "role": "tool",
                    "content": content,
                    "tool_call_id": msg.tool_call_id,
                })
            else:
                # 遇到非 tool 消息时，flush image buffer（仅视觉模式有内容）
                if image_buffer:
                    result.append(self._image_buffer_to_user_message(image_buffer))
                    image_buffer = []
                result.append(self._message_to_dict(msg, is_vision=is_vision))

        # 末尾可能还有未 flush 的图片（视觉模式）
        if image_buffer:
            result.append(self._image_buffer_to_user_message(image_buffer))

        return result

    def _image_buffer_to_user_message(self, images: list[ContentBlock]) -> dict:
        """将收集的图片转为合成 user 消息"""

        content = [self._block_to_openai(b) for b in images]
        return {"role": "user", "content": content}

    def _content_to_openai(self, content: str | list[ContentBlock], role: str, is_vision: bool = True) -> str | list[dict]:
        """将 content 转换为 OpenAI API 格式"""
        if isinstance(content, str):
            return content
        # user 消息可以是 content array
        if role == "user":
            return [self._block_to_openai(b, is_vision=is_vision) for b in content]
        # 其他 role 只取文本
        return "\n".join(b.text for b in content if isinstance(b, TextBlock))

    def _block_to_openai(self, block: ContentBlock, is_vision: bool = True) -> dict:
        """单个 ContentBlock 转 OpenAI 格式。非视觉模型将 ImageBlock 降级为文本引用。"""
        if isinstance(block, TextBlock):
            return {"type": "text", "text": block.text}
        if isinstance(block, ImageBlock):
            if not is_vision:
                ref = block.file_path or "pasted image"
                return {"type": "text", "text": f"[image: {ref}]"}
            return {
                "type": "image_url",
                "image_url": {
                    "url": block.image_url.url,
                    "detail": block.image_url.detail or "auto",
                },
            }
        return {"type": "text", "text": ""}

    def _degrade_image_to_text(self, block: ImageBlock) -> str:
        """非视觉模型降级：ImageBlock → 文本引用"""
        ref = block.file_path or "pasted image"
        return f"[image: {ref}]"
