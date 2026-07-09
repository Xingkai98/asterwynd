# Proposal: refactor-cli-entry-point-for-pypi

## Change Type

- primary: feature
- secondary: refactor

## Summary

将 CLI 入口代码从根目录 `cli.py` 迁移到 `agent/main.py`，重构命令结构（`@app.callback(invoke_without_command=True)` 默认交互 + `run` 子命令单轮，删除 `main` 子命令和 `--interactive` 选项），引入 `platformdirs` 管理日志路径，新增 `LICENSE` 文件，补全 `pyproject.toml` 元数据，使 Asterwynd 可以作为标准 Python 包通过 PyPI 分发和安装。

## Motivation

1. **入口模块命名不合理**: `cli.py` 是泛称，不反映项目 identity。主流工具使用 `main.py`
2. **命令结构不够自然**: `main` 子命令语义模糊，`--interactive` 标志与交互优先理念不一致
3. **路径假设脆弱**: `.env` 和 `logs/` 硬编码依赖项目根目录，pip 安装后失效
4. **pyproject.toml 元数据缺失**: 缺少 license、classifiers、repository URL，无法正常发布 PyPI
5. **LICENSE 文件缺失**: 仓库没有开源许可声明

## Impact Analysis

### 影响的能力域
- **cli**: 入口命名、命令结构、参数声明、路径解析逻辑变更。`main` 子命令和 `--interactive` 选项删除
- **configuration**: `pyproject.toml` metadata 扩展，scripts 引用路径更新，新增 LICENSE 文件
- **web-ui**: `web` 子命令参数独立声明（不受 callback 影响）；`tests/web_tests/test_browser.py` subprocess 调用更新
- **benchmark**: `benchmark` 子命令参数独立声明（不受 callback 影响）
- **agent-modes**: 正式 spec 中引用 `cli.py main` 的示例更新；需新增 `specs/agent-modes/spec.md` delta
- **wheel 打包**: 当前只打包 `agent`，需扩展打包 `web`、`benchmarks` 和 `web/static/`，确保安装后 `asterwynd web` 和 `asterwynd benchmark` 可用

### 影响的代码
- `cli.py` — 删除
- `agent/main.py` — 新增，承载完整 CLI 逻辑，命令结构重构
- `pyproject.toml` — 补全元数据，更新 scripts、build include，新增 `platformdirs` 依赖
- `uv.lock` — 新增 `platformdirs` 直接依赖
- `LICENSE` — 新增 MIT license 文件
- `tests/test_cli.py` — import 路径从 `import cli` 改为 `from agent.main import app`；调用方式从 `["main", ...]` 改为 `["run", ...]`
- `tests/benchmark/test_cli_benchmark.py` — import 路径更新
- `tests/web_tests/test_browser.py:88` — subprocess 从 `cli.py web` 改为 `asterwynd web`
- `tests/web_tests/conftest.py:7` — 注释更新，移除 `cli.py` 引用

### 影响的文档
- `README.md`, `README_EN.md` — 命令示例更新
- `AGENTS.md` — 常用命令更新
- `docs/development-guide.md` — 开发命令示例更新
- `docs/testing-guide.md` — benchmark smoke 命令更新
- `benchmarks/tasks/README.md` — 命令示例更新
- `openspec/specs/cli/spec.md` — spec delta 归档时同步
- `openspec/specs/agent-modes/spec.md` — 命令示例更新

### 影响的 Active OpenSpec Changes
- `add-background-task-execution-and-session-persistence` — `design.md:99` 和 `proposal.md:46` 引用 `cli.py main --resume` / `cli.py web --resume`，需在本 change 中做兼容性 pass 更新或标注冲突
- `add-minimal-tui-runtime-view` — `proposal.md:32` 引用 `cli.py`，同理处理

### 破坏性变更
- `asterwynd main "prompt"` → `asterwynd run "prompt"`（单轮）
- `asterwynd main --interactive` → `asterwynd`（交互 REPL）
- `asterwynd main --interactive "prompt"` → 无直接等价命令（先 `asterwynd` 进交互再输入 prompt）
- `--interactive` 选项删除（`asterwynd --interactive` 报错）
- `main` 子命令删除（`asterwynd main` 报错）
- 根目录 `python cli.py` 不再可用 → 改用 `uv run asterwynd`

## Reference Implementation Research

- status: enabled
- reason: 需要调研主流 Python CLI 工具的入口命名、命令结构、打包模式和路径管理
- research questions:
  - Python CLI 工具的入口模块命名惯例？交互 vs 单轮的业界默认？
  - Typer callback + 子命令的标准实现方式？
  - `platformdirs` vs 手写 XDG 路径的权衡？
  - pyproject.toml 元数据最佳实践？
- findings:
  - aider, typer, pip 均使用 `main.py` 作为入口模块
  - `invoke_without_command=True` + 专用子命令是 Typer 多子命令的标准模式
  - Claude Code、aider 默认交互 REPL
  - `platformdirs` 是 Python CLI 工具的标准路径方案（零依赖，跨平台，尊重 `$XDG_STATE_HOME`）
  - PyPI 需要 license、classifiers、repository 等元数据；需配套 LICENSE 文件
- design impact:
  - `agent/main.py` + `invoke_without_command=True` + `run` 子命令
  - MIT license + LICENSE 文件 + standard classifiers
  - `platformdirs` for logs
  - 新增 `platformdirs` 依赖到 pyproject.toml
