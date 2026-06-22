# OpenSpec Change 实现队列

本文档记录当前 active OpenSpec changes 中尚未实现的需求，并按建议实现顺序排列。它不是规格本身；每个 change 的 source of truth 仍是 `openspec/changes/<change-id>/` 下的 proposal、design、specs 和 tasks。

维护规则：

- 新增 OpenSpec change 后，如果不是纯占位，应把它加入本队列。
- change 实现并合入后，应从“未实现队列”移到“已完成待归档”或直接归档到 `openspec/changes/archive/`。
- 调整实现顺序时，应写清楚依赖原因，而不是只移动条目。
- 本文档只记录可提交的 change id 和稳定判断，不记录本地参考仓库路径。

## 未实现队列

### 1. `add-yaml-configuration`

状态：未实现。

建议先做原因：

- 统一配置是后续 mode deny override、MCP server、browser policy、benchmark 默认参数等能力的基础。
- 先把 `.env`、CLI 参数和 `myagent.yaml` 的优先级固定下来，可以减少后续 change 重复改 CLI/Web/benchmark 构造路径。

主要交付：

- typed config model 和 loader。
- `myagent.example.yaml`。
- CLI/Web/benchmark 接入统一配置。
- ModePolicy deny override、ignore patterns、command denylist 从配置读取。

### 2. `add-repo-map-code-intelligence`

状态：未实现。

建议顺序原因：

- 这是 coding-agent 主线的只读能力增强，能直接提升后续需求讨论、代码定位和 benchmark 表现。
- 它依赖 workspace policy、ignore patterns 和 mode policy；放在 YAML 配置之后，可以直接接入统一 ignore 配置。

主要交付：

- repo scanner 和 Python AST symbol extractor。
- repo map 输出格式。
- 只读 code intelligence 工具。
- WorkspacePolicy 和 ignore patterns 约束。

### 3. `implement-structured-planning-state`

状态：未实现。

建议顺序原因：

- 结构化 planning state 是真实 plan mode、TUI 展示、Web Debug、trace 分析和 subagent 协作的共同基础。
- 不先做 planning state，`add-plan-mode` 只能停留在“只读权限边界”，无法交付真正计划能力。

主要交付：

- `agent/planning/` 数据模型和 PlanningManager。
- AgentLoop planning 事件。
- TraceRecorder planning 记录。
- Web session / Debug 视图转发 planning 事件。
- benchmark artifacts 记录 planning 摘要。

### 4. `add-plan-mode`

状态：未实现。

建议顺序原因：

- 依赖 `introduce-agent-mode-policy` 的 mode 权限边界。
- 依赖 `implement-structured-planning-state` 的结构化计划产物。
- 完成后，`plan` 才从“只读权限模式”升级为“可观察、可验证的计划模式”。

主要交付：

- plan mode 的真实行为。
- plan mode 只暴露只读工具，拒绝写入和 dangerous 工具。
- AgentLoop 在 plan mode 中产出结构化 planning state 和自然语言计划说明。
- CLI/Web 启动 plan mode。

### 5. `add-runtime-mode-switching`

状态：未实现。

建议顺序原因：

- 当前 mode 在 session 内不可变；该 change 负责让 CLI/Web/未来 TUI 中的 mode 修改实时生效。
- 放在真实 plan mode 之后，可以让 `read_only`、`plan`、`build` 之间的切换具备完整语义，而不是只切工具权限。

主要交付：

- session runtime state 或等价状态对象。
- 统一 mode transition API。
- ToolRegistry schema / execute 读取最新 mode。
- `mode_changed` 事件、trace 记录、CLI 交互命令、WebSocket 切换消息。
- 为未来 TUI 暴露复用接口。

### 6. `add-minimal-tui-runtime-view`

状态：未实现。

建议顺序原因：

- TUI 应复用已有 AgentLoop 事件、planning state 和 mode transition，而不是定义另一套运行协议。
- 放在 planning state、plan mode 和 runtime mode switching 之后，可以一次展示稳定的运行状态、工具调用和 mode 状态。

主要交付：

- TUI 命令入口。
- AgentLoop 事件流消费。
- 对话、工具调用、planning state、最终回复、diff/test 摘要和 trace 路径展示。
- 非交互环境 graceful failure 或降级。

### 7. `upgrade-subagents-to-agentloop`

状态：未实现。

建议顺序原因：

- 子 agent 升级为受限 AgentLoop 需要稳定的 mode policy、planning state、trace 和 ParentChannel 语义。
- 放在 TUI 之后，可以复用已经稳定的运行事件和展示/调试模型；如果优先级转向并行调查能力，也可以提前到 TUI 之前。

主要交付：

- SubAgentManager 创建受限 AgentLoop。
- 子 agent 独立 messages、tools、memory、mode 和 trace。
- ParentChannel 回传完成、失败、取消和摘要。
- 取消逻辑能停止子 AgentLoop。

### 8. `add-mcp-tool-adapter`

状态：未实现。

建议顺序原因：

- MCP 需要统一配置管理 server 列表，也需要 mode policy 和 tool permission metadata。
- 放在核心本地工具、planning 和 subagent 语义稳定之后，可以降低外部工具协议引入的复杂度。

主要交付：

- MCP server 配置和连接管理。
- fake MCP server discovery 测试。
- MCP schema 映射为 ToolRegistry schema。
- MCP tool 执行、错误、超时和权限元数据。

### 9. `add-browser-use-safety-foundation`

状态：未实现。

建议顺序原因：

- 浏览器/桌面操作风险更高，需要 URL allowlist、凭据、截图存储、超时和审计策略。
- 应在配置系统、mode policy 和工具权限模型稳定后再实现，避免把高风险外部操作接到不稳定权限边界上。

主要交付：

- browser policy 配置。
- 最小 Playwright browser session 管理。
- 打开页面、读取页面信息和截图工具。
- ToolRegistry、mode policy 和 trace 接入。

## 已完成待归档

这些 change 的 tasks 已完成或已经合入实现，但目录仍在 `openspec/changes/` 下。后续应按项目流程归档到 `openspec/changes/archive/`。

- `introduce-agent-mode-policy`：已实现并合入，PR #10。
- `standardize-change-design-and-diagnosis-docs`：已完成流程文档和 artifact checker 规则。
