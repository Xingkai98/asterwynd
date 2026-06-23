import httpx
import pytest

from agent.config import SearchProviderConfig
from agent.tools.builtin.search_providers import (
    BraveSearchProvider,
    SearchProviderRegistry,
    SearchProviderRequestError,
    SearchProviderResponse,
    SearchResult,
    SearXNGSearchProvider,
    TavilySearchProvider,
    build_search_provider_registry,
)


def _transport(handler):
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_registry_falls_back_after_request_failure():
    class FailingProvider:
        name = "first"

        async def search(self, query: str, limit: int) -> SearchProviderResponse:
            raise SearchProviderRequestError("offline")

    class WorkingProvider:
        name = "second"

        async def search(self, query: str, limit: int) -> SearchProviderResponse:
            return SearchProviderResponse(
                provider_name=self.name,
                results=[SearchResult("Title", "https://example.com", "Snippet")],
            )

    registry = SearchProviderRegistry([FailingProvider(), WorkingProvider()])

    response = await registry.search("agent runtime", 1)

    assert response.provider_name == "second"
    assert [attempt.provider_name for attempt in response.diagnostics] == [
        "first",
        "second",
    ]
    assert response.diagnostics[0].category == "network_error"


@pytest.mark.asyncio
async def test_build_registry_preserves_configured_priority_and_disabled_providers():
    seen_urls = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        assert request.headers["X-Subscription-Token"] == "secret"
        return httpx.Response(
            200,
            json={
                "web": {
                    "results": [
                        {
                            "title": "Brave result",
                            "url": "https://example.com/brave",
                            "description": "From Brave.",
                        }
                    ]
                }
            },
            request=request,
        )

    registry = build_search_provider_registry(
        (
            SearchProviderConfig(name="searxng", enabled=False),
            SearchProviderConfig(name="brave", enabled=True),
            SearchProviderConfig(name="duckduckgo-html", enabled=True),
        ),
        environ={"MYAGENT_BRAVE_SEARCH_API_KEY": "secret"},
        transport=_transport(handler),
    )

    response = await registry.search("agent runtime", 1)

    assert response.provider_name == "brave"
    assert len(seen_urls) == 1
    assert "api.search.brave.com" in seen_urls[0]


@pytest.mark.asyncio
async def test_missing_api_key_falls_back_to_next_provider():
    html = """
    <a class="result__a" href="https://example.com/default">Default</a>
    <a class="result__snippet">Fallback result.</a>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html, request=request)

    registry = build_search_provider_registry(
        (
            SearchProviderConfig(name="tavily", enabled=True),
            SearchProviderConfig(name="duckduckgo-html", enabled=True),
        ),
        environ={},
        transport=_transport(handler),
    )

    response = await registry.search("agent runtime", 1)

    assert response.provider_name == "duckduckgo-html"
    assert response.diagnostics[0].provider_name == "tavily"
    assert response.diagnostics[0].category == "not_configured"
    assert "MYAGENT_TAVILY_API_KEY" in response.diagnostics[0].message


@pytest.mark.asyncio
async def test_missing_searxng_base_url_falls_back_to_next_provider():
    html = """
    <a class="result__a" href="https://example.com/default">Default</a>
    <a class="result__snippet">Fallback result.</a>
    """

    registry = build_search_provider_registry(
        (
            SearchProviderConfig(name="searxng", enabled=True),
            SearchProviderConfig(name="duckduckgo-html", enabled=True),
        ),
        environ={},
        transport=_transport(lambda request: httpx.Response(200, text=html, request=request)),
    )

    response = await registry.search("agent runtime", 1)

    assert response.provider_name == "duckduckgo-html"
    assert response.diagnostics[0].provider_name == "searxng"
    assert response.diagnostics[0].category == "not_configured"
    assert "MYAGENT_SEARXNG_BASE_URL" in response.diagnostics[0].message


@pytest.mark.asyncio
async def test_searxng_provider_parses_fixture_results():
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).startswith("https://search.example.test/search")
        assert request.url.params["q"] == "agent runtime"
        assert request.url.params["format"] == "json"
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "SearXNG result",
                        "url": "https://example.com/searxng",
                        "content": "Aggregated snippet.",
                        "engine": "duckduckgo",
                        "score": 1.0,
                    }
                ]
            },
            request=request,
        )

    provider = SearXNGSearchProvider(
        base_url="https://search.example.test",
        transport=_transport(handler),
    )

    response = await provider.search("agent runtime", 1)

    assert response.provider_name == "searxng"
    assert response.results == [
        SearchResult(
            title="SearXNG result",
            url="https://example.com/searxng",
            snippet="Aggregated snippet.",
            metadata={"engine": "duckduckgo", "score": 1.0},
        )
    ]


@pytest.mark.asyncio
async def test_brave_provider_parses_fixture_results():
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).startswith(
            "https://api.search.brave.com/res/v1/web/search"
        )
        assert request.url.params["q"] == "agent runtime"
        assert request.headers["X-Subscription-Token"] == "secret"
        return httpx.Response(
            200,
            headers={"X-RateLimit-Remaining": "9"},
            json={
                "web": {
                    "results": [
                        {
                            "title": "Brave result",
                            "url": "https://example.com/brave",
                            "description": "From Brave.",
                            "language": "en",
                        }
                    ]
                }
            },
            request=request,
        )

    provider = BraveSearchProvider(api_key="secret", transport=_transport(handler))

    response = await provider.search("agent runtime", 1)

    assert response.provider_name == "brave"
    assert response.results == [
        SearchResult(
            title="Brave result",
            url="https://example.com/brave",
            snippet="From Brave.",
            metadata={"age": None, "language": "en", "family_friendly": None},
        )
    ]
    assert response.metadata["rate_limit"]["X-RateLimit-Remaining"] == "9"


@pytest.mark.asyncio
async def test_tavily_provider_parses_fixture_results():
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://api.tavily.com/search"
        assert request.headers["Authorization"] == "Bearer secret"
        payload = request.read()
        assert b'"query":"agent runtime"' in payload
        assert b'"max_results":1' in payload
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "Tavily result",
                        "url": "https://example.com/tavily",
                        "content": "Search-optimized snippet.",
                        "score": 0.92,
                        "raw_content": "Long page text.",
                        "favicon": "https://example.com/favicon.ico",
                    }
                ],
                "response_time": 0.42,
                "request_id": "req-123",
                "usage": {"credits": 1},
            },
            request=request,
        )

    provider = TavilySearchProvider(api_key="secret", transport=_transport(handler))

    response = await provider.search("agent runtime", 1)

    assert response.provider_name == "tavily"
    assert response.results == [
        SearchResult(
            title="Tavily result",
            url="https://example.com/tavily",
            snippet="Search-optimized snippet.",
            metadata={
                "score": 0.92,
                "raw_content": "Long page text.",
                "favicon": "https://example.com/favicon.ico",
            },
        )
    ]
    assert response.metadata["response_time"] == 0.42
    assert response.metadata["request_id"] == "req-123"
    assert response.metadata["usage"] == {"credits": 1}
