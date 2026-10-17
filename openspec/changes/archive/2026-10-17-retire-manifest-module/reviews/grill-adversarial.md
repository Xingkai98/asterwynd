# Grill Adversarial: retire-manifest-module

## Reviewer
- run id: adversarial-rmm-r1-20261017
- 时间: 2026-10-17

### 第 1 轮 · 批次

| id | severity | 锚点 | 问题 |
|---|---|---|---|
| A1 | medium | `README.md:264`；`README_EN.md:264`；`openspec/changes/retire-manifest-module/proposal.md:50-51`、`:115-121`；`openspec/changes/retire-manifest-module/tasks.md:42`、`:58` | 删除面漏掉 README 双语：`README.md:264` / `README_EN.md:264` 的目录树仍把 `workflow/` 描述为「开发流程状态机 + 事件日志 + **review manifest**」/「Dev-workflow state machine + event log + **review manifest**」；模块删除后该能力已不在 `agent/workflow/`，陈述变假。Impact Analysis 与 tasks 3.1-3.6 均未列 README（proposal 的 Requirement 4 只列「测试、AGENTS.md、openspec/specs/**、docs/**」，README 不在其中）。且 3.7/5.5 的验收 grep 是 `review[-_]manifest`，匹配不到空格形态 `review manifest`，所以强制复核也抓不到。修法：把 `README.md` / `README_EN.md` 加入 Impact Analysis 与 tasks（按 AGENTS.md 的规则同一变更内双语同步），改树注释（如「事件日志 + 受保护写通道」），并把 grep 扩为 `review[-_ ]manifest`（或补一条空格形态的 grep）。 |
| A2 | medium | `openspec/changes/retire-manifest-module/design.md:66-78`；`tasks.md:21`、`:28`；`tests/test_workflow_archive_write_channel.py:262-281` | Decision 2 / 任务 2.2 明确引入两个**新行为**：内联 helper 用 `fullmatch`（替代无 `$` 锚点的 `re.match`）、同一 id 命中多个日期目录时 fail-closed；但测试策略只写「保留 `test_archived_resolution_rejects_longer_prefixed_sibling`」。该用例只断言 `returncode == 1` 且兄弟目录未被写：旧的 `re.match` + 调用侧 `_archive_dir_matches_change_id` 断言同样 exit 1（错误文案是「目录名与 change id 不匹配」），因此它**不能区分** helper 是否真的改成 `fullmatch`；「同 id 多日期目录 ⇒ 明确错误」这条新分支则**零覆盖**。这违反仓库「bug fix 必须新增回归测试」的纪律，也让 `docs/known-debt.md` A-遗留 2 的关闭缺少判别性证据。修法：在兄弟前缀用例中断言 stderr 含「不存在」（旧路径产出的是「不匹配」，新路径才是「不存在」），并新增一个 archive 下同时存在 `2026-01-01-<id>/` 与 `2026-02-02-<id>/` 的用例，断言 exit 1、明确的多匹配错误、且两个目录都未被写入。 |
| A3 | medium | `openspec/changes/retire-manifest-module/design.md:194-196`；`tasks.md:22-23`；`tests/test_retire_manifest_check.py:333-356` | 文档守卫的扩展在删除前**本来就是绿的**，tasks 1.7「运行指定测试确认红」对这一组无法成立：按 design 钉的 marker（`workflow_state.py review-manifest` **带后续参数**、`agent.workflow.review_manifest`）实测扫描 `NORMATIVE_DOCS`，当前 7 个文件里「带参数调用」0 命中、「dotted import」0 命中（唯一裸调用是 `AGENTS.md:115` 的「作为 legacy 通道保留」，不带参数，当然也不构成使用指示）；同时该守卫没有阳性对照，正则写错或过窄会永久假绿。修法：(a) 明确把这组登记为「面向未来的回归守卫，不是红→绿」，并在报告里如实记录；(b) 加阳性对照（对一份含 `workflow_state.py review-manifest --change x` 的临时文本/样例断言守卫会报错），证明 marker 有判别力；(c) 若确实要求红→绿，改为上下文感知判据（命中调用形态时允许同句含「已删除/退役」），使其今天就在 `AGENTS.md:115` 判红、清理后转绿。 |
| A4 | medium | `openspec/changes/retire-manifest-module/design.md:95-100`、`:187-188`；`tasks.md:29`；`scripts/flow-policy.json:3`、`:66-69`；`scripts/workflow_state.py:604-647`、`:714-720`；`scripts/workflow_guard.py:583-616`；`openspec/specs/dev-workflow-state-machine/spec.md:312` | 任务 2.3 要求「策略说明标注 `manifest_verified` 当前无规则使用」，但 `scripts/flow-policy.json` 是 `governance=cli_written`：agent 的 Write/Edit 被 guard 拦截（`workflow_guard.py:608-616`），Bash 直写也被拦，而唯一的合法 CLI 通道 `policy-set` 只增删改 `protected_paths` 条目（`workflow_state.py:616-647`），**没有**修改顶层 `_description` 的入口。因此这条任务在现有通道下**不可由 agent 合法执行**：照字面做只能跳过（任务撒谎）或直接改受保护文件（违反 spec `:312` 的「仅允许人类直改或 policy-* CLI 更新」）。修法三选一并写清：① 去掉 `_description` 改动，把「`manifest_verified` 无规则使用」只写进 `docs/known-debt.md`（已有该任务与事件通道）；② 显式标注为 human 手动步骤；③ 扩展 `policy-set` 支持元数据（属功能扩展，会给「纯删除」变更加面，不建议）。 |

### 第 1 轮 · 验证

| id | 结果 | 修复落点 |
|---|---|---|
| A1 | 已修 | `proposal.md:50-52,120`（Requirement 4 与 Impact 加入 `README.md:264` / `README_EN.md:264`，双语同改）；`tasks.md:36`（3.1 同步双语目录树）；`tasks.md:42,58` 与 `design.md:186-187` 的复核 grep 已扩为 `review[-_ ]manifest`（能命中空格形态）；`design.md:186-187` Testing Strategy 补 README 双语条目。 |
| A2 | 已修 | `design.md:72-79`（删除不可达的 `_archive_dir_matches_change_id` 调用侧断言；兄弟前缀用例额外断言「不存在」且与旧「不匹配」路径区分；新增同 id 多日期目录 fail-closed 用例）；`design.md:179-181`（checker/解析层同步）；`tasks.md:21`（1.5 两条用例落点）与 `tasks.md:28`（2.2 删除断言、fullmatch、多匹配 fail-closed）。 |
| A3 | 已修 | `tasks.md:22`（1.6 守卫判据：调用/导入形态 + 同句含「已删除 / 已退役 / 不存在」放行 + 阳性/阴性对照单测）；`tasks.md:23`（1.7 明确当前红点 = `AGENTS.md:115`）；`design.md:174-175,202-205`（Testing Strategy 与风险段同步，含对照锁定判别力）。 |
| A4 | 已修 | `design.md:100-103`（Decision 4 明确 `_description` **不改**，原因：`cli_written` 文件、`policy-set` 无顶层说明入口）；`design.md:195-196`（Risks 同步）；`tasks.md:29`（2.3 改为不改 `_description`，`manifest_verified` 无规则使用只记 known-debt）；`tasks.md:40`（3.5 保留 known-debt 记录义务）。 |

低风险项 L1–L8 的修复落点也已逐项核实：L1 `design.md:210`（7 条）；L2 `proposal.md:121`、`tasks.md:37`（`:324`）；L3 `tasks.md:73`（8.1 更新 `:116`）；L4 `proposal.md:28`；L5 `specs/dev-workflow-state-machine/spec.md:165`；L6 `tasks.md:18`（排除 `.venv/.dev/.git`）；L7 `tasks.md:42`（docstring 逐处改准）；L8 `design.md:72`、`tasks.md:28`（删除不可达断言）。

验证同时复核：`openspec validate retire-manifest-module --strict` 通过；`check_openspec_artifacts.py --base-ref origin/master --require-base` 通过。

### 第 1 轮 · 下一批（deferred）

无。

### low/nit 登记表

L1–L8 均已在第 1 轮修复中处置（落点见「第 1 轮 · 验证」）；下表保留原登记口径，并追加验证期新增的低风险项（v-L*）。

| id | severity | 处置 | 理由 |
|---|---|---|---|
| L1 | low | 登记不修（改一行即可，建议顺带修） | `design.md:202` 写「8 条 Confirmed Decisions」，`reviews/grill-design.md` 实际 7 条（`:9-15`）。计数口径不一致。 |
| L2 | low | 登记，实现时顺手覆盖 | Impact Analysis 把 development-guide 的改动面写成 `:294-300`，但同一「Review evidence 纪律」节在 `docs/development-guide.md:324` 还有「历史 manifest 的处置留给第二刀」，同样会变假；行号范围不完整。 |
| L3 | low | 登记，收尾时顺带更新 | `docs/openspec-change-backlog.md:116` 现写「第二刀已立项」；本 change 归档后应改为「已完成并归档」，但 tasks 8.1 只说了登记/移除条目，没有这条 summary 行的更新。 |
| L4 | low | 登记（措辞） | proposal 定位「纯删除 + 收尾，不加功能」（`proposal.md:28`），而 Decision 2 顺带修了 `change_dir_for` 的前缀碰撞并新增多匹配 fail-closed（行为变化）。design 的 Risks 已承认，但定位句建议改为「纯删除 + 收尾，附一处已知解析缺陷的收口」，避免读者按字面判断范围。 |
| L5 | low | 登记（规范措辞） | state-machine delta（`specs/dev-workflow-state-machine/spec.md:165`）用「豁免清单 SHALL NOT 包含已删除的子命令」替换了 current spec 的「豁免清单 SHALL 收窄为**仅 `flow status`**」（`openspec/specs/dev-workflow-state-machine/spec.md:337`）。语义大体等价，但丢掉更明确的既有约束；建议保留原句并追加 review-manifest。 |
| L6 | low | 登记（测试实现注意） | tasks 1.2 的「全仓 `.py` import 扫描」需要排除 `.venv/`、`.dev/`、`.git/`；否则测试会扫描依赖树（慢）并可能被本地生成物干扰。 |
| L7 | low | 登记，3.7 清理时顺带 | 多处测试 docstring 仍把 manifest 描述为活产物（`tests/test_workflow_state_cli.py:3`、`tests/test_workflow_archive_write_channel.py:4`、`:181-182`、`tests/test_workflow_guard.py:127`、`tests/test_flow_policy.py:142`）。连字符 grep 能抓大部分，但实现时应逐处改准，而不是只压 grep。 |
| L8 | low | 已按删除方案处置 | 内联 helper 用 `fullmatch` 后，调用侧 `_archive_dir_matches_change_id` 的 False 分支在生产路径上不可达（helper 已不可能返回不匹配的目录）。design 说保留作「防御将来解析路径变化」，可以保留，但 docstring 应写明「按当前 helper 构造不可达，仅作防御」，避免读者误以为仍有活覆盖。 |
| v-L1 | low | 登记（验证期措辞） | `tasks.md:22` 仍写 marker「带后续参数形态」，而 `tasks.md:23` 钉的当前红点 `AGENTS.md:115` 是**不带参数**的裸调用提及。两处只有把 marker 实现为「命中调用 token，再按同句退役词放行」才能同时成立；建议把 1.6 的「带后续参数形态」改为「调用 token（含无参数提及）」以消除歧义。 |
| v-L2 | low | 登记（验收措辞） | `tasks.md:90` 的 V2 写「兄弟前缀碰撞**行为不变**」，但 Decision 2 / 1.5 明确错误文案从「不匹配」变为「不存在」。建议改为「fail-closed 结论不变（错误文案可辨）」，避免验收口径与 1.5 冲突。 |
| v-L3 | low | 登记（Impact 措辞） | `proposal.md:93-94` 仍把 `_archive_dir_matches_change_id` 描述为「的 docstring」改动，而 tasks 2.2 已改为**删除**该函数；建议 Impact 同步为「删除 `:327-343` 及调用侧断言」。 |

### 第 1 轮后 · 收口确认

第 1 轮批次 A1–A4 已全部修复并复核通过：批次为空。验证期未发现新的 medium+（deferred 为空）；新增 3 条 low（v-L1–v-L3）只登记、不阻塞。本轮收口。

## 闭环出口

PASS
