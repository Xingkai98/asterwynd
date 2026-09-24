# Tasks: evaluation-narrative（C4）

## 1. 规格与设计定稿

- [x] 1.1 确认 proposal 的 Change Type、Impact Analysis、Reference Implementation Research（research_tier=exempt，docs-only 豁免 + 引用已关闭决策路径）完整。
- [x] 1.2 开发前使用 `batch-grill-me`（独立零记忆 grill subagent）审视 `design.md`，逐项确认 D1–D5 与开放问题（升级叙事措辞、C3 合入后校准时机）；不得把 agent 推荐答案当作用户确认。**2026-08-17 已由独立零记忆 grill subagent（run f1c9210c-1fd3-47f2-9358-09b84b483d5a）完成。**
- [x] 1.3 grill 产出 `reviews/grill-design.md` 后**停轮**把 `## Open Questions` 逐项抛给用户并等待明确答复（每条配具体例子/场景），用户答复记录进 `## User Confirmation`；收到答复前不写实现代码。**2026-08-17 已停轮确认：8 条 Open Questions 全部按推荐执行，逐条记录于 grill-design.md `## User Confirmation`（含确认时间），停轮解除。**

## 2. resume-description.md

- [x] 2.1 L9/L104 23→27、L87 34→27（26 A 轨 + 1 B 轨口径）、L23/L116 450+→~1997（用户确认以 master 实测为准）。
- [x] 2.2 L9/L89/L105/L125-126/L132 Claw-SWE-Bench 目录表述 → 统一 harness 口径（SwebenchAdapter + 多 runner）。
- [x] 2.3 简历 bullet 7 改后草案落地（用户确认落点 C：展开版 §6 替换 L87 行；含 27 本地任务 + Verified 子集 + bootstrap CI + pass@1/pass@k + 统一 harness 对比 + CI 回归门禁）。

## 3. Q13-benchmark.md

- [x] 3.1 L7 任务层加场景×难度分层 + 三来源任务集（带过渡句区分「两类=执行类型轴」；双要素标注升级目标 ~90 + 当前已落 37）。
- [x] 3.2 L11 指标层加 pass^k/cost@pass/fault_owner（升级方向）。
- [x] 3.3 L13 对比层加配对比较（per-task delta + 差异 CI + win-rate）。
- [x] 3.4 L15 面试重点加污染披露（138 实例 59.4% 缺陷）+ pass@1/pass^k 口径 + 内联 Claw 重锚。
- [x] 3.5 L64 Claw 表述重锚为统一 harness 口径。

## 4. W07-observability-benchmark.md

- [x] 4.1 L3/L98 36+→37（27 本地 + 10 SWE-bench）（用户 Q6 确认；原「36+ 保留」基于过期口径 26+10=36 已推翻）。
- [x] 4.2 L104-109 追加 4 条升级加分点：场景化 ~90/pass^k、污染披露、反作弊诚实边界、预算可配置可取消（标 C1–C3 交付）。

## 5. FINAL-master-script.md

- [x] 5.1 L111 130/~1691→148/~1997（用户确认以 master 实测为准）。
- [x] 5.2 L112 38 工具保留 + 口径注明「38 内置（KNOWN_BUILTIN_TOOL_NAMES 已知名数，含默认关闭的浏览器工具）」，不用「默认模式启用名数」表述。
- [x] 5.3 L117 36→37（27 本地 + 10 SWE-bench）+ 追加升级行（~90 场景×难度分层双要素标注，C1 实现中）。
- [x] 5.4 bullet 7 L96 追加升级句。
- [x] 5.5 速查表新增升级数字行（~90/pass^k/cost@pass/fault_owner/预算，标「设计已定/实现中」）。

## 6. 一致性校验

- [x] 6.1 grep 确认无残留错误口径于 5 份目标文档（扩展词表：`23 个`/`34 个`/`450+`/`claw-swe-bench`/`26 + 10`/`130 文件`/`~1691`/`36（26`，用户 Q4 确认扩展）。
- [x] 6.2 README/README_EN 任务数检查：实测已为 27/37（C1 同步），无待改。
- [x] 6.3 数字与 C1 合入后 master 一致（本地 27 = 26 A 轨 + 1 B 轨；简历用「27 本地任务（26 A 轨 + 1 B 轨）+ Verified 子集」表述，用户 Q2 确认）。

## 7. 同步与验证

- [x] 7.1 维护 Impact Analysis，清理 `unknown`/`TBD`/`待确认`。
- [x] 7.2 维护 Reference Implementation Research 最终结论。
- [ ] 7.3 更新 `docs/openspec-change-backlog.md`（C4 状态）——与 8.3 归档清理合并执行。
- [x] 7.4 将本 change 的 `interview-script` delta 同步到当前规格 `openspec/specs/interview-script/spec.md`（workflow-events seq 2 `current_spec_synced`）。
- [x] 7.5 运行 `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`（31 passed）与 `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py`（passed）。
- [x] 7.6 校准检查：C3（`evaluation-protocol-reporting`）**未合入 master**（master 停在 C2 后 88ed98a），升级叙事段数字无需校准，维持「设计已定、C1–C3 实现中」标注。

## 8. 审阅与 PR 收尾

- [x] 8.1 运行 `/review-loop`（独立零记忆 subagent 审阅 → verdict → CHANGES_REQUESTED 则修复 → 再审至 PASS/3 轮封顶），产出 `reviews/building-review.md` + review manifest（docs-only change 的审阅聚焦文档口径一致性）。**Round 1 PASS（run a62dd79041b1fbdbc），manifest 绑定 base 88ed98a / head 4145f7b。**
- [x] 8.2 将本 change 归档到 `openspec/changes/archive/2026-08-17-evaluation-narrative/`。
- [x] 8.3 从 `docs/openspec-change-backlog.md` 移除/更新本 change 并同步批次（批次条目标已归档 + 校正口径；未实现队列详细条目 7 移除；workflow-events seq 3/4）。
- [x] 8.4 确认 Impact Analysis 与 Reference Implementation Research 无残留未解释项，跑最终 validate + artifact checker（31 passed + passed）。
- [ ] 8.5 发起实现 PR；合入后给跟踪 issue #160 添加完成说明 comment 并关闭——**由主 session 监督执行**（本 change 开发 agent 已 notify，等合入指令）。
