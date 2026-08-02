# Dev Workflow State Machine Spec

## ADDED Requirements

### Requirement: 开发流程精简为 OpenSpec 主干 + 强制审阅闭环

开发流程 SHALL 精简为「OpenSpec 主干」（proposal → batch-grill-me → worktree → TDD → spec sync → PR）加「实现完成后强制独立 subagent 审阅闭环」。原四阶段状态机仪式（phase/sub_state 推进、handoff.json、gate 停止）SHALL 停用，不再作为开发流程的强制要求。审阅证据 SHALL 存放于 `openspec/changes/<id>/reviews/`（随 change 进 PR，CI 可机械校验），非 docs + 有 spec delta + tasks 全部勾选的 change SHALL 有 building-review.md + manifest 且 verdict 为 PASS。

#### Scenario: 实现完成的新 change 提交 PR

- **GIVEN** 一个非 docs change 已实现且 tasks.md 全部勾选
- **WHEN** 提交 PR 前运行 artifact checker
- **THEN** 检查器 SHALL 验证 `openspec/changes/<id>/reviews/building-review.md` 存在
- **AND** 对应 manifest 存在且 verdict 为 PASS
- **AND** 缺审阅证据 SHALL 报错并阻止合入

#### Scenario: 部分实现的 change 不受拦截

- **GIVEN** 一个 change 处于提案或部分实现阶段（tasks.md 有未勾选项）
- **WHEN** 运行 artifact checker
- **THEN** 检查器 SHALL 不要求审阅证据（避免误伤在途 change）

#### Scenario: 状态机仪式停用

- **GIVEN** 开发流程精简已生效
- **WHEN** agent 开始新 change 开发
- **THEN** 无需 phase/sub_state 推进、handoff.json 或 gate 停止
- **AND** 开发流程遵循 OpenSpec 主干 + 实现完成后 `/review-loop` 审阅闭环
