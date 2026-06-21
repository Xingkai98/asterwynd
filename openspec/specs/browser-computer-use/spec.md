# browser-computer-use 规格

## Purpose

定义浏览器、桌面操作、截图、输入和安全边界的未来能力域。当前仓库尚未实现浏览器或桌面 computer use。

## Requirements

### Requirement: browser/computer use 当前为预留能力域

系统 SHALL NOT 声称已经支持浏览器自动化、桌面截图、鼠标键盘输入或 GUI 操作。

#### Scenario: 当前工具列表

- **GIVEN** AgentLoop 构造默认工具
- **WHEN** 工具 schema 暴露给 LLM
- **THEN** 当前系统 SHALL NOT 包含浏览器或桌面操作工具

### Requirement: 未来实现必须先定义安全边界

新增 browser/computer use 前 SHALL 明确可访问 URL、凭据处理、截图存储、输入权限、超时和审计策略。

#### Scenario: 准备增加浏览器工具

- **GIVEN** 需求提出浏览器操作
- **WHEN** 尚未形成 accepted change
- **THEN** 不得直接增加可执行浏览器动作的工具

