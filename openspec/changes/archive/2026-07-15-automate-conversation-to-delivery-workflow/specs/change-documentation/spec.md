## MODIFIED Requirements

### Requirement: Handoff state file artifact

每个准备进入 PR 的 OpenSpec change SHALL 包含由 Workflow Control Plane 生成的最小签名 `workflow-receipt.json`，用于代码审查和 CI 审计。实时状态和完整事件 SHALL 以项目外 event store 为权威；Receipt SHALL 是 Host 在完整历史验证后签发的去敏证明，不得由 agent 直接维护。

#### Scenario: Requirements 批准后创建 Change

- **GIVEN** requirements gate 获得有效人工批准
- **WHEN** 控制面创建 design worktree 和 OpenSpec change
- **THEN** SHALL 在 event store 中记录 workflow/change/template/workspace binding
- **AND** SHALL NOT 要求把完整事件写入 Git

#### Scenario: Closing 生成 Receipt

- **WHEN** workflow 到达 closing 的 PR-ready 前置步骤
- **THEN** Host SHALL 重放并验证完整 event history
- **AND** 验证通过后 SHALL 生成并签名 workflow-receipt.json
- **AND** agent SHALL NOT 通过编辑 Receipt 推进实时状态

#### Scenario: Change 准备 PR

- **WHEN** change 准备创建或更新 PR
- **THEN** 提交内容 SHALL 包含最小签名 workflow-receipt.json
- **AND** Receipt SHALL 包含 event-chain root、必需 Gate 摘要、artifact/evidence hash 和 base commit
- **AND** SHALL NOT 包含完整事件、聊天消息、approval secret、本地绝对路径或未脱敏敏感参数

#### Scenario: Archived Change 仍接受审计

- **WHEN** change 移入 `openspec/changes/archive/`
- **THEN** artifact checker 和 CI SHALL 继续验证其 workflow-receipt.json
- **AND** SHALL NOT 因 active 目录已移除而跳过 history 校验
