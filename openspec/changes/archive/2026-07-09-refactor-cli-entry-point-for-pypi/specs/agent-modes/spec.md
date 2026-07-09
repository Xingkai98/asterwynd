## MODIFIED Requirements

### Requirement: 支持单轮 CLI 模式

系统 SHALL 通过 `asterwynd run <prompt>` 接收单个 prompt，构造 AgentLoop 并输出最终回复。入口模块 SHALL 为 `agent/main.py`。

#### Scenario: 非交互运行

- **GIVEN** 用户执行 `uv run asterwynd run "hello"`
- **WHEN** prompt 非空
- **THEN** CLI SHALL 执行一次 AgentLoop
- **AND** 输出最终 agent 内容和工具调用次数
- **AND** SHALL NOT 进入交互循环

#### Scenario: 非交互缺少 prompt

- **GIVEN** 用户执行 `asterwynd run` 不带 prompt
- **WHEN** 未提供 prompt
- **THEN** CLI SHALL 输出错误
- **AND** 以非零状态退出

### Requirement: 支持 CLI 交互模式

系统 SHALL 通过 `asterwynd` 无子命令进入多轮输入循环，并复用同一个 event loop 和消息历史。交互模式 SHALL 支持 `--provider`、`--model`、`--max-iterations`、`--system`、`--mode`、`--config` 和 `--banner/--no-banner` option。

#### Scenario: 用户连续输入

- **GIVEN** CLI 已通过 `asterwynd` 进入交互模式
- **WHEN** 用户输入多轮内容
- **THEN** 系统 SHALL 将每轮用户消息追加到同一消息列表
- **AND** 使用同一个 AgentLoop 继续运行

#### Scenario: 交互模式不可用 --interactive 进入

- **GIVEN** 用户安装 asterwynd
- **WHEN** 用户执行 `asterwynd --interactive`
- **THEN** 系统 SHALL 报错，提示 `--interactive` 选项不存在

### Requirement: 支持 Web 会话模式

系统 SHALL 通过 `asterwynd web --port <port>` 启动 Web UI，为每个 session 维护独立消息历史和 AgentLoop。`web` 子命令的 `--provider`、`--model`、`--mode`、`--config` option SHALL 独立声明。

#### Scenario: Web 启动

- **GIVEN** 用户执行 `asterwynd web --port 8000`
- **WHEN** 命令启动成功
- **THEN** CLI SHALL 输出访问地址、provider、model 和 debug 状态
- **AND** 使用 uvicorn 运行 app
- **AND** `web` 的 `--model` option SHALL NOT 影响 run 命令或交互模式的配置
