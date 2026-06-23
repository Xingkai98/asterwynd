from __future__ import annotations

import httpx

from agent.tools.base import Tool, tool_parameters
from agent.tools.builtin.search_providers import (
    SearchProvider,
    SearchProviderError,
    SearchProviderExhaustedError,
    SearchProviderRegistry,
    SearchProviderResponse,
    SearchResult,
    build_search_provider_registry,
)


def _format_results(
    *,
    query: str,
    response: SearchProviderResponse,
) -> str:
    lines = [
        f"Search results for: {query}",
        f"Provider: {response.provider_name}",
        "",
    ]
    for index, result in enumerate(response.results, start=1):
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
    lines.extend(_format_diagnostics(response))
    return "\n".join(lines)


def _format_no_results(*, query: str, response: SearchProviderResponse) -> str:
    lines = [
        f"No search results for: {query}",
        f"Provider: {response.provider_name}",
    ]
    lines.extend(_format_diagnostics(response))
    return "\n".join(lines)


def _format_error(*, message: str, attempts: tuple = ()) -> str:
    lines = [f"WebSearch error: {message}"]
    if attempts:
        lines.append("")
        lines.append("Provider diagnostics:")
        for attempt in attempts:
            lines.append(
                f"- {attempt.provider_name}: {attempt.category}: {attempt.message}"
            )
    return "\n".join(lines)


def _format_diagnostics(response: SearchProviderResponse) -> list[str]:
    failures = [attempt for attempt in response.diagnostics if attempt.status != "success"]
    if not failures:
        return []
    lines = ["", "Provider diagnostics:"]
    for attempt in failures:
        lines.append(f"- {attempt.provider_name}: {attempt.category}: {attempt.message}")
    return lines


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
        registry: SearchProviderRegistry | None = None,
        provider_configs: tuple | list = (),
        transport: httpx.AsyncBaseTransport | httpx.BaseTransport | None = None,
        client: httpx.AsyncClient | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._registry = registry or (
            SearchProviderRegistry([provider])
            if provider
            else build_search_provider_registry(
                provider_configs,
                transport=transport,
                client=client,
                timeout=timeout,
            )
        )

    async def execute(self, query: str, limit: int = 5, **kwargs) -> str:
        normalized_query = query.strip()
        normalized_limit = max(1, int(limit))
        try:
            response = await self._registry.search(
                normalized_query,
                normalized_limit,
            )
        except SearchProviderExhaustedError as error:
            return _format_error(message=str(error), attempts=error.attempts)
        except SearchProviderError as error:
            return _format_error(
                message=str(error),
            )

        if response.results:
            return _format_results(
                query=normalized_query,
                response=response,
            )
        return _format_no_results(
            query=normalized_query,
            response=response,
        )
