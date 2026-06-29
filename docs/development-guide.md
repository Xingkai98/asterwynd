# 开发指南

本文档记录 Asterwynd 的本地开发、运行和常用命令。

## 依赖安装

优先使用 `uv`。

```bash
# 基础安装
uv sync --extra dev

# LSP 支持（可选，当前只支持 Python，需 pylsp）
uv sync --extra lsp
# 或
uv sync --extra dev --extra lsp
```

如果当前 Python 环境已经安装好依赖，也可以直接运行 `python` 或 `pytest`，但默认推荐 `uv run`。

## 常用命令

运行全部测试：

```bash
uv run pytest -q
```

运行单个测试文件：

```bash
uv run pytest tests/agent/tools/test_registry.py -v
```

运行 CLI：

```bash
uv run python cli.py main "用 Read 工具读 /tmp"
```

交互模式：

```bash
uv run python cli.py main --interactive
```

启动 Web UI：

```bash
uv run python cli.py web --port 8000
```

启动 Debug Web UI：

```bash
ASTERWYND_DEBUG=enabled uv run python cli.py web --host 127.0.0.1 --port 8000
```

运行 fake benchmark smoke：

```bash
uv run python cli.py benchmark benchmarks/tasks \
  --agent fake \
  --source-repo . \
  --runs-dir /tmp/smoke \
  --fake-edit-file README.md \
  --fake-old-string '# Asterwynd' \
  --fake-new-string '# Asterwynd Coding Agent'
```

运行 Asterwynd benchmark：

```bash
uv run python cli.py benchmark benchmarks/tasks \
  --agent asterwynd \
  --source-repo . \
  --runs-dir /tmp/bench
```

运行单个 `swebench-*` 任务前，当前环境需要可用的 Docker daemon，且 `uv sync --extra dev` 已安装 `swebench` 依赖。Docker 不可用时，这类任务会写出 `unsupported` artifact，而不是回退到本地 venv 兼容路径。

并行 benchmark：

```bash
uv run python cli.py benchmark benchmarks/tasks \
  --agent asterwynd \
  --provider anthropic \
  --parallel 4 \
  --runs-dir /tmp/bench \
  --clone-cache-dir /tmp/swebench-cache
```

如果你当前开发环境本身是一个没有 `systemd` 的容器，可以使用仓库内的辅助脚本手动拉起 Docker daemon：

```bash
sudo ./scripts/start-docker-daemon.sh
```

这个脚本只用于开发和验证当前环境，不属于 benchmark 运行时语义；benchmark CLI 只负责检测 Docker 是否可用。

也可以在 `asterwynd.yaml` 中设置默认 benchmark 参数，字段示例见仓库根目录的 `asterwynd.example.yaml`。

运行 Claw-SWE-Bench 对比评测前，需要先准备 SWE-bench Docker 镜像、独立 Python、Asterwynd venv 和 API key。完整环境说明见仓库根目录 `CLAW-SWE-BENCH.md`。最小命令形态：

```bash
cd claw-swe-bench
uv run python run_infer.py \
  --claw asterwynd \
  --dataset verified \
  --instance_file config/verified_mini_50.txt \
  --run_id asterwynd-lite \
  --model deepseek-v4-pro

uv run python run_eval.py --run_id asterwynd-lite --dataset verified
```

## 环境变量

| 环境变量 | 作用 |
| --- | --- |
| `OPENAI_API_KEY` | OpenAI-compatible provider API key |
| `OPENAI_BASE_URL` | OpenAI-compatible provider base URL |
| `ANTHROPIC_API_KEY` | Anthropic-compatible provider API key |
| `ANTHROPIC_BASE_URL` | Anthropic-compatible provider base URL |
| `ASTERWYND_PROVIDER` | provider，通常是 `openai` 或 `anthropic` |
| `ASTERWYND_MODEL` | 默认模型 |
| `ASTERWYND_STREAMING` | 控制支持 streaming 的 provider 是否启用流式输出；默认开启，设为 `disabled` / `off` / `false` / `0` 可关闭 |
| `ASTERWYND_DEBUG=enabled` | 开启 Web Debug 视图 |
| `ASTERWYND_LOG_LEVEL=DEBUG` | 开启更详细日志 |
| `ASTERWYND_MODE` | 覆盖 `asterwynd.yaml` 中的默认 agent mode |
| `ASTERWYND_BENCHMARK_PARALLEL` | 覆盖 `asterwynd.yaml` 中的 benchmark 并发数 |
| `ASTERWYND_BENCHMARK_TIMEOUT` | 覆盖 `asterwynd.yaml` 中的 benchmark 超时 |
| `ASTERWYND_TAVILY_API_KEY` | Tavily Search provider API key |
| `ASTERWYND_BRAVE_SEARCH_API_KEY` | Brave Search provider API key |
| `ASTERWYND_SEARXNG_BASE_URL` | SearXNG provider base URL |
| `CLAW_PYTHON_HOME` / `CLAW_PYTHON_BIN` | Claw-SWE-Bench 容器内执行用的独立 Python 路径 |
| `ASTERWYND_SRC` | Claw-SWE-Bench 挂载到容器内的 Asterwynd 源码路径 |
| `ASTERWYND_VENV` | Claw-SWE-Bench 挂载到容器内的 Asterwynd venv 路径 |
| `CLAW_NO_RESOURCE_LIMITS` | 在当前开发环境需要时跳过 Claw-SWE-Bench cgroup 资源限制 |

## 结构化配置

非敏感、结构化配置写入 `asterwynd.yaml`；个人配置文件默认不提交，字段示例见 `asterwynd.example.yaml`。工具策略只从 YAML 读取：

- `agent.default_mode`
- `modes.<mode>.deny_tools`
- `tools.ignore_patterns`
- `tools.command_denylist`
- `tools.code_intelligence.tree_sitter_max_file_bytes`
- `tools.code_intelligence.lsp.servers`
- `tools.code_intelligence.lsp.default_request_timeout_ms`
- `tools.web_search.providers`
- `tools.display.max_result_chars`
- `tools.display.max_result_lines`
- `tools.display.preview_chars`
- `benchmark.parallel`
- `benchmark.timeout_seconds`

## 开发注意事项

- CLI 交互模式可用 `/mode build`、`/mode read_only`、`/mode plan` 切换当前 session mode；Web Chat 也支持在当前 session 内切换 mode。
- 当前 CLI/Web 的 mode 切换在用户侧表现为“影响后续 run”；runtime state 仍会在 transition 完成后立即更新，供后续 TUI 或控制面重构复用。
- 优先使用 `rg` 和 `rg --files` 搜索。
- 修改代码前先读相关实现和测试。
- 不要回滚用户未提交改动。
- 不要提交本地环境文件、日志、缓存和生成产物。
- 对 benchmark 相关变更，至少运行 `tests/benchmark` 和 fake-runner smoke；如果改动影响内置 runner 的 `swebench-*` 执行路径，额外验证 Docker preflight 或单任务 SWE-bench smoke；如果改动影响 `claw-swe-bench/` 或 `agent/claw_solve.py`，至少跑一个 Claw-SWE-Bench 单实例 smoke。
- 对 Web 相关变更，至少运行 session/server 测试；浏览器测试按需运行。
