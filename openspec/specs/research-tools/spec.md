# research-tools 规格

## Purpose

定义当前联网研究工具。当前实现包含 WebSearch 和 WebFetch，均为 read-only 工具。

## Requirements

### Requirement: WebSearch 执行网页搜索

WebSearch SHALL 接收查询字符串和可选结果数量，通过搜索 provider registry 调用一个或多个 provider adapter，并返回稳定文本结果。每个 provider adapter SHALL 返回稳定的 provider response object，包含 provider 名称、搜索结果和可诊断元数据。当前未显式配置 provider 时，默认 provider 列表 SHALL 使用 `duckduckgo-html`。

#### Scenario: 搜索结果包含来源和字段

- **GIVEN** 搜索 provider 返回多个结果
- **WHEN** WebSearch 返回
- **THEN** 工具结果 SHALL 包含 provider 名称
- **AND** 每个结果 SHALL 包含序号、标题、URL 和摘要字段

#### Scenario: 搜索无结果

- **GIVEN** 搜索请求执行成功但未提取到匹配结果
- **WHEN** WebSearch 返回
- **THEN** 工具 SHALL 返回“未找到结果”或等价提示

#### Scenario: 搜索 provider 失败

- **GIVEN** provider 请求失败或响应无法解析
- **WHEN** WebSearch 捕获异常
- **THEN** 工具 SHALL 返回包含 provider 名称的可读错误字符串

### Requirement: WebSearch 支持搜索 provider 配置优先级

WebSearch SHALL 支持通过配置声明搜索 provider 启用状态和优先级。环境变量 SHALL 只用于 API key、base URL 等凭据或端点输入，不得作为 provider 排序来源。

#### Scenario: 配置 provider 优先级

- **GIVEN** 配置声明 provider A 优先于 provider B
- **WHEN** WebSearch 执行
- **THEN** 系统 SHALL 先尝试 provider A
- **AND** 只有在满足 fallback 条件时才尝试 provider B

#### Scenario: 配置禁用 provider

- **GIVEN** 配置声明 provider A disabled
- **WHEN** WebSearch 执行
- **THEN** 系统 SHALL NOT 尝试 provider A

#### Scenario: provider 缺少必需配置

- **GIVEN** provider A 需要 API key 或 base URL
- **AND** 当前环境没有提供该配置
- **WHEN** WebSearch 执行
- **THEN** 系统 SHALL 记录 provider A 未配置的诊断信息
- **AND** 如果存在后续可用 provider，系统 SHALL 尝试 fallback

### Requirement: WebSearch provider fallback 可诊断

WebSearch SHALL 在 fallback 发生时保留可诊断信息，包括尝试过的 provider、失败原因和最终 provider。

#### Scenario: 第一 provider 网络失败后 fallback

- **GIVEN** 第一 provider 网络失败
- **AND** 第二 provider 返回结果
- **WHEN** WebSearch 返回
- **THEN** 工具结果 SHALL 展示最终 provider
- **AND** trace 或工具结果 SHALL 能诊断第一 provider 的失败原因

#### Scenario: 搜索成功但无结果

- **GIVEN** 第一 provider 请求成功但返回空结果
- **WHEN** WebSearch 返回
- **THEN** 系统 SHALL NOT 默认尝试后续 provider
- **AND** 工具结果 SHALL 展示最终 provider 和无结果提示

### Requirement: WebFetch 获取网页内容

WebFetch SHALL 接收 URL 和可选字符上限，获取网页正文并按上限截断。返回内容 SHALL 包含 fetched URL、最终 URL、HTTP 状态、content type 和是否截断等诊断信息。

#### Scenario: 内容超过 limit

- **GIVEN** 网页文本长度超过 limit
- **WHEN** WebFetch 返回内容
- **THEN** 工具 SHALL 返回前 limit 个字符
- **AND** 附加截断说明

#### Scenario: 非成功 HTTP 状态

- **GIVEN** 服务端返回非 2xx 状态
- **WHEN** WebFetch 返回
- **THEN** 工具 SHALL 返回包含状态码、URL 和响应摘要的可读错误字符串

#### Scenario: 不支持的内容类型

- **GIVEN** 服务端返回非文本内容类型
- **WHEN** WebFetch 返回
- **THEN** 工具 SHALL 返回包含 content type 和 URL 的可读错误字符串

### Requirement: research tools 只读

WebSearch 和 WebFetch SHALL 声明为 read-only，不得修改本地工作区。

#### Scenario: 联网请求失败

- **GIVEN** 网络请求抛出异常
- **WHEN** 工具捕获异常
- **THEN** 工具 SHALL 返回可读错误字符串
- **AND** 不修改本地文件
