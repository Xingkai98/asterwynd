# benchmark 规格（delta）

本文件是 `evaluation-task-spec`（C1）change 对既有 `benchmark` capability 的修订与增补。既有 requirements 语义保持兼容；本文件修订 3 条既有 Requirement（能力分层口径、Pass@k→pass^k、artifact 标签口径）并新增任务集组成与指标/方法 Requirement（指标/方法实现归 C2 `evaluation-metrics`，本 change 只落规格文本）。

## REVISED Requirements

### Requirement: 任务支持显式能力分层

benchmark task schema SHALL 支持 `scenario` 与 `difficulty` 显式标签：`scenario` 使用代码改动类型 5 枚举（`bug-fix`/`feature-dev`/`refactor`/`debug`/`integration`），`difficulty` 使用 3 档枚举（`easy`/`medium`/`hard`），供评测按场景、难度聚合统计。能力层 SHALL NOT 要求任务级正交标签，改用套件级能力覆盖矩阵表达：任务集 manifest SHALL 声明覆盖的能力域（如 `tool-usage`/`context-planning`/`multi-step-solving`/`error-recovery`/`safety-boundary`/`long-term-memory`/`long-context`），结果页按套件展示能力覆盖度。

#### Scenario: 任务声明场景与难度

- **GIVEN** 某 benchmark 任务填写了 `scenario` 与 `difficulty` 标签
- **WHEN** runner 读取 task schema
- **THEN** 系统 SHALL 保留该双标签用于按场景/难度汇总
- **AND** 结果页 SHALL 能按场景与难度展示通过率与统计指标

#### Scenario: 任务未声明场景或难度

- **GIVEN** 某 benchmark 任务未填写 `scenario` 或 `difficulty`
- **WHEN** 评测汇总结果
- **THEN** 系统 SHALL 将缺失维度归入默认值
- **AND** 不得因缺少标签导致评测失败

#### Scenario: 任务集 manifest 声明能力覆盖矩阵

- **GIVEN** 某任务集 manifest 声明了能力域覆盖矩阵
- **WHEN** 评测渲染结果页
- **THEN** 结果页 SHALL 按能力域展示任务覆盖度与聚合指标
- **AND** 每个已声明能力域 SHALL 至少覆盖一个任务

### Requirement: 输出统计指标与置信区间

benchmark-evaluation SHALL 对重复运行结果计算均值、标准差，并给出置信区间；对通过类任务支持 `pass^k` 稳定性指标，并区分 `pass@1`（有效轮次经验通过率，用户实际获得的质量）、`pass@k`（k 次任一成功，能力上限）、`pass^k`（全部 k 轮成功，可靠性）。统计方法 SHALL 可复现（固定随机种子或记录统计参数）；统计语义 SHALL 声明 n 与 k 关系（n=k 时仅 pass@1 与 pass^k 有统计意义，中间档 1<k<n 高方差不推荐展示）。

#### Scenario: 计算分布统计

- **GIVEN** 某任务已完成 N>=3 次重复运行
- **WHEN** 评测汇总统计
- **THEN** 结果 SHALL 包含均值与标准差
- **AND** SHALL 包含置信区间（如 95% CI）
- **AND** SHALL 包含任务通过率与 `pass^k` 稳定性指标

#### Scenario: 声明统计有效性条件

- **GIVEN** 某任务的重复运行次数 N 与 pass@k 的 k
- **WHEN** 结果页展示统计指标
- **THEN** 系统 SHALL 声明 n 与 k 的有效性条件
- **AND** 无效轮次（`unsupported`/`approval-unavailable`/`docker_unavailable`）SHALL NOT 计入 pass@1 与 pass^k 的分母

### Requirement: 结果 artifact 记录重复运行与统计字段

benchmark result artifact SHALL 在保留既有字段的基础上，新增可选的重复运行、场景/难度标签与统计字段；这些字段存在时 SHALL 携带 `benchmark-evaluation` 结果，缺失时 SHALL 保持既有向后兼容行为。

#### Scenario: 记录场景与统计字段

- **GIVEN** 一次带评测扩展的 benchmark run
- **WHEN** 写入 result artifact
- **THEN** artifact SHALL 记录任务场景与难度标签
- **AND** SHALL 记录重复运行轮次与分布统计（如均值/标准差/置信区间）
- **AND** 既有 `status`/`reason`/`run_id` 语义 SHALL NOT 改变

## ADDED Requirements

### Requirement: 任务集由三来源组成

benchmark 任务集 SHALL 由三来源组成：A 轨历史重建任务（存量回归基线）、B 轨当前演进任务（当前 HEAD 真实缺陷/增强，面试核心）、外部开源测试集精选子集（如 SWE-bench Verified）。任务集 manifest SHALL 为每个任务标注 `track`（`A`/`B`/`verified`）。

#### Scenario: 任务集声明三来源

