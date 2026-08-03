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

### Requirement: Benchmark Regression Gate

可观测性系统 SHALL 提供 benchmark 回归门禁：持久化基线指标（success_rate、p95 latency），将新 run 与基线对比，当成功率下降超过 5 个百分点或 p95 延迟超过 `max(基线*1.05, 基线+1.0s)`（相对 5% + 1 秒绝对值下限，避免亚秒级基线受无意义相对抖动影响）时返回非零退出码。

#### Scenario: 门禁拦截劣化 run

- **GIVEN** 基线 `success_rate=0.95`、`p95_latency_s=10.0`
- **WHEN** 新 run 的 `success_rate=0.85` 或 `p95_latency_s=11.5`
- **THEN** 门禁返回非零
- **AND** 报告列出每个指标的 delta

#### Scenario: p95 恰在绝对下限上限处通过

- **GIVEN** 基线 `p95_latency_s=10.0`
- **WHEN** 新 run 的 `p95_latency_s=11.0`
- **THEN** 门禁通过（上限为 `max(10.5, 11.0)=11.0`，严格 `>`）

#### Scenario: 从信任的 run 更新基线

- **GIVEN** 一个信任的 run
- **WHEN** 门禁以 `--update-baseline` 运行
- **THEN** 基线文件被重写为该 run 的指标
- **AND** 后续 run 与新的基线对比

### Requirement: Session Timeline

可观测性系统 SHALL 暴露每个 session 的工具调用 timeline，按耗时（ms）降序排列，带成功状态，为 Web UI 整形条宽数据。

#### Scenario: session timeline 查询

- **GIVEN** 一个含不同耗时工具调用的 session
- **WHEN** 查询 timeline 端点
- **THEN** calls 按耗时降序返回
- **AND** 每条 call 携带 `tool_name`、`duration_ms`、`success`、`arguments`、`index`、`bar_pct`

### Requirement: error_type 在产生点打标

可观测性系统 SHALL 在关键错误产生点打标结构化 `error_type`，使 `record_tool_result` 收到的是结构化 signal 而非文本猜测。文本分类 SHALL 仅作为对未打标工具的兜底。

#### Scenario: Bash 超时打标

- **GIVEN** Bash 命令在沙箱中超时（`SandboxResult.timed_out=True`）
- **WHEN** loop 记录该工具结果
- **THEN** trace 的 tool_result SHALL 携带 status=`"error"`
- **AND** error_type SHALL 为 `"timeout"`

#### Scenario: approval 预拒绝打标

- **GIVEN** 工具调用要求审批但被拒绝（approval DENIED）
- **WHEN** loop 记录该工具结果
- **THEN** trace 的 tool_result SHALL 携带 status=`"error"`
- **AND** error_type SHALL 为 `"approval_denied"`

#### Scenario: 结构化优先于文本兜底

- **GIVEN** 一个打标工具返回 error_type=`"permission_denied"` 的结构化结果
- **WHEN** loop 判定该工具结果状态
- **THEN** 系统 SHALL 使用结构化 error_type 判定 status=`"error"`
- **AND** SHALL NOT 依赖文本前缀猜测

#### Scenario: 未打标工具仍走文本兜底

- **GIVEN** 一个未打标工具返回 `"[Error: timed out]"` 文本
- **WHEN** loop 判定该工具结果状态
- **THEN** 系统 SHALL 通过文本兜底分类为 `"network_timeout"`（文本兜底返回粗粒度 category.value）
- **AND** status SHALL 为 `"error"`

### Requirement: LLM 错误可观测化

可观测性系统 SHALL 在 LLM 调用失败时记录结构化 `llm_error` 事件（含 error_type），不改变 run 失败语义。

#### Scenario: LLM 网络错误记录

- **GIVEN** LLM 调用因连接错误失败
- **WHEN** loop 捕获该异常
- **THEN** trace SHALL 记录 error_type=`"network_timeout"` 的 llm_error 事件
- **AND** 异常 SHALL 继续向上传播（run 失败语义不变）
