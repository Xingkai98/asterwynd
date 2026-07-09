# Design: refactor-cli-entry-point-for-pypi

## Context

Asterwynd 当前所有 CLI 逻辑放在根目录 `cli.py`（约 612 行），不符合 Python 包结构规范。`pyproject.toml` 的 `[project.scripts]` 声明 `asterwynd = "cli:app"`，但 `cli.py` 不在包内，wheel 构建后入口点解析存在隐患。

当前 `[tool.hatch.build.targets.wheel]` 的 `packages = ["agent"]` 只打包 `agent/` 目录，`cli.py` 需额外 `include`。此外 `pyproject.toml` 缺少 PyPI 必要元数据（license、classifiers、repository URL 等）。仓库目前没有 `LICENSE` 文件。

同时存在设计问题：`main` 子命令语义模糊、`--interactive` 标志与交互优先的理念不一致、`logs/` 路径硬编码在项目根目录。

## Goals / Non-Goals

### Goals
- 将 CLI 逻辑从根目录 `cli.py` 迁移到 `agent/main.py`，符合 Python 包结构
- 默认交互优先：`asterwynd` 直接进 REPL；`asterwynd run "prompt"` 单轮
- `pyproject.toml` 补全 PyPI 元数据
- 新增 `LICENSE` 文件（MIT）
- `logs/` 使用 `platformdirs` 走平台标准路径
- 更新所有文档和 active OpenSpec changes 中的命令示例

### Non-Goals
- 不改变 `web` / `benchmark` 子命令的功能行为
- 不在本次 change 中实际推送到 PyPI（推包属于发布运维操作）
- 不新增 `agent/__main__.py`

## Decisions

### D1: 入口模块命名为 `agent/main.py`

**决定**: 将根目录 `cli.py` 全部内容移至 `agent/main.py`。根目录不再保留任何 entry wrapper。

**理由**:
- 消除 `cli` 泛称，模块名反映应用入口语义
- 安装后命令是 `asterwynd`，入口模块叫 `main.py` 映射自然
- 主流 Python CLI 工具（aider、typer、pip）均使用 `main.py` 命名
- 不保留根目录 thin wrapper：开发时 `uv run asterwynd` 自动解析 `[project.scripts]`，无需 `python cli.py`

### D2: `@app.callback(invoke_without_command=True)` + `run` 子命令

**决定**: 去掉 `main` 子命令和 `--interactive` 选项。采用 Typer 标准模式：`@app.callback(invoke_without_command=True)` 无 positional argument，仅带 option（`--provider`、`--model`、`--max-iterations`、`--system`、`--mode`、`--config`、`--banner/--no-banner`）。callback 的 `ctx.invoked_subcommand is None` 时进入交互 REPL。新增 `run` 子命令处理纯单轮 prompt（positional `prompt` argument 在 `run` 子命令上，不会与子命令路由冲突）。

命令矩阵：

| 输入 | 行为 |
|---|---|
| `asterwynd` | 交互 REPL |
| `asterwynd run "hello"` | 单轮执行（非交互） |
| `asterwynd web --port 8000` | Web UI |
| `asterwynd benchmark ...` | Benchmark |

**理由**:
- `@app.callback()` 的 positional argument 会在子命令路由前消费第一个 token（实测 `asterwynd run hello` → `prompt="run"` + `No such command 'hello'`）。callback 不带 positional argument 彻底消除此冲突
- `invoke_without_command=True` 是 Typer 标准 API，不 hack 内部解析
- `run` 比 `main` 语义更精确，与 `web`/`benchmark` 并列自然
- 删除 `--interactive`：交互/单轮由子命令区分而非 flag
- 删除 `asterwynd "prompt"` 语法：用户进交互后直接输入 prompt，一行的事

### D3: 每个命令独立管理参数，callback 声明交互模式配置

**决定**: `@app.callback(invoke_without_command=True)` 声明交互模式选项（`--provider`、`--model`、`--max-iterations`、`--system`、`--mode`、`--config`、`--banner/--no-banner`），不带 positional argument。`run` / `web` / `benchmark` 子命令各自独立声明同名 `--model`、`--provider` 等选项。子命令激活时以子命令选项优先，callback 选项不会与之冲突。

