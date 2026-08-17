# benchmark 规格（delta）

本文件是 `evaluation-metrics`（C2）change 对既有 `benchmark` capability 的修订。C1 `evaluation-task-spec` 已把 G3 M1–M11 指标/方法 Requirement 落进正式规格（带「实现归 C2 evaluation-metrics」注记）；本 change 实现这些 Requirement 的指标层，以 REVISED 方式去掉注记并补充实现细节。既有 requirements 语义保持兼容，全部为向后兼容扩展。

## MODIFIED Requirements

### Requirement: 评测采样显式化

benchmark-evaluation SHALL 支持显式采样：重复运行次数 `--repeat N` 取 3–5（N>=3 才有 pass^k 意义）；每次运行记录采样参数（`seed`、`temperature`、模型版本）；`seed` 使用固定集合（如 seed 0..N-1）保证可复现；`temperature` 默认 0.2（pass@1 口径）。CLI SHALL 提供 `--seeds`（显式 seed 集合，缺省推导为 0..N-1）、`--temperature`（缺省 0.2）与 `--model-version` 参数；每轮 run artifact SHALL 记录 (temperature, seed, model version)。可复现声明 SHALL 限定在（模型版本、provider、harness）内，部分 provider 不承诺 seed 语义。

#### Scenario: 采样参数记录

- **GIVEN** 一次带重复运行的评测
- **WHEN** 写入 run artifact
- **THEN** 每轮 SHALL 记录 (temperature, seed, model version)
- **AND** 结果页 SHALL 展示采样参数

#### Scenario: 显式 seed 集合

- **GIVEN** 用户传入 `--seeds 0 1 2` 与 `--repeat 3`
- **WHEN** benchmark 命令执行
- **THEN** 三轮 run SHALL 分别使用 seed 0/1/2
- **AND** 每轮 artifact SHALL 记录对应 seed

### Requirement: 成本与延迟联合展示

benchmark-evaluation SHALL 在结果页并列展示 Pass@1 与成本指标 `$/resolved-task`，并报告 token 缓存命中率（cache hit rate）。成本 SHALL 采用 cache-aware 定价（区分 fresh input / cache read / cache write / output 四档），声明定价表版本与日期，并显式定义 `$/resolved-task` 口径（层内全部 run 总成本含失败 run / resolved 数；仅 LLM token 计费，不含沙箱/CI/计算）。成本核算 SHALL 使用 cache-aware 计费函数与四档定价表，未知模型 SHALL 回退为估算并警告（不得静默返回 0），self-hosted 模型 SHALL 标注不计费或估算口径。

#### Scenario: 成本指标展示

- **GIVEN** 一次带统计的评测完成
- **WHEN** 结果页渲染成本
- **THEN** 结果 SHALL 包含 Pass@1 与 `$/resolved-task` 并列
- **AND** SHALL 包含 cache hit rate（按模型、能力层拆分）
- **AND** SHALL 声明定价表版本/日期与成本口径

#### Scenario: 未知模型成本回退

- **GIVEN** 某 run 使用的模型不在定价表
- **WHEN** 核算该 run 成本
- **THEN** 系统 SHALL 输出估算成本并标注未知模型警告
- **AND** SHALL NOT 静默输出零成本

### Requirement: 失败归因与 fault_owner

benchmark-evaluation SHALL 保留失败 `reason` 分类，并新增正交的 `fault_owner` 维度（`agent`/`task`/`environment`/`unknown`）。fault_owner 标注来源 SHALL 声明（主选人审抽样 + 双人标注 κ 报告，可选强 judge 首标 + 人审抽样校准）；未标注的失败 SHALL 归入 `unknown` 聚合。统计层 SHALL 提供 reason × fault_owner 交叉表聚合；fault_owner 绑定 (task, round) 标注，不做 reason→owner 查表推导。

#### Scenario: 失败归因交叉表

- **GIVEN** 一次带失败归因的评测
- **WHEN** 结果页渲染失败
- **THEN** 结果 SHALL 按 reason 展示失败模式占比
- **AND** SHALL 展示 reason × fault_owner 交叉表
- **AND** 每个失败 SHALL 可回查到具体任务与运行轮次
- **AND** 未标注 fault_owner 的失败 SHALL 归入 `unknown` 并单独展示

