# Tasks — fix-issue-232-archived-manifest-gate

## 0. 设计追问（实现前门禁）

- [x] 跑 `batch-grill-me`（或等价设计追问）审视 design.md D1–D6，产出 `reviews/grill-design.md`（≥3 条 Confirmed Decisions + Open Questions 停轮确认后写入 `## User Confirmation`）

## 实现

- [x] `agent/workflow/review_manifest.py`：`verify_review_manifest` 的 `tasks_hash` 比较加 `not archived` 前置（D2）；其余校验（存在性 / 字段 / `spec_hash` / `report_hash` / git span）保持不变
- [x] `scripts/check_openspec_artifacts.py`：归档语境跳过 `tasks_hash` 的**可见输出**落在调用方 `--check-archived` 分支——按归档 change **计数并汇总一行**到 stderr（如 `[archived manifest check] tasks_hash 已按归档语境跳过（N 个 change；其余 hash 仍校验）`）；`verify_review_manifest` 保持纯 predicate，**note 不得混入 `list[str]` 返回值**（否则调用方当 error → exit 1，A′ 失效；grill 已实测），签名契约不变
- [x] `.github/workflows/ci.yml`：`validate` job 增 step 运行 `check_openspec_artifacts.py --check-archived --skip-protected-paths --skip-backlog`（D4；参数钉死以消除 CI 才现形的 base-ref WARNING 与重复检查）
- [x] `docs/development-guide.md`：「manifest 在 tasks.md 最终化后生成」纪律（D3）
- [x] 保留盲区 A（PR #234）全部行为：写通道归档回退、`archived=` 透传、归档跳过刷新、只读投影校验

## 测试

- [x] 归档态 `tasks_hash` 漂移 → 无错（`archived=True` 返回值仍为纯错误列表，不含 note）
- [x] **同输入 active 态 → `tasks hash mismatch`**（判别性对照，锁住 A′ 只放宽归档，D2）
- [x] 归档态 `spec_hash` 漂移 → 仍报错
- [x] 归档态 `report_hash` 漂移 → 仍报错
- [x] 归档态缺 manifest → 仍报「manifest 缺失」
- [x] **改写既有测试** `tests/test_openspec_artifact_checker.py::test_verify_review_manifest_archived_path`（其 :1700-1706 断言归档态 tasks 漂移报错，A′ 下必红）→ 改为「归档态 tasks 漂移不报错 + 归档态 spec/report 漂移仍报错」，**不得删断言**
- [x] 变异验证：去掉 `not archived` 前置 → 归档用例红；把降级扩到 active → 对照用例红；还原后变绿
- [x] 端到端：`PYTHONPATH=. python3 scripts/check_openspec_artifacts.py --check-archived --skip-protected-paths --skip-backlog` 全仓 **exit 0**（放宽前 15 红，由本用例锁定），且 stderr 恰含一行归档跳过汇总
- [x] CI 走查：`.github/workflows/ci.yml` 的 validate job 含 `--check-archived`（且带 `--skip-protected-paths --skip-backlog`）
- [x] 回归：`uv run pytest tests/agent/workflow/test_review_manifest.py tests/test_openspec_artifact_checker.py -v`

## 文档

- [x] spec delta：`specs/dev-workflow-state-machine/spec.md`（MODIFIED「Review evidence manifest」——**补全为变更后完整正文**，保留全部既有 2 条 Scenario + 新增 2 条，退役项 0）
- [x] spec delta 的「manifest 字段和 hash 校验」Scenario：**顺手改措辞**删除「`head_sha` 匹配当前 `HEAD`」（与实现对齐，D5/Q4），保留「`base_sha`/`head_sha` 均为 commit + `diff_hash` 匹配」
- [ ] **当前规格同步**：delta 已合入 `openspec/specs/dev-workflow-state-machine/spec.md`（含 `current_spec_synced` 事件）
- [x] `docs/known-debt.md`：按本 change 收口盲区 B 的范围更新 #232 说明（盲区 A/B 均已收口 → 本条可标记完成）；登记残余风险（归档语境不再检测 tasks.md 任何编辑，含行内描述级篡改，Q5）；新增 `head_sha == HEAD` 原始意图的不可满足结论（D5，`_verify_git_span` 未校验且 spec 已改措辞对齐实现）
- [x] 关键词扫描 `docs/`、`AGENTS.md`、`docs/development-guide.md` 中与 manifest / `--check-archived` / tasks_hash 相关的段落
- [ ] `docs/openspec-change-backlog.md`：登记本 change（立项）+ 收尾移除（含 `backlog_updated` 事件 ×2）

## 审阅闭环

- [ ] 独立 subagent 审阅（`/review-loop`）→ verdict → CHANGES_REQUESTED 则修复 + 回归，再审直到 PASS 或 3 轮封顶
- [ ] **manifest 在 tasks.md 最终化之后生成**（本 change 自身要遵守 D3 立的纪律）
- [ ] 生成 review manifest 绑定 reviewer run / base·head sha / tasks·spec·diff·report hash（verify OK）

## 验证

- [x] 全量 `uv run pytest -q` 通过（与本 change 无关的既有失败如实记录）
- [x] OpenSpec strict validate 通过（`npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`）
- [x] OpenSpec artifact checker 通过（`PYTHONPATH=. python3 scripts/check_openspec_artifacts.py`）
- [x] 端到端验收（issue #232 盲区 B 原文）：CI 的 `validate` job 对归档 change 执行 manifest 校验，且全仓 exit 0
- [ ] 收尾：issue #232 添加 comment 说明**盲区 A + B 均已收口**；若两盲区都已处理完，**关闭 #232**（与盲区 A 那次「保持 OPEN」不同——本次是其最后一块）
