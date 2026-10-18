# dev-workflow-state-machine 规格

## Purpose

定义开发流程状态机，包括 change 生命周期 phase/sub_state 模型、`handoff.json` 全局状态文件 schema、合法流转规则、human review gate 和回退机制。
## Requirements

### Requirement: 工作流事件日志与 handoff.json projection

每个 change 目录下 SHALL 存在一个 `workflow-events.jsonl` 文件，作为该 change 开发流程的权威事实来源。投影分为两代：老世代（归档 change）SHALL 由事件日志 replay 生成 `handoff.json` projection；当代（新 change）SHALL 由事件日志 replay 生成 `workflow-state.json` projection。Agent 不 SHALL 直接编辑投影文件来声明状态变化；所有状态变化 SHALL 通过 CLI 追加事件并重新生成投影。

自本 change 起，**当代 change 的投影刷新 SHALL NOT 产出 `handoff.json`**：`workflow_state.py` 的 `_refresh_workflow_state` SHALL 只写 `workflow-state.json`（#228 层 1）。老世代（gen-1）change 的 `handoff.json` 是其**唯一**投影载体，其刷新行为 SHALL 与修复前保持一致——该分支不属「映射写」。

受保护 artifact 的写入通道（`workflow_state.py` 的 `artifact-event`）SHALL 以 change 的合法性（change 目录存在且含 `proposal.md`）为前置，SHALL NOT 要求 `handoff.json` 存在。为兼容老世代目标（历史 `spawn` 子 change，只有 `handoff.json` 而无 `proposal.md`），前置 SHALL 接受 `proposal.md` **或** `handoff.json` 任一存在。

目标解析 SHALL 采用**写通道自身**的口径：**active 目录优先，否则回退到 `openspec/changes/archive/<date>-<id>/`**。该回退 SHALL NOT 依赖 `flow status` 的解析。解析结果 SHALL 与查询的 change id 一致——目录名 SHALL 为裸 `<id>` 或 `<date>-<id>`，否则 SHALL 以明确错误拒绝（exit 1），SHALL NOT 把事件写进另一个 change 的目录。`--change` SHALL 只接受裸 change id，SHALL NOT 接受带 `<date>-` 前缀的 id。

对已归档目标，写入 SHALL 落在归档目录内（事件追加到归档目录的 `workflow-events.jsonl`），SHALL NOT 在 active 路径新建目录。已归档 change 的投影为**只读历史**：对归档目标的写入 SHALL NOT 触发投影刷新，SHALL NOT 在归档目录中产出 `handoff.json` / `workflow-state.json` 等投影文件；写入后 SHALL 只读校验投影与事件日志是否一致，不一致时 SHALL 告警但 SHALL NOT 落盘、SHALL NOT 因此失败。对 active 目标，该命令成功写入后 SHALL 重新生成投影（只写 `workflow-state.json`），使写入结果可立即被校验。

`workflow_state.py review-manifest` 写通道 SHALL 已删除（`retire-manifest-module` 第二刀）：它不是合法子命令，调用 SHALL 以未知子命令失败（非零退出），SHALL NOT 写入任何 manifest 或事件。

#### Scenario: 当代 change 投影为 workflow-state.json

- **WHEN** change 的事件日志以 `change_created` 开头（当代事件，无 handoff.json）
- **THEN** 系统 SHALL 由其事件 replay 生成 `workflow-state.json`
- **AND** 投影 SHALL 包含 `state`、`milestones` 与 `source_event_seq`（投影来源的最大事件 seq）
- **AND** 投影 SHALL 不包含 `updated_at` 字段

#### Scenario: 老世代 change 仍可投影

- **WHEN** change 的事件日志以 `initialized` 开头且存在 `handoff.json`（老世代，归档 change）
- **THEN** replay SHALL 沿用既有 handoff.json projection 路径，不抛错
- **AND** 与修复前行为保持一致

#### Scenario: 任意 change 可查询状态

- **WHEN** 对任一 change（老或新世代）运行 `flow status`
- **THEN** 系统 SHALL 输出该 change 的投影状态（state / milestones / source_event_seq）
- **AND** SHALL 不要求首事件为 `change_created`（容忍异构派生）

#### Scenario: 新建 change 时初始化 workflow event log

- **WHEN** 创建新的 OpenSpec change
- **THEN** 系统 SHALL 自动生成 `workflow-events.jsonl`
- **AND** 当代 change 的初始状态 SHALL 为 `planning.exploring`
- **AND** 当代 change SHALL NOT 被要求生成 `handoff.json`（其状态由 `workflow-state.json` 投影承载）
- **AND** 老世代 change 的 `handoff.json` 生成行为 SHALL 与修复前保持一致

#### Scenario: 投影被手动篡改

- **GIVEN** `workflow-events.jsonl` replay 的当前状态与磁盘投影不一致（老世代为 `handoff.json`，当代为 `workflow-state.json`）
- **WHEN** 运行 CI 校验
- **THEN** 系统 SHALL 拒绝通过
- **AND** SHALL 报告该投影与事件日志不一致

#### Scenario: 非状态 artifact 事件

- **WHEN** `workflow-events.jsonl` 包含不改变 workflow state 的 artifact 事件
- **THEN** replay 投影时 SHALL 保留事件日志顺序校验
- **AND** SHALL 忽略这些事件对投影的影响
- **AND** 支持的 artifact event type SHALL 至少包含 `protected_artifact_explained`、`current_spec_synced`、`backlog_updated`、`change_archived`

#### Scenario: 自愈不再产出 handoff.json

- **WHEN** 对一个当代 change 运行 `flow status` 且其投影缺失/损坏/stale
- **THEN** 系统 SHALL 由事件 replay 重建并落盘 `workflow-state.json`
- **AND** 该 change 目录 SHALL NOT 新增 `handoff.json`

#### Scenario: 受保护写通道不要求 handoff.json

- **WHEN** 对一个无 `handoff.json` 的当代 change 运行 `workflow_state.py artifact-event`
- **THEN** 系统 SHALL 成功写入对应事件（exit 0）
- **AND** SHALL NOT 因缺少 `handoff.json` 而拒绝
- **AND** 写入后该 change 的投影 SHALL 被重新生成（只落 `workflow-state.json`，不落 `handoff.json`），无需额外运行 `flow status` 即可通过投影一致性校验

#### Scenario: 受保护写通道拒绝非法目标

