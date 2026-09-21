# Tasks — fix-issue-199-handoff-prereq

## 实现

- [ ] `scripts/workflow_state.py`：`cmd_artifact_event` 移除 `handoff.json` 前置，改为 change 目录存在 + `proposal.md` 存在（D1）；不存在 / 缺 `proposal.md` 时明确错误 exit 1（D4）
- [ ] `scripts/workflow_state.py`：`cmd_review_manifest` 同上（D1/D4）
- [ ] 抽出共用前置检查函数（如 `_require_change_target`），两条命令复用，避免文案与判定分叉
- [ ] `scripts/workflow_state.py`：按 D3 决策处置其余 `handoff.json` 引用（`:542` `cmd_current` / `:881` `cmd_spawn` / `:999` `cmd_validate`）——按决策记录执行清理或保留并注释 legacy 理由
- [ ] 若 D3 决策为「保留不改」：把未清理项写入 `docs/known-debt.md`（配 `protected_artifact_explained` 事件）

## 测试

- [ ] 无 `handoff.json` + 有 `proposal.md` + `change_created` 首事件 → `artifact-event` exit 0 且事件写入（判别性：断言事件确在 `workflow-events.jsonl`）
- [ ] 同条件 → `review-manifest` exit 0 且 manifest 写入（断言文件存在 + verify OK）
- [ ] 老世代 change（`initialized` + `handoff.json`）→ 两命令仍 exit 0（兼容性不回归）
- [ ] 不存在的 change → 两命令 exit 1（不退化为任意路径可写）
- [ ] 存在目录但缺 `proposal.md` → 两命令 exit 1
- [ ] 变异验证：把前置改回 `handoff.json` → 当代 change 测试变红；把前置去掉（任意路径可写）→ 非法目标测试变红；还原后变绿
- [ ] 回归：`uv run pytest tests/test_workflow_state_cli.py -v` 通过

## 文档

- [ ] `diagnosis.md`：bugfix 门禁要求的 6 章（已产出）
- [ ] spec delta：`specs/change-documentation/spec.md`（MODIFIED「Handoff state file artifact」）+ `specs/dev-workflow-state-machine/spec.md`（MODIFIED「工作流事件日志与 handoff.json projection」，新增受保护写通道 Scenario）
- [ ] **当前规格同步**：delta 已合入 `openspec/specs/{change-documentation,dev-workflow-state-machine}/spec.md`（含 `current_spec_synced` 事件 ×2）
- [ ] 关键词扫描 `docs/`、`AGENTS.md`、`docs/development-guide.md` 中与 handoff.json / artifact-event / review-manifest 相关的段落，只更新本次造成的事实变化
- [ ] `docs/openspec-change-backlog.md` 已移除本 change 条目（含 `backlog_updated` 事件）

## 审阅闭环

- [ ] 独立 subagent 审阅（`/review-loop`）→ 判 verdict → CHANGES_REQUESTED 则修复 + 回归，再审直到 PASS 或 3 轮封顶
- [ ] 生成 review manifest 绑定 reviewer run / base·head sha / tasks·spec·diff·report hash（verify OK）

## 验证

- [ ] 全量 `uv run pytest -q` 通过（与本 change 无关的既有失败如实记录）
- [ ] OpenSpec strict validate 通过（`npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`）
- [ ] OpenSpec artifact checker 通过（`PYTHONPATH=. python3 scripts/check_openspec_artifacts.py`）
- [ ] 端到端验收（issue #199 验收原文）：新建一个无 `handoff.json` 的 change，`artifact-event` 与 `review-manifest` 均成功写入且通过 `scripts/check_openspec_artifacts.py`
- [ ] `uv run python scripts/workflow_state.py flow status --change fix-issue-199-handoff-prereq` 反映投影
