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
  --fake-old-string 'Asterwynd' \
  --fake-new-string 'Asterwynd Coding Agent'
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

编排 benchmark（workflow 三模式）：

```bash
# 记录一次（每任务落 workflow_record.json）
uv run asterwynd benchmark benchmarks/tasks \
  --agent asterwynd --provider anthropic --model deepseek-v4-flash \
  --workflow-mode dynamic-record --runs-dir /tmp/record

# 重放（--workflow-record 收 run 目录，按 task_id 推导记录路径）
uv run asterwynd benchmark benchmarks/tasks \
  --agent asterwynd --provider anthropic --model deepseek-v4-flash \
  --workflow-mode dynamic-replay --workflow-record /tmp/record --runs-dir /tmp/replay

# 对照臂「小 k vs 大 N」：两份 config 各跑一次
uv run asterwynd benchmark benchmarks/tasks --agent asterwynd \
  --config configs/workflow-arm-small-k.yaml --runs-dir /tmp/arm-small-k
uv run asterwynd benchmark benchmarks/tasks --agent asterwynd \
  --config configs/workflow-arm-large-n.yaml --runs-dir /tmp/arm-large-n
```

`--workflow-mode dynamic-record --e2e-round-trip` 会在记录完成后自动用 `dynamic-replay` 重放本次 run，并断言两次的 `workflow_spec_hash` 相等（真实 LLM 下的端到端可比性验证）。

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
- `tools.allowed_write_paths`（显式可写豁免，默认空列表 = deny 默认不变；
  条目是 workspace 相对路径的**字面值**——不接受 glob / 绝对路径 / `..` /
  目录形式，非法条目在加载配置时直接报错。只影响写不影响读，只覆盖文件级
  deny，不覆盖 `.git/**` 等结构性目录 deny。已知边界：嵌套路径的 Bash
  `cp` / `mv` 写不被覆盖）
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

## 完成度门禁与 `(post-merge)` 任务标记

完成度门禁由**瘦项目规则 checker**（`scripts/check_openspec_artifacts.py`）承载，触发点是**归档点**（issue #235）。判据是：本 PR 的 `--diff-filter=AR` diff 中出现的 `openspec/changes/archive/<YYYY-MM-DD>-<id>/` 路径，**且该归档目录在 base 树不存在**（后者排除「往既有归档目录补文件」被误判成新归档）。门在**归档目录**上评估：building review 存在性 + `## 闭环出口` PASS、grill 证据（`grill-design.md` ≥3 决策 + Open Question 确认、`grill-adversarial.md` 存在）、RIR 内容门槛，以及 tasks 完成度；**不因 tasks 未全勾而降级**。任何本次 diff 触及的**非日期前缀归档目录**也直接报错。Impact Analysis 与 benchmark smoke 只按退役前矩阵在 active change 上评估。

### `(post-merge)` 标记

closeout 类任务（**PR 合入之后**才执行的动作，例如「给关联 issue 添加 comment 并关闭」）在归档时刻**结构上无法完成**，因此必须在行内标注 `(post-merge)`，否则归档 PR 会被完成度门禁判红：

```markdown
- [ ] (post-merge) 收尾：给 issue #235 添加完成 comment 并关闭。
```

**语法**：`(post-merge)` 必须带括号（全角 `（post-merge）` 或半角皆可），大小写不敏感，允许编号/粗体在其前（`- [ ] 5.5 (post-merge)`、`- [ ] **6.9** (post-merge)`），`-`/`*`/`+` 三种列表标记与缩进子项都识别。

**为什么需要**：归档时 PR 尚未合入，「合入后关 issue」这类任务不可能勾选；没有豁免机制则每个格式正确的新归档都会误红。实测 93 个历史归档中 35 个有未勾项，其中 9 个的未勾项全部属 post-merge 类。

**只有带标记的未勾行被豁免**。无标记的未勾行一律视为「实现未完成」并报错——留一条 `- [ ]` 正是 issue #235 记录的绕开路径（它会让四道门全部关闭）。**不做标题级 legacy 兜底**：那是唯一能 fail-open 的面。

