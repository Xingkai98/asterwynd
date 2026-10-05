<p align="center">
  <img src="./docs/assets/asterwynd-wordmark.svg?v=20260628-centered" alt="Asterwynd" width="760" />
</p>

<p align="center">
  <a href="./README.md">简体中文</a>
  ·
  <a href="./README_EN.md">English</a>
</p>

<p align="center">
  <strong>以星为引，变更有证。</strong>
</p>

<p align="center">
  <a href="https://github.com/Xingkai98/asterwynd/actions/workflows/ci.yml"><img src="https://github.com/Xingkai98/asterwynd/actions/workflows/ci.yml/badge.svg" alt="CI" /></a>
  <img src="https://img.shields.io/badge/python-3.11%2B-blue.svg" alt="Python 3.11+" />
  <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="MIT" />
  <img src="https://img.shields.io/badge/tests-3500%2B-brightgreen.svg" alt="tests" />
  <img src="https://img.shields.io/badge/benchmark-72%20tasks-orange.svg" alt="benchmark tasks" />
</p>

**Asterwynd** 是一个会**自己组队干活**的本地 Coding Agent。它不只逐条调用工具改文件——面对一个任务，它能把任务**声明成一张协作图**（并行调研 / 汇合 / 条件分支 / 动态展开），调度一群受预算约束的子 agent 执行，并留下每一步的 **diff、成本账本、工具 trace 与可回放的编排记录**——让每次代码修改都是**可证明的**，而不只是「看起来对的」。

星辰定向，风推动前行，trace 证明来过。

<p align="center">
  <img src="./docs/assets/readme/architecture.svg" alt="Asterwynd 系统架构" width="1000" />
</p>

---

## 特色

### 1 · 动态 Workflow 编排 —— 把任务声明成一张协作图

大多数 coding agent 的工作方式是「模型逐条调工具」，遇到需要并行调研、多方案评审、动态扇出的大任务时只能串行硬推。Asterwynd 让模型**一次性声明协作拓扑**，由系统调度执行：

- **声明式 DSL**：`DeclareWorkflow` 声明拓扑并返回 `workflow_id`，`StartWorkflow` 启动，`GetWorkflow` 查 bounded 状态，`CancelWorkflow` 取消；`RunWorkflow` 是便捷语法（内部走 Declare + Start）。
- **4 种节点**：`subagent`（一个子 agent run）、`aggregate`（多上游汇聚）、`route`（按结构化结果选下一条边）、`foreach`（对有限集合动态展开并行）。
- **2 种汇合语义**：`all_required`（等齐）与 `best_effort`（等截止时间，消费已完成结果并保留失败记录）——「失败不 fail-fast」只在 aggregate 层实现。
- **树状分层汇聚**：模型显式声明 aggregate 树（leaf→shard→domain→root），单汇聚直接上游 >10 时调度器自动插入分层 aggregate，每层受 token 预算约束（leaf 300 / shard 800 / domain 1500 / root 3000）——**上百个叶子也不会撑爆父 agent 上下文**。
- **父 agent 永远 bounded**：父只收 bounded envelope（`workflow_id`/`status`/`completed`/`failed`/`pending`/`root_result_ref`），子级结果落盘 `result_ref`，按需显式 inspect，不默认展开。
- **零成本试错**：`DryRunWorkflow` 不真跑，就能看到图会怎么走、文本会怎么流——模型不必写一次性真 workflow 探路。

<p align="center">
  <img src="./docs/assets/readme/workflow-orchestration.svg" alt="Workflow 编排：声明 → 调度 → 预算/账本/可见" width="1000" />
</p>

**为什么难**：编排系统要同时解决「拓扑合法」（4 种节点 + 汇合语义 + 环上必须有 route + 多入边写同槽必须声明 reducer，全部 schema 期校验）、「不烧穿预算」（四维总预算 + 图级递归上限 + 三闸）、「父 agent 不被淹」（bounded envelope + 分层汇聚）、和「运行时看得见」（运行态图快照 + 三出口报告截断）。Asterwynd 四点都落到了实现与 spec。

---

### 2 · 上下文工程 —— 9 源分层注入 + 前缀缓存 + L1/L2 分层压缩

注入不是「一股脑塞进去」。`ContextBuilder` 把系统提示、ASTER.md、记忆索引、技能、计划、待办等 **9 个上下文源**按优先级（P0 最高）编排：

