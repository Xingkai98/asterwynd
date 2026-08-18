# Tasks: evaluation-btrack-expansion

## 1. 规格与设计定稿

- [ ] 1.1 确认 proposal 的 Change Type、Impact Analysis、Reference Implementation Research（research_tier=light，含本地参考仓库不可用事实）完整。
- [ ] 1.2 开发前使用 `batch-grill-me`（独立零记忆 grill subagent）审视 `design.md`，逐项确认 D1–D6 与开放问题（任务清单、红绿可复现、C4 数字校准范围、与 verified-subset 并行）；不得把 agent 推荐答案当作用户确认。
- [ ] 1.3 grill 产出 `reviews/grill-design.md` 后**停轮**把 `## Open Questions` 逐项抛给用户并等待明确答复（每条配具体例子/场景），用户答复记录进 `## User Confirmation`；收到答复前不写实现代码。

## 2. context-planning 任务（3–5 条）

- [ ] 2.1 CP-1 工具装配链任务（issue.md 不给路径 + 确定性验证 + 红绿可复现）。
- [ ] 2.2 CP-2 statechart 跨 4 处任务。
- [ ] 2.3 CP-3 结果页 track 分组任务。
- [ ] 2.4 CP-4 SwebenchAdapter debug 任务（可选第 4/5 条）。

## 3. long-term-memory / long-context 任务

- [ ] 3.1 LT-MEM-1 scope 隔离任务（写 A 项目 → B 不可见 → 回 A 复用）。
- [ ] 3.2 LC-1 大读取 + 小改动任务（审计拆分 context/memory 职责）。

## 4. 覆盖矩阵 + 场景补齐

- [ ] 4.1 每场景（bug-fix/feature-dev/refactor/debug/integration）≥1–2 校验，缺口补任务。
- [ ] 4.2 manifest coverage 矩阵登记全部新任务。
- [ ] 4.3 `validate_coverage` 7 能力列 × 5 场景列 ≥1 全过。

## 5. 红绿可复现 + smoke

- [ ] 5.1 每个新增任务「base 红 + gold 绿」验证（不加 gold.patch → test_command 红；加 → 绿）。
- [ ] 5.2 `--tasks <glob>` 单任务 smoke（fake runner 发现/执行新 B 轨任务）。

## 6. 面试叙事数字校准

- [ ] 6.1 实现时实测任务数（27+N 本地 / 37+N 总）。
- [ ] 6.2 同步 FINAL-master-script.md / walkthrough/README.md / resume-description.md / README / README_EN 任务数（含升级行「当前已落 37」→ 新数字）。

## 7. 同步与验证

- [ ] 7.1 维护 Impact Analysis，清理 `unknown`/`TBD`/`待确认`。
- [ ] 7.2 维护 Reference Implementation Research 最终结论。
- [ ] 7.3 更新 `docs/openspec-change-backlog.md`（#156 后续项 2 状态）。
- [ ] 7.3b 将本 change 的 `benchmark` delta 同步到当前规格 `openspec/specs/benchmark/spec.md`。
- [ ] 7.4 运行相关单元/集成测试与全量测试。
- [ ] 7.5 运行 `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` 与 `uv run python scripts/check_openspec_artifacts.py`。
- [ ] 7.6 跑通 benchmark smoke。

## 8. 审阅与 PR 收尾

- [ ] 8.1 运行 `/review-loop`（独立零记忆 subagent 审阅 → verdict → CHANGES_REQUESTED 则修复 + 回归测试 → 再审至 PASS/3 轮封顶），产出 `reviews/building-review.md` + review manifest。
- [ ] 8.2 将本 change 归档到 `openspec/changes/archive/YYYY-MM-DD-<change-id>/`。
- [ ] 8.3 从 `docs/openspec-change-backlog.md` 移除/更新本 change 并同步批次。
- [ ] 8.4 确认无残留未解释项，跑最终 validate + artifact checker。
- [ ] 8.5 发起实现 PR；合入后给跟踪 issue #164 添加完成说明 comment 并关闭，在 follow-up #156 标注 B 轨扩展完成。
