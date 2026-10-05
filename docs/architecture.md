# 架构说明

本文档记录 Asterwynd 的系统架构。它描述当前仓库已经具备的主要模块，后续需要随代码演进持续校准。

## 核心循环

`AgentLoop` 是核心调度器，位于 `agent/loop.py`。

```text
messages -> LLM -> tool_calls -> execute tools -> append results -> repeat
```

核心原则：

- `messages` 是 AgentLoop 的主要状态。
- LLM 调用、工具执行、记忆压缩、生命周期扩展和轨迹记录通过独立模块协作。
- tool-call 消息链必须保持合法，assistant 的 tool call 必须对应 tool result。

## 插件系统

当前系统包含以下关键子系统：

| 模块 | 文件 | 职责 |
| --- | --- | --- |
| ToolRegistry | `agent/tools/registry.py` | 工具注册、schema 暴露、工具执行 |
| ToolGovernance | `agent/tools/governance/` | 动态 Top-K 工具选择（BM25 + embedding）+ 稳定核心层 + 质量软降级 |
| WorkspacePolicy | `agent/workspace_policy.py` | 工作区路径、文件和命令安全边界 |
| CommandGuard | `agent/tools/command_guard.py` | 命令语义护栏（绕过变体归一化 + 递归检查被包命令） |
| Sandbox | `agent/tools/sandbox/` | ProcessBackend + cgroup v2 / Docker 双后端，降级绝不静默 |
| HookManager | `agent/hooks/manager.py` | 生命周期扩展点 |
| MemoryManager | `agent/memory/manager.py` | 消息历史、token 阈值 AutoCompact、可插拔 Summarizer；四字段摘要（已完成事项/待办事项/疑难点与决策/当前进行中）、tool_call pending 标记、L1/L2 层级压缩、增量 token 计数 |
| ContextBuilder | `agent/context/` | 上下文注入管线：ASTER.md、记忆索引、技能、计划、待办等 ContextSource 统一编排；静态源缓存 + cache 感知分层注入（`build_blocks`，P0/P1/P2 稳定前缀） |
| PlanningManager | `agent/planning/` | 当前运行的结构化计划状态 |
| AgentRuntimeState | `agent/run_config.py` | 交互式 session 的当前 mode 和运行时 mode transition |
| McpManager | `agent/mcp/` | MCP server 连接、discovery、tools/prompts/resources 调用和本地权限包装 |
| SkillLoader / SkillRuntime | `agent/skills/` | 目录式 Markdown skill 加载、诊断、匹配、reload 和当前 run prompt 注入 |
| SubAgentManager | `agent/subagent/manager.py` | 子 session runtime 管理：子 session、多次 run、状态与 transcript inspect；并发队列 / 深度护栏 / 快照恢复 |
| WorkflowScheduler | `agent/subagent/scheduler.py` | 执行 Workflow DSL 编译出的 DAG：节点状态机、数据槽、四维预算闸门、树状分层汇聚、运行态图快照 |
| WorkflowStore | `agent/subagent/workflow_store.py` | 节点完整结果落盘（`result_ref`），内存只持 bounded summary |
| OrchestrationPatterns | `agent/subagent/patterns.py` | 4 个内置编排模式（orchestrator-worker / peer-review / hierarchical / bidding），编译为 DSL 模板 |
| TraceRecorder | `agent/trace_recorder.py` | 运行轨迹记录 |
| CostLedger | `agent/cost_tracker.py` | 成本账本：`by_session`/`by_phase`/`by_tool` + workflow 四维归因 `by_workflow`/`by_node`/`by_depth`/`by_edge` |
| ErrorClassifier | `agent/observability.py` | 结构化错误分类（4 类业务 + `unknown` 兜底） |
| SlashCommandRegistry | `agent/commands/` | 斜杠命令注册、分发和 `/init` 生成 ASTER.md |
| BrowserService | `agent/browser/` | 受控只读浏览器：导航、截图、内容提取、标签页管理，含安全策略约束 |

