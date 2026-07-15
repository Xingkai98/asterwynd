# OpenSpec Change 实现队列

本文档记录当前 active OpenSpec changes 中尚未实现的需求，并按建议实现顺序排列。它不是规格本身；每个 change 的 source of truth 仍是 `openspec/changes/<change-id>/` 下的 proposal、design、specs 和 tasks。

维护规则：

- 新增 OpenSpec change 后，如果不是纯占位，应把它加入本队列。
- change 实现 PR 必须同时包含归档收尾：归档到 `openspec/changes/archive/YYYY-MM-DD-<change-id>/` 并从本文档移除；如果因冲突、校验失败或其他明确阻塞暂时无法归档，才移到“已完成待归档”。
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

### 第三批：Coding Agent 基本操作面和入口回归

- 当前无未实现 change。

### 第四批：工具权限模型前置，已完成

当前无未实现 change。

### 第五批：MCP 与 TUI 基本扩展

- `add-lsp-code-intelligence`：已合入并归档。
- `add-mcp-tool-adapter`：已合入并归档。
- `add-minimal-tui-runtime-view`：建议在 skills、工具权限模型、planning state、streaming、runtime mode switching、工具结果 display policy 和已完成的 slash command framework 稳定后做，复用统一运行事件和 mode transition。

### 第六批：包结构和分发基础，已完成

- `improve-package-structure`：已合入（PR #49），未走完整 OpenSpec 流程，无需归档。

### 第七批：基础能力补全

基于与其他 coding agent（Claude Code、Codex、Cursor、Aider 等）的系统性对比，以下 6 个 change 覆盖了 Asterwynd 当前必备基础能力的核心缺口。第一批（1/3/4）可并行推进，第二批 2 等 1 合入后开始（共享 AgentLoop 改动面），第三批 5/6 可并行。

- `improve-agent-execution-foundation`：已合入并归档。
- `add-semantic-code-search`：已合入并归档。

### 第八批：高风险 browser 能力，已完成

- `add-browser-use-safety-foundation`：已合入并归档。

### 第九批：开发流程控制平面

- `automate-conversation-to-delivery-workflow`：建立独立于 AgentLoop 的本地 workflow control plane，统一管理探索、需求、设计、开发、审查、worktree 和人工 gate。该 change 影响 workflow、workspace safety、session/executor integration 和 CI，建议先完成 tracer bullet，再逐步接管现有脚本。

## 未实现队列

### 1. `automate-conversation-to-delivery-workflow`

状态：building.实现收尾中，CLI/adapter/workspace/receipt 主路径已实现并进入自审。

批次：第九批，独立控制平面基础设施。

建议顺序原因：

- 当前开发流程仍依赖 `AGENTS.md` 提示、可变 handoff JSON 和 agent 自觉停止，无法为后续多 agent、TUI 和自动化开发提供可信状态基础。
- 应先完成 event store、可信 gate、worktree promotion 和 executor contract 的 tracer bullet，再迁移现有 workflow 脚本。
- 与 `add-minimal-tui-runtime-view` 可并行设计，但 TUI 若展示开发生命周期状态，应最终消费本 change 的统一协议。

主要交付：

- 独立 `workflow_control` bounded context 与本地 CLI。
- CLI Host Wrapper、Prompt Adapter、Asterwynd adapter、workspace binding、旧 handoff 只读兼容入口和最小签名 workflow receipt。
- SQLite append-only event store、snapshot、lease 和状态恢复。
- Requirements gate 后自动创建并绑定 worktree。
- `enter/report/approve` 分权协议与可信人工 gate。
- Workflow bundle、CI 重放审计和可复用 AGENTS 接入模板。

### 2. `add-minimal-tui-runtime-view`

状态：未实现。

批次：第五批，runtime mode switching 和 slash command framework 已合入基础能力；等待 skills、工具权限模型、工具结果 display policy 等其余依赖稳定后开始。

建议顺序原因：

- TUI 应复用已有 AgentLoop 事件、planning state、streaming、工具结果 display policy、slash command registry、skill runtime、tool permission metadata 和 mode transition，而不是定义另一套运行协议。
- 放在这些基础能力之后，可以一次展示稳定的运行状态、工具调用、planning state、streaming 输出、mode 状态和工具权限信息。

主要交付：

- TUI 命令入口。
- AgentLoop 事件流消费。
- 对话、工具调用、planning state、最终回复、diff/test 摘要和 trace 路径展示。
- 非交互环境 graceful failure 或降级。

## 已完成待归档

这些 change 的 tasks 已完成或实现已准备合入，但因明确阻塞暂时无法在同一个实现 PR 中归档，目录仍在 `openspec/changes/` 下。阻塞解除后应优先按项目流程归档到 `openspec/changes/archive/`。

当前无。
