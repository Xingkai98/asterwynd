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
    timeout: float | None = None  # 秒
```

当 `run_in_background=True`：
- `Bash.execute()` 先经 `WorkspacePolicy.assert_command_allowed()` 安全门检查。
- 通过 `SandboxExecutor.run_background(cmd, cwd=...)` 启动子进程，返回 `BackgroundProcessHandle`。
- 调用 `run_in_background_cb` 注册到 `BackgroundTaskManager`。
- 返回 `"Task started: <task_id>. Use TaskOutput to check status."`。
- `timeout` 参数仍生效：后台任务超时后标记为 `timeout` 状态。

`BackgroundProcessHandle` 协议（不暴露 raw `asyncio.subprocess.Process`）：
```python
class BackgroundProcessHandle:
    async def poll(self) -> int | None: ...     # 检查是否结束
    async def read_chunk(self, size: int) -> bytes: ...  # 读一块数据（返回空表示 EOF）
    async def terminate(self) -> None: ...        # SIGTERM
    async def kill(self) -> None: ...             # SIGKILL
    async def wait(self) -> None: ...             # 等待退出
```

`SandboxExecutor.run_background()` 返回 `BackgroundProcessHandle`，未来切换到 Docker/容器沙箱时只需修改 `SandboxExecutor` 返回适配器即可。

#### A.2 BackgroundTaskManager

**定义**："background" = live run 内非阻塞，不是守护进程。所有后台任务在 AgentLoop 退出时终止，不跨 session/进程生存。

数据结构：
```
task_id -> TaskEntry {
    handle: BackgroundProcessHandle,
    tool_call_id: str,           # 原始 Bash tool call 的 id
    command: str,
    started_at: float,
    status: running | completed | failed | timeout | killed | orphaned,
    exit_code: int | None,
    stdout: str,
    stderr: str,
    output_truncated: bool,      # stdout/stderr 被截断时为 True
    reported: bool,              # 已通过 check_completed() 或 TaskOutput 返回给 agent
}
```

MAX_OUTPUT_BYTES = 64KB（可配置）。monitor 协程持续 drain pipe，超出上限时截断并标记 `output_truncated=True`。

**后台监控**：`register()` 时创建 `asyncio.create_task(self._monitor(task_id, entry, timeout))`，在同一 event loop 中运行。monitor 负责：
1. 持续读 stdout/stderr pipe（`read_chunk(4096)`），防止管道满导致子进程阻塞
2. 检查超时，超时后 SIGTERM → SIGKILL
3. 检测进程退出后更新 `exit_code`、status → `completed`/`failed`
4. 确认 `output_truncated` 标志

生命周期：
- **创建**：`AgentLoop.__init__` 构造时注入（与 `MemoryManager`、`SubAgentManager` 模式一致）。
- **工具访问**：`BashTool`、`TaskOutputTool`、`TaskStopTool` 通过回调注入（与 `TodoWriteTool` 模式一致）：
  ```python
  RunInBackgroundCb = Callable[[str, float | None], str]  # (cmd, timeout_seconds) -> task_id
  GetTaskCb = Callable[[str, bool, float], str]           # (task_id, block, timeout_seconds) -> output
  StopTaskCb = Callable[[str], str]                        # (task_id) -> final output
  ```
- **清理**：`AgentLoop._run()` 的 try/finally 中调用 `cleanup()`，清理超时可配置（`cleanup_timeout: float = 5.0` 秒）。

关键行为：
- AgentLoop 每次迭代开始时调用 `manager.check_completed()` → 返回新完成的、尚未报告的任务列表，标记 `reported=True` 防止重复注入。
- AgentLoop 主动拉取结果并构建 `role=user` 观测消息追加到 `messages`（不用 `role=tool`，因为原始 Bash tool_call 已被初始的 "Task started" 结果消费）。
  ```
  [user] [Background task bg_001 completed: exit_code=0, stdout_truncated=False]
  <64KB stdout content>
  ```
- `TaskOutput` 工具阻塞轮询时**只等目标 task**，不主动注入其他已完成任务。其他任务的完成结果在下次 AgentLoop 迭代开始时由 `check_completed()` 统一注入。
- 不跨 session 生存，不跨进程生存（与 Claude Code 行为一致）。

#### A.3 TaskOutput / TaskStop 工具

- `TaskOutput(task_id, block=True, timeout=30.0)`：获取任务输出。`block=True` 时非阻塞轮询（1s 间隔）直到 completed/failed/timeout/killed。`block=False` 时立即返回当前状态。超时后返回已收集的部分输出。阻塞期间只关注目标 task，不注入其他已完成任务。
- `TaskStop(task_id)`：发送 SIGTERM，等 3s，SIGKILL。返回最终输出。状态标记为 `killed`。
- `parallelizable = False`：两者都不参与 AgentLoop 的并行分组。
- 权限：`TaskOutput` = `WORKSPACE_READ` / `LOW`；`TaskStop` = `COMMAND_EXECUTE` / `MEDIUM`。
- 审批：两者都不需要额外审批（后台命令启动时已审批）。TaskStop 仅作用于当前 AgentLoop/session 内启动的任务。

**timeout 单位统一为秒（float）**：

| 位置 | 类型 | 默认值 |
|------|------|--------|
| BashInput.timeout | `float \| None` | `None`（无超时） |
| TaskOutput timeout | `float` | `30.0` |
| BackgroundTaskManager monitor timeout | `float \| None` | 由 Bash timeout 传入 |
| cleanup_timeout | `float` | `5.0` |
| RunInBackgroundCb timeout | `float \| None` | — |

### Part B: 会话持久化

#### B.1 持久化范围

持久化内容（仅功能性字段）：
```python
@dataclass
class SessionSnapshot:
    schema_version: str          # semver ("1.0")，major 不兼容拒绝，minor 兼容填充默认值
    session_id: str
    created_at: str
    updated_at: str
    messages: list[Message]
    mode: AgentMode
    todos: list[PlanItem]       # 从 AgentLoop._execution_todos 序列化，PlanItem 已有 to_dict()
    active_skills: list[str]    # 从 SkillRuntime 获取，需新增 public accessor
    run_id: str
    iteration: int
    runtime_fingerprint: dict   # 恢复时 warn 不匹配，不拒绝
