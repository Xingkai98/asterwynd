# memory-context spec delta: 压缩硬顶

## MODIFIED Requirements

### Requirement: 超过 90% token 阈值时触发压缩

MemoryManager SHALL 在估算 token 数达到 `max_tokens` 的 90% 时执行 compact。`compact_if_needed` SHALL 接受可选的 `iteration` 参数，在上一次压缩后的 `compaction_gap` 轮内不重复触发。`compact_if_needed` SHALL 返回是否实际触发了 compact；未达到阈值或间隔不足时 SHALL 返回 false 并保持消息列表不变。

`compaction_gap` 节流 SHALL 只用于避免频繁压缩的抖动，SHALL NOT 成为「允许上下文无界增长」的许可证：当估算占用量达到一个**硬上限**（高于常规阈值，为 `max_tokens` 的若干倍，或等价的明确常量/可配置上界）时，`compact_if_needed` SHALL **无视间隔限制强制执行 compact**，使**由工具结果主导**的常驻上下文有界。硬上限 SHALL NOT 为无限。

该硬上限 SHALL 同时约束两个维度：token 估算 **与** 常驻字节（尤其内容块类结果，其 token 估算可能远低于实际字节占用）——SHALL NOT 仅凭 token 估算判定而在字节维度已失控时放行。

对工具结果输入侧的有界化（工具结果生命周期处理）SHALL 在判定压缩**之前**发生：`compact_if_needed` 的判定 SHALL 看到的是有界化之后的占用量。

已知残余边界（**如实声明，不掩盖**）：本条款只保证「工具结果主导」的上下文有界；近期窗口内的**非工具大内容**（超大用户粘贴、超大工具调用参数、后台任务的注入输出）不在工具结果有界化范围内，其驻留由近期窗口的保留策略约束、SHALL NOT 被本条款的错误解读为「本机制已保证一切内容有界」。

#### Scenario: 未达到阈值

- **GIVEN** 消息 token 估算未达到 `max_tokens` 的 90%
- **WHEN** 调用 `compact_if_needed`
- **THEN** 系统 SHALL 保持消息列表不变
- **AND** 返回 false

#### Scenario: 达到阈值但间隔不足且未到硬上限

- **GIVEN** 消息占用量达到 `max_tokens` 的 90%
- **AND** 距离上一次 compaction 不足 `compaction_gap` 轮
- **AND** 消息占用量**未达到硬上限**
- **WHEN** 调用 `compact_if_needed`
- **THEN** 系统 SHALL 跳过 compaction（gap 防抖）
- **AND** 返回 false

#### Scenario: 达到硬上限时无视间隔强制执行

- **GIVEN** 消息占用量达到**硬上限**
- **AND** 距离上一次 compaction 不足 `compaction_gap` 轮
- **WHEN** 调用 `compact_if_needed`
- **THEN** 系统 SHALL **无视间隔限制**执行 compact
- **AND** 返回 true
- **AND** 常驻上下文 SHALL 有界（SHALL NOT 因 gap 未到间隔就放任其无界增长）

#### Scenario: 字节维度驱动硬上限

- **GIVEN** 消息的 token 估算因内容块类结果而偏低，但**常驻字节**已达到硬上限
- **WHEN** 调用 `compact_if_needed`
- **THEN** 系统 SHALL 按字节维度认定达到硬上限并执行 compact
- **AND** SHALL NOT 仅因 token 估算未达上限而放行

#### Scenario: 达到阈值且间隔足够

- **GIVEN** 消息占用量达到 `max_tokens` 的 90%
- **AND** 距离上一次 compaction 已达到或超过 `compaction_gap` 轮
- **WHEN** 调用 `compact_if_needed`
- **THEN** 系统 SHALL 执行 compact
- **AND** 返回 true