**理由**:
- 交互模式用户仍可通过 CLI 配置 provider/model/mode（`asterwynd --model gpt-4o-mini`）
- 无 positional argument 避免 Typer 在子命令解析前消费首个 token（实测 `asterwynd web` 会因 callback 有 positional 而报 "No such command"）
- 子命令各自独立声明避免选项冲突

### D4: `.env` 加载用 CWD 默认搜索

**决定**: 删除 `load_dotenv(Path(__file__).parent / ".env")`，改用 `load_dotenv()` 不带参数。

**理由**:
- `python-dotenv` 默认从 CWD 向上搜索 `.env`，开发 clone 和 pip 安装后均适用
- 不依赖包内路径推断项目根目录

### D5: `logs/` 使用 `platformdirs`

**决定**: 引入 `platformdirs` 库（零依赖），使用 `platformdirs.user_log_path("asterwynd")` 作为日志目录。Linux 解析为 `~/.local/state/asterwynd/log/`（尊重 `$XDG_STATE_HOME`），macOS 为 `~/Library/Logs/asterwynd/`，Windows 为对应 AppData 路径。

**理由**:
- `platformdirs` 是 Python 生态标准方案（aider、pipx 等均使用），零依赖
- 正确尊重 `$XDG_STATE_HOME` 和各平台路径约定
- 安装后行为一致，不区分开发 clone 还是 pip 安装

### D6: License 和 Classifiers

**决定**: `license = "MIT"`。新增 `LICENSE` 文件。`pyproject.toml` classifiers 包含：
- `License :: OSI Approved :: MIT License`
- `Programming Language :: Python :: 3.11/3.12/3.13`
- `Environment :: Console`、`Environment :: Web Environment`
- `Operating System :: OS Independent`
- `Topic :: Software Development :: Libraries :: Python Modules`
- `Intended Audience :: Developers`

**理由**: MIT 是 Python CLI 工具生态最通用的选择，零维护负担。新增 LICENSE 文件满足 PyPI 和开源规范。

### D7: 不新增 `agent/__main__.py`

**决定**: 不支持 `python -m agent`。入口统一为 `asterwynd` 命令。

**理由**: `python -m agent` 语义模糊（非工具名）；`asterwynd` entry point 已是最佳入口。

## Pre-Implementation Review

### grill-with-docs 确认方向
1. `main` 子命令名与模块名冲突，通过去掉子命令并引入 `run` 解决
2. 交互优先 > 单轮优先，与同类工具体验对齐
3. 路径问题通过 CWD 搜索和 `platformdirs` 解决，安装后无假设破裂
4. 根目录 thin wrapper 不再需要

### codex review R1 (NEEDS_REVISION → 已修复)
1. D2 从 callback 带参数改为 `invoke_without_command=True` + `run` 子命令，解决 Typer 解析冲突
2. Spec delta 改为引用正式 spec 中的真实 requirement 名称，增加 REMOVED 声明
3. 影响分析补充 test_browser.py、conftest.py、agent-modes spec、active changes
4. 新增 active OpenSpec changes 兼容性 pass 任务
5. 新增 RIR 维护任务
6. XDG 改为 `platformdirs`，覆盖路径、env override 和平台差异
7. 新增 LICENSE 文件创建任务
8. 修正文档中 "agent/cli.py" 事实错误
9. Spec delta 增加破坏性变更失败场景

### codex review R2 (NEEDS_REVISION → 已修复)
1. Spec delta 删除 "（替换正式 spec 中的同名词条）" 独立段，确保 SHALL/MUST 正文在 requirement 首段
2. Callback 恢复 `--provider`/`--model`/`--max-iterations`/`--system`/`--mode`/`--config` option
3. D2 明确 `asterwynd "prompt"` 为交互+初始 prompt（非单轮），保留旧 `main --interactive "prompt"` 语义
4. Change Type 改为 primary: feature, secondary: refactor；backlog 描述纠正为"破坏性变更"
5. Impact Analysis 增加 `uv.lock`；tasks 增加 `uv.lock` 更新
6. `platformdirs` 固定为 `user_log_path`（非 `user_state_path`），路径说明与 API 匹配
7. 测试迁移任务改为 `import agent.main as cli`（保留 monkeypatch 面）
8. Spec 新增 benchmark `--config` scenario 和交互模式配置 option scenario

