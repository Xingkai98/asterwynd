## MODIFIED Requirements

### Requirement: Agent 间 handoff

phase 间交接时，完成当前 phase 的 agent SHALL 生成 handoff note，为接手下一 phase 的 agent 提供上下文。Handoff note SHALL 默认作为本地协作临时材料存储在 `.handoff/<change-id>/`，不要求作为 PR artifact 提交。

`handoff` trigger 标记 agent 完成工作并生成 handoff note 的时刻，但不改变 state.phase。实际跨 phase 状态变更由 human gate 的 `human_review` trigger 驱动。handoff note 在 agent 到达 `ready_for_review` 时生成，transition 中记录 `trigger: handoff` 和 handoff note 路径；人确认后追加 `trigger: human_review` 的 transition 完成 phase 流转。

#### Scenario: 生成本地 handoff note

- **WHEN** agent 完成一个 phase 并准备交接给下一个 agent
- **THEN** agent SHALL 在 `.handoff/<change-id>/` 目录下生成 handoff note
- **AND** handoff note SHALL 包含: 本阶段完成内容、关键决策及原因、未选方案、待解决问题或风险、下一阶段入口点和优先级
- **AND** `.handoff/<change-id>/` 下的 handoff note SHALL 默认不提交到 Git

#### Scenario: 记录 handoff 路径

- **WHEN** agent 生成 handoff note
- **THEN** agent SHALL 在 `handoff.json` transitions 中记录 handoff note 的本地路径
- **AND** 同一工作区中的后续 agent MAY 直接读取该路径获取交接上下文

#### Scenario: 长期结论留存

- **WHEN** handoff note 中包含后续 PR、审计或长期维护需要依赖的关键结论
- **THEN** agent SHALL 将这些结论同步写入当前 change 的 OpenSpec 文档、`handoff.json` transition、设计/代码评审报告或稳定项目文档
- **AND** agent SHALL NOT 只依赖 `.handoff/` 中的本地文件保存长期事实

#### Scenario: 用户要求提交 handoff note

- **GIVEN** `.handoff/` 被工作区 `.gitignore` 忽略
- **WHEN** 用户明确要求把某份 handoff note 纳入 PR
- **THEN** agent SHALL 只对该指定文件使用 `git add -f`
- **AND** agent SHALL NOT 批量提交整个 `.handoff/` 目录
