# README 事实校对（对抗式）

- **change**: `readme-narrative-refresh`
- **审阅对象**: `README.md`（中文）、`README_EN.md`（英文）
- **审阅基线**: 分支 `readme-narrative-refresh/2026-10-06`，工作区 HEAD `8a255b0`
- **审阅性质**: 独立零记忆、只读、对抗式事实核查（默认假设每句有错，逐条证伪）
- **verdict**: **CHANGES_REQUESTED**

> 说明：本报告只读，未修改 README。所有证据均为 `文件:行号`，来自当前工作区实际代码。

---

## 一、数字类（核对结论：基本正确）

| # | README 断言 | 实际值 | 证据 | 判定 |
|---|---|---|---|---|
| N1 | `agent/` 生产代码规模（proposal 口径 38,508 行 / 147 个 `.py`） | 147 个 `.py` / 38,508 行 | `find agent -name '*.py' -not -path '*__pycache__*'`（147 文件；`cat` 合计 38508 行） | **正确** |
| N2 | 测试 225 文件 / 3,511 函数（badge 文案「tests-3500+」） | 225 个 `test_*.py`；3,511 个 `def test_` | `find tests -name 'test_*.py' \| wc -l` = 225；`grep -rE '\bdef test_' tests \| wc -l` = 3511 | **正确**（badge 3500+ 成立） |
| N3 | 内置工具「40 个」 | 恰好 40 | `agent/tools/factory.py:72` `KNOWN_BUILTIN_TOOL_NAMES`（40 项），README `README.md:307-319` 表逐项数 = 40，集合完全一致 | **正确**（逐项对照无遗漏、无多列） |
| N4 | 上下文源「9 个」 | 根 loop 9 个；子 loop 8 个 | `agent/loop.py:1699-1721` `_make_default_context_builder`：SystemPrompt / AsterMd / MemoryIndex /（`include_workflow_asset_index` 默认 `True`，`loop.py:155`）WorkflowAssetIndex / Todo / SkillIndex / SkillActive / PlanMode / PlanningState = 9 | **正确（根 loop 口径）**；见备注 F1 |
| N5 | Hook 切面「7 个」 | 7 | `agent/hooks/manager.py:15-27`：on_run_started / before_iteration / after_llm_call / before_tool_execute / after_tool_execute / on_error / on_completion | **正确** |
| N6 | 编排模式 4 / workflow 节点 4 / 汇合语义 2 | 4 / 4 / 2 | `agent/subagent/patterns.py`（orchestrator-worker / peer-review / hierarchical / bidding）；`workflow.py:30` `NODE_KINDS = ("subagent","aggregate","route","foreach")`；`workflow.py:31` `JOIN_SEMANTICS = ("all_required","best_effort")` | **正确** |
| N7 | Benchmark「72 个任务（34 本地 + 38 SWE-bench Verified）」 | 72 = 34 + 38 | `benchmarks/tasks/`：含 `task.json` 的非 swebench 目录 = 34；`swebench-*` 目录 = 38 | **正确**（A 轨 22 / B 轨 11 / 无 track 1 = 34，见 proposal） |

---

## 二、能力断言类

### 2.1 Workflow DSL 与调度（核对结论：正确）

