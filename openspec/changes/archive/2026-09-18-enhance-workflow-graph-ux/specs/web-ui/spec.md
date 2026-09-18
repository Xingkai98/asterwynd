# web-ui spec delta: Workflow 流程图可视化体验增强

## MODIFIED Requirements

### Requirement: workflow 图跨端适配

Workflow 视图 SHALL 在桌面（>720px）显示横向 DAG（左→右）、在手机/平板（≤720px）显示纵向 DAG（上→下）。SHALL 支持 pinch 缩放 + pan 平移。50–200 节点 SHALL 折叠 foreach/自动插层（折叠组聚合状态）。

折叠组的展开/收起 SHALL 由**节点详情面板**承担（不再由「点击节点」承担，也不在节点上单独画控件）：点击节点 SHALL 一律打开节点详情面板（见「workflow 节点详情面板」），面板 SHALL 为折叠组组长提供「展开成员 / 收起成员」动作。`max_nodes` 超限 SHALL 表现为「声明期被拒（无图）/ 运行期 `status == "graph_recursion_exceeded"` + `diagnostics`」两种，前端 SHALL NOT 依赖 `nodes.length > 200` 判断超限，也不存在「渲染一张 >200 节点的图再截断」的路径；超限时 SHALL 仍然绘制图并在画布上方叠加告警条（告警条 SHALL 含 `diagnostics.current_nodes` 与 `steps`）。

分层布局、状态映射与折叠归类 SHALL 与 DOM 解耦为可单独测试的纯函数。

#### Scenario: 手机端纵向布局

- **GIVEN** 一个 ≤720px 视口的移动端
- **WHEN** 渲染 workflow 图
- **THEN** SHALL 显示纵向 DAG（根在上、叶在下）
- **AND** SHALL 支持 pinch 缩放与 pan 平移

#### Scenario: 折叠组展开与节点点击语义分离

- **GIVEN** 一个折叠的 foreach 容器节点
- **WHEN** 用户点击该节点
- **THEN** SHALL 打开节点详情面板
- **AND** SHALL NOT 因此展开/收起该折叠组（展开由详情面板中的动作承担）

#### Scenario: 图超限时仍可见

- **GIVEN** 一张运行期超限的图（`status == "graph_recursion_exceeded"`）
- **WHEN** 前端渲染该快照
- **THEN** SHALL 绘制图并在画布上方显示告警条
- **AND** 告警条 SHALL 给出超限原因、超限时仍就绪的节点与已跑 superstep 数

### Requirement: workflow 图快照

scheduler SHALL 提供 `workflow_graph_snapshot()`，返回完整运行期图（nodes + edges + 每节点 status + 每边 status）。该快照 SHALL 基于运行期 `ExecutionPlan`（含自动插层 + foreach 展开），SHALL NOT 改变现有 `_envelope`/`parent_envelope` 的父 Agent 数据契约。快照 SHALL 显式挑选字段（节点不含 `subagent_ids`/`slots`/`raw`，边只含结构字段），SHALL NOT 复用 `NodeState.to_dict()` 直出或整包复用 `_envelope`。

快照 SHALL 额外包含供可读性展示的加法字段：节点 `reason`（**在投影层**截断到与 `summary` 同口径的 bounded 上限；`state.reason` 本体 SHALL NOT 改变，它是 `_envelope` 的字段）、节点 `task`、图级 `started_at`/`finished_at`（**无值统一为 `null`**——构造期哨兵 `0.0` SHALL NOT 直出，否则前端会渲染成 epoch 0）、图级 `budget`、`kind == "foreach"` 节点的 `item_states`/`items_running`/`items_completed`/`items_failed`。既有字段的语义 SHALL NOT 改变。

节点状态 SHALL 支持「**已派发但仍在等执行 slot**」的投影态 `queued`：该值 SHALL 只在图投影层按 run record 的 `status` 派生，SHALL NOT 写入 `NodeState.status`（后者参与调度器收敛判断）。

#### Scenario: 快照包含边与状态

- **GIVEN** 一个运行中的 workflow
- **WHEN** 调用 `workflow_graph_snapshot()`
- **THEN** 返回 SHALL 含 nodes（每节点 status）
- **AND** SHALL 含 edges（每边 status）

#### Scenario: 快照加法字段 bounded

- **GIVEN** 一个节点带超长错误文本的 workflow
- **WHEN** 调用 `workflow_graph_snapshot()`
- **THEN** 节点 `reason` SHALL 被截断到 bounded 上限
- **AND** 快照 SHALL NOT 出现 `subagent_ids`/`slots`/`raw` 等随规模膨胀的字段
- **AND** `_envelope`/`parent_envelope` 契约 SHALL NOT 漂移

## ADDED Requirements

### Requirement: workflow 图图例