- **critical 层（P0/P1）永不裁剪**；**可缓存层**（系统提示 / ASTER.md / 记忆索引）**字节级不变**，让 Anthropic 的 `cache_control` 断点命稳 **Prompt Cache**；P4/P5（技能 / 计划）与动态尾部（对话历史、工具结果）才是每轮可变的部分。
- **AutoCompact** 在 token 阈值触发，按 L1/L2 分层压缩：L1 把中间部分压成四字段结构化摘要（已完成 / 待办 / 疑难与决策 / 进行中），多个 L1 累积超阈值时 L2 压成顶层结论。
- **工具链不断裂**：压缩会把中间 tool result 压掉，未完成的 `tool_call` 被标记 `[call#…: … pending]`，保证消息链合法。

<p align="center">
  <img src="./docs/assets/readme/feature-context.svg" alt="上下文工程：9 源分层注入" width="1000" />
</p>

**为什么难**：前缀缓存要求「稳定前缀逐字节不变」，但上下文又要按轮次更新——这两者天然冲突。Asterwynd 的解法是分层 + 缓存标记：把不变的和可变的切开，让缓存命中率和上下文新鲜度同时成立。

---

### 3 · 长期记忆 —— 写时去重 + git 可逆 + 衰减归档

记忆最大的风险不是「记不住」，而是「记错了还改不回来」。Asterwynd 把可逆性做在**写路径**上：

- **写时 LLM 三路去重**：`supplement` / `update` / `conflict`（`new` 兜底），相似度低于阈值直接短路（零 LLM 成本）。
- **git commit-before-write**：写入前先快照，误判了可用 `MemoryGitBackend.revert` 两段式回滚——**绝不静默污染记忆库**（对比 mem0 的 ADD-only，取舍记录在 [ADR-0002](./docs/adr/ADR-0002-long-term-memory-reversibility.md)）。
- **importance × recency 衰减**：`score = importance × 0.5^(days/30)`，30 天半衰期；超期未访问且分数低于阈值自动归档（可恢复）；recall/search 会 touch 更新 `last_accessed_at`。

<p align="center">
  <img src="./docs/assets/readme/feature-memory.svg" alt="长期记忆：写入 / 可逆 / 衰减" width="1000" />
</p>

**为什么难**：把「可逆」当成第一公民。大多数记忆系统假设写入是对的，Asterwynd 假设写入可能错，于是把回滚通道和写入通道一起设计。

---

### 4 · 三层纵深防御 —— 护栏不是边界，隔离才是

安全上最大的认知陷阱是把「正则校验」当成边界。Asterwynd 明确区分：

- **第一层 WorkspacePolicy**：路径边界 + 目录穿越拒绝 + 敏感文件写入拒绝（`.env` 等）。
- **第二层 CommandGuard**：语义级命令校验，覆盖 flag 重排 / `timeout` 包裹 / `$IFS` / 反斜杠转义等绕过变体，**递归检查被包命令**（`timeout 5 rm -rf /` 也拦得住）。
- **第三层 Sandbox**：`ProcessBackend` + cgroup v2 资源限制（`memory.max`/`memory.swap.max` 硬禁 swap）或 Docker 容器隔离（`--network none`）——**这才是唯一的边界**。
- **细粒度权限**：`ToolPermission` 用 8 种 capability × 3 个风险等级 × origin 判权，`plan`/`read_only`/`build`/`bypass` 各绑定一套 profile；高风险工具需人工审批，无人值守入口 fail-closed。
- **降级绝不静默**：cgroup 不可用时降级为纯 timeout，结果带 `degraded=True` + 一次性事件，绝不谎称「已限制」。

<p align="center">
  <img src="./docs/assets/readme/feature-safety.svg" alt="三层纵深防御" width="1000" />
</p>

**为什么难**：分清「护栏（guardrail）」和「边界（boundary）」——护栏降低风险，边界才真正隔离。诚实标注降级状态，比假装安全更重要。

---

### 5 · 工具治理 —— 40 个工具不必全塞给模型

工具一多，全量注入既浪费 token 又稀释注意力。Asterwynd 做**动态 Top-K 选择**：