- **WHEN** 对一个不存在的 change、一个既无 `proposal.md` 也无 `handoff.json` 的目录，或一个路径型 `--change`（绝对路径或含 `/`，非单段 change id）运行 `artifact-event`
- **THEN** 系统 SHALL 以明确错误退出（exit 1）
- **AND** SHALL NOT 写入任何事件
- **AND** SHALL NOT 抛出未捕获的 traceback，也 SHALL NOT 写入仓库外路径

#### Scenario: 老世代 change 的受保护写通道保持可用

- **WHEN** 对一个有 `handoff.json` 的老世代 change（含无 `proposal.md` 的历史 `spawn` 子 change）运行 `artifact-event`
- **THEN** 系统 SHALL 成功写入（exit 0）
- **AND** 系统 SHALL 刷新其 `handoff.json` 投影（gen-1 的唯一投影载体），行为与修复前保持一致

#### Scenario: 受保护写通道支持已归档 change

- **GIVEN** 一个已归档 change（存在于 `openspec/changes/archive/<date>-<id>/`，active 目录不存在）
- **WHEN** 以该 change id（裸 id）运行 `workflow_state.py artifact-event`
- **THEN** 系统 SHALL 成功写入（exit 0），SHALL NOT 报「change 不存在」
- **AND** 事件 SHALL 追加到归档目录的 `workflow-events.jsonl`
- **AND** SHALL NOT 在 active 路径 `openspec/changes/<id>/` 新建任何目录或文件
- **AND** 归档目录 SHALL NOT 新增 `handoff.json` / `workflow-state.json` 等投影文件（归档投影为只读历史）
- **AND** 若归档目录中已存在投影且因本次写入与事件日志不一致，系统 SHALL 告警，但 SHALL NOT 因该不一致而失败或落盘

#### Scenario: 受保护写通道拒绝归档语境下的非法 change id

- **WHEN** 对一个已归档 change 运行 `artifact-event`，且 `--change` 为带 `<date>-` 前缀的 id（如 `2026-09-21-<id>`），或解析出的目录名不是裸 `<id>` / `<date>-<id>`
- **THEN** 系统 SHALL 以明确错误退出（exit 1）
- **AND** SHALL NOT 把事件写进任何 change 目录，也 SHALL NOT 报「change 不存在」以外的误导性成功

### Requirement: Protected artifact 变更解释

工作流保护的项目级 artifact 被修改时，CI/gate SHALL 要求对应 `workflow-events.jsonl` 中存在结构化解释事件。解释事件 SHALL 包含 `artifact_path`、`reason`、`approved_by` 和匹配的 `change_id`，不得只依赖自然语言对话或手写无证据 review 文本。受保护路径清单 SHALL 从 `scripts/flow-policy.json` 中 `governance == event_explained` 的规则子集加载（flow-policy-source P0 单一策略源），checker 不保留独立硬编码清单；策略文件缺失/损坏时 checker SHALL fail-closed。

#### Scenario: known issues/debt 文档变更

- **GIVEN** PR diff 修改 `docs/known-issues.md` 或 `docs/known-debt.md`
- **WHEN** 运行项目 artifact checker
- **THEN** checker SHALL 要求存在 `protected_artifact_explained` 事件
- **AND** 事件的 `artifact_path` SHALL 覆盖被修改路径

#### Scenario: current spec 变更

- **GIVEN** PR diff 修改 `openspec/specs/**`
- **WHEN** 运行项目 artifact checker
- **THEN** checker SHALL 要求存在 `current_spec_synced` 事件
- **AND** 事件 SHALL 说明该 current spec 由哪个已批准变更同步而来

#### Scenario: backlog 变更

- **GIVEN** PR diff 修改 `docs/openspec-change-backlog.md`
- **WHEN** 运行项目 artifact checker
- **THEN** checker SHALL 要求存在 `backlog_updated` 事件
- **AND** 事件 SHALL 说明 backlog 更新发生在 closing 收尾语境中

#### Scenario: archive 变更

- **GIVEN** PR diff 修改 `openspec/changes/archive/**`
- **WHEN** 运行项目 artifact checker
- **THEN** checker SHALL 要求存在 `change_archived` 事件
- **AND** archive 目录名为 `YYYY-MM-DD-<change-id>` 时，事件 `change_id` SHALL 使用原始 `<change-id>`

### Requirement: Workflow 总开关

`scripts/workflow_methods.json` SHALL 提供 `workflow.enabled` 布尔开关，默认值为 `true`。当其为 `false` 时，workflow automation SHALL 视为未启用：受保护写通道（`artifact-event`）SHALL 拒绝写入，PreToolUse 门禁 SHALL NOT 阻止写操作。系统 SHALL 支持本地 resume audit baseline；通过 workflow CLI 禁用 workflow 时 SHALL 记录当前 git `HEAD`，重新启用时 SHALL 对 baseline 之后的非 workflow 管理文件改动执行恢复审计。

自本 change 起，原口径中依赖 `discover` 与 `check_phase_done.py` 的表述 SHALL 移除——此二者随四阶段状态机退役删除。

#### Scenario: workflow 未启用时写通道拒绝

- **GIVEN** `workflow.enabled = false`
- **WHEN** 调用 `workflow_state.py artifact-event`
- **THEN** 系统 SHALL 以明确错误拒绝（exit 1）

#### Scenario: workflow 未启用时门禁退化

- **GIVEN** `workflow.enabled = false`
- **WHEN** PreToolUse 门禁运行
- **THEN** 系统 SHALL NOT 阻止写操作

#### Scenario: 禁用期间存在未恢复改动

- **GIVEN** workflow CLI 禁用 workflow 时已写入 resume baseline
- **AND** baseline 之后存在非 workflow 管理文件改动
- **WHEN** workflow 被重新启用或 agent 运行 `resume-audit`
- **THEN** 系统 SHALL 报告需要 resume audit reconciliation
- **AND** 系统 SHALL 阻止 workflow 被重新启用（`enable` 以非零退出），直到改动被归入某个 change

#### Scenario: 禁用期间改动被恢复确认

- **GIVEN** baseline 之后存在非 workflow 管理文件改动
- **WHEN** 人通过 `workflow_state.py resume-audit --reconcile-change <id>` 将改动归入某个 change
- **THEN** 系统 SHALL 向该 change 的 `workflow-events.jsonl` 追加 `resume_audit_reconciled` 事件
- **AND** 事件 SHALL 记录 `baseline_sha`、`head_sha`、`changed_paths_hash`、`changed_paths`、`reason` 和 `approved_by`
- **AND** replay 投影时 SHALL 忽略该非状态事件

