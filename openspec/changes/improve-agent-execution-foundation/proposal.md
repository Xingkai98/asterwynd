## Why

当前 Asterwynd 在 build mode 执行期有两个基础缺陷：

1. **无执行期任务追踪**：Plan Mode 产出 `Plan Document` 和 `Planning State`，但 build mode 下 agent 没有工具把自己的执行进度写成结构化 todo 状态。多步任务中 agent 容易遗落步骤，benchmark 中 `asterwynd-003-agentloop-trace` 的跨文件 trace 传播遗漏正是这个问题的典型症状。

2. **工具调用失败无自动恢复**：`RetryHook`（`agent/hooks/builtin/retry.py`）已实现指数退避重试逻辑但从未接入 `AgentLoop`。工具调用失败后 agent 直接拿到错误字符串，无法自动重试，导致 benchmark 的 `tool_error` 失败类别中包含大量可重试的瞬时错误。

Claude Code 的 `TodoWrite` 工具让 agent 在任意 mode 下维护 `pending/in_progress/completed` 状态的任务列表；Codex、Cursor 均有类似机制。Claude Code 和 Codex 的工具调用失败均有重试/降级策略。

## What Changes

### 执行期 Todo 追踪

- 新增 `TodoWrite` 工具，提供 `create`/`update`/`list` 操作，task item 模型复用 `Planning State` 的 item 结构（id、content、status、notes）。
- `TodoWrite` 在 build/read_only/plan mode 下均可用，不限于 plan mode。
- AgentLoop 在 build mode 系统消息中注入当前 todo 状态摘要。
- TUI 和 Web UI 展示当前 todo 列表面板。

### 工具错误恢复

- 将 `RetryHook` 接入 AgentLoop 的 HookManager。
- 定义重试策略：最大 3 次重试、指数退避（1s/2s/4s）、仅对瞬时错误（timeout、connection、rate limit）重试。
- 确定性错误（参数错误、权限拒绝、文件不存在）不重试。
- 重试过程在 trace 中记录为独立 step。

## Capabilities

### New Capabilities

- 无。在现有 `agent-runtime`、`tool-system`、`planning` 能力域内扩展。

### Modified Capabilities

- `tool-system`: 新增 `TodoWrite` 工具。
- `agent-runtime`: `AgentLoop` 接入 `RetryHook`，定义可重试错误分类。
- `planning`: `Planning State` item 模型被 `TodoWrite` 复用，build mode 下可展示执行进度。

## Impact

- 影响代码：
  - `agent/tools/builtin/todo.py`（新增）
  - `agent/tools/factory.py`
  - `agent/loop.py`
  - `agent/hooks/builtin/retry.py`
  - `agent/tui/*.py`（todo 面板展示）
  - `web/`（todo 面板展示）
- 影响测试：
  - `tests/agent/tools/test_todo_tool.py`
  - `tests/agent/test_loop.py`
  - `tests/agent/hooks/test_retry.py`
  - `tests/agent/tui/`
- 不影响：LLM provider 协议、workspace safety、benchmark runner、MCP 集成。

## Change Type

- primary: feature
- secondary: refactor