## 多 Agent 编排

`agent/subagent/` 提供声明式动态编排能力。模型通过 **Workflow DSL** 一次性声明协作拓扑，由统一调度器执行；`agent/subagent/patterns.py` 的 4 个内置模式只是编译到 DSL 模板的兼容层。

### Workflow DSL

- **分离式入口工具**：`DeclareWorkflow` 声明拓扑并返回 `workflow_id`，`StartWorkflow` 启动，`GetWorkflow` 查询 bounded 状态，`CancelWorkflow` 取消，`ReadWorkflowResult` 读取落盘结果；`RunWorkflow` 为便捷语法（内部走 Declare + Start）。`DryRunWorkflow` 不真跑即可预演图的路由与文本流向。`SaveWorkflowAsset`/`GetWorkflowAsset`/`ListWorkflowAssets`/`RunWorkflowAsset` 提供可复用的 workflow 资产。
- **4 种节点**：`subagent`（一个子 agent run）、`aggregate`（多上游汇聚）、`route`（按结构化结果选下一条边）、`foreach`（对有限集合动态展开并行）。
- **2 种汇合语义**：`all_required`（全部 required 上游完成才汇合）与 `best_effort`（等截止时间，消费已完成结果并保留失败记录）。「失败不 fail-fast」只在 aggregate 层实现。
- **schema 期校验**（`agent/subagent/workflow.py`）：节点类型 / 汇合语义 / 受限 reducer 枚举（`concat`/`merge_dict`/`first_non_empty`/`last`，不执行模型生成代码）；环上必须有 `route`（唯一能提供条件出口 + 上限的节点，否则是不可终止死循环）；多入边写同一结果槽必须声明 reducer，否则报 schema 错。
- **三闸结构上限**：图级步数 `recursion_limit`（默认 100）、节点数 `max_nodes`（默认 200）、run 总数 `max_runs`（默认 300）。

### 调度与预算

调度器（`agent/subagent/scheduler.py`）按数据依赖推进节点状态机，并施加 **workflow 级四维总预算**：`max_total_tokens` / `max_total_cost_usd` / `max_total_runs` / `max_wall_time_s`；任一维度超限即停止派发新节点、取消排队未执行的 run、drain 已启动的 run，并把根节点标记 `budget_exceeded`（返回 envelope，不向父 agent 抛未捕获异常）。四维默认值为不限（`0` = 该维度不限），但 `max_total_runs=0` **不**解除 `max_runs` 结构闸。

**树状分层汇聚**：模型可显式声明 aggregate 树（leaf→shard→domain→root）；单 aggregate 直接上游 >10 时，调度器自动插入分层 aggregate（逐层分组 `ceil(n / 10)` 直到顶层输入 ≤ 10），每层输出遵守 token 预算（leaf 300 / shard 800 / domain 1500 / root 3000，可配置）。

**父 agent 永远 bounded**：父只接收 bounded envelope（`workflow_id`/`status`/`completed`/`failed`/`pending`/`root_result_ref`），不默认展开子级详细结果；子级完整结果/transcript 落盘 workflow store，通过 `GetWorkflow` 的 detail 参数或 `InspectSubagentTranscript` 按需读取。

**成本归因**：`CostLedger` 在既有 `by_session`/`by_phase`/`by_tool` 三维之外，增 workflow 四维归因 `by_workflow`/`by_node`/`by_depth`/`by_edge`——每个 LLM 调用携带其 workflow_id / node_id / depth / edge 归因键，可回答「哪个节点最贵、哪层重复 token 最多、动态 vs 固定 pattern 差多少」。

### 运行态可视化

Web 端提供 workflow 运行态 DAG 实时图（`web/static/workflow_graph.js`）：scheduler 通过独立 `workflow_graph_snapshot()` 输出完整 nodes + edges + 每节点/每边 status（**不动**父 Agent 数据契约），经 session 级事件通道推送到 WebSocket；节点八档状态、边六档状态高亮，route 控制边单列，>720 桌面横向 DAG / <720 手机纵向 DAG，复用既有断点做 pinch 缩放 + pan 平移。

