# browser-computer-use 规格

## Purpose

定义浏览器操作的安全基础、URL allowlist、截图 artifact 存储和最小只读浏览器工具集。当前提供受控只读浏览器观察能力；交互能力（click、type）后续 change 单独实现。

## Requirements

### Requirement: 提供最小浏览器读取工具

系统 SHALL 提供最小 browser tools，用于打开允许 URL、读取页面标题或文本、滚动和保存截图。工具受 BrowserConfig 控制，默认 disabled。

#### Scenario: 读取允许页面

- **GIVEN** URL 命中 allowlist
- **WHEN** 调用 browser read tool
- **THEN** 工具 SHALL 返回页面标题或文本摘要

#### Scenario: 浏览器工具默认不暴露

- **GIVEN** BrowserConfig.enabled 为 false
- **WHEN** AgentLoop 构造默认工具
- **THEN** 系统 SHALL NOT 注册 browser tools

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

### Requirement: 交互能力后续实现

系统 SHALL NOT 提供点击、输入、表单填写等破坏性浏览器交互能力；这些能力由后续 change 单独实现。

#### Scenario: 当前工具列表

- **GIVEN** AgentLoop 构造默认工具
- **WHEN** 工具 schema 暴露给 LLM
- **THEN** 当前系统 SHALL NOT 包含点击、输入或表单填写工具