### Requirement: 阻塞状态

系统 SHALL 在投影层保留 awaiting 态建模：awaiting 态 SHALL 建模为 `blocked` phase 的 sub_state（如 `blocked.awaiting_proposal_confirmation`），普通 `blocked`（非 awaiting）sub_state 为 null；awaiting 态集合 SHALL 包含 `awaiting_proposal_confirmation`、`awaiting_human_review` 与 `awaiting_user_confirmation`；`review_blocked` 不 SHALL 计入 awaiting 集。等待合法化不弱化执法：awaiting 期间写操作 SHALL 仍被 guard 拦截（exit 2）。

自本 change 起，awaiting 态的**进入 / 解除 CLI 通道已随四阶段状态机退役删除**（`flow block` / `flow confirm` / `flow approve`）：`blocked_entered` 与 `blocked_resolved` 事件不再有 CLI 写入者。guard 的 awaiting 执法**保留且不弱化**——处于 `blocked.awaiting_*` 的 change 仍会被门禁拦截写操作。该残留面（执法保留但无 CLI 解除通道）SHALL 记录于 `docs/known-debt.md`。

#### Scenario: checker 派生物一致性

- **WHEN** 项目 artifact checker 校验 change
- **THEN** 它 SHALL 校验磁盘投影（`workflow-state.json`）与从事件 replay 重建的投影一致（投影 == replay）
- **AND** 不一致时 SHALL 失败（exit 2），防止自锁

#### Scenario: guard 读投影执法

- **WHEN** guard 判断某 change 处于 awaiting 态且未确认
- **THEN** 写操作（Write/Edit 与 write-intent Bash）SHALL exit 2（awaiting 执法不弱化，不可经 Bash 绕过）
- **AND** guard SHALL 以事件日志 replay 结果判定 awaiting（事件是唯一真相）：投影缺失/损坏/stale 不影响判定——awaiting 仍 exit 2（不因投影问题放行）、非 awaiting 放行（不额外误拦）
- **AND** guard SHALL 只读，不写盘（hook 无副作用）
- **AND** 仅事件不完整（缺 seq / JSON 语法坏 / 末尾截断）导致无法 replay 时，guard SHALL fail-closed（exit 2，报「事件不完整，检查 seq N」）；`flow status` 同口径报错，不猜测不跳过

### Requirement: flow 命令与受保护路径

`workflow_state.py` 的 `flow` 子命令组 SHALL 仅保留 `flow status`（投影查询）。原 gate 家族子命令（`flow approve` / `flow advance` / `flow block` / `flow confirm`）SHALL 删除，因为四阶段状态机已停用且它们无生产调用方。`workflow-state.json` 与 `workflow-events.jsonl` SHALL 纳入受保护路径（governance=cli_written），只允许 CLI 写入。

已删除的子命令 SHALL NOT 再被 guard 的写通道豁免列为合法通道。`review-manifest` 子命令 SHALL 已删除（`retire-manifest-module` 第二刀）；调用它 SHALL 视为未知子命令。

#### Scenario: flow status 展示投影

- **WHEN** 运行 `flow status [--change <id>|--all]`
- **THEN** 系统 SHALL 输出各 change 的投影状态（state / milestones / source_event_seq），唯一/默认格式为 JSON
- **AND** 事件文件不一致时 SHALL 提示 stale
- **AND** 投影缺失/损坏/stale 时 SHALL 先用事件 replay 自动重建（只落 `workflow-state.json`，不落 `handoff.json`），重建成功即输出；仅事件不完整导致重建失败时 SHALL 报「事件不完整，检查 seq N」

#### Scenario: 已删子命令不再存在

- **WHEN** 调用 `workflow_state.py flow approve`（或 `advance` / `block` / `confirm`）、调用 legacy 子命令 `discover` / `current` / `validate` / `spawn`，或调用 `review-manifest`
- **THEN** CLI SHALL 以明确错误退出（未知子命令，非零退出），SHALL NOT 静默成功
- **AND** SHALL NOT 产生任何副作用（不写事件、不落投影、不新建 change 目录、不写 manifest）

#### Scenario: 受保护路径只准 CLI 写

- **WHEN** agent 直接 Write/Edit `workflow-state.json` 或 `workflow-events.jsonl`
- **THEN** guard SHALL 拦截（exit 2）
- **AND** `flow status` / `policy-*` / `artifact-event` CLI 作为合法写通道 SHALL 被 guard 豁免

### Requirement: 开发流程精简为 OpenSpec 主干 + 强制审阅闭环

开发流程 SHALL 精简为「OpenSpec 主干」（proposal → grilling → worktree → TDD → spec sync → PR）加「实现完成后强制独立 subagent 审阅闭环」。原四阶段状态机仪式（phase/sub_state 推进、handoff.json、gate 停止）SHALL 停用，不再作为开发流程的强制要求。审阅证据 SHALL 存放于 `openspec/changes/<id>/reviews/`（随 change 进 PR，CI 可机械校验）。

其中的 grill 环节 SHALL 为「grilling（独立零记忆设计追问）→ 设计阶段审阅闭环（独立零记忆审阅者对抗分析 → verdict → 修 → 按有界批次模型推进（开批 → 全修 → 只做修复验证 → 收口；最多 20 个已收口轮）；能由代码判定的问题用代码给出带证据的答案）→ 停轮确认」，产出 SHALL 记于 `openspec/changes/<id>/reviews/grill-adversarial.md`。该「设计阶段审阅闭环」与实现完成后的 `/review-loop` **同构但对象不同**（前者审设计、后者审代码），二者分属两阶段、SHALL 并存；实现后的 `/review-loop` SHALL NOT 被本环节替代。

**审阅门的触发条件 SHALL 为「归档点」，而非「tasks.md 全部勾选」。** 依据：留一条未勾选项即可关闭全部下游门禁，构成绕开路径；而 `AGENTS.md` 强制「实现 PR 必须同时包含归档收尾」，故**归档 commit 是 PR 的最后一个 commit，归档点是唯一必要且充分的评估点**。触发集合 SHALL 为 `--base-ref` diff 中 `--diff-filter=AR`、匹配 `openspec/changes/archive/<date>-<id>/` **且该归档子目录在 base 树不存在**的路径——末条为必需，否则「向既有归档目录补文件」会被误判成本 PR 新归档，从而对陈旧 change 追溯求值。对**本 PR 新归档**的 change，checker SHALL 在其**归档目录**上评估非 docs + 有 spec delta 的审阅证据与内容门槛，SHALL NOT 因 tasks 未全勾而跳过。