## 工具系统

内置工具位于 `agent/tools/builtin/`。

| 工具 | Capability / Risk | 作用 |
| --- | --- | --- |
| Read | workspace_read / low | 读取文件；无显式正 `limit` 时默认输出有界（2000 行或 128KB，先到者截），超出时返回带 `truncated=true` 与续读 offset 的 `[ReadProgress ...]` 注记；支持 `offset`/`limit` 分页 |
| ReadDoc | workspace_read / low | 按需读取深层 Markdown 文档（.md、32KB 上限） |
| Write | workspace_write / medium | 创建新文件，禁止覆盖已有文件 |
| Edit | workspace_write / medium | 精确文本替换 |
| Bash | command_execute / high | 执行命令并返回结构化 JSON |
| Grep | workspace_read / low | 正则搜索 |
| InspectGitDiff | workspace_read / low | 查看 git diff |
| ListFiles | workspace_read / low | 列出目录 |
| Find | workspace_read / low | 按 glob 查找文件 |
| RepoMap / SymbolSearch / LSP 工具 | workspace_read / low | 代码结构、符号和语义查询 |
| WebSearch / WebFetch | network_read / low | 搜索网页或抓取网页正文 |
| ActivateSkill | agent_state / medium | 在当前 run 内激活已加载 skill，使下一次 LLM 调用获得完整 skill prompt |
| 子 session 工具 | subagent_control / medium | 创建、运行、查询、取消和检查子 session |
| workflow 资产工具 | subagent_control / medium（`SaveWorkflowAsset` 为 agent_state / medium） | `SaveWorkflowAsset` / `ListWorkflowAssets` / `GetWorkflowAsset` / `RunWorkflowAsset`：把跑过的图沉淀为命名资产并按名复用；`RunWorkflowAsset` 属 spawn 类，进深度闸 |
| UpdatePlan / ExitPlanMode | agent_state / medium，plan-only | 更新或定稿 Plan Document，并将高层步骤同步为 planning state |
| BrowserNavigate / BrowserScreenshot / BrowserGetContent / BrowserScroll / BrowserTabs | browser_read / low | 受控只读浏览器操作，含 URL/域白名单和敏感数据遮蔽 |

`ToolPermission` 将 capability、risk level 和 origin 分开记录；`read_only`、`dangerous` 仍作为 legacy compatibility flag 保留。`ModePolicy` 通过 permission profile 产生 `allow`、`deny` 或 `require_approval` 三值判定。默认 `build_default` 会直接允许 low/medium 风险工具，高风险工具需要审批；无人值守入口使用 fail-closed approval handler。BashTool 返回结构化 JSON，包含 `exit_code`、`stdout`、`stderr`、`duration_ms` 和 `timed_out`。WorkspacePolicy 负责命令 allowlist / denylist 和敏感路径限制，不能被 capability metadata 绕过。

`RepoMap` 和 `SymbolSearch` 属于当前轻量 code intelligence 能力：它们复用 WorkspacePolicy、忽略规则和只读工具边界，使用文件扫描、Python AST 和 tree-sitter 提取仓库结构和符号摘要。Tree-sitter 首批覆盖 TypeScript/JavaScript、Go 和 Rust；Python 继续使用 AST extractor。

LSP 工具（`LspDefinition`、`LspReferences`、`LspHover`、`LspDocumentSymbols`、`LspWorkspaceSymbols`、`LspDiagnostics`）提供更丰富的语义代码理解能力，通过 `agent/lsp/` 模块管理 stdio LSP server 进程并按 (language, workspace_root) 缓存单例。Write/Edit 工具修改文件后会自动触发 LSP 诊断反馈。配置入口为 `tools.code_intelligence.lsp`。首版只支持 Python（需安装 `python-lsp-server`，可通过 `pip install asterwynd[lsp]` 或 `uv sync --extra lsp` 安装）；其他语言可在 `asterwynd.yaml` 中配置对应 server，但尚未官方验证。