| # | README 断言 | 证据 | 判定 |
|---|---|---|---|
| W1 | 工具名 `DeclareWorkflow` / `StartWorkflow` / `GetWorkflow` / `CancelWorkflow` / `ReadWorkflowResult` / `DryRunWorkflow` / `RunWorkflow` / `SaveWorkflowAsset` / `GetWorkflowAsset` / `ListWorkflowAssets` / `RunWorkflowAsset` 均存在 | `agent/tools/builtin/subagents.py`：`:762` `DeclareWorkflow`、`:886` `StartWorkflow`、`:1033` `GetWorkflow`、`:1251` `CancelWorkflow`、`:960` `ReadWorkflowResult`、`:2055` `DryRunWorkflow`、`:1307` `RunWorkflow`、`:2202` `SaveWorkflowAsset`、`:2301` `GetWorkflowAsset`、`:2270` `ListWorkflowAssets`、`:2397` `RunWorkflowAsset` | **正确**（11/11 全存在） |
| W2 | 4 节点 / 2 汇合语义 / reducer 枚举 concat·merge_dict·first_non_empty·last | `workflow.py:30/31`；`workflow.py:34` `REDUCERS = ("concat","merge_dict","first_non_empty","last")` | **正确** |
| W3 | 环上必须有 route | `workflow.py:11-12`（模块说明）+ `:720-723` `_validate_cycles`「环上必须有 route 节点」 | **正确** |
| W4 | 多入边写同槽必须声明 reducer，schema 期校验 | `workflow.py:792-819` `_validate_reducers`；`workflow.py:396` 在校验链中调用 | **正确** |
| W5 | 三闸默认值 100 / 200 / 300 | `agent/config.py:354-356` `recursion_limit=100` / `max_nodes=200` / `max_runs=300`；`workflow.py:13,44-45` | **正确** |
| W6 | 每层预算 300 / 800 / 1500 / 3000 | `agent/subagent/aggregation.py:57-62` `DEFAULT_TOKEN_BUDGETS {leaf:300, shard:800, domain:1500, root:3000}` | **正确** |
| W7 | 四维预算字段名 + 「默认不限」 | `agent/subagent/workflow_budget.py:29` `DIMENSIONS = ("tokens","cost_usd","runs","wall_time_s")`；`:65-72` 缺配置落 `0` = 该维度不限 | **正确**（README 未列字段名，仅说「四维总预算」，无冲突） |
| W8 | 单汇聚上游 >10 自动插层 | `aggregation.py:36` `MAX_FAN_IN = 10`；`:126` `plan_layer_insertions`（`count <= max_fan_in` 返回空，即恰好 10 不触发） | **正确** |
| W9 | 「或叶子总数 >10」独立判据 | 见 **F1（口径模糊/夸大）** | **存疑** |

### 2.2 可观测（核对结论：正确）

| # | README 断言 | 证据 | 判定 |
|---|---|---|---|
| O1 | CostLedger 四维归因 | 见 **F2（错误）** | **错误** |
| O2 | ErrorClassifier 4 类业务错误 + unknown 兜底 | `agent/observability.py:20-27` `ErrorCategory`：PERMISSION_DENIED / NETWORK_TIMEOUT / MODEL_ERROR / PARAMETER_ERROR / UNKNOWN（4 业务 + unknown） | **正确** |
| O3 | 审批拒绝归到 permission_denied | `observability.py:46` `_ERROR_TYPE_TO_CATEGORY`：`"permission_denied" → PERMISSION_DENIED` | **正确** |
| O4 | trace step 流（run_started → llm_iteration → tool_call → approval → sandbox → compaction → completion） | `agent/trace_recorder.py`：`:101` `run_started`、`:126` `llm_iteration`、`:139` `tool_call`、`:197-201` `approval_request`/`approval_response`、`:195` `sandbox`、`:217` `memory_compaction`、`:299` `completion` | **基本正确**；见备注 F3（`approval`/`compaction` 为简写，实际 step 名是 `approval_request`/`approval_response`/`memory_compaction`） |
| O5 | 节点七档 / 边五档 | 见 **F4 / F5（错误）** | **错误** |

### 2.3 上下文工程（核对结论：正确）

