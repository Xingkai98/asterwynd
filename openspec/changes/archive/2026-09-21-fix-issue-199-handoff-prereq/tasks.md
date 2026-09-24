# Tasks — fix-issue-199-handoff-prereq

## 实现

- [x] `scripts/workflow_state.py`：`cmd_artifact_event` 移除 `handoff.json` 硬前置，改为「change 目录存在 且（`proposal.md` 存在 或 `handoff.json` 存在）」（D1 / grill Q1-Q2）；不存在或两者皆缺时明确错误 exit 1（D5）
- [x] `scripts/workflow_state.py`：`cmd_review_manifest` 同上（D1/D5）
- [x] 抽出共用前置检查函数（如 `_require_change_target`），两条命令复用，避免文案与判定分叉
- [x] 前置检查保持 `is_workflow_enabled` 之后、原 `handoff.json` 检查的同一位置（D5 顺序，grill 确认）
- [x] `scripts/workflow_state.py`：两条命令成功追加后调用 `_flow_refresh_after_event(change_dir)` 刷新投影（D7 / grill Q6），使写入结果可立即被 checker 校验
- [x] `scripts/workflow_state.py`：按 D3 决策处置其余 `handoff.json` 引用（`:539` `cmd_current` / `:881` `cmd_spawn` / `:996` `cmd_validate` / `discover` `_cmd_discover_text:364-374`）——按决策记录保留并注释 legacy 理由，不删子命令

## 测试

全部从**冷状态**构造（种子为直接落盘的 `change_created` 事件，**不得**用 `WorkflowManager.init()`——它写 `initialized` 是 gen-1，会让测试恒绿；调用 CLI 前断言无 `handoff.json`；测试内不得先跑 `flow status` 或任何写事件子命令）。测试内显式注释说明该约束。

- [x] 无 `handoff.json` + 有 `proposal.md` + `change_created` 首事件 → `artifact-event` exit 0 且事件写入（判别性：断言事件确在 `workflow-events.jsonl`）
- [x] 同条件 → `review-manifest` exit 0 且 manifest 写入（断言文件存在 + `verify_review_manifest` 为空）
- [x] 老世代 change（`initialized` + `handoff.json` + `proposal.md`）→ 两命令仍 exit 0（兼容性不回归）
- [x] 无 `proposal.md` 但有 `handoff.json`（spawn 子 change 形态）→ 两命令仍 exit 0（Q1 兼容分支）
- [x] 不存在的 change → 两命令 exit 1（不退化为任意路径可写）
- [x] 存在目录但既无 `proposal.md` 也无 `handoff.json` → 两命令 exit 1
- [x] 路径型 `--change`（绝对路径 / 含 `/`）→ 两命令 exit 1、不抛裸 traceback（R2 审阅 New-1：D7 刷新对 gen-1+路径型目标抛裸 `FileNotFoundError` 的回归；同时封住 R1 问题 4「绝对路径可写到仓库外」）
- [x] 写入后 `verify_projection` 为空（D7 刷新生效，不需再跑 `flow status`）
- [x] 变异验证：把前置改回「必须有 `handoff.json`」→ 当代 change 测试变红；把前置整个去掉（任意路径可写）→ 非法目标测试变红；还原后变绿
- [x] 回归：`uv run pytest tests/test_workflow_state_cli.py -v` 通过 + 全量 `uv run pytest -q`

## 文档

- [x] `diagnosis.md`：bugfix 门禁要求的 6 章（已产出）
- [x] spec delta：`specs/change-documentation/spec.md`（MODIFIED「Handoff state file artifact」）+ `specs/dev-workflow-state-machine/spec.md`（MODIFIED「工作流事件日志与 handoff.json projection」）——**正文补全为变更后完整正文**，保留既有 8 条 Scenario（按两代口径改写），退役项在 design.md D6 显式列出（grill Q5）
- [x] `docs/known-debt.md` 新增债务条目（配 `protected_artifact_explained` 事件）：四处 CLI 漏网（`discover` 单列）+ D4 三层债务 + 伪造目录缺口
- [x] **当前规格同步**：delta 已合入 `openspec/specs/{change-documentation,dev-workflow-state-machine}/spec.md`（含 `current_spec_synced` 事件 ×2）
- [x] 关键词扫描 `docs/`、`AGENTS.md`、`docs/development-guide.md` 中与 handoff.json / artifact-event / review-manifest 相关的段落，只更新本次造成的事实变化
- [x] `docs/openspec-change-backlog.md` 已移除本 change 条目（含 `backlog_updated` 事件）
- [x] **收尾纪律**：确认本 change 未跟踪 `handoff.json` / `workflow-state.json`（自愈产物，非本 change 资产）。R1 提交曾因 `git add -A` 误吞二者，已 `git rm --cached` 并删除工作区文件；收尾**不得用 `git add -A` / `git add .`**，只显式列路径（`flow status` 会自愈重建这两个文件，`-A` 会再次吞入；根因见 #228 债务条目）

## 审阅闭环

- [x] 独立 subagent 审阅（`/review-loop`）→ 判 verdict → CHANGES_REQUESTED 则修复 + 回归，再审直到 PASS 或 3 轮封顶
- [x] 生成 review manifest 绑定 reviewer run / base·head sha / tasks·spec·diff·report hash（verify OK）

## 验证

- [x] 全量 `uv run pytest -q` 通过（与本 change 无关的既有失败如实记录）
- [x] OpenSpec strict validate 通过（`npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`）
- [x] OpenSpec artifact checker 通过（`PYTHONPATH=. python3 scripts/check_openspec_artifacts.py`）
- [x] 端到端验收（issue #199 验收原文）：新建一个无 `handoff.json` 的 change，`artifact-event` 与 `review-manifest` 均成功写入且**无需先跑 `flow status`** 即通过 `scripts/check_openspec_artifacts.py`
- [x] `uv run python scripts/workflow_state.py flow status --change fix-issue-199-handoff-prereq` 反映投影
