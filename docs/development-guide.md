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
uv run asterwynd run "用 Read 工具读 /tmp"
```

交互模式：

```bash
uv run asterwynd
```

交互模式内置 slash commands：

```text
/help                         # 查看可用命令
/status                       # 查看 session、mode、provider、model 和上下文摘要
/mode <build|read_only|plan|bypass>  # 切换后续 run 的 agent mode
/clear                        # 清空当前交互历史，保留 system context 和 Session ID
/compact                      # 主动压缩符合条件的旧上下文
/skills                       # 查看当前加载的 skills 和诊断
/skills reload                # 重新加载 configured skill roots
/<skill-name> <request>       # 显式激活用户可调用 skill，并用 request 启动 Agent run
/mcp                          # 查看 MCP server 状态和 tools/prompts/resources 数量
/mcp-prompt <server> <prompt> [json args]  # 读取 MCP prompt 并注入上下文
/mcp-resource <server> <uri>  # 读取 MCP resource 并注入上下文
/exit 或 /quit                # 退出交互模式
```

启动 Web UI：

```bash
uv run asterwynd web --port 8000
```

启动 Debug Web UI：

```bash
ASTERWYND_DEBUG=enabled uv run asterwynd web --host 127.0.0.1 --port 8000
```

运行 fake benchmark smoke：

```bash
uv run asterwynd benchmark benchmarks/tasks \
  --agent fake \
  --source-repo . \
  --runs-dir /tmp/smoke \
  --fake-edit-file README.md \
  --fake-old-string '# Asterwynd' \
  --fake-new-string '# Asterwynd Coding Agent'
```

运行 Asterwynd benchmark：

```bash
uv run asterwynd benchmark benchmarks/tasks \
  --agent asterwynd \
  --source-repo . \
  --runs-dir /tmp/bench
```

运行单个 `swebench-*` 任务前，当前环境需要可用的 Docker daemon，且 `uv sync --extra dev` 已安装 `swebench` 依赖。Docker 不可用时，这类任务会写出 `unsupported` artifact，而不是回退到本地 venv 兼容路径。

并行 benchmark：

```bash
uv run asterwynd benchmark benchmarks/tasks \
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

运行 benchmark 回归门禁（对比已提交基线，劣化 >5% 返回非零）：

```bash
# 用仓库内 gate-smoke 任务集 + 已提交基线（CI 同款）
uv run asterwynd benchmark-gate benchmarks/tasks/gate-smoke \
  --source-repo . \
  --baseline benchmarks/baseline.json \
  --require-baseline

# 跑完把当前结果固化为新基线（显式确认覆盖）
uv run asterwynd benchmark-gate benchmarks/tasks \
  --source-repo . \
  --baseline benchmarks/baseline.json \
  --update-baseline

# 近零 IO 确定性任务集可跳过 P95 延迟检查（墙钟受环境主导不可靠）
uv run asterwynd benchmark-gate benchmarks/tasks/gate-smoke \
  --source-repo . \
  --baseline benchmarks/baseline.json \
  --require-baseline --skip-p95
```

门禁判定规则：成功率相对基线绝对下降 >5 个百分点，或 P95 延迟超过 `max(基线*1.05, 基线+1.0s)`（相对 5% + 1 秒绝对值下限）即返回非零。`--update-baseline` 为显式确认覆盖；0 任务时不会写空基线。

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
- `modes.<mode>.permission_profile`
- `modes.<mode>.deny_tools`
- `permissions.profiles.<name>.allowed_capabilities`
- `permissions.profiles.<name>.auto_approve_max_risk`
- `permissions.profiles.<name>.approval_required_max_risk`
- `permissions.profiles.<name>.denied_tools`
- `tools.ignore_patterns`
- `tools.command_denylist`
- `tools.code_intelligence.tree_sitter_max_file_bytes`
- `tools.code_intelligence.lsp.servers`
- `tools.code_intelligence.lsp.default_request_timeout_ms`
- `tools.web_search.providers`
- `tools.display.max_result_chars`
- `tools.display.max_result_lines`
- `tools.display.preview_chars`
- `mcp.default_timeout_seconds`
- `mcp.servers.<name>.type`
- `mcp.servers.<name>.command` / `args` / `cwd` / `env`
- `mcp.servers.<name>.url` / `headers`
- `mcp.servers.<name>.default_permission`
- `mcp.servers.<name>.tools` / `prompts` / `resources`
- `skills.roots`
- `benchmark.parallel`
- `benchmark.timeout_seconds`

## 开发注意事项

