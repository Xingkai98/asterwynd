# multi-agent-collaboration spec delta: foreach 预算截断可见性

## ADDED Requirements

### Requirement: foreach 预算截断可见

当一个 `foreach` 节点的 `max_items == 0`（不静态截断、展开到图级预算耗尽）且其集合被**图级预算**截断（剩余 `max_total_runs` / `max_runs` / `max_nodes` 不足以展开全部项）时，系统 SHALL 在**模型可见的出口**如实报告「声明（集合）总数、实际展开数、被省略数」，并 SHALL 以**成因判别字段**标明该省略源于**预算**（区别于 `max_items` 静态截断），SHALL NOT 静默丢弃而不报告。

报告 SHALL 覆盖以下出口，语义一致：

- **dry run**（`DryRunWorkflow` 的 foreach 条目）：SHALL 报告集合总数、被省略数与成因（与既有「展开数」一并构成「总/展开/省略」三元）。
- **运行期**（`GetWorkflow` 的 foreach 节点投影）：SHALL 暴露预算截断信号（被预算丢弃的项数）与成因。

声明期（`DeclareWorkflow` / `RunWorkflow(spec=...)` 的 `warnings`）SHALL NOT 报告预算截断——预算截断取决于运行期已用预算与集合大小，声明期无从可知。

当 `max_items == 0` 且集合未被预算截断（展开数 == 声明数）时，系统 SHALL NOT 产生任何截断报告（零噪声）。

本 Requirement 的「省略数」SHALL 与「`max_items` 静态截断的省略数」可区分（成因判别字段取值不同），且 SHALL 与既有的「结果投影里 ref 列表被界截断的条数」是不同的量，SHALL NOT 混用同一语义。

#### Scenario: dry run 报告预算截断的三元与成因

- **GIVEN** 一个 `max_items=0` 的 `foreach` 节点，其集合声明 60 项、但图级 `max_runs` 只允许展开 24 项
- **WHEN** 运行 `DryRunWorkflow`
- **THEN** 该节点条目 SHALL 报告集合总数 60、展开数 24、被省略数 36
- **AND** 成因判别字段 SHALL 标为**预算**（区别于 `max_items` 静态截断）
- **AND** 展开数 + 省略数 SHALL == 集合总数

#### Scenario: 运行期报告预算截断

- **GIVEN** 一个 `max_items=0` 的 `foreach` 节点被图级预算截断
- **WHEN** 运行后读取 `GetWorkflow` 的该节点投影
- **THEN** 节点投影 SHALL 暴露被预算丢弃的项数
- **AND** 成因判别字段 SHALL 标为**预算**

#### Scenario: 预算充足时零噪声

- **GIVEN** 一个 `max_items=0` 的 `foreach` 节点，其集合被完整展开（未被预算截断）
- **WHEN** dry run 或运行后读取投影
- **THEN** SHALL NOT 产生任何截断省略数或成因字段

#### Scenario: 成因与静态截断可区分

- **GIVEN** 一个 `max_items>0` 被**静态截断**的 `foreach` 节点，与一个 `max_items=0` 被**预算截断**的 `foreach` 节点
- **WHEN** 分别读取两者投影的成因判别字段
- **THEN** 两者取值 SHALL 不同（前者 `max_items`、后者 `budget`），使模型能区分截断成因

## MODIFIED Requirements

### Requirement: foreach 静态截断可见

当一个 `foreach` 节点的 `items` 集合超过生效的 `max_items`（且 `max_items > 0`）而被**静态截断**时，系统 SHALL 在**模型可见的出口**如实报告「声明（集合）总数、实际展开数、被省略数」，SHALL NOT 静默丢弃而不报告。

报告 SHALL 覆盖以下出口，三者语义一致：

- **声明期**（`DeclareWorkflow` 的返回体、`RunWorkflow(spec=...)` 的 `warnings`）：当 `items` 为声明期即可知的**字面列表**时，SHALL 报告截断；措辞 SHALL **可行动**（指明「哪里发生截断」与「如何展开全部」，如减小 items / 调大 `max_items` / 声明 `max_items: 0`）。
- **dry run**（`DryRunWorkflow` 的 foreach 条目）：SHALL 报告集合总数与被省略数（与既有「展开数」一并构成「总/展开/省略」三元）。
- **运行期**（`GetWorkflow` 的 foreach 节点投影）：SHALL 暴露静态截断信号（被 `max_items` 丢弃的项数）。

当 `items` 由 `source` 驱动（声明期无法得知集合大小）时，声明期 SHALL NOT 猜测或报告其展开数；截断情况 SHALL 由 dry run 与运行期出口报告。

当 `max_items == 0`（不静态截断）时，系统 SHALL NOT 报告**静态**截断。当集合未超过 `max_items`（无截断）时，系统 SHALL NOT 产生任何截断报告（零噪声）。

本 Requirement 的「省略数」（`max_items` 丢弃的项数）SHALL 与既有的「结果投影里 ref 列表被界截断的条数」是不同的量，SHALL NOT 混用同一语义。该「省略数」SHALL 与一个**成因判别字段**配对出现，其取值 SHALL 标明截断源于 `max_items`（静态）——以便与「`max_items=0` 的预算截断」的同类省略数区分（见「foreach 预算截断可见」Requirement）。

`foreach` 的展开集合为空（`source` 未产出、产出解析为空、或上游成功但内容为空）时，系统 SHALL 显式表明该节点展开 0 项**是因为集合为空**，SHALL NOT 只报一个无从归因的零展开数；该信号 SHALL 与「正常解析出非空集合」可区分。

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
- **AND** 成因判别字段 SHALL 标为 `max_items`

#### Scenario: source 驱动在声明期不猜

- **GIVEN** 一个 `source` 驱动的 `foreach` 节点，其集合大小声明期不可知
- **WHEN** 调用 `DeclareWorkflow`
- **THEN** SHALL NOT 报告该节点的展开数或截断数
- **AND** 其截断情况 SHALL 由 dry run 与运行期出口报告

#### Scenario: dry run 对 source 驱动的集合数不具预测性

- **GIVEN** 一个 `source` 驱动的 `foreach` 节点
- **WHEN** `DryRunWorkflow` 报告其集合数
- **THEN** 该数 SHALL 标注为**模拟产物**（dry run 用假 LLM，source 的真实产出未知）
- **AND** 模型 SHALL NOT 能把它读成「真实运行会展开这么多」

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

#### Scenario: 空集合 / source 无产出不静默

- **GIVEN** 一个 `foreach` 节点解析出的集合为空（`source` 未产出、产出解析为空、或上游成功但内容为空）
- **WHEN** dry run 报告该节点，或运行后读取其投影
- **THEN** 系统 SHALL 显式表明该节点展开 0 项**是因为集合为空**，SHALL NOT 只报一个无从归因的 `items_expanded: 0`
- **AND** 该信号 SHALL 与「正常解析出非空集合」可区分