### MCP integration

`agent/mcp/` 使用官方 Python MCP SDK 连接 MCP server。配置入口为顶层 `mcp.servers`，首版支持 `stdio` 和 `streamable_http` transport；Streamable HTTP 支持无认证或静态 headers / env headers，不内置 OAuth 流程。

MCP tools 会包装为 `McpTool` 并注册到 ToolRegistry，模型可见名为 `mcp__<server>__<tool>`，内部仍保留原始 `(server, tool)` 用于 `tools/call`。Prompts 和 resources 不自动注册为工具；CLI/Web 通过 `/mcp`、`/mcp-prompt` 和 `/mcp-resource` 显式查看或读取，并以带来源标记的 system context 注入当前会话。

MCP action 默认权限为 `origin=mcp`、`external_side_effect`、`high`，因此默认 build mode 需要审批；只有本地配置可以将指定 server/tool/prompt/resource 降为 `network_read` 或其他低风险 capability。MCP server 自身 annotation 只作为外部提示，不参与最终权限判定。

### WebSearch provider adapter

`WebSearch` 通过 `SearchProviderRegistry` 调用搜索 provider adapter。provider 优先级来自 `asterwynd.yaml` 的 `tools.web_search.providers`；未配置时使用保守默认 `duckduckgo-html`。环境变量只提供 provider 凭据和端点，例如 `ASTERWYND_TAVILY_API_KEY`、`ASTERWYND_BRAVE_SEARCH_API_KEY` 和 `ASTERWYND_SEARXNG_BASE_URL`，不参与 provider 排序。

每个 provider 返回统一的 provider response object，包含最终 provider、结果和诊断信息。网络失败、超时、5xx、429、解析失败、缺 key 或缺 base URL 可以 fallback；搜索成功但无结果默认不 fallback。CI 测试只使用 fake provider、fixture 和 `httpx.MockTransport`，真实 provider smoke 需要显式环境变量并手动执行。`WebFetch` 会对非 2xx、非文本内容、请求失败和截断结果返回可读诊断。

## Web UI

Web UI 位于 `web/`，使用 FastAPI、WebSocket 和原生前端实现。

- `web/server.py`: FastAPI app、WebSocket endpoint、静态文件服务。
- `web/session.py`: 会话管理，每个 session 维护一组消息和 AgentLoop。
- `web/debug_hook.py`: DebugHook，捕获每轮 LLM 输入输出、工具调用和错误/完成事件；Memory compact 事件由 AgentLoop 通过 Web session 的 `on_event("memory_compaction", ...)` 发送，payload 含 before/after messages·tokens 与压缩层级元数据。
- `web/static/`: Chat、Debug 与 Workflow 页面前端资源。

