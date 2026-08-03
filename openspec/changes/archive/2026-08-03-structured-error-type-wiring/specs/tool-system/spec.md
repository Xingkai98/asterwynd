## ADDED Requirements

### Requirement: 工具执行结果携带结构化错误码

ToolRegistry 的执行结果 SHALL 携带可选的结构化错误码（`error_type`），并保持向后兼容：未打标的工具仍返回纯字符串或 ContentBlock，系统 SHALL 自动包装为结构化结果。错误码 SHALL 在错误产生点打标，而不是由调用方从文本猜测。

#### Scenario: 普通工具返回被自动包装

- **GIVEN** 一个工具返回纯字符串
- **WHEN** `ToolRegistry.execute` 执行该工具
- **THEN** 系统 SHALL 返回包含该字符串的结构化结果
- **AND** 结构化结果的 error_type SHALL 为 None

#### Scenario: 打标工具透传结构化错误码

- **GIVEN** 一个工具在错误产生点返回带 `error_type="timeout"` 的结构化结果
- **WHEN** `ToolRegistry.execute` 执行该工具
- **THEN** 系统 SHALL 原样透传该结构化结果
- **AND** error_type SHALL 保持 `"timeout"`

#### Scenario: registry deny 打标

- **GIVEN** 工具被 ModePolicy 判定为 DENY
- **WHEN** `ToolRegistry.execute` 执行该工具
- **THEN** 系统 SHALL 返回结构化结果，text 为权限拒绝说明
- **AND** error_type SHALL 为 `"permission_denied"`

#### Scenario: approval required 兜底打标

- **GIVEN** 工具需要审批且未获批准（registry 兜底路径）
- **WHEN** `ToolRegistry.execute` 执行该工具
- **THEN** 系统 SHALL 返回结构化结果，text 为审批要求说明
- **AND** error_type SHALL 为 `"approval_required"`
