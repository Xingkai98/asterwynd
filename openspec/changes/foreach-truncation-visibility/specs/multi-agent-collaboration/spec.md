# multi-agent-collaboration spec delta: foreach 截断可见性

## ADDED Requirements

### Requirement: foreach 静态截断可见

当一个 `foreach` 节点的 `items` 集合超过生效的 `max_items`（且 `max_items > 0`）而被**静态截断**时，系统 SHALL 在**模型可见的出口**如实报告「声明（集合）总数、实际展开数、被省略数」，SHALL NOT 静默丢弃而不报告。

报告 SHALL 覆盖以下出口，三者语义一致：

- **声明期**（`DeclareWorkflow` 的返回体、`RunWorkflow(spec=...)` 的 `warnings`）：当 `items` 为声明期即可知的**字面列表**时，SHALL 报告截断；措辞 SHALL **可行动**（指明「哪里发生截断」与「如何展开全部」，如减小 items / 调大 `max_items` / 声明 `max_items: 0`）。
- **dry run**（`DryRunWorkflow` 的 foreach 条目）：SHALL 报告集合总数与被省略数（与既有「展开数」一并构成「总/展开/省略」三元）。
- **运行期**（`GetWorkflow` 的 foreach 节点投影）：SHALL 暴露静态截断信号（被 `max_items` 丢弃的项数）。

当 `items` 由 `source` 驱动（声明期无法得知集合大小）时，声明期 SHALL NOT 猜测或报告其展开数；截断情况 SHALL 由 dry run 与运行期出口报告。

当 `max_items == 0`（不静态截断）时，系统 SHALL NOT 报告静态截断。当集合未超过 `max_items`（无截断）时，系统 SHALL NOT 产生任何截断报告（零噪声）。

本 Requirement 的「省略数」（`max_items` 丢弃的项数）SHALL 与既有的「结果投影里 ref 列表被界截断的条数」是不同的量，SHALL NOT 混用同一语义。

#### Scenario: 声明期报告字面 items 的截断

- **GIVEN** 一个 `foreach` 节点声明了 60 个字面 `items`，且未显式声明 `max_items`（默认为 20）
- **WHEN** 调用 `DeclareWorkflow`（或 `RunWorkflow(spec=...)`）
- **THEN** 返回体的 `warnings` SHALL 含一条报告「声明 60、仅前 20 会运行」的提示
- **AND** 提示 SHALL 可行动（给出展开全部的途径）

#### Scenario: dry run 报告集合总数与省略数

- **GIVEN** 一个将被静态截断的 `foreach` 节点
- **WHEN** 运行 `DryRunWorkflow`
- **THEN** 该节点条目 SHALL 报告集合总数与被省略数
- **AND** SHALL 与既有的展开数一致（展开数 + 省略数 == 集合总数）

#### Scenario: source 驱动在声明期不猜

- **GIVEN** 一个 `source` 驱动的 `foreach` 节点，其集合大小声明期不可知
- **WHEN** 调用 `DeclareWorkflow`
- **THEN** SHALL NOT 报告该节点的展开数或截断数
- **AND** 其截断情况 SHALL 由 dry run 与运行期出口报告

#### Scenario: 无截断时不产生报告

- **GIVEN** 一个 `foreach` 节点的集合大小不超过 `max_items`
- **WHEN** 声明 / dry run / 运行
- **THEN** SHALL NOT 产生任何静态截断警告或字段

#### Scenario: max_items=0 不报静态截断

- **GIVEN** 一个 `foreach` 节点声明 `max_items: 0`
- **WHEN** 声明 / dry run / 运行
- **THEN** SHALL NOT 报告静态截断（不静态截断，SHALL NOT 误报）

#### Scenario: 省略数与 ref 列表界不混

- **GIVEN** 一个 `foreach` 节点展开了全部集合项（未被 `max_items` 截断），但其结果投影的 ref 列表被界截断
- **WHEN** 读取该节点的投影
- **THEN** 其「静态截断省略数」SHALL 为 0
- **AND** 既有的「ref 列表被截条数」SHALL 独立报告，两者 SHALL NOT 使用同一语义
