from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

import httpx

from agent.tools.base import Tool, tool_parameters
from agent.tool_permissions import NETWORK_READ_PERMISSION


# SSRF 防护：禁止请求的 IP 范围和 hostname
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),       # loopback
    ipaddress.ip_network("10.0.0.0/8"),         # private A
    ipaddress.ip_network("172.16.0.0/12"),      # private B
    ipaddress.ip_network("192.168.0.0/16"),     # private C
    ipaddress.ip_network("169.254.0.0/16"),     # link-local / cloud metadata
    ipaddress.ip_network("0.0.0.0/8"),          # "this" network
    ipaddress.ip_network("::1/128"),            # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),           # IPv6 unique local
    ipaddress.ip_network("fe80::/10"),          # IPv6 link-local
]
_BLOCKED_HOSTS = {"localhost", "metadata.google.internal"}


def _validate_url_host(url: str) -> None:
    """校验 URL host，阻止 SSRF 攻击（私有 IP、localhost、云元数据端点）。"""
    parsed = urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        raise ValueError(f"无法解析 URL hostname: {url}")
    if hostname in _BLOCKED_HOSTS:
        raise ValueError(f"禁止访问内部地址: {hostname}")
    # 尝试解析为 IP 地址
    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        ip = None
    if ip is not None:
        # hostname 本身是 IP，直接校验
        for net in _BLOCKED_NETWORKS:
            if ip in net:
                raise ValueError(f"禁止访问内部地址: {hostname} ({net})")
        return  # 合法 IP，校验通过
    # hostname 是域名，DNS 解析后校验
    try:
        resolved = socket.getaddrinfo(hostname, None)
        for _, _, _, _, sockaddr in resolved:
            addr = sockaddr[0]
            try:
                resolved_ip = ipaddress.ip_address(addr)
                for net in _BLOCKED_NETWORKS:
                    if resolved_ip in net:
                        raise ValueError(f"禁止访问内部地址: {hostname} -> {addr} ({net})")
            except ValueError:
                pass  # 不是 IP，跳过
    except socket.gaierror:
        raise ValueError(f"无法解析域名: {hostname}")


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
            _validate_url_host(url)
        except ValueError as e:
            return f"WebFetch error: {e}"
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
