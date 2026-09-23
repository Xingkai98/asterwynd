# dev-workflow-state-machine 规格

## Purpose

定义开发流程状态机，包括 change 生命周期 phase/sub_state 模型、`handoff.json` 全局状态文件 schema、合法流转规则、human review gate 和回退机制。
## Requirements
### Requirement: 工作流事件日志与 handoff.json projection

每个 change 目录下 SHALL 存在一个 `workflow-events.jsonl` 文件，作为该 change 开发流程的权威事实来源。投影分为两代：老世代（归档 change）SHALL 由事件日志 replay 生成 `handoff.json` projection；当代（新 change）SHALL 由事件日志 replay 生成 `workflow-state.json` projection。Agent 不 SHALL 直接编辑投影文件来声明状态变化；所有状态变化 SHALL 通过 CLI 追加事件并重新生成投影。

自本 change 起，**当代 change 的投影刷新 SHALL NOT 产出 `handoff.json`**：`workflow_state.py` 的 `_refresh_workflow_state` SHALL 只写 `workflow-state.json`（#228 层 1）。老世代（gen-1）change 的 `handoff.json` 是其**唯一**投影载体，其刷新行为 SHALL 与修复前保持一致——该分支不属「映射写」。

受保护 artifact 的写入通道（`workflow_state.py` 的 `artifact-event` 与 `review-manifest`）SHALL 以 change 的合法性（change 目录存在且含 `proposal.md`）为前置，SHALL NOT 要求 `handoff.json` 存在。为兼容老世代目标（历史 `spawn` 子 change，只有 `handoff.json` 而无 `proposal.md`），前置 SHALL 接受 `proposal.md` **或** `handoff.json` 任一存在。

目标解析 SHALL 采用**写通道自身**的口径：**active 目录优先，否则回退到 `openspec/changes/archive/<date>-<id>/`**。该回退 SHALL NOT 依赖 `flow status` 的解析。解析结果 SHALL 与查询的 change id 一致——目录名 SHALL 为裸 `<id>` 或 `<date>-<id>`，否则 SHALL 以明确错误拒绝（exit 1），SHALL NOT 把事件或 manifest 写进另一个 change 的目录。`--change` SHALL 只接受裸 change id，SHALL NOT 接受带 `<date>-` 前缀的 id。

对已归档目标，写入 SHALL 落在归档目录内（manifest 落在 `archive/<date>-<id>/reviews/`，事件追加到归档目录的 `workflow-events.jsonl`），SHALL NOT 在 active 路径新建目录。已归档 change 的投影为**只读历史**：对归档目标的写入 SHALL NOT 触发投影刷新，SHALL NOT 在归档目录中产出 `handoff.json` / `workflow-state.json` 等投影文件；写入后 SHALL 只读校验投影与事件日志是否一致，不一致时 SHALL 告警但 SHALL NOT 落盘、SHALL NOT 因此失败。对 active 目标，两条命令成功写入后 SHALL 重新生成投影（只写 `workflow-state.json`），使写入结果可立即被校验。

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

- **WHEN** 对一个无 `handoff.json` 的当代 change 运行 `workflow_state.py artifact-event` 或 `workflow_state.py review-manifest`
- **THEN** 系统 SHALL 成功写入对应事件 / manifest（exit 0）
- **AND** SHALL NOT 因缺少 `handoff.json` 而拒绝
- **AND** 写入后该 change 的投影 SHALL 被重新生成（只落 `workflow-state.json`，不落 `handoff.json`），无需额外运行 `flow status` 即可通过投影一致性校验

#### Scenario: 受保护写通道拒绝非法目标

- **WHEN** 对一个不存在的 change、一个既无 `proposal.md` 也无 `handoff.json` 的目录，或一个路径型 `--change`（绝对路径或含 `/`，非单段 change id）运行 `artifact-event` 或 `review-manifest`
- **THEN** 系统 SHALL 以明确错误退出（exit 1）
- **AND** SHALL NOT 写入任何事件或 manifest
- **AND** SHALL NOT 抛出未捕获的 traceback，也 SHALL NOT 写入仓库外路径

#### Scenario: 老世代 change 的受保护写通道保持可用

- **WHEN** 对一个有 `handoff.json` 的老世代 change（含无 `proposal.md` 的历史 `spawn` 子 change）运行 `artifact-event` 或 `review-manifest`
- **THEN** 系统 SHALL 成功写入（exit 0）
- **AND** 系统 SHALL 刷新其 `handoff.json` 投影（gen-1 的唯一投影载体），行为与修复前保持一致

#### Scenario: 受保护写通道支持已归档 change

