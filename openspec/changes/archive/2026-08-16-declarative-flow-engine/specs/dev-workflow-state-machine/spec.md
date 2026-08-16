# dev-workflow-state-machine 规格 delta

## ADDED Requirements

### Requirement: 流程状态机声明化

流程状态机 SHALL 可声明化：`flow/statechart.json`（或等价声明文件）SHALL 声明状态（`<phase>.<sub_state>`）、初始状态与转移表（`on: <event>: <target>`），语义对齐现有 Python 常量（awaiting 三态建模为 `blocked.awaiting_*`、派生 any-of + 容忍异构）。薄引擎 SHALL 消费声明文件提供等价派生与转移，并与现有 Python 行为 parity 等价 pin 住（golden 断言）。

#### Scenario: 声明文件定义状态机

- **WHEN** 查看 `flow/statechart.json`
- **THEN** 它 SHALL 声明 `initial`、`states`（每个含 `on` 转移表）
- **AND** 状态名 SHALL 为 `<phase>.<sub_state>` 形式
- **AND** awaiting 态 SHALL 建模为 `blocked.awaiting_*`

#### Scenario: 引擎与现有 Python parity 等价

- **WHEN** 对同一事件序列运行薄引擎与现有 Python 派生
- **THEN** 结果 SHALL 一致（parity golden 断言，完整投影 dict）
- **AND** 引擎对未知事件类型的处理 SHALL 与现有 Python 一致（raise）
- **AND** 「容忍异构」SHALL 仅指无 seed 事件（首事件非 `change_created`）仍可投影，不抛错

#### Scenario: 改规则不改 Python

- **WHEN** 在声明文件中新增状态或转移（如 test fixture 注入 `awaiting_design_confirmation`）
- **THEN** 引擎 SHALL 正确派生新态与转移
- **AND** 现有 Python 逻辑 SHALL 不需要修改
- **AND** 本 change SHALL 不要求现有 Python 处理该新态（未知 sub_state 由既有校验拒绝，属已知边界）

### Requirement: 状态机声明与执行方法分工

流程状态机声明（`statechart`）与每个状态使用的执行方法（`workflow_methods.json`）SHALL 分工不重叠：statechart 描述状态流转，workflow_methods 描述每个状态用哪个 skill/command/agent 执行。

#### Scenario: 状态流转变更只改 statechart

- **WHEN** 调整状态转移（如新增 transition）
- **THEN** 只需修改 `statechart` 声明文件
- **AND** `workflow_methods.json` 的执行方法映射 SHALL 不变

#### Scenario: 执行方法变更只改 workflow_methods

- **WHEN** 更换某状态使用的 skill/command
- **THEN** 只需修改 `workflow_methods.json`
- **AND** `statechart` 声明文件 SHALL 不变
