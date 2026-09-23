# Tasks — fix-issue-235-completion-gate

## 0. 设计追问（实现前门禁）

- [ ] 跑 `batch-grill-me`（或等价设计追问，`/grill`；独立零记忆 subagent）审视 design.md D1–D7，产出 `reviews/grill-design.md`（≥3 条 Confirmed Decisions + Open Questions 停轮确认后写入 `## User Confirmation`）
- [ ] **grill 必答（R5 的 7 条观察项作为输入）**：
  - **O3（最重要）**：D3 的解耦路线 A（参数化 `assume_implemented`）还是 **B（抽出独立评估函数，active 路径不动）**？本设计倾向 B。
  - **O5**：无日期前缀的归档目录绕过——记 known-debt 还是对非规范归档目录单独报错？
  - O1：D2 表格的"继承豁免"是否需在实现中显式断言（docs-only/无 delta/bugfix 归档不要求四门）？
  - O4：D2 的 RIR 口径统一（`:585` 是内容门槛「自认未完成短语 + tier/status」，不是"三字段非空"）。
  - O6：补 2 条测试（有 review 无 manifest → 第二步报；M + AR 同 PR → 只评估新 id）。
  - O7：§三统计口径（9 与 12 分类重叠、原 issue 表未标注）。

## 实现

- [ ] `scripts/check_openspec_artifacts.py`：`main()` 中新增归档点求值（仅 `--base-ref` 模式，**不被 `--skip-protected-paths` 门控**，**不被 `--check-archived` 触发**）
- [ ] 新增 `new_archived_ids` 解析：`git diff --name-only --diff-filter=AR <base>` + 正则 `^openspec/changes/archive/\d{4}-\d{2}-\d{2}-([^/]+)/`
- [ ] 新增归档点门评估（按 D3 裁定的路线）：四道门 + 未勾任务，作用于 `openspec/changes/archive/<date>-<id>/`
- [ ] **building-review 只做存在性**（不复用 `_check_review_manifests`，避免严格 `tasks_hash` 误报；manifest 完整性留 CI 第二步）
- [ ] 四道门**复用现有判定函数**（继承 docs 豁免 `:508` / DESIGN_TYPES `:712` / `primary != docs` + `_changed_capabilities` `:1029-1031`）
- [ ] `_tasks_all_complete` 扫描放宽：覆盖 `[X]`、`+ [ ]`，保留「缩进子项也算」
- [ ] 新增 `(post-merge)` tag 解析（正则见 design D4，容忍编号/粗体在前、全半角括号、大小写）
- [ ] 未勾任务判定：无 tag 的未勾行进 `errors`；有 tag 的豁免
- [ ] **不改 active 路径**（若 D3 选 B，`check_change` 原样不动）

## 测试

- [ ] **问题二**：本 PR 新归档 + 缺 `building-review.md` → 门触发
- [ ] **问题一**：本 PR 新归档 + 一条无 tag 未勾任务 → 门触发
- [ ] 同 fixture 该未勾任务加 `(post-merge)` → 不报
- [ ] **tag 语法参数化**：8 变体（`- [ ] (post-merge)` / `- [ ] 5.5 (post-merge)` / `- [ ] **6.9** (post-merge)` / 全角 `（post-merge）` / `(POST-MERGE)` / `+ [ ]` / `* [ ]`）全识别为豁免
- [ ] **不反转 `f4a4272`**：`tests/test_openspec_artifact_checker.py:241`（`test_partial_change_does_not_require_building_review`）**原样通过**
- [ ] **豁免继承**：docs-only 归档 → 不要求四门；无 spec delta / bugfix 归档 → 不要求 grill 证据
- [ ] **不追溯**：既有归档（M 路径）→ 不触发；`--check-archived` → 不触发
- [ ] **AR 的必要性**：纯 rename 归档（`R100`）→ 仍取到 id
- [ ] **`--skip-protected-paths` 不关新门**
- [ ] **O6a**：有 `building-review.md` 但无 manifest → 第一步过、第二步报 `review manifest missing`
- [ ] **O6b**：同 PR 既有 M（旧归档）又有 AR（新归档）→ 只评估新 id
- [ ] 四道门**各自独立断言**（防"只实现了一道"）
- [ ] 变异验证：去掉 AR 改 A → rename 用例红；去掉 tag → 豁免用例红；把新门挂到 `--check-archived` → 不追溯用例红
- [ ] 全量 `uv run pytest -q` + OpenSpec strict validate + artifact checker + `--check-archived`

## 文档

- [ ] `AGENTS.md`：`(post-merge)` tag 约定（closeout 任务）+ 更新门禁描述（触发条件从「全勾」改「归档点」）
- [ ] `docs/development-guide.md`：tag 语法与用途（含"为什么需要"）
- [ ] archive 命令文件（`.claude/commands/opsx/archive.md`，**当前不存在**，需先 `npx openspec init --tools claude` 生成；存在则改）
- [ ] `docs/known-debt.md`：残余面（「实现 PR 完全不归档」+ O5 的无日期前缀归档面），配 `protected_artifact_explained` 事件
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
- [ ] 端到端：构造一个「留一条无 tag 未勾任务的 change + 归档」→ CI 红；加 tag → 绿
- [ ] 收尾：issue #235 添加完成 comment 并关闭
