# Tasks: evaluation-task-spec（C1）

> 标注约定：`[spec]` = 规格落定任务（本 change 完成）；`[C2]` = Requirement 文本已落、实现归 C2 `evaluation-metrics`（本 change 只落 spec，不写实现代码）。

## 1. 规格与设计定稿

- [ ] 1.1 确认 proposal 的 Change Type、Impact Analysis、Reference Implementation Research（research_tier=full，含本地参考仓库不可用事实与替代依据）完整。
- [ ] 1.2 开发前使用 `batch-grill-me`（独立零记忆 grill subagent）审视 `design.md`，逐项确认 D1–D8 与开放问题 OQ-B1（B 轨具体任务清单）、OQ-V1（Verified 50 具体实例）；不得把 agent 推荐答案当作用户确认。
- [ ] 1.3 grill 产出 `reviews/grill-design.md` 后**停轮**把 `## Open Questions` 逐项抛给用户并等待明确答复（每条配具体例子/场景），用户答复记录进 `## User Confirmation`；收到答复前不写实现代码。
- [ ] 1.4 确认 spec delta（`benchmark` ADDED/REVISED）与 proposal Modified Capabilities 一致，且为向后兼容扩展。

## 2. 任务 schema 扩展

- [ ] 2.1 `TaskSpec` 新增 `scenario` 字段（5 枚举：bug-fix/feature-dev/refactor/debug/integration），`from_dict` 缺省兼容。
- [ ] 2.2 `difficulty` 归一化为 3 档枚举（easy/medium/hard），`validate()` 校验；swebench `<15 min fix` 映射规则落进 manifest/文档。
- [ ] 2.3 为 schema 扩展补单元测试（枚举校验、缺省兼容、旧任务 JSON 向后兼容）。
- [ ] 2.4 任务集 manifest 引入 `track`（A|B|verified）与套件级能力覆盖矩阵（7 能力列）声明。

## 3. 存量 26 去留 / 重打标

- [ ] 3.1 4 陈旧任务处理：002-sandbox-executor、004-benchmark-cli 重写为 B 轨当前 HEAD 任务；005-bash-workspace、021-lsp-diagnostics 按新架构改写（D4）。
- [ ] 3.2 2 gold.patch 空（018-warning-passes、020-close-clients）补参考实现；若成本过高按 D4 降级并入评测基建任务并记录原因。
- [ ] 3.3 1 弱评估（022-collaborative-context-audit）补结构校验（确定性断言审计报告章节/格式）。
- [ ] 3.4 其余 19–20 保留 A 轨，重打 `scenario`/`difficulty` 标签（按 issue.md 实际改动类型 + 预期解决投入）。
- [ ] 3.5 重打标后跑存量 benchmark smoke，确认 A 轨任务逻辑不回归（重打标不改逻辑，只改元数据）。

## 4. B 轨新增任务（context-planning 优先）

- [ ] 4.1 按用户确认后的 OQ-B1 落 B 轨任务清单（12–16 条），含 context-planning 3–5、long-term-memory +1、long-context +1–2、每场景 ≥1–2、2–3 条 hard。
- [ ] 4.2 每个 B 轨任务测试先行：先写问题描述（issue.md）、验证命令/gold patch，再落任务。
- [ ] 4.3 B 轨任务覆盖矩阵校验通过（每能力列、每场景列 ≥1 任务）。
- [ ] 4.4 B 轨任务至少跑通 1 条 smoke（`--tasks <glob>` 单任务验证）。

## 5. Verified 50 子集接入

- [ ] 5.1 按用户确认后的 OQ-V1 生成 Verified 50 fixture（保留 10 现有 + 轻量中等池过滤 KNOWN_BAD 补齐，不含 django/sphinx）。
- [ ] 5.2 fixture 元数据校验（instance_id/dataset_name/dataset_split 齐全、无 KNOWN_BAD、difficulty 映射 easy 等）。
- [ ] 5.3 实现/确认 L1 本地轻量验证路径（免 Docker 实例的本地 test_command 验证）。
- [ ] 5.4 L3 金补丁自检脚本：所选子集跑 gold.patch 确认可复现，剔除 flaky/坏实例。
- [ ] 5.5 子集污染披露文案（KNOWN_BAD 过滤、偏置、数据集/包版本钉住 4.1.x）落进结果页/文档；[C2] 结果页渲染归 C2/C3。

## 6. 反作弊披露

- [ ] 6.1 A 轨反作弊泄漏披露文案落进任务集 manifest/结果页（"回归基线、非公平评测"定位 + 来源/时间范围披露）。[spec]
- [ ] 6.2 shallow/mirror 克隆截断历史记录为后续加固项（不实现），在 change 文档记触发条件。[spec]

## 7. spec delta 落定（含 C2 需求文本）

- [ ] 7.1 修订 spec `任务支持显式能力分层` Requirement → 场景×难度双标签 + 套件级能力覆盖矩阵（D2）。[spec]
- [ ] 7.2 修订 `Pass@k 稳定性指标` → `pass^k` 改名 + pass@1/pass@k/pass^k 三分定义（G3 M1）。[spec]
- [ ] 7.3 新增任务 schema（scenario/difficulty）、任务集三来源组成、Verified 子集接入、反作弊披露 Requirement（D1/D3/D6/D7）。[spec]
- [ ] 7.4 新增 G3 M1–M11 指标/方法对应 Requirement（指标三分/采样/成本/失败归因/报告元组/污染披露/配对比较/f2p-p2p/小N/过程效率）。[spec] [C2]
- [ ] 7.5 将本 change 的 `benchmark` delta 同步到当前规格 `openspec/specs/benchmark/spec.md`。[spec]

## 8. 同步与验证

- [ ] 8.1 维护 Impact Analysis，清理开发中发现的 `unknown`/`TBD`/`待确认`。
- [ ] 8.2 维护 Reference Implementation Research 最终结论；调研结论变化先回写 change 文档。
- [ ] 8.3 更新 `docs/benchmark-plan.md` 任务数口径（34→26 + 三来源目标），README 如涉及任务数同步（含 README_EN）。
- [ ] 8.4 运行相关单元/集成测试与全量测试。
- [ ] 8.5 运行 `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` 与 `uv run python scripts/check_openspec_artifacts.py`。
- [ ] 8.6 跑通至少一个 benchmark smoke（一组本地任务），确认 schema 扩展/重打标后全链路不回归。

## 9. 审阅与 PR 收尾

- [ ] 9.1 运行 `/review-loop`（独立零记忆 subagent 审阅 → verdict → CHANGES_REQUESTED 则修复 + 回归测试 → 再审至 PASS/3 轮封顶），产出 `reviews/building-review.md` + review manifest。
- [ ] 9.2 将本 change 归档到 `openspec/changes/archive/YYYY-MM-DD-<change-id>/`。
- [ ] 9.3 从 `docs/openspec-change-backlog.md` 移除/更新本 change 并同步批次。
- [ ] 9.4 确认 Impact Analysis 与 Reference Implementation Research 无残留未解释项，跑最终 validate + artifact checker。
- [ ] 9.5 发起实现 PR；合入后给跟踪 issue #154 添加完成说明 comment 并关闭。
