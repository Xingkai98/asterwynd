# agent/llm.py
from dataclasses import dataclass, field
from typing import Protocol, Optional, runtime_checkable, TYPE_CHECKING

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
class LLMResponse:
    content: Optional[str]
    tool_calls: list[ToolCallDelta] = field(default_factory=list)
    stop_reason: Optional[str] = None


class BaseLLM:
    """LLM 基类：统一构造函数、客户端管理、资源释放"""
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

    def _get_headers(self) -> dict:
        """子类实现：返回 HTTP headers（含认证）"""
        raise NotImplementedError

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers=self._get_headers(),
                timeout=60.0,
            )
        return self._client

    async def _stream_events(self, url: str, json: dict):
        """SSE 流式请求，yield (event_type, data_dict) tuples。

        共享逻辑：所有 provider 的 SSE 格式相同（event:/data: 行）。
        子类的 chat() 调用此方法，各自解析特定 provider 的语义。
        """
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