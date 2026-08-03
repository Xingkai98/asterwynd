# Proposal: grill 用户确认门禁 — 设计追问后必须停轮拍板

## Change Type

primary: process
secondary:
  - change-documentation

## 需求

1. grill 之后，主 agent 必须把「Confirmed Decisions 摘要 + 每个 Open Question」抛给用户，收到明确答复前不得进入 building 写代码。
2. 用户的答复必须记录进 `reviews/grill-design.md` 的 `## User Confirmation` 节（可审计）。
3. 机械强制：
   - 写代码 gate（`scripts/workflow_guard.py`）：grill-design.md 存在但 Open Questions 未全部确认 → 仍拦截代码写。
   - 归档 checker（`scripts/check_openspec_artifacts.py`）：tasks 全勾选的已完成 change，若 Open Questions 非空且 User Confirmation 未覆盖全部 → 报错。

## 背景

issue #95 引入了 grill 门禁：独立零记忆 subagent 挑战 design.md，产出结构化决策记录 `reviews/grill-design.md`（`## Confirmed Decisions` ≥3 条 + `## Open Questions`）。但该门禁只保证「独立 grill 跑过」，不保证「用户拍板过」——checker 只校验决策记录存在，没有任何字段证明决策经过用户确认。

issue #74 开发暴露了实际偏差：主 agent 加载 batch-grill-me、用 workflow 跑了 4 视角审阅面板、产出 `design-grill.md`（12 项裁定，标注「agent 推荐答案待用户确认」），但**没有逐项停轮让用户确认**就自行按推荐答案进了 building。AGENTS.md 明确「agent 可以给推荐答案，但不能把自己的推断当作用户确认」——这条被踩线了。

本 change 把「用户确认」从自律约定升级为机械强制：确认记录必须存在、必须覆盖每个 Open Question、未确认则写代码被拦、归档被卡。

## 非目标

- 不防恶意伪造（与 #95 边界一致：独立执行只提高伪造成本 + 拦偶然跳过，不保证证据真实）。
- 不重做 OpenSpec 主干流程。
- 不追溯清理存量 change（archive 已被 `iter_change_dirs` 排除；当前 active changes 无 grill-design.md，无迁移负担）。

## Impact Analysis

| 影响面 | 说明 |
|---------|------|
| `scripts/check_openspec_artifacts.py` | `_check_design_review_task` 增加 User Confirmation 校验；新增 `_extract_open_questions`/`_extract_user_confirmations` helper |
| `scripts/workflow_guard.py` | `_grill_evidence_missing` 增强：grill-design.md 存在但未确认 Open Questions 仍视为缺证据 |
| `tests/test_openspec_artifact_checker.py` | 新增 User Confirmation 校验回归测试（通过/缺失/不完整/未确认全勾选） |
| `AGENTS.md` | 最高优先级规则增加「grill 后必须停轮确认，未确认不得进 building」 |
| `~/.claude/skills/batch-grill-me/SKILL.md`、`grilling/SKILL.md` | 停轮契约 + User Confirmation 节产出要求（本地安装件，不进 PR） |

## Reference Implementation Research

- status: enabled
- reason: 设计追问的「用户拍板」强制，与 plan mode 的 ExitPlanMode 审批、GitHub PR review 的 approval 机制同构——「人批准这个动作由 harness/机械层记录，agent 伪造不了」是共同原则。应参考本仓库 #95 grill-enforcement 与 review-loop 的 manifest 绑定机制。
- research questions:
  - plan mode（`agent/planning`）的 ExitPlanMode 如何记录用户批准？能否复用其「批准动作」语义？
  - review-loop 的 review manifest 如何绑定 reviewer/shas/hashes，grill 确认能否对称绑定？
- findings:
  - 本仓库已有 `agent/workflow/review_manifest.py`：把 review report 与 base/head sha、tasks/spec/diff/report hash 绑定。grill 的用户确认可沿用「记录在 change 目录 + checker 机械校验」的既有模式，无需引入新的批准通道。
  - plan mode 的 ExitPlanMode 是 harness 权限门禁（用户点同意才放行），但本 change 的范围是仓库级 checker/hook 强制；两条路径可并存，不互相依赖。
- design impact:
  - 确认记录落在 `reviews/grill-design.md` 的 `## User Confirmation` 节，与 #95 的决策记录同文件，避免新增文件类型。
  - workflow_guard 与 checker 共享同一组提取规则（Open Questions 条目数 / 确认记录数），两处实现要保持一致。

## Dependencies

- 依赖 #95 grill-enforcement（已合入）：`grill-design.md` 文件格式与 gate 骨架。
- 无未就绪模块。

## 验收

- 新 change 开发中，grill 后未收到用户确认 → workflow_guard 拦代码写。
- 已完成 change（tasks 全勾选）有未确认的 Open Question → checker 报错。
- 确认记录完整 → 两门禁均放行。
