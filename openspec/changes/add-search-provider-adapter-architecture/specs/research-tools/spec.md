## ADDED Requirements

### Requirement: WebSearch 支持搜索 provider adapter 架构

WebSearch SHALL 通过搜索 provider registry 调用一个或多个 provider adapter，而不是直接绑定单个 provider 实现。

#### Scenario: 使用默认搜索 provider

- **GIVEN** 用户未显式配置搜索 provider
- **WHEN** WebSearch 执行
- **THEN** 系统 SHALL 使用默认 provider 列表中的第一个可用 provider
- **AND** 工具结果 SHALL 展示最终使用的 provider 名称

### Requirement: 搜索 provider 支持配置优先级

系统 SHALL 支持通过配置声明搜索 provider 启用状态和优先级。

#### Scenario: 配置 provider 优先级

- **GIVEN** 配置声明 provider A 优先于 provider B
- **WHEN** WebSearch 执行
- **THEN** 系统 SHALL 先尝试 provider A
- **AND** 只有在满足 fallback 条件时才尝试 provider B

### Requirement: 搜索 provider fallback 可诊断

WebSearch SHALL 在 fallback 发生时保留可诊断信息，包括尝试过的 provider、失败原因和最终 provider。

#### Scenario: 第一 provider 网络失败后 fallback

- **GIVEN** 第一 provider 网络失败
- **AND** 第二 provider 返回结果
- **WHEN** WebSearch 返回
- **THEN** 工具结果 SHALL 展示最终 provider
- **AND** trace 或工具结果 SHALL 能诊断第一 provider 的失败原因

### Requirement: 搜索 provider adapter 测试不依赖真实外网

搜索 provider registry、fallback 和 adapter 解析测试 SHALL 使用 fake provider、fake HTTP 响应或 fixture，不依赖真实外网。

#### Scenario: CI 运行 provider adapter 测试

- **GIVEN** CI 环境没有 provider API key
- **WHEN** 运行 provider adapter 单元测试
- **THEN** 测试 SHALL 使用 fake provider 或 fixture
- **AND** 测试 SHALL NOT 访问真实外网
