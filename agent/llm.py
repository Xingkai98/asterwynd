# agent/llm.py
import asyncio
from dataclasses import dataclass, field
from typing import Literal, Protocol, Optional, runtime_checkable, TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from agent.message import Message


@dataclass
class ToolCallDelta:
    id: str
    name: str
    arguments: str  # JSON string


@runtime_checkable
class LLM(Protocol):
    """LLM provider 接口"""
    async def chat(
        self,
        messages: list["Message"],
        tools: Optional[list[dict]] = None,
        model: str = "gpt-4",
    ) -> "LLMResponse":
        ...


@dataclass
class Usage:
    """LLM API token 用量"""
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class LLMResponse:
    content: Optional[str]
    tool_calls: list[ToolCallDelta] = field(default_factory=list)
    stop_reason: Optional[str] = None
    reasoning_content: Optional[str] = None
    usage: Optional[Usage] = None


@dataclass
class LLMStreamEvent:
    type: Literal["assistant_delta", "complete"]
    delta: str = ""
    content: str = ""
    stop_reason: Optional[str] = None
    response: Optional[LLMResponse] = None


class BaseLLM:
    """LLM 基类：统一构造函数、客户端管理、资源释放

    子类可设置 stream=True 启用 SSE 流式（需 provider 支持）。
    不支持的 provider 保持 stream=False，用非流式 + 长 read timeout。
    """

    stream: bool = False

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        max_tokens: int = 16384,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.max_tokens = max_tokens
        self._client: Optional[httpx.AsyncClient] = None
        self._client_lock = asyncio.Lock()

    def _get_headers(self) -> dict:
        """子类实现：返回 HTTP headers（含认证）"""
        raise NotImplementedError

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        async with self._client_lock:
            if self._client is None:
                # 流式：chunk 间隔短，用默认 read timeout
                # 非流式：大响应可能超 60s，read timeout 拉到 180s
                read_timeout = 60.0 if self.stream else 180.0
                self._client = httpx.AsyncClient(
                    headers=self._get_headers(),
                    timeout=httpx.Timeout(60.0, read=read_timeout),
                )
            return self._client

    async def _stream_events(self, url: str, json: dict):
        """SSE 流式请求，yield (event_type, data_dict) tuples。"""
        client = await self._get_client()
        async with client.stream("POST", url, json=json) as response:
            response.raise_for_status()
            event_type = None
            async for line in response.aiter_lines():
                if line.startswith("event: "):
                    event_type = line[7:]
                elif line.startswith("data: "):
                    data_str = line[6:]
                    import json as _json
                    try:
                        data = _json.loads(data_str)
                    except _json.JSONDecodeError:
                        continue
                    yield event_type, data
                    event_type = None

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    async def chat(
        self,
        messages: list["Message"],
        tools: Optional[list[dict]] = None,
        model: Optional[str] = None,
    ) -> LLMResponse:
        raise NotImplementedError


# ── 视觉模型检测 ─────────────────────────────────────────────────────

VISION_MODEL_PREFIXES = (
    "gpt-4o",
    "gpt-4.1",
    "gpt-5",
    "claude-",
    "gemini-",
)


def supports_vision(model: str) -> bool:
    """检测模型是否支持视觉输入"""
    return model.startswith(VISION_MODEL_PREFIXES)


def vision_mode(model: str) -> str:
    """判断模型的视觉处理模式.

    Returns:
        "vision":     已知视觉模型，直接发送图片。
        "try_vision": 未知模型，先尝试发送图片，400 后降级重试。
    """
    return "vision" if supports_vision(model) else "try_vision"


def _messages_have_images(messages: list["Message"]) -> bool:
    """检查消息列表中是否包含 ImageBlock"""
    from agent.message import ImageBlock

    for msg in messages:
        if isinstance(msg.content, list):
            if any(isinstance(b, ImageBlock) for b in msg.content):
                return True
    return False


def _is_400_error(exc: Exception) -> bool:
    """判断异常是否为 httpx 400 错误"""
    try:
        import httpx
        if isinstance(exc, httpx.HTTPStatusError):
            return exc.response.status_code == 400
    except ImportError:
        pass
    return False


def sanitize_payload_for_logging(payload: dict) -> dict:
    """深拷贝 payload 并替换 data:image/ URL 为占位符，避免日志泄露 base64"""
    import copy
    sanitized = copy.deepcopy(payload)
    _sanitize_object(sanitized)
    return sanitized


def _sanitize_object(obj):
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in ("url", "data") and isinstance(value, str) and value.startswith("data:image/"):
                obj[key] = "[image data omitted]"
            else:
                _sanitize_object(value)
    elif isinstance(obj, list):
        for item in obj:
            _sanitize_object(item)
