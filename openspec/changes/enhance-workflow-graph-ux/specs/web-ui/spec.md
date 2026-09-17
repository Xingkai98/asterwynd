# web-ui spec delta: Workflow 流程图可视化体验增强

## MODIFIED Requirements

### Requirement: workflow 图跨端适配

Workflow 视图 SHALL 在桌面（>720px）显示横向 DAG（左→右）、在手机/平板（≤720px）显示纵向 DAG（上→下）。SHALL 支持 pinch 缩放 + pan 平移。50–200 节点 SHALL 折叠 foreach/自动插层（折叠组聚合状态）。

折叠组的展开/收起 SHALL 由节点上的**独立控件**承担（不再由「点击节点」承担）；点击节点 SHALL 打开节点详情面板（见「workflow 节点详情面板」）。`max_nodes` 超限 SHALL 表现为「声明期被拒（无图）/ 运行期 `status == "graph_recursion_exceeded"` + `diagnostics`」两种，前端 SHALL NOT 依赖 `nodes.length > 200` 判断超限，也不存在「渲染一张 >200 节点的图再截断」的路径。

分层布局、状态映射与折叠归类 SHALL 与 DOM 解耦为可单独测试的纯函数。

#### Scenario: 手机端纵向布局

- **GIVEN** 一个 ≤720px 视口的移动端
- **WHEN** 渲染 workflow 图
- **THEN** SHALL 显示纵向 DAG（根在上、叶在下）
- **AND** SHALL 支持 pinch 缩放与 pan 平移

#### Scenario: 折叠组展开与节点点击语义分离

- **GIVEN** 一个折叠的 foreach 容器节点
- **WHEN** 用户点击该节点（而非其展开控件）
- **THEN** SHALL 打开节点详情面板
- **AND** SHALL NOT 因此展开/收起该折叠组（展开由独立控件承担）

### Requirement: workflow 图快照

scheduler SHALL 提供 `workflow_graph_snapshot()`，返回完整运行期图（nodes + edges + 每节点 status + 每边 status）。该快照 SHALL 基于运行期 `ExecutionPlan`（含自动插层 + foreach 展开），SHALL NOT 改变现有 `_envelope`/`parent_envelope` 的父 Agent 数据契约。快照 SHALL 显式挑选字段（节点不含 `subagent_ids`/`slots`/`raw`，边只含结构字段），SHALL NOT 复用 `NodeState.to_dict()` 直出或整包复用 `_envelope`。

快照 SHALL 额外包含供可读性展示的加法字段：节点 `reason`（截断到与 `summary` 同口径的 bounded 上限）、图级 `started_at`/`finished_at`、foreach/自动插层节点的 `items_completed`/`items_failed`。既有字段的语义 SHALL NOT 改变。

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

Workflow 视图 SHALL 提供常驻可折叠的图例（legend），说明节点类型（`S` subagent / `F` foreach / `R` route / `A` aggregate）、节点状态七档、边状态五档与 channel 线型语义。图例 SHALL 在桌面（>720px）默认展开、在手机（≤720px）默认折叠。图例每条目 SHALL 包含人话解释（而非仅状态词）。图例内容 SHALL 与状态词表（颜色/线型/代号/状态名）同源生成。

#### Scenario: 手机端图例可折叠且可见

- **GIVEN** 一个 ≤720px 视口的移动端打开 Workflow 视图
- **WHEN** 图渲染完成
- **THEN** SHALL 显示一行折叠态图例入口（`图例 ▾`）
- **AND** 点击后 SHALL 展开显示节点类型、状态、边状态的完整图例

#### Scenario: 图例与状态词表同源

- **GIVEN** 状态词表（`NODE_COLORS`/`NODE_LABELS`/`EDGE_STYLES`/`KIND_GLYPHS`）发生变化
- **WHEN** 重建图例内容
- **THEN** 图例条目 SHALL 自动反映新词表，SHALL NOT 出现图例与图不一致

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

Web 服务 SHALL 提供只读接口 `GET /api/sessions/{session_id}/workflows/{workflow_id}/nodes/{node_id}/transcript`，复用 `SubAgentManager.inspect_transcript()`，返回该节点的运行 transcript。接口 SHALL bounded（条数上限 + 单条内容截断），SHALL 默认排除工具结果。接口 SHALL NOT 调用 LLM、写盘或改变 workflow 执行状态。

#### Scenario: 读取已执行节点的 transcript

- **GIVEN** 一个 workflow 中已执行的节点（存在对应 subagent）
- **WHEN** 请求该节点 transcript
- **THEN** SHALL 返回该节点的 messages（bounded）与 `truncated` 标志
- **AND** SHALL NOT 触发任何 LLM 调用或状态变更

#### Scenario: 无单一 transcript 的节点优雅降级

- **GIVEN** 一个 foreach 容器节点（展开项各自独立）或一个从未派发的 `pending`/`blocked` 节点
- **WHEN** 请求该节点 transcript
- **THEN** 服务端 SHALL 返回结构化说明（容器附项数 / 未派发节点 `subagent_id: null`）
- **AND** SHALL NOT 编造 transcript

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