**标记必须紧邻复选框**——标签与 `[ ]` 之间只允许编号或粗体，**不能有任务正文**：

| 写法 | 是否识别 |
|------|---------|
| `- [ ] (post-merge) 收尾：关 issue` | ✓ |
| `- [ ] 5.5 (post-merge) 收尾：关 issue` | ✓ |
| `- [ ] **6.9** (post-merge) 收尾` | ✓ |
| `- [ ] 收尾：关 issue。(post-merge)` | ✗ 标在行尾 |
| `- [ ] 5.5 收尾：关 issue (post-merge)` | ✗ 正文插在中间 |

不识别时**会报错提示**（fail-closed，不会静默放行），但写法要注意：把标记紧跟在 `[ ]`（或编号/粗体）之后。

**`tasks.md` 必须能证明完成了事**：它是「完成度」这一维度唯一的证据载体。以下三种形态都会被归档点报错——缺文件；写成散文或空文件（零 checkbox 行）；**有 checkbox 行但一条都没勾**（例如把所有任务都标成 `(post-merge)`）。否则「不写 checkbox」「一条都不勾」就成了与「留一条 `- [ ]`」同构的绕开路径。下限是**至少勾选一条**。

### 归档目录命名

归档目录 MUST 为 `openspec/changes/archive/<YYYY-MM-DD>-<change-id>/`。缺日期前缀（如 `archive/<id>/`）会被瘦 checker **直接报错**——这类目录既不匹配归档正则、又被 active 迭代排除，否则会落进「谁都不管」的静默面。

## Review evidence 纪律（收尾）

本仓只要求 **witnessloop 形态** manifest：`reviews/<stage>.manifest.json`（`grill` /
`grill-adversarial` / `building` 三份）。asterwynd 形态
`reviews/<phase>-review-manifest.json` 已随 `retire-manifest-check`（issue #316）退役：
不再要求产出、不再由本仓 checker 校验，历史 80 份保持原样。其生成模块与
`workflow_state.py review-manifest` 写通道已删除；历史文件仅作为提交历史保留。

- **三份 manifest SHALL 在所有内容提交之后、归档 move 之后生成**，用**归档目录名**作为
  `--change`（`<YYYY-MM-DD>-<change-id>`）；`report_path` SHALL 覆盖 `reviews/` 下每一份
  `.md`（孤儿规则）。
- 产出命令（`--report` 按 stage 取实际报告名）：

  ```bash
  witnessloop manifest build --root . --change <归档目录名> --stage grill \
    --report reviews/grill-design.md --reviewer-run-id <run> --author-run-id <run>
  witnessloop manifest build --root . --change <归档目录名> --stage grill-adversarial \
    --report reviews/grill-adversarial.md --reviewer-run-id <run> --author-run-id <run>
  witnessloop manifest build --root . --change <归档目录名> --stage building \
    --report reviews/building-review.md --reviewer-run-id <run> --author-run-id <run>
  ```

  先内容、后证据；审阅之后再落非证据文件会让 manifest 变 stale。
- **building review 的终结 verdict**：`reviews/building-review.md` SHALL 以二级标题
  `## 闭环出口` 记录终结出口，首个非空行以 `PASS` 开头；`BLOCKED` /
  `CHANGES_REQUESTED` 是 terminal 非 PASS，宽触发一律报错；`未定` / 缺小节只在完成面
  报错。解析细节见 `openspec/specs/dev-workflow-gate/spec.md` 的 building review Scenario。
- **本地冒烟与默认 base**：`--base-ref` 未显式提供时，checker 用 `HEAD` 与
  `origin/master` 的 merge-base（三点语义；没有 `origin/master` 时回退到与 `master`
  的 merge-base）。本地 `master` 落后或分支落后于 `origin/master` 时，历史归档与上游
  受保护路径改动都不会被误判为本 PR 的变更；隐式解析会在 stderr 打一行
  `INFO: using implicit base ref ...`。裸跑前先 `git fetch origin master`，确保
  `origin/master` 不是陈旧的。显式 `--base-ref` 仍是两点 diff，可复现旧口径；CI 用
  PR base sha，不受影响。标准命令 `--base-ref origin/master --require-base` 继续可用。
