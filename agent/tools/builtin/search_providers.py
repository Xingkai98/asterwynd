from __future__ import annotations

import os
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any, Mapping, Protocol, Sequence
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import httpx


DEFAULT_SEARCH_PROVIDER_ORDER = ("duckduckgo-html",)


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SearchProviderCapability:
    name: str
    requires_api_key: bool = False
    requires_base_url: bool = False
    default_enabled: bool = False
    supports_snippets: bool = True
    supports_time_range: bool = False
    supports_domain_filters: bool = False
    supports_raw_content: bool = False
    cost_model: str = "free"
    stability: str = "stable"


@dataclass(frozen=True)
class SearchProviderAttempt:
    provider_name: str
    status: str
    category: str
    message: str = ""
    raw_status: int | None = None


@dataclass
class SearchProviderResponse:
    provider_name: str
    results: list[SearchResult]
    diagnostics: tuple[SearchProviderAttempt, ...] = ()
    raw_status: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class SearchProvider(Protocol):
    name: str
    capability: SearchProviderCapability

    async def search(self, query: str, limit: int) -> SearchProviderResponse:
        ...


class SearchProviderError(Exception):
    def __init__(
        self,
        message: str,
        *,
        category: str = "provider_error",
        raw_status: int | None = None,
        fallbackable: bool = True,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.raw_status = raw_status
        self.fallbackable = fallbackable


class SearchProviderConfigurationError(SearchProviderError):
    def __init__(self, message: str) -> None:
        super().__init__(message, category="not_configured", fallbackable=True)


class SearchProviderRequestError(SearchProviderError):
    def __init__(self, message: str, *, category: str = "network_error") -> None:
        super().__init__(message, category=category, fallbackable=True)


class SearchProviderParseError(SearchProviderError):
    def __init__(self, message: str = "provider response could not be parsed") -> None:
        super().__init__(message, category="parse_error", fallbackable=True)


class SearchProviderHTTPError(SearchProviderError):
    def __init__(self, status_code: int, message: str | None = None) -> None:
        category = _http_error_category(status_code)
        super().__init__(
            message or f"provider returned HTTP {status_code}",
            category=category,
            raw_status=status_code,
            fallbackable=True,
        )
        self.status_code = status_code


class SearchProviderExhaustedError(SearchProviderError):
    def __init__(self, attempts: Sequence[SearchProviderAttempt]) -> None:
        super().__init__(
            "all search providers failed",
            category="providers_exhausted",
            fallbackable=False,
        )
        self.attempts = tuple(attempts)


class UnconfiguredSearchProvider:
    capability = SearchProviderCapability(
        name="unconfigured",
        requires_api_key=True,
        default_enabled=False,
        cost_model="unknown",
        stability="unavailable",
    )

    def __init__(self, name: str, missing: str) -> None:
        self.name = name
        self.capability = SearchProviderCapability(
            name=name,
            requires_api_key="API_KEY" in missing,
            requires_base_url="BASE_URL" in missing,
            default_enabled=False,
            cost_model="unknown",
            stability="unavailable",
        )
        self._missing = missing

    async def search(self, query: str, limit: int) -> SearchProviderResponse:
        raise SearchProviderConfigurationError(f"missing {self._missing}")


class SearchProviderRegistry:
    def __init__(self, providers: Sequence[SearchProvider]) -> None:
        self._providers = tuple(providers)

    @property
    def providers(self) -> tuple[SearchProvider, ...]:
        return self._providers

    async def search(self, query: str, limit: int) -> SearchProviderResponse:
        attempts: list[SearchProviderAttempt] = []
        if not self._providers:
            raise SearchProviderExhaustedError(
                [
                    SearchProviderAttempt(
                        provider_name="registry",
                        status="error",
                        category="not_configured",
                        message="no search providers configured",
                    )
                ]
            )

        for provider in self._providers:
            try:
                response = await provider.search(query, limit)
            except SearchProviderError as error:
                attempts.append(
                    SearchProviderAttempt(
                        provider_name=provider.name,
                        status="error",
                        category=error.category,
                        message=str(error),
                        raw_status=error.raw_status,
                    )
                )
                if error.fallbackable:
                    continue
                raise SearchProviderExhaustedError(attempts) from error

            success_attempt = SearchProviderAttempt(
                provider_name=response.provider_name,
                status="success",
                category="success",
                raw_status=response.raw_status,
            )
            response.diagnostics = tuple([*attempts, success_attempt])
            return response

        raise SearchProviderExhaustedError(attempts)


class DuckDuckGoHTMLSearchProvider:
    name = "duckduckgo-html"
    search_url = "https://html.duckduckgo.com/html/"
    capability = SearchProviderCapability(
        name=name,
        default_enabled=True,
        supports_snippets=True,
        cost_model="free",
        stability="reverse_engineered_html",
    )

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

    async def search(self, query: str, limit: int) -> SearchProviderResponse:
        try:
            response = await self._get(query)
        except httpx.TimeoutException as error:
            raise SearchProviderRequestError(str(error), category="timeout") from error
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
            return SearchProviderResponse(
                provider_name=self.name,
                results=results,
                raw_status=response.status_code,
            )
        raise SearchProviderParseError()

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


class SearXNGSearchProvider:
    name = "searxng"
    capability = SearchProviderCapability(
        name=name,
        requires_base_url=True,
        default_enabled=False,
        supports_snippets=True,
        cost_model="self_hosted",
        stability="deployment_dependent",
    )

    def __init__(
        self,
        *,
        base_url: str,
        transport: httpx.AsyncBaseTransport | httpx.BaseTransport | None = None,
        client: httpx.AsyncClient | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._base_url = base_url.rstrip("/") + "/"
        self._transport = transport
        self._client = client
        self._timeout = timeout

    async def search(self, query: str, limit: int) -> SearchProviderResponse:
        try:
            response = await self._get(query, limit)
        except httpx.TimeoutException as error:
            raise SearchProviderRequestError(str(error), category="timeout") from error
        except httpx.RequestError as error:
            raise SearchProviderRequestError(str(error)) from error
        except Exception as error:
            raise SearchProviderRequestError(str(error)) from error

        if not 200 <= response.status_code < 300:
            raise SearchProviderHTTPError(response.status_code)

        try:
            payload = response.json()
        except ValueError as error:
            raise SearchProviderParseError() from error
        if not isinstance(payload, dict):
            raise SearchProviderParseError()

        raw_results = payload.get("results")
        if not isinstance(raw_results, list):
            raise SearchProviderParseError()

        results = []
        for raw_result in raw_results[:limit]:
            if not isinstance(raw_result, dict):
                continue
            title = str(raw_result.get("title") or "").strip()
            url = str(raw_result.get("url") or "").strip()
            snippet = str(
                raw_result.get("content")
                or raw_result.get("snippet")
                or "No snippet"
            ).strip()
            if title and url:
                results.append(
                    SearchResult(
                        title=title,
                        url=url,
                        snippet=snippet or "No snippet",
                        metadata={
                            "engine": raw_result.get("engine"),
                            "score": raw_result.get("score"),
                        },
                    )
                )

        return SearchProviderResponse(
            provider_name=self.name,
            results=results,
            raw_status=response.status_code,
        )

    async def _get(self, query: str, limit: int) -> httpx.Response:
        params = {"q": query, "format": "json", "pageno": 1, "limit": limit}
        url = urljoin(self._base_url, "search")
        if self._client:
            return await self._client.get(url, params=params, timeout=self._timeout)
        async with httpx.AsyncClient(transport=self._transport) as client:
            return await client.get(url, params=params, timeout=self._timeout)


class BraveSearchProvider:
    name = "brave"
    search_url = "https://api.search.brave.com/res/v1/web/search"
    capability = SearchProviderCapability(
        name=name,
        requires_api_key=True,
        default_enabled=False,
        supports_snippets=True,
        supports_time_range=True,
        supports_domain_filters=False,
        cost_model="paid_api",
        stability="official_api",
    )

    def __init__(
        self,
        *,
        api_key: str,
        transport: httpx.AsyncBaseTransport | httpx.BaseTransport | None = None,
        client: httpx.AsyncClient | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._api_key = api_key
        self._transport = transport
        self._client = client
        self._timeout = timeout

    async def search(self, query: str, limit: int) -> SearchProviderResponse:
        try:
            response = await self._get(query, limit)
        except httpx.TimeoutException as error:
            raise SearchProviderRequestError(str(error), category="timeout") from error
        except httpx.RequestError as error:
            raise SearchProviderRequestError(str(error)) from error
        except Exception as error:
            raise SearchProviderRequestError(str(error)) from error

        if not 200 <= response.status_code < 300:
            raise SearchProviderHTTPError(response.status_code)

        try:
            payload = response.json()
        except ValueError as error:
            raise SearchProviderParseError() from error
        if not isinstance(payload, dict):
            raise SearchProviderParseError()

        web_results = payload.get("web", {}).get("results")
        if not isinstance(web_results, list):
            raise SearchProviderParseError()

        results = []
        for raw_result in web_results[:limit]:
            if not isinstance(raw_result, dict):
                continue
            title = str(raw_result.get("title") or "").strip()
            url = str(raw_result.get("url") or "").strip()
            snippet = str(
                raw_result.get("description")
                or _first_extra_snippet(raw_result)
                or "No snippet"
            ).strip()
            if title and url:
                results.append(
                    SearchResult(
                        title=title,
                        url=url,
                        snippet=snippet or "No snippet",
                        metadata={
                            "age": raw_result.get("age"),
                            "language": raw_result.get("language"),
                            "family_friendly": raw_result.get("family_friendly"),
                        },
                    )
                )

        return SearchProviderResponse(
            provider_name=self.name,
            results=results,
            raw_status=response.status_code,
            metadata={
                "rate_limit": _rate_limit_metadata(response.headers),
            },
        )

    async def _get(self, query: str, limit: int) -> httpx.Response:
        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": self._api_key,
        }
        params = {"q": query, "count": min(limit, 20)}
        if self._client:
            return await self._client.get(
                self.search_url,
                params=params,
                headers=headers,
                timeout=self._timeout,
            )
        async with httpx.AsyncClient(transport=self._transport) as client:
            return await client.get(
                self.search_url,
                params=params,
                headers=headers,
                timeout=self._timeout,
            )


class TavilySearchProvider:
    name = "tavily"
    search_url = "https://api.tavily.com/search"
    capability = SearchProviderCapability(
        name=name,
        requires_api_key=True,
        default_enabled=False,
        supports_snippets=True,
        supports_time_range=True,
        supports_domain_filters=True,
        supports_raw_content=True,
        cost_model="free_tier_credits",
        stability="official_api",
    )

    def __init__(
        self,
        *,
        api_key: str,
        transport: httpx.AsyncBaseTransport | httpx.BaseTransport | None = None,
        client: httpx.AsyncClient | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._api_key = api_key
        self._transport = transport
        self._client = client
        self._timeout = timeout

    async def search(self, query: str, limit: int) -> SearchProviderResponse:
        try:
            response = await self._post(query, limit)
        except httpx.TimeoutException as error:
            raise SearchProviderRequestError(str(error), category="timeout") from error
        except httpx.RequestError as error:
            raise SearchProviderRequestError(str(error)) from error
        except Exception as error:
            raise SearchProviderRequestError(str(error)) from error

        if not 200 <= response.status_code < 300:
            raise SearchProviderHTTPError(response.status_code)

        try:
            payload = response.json()
        except ValueError as error:
            raise SearchProviderParseError() from error
        if not isinstance(payload, dict):
            raise SearchProviderParseError()

        raw_results = payload.get("results")
        if not isinstance(raw_results, list):
            raise SearchProviderParseError()

        results = []
        for raw_result in raw_results[:limit]:
            if not isinstance(raw_result, dict):
                continue
            title = str(raw_result.get("title") or "").strip()
            url = str(raw_result.get("url") or "").strip()
            snippet = str(raw_result.get("content") or "No snippet").strip()
            if title and url:
                results.append(
                    SearchResult(
                        title=title,
                        url=url,
                        snippet=snippet or "No snippet",
                        metadata={
                            "score": raw_result.get("score"),
                            "raw_content": raw_result.get("raw_content"),
                            "favicon": raw_result.get("favicon"),
                        },
                    )
                )

        return SearchProviderResponse(
            provider_name=self.name,
            results=results,
            raw_status=response.status_code,
            metadata={
                "response_time": payload.get("response_time"),
                "request_id": payload.get("request_id"),
                "usage": payload.get("usage"),
            },
        )

    async def _post(self, query: str, limit: int) -> httpx.Response:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "query": query,
            "max_results": limit,
            "search_depth": "basic",
        }
        if self._client:
            return await self._client.post(
                self.search_url,
                json=payload,
                headers=headers,
                timeout=self._timeout,
            )
        async with httpx.AsyncClient(transport=self._transport) as client:
            return await client.post(
                self.search_url,
                json=payload,
                headers=headers,
                timeout=self._timeout,
            )


def build_search_provider_registry(
    provider_configs: Sequence[Any] = (),
    *,
    environ: Mapping[str, str] | None = None,
    transport: httpx.AsyncBaseTransport | httpx.BaseTransport | None = None,
    client: httpx.AsyncClient | None = None,
    timeout: float = 10.0,
) -> SearchProviderRegistry:
    environ = environ or os.environ
    configs = tuple(provider_configs)
    names = (
        tuple(config.name for config in configs if config.enabled)
        if configs
        else DEFAULT_SEARCH_PROVIDER_ORDER
    )
    providers = [
        _build_provider(
            name,
            environ=environ,
            transport=transport,
            client=client,
            timeout=timeout,
        )
        for name in names
    ]
    return SearchProviderRegistry(providers)


def _build_provider(
    name: str,
    *,
    environ: Mapping[str, str],
    transport: httpx.AsyncBaseTransport | httpx.BaseTransport | None,
    client: httpx.AsyncClient | None,
    timeout: float,
) -> SearchProvider:
    if name == DuckDuckGoHTMLSearchProvider.name:
        return DuckDuckGoHTMLSearchProvider(
            transport=transport,
            client=client,
            timeout=timeout,
        )
    if name == SearXNGSearchProvider.name:
        base_url = environ.get("MYAGENT_SEARXNG_BASE_URL", "").strip()
        if not base_url:
            return UnconfiguredSearchProvider(name, "MYAGENT_SEARXNG_BASE_URL")
        return SearXNGSearchProvider(
            base_url=base_url,
            transport=transport,
            client=client,
            timeout=timeout,
        )
    if name == BraveSearchProvider.name:
        api_key = environ.get("MYAGENT_BRAVE_SEARCH_API_KEY", "").strip()
        if not api_key:
            return UnconfiguredSearchProvider(name, "MYAGENT_BRAVE_SEARCH_API_KEY")
        return BraveSearchProvider(
            api_key=api_key,
            transport=transport,
            client=client,
            timeout=timeout,
        )
    if name == TavilySearchProvider.name:
        api_key = environ.get("MYAGENT_TAVILY_API_KEY", "").strip()
        if not api_key:
            return UnconfiguredSearchProvider(name, "MYAGENT_TAVILY_API_KEY")
        return TavilySearchProvider(
            api_key=api_key,
            transport=transport,
            client=client,
            timeout=timeout,
        )
    return UnconfiguredSearchProvider(name, f"supported provider adapter for {name}")


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


def _http_error_category(status_code: int) -> str:
    if status_code == 429:
        return "rate_limited"
    if status_code in {401, 403}:
        return "auth_error"
    if status_code >= 500:
        return "http_5xx"
    if status_code >= 400:
        return "bad_request"
    return "http_error"


def _first_extra_snippet(raw_result: Mapping[str, Any]) -> str:
    extra_snippets = raw_result.get("extra_snippets")
    if isinstance(extra_snippets, list) and extra_snippets:
        return str(extra_snippets[0])
    return ""


def _rate_limit_metadata(headers: httpx.Headers) -> dict[str, str]:
    return {
        key: headers[key]
        for key in (
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining",
            "X-RateLimit-Reset",
            "Retry-After",
        )
        if key in headers
    }


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