- **两段式召回**：BM25 粗筛 50 → embedding 精排取 **Top-K = 5** 注入本次 LLM 调用。
- **稳定核心层**：`CORE_STABLE_TOOL_NAMES` 里实际注册的核心工具（`Read`/`Edit`/`Write`/`Bash`/`Grep`/`InspectGitDiff`）恒在前且字节不变，**不占 Top-K 预算**——稳定前缀保住 Prompt Cache，变化只发生在尾部。
- **质量软降级**：运行时按「成功率 / 耗时 / 审批率 = 0.5 / 0.3 / 0.2」评分（窗口 50、阈值 0.4），低分工具退出「变化层」候选——**是软降级不是禁用**，schema 仍可见、仍可调用，权限模型不动。
- **零依赖默认**：内置 NGramEmbedding，可换真 embedding provider。

<p align="center">
  <img src="./docs/assets/readme/feature-tools.svg" alt="工具治理：动态 Top-K + 稳定核心层" width="1000" />
</p>

**为什么难**：「省 token」和「命中缓存」是两个会互相打架的目标——动态选择让注入内容每轮都变，缓存就废了。解法是切出恒定的稳定层，只让尾巴变。

---

### 6 · 可观测 + 评测闭环 —— 每次变更都可证明

不是「看起来对」，而是留下一条证据链：

- **TraceRecorder**：全链路 step 流（`run_started` → `llm_iteration` → `tool_call` → `approval` → `sandbox` → `compaction` → `completion`）。
- **CostLedger 成本归因**：在既有 `by_session` / `by_phase` / `by_tool` 三维之外，增 workflow 四维归因 `by_workflow` / `by_node` / `by_depth` / `by_edge`——能回答「哪个节点最贵、哪层重复 token 最多、动态 vs 固定 pattern 差多少」。
- **ErrorClassifier**：结构化错误分类（4 类业务错误 + `unknown` 兜底，审批拒绝归到 `permission_denied`）。
- **运行态图可视化**：Web 端实时 DAG（节点八档状态、边六档状态，route 控制边单列，桌面/手机双布局）。
- **Benchmark 闭环**：**72 个任务**（34 本地 + 38 SWE-bench Verified）在 git worktree / Docker 隔离执行，隐藏评测文件防作弊，产出 pass@k / pass^k / cost@pass / bootstrap 95% CI / `fault_owner` 归因；CI 回归门禁对比 baseline（成功率 drop > 5pp 或 p95 超基线 → FAIL）。

<p align="center">
  <img src="./docs/assets/readme/feature-observability.svg" alt="可观测 + 评测闭环" width="1000" />
</p>

**为什么难**：把「过程记录」和「财务记录」解耦（trace vs cost ledger），把「可复现」做实（固定 seed bootstrap），把「防作弊」做进隔离（评测前隐藏 task 文件），并且诚实标注边界（幻觉类错误不自动分类，需 LLM judge）。

---

## 用 Agent 开发 Agent

Asterwynd 用**自己定义的一套工程闭环**开发自己——不是一次性 demo，是持续运行的开发纪律：

```
需求讨论 → OpenSpec 立项（proposal / design / tasks / spec-delta）
        → 独立 subagent 设计追问（grill，逐条决策 + 停轮等用户确认）
        → 独立零记忆 subagent 对抗验证（试图推翻设计结论）
        → 实现（独立 git worktree，测试先行）
        → 独立 subagent 审阅闭环（审 → 改 → 再审，直到 PASS 或 3 轮封顶）
        → CI 门禁（全量 pytest + OpenSpec strict validate + artifact checker + benchmark-gate）
        → 归档收尾（spec 同步 + change 归档 + backlog 清理）
```

这套流程本身也被机器强制：受保护路径需结构化事件、审阅需 review manifest 绑定 hash、grill 需结构化决策记录、分支名要能推导 change-id。**项目的每次变更都走这条路，包括这份 README。**

---

## 快速开始

