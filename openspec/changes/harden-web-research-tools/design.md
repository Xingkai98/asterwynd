## Context

WebSearch 和 WebFetch 是 coding agent 调研外部信息的基础工具。当前实现和规格偏最小可用，缺少对搜索结果结构、失败类型和可重复测试方式的约束。

## Goals / Non-Goals

**Goals:**

- 提高 WebSearch / WebFetch 的错误可读性和可诊断性。
- 让搜索结果更适合 UI、trace 和最终回复引用。
- 建立无需真实网络的测试替身。

**Non-Goals:**

- 不引入浏览器自动化。
- 不实现 RAG 索引或长期缓存。
- 不保证搜索 provider 的排序质量。

## Decisions

### Decision 1: 先增强结构和诊断，不换工具边界

WebSearch / WebFetch 仍保持 read-only 工具，不引入写文件、副作用缓存或浏览器状态。

### Decision 2: 测试优先使用 fake provider

联网工具测试应通过 fake response、fixture HTML 和异常注入覆盖，不依赖真实外网请求。

### Decision 3: 当前 change 只抽单 provider 内部边界

WebSearchTool 只负责工具参数、结果格式和诊断文本；当前唯一 provider adapter 是 DuckDuckGo HTML。完整 provider registry、多 provider fallback、优先级和配置留给后续独立 change。

## Risks / Trade-offs

- [Risk] 过早绑定某个搜索 provider 的 HTML 结构。Mitigation: 将 provider 解析封装在工具内部，并用 fixture 覆盖。
- [Risk] 返回结构变更影响现有 prompt。Mitigation: 保留可读文本输出，同时逐步增加结构化字段。
- [Risk] 把 hardening 扩大成完整搜索 provider 平台。Mitigation: 本 change 只拆出当前 DuckDuckGo provider adapter，不引入 registry、fallback 或配置。

## Testing Strategy

- 单元测试覆盖无结果、解析失败、网络异常、截断和重定向。
- 使用 fixture HTML / fake client，避免真实网络。
- 回归测试确认工具仍声明为 read-only。
