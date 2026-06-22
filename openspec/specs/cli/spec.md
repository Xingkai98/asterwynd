# cli 规格

## Purpose

定义 Typer CLI 的命令入口、参数、非交互运行、Web 启动和 benchmark 启动。当前入口为 `cli.py`。

## Requirements

### Requirement: CLI 构造默认 AgentLoop

CLI SHALL 通过 provider、model、ToolRegistry、HookManager 和 MemoryManager 构造默认 AgentLoop。

#### Scenario: build_agent

- **GIVEN** 用户选择 provider 和可选 model
- **WHEN** CLI 调用 `build_agent`
- **THEN** 系统 SHALL 构造 LLM
- **AND** 注册默认工具
- **AND** 配置 LoggingHook、TracingHook 和 MemoryManager

### Requirement: CLI 接入统一配置

CLI `main`、`web` 和 `benchmark` 命令 SHALL 支持 `--config <path>`，并在入口层解析统一配置。未显式传入 `--mode` 时，CLI SHALL 使用配置中的 `agent.default_mode`。

#### Scenario: main 使用配置默认 mode

- **GIVEN** `myagent.yaml` 设置了 `agent.default_mode`
- **AND** 用户未传入 `--mode`
- **WHEN** CLI 执行 `main`
- **THEN** CLI SHALL 使用配置默认 mode 构造 AgentLoop

#### Scenario: CLI mode 覆盖配置

- **GIVEN** `myagent.yaml` 设置了默认 mode
- **AND** 用户显式传入 `--mode`
- **WHEN** CLI 构造运行配置
- **THEN** CLI SHALL 使用显式 mode

### Requirement: main 命令支持单轮和交互

`main` 命令 SHALL 支持默认单轮模式和 `--interactive` 交互模式。

#### Scenario: 单轮 prompt

- **GIVEN** 用户提供 prompt
- **WHEN** 未设置 `--interactive`
- **THEN** CLI SHALL 执行 `run_single`

#### Scenario: 交互模式

- **GIVEN** 用户设置 `--interactive`
- **WHEN** CLI 启动
- **THEN** CLI SHALL 执行 `run_interactive`

### Requirement: web 命令启动 Web UI

`web` 命令 SHALL 接收 host、port、provider 和 model 参数，构造 LLM 并启动 FastAPI 应用。

#### Scenario: 启动 web

- **GIVEN** 用户执行 `uv run python cli.py web --port 8000`
- **WHEN** 命令启动成功
- **THEN** CLI SHALL 输出访问地址、provider、model 和 debug 状态
- **AND** 使用 uvicorn 运行 app

### Requirement: benchmark 命令选择 runner

`benchmark` 命令 SHALL 支持 fake、shell、myagent 和 claude runner，并把任务目录交给 BenchmarkRunner。

#### Scenario: shell runner 缺少命令

- **GIVEN** 用户选择 `--agent shell`
- **WHEN** 未提供 `--shell-command`
- **THEN** CLI SHALL 输出错误
- **AND** 退出
