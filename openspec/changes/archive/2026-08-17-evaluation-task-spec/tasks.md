# Tasks: evaluation-task-spec（C1）

> 标注约定：`[spec]` = 规格落定任务（本 change 完成）；`[C2]` = Requirement 文本已落、实现归 C2 `evaluation-metrics`（本 change 只落 spec，不写实现代码）。

## 1. 规格与设计定稿

- [x] 1.1 确认 proposal 的 Change Type、Impact Analysis、Reference Implementation Research（research_tier=full，含本地参考仓库不可用事实与替代依据）完整。
- [x] 1.2 开发前使用 `batch-grill-me`（独立零记忆 grill subagent）审视 `design.md`，逐项确认 D1–D8 与开放问题 OQ-B1（B 轨具体任务清单）、OQ-V1（Verified 50 具体实例）；不得把 agent 推荐答案当作用户确认。
- [x] 1.3 grill 产出 `reviews/grill-design.md` 后**停轮**把 `## Open Questions` 逐项抛给用户并等待明确答复（每条配具体例子/场景），用户答复记录进 `## User Confirmation`；收到答复前不写实现代码。
- [x] 1.4 确认 spec delta（`benchmark` ADDED/REVISED）与 proposal Modified Capabilities 一致，且为向后兼容扩展。

## 2. 任务 schema 扩展

- [x] 2.1 `TaskSpec` 新增 `scenario` 字段（5 枚举：bug-fix/feature-dev/refactor/debug/integration），`from_dict` 缺省兼容。
- [x] 2.2 `difficulty` 归一化为 3 档枚举（easy/medium/hard），`validate()` 校验；swebench `<15 min fix` 映射规则落进 manifest/文档。
- [x] 2.3 为 schema 扩展补单元测试（枚举校验、缺省兼容、旧任务 JSON 向后兼容）。
- [x] 2.4 任务集 manifest 引入 `track`（A|B|verified）与套件级能力覆盖矩阵（7 能力列）声明。

## 3. 存量 26 去留 / 重打标

- [x] 3.1 4 陈旧任务处理：002-sandbox-executor、004-benchmark-cli 重写为 B 轨当前 HEAD 任务；005-bash-workspace、021-lsp-diagnostics 按新架构改写（D4，OQ-2 确认归 B 轨）。
- [x] 3.2 2 gold.patch 空（018-warning-passes、020-close-clients）补参考实现（从合入 commit 提取，base_commit 验证通过）。
- [x] 3.3 1 弱评估（022-collaborative-context-audit）补结构校验（test.patch 三章节 + 真实类名/字段断言）。
- [x] 3.4 其余 22 个保留 A 轨，重打 `scenario`/`difficulty` 标签（按 issue.md 实际改动类型 + 预期解决投入）。
- [x] 3.5 重打标后跑存量 benchmark smoke，确认 A 轨任务逻辑不回归（重打标不改逻辑，只改元数据）。

## 4. B 轨任务（context-planning 优先）

- [x] 4.1 按用户确认后的 OQ-B1 落 B 轨任务清单。**实际交付 5 条（4 陈旧重写 + 1 新增），较目标 12–16 收敛**：4 重写（002 沙箱命令审计字段 / 004 CLI --list-tasks / 005 mv-cp 工作区边界 / 021 LSP language 覆盖）+ 1 新增（asterwynd-b01 结果页按 task_family 分组，承担 integration 场景 + long-context 能力）。覆盖矩阵机械校验每能力列/每场景列 ≥1 已达标；context-planning 能力列由 A 轨 010/022-audit 覆盖。收敛原因：上下文/数据约束下优先保证覆盖矩阵完整与每任务红绿可复现；完整 12–16 目标记为 B 轨扩展，收尾披露（tasks 9.x 记录）。b01 的 long-context 为**轻量形态**（issue 给出 report.py 路径，但需通读 report/models/statistics 三模块；与 OQ-B1 确认的「强制大读取+不给路径」理想形态有偏差，审阅 I2 记录，接受为覆盖矩阵达标的最小实现）。
- [x] 4.2 每个 B 轨任务测试先行：先写问题描述（issue.md）、验证命令/gold patch，再落任务；全部红绿验证（base+test 红、+gold 绿）。
- [x] 4.3 B 轨任务覆盖矩阵校验通过（`validate_coverage`：7 能力列 + 5 场景列全 ≥1、无未知任务 id）。
- [x] 4.4 B 轨任务至少跑通 1 条 smoke（fake runner 含 asterwynd-b01 发现/执行）。

## 5. Verified 50 子集接入