Web UI 当前包含 Hub、Chat、Workflow 和 Debug 四个视图。Debug 视图通过 `ASTERWYND_DEBUG=enabled` 开启。Hub 视图按 workspace 组织已保存会话，workspace 选择器列出主 workspace（启动目录或 `--workspace`）与配置 `web.workspaces` allowlist；`Workspace → +` 可新增任意绝对路径（不存在则创建目录），新路径写入 `<配置目录>/.asterwynd/workspaces.yaml` 并在同进程内立即生效，不修改用户手写的 `asterwynd.yaml`。Chat 视图展示当前 session id、最近一次 run id、当前 session mode、Plan Document、planning state、assistant Markdown 正文和工具执行行；用户可以在同一 session 内切换 `build` / `read_only` / `plan` / `bypass`。对话区是 **harness 式 transcript**：正文是单列定宽文档流（user 轮为整列宽输入块 + 角色标签，assistant 无气泡），**每次工具执行只占一行**（默认折叠，点开才见缩进参数与完整结果；失败在折叠行上就可见且不自动展开）。工具执行行的渲染口径集中在 `web/static/tool_rows.js`（`window.AsterwyndToolRows`），由对话区与工作流节点详情抽屉的「对话」tab 共用；摘要生成是 DOM 无关的纯函数，由 `tests/web_tests/test_transcript_js.py` 用 node 直接单测。`tool_call` / `tool_result` 事件不带调用 id，配对按到达顺序 FIFO（同名优先），run 结束时收尾未配对行。当工具调用需要审批时，服务端发送 `approval_request` 事件，前端展示脱敏参数摘要并回传批准或拒绝；每个 Web session 同一时刻只允许一个 pending approval。工具结果事件带 display metadata 与 `tool_call_id`（**不含完整正文**）：折叠行只用它的字符数/行数做行尾元数据、用 `preview` 做**判定与摘要的文本依据**（失败首行、结构化 `exit_code`），不把 preview 当正文铺进对话流；用户展开时按该 id 向服务端按需取回全文（服务端从会话消息或已落盘的 artifact 读回）并在展开体里展示，收起时释放缓存——避免长结果全文无条件经过 WebSocket 进入浏览器。支持 streaming 的 provider 会通过 `assistant_delta` 事件实时更新 assistant 正文，最终 `llm_response(streamed=true)` 只作为完整响应事件，不重复展示文本；非 streaming provider 仍展示整段 `llm_response.content`。`session_history` 载荷额外携带 `tool_call_id` 与 assistant 消息的 `tool_calls`（仅 id/name），供前端把重连后的历史工具行还原成带工具名的折叠行。

Web session 的 run 事件出口是 **session 级、与单条 WebSocket 连接解耦**的（`AgentSession.event_channel`）：浏览器断开（移动端切后台/锁屏）只解绑该连接，不会终止正在执行的 run，也不会把 pending 审批/提问判定为失败。重连命中同一内存 session 时，服务端按 `session_resumed → session_history → pending 卡片补发 → workflow 快照` 的顺序推送，把仍处于 pending 的 `approval_request` / `user_question` 卡片补发回前端（已作答/已超时/已取消的请求不补发）。同一 session 存在多条连接（多 tab / 多设备）时 run 事件广播给全部连接，作答采用「先答者胜」，终态广播回所有连接。

pending 交互有显式超时，由 `WebConfig.question_timeout_seconds`（缺省 300 秒）与 `WebConfig.approval_timeout_seconds`（缺省 600 秒）配置，语义是**总等待时长**：从 pending 建立时开始计时，连接断开与保持都不影响计时。提问超时返回 `[Error: ...]` 答复；审批超时按 fail-closed 判定为 `unavailable`（绝不放行不可逆操作），AgentLoop 继续运行而不是永久挂起。`reset` / `cancel` 与 run 真正结束仍立即失败 pending。注意 `{"type":"cancel"}` 只失败 pending 交互、**不停止 workflow run**；真正停图走 `{"type":"cancel_workflow"}`。

### Workflow 视图

Workflow 视图在模型触发多 Agent 流程时自动打开（`workflow_started` 事件），由 scheduler 的 `workflow_graph_snapshot()` 经 session 级 forwarder 推送到前端。桌面（>720px）显示横向 DAG、手机（≤720px）纵向 DAG，同一份 DOM 按 720 断点切 class；分层布局 / 状态映射 / 折叠归类是 `web/static/workflow_graph.js` 里的纯函数，由 node + vm 单测与 Playwright 浏览器 smoke 双层覆盖。