```bash
# 安装（uv，推荐）
uv sync --extra dev

# 配置 API Key（OpenAI 或 Anthropic 兼容端点均可）
cp .env.example .env
# 编辑 .env：填 OPENAI_API_KEY 或 ANTHROPIC_API_KEY
# 可选：OPENAI_BASE_URL 指向任意 OpenAI 兼容 API（DeepSeek / OrcaRouter 等）
# 可选：ASTERWYND_PROVIDER（openai / anthropic）、ASTERWYND_MODEL 设默认

uv run asterwynd run "Hello"          # CLI 单轮
uv run asterwynd                       # CLI 交互模式
uv run asterwynd web --port 8000       # Web UI
uv run pytest -q                       # 跑测试

# 本地 benchmark（fake runner smoke，确定性）
uv run asterwynd benchmark benchmarks/tasks \
  --agent fake --source-repo . --runs-dir /tmp/smoke \
  --fake-edit-file README.md \
  --fake-old-string 'Asterwynd' --fake-new-string 'Asterwynd Coding Agent'
```

`uv run` 是推荐的环境隔离方式（依赖更可复现），不是业务运行必需——环境已就绪时 `asterwynd run "Hello"` / `pytest -q` 等价可用。

<details>
<summary><b>更多运行方式（provider 覆盖 / Web Debug / 编排 benchmark）</b></summary>

```bash
# 覆盖 provider / model
uv run asterwynd run --provider anthropic --model claude-sonnet-4-20250514 "Hello"

# Web UI + 详细日志（记录 LLM 输入/输出）
ASTERWYND_LOG_LEVEL=DEBUG uv run asterwynd web --port 8000 --model deepseek-v4-pro

# Web Debug 界面（Chat + Debug 双视图）
ASTERWYND_DEBUG=enabled uv run asterwynd web --host 127.0.0.1 --port 8000

# 编排 benchmark：模型自由生成 workflow 并旁路记录（详见「Benchmark」节）
uv run asterwynd benchmark benchmarks/tasks --agent asterwynd \
  --provider anthropic --model deepseek-v4-flash \
  --workflow-mode dynamic-record --runs-dir /tmp/record
```

交互模式内置 slash command：`/help`、`/status`、`/mode <build|read_only|plan|bypass>`、`/clear`、`/compact`、`/skills`、`/skills reload`、`/mcp`、`/<skill-name> <request>`、`/exit`。

</details>

---

## Web UI

```bash
uv run asterwynd web --port 8000                          # 基本启动
ASTERWYND_DEBUG=enabled uv run asterwynd web --port 8000  # 开启 Debug 视图
```

- **Chat 视图**：Markdown 渲染、工具调用可视化、长结果折叠、session/run/mode 展示、Plan Document + planning state、审批卡片。
- **Debug 视图**：逐轮展示发给 LLM 的完整消息列表、LLM 响应、工具调用详情、记忆压缩事件。
- **Workflow 视图**：运行态 DAG 实时图（节点/边状态高亮、route 控制边单列、桌面/手机双布局）。

会话内可切换 `build` / `read_only` / `plan` / `bypass` 模式。每次启动在平台用户日志目录（`platformdirs.user_log_path("asterwynd")`）生成独立日志文件。

<details>
<summary><b>环境变量与配置优先级</b></summary>

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `ASTERWYND_PROVIDER` | `openai` | LLM 提供商：`openai` 或 `anthropic` |
| `ASTERWYND_MODEL` | 各 provider 默认 | 使用的模型名称 |
| `ASTERWYND_LOG_LEVEL` | `INFO` | `DEBUG` 时记录 LLM 请求 payload 和原始响应 JSON |
| `ASTERWYND_DEBUG` | `disabled` | `enabled` 时开启 Debug Web UI |

配置优先级：CLI 显式参数 > 进程环境变量 > `.env` 加载值 > `asterwynd.yaml` > 代码默认值。API key / base URL / provider / model / debug / log level 用 `.env` 或环境变量；agent mode、permission profile、工具策略、工具结果展示阈值和 benchmark 默认参数用 `asterwynd.yaml`。

</details>

---

## 项目结构

