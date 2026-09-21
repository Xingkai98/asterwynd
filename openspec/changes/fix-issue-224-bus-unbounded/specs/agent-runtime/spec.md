# Spec Delta: agent-runtime — 编排运行结果里的 bus 快照 SHALL bounded

## ADDED Requirements

### Requirement: 编排结果中的 bus 快照有界

编排 pattern（`RunPattern`）返回体中的 `bus` 快照（`MessageBus.snapshot_payload()`）SHALL bounded：每条消息的 `summary` SHALL 不超过与其它模型面出口同值的固定单条上限，返回的消息条数 SHALL 有固定上限。

该快照是一次编排里所有 worker 发布消息折进父上下文的注入路径，故条数上限 SHALL 存在——否则「一次调用注入多少父上下文」由被检视的子 agent 决定。

超出条数上限时，快照 SHALL **显式报告**被省略的条数（例如 `messages_omitted` / `messages_total`），SHALL NOT 静默丢弃。

该界 SHALL 施加在 `snapshot_payload()` **本身**（唯一模型面调用点是 `RunPattern` 的 `patterns.py:458`），SHALL NOT 只在某个调用点加固：调度器的 `_envelope()` 同样调用该方法，只加固一处等于留一个同类漏口。

本 Requirement 只约束 `bus` 快照这一项。`RunPattern` 返回体中的 `workers[]` 与顶层 `summary` 的条数维**不在**本 Requirement 范围内（另案处理）——读者 SHALL NOT 把本 Requirement 读成「`RunPattern` 返回体已整体 bounded」。

#### Scenario: RunPattern 返回体的 bus 快照有界

- **GIVEN** 一次 `RunPattern` 编排里，100 个 worker 各发布了一条 1600 字的 bus 消息
- **WHEN** 父 agent 收到 `RunPattern` 的返回体
- **THEN** 返回体 `bus.messages` 的条数 SHALL 不超过固定上限
- **AND** 其中每条 `summary` SHALL 不超过固定的单条内容上限
- **AND** 返回体 SHALL 显式报告被省略的消息条数

#### Scenario: bus 快照的界施加在方法本身

- **GIVEN** `snapshot_payload()` 是 `RunPattern` 与调度器 `_envelope()` 的共同来源
- **WHEN** 直接调用 `MessageBus.snapshot_payload()`
- **THEN** 返回体的条数与单条上限 SHALL 已生效（不依赖任何调用点额外处理）
- **AND** SHALL 显式报告被省略的条数

#### Scenario: bus 快照的界不随调用方参数放大

- **GIVEN** 同一个已满载的 bus
- **WHEN** 父 agent 通过不同的调用参数（含超大的发布侧 `max_tokens`）取得快照
- **THEN** 快照的条数与单条上限 SHALL 保持不变
- **AND** 结果 SHALL NOT 随调用方传入的数值变化
