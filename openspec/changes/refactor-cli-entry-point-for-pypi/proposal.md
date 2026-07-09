# Proposal: refactor-cli-entry-point-for-pypi

## Change Type

- **Primary**: refactor
- **Secondary**: feature

## Summary

将 CLI 入口代码从根目录 `cli.py` 迁移到 `agent/main.py`，重构命令结构（默认交互优先、去掉 `main` 子命令、删除 `--interactive` 标志），补全 `pyproject.toml` 包元数据，使 Asterwynd 可以作为标准 Python 包通过 PyPI 分发和安装。

## Motivation

1. **入口模块命名不合理**: `cli.py` 是泛称，不反映项目 identity。主流工具使用 `main.py`
2. **命令结构不够自然**: `main` 子命令语义模糊，`--interactive` 标志与交互优先理念不一致
3. **路径假设脆弱**: `.env` 和 `logs/` 硬编码依赖项目根目录，pip 安装后失效
4. **pyproject.toml 元数据缺失**: 无法正常发布 PyPI

## Impact Analysis

### 影响的能力域
- **cli**: 入口命名、命令结构、参数声明、路径解析逻辑变更
- **configuration**: `pyproject.toml` metadata 扩展，scripts 引用路径更新
- **web-ui**: `web` 子命令参数独立声明（不受 callback 影响）
- **benchmark**: `benchmark` 子命令参数独立声明（不受 callback 影响）

### 影响的代码
- `cli.py` — 删除
- `agent/main.py` — 新增（原 `agent/cli.py` 改名），承载完整 CLI 逻辑，命令结构重构
- `pyproject.toml` — 补全元数据，更新 scripts、build include，移除 `cli.py` 引用
- `tests/test_cli.py` — import 路径和调用方式更新
- `tests/benchmark/test_cli_benchmark.py` — import 路径更新

### 影响的文档
- `README.md`, `README_EN.md` — 命令示例从 `uv run python cli.py main` 改为 `uv run asterwynd`
- `AGENTS.md` — 常用命令更新
- `docs/development-guide.md` — 开发命令示例更新
- `docs/testing-guide.md` — benchmark 命令示例更新
- `benchmarks/tasks/README.md` — 命令示例更新
- `openspec/specs/cli/spec.md` — spec delta 更新
- 其他 OpenSpec change/archive 中的示例命令

### 破坏性变更
- `asterwynd main "prompt"` → `asterwynd "prompt"`
- `asterwynd main --interactive` → `asterwynd`
- 根目录 `python cli.py` 不再可用 → 改用 `uv run asterwynd`
- `--interactive` 选项删除

## Reference Implementation Research

- status: enabled
- reason: 需要调研主流 Python CLI 工具的入口命名、命令结构和打包模式
- research questions:
  - Python CLI 工具的入口模块命名惯例？交互 vs 单轮的业界默认？
  - pyproject.toml 元数据最佳实践？日志/缓存路径惯例？
- findings:
  - aider, typer, pip 均使用 `main.py`；Claude Code、aider 默认交互 REPL
  - MIT 是 Python CLI 工具最通用的 license；XDG 是日志/缓存标准路径
  - `python-dotenv` 默认 CWD 搜索，不需要显式指定路径
- design impact:
  - `agent/main.py` + `@app.callback()` 默认交互
  - MIT + standard classifiers + XDG logs
  - 删除根目录 thin wrapper