- **GIVEN** 一次带评测扩展的 benchmark run
- **WHEN** 汇总任务集组成
- **THEN** 任务集 SHALL 按 track 分组展示数量与占比
- **AND** 每个 track SHALL 至少包含一个任务

### Requirement: 外部测试集精选子集接入

benchmark SHALL 支持接入外部开源测试集精选子集（如 SWE-bench Verified 50 条）：从轻量/中等难度实例池逐条过滤已知坏实例（KNOWN_BAD）与重实例（如 django/sphinx），验证路径按资源可用性分级（L1 本地轻量验证、L2 Docker harness 验证、L3 金补丁自检剔除 flaky/坏实例），结果页携带子集污染与偏置披露。

#### Scenario: 精选子集元数据校验

- **GIVEN** 某 external 子集 fixture 已生成
- **WHEN** runner 读取任务
- **THEN** fixture SHALL 提供完整实例元数据（instance_id/dataset_name/dataset_split）
- **AND** SHALL 不包含 KNOWN_BAD 或重实例

#### Scenario: 验证路径分级

- **GIVEN** 某 external 子集任务可本地轻量验证（L1）
- **WHEN** runner 尝试验证
- **THEN** 系统 SHALL 优先走本地 test_command 验证
- **AND** Docker 不可用或内存不足时 L2 路径 SHALL 标记为 `unsupported` 而非伪造结果
- **AND** 子集接入时 SHALL 提供 L3 金补丁自检能力以剔除 flaky/坏实例

### Requirement: 反作弊泄漏披露

benchmark SHALL 对存在反作弊泄漏面的任务集（如 A 轨历史重建任务在完整 git 历史中运行、agent 可见后续提交）在结果页/任务集 manifest 披露泄漏事实，并声明任务集定位（如"回归基线、非公平评测"），不得冒充公平评测。

#### Scenario: A 轨任务披露泄漏

- **GIVEN** 某任务集包含 A 轨历史重建任务
- **WHEN** 评测产出结果页
- **THEN** 结果页 SHALL 披露该任务集的反作弊泄漏面（任务集来源、运行环境、训练 cutoff 未知性）
- **AND** SHALL 声明该 track 定位为回归基线而非公平评测

### Requirement: 评测采样显式化

benchmark-evaluation SHALL 支持显式采样：重复运行次数 `--repeat N` 取 3–5（N>=3 才有 pass^k 意义）；每次运行记录采样参数（`seed`、`temperature`、模型版本）；`seed` 使用固定集合（如 seed 0..N-1）保证可复现；`temperature` 默认 0.2（pass@1 口径）。可复现声明 SHALL 限定在（模型版本、provider、harness）内，部分 provider 不承诺 seed 语义。
> 状态：本 Requirement 已落规格文本；实现归 C2 `evaluation-metrics`（本 change 只落规格，不实现）。


#### Scenario: 采样参数记录

- **GIVEN** 一次带重复运行的评测
- **WHEN** 写入 run artifact
- **THEN** 每轮 SHALL 记录 (temperature, seed, model version)
- **AND** 结果页 SHALL 展示采样参数

### Requirement: 成本与延迟联合展示

benchmark-evaluation SHALL 在结果页并列展示 Pass@1 与成本指标 `$/resolved-task`，并报告 token 缓存命中率（cache hit rate）。成本 SHALL 采用 cache-aware 定价（区分 fresh input / cache read / cache write / output 四档），声明定价表版本与日期，并显式定义 `$/resolved-task` 口径（层内全部 run 总成本含失败 run / resolved 数；仅 LLM token 计费，不含沙箱/CI/计算）。
> 状态：本 Requirement 已落规格文本；实现归 C2 `evaluation-metrics`（本 change 只落规格，不实现）。


#### Scenario: 成本指标展示

- **GIVEN** 一次带统计的评测完成
- **WHEN** 结果页渲染成本
- **THEN** 结果 SHALL 包含 Pass@1 与 `$/resolved-task` 并列
- **AND** SHALL 包含 cache hit rate（按模型、能力层拆分）
- **AND** SHALL 声明定价表版本/日期与成本口径

### Requirement: 失败归因与 fault_owner

benchmark-evaluation SHALL 保留失败 `reason` 分类，并新增正交的 `fault_owner` 维度（`agent`/`task`/`environment`/`unknown`）。fault_owner 标注来源 SHALL 声明（主选人审抽样 + 双人标注 κ 报告，可选强 judge 首标 + 人审抽样校准）；未标注的失败 SHALL 归入 `unknown` 聚合。结果页 SHALL 展示 reason × fault_owner 交叉表。
> 状态：本 Requirement 已落规格文本；实现归 C2 `evaluation-metrics`（本 change 只落规格，不实现）。


#### Scenario: 失败归因交叉表