- **瘦 checker 的命令与 exit 语义**（CI 的 `validate` job 已接入）：

```bash
# 0 = 通过；1 = 规则违规；2 = changes root 缺失或用法错误
uv run python scripts/check_openspec_artifacts.py --base-ref origin/master --require-base
```

  `--base-ref` 省略时用 `HEAD` 与 `origin/master` 的 merge-base（没有则退 `master`）；
  `--require-base` 让 base 不可解析时 fail-closed。`--check-archived` / `--skip-protected-paths`
  已删除：归档点完成度在正常模式的 diff 上评估，受保护写入解释由 witnessloop 承担。

## 业界调研门禁

方案设计（proposal/design）前须按改动性质分流调研业界最新实践或框架（核心规则见 AGENTS.md「业界调研门禁」节；机械校验由瘦项目规则 checker 执行）。本小节给判据举例、豁免 reason 写法示范与常见误用。

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

## witnessloop 接入（阶段 A 影子 → 阶段 C 已翻开关）

本仓已接入上游工具 **witnessloop**（流程门禁工具化抽取的独立仓）。change 与设计见 `openspec/changes/archive/2026-10-13-witnessloop-adoption/`，阶段 A 验收报告见该 change 的 `reviews/acceptance-stage-a.md`。

### 现状（阶段 C：`gate / check` 是唯一 required）

- **产物 4 个**：`.witnessloop/policy.json`（定制 policy）、`.witnessloop/init-manifest.json`（init 台账）、`.github/workflows/witnessloop.yml`（caller）、`.github/witnessloop-tests.txt`（测试执行点 = `uv run --extra dev pytest -q`）。`.github/workflows/ci.yml` **未被触碰**。
- **required 只有 `gate / check`**（阶段 C 翻开关，issue #305，2026-10-17）：`master` 的 `required_status_checks.contexts` = `["gate / check"]`。本仓自建的 `validate` / `benchmark-gate` / `windows-platform` **照跑、只是不再拦合并**。
- **降级代价（须知）**：只由本仓 checker 承载的 RIR / Impact Analysis / benchmark smoke / 归档点完成度 / backlog 一致性 / building review 的 `## 闭环出口` PASS 判据 **不再拦合并**。逐条分叉清单见 issue #305 的阶段 C 前置 comment。⇒ **不要把「CI 绿」读成「项目规则已满足」**。
- **caller 钉 `@v1.7.0`**：包版本由 reusable workflow 自己的 `job.workflow_sha` 推导（witnessloop issue #30 的修复），**不需要** `with: witnessloop-ref:`；升级 = `witnessloop init --gate-ref <新 ref>`（幂等，重写 caller + 同步台账）。
- **旧门禁主体已删除**：`workflow_state.py` / `agent/workflow/*` / `flow-policy.json` / `workflow_methods.json` / 旧 `workflow_guard.py` 已移除。`validate` job 仍跑 pytest + OpenSpec validate + **瘦项目规则 checker**（RIR / Impact / benchmark smoke / tasks 与归档点完成度 / backlog / building exit）；`scripts/platform_gate.py` 保留 branch protection 配置即代码；本地 Bash 写前拦截由 `scripts/bash_write_guard.py` 提供。
- **已知红（阶段 A 历史记录，已处置）**：① `add-minimal-tui-runtime-view`（无 `reviews/`）已由 `retire-tui-proposal`（issue #319 PR B）**原地废弃**：目录保留原样（不删、不写、不加标记；witnessloop 对纯 docs-only 删除/加标记分别实测 3/3 项 finding；含 code_hits 的删除实验为 5 项），backlog 移除，ADR-0006 留痕；② 阶段 A 的 change `witnessloop-adoption` 当时缺 witnessloop 形态 manifest（该 change **已归档**，此条只作历史记录）。两条都属「**缺 manifest**」这一类，不是配置错误。
- **`reviews/` 的一致状态（阶段 A 实测，仍然适用）**：一个 change 的 `reviews/` 下，**每份 `.md` 都必须被某份 witnessloop 形态 manifest 的 `report_path` 绑定**，否则触发孤儿规则——阶段 A 实测「只落一部分」比「一份都不落」更红（2 条 → 14 条 → 16 条）。阶段 C 之后 `gate / check` 是 required ⇒ 一个 change 要判绿就必须把 `reviews/` 落齐并全部绑定（`grill` / `grill-adversarial` / `building` 三份 manifest）。
- **grill 决策记录的格式契约（v1.7.0 实测，2026-10-17 补记）四条**：`reviews/grill-design.md` 必须含 `## Confirmed Decisions`（**至少 3 条**决策块——`MIN_CONFIRMED_DECISIONS = 3` 是硬门槛；且每条决策块内有**同行裸** `来源:`——加粗的 `- **来源**:` 匹配不上）、`## User Confirmation`（**无条件存在**：一条 Open Question 都没有时也要有该小节）、以及与逐字标题一致的 Open Questions 小节。详见 `openspec/specs/dev-workflow-gate/spec.md` 的「grill 报告正文判据的已知不兼容」。

