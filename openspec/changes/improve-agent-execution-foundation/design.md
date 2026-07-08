## Context

两个子能力共享一个主题：让 agent 在 build mode 执行期更有自我感知——知道自己做到哪了（todo 追踪），失败了能自己恢复（错误重试）。

## Decisions

### 1. TodoWrite 工具设计

数据模型复用 `Planning State` 的 `PlanItem`：

```python
class TodoItem:
    id: str          # 稳定标识
    content: str     # 任务描述
    status: str      # pending | in_progress | completed
    notes: str | None  # 可选说明
```

工具操作：

- `create(content: str) -> TodoItem` — 创建新 todo
- `update(id: str, status: str, notes: str | None) -> TodoItem` — 更新状态
- `list(status: str | None) -> list[TodoItem]` — 列出所有或按状态过滤

工具能力标记：`AGENT_STATE` / `MEDIUM` risk。

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

只展示最近 10 条，按创建时间排序，completed 项在末尾。

### 3. RetryHook 接入

`RetryHook` 已有实现（`agent/hooks/builtin/retry.py`），核心逻辑：

- `max_attempts = 3`
- 退避：1s / 2s / 4s
- 可重试错误分类基于工具返回的错误字符串：
  - 匹配 `timeout|timed out|connection|rate limit|429|503|temporary` → 重试
  - 匹配 `permission denied|not found|invalid|no such file` → 不重试
- 重试时 trace 记录 `tool_retry` step

接入方式：AgentLoop 在 `after_tool_execute` 中检查 `result` 是否为错误字符串，匹配可重试模式时，循环重试直到成功或达到最大次数。

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

## Testing Strategy

- TodoWrite 工具单元测试：create/update/list operation、status 合法性校验、duplicate id。
- RetryHook 策略单元测试：可重试错误重试 3 次后失败、不可重试不触发、退避间隔。
- AgentLoop 集成测试：工具失败后自动重试、重试成功继续执行、达到上限报错。
- AgentLoop 集成测试：build mode 注入 todo、todo 为空不注入、retry 不重复审批。
- TUI todo 面板单元测试：pending/in_progress/completed 展示。
## Pre-Implementation Review

待 `grill-with-docs` 执行后填写。
