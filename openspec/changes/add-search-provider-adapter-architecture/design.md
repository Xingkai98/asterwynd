## Context

当前 WebSearch 已有一个 DuckDuckGo HTML provider adapter，但它只是 hardening change 内的最小边界拆分。完整 provider architecture 需要回答：支持哪些 provider、如何配置、如何排序、什么时候 fallback、如何处理鉴权和成本、如何让结果结构稳定、如何测试。

## Goals / Non-Goals

**Goals:**

- 调研至少 5 类搜索 provider 或工具实现，包括开源和商业方案。
- 定义稳定的 `SearchProvider` 协议和 `SearchResult` 字段。
- 定义 provider capability metadata，例如是否需要 API key、是否支持 snippets、是否支持时间范围、是否适合默认启用。
- 定义 provider registry / factory 和配置格式。
- 定义 provider 优先级、fallback 条件和失败诊断。
- 至少实现两个 provider adapter，并保留当前 DuckDuckGo HTML provider。
- 保证测试不依赖真实外网。

**Non-Goals:**

- 不引入浏览器自动化；浏览器搜索能力属于 browser safety 方向。
- 不实现 RAG 索引或长期缓存。
- 不承诺某个商业 provider 一定可用。
- 不把真实外网 live test 纳入必跑单元测试。

## Required Research Before Implementation

实现前必须调研并记录结论，至少覆盖：

- Tavily、SerpAPI、Brave Search、DuckDuckGo HTML、SearXNG。
- 至少两个 coding-agent 或 agent 框架中的搜索工具实现。
- 各 provider 的鉴权、速率限制、返回字段、错误模型、成本和本地可测试性。
- 是否存在适合默认无 key 使用的 provider，以及它的稳定性风险。

调研结论应写入本 change 的设计文档或 `docs/discussions/`，不得只停留在对话中。

## Provider Research Notes

调研日期：2026-06-23。

本地参考仓库：当前 worktree 没有 `.dev/reference-repos.txt`，因此本轮未找到可用本地参考仓库，也未生成 codegraph 产物。

### Provider 对比