### 本地跑 `check`

**必须锚定 CI 实际使用的 v1.7.0**。注意 `v1.7.0` 是 annotated tag：tag object `00192ab`
对应 commit `c9b2811`；本机 `/home/happy/witnessloop` 的当前 HEAD **不是** v1.7.0，不要用。

```bash
# 本机可执行锚点（实测 DEFAULT_GATE_REF=@v1.7.0）
/home/happy/wl170/bin/witnessloop check --root . --base origin/master --head HEAD
# 或者：git -C <witnessloop> checkout v1.7.0 && cd <witnessloop> && uv run witnessloop check --root <本仓根>
```

原因：PATH 上还有一份旧 uv-tool 版本（实测 0.1.0，没有 `guard` 子命令）；用错版本会得到
假绿/假红。

### 本地 `guard` 的前置核验（必做）

plugin 的守卫 shim `plugin/hooks/guard.sh` 调的是 **PATH 上的裸 `witnessloop`**，且退出码映射为「`1` → 拦（映射成 CC 的 `exit 2`），**其余一律放行**（含旧版 CLI 的 `invalid choice` → 2）」。⇒ PATH 上若是没有 `guard` 子命令的旧版 CLI，**整个守卫静默空转**，「放行」会被误读成「证据完备」。先核验：

```bash
command -v witnessloop && witnessloop --help | grep -q guard || echo "⚠️ PATH 上这份没有 guard：plugin 守卫空转，改用 uv run 那份或先升级"
```

### 两个 PreToolUse 守卫的分工

本仓现行形态是 **witnessloop plugin guard（`Write|Edit`）+ `scripts/bash_write_guard.py`（`Bash`）**。
旧 `scripts/workflow_guard.py`（`Write|Edit|Bash`）已删除；它的 Bash 面由新 guard 以更窄、
可测试的判据承接。

阶段 A 用 Claude Code 2.1.231 实测过「两个 hook 同时启用」的合并语义（记录见
`openspec/changes/archive/2026-10-13-witnessloop-adoption/reviews/acceptance-stage-a.md`）：
两个 hook **都执行**、**并行**、**任一 `exit 2` 即拦**（并集），被拦时只出现其中一个阻断
hook 的 stderr。`--permission-mode bypassPermissions` **不能**绕过 PreToolUse hook。
本 change 的 4.8 会按同一方法再记录一次当前两 hook 的求值归属。

**命名空间**：plugin 的 `plugin.json` 里 `"name": "witnessloop"` ⇒ 命令是
`witnessloop:grill` / `witnessloop:review-loop`，与仓内 `.claude/commands/{grill,review-loop}.md`
不撞名。

### 本地 Bash 写前拦截（`scripts/bash_write_guard.py`）

