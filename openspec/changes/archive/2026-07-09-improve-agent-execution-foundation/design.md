## Context

两个子能力共享一个主题：让 agent 在 build mode 执行期更有自我感知——知道自己做到哪了（todo 追踪），失败了能自己恢复（错误重试）。

## Decisions

### 1. TodoWrite 工具设计

数据模型复用 `Planning State` 的 `PlanItem`：

```python
class PlanItem:
    id: str          # 稳定标识
    content: str     # 任务描述
    status: str      # pending | in_progress | completed
    note: str | None # 可选说明
```

工具操作：

- `create(content: str) -> PlanItem` — 创建新 todo，status 初始为 `pending`
- `update(id: str, status: str, note: str | None) -> PlanItem` — 更新状态，无效 status（不在 `pending/in_progress/completed` 范围内）返回错误
- `list(status: str | None) -> list[PlanItem]` — 列出所有或按 status 过滤

工具能力标记：`AGENT_STATE` / `LOW` risk。

与 Plan Mode 的 Planning State 关系：
- Plan Mode 下 `UpdatePlan` 产出的是 *计划*（plan item），`TodoWrite` 操作的是 *执行状态*（execution todo）。
- 两者使用相同的 item 数据模型但存储分开。Plan items 按 plan document 章节组织；execution todos 是扁平列表。
- Build mode 下 `UpdatePlan` 不可用，只能用 `TodoWrite`。

### 2. AgentLoop 注入 todo 上下文

`_messages_with_run_context()` 在当前 todo 列表非空时，在系统消息末尾注入：

```
## Current Progress
- [ ] 找到所有需要修改的文件
- [in_progress] 实现 Edit 工具的替换逻辑
- [completed] 阅读现有 tool registry 代码
```

只展示最近 10 条，按 status 分组排序（in_progress > pending > completed），同组内按创建顺序。

### 3. RetryHook 接入

`RetryHook` 已有实现（`agent/hooks/builtin/retry.py`），核心逻辑：

- `max_retries = 3`（1 次初始调用 + 最多 3 次重试 = 最多 4 次总尝试）
- 退避：1s / 2s / 4s
- 可重试错误分类基于工具执行抛出的 Exception 消息：
  - 匹配 `timeout|timed out|connection|rate limit|429|503|temporary` → 重试
  - 不匹配 → 不重试，错误消息直接返回给 LLM
- 工具正常返回的错误字符串（如 `[Error: ...]`）不触发重试
- 重试时 trace 记录 `tool_retry` step，由 AgentLoop 通过 `TraceRecorder.record("tool_retry", ...)` 记录：
  - `tool_name: str` — 工具名
  - `attempt: int` — 第几次尝试（1-based）
  - `max_retries: int` — 配置的最大重试次数
  - `error: str` — 异常消息摘要
  - `delay_ms: float` — 本次退避等待时间（毫秒）
  - `final: bool` — 是否最终失败（重试耗尽时为 `true`）

接入方式：AgentLoop 在工具调用外层 try/except 捕获 Exception，匹配可重试模式时循环重试直到成功或达到最大次数。

不通过 Hook 协议接入——Hook 协议是 fire-and-forget 回调形式，不返回"是否恢复"信号。改为直接在 AgentLoop 工具执行路径中内联重试逻辑，保留 RetryHook 类作为重试策略的配置载体。

### 4. 重试与 approval 的交互

如果第一次工具调用触发了 approval 且用户拒绝，不重试（权限拒绝是确定性错误）。
如果第一次工具调用被 auto-approve 后执行失败，重试不再次触发 approval（同一个 tool call 的首次执行已经过了 approval gate）。

## Goals / Non-Goals

- 不改变 Plan Mode 的 `UpdatePlan`/`ExitPlanMode` 语义。
- 不支持 todo 的依赖关系（不引入 DAG）。
- 不支持跨 session 持久化 todo 状态。
- 不支持 Bash 命令的重试——命令可能有副作用，不应该静默重试。

## Reference Implementation Research

- status: enabled
- reason: 与主流 coding agent 对比后识别的基础能力差距，需调研行业参考实现以指导设计方案。

- research questions:

1. Claude Code 的 `TodoWrite` 工具如何设计？
2. Claude Code 的工具重试策略如何？
3. Codex 的 task tracking 机制如何？

- findings:

- Claude Code 的 `TodoWrite` 以 `todos: list[{content, status, activeForm}]` 为参数，一次调用全量替换。status 为 `pending/in_progress/completed`，需要两个描述字段（列表显示用 content，状态栏用 activeForm）。Asterwynd 采用更简单的单条目 CRUD 模型，减少每次调用的 token 开销。
- Claude Code 的 tool error retry 在 framework 层不可见（由 SDK 处理）。Codex 有显式的 tool retry with backoff。Asterwynd 采取中间路线：在 AgentLoop 层做基于错误字符串分类的重试，避免 SDK 依赖但提供比 "只报错" 更好的体验。
- Codex 的 task list 与 Claude Code 类似，也是全量替换模式。

- design impact:

- Todo 采用单条目 CRUD 而非全量替换，减少 LLM 每次需要重写整个列表的 token 开销。
- 重试策略先从简单错误字符串匹配开始，后续可升级为结构化错误码。

## Impact Analysis

