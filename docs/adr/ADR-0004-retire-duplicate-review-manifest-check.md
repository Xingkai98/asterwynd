# ADR-0004: 下掉与 witnessloop 重复的本仓 review manifest 校验

- **Status**: accepted
- **Date**: 2026-10-17
- **Deciders**: 用户裁决（issue #316 第一刀方向）、主 agent、独立 grill / 设计对抗审阅者

## Context

本仓同时维护两套审阅 manifest：

- **asterwynd 形态**：`reviews/<phase>-review-manifest.json`（schema `review-manifest/v1`），
  由 `agent/workflow/review_manifest.py` 产出，`scripts/check_openspec_artifacts.py` 消费；
- **witnessloop 形态**：`reviews/<stage>.manifest.json`（schema
  `witnessloop/review-manifest@v1`），由 `witnessloop manifest build` 产出，required 的
  `gate / check` 消费。

issue #316 的探索 comment（2026-10-17）逐字段对照后给出四个候选，并推荐 **(d)**：保留两套，
在收尾时从 witnessloop 形态自动派生 asterwynd 形态。但两套不是同一份内容的两个文件名：
`spec_hash` 算法不同、80 份历史 manifest 无法干净迁移（27 份 `tasks_hash` 漂移、8 份提交
不可解析、全部缺 `author_run_id`）。用户在探索之后明确裁决第一刀改为**下掉与 witnessloop
重复的本仓校验**，而不是继续维护/派生第二份。

关键约束是「不放宽任何判据」：witnessloop 明确不读 `verdict`，所以 building review 的
`PASS` 门是本仓独有、不能随 manifest 校验一起删除。

## Decision

采用「下掉重复校验 + 保留极小 verdict 检查」：

1. 删除 `_check_review_manifests` 及 active / `--check-archived` 两个调用点；本仓不再要求、
   产出或校验 `reviews/<phase>-review-manifest.json`。
2. 保留 building review 的终结 `PASS` 判据，改由 `reviews/building-review.md` 的
   `## 闭环出口` 承载：
   - **宽触发**：任何已存在报告的 terminal `BLOCKED` / `CHANGES_REQUESTED` 一律报错（不看
     change 类型、spec delta 或 tasks 勾选）；
   - **完成面**：active 的「非 docs + spec delta + tasks 全勾」与归档点的「本 PR 新建非 docs
     + spec delta 归档目录」要求出口存在且为 `PASS`；
   - `未定` / 缺小节只在完成面报错，历史归档不追溯。
3. `--check-archived` 收窄为归档事件日志可投影校验；历史 80 份 ast manifest 保持冻结。
4. `agent/workflow/review_manifest.py`、其测试、`workflow_state.py review-manifest` 写通道
   与 `flow-policy.json` 的受保护规则保留为 legacy，由第二刀处置。

**第二刀已完成**（`retire-manifest-module`，PR 见该 change）：上述 legacy 资产已全部删除，
80 份历史 manifest 冻结；决策与备选见 [ADR-0005](./ADR-0005-retire-legacy-review-manifest-module.md)。

## Alternatives Considered

| 备选方案 | 描述 | 拒绝原因 |
|----------|------|---------|
| (a) witnessloop 接受 asterwynd schema | 改 witnessloop 的 glob / 必填字段 / 哈希算法 | 要放弃 D4（`reviewer != author`）与孤儿规则，或把两份都变成超集；仍需为 grill / grill-adversarial 产 witnessloop manifest，不能收敛成一套 |
| (b) asterwynd 改用 witnessloop schema 并废掉自己那份（不做 verdict 补偿） | 只产 witnessloop 形态 | 80 份历史 manifest 无法真实迁移（缺 `author_run_id`、8 份提交缺失、27 份 tasks 漂移），且 witnessloop 不读 verdict ⇒ PASS 门消失；本 ADR 保留 verdict 检查，因此只采纳「废掉 ast manifest」这一半 |
| (c) 公共超集 schema | 两仓协同定义 v2 | 协调成本最高（witnessloop 发版 + 升级 caller ref），一次 change 无法完成 |
| (d) 保留两套并自动派生（#316 推荐） | 从 witnessloop manifest 确定性生成 ast manifest | 仍有两份物理文件与一条派生命令；用户裁决第一刀直接下掉重复校验，回到一套 |

## Consequences

- 正面影响：每个 change 只维护一套 review manifest；删除约 40 行重复校验逻辑；RIR / Impact /
  benchmark / backlog / 归档点其它门行为不变。
- 负面影响：`diff_hash` 强校验、`--check-archived` 历史 drift 检测、非 building
  `*-review.md` 的 PASS 门消失；完成面之外的 `未定` / 缺出口报告不再报错。均已在
  `docs/known-debt.md` 登记。
- 需要的相关变更：`AGENTS.md` / README 双语 / development-guide / requirements-process /
  interview-script 的规则口径；`dev-workflow-gate` / `dev-workflow-state-machine` /
  `platform-gate` 的规格 delta；本地 `.claude/commands/review-loop.md` 改为只产 witnessloop
  形态。

## Revisit Conditions

- [x] 第二刀已完成（`retire-manifest-module`）：`review_manifest.py` / CLI / 受保护路径规则 / resume audit 忽略项已删除；80 份历史 manifest 冻结。见 ADR-0005。
- [ ] witnessloop 开始读取或校验 `verdict`，且本仓不再需要本地 `## 闭环出口` 检查。
- [ ] 需要恢复历史归档的 manifest drift 检测或 `diff_hash` 强校验。