**默认 base 解析 SHALL 代表本 PR。** `--base-ref` 未显式提供时，checker SHALL 优先以 `origin/master` 与 `HEAD` 的 merge-base 作为 diff base（`origin/master` 可解析时；merge-base 不可用则退回 `origin/master`），否则回退到与 `master` 的 merge-base；非空显式提供的 `--base-ref` SHALL 保持原有两点 diff 语义、SHALL NOT 被默认解析覆盖；空/纯空白显式值 SHALL 按未提供处理，SHALL NOT 静默跳过归档点 diff 与受保护路径 diff。解析结果 SHALL 同时用于归档点 diff 与受保护路径 diff。该三点语义 SHALL 保证分支落后于 `origin/master` 时，上游已合入的受保护路径改动 SHALL NOT 被反向列为本分支改动。历史归档 SHALL NOT 因本地默认分支（如陈旧的本地 `master`）而出现在本 PR 的 AR diff 中并被追溯求值；两个候选 ref 都不可解析时 SHALL 沿用既有 `--require-base` 的 fail-closed / warning 语义。

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

#### Scenario: 裸跑不追溯历史归档

- **GIVEN** 本地 `master` 落后 `origin/master`，HEAD 与 `origin/master` 一致或仅含本 PR 提交
- **AND** 历史归档中存在缺少 `## 闭环出口` 的报告
- **WHEN** 运行 artifact checker 且未显式提供 `--base-ref`
- **THEN** checker SHALL 以 `origin/master` 与 `HEAD` 的 merge-base 作为默认 base（三点语义）
- **AND** 历史归档 SHALL NOT 被当作本 PR 新归档求值
- **AND** 分支落后于 `origin/master` 时，上游受保护路径改动 SHALL NOT 被反向列为本分支改动
- **AND** 新建归档缺 `## 闭环出口` 仍 SHALL 报错

#### Scenario: 显式 base 不被默认解析覆盖

- **GIVEN** 调用方显式传入 `--base-ref master`
- **WHEN** 运行 artifact checker
- **THEN** checker SHALL 使用 `master` 作为两点 diff base，SHALL NOT 替换为默认解析结果（merge-base / `origin/master`）

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
- **THEN** 归档点完成度门 SHALL NOT 被触发（该模式 SHALL 只做归档事件日志可投影校验，SHALL NOT 做 manifest 漂移检测）
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
- **THEN** SHALL 先运行设计阶段审阅闭环（独立零记忆审阅者，对抗分析 → verdict → 修 → 按有界批次模型验证直到收口），产出 `reviews/grill-adversarial.md`
- **AND** 该闭环与实现完成后的 `/review-loop` 同构但对象不同（审设计 vs 审代码）
- **AND** 实现后的 `/review-loop` SHALL 继续存在，不被本闭环替代

### Requirement: 开发流程策略单一源

受保护路径治理规则 SHALL 收敛到单一策略文件 `scripts/flow-policy.json`，作为 guard（PreToolUse hook）与 CI artifact checker 的共同规则来源。该文件 SHALL 以 JSON 承载受保护路径规则表，每条规则 SHALL 声明 `match_type(exact|prefix|contains)`、`governance(guard_only|event_explained|manifest_verified|cli_written)` 与可空 `event_types`。系统 SHALL 禁止 agent 直接改写该策略文件（governance=cli_written），仅允许人类直改或 `policy-*` CLI 子命令更新。

#### Scenario: guard 与 checker 同源加载受保护路径规则

- **WHEN** guard 或 checker 需要判断某路径是否受保护
- **THEN** 系统 SHALL 从 `scripts/flow-policy.json` 读取规则表，而不再使用各自硬编码的独立清单
- **AND** guard 与 checker 对同一路径 SHALL 得出一致的受保护判定

#### Scenario: 策略文件缺失或损坏时 guard fail-closed

- **GIVEN** `scripts/flow-policy.json` 缺失、损坏或非法
- **WHEN** guard 拦截代码写操作
- **THEN** guard SHALL fail-closed（exit 2），不得静默放行
- **AND** guard SHALL 在错误信息中指明策略文件问题与恢复方向

#### Scenario: 策略文件规则与 guard 内嵌默认表保持一致

- **WHEN** 运行 parity 测试
- **THEN** 磁盘上的 `flow-policy.json` 规则表 SHALL 与 guard 源码内嵌的默认规则表一致
- **AND** checker 的受保护路径规则集 SHALL 是策略表 `event_explained` 子集

### Requirement: guard 写操作门禁顺序与路径归一化

guard 对 Bash 命令 SHALL 在 is_write 判定之前先扫描受保护路径；对 Write/Edit 的 `file_path` SHALL 先做路径归一化（normpath / 剥离 `./`、解析 `..`）再匹配。已知绕过形态（`echo > file`、`cat <<EOF`、`pathlib.write_text`、`docs/./` 变体）SHALL 被拦截。`workflow_state.py (artifact-event|policy-*|flow status)` 作为合法写通道 SHALL 被豁免，但豁免 SHALL 仅限独立调用（无 `&&`/`;`/`|` 链式、无重定向、无命令替换、无换行）。

自本 change 起，豁免清单 SHALL 收窄为**仅 `flow status`**——已删除的 gate 家族（`flow approve` / `advance` / `block` / `confirm`）SHALL NOT 再被豁免。`review-manifest` 子命令 SHALL 已删除，同样 SHALL NOT 被豁免。

#### Scenario: Bash 命令绕过受保护路径被拦截

- **GIVEN** Bash 命令尝试改写受保护 artifact 但未命中既有写模式（如 `cat <<EOF`、`python3 -c "Path(...).write_text(...)"`）
- **WHEN** 命令具有写意图且包含受保护路径
- **THEN** guard SHALL 拦截（exit 2），不受 is_write 判定前置影响

#### Scenario: 归一化变体写入受保护路径被拦截

- **GIVEN** Write/Edit 或 Bash 使用 `docs/./known-debt.md` 等归一化变体路径
- **WHEN** 目标指向受保护 artifact
- **THEN** guard SHALL 在路径归一化后拦截（exit 2）

#### Scenario: 特权 CLI 链式调用不被豁免

