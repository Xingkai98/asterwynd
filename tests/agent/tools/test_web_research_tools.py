import httpx
import pytest

from agent.tools.builtin.web_fetch import WebFetchTool
from agent.tools.builtin.web_search import WebSearchTool
from agent.tools.builtin.search_providers import SearchResult


def _transport(handler):
    return httpx.MockTransport(handler)


def test_web_research_tool_schemas_are_read_only():
    assert WebSearchTool().read_only is True
    assert WebFetchTool().read_only is True


@pytest.mark.asyncio
async def test_web_search_formats_injected_provider_results():
    class FakeSearchProvider:
        name = "fake-search"

        async def search(self, query: str, limit: int) -> list[SearchResult]:
            assert query == "agent runtime"
            assert limit == 1
            return [
                SearchResult(
                    title="Runtime",
                    url="https://example.com/runtime",
                    snippet="Agent runtime summary.",
                )
            ]

    tool = WebSearchTool(provider=FakeSearchProvider())

    result = await tool.execute(query="agent runtime", limit=1)

    assert result == (
        "Search results for: agent runtime\n"
        "Provider: fake-search\n\n"
        "Result 1:\n"
        "Title: Runtime\n"
        "URL: https://example.com/runtime\n"
        "Snippet: Agent runtime summary."
    )


@pytest.mark.asyncio
async def test_web_search_returns_structured_results():
    html = """
    <html><body>
      <div class="result">
        <a class="result__a" href="/l/?uddg=https%3A%2F%2Fexample.com%2Falpha">
          Alpha &amp; Beta
        </a>
        <a class="result__snippet">First <b>summary</b>.</a>
      </div>
      <div class="result">
        <a class="result__a" href="https://example.org/bravo">Bravo</a>
        <a class="result__snippet">Second summary.</a>
      </div>
    </body></html>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["q"] == "agent runtime"
        return httpx.Response(200, text=html, request=request)

    tool = WebSearchTool(transport=_transport(handler))

    result = await tool.execute(query="agent runtime", limit=2)

    assert "Search results for: agent runtime" in result
    assert "Provider: duckduckgo-html" in result
    assert "Result 1:" in result
    assert "Title: Alpha & Beta" in result
    assert "URL: https://example.com/alpha" in result
    assert "Snippet: First summary." in result
    assert "Result 2:" in result
    assert "Title: Bravo" in result
    assert "URL: https://example.org/bravo" in result


@pytest.mark.asyncio
async def test_web_search_respects_limit():
    html = """
    <a class="result__a" href="https://example.com/one">One</a>
    <a class="result__snippet">First</a>
    <a class="result__a" href="https://example.com/two">Two</a>
    <a class="result__snippet">Second</a>
    """

    tool = WebSearchTool(
        transport=_transport(
            lambda request: httpx.Response(200, text=html, request=request)
        )
    )

    result = await tool.execute(query="agent", limit=1)

    assert "Result 1:" in result
    assert "Result 2:" not in result


@pytest.mark.asyncio
async def test_web_search_reports_no_results():
    html = '<div class="no-results">No results found for agent</div>'
    tool = WebSearchTool(
        transport=_transport(
            lambda request: httpx.Response(200, text=html, request=request)
        )
    )

    result = await tool.execute(query="agent")

    assert result == "No search results for: agent\nProvider: duckduckgo-html"


@pytest.mark.asyncio
async def test_web_search_reports_parse_failure():
    html = "<html><body><main>unexpected provider shape</main></body></html>"
    tool = WebSearchTool(
        transport=_transport(
            lambda request: httpx.Response(200, text=html, request=request)
        )
    )

    result = await tool.execute(query="agent")

    assert result == (
        "WebSearch error: provider response could not be parsed\n"
        "Provider: duckduckgo-html"
    )


@pytest.mark.asyncio
async def test_web_search_reports_request_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    tool = WebSearchTool(transport=_transport(handler))

    result = await tool.execute(query="agent")

    assert result.startswith("WebSearch error: provider request failed: offline")
    assert "Provider: duckduckgo-html" in result


@pytest.mark.asyncio
async def test_web_fetch_returns_headers_and_text_content():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/plain; charset=utf-8"},
            text="hello world",
            request=request,
        )

    tool = WebFetchTool(transport=_transport(handler))

    result = await tool.execute("https://example.com/page")

    assert result == (
        "Fetched: https://example.com/page\n"
        "Final URL: https://example.com/page\n"
        "Status: 200\n"
        "Content-Type: text/plain; charset=utf-8\n\n"
        "hello world"
    )


@pytest.mark.asyncio
async def test_web_fetch_reports_truncation():
    tool = WebFetchTool(
        transport=_transport(
            lambda request: httpx.Response(
                200,
                headers={"content-type": "text/html"},
                text="abcdef",
                request=request,
            )
        )
    )

    result = await tool.execute("https://example.com/page", limit=3)

    assert "Truncated: yes, omitted 3 characters" in result
    assert result.endswith("\n\nabc")


@pytest.mark.asyncio
async def test_web_fetch_reports_final_url_after_redirect():
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == "https://example.com/start":
            return httpx.Response(
                302,
                headers={"location": "https://example.com/final"},
                request=request,
            )
        return httpx.Response(
            200,
            headers={"content-type": "text/plain"},
            text="done",
            request=request,
        )

    tool = WebFetchTool(transport=_transport(handler))

    result = await tool.execute("https://example.com/start")

    assert "Fetched: https://example.com/start" in result
    assert "Final URL: https://example.com/final" in result


@pytest.mark.asyncio
async def test_web_fetch_reports_http_error_without_body():
    tool = WebFetchTool(
        transport=_transport(
            lambda request: httpx.Response(
                404,
                headers={"content-type": "text/html"},
                text="<h1>not found</h1>",
                request=request,
            )
        )
    )

    result = await tool.execute("https://example.com/missing")

    assert result == (
        "WebFetch error: HTTP 404\n"
        "Fetched: https://example.com/missing\n"
        "Final URL: https://example.com/missing\n"
        "Content-Type: text/html"
    )
    assert "not found" not in result


@pytest.mark.asyncio
async def test_web_fetch_reports_unsupported_content_type():
    tool = WebFetchTool(
        transport=_transport(
            lambda request: httpx.Response(
                200,
                headers={"content-type": "application/pdf"},
                content=b"%PDF",
                request=request,
            )
        )
    )

    result = await tool.execute("https://example.com/file.pdf")

    assert result == (
        "WebFetch error: unsupported content type\n"
        "Fetched: https://example.com/file.pdf\n"
        "Final URL: https://example.com/file.pdf\n"
        "Status: 200\n"
        "Content-Type: application/pdf"
    )


@pytest.mark.asyncio
async def test_web_fetch_reports_request_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    tool = WebFetchTool(transport=_transport(handler))

    result = await tool.execute("https://example.com/page")

    assert result.startswith("WebFetch error: request failed: offline")
    assert "Fetched: https://example.com/page" in result