- CLI 交互模式通过 slash command registry 处理 `/help`、`/status`、`/mode`、`/clear`、`/compact`、`/skills`、`/skills reload`、`/exit` 和 `/quit`；裸 `exit`、`quit`、`q` 仍可退出。
- Web Chat 输入框在输入 `/` 时会显示 slash command 提示，并按当前前缀实时过滤；发送独立 slash command 时由 WebSocket 按命令类型执行。本地控制命令不作为普通聊天消息进入 AgentLoop/LLM；用户可调用 skill 命令会先激活 skill，再用命令参数启动 Agent run。
- MCP server 通过顶层 `mcp.servers` 配置，支持 `stdio` 和 `streamable_http`。MCP tools 注册为 `mcp__<server>__<tool>`；`/mcp-prompt` 和 `/mcp-resource` 读取结果以 system context 注入当前会话，并按 mode policy 判权。
- Skill 使用 `skills/<name>/SKILL.md` 目录格式。每次 run 都会向模型注入简短 skill index；完整 skill prompt 只在 `always: true`、本地匹配、显式 `/skill args` 或 `ActivateSkill` 激活时进入当前 run context。
- `/clear` 只清当前 CLI 交互上下文，不生成新的 Session ID；后续如果引入持久 transcript 或 cache reset，需要单独扩展语义。
- CLI 交互模式可用 `/mode build`、`/mode read_only`、`/mode plan`、`/mode bypass` 切换当前 session mode；Web Chat 也支持在当前 session 内切换 mode。
- 当前 CLI/Web 的 mode 切换在用户侧表现为“影响后续 run”；runtime state 仍会在 transition 完成后立即更新，供后续 TUI 或控制面重构复用。
- 默认 `build` mode 会把 high risk 工具判定为 `require_approval`。CLI 交互模式在 TTY 中提示 `Approve? [y/N]`；CLI 单轮、benchmark 和子 agent 遇到需要审批的工具调用时 fail closed。Web Chat 通过审批卡片批准或拒绝当前 pending approval。
- 优先使用 `rg` 和 `rg --files` 搜索。
- 修改代码前先读相关实现和测试。
- 不要回滚用户未提交改动。
- 不要提交本地环境文件、日志、缓存和生成产物。
- 对 benchmark 相关变更，至少运行 `tests/benchmark` 和 fake-runner smoke；如果改动影响内置 runner 的 `swebench-*` 执行路径，额外验证 Docker preflight 或单任务 SWE-bench smoke；如果改动影响 `claw-swe-bench/`，至少跑一个 Claw-SWE-Bench 单实例 smoke。
- 对 Web 相关变更，至少运行 session/server 测试；浏览器测试按需运行。

## 业界调研门禁

方案设计（proposal/design）前须按改动性质分流调研业界最新实践或框架（核心规则见 AGENTS.md「业界调研门禁」节；机械校验由 artifact checker 执行）。本小节给判据举例、豁免 reason 写法示范与常见误用。

### 三档判据举例

| 档位 | 适用示例 | 反例（不属于该档） |
|------|---------|------------------|
| `full` 必调研 | 引入新框架/新依赖/新协议；架构级改造；对标业界产品（如"参考 Herdr/Orca 的桌面端编排"）；走 grill 的非平凡 change | 给已有工具加一个可选参数（→ light） |
| `light` 浅调研 | 常规功能增强；成熟模式的局部应用；给已有工具扩展参数 | 引入全新消息协议（→ full） |
| `exempt` 可豁免（须 reason） | docs-only；纯 bugfix（无新增能力面 + 回归测试）；上游决策锁定（方案已由已关闭决策 issue/架构评审锁定，无待定设计项） | 有设计空间的新功能标 exempt（→ 至少 light） |

### 豁免 reason 写法示范

**好例子**（checker 可机械通过）：

- `- reason: 纯 bugfix（修复 X 越界），无新增能力面，带回归测试。` —— 命中关键词 `bugfix`
- `- reason: 方案已由 #128 决策 issue 完整讨论并记录，无待定设计项。` —— 命中 `方案已由.*决策` + 引用 `#<数字>`
- `- reason: 决策已记录于 docs/adr/0007-gate.md 与 openspec/changes/archive/2026-08-14-flow-policy-source/。` —— 引用 `docs/`、`openspec/changes/archive/` 路径
- `- reason: 上游决策锁定——依赖 #121 cross-cutting 规则与既有 checker 实现，无外部同类可比。` —— 命中关键词 `上游决策锁定` + issue 引用

**坏例子**（checker 拒绝）：

- `- reason: 方案明确。` —— 无关键词、无引用、非实质依据（占位）
- `- reason: 待确认。` / `- reason: 待补充。` —— 命中 #123 占位词表
- `- reason: 与已有模块 X 等价改造。` —— 判断性豁免但**无引用**；判断性豁免必须带引用（`#<数字>` issue 或 `docs/`、`openspec/changes/archive/`、`reviews/` 下的文档路径，代码路径如 `agent/`、`scripts/` 不在证据路径清单内）
- `- reason: 本地参考仓库不可用。` —— 不构成豁免理由；业界调研不依赖本地参考仓库，应在 full/light 的 findings 中记录不可用事实与替代依据

### 常见误用

- **占位文本**：`待确认`/`待补充`/`待调研`/`TBD`/`todo` 等（#123 词表）出现在 full/light 的 findings/design impact 或 exempt 的 reason 里，tasks 全勾时 exit 2。
- **无证据空话**：一句「方案明确」「无需调研」不命中关键词也无引用 → exempt 证据校验失败。
- **tier 与 status 不一致**：`exempt` + `status: enabled`（声言豁免却完成了调研）→ 完成时被「exempt 必须 disabled」拦下；正确做法是**如实改 tier 为 light/full + status: enabled**。
- **full/light 完成时仍 disabled**：proposal 阶段允许 full/light + disabled 在途（只查结构），但 tasks 全勾时必调研档必须已完成调研 → 完成时改 `status: enabled`。
