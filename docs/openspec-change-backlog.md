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

### 第六批：基础能力补全

基于与其他 coding agent（Claude Code、Codex、Cursor、Aider 等）的系统性对比，以下 6 个 change 覆盖了 Asterwynd 当前必备基础能力的核心缺口。第一批（1/3/4）可并行推进，第二批 2 等 1 合入后开始（共享 AgentLoop 改动面），第三批 5/6 可并行。

- `improve-agent-execution-foundation`：Agent 执行可靠性——todo 任务追踪 + 工具错误恢复重试。
- `add-parallel-tool-execution`：AgentLoop 并行工具执行——独立只读调用并发化。
- `add-persistent-cross-session-memory`：跨 session 持久记忆——user/feedback/project/reference 四类，与 Claude Code 格式兼容。
- `add-semantic-code-search`：语义代码搜索——embedding 索引 + SearchSimilar 工具。
- `add-multimodal-input-support`：图片/多模态输入——Message 协议扩展 + Read 工具图片支持。
- `add-background-task-execution-and-session-persistence`：后台任务执行 + 会话保存/恢复。

### 第七批：高风险 browser 能力

- `add-browser-use-safety-foundation`：风险高于 MCP，应在配置、mode policy、workspace safety 和工具权限模型稳定后做。

## 未实现队列

### 1. `improve-agent-execution-foundation`

状态：未实现。

批次：第六批，第一批可并行推进。

建议顺序原因：

- Todo 追踪和错误重试都是小改动、低风险、高回报。
- 不依赖其他 change，可独立开发合入。

主要交付：

- `TodoWrite` 工具（create/update/list）。
- AgentLoop 接入 RetryHook，基于错误类型分类的重试策略。
- build mode 系统消息注入 todo 状态；TUI/Web 可选 todo 面板。

### 2. `add-parallel-tool-execution`

状态：未实现。

批次：第六批第二批，建议等 `improve-agent-execution-foundation` 合入后再开始（共享 AgentLoop 改动面）。

建议顺序原因：

- AgentLoop 核心重构，架构风险最高。
- 与 Change 1 共享 `loop.py` 改动面，错开合入避免冲突。

主要交付：

- Tool 基类 `parallelizable` 属性。
- AgentLoop 分组并行执行（连续只读 tool calls 同组并发）。
- 并行组审批退化策略；错误隔离。

### 3. `add-persistent-cross-session-memory`

状态：未实现。

批次：第六批第一批，可并行推进。

建议顺序原因：

- 自包含的 memory 模块扩展，只新增文件和工具，不改动核心路径。
- 与 Claude Code 格式兼容，方便后续互操作。

主要交付：

- `PersistentMemory` 类，管理四类记忆文件。
- `SaveMemory` / `RecallMemory` 工具。
- AgentLoop 系统消息注入持久记忆上下文。

### 4. `add-semantic-code-search`

状态：未实现。

批次：第六批第一批，可并行推进。

建议顺序原因：

- 完全独立的 code_intelligence 模块扩展。
- 不影响 AgentLoop 核心路径。

主要交付：

- `agent/code_intelligence/embeddings.py` — embedding 模型加载和编码。
- `agent/code_intelligence/index.py` — sqlite-vec 向量索引。
- `SearchSimilar` 语义搜索工具。

### 5. `add-multimodal-input-support`

状态：未实现。

批次：第六批第三批，改动面最大（Message 协议 + 所有 provider adapter），建议等第一批合入后再开始。

建议顺序原因：

- 触及整个消息传递链（Message → LLM adapter → compact → trace → subagent）。
- 需要等 AgentLoop 改动（Change 1/2）稳定后再叠加 Message 协议扩展。

主要交付：

- `Message.content` 扩展为 `str | list[ContentBlock]`。
- `ToolResult.content_blocks` 新增字段。
- Read 工具图片识别 + base64 编码。
- OpenAI/Anthropic adapter 多模态格式转换。

### 6. `add-background-task-execution-and-session-persistence`

状态：未实现。

批次：第六批第三批，可并行推进。

建议顺序原因：

- Bash 后台执行和 session 持久化都不改变已有核心路径语义。
- 新增组件（BackgroundTaskManager、SessionStore）不与其他 change 冲突。

主要交付：

- Bash `run_in_background` 参数 + BackgroundTaskManager。
- `TaskOutput` / `TaskStop` 工具。
- SessionStore 序列化/恢复 + CLI `--resume`。

### 7. `add-minimal-tui-runtime-view`

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

### 8. `add-browser-use-safety-foundation`

状态：未实现。

批次：第六批，建议在 MCP 或核心工具权限模型更稳定后开始。

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
