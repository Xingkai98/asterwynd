## ADDED Requirements

### Requirement: ToolRegistry 使用当前 session mode

ToolRegistry SHALL 通过 session runtime state 读取当前 mode。mode transition 完成后，下一次 schema 获取和下一次工具执行 SHALL 使用最新 mode。

#### Scenario: 切换后 schema 立即变化

- **GIVEN** ToolRegistry 当前以 `build` mode 暴露工具
- **WHEN** session mode 切换为 `read_only`
- **THEN** 下一次 `get_all_schemas()` SHALL 使用 `read_only` mode 过滤工具

#### Scenario: 切换后尚未执行的工具按新 mode 拒绝

- **GIVEN** LLM 已在旧 mode 下生成 tool call
- **WHEN** 该 tool call 真正执行前 session mode 已切换为更严格的 mode
- **THEN** `execute()` SHALL 按最新 mode 判断权限
- **AND** 返回权限拒绝结果而不是执行该工具
