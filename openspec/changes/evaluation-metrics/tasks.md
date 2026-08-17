# Tasks: evaluation-metrics（C2）

> 本 change 实现 C1 已落进 `openspec/specs/benchmark/spec.md` 的 M1–M11 Requirement 中归 C2 的部分；spec delta 以 REVISED 方式去掉「实现归 C2」注记并补充具体化细节。
> grill 确认（2026-08-17）：用户按 grill 推荐答复全部 13 条 Open Questions，记录于 `reviews/grill-design.md` `## User Confirmation`；grill 补充决策 D10/D11 已并入 design.md。

## 1. 规格与设计定稿

- [x] 1.1 确认 proposal 的 Change Type、Impact Analysis、Reference Implementation Research（research_tier=full，含本地参考仓库不可用事实与替代依据）完整。
- [x] 1.2 开发前使用 `batch-grill-me`（独立零记忆 grill subagent）审视 `design.md`，逐项确认 D1–D9 与开放问题（数据模型字段集、pass^k 无效轮次口径、$/resolved-task 分子分母、fault_owner 标注来源边界、配对比较统计方法）；不得把 agent 推荐答案当作用户确认。
- [x] 1.3 grill 产出 `reviews/grill-design.md` 后**停轮**把 `## Open Questions` 逐项抛给用户并等待明确答复（每条配具体例子/场景），用户答复记录进 `## User Confirmation`；收到答复前不写实现代码。
- [x] 1.4 确认 spec delta（REVISED 去注记清单）与 proposal Modified Capabilities 一致，且为向后兼容扩展。

## 2. 数据模型扩展（D1 + Q5/Q9/Q11/Q13）

- [x] 2.1 `TaskResult` 新增 `cache_read_tokens`/`cache_write_tokens`/`temperature`/`seed`/`fault_owner`/`partial`（可选字段）。
- [x] 2.2 `RunMetadata` 新增 `task_set_hash`/`max_iterations`/`timeout_seconds`/`network`/`adapter_version`/`prompt_version`/`pricing_table_version`/`temperature`/`seed`/`model_version`/`swebench_dataset_version`/`swebench_package_version`（可选字段）。
- [x] 2.3 `from_dict`/`to_dict` 向后兼容测试（旧 artifact 读取不报错、未知 key 忽略、None 省略）。

## 3. pass^k 聚合（D2 + Q1/Q2/Q3）

- [x] 3.1 `statistics.py` 新增 `pass_k_success_rate`（任务级「全部有效轮通过」布尔 → 跨任务均值），区分 pass@1/pass@k/pass^k 语义。
- [x] 3.2 无效轮次排除谓词显式化（`status=='unsupported'` 或 `reason ∈ {docker_unavailable, task_family_unsupported, approval_unavailable}`）+ 单元测试（不进分母、不当失败、全无效任务剔除、有效轮<3 标「样本不足」）。
- [x] 3.3 pass@1 定义为排除无效轮的新聚合，结果页 `layer_pass_rate` 按规格口径替换（golden 测试同步更新）。
- [x] 3.4 结果页/统计层三指标并列标注语义（pass@1 用户实际获得 / pass@k 能力上限 / pass^k 可靠性）+ n/k 有效性声明。

## 4. cache-aware 成本（D3/D4 + Q4/Q5/Q6）

- [x] 4.1 `agent/cost_tracker.py` 定价表扩展为四档（fresh input / cache read / cache write / output）+ 5 系模型（claude-sonnet-5/opus-5/haiku-4.5）+ deepseek-v4-flash（self-hosted 口径）；`MODEL_PRICES` 统一改四元组 + `compute_cost` 同步解包，消费点行为不变。
- [x] 4.2 `compute_cost_cached` + `cache_hit_rate` 实现 + 单元测试（含未知模型回退估算/警告、self-hosted 不计费、cache_hit_rate 分母定义）。
- [x] 4.3 `PRICING_TABLE_VERSION` + 日期落进定价表。
- [x] 4.4 cache token 采集链：`Usage` 加 cache_read/cache_creation 字段 → anthropic_llm 解析 → loop 累加 → AgentRunResult → TaskResult（真实 run 可采集）。

## 5. $/resolved-task 与 fault_owner（D4/D5 + Q6/Q7）

