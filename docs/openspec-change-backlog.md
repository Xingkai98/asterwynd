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
- `add-tree-sitter-symbol-extraction`：已合入并归档。
- `add-plan-mode`：已合入并归档。
- `add-streaming-agent-output`：已合入并归档。
- `add-runtime-mode-switching`：已合入并归档。

### 第二批：benchmark 基础设施，已完成关键收敛

- `add-swebench-docker-harness`：已合入，后续 benchmark 相关 change 可以直接复用 Docker preflight、`status + reason` 和 SWE-bench harness 路径。

### 第三批：语义 code intelligence 与 TUI

- `add-lsp-code-intelligence`：repo map 和 tree-sitter 多语言 symbol 已合入，后续应把 LSP 作为更强 provider 接入，避免直接把 LSP 当成仓库结构层。
- `add-minimal-tui-runtime-view`：建议在 planning state、streaming、runtime mode switching 和工具结果 display policy 稳定后做，复用统一运行事件和 mode transition。

### 第四批：外部工具与高风险能力

- `add-mcp-tool-adapter`：可提前做设计和 fake server 测试，但实现会碰 ToolRegistry 权限元数据，建议与 browser 能力错开合入。
- `add-browser-use-safety-foundation`：风险高于 MCP，应在配置、mode policy、workspace safety 和工具权限模型稳定后做。

## 未实现队列

### 1. `add-lsp-code-intelligence`

状态：未实现。

批次：第四批，repo map 和 tree-sitter 基础设施已合入，可开始细化 LSP provider 边界。

建议顺序原因：

- LSP 提供 definition、references、hover、diagnostics 等语义能力，但需要 language server 配置、进程生命周期、文档同步和超时/错误处理。
- repo map 和 tree-sitter 已提供文件级扫描和语法级符号，LSP 应作为更强 provider 接入，而不是承担仓库结构发现职责。

主要交付：

- LSP server 配置、发现和生命周期管理。
- document open/sync、请求调度、超时和状态观测。
- 只读 LSP 工具或 provider。
- definition、references、hover、documentSymbol、workspaceSymbol 和 diagnostics。
- 修改后 diagnostics 反馈。

### 2. `add-minimal-tui-runtime-view`

状态：未实现。

批次：第四批，runtime mode switching 已合入；等待工具结果 display policy 等其余依赖稳定后开始。

建议顺序原因：

- TUI 应复用已有 AgentLoop 事件、planning state、streaming、工具结果 display policy 和 mode transition，而不是定义另一套运行协议。
- 放在这些基础能力之后，可以一次展示稳定的运行状态、工具调用、planning state、streaming 输出和 mode 状态。

主要交付：

- TUI 命令入口。
- AgentLoop 事件流消费。
- 对话、工具调用、planning state、最终回复、diff/test 摘要和 trace 路径展示。
- 非交互环境 graceful failure 或降级。

### 3. `add-mcp-tool-adapter`

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

### 5. `add-browser-use-safety-foundation`

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
