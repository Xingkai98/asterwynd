## Why

`harden-web-research-tools` 只硬化当前 DuckDuckGo HTML 路径，并把单 provider adapter 从 WebSearchTool 中拆出。后续如果要支持 Tavily、SerpAPI、Brave Search、SearXNG、自托管搜索或其他开源/商业 provider，需要正式设计 provider adapter 架构，而不是在 WebSearchTool 内继续堆分支。

搜索 provider 选择会影响联网调研质量、成本、速率限制、鉴权、失败降级、结果字段和 benchmark 可重复性，因此需要独立 change 承接充分调研和设计。

## Change Type

- primary: feature
- secondary: [research]

## What Changes

- 调研 coding agent 和开源搜索工具的 provider adapter 实现，形成可提交结论。
- 定义搜索 provider 协议、能力元数据、错误分类和结果字段。
- 增加 provider registry / factory，并支持配置 provider 优先级。
- 支持多 provider fallback，并记录 provider 选择、失败原因和最终使用 provider。
- 为至少两个 provider 建立 adapter，其中一个可以是当前 DuckDuckGo HTML。
- 建立 fake provider / fake HTTP 测试，不依赖真实外网；真实 provider smoke 只能作为可选手动验证。

## Capabilities

### Modified Capabilities

- `research-tools`: 从单 DuckDuckGo HTML provider 演进为可配置搜索 provider adapter 架构。

## Impact

- 影响代码：
  - `agent/tools/builtin/search_providers.py`
  - `agent/tools/builtin/web_search.py`
  - 配置加载路径
  - 可能新增 `agent/research/` 或 `agent/search/`
- 影响测试：
  - `tests/agent/tools/test_web_research_tools.py`
  - 可能新增 `tests/agent/research/`
- 实现前必须先完成 provider 调研、优先级策略和配置/鉴权边界确认。