- **GIVEN** 一个已归档 change（存在于 `openspec/changes/archive/<date>-<id>/`，active 目录不存在）
- **WHEN** 以该 change id（裸 id）运行 `workflow_state.py artifact-event` 或 `workflow_state.py review-manifest`
- **THEN** 系统 SHALL 成功写入（exit 0），SHALL NOT 报「change 不存在」
- **AND** review manifest SHALL 落在 `archive/<date>-<id>/reviews/`，事件 SHALL 追加到归档目录的 `workflow-events.jsonl`
- **AND** SHALL NOT 在 active 路径 `openspec/changes/<id>/` 新建任何目录或文件
- **AND** 归档目录 SHALL NOT 新增 `handoff.json` / `workflow-state.json` 等投影文件（归档投影为只读历史）
- **AND** 若归档目录中已存在投影且因本次写入与事件日志不一致，系统 SHALL 告警，但 SHALL NOT 因该不一致而失败或落盘

#### Scenario: 受保护写通道拒绝归档语境下的非法 change id

- **WHEN** 对一个已归档 change 运行 `artifact-event` 或 `review-manifest`，且 `--change` 为带 `<date>-` 前缀的 id（如 `2026-09-21-<id>`），或解析出的目录名不是裸 `<id>` / `<date>-<id>`
- **THEN** 系统 SHALL 以明确错误退出（exit 1）
- **AND** SHALL NOT 把事件或 manifest 写进任何 change 目录，也 SHALL NOT 报「change 不存在」以外的误导性成功

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

### Requirement: Review evidence manifest

每个阶段的独立 review report SHALL 绑定机器可验证的 manifest。review report 文件为 `.handoff/<change-id>/<phase>-review.md`，manifest 文件为 `.handoff/<change-id>/<phase>-review-manifest.json`。gate/CI 不得只根据 review report 文本中的 `PASS` 判断审查通过。

存续期（active）change 的 manifest SHALL 在其 `tasks.md` **最终化之后**生成（含归档移动之后的最终 head），使 `tasks_hash` 绑定的是该 change 的最终任务清单而非收尾中途的快照。

`tasks_hash` 的校验 SHALL 按 change 存续期分别处理：**active** change SHALL 校验 `tasks_hash` 与当前 `tasks.md` 一致；**已归档** change SHALL NOT 以 `tasks_hash` 判定失败——`tasks.md` 是贯穿到归档的活文档，其收尾清单项在 manifest 生成后仍会被勾选或补写，故其字节哈希在归档语境下不构成漂移证据。该降级的代价 SHALL 被明示：归档语境**不再检测 `tasks.md` 的任何编辑，含 checkbox 行内的描述级编辑**；承载「审阅了什么」的实质证据是 `report_hash`（审阅报告原文）与 `spec_hash`（当时已冻结的规格 delta）。该降级 SHALL NOT 静默：归档校验的输出 SHALL 可见地说明 `tasks_hash` 已按归档语境跳过（可为汇总行，无需逐 change 逐行）。归档 change 的 manifest 存在性、字段完整性与 `report_hash` / `spec_hash` / git span SHALL 仍被校验。

CI SHALL 对已归档 change 执行 manifest 校验（`check_openspec_artifacts.py --check-archived`），使 change 归档后不脱离校验范围。

#### Scenario: review report 缺少 manifest

- **GIVEN** `.handoff/<change-id>/<phase>-review.md` 存在
- **AND** 对应 review manifest 不存在
- **WHEN** 运行 gate 或项目 artifact checker
- **THEN** 系统 SHALL 拒绝通过
- **AND** SHALL 报告 review manifest 缺失

#### Scenario: manifest 字段和 hash 校验

- **WHEN** 校验 review manifest
- **THEN** manifest SHALL 声明 `schema`、`change_id`、`phase`、`verdict`、`reviewer_run_id`、`base_sha`、`head_sha`、`tasks_hash`、`spec_hash`、`diff_hash`、`report_hash`
- **AND** `verdict` SHALL 为 `PASS`
- **AND** checker SHALL 验证 `report_hash`、`tasks_hash`（**已归档** change 除外，见下述归档 Scenario）、`spec_hash`
- **AND** 当 repo root 是 git repo 时，checker SHALL 验证 `base_sha` / `head_sha` 均为 commit，且 `diff_hash` 匹配 `git diff --binary <base_sha> <head_sha>` 的 sha256

#### Scenario: 归档 change 的 manifest 校验不因 tasks_hash 漂移而失败

- **GIVEN** 一个已归档 change，其 manifest 的 `tasks_hash` 与当前 `tasks.md` 不一致（因收尾清单项在 manifest 生成后被勾选）
- **WHEN** 对归档语境运行 manifest 校验
- **THEN** 系统 SHALL NOT 以 `tasks_hash` 不一致判定失败
- **AND** SHALL 在输出中说明归档语境跳过 `tasks_hash` 校验（该降级不得静默）
- **AND** manifest 存在性、字段完整性、`report_hash`、`spec_hash` 与 git span SHALL 仍被校验，任一不符 SHALL 判定失败