- **GIVEN** Bash 命令以 `workflow_state.py` 合法子命令开头但通过 `&&`、`;`、`|` 或换行链式拼接写命令
- **WHEN** 该命令尝试改写受保护 artifact
- **THEN** guard SHALL 拒绝豁免并拦截（exit 2）

#### Scenario: 已删 gate 子命令不再被豁免

- **GIVEN** Bash 命令调用 `workflow_state.py flow approve`（或 `advance` / `block` / `confirm`），或调用已删除的 `review-manifest`
- **WHEN** guard 判定该命令是否为豁免的合法写通道
- **THEN** guard SHALL NOT 豁免它（与子命令已删除的事实一致）

### Requirement: 内容门槛阶段感知

CI artifact checker 对 `Reference Implementation Research` 字段的检查 SHALL 区分结构门槛与内容门槛：change 处于 proposal 阶段时 SHALL 只要求 section 存在且非空；当 change **在本 PR 归档**时 SHALL 额外执行**两**项内容检查——(1)「自认未完成」短语级模式，命中 SHALL 报错（exit 2）并指明命中短语与字段；(2) **`research_tier` 与 `status` 的闭环校验**：`research_tier: full|light` 时 `status` SHALL 为 `enabled`，`research_tier: exempt` 时 `status` SHALL 为 `disabled` 且 `reason` SHALL 命中结构性豁免关键词或引用证据（`#<数字>` 或 `docs/`、`openspec/changes/archive/`、`reviews/` 路径），违反 SHALL 报错。

（原触发条件「tasks 全部勾选（实现完成）」SHALL 改为「本 PR 归档」——与本 change 的审阅门触发条件对齐；未归档的 active change SHALL 仍只按结构门槛检查。）

#### Scenario: 归档的 change 含自认未完成占位

- **GIVEN** 一个本 PR 新归档的 change
- **WHEN** 其 Reference Implementation Research 字段包含「尚未完成」「待补充」等自认未完成短语
- **THEN** checker SHALL exit 2
- **AND** 错误信息 SHALL 指明命中短语与所在字段

#### Scenario: 归档的 change 的 tier 与 status 不闭环

- **GIVEN** 一个本 PR 新归档的 change，其 Reference Implementation Research 声明 `research_tier: exempt` 而 `status: enabled`
- **WHEN** checker 在该归档目录上求值内容门槛
- **THEN** checker SHALL 报错，指明 `research_tier: exempt` 在归档时 `status` 必须为 `disabled`
- **AND** 该检查 SHALL NOT 因该 change 的 tasks 未全勾而被跳过

#### Scenario: proposal 阶段含占位不触发内容门槛

- **GIVEN** 一个 change 处于 proposal 阶段或尚未归档
- **WHEN** 其 Reference Implementation Research 字段含占位文本
- **THEN** checker SHALL 只按结构门槛检查（section 存在 + 非空），不触发内容门槛报错

### Requirement: 阶段执行者 agent schema 定义

`scripts/flow-policy.json` SHALL 支持可选的 `phases.<phase>.agent = {provider, model}` 与顶层 `review.agent` 声明，用于表达每阶段与审阅节点的执行者选择。本 requirement 只定义 schema 并做结构校验，不实现按阶段 spawn 执行者（后续阶段实现）。

#### Scenario: 合法 agent schema 通过校验

- **GIVEN** `flow-policy.json` 声明 `phases.building.agent` 或 `review.agent`，字段为合法 provider/model 字符串
- **WHEN** 运行 artifact checker
- **THEN** checker SHALL 通过 schema 校验

#### Scenario: 非法 agent schema 被拒绝

- **GIVEN** `flow-policy.json` 声明未知 phase 键、非字符串 provider/model 或额外未知字段
- **WHEN** 运行 artifact checker
- **THEN** checker SHALL 报错并指明非法字段

### Requirement: 审阅闭环的轮次模型为有界批次，最多 20 个已收口轮

实现后的 `/review-loop` 与设计阶段的审阅闭环 SHALL 使用同一套有界批次轮次模型。**一轮** SHALL
定义为一个**非空 medium+ 批次**的完整闭环：审阅者开批 → 开发者全修 → 审阅者只做修复验证 →
全部通过 ⇒ 本轮结束；下一轮才开新一批（含 deferred）。单次审阅意见、单次修复提交、单次验证
SHALL NOT 各自计为一轮。

**批次**：一轮开始时审阅者 SHALL 只把 severity 为 `blocker` / `high` / `medium` 的问题
（合称 medium+）列入批次 `B_n`；开批时发现的 `low` / `nit` SHALL 直接进入本轮 low/nit
登记表，不进入阻塞批次。批次 `B_n` 在开批后 SHALL 冻结——本轮内 SHALL NOT 增加、删除或
替换成员，severity SHALL 随批次冻结。`B_n = ∅` ⇒ 审阅闭环 SHALL 以 `PASS` 结束，不进入
修复，也不消耗轮数。

**全修**：开发者 SHALL 修完 `B_n` 的每一项。实现环每项 SHALL 附一条**能变红的回归测试**
（先红后绿）；设计环的对应物 SHALL 是可复现反例 / 一条改前失败、改后通过的文档守卫 /
逐条决策记录（三选一），SHALL NOT 填 `N/A`。

**修复验证**：审阅者 SHALL 只逐条确认 `B_n` 每一项是否修好；未修好 ⇒ 开发者继续修，
**仍是同一轮**，SHALL NOT 另计一轮。**验证重试的终止点**：同一项被再次（第二次及以后）判
`未修好`、且开发者拿不出**新的、可验证的修复方案**时，审阅者 SHALL 以 `BLOCKED` + 成因终结
（记录验证次数、每次的修复提交与测试）；第一次判 `未修好` 时开发者就明确拿不出新方案，也立即
触发。「新的、可验证的修复方案」= 实现环：新 commit + 一条修复前红、修复后绿的回归测试
（或可复现失败的命令）；设计环：具体文本修改 + 可复现反例 / 文档守卫 / 逐条决策记录。
**若上述终止点发生在第 20 轮，出口是超上限 `BLOCKED`，不是通用 `BLOCKED`**。

**验证期禁提新问题**：验证阶段 SHALL 只做「当前批次逐项是否修好」的确认。审阅者在验证期间
发现的任何**新**问题 SHALL：

- severity 为 medium+ ⇒ 写入本轮报告的 `deferred`（下一批）清单，**不得**当场要求修复，
  **不得**扩大 `B_n`；
- severity 为 low / nit ⇒ 写入本轮报告的 low/nit 登记表。

