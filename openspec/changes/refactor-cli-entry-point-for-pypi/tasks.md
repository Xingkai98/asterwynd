# Tasks: refactor-cli-entry-point-for-pypi

## 1. 代码重构

- [ ] 1.1 删除 `agent/cli.py`，创建 `agent/main.py`（完整 CLI 逻辑迁入）
- [ ] 1.2 删除根目录 `cli.py`
- [ ] 1.3 `main` 子命令改为 `@app.callback()`：无参数进交互 REPL，带 prompt 单轮执行
- [ ] 1.4 删除 `--interactive` 选项
- [ ] 1.5 `web` / `benchmark` 子命令参数各自独立声明
- [ ] 1.6 `.env` 加载改为 `load_dotenv()` CWD 默认搜索
- [ ] 1.7 `LOGS_DIR` 改为 XDG 路径：`~/.local/state/asterwynd/logs/`
- [ ] 1.8 更新 `pyproject.toml`：`[project.scripts]` → `agent.main:app`，build include 移除 `cli.py` 引用
- [ ] 1.9 补全 `pyproject.toml` 元数据：license = MIT、classifiers、repository URL、扩写 description

## 2. 测试更新

- [ ] 2.1 `tests/test_cli.py`：`import cli` → `from agent.main import app`，适配无 `main` 子命令
- [ ] 2.2 `tests/benchmark/test_cli_benchmark.py`：同理更新 import
- [ ] 2.3 运行全量 pytest 确认不回归
- [ ] 2.4 手动验证 `uv run asterwynd` 进交互、`uv run asterwynd "hello"` 单轮

## 3. 文档更新

- [ ] 3.1 `README.md`：`uv run python cli.py main` → `uv run asterwynd`
- [ ] 3.2 `README_EN.md`：同步英文版
- [ ] 3.3 `AGENTS.md`：常用命令更新
- [ ] 3.4 `docs/development-guide.md`：开发命令示例更新
- [ ] 3.5 `docs/testing-guide.md`：benchmark smoke 命令更新
- [ ] 3.6 `benchmarks/tasks/README.md`：命令示例更新
- [ ] 3.7 `openspec/specs/cli/spec.md`：入口命令示例更新（归档时同步）

## 4. 验证和收尾

- [ ] 4.1 构建 wheel：`uv build`，验证 `agent/main.py` 在 wheel 中、`cli.py` 不在
- [ ] 4.2 跑通 benchmark smoke：`uv run asterwynd benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/smoke`
- [ ] 4.3 运行 `openspec validate --strict` 确认 change 文档合规
- [ ] 4.4 运行项目 artifact checker
- [ ] 4.5 同步 spec delta to `openspec/specs/cli/spec.md`
- [ ] 4.6 归档 change 到 `openspec/changes/archive/`，更新 `docs/openspec-change-backlog.md`