### codex review R3 (NEEDS_REVISION → 已修复)
1. CRITICAL: Typer callback positional `prompt` 与子命令解析冲突（实测确认）。改为 callback 不带 positional argument，仅带 option
2. D2 删除 `asterwynd "prompt"` 语法（后续进交互直接输入）
3. MAJOR: tasks.md:1.6 callback 选项与 design/spec 矛盾 → 修正为完整 option 列表
4. MAJOR: wheel 打包分析不完整（缺 web/benchmarks/web/static）→ 新增 tasks 1.9 wheel 扩展、5.2 wheel smoke
5. MAJOR: 缺 agent-modes spec delta → 新增 `specs/agent-modes/spec.md`
6. MAJOR: MODIFIED CLI 构造 AgentLoop 丢失原有构造约束 → 保留 provider/model/tools/hooks/memory SHALL
7. MAJOR: `asterwynd "prompt"` 测试缺口 → 已 moot（该语法已删除）
8. MINOR: backlog 文案与 design 不一致 → 修正

## Risks / Trade-offs

- **破坏性变更**: 删除 `--interactive` 选项和 `main` 子命令，现有脚本和文档命令需要全部更新。**缓解**: 影响面已完整分析，文档和 active changes 均在本次 change 中更新。
- **破坏性变更**: `asterwynd` 无参数行为从报错变为进入交互 REPL。**缓解**: 这是预期的体验改进，不是意外行为变化。`asterwynd main` 不再可用，新增回归测试覆盖错误场景。
- **破坏性变更**: 根目录 `cli.py` 删除，`tests/web_tests/test_browser.py` 中的 subprocess 调用需更新。**缓解**: 改为 `asterwynd web` 或 `uv run asterwynd web`。
- **风险**: `logs/` 路径从项目根目录迁移到 `platformdirs`，已有日志文件不自动迁移。**缓解**: 日志为调试产物，不影响功能，用户无需手动迁移。
- **风险**: Active OpenSpec changes 中引用 `cli.py` 的命令示例过时。**缓解**: 本次 change 中做兼容性 pass，更新或标注冲突。

## Testing Strategy

1. `tests/test_cli.py`：import 改为 `from agent.main import app`；适配 `run` 子命令和 callback 默认交互
2. `tests/benchmark/test_cli_benchmark.py`：同理更新 import 和调用方式
3. `tests/web_tests/test_browser.py`：subprocess 改为 `asterwynd web` entry point
4. `tests/web_tests/conftest.py`：更新注释和 `.env` 加载口径
5. 新增解析回归测试：`asterwynd`→交互、`asterwynd run "hello"`→单轮、`asterwynd web --port 8000`→Web、`asterwynd benchmark`→benchmark
6. 新增负向测试：`asterwynd main`、`asterwynd --interactive` 不可用
7. 新增 `LOG_DIR` 路径测试：env override `$XDG_STATE_HOME` 和目录自动创建
8. 构建 wheel 确认 `agent/main.py` 包含在内、根目录 `cli.py` 不在
9. Benchmark smoke 通过

## Reference Implementation Research

- status: enabled
- reason: 调研主流 Python CLI 工具的命令结构、打包模式和路径管理
- research questions:
  - Python CLI 工具的入口模块命名和命令结构惯例？
  - Typer callback + 子命令的标准实现方式？
  - `platformdirs` vs 手写 XDG 路径的权衡？
  - pyproject.toml PyPI 元数据最佳实践？
- findings:
  - aider, typer, pip 均使用 `main.py` 作为入口模块
  - `invoke_without_command=True` + 专用子命令是 Typer 多子命令的标准模式
  - Claude Code、aider 均默认交互 REPL
  - `platformdirs` 是 Python CLI 工具的标准路径方案（零依赖，跨平台）
  - PyPI 需要 license、classifiers、repository 等元数据；需配套 LICENSE 文件
- design impact:
  - `agent/main.py` + `invoke_without_command=True` + `run` 子命令
  - MIT license + LICENSE 文件 + standard classifiers
  - `platformdirs` for logs