验证期间若审阅者确认 low/nit 登记表里的某项实际是 medium+，它 SHALL 从 low/nit 表移到
`deferred`，**不得**当场加入当前批次。验证阶段的唯一允许变化是：`B_n` 各项的验证状态、
`deferred` 清单、low/nit 登记表；批次成员 SHALL 保持不变。**例外不是「新问题」**：若该新问题使当前轮的验证失去意义，或继续实现/验证
本身不安全 ⇒ SHALL 以 `BLOCKED` + 成因终结；其余安全漏洞 SHALL 进 `deferred`。所有 deferred
medium+ 的「延后理由」列 SHALL 写「为什么可以延后一轮」；安全项额外写「为什么晚一轮仍安全」。

**deferred 传递**：下一次开批 SHALL 先读上一轮的 `deferred` 与 low/nit 表；每个 deferred
medium+ SHALL 以**原 id** 出现在下一轮批次，或出现在本轮 `BLOCKED` 的成因里。

**severity 与处置**：medium+ SHALL 全部修完并验证通过，SHALL NOT 以「登记不修」放行。
low / nit SHALL NOT 阻塞本轮收口或 `PASS`；可修，也可登记不修，但报告 SHALL 逐条写明理由。
severity SHALL 由审阅者定级；开发者 SHALL NOT 自行把 medium+ 降级以跳过修复。验证期若审阅者
认为定级错误，只能二选一：（a）按原 severity 要求修完；或（b）`BLOCKED` 并把争议写进成因；
SHALL NOT 静默把批次项移出批次或降为 low/nit。最终 `PASS` 报告 SHALL 携带**累积** low/nit
登记表，或逐项链接到首次登记的轮次小节。

**20 轮上限**：审阅闭环 SHALL 最多存在 **20 个已收口的轮**（`B_n` 全部验证通过的轮；
`BLOCKED` / 超上限 `BLOCKED` 的终结态不计入）。轮数 SHALL 按 **change（且按环）** 累计；
后续报告 SHALL 保留前序轮次，或引用同一份叠写报告；换审阅者 run / 另写一份从第 1 轮开始的
新报告 SHALL NOT 重置计数。重置计数只能来自用户的明确裁决，并 SHALL 记为 `BLOCKED` /
建议重开设计。第 20 轮自身达到验证重试终止点 ⇒ SHALL 以**超上限 `BLOCKED`**
终结。第 20 轮收口后、收口确认前 SHALL NOT 开启第 21 轮或做修复；审阅者 SHALL 做一次
**收口确认**（下一次开批）：批次为空 ⇒ `PASS`；批次非空 ⇒ **超上限 `BLOCKED`**，附第 20 轮
账本与未收口 medium+ 列表，SHALL NOT 开启第 21 轮修复。超上限报告 SHALL 明确写
「**建议推倒重开（revise the design）**」，其停轮原因 SHALL 表述为「20 轮有界修复仍未收口，
说明问题在设计层」，SHALL NOT 表述为「到轮数就停」或「照合交人」。

**零轮 PASS 与 id**：初次开批（第 0 轮）为空 ⇒ `PASS`；报告 SHALL 写
`### 初次开批 · 收口确认`，low/nit 用 `R0-<序号>`。第 20 轮收口后的收口确认若发现 medium+
⇒ 超上限 `BLOCKED`，标识用 `C-<序号>`（或 `R20-C<序号>`）；若只发现 low/nit ⇒ 仍可
`PASS`，同样用 `C-<序号>`。一般批次项 id SHALL 形如 `R<首次出现轮次>-<序号>`；deferred 项
进入下一轮批次时 SHALL 沿用原 id。多轮同文件时，每轮小节标题 SHALL 带轮次（例：
`### 第 3 轮 · 批次`），以便第三方只读相邻轮次即可复核。

**报告形态**：每轮报告 SHALL 至少包含（轮内 verdict 与闭环出口分开）：

1. **本轮判定（verdict）**：`PASS` / `CHANGES_REQUESTED` / `BLOCKED`（轮内可见，不是终结出口）；
2. **批次表**：`id` / severity / 锚点（`文件:行`）/ 问题；
3. **验证表**：`id` / 结果（已修好 / 未修好）/ 修复提交 / 回归测试或设计环对应物；
4. **deferred 表**：`id` / severity / 锚点 / 问题 / 来源 / 延后理由；
5. **low/nit 登记表**：`id` / severity / 处置（已修 / 登记不修）/ 理由（累积或链接）；
6. **收口确认**：`### 第 <n> 轮后 · 收口确认`；`PASS` 出口 SHALL 引用这一节；`BLOCKED` /
   超上限 `BLOCKED` 报告 SHALL NOT 伪造收口确认，改记「终止状态 / 验证账本 / 未通过项」；
7. **闭环出口**：只在终结时填 `PASS` / `BLOCKED`（成因）/ 超上限 `BLOCKED`（建议重开设计）；
   轮内写「未定」。

**三种出口**：审阅闭环的终结态 SHALL 只有：

| 出口 | 条件 |
|---|---|
| `PASS` | 收口确认批次为空（含初次开批） |
| `BLOCKED` + 成因 | 阻塞性缺陷 / 同一批反复无法收口（验证重试终止点）；停下报告、不自行修复 |
| 超上限 `BLOCKED` | 20 个轮已收口且收口确认仍有 medium+，或第 20 轮自身达到验证重试终止点；附「建议推倒重开（revise the design）」 |

`CHANGES_REQUESTED` SHALL NOT 被视为出口；它只表示「本批仍有未验证通过的项」，对应动作是
继续修 / 继续验证。

**两环共用**：设计阶段对抗环与实现后 `/review-loop` SHALL 使用同一套轮次模型（批次 / 验证 /
deferred / 20 / 三出口）。设计环的 `BLOCKED` 成因映射 SHALL 为：核心需求缺失 / 设计自相矛盾 /
依赖不可满足 / 同一批反复无法收口；作者负责改该 change 的设计制品：`design.md`、`proposal.md`、
`specs/<capability>/spec.md`、`tasks.md`，以及决策记录 `grill-design.md`。**设计环的出口
SHALL 是实现的前置条件**：设计环以 `BLOCKED` 终结时 SHALL NOT 作为写码许可；只有设计环
`PASS`，或 `BLOCKED` + 成因 + **用户明确裁决继续**，才允许进入实现。用户裁决 SHALL 记入
`grill-design.md` 的 `## User Confirmation`（或 `## Blocked Ruling`）。

