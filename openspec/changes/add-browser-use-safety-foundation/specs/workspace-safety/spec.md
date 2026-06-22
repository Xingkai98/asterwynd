## ADDED Requirements

### Requirement: browser artifacts 存储受 workspace policy 约束

Browser screenshots、HTML snapshots 和日志 artifacts SHALL 保存到 workspace policy 允许的目录，并避免写入 denied paths。

#### Scenario: browser artifact 路径被拒绝

- **GIVEN** browser tool 请求保存 artifact 到 denied path
- **WHEN** WorkspacePolicy 校验写入路径
- **THEN** 系统 SHALL 拒绝保存