- [x] 5.1 `cost_per_resolved` 聚合（层内全部 run 总成本含失败 / resolved 数；passed_with_warnings 计入分母；Verdict 加 resolved 字段透传 SWE-bench 严格 resolved；resolved=0 返回 None；self-hosted 分子 0 输出 $0.00+注记；口径声明「仅 LLM token 计费」）+ 单元测试。
- [x] 5.2 `fault_owner` 数据模型（D5）+ `fault_owner_cross` 交叉表聚合（reason × fault_owner，默认 unknown 归并、非法字符串归 unknown 并警告）+ 单元测试。
- [x] 5.3 最小标注工具 `benchmark annotate <run-dir> (task,round) --owner agent|task|environment|unknown`（更新 result.json）+ CLI 测试。
- [x] 5.4 κ helper（双人标注一致性 Cohen's kappa）归 C2 统计层 + 单元测试。

## 6. 配对比较统计（D6 + Q8）

- [x] 6.1 `compare.py` 新增 `paired_comparison`（per-task delta 用 pass@1 有效轮通过率 + 差异 CI（paired bootstrap，seed 固定）+ win-rate）。
- [x] 6.2 McNemar 显著性检验（精确二项，用 pass^k 布尔做 2×2）+ 单元测试（含小样本路径、任务集不完全重合剔除并注记）。

## 7. f2p/p2p 保留 + 小 N 声明（D7/D8 + Q9/Q10）

- [ ] 7.1 `adapters.py` SwebenchAdapter 透传 `f2p_rate`/`p2p_rate`/`reward` 到 Verdict `partial` 字段 + runner 透传到 `TaskResult.partial` + 契约测试更新。
- [ ] 7.2 统计层输出样本量 N 供渲染层判断（小样本声明文案渲染归 C3，本 change 不渲染声明文案）+ 单元测试。

## 8. 采样显式化 CLI（D9 + Q11/Q12）

- [ ] 8.1 `agent/main.py` benchmark CLI 新增 `--seeds`（默认 seed 0..N-1）、`--temperature`（默认 0.2）、`--model-version`；`--seeds` 与 `--repeat` 长度不一致报错；`--repeat` 上限 5、N<3 警告。
- [ ] 8.2 每轮 run 记录 (temperature, seed, model version) 进 run.json（RunMetadata）与 result.json（TaskResult）+ 单元/CLI 测试。

## 9. 过程效率指标 + SWE-bench 污染披露数据层（D10/D11 + Q13）

- [ ] 9.1 `process_efficiency` 统计函数（time-to-first-successful-edit + exploration fraction，从 trace 事件采集；exploration fraction 口径=非 Edit 工具调用耗时占比；渲染归 C3）+ 单元测试。
- [ ] 9.2 SwebenchAdapter 采集 `swebench_dataset_version`/`swebench_package_version` 写进 run metadata + 契约测试。

## 10. spec 注记清理与同步

- [ ] 10.1 将 `openspec/specs/benchmark/spec.md` 中带「实现归 C2 evaluation-metrics」注记的 Requirement 在本 change 的 spec delta 以 REVISED 列出（去掉注记、补充具体化细节）。
- [ ] 10.2 将本 change 的 `benchmark` delta 同步到当前规格 `openspec/specs/benchmark/spec.md`。

## 11. 同步与验证

- [ ] 11.1 维护 Impact Analysis，清理开发中发现的 `unknown`/`TBD`/`待确认`。
- [ ] 11.2 维护 Reference Implementation Research 最终结论；调研结论变化先回写 change 文档。
- [ ] 11.3 更新 `docs/openspec-change-backlog.md`（C2 状态从「已立项」→ 已合入归档）。
- [ ] 11.4 运行相关单元/集成测试与全量测试。
- [ ] 11.5 运行 `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` 与 `uv run python scripts/check_openspec_artifacts.py`。
- [ ] 11.6 跑通至少一个 benchmark smoke（`--repeat 3 --seeds 0 1 2` fake runner），确认采样参数 + 指标层全链路。

## 12. 审阅与 PR 收尾

- [ ] 12.1 运行 `/review-loop`（独立零记忆 subagent 审阅 → verdict → CHANGES_REQUESTED 则修复 + 回归测试 → 再审至 PASS/3 轮封顶），产出 `reviews/building-review.md` + review manifest。
- [ ] 12.2 将本 change 归档到 `openspec/changes/archive/YYYY-MM-DD-<change-id>/`。
- [ ] 12.3 从 `docs/openspec-change-backlog.md` 移除/更新本 change 并同步批次。
- [ ] 12.4 确认 Impact Analysis 与 Reference Implementation Research 无残留未解释项，跑最终 validate + artifact checker。
- [ ] 12.5 发起实现 PR；合入后给跟踪 issue #157 添加完成说明 comment 并关闭，并在 follow-up #156 上确认 C3 前置跟踪项状态。
