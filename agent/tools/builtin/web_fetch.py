from __future__ import annotations

import httpx

from agent.tools.base import Tool, tool_parameters
from agent.tool_permissions import NETWORK_READ_PERMISSION


TEXT_CONTENT_TYPES = {
    "application/json",
    "application/javascript",
    "application/xml",
    "application/xhtml+xml",
}


def _content_type(response: httpx.Response) -> str:
    return response.headers.get("content-type", "unknown")


def _media_type(content_type: str) -> str:
    return content_type.split(";", 1)[0].strip().lower()


def _is_text_content(content_type: str) -> bool:
    media_type = _media_type(content_type)
    return media_type.startswith("text/") or media_type in TEXT_CONTENT_TYPES


def _format_header(
    *,
    fetched_url: str,
    final_url: str,
    status_code: int,
    content_type: str,
    omitted_characters: int = 0,
) -> str:
    lines = [
        f"Fetched: {fetched_url}",
        f"Final URL: {final_url}",
        f"Status: {status_code}",
        f"Content-Type: {content_type}",
    ]
    if omitted_characters > 0:
        lines.append(f"Truncated: yes, omitted {omitted_characters} characters")
    return "\n".join(lines)


def _format_http_error(
    *,
    status_code: int,
    fetched_url: str,
    final_url: str,
    content_type: str,
) -> str:
    return "\n".join(
        [
            f"WebFetch error: HTTP {status_code}",
            f"Fetched: {fetched_url}",
            f"Final URL: {final_url}",
            f"Content-Type: {content_type}",
        ]
    )


def _format_unsupported_content_type(
    *,
    fetched_url: str,
    final_url: str,
    status_code: int,
    content_type: str,
) -> str:
    return "\n".join(
        [
            "WebFetch error: unsupported content type",
            f"Fetched: {fetched_url}",
            f"Final URL: {final_url}",
            f"Status: {status_code}",
            f"Content-Type: {content_type}",
        ]
    )


@tool_parameters(
    name="WebFetch",
    description="获取网页内容",
    parameters={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "网页URL"},
            "limit": {"type": "integer", "description": "最多返回字符数", "default": 2000},
        },
        "required": ["url"],
    },
)
class WebFetchTool(Tool):
    read_only = True
    permission = NETWORK_READ_PERMISSION

    def __init__(
        self,
        *,
        transport: httpx.AsyncBaseTransport | httpx.BaseTransport | None = None,
        client: httpx.AsyncClient | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._transport = transport
        self._client = client
        self._timeout = timeout

    async def execute(self, url: str, limit: int = 2000, **kwargs) -> str:
        normalized_limit = max(0, int(limit))
        try:
            response = await self._get(url)
        except httpx.RequestError as error:
            return f"WebFetch error: request failed: {error}\nFetched: {url}"
        except Exception as error:
            return f"WebFetch error: request failed: {error}\nFetched: {url}"

        final_url = str(response.url)
        content_type = _content_type(response)

        if not 200 <= response.status_code < 300:
            return _format_http_error(
                status_code=response.status_code,
                fetched_url=url,
                final_url=final_url,
                content_type=content_type,
            )

        if not _is_text_content(content_type):
            return _format_unsupported_content_type(
                fetched_url=url,
                final_url=final_url,
                status_code=response.status_code,
                content_type=content_type,
            )

        full_text = response.text
        content = full_text[:normalized_limit]
        omitted_characters = max(0, len(full_text) - normalized_limit)
        header = _format_header(
            fetched_url=url,
            final_url=final_url,
            status_code=response.status_code,
            content_type=content_type,
            omitted_characters=omitted_characters,
        )
        return f"{header}\n\n{content}"

    async def _get(self, url: str) -> httpx.Response:
        if self._client:
            return await self._client.get(
                url,
                timeout=self._timeout,
                follow_redirects=True,
            )

        async with httpx.AsyncClient(
            transport=self._transport,
            follow_redirects=True,
        ) as client:
            return await client.get(url, timeout=self._timeout)
