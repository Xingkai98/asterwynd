## MODIFIED Requirements

### Requirement: workflow 图级终态区分「有失败」

scheduler SHALL 在图收敛时按**实际执行结果**区分图级终态，判据按以下优先级（先命中先返回）：

1. 存在**任何**节点 `failed` 且**至少一个**节点 `completed` → `completed_with_failures`
2. **至少一个**节点 `completed` 且无节点 `failed` → `completed`
3. **零**节点 `completed` 且存在节点 `failed` → `failed`
4. **零**节点 `completed` 且**零**节点 `failed`（图根本没跑起来——入口互等 / 全部被挡）→ `stalled`

`completed` SHALL NOT 用于「零节点成功」的收敛：图说「完成」而实际什么都没跑，会让用户不去排查，并让外部消费方（`GetWorkflow` / benchmark / CI）把「图根本没跑起来」判为通过。

`stalled` SHALL 表达「图收敛时没有任何节点成功执行」。`stalled` 对**所有消费方**的语义 SHALL 为**非成功**：消费方 SHALL NOT 用「`status == "failed"` 才算失败」判定整图结果（该写法会把 `stalled` 悄悄算成成功，等于换一种骗法）；判「通过」的消费方 SHALL 要求 `status == "completed"`。`stalled` SHALL NOT 使整图算作 `failed`（二者对用户的行动指引不同：`failed` 指向「哪个节点失败了」，`stalled` 指向「为什么一个都没跑」）。

`completed` 的计数口径 SHALL 为 `status == "completed"` 的**节点**数，SHALL NOT 计入 `skipped`（未选中 ≠ 跑成功），也 SHALL NOT 与快照的 `completed` 计数（来自 `_unit_counts()['completed_units']`，是 `_logical_units` 口径——`foreach` 容器按展开项数计）混用；二者**不同源**。

`budget_exceeded` / `cancelled` / `graph_recursion_exceeded` SHALL 优先于以上四档（预算停与取消是更强的停止原因），SHALL NOT 被 `stalled` 覆盖。

终态集合的**三个副本** SHALL 保持集合相等：

- scheduler 侧 `_SNAPSHOT_TERMINAL_STATUSES`（`agent/subagent/scheduler.py`）
- 前端 `web/static/workflow.js` 的 `TERMINAL_STATUSES`（`pruneGraphs` 的消费方）
- 前端 `web/static/workflow_graph.js` 的 `isGraphTerminal()`（`graphTabMeta` 的计时判据）

任一副本缺失该档，图会被当成 running、永不进入 tab 淘汰池、每次 ws 重连都被补发。

#### Scenario: 有节点失败的图不再报 completed

- **GIVEN** 一张图中某个节点 `failed`，其余节点正常收敛
- **WHEN** workflow 收敛
- **THEN** 图级 status SHALL 为 `completed_with_failures`，SHALL NOT 为 `completed`
- **AND** 视图头 / tab 徽标 SHALL 明确标示「有失败」，SHALL NOT 只显示成功语义

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

#### Scenario: stalled 的视觉与文案可分辨

- **GIVEN** 一张图收敛为 `stalled`
- **WHEN** 用户在 tab 与图上查看该图
- **THEN** 前端 SHALL 以与 `completed`（绿）和 `budget_exceeded`（橙）均可分辨的编码表达它
- **AND** tab 徽标 SHALL 显示「停滞（无节点完成）」，图例 SHALL 说明「图收敛时没有任何节点成功执行」
- **AND** 该图 SHALL 立即进入终态 tab 淘汰池（三个副本同步），SHALL NOT 被当成 running

### Requirement: workflow 节点异常态语义表达

Workflow 视图 SHALL NOT 仅靠颜色区分节点状态。非成功状态（`failed` / `blocked` / `budget_exceeded` / `cancelled`）SHALL 至少以颜色 + 形状/角标 + 状态词三重编码表达。视图 SHALL 为异常节点提供「为什么是这个状态」的因果说明（如 `blocked` 指明被哪个上游失败挡住、`budget_exceeded` 指明预算维度）。因果说明 SHALL 可在节点上或详情面板中看到，SHALL NOT 仅依赖在移动端不显示的 `<svg:title>`。

