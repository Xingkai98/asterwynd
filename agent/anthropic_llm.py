# agent/anthropic_llm.py
import asyncio
import json
import logging
import re
from contextvars import ContextVar
from typing import Optional, TYPE_CHECKING

from agent.llm import (
    BaseLLM, CachePlan, LLMResponse, LLMStreamEvent, ToolCallDelta, Usage,
    supports_vision, vision_mode, _messages_have_images, _is_400_error,
    sanitize_payload_for_logging,
)
from agent.message import Message, ReasoningBlock, TextBlock, ImageBlock

if TYPE_CHECKING:
    from agent.message import ContentBlock

logger = logging.getLogger("asterwynd.llm.anthropic")

# Anthropic beta 能力（issue #256）：
# - context-management-2025-06-27：clear_thinking_20251015 上下文编辑策略，
#   在 keep-all 模型上回收历史 thinking 占用的窗口（保留则缓存命中、清掉则失效）。
# - thinking-binding-controls-2026-08-01：thinking block 前缀绑定的控制，
#   配 block_binding.prefix_mismatch_behavior="drop_block" 避免 history 被改写后硬 400。
CONTEXT_MANAGEMENT_BETA = "context-management-2025-06-27"
THINKING_BINDING_BETA = "thinking-binding-controls-2026-08-01"

#: 命中 reasoning 相关 400 后的降级标志（issue #256 D7）。
#:
#: **作用域 = 一次 run 的上下文，不是 session 的持久状态**。理由：`ContextVar`
#: 按 asyncio task 隔离，而 web 下每个用户回合都是新 task
#: （`web/session.py` 的 `asyncio.create_task(run_agent())`），所以标志天然止于
#: 本回合。要让「本会话持续禁用」成立，**由 session 侧持有真值并在每次 run 开始时
#: 注入**（见 `set_reasoning_disabled` 与 `web/session.py` 的 run 入口）——
#: LLM 实例在 web 下是应用级单例（`web/server.py` 创建一个 llm 传给所有 session），
#: 所以真值绝不能放在 LLM 实例属性上（会跨会话泄漏）。
_reasoning_disabled: "ContextVar[bool]" = ContextVar("reasoning_disabled", default=False)


def set_reasoning_disabled(disabled: bool) -> None:
    """设置当前 run 上下文的 reasoning 降级标志（由 session 在 run 开始时注入）。"""
    _reasoning_disabled.set(disabled)


def is_reasoning_disabled() -> bool:
    """读取当前 run 上下文的 reasoning 降级标志（供 session 回写自己的状态）。"""
    return _reasoning_disabled.get()


# reasoning 相关 400 的错误文案族（issue #256 D7）。两类失败模式不同，需分别匹配：
# (a) 缺回传；(b) 签名/前缀失配。
REASONING_400_PATTERNS = (
    "thinking",          # "The content[].thinking ... must be passed back"
    "reasoning_content",  # OpenAI 兼容端点的同义文案
    "signature",         # "invalid signature in thinking block"
    "bound to a different conversation",
    "prefix mismatch",
)


def _is_reasoning_400(error_text: str) -> bool:
    """判断 400 文案是否指向 reasoning 回传问题（issue #256 D7）。"""
    lowered = (error_text or "").lower()
    return any(pat in lowered for pat in REASONING_400_PATTERNS)


def _http_error_text(exc: Exception) -> str:
    """取 HTTP 错误体文本。

    前提「错误体不被包装」已实测成立：httpx 0.28.1 下即使 streaming 上下文，
    ``HTTPStatusError.response.text`` 仍可读（issue #256 D7）。错误文案在
    ``error.message`` 里。取不到时返回空串（不抛）。
    """
    response = getattr(exc, "response", None)
    if response is None:
        return ""
    try:
        return response.text or ""
    except Exception:
        return ""


