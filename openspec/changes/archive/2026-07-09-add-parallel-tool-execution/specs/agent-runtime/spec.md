## MODIFIED Requirements

### Requirement: 工具调用并行执行

AgentLoop SHALL 在一次迭代内对连续的 `parallelizable` 工具调用执行并发执行。不可并行的工具调用 SHALL 保持串行。并发组中任一工具调用失败 SHALL NOT 影响组内其他工具调用。所有工具执行完成后 SHALL 按原始 tool call 顺序返回结果。

#### Scenario: 全并行组

- **GIVEN** 单次迭代中有 3 个 tool call 均为 `parallelizable`
- **WHEN** AgentLoop 执行这些 tool call
- **THEN** 3 个 call SHALL 在同一组中并发执行
- **AND** 结果 SHALL 按原始顺序排列

#### Scenario: 混合分组

- **GIVEN** tool call 序列为 `[Edit, Read, Read, Bash]`（Edit 和 Bash 不可并行，Read 可并行）
- **WHEN** AgentLoop 执行这些 tool call
- **THEN** 分组 SHALL 为 `[[Edit], [Read, Read], [Bash]]`
- **AND** 每组内部串行或并行执行

#### Scenario: 并行组错误隔离

- **GIVEN** 并行组内有 2 个 Read 调用，其中一个因文件不存在失败
- **WHEN** 并行组执行完成
- **THEN** 成功的 Read SHALL 返回文件内容
- **AND** 失败的 Read SHALL 返回错误
- **AND** 两个结果 SHALL 均出现在最终结果列表中

#### Scenario: 并行组审批退化

- **GIVEN** 并行组内有一个工具需要审批
- **WHEN** AgentLoop 准备执行并行组
- **THEN** 整组 SHALL 退化为串行执行
- **AND** 每个工具 SHALL 逐一通过审批 gate

#### Scenario: 结果顺序保持

- **GIVEN** 原始 tool call 顺序为 `[Grep, Read, Find]`（全部可并行）
- **WHEN** 并发执行完成
- **THEN** 返回结果 SHALL 保持 `[GrepResult, ReadResult, FindResult]` 顺序
