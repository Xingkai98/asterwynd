from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Protocol
from urllib.parse import parse_qs, unquote, urlparse

import httpx


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str


class SearchProvider(Protocol):
    name: str

    async def search(self, query: str, limit: int) -> list[SearchResult]:
        ...


class SearchProviderError(Exception):
    pass


class SearchProviderRequestError(SearchProviderError):
    pass


class SearchProviderParseError(SearchProviderError):
    pass


class SearchProviderHTTPError(SearchProviderError):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"provider returned HTTP {status_code}")
        self.status_code = status_code


class DuckDuckGoHTMLSearchProvider:
    name = "duckduckgo-html"
    search_url = "https://html.duckduckgo.com/html/"

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

    async def search(self, query: str, limit: int) -> list[SearchResult]:
        try:
            response = await self._get(query)
        except httpx.RequestError as error:
            raise SearchProviderRequestError(str(error)) from error
        except Exception as error:
            raise SearchProviderRequestError(str(error)) from error

        if not 200 <= response.status_code < 300:
            raise SearchProviderHTTPError(response.status_code)

        results, parsed_provider_shape = _parse_duckduckgo_results(
            response.text,
            limit,
        )
        if results or parsed_provider_shape:
            return results
        raise SearchProviderParseError("provider response could not be parsed")

    async def _get(self, query: str) -> httpx.Response:
        if self._client:
            return await self._client.get(
                self.search_url,
                params={"q": query},
                timeout=self._timeout,
            )

        async with httpx.AsyncClient(
            transport=self._transport,
            follow_redirects=True,
        ) as client:
            return await client.get(
                self.search_url,
                params={"q": query},
                timeout=self._timeout,
            )


class DuckDuckGoHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[SearchResult] = []
        self.saw_result_marker = False
        self.saw_no_results_marker = False
        self._capture_field: str | None = None
        self._capture_tag: str | None = None
        self._capture_text: list[str] = []
        self._capture_href = ""

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        attrs_dict = {name: value or "" for name, value in attrs}
        classes = set(attrs_dict.get("class", "").split())

        if "no-results" in classes:
            self.saw_no_results_marker = True

        if "result__a" in classes:
            self.saw_result_marker = True
            self._start_capture("title", tag, attrs_dict.get("href", ""))
            return

        if "result__snippet" in classes:
            self.saw_result_marker = True
            self._start_capture("snippet", tag)

    def handle_data(self, data: str) -> None:
        if self._capture_field:
            self._capture_text.append(data)
        if "no results" in data.lower():
            self.saw_no_results_marker = True

    def handle_endtag(self, tag: str) -> None:
        if self._capture_field and tag == self._capture_tag:
            field = self._capture_field
            text = _normalize_text("".join(self._capture_text))
            href = self._capture_href
            self._clear_capture()
            if field == "title":
                url = _normalize_result_url(href)
                if url:
                    self.results.append(
                        SearchResult(
                            title=text or "Untitled",
                            url=url,
                            snippet="No snippet",
                        )
                    )
            elif field == "snippet" and self.results:
                self.results[-1].snippet = text or "No snippet"

    def _start_capture(
        self,
        field: str,
        tag: str,
        href: str = "",
    ) -> None:
        self._capture_field = field
        self._capture_tag = tag
        self._capture_text = []
        self._capture_href = href

    def _clear_capture(self) -> None:
        self._capture_field = None
        self._capture_tag = None
        self._capture_text = []
        self._capture_href = ""


def _normalize_text(value: str) -> str:
    return " ".join(value.split())


def _normalize_result_url(href: str) -> str:
    href = href.strip()
    if not href:
        return ""

    parsed = urlparse(href)
    query = parse_qs(parsed.query)
    if "uddg" in query and query["uddg"]:
        return unquote(query["uddg"][0])
    return href


def _parse_duckduckgo_results(html: str, limit: int) -> tuple[list[SearchResult], bool]:
    parser = DuckDuckGoHTMLParser()
    parser.feed(html)
    parser.close()
    return parser.results[:limit], parser.saw_result_marker or parser.saw_no_results_marker
