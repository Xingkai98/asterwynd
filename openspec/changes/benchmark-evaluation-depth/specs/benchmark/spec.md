# benchmark 规格（delta）

本文件是 `benchmark-evaluation-depth` change 对既有 `benchmark` capability 的增量补充。既有 requirements 语义保持不变；本文件仅新增向后兼容的评测扩展字段与 CLI 参数。

## ADDED Requirements

### Requirement: 结果 artifact 记录重复运行与统计字段

benchmark result artifact SHALL 在保留既有字段的基础上，新增可选的重复运行、能力分层与统计字段；这些字段存在时 SHALL 携带 `benchmark-evaluation` 结果，缺失时 SHALL 保持既有向后兼容行为。

#### Scenario: 记录分层与统计字段

- **GIVEN** 一次带评测扩展的 benchmark run
- **WHEN** 写入 result artifact
- **THEN** artifact SHALL 记录任务能力分层标签
- **AND** SHALL 记录重复运行轮次与分布统计（如均值/标准差/置信区间）
- **AND** 既有 `status`/`reason`/`run_id` 语义 SHALL NOT 改变

### Requirement: benchmark CLI 支持重复运行参数

benchmark CLI SHALL 支持传入重复运行次数（如 `--repeat N`），用于评测聚合；不传时 SHALL 默认单次运行以保持既有行为。

#### Scenario: 传入重复运行次数

- **GIVEN** 用户传入 `--repeat 3`
- **WHEN** benchmark 命令执行
- **THEN** 系统 SHALL 对任务集合执行 3 次重复运行
- **AND** 汇总到评测聚合层

#### Scenario: 未传入重复运行次数

- **GIVEN** 用户未传入 `--repeat`
- **WHEN** benchmark 命令执行
- **THEN** 系统 SHALL 按既有单次运行执行

### Requirement: 任务支持显式能力分层

benchmark task schema SHALL 支持显式能力分层字段，将任务归入可复用的能力层级。分层使用标签表达（如 `execution`、`tool-usage`、`context-planning`、`multi-step-solving`），供评测按层聚合统计。

#### Scenario: 任务声明能力层级

- **GIVEN** 某 benchmark 任务填写了能力分层标签
- **WHEN** runner 读取 task schema
- **THEN** 系统 SHALL 保留该分层标签用于按层汇总
- **AND** 结果页 SHALL 能按层展示通过率与统计指标

#### Scenario: 任务未声明能力层级

- **GIVEN** 某 benchmark 任务未填写能力分层字段
- **WHEN** 评测汇总结果
- **THEN** 系统 SHALL 将该任务归入默认层级
- **AND** 不得因缺少分层字段导致评测失败

### Requirement: 输出统计指标与置信区间

benchmark-evaluation SHALL 对重复运行结果计算均值、标准差，并给出置信区间；对通过类任务支持 `Pass@k` 稳定性指标。统计方法 SHALL 可复现（固定随机种子或记录统计参数）。

#### Scenario: 计算分布统计

- **GIVEN** 某任务已完成 N>=3 次重复运行
- **WHEN** 评测汇总统计
- **THEN** 结果 SHALL 包含均值与标准差
- **AND** SHALL 包含置信区间（如 95% CI）
- **AND** SHALL 包含任务通过率与 `Pass@k`

### Requirement: 开放式任务支持 judge 校准与人工回流

对无 hidden test 的开放式任务，benchmark-evaluation SHALL 提供判定流程，保证判分口径一致，并记录人工回流证据。

#### Scenario: 开放式任务判定

- **GIVEN** 某任务无 hidden test 且标记为开放式
- **WHEN** 评测对 agent 输出做判定
- **THEN** 系统 SHALL 使用一致的判定流程（judge）
- **AND** 判定结果 SHALL 记录可审计的人工回流标记或判定理由

### Requirement: 失败归因分类

benchmark-evaluation SHALL 按失败 `reason` 对重复运行结果分类统计，输出失败模式占比与样例回查入口，供性能退化定位（如 git bisect）使用。

#### Scenario: 失败模式占比

- **GIVEN** 某次评测包含多种失败原因
- **WHEN** 结果页渲染失败归因
- **THEN** 结果 SHALL 按 reason 展示失败模式占比
- **AND** 每个失败模式 SHALL 可回查到具体任务与运行轮次

### Requirement: 渲染可引用的量化结果页

benchmark-evaluation SHALL 把上述指标汇总渲染为一个可在面试中直接引用的结果页（markdown/HTML），覆盖 Pass@k、均值/标准差、置信区间、延迟分布和 token 成本。

#### Scenario: 生成结果页

- **GIVEN** 一次带重复运行和统计的评测完成
- **WHEN** 评测输出结果页
- **THEN** 结果页 SHALL 包含 Pass@k、均值/标准差、置信区间、延迟分布与 token 成本
- **AND** SHALL 按能力层级组织，便于按层引用
