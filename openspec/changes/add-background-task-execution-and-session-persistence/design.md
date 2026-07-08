## Context

Bash 工具同步阻塞的问题在 benchmark 中已暴露：agent 跑完整测试套件时阻塞等待 2 分钟，期间无法做任何有用工作。同时，Web UI 和 CLI 交互模式都面临 session 断开丢失上下文的问题。

两个子能力的技术方案不同但共享"跨调用状态管理"的设计约束，合入同一 change 可以减少架构碎片化。

## Decisions

### Part A: 后台任务执行

#### A.1 Bash 扩展

```python
class BashInput:
    command: str
    run_in_background: bool = False
    timeout: int | None = None
```

当 `run_in_background=True`：
- `Bash.execute()` 启动子进程（`asyncio.create_subprocess_shell`）。
- 注册到 `BackgroundTaskManager`。
- 返回 `"Task started: <task_id>. Use TaskOutput to check status."`。
- `timeout` 参数仍生效：后台任务超时后标记为 `timeout` 状态。

#### A.2 BackgroundTaskManager

```
task_id -> {
    process: asyncio.subprocess.Process,
    command: str,
    started_at: float,
    status: running | completed | timeout | failed,
    exit_code: int | None,
    stdout: str,
    stderr: str,
}
```

关键行为：
- AgentLoop 每次迭代开始时调用 `manager.check_completed()` → 收集所有已完成的后台任务。
- 每个已完成的后台任务作为一条 tool result 消息注入到消息列表（role=tool, name=Bash, content=结构化输出）。
- 同个 task_id 最多报告一次（报告后从 active 列表移到历史）。
- AgentLoop 退出时，`BackgroundTaskManager` 清理所有仍在运行的进程（SIGTERM，等 5s，SIGKILL）。

#### A.3 TaskOutput / TaskStop 工具

- `TaskOutput(task_id, block=True, timeout=30000)`：获取任务输出。`block=True` 时等待直到 completed/timeout/failed（非阻塞轮询，1s 间隔）。`block=False` 时立即返回当前状态。超时后返回已收集的部分输出。
- `TaskStop(task_id)`：发送 SIGTERM，等 3s，SIGKILL。返回最终输出。

两个工具的 capability：`COMMAND_EXECUTE` / `HIGH` risk（TaskStop 可终止进程）。

### Part B: 会话持久化

#### B.1 持久化范围

持久化内容：
```python
@dataclass
class SessionSnapshot:
    session_id: str
    created_at: str
    updated_at: str
    messages: list[Message]
    mode: AgentMode
    todos: list[TodoItem]
    active_skills: list[str]
    run_id: str
    iteration: int
    tool_call_count: int
    edit_count: int
```

明确不持久化：
- LLM client（需要重新初始化 API key / connection）
- MCP server 连接（需要重新启动和发现）
- Background tasks（后台进程在 session 保存时不杀死，但不恢复——下一 session 的 agent 无法继续检查它们）
- WorkspacePolicy（重新从配置构建）

#### B.2 存储格式

```
.asterwynd/sessions/
  <session_id>/
    snapshot.json    # SessionSnapshot JSON
    messages.json    # 完整消息历史（可能很大）
```

`snapshot.json` 包含除 messages 外的所有字段，`messages.json` 是 `list[dict]`。

#### B.3 保存时机

1. **自动保存**：每次迭代结束后自动写入（可配置：`config.session.auto_save: bool = True`）。
2. **手动保存**：agent 可以调用内置的 save session 行为（不是单独工具，由 `--save-on-exit` CLI 参数控制）。
3. **退出时保存**：AgentLoop 正常结束时保存最终快照。

#### B.4 恢复入口

```bash
uv run python cli.py main --resume <session_id>
uv run python cli.py web --resume <session_id>
```

恢复流程：
1. 加载 `snapshot.json` + `messages.json`。
2. 重建 `AgentLoop`，注入消息历史、mode、todos、skills。
3. 系统消息追加 `## Session Resumed\nPrevious session <session_id> ended at <timestamp>.\n`
4. 正常进入交互循环。