Workflow 视图 SHALL 提供常驻可折叠的图例（legend），说明节点类型（`S` subagent / `F` foreach / `R` route / `A` aggregate）、节点状态八档、边状态五档与 channel 线型语义。图例 SHALL 在桌面（>720px）默认展开、在手机（≤720px）默认折叠。图例每条目 SHALL 包含人话解释（而非仅状态词）。图例内容 SHALL 与状态词表（颜色/线型/代号/状态名）同源生成。

#### Scenario: 手机端图例可折叠且可见

- **GIVEN** 一个 ≤720px 视口的移动端打开 Workflow 视图
- **WHEN** 图渲染完成
- **THEN** SHALL 显示一行折叠态图例入口（`图例 ▾`）
- **AND** 点击后 SHALL 展开显示节点类型、状态、边状态的完整图例

#### Scenario: 图例与状态词表同源

- **GIVEN** 状态词表（`NODE_COLORS`/`NODE_LABELS`/`EDGE_STYLES`/`KIND_GLYPHS`）发生变化
- **WHEN** 重建图例内容
- **THEN** 图例条目 SHALL 自动反映新词表，SHALL NOT 出现图例与图不一致

### Requirement: workflow 未选中分支状态（skipped）

scheduler 对「只被 route 控制边门控、且没有任何 route 选中它的未派发节点」SHALL 标记为 `skipped`（未选中），SHALL NOT 标记为 `blocked`（被上游连累）。判据 SHALL 复用既有控制激活信号（`_has_control_incoming` 且 `activations <= 0`），SHALL NOT 引入新的记账。若节点同时满足「被上游失败/取消/受阻连累」与「未被选中」，SHALL 优先记 `blocked`。`skipped` SHALL 是良性终态（不使整图 failed），SHALL 进独立计数桶。

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

> **验收构造说明（审阅员 B）**：上面的 GIVEN 在真实调度器里**不能只靠「数据上游 failed」构造**——`failed`/`cancelled` 都是终态，`_data_deps_satisfied` 随即满足、节点会被**派发**（不是停在 pending）。要构造该场景必须**再叠一个未满足的 required 依赖**（例如另一条 required 入边的上游仍是 `pending`/`blocked`）。测试与实现都按这个构造写。

### Requirement: route 数据入边的消费记账

scheduler SHALL 在 route 节点读取数据上游产出（`_route_verdict`）处记录该数据入边已被消费，使该边的状态 SHALL 判定为 `passed`（而非 `inactive`）。记账 SHALL 与既有 per-edge 记账同构（旁加，`_mark_consumed` 本体不改），SHALL NOT 改变 `_consumed_run_ids` 基数或 C5 的 `useful_runs`/`redundancy` 口径。

#### Scenario: route 的上游数据边显示为已消费

- **GIVEN** 一个 route 节点读取了已完成上游节点的产出并据此判定
- **WHEN** 渲染该 route 的数据入边
- **THEN** 该边 SHALL 判定为 `passed`，SHALL NOT 落到 `inactive` 兜底

### Requirement: workflow 图级终态区分「有失败」

scheduler SHALL 在图收敛时区分两种成功收敛的图级终态：存在任何节点 `failed` 时 SHALL 为 `completed_with_failures`，无节点失败时才 SHALL 为 `completed`。`budget_exceeded` / `cancelled` / `graph_recursion_exceeded` SHALL 优先于二者（预算停与取消是更强的停止原因）。`completed_with_failures` SHALL NOT 使整图算作失败，但前端 SHALL 让用户一眼看到「有节点未成功」。

#### Scenario: 有节点失败的图不再报 completed

- **GIVEN** 一张图中某个节点 `failed`，其余节点正常收敛
- **WHEN** workflow 收敛
- **THEN** 图级 status SHALL 为 `completed_with_failures`，SHALL NOT 为 `completed`
- **AND** 视图头 / tab 徽标 SHALL 明确标示「有失败」，SHALL NOT 只显示成功语义

#### Scenario: 全部成功的图仍是 completed

- **GIVEN** 一张图所有节点都 `completed`
- **WHEN** workflow 收敛
- **THEN** 图级 status SHALL 为 `completed`

### Requirement: workflow 节点异常态语义表达

Workflow 视图 SHALL NOT 仅靠颜色区分节点状态。非成功状态（`failed` / `blocked` / `budget_exceeded` / `cancelled`）SHALL 至少以颜色 + 形状/角标 + 状态词三重编码表达。视图 SHALL 为异常节点提供「为什么是这个状态」的因果说明（如 `blocked` 指明被哪个上游失败挡住、`budget_exceeded` 指明预算维度）。因果说明 SHALL 可在节点上或详情面板中看到，SHALL NOT 仅依赖在移动端不显示的 `<svg:title>`。

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

### Requirement: workflow 节点详情面板

Workflow 视图 SHALL 支持点击任意节点打开节点详情面板。详情 SHALL 包含该节点的 id、kind、status、因果说明、起止/耗时、runs 次数、task 与产出 summary。面板 SHALL 在桌面（>720px）以右侧抽屉、在手机（≤720px）以底部抽屉呈现（同一 DOM，按断点切换）。点击节点的语义 SHALL 与折叠组展开/收起分离（见「workflow 图跨端适配」的 MODIFIED 口径）。