```text
agent/
├── loop.py                  # AgentLoop 核心（消息驱动主循环）
├── llm.py                   # LLM Protocol + ToolCallDelta
├── openai_llm.py            # OpenAI Chat Completions 实现
├── anthropic_llm.py         # Anthropic Messages API 实现
├── workspace_policy.py      # 工作区安全边界
├── trace_recorder.py        # 全量轨迹记录
├── cost_tracker.py          # 成本账本（四维归因）
├── observability.py         # 结构化错误分类
├── context/                 # ContextBuilder 上下文注入管线 + Summarizer
├── memory/                  # MemoryManager + AutoCompact + 长期记忆 + git backend
├── tools/
│   ├── registry.py          # ToolRegistry
│   ├── sandbox/             # ProcessBackend / cgroup / Docker 三后端
│   ├── command_guard.py     # 命令语义护栏
│   ├── governance/          # 动态 Top-K 工具选择 + 质量软降级
│   └── builtin/             # 内置工具（文件/命令/浏览器/搜索/子 agent 等）
├── subagent/
│   ├── scheduler.py         # Workflow 调度器（DAG 执行 + 预算 + 分层汇聚）
│   ├── workflow.py          # Workflow DSL 数据结构与 schema 校验
│   ├── patterns.py          # 4 个内置编排模式（编译为 DSL 模板）
│   ├── manager.py           # 子会话 runtime（并发 / 深度 / 预算护栏）
│   ├── bus.py               # 轻量消息总线（非权威）
│   └── snapshot.py          # 快照与恢复
├── workflow/                # 开发流程状态机 + 事件日志 + review manifest
└── skills/ planning/ mcp/ browser/ code_intelligence/ lsp/  # 支撑能力

web/                         # FastAPI + WebSocket（Chat / Debug / Workflow 视图）
benchmarks/                  # 本地 runner + 72 任务 + 统计 / 门禁 / 对比
docs/                        # 架构 / 开发指南 / 测试指南 / ADR / 面试材料
openspec/                    # 需求与规格（specs/ 已确认规格，changes/ 演进中变更）
```

---

## 架构

- **核心循环**：`AgentLoop.run()` 是唯一状态管理者，`messages` 是唯一可变状态；工具执行、记忆压缩、子会话 runtime 通过依赖注入持有引用。tool-call 消息链合法性由 API 强制。
- **编排层**：`agent/subagent/scheduler.py` 执行 Workflow DSL 编译出的 DAG，管理节点状态机、数据槽、预算闸门与分层汇聚。
- **可观测栈**：TraceRecorder（过程）+ CostLedger（成本）+ ErrorClassifier（错误）+ 运行态图快照构成全链路证据面。
- **插件面**：7 个 Hook 生命周期切点；`@tool_parameters` 声明式工具注册；skill 目录式加载；MCP 通过 stdio / Streamable HTTP 接入。

<details>
<summary><b>完整模块表与内置工具清单</b></summary>

| 模块 | 说明 |
|------|------|
| **AgentLoop** | 消息驱动主循环；`messages` 是唯一状态，能力委托给插件 |
| **ToolRegistry** | `@tool_parameters` 声明式注册；40 个内置工具 + MCP 动态挂载 |
| **Tool Governance** | BM25 + embedding 动态 Top-K 选择；稳定核心层保前缀缓存；质量软降级 |
| **Code Intelligence** | Tree-sitter（TS/JS、Go、Rust）+ Python AST 符号提取；RepoMap；Python LSP 语义工具 |
| **WorkspacePolicy** | 路径穿越拒绝、敏感文件写入拒绝、命令拒绝列表 |
| **CommandGuard** | 命令语义护栏（flag 重排 / timeout 包裹 / `$IFS` / 反斜杠转义） |
| **Sandbox** | ProcessBackend + cgroup v2 / Docker（`--network none`）双后端，降级不静默 |
| **HookManager** | 7 个生命周期切点；内置日志/重试/追踪/预算 Hook |
| **MemoryManager** | AutoCompact（L1/L2 分层压缩、tool_call pending 标记）；长期记忆（写时去重 + git 可逆 + 衰减） |
| **ContextBuilder** | 9 个 ContextSource 分层注入；静态源缓存 + 稳定前缀（Prompt Cache 断点） |
| **SubAgentManager** | 子会话 runtime：独立 transcript、多次 run、并发队列、深度护栏、快照恢复 |
| **Workflow Scheduler** | 声明式 DSL 执行：4 节点 / 2 汇合语义 / 树状汇聚 / 四维预算 / bounded envelope |
| **Orchestration Patterns** | 4 个内置模式（orchestrator-worker / peer-review / hierarchical / bidding），编译为 DSL 模板 |
| **Browser** | 受控只读浏览器（导航、截图、内容提取、标签页），安全策略约束 |
| **MCP Adapter** | stdio / Streamable HTTP server 接入，注册 `mcp__<server>__<tool>` |
| **Observability** | TraceRecorder + CostLedger（四维）+ ErrorClassifier + 运行态图可视化 |
| **Benchmark** | 72 任务（34 本地 + 38 SWE-bench Verified）；workflow 三模式；CI 回归门禁 |

