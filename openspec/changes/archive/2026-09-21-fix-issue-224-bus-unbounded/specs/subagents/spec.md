# Spec Delta: subagents — message bus 出口 SHALL bounded

## ADDED Requirements

### Requirement: message bus 模型面出口有界

编排 message bus（`agent/subagent/bus.py`）返回给**模型面**的消息 SHALL 在**单条**与**总量**两个维度上均 bounded：单条 `summary` SHALL 不超过一个**固定**的单条内容上限，返回的消息**总量** SHALL 不超过一个固定的输出上限。单条上限 SHALL 与模型面其它出口的单条内容上限（`TRANSCRIPT_ITEM_LIMIT`）**同值**，SHALL NOT 另立一套数字。

**总量**维是本 Requirement 的核心，SHALL NOT 只界住单条：`read()` 的 `max_tokens` / `limit` 两个参数由调用方（被检视的模型）给出，若不加钳制，单条截断后总量仍随调用方参数无限增长（实测 `max_tokens=10^9` 时返回 100 条 / 3,000,000 字符）——「界不可被被检视对象影响」。

单条上限 SHALL **独立于调用方传入的 `max_tokens`**：发布侧 `max_tokens` 是 summarize 的阈值，若它可无上界地高于单条上限，summarize 分支就不会触发、原文直入 bus。故发布侧阈值 SHALL 被钳到与单条上限等价的值，且 summarize 闸门 SHALL 在阈值**等于**上限时即触发（`>=`），使 summarize SHALL 必然触发（`estimate_tokens` 向下取整，严格大于会留缝）。

**发布侧的界由出口投影保证，不由阈值保证**：`_summarize` 的 LLM 分支是 advisory、**不保证**产出 ≤ 上限（见 `agent/context/summarizer.py`：「not a hard guarantee」，预算只拼进 prompt）。因此发布侧的**模型面输出**（`PublishBusMessage` 的回包，即第 5 条出口）SHALL 与消费侧同走出口投影——被截断的 SHALL 不超过单条上限并携带 `summary_truncated`。SHALL NOT 声称「阈值钳制使发布侧严格不超过上限」这种对 LLM 分支不成立的断言。

**队列不因出口投影而改变**：`publish()` 入队的内容 SHALL 保留原样（含 LLM 摘要超预算的情形）；bounded 化只发生在出口投影。

被截断的单条消息 SHALL 携带布尔标志（`summary_truncated`），SHALL NOT 依赖调用方用长度比较自行推断；被截断消息的 `token_count` SHALL 与截断后的文本一致（SHALL NOT 继续报告全文的记账值）。

截断 SHALL NOT 修改队列中保存的消息本身：bus 的会话恢复视图（`compact_summary()`）与 checkpoint 快照 SHALL 仍看到未截断的原文。

bus 消息**不落盘**，因此截断 SHALL NOT 声称「全文可从某个引用取得」——没有权威件可指时，任何 ref 字样都是一句假话。截断只如实回流标志本身。

#### Scenario: ReadBus 单条超长内容被截断

- **GIVEN** bus 中存在一条 `summary` 为 30,000 字的子 agent 消息
- **WHEN** 父 agent 调用 `ReadBus`
- **THEN** 返回的该条 `summary` SHALL 不超过固定的单条内容上限
- **AND** 该条 SHALL 携带 `summary_truncated` 为 `true`

#### Scenario: ReadBus 总量不随调用方参数放大

- **GIVEN** bus 满载 100 条、每条 30,000 字
- **WHEN** 父 agent 调用 `ReadBus` 并传入一个极大的 `max_tokens`（例如 10^9）与极大的 `limit`
- **THEN** 返回的消息条数 SHALL 不超过固定的条数上限
- **AND** 返回的总字符量 SHALL 不超过与快照出口同界的固定上限
- **AND** 结果 SHALL NOT 随传入参数增大而无限增大

#### Scenario: 单条超窗时仍返回最新一条（截断后）

- **GIVEN** bus 中最新的那条消息其体量**单独就超过**消费侧 token 窗口
- **WHEN** 父 agent 以该窗口调用 `ReadBus`
- **THEN** 系统 SHALL 仍返回这条最新的消息（消费者 SHALL NOT 失明）
- **AND** 返回的 `summary` SHALL 不超过固定的单条内容上限
- **AND** 该条 SHALL 携带 `summary_truncated` 为 `true`

#### Scenario: 截断不改动队列中的原文

- **GIVEN** bus 中存在一条超长消息
- **WHEN** 父 agent 经 `ReadBus` 读到该条的截断件
- **THEN** bus 队列中保存的该条 `summary` SHALL 仍为全文
- **AND** `compact_summary()` 的输出 SHALL NOT 因该次读取而变短

#### Scenario: 截断后 token_count 与文本一致

- **GIVEN** 一条 30,000 字的 bus 消息被截断后返回
- **WHEN** 调用方读取该条的 `token_count`
- **THEN** 该值 SHALL 与截断后的文本一致
- **AND** SHALL NOT 等于全文的记账值

#### Scenario: 截断上限与其它模型面出口同值

- **GIVEN** 同一份子 agent 撰写的文本经 bus 出口与经 run envelope 出口返回
- **WHEN** 比较两处对单条内容的上限
- **THEN** 两个上限 SHALL 相等
- **AND** 该相等关系 SHALL 有测试机械锁定（SHALL NOT 只靠注释约定）

#### Scenario: 发布侧阈值不放大单条出口

- **GIVEN** 父 agent 调 `PublishBusMessage` 时传入一个远超单条上限的 `max_tokens`（例如 10^9）
- **WHEN** 随后通过 `ReadBus` 读回该消息
- **THEN** 读回的 `summary` SHALL 仍不超过固定的单条内容上限
- **AND** 结果 SHALL NOT 随传入 `max_tokens` 的取值变化

#### Scenario: 发布回包不因摘要超预算而越界

- **GIVEN** summarize 的 LLM 分支返回了一个**超过**单条上限的摘要（advisory 预算，允许发生）
- **WHEN** `PublishBusMessage` 返回其回包
- **THEN** 回包的 `summary` SHALL 不超过固定的单条内容上限
- **AND** 该条 SHALL 携带 `summary_truncated` 为 `true`
- **AND** bus 队列中保存的该条 SHALL 仍保留摘要的完整文本

#### Scenario: 截断标记不指向不存在的引用

- **GIVEN** 一条因超长而被截断的 bus 消息
- **WHEN** 该消息经模型面出口返回
- **THEN** 截断相关的文本 SHALL NOT 声称全文可从某个引用（`result_ref` / `summary_ref`）取得
- **AND** SHALL 仍然如实表达「该条已被截断」
