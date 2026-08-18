# Tasks: evaluation-verified-subset

## 1. 规格与设计定稿

- [x] 1.1 确认 proposal 的 Change Type、Impact Analysis、Reference Implementation Research（research_tier=light，含本地参考仓库不可用事实）完整。
- [x] 1.2 开发前使用 `batch-grill-me`（独立零记忆 grill subagent）审视 `design.md`，逐项确认 D1–D5 与开放问题（CLI 形态、gold_check 覆盖、manifest 登记、幂等/resume）；不得把 agent 推荐答案当作用户确认。
- [x] 1.3 grill 产出 `reviews/grill-design.md` 后**停轮**把 `## Open Questions` 逐项抛给用户并等待明确答复（每条配具体例子/场景），用户答复记录进 `## User Confirmation`；收到答复前不写实现代码。

## 2. 生成管线

- [x] 2.1 `swebench_subset.py` argparse 新增 `build-subset` 子命令（--output/--targets/--skip-gold-check/--resume）。
- [x] 2.2 流程接线：`load_verified()` → `build_subset()` → `generate_tasks()` 落盘。
- [x] 2.3 落盘后自动 `validate_fixtures_dir`，invalid exit 1。

## 3. 本机生成 + 校验

- [x] 3.1 `HF_ENDPOINT=https://hf-mirror.com` 实际运行 build-subset 生成（实测补 28 条新，flask/seaborn 池上限约束，共 38 条）。
- [x] 3.2 `validate_fixtures_dir` 全过（instance_id/dataset/track/scenario/difficulty/task_family/environment）。
- [x] 3.3 L3 `gold_check` 对生成 fixture 自检（requests/flask/pytest 3 条 PASS，sympy/seaborn/pylint 未自检记录）。
- [x] 3.4 生成结果回写 change 文档（实际条数 38/配比/difficulty 分布/自检结果/github 不可达记录）。

## 4. manifest 登记 + 清理

- [x] 4.1 `benchmarks/tasks/manifest.json` 登记 verified 摘要段（count=38/by_repo/by_difficulty，不占 coverage 矩阵）。
- [x] 4.2 清理生成过程中的临时文件（.gold-check/.gold-check-venv 已清）；确认无测试/gold.patch 泄漏。

## 5. 同步与验证

- [ ] 5.1 维护 Impact Analysis，清理 `unknown`/`TBD`/`待确认`。
- [ ] 5.2 维护 Reference Implementation Research 最终结论。
- [ ] 5.3 更新 `docs/openspec-change-backlog.md`（#156 后续项 1 状态）。
- [ ] 5.3b 将本 change 的 `benchmark` delta 同步到当前规格 `openspec/specs/benchmark/spec.md`。
- [ ] 5.4 运行相关单元/集成测试与全量测试。
- [ ] 5.5 运行 `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` 与 `uv run python scripts/check_openspec_artifacts.py`。
- [ ] 5.6 跑通 benchmark smoke（fake runner 含新 swebench fixture 发现/加载）。

## 6. 审阅与 PR 收尾

- [ ] 6.1 运行 `/review-loop`（独立零记忆 subagent 审阅 → verdict → CHANGES_REQUESTED 则修复 + 回归测试 → 再审至 PASS/3 轮封顶），产出 `reviews/building-review.md` + review manifest。
- [ ] 6.2 将本 change 归档到 `openspec/changes/archive/YYYY-MM-DD-<change-id>/`。
- [ ] 6.3 从 `docs/openspec-change-backlog.md` 移除/更新本 change 并同步批次。
- [ ] 6.4 确认无残留未解释项，跑最终 validate + artifact checker。
- [ ] 6.5 发起实现 PR；合入后给跟踪 issue #163 添加完成说明 comment 并关闭，在 follow-up #156 标注 Verified 40 完成。