```

`runtime_fingerprint` 字段：
```python
{
    "cwd": "/home/user/project",
    "model": "claude-opus-4-7",
    "provider": "anthropic",
    "agent_version": "0.1.0",
}
```

明确不持久化：
- LLM client（需要重新初始化）
- MCP server 连接（需要重新启动和发现）
- Background tasks（后台进程不跨 session 生存）
- WorkspacePolicy（重新从配置构建）
- `tool_call_count` / `edit_count`（纯统计数据）

#### B.2 存储格式

```
.asterwynd/sessions/          # CWD 相对路径
  <session_id>/
    snapshot.json              # SessionSnapshot JSON（不含 messages）
    messages.json              # 完整消息历史 list[dict]
```

- 目录在 `SessionStore.save()` 首次调用时 lazy 创建。
- JSON 格式（非 pickle），确保可读性和向前兼容。

**原子写入**：先写 `.tmp` 文件，再 `os.replace()` rename：
1. `snapshot.json.tmp` → `os.replace()` → `snapshot.json`
2. `messages.json.tmp` → `os.replace()` → `messages.json`

**损坏处理**：
- 两个文件都在 → 正常加载
- 只有一个文件（.tmp 残留）→ 报告 corruption error
- JSON 解析失败 → 报告 corruption error

#### B.3 保存时机

1. **回合保存**：AgentLoop 每次 `_run()` 结束（即每次用户输入得到完整回复后）保存一次。基于**整个 snapshot dict hash** 去重（覆盖 messages/mode/todos/skills/iteration 等所有字段变更）。可配置关闭：`config.session.auto_save: bool = True`。
2. **退出时保存**：AgentLoop 正常结束时保存最终快照。

保存触发位置在 `run()` 方法中（`_run()` 返回后），而非迭代循环内。因为 `_run()` 对应一次用户交互，按"用户回合"粒度保存的恢复语义最自然。

#### B.4 恢复入口

```bash
uv run asterwynd session resume <session_id>   # 恢复并进入交互 REPL
uv run asterwynd run --resume <session_id> "prompt"   # 单轮恢复
uv run asterwynd web --resume <session_id>            # Web 恢复
```

恢复流程（修正：总是重建当前 system prompt）：
1. 加载 `snapshot.json` + `messages.json`。
2. 正常构建 system prompt（当前的 mode policy、tool schemas、安全策略、skills）。
3. 过滤 snapshot.messages 中的旧 system 消息，只保留 user/assistant/tool 对话。
4. 追加恢复标记系统消息：`"## Session Resumed\nPrevious session <session_id> from 2026-07-09 ended at iteration 12.\n"`
5. 追加过滤后的对话历史。
6. 对比 `runtime_fingerprint`：cwd/model/provider/agent_version 不匹配时打印 warning（不拒绝恢复）。
7. 恢复 `AgentRuntimeState` mode、恢复 `PlanItem` todos、恢复 `SkillRuntime` active skills。
8. 进入正常交互循环。

`schema_version` 兼容策略：
- Major 不兼容 → 拒绝恢复，打印错误："Session schema vX.Y is incompatible with current vA.B."
- Minor 兼容 → 加载时填充默认值，正常恢复。

#### B.5 CLI 变更

使用 Typer sub-group：
```
asterwynd session list                # 列出可恢复会话（默认表格，--json 输出 JSON）
asterwynd session resume <session_id> # 恢复并进入交互 REPL
asterwynd session rm <session_id>     # 删除会话（需确认）
asterwynd session rm <session_id> -f  # 跳过确认删除
asterwynd run --resume <session_id> "prompt"
asterwynd web --resume <session_id>
```

`session list` 表格字段：`SESSION_ID`（截断 12 位）、`CREATED`、`UPDATED`、`MESSAGES`（消息数）、`MODE`。

### 子能力间的交互

- 后台任务在 session 保存时不杀，但不恢复。AgentLoop 退出时 finally 块统一清理所有活跃后台进程。
- 会话恢复后再启动后台任务时使用新的 BackgroundTaskManager 实例。
- Todo 列表持久化同时由 session save 受益。

## Goals / Non-Goals

- 不跨机器恢复会话（不支持远程 session sync）。
- 不支持后台任务的依赖管理（task A → task B 依赖）。
- 不持久化 LSP server 连接状态。
- 不持久化 embedding 索引状态。
- `--resume` 不支持恢复部分消息（不支持 --resume-from-iteration N）。
- 后台任务不跨 session/进程生存。

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
| Bash 工具 | 新增 run_in_background 参数，timeout 改为 float 秒 |
| SandboxExecutor | 新增 run_background() + BackgroundProcessHandle（含 read_chunk） |
| AgentLoop | 迭代开始注入 role=user 观测消息、_run() 结束 snapshot hash 去重保存、finally 清理后台进程、恢复时重建 system prompt |
| ToolRegistry | 新增 TaskOutput / TaskStop |
| CLI | 新增 --resume 和 session 子命令（list/resume/rm） |
| SkillRuntime | 新增 active_skill_names public property |
| PlanItem | 补充 from_dict() 静态方法（含基础校验） |
| Message | 复用 to_dict()/from_dict() 序列化 |
| Workspace safety | 后台命令仍通过 allowlist/denylist 检查 |
| 审批链路 | 后台命令在启动时走一次审批（不额外审批检查结果） |
| MemoryManager compact | 后台任务观测消息作为普通 user 消息参与 compact |
| MCP | 不影响 |
| Benchmark | 不影响（benchmark 不持久化、不使用后台任务） |
| TUI/Web | TUI 可选展示后台任务状态条 |

## Risks / Trade-offs

- [Risk] 后台进程可能在 AgentLoop 退出时未正确清理。Mitigation: `_run()` 的 try/finally 块中强制 SIGTERM → SIGKILL 清理所有活跃进程（cleanup_timeout 可配置，默认 5s）。
- [Risk] Session 恢复时消息格式不兼容（跨版本升级）。Mitigation: SessionSnapshot 包含 schema_version 字段，semver 策略：major 不兼容拒绝，minor 兼容填充默认值。
- [Risk] 自动保存 session 可能在频繁迭代时产生磁盘 I/O 压力。Mitigation: 基于整个 snapshot dict hash 去重，可配置关闭。
- [Risk] 后台命令大量输出导致内存压力。Mitigation: MAX_OUTPUT_BYTES=64KB 上限 + monitor 协程持续 drain pipe + output_truncated 标志。
- [Risk] 恢复时 runtime 环境变化（切换 model/升级 agent）。Mitigation: runtime_fingerprint 对比，不匹配时 warning 而非拒绝。
- [Risk] Session 文件写入中断导致损坏。Mitigation: temp file + os.replace() 原子写入，读取时检测配对文件和 JSON 完整性。

## Testing Strategy

- BackgroundTaskManager 单元测试：启动/状态/输出获取/超时终止/进程清理。用真实子进程（`sleep 0.5 && echo done` 等快速命令）。
- Bash 工具测试：run_in_background=True 返回 task_id、后台命令仍过安全门、timeout 为秒单位。
- TaskOutput/TaskStop 工具测试：block/非阻塞查询、终止运行中任务。
- SessionStore 单元测试：保存快照/恢复/损坏文件报错/不存在的 session/schema_version 兼容/原子写入/runtime_fingerprint mismatch warning。
- AgentLoop 集成：后台任务完成后注入 role=user 观测消息（真实子进程）、退出时清理进程、全 snapshot hash 去重保存。
- CLI 测试：--resume 参数、session list/resume/rm。

## Pre-Implementation Review

2026-07-10 grill-with-docs + Codex review 决策记录：

### 第一轮 grill-with-docs（15 项）

1. **BackgroundTaskManager 生命周期**：AgentLoop 构造函数注入，工具通过回调访问（与 TodoWriteTool 模式一致）。
2. **TaskOutput 阻塞行为**：只等目标 task，不主动注入其他已完成任务。
3. **结果注入时机**：AgentLoop 迭代开始前 + check_completed() 统一拉取。
4. **进程清理**：_run() try/finally 中执行，cleanup_timeout 可配置（默认 5s）。
5. **自动保存**：AgentLoop `run()` 方法中 `_run()` 返回后保存，每次用户输入得到完整回复后触发。全 snapshot hash 去重，不走 Hook。
6. **schema_version**：Semantic versioning —— major 拒绝，minor 填充默认值。
7. **CLI 结构**：Typer sub-group，session list/resume/rm，表格 + --json，rm 确认 + -f。
8. **SessionSnapshot**：去掉 tool_call_count 和 edit_count。
9. **TaskOutput/TaskStop 权限**：TaskOutput = WORKSPACE_READ/LOW；TaskStop = COMMAND_EXECUTE/MEDIUM。
10. **TaskOutput parallelizable = False**。
11. **结果注入消息**：关联原始 tool_call_id，Manager 标记"已报告"去重，AgentLoop 主动拉取。
12. **进程创建**：SandboxExecutor.run_background() + BackgroundProcessHandle 协议。
13. **SessionStore 路径**：CWD 相对 .asterwynd/sessions/，lazy 创建目录。
14. **恢复入口**：_run() 接收 resume_snapshot 参数。
15. **测试**：真实子进程做集成测试。

### 第二轮 Codex design review（10 项修正 + 6 项确认）

**High（4 项修正）**：
16. **tool_call_id 复用**：改用 `role=user` 观测消息注入，不重复消费 tool_call_id。
17. **异步桥接**：BackgroundTaskManager.register() 时 `asyncio.create_task(_monitor())` 协程监控。
18. **输出缓冲背压**：MAX_OUTPUT_BYTES=64KB + monitor 持续 drain pipe + output_truncated 标志。
19. **恢复 system prompt**：总是重建当前 system prompt，过滤旧 system 消息，只恢复对话。

**Medium（6 项确认）**：
20. **清理语义**："background" = live run 内非阻塞，不跨 session/进程。
21. **任务状态模型**：running/completed/failed/timeout/killed/orphaned + output_truncated 标志。
22. **timeout 单位**：全部统一为秒（float）。
23. **运行时指纹**：SessionSnapshot.runtime_fingerprint，恢复时 warn 不匹配。
24. **保存去重**：从 messages hash 改为整个 snapshot dict hash。
25. **文件原子性**：temp file + os.replace()，配对检测 + JSON 损坏报告。

**Deferred debt**：
- PlanItem.from_dict() 严格校验
- .asterwynd/ gitignore 策略