- **节点状态八档**：`pending` / `started` / `completed` / `failed` / `cancelled` / `blocked` / `budget_exceeded` / `skipped`（未选中：route 判定没走这条分支）。前七档分色 + 形状/角标编码（不只靠颜色，Airflow 的 `failed`/`upstream_failed` 在绿色盲下几乎同色是该坑的反面教材），`skipped` 与 `blocked` 刻意拉开明度差。
- **投影层 `queued`**：scheduler 不把 `queued` 写进 `NodeState.status`（那个值参与收敛判断），而是在 `_graph_node_projection` 里按 run record 的 `status` 派生——所以图上能区分「真正在跑」与「已派发、在等执行 slot」。
- **图级终态四档**（按实际执行结果，优先级即语义）：`completed_with_failures`（跑了但有节点失败）/ `completed`（跑了且全成功）/ `failed`（零节点成功且有节点失败）/ `stalled`（零节点成功且零节点失败——图根本没跑起来：入口互等 / 全被挡）。`stalled` 与 `failed` 分开是因为二者对用户的行动指引不同（前者指向「为什么一个都没跑」，后者指向「哪个节点失败了」）；`budget_exceeded` / `cancelled` / `graph_recursion_exceeded` 优先于这四档。**`completed` 不再覆盖「零节点成功」的收敛**：图说「完成」而实际什么都没跑会让用户不去排查，并让外部消费方把「图根本没跑起来」判为通过（`stalled` 对消费方的语义是**非成功**）。终态集合必须同时出现在**三个副本**——scheduler 的 `_SNAPSHOT_TERMINAL_STATUSES`、前端 `workflow.js` 的 `TERMINAL_STATUSES`、`workflow_graph.js` 的 `isGraphTerminal()`，否则那张图会被当成 running、永不进 tab 淘汰池、每次重连都补发。
- **节点因由如实**：`blocked` 节点的因由按真实成因分档——图级闸门触发（穿透 `diagnostics`，含闸门名与上限值）/ 入边互相等待（无闸门时说明结构性原因）/ 兜底。前端 `explainNode()` 让携带具体成因的 `node.reason` 优先于泛化的「流程因图超限被停止」，否则后端写了真因、用户仍看不到。
- **回边重跑不清空发起者**：数据边回边（如 `body → cycle_gate`）会让子树复位递归走回发起者自己、清掉刚写的 `status`/`targets`。`_reset_subtree(origin=...)` 豁免发起者一个节点（**不**停止传播——环上其它节点仍按 G11 语义重跑）；配套地 `_is_skipped` 用控制源的 `targets` 而非 `activations` 判「是否被选中」，因为后者会被复位清零，会把「选过、也跑过」的节点误报成 `route did not select this branch`。
- **只读下钻**：`GET /api/sessions/{session_id}/workflows/{workflow_id}/nodes/{node_id}/transcript` 按节点类型返回三态 union（`single` / `candidates` / `none`），复用 `SubAgentManager.inspect_transcript()`，bounded 且不调 LLM、不写盘、不改执行状态。session 校验是**内存口径**（与 `/api/sessions/{id}/timeline` 同），冷会话/进程重启后 404。
- **失败证据投影**：同一载荷另带 `failure_evidence`（`state` / `total` / `truncated` / `message` / `items`），数据源是该 run 已经写入的 `run.trace.steps` 中 `status != "ok"` 的 `tool_result` 与全部 `llm_error`——**只读投影，不新增采集**（issue #215：这些信号此前在用户面零出口，一个 `completed` 的绿节点可以内部失败多次而不露痕迹）。`state` 是七值枚举 `present` / `clean` / `running` / `empty_trace` / `no_trace` / `unavailable` / `not_applicable`，其中 `clean`（走完 trace 且零失败）是**正向声明**，与「没有 trace」严格分开——所有负向态都带可读原因文案，不返回空列表了事。bounded：只回最近 `FAILURE_EVIDENCE_LIMIT` 条、单条文本截到 `TRANSCRIPT_CONTENT_LIMIT` 并置 `text_truncated`。容器形态（`candidates`）每候选只带**轻量**证据（≤1 条 × 400 字符），完整证据在下钻与 `single` 形态给。前端证据正文在「对话」tab（沿用懒加载不变），「任务」tab 另有一行来自快照的零请求线索（节点 `failure_count` 三态：`null` 不显示 / `0` 已检查无失败 / `N` 次失败）。
- **对话 tab 的取数时机**：切到「对话」才请求（懒加载），运行中按 `TRANSCRIPT_REFRESH_S`（10s）节律重取；节点到终态即停轮询，但**若手上这一帧取自终态之前则补取一次**（`transcriptRefreshDue` 的 `fetchedStatus` 判据，change `fix-node-transcript-stale-refresh`）——否则运行期抓到的那一帧会被永久缓存：跑完后对话停在半途，同一 run 的失败证据也一并看不到（用户实测缺陷）。**暂停优先于补取**（暂停期间连终态补取也不发生），点「继续实时更新」时若补取条件成立则立即取一次（「继续」= 现在就跟上，不等下一个节律 tick）；另提供「刷新」（清该节点缓存重取，不受暂停影响）。前端按 50 行一簇做虚拟化。
- **控制面**：`{"type":"cancel_workflow"}` 经 WebSocket 取消一张运行中的图；`reset` 在替换会话前会先取消该会话内所有在跑的图（否则图继续烧预算而用户已看不到它——forwarder 已 detach）。

