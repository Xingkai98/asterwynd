# dev-workflow-state-machine spec delta: grill 环节加固

## MODIFIED Requirements

### Requirement: 开发流程精简为 OpenSpec 主干 + 强制审阅闭环

开发流程 SHALL 精简为「OpenSpec 主干」（proposal → grilling → worktree → TDD → spec sync → PR）加「实现完成后强制独立 subagent 审阅闭环」。原四阶段状态机仪式（phase/sub_state 推进、handoff.json、gate 停止）SHALL 停用，不再作为开发流程的强制要求。审阅证据 SHALL 存放于 `openspec/changes/<id>/reviews/`（随 change 进 PR，CI 可机械校验）。

其中的 grill 环节 SHALL 为「grilling（独立零记忆设计追问）→ 设计阶段审阅闭环（独立零记忆审阅者对抗分析 → verdict → 修 → 再审直到收敛；能由代码判定的问题用代码给出带证据的答案）→ 停轮确认」，产出 SHALL 记于 `openspec/changes/<id>/reviews/grill-adversarial.md`。该「设计阶段审阅闭环」与实现完成后的 `/review-loop` **同构但对象不同**（前者审设计、后者审代码），二者分属两阶段、SHALL 并存；实现后的 `/review-loop` SHALL NOT 被本环节替代。

**审阅门的触发条件 SHALL 为「归档点」，而非「tasks.md 全部勾选」。** 依据：留一条未勾选项即可关闭全部下游门禁，构成绕开路径；而 `AGENTS.md` 强制「实现 PR 必须同时包含归档收尾」，故**归档 commit 是 PR 的最后一个 commit，归档点是唯一必要且充分的评估点**。触发集合 SHALL 为 `--base-ref` diff 中 `--diff-filter=AR`、匹配 `openspec/changes/archive/<date>-<id>/` **且该归档子目录在 base 树不存在**的路径——末条为必需，否则「向既有归档目录补文件」会被误判成本 PR 新归档，从而对陈旧 change 追溯求值。对**本 PR 新归档**的 change，checker SHALL 在其**归档目录**上评估非 docs + 有 spec delta 的审阅证据与内容门槛，SHALL NOT 因 tasks 未全勾而跳过。

**归档目录命名 SHALL 合规**（`archive/<YYYY-MM-DD>-<change-id>/`）：diff 中出现于归档根下但不匹配该命名规则的路径 SHALL 报错，SHALL NOT 静默——否则会落进「既不在 active 也不在归档门」的无人覆盖区。

**部分实现的 active change 仍 SHALL NOT 被要求审阅证据**——`tasks.md` 有未勾选项的在途 change 继续不受拦截（保留原「避免误伤在途 change」口径）。

**未勾选任务 SHALL 显式分类**：closeout 类任务（PR 合入后的动作，结构上在归档时无法完成）SHALL 以 `(post-merge)` 标记标注；未标的未勾选项在归档点评估时 SHALL 报错，SHALL NOT 静默存在。

**完成度证据 SHALL 存在且可证明完成**：归档 change 的 `tasks.md` SHALL 存在，SHALL 含 ≥1 条 checkbox 行，且 SHALL 至少有一条被勾选。三种形态——缺文件、无 checkbox 行（散文/空文件）、全部未勾选（例如把所有项都标 `(post-merge)`）——在归档点 SHALL 各自报错并指明形态，SHALL NOT 静默通过。缺任一，则「不写 checkbox」或「一条都不勾」就与「留一条 `- [ ]`」同构地关掉了完成度维度。

#### Scenario: 实现完成且已归档的 change 提交 PR

- **GIVEN** 一个非 docs change 已实现、已归档到 `openspec/changes/archive/<date>-<id>/`，且该归档路径出现在本 PR 的 `--diff-filter=AR` diff 中
- **WHEN** 运行 artifact checker
- **THEN** 检查器 SHALL 验证 `reviews/building-review.md` 存在
- **AND** 缺审阅证据 SHALL 报错并阻止合入

#### Scenario: 归档 change 的未标未勾任务报错

- **GIVEN** 一个本 PR 新归档的 change，其 `tasks.md` 存在未勾选项且该项**未**标 `(post-merge)`
- **WHEN** 运行 artifact checker
- **THEN** 检查器 SHALL 报错（未勾选任务 SHALL NOT 静默存在）

