## REMOVED Requirements

### Requirement: main 命令支持单轮和交互

**Reason**: `main` 子命令被替换为 `@app.callback(invoke_without_command=True)` 默认交互 + `run` 子命令单轮。交互/单轮不再通过 `--interactive` flag 区分，而是通过是否提供子命令区分。

**Migration**: `asterwynd main "prompt"` → `asterwynd run "prompt"`；`asterwynd main --interactive` → `asterwynd`；`--interactive` 选项不再支持。

## MODIFIED Requirements

### Requirement: CLI 构造默认 AgentLoop

系统 SHALL 从 `agent/main.py` 构造 AgentLoop，通过 provider、model、ToolRegistry、HookManager 和 MemoryManager 配置。根目录 `cli.py` SHALL NOT 存在。`pyproject.toml` 的 `[project.scripts]` SHALL 指向 `agent.main:app`。`@app.callback(invoke_without_command=True)` SHALL 处理无子命令时的默认交互行为。

#### Scenario: 入口模块正确加载

- **GIVEN** 用户通过 `pip install asterwynd` 安装
- **WHEN** 用户执行 `asterwynd`
- **THEN** 系统 SHALL 从 `agent.main:app` 加载 Typer 应用
- **AND** 无子命令时 SHALL 进入交互 REPL

#### Scenario: 根 `cli.py` 不存在

- **GIVEN** 项目已安装或构建为 wheel
- **WHEN** 检查 wheel 内容或包目录
- **THEN** 根目录 `cli.py` SHALL NOT 存在
- **AND** `python cli.py` SHALL NOT 可用（文件不存在）

### Requirement: CLI 接入统一配置

`run`、`web` 和 `benchmark` 子命令 SHALL 各自独立支持 `--config <path>` 和 `--mode` option。未显式传入 `--mode` 时，各命令 SHALL 使用配置中的 `agent.default_mode`。

#### Scenario: run 使用配置默认 mode

- **GIVEN** `asterwynd.yaml` 设置了 `agent.default_mode`
- **AND** 用户未传入 `--mode`
- **WHEN** CLI 执行 `asterwynd run "hello"`
- **THEN** CLI SHALL 使用配置默认 mode 构造 AgentLoop

#### Scenario: CLI mode 覆盖配置

- **GIVEN** `asterwynd.yaml` 设置了默认 mode
- **AND** 用户显式传入 `--mode plan`
- **WHEN** CLI 执行 `asterwynd run "hello" --mode plan`
- **THEN** CLI SHALL 使用 `plan` mode

### Requirement: web 命令启动 Web UI

`web` 子命令 SHALL 接收 host、port、provider、model、mode 和 config_path 参数，参数 SHALL 独立声明（不受 callback 或其他子命令影响）。

#### Scenario: 启动 web

- **GIVEN** 用户执行 `asterwynd web --port 8000`
- **WHEN** 命令启动成功
- **THEN** CLI SHALL 输出访问地址、provider、model 和 debug 状态
- **AND** 使用 uvicorn 运行 app

## ADDED Requirements

### Requirement: run 子命令单轮执行

`asterwynd run <prompt>` SHALL 执行单轮 Agent 运行。`run` 子命令 SHALL 接收 `--model`、`--provider`、`--max-iterations`、`--system`、`--mode` 和 `--config` option。

#### Scenario: 单轮 prompt

- **GIVEN** 用户执行 `asterwynd run "hello"`
- **WHEN** 提供 prompt 参数
- **THEN** 系统 SHALL 执行单轮 Agent 运行
- **AND** SHALL NOT 显示品牌 banner

#### Scenario: run 子命令不冲突 web/benchmark

- **GIVEN** 用户安装 asterwynd
- **WHEN** 用户执行 `asterwynd web --port 8000`
- **THEN** 系统 SHALL 启动 Web UI（不会将 `web` 解析为 prompt）
- **WHEN** 用户执行 `asterwynd benchmark benchmarks/tasks --agent fake`
- **THEN** 系统 SHALL 执行 benchmark

#### Scenario: benchmark 使用独立 --config

- **GIVEN** 用户执行 `asterwynd benchmark benchmarks/tasks --agent fake --config asterwynd.yaml`
- **WHEN** 提供 `--config` option
- **THEN** 系统 SHALL 使用指定配置文件的 benchmark 设置
- **AND** benchmark 的 `--config` SHALL 不影响 run 或 web 的配置

### Requirement: 默认交互模式（callback）

`asterwynd` 无子命令时 SHALL 进入交互 REPL。交互模式 SHALL 显示品牌 banner（可通过 `--no-banner` 关闭）和 Session ID。交互模式 SHALL 支持 `--provider`、`--model`、`--max-iterations`、`--system`、`--mode`、`--config` option。callback SHALL NOT 声明 positional argument。

#### Scenario: 默认交互

- **GIVEN** 用户安装后执行 `asterwynd`
- **WHEN** 无子命令
- **THEN** 系统 SHALL 进入交互 REPL
- **AND** SHALL 显示品牌 banner 和 Session ID

#### Scenario: 交互模式配置 provider/model

- **GIVEN** 用户执行 `asterwynd --model gpt-4o-mini --mode plan`
- **WHEN** 无子命令
- **THEN** 系统 SHALL 使用指定 model 和 mode 进入交互 REPL

#### Scenario: 关闭 banner

- **GIVEN** 用户执行 `asterwynd --no-banner`
- **WHEN** 无子命令
- **THEN** 系统 SHALL 进入交互 REPL
- **AND** SHALL NOT 显示品牌 banner

#### Scenario: main 子命令不可用

- **GIVEN** 用户安装 asterwynd
- **WHEN** 用户执行 `asterwynd main "hello"`
- **THEN** 系统 SHALL 报错，提示子命令不存在
- **AND** SHALL NOT 进入 Agent 运行

#### Scenario: --interactive 不可用

- **GIVEN** 用户安装 asterwynd
- **WHEN** 用户执行 `asterwynd --interactive`
- **THEN** 系统 SHALL 报错，提示未知 option

### Requirement: 日志目录使用 platformdirs

系统 SHALL 使用 `platformdirs.user_log_path("asterwynd")` 作为日志目录。Linux 下 SHALL 尊重 `$XDG_STATE_HOME`（默认 `~/.local/state/asterwynd/log/`），macOS 为 `~/Library/Logs/asterwynd/`，Windows 为对应 AppData 路径。目录不存在时 SHALL 自动创建。

#### Scenario: 默认日志路径

- **GIVEN** 用户运行 asterwynd
- **WHEN** 系统需要写日志
- **THEN** 日志 SHALL 写入 `platformdirs.user_log_path("asterwynd")`
- **AND** 目录不存在时 SHALL 自动创建

#### Scenario: 尊重 XDG_STATE_HOME

- **GIVEN** Linux 环境设置了 `XDG_STATE_HOME=/custom/state`
- **WHEN** 系统需要写日志
- **THEN** 日志 SHALL 写入 `/custom/state/asterwynd/log/`

### Requirement: CLI 文档命令示例使用统一入口

项目文档中的 CLI 命令示例 SHALL 以 `asterwynd` 为统一入口（开发时加 `uv run` 前缀）。

#### Scenario: README 命令示例

- **GIVEN** 用户阅读 README.md 或 README_EN.md
- **WHEN** 看到快速开始命令
- **THEN** 命令 SHALL 为 `uv run asterwynd` 或 `uv run asterwynd run "Hello"`
- **AND** SHALL NOT 包含 `python cli.py main` 形式
