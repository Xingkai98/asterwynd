# Tasks: evaluation-metrics（C2）

> 本 change 实现 C1 已落进 `openspec/specs/benchmark/spec.md` 的 M1–M11 Requirement 中归 C2 的部分；spec delta 以 REVISED 方式去掉「实现归 C2」注记并补充具体化细节。

## 1. 规格与设计定稿

- [ ] 1.1 确认 proposal 的 Change Type、Impact Analysis、Reference Implementation Research（research_tier=full，含本地参考仓库不可用事实与替代依据）完整。
- [ ] 1.2 开发前使用 `batch-grill-me`（独立零记忆 grill subagent）审视 `design.md`，逐项确认 D1–D9 与开放问题（数据模型字段集、pass^k 无效轮次口径、$/resolved-task 分子分母、fault_owner 标注来源边界、配对比较统计方法）；不得把 agent 推荐答案当作用户确认。
- [ ] 1.3 grill 产出 `reviews/grill-design.md` 后**停轮**把 `## Open Questions` 逐项抛给用户并等待明确答复（每条配具体例子/场景），用户答复记录进 `## User Confirmation`；收到答复前不写实现代码。
- [ ] 1.4 确认 spec delta（REVISED 去注记清单）与 proposal Modified Capabilities 一致，且为向后兼容扩展。

## 2. 数据模型扩展

- [ ] 2.1 `TaskResult` 新增 `cache_read_tokens`/`cache_write_tokens`/`temperature`/`seed`/`fault_owner`（可选字段）。
- [ ] 2.2 `RunMetadata` 新增 `task_set_hash`/`max_iterations`/`timeout_seconds`/`network`/`adapter_version`/`prompt_version`/`pricing_table_version`（可选字段）。
- [ ] 2.3 `from_dict`/`to_dict` 向后兼容测试（旧 artifact 读取不报错、未知 key 忽略、None 省略）。

## 3. pass^k 聚合

- [ ] 3.1 `statistics.py` 新增 `pass_k_success_rate`（任务级「全部有效轮通过」布尔 → 跨任务均值），区分 pass@1/pass@k/pass^k 语义。
- [ ] 3.2 无效轮次（unsupported/approval-unavailable/docker_unavailable）排除逻辑 + 单元测试（不进分母、不当失败）。
- [ ] 3.3 结果页/统计层三指标并列标注语义（pass@1 用户实际获得 / pass@k 能力上限 / pass^k 可靠性）。

## 4. cache-aware 成本

- [ ] 4.1 `agent/cost_tracker.py` 定价表扩展为四档（fresh input / cache read / cache write / output）+ 5 系模型（claude-sonnet-5/opus-5/haiku-4.5）+ deepseek-v4-flash（self-hosted 口径）。
- [ ] 4.2 `compute_cost_cached` + `cache_hit_rate` 实现 + 单元测试（含未知模型回退估算/警告、self-hosted 不计费）。
- [ ] 4.3 `PRICING_TABLE_VERSION` + 日期落进定价表。

## 5. $/resolved-task 与 fault_owner

- [ ] 5.1 `cost_per_resolved` 聚合（层内全部 run 总成本含失败 / resolved 数；口径声明「仅 LLM token 计费」）+ 单元测试。
- [ ] 5.2 `fault_owner` 数据模型（D5）+ `fault_owner_cross` 交叉表聚合（reason × fault_owner，默认 unknown 归并）+ 单元测试。

## 6. 配对比较统计

- [ ] 6.1 `compare.py` 新增 `paired_comparison`（per-task delta + 差异 CI（paired bootstrap，seed 固定）+ win-rate）。
- [ ] 6.2 McNemar 显著性检验（精确二项）+ 单元测试（含小样本路径）。

## 7. f2p/p2p 保留 + 小 N 声明

- [ ] 7.1 `adapters.py` SwebenchAdapter 透传 `f2p_rate`/`p2p_rate`/`reward` 到 Verdict detail + 契约测试更新。
- [ ] 7.2 统计/渲染层小 N 声明（N=3–5 附声明；layer 级 CI 权重优先）+ 单元测试。

## 8. 采样显式化 CLI

- [ ] 8.1 `agent/main.py` benchmark CLI 新增 `--seeds`（默认 seed 0..N-1）、`--temperature`（默认 0.2）、`--model-version`。
- [ ] 8.2 每轮 run 记录 (temperature, seed, model version) 进 artifact + 单元/CLI 测试。

## 9. spec 注记清理与同步

- [ ] 9.1 将 `openspec/specs/benchmark/spec.md` 中带「实现归 C2 evaluation-metrics」注记的 Requirement 在本 change 的 spec delta 以 REVISED 列出（去掉注记、补充具体化细节）。
- [ ] 9.2 将本 change 的 `benchmark` delta 同步到当前规格 `openspec/specs/benchmark/spec.md`。

## 10. 同步与验证

- [ ] 10.1 维护 Impact Analysis，清理开发中发现的 `unknown`/`TBD`/`待确认`。
- [ ] 10.2 维护 Reference Implementation Research 最终结论；调研结论变化先回写 change 文档。
- [ ] 10.3 更新 `docs/openspec-change-backlog.md`（C2 状态从「未立项」→ 已合入归档）。
- [ ] 10.4 运行相关单元/集成测试与全量测试。
- [ ] 10.5 运行 `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` 与 `uv run python scripts/check_openspec_artifacts.py`。
- [ ] 10.6 跑通至少一个 benchmark smoke（`--repeat 3 --seeds 0 1 2` fake runner），确认采样参数 + 指标层全链路。

## 11. 审阅与 PR 收尾

- [ ] 11.1 运行 `/review-loop`（独立零记忆 subagent 审阅 → verdict → CHANGES_REQUESTED 则修复 + 回归测试 → 再审至 PASS/3 轮封顶），产出 `reviews/building-review.md` + review manifest。
- [ ] 11.2 将本 change 归档到 `openspec/changes/archive/YYYY-MM-DD-<change-id>/`。
- [ ] 11.3 从 `docs/openspec-change-backlog.md` 移除/更新本 change 并同步批次。
- [ ] 11.4 确认 Impact Analysis 与 Reference Implementation Research 无残留未解释项，跑最终 validate + artifact checker。
- [ ] 11.5 发起实现 PR；合入后给跟踪 issue #157 添加完成说明 comment 并关闭，并在 follow-up #156 上确认 C3 前置跟踪项状态。
