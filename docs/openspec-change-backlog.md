# OpenSpec Change 实现队列

本文档记录当前 active OpenSpec changes 中尚未实现的需求，并按建议实现顺序排列。它不是规格本身；每个 change 的 source of truth 仍是 `openspec/changes/<change-id>/` 下的 proposal、design、specs 和 tasks。

维护规则：

- 新增 OpenSpec change 后，如果不是纯占位，应把它加入本队列。
- change 实现并 PR 合入后，必须直接归档到 `openspec/changes/archive/YYYY-MM-DD-<change-id>/` 并从本文档移除；如果暂时无法归档，才移到“已完成待归档”。
- change 状态变化时，必须同步更新“并行开发批次”和“未实现队列”两个章节，避免批次章节保留过期状态。
- 调整实现顺序时，应写清楚依赖原因，而不是只移动条目。
- 本文档只记录可提交的 change id 和稳定判断，不记录本地参考仓库路径。

## 并行开发批次

后续 change 不应全部串行，也不应全量并行。建议按以下批次推进；同一批次内可以并行开 PR，但如果两个 change 同时修改 AgentLoop、ToolRegistry、Web session 或 trace 语义，应在实现阶段错开合入，避免协议和事件模型互相覆盖。

### 第一批：已完成

- `add-repo-map-code-intelligence`：已合入并归档。
- `implement-structured-planning-state`：已合入并归档。
- `add-tool-result-display-controls`：已合入并归档。
- `harden-web-research-tools`：已合入并归档。
- `render-markdown-in-chat-surfaces`：已合入并归档。

### 第二批：可立即并行的低耦合基础能力

- `add-search-provider-adapter-architecture`：搜索 provider 架构增强，基于已合入的 `harden-web-research-tools` 单 provider 边界，先调研再实现多 provider、优先级和 fallback。
- `add-tree-sitter-symbol-extraction`：`add-repo-map-code-intelligence` 已合入，可复用 repo scanner、extractor 接口、repo map 输出和只读工具。
- `add-plan-mode`：planning state 已合入，可开始真实 plan mode；与 streaming / mode switching 都会碰 AgentLoop，合入阶段需要错开。

### 第三批：运行时交互协议，建议串行合入

- `add-streaming-agent-output`：先统一 AgentLoop streaming event，Web / CLI / 未来 TUI 后续都复用这条事件通道。
- `add-runtime-mode-switching`：可在 session id 和 streaming event 语义稳定后做；如果提前推进，应限定为 mode transition API、Web/CLI 入口和当前 mode 语义。
- `upgrade-subagents-to-agentloop`：planning state 已合入；建议在 streaming / mode switching 的事件语义稳定后推进，便于 parent channel 和 trace 复用。

### 第四批：语义 code intelligence 与 TUI

- `add-lsp-code-intelligence`：等待 repo map 基础设施稳定，建议在 tree-sitter 多语言 symbol 之后推进，避免直接把 LSP 当成仓库结构层。
- `add-minimal-tui-runtime-view`：建议在 planning state、streaming、runtime mode switching 和工具结果 display policy 稳定后做，复用统一运行事件和 mode transition。

### 第五批：外部工具与高风险能力

- `add-mcp-tool-adapter`：可提前做设计和 fake server 测试，但实现会碰 ToolRegistry 权限元数据，建议与 browser 能力错开合入。
- `add-browser-use-safety-foundation`：风险高于 MCP，应在配置、mode policy、workspace safety 和工具权限模型稳定后做。

## 未实现队列

### 1. `add-search-provider-adapter-architecture`

状态：未实现。

批次：第二批，建议在 `harden-web-research-tools` 合入后开始；必须先做 provider 调研和设计确认。

建议顺序原因：

- 已合入的 `harden-web-research-tools` 只硬化当前 DuckDuckGo HTML 路径并拆出单 provider 边界；完整 provider registry、优先级和 fallback 应作为独立能力设计。
- 搜索 provider 选择会引入鉴权、成本、速率限制、fallback 和结果字段差异，不应混入 research tools hardening。

主要交付：

- 搜索 provider 调研结论。
- provider protocol、capability metadata 和错误模型。
- provider registry / factory 与配置优先级。
- 多 provider fallback diagnostics。
- 至少两个 provider adapter 和 fixture 测试。

### 2. `add-tree-sitter-symbol-extraction`

状态：未实现。

批次：第二批，`add-repo-map-code-intelligence` 已合入，可开始。

建议顺序原因：

- tree-sitter 应复用第一阶段的 repo scanner、extractor 接口、WorkspacePolicy 约束和 repo map 输出格式。
- 这是 LSP 之前的多语言语法级 symbol 能力，不应和第一阶段 Python AST 证明点捆绑。

主要交付：

- tree-sitter parser / grammar registry。
- per-language query registry。
- 多语言 symbol extraction。
- 未注册语言和解析失败降级。
- 多语言 fixture 与 benchmark smoke。

### 3. `add-plan-mode`

状态：未实现。

批次：第二批，planning state 已合入，可开始；与 streaming / mode switching 同改 AgentLoop，合入阶段需要错开。

建议顺序原因：

- 依赖 `introduce-agent-mode-policy` 的 mode 权限边界。
- 依赖已合入的 `implement-structured-planning-state` 结构化计划产物。
- 完成后，`plan` 才从“只读权限模式”升级为“可观察、可验证的计划模式”。

