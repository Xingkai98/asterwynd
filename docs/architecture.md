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
| WorkspacePolicy | `agent/workspace_policy.py` | 工作区路径、文件和命令安全边界 |
| HookManager | `agent/hooks/manager.py` | 生命周期扩展点 |
| MemoryManager | `agent/memory/manager.py` | 消息历史与 AutoCompact |
| PlanningManager | `agent/planning/` | 当前运行的结构化计划状态 |
| AgentRuntimeState | `agent/run_config.py` | 交互式 session 的当前 mode 和运行时 mode transition |
| McpManager | `agent/mcp/` | MCP server 连接、discovery、tools/prompts/resources 调用和本地权限包装 |
| SkillLoader / SkillRuntime | `agent/skills/` | 目录式 Markdown skill 加载、诊断、匹配、reload 和当前 run prompt 注入 |
| SubAgentManager | `agent/subagent/manager.py` | 子 session runtime 管理：子 session、多次 run、状态与 transcript inspect |
| TraceRecorder | `agent/trace_recorder.py` | 运行轨迹记录 |

## 工具系统

内置工具位于 `agent/tools/builtin/`。

| 工具 | Capability / Risk | 作用 |
| --- | --- | --- |
| Read | workspace_read / low | 读取文件 |
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
| UpdatePlan / ExitPlanMode | agent_state / medium，plan-only | 更新或定稿 Plan Document，并将高层步骤同步为 planning state |

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
- `web/debug_hook.py`: DebugHook，捕获每轮 LLM 输入输出、工具调用和错误/完成事件；Memory compact 事件由 AgentLoop 通过 Web session 的 `on_event("memory_compaction", ...)` 发送。
- `web/static/`: Chat 与 Debug 页面前端资源。

Web UI 当前包含 Chat 和 Debug 两个视图。Debug 视图通过 `ASTERWYND_DEBUG=enabled` 开启。Chat 视图展示当前 session id、最近一次 run id、当前 session mode、Plan Document、planning state、assistant Markdown 和工具调用过程；用户可以在同一 session 内切换 `build` / `read_only` / `plan`。当工具调用需要审批时，服务端发送 `approval_request` 事件，前端展示脱敏参数摘要并回传批准或拒绝；每个 Web session 同一时刻只允许一个 pending approval。工具结果事件会带 display metadata，前端按配置折叠长结果并保留可展开全文。支持 streaming 的 provider 会通过 `assistant_delta` 事件实时更新 assistant 气泡，最终 `llm_response(streamed=true)` 只作为完整响应事件，不重复展示文本；非 streaming provider 仍展示整段 `llm_response.content`。

## Skills

Skill 使用目录格式：`skills/<name>/SKILL.md`。`SkillLoader` 解析 frontmatter 和正文，`SkillRuntime` 按配置的 skill roots 加载并保留诊断；配置文件所在目录的 `skills/` 总是先加载，`skills.roots` 中的路径作为追加 roots，重复名称按“先加载者生效”处理。

每次 Agent run 都会向模型注入简短 skill index，包含用户可调用 skill 的名称、描述和 `/skill-name <args>` 调用方式。完整 skill prompt 只在三种情况下进入当前 run context：`always: true`、本地 name/description/triggers 匹配当前用户输入、或通过 slash command / `ActivateSkill` 显式激活。注入内容不会写回 conversation memory。

CLI 和 Web 复用 central slash command registry。`/skills` 展示当前加载结果，`/skills reload` 重新加载 configured roots；`/skill-name args` 会先 queue skill activation，再以 `args` 作为用户消息启动 Agent run，原始 slash command 不进入 LLM 普通消息。MCP 控制命令 `/mcp`、`/mcp-prompt` 和 `/mcp-resource` 不直接启动 Agent run；prompt/resource 结果以带来源标记的 system context 注入当前会话。

## Benchmark

Benchmark 目标是用可复现任务评测 coding-agent 能力。当前有两条路径：

- `benchmarks/`：项目内置 runner，覆盖本地 worktree 任务和少量 `swebench-*` 外部任务。
- `claw-swe-bench/`：Claw-SWE-Bench 统一 harness 副本，用 SWE-bench Verified 实例对比 Asterwynd、Aider、OpenCode 等 agent。

核心流程：

1. 根据 task 定义准备工作区。
2. 运行指定 agent。
3. 保存 trace、runner log 和 result；在 agent diff capture 完成后保存 final diff。
4. 应用 hidden test patch。
5. 运行验证命令。
6. 在验证命令实际运行后保存 test output，并汇总 run-level 报告。

内置 runner 的本地任务和外部 SWE-bench 风格任务都通过统一 runner 执行。Claw-SWE-Bench 路径则复用其 orchestrator、workspace、patch collection 和 eval flow；Asterwynd adapter 通过 `agent/claw_solve.py` 在目标容器内运行 headless solver。

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
