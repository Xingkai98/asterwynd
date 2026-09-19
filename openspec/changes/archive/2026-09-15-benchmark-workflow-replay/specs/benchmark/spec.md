# benchmark spec delta: workflow 可重放三模式

## ADDED Requirements

### Requirement: benchmark workflow 三模式

系统 SHALL 支持三种 workflow benchmark 运行模式：`template`（固定 Pattern/DSL 回归 baseline）、`dynamic-record`（模型自由生成 workflow 并旁路记录规范化 spec + spec_hash + scheduler_version + budget_config + seed/model/temperature）、`dynamic-replay`（不重跑规划模型，离线重放已保存的 workflow_record.json）。`dynamic-record` 与 `dynamic-replay` 的 `spec_hash` SHALL 一致（`WorkflowSpec.spec_hash` 是 replay 锚点）。

#### Scenario: dynamic-record 落盘可重放记录

- **GIVEN** 一个 dynamic-record 模式的任务运行
- **WHEN** 模型自由生成并执行 workflow
- **THEN** 系统 SHALL 旁路保存规范化 workflow 记录（spec/spec_hash/scheduler_version/budget_config/seed/model/temperature）
- **AND** SHALL NOT 打断模型自由生成

#### Scenario: dynamic-replay 离线重放

- **GIVEN** 一份已保存的 workflow_record.json
- **WHEN** dynamic-replay 模式运行
- **THEN** 系统 SHALL 不重跑规划模型、直接重放 spec
- **AND** SHALL 得到与 record 一致的 spec_hash

### Requirement: workflow 报告字段

benchmark 任务结果 SHALL 记录 workflow 字段：workflow_mode / workflow_spec_hash / scheduler_version / node_count / run_count / peak_active / queue_wait_s / critical_path_s / workflow_cost_usd。无 workflow 的任务这些字段 SHALL 为 null，报告 SHALL 不崩。

#### Scenario: workflow 任务记录完整字段

- **GIVEN** 一个 workflow 模式的 benchmark 任务完成
- **WHEN** 结果被记录
- **THEN** 系统 SHALL 记录全部 workflow 字段
- **AND** 报告 SHALL 渲染这些字段

### Requirement: 编排质量指标

系统 SHALL 记录编排质量指标：冗余度（有用产出 / spawn 总数）、图级步数、拒绝降级计数（queue_full + 深度撤工具 + spawn 拒绝 + 图级超限）、`depth_capped_runs`（按构造次数计、并入拒绝总量）、`queue_cancelled_runs`（单列、不并入）。这些指标 SHALL 从 scheduler/manager 既有状态字段汇总或新增 instrumentation 计数器取得，SHALL NOT 新增执行路径分支。

#### Scenario: 拒绝降级计数

- **GIVEN** 一个 workflow 运行中护栏拒绝或降级了 spawn
- **WHEN** 结果被记录
- **THEN** 系统 SHALL 记录拒绝降级计数
- **AND** 冗余度 SHALL = 有用产出 / spawn 总数

### Requirement: 编排比较口径

benchmark 比较 SHALL 从「pass rate」扩展为：完成率 + 总 token + $/resolved-task + wall time + 节点数 + 峰值并发 + 关键路径 + 失败原因。对照臂 SHALL 含「小 k 高质量 vs 大 N 暴力」。判分 SHALL 沿用确定性 verifier，SHALL NOT 把「模型选了哪条路径」当主观 judge 分。

#### Scenario: 多口径比较

- **GIVEN** 两个 workflow benchmark 运行结果
- **WHEN** 比较
- **THEN** 系统 SHALL 输出多口径（不只 pass rate）
- **AND** SHALL 含 $/resolved-task 与峰值并发等编排口径

### Requirement: workflow 报告渲染与 replay 判分边界

workflow 字段 SHALL 渲染为**独立 section**（只统计有 workflow 的记录，主表仅加一列 `workflow_mode`），SHALL NOT 让 null 单元格污染主表与 pass@k 聚合口径。`dynamic-replay` 的结果 SHALL 只比编排指标、SHALL NOT 走 benchmark verifier 判分，SHALL 在 `is_valid_round`/`_valid_results` 中显式排除（不进 pass@k 分母），避免与 record 双重计数。

#### Scenario: 独立 section 渲染

- **GIVEN** 一批同时含「有 workflow」与「无 workflow」的 benchmark 结果
- **WHEN** 报告渲染
- **THEN** 系统 SHALL 把 workflow 字段放进独立 section
- **AND** 主表 SHALL 只加一列 workflow_mode、SHALL NOT 被 null 污染

#### Scenario: replay 不进判分分母

- **GIVEN** 一个 dynamic-replay 模式的 benchmark 结果
- **WHEN** 计算 pass@k 与 $/resolved-task
- **THEN** 系统 SHALL 把 replay 记录从分母显式排除
- **AND** SHALL 只比编排指标、SHALL NOT 判 pass/fail
