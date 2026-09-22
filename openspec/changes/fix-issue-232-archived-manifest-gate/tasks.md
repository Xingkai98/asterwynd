# Tasks — fix-issue-232-archived-manifest-gate

## 0. 设计追问（实现前门禁）

- [ ] 跑 `batch-grill-me`（或等价设计追问）审视 design.md D1–D6，产出 `reviews/grill-design.md`（≥3 条 Confirmed Decisions + Open Questions 停轮确认后写入 `## User Confirmation`）

## 实现

- [ ] `agent/workflow/review_manifest.py`：`verify_review_manifest` 的 `tasks_hash` 比较加 `not archived` 前置（D2）；其余校验（存在性 / 字段 / `spec_hash` / `report_hash` / git span）保持不变
- [ ] `agent/workflow/review_manifest.py`：归档语境跳过 `tasks_hash` 时**输出说明**（D2 要求降级可见、不静默）——确定输出形式（返回值 note / stderr），保持函数既有签名契约
- [ ] `.github/workflows/ci.yml`：`validate` job 增 `check_openspec_artifacts.py --check-archived` 步骤（D4）
- [ ] `docs/development-guide.md`：「manifest 在 tasks.md 最终化后生成」纪律（D3）
- [ ] 保留盲区 A（PR #234）全部行为：写通道归档回退、`archived=` 透传、归档跳过刷新、只读投影校验

## 测试

- [ ] 归档态 `tasks_hash` 漂移 → 无错（且输出含归档跳过说明）
- [ ] **同输入 active 态 → `tasks hash mismatch`**（判别性对照，锁住 A′ 只放宽归档，D2）
- [ ] 归档态 `spec_hash` 漂移 → 仍报错
- [ ] 归档态 `report_hash` 漂移 → 仍报错
- [ ] 归档态缺 manifest → 仍报「manifest 缺失」
- [ ] 变异验证：去掉 `not archived` 前置 → 归档用例红；把降级扩到 active → 对照用例红；还原后变绿
- [ ] 端到端：`PYTHONPATH=. python3 scripts/check_openspec_artifacts.py --check-archived` 全仓 **exit 0**（放宽前 15 红，由本用例锁定）
- [ ] CI 走查：`.github/workflows/ci.yml` 的 validate job 含 `--check-archived`
- [ ] 回归：`uv run pytest tests/agent/workflow/test_review_manifest.py tests/test_openspec_artifact_checker.py -v`

## 文档

- [ ] spec delta：`specs/dev-workflow-state-machine/spec.md`（MODIFIED「Review evidence manifest」——**补全为变更后完整正文**，保留全部既有 2 条 Scenario + 新增 2 条，退役项 0）
- [ ] **当前规格同步**：delta 已合入 `openspec/specs/dev-workflow-state-machine/spec.md`（含 `current_spec_synced` 事件）
- [ ] `docs/known-debt.md`：按本 change 收口盲区 B 的范围更新 #232 说明（盲区 A/B 均已收口 → 本条可标记完成）；新增 `head_sha` 校验口径债（D5，`_verify_git_span` 未校验 `head_sha == HEAD` 而 spec 声称校验）
- [ ] 关键词扫描 `docs/`、`AGENTS.md`、`docs/development-guide.md` 中与 manifest / `--check-archived` / tasks_hash 相关的段落
- [ ] `docs/openspec-change-backlog.md`：登记本 change（立项）+ 收尾移除（含 `backlog_updated` 事件 ×2）

## 审阅闭环

- [ ] 独立 subagent 审阅（`/review-loop`）→ verdict → CHANGES_REQUESTED 则修复 + 回归，再审直到 PASS 或 3 轮封顶
- [ ] **manifest 在 tasks.md 最终化之后生成**（本 change 自身要遵守 D3 立的纪律）
- [ ] 生成 review manifest 绑定 reviewer run / base·head sha / tasks·spec·diff·report hash（verify OK）

## 验证

- [ ] 全量 `uv run pytest -q` 通过（与本 change 无关的既有失败如实记录）
- [ ] OpenSpec strict validate 通过（`npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`）
- [ ] OpenSpec artifact checker 通过（`PYTHONPATH=. python3 scripts/check_openspec_artifacts.py`）
- [ ] 端到端验收（issue #232 盲区 B 原文）：CI 的 `validate` job 对归档 change 执行 manifest 校验，且全仓 exit 0
- [ ] 收尾：issue #232 添加 comment 说明**盲区 A + B 均已收口**；若两盲区都已处理完，**关闭 #232**（与盲区 A 那次「保持 OPEN」不同——本次是其最后一块）