**内置工具（40 个，含默认关闭的浏览器工具）**：

| 类别 | 工具 |
|------|------|
| 文件读写 | `Read` · `ReadDoc` · `Write` · `Edit` · `ListFiles` · `Find` · `Grep` · `InspectGitDiff` |
| 命令执行 | `Bash`（结构化输出：exit_code / stdout / stderr / duration / timed_out） |
| 代码理解 | `RepoMap` · `SymbolSearch` · `LspDefinition` · `LspReferences` · `LspHover` · `LspDocumentSymbols` · `LspWorkspaceSymbols` · `LspDiagnostics` |
| 联网研究 | `WebSearch` · `WebFetch` |
| 记忆 | `SaveMemory` · `RecallMemory` · `SearchMemory` · `ResolveMemoryConflict` · `MemoryGitBackend` |
| 规划与交互 | `UpdatePlan` · `ExitPlanMode` · `TodoWrite` · `AskUserQuestion` |
| 技能与任务 | `ActivateSkill` · `TaskOutput` · `TaskStop` |
| 工作树 | `EnterWorktree` · `ExitWorktree` |
| 浏览器（默认关闭） | `BrowserNavigate` · `BrowserGetContent` · `BrowserScreenshot` · `BrowserScroll` · `BrowserListTabs` · `BrowserSwitchTab` · `BrowserCloseTab` |

命令安全：先经 mode permission profile 判权；默认 `build` mode 下 high risk 命令需审批，CLI 单轮与 benchmark 等无人值守入口 fail-closed（显式 `bypass` 才放行）。执行前仍检查正则黑名单（`rm -rf /`、fork 炸弹、`curl | sh` 等）再匹配安全前缀白名单。项目级规则经 `asterwynd.yaml` 扩展，见 `asterwynd.example.yaml`。

</details>

<details>
<summary><b>扩展指南（添加工具 / Hook / 技能）</b></summary>

**添加新工具**：创建 `agent/tools/builtin/my_tool.py`，继承 `Tool` ABC 并用 `@tool_parameters` 声明 schema；在 `agent/tools/__init__.py` 中 import 并加入 `get_default_tools()`；注册到 `ToolRegistry`。

```python
from agent.tools import Tool, tool_parameters, ToolRegistry

@tool_parameters(
    name="MyTool",
    description="做什么",
    parameters={"type": "object", "properties": {"arg": {"type": "string"}}},
)
class MyTool(Tool):
    read_only = True

    async def execute(self, arg: str, **kwargs) -> str:
        return f"result: {arg}"

registry = ToolRegistry()
registry.register(MyTool())
```

**添加新 Hook**：实现 `Hook` Protocol（7 个生命周期方法，均可空实现），传入 `HookManager([MyHook()])`。

```python
from agent.hooks import HookManager, Hook

class MyHook(Hook):
    async def on_run_started(self, run_config): ...
    async def before_iteration(self, iteration, messages): ...
    async def after_llm_call(self, response): ...
    async def before_tool_execute(self, tool_call): ...
    async def after_tool_execute(self, tool_call, result): ...
    async def on_error(self, error): ...
    async def on_completion(self, result): ...
```

**添加新技能**：在 `skills/<name>/SKILL.md` 创建目录式 skill（YAML frontmatter + prompt 正文）。

```markdown
---
name: my-skill
description: 技能描述
tools: [Read, Bash]
always: false
user_invocable: true
argument_hint: <request>
triggers:
  - 触发词
---

# 技能标题

这里是指示 prompt...
```

每次 run 都会向模型注入简短 skill index；完整 skill prompt 只在 `always: true`、本地匹配、显式 `/my-skill ...` 或 `ActivateSkill` 工具激活时进入当前 run context。交互模式可用 `/skills` 查看加载结果、`/skills reload` 重新加载 configured skill roots。

</details>

---

## Benchmark

内置 runner 覆盖 **72 个任务**（34 本地 A/B 轨 + 38 `swebench-*` Verified 子集），在 git worktree / Docker 隔离执行。

