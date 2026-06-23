## ADDED Requirements

### Requirement: Web UI 支持工具结果折叠与展开

Web UI SHALL 对 WebFetch 等长工具结果默认折叠展示，并提供展开查看完整结果的入口。

#### Scenario: WebFetch 返回长内容

- **GIVEN** WebFetch 返回长内容
- **WHEN** Web UI 展示工具结果
- **THEN** 默认 SHALL 展示摘要
- **AND** 用户 SHALL 能展开查看完整结果
