# 开发指南

本文档记录 MyAgent 的本地开发、运行和常用命令。

## 依赖安装

优先使用 `uv`。

```bash
uv sync --extra dev
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
MYAGENT_DEBUG=enabled uv run python cli.py web --host 127.0.0.1 --port 8000
```

运行 fake benchmark smoke：

```bash
uv run python cli.py benchmark benchmarks/tasks \
  --agent fake \
  --source-repo . \
  --runs-dir /tmp/smoke \
  --fake-edit-file README.md \
  --fake-old-string '# MyAgent' \
  --fake-new-string '# MyAgent Coding Agent'
```

运行 MyAgent benchmark：

```bash
uv run python cli.py benchmark benchmarks/tasks \
  --agent myagent \
  --source-repo . \
  --runs-dir /tmp/bench
```

并行 benchmark：

```bash
uv run python cli.py benchmark benchmarks/tasks \
  --agent myagent \
  --provider anthropic \
  --parallel 4 \
  --runs-dir /tmp/bench \
  --clone-cache-dir /tmp/swebench-cache
```

也可以在 `myagent.yaml` 中设置默认 benchmark 参数，字段示例见仓库根目录的 `myagent.example.yaml`。

## 环境变量

| 环境变量 | 作用 |
| --- | --- |
| `OPENAI_API_KEY` | OpenAI-compatible provider API key |
| `OPENAI_BASE_URL` | OpenAI-compatible provider base URL |
| `ANTHROPIC_API_KEY` | Anthropic-compatible provider API key |
| `ANTHROPIC_BASE_URL` | Anthropic-compatible provider base URL |
| `MYAGENT_PROVIDER` | provider，通常是 `openai` 或 `anthropic` |
| `MYAGENT_MODEL` | 默认模型 |
| `MYAGENT_DEBUG=enabled` | 开启 Web Debug 视图 |
| `MYAGENT_LOG_LEVEL=DEBUG` | 开启更详细日志 |
| `MYAGENT_MODE` | 覆盖 `myagent.yaml` 中的默认 agent mode |
| `MYAGENT_BENCHMARK_PARALLEL` | 覆盖 `myagent.yaml` 中的 benchmark 并发数 |
| `MYAGENT_BENCHMARK_TIMEOUT` | 覆盖 `myagent.yaml` 中的 benchmark 超时 |

## 结构化配置

非敏感、结构化配置写入 `myagent.yaml`；个人配置文件默认不提交，字段示例见 `myagent.example.yaml`。工具策略只从 YAML 读取：

- `agent.default_mode`
- `modes.<mode>.deny_tools`
- `tools.ignore_patterns`
- `tools.command_denylist`
- `benchmark.parallel`
- `benchmark.timeout_seconds`

## 开发注意事项

- 优先使用 `rg` 和 `rg --files` 搜索。
- 修改代码前先读相关实现和测试。
- 不要回滚用户未提交改动。
- 不要提交本地环境文件、日志、缓存和生成产物。
- 对 benchmark 相关变更，至少运行 `tests/benchmark` 和 fake-runner smoke。
- 对 Web 相关变更，至少运行 session/server 测试；浏览器测试按需运行。