#### Scenario: 标注 post-merge 的未勾任务被豁免

- **GIVEN** 一个本 PR 新归档的 change，其未勾选项标注了 `(post-merge)`（如「PR 合入后关闭 issue」）
- **WHEN** 运行 artifact checker
- **THEN** 检查器 SHALL 不因其未勾而报错

#### Scenario: 部分实现的 change 不受拦截

- **GIVEN** 一个 change 处于提案或部分实现阶段（tasks.md 有未勾选项），且**不在本 PR 的归档路径中**
- **WHEN** 运行 artifact checker
- **THEN** 检查器 SHALL 不要求审阅证据（避免误伤在途 change）

#### Scenario: 既有归档不被追溯

- **GIVEN** 一个在**过去的** PR 中归档的 change（其归档路径不在本 PR diff 中）
- **WHEN** 运行 artifact checker（含 `--check-archived`）
- **THEN** 检查器 SHALL NOT 要求该 change 补审阅证据或补勾任务

#### Scenario: 向既有归档目录新增文件不被当成新归档

- **GIVEN** 本 PR 向一个**在 base 树中已存在**的归档目录新增了文件（例如补一份 review manifest），该路径以 `A` 出现在 diff 中
- **WHEN** 运行 artifact checker
- **THEN** 检查器 SHALL NOT 把该归档目录的 change 当作本 PR 新归档求值
- **AND** 判据 SHALL 为「该归档子目录在 base 树不存在」，SHALL NOT 仅凭路径匹配正则

#### Scenario: 归档目录命名不合规即报错

- **GIVEN** 本 PR 把 change 移入 `openspec/changes/archive/<id>/`（缺 `YYYY-MM-DD-` 日期前缀）
- **WHEN** 运行 artifact checker
- **THEN** 检查器 SHALL 报错，说明该归档目录命名不合规、无法评估完成度门
- **AND** 该 change SHALL NOT 静默落在「既不在 active 也不在归档门」的无人覆盖区

#### Scenario: 归档点门不因 tasks 未全勾而降级

- **GIVEN** 一个本 PR 新归档的非 docs change，其 `tasks.md` 存在未勾选项且 `reviews/grill-design.md` 不存在
- **WHEN** 运行 artifact checker
- **THEN** 检查器 SHALL 在该归档目录上评估 grill 证据并报缺失
- **AND** 该评估 SHALL NOT 因 tasks 未全勾而静默跳过

#### Scenario: 归档点门与 manifest 校验模式互斥

- **GIVEN** 运行 artifact checker 时带有 `--check-archived`
- **WHEN** 本 PR 的 diff 中含新归档路径
- **THEN** 归档点完成度门 SHALL NOT 被触发（该模式 SHALL 只做既有 manifest 的漂移检测）
- **AND** 单 change 模式（`--change <id>`）SHALL 同样不触发归档点门

#### Scenario: 状态机仪式停用

- **GIVEN** 开发流程精简已生效
- **WHEN** agent 开始新 change 开发
- **THEN** 无需 phase/sub_state 推进、handoff.json 或 gate 停止
- **AND** 开发流程遵循 OpenSpec 主干 + 实现完成后 `/review-loop` 审阅闭环

#### Scenario: 归档 change 需设计阶段审阅证据

- **GIVEN** 一个本 PR 新归档的、非 docs + 属 DESIGN_TYPES（feature/refactor/process）+ 有 spec delta 的 change（bugfix/research 不走 grill，故豁免本门）
- **WHEN** 运行 artifact checker
- **THEN** 检查器 SHALL 验证 `reviews/grill-adversarial.md` 存在
- **AND** 缺失 SHALL 报错（归档点要求设计阶段审阅闭环证据）

#### Scenario: grill 环节含设计阶段审阅闭环

- **GIVEN** 一个非平凡 change 完成 grilling 并产出 `reviews/grill-design.md`
- **WHEN** 进入停轮确认前
- **THEN** SHALL 先运行设计阶段审阅闭环（独立零记忆审阅者，对抗分析 → verdict → 修 → 再审直到收敛），产出 `reviews/grill-adversarial.md`
- **AND** 该闭环与实现完成后的 `/review-loop` 同构但对象不同（审设计 vs 审代码）
- **AND** 实现后的 `/review-loop` SHALL 继续存在，不被本闭环替代
