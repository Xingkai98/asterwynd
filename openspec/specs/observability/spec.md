# 可观测性 规格

## Purpose

定义 可观测性 能力域的规格。当前为基线状态；深化需求通过 OpenSpec change 的 spec delta 演进。

## Requirements

### Requirement: 可观测性 能力域基线

可观测性 能力域 SHALL 提供基础能力，深化需求通过 OpenSpec change 的 ADDED Requirements 合入演进。

#### Scenario: 能力域可扩展

- **GIVEN** 一个针对 可观测性 能力域的 OpenSpec change
- **WHEN** 该 change 的 spec delta 被接受
- **THEN** 能力域的 requirement 随 ADDED Requirements 演进

### Requirement: Structured Token Metrics

trace recorder SHALL 记录每次 LLM 迭代的 token（input/output tokens、model、finish_reason），SHALL 为每个 trace step 附加 wall-clock 时间戳，SHALL 暴露事件 schema 版本。

#### Scenario: LLM 迭代 token 记录

- **GIVEN** 一次带 token 用量的 LLM 迭代
- **WHEN** trace recorder 记录该迭代
- **THEN** input/output tokens、model、finish_reason 被记录
- **AND** 每个 trace step 携带时间戳
- **AND** 序列化 trace 包含 schema 版本

### Requirement: Cost Attribution (CostLedger)

可观测性系统 SHALL 通过 `CostLedger` 按 session/phase/tool 归属 token 成本，SHALL 输出可查账单（`by_session`/`by_phase`/`by_tool`），SHALL 将记录持久化到 JSONL 以支持跨 session 历史统计。

#### Scenario: session 成本账单

- **GIVEN** 一个含多 phase 多 tool 的 session
- **WHEN** ledger 记录 LLM 调用
- **THEN** token 成本按 session/phase/tool 分组
- **AND** 输出可查账单
- **AND** flush 到 JSONL 再 load 恢复相同总额

### Requirement: Error Auto-Classification

可观测性系统 SHALL 将系统级错误分类为四类（permission_denied/network_timeout/model_error/parameter_error），SHALL 优先使用结构化属性（error_type/finish_reason）+ 文本兜底，SHALL 为每类分配告警策略，SHALL NOT 自动分类语义错误（幻觉）——那由 LLM judge 处理。

#### Scenario: 结构化错误分类

- **GIVEN** 一个 `error_type=permission_denied` 的错误
- **WHEN** 分类器处理
- **THEN** 分类为 permission_denied
- **AND** 告警策略为 `immediate`

#### Scenario: 非结构化错误文本兜底

- **GIVEN** 含 "timed out" 的错误文本且无结构化字段
- **WHEN** 分类器处理
- **THEN** 分类为 network_timeout
- **AND** 告警策略为 `warn`

### Requirement: 事件 schema 扩展

`agent-runtime` 的 trace 事件 SHALL 增加 timestamp（TraceStep 字段，不污染 data 负载）、schema_version、llm_iteration 的 token/model/finish_reason 字段、tool_result 的 error_type 字段——全部向后兼容扩展。

#### Scenario: 既有事件结构不破坏

- **GIVEN** 一个既有 trace 事件（无 token/timestamp 字段）
- **WHEN** 新 recorder 序列化它
- **THEN** data 负载保持不变（timestamp 是 step 字段）
- **AND** schema_version 附加在顶层
