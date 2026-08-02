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

### 第九批：Wayfinder 面试深度深化（#73-79）

基于 wayfinder 地图 #72（面试深度路线）拆解的 6 个深化方向，已全部立项为 OpenSpec change（2026-08-01）。按批次推进；同一批次可并行开 PR，但共享 AgentLoop/ToolRegistry/trace 语义的 change 需错开合入。

- **Batch 1（并行，低冲突）**：`tool-governance-deepening`（✅ 已合入并归档，2026-08-02）‖ `sandbox-hardening`。最独立、无硬依赖，各开独立 worktree。先立 `agent/embedding/` 公共模块（#77 提供，供 #75 复用）。
- **Batch 2（高冲突，拆分）**：`context-engineering-deepening`。拆 3 子 change（增量 token 计数+四字段摘要 / Prefix Cache 注入顺序 / 分页进度+深层 MD 按需加载）；与 #77 约定「稳定层/可变层」注入契约。
- **Batch 3（并行）**：`observability-deepening`（待实现第二批）‖ `long-term-memory-deepening`（✅ 已合入并归档，2026-08-02）。依赖 PR #80 statistics（已合入）做回归门禁；#75 先 ADR 论证三层存储，低风险切片先行。
- **Batch 4（最后）**：`multi-agent-collaboration`。依赖最重，先 grill 设计；复用 #67 `agent/workflow/` 状态机。

关键依赖：`#78 observability` 依赖 `#77 tool-governance` 质量事件 schema；`#75 long-term-memory` 依赖 `#77` embedding 模块；`#74` 子项②③ 依赖 `#77` 注入契约；`#79` 依赖 `#74/#78`。

## 未实现队列

### 1. `sandbox-hardening`

状态：未实现。

批次：第九批 Batch 1（并行，与 tool-governance-deepening 同时开）。

建议顺序原因：

- 与 #77 并行（独立 worktree）。分阶段交付：bash AST 句型校验 + cgroup v2 资源限制 + 50+ 恶意 prompt 回归集先行，容器隔离作可选后端。
- 多 workspace 边界已由 add-workspace-param 合入，为本 change 基准。

主要交付：

- bash AST 句型校验（参数类型+范围约束）。
- cgroup v2 资源限制 + 超限 kill 入 trace。
- 50+ 恶意 prompt 攻击回归集。
- 沙箱 deny/kill/oom 事件入 trace。

### 2. `context-engineering-deepening`

状态：未实现。

批次：第九批 Batch 2（拆 3 子 change）。

建议顺序原因：

- 共享底座、冲突面最大，拆 3 子 change 分阶段合入（① 增量 token 计数+四字段摘要 ② Prefix Cache 注入顺序 ③ 分页进度+深层 MD 按需加载）。
- 在 #77 注入契约之上做稳定前缀缓存（稳定层/可变层分层解决动态选择与 cache 张力）。

主要交付：

- 四字段结构化摘要 + tool_call pending 标记。
- 两级层级压缩。
- Prefix Cache 注入顺序 + cache_control 断点。
- 分页读进度 `(file,offset,total)` + 深层 MD 按需加载。

### 3. `observability-deepening`

状态：第一批已合入（PR #87，2026-08-02）；第二批待实现。

批次：第九批 Batch 3（与 long-term-memory-deepening 并行）。

建议顺序原因：

- 依赖 PR #80 statistics（已合入）做回归门禁基线；依赖 #77 质量事件 schema。
- 交付 CI P95/成功率 >5% 拦截、成本归属账单、四类异常分类、session timeline 看板。

第一批（已完成）交付：

- TraceRecorder 记录 token + 结构化事件 schema。
- 按 session/phase/tool 成本归属账单（CostLedger + JSONL 持久化）。
- 异常自动分类（权限拒绝/网络超时/模型幻觉/参数错误）+ 差异化告警。

第二批（待实现）：

- CI benchmark 回归门禁（>5% 拦截）。
- Session timeline 看板。

### 4. `multi-agent-collaboration`

状态：未实现。

批次：第九批 Batch 4（最后）。

建议顺序原因：

- 依赖最重且需先决策复用 PR #63 控制平面（已关闭，改用 #67 `agent/workflow/` 状态机）。
- 做 token/time 预算硬 kill、JSON 快照恢复、消息总线、编排模式库，均建立在 #74/#75 压缩与 #78 事件流稳定之后。

主要交付：

- 状态快照与恢复（JSON + 断点续跑）。
- 每子 agent token/时间预算硬 kill + 失败摘要。
- 轻量消息总线（严格 token 预算）。
- 编排模式库（orchestrator-worker/peer-review/hierarchical/竞标）。

### 5. `add-minimal-tui-runtime-view`

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
