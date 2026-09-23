# Tasks — fix-issue-235-completion-gate

## 0. 设计追问（实现前门禁）

- [x] 跑 `batch-grill-me`（或等价设计追问，`/grill`；独立零记忆 subagent）审视 design.md D1–D7，产出 `reviews/grill-design.md`（≥3 条 Confirmed Decisions + Open Questions 停轮确认后写入 `## User Confirmation`）
- [x] **grill 必答（R5 的 7 条观察项作为输入）**：O1–O7 全部经用户逐项拍板，另裁定 3 条新风险（结果见 `reviews/grill-design.md` 的 `## User Confirmation`）：
  - **O3 → 路线 A′**（B 被实跑否决：RIR 内容门与 grill 完整性门的判据本身挂在 `_tasks_all_complete` 上）
  - **O5 → 报错 + known-debt 双写**
  - O1 → 补两条测试（豁免继承 + 触发覆盖）
  - O4 → spec delta 展开为两个子检查（自含未完成短语 + tier/status 闭环）
  - O6 → O6a 保留；O6b 命题换成「旧归档目录新增文件（`A` 路径）→ 不评估」
  - O7 → 更正为 9/3/23
  - 风险② → 采纳「base 树不存在」修正；小a/b/c → 全部采纳

## 实现

- [x] `scripts/check_openspec_artifacts.py`：`main()` 中新增归档点求值（**放在 `if not args.skip_protected_paths:` 块之外**，用 `not args.check_archived and not args.change` 显式守卫）
- [x] 新增 `new_archived_ids` 解析：`git diff --name-only --diff-filter=AR <base>` + 正则 `^openspec/changes/archive/\d{4}-\d{2}-\d{2}-([^/]+)/` + **「该归档子目录在 base 树不存在」判定**（`git ls-tree -d <base>:openspec/changes/archive` 取差集）
- [x] 非规范归档目录（`startswith("openspec/changes/archive/")` 但不匹配日期正则）→ 进 `errors`
- [x] 新门**消费 `--require-base` 语义**（base 不可解析 ∧ require_base → 报错，防浅检出 fail-open）
- [x] 新增归档点门评估（按 D3 裁定的路线）：四道门 + 未勾任务，作用于 `openspec/changes/archive/<date>-<id>/`
- [x] **building-review 只做存在性**（不复用 `_check_review_manifests`——理由经 grill 修正为 active 路径解析，非 `tasks_hash`；manifest 完整性留 CI 第二步）
- [x] **A′ 参数化**：`_check_reference_implementation_research` 与 `_check_design_review_task` 各加 `*, assume_implemented: bool = False`，函数内三处判据（`:585`/`:733`/`:750`）改为 `assume_implemented or _tasks_all_complete(change_dir)`
- [x] 四道门**复用现有判定函数**（继承 docs 豁免 `:508` / DESIGN_TYPES `:712` / `primary != docs` + `_changed_capabilities` `:1029-1031`）
- [x] `_tasks_all_complete` 扫描放宽：覆盖 `[X]`、`+ [ ]`，保留「缩进子项也算」
- [x] 新增 `(post-merge)` tag 解析（正则见 design D4，容忍编号/粗体在前、全半角括号、大小写）
- [x] 未勾任务判定：无 tag 的未勾行进 `errors`；有 tag 的豁免
- [x] **`check_change` 一行不动**（A′：不传 `assume_implemented` → 默认 False → active 行为逐字节不变）

## 测试

