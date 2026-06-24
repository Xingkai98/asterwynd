# 架构说明

本文档记录 MyAgent 的系统架构。它描述当前仓库已经具备的主要模块，后续需要随代码演进持续校准。

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
| SkillLoader | `agent/skills/loader.py` | Markdown skill 加载 |
| SubAgentManager | `agent/subagent/manager.py` | 后台子 agent 委托 |
| TraceRecorder | `agent/trace_recorder.py` | 运行轨迹记录 |

## 工具系统

内置工具位于 `agent/tools/builtin/`。

| 工具 | 权限 | 作用 |
| --- | --- | --- |
| Read | read_only | 读取文件 |
| Write | read_write | 创建新文件，禁止覆盖已有文件 |
| Edit | read_write | 精确文本替换 |
| Bash | dangerous | 执行命令并返回结构化 JSON |
| Grep | read_only | 正则搜索 |
| InspectGitDiff | read_only | 查看 git diff |
| ListFiles | read_only | 列出目录 |
| Find | read_only | 按 glob 查找文件 |
| RepoMap | read_only | 生成仓库结构和已支持语言的顶层符号摘要 |
| SymbolSearch | read_only | 按名称搜索已支持语言的符号 |
| WebSearch | read_only | 网络搜索，当前默认 DuckDuckGo HTML provider |
| WebFetch | read_only | 抓取网页正文并返回状态/类型/截断诊断 |
| UpdatePlan | plan-only | 更新 Plan Document 草案，并将高层步骤同步为 planning state |
| ExitPlanMode | plan-only | 定稿 Plan Document，并将高层步骤同步为 planning state |

BashTool 返回结构化 JSON，包含 `exit_code`、`stdout`、`stderr`、`duration_ms` 和 `timed_out`。WorkspacePolicy 负责命令 allowlist / denylist 和敏感路径限制。

`RepoMap` 和 `SymbolSearch` 属于当前轻量 code intelligence 能力：它们复用 WorkspacePolicy、忽略规则和只读工具边界，使用文件扫描、Python AST 和 tree-sitter 提取仓库结构和符号摘要。Tree-sitter 首批覆盖 TypeScript/JavaScript、Go 和 Rust；Python 继续使用 AST extractor。LSP、引用分析、诊断和类型推断仍是后续能力。

### WebSearch provider adapter

`WebSearch` 通过 `SearchProviderRegistry` 调用搜索 provider adapter。provider 优先级来自 `myagent.yaml` 的 `tools.web_search.providers`；未配置时使用保守默认 `duckduckgo-html`。环境变量只提供 provider 凭据和端点，例如 `MYAGENT_TAVILY_API_KEY`、`MYAGENT_BRAVE_SEARCH_API_KEY` 和 `MYAGENT_SEARXNG_BASE_URL`，不参与 provider 排序。

每个 provider 返回统一的 provider response object，包含最终 provider、结果和诊断信息。网络失败、超时、5xx、429、解析失败、缺 key 或缺 base URL 可以 fallback；搜索成功但无结果默认不 fallback。CI 测试只使用 fake provider、fixture 和 `httpx.MockTransport`，真实 provider smoke 需要显式环境变量并手动执行。`WebFetch` 会对非 2xx、非文本内容、请求失败和截断结果返回可读诊断。

## Web UI

Web UI 位于 `web/`，使用 FastAPI、WebSocket 和原生前端实现。

- `web/server.py`: FastAPI app、WebSocket endpoint、静态文件服务。
- `web/session.py`: 会话管理，每个 session 维护一组消息和 AgentLoop。
- `web/debug_hook.py`: DebugHook，捕获每轮 LLM 输入输出、工具调用和错误/完成事件；Memory compact 事件由 AgentLoop 通过 Web session 的 `on_event("memory_compaction", ...)` 发送。
- `web/static/`: Chat 与 Debug 页面前端资源。

Web UI 当前包含 Chat 和 Debug 两个视图。Debug 视图通过 `MYAGENT_DEBUG=enabled` 开启。Chat 视图展示当前 session id、最近一次 run id、Plan Document、planning state、assistant Markdown 和工具调用过程；工具结果事件会带 display metadata，前端按配置折叠长结果并保留可展开全文。支持 streaming 的 provider 会通过 `assistant_delta` 事件实时更新 assistant 气泡，最终 `llm_response(streamed=true)` 只作为完整响应事件，不重复展示文本；非 streaming provider 仍展示整段 `llm_response.content`。

## Benchmark

Benchmark 模块位于 `benchmarks/`，目标是用可复现任务评测 coding-agent 能力。

核心流程：

1. 根据 task 定义准备工作区。
2. 运行指定 agent。
3. 保存 trace、runner log 和 result；在 agent diff capture 完成后保存 final diff。
4. 应用 hidden test patch。
5. 运行验证命令。
6. 在验证命令实际运行后保存 test output，并汇总 run-level 报告。

内部任务和外部 SWE-bench 风格任务都通过统一 runner 执行。当前任务数量和文档口径需要后续统一校准。

## LLM Provider

LLM 抽象位于 `agent/llm.py`。当前包含 OpenAI-compatible 和 Anthropic-compatible provider。

Anthropic / DeepSeek 兼容路径需要注意：

- 连续 tool result 需要合并为一个 user 消息中的多个 `tool_result` block。
- assistant 消息中 text block 必须在 tool_use block 前。
- provider 专有字段需要保守保留，避免后续请求丢字段。

## 扩展方式

- 新工具：继承 Tool，使用 `@tool_parameters` 声明 schema，注册到 ToolRegistry。
- 新 Hook：实现 Hook Protocol，加入 HookManager。
- 新 Skill：在 `skills/` 下创建 Markdown 文件。
- 新 LLM provider：实现 LLM Protocol。
