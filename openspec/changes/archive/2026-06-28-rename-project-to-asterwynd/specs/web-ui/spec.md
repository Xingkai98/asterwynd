## MODIFIED Requirements

### Requirement: FastAPI app 提供静态资源和 WebSocket

Web UI SHALL 通过 FastAPI 创建应用，提供静态页面、品牌资产静态路径和 WebSocket 交互入口。

#### Scenario: 创建 app

- **GIVEN** CLI 提供 LLM 实例
- **WHEN** 调用 `create_app(llm)`
- **THEN** 系统 SHALL 创建可由 uvicorn 运行的 FastAPI app
- **AND** Web UI SHALL 提供品牌 wordmark 静态资源访问路径

## ADDED Requirements

### Requirement: Web UI 命名品牌 wordmark

Web UI SHALL 在 header 中命名当前正式项目名的 wordmark，并在窄屏或图片不可用时保持可读文本降级。

#### Scenario: header 命名品牌

- **GIVEN** 用户打开 Web UI
- **WHEN** 页面静态资源加载完成
- **THEN** header SHALL 命名 Asterwynd wordmark 或等价文本
- **AND** 该命名 SHALL NOT 遮挡 session id、run id、mode 控件、tabs 或状态文本

#### Scenario: 小屏降级

- **GIVEN** 用户在很窄的移动端视口打开 Web UI
- **WHEN** wordmark 图像空间不足
- **THEN** header SHALL 使用可读文本形式命名品牌名
