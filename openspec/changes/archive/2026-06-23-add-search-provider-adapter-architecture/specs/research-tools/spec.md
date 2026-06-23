## ADDED Requirements

### Requirement: WebSearch 支持搜索 provider adapter 架构

WebSearch SHALL 通过搜索 provider registry 调用一个或多个 provider adapter，而不是直接绑定单个 provider 实现。
每个 provider adapter SHALL 返回稳定的 provider response object，包含 provider 名称、搜索结果和可诊断元数据。

#### Scenario: 使用默认搜索 provider

- **GIVEN** 用户未显式配置搜索 provider
- **WHEN** WebSearch 执行
- **THEN** 系统 SHALL 使用默认 provider 列表中的第一个可用 provider
- **AND** 工具结果 SHALL 展示最终使用的 provider 名称

### Requirement: 搜索 provider 支持配置优先级

系统 SHALL 支持通过配置声明搜索 provider 启用状态和优先级。
环境变量 SHALL 只用于 API key、base URL 等凭据/端点输入，不得作为 provider 排序来源。

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

### Requirement: 搜索 provider fallback 可诊断

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

### Requirement: 搜索 provider adapter 测试不依赖真实外网

搜索 provider registry、fallback 和 adapter 解析测试 SHALL 使用 fake provider、fake HTTP 响应或 fixture，不依赖真实外网。

#### Scenario: CI 运行 provider adapter 测试

- **GIVEN** CI 环境没有 provider API key
- **WHEN** 运行 provider adapter 单元测试
- **THEN** 测试 SHALL 使用 fake provider 或 fixture
- **AND** 测试 SHALL NOT 访问真实外网