节点因由 SHALL 指向该节点**未执行或未成功的真实成因**，SHALL NOT 用一句无区分度的兜底文案覆盖多种成因。至少 SHALL 区分：

- **图级闸门触发**（`max_routes` / `recursion_limit` / `max_nodes` / `max_runs`）：因由 SHALL 含闸门名与被牵连的事实（例：`图级闸门 max_routes 触发（…超过上限 2），本节点未派发`）
- **入边互相等待**（无图级闸门，节点因入边永远不就绪而未派发）：因由 SHALL 说明是「入边互等/永远未就绪」，SHALL NOT 表达为「工作流提前结束」——后者读起来像外部原因、被动受牵连，而真实成因是结构性的

注入的图级诊断文本 SHALL bounded（与 `summary` 同口径截断）。`state.reason` 本体的语义 SHALL NOT 改变（它是 `_envelope` 的字段，被截断的投影只发生在出口层）。

**用户可见性**：上述因由 SHALL 真正出现在用户看到的那句话里。前端因果合成（`explainNode()`）对 `blocked` 节点的取因顺序 SHALL 让**节点自身的具体因由**（含图级闸门信息的 `reason`）优先于泛化的图级停止文案（如「流程因图超限被停止，该节点没来得及执行」）；具体因由缺失时才 SHALL 回退到泛化文案。「后端写了但因前端优先级遮蔽而用户看不到」SHALL NOT 被视为满足本 Requirement。

#### Scenario: 区分 failed 与 blocked

- **GIVEN** 一张图同时存在 `failed`（红）与 `blocked`（黄）节点
- **WHEN** 用户查看该图（含色觉障碍或灰度屏场景）
- **THEN** 两者 SHALL 通过形状/角标或状态词区分，SHALL NOT 仅靠色相
- **AND** `blocked` 节点 SHALL 指明其被上游失败挡住或预算/流程原因未执行

#### Scenario: 预算超限节点的因果

- **GIVEN** 一个 foreach workflow 触发预算超限，图中出现 `failed`/`blocked`/`budget_exceeded` 混合状态
- **WHEN** 用户查看这些异常节点
- **THEN** 每个异常节点 SHALL 显示对应的人话因果（自身失败原因 / 被上游挡住 / 预算超限）
- **AND** 用户 SHALL 能分清「自己失败」「被挡住没跑」「预算停下」三种语义

#### Scenario: 图级闸门停下时节点因由说明真因

- **GIVEN** 一张图因 `max_routes` 闸门而停（`diagnostics.reason == "max_routes"`）
- **WHEN** 用户查看被牵连节点（含详情面板与节点上的因果说明）
- **THEN** 用户看到的因由 SHALL 指明是图级闸门 `max_routes` 导致未派发，SHALL NOT 仅为「workflow ended before the node became ready」或泛化的「流程因图超限被停止」

#### Scenario: 无图级闸门的死锁也要说明真因

- **GIVEN** 一张图因 `route` 回边的入口互等而死锁（**无任何图级闸门触发**、`diagnostics` 为空）
- **WHEN** 用户查看该节点的因由
- **THEN** 因由 SHALL 说明是「入边互相等待、永远未就绪」，SHALL NOT 仅为「workflow ended before the node became ready」

### Requirement: workflow 未选中分支状态（skipped）

scheduler 对「只被 route 控制边门控、且没有任何 route 选中它的未派发节点」SHALL 标记为 `skipped`（未选中），SHALL NOT 标记为 `blocked`（被上游连累）。若节点同时满足「被上游失败/取消/受阻连累」与「未被选中」，SHALL 优先记 `blocked`。`skipped` SHALL 是良性终态（不使整图 failed），SHALL 进独立计数桶。

「是否被选中」的判据 SHALL 同时满足以下两条，缺一不可：