#### Scenario: active change 的 tasks_hash 漂移仍判失败

- **GIVEN** 一个 active（未归档）change，其 manifest 的 `tasks_hash` 与当前 `tasks.md` 不一致
- **WHEN** 对该 change 运行 manifest 校验
- **THEN** 系统 SHALL 判定失败并报告 `tasks hash mismatch`
- **AND** 该判据 SHALL NOT 因归档语境的降级而放宽

### Requirement: Workflow 总开关

`scripts/workflow_methods.json` SHALL 提供 `workflow.enabled` 布尔开关，默认值为 `true`。当其为 `false` 时，workflow automation SHALL 视为未启用：受保护写通道（`artifact-event` / `review-manifest`）SHALL 拒绝写入，PreToolUse 门禁 SHALL NOT 阻止写操作。系统 SHALL 支持本地 resume audit baseline；通过 workflow CLI 禁用 workflow 时 SHALL 记录当前 git `HEAD`，重新启用时 SHALL 对 baseline 之后的非 workflow 管理文件改动执行恢复审计。

自本 change 起，原口径中依赖 `discover` 与 `check_phase_done.py` 的表述 SHALL 移除——此二者随四阶段状态机退役删除。

#### Scenario: workflow 未启用时写通道拒绝

- **GIVEN** `workflow.enabled = false`
- **WHEN** 调用 `workflow_state.py artifact-event` 或 `review-manifest`
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

已删除的子命令 SHALL NOT 再被 guard 的写通道豁免列为合法通道。

#### Scenario: flow status 展示投影

- **WHEN** 运行 `flow status [--change <id>|--all]`
- **THEN** 系统 SHALL 输出各 change 的投影状态（state / milestones / source_event_seq），唯一/默认格式为 JSON
- **AND** 事件文件不一致时 SHALL 提示 stale
- **AND** 投影缺失/损坏/stale 时 SHALL 先用事件 replay 自动重建（只落 `workflow-state.json`，不落 `handoff.json`），重建成功即输出；仅事件不完整导致重建失败时 SHALL 报「事件不完整，检查 seq N」

#### Scenario: 已删子命令不再存在

- **WHEN** 调用 `workflow_state.py flow approve`（或 `advance` / `block` / `confirm`），或调用 legacy 子命令 `discover` / `current` / `validate` / `spawn`
- **THEN** CLI SHALL 以明确错误退出（未知子命令，非零退出），SHALL NOT 静默成功
- **AND** SHALL NOT 产生任何副作用（不写事件、不落投影、不新建 change 目录）

#### Scenario: 受保护路径只准 CLI 写

- **WHEN** agent 直接 Write/Edit `workflow-state.json` 或 `workflow-events.jsonl`
- **THEN** guard SHALL 拦截（exit 2）
- **AND** `flow status` / `policy-*` / `artifact-event` / `review-manifest` CLI 作为合法写通道 SHALL 被 guard 豁免

### Requirement: 开发流程精简为 OpenSpec 主干 + 强制审阅闭环

开发流程 SHALL 精简为「OpenSpec 主干」（proposal → batch-grill-me → worktree → TDD → spec sync → PR）加「实现完成后强制独立 subagent 审阅闭环」。原四阶段状态机仪式（phase/sub_state 推进、handoff.json、gate 停止）SHALL 停用，不再作为开发流程的强制要求。审阅证据 SHALL 存放于 `openspec/changes/<id>/reviews/`（随 change 进 PR，CI 可机械校验）。

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

guard 对 Bash 命令 SHALL 在 is_write 判定之前先扫描受保护路径；对 Write/Edit 的 `file_path` SHALL 先做路径归一化（normpath / 剥离 `./`、解析 `..`）再匹配。已知绕过形态（`echo > file`、`cat <<EOF`、`pathlib.write_text`、`docs/./` 变体）SHALL 被拦截。`workflow_state.py (artifact-event|review-manifest|policy-*|flow status)` 作为合法写通道 SHALL 被豁免，但豁免 SHALL 仅限独立调用（无 `&&`/`;`/`|` 链式、无重定向、无命令替换、无换行）。

自本 change 起，豁免清单 SHALL 收窄为**仅 `flow status`**——已删除的 gate 家族（`flow approve` / `advance` / `block` / `confirm`）SHALL NOT 再被豁免。

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

- **GIVEN** Bash 命令调用 `workflow_state.py flow approve`（或 `advance` / `block` / `confirm`）
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

