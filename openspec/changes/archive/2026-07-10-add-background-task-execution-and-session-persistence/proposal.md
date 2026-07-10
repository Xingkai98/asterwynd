## Why

当前 Asterwynd 有两个"跨单次工具调用"的能力缺口：

1. **无法后台执行任务**：`Bash` 工具同步阻塞，长时间命令（全量测试、npm install）占用整个 agent 迭代。Claude Code 的 `run_in_background` 参数允许 agent 让命令后台执行、稍后检查结果。

2. **无法保存恢复会话**：Session 断开后全部上下文丢失。Claude Code 有 `--resume`，Codex 有会话持久化。

两者共享核心概念——"跨工具调用的状态生命周期"。后台任务需要进程管理器（跨调用的进程状态），会话恢复需要序列化（跨进程的 AgentLoop 状态）。合入同一个 change 做一个统一的状态持久化抽象。

## What Changes

### 后台任务执行

- `Bash` 工具新增 `run_in_background: bool = False` 参数。
- 新增 `agent/background.py`：`BackgroundTaskManager`，管理后台进程的启动、状态查询和清理。
- 新增工具：
  - `TaskOutput(task_id: str)`：获取后台任务的 stdout/stderr 输出和状态（running/completed/timeout/failed）。
  - `TaskStop(task_id: str)`：终止后台任务。
- AgentLoop 在每次迭代开始前检查已完成的后台任务，将结果作为 tool result 注入消息。

### 会话持久化

- 新增 `agent/session.py`：`SessionStore`，负责序列化 AgentLoop 状态。
- 持久化内容：消息历史、当前 mode、todo 列表、技能激活状态、最近的 tool call 结果。
- CLI 新增 `--resume <session_id>` 参数，从 SessionStore 恢复会话。
- 会话默认保存在 `.asterwynd/sessions/` 目录下。
- 不持久化：LLM connection、未完成的后台任务、MCP server 连接。

## Capabilities

### Modified Capabilities

- `agent-runtime`: `Bash` 后台执行、`AgentLoop` 会话序列化/恢复。
- `coding-tools`: `Bash` 工具扩展 `run_in_background` 参数。

## Impact

- 影响代码：
  - `agent/background.py`（新增）
  - `agent/session.py`（新增）
  - `agent/tools/builtin/bash.py`（新增 background 参数）
  - `agent/tools/builtin/tasks.py`（新增 TaskOutput / TaskStop）
  - `agent/tools/factory.py`
  - `agent/loop.py`（后台任务结果注入、session save/restore）
  - `agent/main.py`（新增 --resume 参数）
- 影响测试：
  - `tests/agent/test_background.py`
  - `tests/agent/test_session.py`
  - `tests/agent/tools/test_bash.py`
  - `tests/agent/tools/test_tasks.py`
  - `tests/test_cli.py`

## Change Type

- primary: feature
- secondary: refactor
