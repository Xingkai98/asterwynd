## MODIFIED Requirements

### Requirement: browser/computer use 当前为预留能力域

系统 SHALL 在本 change 实现后提供最小浏览器工具；在实现前不得声称已经支持浏览器自动化、桌面截图、鼠标键盘输入或 GUI 操作。

#### Scenario: 当前工具列表

- **GIVEN** AgentLoop 构造默认工具
- **WHEN** 工具 schema 暴露给 LLM
- **THEN** 当前系统 SHALL NOT 包含浏览器或桌面操作工具
- **AND** 只有在本 change 实现后才 MAY 暴露受控 browser tools

## ADDED Requirements

### Requirement: browser use 受安全策略约束

Browser tools SHALL 受 URL allowlist、超时、凭据处理、截图存储和审计策略约束。

#### Scenario: URL 不在 allowlist

- **GIVEN** browser tool 请求访问未允许 URL
- **WHEN** browser policy 校验 URL
- **THEN** 系统 SHALL 拒绝访问

#### Scenario: 保存截图

- **GIVEN** browser tool 生成截图
- **WHEN** 系统保存截图 artifact
- **THEN** 截图 SHALL 保存到 workspace policy 允许的 artifact 路径

### Requirement: 提供最小浏览器读取工具

系统 SHALL 提供最小 browser tools，用于打开允许 URL、读取页面标题或文本、保存截图。

#### Scenario: 读取允许页面

- **GIVEN** URL 命中 allowlist
- **WHEN** 调用 browser read tool
- **THEN** 工具 SHALL 返回页面标题或文本摘要