- [x] **问题二**：本 PR 新归档 + 缺 `building-review.md` → 门触发
- [x] **问题一**：本 PR 新归档 + 一条无 tag 未勾任务 → 门触发
- [x] 同 fixture 该未勾任务加 `(post-merge)` → 不报
- [x] **tag 语法参数化**：8 变体（`- [ ] (post-merge)` / `- [ ] 5.5 (post-merge)` / `- [ ] **6.9** (post-merge)` / 全角 `（post-merge）` / `(POST-MERGE)` / `+ [ ]` / `* [ ]`）全识别为豁免
- [x] **不反转 `f4a4272`**：`tests/test_openspec_artifact_checker.py:241`（`test_partial_change_does_not_require_building_review`）**原样通过**
- [x] **豁免继承（Q1a）**：docs-only 归档 → 不要求四门
- [x] **触发覆盖（Q1b）**：无 `reviews/` 的非 docs 归档 → 报需要 grill 证据（A′ 判别性断言）
- [x] **不追溯**：既有归档（M 路径）→ 不触发；`--check-archived` → 不触发；`--change <id>` → 不触发
- [x] **旧归档目录新增文件（`A` 路径）→ 不评估该旧 id**（风险②判别性测试）
- [x] **AR 的必要性**：纯 rename 归档（`R100`）→ 仍取到 id
- [x] **非规范归档目录 → 报错**
- [x] **`--skip-protected-paths` 不关新门**
- [x] **fail-closed**：base 不可解析 ∧ `--require-base` → 新门报错
- [x] **O6a**：有 `building-review.md` 但无 manifest → 第一步过、第二步报 `review manifest missing`
- [x] 四道门**各自独立断言**（防"只实现了一道"）
- [x] 变异验证：去掉 AR 改 A → rename 用例红；去掉 tag → 豁免用例红；去掉「base 树不存在」→ 旧归档用例红；把新门挂到 `--check-archived` → 不追溯用例红
- [x] 全量 `uv run pytest -q` + OpenSpec strict validate + artifact checker + `--check-archived`

## 文档

- [x] `AGENTS.md`：`(post-merge)` tag 约定（closeout 任务）+ 更新门禁描述（触发条件从「全勾」改「归档点」）
- [x] `docs/development-guide.md`：tag 语法与用途（含"为什么需要"）
- [x] `docs/known-debt.md`：残余面（「实现 PR 完全不归档」+ 无日期前缀归档面），配 `protected_artifact_explained` 事件
- [x] spec delta：`dev-workflow-state-machine` MODIFIED 2 条（审阅门触发 + 内容门槛触发），**完整正文**
- [x] **当前规格同步**：delta 合入 `openspec/specs/dev-workflow-state-machine/spec.md`（`current_spec_synced` 事件）
- [x] `docs/openspec-change-backlog.md`：登记本 change + 收尾移除（`backlog_updated` 事件 ×2）
- [x] 关键词扫描 `docs/`、`AGENTS.md` 中与「tasks 全勾 / 完成度门禁 / building-review 触发」相关的段落

## 审阅闭环

- [x] `/review-loop` 独立零记忆 subagent 审阅 → PASS 或 3 轮封顶
- [x] 生成 review manifest（绑归档后最终 head）

### R1 审阅发现与修复（独立零记忆 subagent `3ce1e878`，CHANGES_REQUESTED）

核心功能经对方实跑确认成立（两条绕开路径都堵住、4 条变异各自只让对应用例转红），修复以下 4 项：

- [x] **M1（medium，fail-open）**：归档目录缺 `tasks.md`、或 tasks.md 无任何 checkbox 行（散文/空文件）时，
      `_untagged_unchecked_tasks` 返回空 ⇒ 完成度维度静默通过。这与「留一条 `- [ ]` 自我关闸」同构
      （靠「不写 checkbox」而非「不勾 checkbox」）。修复：新增 `_tasks_missing_evidence`，非 docs 新归档
      在缺证据时报错。回归测试：`test_archived_gate_flags_missing_tasks_md` +
      `test_archived_gate_flags_tasks_md_without_checkbox_lines`（参数化散文/空文件两形态）
- [x] **low-1（假阳性）**：非规范归档判定过宽——`archive/.gitkeep` 这类归档根下的普通文件被判成
      「归档目录命名不合规」，且该分支不受「base 树不存在」约束（触碰历史非规范目录会红）。
      修复：新增 `ARCHIVE_DIR_SEGMENT_RE`，只对「有目录段」的路径评命名。回归测试：
      `test_archived_gate_does_not_flag_plain_file_under_archive_root` +
      `test_archived_gate_still_flags_non_dated_archive_directory`（防修成 fail-open）
