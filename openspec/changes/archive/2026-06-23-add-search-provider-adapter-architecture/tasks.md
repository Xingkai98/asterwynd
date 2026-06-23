## 1. 调研与需求

- [x] 1.1 调研 Tavily、SerpAPI、Brave Search、DuckDuckGo HTML、SearXNG 的鉴权、字段、错误、成本、速率限制和测试方式。
- [x] 1.2 调研至少两个 coding-agent 或 agent 框架中的搜索 provider / search tool 实现。
- [x] 1.3 将调研结论写入 `design.md` 或 `docs/discussions/`。
- [x] 1.4 开发前使用 `grill-with-docs` 或等价设计追问审视 `design.md`，确认 provider 协议、优先级、fallback、配置、鉴权、测试和文档影响。

## 2. 规格

- [x] 2.1 修改 research-tools 规格，定义搜索 provider adapter 架构。
- [x] 2.2 定义 provider registry、配置优先级和 fallback 语义。
- [x] 2.3 定义 provider diagnostics 在工具结果、trace 和测试中的可观察语义。
- [x] 2.4 同步对应 current spec 到 `openspec/specs/<capability>/spec.md`。

## 3. 测试

- [x] 3.1 新增 fake provider registry / factory 测试。
- [x] 3.2 新增 provider 优先级和 fallback 测试。
- [x] 3.3 新增至少两个 provider adapter 的 fixture 测试。
- [x] 3.4 新增 WebSearch 工具层最终 provider 和 fallback diagnostics 测试。
- [x] 3.5 新增配置缺失、API key 缺失和禁用 provider 的测试。

## 4. 实现

- [x] 4.1 定义 provider response、capability metadata 和错误模型。
- [x] 4.2 实现 provider registry / factory。
- [x] 4.3 实现配置驱动的 provider 优先级。
- [x] 4.4 实现 fallback 调度和 diagnostics 记录。
- [x] 4.5 实现至少两个 provider adapter，其中一个复用 DuckDuckGo HTML。
- [x] 4.6 将 WebSearchTool 接入 provider registry。

## 5. 验证

- [x] 5.1 运行 research tools 和 provider adapter 测试。
- [x] 5.2 运行全量测试。
- [x] 5.3 运行 OpenSpec strict validate。
- [x] 5.4 跑通至少一个 benchmark smoke。
- [ ] 5.5 如环境变量提供真实 provider key，手动运行 live smoke 并记录结果。
