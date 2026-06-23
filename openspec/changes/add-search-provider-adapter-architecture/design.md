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

## Decisions

### Decision 1: Provider protocol shape

当前待确认：`SearchProvider.search()` 返回纯 `list[SearchResult]`，还是返回包含 diagnostics 的 provider response object。

推荐：返回 provider response object，包含 `provider_name`、`results`、`diagnostics`、`raw_status` 和 `fallback_reason`，避免把 fallback 信息塞进异常。

### Decision 2: Provider priority source

当前待确认：优先级来自配置文件、环境变量还是固定默认列表。

推荐：配置文件声明显式优先级；未配置时使用保守默认 provider。

### Decision 3: Fallback conditions

当前待确认：哪些错误触发 fallback。

推荐：网络失败、超时、5xx、provider parse failure 可 fallback；4xx 鉴权/配额错误返回明确诊断并可 fallback 到无 key provider；无结果不自动 fallback，除非配置允许。

### Decision 4: Test strategy

当前待确认：真实 provider smoke 是否纳入 CI。

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