- [x] **low-3（证据污染）**：本 change 改了受保护文件 `docs/known-debt.md`，但 HEAD 上**没有自己的**
      `protected_artifact_explained` 事件——CI 绿只因 checker 全仓 rglob 撞上别的 change 的陈旧事件。
      修复：写入本 change 自己的事件（seq 2）；回归测试
      `test_own_change_explains_protected_artifact_with_its_own_event`（去掉事件即转红，已验证）。
      该机制弱点本身（收窄为「只认本 change 的事件」）已记 `docs/known-debt.md`
- [x] **info（写法提示）**：tag 必须紧邻复选框，行尾追加写法不被识别（fail-closed 方向，会报错不静默）。
      已写入 `docs/development-guide.md` 的「完成度门禁与 (post-merge) 任务标记」节

### R2 审阅发现与修复（独立零记忆 subagent `7c72c707`，CHANGES_REQUESTED）

R2 用实跑确认 R1 四项修复**全部成立**（M1 三形态端到端报错、low-1 两侧都锁住、low-3 事件判别、info 已落地），
但 R1 的修复自身引入/遗留两条中等项：

- [x] **M1′（medium，landmine）**：R1 新增的 `test_own_change_explains_protected_artifact_with_its_own_event`
      硬编码 **active** 路径且以 `origin/master...HEAD` 触碰 `docs/known-debt.md` 为触发条件——而该文件内容
      **永久留在 master**。后果：本 change 执行 AGENTS.md 强制的**归档 move** 时该测试 `FileNotFoundError` 转红
      （CI 的 pytest 步必挂），且此后**任何**触碰该文档的未来 PR 都会被同一条件误伤；`origin/master` 不可解析时
      还会静默 skip。修复：抽出 `_change_dir_in_any_form`（active → archive 双形态 + 存在性保护），
      触发条件改为「本树存在本 change 的事件日志」，两个形态都无则 skip。**实跑验证三态**：
      归档后 pass、模拟未来 PR 触碰该文件 pass、change 离开本树 skip。
- [x] **M2（medium，fail-open 边界窄）**：M1 只堵「无 checkbox 行」，未堵「有 checkbox 行但**零勾选**」
      （全部标 `(post-merge)`、一个都不勾）。该形态历史归档真实存在 **8/93**（已实测复现）。
      修复：`_tasks_missing_evidence` 的下限提到「≥1 条被勾选」（对齐 `_tasks_all_complete` 的 `checked > 0`）。
      回归测试：`test_archived_gate_flags_all_post_merge_zero_checked` +
      `test_archived_gate_passes_when_at_least_one_task_checked`（防误红）。变异：回退即转红。
- [x] **low（对称性）**：docs 归档缺 `tasks.md` 曾一律豁免 ⇒ 「删掉 tasks.md」成了 docs 的关闸路径。
      修复：`_tasks_missing_evidence` 判定改为对 docs 同样生效（语料实测 **0/93** 个 docs 归档缺 tasks.md，
      统一口径不产生假阳性）。回归测试：`test_archived_gate_docs_only_missing_tasks_md_is_flagged`。
- [x] **low（记录待办）**：`ARCHIVE_DIR_SEGMENT_RE` 收敛后，`archive/unknown-1.0/file.md` 这类**非 change
      目录**仍会被评命名（当前语料 0 命中，方向 fail-closed）。已记入 `docs/known-debt.md`（「归档目录名
      收敛后的边界」），不阻塞。

## 验证

- [x] 全量 `uv run pytest -q` 通过
- [x] OpenSpec strict validate 通过
- [x] artifact checker + `--check-archived` 通过
- [x] 端到端：构造一个「留一条无 tag 未勾任务的 change + 归档」→ 红；加 tag → 绿
- [ ] (post-merge) 收尾：issue #235 添加完成 comment 并关闭
