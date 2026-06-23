## ADDED Requirements

### Requirement: Web research tools 提供可诊断结果

WebSearch 和 WebFetch SHALL 在无结果、解析失败、网络失败、HTTP 错误、内容类型不支持和截断时返回可读且可测试的诊断信息。

#### Scenario: 搜索 provider 解析失败

- **GIVEN** 搜索 provider 返回无法解析的响应
- **WHEN** WebSearch 执行
- **THEN** 工具 SHALL 返回 `WebSearch error: provider response could not be parsed`
- **AND** 工具 SHALL 返回当前 provider 名称
- **AND** SHALL NOT 修改本地工作区

#### Scenario: 搜索 provider 无结果

- **GIVEN** 搜索 provider 返回可识别的无结果响应
- **WHEN** WebSearch 执行
- **THEN** 工具 SHALL 返回 `No search results for: <query>`
- **AND** 工具 SHALL 返回当前 provider 名称

#### Scenario: 搜索 provider 网络失败

- **GIVEN** 搜索 provider 请求抛出网络异常
- **WHEN** WebSearch 执行
- **THEN** 工具 SHALL 返回 `WebSearch error: provider request failed: <message>`
- **AND** SHALL NOT 修改本地工作区

#### Scenario: WebFetch 网络失败

- **GIVEN** WebFetch 请求抛出网络异常
- **WHEN** WebFetch 执行
- **THEN** 工具 SHALL 返回 `WebFetch error: request failed: <message>`
- **AND** SHALL NOT 修改本地工作区

### Requirement: WebSearch 返回可展示结果结构

WebSearch SHALL 以稳定纯文本格式返回 provider 名称，并为每条搜索结果保留标题、URL 和摘要，便于 Web / CLI / TUI 展示和 trace 诊断。

#### Scenario: 搜索返回多条结果

- **GIVEN** 搜索 provider 返回多条结果
- **WHEN** WebSearch 返回
- **THEN** 工具 SHALL 返回 `Search results for: <query>`
- **AND** 工具 SHALL 返回 `Provider: duckduckgo-html`
- **AND** 每条结果 SHALL 使用 `Result N:` 分隔
- **AND** 每条结果 SHALL 包含 `Title: <title>`、`URL: <url>` 和 `Snippet: <summary>`

### Requirement: WebFetch 返回内容边界诊断

WebFetch SHALL 以稳定纯文本格式返回原始 URL、最终 URL、HTTP 状态、内容类型和截断诊断。

#### Scenario: WebFetch 返回文本内容

- **GIVEN** WebFetch 收到 2xx 文本类响应
- **WHEN** WebFetch 返回
- **THEN** 工具 SHALL 返回 `Fetched: <url>`
- **AND** 工具 SHALL 返回 `Final URL: <final-url>`
- **AND** 工具 SHALL 返回 `Status: <status-code>`
- **AND** 工具 SHALL 返回 `Content-Type: <content-type>`
- **AND** 工具 SHALL 在空行后返回按 limit 截断的正文

#### Scenario: WebFetch 内容超过 limit

- **GIVEN** WebFetch 收到 2xx 文本类响应
- **AND** 正文长度超过 limit
- **WHEN** WebFetch 返回
- **THEN** 工具 SHALL 返回前 limit 个字符
- **AND** 工具 SHALL 返回 `Truncated: yes, omitted <n> characters`

#### Scenario: WebFetch 返回非 2xx 状态

- **GIVEN** WebFetch 收到非 2xx 响应
- **WHEN** WebFetch 返回
- **THEN** 工具 SHALL 返回 `WebFetch error: HTTP <status-code>`
- **AND** 工具 SHALL 返回原始 URL、最终 URL 和内容类型
- **AND** 工具 SHALL NOT 返回响应正文

#### Scenario: WebFetch 返回不支持的内容类型

- **GIVEN** WebFetch 收到 2xx 响应
- **AND** 响应内容类型不是 `text/*`、`application/json`、`application/xml`、`application/xhtml+xml` 或 `application/javascript`
- **WHEN** WebFetch 返回
- **THEN** 工具 SHALL 返回 `WebFetch error: unsupported content type`
- **AND** 工具 SHALL 返回原始 URL、最终 URL、HTTP 状态和内容类型
- **AND** 工具 SHALL NOT 返回响应正文

### Requirement: research tools 支持无外网测试替身

WebSearch 和 WebFetch SHALL 支持注入 HTTP 测试替身，以便单元测试覆盖 provider 响应、异常、重定向、状态码和内容类型，不依赖真实外网。

#### Scenario: 使用 fake transport 测试联网工具

- **GIVEN** 测试向 WebSearch 或 WebFetch 注入 fake transport
- **WHEN** 工具执行
- **THEN** 工具 SHALL 使用 fake transport 返回的响应或异常
- **AND** 测试 SHALL NOT 访问真实外网

### Requirement: WebSearch 隔离当前搜索 provider adapter

WebSearch SHALL 将工具层格式化和当前搜索 provider adapter 分离；当前 change 只要求实现一个 DuckDuckGo HTML provider adapter，不要求 provider registry、多 provider fallback 或配置优先级。

#### Scenario: WebSearch 使用注入的搜索 provider

- **GIVEN** 测试向 WebSearch 注入 fake search provider
- **WHEN** WebSearch 执行
- **THEN** 工具 SHALL 使用 fake provider 返回的搜索结果
- **AND** 工具 SHALL 在输出中展示 fake provider 名称
