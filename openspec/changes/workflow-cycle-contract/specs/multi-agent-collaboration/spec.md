## ADDED Requirements

### Requirement: 循环图形的声明期校验

`DeclareWorkflow` 的 `parse_workflow_spec` SHALL 在声明期校验**有限循环**（route 回边）的**可启动性**，SHALL 在**环内没有任何节点可派发**（即该环永远跑不起来）时拒绝声明，并给出可操作的原因。

**判据（环必须能启动）**：对每个环（强连通分量），若分量内**不存在任何可派发节点**，SHALL 拒绝。某节点「可派发」SHALL 按调度器的真实派发语义静态判定（取最小不动点）：

- 该节点的全部 `required` 数据入边源头可派发（`required: false` 的边不参与门控）；
- **且**满足其一：该节点是 `entry`（显式声明或「无任何入边」）；或它没有控制入边；或它存在一个可派发的控制源 `route`（`route` 出边是控制边）。

拒绝时，错误信息 SHALL 含三要素：**环的成员节点 id**、**缺失项（为什么跑不起来，逐条列出谁在等谁）**、**修法（可照做的具体动作）**，SHALL NOT 只陈述规则。

当被拒的环内存在**同环内的 `required` 数据入边**时，错误信息 SHALL 点出这些边，SHALL 给出「声明 `"required": false`（或把回边改从 `route` 出发——`route` 出边是控制边、不参与门控）」的修法建议。

`DeclareWorkflow` 对本类错误的返回 SHALL 自足：其 `reason` 与 `hint` 合起来 SHALL 足以让模型改对 spec 并重新声明（该返回体不含 `workflow_id`）。

本校验 SHALL 只作用于**声明期入口**；调度器对**运行期**出现的入边互等 SHALL 继续按既有诊断（`blocked` 节点因由「入边互相等待」）如实表达。

#### Scenario: 环永远跑不起来时被声明期拒绝

- **GIVEN** 一个环由 `route` 与 `aggregate(strategy="collect")` 构成，且环内每个节点都在等环内另一个节点（环内存在 `required` 数据边，且没有节点能先跑起来）
- **WHEN** 调用 `DeclareWorkflow`
- **THEN** 声明 SHALL 被拒绝，错误信息 SHALL 指明环成员节点 id、谁在等谁、以及修法
- **AND** SHALL NOT 返回 workflow_id

#### Scenario: 环内有能自启动的节点时正常声明

- **GIVEN** 一个环，其中至少一个节点是 `entry`、且它的 `required` 输入来自环外（因此能先跑起来）
- **WHEN** 调用 `DeclareWorkflow`
- **THEN** 声明 SHALL 成功

#### Scenario: 环内有产出节点但全部互等时仍被拒绝

- **GIVEN** 一个环，环内有 `subagent`，但其中两个节点互相以 `required` 数据边等待（没有任何节点能先跑起来）
- **WHEN** 调用 `DeclareWorkflow`
- **THEN** 声明 SHALL 被拒绝（「环内有产出节点」不构成可启动性）

#### Scenario: 回边从 route 出发（控制边）不受影响

- **GIVEN** 一个环的回边从 `route` 节点出发（`route` 出边为控制边，不参与门控），且环内有能自启动的 `entry`
- **WHEN** 调用 `DeclareWorkflow`
- **THEN** 声明 SHALL 成功（内置 `peer-review` pattern 即此形态）

#### Scenario: 回边声明 required:false 且环能启动时正常声明

- **GIVEN** 一个环的回边显式声明 `"required": false`，且环内有能自启动的节点
- **WHEN** 调用 `DeclareWorkflow`
- **THEN** 声明 SHALL 成功

#### Scenario: 内置编排模式仍可声明

- **GIVEN** 四个内置 pattern（orchestrator-worker / peer-review / hierarchical / bidding）
- **WHEN** 逐个调用 `DeclareWorkflow`
- **THEN** 全部 SHALL 声明成功

### Requirement: DeclareWorkflow 描述暴露循环契约

`DeclareWorkflow` 的工具描述 SHALL 说明有限循环的契约，SHALL 至少覆盖：

- **环里必须有个节点先跑起来，且它不能反过来等环里的节点**，否则环内所有节点互等、一个都跑不起来（声明期会被拒绝）
- 回边应从 `route` 出发（`route` 出边是控制边，不参与门控）；从其它节点出发的回边是数据边、默认门控，须显式声明 `"required": false`
- `max_routes` 的默认值为 `1`，且只能在节点上逐节点声明
- `max_routes` 的计数是节点级、跨轮累加、不因新一轮循环而重置

描述 SHALL 附**最小正确示例与反例**，SHALL NOT 仅罗列规则。

#### Scenario: 描述含循环契约

- **GIVEN** 模型读取 `DeclareWorkflow` 的工具描述
- **WHEN** 它需要构造一个有限循环
- **THEN** 描述 SHALL 能回答「环里的节点要满足什么条件才转得起来」「回边从哪出发」「`max_routes` 默认几、在哪配、怎么计数」
- **AND** 描述 SHALL 给出一个能启用的最小正例与一个会被拒绝的最小反例
