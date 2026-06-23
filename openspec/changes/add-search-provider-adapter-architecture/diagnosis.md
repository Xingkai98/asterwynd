## Symptom

`harden-web-research-tools` 已经让 WebSearch 具备更稳定的文本输出和单 provider 边界，但当前 master 仍只有 DuckDuckGo HTML provider。后续如果继续在 WebSearchTool 内直接追加 Tavily、SerpAPI、Brave Search 或 SearXNG 分支，会把鉴权、成本、fallback、错误分类和结果字段差异混在工具实现里。

## Reproduction

阅读当前 research tools 实现和 `harden-web-research-tools` 归档结论即可复现该结构限制：WebSearchTool 可以注入 provider 或 transport 做测试，但还没有 provider registry、配置驱动优先级、多 provider fallback、capability metadata 或跨 provider diagnostics。

## Evidence

- `agent/tools/builtin/web_search.py` 当前默认仍绑定 DuckDuckGo HTML provider。
- `tests/agent/tools/test_web_research_tools.py` 覆盖 fake provider 和 DuckDuckGo HTML fixture，但没有 provider registry、优先级或 fallback 测试。
- `docs/openspec-change-backlog.md` 明确把 `add-search-provider-adapter-architecture` 放在 `harden-web-research-tools` 之后，作为完整 provider adapter 架构的独立 change。

## Root Cause

上一阶段的目标是硬化当前联网研究工具，而不是一次性设计完整搜索 provider 平台。因此它只抽出了足够测试和稳定输出的单 provider 边界，没有引入配置、registry、fallback 调度、鉴权模型或多 provider 兼容层。

## Recommended Direction

本 change 应先完成 provider 调研和设计确认，再实现最小但完整的 provider adapter 架构：明确 `SearchProvider` 协议、结果字段、capability metadata、provider registry / factory、配置优先级、fallback 条件和 diagnostics。默认路径应保持保守，CI 测试依赖 fake provider 或 fixture，不依赖真实外网。

## Regression Tests

- provider registry / factory 单元测试覆盖默认 provider、显式优先级、禁用 provider 和缺失 API key。
- fallback 测试覆盖网络失败、超时、5xx、解析失败、鉴权失败和无结果场景。
- 至少两个 provider adapter 使用 fixture 测试解析行为，不访问真实外网。
- WebSearch 工具层测试确认工具结果包含最终 provider 和 fallback diagnostics。