| Provider | 鉴权 | 结果字段 | 错误 / 限流 | 成本 / 默认启用判断 | 本地测试方式 |
| --- | --- | --- | --- | --- | --- |
| Tavily | `Authorization: Bearer <api-key>`；所有 endpoint 需要 API key。见 [Tavily API Introduction](https://docs.tavily.com/documentation/api-reference/introduction)。 | `/search` 返回 `results[]`，单条包含 `title`、`url`、`content`、`score`、可选 `raw_content`、`favicon`、`images`；响应还有 `response_time`、`usage.credits`、`request_id`。见 [Tavily Search API](https://docs.tavily.com/documentation/api-reference/endpoint/search)。 | 文档列出 400、401、429、432、433、500；限流响应为 429，并带 `retry-after`。开发 key 默认 100 RPM，生产 key 1000 RPM。见 [Tavily Rate Limits](https://docs.tavily.com/documentation/rate-limits)。 | 免费计划提供 1000 credits/month，付费用量按 credit 计价；`basic`/`fast`/`ultra-fast` 通常 1 credit，`advanced` 2 credits。适合有 key 时作为高质量 provider，不适合作为无 key 默认。见 [Tavily FAQ](https://docs.tavily.com/faq/faq)。 | fixture JSON 覆盖 `results[]`、空结果、429、401、500；不在 CI 调真实 API。 |
| SerpAPI | `api_key` 是 required query parameter。见 [SerpAPI Google Search API](https://serpapi.com/search-api)。 | Google engine 返回结构化 JSON，核心使用 `organic_results[]` 映射 `title`、`link`、`snippet`；还有 `search_metadata.status`、`search_metadata.id` 和顶层 `error`。 | 4xx 通常是参数、鉴权或额度问题；5xx 是 SerpAPI 服务端问题。失败搜索会在 `error` 字段给出消息。见 [SerpAPI Status and Error Codes](https://serpapi.com/api-status-and-error-codes)。 | 商业 SERP API；官方说明按月搜索量和小时吞吐限制计费/限流。适合需要 Google SERP 兼容时显式配置，不默认启用。见 [SerpAPI](https://serpapi.com/)。 | fixture JSON 覆盖 `organic_results`、`error`、不同 HTTP status；不依赖真实 key。 |
| Brave Search | `X-Subscription-Token: <api-key>` header。见 [Brave Web Search API](https://api-dashboard.search.brave.com/app/documentation/web-search/get-started)。 | Web Search 返回 `web.results[]`，单条包含 `title`、`url`、`description`，可选 `extra_snippets`；支持 freshness、country、language、safe search、pagination。 | API 每个响应包含 `X-RateLimit-*` header；超限返回 429。限流按 1 秒滑动窗口。见 [Brave Rate Limiting](https://api-dashboard.search.brave.com/documentation/guides/rate-limiting)。 | 商业 API，面向 web data / AI search；需要 key，不作为无 key 默认。见 [Brave Search API](https://brave.com/search/api/)。 | fixture JSON 覆盖 `web.results`、429、401/403、5xx；可解析 rate-limit header 到 diagnostics。 |
| DuckDuckGo HTML | 无 API key；当前实现请求 `https://html.duckduckgo.com/html/`。DuckDuckGo 的 Instant Answer API 不是完整搜索结果 API；HTML 路径属于反向解析。见 [SearXNG DuckDuckGo Engine](https://docs.searxng.org/dev/engines/online/duckduckgo.html)。 | HTML 页面解析 `.result__a`、`.result__snippet`；字段不稳定，只能映射 `title`、`url`、`snippet`。 | HTTP status、网络失败、HTML 结构变化都可能失败；没有正式错误模型或 SLA。SearXNG 文档也说明 DDG HTML form 字段是 reverse-engineered，未来可能受 bot detection 或页面结构变化影响。 | 唯一无 key 默认候选，但稳定性和合规风险最高；适合保守默认和 fallback，而非高可靠生产 provider。 | 继续使用 HTML fixture / `httpx.MockTransport`，覆盖正常结果、无结果 marker、解析失败。 |
| SearXNG | 自托管实例通常无 API key；鉴权取决于部署侧反向代理或网关。API base URL 必须配置。见 [SearXNG Search API](https://docs.searxng.org/dev/search_api.html)。 | `format=json` 返回聚合搜索结果；字段由实例和启用 engine 决定，通常可映射 title/url/content。 | 如果实例未启用 JSON format，请求会返回 403；公共实例可能禁用 JSON。见 [SearXNG Search API](https://docs.searxng.org/dev/search_api.html)。LiteLLM 文档也强调默认只启用 HTML，需要在 `settings.yml` 加 `json`。见 [LiteLLM SearXNG](https://docs.litellm.ai/docs/search/searxng)。 | 开源、自托管、隐私友好；不是零配置，因为必须提供可用实例 URL。适合显式配置为首选 provider。 | fixture JSON + fake base URL；配置测试覆盖缺失 base URL、403、空结果和解析失败。 |

### Agent / Framework 参考结论

- LangChain 把 Tavily 作为独立 tool integration，暴露 provider 原生能力，例如 `maxResults`、`topic`、`includeAnswer`、`includeRawContent`、`timeRange`、domain include/exclude，并要求 `TAVILY_API_KEY`。结果直接保留 title、URL、content、raw content、answer、images 等字段。见 [LangChain Tavily Search](https://docs.langchain.com/oss/javascript/integrations/tools/tavily_search)。
- Open WebUI 使用配置选择具体 web search engine。Brave 集成区分 `brave` 和 `brave_llm_context` 两个 endpoint，共享 `BRAVE_SEARCH_API_KEY`，并针对 429 做一次 1 秒 backoff retry；Tavily 集成通过 UI / 环境变量配置 key 和 provider。见 [Open WebUI Brave](https://docs.openwebui.com/features/chat-conversations/web-search/providers/brave/) 和 [Open WebUI Tavily](https://docs.openwebui.com/features/chat-conversations/web-search/providers/tavily/)。
- LlamaIndex 的 BraveSearchToolSpec 是 endpoint-specific tool：初始化时注入 `api_key`，请求时用 `query`、`search_lang`、`num_results`，HTTP error 直接 raise，返回 `Document(text=response.text)`。这说明简单集成容易把 provider JSON 泄漏给上层，MyAgent 应统一映射为稳定 `SearchResult`。见 [LlamaIndex Brave Search](https://developers.llamaindex.ai/python/framework-api-reference/tools/brave_search/)。
- CrewAI 把搜索能力拆成多个 provider-specific tools，包括 Brave、Exa、Tavily、SerpAPI 等；Tavily tool 直接依赖 `TAVILY_API_KEY`，并支持 search depth、topic、time range、domain filters、answer/raw content/images 等 provider 原生选项。见 [CrewAI Search & Research Overview](https://docs.crewai.com/en/tools/search-research/overview) 和 [CrewAI Tavily Search Tool](https://docs.crewai.com/en/tools/search-research/tavilysearchtool)。

### 对本 change 的设计影响

- `SearchResult` 应保持 MyAgent 稳定字段：`title`、`url`、`snippet`，可选扩展 `published_at`、`source`、`score`、`raw_content`、`metadata`。第一版实现只需要必填三元组和 `metadata`，避免过早承诺所有 provider 特性。
- `SearchProvider.search()` 不应只返回 `list[SearchResult]`。需要返回 `SearchProviderResponse`，包含 `provider_name`、`results`、`diagnostics`、`raw_status`、`request_id`/`usage` 等可选元数据，便于 WebSearch 输出和 trace 记录 fallback。
- provider capability metadata 至少包含：`name`、`requires_api_key`、`requires_base_url`、`default_enabled`、`supports_snippets`、`supports_time_range`、`supports_domain_filters`、`supports_raw_content`、`cost_model`、`stability`。
- fallback 错误分类应区分 `network_error`、`timeout`、`http_5xx`、`rate_limited`、`auth_error`、`quota_error`、`bad_request`、`parse_error`、`not_configured`。其中网络、超时、5xx、429、parse failure 可 fallback；401/403/缺 key/配额错误应记录明确诊断，并可继续 fallback 到后续可用 provider；空结果默认不 fallback。
- 默认 provider 列表建议只包含 `duckduckgo-html`，因为它无 key。配置提供 key 或 base URL 后再启用 `brave`、`tavily`、`serpapi`、`searxng`。
- 本 change 首批实现 `duckduckgo-html`、`tavily`、`brave` 和 `searxng`。`serpapi` 已完成调研但暂不实现，避免在同一 change 内扩大凭据和字段兼容面。

## Decisions

### Decision 1: Provider protocol shape

已确认：`SearchProvider.search()` 返回包含 diagnostics 的 provider response object，而不是纯 `list[SearchResult]`。

推荐：返回 provider response object，包含 `provider_name`、`results`、`diagnostics`、`raw_status` 和 `fallback_reason`，避免把 fallback 信息塞进异常。

### Decision 2: Provider priority source

已确认：provider 优先级来自配置文件声明；未配置时使用保守默认 provider 列表。环境变量只用于 API key、base URL 等凭据/端点输入，不用于排序。

推荐：配置文件声明显式优先级；未配置时使用保守默认 provider。

### Decision 3: Fallback conditions

已确认：网络失败、超时、HTTP 5xx、429 限流、provider parse failure、缺 key、缺 base URL、401/403 鉴权或配额错误可以 fallback；搜索成功但无结果默认不 fallback，除非后续显式配置允许。每次 fallback 都记录尝试过的 provider、错误分类、错误消息和最终 provider。

推荐：网络失败、超时、5xx、provider parse failure 可 fallback；4xx 鉴权/配额错误返回明确诊断并可 fallback 到无 key provider；无结果不自动 fallback，除非配置允许。

### Decision 4: Test strategy

已确认：真实 provider smoke 不纳入 CI。CI 只跑 fake provider、fixture 和 `httpx.MockTransport`；真实 provider smoke 必须由环境变量显式开启后手动运行。

推荐：CI 只跑 fake provider / fixture；真实 provider smoke 使用手动命令和环境变量显式开启。

## Risks / Trade-offs

- [Risk] 过早抽象导致 provider 协议过宽。Mitigation: 先从 WebSearch 当前需求和至少两个真实 adapter 反推最小协议。
- [Risk] 商业 provider 引入密钥和成本。Mitigation: provider capability metadata 明确鉴权和默认启用策略。
- [Risk] fallback 掩盖 provider 质量问题。Mitigation: trace 和工具结果必须记录尝试过的 provider、失败原因和最终 provider。
- [Risk] live provider 测试不稳定。Mitigation: 单元测试只依赖 fake provider 和 fixture。

## Testing Strategy

- fake provider registry 测试覆盖优先级排序。
- fake provider fallback 测试覆盖网络异常、超时、5xx、解析失败、鉴权失败和无结果。
- adapter 单元测试使用 fixture 响应，不访问真实外网。
- WebSearch 工具测试确认输出包含最终 provider 和 fallback diagnostics。
- 配置测试覆盖默认 provider、显式优先级、禁用 provider 和缺失 API key。
- 可选手动 smoke 覆盖真实 provider，不作为 CI 必跑项。
