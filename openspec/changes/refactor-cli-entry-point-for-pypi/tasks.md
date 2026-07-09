# Tasks: refactor-cli-entry-point-for-pypi

## 1. 代码重构

- [ ] 1.1 创建 `agent/main.py`：将根目录 `cli.py` 完整 CLI 逻辑迁入
- [ ] 1.2 删除根目录 `cli.py`
- [ ] 1.3 `@app.callback(invoke_without_command=True)` 处理默认交互 REPL；新增 `run` 子命令处理单轮 prompt
- [ ] 1.4 删除 `--interactive` 选项和 `main` 子命令
- [ ] 1.5 `run` / `web` / `benchmark` 子命令参数各自独立声明
- [ ] 1.6 `@app.callback()` 声明交互模式 option（`--provider`、`--model`、`--max-iterations`、`--system`、`--mode`、`--config`、`--banner/--no-banner`），不带 positional argument
- [ ] 1.7 `.env` 加载改为 `load_dotenv()` CWD 默认搜索（删除显式路径）
- [ ] 1.8 `LOG_DIR` 改为 `platformdirs.user_log_path("asterwynd")`，尊重 `$XDG_STATE_HOME`，macOS `~/Library/Logs/asterwynd/`
- [ ] 1.9 更新 `pyproject.toml`：`[project.scripts]` → `agent.main:app`；`[tool.hatch.build.targets.wheel]` 的 packages 包含 `agent`、`web`、`benchmarks`，include `web/static/**`；移除 `cli.py` 引用；新增 `platformdirs` 依赖
- [ ] 1.10 补全 `pyproject.toml` 元数据：license = MIT、classifiers、repository URL、扩写 description
- [ ] 1.11 新增 `LICENSE` 文件（MIT）

## 2. 测试更新

- [ ] 2.1 `tests/test_cli.py`：`import cli` → `import agent.main as cli`（保留 monkeypatch 面，`build_agent`/`build_llm`/`new_run_id` 等 monkeypatch 路径不变）；`["main", ...]` → `["run", ...]`
- [ ] 2.2 `tests/benchmark/test_cli_benchmark.py`：同理更新 import 和调用方式
- [ ] 2.3 `tests/web_tests/test_browser.py:88`：subprocess 从 `cli.py web` 改为 `asterwynd web`
- [ ] 2.4 `tests/web_tests/conftest.py:7`：更新注释，移除 `cli.py` 引用
- [ ] 2.5 新增解析回归测试：`asterwynd`→交互 REPL、`asterwynd run "hello"`→单轮、`asterwynd web --port 8000`→Web、`asterwynd benchmark`→benchmark
- [ ] 2.6 新增负向测试：`asterwynd main` 报错子命令不存在、`asterwynd --interactive` 报错未知 option
- [ ] 2.7 新增 `LOG_DIR` 测试：env override `$XDG_STATE_HOME` 和目录自动创建
- [ ] 2.8 运行全量 pytest 确认不回归

## 3. 文档更新

- [ ] 3.1 `README.md`：命令示例从 `uv run python cli.py main` 改为 `uv run asterwynd` / `uv run asterwynd run`
- [ ] 3.2 `README_EN.md`：同步英文版命令示例
- [ ] 3.3 `AGENTS.md`：常用命令部分更新
- [ ] 3.4 `docs/development-guide.md`：开发命令示例更新
- [ ] 3.5 `docs/testing-guide.md`：benchmark smoke 命令更新
- [ ] 3.6 `benchmarks/tasks/README.md`：命令示例更新

## 4. Active OpenSpec Changes 兼容性 Pass

- [ ] 4.1 `add-background-task-execution-and-session-persistence`：更新 `design.md` 和 `proposal.md` 中的 `cli.py main --resume` / `cli.py web --resume` 引用
- [ ] 4.2 `add-minimal-tui-runtime-view`：更新 `proposal.md` 中的 `cli.py` 引用
- [ ] 4.3 `openspec/specs/agent-modes/spec.md`：更新 `cli.py main` 命令示例

## 5. 验证和收尾

- [ ] 5.1 构建 wheel：`uv build`，验证 `agent/main.py`、`web/`、`benchmarks/`、`web/static/` 在 wheel 中、`cli.py` 不在、LICENSE 在 sdist 中
- [ ] 5.2 wheel smoke：从 wheel 安装到临时 venv，验证 `asterwynd --help`、`asterwynd web --help`、`asterwynd benchmark --help` 均可运行
- [ ] 5.3 跑通 benchmark smoke：`uv run asterwynd benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/smoke`
- [ ] 5.4 手动验证：`uv run asterwynd` 进交互、`uv run asterwynd run "hello"` 单轮、`uv run asterwynd web --port 8000`
- [ ] 5.5 运行 `openspec validate --strict` 确认 change 文档合规
- [ ] 5.6 运行项目 artifact checker
- [ ] 5.7 同步 spec delta to `openspec/specs/cli/spec.md` 和 `openspec/specs/agent-modes/spec.md`（归档时）
- [ ] 5.8 维护 Reference Implementation Research：实现过程中若调研结论变化，先回写 proposal/design 的 `Reference Implementation Research`
- [ ] 5.9 归档 change 到 `openspec/changes/archive/`，更新 `docs/openspec-change-backlog.md`