如果 session 文件损坏或 message 格式不兼容（例如升级后），返回明确错误而非静默失败。

#### B.5 CLI 变更

```
cli.py main [--resume SESSION_ID]
cli.py web [--resume SESSION_ID]
cli.py session list     # 列出可恢复 session
cli.py session rm ID    # 删除某个 session
```

### 子能力间的交互

- 后台任务在 session 保存时不随 agent 状态一起序列化（后台进程的生命周期独立于 AgentLoop）。
- 会话恢复后再启动后台任务时使用新的 BackgroundTaskManager 实例。
- Todo 列表持久化同时由 session save 和 Change 1 的 todo 工具间接受益。

## Goals / Non-Goals

- 不跨机器恢复会话（不支持远程 session sync）。
- 不支持后台任务的依赖管理（task A → task B 依赖）。
- 不持久化 LSP server 连接状态。
- 不持久化 embedding 索引状态。
- `--resume` 不支持恢复部分消息（不支持 --resume-from-iteration N）。

## Reference Implementation Research

- status: enabled
- reason: 与主流 coding agent 对比后识别的基础能力差距，需调研行业参考实现以指导设计方案。

- research questions:

1. Claude Code 的 background task 如何实现？
2. Claude Code 的 --resume 如何工作？
3. Aider 的会话管理机制？

- findings:

- Claude Code 的 `Bash` 工具有 `run_in_background` 参数。后台任务启动后返回 task_id；`TaskOutput` 工具用于轮询结果。Claude Code 的后台任务在 agent 退出时会自动终止（不持久化后台进程）。
- Claude Code 的 `--resume` 使用 `.claude/sessions/` 目录存储会话快照，恢复时注入 "继续上次对话" 的上下文提示。Resumed session 的 compaction 状态、mode 等都会恢复。
- Aider 有 `/run` 命令支持后台执行测试和 lint 命令。没有独立的会话持久化机制。

- design impact:

- Background task 设计直接参考 Claude Code 的 Bash + TaskOutput 模式。
- Session 持久化格式使用 JSON（而非 pickle），确保可读性和向前兼容。
- 后台任务不与 session 绑定（不跨恢复），与 Claude Code 行为一致。

## Impact Analysis

| 影响面 | 状态 |
|--------|------|
| Bash 工具 | 新增 run_in_background 参数 |
| AgentLoop | 迭代开始检查已完成后台任务、迭代结束自动保存 session |
| ToolRegistry | 新增 TaskOutput / TaskStop |
| CLI | 新增 --resume 和 session 子命令 |
| Workspace safety | 后台命令仍通过 allowlist/denylist 检查 |
| 审批链路 | 后台命令在启动时走一次审批（不额外审批检查结果） |
| MemoryManager compact | 后台任务结果作为普通 tool result 参与 compact |
| MCP | 不影响 |
| Benchmark | 不影响（benchmark 不持久化、不使用后台任务） |
| TUI/Web | TUI 可选展示后台任务状态条 |


## Risks / Trade-offs

- [Risk] 后台进程可能在 AgentLoop 退出时未正确清理。Mitigation: `run()` 的 finally 块中强制 SIGTERM → SIGKILL 清理所有活跃进程。
- [Risk] Session 恢复时消息格式不兼容（跨版本升级）。Mitigation: SessionSnapshot 包含 schema_version 字段，版本不匹配时明确报错。
- [Risk] 自动保存 session 可能在频繁迭代时产生磁盘 I/O 压力。Mitigation: 只在有变更时写入（基于 messages hash），可配置关闭。

## Testing Strategy

- BackgroundTaskManager 单元测试：启动/状态/输出获取/超时终止/进程清理。
- Bash 工具测试：run_in_background=True 返回 task_id、后台命令仍过安全门。
- TaskOutput/TaskStop 工具测试：block/非阻塞查询、终止运行中任务。
- SessionStore 单元测试：保存快照/恢复/损坏文件报错/不存在的 session。
- AgentLoop 集成：后台任务完成后注入结果、退出时清理进程。
- CLI 测试：--resume 参数、session list/rm。
## Pre-Implementation Review

待 `grill-with-docs` 执行后填写。
