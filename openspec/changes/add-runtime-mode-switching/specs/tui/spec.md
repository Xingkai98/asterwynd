## ADDED Requirements

### Requirement: 未来 TUI 复用 mode transition 语义

未来 TUI SHALL 复用 runtime mode transition API，不得单独实现一套与 CLI / Web 不兼容的 mode 切换逻辑。

#### Scenario: TUI 切换 mode

- **GIVEN** TUI 已接入 Agent runtime
- **WHEN** 用户在 TUI 中切换 mode
- **THEN** TUI SHALL 调用统一 mode transition API
- **AND** runtime SHALL 发布与 CLI / Web 一致的 mode_changed 事件
