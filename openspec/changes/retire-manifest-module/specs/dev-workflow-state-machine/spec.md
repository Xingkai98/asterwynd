# dev-workflow-state-machine 规格 delta

## MODIFIED Requirements

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

### Requirement: 开发流程精简为 OpenSpec 主干 + 强制审阅闭环

开发流程 SHALL 精简为「OpenSpec 主干」（proposal → grilling → worktree → TDD → spec sync → PR）加「实现完成后强制独立 subagent 审阅闭环」。原四阶段状态机仪式（phase/sub_state 推进、handoff.json、gate 停止）SHALL 停用，不再作为开发流程的强制要求。审阅证据 SHALL 存放于 `openspec/changes/<id>/reviews/`（随 change 进 PR，CI 可机械校验）。

其中的 grill 环节 SHALL 为「grilling（独立零记忆设计追问）→ 设计阶段审阅闭环（独立零记忆审阅者对抗分析 → verdict → 修 → 按有界批次模型推进（开批 → 全修 → 只做修复验证 → 收口；最多 20 个已收口轮）；能由代码判定的问题用代码给出带证据的答案）→ 停轮确认」，产出 SHALL 记于 `openspec/changes/<id>/reviews/grill-adversarial.md`。该「设计阶段审阅闭环」与实现完成后的 `/review-loop` **同构但对象不同**（前者审设计、后者审代码），二者分属两阶段、SHALL 并存；实现后的 `/review-loop` SHALL NOT 被本环节替代。

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
