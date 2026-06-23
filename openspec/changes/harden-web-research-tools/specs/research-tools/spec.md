## ADDED Requirements

### Requirement: Web research tools 提供可诊断结果

WebSearch 和 WebFetch SHALL 在无结果、解析失败、网络失败和截断时返回可读且可测试的诊断信息。

#### Scenario: 搜索 provider 解析失败

- **GIVEN** 搜索 provider 返回无法解析的响应
- **WHEN** WebSearch 执行
- **THEN** 工具 SHALL 返回可读错误或无结果说明
- **AND** SHALL NOT 修改本地工作区

### Requirement: WebSearch 返回可展示结果结构

WebSearch SHALL 保留搜索结果的标题、URL 和摘要，便于 Web / CLI / TUI 展示和 trace 诊断。

#### Scenario: 搜索返回多条结果

- **GIVEN** 搜索 provider 返回多条结果
- **WHEN** WebSearch 返回
- **THEN** 调用方 SHALL 能区分每条结果的标题、URL 和摘要
