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

- [ ] `scripts/check_openspec_artifacts.py`：`main()` 中新增归档点求值（**放在 `if not args.skip_protected_paths:` 块之外**，用 `not args.check_archived and not args.change` 显式守卫）
- [ ] 新增 `new_archived_ids` 解析：`git diff --name-only --diff-filter=AR <base>` + 正则 `^openspec/changes/archive/\d{4}-\d{2}-\d{2}-([^/]+)/` + **「该归档子目录在 base 树不存在」判定**（`git ls-tree -d <base>:openspec/changes/archive` 取差集）
- [ ] 非规范归档目录（`startswith("openspec/changes/archive/")` 但不匹配日期正则）→ 进 `errors`
- [ ] 新门**消费 `--require-base` 语义**（base 不可解析 ∧ require_base → 报错，防浅检出 fail-open）
- [ ] 新增归档点门评估（按 D3 裁定的路线）：四道门 + 未勾任务，作用于 `openspec/changes/archive/<date>-<id>/`
- [ ] **building-review 只做存在性**（不复用 `_check_review_manifests`——理由经 grill 修正为 active 路径解析，非 `tasks_hash`；manifest 完整性留 CI 第二步）
- [ ] **A′ 参数化**：`_check_reference_implementation_research` 与 `_check_design_review_task` 各加 `*, assume_implemented: bool = False`，函数内三处判据（`:585`/`:733`/`:750`）改为 `assume_implemented or _tasks_all_complete(change_dir)`
- [ ] 四道门**复用现有判定函数**（继承 docs 豁免 `:508` / DESIGN_TYPES `:712` / `primary != docs` + `_changed_capabilities` `:1029-1031`）
- [ ] `_tasks_all_complete` 扫描放宽：覆盖 `[X]`、`+ [ ]`，保留「缩进子项也算」
- [ ] 新增 `(post-merge)` tag 解析（正则见 design D4，容忍编号/粗体在前、全半角括号、大小写）
- [ ] 未勾任务判定：无 tag 的未勾行进 `errors`；有 tag 的豁免
- [ ] **`check_change` 一行不动**（A′：不传 `assume_implemented` → 默认 False → active 行为逐字节不变）

## 测试

- [ ] **问题二**：本 PR 新归档 + 缺 `building-review.md` → 门触发
- [ ] **问题一**：本 PR 新归档 + 一条无 tag 未勾任务 → 门触发
- [ ] 同 fixture 该未勾任务加 `(post-merge)` → 不报
- [ ] **tag 语法参数化**：8 变体（`- [ ] (post-merge)` / `- [ ] 5.5 (post-merge)` / `- [ ] **6.9** (post-merge)` / 全角 `（post-merge）` / `(POST-MERGE)` / `+ [ ]` / `* [ ]`）全识别为豁免
- [ ] **不反转 `f4a4272`**：`tests/test_openspec_artifact_checker.py:241`（`test_partial_change_does_not_require_building_review`）**原样通过**
- [ ] **豁免继承（Q1a）**：docs-only 归档 → 不要求四门
- [ ] **触发覆盖（Q1b）**：无 `reviews/` 的非 docs 归档 → 报需要 grill 证据（A′ 判别性断言）
- [ ] **不追溯**：既有归档（M 路径）→ 不触发；`--check-archived` → 不触发；`--change <id>` → 不触发
- [ ] **旧归档目录新增文件（`A` 路径）→ 不评估该旧 id**（风险②判别性测试）
- [ ] **AR 的必要性**：纯 rename 归档（`R100`）→ 仍取到 id
- [ ] **非规范归档目录 → 报错**
- [ ] **`--skip-protected-paths` 不关新门**
- [ ] **fail-closed**：base 不可解析 ∧ `--require-base` → 新门报错
- [ ] **O6a**：有 `building-review.md` 但无 manifest → 第一步过、第二步报 `review manifest missing`
- [ ] 四道门**各自独立断言**（防"只实现了一道"）
- [ ] 变异验证：去掉 AR 改 A → rename 用例红；去掉 tag → 豁免用例红；去掉「base 树不存在」→ 旧归档用例红；把新门挂到 `--check-archived` → 不追溯用例红
- [ ] 全量 `uv run pytest -q` + OpenSpec strict validate + artifact checker + `--check-archived`

## 文档

- [ ] `AGENTS.md`：`(post-merge)` tag 约定（closeout 任务）+ 更新门禁描述（触发条件从「全勾」改「归档点」）
- [ ] `docs/development-guide.md`：tag 语法与用途（含"为什么需要"）
- [ ] `docs/known-debt.md`：残余面（「实现 PR 完全不归档」+ 无日期前缀归档面），配 `protected_artifact_explained` 事件
- [ ] spec delta：`dev-workflow-state-machine` MODIFIED 2 条（审阅门触发 + 内容门槛触发），**完整正文**
- [ ] **当前规格同步**：delta 合入 `openspec/specs/dev-workflow-state-machine/spec.md`（`current_spec_synced` 事件）
- [ ] `docs/openspec-change-backlog.md`：登记本 change + 收尾移除（`backlog_updated` 事件 ×2）
- [ ] 关键词扫描 `docs/`、`AGENTS.md` 中与「tasks 全勾 / 完成度门禁 / building-review 触发」相关的段落

## 审阅闭环

- [ ] `/review-loop` 独立零记忆 subagent 审阅 → PASS 或 3 轮封顶
- [ ] 生成 review manifest（绑归档后最终 head）

## 验证

- [ ] 全量 `uv run pytest -q` 通过
- [ ] OpenSpec strict validate 通过
- [ ] artifact checker + `--check-archived` 通过
- [ ] 端到端：构造一个「留一条无 tag 未勾任务的 change + 归档」→ 红；加 tag → 绿
- [ ] (post-merge) 收尾：issue #235 添加完成 comment 并关闭
