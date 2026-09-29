# agent-runtime spec delta: bus 快照出口随 RunPattern 退役而改挂

## MODIFIED Requirements

### Requirement: 编排结果中的 bus 快照有界

编排中 `MessageBus.snapshot_payload()` 的产出 SHALL bounded：每条消息的 `summary` SHALL 不超过与其它模型面出口同值的固定单条上限，返回的消息条数 SHALL 有固定上限。该 Requirement SHALL 适用于**任何仍向模型面暴露 bus 快照的出口**（当前为 `ReadBus` 工具与调度器权威 `_envelope()`）；父 agent 的 workflow 结果投影（`parent_envelope()`）SHALL NOT 携带 `bus`，因此不在此列。

该快照是一次编排里所有 worker 发布消息折进模型上下文的注入路径，故条数上限 SHALL 存在——否则「一次调用注入多少上下文」由被检视的子 agent 决定。

超出条数上限时，快照 SHALL **显式报告**被省略的条数（例如 `messages_omitted` / `messages_total`），SHALL NOT 静默丢弃。

该界 SHALL 施加在 `snapshot_payload()` **本身**（`agent/subagent/bus.py`），SHALL NOT 只在某个调用点加固：`ReadBus` 与调度器 `_envelope()` 共用该方法，只加固一处等于留一个同类漏口。

本 Requirement 只约束 `bus` 快照这一项。历史 `RunPattern` 返回体中的 `workers[]` 与顶层 `summary` 的条数维**不在**本 Requirement 范围内（随该返回体退役一并消失）。

#### Scenario: bus 快照的界施加在方法本身

- **GIVEN** `snapshot_payload()` 是 `ReadBus` 与调度器 `_envelope()` 的共同来源
- **WHEN** 直接调用 `MessageBus.snapshot_payload()`
- **THEN** 返回体的条数与单条上限 SHALL 已生效（不依赖任何调用点额外处理）

#### Scenario: 父 agent 的编排结果投影不含 bus

- **GIVEN** 一次编排里 100 个 worker 各发布了一条 1600 字的 bus 消息
- **WHEN** 父 agent 收到统一 Workflow 入口的返回体
- **THEN** 该返回体 SHALL NOT 含 `bus` 键
- **AND** 同一批消息经 `ReadBus` 读取时 SHALL 满足条数与单条上限，并显式报告被省略的条数