安装：把 `scripts/bash_write_guard.example.json` 的 `hooks` 块合并进
`.claude/settings.local.json`（项目本地、被 gitignore）或用户级 `~/.claude/settings.json`。
**building worktree 不会自动带 `.claude/`**：要么用示例里的绝对路径命令，要么在每个 worktree
手动安装；否则该 worktree 只有 witnessloop 的 `Write|Edit` guard。

边界：只拦**直接文件写操作**（重定向、`cp`/`mv`/`tee`/`dd`/`sed -i`/`install`/`rm` 等）命中
受管路径（`agent/**`、`scripts/**`、`web/**`）或受保护 artifact（policy 的 `protected_paths`）。
`ls`/`grep`/`cat`/`git status` 放行；引号内写样式文本、`cp` 的源参数、`>/dev/null`、`2>&1`、
here-doc 数据不误伤。`git rm`/`git mv` 放行（否则文件无法删除/改名）；显式路径的
`git restore` / `git checkout --` 与非只读 `git apply` 拦截；`git merge` / `rebase` /
`cherry-pick` / `stash` / `am`、变量展开、符号链接、`find -exec`、被执行程序等是**已知绕过面**
（本地 checkpoint，CI `gate / check` 兜底）。

**两 hook 并存实测（2026-10-18，命令级）**：把 witnessloop plugin 的 `guard.sh`（PATH 注入
v1.7.0 CLI）与 `scripts/bash_write_guard.py` 同时挂到同一临时仓库环境，用同一组 PreToolUse
payload 触发：

| payload | witnessloop guard（Write/Edit） | bash guard（Bash） | 并集结果 |
|---|---|---|---|
| Write `agent/loop.py`（缺 grill 证据） | exit 2（拦） | exit 0（不处理 Write） | 拦 |
| Bash `echo x > agent/y` | exit 0（无 `file_path`） | exit 2（拦） | 拦 |
| Bash `ls agent` | exit 0 | exit 0 | 放行 |

两个 hook 都执行；被拦时只有阻断 hook 的 stderr 出现。Claude Code 的并行 / 并集 / 提示归属语义
沿用阶段 A（2026-10-13）的真实 CC 2.1.231 实测记录。该实测不替代 CI：`gate / check` 仍是最终防线。

### Claude Code plugin：安装 / 升级 / 卸载

plugin 在 witnessloop 仓的 `plugin/` 下（`commands/` 的 `grill` / `review-loop` + `hooks/` 的 guard hook）。上游**没有** marketplace 清单（实测 `plugin/.claude-plugin/plugin.json` 存在、仓根无 `.claude-plugin/marketplace.json`），所以**没有 `claude plugin install` 这条路**，按上游 README 用启动参数加载：

```bash
# 安装（= 本次会话加载；不改仓库、不落任何文件）。<witnessloop> 指 witnessloop 仓的本地克隆目录
claude --plugin-dir <witnessloop>/plugin

# 升级：更新 witnessloop 仓（git pull / 切 tag），下次以同一路径启动即生效

# 卸载：不带 --plugin-dir 启动即可（没有任何落盘残留）
```

因为它是**启动参数**而非文件安装，`claude plugin list` 里看不到它（实测输出 `No plugins installed`）——这是正常的，不是装失败；判定是否加载成功看会话 init 事件里的 `plugins` 字段（实测 `[{"name":"witnessloop","path":…,"source":"witnessloop@inline","version":"0.1.0"}]`）与 slash command 里是否出现 `witnessloop:grill`。

**本地层与 CI 层是两个独立开关**：不装 plugin，CI 里的 `gate / check` 照跑；装了 plugin 也不会自动把 `gate / check` 勾成 required。

### 回退

```bash
# 依 init 台账精确回滚（删掉 .witnessloop/ + caller）
cd <witnessloop> && uv run witnessloop uninit --root <本仓根>

# 或手工删：.witnessloop/ + .github/workflows/witnessloop.yml + .github/witnessloop-tests.txt
```

回退不需要动 `ci.yml`、瘦 checker、Bash guard 或 branch protection；witnessloop 的 caller / policy 由 `uninit` 精确回滚。