1. **控制激活信号为负**：`_has_control_incoming` 且 `activations <= 0`；
2. **已完成控制源的本次选中出口不含本节点**：对每条控制入边，源头 route 已 `completed` 时，本节点 id SHALL NOT 出现在该 route 的 `targets` 中。

条件 2 是必需的：`activations` 会被子树复位（`_reset_subtree`）清零，而回边场景下 route 可能**已经选中并派发过**本节点，仅凭 `activations <= 0` 会把「选过、也跑过」的节点报成 `route did not select this branch`——**用户读到的是假话**。`targets` 是「选没选它」的权威信号（它受发起者豁免保护，不被回边复位清空）。该判据 SHALL NOT 引入新的记账字段（只读既有 `targets`）。

前端 SHALL 用与 `blocked` 明显区分的编码表达 `skipped`（冷灰蓝 + 虚边框 + `—` 角标 + 状态词），图例 SHALL 说明「未选中：条件判断没走这条分支」。

#### Scenario: 未选中的 route 分支记为 skipped

- **GIVEN** 一个 route 节点命中 `APPROVED` 出口，`DEFAULT` 出口的下游节点未被激活
- **WHEN** workflow 正常完成
- **THEN** `DEFAULT` 下游节点 SHALL 标记为 `skipped`，SHALL NOT 标记为 `blocked`
- **AND** 前端 SHALL 以「未选中」语义（非失败、非受阻）展示该节点

#### Scenario: 控制它的 route 从未运行时不报 skipped

- **GIVEN** 一个节点 T 只被 route R 的控制边门控，而 R 自身因某个**未满足的 required 数据依赖**从未运行（R 最终为 `blocked`）
- **WHEN** workflow 收尾
- **THEN** T SHALL 标记为 `blocked`（真因是「R 没跑」，不是「R 没选它」）
- **AND** SHALL NOT 标记为 `skipped`（否则用户读到「条件没走这条」这句假话）

#### Scenario: 被上游连累优先于未选中

- **GIVEN** 一个节点既未被 route 选中，其数据上游又已 `failed`/`cancelled`/`blocked`
- **WHEN** workflow 收尾
- **THEN** 该节点 SHALL 标记为 `blocked`（反映真实阻塞原因），SHALL NOT 标记为 `skipped`

#### Scenario: 被选中且已执行过的节点不得因复位被报 skipped

- **GIVEN** 一张含数据边回边的图：`route` 节点已 `completed` 且其 `targets` 含节点 T，T 因此被派发并执行过；随后子树复位把 T 的 `activations` 清零
- **WHEN** workflow 收尾
- **THEN** T SHALL NOT 被标记为 `skipped`
- **AND** T 的因由 SHALL NOT 为 `route did not select this branch`（route 确实选中了它）

## ADDED Requirements

### Requirement: 回边重跑不得清空本次派发的发起者

当 `route` 节点完成并派发下游时，若下游完成触发的子树复位沿**数据边回边**递归走回该 `route` 自身，复位 SHALL NOT 清空该 `route` 刚写入的执行结果（`status` / `targets` / `summary` / `verdict`）。

发起者豁免 SHALL 只豁免**本次派发链的发起者**这一个节点，SHALL NOT 停止复位的传播——回边环上的其它节点 SHALL 仍按既有语义重跑。

复位 SHALL 仍然让环上的其它节点按既有语义重跑（清 `reason` / `error` / `summary` / `finished_at` / `status` / `activations` / `verdict` / `targets`），SHALL NOT 因本豁免而减少任何清理项。

#### Scenario: 数据边回边不清空发起者

- **GIVEN** 一张图含回边 `body → cycle_gate`（`body` 为聚合节点，即该边为**数据边**）
- **WHEN** `cycle_gate` 完成并派发 `body`，`body` 完成触发子树复位
- **THEN** `cycle_gate` 的 `status` SHALL 保持 `completed`，SHALL NOT 被复位成 `pending`
- **AND** `cycle_gate` 的 `targets` SHALL 保持其选中的出口，SHALL NOT 为空
- **AND** 该 `route` 选中的控制边 SHALL 判为 `passed`，SHALL NOT 为 `inactive`
