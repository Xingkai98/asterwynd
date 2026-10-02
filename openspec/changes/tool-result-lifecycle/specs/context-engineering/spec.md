# context-engineering spec delta: 工具结果生命周期

## ADDED Requirements

### Requirement: 工具结果全文的单受管持有与释放

系统的上下文管线 SHALL 保证：任何持有工具结果全文的常驻池（对话消息 `messages`、执行账本 `trace`、运行结果 `tool_calls_made`）都 SHALL 有界，SHALL NOT 存在「只增不减且无上限」的工具结果全文副本。

当一个池把工具结果的正文替换为有界预览（或随生命周期释放）时，SHALL 使该全文**可被垃圾回收**——SHALL NOT 出现「把一处引用换成预览，而另一池仍持同一全文对象」从而使全文继续常驻内存的情况。

对话消息中的替换 SHALL 保证模型仍能获取全文：被替换的工具结果 SHALL 可**按引用（ref）完整、无损地回读**（区别于压缩摘要的有损）。SHALL NOT 仅以 ref 替代正文却使该 ref 不可解析——若落盘未成功，标记 SHALL 如实反映「全文不可回读」，SHALL NOT 声称存在可读的 ref。

账本类池（`trace`、`tool_calls_made`）的正文在超阈时 SHALL 以有界预览驻留，且 SHALL 保留其分析所依赖的结构字段（工具名、状态、错误类型、参数），SHALL NOT 因有界化而丢失这些字段。

替换 SHALL 对模型与观察者可见：被替换处 SHALL 带有可识别标记使模型知悉曾有更完整的内容及其获取方式；有界化的发生 SHALL 可被计数、可被观察，SHALL NOT 静默丢弃。

工具结果在消息中的替换 SHALL NOT 破坏 tool-call 消息链的合法性（`tool_call_id` 等结构 SHALL NOT 因此改变）。

回读入口 SHALL 对**任意 agent** 可用（含根 agent 与因深度到限而被撤除 spawn 工具的子 agent），SHALL NOT 仅限 workflow 身份。

#### Scenario: 陈旧的工具结果被替换为预览与引用

- **GIVEN** 一次对话中较早轮次产生了一个体积很大的工具结果，其已被模型消费过且滑出近期窗口
- **WHEN** 上下文管线处理
- **THEN** 该工具结果在 `messages` 中的正文 SHALL 被替换为有界预览 + ref
- **AND** 其 `tool_call_id` SHALL 保持不变，tool-call 链仍合法

#### Scenario: 当轮工具结果不被替换

- **GIVEN** 模型在本轮刚产生一个工具结果并将在本轮或下一轮使用
- **WHEN** 上下文管线处理
- **THEN** 该工具结果的正文 SHALL 保留全文
- **AND** SHALL NOT 在模型消费之前被替换为预览

#### Scenario: 替换后全文可被回收

- **GIVEN** 同一工具结果全文被 `messages` 与账本池（`trace` / `tool_calls_made`）共同持有
- **WHEN** 所有持有者都已把正文替换为有界预览
- **THEN** 原工具结果全文 SHALL 不再被任何池强引用（可被垃圾回收）
- **AND** SHALL NOT 出现「仅替换了一处、全文仍被另一处持有」的情形

#### Scenario: 账本池有界但保留分析字段

- **GIVEN** 一个体积很大的工具结果被写入 `trace` / `tool_calls_made`
- **WHEN** 其正文超过阈值
- **THEN** 正文 SHALL 以有界预览驻留
- **AND** 工具名、状态、错误类型、参数等分析字段 SHALL 保持不变

#### Scenario: 被替换的结果可按引用无损回读

- **GIVEN** 一个已被替换为 ref 的工具结果
- **WHEN** 调用方按该 ref 回读
- **THEN** 系统 SHALL 返回与原始完全一致的内容（逐字节相等）
- **AND** 该回读入口 SHALL 对根 agent 与子 agent 均可用

#### Scenario: 无引用时不谎称可回读

- **GIVEN** 一个工具结果因超过阈值被截断，但其落盘未成功（无 ref）
- **WHEN** 上下文管线替换其正文
- **THEN** 标记 SHALL 如实表示为「已截断、全文不可回读」
- **AND** SHALL NOT 声称存在可解析的 ref

#### Scenario: 有界化不静默

- **GIVEN** 上下文管线对若干工具结果执行了有界化
- **WHEN** 一次 run 结束
- **THEN** 有界化的发生与量（条数、释放的字节）SHALL 可被观察
- **AND** SHALL NOT 静默发生
