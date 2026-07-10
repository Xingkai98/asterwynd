## MODIFIED Requirements

### Requirement: 工具并行执行标记

Tool 基类 SHALL 新增 `parallelizable` 属性。只读且无副作用的工具 SHALL 标记 `parallelizable = True`。写操作、状态变更和有副作用的工具 SHALL NOT 标记为可并行。

#### Scenario: 只读工具可并行

- **GIVEN** 一个 `Read` 工具实例
- **WHEN** 查询 `parallelizable` 属性
- **THEN** 返回值 SHALL 为 `True`

#### Scenario: 写工具不可并行

- **GIVEN** 一个 `Edit` 工具实例
- **WHEN** 查询 `parallelizable` 属性
- **THEN** 返回值 SHALL 为 `False`

#### Scenario: MCP 工具默认不可并行

- **GIVEN** 一个 MCP 工具实例
- **WHEN** 查询 `parallelizable` 属性
- **THEN** 返回值 SHALL 为 `False`（除非 MCP server 显式声明）
