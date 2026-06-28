## MODIFIED Requirements

### Requirement: main 命令支持单轮和交互

`main` 命令 SHALL 支持默认单轮模式和 `--interactive` 交互模式。交互模式 SHOULD 显示项目品牌 banner；单轮模式 SHALL NOT 默认显示品牌 banner。

#### Scenario: 单轮 prompt

- **GIVEN** 用户提供 prompt
- **WHEN** 未设置 `--interactive`
- **THEN** CLI SHALL 执行 `run_single`
- **AND** CLI SHALL NOT 输出品牌 banner

#### Scenario: 交互模式

- **GIVEN** 用户设置 `--interactive`
- **WHEN** CLI 启动
- **THEN** CLI SHALL 执行 `run_interactive`
- **AND** CLI SHOULD 输出 Asterwynd wordmark 和 slogan

#### Scenario: 交互模式关闭 banner

- **GIVEN** 用户设置 `--interactive --no-banner`
- **WHEN** CLI 启动
- **THEN** CLI SHALL 执行 `run_interactive`
- **AND** CLI SHALL NOT 输出 Asterwynd wordmark

### Requirement: web 命令启动 Web UI

`web` 命令 SHALL 接收 host、port、provider 和 model 参数，构造 LLM 并启动 FastAPI 应用。启动提示 SHOULD 使用当前正式项目名，同时保留运行时配置和 debug 状态。

#### Scenario: 启动 web

- **GIVEN** 用户执行 `uv run python cli.py web --port 8000`
- **WHEN** 命令启动成功
- **THEN** CLI SHALL 输出访问地址、provider、model 和 debug 状态
- **AND** 使用 uvicorn 运行 app