- **GIVEN** 一次带失败归因的评测
- **WHEN** 结果页渲染失败
- **THEN** 结果 SHALL 按 reason 展示失败模式占比
- **AND** SHALL 展示 reason × fault_owner 交叉表
- **AND** 每个失败 SHALL 可回查到具体任务与运行轮次
- **AND** 未标注 fault_owner 的失败 SHALL 归入 `unknown` 并单独展示

### Requirement: 报告元组结构化披露

benchmark 报告 SHALL 以结构化元组披露运行环境：模型（`model`: name/version/provider/seed 支持）、harness（`harness`: adapter/prompt_version/tools/max_turns/timeout/patch_collection/network on-off）、`task_set_hash`（任务集版本钉住）、grader 版本、成本口径（定价表版本/日期 + cache hit rate）。run artifact SHALL 记录对应字段（task_set_hash、adapter/grader 版本、max_iterations、timeout、network、温度/seed、cache tokens）。
> 状态：本 Requirement 已落规格文本；实现归 C2 `evaluation-metrics`（本 change 只落规格，不实现）。


#### Scenario: 报告元组完整

- **GIVEN** 一次带评测扩展的 benchmark run
- **WHEN** 写入报告/run artifact
- **THEN** 报告 SHALL 包含 model/harness/task_set_hash/grader/成本口径元组
- **AND** 缺失字段 SHALL 保持向后兼容（可空）

### Requirement: SWE-bench 污染披露

引用 SWE-bench 数字时，benchmark 报告 SHALL 携带污染与缺陷披露：OpenAI 2026-02 已弃用 SWE-bench Verified（审计 138 个高失败率实例中 59.4% 有实质缺陷），数字只能作为对照参考、不得作为无保留金标准；披露 SHALL 覆盖子集层面风险（KNOWN_BAD 过滤条数、现有 fixture 偏置、数据集版本与 swebench 包版本钉住）。
> 状态：本 Requirement 已落规格文本；实现归 C2 `evaluation-metrics`（本 change 只落规格，不实现）。


#### Scenario: 结果页污染注记

- **GIVEN** 结果页引用 SWE-bench 数字
- **WHEN** 渲染结果页
- **THEN** 结果页 SHALL 带保留条件域的污染注记
- **AND** SHALL 注明子集过滤与版本钉住信息

### Requirement: 配对比较统计

compare 路径 SHALL 支持配对比较统计：per-task delta + 差异置信区间（paired bootstrap / McNemar）+ win-rate，用于"同任务同 harness 换 agent/模型"的对照展示，不得只给两个点估计。
> 状态：本 Requirement 已落规格文本；实现归 C2 `evaluation-metrics`（本 change 只落规格，不实现）。


#### Scenario: 换 agent 对照

- **GIVEN** 两组 run 在同一任务集、同一 harness 下使用不同 agent/模型
- **WHEN** compare 渲染对照
- **THEN** 结果 SHALL 包含 per-task delta、差异 CI 与 win-rate
- **AND** SHALL 按任务展示逐项差异

### Requirement: SWE-bench 部分成功保留

SWE-bench adapter SHALL 保留 report.json 的部分成功字段（`f2p_rate`/`p2p_rate`/`reward`），失败归因与结果页建立在更细粒度信息上，不得只保留整体 resolved 布尔值。
> 状态：本 Requirement 已落规格文本；实现归 C2 `evaluation-metrics`（本 change 只落规格，不实现）。


#### Scenario: 部分成功字段透传

- **GIVEN** SWE-bench harness 返回 report.json
- **WHEN** adapter 标准化 Verdict
- **THEN** Verdict SHALL 保留 f2p_rate/p2p_rate/reward 字段
- **AND** 结果页 SHALL 展示部分成功档

### Requirement: 小样本统计声明

小样本（N=3–5）下 per-task bootstrap CI 统计意义弱，结果页渲染层 SHALL 添加小样本声明，或仅在 layer/aggregate 层级展示 CI 权重。
> 状态：本 Requirement 已落规格文本；实现归 C2 `evaluation-metrics`（本 change 只落规格，不实现）。


#### Scenario: 小 N 声明

- **GIVEN** 某任务重复运行次数 N 为 3–5
- **WHEN** 结果页渲染 per-task CI
- **THEN** 结果页 SHALL 附带小样本统计声明

### Requirement: 过程效率指标

benchmark-evaluation SHALL 从 trace 记录采集过程效率指标：time-to-first-successful-edit（首次成功编辑耗时）与 exploration fraction（探索占比），作为结果页可选项展示。
> 状态：本 Requirement 已落规格文本；实现归 C2 `evaluation-metrics`（本 change 只落规格，不实现）。


#### Scenario: 过程效率采集

- **GIVEN** 某任务 trace.json 记录了步骤事件
- **WHEN** 结果页渲染过程指标
- **THEN** 结果 SHALL 可展示 time-to-first-successful-edit 与 exploration fraction