**frontier 豁免**：grill 的 frontier 追问轮 SHALL 仅指**进入对抗环之前**、为求设计树完备而做
的内部轮；它 SHALL NOT 算作审阅轮，SHALL NOT 受 20 上限或「验证禁提新问题」约束。由对抗环
批次项驱动的设计探索属于该轮修复，SHALL NOT 改标为 frontier。

**机械门禁**：本模型 SHALL NOT 新增轮次 / 批次 / deferred 等正文解析。两侧既有判据分别为：

- **witnessloop `check`**：change 契约件、review manifest / 报告 / revision / hash /
  `reviewer_run_id != author_run_id`、孤儿报告，以及 `stage=grill` 的既有正文完备性判据；
- **`scripts/check_openspec_artifacts.py`**：building review 的终结 `## 闭环出口` PASS 判据
  （见 `Review evidence 与终结 verdict`）、受保护写入解释事件与归档点完成度门；
  `retire-manifest-check` 起不再校验 review manifest 字段 / hash。

两侧 SHALL NOT 解析报告正文里的批次、severity、轮数、deferred 或 low/nit 理由
（`stage=grill` 的既有正文判据与 `## 闭环出口` 的 PASS 门另计）。20 上限、批次冻结、
deferred 都是**流程规定**，不是机械判据；`check` 绿只证明既有证据判据通过，不证明报告
按本模型执行。

#### Scenario: 第 1 轮验证不通过 ⇒ 继续修，不另计轮

- **GIVEN** 第 1 轮批次为 A/B/C（均为 medium+）
- **WHEN** 开发者修完 A/B/C，审阅者复验发现 A/B 已修好、C 未修好
- **THEN** 本轮不结束；开发者继续修 C；C 修好并复验通过后，本轮结束
- **AND** 轮数仍为 1；第 2 轮仅在开新批次时开始

#### Scenario: 验证期发现新 medium+ ⇒ 只进 deferred

- **GIVEN** 第 3 轮批次 `B_3` 有 4 项，验证到第 2 项时发现一个 medium+ 新问题
- **WHEN** 审阅者写本轮报告
- **THEN** 该新问题只出现在 `### 第 3 轮 · 下一批（deferred）`；`B_3` 仍为 4 项
- **AND** 第 3 轮批次全部验证通过后，本轮结束；该新问题进入第 4 轮批次

#### Scenario: 下次开批必须携带上一轮 deferred

- **GIVEN** 第 3 轮 deferred 表含 `R3-2`
- **WHEN** 第 4 轮开批
- **THEN** `R3-2` SHALL 以原 id 出现在第 4 轮批次，或出现在本轮 `BLOCKED` 的成因里

#### Scenario: 开批为空 ⇒ PASS（零轮）

- **GIVEN** 初次开批没有发现任何 medium+，但有 2 条 low/nit
- **WHEN** 判定出口
- **THEN** 以 `PASS` 结束；报告写 `### 初次开批 · 收口确认`，low/nit 用 `R0-1` / `R0-2`

#### Scenario: medium+ 写成「登记不修」⇒ 不合格

- **GIVEN** 批次里有一条 severity = medium 的项，开发者标为「登记不修」
- **WHEN** 审阅者验证
- **THEN** 该项 SHALL 判为**未修好**；本轮不结束，直到它被修完并验证通过

#### Scenario: 第 20 轮收口后仍有 medium+ ⇒ 超上限 BLOCKED

- **GIVEN** 第 1–20 轮均已收口；收口确认发现 2 条 medium+（id 用 `C-1` / `C-2`）
- **WHEN** 判定出口
- **THEN** **超上限 `BLOCKED`**；报告含「建议推倒重开（revise the design）」与那 2 条问题
- **AND** 不会开始第 21 轮修复

#### Scenario: 第 20 轮收口后批次为空 ⇒ PASS

- **GIVEN** 第 1–20 轮均已收口；收口确认没有 medium+
- **WHEN** 判定出口
- **THEN** `PASS`——收口确认不占第 21 轮，也不把「第 20 轮」改写成停轮理由

#### Scenario: 第 20 轮自身达到验证重试终止点 ⇒ 超上限 BLOCKED

- **GIVEN** `B_20` 有 1 项，第二次验证仍为 `未修好`，开发者拿不出新的可验证修复方案
- **WHEN** 判定出口
- **THEN** **超上限 `BLOCKED`**；报告含「建议推倒重开（revise the design）」+ 第 20 轮账本
- **AND** 不会开启第 21 轮，也不会退化成不带「建议重开」的通用 `BLOCKED`

#### Scenario: 本批仍有未通过项 ⇒ 不是出口

- **GIVEN** 第 5 轮批次尚有 1 项未修好
- **WHEN** 写报告
- **THEN** 报告可以写 `CHANGES_REQUESTED` 作为轮内状态，但 `## 闭环出口` 写「未定」
- **AND** SHALL NOT 据此停下交人，除非命中 `BLOCKED` 的成因

#### Scenario: grill frontier 的内部轮不占 20

- **GIVEN** grill 为求 frontier 为空内部走了 5 轮追问
- **WHEN** 进入设计对抗环
- **THEN** 对抗环仍从第 1 轮开始计数；frontier 的 5 轮不占 20 上限

#### Scenario: 对抗环的验证期发现新问题

- **GIVEN** 设计对抗环第 2 轮批次已全部修完，验证时又发现一条必须修改
- **WHEN** 审阅者写报告
- **THEN** 该条进 deferred，进入第 3 轮批次；不得当场扩第 2 轮批次

#### Scenario: 第 20 轮第一次未修好但开发者有新方案 ⇒ 同轮继续

- **GIVEN** `B_20` 有 1 项，第一次验证判 `未修好`，开发者提交了新 commit + 先红后绿的回归测试
- **WHEN** 判定出口
- **THEN** **不是**超上限 `BLOCKED`；继续第 20 轮修复/验证（同轮，不另计轮）

#### Scenario: 验证期把 low 重分类为 medium+ ⇒ 进 deferred

- **GIVEN** low/nit 登记表里有一项，验证期间审阅者确认它实际是 medium+
- **WHEN** 写本轮报告
- **THEN** 它 SHALL 从 low/nit 表移到 `deferred`，**不得**当场加入当前批次

### Requirement: Review evidence 与终结 verdict

