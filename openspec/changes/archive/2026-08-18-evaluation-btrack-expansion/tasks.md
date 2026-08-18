# Tasks: evaluation-btrack-expansion

## 1. 规格与设计定稿

- [x] 1.1 确认 proposal 的 Change Type、Impact Analysis、Reference Implementation Research（research_tier=light，含本地参考仓库不可用事实）完整。
- [x] 1.2 开发前使用 `batch-grill-me`（独立零记忆 grill subagent）审视 `design.md`，逐项确认 D1–D6 与开放问题（任务清单、红绿可复现、C4 数字校准范围、与 verified-subset 并行）；不得把 agent 推荐答案当作用户确认。
- [x] 1.3 grill 产出 `reviews/grill-design.md` 后**停轮**把 `## Open Questions` 逐项抛给用户并等待明确答复（每条配具体例子/场景），用户答复记录进 `## User Confirmation`；收到答复前不写实现代码。

## 2. context-planning 任务（CP-1~CP-4）

- [x] 2.1 CP-1 工具装配链任务（issue.md 不给路径 + 确定性验证 + 红绿可复现；工具类名按惯例 `ListRunningBenchmarksTool`）。
- [x] 2.2 CP-2 statechart 新增 `awaiting_grill_confirmation` 任务，**触面 6 处写进 issue.md**：①statechart.json ②`agent/workflow/event_log.py` AWAITING_SUB_STATES ③`scripts/workflow_state.py` args.awaiting 校验（~L576）④`_AWAITING_RECOVERY_DEFAULTS` ⑤`scripts/workflow_methods.json` ⑥parity 测试 `tests/test_declarative_flow_engine.py`。
- [x] 2.3 CP-3 结果页 track 分组任务（触面 models+runner+statistics+report，TaskResult 需加 track 字段）。
- [x] 2.4 CP-4 SwebenchAdapter 合成回归任务（grill OQ-2 确认：base 人为去掉转义 + gold 加回 + 单测断言路径转义与 harness 目录命名一致；判别力弱则换本地确定性 debug 任务）。

## 3. long-term-memory / long-context 任务

- [x] 3.1 LT-MEM-1 scope 隔离任务（project 身份双端闭合：SaveMemoryTool 新增 `--project <hash>` + MemoryIndexSource 按 session project 过滤；测试构造两个 project 实例断言隔离）。
- [x] 3.2 LC-1 大读取 + 小改动任务（拆分目标钉具体：sources.py memory 注入逻辑下沉到 agent/memory/ 明确归属；base 红用「行为保持断言 + 新模块路径可用」双断言）。

## 3b. 第 7 条 bug-fix 任务（B=12，grill OQ-1 确认）

- [x] 3.3 BF-1 B 轨 bug-fix 任务（command_guard/sandbox 真实模块挑可确定性验证缺陷形态，红绿可复现；判别力不足则收敛并在 #156 标注）。

## 4. 覆盖矩阵 + 场景补齐

- [x] 4.1 每场景（bug-fix/feature-dev/refactor/debug/integration）≥1–2 校验，缺口补任务。
- [x] 4.2 manifest coverage 矩阵登记全部新任务。
- [x] 4.3 `validate_coverage` 扩展 per-track B 能力列校验（`required_track_coverage = {"context-planning": {"B"}, "long-term-memory": {"B"}, "long-context": {"B"}}`）+ 7 能力列 × 5 场景列 ≥1 全过。

## 5. 红绿可复现 + smoke

- [x] 5.1 每个新增任务「base 红 + gold 绿」验证（不加 gold.patch → test_command 红；加 → 绿）。
- [x] 5.2 `--tasks <glob>` 单任务 smoke（fake runner 发现/执行新 B 轨任务）。

## 6. 面试叙事数字校准（grill OQ-3 全套清单）

- [x] 6.1 实现时实测任务数（A=22/B=12/verified=10 → 34 本地 / 44 总）。
- [x] 6.2 同步全套：FINAL-master-script.md（L11/L27/L96/L117/L118，含升级行「当前已落 37」→ 新数字）/ `docs/interview-script/walkthrough/README.md` L27 / `docs/resume-description.md`（L9/L87/L104，22 A + 12 B）/ README L36/L178/L373 / README_EN L36/L178（README 修改同变更同步 README_EN）。

## 7. 同步与验证

- [x] 7.1 维护 Impact Analysis，清理 `unknown`/`TBD`/`待确认`。
- [x] 7.2 维护 Reference Implementation Research 最终结论。
- [x] 7.3 更新 `docs/openspec-change-backlog.md`（#156 后续项 2 状态）。
- [x] 7.3b 将本 change 的 `benchmark` delta 同步到当前规格 `openspec/specs/benchmark/spec.md`。
- [x] 7.4 运行相关单元/集成测试与全量测试。
- [x] 7.5 运行 `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` 与 `uv run python scripts/check_openspec_artifacts.py`。
- [x] 7.6 跑通 benchmark smoke。

## 8. 审阅与 PR 收尾

- [x] 8.1 运行 `/review-loop`（独立零记忆 subagent 审阅 → verdict → CHANGES_REQUESTED 则修复 + 回归测试 → 再审至 PASS/3 轮封顶），产出 `reviews/building-review.md` + review manifest。
- [x] 8.2 将本 change 归档到 `openspec/changes/archive/YYYY-MM-DD-<change-id>/`。
- [x] 8.3 从 `docs/openspec-change-backlog.md` 移除/更新本 change 并同步批次。
- [x] 8.4 确认无残留未解释项，跑最终 validate + artifact checker。
- [ ] 8.5 发起实现 PR；合入后给跟踪 issue #164 添加完成说明 comment 并关闭，在 follow-up #156 标注 B 轨扩展完成。