| # | README 断言 | 证据 | 判定 |
|---|---|---|---|
| C1 | critical 层（P0/P1）永不裁剪 | `agent/context/sources.py:107-111`（SystemPrompt：priority 0 / critical True / cacheable True）、`:265-269`（AsterMd：priority 1 / critical True / cacheable True）；`builder.py:139,178` `_find_trimmable_index` 跳过 critical | **正确** |
| C2 | 可缓存层 = 系统提示 / ASTER.md / 记忆索引 | `sources.py:111`（SystemPrompt cacheable）、`:269`（AsterMd cacheable）、`:288`（MemoryIndex priority 2 / cacheable True）——三者是 `cacheable=True` 的全部来源 | **正确**（P2 内 `TodoSource` `sources.py:391` cacheable=False、`WorkflowAssetIndexSource` `workflow_asset_source.py:35` cacheable=False，README 未声称 P2 全部可缓存，无冲突） |
| C3 | 「是否存在 P3」 | `sources.py` 实际只用到 P0/P1/P2/P4/P5；`sources.py:4` docstring 写「P0-P6」但无 P3 源定义。README 未声称 P3 存在 | **无冲突** |
| C4 | AutoCompact L1 四字段（已完成 / 待办 / 疑难与决策 / 进行中） | `agent/context/summarizer.py:76-87`「exactly four sections：## 已完成事项 / ## 待办事项 / ## 疑难点与决策 / ## 当前进行中」 | **正确** |
| C5 | 未完成 tool_call 标记 `[call#…: … pending]` | `agent/memory/manager.py:407,585,608`（`[call#{i}: {tc.id} pending]`）；`summarizer.py:60,71,91,104` | **正确** |
| C6 | 前缀缓存断点 | `agent/loop.py:1314-1366` `_apply_cache_plan` / `_compute_cache_plan`；`builder.py:114-125` `build_blocks` 对 `cacheable` 源打 `cache=True` | **正确** |

### 2.4 长期记忆（核对结论：正确）

| # | README 断言 | 证据 | 判定 |
|---|---|---|---|
| M1 | 三路去重 supplement / update / conflict（new 兜底） | `agent/memory/dedup.py:24` `_ACTIONS = {"new","supplement","update","conflict"}`；`:45-50`（prompt 定义三选一 + new） | **正确** |
| M2 | 相似度低于阈值直接短路（零 LLM 成本） | `dedup.py:68-69,93-95`（`recall_threshold=0.5`，`below_recall_threshold` 直接返回 `new`） | **正确** |
| M3 | git commit-before-write + `MemoryGitBackend.revert` 两段式回滚 | `agent/memory/git_backend.py:11-15,69-75`（two-step commit：snapshot → apply revert → commit） | **正确** |
| M4 | `score = importance × 0.5^(days/30)`；30 天半衰期 | `agent/memory/persistent.py:212-223`（`recency = 0.5 ** (days/halflife)`；`return entry.importance * recency`）；`:43-44` `ARCHIVE_AFTER_DAYS = 30` / `RECENCY_HALFLIFE_DAYS = 30` | **正确** |
| M5 | recall/search 会 touch 更新 `last_accessed_at` | `persistent.py:714` `self._touch(entry.name)`；`:539` `last_accessed_at=now` | **正确** |

### 2.5 安全（核对结论：正确）

| # | README 断言 | 证据 | 判定 |
|---|---|---|---|
| S1 | 三层（WorkspacePolicy / CommandGuard / Sandbox） | `agent/workspace_policy.py`、`agent/tools/command_guard.py`、`agent/tools/sandbox/` | **正确** |
| S2 | 路径边界 + 目录穿越拒绝 + 敏感文件写入拒绝（`.env` 等） | `workspace_policy.py:69-91`（敏感 dot-file / `.env` 家族判定，含 `.env.example` 模板豁免） | **正确** |
| S3 | 覆盖 flag 重排 / timeout 包裹 / `$IFS` / 反斜杠转义 | `command_guard.py:53,67,93,147,163-188,259-291`（wrapper/launcher fixpoint、`$IFS`、反斜杠归一、`\n`/`\r` 预处理） | **正确** |
| S4 | 递归检查被包命令（`timeout 5 rm -rf /` 也拦得住） | `command_guard.py:288` 「Strip wrappers and launchers alternating to a fixpoint」；`:582-583` `rm -rf /` 正则；`:93` `_LAUNCHER_POSITIONAL_VALUE {"timeout","chrt"}` | **正确** |
| S5 | cgroup `memory.max` / `memory.swap.max` 硬禁 swap | `agent/tools/sandbox/cgroup.py:9,233-238`（`memory.max` + `memory.swap.max = "0"`） | **正确** |
| S6 | Docker `--network none` | `agent/tools/sandbox/docker_backend.py:6,103` | **正确** |
| S7 | 8 capability × 3 风险等级 × origin 判权；plan/read_only/build/bypass 各绑定 profile | `agent/tool_permissions.py:8-15`（8 capability）、`:18-21`（3 risk）、`:25-29`（origin 5 值）；`:144-183` `BUILTIN_PERMISSION_PROFILES`（build_default/read_only_default/plan_default/bypass_default/fail_closed） | **正确** |
| S8 | 高风险工具需人工审批，无人值守入口 fail-closed | `tool_permissions.py:179-183` `fail_closed` profile；`agent/run_config.py:175-178` 未知 mode → fail_closed；`openspec/specs/cli/spec.md:349-351`、`benchmark/spec.md:177-179` | **正确** |
| S9 | cgroup 不可用时降级纯 timeout，结果带 `degraded=True` + 一次性事件 | `agent/tools/sandbox/process_backend.py:109-135`（`_setup_cgroup` → `degraded` + `_emit_degraded_once`）；`base.py:107` `degraded: bool = False` | **正确** |