## Skills

Skill 使用目录格式：`skills/<name>/SKILL.md`。`SkillLoader` 解析 frontmatter 和正文，`SkillRuntime` 按配置的 skill roots 加载并保留诊断；配置文件所在目录的 `skills/` 总是先加载，`skills.roots` 中的路径作为追加 roots，重复名称按“先加载者生效”处理。

每次 Agent run 都会向模型注入简短 skill index，包含用户可调用 skill 的名称、描述和 `/skill-name <args>` 调用方式。完整 skill prompt 只在三种情况下进入当前 run context：`always: true`、本地 name/description/triggers 匹配当前用户输入、或通过 slash command / `ActivateSkill` 显式激活。注入内容不会写回 conversation memory。

CLI 和 Web 复用 central slash command registry。`/skills` 展示当前加载结果，`/skills reload` 重新加载 configured roots；`/skill-name args` 会先 queue skill activation，再以 `args` 作为用户消息启动 Agent run，原始 slash command 不进入 LLM 普通消息。MCP 控制命令 `/mcp`、`/mcp-prompt` 和 `/mcp-resource` 不直接启动 Agent run；prompt/resource 结果以带来源标记的 system context 注入当前会话。

## Benchmark

Benchmark 目标是用可复现任务评测 coding-agent 能力。`benchmarks/` 是项目内置 runner，覆盖本地 worktree 任务和 `swebench-*` 外部任务。

核心流程：

1. 根据 task 定义准备工作区。
2. 运行指定 agent。
3. 保存 trace、runner log 和 result；在 agent diff capture 完成后保存 final diff。
4. 应用 hidden test patch。
5. 运行验证命令。
6. 在验证命令实际运行后保存 test output，并汇总 run-level 报告。

内置 runner 的本地任务和外部 SWE-bench 风格任务都通过统一 runner 执行。`--workflow-mode` 三模式（`template` / `dynamic-record` / `dynamic-replay`）让 benchmark 直接测「编排本身」的质量，报告新增独立的 workflow 编排 section。

## LLM Provider

LLM 抽象位于 `agent/llm.py`。当前包含 OpenAI-compatible 和 Anthropic-compatible provider。

Anthropic / DeepSeek 兼容路径需要注意：

- 连续 tool result 需要合并为一个 user 消息中的多个 `tool_result` block。
- assistant 消息中 text block 必须在 tool_use block 前。
- provider 专有字段需要保守保留，避免后续请求丢字段。

## 扩展方式

- 新工具：继承 Tool，使用 `@tool_parameters` 声明 schema，注册到 ToolRegistry。
- 新 Hook：实现 Hook Protocol，加入 HookManager。
- 新 Skill：在 `skills/<name>/SKILL.md` 中创建目录式 Markdown skill，并按需配置 `triggers`、`argument_hint` 和 `user_invocable`。
- 新 LLM provider：实现 LLM Protocol。
