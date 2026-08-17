# Tasks: evaluation-narrative（C4）

## 1. 规格与设计定稿

- [ ] 1.1 确认 proposal 的 Change Type、Impact Analysis、Reference Implementation Research（research_tier=exempt，docs-only 豁免 + 引用已关闭决策路径）完整。
- [ ] 1.2 开发前使用 `batch-grill-me`（独立零记忆 grill subagent）审视 `design.md`，逐项确认 D1–D5 与开放问题（升级叙事措辞、C3 合入后校准时机）；不得把 agent 推荐答案当作用户确认。
- [ ] 1.3 grill 产出 `reviews/grill-design.md` 后**停轮**把 `## Open Questions` 逐项抛给用户并等待明确答复（每条配具体例子/场景），用户答复记录进 `## User Confirmation`；收到答复前不写实现代码（本文档修改亦属实现，停轮覆盖）。

## 2. resume-description.md

- [ ] 2.1 L9/L104 23→26、L87 34→26、L23/L116 450+→1700+。
- [ ] 2.2 L9/L89/L105/L125-126/L132 Claw-SWE-Bench 目录表述 → 统一 harness 口径（SwebenchAdapter + 多 runner）。
- [ ] 2.3 简历 bullet 7 改后草案落地（T2 §1 草案，含 26 本地任务 + Verified 子集 + bootstrap CI + pass@1/pass@k + 统一 harness 对比 + CI 回归门禁）。

## 3. Q13-benchmark.md

- [ ] 3.1 L7 任务层加场景×难度分层 + 三来源任务集（带过渡句区分「两类=执行类型轴」）。
- [ ] 3.2 L11 指标层加 pass^k/cost@pass/fault_owner（升级方向）。
- [ ] 3.3 L13 对比层加配对比较（per-task delta + 差异 CI + win-rate）。
- [ ] 3.4 L15 面试重点加污染披露（138 实例 59.4% 缺陷）+ pass@1/pass^k 口径 + 内联 Claw 重锚。
- [ ] 3.5 L64 Claw 表述重锚为统一 harness 口径。

## 4. W07-observability-benchmark.md

- [ ] 4.1 L3/L98 36+ 保留（当前准确，不改）。
- [ ] 4.2 L104-109 追加 4 条升级加分点：场景化 ~90/pass^k、污染披露、反作弊诚实边界、预算可配置可取消（标 C2/C3 交付）。

## 5. FINAL-master-script.md

- [ ] 5.1 L111 130/~1691→135/1700+。
- [ ] 5.2 L112 38 工具保留 + 口径注明「38 内置（KNOWN_BUILTIN_TOOL_NAMES 已知名数，含默认关闭的浏览器工具）」，不用「默认模式启用名数」表述。
- [ ] 5.3 L117 36 保留 + 追加升级行（~90 场景×难度分层，C1 实现中）。
- [ ] 5.4 bullet 7 L96 追加升级句。
- [ ] 5.5 速查表新增升级数字行（~90/pass^k/cost@pass/fault_owner/预算，标「设计已定/实现中」）。

## 6. 一致性校验

- [ ] 6.1 grep 确认无残留错误口径（`23 个`/`34 个`/`450+`/`claw-swe-bench/`）于 4 份文档。
- [ ] 6.2 README/README_EN 如涉及任务数（23/34/450+）同步修正（含 README_EN 英文翻译）。
- [ ] 6.3 数字与 C1 合入后 master 一致（26→27 本地任务口径在简历用「26 + Verified 子集」表述避免过期）。

## 7. 同步与验证

- [ ] 7.1 维护 Impact Analysis，清理 `unknown`/`TBD`/`待确认`。
- [ ] 7.2 维护 Reference Implementation Research 最终结论。
- [ ] 7.3 更新 `docs/openspec-change-backlog.md`（C4 状态）。
- [ ] 7.4 将本 change 的 `interview-script` delta 同步到当前规格 `openspec/specs/interview-script/spec.md`。
- [ ] 7.5 运行 `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` 与 `uv run python scripts/check_openspec_artifacts.py`。
- [ ] 7.6 若 C3 已合入，校准升级叙事段数字（任务数/协议细节）。

## 8. 审阅与 PR 收尾

- [ ] 8.1 运行 `/review-loop`（独立零记忆 subagent 审阅 → verdict → CHANGES_REQUESTED 则修复 → 再审至 PASS/3 轮封顶），产出 `reviews/building-review.md` + review manifest（docs-only change 的审阅聚焦文档口径一致性）。
- [ ] 8.2 将本 change 归档到 `openspec/changes/archive/YYYY-MM-DD-<change-id>/`。
- [ ] 8.3 从 `docs/openspec-change-backlog.md` 移除/更新本 change 并同步批次。
- [ ] 8.4 确认 Impact Analysis 与 Reference Implementation Research 无残留未解释项，跑最终 validate + artifact checker。
- [ ] 8.5 发起实现 PR；合入后给跟踪 issue #160 添加完成说明 comment 并关闭。