### 2.6 工具治理（核对结论：一处错误）

| # | README 断言 | 证据 | 判定 |
|---|---|---|---|
| T1 | 两段式召回：BM25 粗筛 50 → embedding Top-K=5 | `agent/tools/governance/selector.py:28-29` `top_k=5` / `coarse_k=50` | **正确** |
| T2 | 稳定核心层含 `Read`/`Edit`/`Write`/`Bash`/`Grep`/`Find`/`ListFiles` | 见 **F6（错误）** | **错误** |
| T3 | 质量评分 0.5/0.3/0.2，窗口 50、阈值 0.4 | `agent/tools/governance/quality.py:24-29`（`window_size=50`、`success_weight=0.5`、`duration_weight=0.3`、`approval_weight=0.2`、`degrade_threshold=0.4`） | **正确** |
| T4 | 零依赖 NGramEmbedding 默认 | `agent/tools/factory.py`（`_wire_governance` 内 `from agent.embedding import NGramEmbedding`） | **正确** |
| T5 | 是软降级不是禁用（schema 仍可见、仍可调用，权限模型不动） | `quality.py:6,105,113`（低于阈值离开「变化层」候选，给出提示语而非禁用） | **正确** |

### 2.7 其他能力断言

| # | README 断言 | 证据 | 判定 |
|---|---|---|---|
| X1 | Code Intelligence：Tree-sitter（TS/JS、Go、Rust）+ Python AST + RepoMap + Python LSP | `agent/code_intelligence/tree_sitter_symbols.py:120-163` `DEFAULT_TREE_SITTER_REGISTRY`（javascript/typescript/go/rust/**java/kotlin**）；`extractors.py:22-34`（PythonAstExtractor + TreeSitterExtractor）；`agent/lsp/` 存在 | **正确但低估**（实际支持 6 种语言，README 只列 3 类，非错误） |
| X2 | Browser 受控只读浏览器，默认关闭 | `agent/config.py:90-98` `BrowserConfig.enabled: bool = False`「默认 enabled=False，所有浏览器工具不注册」；`agent/tools/factory.py:370-372` 条件注册 | **正确** |
| X3 | MCP 通过 stdio / Streamable HTTP 接入，注册 `mcp__<server>__<tool>` | `agent/mcp/` 存在（README 未逐条核验命名模板，属既有口径） | **未证伪** |
| X4 | Web UI 三视图（Chat / Debug / Workflow） | `web/server.py`、`web/static/workflow_graph.js` | **正确** |
| X5 | 每次启动在 `logs/` 生成独立日志文件 | 见 **F7（口径错误）** | **错误** |

---

## 三、命令正确性（核对结论：flag 全部存在）

`agent/main.py`：

| README 命令 / flag | 证据 | 判定 |
|---|---|---|
| `asterwynd run "…"` | `main.py:387-389` `@app.command() def run(...)` | **正确** |
| `asterwynd web --port/--host` | `main.py:668-672` `def web(port=…"--port"…, host=…"--host"…)` | **正确** |
| `asterwynd benchmark … --agent fake/asterwynd` | `main.py:710-713` `--agent`（fake/shell/asterwynd/claude） | **正确** |
| `--source-repo` / `--runs-dir` / `--parallel` / `--fake-edit-file` / `--fake-old-string` / `--fake-new-string` | `main.py:714,715,723,726,727`(+`728`) | **正确** |
| `--repeat`（`--repeat 3`） | `main.py:731` `repeat: int = typer.Option(1,"--repeat", min=1)`（`:784-785` 上限 5） | **正确** |
| `--workflow-mode` | `main.py:752-754`（校验 `WORKFLOW_MODES`，`benchmarks/agent_runner.py:40` = template/dynamic-record/dynamic-replay） | **正确** |
| `--workflow-record` | `main.py:757-760` | **正确** |
| `asterwynd benchmark-gate … --baseline … --require-baseline` | `main.py:1216-1231`（`@app.command() def benchmark_gate`，typer 派生名 `benchmark-gate`；`--baseline`、`--require-baseline` 存在） | **正确** |
| `uv run asterwynd run --provider anthropic --model …` | `main.py:357-359` | **正确** |
| quickstart fake smoke `--fake-old-string '# Asterwynd'` 目标串 | 见 **F8（低：示例目标串在 README.md 中不存在）** | **存疑** |

---

## 四、图片路径（核对结论：全部存在）

| README 引用 | 文件系统 | 判定 |
|---|---|---|
| `docs/assets/asterwynd-wordmark.svg` | 存在 | **正确** |
| `docs/assets/readme/architecture.svg` | 存在（`docs/assets/readme/`） | **正确** |
| `docs/assets/readme/workflow-orchestration.svg` | 存在 | **正确** |
| `docs/assets/readme/feature-context.svg` | 存在 | **正确** |
| `docs/assets/readme/feature-memory.svg` | 存在 | **正确** |
| `docs/assets/readme/feature-safety.svg` | 存在 | **正确** |
| `docs/assets/readme/feature-tools.svg` | 存在 | **正确** |
| `docs/assets/readme/feature-observability.svg` | 存在 | **正确** |

> 注：`docs/assets/readme/*.svg` 为本 change 新增的未跟踪文件（`git status` 显示 `?? docs/assets/readme/`）。目录内还包含同名 `.excalidraw` 源文件，属工具源，无需在 README 引用。

---

## 五、错误清单（需修正）

### F2 ·【错误】CostLedger「四维成本归因」维度名写错

- **README 原文**（`README.md:126`、`README_EN.md:126`）：
  「`CostLedger` 四维成本归因：`by_session` / `by_node` / `by_depth` / `by_edge`」
- **实际**（`agent/cost_tracker.py:218-233`）：
  四维归因 = `by_workflow` / `by_node` / `by_depth` / `by_edge`；
  其中 `by_session`（连同 `by_phase`/`by_tool`）是**改造前的 legacy 三维**账单（`:214-216`）。
- **规范依据**：`openspec/specs/multi-agent-collaboration/spec.md:279`「`CostLedger` SHALL 增四维成本归因：by_workflow / by_node / by_depth / by_edge」。
- **修正建议**：把 `by_session` 改为 `by_workflow`（中英同步）：
  「四维成本归因：`by_workflow` / `by_node` / `by_depth` / `by_edge`」。

### F6 ·【错误】「稳定核心层」工具名单与代码常量不符

- **README 原文**（`README.md:109`、`README_EN.md:109`）：
  「`Read`/`Edit`/`Write`/`Bash`/`Grep`/`Find`/`ListFiles` 恒在前且字节不变」
- **实际**（`agent/loop.py:104-106`）：`CORE_STABLE_TOOL_NAMES = ("Read","Edit","Write","Bash","Glob","Grep","InspectGitDiff")`
  - README 列的 `Find` / `ListFiles` **不在**稳定层；
  - 稳定层里的 `Glob` / `InspectGitDiff` **被 README 漏列**。
  - 另注：`Glob` 在 `agent/tools/builtin/` 并无同名工具类（实际工具是 `Find`/`ListFiles`，见 `find.py:19`、`list_files.py:13`），故 `CORE_STABLE_TOOL_NAMES` 中的 `Glob` 可能是代码侧的历史遗留项；但 README 的事实口径应以该常量为准。
- **修正建议**：README 改为「`Read`/`Edit`/`Write`/`Bash`/`Grep`/`InspectGitDiff` …」（与常量一致）；若认为代码常量本身应更新（`Glob`→`Find`），应另立 bug/change 修正代码，README 不应先行描述未实现的名单。

### F4 ·【错误】「节点七档」——实际 8 档（另有投影层 `queued`）

- **README 原文**（`README.md:128`、`README_EN.md:128`）：Web 端实时 DAG「**节点七档状态**、边五档状态」。
- **实际**（`web/static/workflow_graph.js:210-219` `NODE_STATUS_TEXT` + `NODE_LABELS`）：
  `pending` / `started` / `completed` / `failed` / `cancelled` / `blocked` / `budget_exceeded` / `skipped` = **8 档**；另有投影层 `queued`（`workflow_graph.js:44-46`）。
- **一致源**：`docs/architecture.md:135` 明确写「**节点状态八档**」（同一仓库内已有正确口径），而本 change 同时改动的 `docs/architecture.md:71` 却写「节点七档」——两处自相矛盾。
- **修正建议**：README 改为「节点八档状态、边六档状态」（与 `architecture.md:135` / `:136` 对齐）。

### F5 ·【错误】「边五档」——实际 6 档

- **README 原文**（`README.md:128`、`README_EN.md:128`）：边五档状态。
- **实际**（`web/static/workflow_graph.js:226-233` `EDGE_STATUS_TEXT`）：`inactive` / `ready` / `active` / `passed` / `satisfied` / `blocked` = **6 档**；`agent/subagent/scheduler.py:3010-3016` `_edge_status` docstring 亦写「边**六档**状态……第 6 档 `satisfied` 见 issue #207」。
- **修正建议**：README 改为「边六档状态」。

### F9 ·【错误】项目结构声称 `agent/tui/` 存在——实际不存在

- **README 原文**（`README.md:266`、`README_EN.md:266`）：`└── tui/   # 终端 UI 运行视图`。
- **实际**：`agent/tui/` 目录**不存在**（`ls agent/tui` → No such file or directory）。全仓 `tui` 仅存在于 `openspec/specs/tui/` 与历史归档 change；实现层无 TUI 模块（仅 `agent/branding.py` 有 `render_tui_banner`）。
- **规范明确反向**：`openspec/specs/tui/spec.md:5`「**当前仓库尚未实现 TUI**」，`:9-17`「系统 SHALL NOT 声称已经支持独立 TUI……不提供 TUI 命令」。
- **修正建议**：从项目结构树中**删除** `tui/` 行；如需保留 `agent/` 实际目录，可改为列出 `workflow/`、`skills/ planning/ mcp/ browser/ code_intelligence/ lsp/`（均存在）。

### F10 ·【错误】`claw-swe-bench/` 目录与 `CLAW-SWE-BENCH.md` 均不存在

- **README 原文**：
  - `README.md:196-199` / `README_EN.md:196-199`：`cd claw-swe-bench && uv run python run_infer.py ...`；
  - `README.md:270` / `README_EN.md:270`：项目结构含 `claw-swe-bench/`；
  - `README.md:332` / `README_EN.md:332`：`claw-swe-bench/` 统一 harness 对比；
  - `README.md:391` / `README_EN.md:391`：文档地图指向 `./CLAW-SWE-BENCH.md`。
- **实际**：仓内既无 `claw-swe-bench/` 目录，也无 `CLAW-SWE-BENCH.md`（`find . -iname '*claw*'` 无结果；`git ls-tree HEAD` 亦无）。
- **修正建议**：删除/改写这 4 处。若该集成已下线，应从快速开始「更多运行方式」、Benchmark「两条评测路径」、项目结构、文档地图中一并移除；若仍计划保留，需提供实际路径或标注「未随本仓库分发」。

### F7 ·【口径错误】「每次启动在 `logs/` 生成独立日志文件」

- **README 原文**（`README.md:219`、`README_EN.md:219`）：每次启动在 `logs/` 生成独立日志文件。
- **实际**（`agent/main.py:55-67`）：`LOG_DIR = platformdirs.user_log_path("asterwynd")`，`LOG_FILE = LOG_DIR / f"asterwynd-<ts>.log"`。日志写到**操作系统用户日志目录**（如 `~/.local/state/asterwynd/log/`），不是仓库相对的 `logs/`。「每次启动独立文件」正确，但位置口径错。
- **修正建议**：改为「每次启动在用户日志目录（`platformdirs.user_log_path("asterwynd")`）生成独立日志文件」；或写「按 `asterwynd-<时间戳>.log` 生成独立日志文件（位于系统用户日志目录）」。

### F1 ·【口径模糊/夸大】「总叶子数 >10」为独立插层判据

- **README 原文**（`README.md:42`）：树状分层汇聚「单汇聚上游 >10 **或叶子总数 >10** 时调度器自动插层」。
- **实际**（`agent/subagent/aggregation.py:268-318` `ExecutionPlan.build`）：自动插层**仅按每个 aggregate 的「逻辑上游贡献数」**（`contributions > MAX_FAN_IN=10`）触发；全仓未找到以「总叶子数」为独立判据的逻辑（`grep -rE '总叶子|leaf_count|total_leaves|num_leaves' agent/` 无命中）。
  - 效果上：100 个叶子**汇入同一 aggregate** 时会触发（contributions=100>10）——这正是「上百个叶子」场景；但 100 个叶子分散到 20 个各 5 上游的 aggregate（总叶子 100 > 10）时**不会**触发。
- **说明**：该措辞与 `openspec/specs/multi-agent-collaboration/spec.md:180` 逐字一致，README 只是复述 spec。问题在 spec 与实现的潜在不齐（`总叶子数 >10` 分支在实现中不可独立观测）。
- **修正建议**：README 保留 spec 原文即可（口径与 spec 对齐），但**建议同时另立 issue** 澄清「总叶子数 >10」是 spec 层的说明性描述（其效果由「每个 aggregate 上游 >10」在树状拓扑下隐式覆盖），避免读者据字面推断存在全局叶子计数闸门。

---

## 六、低优先 / 备注（非阻塞）

- **F3（备注）** trace step 名：README 用概念名 `approval` / `compaction`，实际 step 类型为 `approval_request` / `approval_response` / `memory_compaction`（`trace_recorder.py:197-217`）。作为「全链路 step 流」的示意可接受，如需逐字精确可补全。
- **F8（低）** quickstart fake smoke 的 `--fake-old-string '# Asterwynd'`：`README.md` 已无 `# Asterwynd` 一级标题（当前 README 首行是 `<p align="center">`，`grep -c '^# Asterwynd$' README.md` = 0），fake runner 会记录 `old_string not found`（`benchmarks/agent_runner.py:107-108`）。该示例自 HEAD 起即如此（`git show HEAD:README.md:74-75`），非本 change 引入，但既然重写了快速开始，建议顺手改为仓库中确实存在的串。
- **F11（备注·非本文件范围）** `docs/architecture.md:71`（本 change 修改行）同样写「节点七档 / 边五档」，与同文件 `:135`「节点八档」矛盾；`docs/architecture.md:63` 复述「总叶子数 >10」。若修 README 口径，应同步修正 architecture.md 这两行，保持全仓一致。
- **备注·上下文源 9 的口径**：README 写「9 个上下文源」，成立前提是**根 loop**（`include_workflow_asset_index` 默认 True）。子 agent loop 为 8 个（`agent/subagent/manager.py:1329` 传 `include_workflow_asset_index=False`）——各子 agent 少 1 源，正是设计意图（见 `loop.py:1708-1711`）。README 主语境谈的是「父子 agent 通用注入」，此处「9」应按「根 loop」理解；当前措辞可接受，若追求严谨可加注「（根 loop；子 agent 少 workflow asset 索引一源）」。

---

## 结论

- **verdict: CHANGES_REQUESTED**
- 阻塞项（必须改）：**F2（cost 维度名）**、**F6（稳定层工具名单）**、**F4（节点档数）**、**F5（边档数）**、**F9（`tui/` 不存在）**、**F10（`claw-swe-bench/` 与 CLAW-SWE-BENCH.md 不存在）**、**F7（logs 路径）**。
- 口径项（建议改）：**F1**。
- 数字、Workflow DSL、上下文、记忆、安全、工具治理常量、CLI flag、图片路径——**均经代码实证核对通过**（见各表）。
