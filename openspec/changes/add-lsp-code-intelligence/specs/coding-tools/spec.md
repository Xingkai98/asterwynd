## ADDED Requirements

### Requirement: 提供只读 LSP 工具

系统 SHALL 提供只读 LSP 工具或等价 code intelligence 工具入口，用于查询 definition、references、hover、documentSymbol、workspaceSymbol 和 diagnostics。

#### Scenario: 调用 LSP 工具

- **GIVEN** agent 请求 LSP 查询
- **WHEN** 调用 LSP 工具
- **THEN** 工具 SHALL NOT 修改工作区文件
- **AND** SHALL 返回受限长度的结构化或可读结果

### Requirement: 修改工具可附加 LSP diagnostics

Write/Edit/patch 类修改工具 SHALL 能在成功修改后附加 LSP diagnostics 摘要，但修改权限仍由原工具控制。

#### Scenario: Edit 后附加诊断

- **GIVEN** Edit 成功修改文件
- **WHEN** LSP diagnostics 可用
- **THEN** Edit 结果 MAY 附加该文件的诊断摘要
- **AND** SHALL NOT 因 diagnostics 不可用而回滚成功编辑
