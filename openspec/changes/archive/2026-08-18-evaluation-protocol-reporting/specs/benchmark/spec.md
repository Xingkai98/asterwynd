# benchmark 规格（delta）

本文件是 `evaluation-protocol-reporting`（C3）change 对既有 `benchmark` capability 的修订。C2 已在数据/统计/CLI 层实现指标（pass^k/cache-aware 成本/fault_owner/配对比较）；本 change **已实现结果页渲染义务**（C2 spec 边界注记的 9 项披露段 + 能力覆盖矩阵独立 Requirement）、运行协议文档、预算/预检 CLI 与 self_check 自洽门禁。既有 requirements 语义保持兼容。

## MODIFIED Requirements

### Requirement: 渲染可引用的量化结果页

benchmark-evaluation SHALL 把指标汇总渲染为一个可在面试中直接引用的结果页（markdown/HTML），覆盖 Pass@k、均值/标准差、置信区间、延迟分布和 token 成本，并按能力层级组织、保留并展示任务所属评测框架（task_family）。结果页 SHALL 同时渲染披露段：报告元组（model/harness/task_set_hash/grader/成本口径）、SWE-bench 污染注记（保留条件域）、反作弊泄漏披露（A 轨回归基线定位）、reason × fault_owner 交叉表、$/resolved-task + cache hit rate + 定价表版本、f2p/p2p 部分成功档、采样参数（temperature/seed/model version）、小样本声明（N=3–5）、过程效率展示。

#### Scenario: 生成结果页

- **GIVEN** 一次带重复运行和统计的评测完成
- **WHEN** 评测输出结果页
- **THEN** 结果页 SHALL 包含 Pass@k、均值/标准差、置信区间、延迟分布与 token 成本
- **AND** SHALL 按能力层级组织，便于按层引用
- **AND** SHALL 保留并展示任务所属评测框架（task_family）

#### Scenario: 结果页披露段齐全

- **GIVEN** 一次带评测扩展的 benchmark run
- **WHEN** 渲染结果页
- **THEN** 结果页 SHALL 包含报告元组、SWE-bench 污染注记、反作弊泄漏披露、reason × fault_owner 交叉表、$/resolved-task、部分成功档、采样参数、小样本声明与过程效率展示
- **AND** 缺失字段（如旧 run.json）SHALL 渲染兜底占位而不报错

### Requirement: 反作弊泄漏披露

benchmark SHALL 对存在反作弊泄漏面的任务集（如 A 轨历史重建任务在完整 git 历史中运行、agent 可见后续提交）在结果页/任务集 manifest 披露泄漏事实，并声明任务集定位（如"回归基线、非公平评测"），不得冒充公平评测。

#### Scenario: A 轨任务披露泄漏

- **GIVEN** 某任务集包含 A 轨历史重建任务
- **WHEN** 评测产出结果页
- **THEN** 结果页 SHALL 披露该任务集的反作弊泄漏面（任务集来源、运行环境、训练 cutoff 未知性）
- **AND** SHALL 声明该 track 定位为回归基线而非公平评测

### Requirement: 报告元组结构化披露

benchmark 报告 SHALL 以结构化元组披露运行环境：模型（`model`: name/version/provider/seed 支持）、harness（`harness`: adapter/prompt_version/tools/max_turns/timeout/patch_collection/network on-off）、`task_set_hash`（任务集版本钉住）、grader 版本、成本口径（定价表版本/日期 + cache hit rate）。结果页 SHALL 渲染该元组供面试引用。

#### Scenario: 报告元组完整

- **GIVEN** 一次带评测扩展的 benchmark run
- **WHEN** 写入报告/run artifact
- **THEN** 报告 SHALL 包含 model/harness/task_set_hash/grader/成本口径元组
- **AND** 缺失字段 SHALL 保持向后兼容（可空）

## ADDED Requirements

### Requirement: 运行协议文档

benchmark SHALL 提供运行协议文档（`docs/benchmark-run-protocol.md`），定义任务集口径、模型与采样参数、预算上限、对照口径、artifact 布局与自洽门禁，作为评测执行的权威约定。

#### Scenario: 协议文档可执行

- **GIVEN** 开发者要跑一次评测
- **WHEN** 按协议文档执行
- **THEN** 命令 SHALL 可复现（含 repeat/seeds/temperature/budget-cap 参数）
- **AND** artifact 布局 SHALL 与文档一致（run.json/trace.json/summary）

### Requirement: 预算上限可配置可取消

benchmark CLI SHALL 支持 `--budget-cap <USD>` 设置成本上限（建议值 $50，写于运行协议文档），任一轮累计成本超限时停止剩余轮次，并将该轮标记为 `truncated`（新增运行字段）；`--budget-cap 0`（或 `--no-cap`）取消上限。缺省 SHALL 不设上限保持既有行为。

#### Scenario: 预算超限

- **GIVEN** 某轮累计成本超过 `--budget-cap`
- **WHEN** runner 继续执行
- **THEN** 系统 SHALL 停止剩余轮次（已启动的并发任务自然完成，不 cancel）
- **AND** 该轮结果 SHALL 标记为 `truncated`（不伪造通过/失败）

#### Scenario: 取消预算上限

- **GIVEN** 用户传入 `--budget-cap 0` 或 `--no-cap`
- **WHEN** benchmark 命令执行
- **THEN** 系统 SHALL 不设成本上限

### Requirement: 预检命令

benchmark CLI SHALL 支持 `--preflight` 检查环境：Docker daemon 可用性 + 可用内存检测；内存 <8GiB 时提示走 L1 本地轻量路径。预检结果 SHALL 以退出码表达（0=可跑全量、1=内存不足需 L1 降级、2=Docker 不可用）。

#### Scenario: 内存不足提示 L1

- **GIVEN** 当前环境可用内存 <8GiB
- **WHEN** 运行 `--preflight`
- **THEN** 系统 SHALL 提示 Docker 路径可能受限、建议走 L1 本地验证
- **AND** 退出码 SHALL 为 1

### Requirement: 自洽五门禁检查

benchmark SHALL 提供 `self_check` 脚本校验结果自洽性五门禁：同模型同 harness 复现、seed 复现、失败归因闭环（fault_owner + 校准证据 + reason×owner 交叉表）、披露段齐全（污染注记 + 严格 resolved + f2p/p2p 保留 + A 轨泄漏 + 小 N 声明）、报告元组完整。每门禁缺失 SHALL 报告具体项并以非零退出码表达。

#### Scenario: 五门禁全过

- **GIVEN** 一次披露齐全、归因完整、可复现的评测
- **WHEN** 运行 self_check
- **THEN** 五门禁 SHALL 全部通过
- **AND** 退出码 SHALL 为 0

#### Scenario: 门禁缺失报告

- **GIVEN** 某评测缺少 fault_owner 标注
- **WHEN** 运行 self_check
- **THEN** 系统 SHALL 报告「失败归因闭环」门禁缺失具体项
- **AND** 退出码 SHALL 非零