def _strip_reasoning_from_messages(messages: list["Message"]) -> list["Message"]:
    """返回去掉所有 reasoning 的消息副本（自愈降级用，不改原对象）。"""
    return [
        Message(
            role=m.role,
            content=m.content,
            tool_call_id=m.tool_call_id,
            reasoning=[],
            tool_calls=m.tool_calls,
        )
        for m in messages
    ]


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

    supports_cache_control = True  # 非 Anthropic 端点（DeepSeek-anthropic 等）可能拒绝 cache_control

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.anthropic.com",
        model: str = "claude-sonnet-4-20250514",
        max_tokens: int = 16384,
    ):
        super().__init__(api_key=api_key, base_url=base_url, model=model, max_tokens=max_tokens)
        self.cache_plan: CachePlan | None = None
        self._last_cache_plan: CachePlan | None = None
        # beta 能力开关（issue #256 D2/D7b）：
        # - context_management: clear_thinking_20251015（keep-all 模型上回收 thinking）
        # - thinking_binding: 前缀绑定的 drop_block 退路（compaction 改写历史后不硬崩）
        self.enable_context_management = False
        self.enable_thinking_binding_controls = False

    def _get_headers(self) -> dict:
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        betas: list[str] = []
        if self.enable_context_management:
            betas.append(CONTEXT_MANAGEMENT_BETA)
        if self.enable_thinking_binding_controls:
            betas.append(THINKING_BINDING_BETA)
        if betas:
            headers["anthropic-beta"] = ",".join(betas)
        return headers

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
            if not _is_400_error(e):
                raise
            logger = __import__("logging").getLogger("asterwynd.llm.anthropic")
            # reasoning 相关 400 的自愈（issue #256 D7）：本轮去掉 thinking 重试，
            # 并记 session 级降级标志（本轮降级 + 记状态，用户拍板 Q8）。
            if _is_reasoning_400(_http_error_text(e)):
                logger.warning(
                    "400 points at reasoning blocks — retrying without them "
                    "(session-level reasoning disabled from now on)"
                )
                _reasoning_disabled.set(True)
                payload = self._strip_cache_control(payload) if self._payload_has_cache_control(payload) else payload
                payload = self._build_payload(messages, tools, model, force_vision=force_vision)
                if self.stream:
                    return await self._chat_stream(payload)
                else:
                    return await self._chat_nonstream(payload)
            # Some Anthropic-compatible endpoints (e.g. DeepSeek-anthropic)
            # reject `cache_control`; retry once without it.
            if self._payload_has_cache_control(payload):
                logger.info("400 with cache_control — retrying without it")
                payload = self._strip_cache_control(payload)
                if self.stream:
                    return await self._chat_stream(payload)
                else:
                    return await self._chat_nonstream(payload)
            if not try_vision:
                raise
            logger.info(
                "First attempt with images failed (400) for model=%s, retrying without images",
                resolved_model,
            )
            payload = self._build_payload(messages, tools, model, force_vision=False)
            if self.stream:
                return await self._chat_stream(payload)
            else:
                return await self._chat_nonstream(payload)

    @staticmethod
    def _parse_replayed_arguments(tc: ToolCallDelta) -> dict:
        """解析历史消息里的 tool call 参数用于**重放**。

        与 ``_build_response`` 不同，这里只构造下一次请求体，该 tool call 的
        结果已在历史里、不会再被执行。非法 JSON（截断残留）降级为 ``{}``，
        避免重放时二次崩溃（issue #249 链路 B）。
        """
        if not isinstance(tc.arguments, str):
            return tc.arguments
        try:
            return json.loads(tc.arguments)
        except json.JSONDecodeError:
            logger.warning(
                "Replayed tool call %r has invalid JSON arguments (%d chars); "
                "degrading to empty object",
                tc.name, len(tc.arguments),
            )
            return {}

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
                # thinking block 必须在 text/tool_use 之前，且顺序与原始响应一致
                # （官方要求「连续的 thinking 块序列不可重排」，issue #256 D2）。
                # reasoning_disabled 为真时整段跳过（命中 400 后的 session 级降级，D7）。
                for rb in ([] if _reasoning_disabled.get() else msg.reasoning):
                    block: dict = {"type": "thinking", "thinking": rb.text}
                    if rb.opaque is not None:
                        # opaque 原样回传，不经任何清洗（issue #256 D1）。
                        block["signature"] = rb.opaque
                    content_parts.append(block)
                # text must come before tool_use blocks (required by DeepSeek Anthropic endpoint)
                if msg.content:
                    assistant_text = _strip_surrogates(msg.content) if isinstance(msg.content, str) else ""
                    if assistant_text:
                        content_parts.append({"type": "text", "text": assistant_text})
                for tc in msg.tool_calls:
                    input_dict = self._parse_replayed_arguments(tc)
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
        if self.enable_thinking_binding_controls:
            # 前缀绑定失配时丢弃该 block 而非硬 400（issue #256 D7b）：
            # compaction 改写历史后不会让整个 run 崩掉。
            payload["thinking"] = {
                "block_binding": {"prefix_mismatch_behavior": "drop_block"},
            }

        self._apply_cache_plan(payload)
        return payload

    # ------------------------------------------------------------------
    # Prompt caching (cache_control)
    # ------------------------------------------------------------------

    def _apply_cache_plan(self, payload: dict) -> None:
        """Attach ``cache_control`` breakpoints per the CachePlan set by the loop.

        The plan is consumed once per request: the loop sets ``self.cache_plan``
        before ``chat``/``stream_chat``; this method reads-and-clears it so a
        stale plan never leaks into summarizer or other direct chat calls.
        Per-mode strategy (design Decision 4 / grill Q3): selector OFF places a
        breakpoint on the last stable system block only; selector ON places one
        on the last core tool only.
        """
        plan = getattr(self, "cache_plan", None)
        self.cache_plan = None  # consume once
        self._last_cache_plan = plan  # keep for 400-retry detection
        if plan is None:
            return

        if plan.stable_system_block_count > 0:
            system = payload.get("system")
            if system:
                idx = min(plan.stable_system_block_count, len(system)) - 1
                if idx >= 0 and isinstance(system[idx], dict):
                    system[idx] = {**system[idx], "cache_control": {"type": "ephemeral"}}
        if plan.stable_tool_count > 0:
            tools = payload.get("tools")
            if tools:
                idx = min(plan.stable_tool_count, len(tools)) - 1
                if idx >= 0 and isinstance(tools[idx], dict):
                    tools[idx] = {**tools[idx], "cache_control": {"type": "ephemeral"}}

    @staticmethod
    def _payload_has_cache_control(payload: dict) -> bool:
        for block in payload.get("system") or []:
            if isinstance(block, dict) and "cache_control" in block:
                return True
        for tool in payload.get("tools") or []:
            if isinstance(tool, dict) and "cache_control" in tool:
                return True
        return False

    @staticmethod
    def _strip_cache_control(payload: dict) -> dict:
        """Return a deep copy of the payload without any cache_control keys."""
        stripped = json.loads(json.dumps(payload))
        for block in stripped.get("system") or []:
            if isinstance(block, dict):
                block.pop("cache_control", None)
        for tool in stripped.get("tools") or []:
            if isinstance(tool, dict):
                tool.pop("cache_control", None)
        return stripped

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
            if not _is_400_error(e):
                raise
            logger = __import__("logging").getLogger("asterwynd.llm.anthropic")
            # reasoning 相关 400 的自愈（issue #256 D7）：本轮去掉 thinking 重试，
            # 并记 session 级降级标志（本轮降级 + 记状态，用户拍板 Q8）。
            if _is_reasoning_400(_http_error_text(e)):
                logger.warning(
                    "Stream 400 points at reasoning blocks — retrying without them "
                    "(session-level reasoning disabled from now on)"
                )
                _reasoning_disabled.set(True)
                async for event in self._stream_chat_impl(
                    messages,
                    tools,
                    resolved_model,
                    force_vision=force_vision,
                ):
                    yield event
                return
            # Some Anthropic-compatible endpoints reject `cache_control`; retry once
            # without it (mirrors the non-streaming path in chat()).  The plan was
            # consumed by the first _stream_chat_impl's _build_payload, so the
            # retry below naturally produces a payload without cache_control.
            last_plan = getattr(self, "_last_cache_plan", None)
            had_cache = bool(
                last_plan
                and (last_plan.stable_system_block_count > 0 or last_plan.stable_tool_count > 0)
            )
            if had_cache:
                logger.info("Stream 400 with cache_control — retrying without it")
                async for event in self._stream_chat_impl(
                    messages,
                    tools,
                    resolved_model,
                    force_vision=force_vision,
                ):
                    yield event
                return
            if not try_vision:
                raise
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
        reasoning_text = ""
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
                    "signature": block.get("signature") or None,
                    "reasoning_parts": [],
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
                elif delta["type"] == "thinking_delta":
                    # 思维链增量走独立事件，绝不混入 assistant_delta（否则前端
                    # 会把它写进 markdown 正文，issue #256 D5）。
                    thinking_delta = _strip_surrogates(delta.get("thinking", ""))
                    blk["reasoning_parts"].append(thinking_delta)
                    reasoning_text += thinking_delta
                    if thinking_delta:
                        yield LLMStreamEvent(
                            type="reasoning_delta",
                            delta=thinking_delta,
                            content=reasoning_text,
                        )
                elif delta["type"] == "signature_delta":
                    # opaque 载荷：原样保存，**不经 _strip_surrogates**（清洗会
                    # 改写字节，破坏回传校验，issue #256 D1）。
                    blk["signature"] = delta.get("signature")
                elif delta["type"] == "input_json_delta":
                    blk["json_parts"].append(delta["partial_json"])

            elif event_type == "message_start":
                msg_usage = data.get("message", {}).get("usage", {})
                if msg_usage:
                    usage = Usage(
                        input_tokens=msg_usage.get("input_tokens", 0),
                        cache_read_input_tokens=msg_usage.get("cache_read_input_tokens", 0),
                        cache_creation_input_tokens=msg_usage.get("cache_creation_input_tokens", 0),
                    )

            elif event_type == "message_delta":
                raw_stop = data["delta"].get("stop_reason", "")
                stop_reason = self.STOP_REASON_MAP.get(raw_stop, raw_stop)
                stream_usage = data.get("usage", {})
                if stream_usage:
                    if usage is None:
                        usage = Usage()
                    usage.output_tokens = stream_usage.get("output_tokens", 0)

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
                    "signature": block.get("signature") or None,
                    "reasoning_parts": [],
                }

            elif event_type == "content_block_delta":
                idx = data["index"]
                delta = data["delta"]
                blk = blocks.get(idx)
                if blk is None:
                    continue
                if delta["type"] == "text_delta":
                    blk["text_parts"].append(delta["text"])
                elif delta["type"] == "thinking_delta":
                    blk["reasoning_parts"].append(delta.get("thinking", ""))
                elif delta["type"] == "signature_delta":
                    blk["signature"] = delta.get("signature")
                elif delta["type"] == "input_json_delta":
                    blk["json_parts"].append(delta["partial_json"])

            elif event_type == "message_start":
                msg_usage = data.get("message", {}).get("usage", {})
                if msg_usage:
                    usage = Usage(
                        input_tokens=msg_usage.get("input_tokens", 0),
                        cache_read_input_tokens=msg_usage.get("cache_read_input_tokens", 0),
                        cache_creation_input_tokens=msg_usage.get("cache_creation_input_tokens", 0),
                    )

            elif event_type == "message_delta":
                raw_stop = data["delta"].get("stop_reason", "")
                stop_reason = self.STOP_REASON_MAP.get(raw_stop, raw_stop)
                stream_usage = data.get("usage", {})
                if stream_usage:
                    if usage is None:
                        usage = Usage()
                    usage.output_tokens = stream_usage.get("output_tokens", 0)

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
            cache_read_input_tokens=usage_data.get("cache_read_input_tokens", 0),
            cache_creation_input_tokens=usage_data.get("cache_creation_input_tokens", 0),
        ) if usage_data else None

        api_stop_reason = self.STOP_REASON_MAP.get(data.get("stop_reason", ""), "end_turn")

        if data.get("content"):
            tool_calls = []
            text_content = []
            reasoning: list[ReasoningBlock] = []

            for block in data["content"]:
                if block["type"] == "tool_use":
                    tool_calls.append(ToolCallDelta(
                        id=block["id"],
                        name=block["name"],
                        arguments=json.dumps(block["input"]) if isinstance(block["input"], dict) else str(block["input"]),
                    ))
                elif block["type"] == "thinking":
                    # 文本走清洗、签名原样（issue #256 D1）。
                    reasoning.append(ReasoningBlock(
                        text=_strip_surrogates(block.get("thinking", "")),
                        opaque=block.get("signature"),
                    ))
                elif block["type"] == "text":
                    text_content.append(_strip_surrogates(block["text"]))

            if tool_calls:
                return LLMResponse(
                    content="\n".join(text_content) if text_content else None,
                    tool_calls=tool_calls,
                    stop_reason=api_stop_reason,
                    reasoning=reasoning,
                    usage=usage,
                )

            return LLMResponse(
                content="\n".join(text_content) if text_content else None,
                tool_calls=[],
                stop_reason=api_stop_reason,
                reasoning=reasoning,
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
        reasoning: list[ReasoningBlock] = []

        for blk in blocks.values():
            if blk["type"] == "text":
                text = _strip_surrogates("".join(blk["text_parts"]))
                if text:
                    text_content.append(text)
            elif blk["type"] == "thinking":
                # 一段 thinking = 可展示文本 + opaque 签名。文本走清洗，签名
                # **绝不**走清洗（改写字节会破坏回传校验，issue #256 D1）。
                block_text = _strip_surrogates("".join(blk.get("reasoning_parts", [])))
                signature = blk.get("signature")
                if block_text or signature:
                    reasoning.append(ReasoningBlock(text=block_text, opaque=signature))
            elif blk["type"] == "tool_use":
                json_str = "".join(blk["json_parts"])
                try:
                    args = json.loads(json_str) if json_str else {}
                except json.JSONDecodeError:
                    # 流式 tool call 的参数是分片拼接的，被 max_tokens 截断或
                    # 连接中断时会留下未闭合的 JSON（issue #249）。这里绝不把
                    # fragment 当结果：截断时丢弃该 call，让 stop_reason 保持
                    # max_tokens 交给 AgentLoop 的续接路径；其它情况保留原始串，
                    # 由 loop 的 _parse_arguments 降级为可恢复的 tool error。
                    if stop_reason == "max_tokens":
                        logger.warning(
                            "Dropping truncated tool call %r: arguments incomplete "
                            "under stop_reason=max_tokens (%d chars)",
                            blk.get("name"), len(json_str),
                        )
                        continue
                    logger.warning(
                        "Tool call %r has incomplete JSON arguments (%d chars); "
                        "passing raw string to the loop parser",
                        blk.get("name"), len(json_str),
                    )
                    tool_calls.append(ToolCallDelta(
                        id=blk["id"],
                        name=blk["name"],
                        arguments=json_str,
                    ))
                    continue
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
                reasoning=reasoning,
                usage=usage,
            )

        return LLMResponse(
            content="\n".join(text_content) if text_content else None,
            tool_calls=[],
            stop_reason=stop_reason or "end_turn",
            reasoning=reasoning,
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
