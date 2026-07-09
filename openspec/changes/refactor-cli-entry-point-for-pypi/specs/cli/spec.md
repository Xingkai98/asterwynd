## MODIFIED Requirements

### Requirement: CLI 入口模块与命令结构

CLI 入口逻辑 SHALL 位于 `agent/main.py` 包内模块。根目录 `cli.py` SHALL NOT 存在。`pyproject.toml` 的 `[project.scripts]` SHALL 指向 `agent.main:app`。

`@app.callback()` SHALL 作为默认入口：无参数时进入交互 REPL；提供 prompt 参数时执行单轮运行。

`web` 和 `benchmark` SHALL 作为独立子命令，各自声明参数，不共享顶层选项。

#### Scenario: 默认交互模式

- **GIVEN** 用户安装后执行 `asterwynd`
- **WHEN** 无参数
- **THEN** 系统 SHALL 进入交互 REPL
- **AND** SHALL 显示 Session ID 和品牌 banner（可 `--no-banner` 关闭）

#### Scenario: 单轮 prompt

- **GIVEN** 用户执行 `asterwynd "hello"`
- **WHEN** 提供 prompt 参数
- **THEN** 系统 SHALL 执行单轮 Agent 运行
- **AND** SHALL NOT 显示品牌 banner

#### Scenario: Web 子命令

- **GIVEN** 用户执行 `asterwynd web --port 8000`
- **WHEN** 提供 `web` 子命令
- **THEN** 系统 SHALL 启动 Web UI 服务
- **AND** `web` 的参数 SHALL 独立声明，不受 callback 选项影响

#### Scenario: Benchmark 子命令

- **GIVEN** 用户执行 `asterwynd benchmark benchmarks/tasks --agent fake`
- **WHEN** 提供 `benchmark` 子命令
- **THEN** 系统 SHALL 执行 benchmark
- **AND** `benchmark` 的参数 SHALL 独立声明

### Requirement: 运行时路径与 XDG 兼容

`.env` 加载 SHALL 使用 `python-dotenv` 默认 CWD 搜索。日志目录 SHALL 使用 XDG state 路径（`~/.local/state/asterwynd/logs/`）。

#### Scenario: 安装后 .env 加载

- **GIVEN** 用户通过 pip 全局安装 asterwynd
- **AND** CWD 或其父目录存在 `.env` 文件
- **WHEN** 用户运行 `asterwynd "hello"`
- **THEN** 系统 SHALL 自动加载该 `.env` 文件

#### Scenario: 日志写入 XDG 路径

- **GIVEN** 用户运行 asterwynd
- **WHEN** 系统需要写日志
- **THEN** 日志 SHALL 写入 `~/.local/state/asterwynd/logs/`
- **AND** 目录不存在时 SHALL 自动创建

### Requirement: pyproject.toml 包含完整 PyPI 元数据

`pyproject.toml` SHALL 包含 PyPI 发布所需的最小元数据：`license = "MIT"`、`classifiers`（Python 3.11/3.12/3.13、Environment、Topic）、repository URL 和足够详细的 `description`。

#### Scenario: wheel 包含完整元数据

- **GIVEN** 项目执行 `uv build`
- **WHEN** 生成 wheel 包
- **THEN** wheel 的 METADATA SHALL 包含 Name、Version、License、Classifier、Project-URL 和 Description
- **AND** `agent/main.py` SHALL 包含在 wheel 中
- **AND** 根目录 `cli.py` SHALL NOT 包含在 wheel 中

### Requirement: CLI 文档命令示例使用统一入口

项目文档中的 CLI 命令示例 SHALL 以 `asterwynd` 为统一入口（开发时加 `uv run` 前缀）。

#### Scenario: README 命令示例

- **GIVEN** 用户阅读 README.md 或 README_EN.md
- **WHEN** 看到快速开始命令
- **THEN** 命令 SHALL 为 `uv run asterwynd "Hello"` 或 `uv run asterwynd`
- **AND** SHALL NOT 包含 `python cli.py main` 形式