#### Scenario: 点节点打开详情

- **GIVEN** 一张已渲染的 workflow 图
- **WHEN** 用户点击任意非容器节点
- **THEN** SHALL 打开该节点的详情面板并显示其状态、因果说明与元信息
- **AND** 桌面端 SHALL 从右侧滑入、手机端 SHALL 从底部滑入

### Requirement: workflow 节点 transcript 只读接口

Web 服务 SHALL 提供只读接口 `GET /api/sessions/{session_id}/workflows/{workflow_id}/nodes/{node_id}/transcript`，复用 `SubAgentManager.inspect_transcript()`，按节点的**对话形态**返回三态之一：`single`（1 个对应 subagent：`subagent` / `aggregate(strategy="llm")` / 自动插层聚合）、`candidates`（foreach 容器，N 个展开项）、`none`（`route` / `aggregate(strategy="collect")` / 从未派发的节点——这些节点不产生 run）。接口 SHALL bounded（条数上限 + 单条内容截断 + 候选集分页上限），SHALL 默认排除工具结果。接口 SHALL NOT 调用 LLM、写盘或改变 workflow 执行状态。

#### Scenario: 读取单 subagent 节点的 transcript

- **GIVEN** 一个已执行、恰好对应 1 个 subagent 的节点（普通节点 / LLM 聚合 / 自动插层聚合）
- **WHEN** 请求该节点 transcript
- **THEN** SHALL 返回 `kind: "single"` 与该节点的 messages（bounded）与 `truncated` 标志
- **AND** SHALL NOT 触发任何 LLM 调用或状态变更

#### Scenario: foreach 容器返回候选集

- **GIVEN** 一个 foreach 容器节点（N 个展开项各自独立 subagent，且 N>1）
- **WHEN** 请求该节点 transcript
- **THEN** SHALL 返回 `kind: "candidates"` 与至多 `limit` 条候选（每条含 `subagent_id`/`run_id`/`status`/`summary`），附 `total`/`has_more`
- **AND** 用户点某一项后 SHALL 能按该项的 `subagent_id` 取到该项自己的 transcript，SHALL NOT 混入同容器其它项的 messages

#### Scenario: 不产生 run 的节点优雅降级

- **GIVEN** 一个 `route` 节点、一个 `strategy="collect"` 的聚合节点，或一个从未派发的 `pending`/`blocked` 节点
- **WHEN** 请求该节点 transcript
- **THEN** SHALL 返回 `kind: "none"` 与结构化说明（route 附命中标签与选中出口、collect 附合并产出、未派发节点说明未执行）
- **AND** SHALL NOT 编造 transcript

前端 SHALL 在切到「对话」tab 时才请求（懒加载），SHALL 按**定死的刷新节律**按需重取（节点已到终态或用户暂停后 SHALL NOT 再重取），且对话区 SHALL 提供暂停/继续实时更新的动作。transcript 的渲染 SHALL 按行聚簇做 UI 虚拟化（SHALL NOT 按行建 DOM）。

#### Scenario: 对话内容的刷新与暂停

- **GIVEN** 一个仍在运行的节点，用户已切到该节点的「对话」tab
- **WHEN** 达到刷新节律
- **THEN** SHALL 重取该节点的 transcript
- **AND** 用户点「暂停实时更新」后 SHALL NOT 再重取（节点到终态后同样不再重取）

### Requirement: workflow 多图与 foreach 可读性

Workflow 视图的多图 tab SHALL 显示可区分不同运行的元信息（序号 + 起止/相对时间 + 耗时 + 完成计数），SHALL 将运行中的图排在前面。foreach 容器节点 SHALL 常显并行计数（`完成 M/N`，缺失信息时退化为项数）并表达并行项的状态分布。图的统计行 SHALL 如实反映实际绘制的边数，SHALL 在存在同对节点并行边或折叠合并时给出可解释的口径差异。

#### Scenario: 区分多次运行

- **GIVEN** 同一 session 内模型启动了 3 次 workflow
- **WHEN** 用户查看多图 tab
- **THEN** 每个 tab SHALL 显示序号、时间与完成计数等可区分信息
- **AND** 用户 SHALL 能判断「第几次 run」「何时起」「结果差异」

#### Scenario: foreach 并行可见

- **GIVEN** 一个 foreach 容器节点（含 N 个并行项）
- **WHEN** 渲染该节点（无论是否折叠）
- **THEN** SHALL 常显「完成 M/N」计数并表达项的状态分布

#### Scenario: 边统计与可见线条一致

- **GIVEN** 一个图有 11 条边，其中若干为同一对节点的并行边 / 被折叠合并
- **WHEN** 渲染统计行
- **THEN** SHALL 显示实际绘制的路径数
- **AND** 存在差异时 SHALL 给出可解释口径（如原始边数）
