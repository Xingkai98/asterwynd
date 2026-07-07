## ADDED Requirements

### Requirement: Web UI 回归复用共享测试 LLM harness

Web server、WebSocket 和浏览器回归 SHALL 能通过共享 fake LLM harness 运行，不依赖真实 API key 或模型输出。真实 API 浏览器 E2E MAY 保留为显式 opt-in 验证。

#### Scenario: WebSocket fake LLM smoke

- **GIVEN** Web app 使用共享 fake LLM harness 创建
- **WHEN** 浏览器或测试客户端通过 WebSocket 发送聊天消息
- **THEN** Web session SHALL 通过真实 SessionManager 和 AgentLoop 运行
- **AND** WebSocket SHALL 返回 run event 和 fake assistant 回复

#### Scenario: Playwright fake LLM browser smoke

- **GIVEN** Playwright 打开使用共享 fake LLM harness 的 Web UI
- **WHEN** 用户发送普通消息
- **THEN** 页面 SHALL 展示 fake assistant 回复
- **AND** 测试 SHALL 不需要真实 API key

#### Scenario: Browser smoke 覆盖控制面基础交互

- **GIVEN** Playwright 打开 Web Chat
- **WHEN** 用户输入 slash command 前缀、执行 `/status`、执行 `/clear` 或切换 mode
- **THEN** 页面 SHALL 展示对应 suggestions、command result、消息清理和 mode 变化
- **AND** 这些控制面操作 SHALL NOT 启动普通 Agent run
