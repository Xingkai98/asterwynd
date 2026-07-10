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

### 第六批：包结构和分发基础


### 第七批：基础能力补全

基于与其他 coding agent（Claude Code、Codex、Cursor、Aider 等）的系统性对比，以下 6 个 change 覆盖了 Asterwynd 当前必备基础能力的核心缺口。第一批（1/3/4）可并行推进，第二批 2 等 1 合入后开始（共享 AgentLoop 改动面），第三批 5/6 可并行。

- `improve-agent-execution-foundation`：已合入并归档。
- `add-semantic-code-search`：语义代码搜索——embedding 索引 + SearchSimilar 工具。
- `add-background-task-execution-and-session-persistence`：后台任务执行 + 会话保存/恢复。

### 第八批：高风险 browser 能力

- `add-browser-use-safety-foundation`：风险高于 MCP，应在配置、mode policy、workspace safety 和工具权限模型稳定后做。

## 未实现队列


状态：实现中（partial 已应用在 disk）。

批次：第六批，独立推进。

建议顺序原因：

- 用户可见破坏性变更：`main` 子命令删除、`--interactive` 删除、根 `cli.py` 删除。
- 不依赖任何其他 change，可独立开发和合入。

主要交付：

- `agent/main.py` 作为 CLI 主入口模块；删除根目录 `cli.py`。
- `@app.callback(invoke_without_command=True)` 默认交互；`run` 子命令单轮；删除 `--interactive` 和 `main` 子命令。
- XDG 日志路径 + CWD `.env` 搜索。
- `pyproject.toml` 元数据补全（MIT license、classifiers 等）。

### 1. `add-background-task-execution-and-session-persistence`

状态：未实现。

批次：第七批第三批，可并行推进。

建议顺序原因：

- Bash 后台执行和 session 持久化都不改变已有核心路径语义。
- 新增组件（BackgroundTaskManager、SessionStore）不与其他 change 冲突。

主要交付：

- Bash `run_in_background` 参数 + BackgroundTaskManager。
- `TaskOutput` / `TaskStop` 工具。
- SessionStore 序列化/恢复 + CLI `--resume`。

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

### 3. `add-browser-use-safety-foundation`

状态：未实现。

批次：第八批，建议在 MCP 或核心工具权限模型更稳定后开始。

建议顺序原因：

- 浏览器/桌面操作风险更高，需要 URL allowlist、凭据、截图存储、超时和审计策略。
- 应在配置系统、mode policy、workspace safety、runtime event 和工具权限模型稳定后再实现，避免把高风险外部操作接到不稳定权限边界上。

主要交付：

- browser policy 配置。
- 最小 Playwright browser session 管理。
- 打开页面、读取页面信息和截图工具。
- ToolRegistry、mode policy 和 trace 接入。

## 已完成待归档

这些 change 的 tasks 已完成或实现已准备合入，但因明确阻塞暂时无法在同一个实现 PR 中归档，目录仍在 `openspec/changes/` 下。阻塞解除后应优先按项目流程归档到 `openspec/changes/archive/`。

当前无。