| 影响面 | 状态 |
|--------|------|
| AgentLoop 工具执行路径 | 新增 retry 循环，向后兼容 |
| ToolRegistry | 新增 TodoWrite 注册，不影响现有工具 |
| AgentLoop run context | 新增 todo 注入段，不影响现有注入 |
| TUI/Web 展示 | 新增可选面板，不改变现有面板 |
| Plan Mode | 不影响 UpdatePlan/ExitPlanMode |
| Benchmark | 不影响 runner，但可改善 benchmark 任务通过率 |
| MCP | 不影响 |


## Risks / Trade-offs

- [Risk] TodoWrite 与 UpdatePlan/ExitPlanMode 共享 PlanItem 数据模型，可能造成语义混淆。Mitigation: 两者存储完全隔离，工具在不同 mode 下独立注册。
- [Risk] 错误字符串匹配的重试分类可能漏判或误判。Mitigation: 从保守的匹配模式开始，后续 benchmark 数据驱动调整。
- [Risk] Bash 命令被排除在重试范围外，但某些只读 Bash（如 `cat`）理论上可重试。Mitigation: 先保守排除全部 Bash 命令，后续数据驱动调整。
- [Risk] 非 Bash 的副作用工具（Write、Edit、MCP tool、Web/API tool）若"部分成功执行后抛异常"，自动重试可能造成重复写入、重复请求等副作用。当前仅按工具名排除 Bash，未对 Write/Edit 等工具做幂等性保护。Mitigation: 当前重试仅匹配 Exception 消息模式——Write/Edit 写入成功后的异常极少匹配 `timeout|connection|rate limit` 模式；如需更安全，后续可引入工具 `retryable` 属性白名单或依赖幂等 token。

## Testing Strategy

- TodoWrite 工具单元测试：create/update/list operation、status 合法性校验（无效 status 被拒绝）、duplicate id。
- RetryHook 策略单元测试：可重试错误重试 3 次后失败、不可重试不触发、退避间隔。
- AgentLoop 集成测试：工具失败后自动重试、重试成功继续执行、达到上限报错。
- AgentLoop 集成测试：build mode 注入 todo、todo 为空不注入、retry 不重复审批。
- AgentLoop 集成测试：`tool_retry` trace step 记录（retry 中 + 耗尽两场景）。
- AgentLoop 集成测试：read_only mode 下 TodoWrite 权限/执行/注入全链路。
- TodoWrite 单元测试：排序规则（in_progress > pending > completed，同组按创建顺序）、最多 10 条截断。
- Web UI 测试：planning-panel 在 build/read_only mode 展示 execution todos、plan mode 展示 plan items、mode 切换时正确替换内容。
- WebSocket/session 层测试：`todo_updated` 事件到 Web UI 面板渲染。
- AgentLoop 集成测试：Plan items 与 execution todos 隔离——mode 切换后展示互不污染。
- AgentLoop 集成测试：Bash 命令异常不触发重试。

## Document Impact

实现和归档时需要更新的文档：

- `docs/openspec-change-backlog.md`: 实现后从 backlog 移除。
- `docs/architecture.md`: 如果 RetryHook 接入方式或 TodoWrite 与 Planning State 的共享模型关系需要记录。
- `AGENTS.md`: 无需变更（规则不变）。
- `README.md` / `README_EN.md`: 无需变更（不新增面向用户的功能入口）。
## Pre-Implementation Review

2026-07-09 执行 `grill-with-docs`，逐项确认以下决策：

1. **数据模型**: 直接复用 `PlanItem(id, content, status, note)`，不新建 TodoItem 类。
2. **状态存储**: AgentLoop 新增 `_execution_todos: list[PlanItem]` 属性和 create/update/list 方法。TodoWrite 工具通过回调操作此列表。
3. **RetryHook 接入**: 方案 B — RetryHook 保留为工具类，AgentLoop 在工具执行路径中直接调用 `execute_with_retry()`，不通过 HookManager 协议。
4. **TodoWrite API**: 单工具 + `operation` 枚举字段（`create`/`update`/`list`）。一次调用只操作一个 item。
5. **可重试错误**: 仅匹配 `Exception` 消息（`timeout|timed out|connection|rate limit|429|503|temporary`）。工具返回的错误字符串（权限、文件不存在）不会抛异常，自然跳过。
6. **Bash 排除**: 按工具名 `tool_call.name == 'Bash'` 直接跳过重试，不检查 `read_only` 属性。
7. **Todo 上下文注入**: BUILD 和 READ_ONLY mode 下注入。Plan mode 有自己的 Planning State。
8. **排序规则**: in_progress > pending > completed，同组内按创建顺序。最多展示 10 条。
9. **权限**: `AGENT_STATE_PERMISSION`（AGENT_STATE / LOW risk），不设 `allowed_modes` 限制。所有 mode 下 auto-approve（LOW 风险在各 profile 的 auto-approve 范围内）。ActivateSkill 同样受益于此降级。
10. **Web UI**: 复用现有 `planning-panel`。build/read_only mode 展示 execution todos，plan mode 展示 plan items。通过 `todo_updated` 事件驱动。TUI 跳过（目录不存在）。
11. **RetryHook 改造**: 新增 `_is_retryable()` 函数做错误字符串模式匹配。`execute_with_retry()` 改为：Exception 且可重试 → 循环重试；Exception 但不可重试 → 直接返回错误；成功 → 返回结果。
