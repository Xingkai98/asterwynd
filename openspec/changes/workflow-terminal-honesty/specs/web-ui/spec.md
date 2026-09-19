## MODIFIED Requirements

### Requirement: workflow 图级终态如实反映「实际发生了什么」

scheduler SHALL 在图收敛时按**实际执行结果**区分图级终态，判据按以下优先级（先命中先返回）：

1. 存在**任何**节点 `failed` 且**至少一个**节点 `completed` → `completed_with_failures`
2. **至少一个**节点 `completed` 且无节点 `failed` → `completed`
3. **零**节点 `completed` 且存在节点 `failed` → `failed`
4. **零**节点 `completed` 且**零**节点 `failed`（图根本没跑起来——入口互等 / 全部被挡）→ `stalled`

`completed` SHALL NOT 用于「零节点成功」的收敛：图说「完成」而实际什么都没跑，会让用户不去排查，并让外部消费方（`GetWorkflow` / benchmark / CI）把「图根本没跑起来」判为通过。

`stalled` SHALL 表达「图收敛时没有任何节点成功执行」，SHALL NOT 被表达为成功，SHALL NOT 使整图算作 `failed`（二者对用户的行动指引不同：`failed` 指向「哪个节点失败了」，`stalled` 指向「为什么一个都没跑」）。

`completed` 的计数口径 SHALL 为 `status == "completed"` 的**节点**数，SHALL NOT 计入 `skipped`（未选中 ≠ 跑成功）。

`budget_exceeded` / `cancelled` / `graph_recursion_exceeded` SHALL 优先于以上四档（预算停与取消是更强的停止原因），SHALL NOT 被 `stalled` 覆盖。

终态集合的**三个副本**（scheduler 侧 `TERMINAL_STATUSES`、快照补发池 `_SNAPSHOT_TERMINAL_STATUSES`、前端 `workflow_graph.js` 的 `TERMINAL_STATUSES`）SHALL 保持集合相等。任一副本缺失该档，图会被当成 running、永不进入 tab 淘汰池、每次 ws 重连都被补发。

#### Scenario: 有节点失败的图不再报 completed

- **GIVEN** 一张图中某个节点 `failed`，其余节点正常收敛
- **WHEN** workflow 收敛
- **THEN** 图级 status SHALL 为 `completed_with_failures`，SHALL NOT 为 `completed`

#### Scenario: 全部成功的图仍是 completed

- **GIVEN** 一张图所有节点都 `completed`
- **WHEN** workflow 收敛
- **THEN** 图级 status SHALL 为 `completed`

#### Scenario: 零节点成功的图不得报 completed

- **GIVEN** 一张图的所有节点都未成功（如 `route` 回边的入口互等导致全部 `blocked`，或节点全被上游挡住）
- **WHEN** workflow 收敛且没有任何节点 `completed`
- **THEN** 图级 status SHALL NOT 为 `completed`
- **AND** 无节点 `failed` 时 SHALL 为 `stalled`；有节点 `failed` 时 SHALL 为 `failed`

#### Scenario: stalled 与 budget_exceeded 的优先级

- **GIVEN** 一张图既零节点成功、又因预算耗尽而停
- **WHEN** workflow 收敛
- **THEN** 图级 status SHALL 为 `budget_exceeded`（更强的停止原因）

### Requirement: workflow 节点因由如实指向真实成因

前端在节点上 / 详情面板展示的 `reason` SHALL 指向该节点**未执行或未成功的真实成因**，SHALL NOT 用一句无区分度的兜底文案覆盖多种成因。

至少 SHALL 区分以下成因：

- **图级闸门触发**（`max_routes` / `recursion_limit` / `max_nodes` / `max_runs`）：因由 SHALL 含闸门名与被牵连的事实（例：`图级闸门 max_routes 触发（…超过上限 2），本节点未派发`）
- **入边互相等待**（无图级闸门，节点因入边永远不就绪而未派发）：因由 SHALL 说明是「入边互等/永远未就绪」，SHALL NOT 表达为「工作流提前结束」——后者读起来像外部原因、被动受牵连，而真实成因是结构性的

注入的图级诊断文本 SHALL bounded（与 `summary` 同口径截断）。`state.reason` 本体的语义 SHALL NOT 改变（它是 `_envelope` 的字段，被截断的投影只发生在出口层）。

#### Scenario: 图级闸门停下时节点因由说明真因

- **GIVEN** 一张图因 `max_routes` 闸门而停（`diagnostics.reason == "max_routes"`）
- **WHEN** 查看被牵连节点的 `reason`
- **THEN** `reason` SHALL 指明是图级闸门 `max_routes` 导致未派发，SHALL NOT 仅为「workflow ended before the node became ready」

#### Scenario: 无图级闸门的死锁也要说明真因

- **GIVEN** 一张图因 `route` 回边的入口互等而死锁（**无任何图级闸门触发**、`diagnostics` 为空）
- **WHEN** 查看该节点的 `reason`
- **THEN** `reason` SHALL 说明是「入边互相等待、永远未就绪」，SHALL NOT 仅为「workflow ended before the node became ready」

### Requirement: 回边重跑不得清空本次派发的发起者

当 `route` 节点完成并派发下游时，若下游完成触发的子树复位沿**数据边回边**递归走回该 `route` 自身，复位 SHALL NOT 清空该 `route` 刚写入的执行结果（`status` / `targets` / `summary` / `verdict`）。

复位 SHALL 仍然让**回边环上的其它节点**按既有语义重跑（清 `reason` / `error` / `summary` / `finished_at` / `status` / `activations` / `verdict` / `targets`），SHALL NOT 因本豁免而减少任何清理项。

#### Scenario: 数据边回边不清空发起者

- **GIVEN** 一张图含回边 `body → cycle_gate`（`body` 为聚合节点，即该边为**数据边**）
- **WHEN** `cycle_gate` 完成并派发 `body`，`body` 完成触发子树复位
- **THEN** `cycle_gate` 的 `status` SHALL 保持 `completed`，SHALL NOT 被复位成 `pending`
- **AND** `cycle_gate` 的 `targets` SHALL 保持其选中的出口，SHALL NOT 为空
- **AND** 该 `route` 选中的控制边 SHALL 判为 `passed`，SHALL NOT 为 `inactive`