```bash
# 真实 agent 评测
uv run asterwynd benchmark benchmarks/tasks --agent asterwynd --source-repo . --runs-dir /tmp/bench

# 重复运行 + 量化报告（pass@k / pass^k / cost@pass / bootstrap CI / fault_owner）
uv run asterwynd benchmark benchmarks/tasks \
  --agent fake --source-repo . --runs-dir /tmp/eval --repeat 3 --parallel 1

# CI 回归门禁（对比已提交基线，劣化 >5% 非零退出）
uv run asterwynd benchmark-gate benchmarks/tasks/gate-smoke \
  --source-repo . --baseline benchmarks/baseline.json --require-baseline
```

<details>
<summary><b>编排 benchmark（workflow 三模式）与评测流程</b></summary>

`--workflow-mode` 让 benchmark 直接测「编排本身」的质量：

| 模式 | 含义 |
|---|---|
| `template` | 固定 Pattern/DSL 模板当被测编排，走既有 verifier 判分（固定 baseline） |
| `dynamic-record` | 模型自由生成 workflow，执行时旁路记录规范化 spec 与编排指标 |
| `dynamic-replay` | 读已保存记录、不重跑规划模型、离线重放；只比编排指标、不判分 |

```bash
uv run asterwynd benchmark benchmarks/tasks \
  --agent asterwynd --provider anthropic --model deepseek-v4-flash \
  --workflow-mode dynamic-record --runs-dir /tmp/record

uv run asterwynd benchmark benchmarks/tasks \
  --agent asterwynd --provider anthropic --model deepseek-v4-flash \
  --workflow-mode dynamic-replay --workflow-record /tmp/record --runs-dir /tmp/replay
```

报告新增独立的 workflow 编排 section（冗余度 / 图级步数 / 拒绝降级计数 / 节点数 / 峰值并发 / 关键路径 / 编排成本），主表只加一列 `workflow_mode`；`dynamic-replay` 记录不进 pass@k 分母。

**评测流程（本地任务）**：在 base_commit 创建独立 worktree → 隐藏 `benchmarks/tasks/`（防作弊）→ agent 运行 → 捕获改动 diff（`:!tests/` 排除测试）→ 重置 worktree 重放源码改动 → 应用 `test.patch`（隐藏评测测试）→ 运行验证命令 → 写 `result.json` / `trace.json` / `runner.log`。结果状态：`passed` / `passed_with_warnings` / `unsupported` / `failed` / `error`，细节归因写入 `reason`。

</details>

---

## 文档地图

| 文档 | 内容 |
|------|------|
| [项目定位](./docs/project-positioning.md) | 目标岗位、主线/支撑能力、能力证明链 |
| [上下文词汇](./CONTEXT.md) | 需求、路线图、面试材料的核心项目语言 |
| [架构说明](./docs/architecture.md) | AgentLoop、工具系统、编排、上下文、记忆、Web UI、Benchmark |
| [开发指南](./docs/development-guide.md) | 安装、运行、常用命令、环境变量、开发流程 |
| [测试指南](./docs/testing-guide.md) | 测试分层、回归测试规则、覆盖要求 |
| [Agent 内部机制](./docs/agent-internals.md) | 逐章代码走读（主循环 / 工具 / 上下文） |
| [经验教训](./docs/lessons-learned.md) | 历史问题、根因、后续必须吸取的教训 |
| [ADR](./docs/adr/) | 架构决策记录（长期记忆存储与可逆性等） |
| [OpenSpec](./openspec/project.md) | 能力域地图；`specs/` 已确认规格，`changes/` 演进中变更 |
| [面试讲稿](./docs/interview-script/README.md) | 分层讲稿 + 代码走读 |
| [开发队列](./docs/openspec-change-backlog.md) | 未实现 OpenSpec change 与建议顺序 |
| [Benchmark 方案](./docs/benchmark-plan.md) | 任务集、runner、评测指标与结果设计 |

## 技术栈

Python 3.11+ / asyncio / FastAPI + WebSocket / httpx / typer / tree-sitter / tiktoken（可选）

## 致谢

- [OrcaRouter](https://www.orcarouter.ai/ref/ref_4c1cf5a5bb71174f474d) — 多模型网关（含 DeepSeek、千问等免费模型）。把 `OPENAI_BASE_URL` 设为 `https://api.orcarouter.ai/v1` 即可通过 Asterwynd 使用。