- [~] 5.1 **部分完成（生成阻塞）**：`benchmarks/swebench_subset.py` 已交付配比选择（OQ-V1：requests+4/flask+6/pytest+8/sympy+8/seaborn+6/pylint+8）与 KNOWN_BAD/重实例/空 test_patch 过滤逻辑 + 生成 CLI；**40 条新 fixture 未实际生成**——本环境 huggingface（princeton-nlp/SWE-bench_Verified）不可达（load_dataset 超时），实际生成需在数据可访问环境执行 `build_subset` 后按 `swebench_convert.py` 模板落 fixture。现有 10 fixture 保留。
- [x] 5.2 fixture 元数据校验（validate_fixture：instance_id/dataset_name/dataset_split/track=verified/scenario=bug-fix/difficulty 归一化/execution_environment），现有 10 条全部通过。
- [x] 5.3 实现/确认 L1 本地轻量验证路径（task_schema 允许 swebench+local；runner 已有 local+external_repo → clone+install+test_command 路径）。
- [x] 5.4 L3 金补丁自检脚本（`swebench_subset.py gold_check`：检出 base_commit → 应用 gold.patch → 跑 test_command，剔除 flaky/坏实例）。
- [x] 5.5 子集污染披露文案落进 spec（`SWE-bench 污染披露` Requirement）与 manifest（KNOWN_BAD 过滤、现有 fixture 偏置、版本钉住）；结果页渲染归 C2/C3。

## 6. 反作弊披露

- [x] 6.1 A 轨反作弊泄漏披露文案落进任务集 manifest/结果页（"回归基线、非公平评测"定位 + 来源/时间范围披露）。[spec]
- [x] 6.2 shallow/mirror 克隆截断历史记录为后续加固项（不实现），design D7 记触发条件。[spec]

## 7. spec delta 落定（含 C2 需求文本）

- [x] 7.1 修订 spec `任务支持显式能力分层` Requirement → 场景×难度双标签 + 套件级能力覆盖矩阵（D2）。[spec]
- [x] 7.2 修订 `Pass@k 稳定性指标` → `pass^k` 改名 + pass@1/pass@k/pass^k 三分定义（G3 M1）。[spec]
- [x] 7.3 新增任务 schema（scenario/difficulty）、任务集三来源组成、Verified 子集接入、反作弊披露 Requirement（D1/D3/D6/D7）。[spec]
- [x] 7.4 新增 G3 M1–M11 指标/方法对应 Requirement（指标三分/采样/成本/失败归因/报告元组/污染披露/配对比较/f2p-p2p/小N/过程效率），9 个归 C2 Requirement 加「实现归 C2 evaluation-metrics」注记。[spec] [C2]
- [x] 7.5 将本 change 的 `benchmark` delta 同步到当前规格 `openspec/specs/benchmark/spec.md`（workflow-events 记录 current_spec_synced）。[spec]

## 8. 同步与验证

- [x] 8.1 维护 Impact Analysis，清理开发中发现的 `unknown`/`TBD`/`待确认`（无残留）。
- [x] 8.2 维护 Reference Implementation Research 最终结论（无新调研结论变化）。
- [x] 8.3 更新 `docs/benchmark-plan.md` 任务数口径（34→26 + 三来源目标），README/README_EN/tasks-README 同步。
- [x] 8.4 运行相关单元/集成测试与全量测试（2007 passed；5 个 MCP 测试失败为环境性，master 上同样失败，与本 change 无关）。
- [x] 8.5 运行 `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`（30 passed）与 `uv run python scripts/check_openspec_artifacts.py`（passed）。
- [x] 8.6 跑通至少一个 benchmark smoke（fake runner 含 A/B 轨任务，schema 扩展/重打标后全链路不回归）。

## 审阅修复记录（review-loop Round 1 → CHANGES_REQUESTED）

- **I1（中）文档任务数 off-by-one**：新增 b01 后本地任务 26→27、总 36→37，README/README_EN/benchmark-plan/tasks-README 未同步。修复：4 处文档 26→27、36→37（已提交）。
- **I2（低）b01 long-context 轻量形态**：与「大读取+不给路径」理想形态有偏差。处理：tasks 4.1 注明轻量形态，接受为覆盖矩阵最小实现。
- **I3（低）004 gold.patch help 文案**：「按 track 分组」与实际实现（只列 id）不符。修复：help 文案改为「总数 + 任务 id」。
- **I4（低）swebench_subset 健壮性**：gold_check 未用 python 参数移除；build_subset 对缺失 instance_id 跳过并计数。修复：已改 + 测试更新。

## 9. 审阅与 PR 收尾

- [x] 9.1 运行 `/review-loop`（独立零记忆 subagent 审阅 → verdict → CHANGES_REQUESTED 则修复 + 回归测试 → 再审至 PASS/3 轮封顶），产出 `reviews/building-review.md` + review manifest（Round 2 PASS）。
- [ ] 9.2 将本 change 归档到 `openspec/changes/archive/YYYY-MM-DD-<change-id>/`。
- [ ] 9.3 从 `docs/openspec-change-backlog.md` 移除/更新本 change 并同步批次。
- [ ] 9.4 确认 Impact Analysis 与 Reference Implementation Research 无残留未解释项，跑最终 validate + artifact checker。
- [ ] 9.5 发起实现 PR；合入后给跟踪 issue #154 添加完成说明 comment 并关闭。