### Requirement: 报告元组结构化披露

benchmark 报告 SHALL 以结构化元组披露运行环境：模型（`model`: name/version/provider/seed 支持）、harness（`harness`: adapter/prompt_version/tools/max_turns/timeout/patch_collection/network on-off）、`task_set_hash`（任务集版本钉住）、grader 版本、成本口径（定价表版本/日期 + cache hit rate）。run artifact SHALL 记录对应字段（task_set_hash、adapter/grader 版本、max_iterations、timeout、network、温度/seed、cache tokens）；缺失字段 SHALL 保持向后兼容（可空）。

#### Scenario: 报告元组完整

- **GIVEN** 一次带评测扩展的 benchmark run
- **WHEN** 写入报告/run artifact
- **THEN** 报告 SHALL 包含 model/harness/task_set_hash/grader/成本口径元组
- **AND** 缺失字段 SHALL 保持向后兼容（可空）

### Requirement: SWE-bench 污染披露

引用 SWE-bench 数字时，benchmark 报告 SHALL 携带污染与缺陷披露：OpenAI 2026-02 已弃用 SWE-bench Verified（审计 138 个高失败率实例中 59.4% 有实质缺陷），数字只能作为对照参考、不得作为无保留金标准；披露 SHALL 覆盖子集层面风险（KNOWN_BAD 过滤条数、现有 fixture 偏置、数据集版本与 swebench 包版本钉住）。run metadata SHALL 记录 swebench 数据集版本与 swebench 包版本，供披露引用。

#### Scenario: 结果页污染注记

- **GIVEN** 结果页引用 SWE-bench 数字
- **WHEN** 渲染结果页
- **THEN** 结果页 SHALL 带保留条件域的污染注记
- **AND** SHALL 注明子集过滤与版本钉住信息

### Requirement: 配对比较统计

compare 路径 SHALL 支持配对比较统计：per-task delta + 差异置信区间（paired bootstrap / McNemar）+ win-rate，用于"同任务同 harness 换 agent/模型"的对照展示，不得只给两个点估计。统计方法 SHALL 可复现（固定随机种子）。

#### Scenario: 换 agent 对照

- **GIVEN** 两组 run 在同一任务集、同一 harness 下使用不同 agent/模型
- **WHEN** compare 渲染对照
- **THEN** 结果 SHALL 包含 per-task delta、差异 CI 与 win-rate
- **AND** SHALL 按任务展示逐项差异

#### Scenario: 配对统计可复现

- **GIVEN** 同一对 run 重复执行 paired comparison
- **WHEN** 计算差异 CI 与 win-rate
- **THEN** 结果 SHALL 可复现（固定 seed）

### Requirement: SWE-bench 部分成功保留

SWE-bench adapter SHALL 保留 report.json 的部分成功字段（`f2p_rate`/`p2p_rate`/`reward`），失败归因与结果页建立在更细粒度信息上，不得只保留整体 resolved 布尔值。

#### Scenario: 部分成功字段透传

- **GIVEN** SWE-bench harness 返回 report.json
- **WHEN** adapter 标准化 Verdict
- **THEN** Verdict SHALL 保留 f2p_rate/p2p_rate/reward 字段
- **AND** 结果页 SHALL 展示部分成功档

### Requirement: 小样本统计声明

小样本（N=3–5）下 per-task bootstrap CI 统计意义弱，结果页渲染层 SHALL 添加小样本声明，或仅在 layer/aggregate 层级展示 CI 权重。统计层 SHALL 输出样本量 N 供渲染层判断。

#### Scenario: 小 N 声明

- **GIVEN** 某任务重复运行次数 N 为 3–5
- **WHEN** 结果页渲染 per-task CI
- **THEN** 结果页 SHALL 附带小样本统计声明

### Requirement: 过程效率指标

benchmark-evaluation SHALL 从 trace 记录采集过程效率指标：time-to-first-successful-edit（首次成功编辑耗时）与 exploration fraction（探索占比），作为结果页可选项展示。

#### Scenario: 过程效率采集

- **GIVEN** 某任务 trace.json 记录了步骤事件
- **WHEN** 结果页渲染过程指标
- **THEN** 结果 SHALL 可展示 time-to-first-successful-edit 与 exploration fraction
