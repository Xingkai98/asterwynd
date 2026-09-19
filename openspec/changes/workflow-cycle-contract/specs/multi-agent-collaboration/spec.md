## ADDED Requirements

### Requirement: 循环图形的声明期校验

`DeclareWorkflow` 的 `parse_workflow_spec` SHALL 在声明期对**有限循环**（route 回边）施加两条静态校验，SHALL 在不可能成功的环上拒绝声明并给出可操作的原因。

**校验一（空转环）**：环（强连通分量）内**没有任何产出节点**时 SHALL 拒绝。产出节点 SHALL 定义为 `kind == "subagent"` 或 `kind == "aggregate" and strategy == "llm"`（`foreach` 计入，因其展开项为 subagent）。`aggregate(strategy="collect")` 与 `route` SHALL NOT 计入——前者是纯逻辑拼接、后者不产出 `result` 槽，二者构成的环每轮读到相同输入，退出条件永不成立。

**校验二（回边死锁）**：`route` 节点存在**来自同一环内**的 `required` 数据入边时 SHALL 拒绝。`required` 数据入边要求上游先到终态，而同环内上游的启动又依赖该 route 的控制激活——二者互等。**route 自身的出边是控制边**，不受本条约束。

拒绝时的错误信息 SHALL 含环的成员节点 id、缺失项与**修法**，SHALL NOT 只陈述规则。

#### Scenario: 空转环被声明期拒绝

- **GIVEN** 一个环由 `route` 与 `aggregate(strategy="collect")` 构成（环内无任何产出节点）
- **WHEN** 调用 `DeclareWorkflow`
- **THEN** 声明 SHALL 被拒绝，错误信息 SHALL 指明「环内无产出节点」及环成员
- **AND** SHALL NOT 返回 workflow_id

#### Scenario: 环内有产出节点时正常声明

- **GIVEN** 一个环内包含 `subagent`（或 `aggregate(strategy="llm")`，或 `foreach`）
- **WHEN** 调用 `DeclareWorkflow`
- **THEN** 声明 SHALL 成功

#### Scenario: 回边为 required 数据边时被拒绝

- **GIVEN** 一个 `route` 节点有来自同一环内的 `required` 数据入边（未显式声明 `required: false`）
- **WHEN** 调用 `DeclareWorkflow`
- **THEN** 声明 SHALL 被拒绝，错误信息 SHALL 提示「改为 `required: false` 或从 route 出发」

#### Scenario: 回边从 route 出发（控制边）不受影响

- **GIVEN** 一个环的回边从 `route` 节点出发（route 出边为控制边）
- **WHEN** 调用 `DeclareWorkflow`
- **THEN** 声明 SHALL 成功（内置 `peer-review` pattern 即此形态）

#### Scenario: 内置编排模式仍可声明

- **GIVEN** 四个内置 pattern（orchestrator-worker / peer-review / hierarchical / bidding）
- **WHEN** 逐个调用 `DeclareWorkflow`
- **THEN** 全部 SHALL 声明成功

### Requirement: DeclareWorkflow 描述暴露循环契约

`DeclareWorkflow` 的工具描述 SHALL 说明有限循环的四条契约，SHALL 至少覆盖：

- 环内必须有产出节点（`subagent` 或 `aggregate(strategy="llm")`），否则环不产生变化、无法退出
- 回边应从 `route` 出发（控制边）；若从其它节点出发则须声明 `required: false`
- `max_routes` 的默认值为 `1`，且只能在节点上逐节点声明
- `max_routes` 的计数是节点级、跨轮累加、不因新一轮循环而重置

描述 SHALL 附**最小正确示例与反例**，SHALL NOT 仅罗列规则。

#### Scenario: 描述含循环契约

- **GIVEN** 模型读取 `DeclareWorkflow` 的工具描述
- **WHEN** 它需要构造一个有限循环
- **THEN** 描述 SHALL 能回答「环里要放什么节点」「回边从哪出发」「`max_routes` 默认几、在哪配」