主要交付：

- plan mode 的真实行为。
- plan mode 只暴露只读工具，拒绝写入和 dangerous 工具。
- AgentLoop 在 plan mode 中产出结构化 planning state 和自然语言计划说明。
- CLI/Web 启动 plan mode。

### 4. `add-streaming-agent-output`

状态：未实现。

批次：第三批，建议在 session/run id 可观察性之后推进；与 runtime mode switching 串行合入。

建议顺序原因：

- 现有 provider 层已有部分 SSE 能力，但 AgentLoop / Web / CLI 仍是整段响应后展示。
- streaming 会重塑运行事件语义，后续 TUI 和 mode switching 都应复用这条稳定事件通道。

主要交付：

- LLM streaming protocol 或 stream path。
- AgentLoop assistant text delta 事件。
- WebSocket / CLI 实时输出。
- 非 streaming provider fallback。
- 为未来 TUI 暴露 streaming event。

### 5. `add-runtime-mode-switching`

状态：未实现。

批次：第三批，建议在 session id 和 streaming event 语义稳定后推进；如需提前，只先做 mode transition API 和当前 mode 语义。

建议顺序原因：

- 当前 mode 在 session 内不可变；该 change 负责让 CLI/Web/未来 TUI 中的 mode 修改实时生效。
- 与 streaming 同样触碰 AgentLoop、WebSocket、CLI event 和 trace，不能和 streaming 同时无序合入。

主要交付：

- session runtime state 或等价状态对象。
- 统一 mode transition API。
- ToolRegistry schema / execute 读取最新 mode。
- `mode_changed` 事件、trace 记录、CLI 交互命令、WebSocket 切换消息。
- 为未来 TUI 暴露复用接口。

### 6. `upgrade-subagents-to-agentloop`

状态：未实现。

批次：第三批，planning state 已合入；建议等待 streaming / mode switching 事件语义稳定后推进。

建议顺序原因：

- 子 agent 升级为受限 AgentLoop 需要稳定的 mode policy、planning state、trace 和 ParentChannel 语义。
- 放在 streaming / mode switching 后，可以复用已经稳定的运行事件和展示/调试模型；如果优先级转向并行调查能力，也可以提前到 TUI 之前。

主要交付：

- SubAgentManager 创建受限 AgentLoop。
- 子 agent 独立 messages、tools、memory、mode 和 trace。
- ParentChannel 回传完成、失败、取消和摘要。
- 取消逻辑能停止子 AgentLoop。

### 7. `add-lsp-code-intelligence`

状态：未实现。

批次：第四批，repo map 基础设施已合入；建议在 `add-tree-sitter-symbol-extraction` 后推进。

建议顺序原因：

- LSP 提供 definition、references、hover、diagnostics 等语义能力，但需要 language server 配置、进程生命周期、文档同步和超时/错误处理。
- 先完成 repo map 和 tree-sitter，可以让 LSP 作为更强 provider 接入，而不是承担仓库结构发现职责。

主要交付：

- LSP server 配置、发现和生命周期管理。
- document open/sync、请求调度、超时和状态观测。
- 只读 LSP 工具或 provider。
- definition、references、hover、documentSymbol、workspaceSymbol 和 diagnostics。
- 修改后 diagnostics 反馈。

### 8. `add-minimal-tui-runtime-view`

状态：未实现。

批次：第四批，等待 planning state、streaming、runtime mode switching 和工具结果 display policy 稳定后开始。

建议顺序原因：

- TUI 应复用已有 AgentLoop 事件、planning state、streaming、工具结果 display policy 和 mode transition，而不是定义另一套运行协议。
- 放在这些基础能力之后，可以一次展示稳定的运行状态、工具调用、planning state、streaming 输出和 mode 状态。

主要交付：

- TUI 命令入口。
- AgentLoop 事件流消费。
- 对话、工具调用、planning state、最终回复、diff/test 摘要和 trace 路径展示。
- 非交互环境 graceful failure 或降级。

### 9. `add-mcp-tool-adapter`

状态：未实现。

批次：第五批，可提前做设计和 fake server 测试；实现阶段建议与 browser 能力错开。

建议顺序原因：

- MCP 需要统一配置管理 server 列表，也需要 mode policy 和 tool permission metadata。
- 放在核心本地工具、planning、runtime event 和 subagent 语义稳定之后，可以降低外部工具协议引入的复杂度。

主要交付：

- MCP server 配置和连接管理。
- fake MCP server discovery 测试。
- MCP schema 映射为 ToolRegistry schema。
- MCP tool 执行、错误、超时和权限元数据。

### 10. `add-browser-use-safety-foundation`

状态：未实现。

批次：第五批，建议在 MCP 或核心工具权限模型更稳定后开始。

建议顺序原因：

- 浏览器/桌面操作风险更高，需要 URL allowlist、凭据、截图存储、超时和审计策略。
- 应在配置系统、mode policy、workspace safety、runtime event 和工具权限模型稳定后再实现，避免把高风险外部操作接到不稳定权限边界上。

主要交付：

- browser policy 配置。
- 最小 Playwright browser session 管理。
- 打开页面、读取页面信息和截图工具。
- ToolRegistry、mode policy 和 trace 接入。

## 已完成待归档

这些 change 的 tasks 已完成或已经合入实现，但目录仍在 `openspec/changes/` 下。后续应按项目流程归档到 `openspec/changes/archive/`。

当前无。
