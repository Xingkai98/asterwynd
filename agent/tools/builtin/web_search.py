from __future__ import annotations

import httpx

from agent.tools.base import Tool, tool_parameters
from agent.tools.builtin.search_providers import (
    DuckDuckGoHTMLSearchProvider,
    SearchProvider,
    SearchProviderError,
    SearchProviderHTTPError,
    SearchProviderParseError,
    SearchProviderRequestError,
    SearchResult,
)


def _format_results(
    *,
    provider_name: str,
    query: str,
    results: list[SearchResult],
) -> str:
    lines = [
        f"Search results for: {query}",
        f"Provider: {provider_name}",
        "",
    ]
    for index, result in enumerate(results, start=1):
        if index > 1:
            lines.append("")
        lines.extend(
            [
                f"Result {index}:",
                f"Title: {result.title}",
                f"URL: {result.url}",
                f"Snippet: {result.snippet}",
            ]
        )
    return "\n".join(lines)


def _format_no_results(*, provider_name: str, query: str) -> str:
    return f"No search results for: {query}\nProvider: {provider_name}"


def _format_error(*, provider_name: str, message: str) -> str:
    return f"WebSearch error: {message}\nProvider: {provider_name}"


@tool_parameters(
    name="WebSearch",
    description="搜索网页",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索关键词"},
            "limit": {"type": "integer", "description": "返回结果数量", "default": 5},
        },
        "required": ["query"],
    },
)
class WebSearchTool(Tool):
    read_only = True

    def __init__(
        self,
        *,
        provider: SearchProvider | None = None,
        transport: httpx.AsyncBaseTransport | httpx.BaseTransport | None = None,
        client: httpx.AsyncClient | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._provider = provider or DuckDuckGoHTMLSearchProvider(
            transport=transport,
            client=client,
            timeout=timeout,
        )

    async def execute(self, query: str, limit: int = 5, **kwargs) -> str:
        normalized_query = query.strip()
        normalized_limit = max(1, int(limit))
        try:
            results = await self._provider.search(
                normalized_query,
                normalized_limit,
            )
        except SearchProviderRequestError as error:
            return _format_error(
                provider_name=self._provider.name,
                message=f"provider request failed: {error}",
            )
        except SearchProviderHTTPError as error:
            return _format_error(
                provider_name=self._provider.name,
                message=str(error),
            )
        except SearchProviderParseError:
            return _format_error(
                provider_name=self._provider.name,
                message="provider response could not be parsed",
            )
        except SearchProviderError as error:
            return _format_error(
                provider_name=self._provider.name,
                message=str(error),
            )

        if results:
            return _format_results(
                provider_name=self._provider.name,
                query=normalized_query,
                results=results,
            )
        return _format_no_results(
            provider_name=self._provider.name,
            query=normalized_query,
        )
