# Tasks: evaluation-protocol-reporting（C3）

## 1. 规格与设计定稿

- [x] 1.1 确认 proposal 的 Change Type、Impact Analysis、Reference Implementation Research（research_tier=full，含本地参考仓库不可用事实与替代依据）完整。
- [x] 1.2 开发前使用 `batch-grill-me`（独立零记忆 grill subagent）审视 `design.md`，逐项确认 D1–D8 与开放问题（披露渲染 10 项清单、预算超限语义、self_check 门禁粒度、C4 并行边界）；不得把 agent 推荐答案当作用户确认。
- [x] 1.3 grill 产出 `reviews/grill-design.md` 后**停轮**把 `## Open Questions` 逐项抛给用户并等待明确答复（每条配具体例子/场景），用户答复记录进 `## User Confirmation`；收到答复前不写实现代码。
- [x] 1.4 确认 spec delta（MODIFIED 渲染边界注记→已实现）与 proposal Modified Capabilities 一致，且为向后兼容扩展。

## 2. 运行协议文档

- [x] 2.1 T1 `eval-run-protocol-2026-08-17.md` 转正为 `docs/benchmark-run-protocol.md`（中文，清理 wayfinder-research 引用，落真实命令）。
- [x] 2.2 协议含：任务集 82–90 口径、模型/采样（repeat 5 + seed 0..4 + temp 0.2）、预算 `--budget-cap`/`--budget-cap 0`、对照口径（换 agent/换 model 分开）、artifact 布局、自洽五门禁、reproduction 步骤、Verified 40 fixture 前置说明（#156）。

## 3. 结果页披露渲染

- [ ] 3.1 `report.py` 渲染报告元组（model/harness/task_set_hash/grader/成本口径，读 RunMetadata 新字段）。
- [ ] 3.2 渲染 SWE-bench 污染注记（保留条件域）+ 反作弊泄漏披露（A 轨回归基线）。
- [ ] 3.3 渲染 reason × fault_owner 交叉表 + $/resolved-task + cache hit rate + 定价表版本。
- [ ] 3.4 渲染 f2p/p2p 部分成功档 + 采样参数 + 小样本声明 + 过程效率（10 项清单完整）。
- [ ] 3.5 能力覆盖矩阵（C1 manifest）套件级展示。
- [ ] 3.6 披露渲染 golden 片段测试（不含时间戳/路径）。

## 4. compare 配对渲染

- [ ] 4.1 `compare.py` 接入 `statistics.paired_comparison`：per-task delta 表 + 差异 CI + win-rate + McNemar p 值。
- [ ] 4.2 run 元数据补齐（model version/date/cost 口径读 run.json 新字段）。
- [ ] 4.3 配对渲染测试 + 既有 compare 回归。

## 5. CLI 预算/预检

- [ ] 5.1 `--budget-cap <USD>`（默认建议 $50，超限标 `incomplete`）+ `--no-cap`/`--budget-cap 0` 取消。
- [ ] 5.2 `--preflight`（Docker daemon + 内存 <8GiB 提示 L1 路径，退出码 0/1）。
- [ ] 5.3 CLI 测试（超限 incomplete、取消上限、preflight 内存分支）。

## 6. self_check 五门禁

- [ ] 6.1 `scripts/self_check.py <run_dir>`：同模型同 harness 复现、seed 复现、失败归因闭环、披露段齐全、报告元组完整五门禁。
- [ ] 6.2 每门禁缺失项报告 + exit 码；全部通过 exit 0。
- [ ] 6.3 门禁测试（各门禁缺失场景 + 全通过场景）。

## 7. spec 同步

- [ ] 7.1 本 change 的 spec delta 以 MODIFIED 更新渲染边界注记（C2 留下的「归 C3」注记 → 已实现）。
- [ ] 7.2 将本 change 的 `benchmark` delta 同步到当前规格 `openspec/specs/benchmark/spec.md`。

## 8. 同步与验证

- [ ] 8.1 维护 Impact Analysis，清理 `unknown`/`TBD`/`待确认`。
- [ ] 8.2 维护 Reference Implementation Research 最终结论。
- [ ] 8.3 更新 `docs/openspec-change-backlog.md`（C3 状态）。
- [ ] 8.4 运行相关单元/集成测试与全量测试。
- [ ] 8.5 运行 `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` 与 `uv run python scripts/check_openspec_artifacts.py`。
- [ ] 8.6 跑通 benchmark smoke（`--repeat 3 --seeds 0 1 2` fake runner），确认结果页含披露段。

## 9. 审阅与 PR 收尾

- [ ] 9.1 运行 `/review-loop`（独立零记忆 subagent 审阅 → verdict → CHANGES_REQUESTED 则修复 + 回归测试 → 再审至 PASS/3 轮封顶），产出 `reviews/building-review.md` + review manifest。
- [ ] 9.2 将本 change 归档到 `openspec/changes/archive/YYYY-MM-DD-<change-id>/`。
- [ ] 9.3 从 `docs/openspec-change-backlog.md` 移除/更新本 change 并同步批次。
- [ ] 9.4 确认 Impact Analysis 与 Reference Implementation Research 无残留未解释项，跑最终 validate + artifact checker。
- [ ] 9.5 发起实现 PR；合入后给跟踪 issue #159 添加完成说明 comment 并关闭，在 follow-up #156 确认 Verified 40 fixture 前置项状态。
