# Design: refactor-cli-entry-point-for-pypi

## Context

Asterwynd 当前所有 CLI 逻辑放在根目录 `cli.py`（约 612 行），不符合 Python 包结构规范。`pyproject.toml` 的 `[project.scripts]` 声明 `asterwynd = "cli:app"`，但 `cli.py` 不在包内，wheel 构建后入口点解析存在隐患。

当前 `[tool.hatch.build.targets.wheel]` 的 `packages = ["agent"]` 只打包 `agent/` 目录，`cli.py` 需额外 `include`。此外 `pyproject.toml` 缺少 PyPI 必要元数据（license、classifiers、repository URL 等）。

同时存在设计问题：`main` 子命令语义模糊、`--interactive` 标志与交互优先的理念不一致、`logs/` 路径硬编码在项目根目录。

## Goals / Non-Goals

### Goals
- 将 CLI 逻辑迁移到 `agent/main.py`，符合 Python 包结构
- 默认交互优先：`asterwynd` 直接进 REPL，带 prompt 参数走单轮
- `pyproject.toml` 补全 PyPI 元数据
- `logs/` 走 XDG 标准路径
- 更新所有文档命令示例

### Non-Goals
- 不改变 `web` / `benchmark` 子命令的功能行为
- 不在本次 change 中实际推送到 PyPI（推包属于发布运维操作）
- 不新增 `agent/__main__.py`
- 不引入新的 CLI 命令

## Decisions

### D1: 入口模块命名为 `agent/main.py`

**决定**: 将原 `cli.py` 全部内容移至 `agent/main.py`。根目录不再保留 thin wrapper。

**理由**:
- 消除 `cli` 这个泛称，模块名反映应用入口语义
- 安装后命令是 `asterwynd`，入口模块叫 `main.py` 映射自然
- 主流 Python CLI 工具（aider、typer、pip）均使用 `main.py` 命名
- 不保留根目录 thin wrapper：开发时 `uv run asterwynd` 自动解析 `[project.scripts]`，无需 `python cli.py`

### D2: `main` 子命令改为 `@app.callback()` 默认行为

**决定**: 去掉 `main` 子命令。`asterwynd` 无参数进入交互 REPL，带 prompt 参数走单轮。

**理由**:
- 消除 `main` 子命令名与 `agent/main.py` 文件的命名冲突
- 交互优先：`asterwynd` 回车即进 REPL，与 Claude Code、aider 等体验一致
- 单轮只需 `asterwynd "prompt"` 一步到位
- 删除 `--interactive` 选项

### D3: 每个子命令独立管理参数

**决定**: `@app.callback()` 的选项（`--model`、`--provider`、`--max-iterations`、`--system`、`--mode`、`--config`、`--banner/--no-banner`）和 `web`/`benchmark` 的选项各自独立声明，不做顶层共享。

**理由**:
- 避免选项冲突（`web` 也有 `--model` 等）
- 每个命令入口自包含，阅读和维护更清晰

### D4: `.env` 加载用 CWD 默认搜索

**决定**: 删除 `load_dotenv(Path(__file__).parent.parent / ".env")`，改用 `load_dotenv()` 不带参数。

**理由**:
- `python-dotenv` 默认从 CWD 向上搜索 `.env`，开发 clone 和 pip 安装后均适用
- 不依赖包内路径推断项目根目录

### D5: `logs/` 走 XDG 标准路径

**决定**: 统一使用 `~/.local/state/asterwynd/logs/`（Linux）或等价平台路径（macOS `~/Library/Logs/asterwynd/`），不再依赖项目根目录。

**理由**:
- 安装后行为一致，不区分开发 clone 还是 pip 安装
- 主流工具（aider 等）均使用 XDG

### D6: License 和 Classifiers

**决定**: `license = "MIT"`。Classifiers 包含 Python 3.11/3.12/3.13、`Environment :: Console`、`Environment :: Web Environment`、`Operating System :: OS Independent`、`Topic :: Software Development :: Libraries :: Python Modules`。

**理由**: MIT 是 Python CLI 工具生态最通用的选择，零维护负担。

### D7: 不新增 `agent/__main__.py`

**决定**: 不支持 `python -m agent`。入口统一为 `asterwynd` 命令。

**理由**:
- `python -m agent` 语义模糊（非工具名）
- `asterwynd` entry point 已是最佳入口
- 减少维护的文件

## Pre-Implementation Review

grill-with-docs 确认了以下关键方向：
1. `main` 子命令名与模块名冲突，通过去掉子命令改为 callback 默认行为解决
2. 交互优先 > 单轮优先，与同类工具体验对齐
3. 路径问题通过 CWD 搜索和 XDG 标准路径解决，安装后无假设破裂
4. 根目录 thin wrapper 不再需要，uv run asterwynd 已覆盖开发场景

## Risks / Trade-offs

- **破坏性变更**: 删除 `--interactive` 选项和 `main` 子命令，现有脚本和文档命令需要全部更新。**缓解**: 影响面可控，文档已在本次 change 中更新。
- **破坏性变更**: `asterwynd` 无参数行为从报错变为进入交互 REPL。**缓解**: 这是预期的体验改进，不是意外行为变化。
- **风险**: `logs/` 路径从项目根目录迁移到 XDG，已有日志文件不自动迁移。**缓解**: 日志为调试产物，不影响功能，用户无需手动迁移。

## Testing Strategy

1. 更新 `tests/test_cli.py`：import 改为 `from agent.main import app`；适配无 `main` 子命令的调用方式
2. 更新 `tests/benchmark/test_cli_benchmark.py`：同理更新 import
3. 手动验证 `uv run asterwynd` 进交互、`uv run asterwynd "hello"` 单轮
4. 构建 wheel 确认 `agent/main.py` 包含在内、根目录 `cli.py` 不在

## Reference Implementation Research

- status: enabled
- reason: 调研主流 Python CLI 工具的打包模式和命令结构
- research questions:
  - Python CLI 工具的入口模块命名惯例？
  - 默认行为（交互 vs 单轮）的业界惯例？
  - pyproject.toml 元数据最佳实践？
- findings:
  - aider, typer, pip 均使用 `main.py` 作为入口模块
  - Claude Code、aider 等均默认进入交互 REPL，无 `--interactive` 概念
  - PyPI 需要 license、classifiers、repository 等元数据
  - XDG 路径是 Python CLI 工具的日志/缓存标准位置
- design impact:
  - `agent/main.py` + callback 默认交互
  - MIT license + standard classifiers
  - XDG for logs