实现完成与归档点的审阅证据 SHALL 由 witnessloop 形态 manifest 与 building review 报告共同承载，本仓 SHALL NOT 再要求 asterwynd 形态 manifest。witnessloop 形态 manifest（`reviews/<stage>.manifest.json`）SHALL 是唯一被要求的 review manifest；本仓 checker 的 manifest 字段 / hash / git span 校验 SHALL 移除。

building review 报告 SHALL 在 `reviews/building-review.md` 中以二级标题 `## 闭环出口` 记录终结 verdict。解析规则 SHALL 为：标题以 `闭环出口` 为前缀即命中（容忍中文括号后缀，`###` 级不命中）；fenced code（` ``` ` / `~~~`）内的标题与 token SHALL 被忽略；只认该小节**首个非空行**，剥掉行首 list/bold/引用符/反引号标记后该行 SHALL 以 `PASS` / `BLOCKED` / `CHANGES_REQUESTED` 之一开头，且首个 token 后 SHALL 紧跟行尾/空白/`（`/`(`/`：`/`:` 等终止符（`PASSED` 不合规），首个 token 之后 SHALL NOT 出现 `|` 分隔的其它终结 token（官方模板占位行 `PASS | BLOCKED（…） | BLOCKED（…）` 不合规）；`PASS（此前 CHANGES_REQUESTED 已收口）` SHALL 视为合法；报告中出现多个 `## 闭环出口` 小节 SHALL 报错。终结出口 SHALL 为 `PASS` 才视为审阅通过；该判据只覆盖 building review，非 building 的 `*-review.md` PASS 门随旧 manifest 校验退役并由 known-debt 登记。

本仓 checker SHALL 在两类触发面机械校验：

- **宽触发（terminal 非 PASS）**：只要 `reviews/building-review.md` 存在且出口首个 token 为 `BLOCKED` / `CHANGES_REQUESTED`，SHALL 报错，SHALL NOT 区分 change 类型、spec delta 或 `tasks.md` 勾选状态；
- **完成面（必须 PASS）**：**active** 侧为非 docs、有 spec delta、且 `tasks.md` 全部勾选的 change；**归档点**为本 PR `--diff-filter=AR` 新建、在 base 树不存在、且**有 spec delta** 的非 docs 归档 change。完成面 SHALL 要求出口小节存在且为 `PASS`；`未定` 或小节缺失只在完成面报错。

**在完成面上**，小节缺失、首个非空行不以任何终结 token 开头、或以非 `PASS` token 开头 SHALL 报错，SHALL NOT 静默通过；**宽触发只对 terminal 非 `PASS` 报错**，不因 `未定` 或缺小节报错。多个同名小节 SHALL 在任何触发面都报错（见解析规则第 4 条）。该判据 SHALL NOT 扩大到历史归档报告，SHALL NOT 解析轮次、severity、deferred 或 low/nit 内容；`design-review.md` 等非 building 报告不在本判据覆盖面。

#### Scenario: PASS 出口通过

- **GIVEN** 一个实现完成的非 docs change，`tasks.md` 全部勾选
- **AND** `reviews/building-review.md` 含 `## 闭环出口`，首个非空行以 `PASS` 开头（允许 `PASS（...）` 说明）
- **WHEN** 运行项目 artifact checker
- **THEN** checker SHALL NOT 报告审阅证据错误
- **AND** SHALL NOT 要求 `reviews/<phase>-review-manifest.json`

#### Scenario: 非 PASS 出口被拒

- **GIVEN** `reviews/building-review.md` 的 `## 闭环出口` 首个非空行以 `BLOCKED` 或 `CHANGES_REQUESTED` 开头
- **WHEN** 运行项目 artifact checker
- **THEN** 系统 SHALL 判定失败并报告出口不是 `PASS`

#### Scenario: 完成面上出口缺失、无效或多小节被拒

- **GIVEN** 一个**完成面** change（非 docs、有 spec delta、`tasks.md` 全部勾选）
- **AND** `reviews/building-review.md` 没有 `## 闭环出口` 小节，或首个非空行为 `未定` / `不是 PASS` / `PASSED` / 模板占位行 `PASS | BLOCKED（…） | BLOCKED（…）`，或出现多个同名小节
- **WHEN** 运行项目 artifact checker
- **THEN** 系统 SHALL 判定失败并报告「缺少闭环出口」「出口未填 / 不以终结 token 开头」「出口不唯一」或「闭环出口小节不唯一」

#### Scenario: fenced code 中的示例不参与判定

- **GIVEN** `reviews/building-review.md` 在 fenced code 中引用了 `## 闭环出口` 与 `BLOCKED` 的模板文本
- **AND** 真正的 `## 闭环出口` 小节首个非空行以 `PASS` 开头
- **WHEN** 运行项目 artifact checker
- **THEN** fenced code 内的标题与 token SHALL 被忽略
- **AND** checker SHALL 判定通过

#### Scenario: partial change 的未终结报告不被误伤

- **GIVEN** 一个非 docs change 有 spec delta，但 `tasks.md` 仍有未勾选项
- **AND** `reviews/building-review.md` 存在且出口为 `未定` 或没有 `## 闭环出口`
- **WHEN** 运行项目 artifact checker
- **THEN** checker SHALL NOT 因该报告报错（完成面才触发）

#### Scenario: 宽触发覆盖 docs / 无 spec delta / partial

- **GIVEN** 一个 docs change、一个无 spec delta 的 process change，或一个 `tasks.md` 未全勾的 change
- **AND** 其 `reviews/building-review.md` 存在且出口首个 token 为 `BLOCKED` 或 `CHANGES_REQUESTED`
- **WHEN** 运行项目 artifact checker
- **THEN** checker SHALL 判定失败（宽触发，不看类型 / spec delta / 勾选状态）

#### Scenario: 归档点完成面要求 spec delta，宽触发不看

- **GIVEN** 一个本 PR 新归档的非 docs change 没有 spec delta
- **WHEN** 运行归档点完成度门
- **THEN** SHALL NOT 要求 `## 闭环出口` 存在（完成面不触发）
- **AND** 若其 `building-review.md` 存在且出口为 terminal 非 PASS，SHALL 仍按宽触发报错

#### Scenario: 历史归档不追溯

- **GIVEN** 一个早于本 change 的归档 change，其 `building-review.md` 没有 `## 闭环出口`
- **WHEN** 运行 `--check-archived`
- **THEN** checker SHALL NOT 因该历史报告格式报错
- **AND** SHALL NOT 校验其历史 asterwynd 形态 manifest
