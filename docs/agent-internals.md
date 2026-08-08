# Asterwynd Agent 内部机制讲解

本文档用"具体例子串起完整链路"的方式，逐一讲解 Asterwynd Agent 系统的核心子系统。每章都从一个实际场景出发，逐步推演代码执行路径，最后给出关键设计要点。

---

## 第一章：Agent 主循环

**文件**：`agent/loop.py`
**核心类**：`AgentLoop`

### 它在做什么

Agent 主循环是 Asterwynd 的"心跳"。它负责从收到用户输入到返回最终结果之间的全部调度工作：每轮迭代调用 LLM、解析工具调用、执行工具、拼接结果、压缩上下文，直到 LLM 不再需要调工具或达到上限。

### 实战例子：用户说"帮我把 README.md 里的 Python 版本从 3.10 改成 3.12"

#### 第 1 步：启动（`AgentLoop.run()`，`loop.py:493`）

```python
async def run(self, messages, on_event=None, trace_recorder=None,
              session_id=None, run_id=None, resume_snapshot=None):
```

`run()` 是外包装层，负责设置事件回调、追踪记录器，然后调用内部的 `_run()`。结束时的 `finally` 块做五件事：

1. 清理后台任务（`background_manager.cleanup()`）
2. 保存会话快照（`_save_session()`）——即使崩溃也会尽量存
3. 恢复之前的事件回调（防止嵌套 run 互相污染）
4. 恢复 sandbox sink（`set_sandbox_sink`）
5. flush cost ledger（把累积的 token 用量写入成本台账）

`_run()` 是真正的主循环。先判断是否恢复会话：

- **新会话**：触发 `hooks.on_run_started()`，记录 trace，发射 `run_started` 事件，让 `SkillRuntime` 根据首条用户消息自动匹配技能
- **恢复会话**（`resume_snapshot is not None`）：从快照中还原 mode、todos、skills、user_system_prompt，把历史消息拼回去，插入一条 `[Session resumed...]` 消息

#### 第 2 步：进入迭代循环（`loop.py:605`）

```python
for iteration in range(start_iteration, self.max_iterations):
    self._iteration = iteration
```

默认 `max_iterations=20`。每轮迭代做以下事情：

**2a. 检查后台任务完成情况**（line 608）

如果有后台任务（`Bash` 带 `run_in_background=true`）跑完了，注入一条 user 消息通知 agent。

**2b. 获取工具 Schema**（line 622）

```python
tool_schemas = self._select_tool_schemas(messages)
```

`_select_tool_schemas()` 决定给 LLM 看哪些工具。当 registry 配置了 selector 时走 Top-K 选择（query 由最近一条 user 消息 + 最近 3 个工具名构成，k=5，且核心稳定工具始终在前保证前缀缓存命中）；没有 selector 时才回退到 `get_all_schemas()`——后者会按当前 mode 过滤（PLAN 模式下只返回只读工具）。

**2c. 注入上下文**（line 624）

```python
contextualized = await self._messages_with_run_context(messages)
```

这就是第三章讲的上下文注入管线——把 P0/P1/P2/P4/P5 八层上下文源渲染成 TextBlock 列表，插入消息列表。详见第三章。

**2d. 调用 LLM**（line 626）

```python
response, streamed = await self._call_llm(messages=contextualized, tools=tool_schemas, on_event=on_event)
```

`_call_llm()` 决定走流式还是非流式：
- 流式：调用 `llm.stream_chat()`，逐 chunk 发射 `assistant_delta` 事件给 Web UI
- 非流式：直接调用 `llm.chat()`，等完整响应

随后触发 `hooks.after_llm_call()`，记录 token 用量到 cost ledger，并发射 `llm_response` 事件。

**2e. 判断 LLM 是否要调工具**（line 671）

```python
if not response.tool_calls:
    # 没有工具调用 → 对话结束
    if response.stop_reason == "max_tokens":
        # 输出被截断 → 先追加 assistant 文本，再追加 "Please continue" → 继续迭代
        if response.content:
            messages.append(Message(role="assistant", content=response.content))
        messages.append(Message(role="user", content="Please continue from where you left off."))
        continue
    # 正常结束 → 返回 RunResult(stop_reason=END_TURN)
```

如果 LLM 返回了文本但没有工具调用，说明它认为任务完成了。唯一的例外是 `stop_reason == "max_tokens"`——LLM 的输出被 token 上限截断了，此时先把已产生的 assistant 文本追加进历史，再追加一条 "Please continue" 让 LLM 接着输出。

#### 第 3 步：工具执行（三阶段）

当 LLM 返回了 `tool_calls` 时，进入工具执行管道：

**Phase 1 — 预处理**（line 707）：遍历每个 `ToolCallDelta`：
1. 解析 JSON arguments → `ToolCall` 对象
2. 查 `ToolRegistry` 找对应 `Tool` 实例
3. 调用 `ModePolicy.decide_tool()` 判断权限
4. 如果需要审批 → 调 `ApprovalHandler.request_approval()`，等待用户确认
5. 审批被拒 → 标记 `pre_denied_result`，后续跳过执行

**Phase 2 — 执行**（line 847）：`_execute_tool_calls()` 并行执行：
- `parallelizable=True` 的连续工具 → 用 `asyncio.gather()` 并发
- 串行工具、**审批待决**（`requires_approval`）或审批被拒的 → 逐个处理（被拒的直接返回错误消息）

**Phase 3 — 后处理**（line 850）：按原始顺序遍历结果：
1. `trace_recorder.record_tool_call()` / `record_tool_result()`
2. 发射 `tool_call` 和 `tool_result` 事件给 Web UI
3. 检查技能激活（如 `ActivateSkillTool` 触发了技能）
4. 将 `tool_result_message` 追加到 `messages` 列表

#### 第 4 步：Compact 检查（line 941）

```python
compacted = await self.memory.compact_if_needed(messages, iteration=self._iteration)
```

每轮结束后检查 token 是否达到压缩阈值：默认 `max_tokens − 15_000`（预留 15K 给 LLM 输出；默认 100K 预算即 85K 触发），可配置 `compact_trigger_tokens` 覆盖。详见第三章 3.3。

#### 第 5 步：循环回到第 2 步

LLM 收到工具结果后，下一轮迭代会基于结果继续推理——可能继续调工具，也可能输出最终答案。

在这个例子中，典型的迭代序列是：

```
迭代 1: LLM 返回 Read("README.md")       → 执行 Read → 结果追加到消息
迭代 2: LLM 返回 Edit(改 Python 版本)     → 执行 Edit → 结果追加
迭代 3: LLM 返回 InspectGitDiff()         → 执行 diff → 结果追加
迭代 4: LLM 返回 "已经把 Python 版本从 3.10 改成 3.12 了"
        → 无 tool_calls → return RunResult(END_TURN)
```

#### 第 6 步：达到 max_iterations

如果 20 轮还没结束，返回 `RunResult(stop_reason=MAX_ITERATIONS)`。这是一种保护措施，防止 agent 陷入死循环。

### 完整流程图

```
run(messages)
  │
  ├─ 新会话? → hooks.on_run_started() + SkillRuntime.begin_run()
  └─ 恢复会话? → 还原 mode/todos/skills/messages
  │
  ▼
for iteration in 0..max_iterations:
  │
  ├─ 检查后台任务完成 → 注入通知
  ├─ tool_schemas = _select_tool_schemas(messages)  (Top-K / mode 过滤)
  ├─ contextualized = _messages_with_run_context(messages)  (P0/P1/P2/P4/P5 注入)
  ├─ hooks.before_iteration()
  ├─ response = await _call_llm(messages, tools)
  ├─ hooks.after_llm_call()
  ├─ 发射 llm_response 事件
  │
  ├─ 无 tool_calls?
  │   ├─ stop_reason == "max_tokens" → 追加 assistant 文本 + "Please continue" → continue
  │   └─ 否则 → return RunResult(END_TURN)
  │
  ├─ Phase 1: 预处理 (解析 args → 查 tool → 权限决策 → 审批)
  ├─ Phase 2: 执行 (并行/串行分组)
  ├─ Phase 3: 后处理 (trace + event + 追加 tool_result)
  │
  └─ memory.compact_if_needed()  (max_tokens − 15_000 阈值检查)
  │
  ▼
return RunResult(MAX_ITERATIONS)  // 保底
```

### 关键设计要点

| 要点 | 说明 |
|------|------|
| **max_iterations=20** | 防止死循环，20 轮足以完成大多数任务 |
| **max_tokens 自动续接** | LLM 输出被截断时不会丢上下文，而是自动让 LLM 继续 |
| **finally 块保底** | 即使崩溃也尝试保存会话、清理后台任务 |
| **流式 vs 非流式** | 根据 provider 能力自动选择；流式模式下 Web UI 实时看到 LLM 输出 |
| **事件回调解耦** | AgentLoop 本身不关心事件发给谁——CLI、Web、trace 都可以独立订阅 |

---

## 第二章：工具系统

**文件**：`agent/tools/base.py`、`agent/tools/registry.py`、`agent/tools/sandbox/`（包）、`agent/tool_permissions.py`、`agent/workspace_policy.py`、`agent/run_config.py`

### 它在做什么

工具系统让 LLM 能够"动手"——读文件、改代码、搜代码、跑命令。它的核心职责是：定义工具接口、注册管理、权限决策、在受控环境中执行。

### 实战例子：EditTool 从 LLM 调用到实际修改文件

假设 LLM 返回了这个 tool_call：

```json
{
  "id": "call_abc123",
  "name": "Edit",
  "arguments": "{\"file_path\": \"/Users/kaixing/code/asterwynd/README.md\", \"old_string\": \"Python 3.10\", \"new_string\": \"Python 3.12\"}"
}
```

#### 第 1 步：工具定义（`base.py:37`）

每个工具继承 `Tool` ABC：

```python
class Tool(ABC):
    name: str                    # "Edit"
    description: str             # LLM 看到的说明
    parameters: dict             # JSON Schema
    read_only: bool = False      # 是否只读（legacy 兼容标志）
    dangerous: bool = False      # 是否危险（legacy 兼容标志）
    parallelizable: bool = False # 是否可与其他工具并发
    allowed_modes: tuple | None  # 允许在哪些 mode 下运行
    permission: ToolPermission | None = None   # 权限元数据（内置工具显式设置）

    async def execute(self, **kwargs) -> str | list[ContentBlock] | ToolResult:
        ...  # 子类实现
```

`get_permission()` 优先返回显式设置的 `permission` 字段（非 None 即短路）；`read_only` / `dangerous` 只是当 `permission` 为 None 时才生效的 legacy 兜底推断：

| 兜底属性（仅 permission 为 None 时） | 推断结果 |
|------|---------|
| `read_only=True` | `LOW` 风险 + `WORKSPACE_READ` 能力 |
| `dangerous=True` | `HIGH` 风险 + `COMMAND_EXECUTE` 能力 |
| 默认（写操作） | `MEDIUM` 风险 + `WORKSPACE_WRITE` 能力 |

内置工具（Bash/Edit/Write 等）都已显式设置 `permission`。EditTool 是 `WORKSPACE_WRITE_PERMISSION`——`MEDIUM` 风险，属于 BUILD 模式允许的写操作。

#### 第 2 步：注册（`registry.py:19`）

`ToolRegistry` 是一个 dict 封装：

```python
class ToolRegistry:
    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get_all_schemas(self) -> list[dict]:
        return [
            tool.get_schema()
            for tool in self._tools.values()
            if self.mode_policy.is_tool_allowed(tool)   # mode 过滤
            and self._is_governance_visible(tool)        # 治理可见性过滤
        ]
```

`get_all_schemas()` 返回给 LLM 的工具列表——PLAN 模式下只返回只读工具，BYPASS 模式下全部可见；此外 `_is_governance_visible()` 还会隐藏被 lifecycle 移除或已降级的 MCP 工具。

EditTool 在 `build_default_tool_registry()` 中注册，BUILD 模式下可见。

#### 第 3 步：权限决策（`run_config.py:97`）

当 AgentLoop 的 Phase 1 执行到：

```python
decision = self.tool_registry.mode_policy.decide_tool(tool)
```

`ModePolicy.decide_tool()` 的决策链（5 级检查，任一拦截即返回）：

```
1. allowed_modes 检查
   → Edit.allowed_modes 未设置 → 通过

2. deny_tools_by_mode 检查
   → 查当前 mode 的拒绝列表 → Edit 不在 BUILD 的拒绝列表 → 通过

3. profile.denied_tools 检查
   → 查权限配置的拒绝列表 → Edit 不在 → 通过

4. 能力集检查
   → Edit 的 WORKSPACE_WRITE 是否在 BUILD profile 的允许能力中 → 是 → 通过

5. 风险等级决策
   → Edit 的 MEDIUM 风险 vs build_default 的 auto_approve_max_risk (MEDIUM)
   → MEDIUM <= MEDIUM → 命中自动批准 → 返回 ALLOW
```

对 Edit 工具，`build_default` profile 的 `auto_approve_max_risk=MEDIUM`，Edit 风险也是 `MEDIUM`，因此最终返回 **`ALLOW`（自动批准）**，不产生审批请求。

只有当工具风险超过 `auto_approve_max_risk` 时才返回 `REQUIRE_APPROVAL`。例如 `Bash` 是 `COMMAND_EXECUTE` / `HIGH` 风险，超过了 build 的自动批准上限 `MEDIUM`。此时 AgentLoop 调 `ApprovalHandler.request_approval()`：

- **CLI 模式**：`CliApprovalHandler` 先向 stderr 打印 `Approval required:` + JSON 摘要，再用 `input("Approve? [y/N] ")` 询问
- **Web 模式**：`WebApprovalHandler` 通过 WebSocket 发给浏览器，弹审批对话框
- **默认（无交互）**：`FailClosedApprovalHandler` 直接拒绝

用户点"批准"后，`approval_granted=True`，进入执行阶段。BYPASS 模式使用 `bypass_default` profile（`auto_approve_max_risk=HIGH`），因此所有命令自动执行、不经过审批。

#### 第 4 步：执行（`registry.py:137`）

```python
async def execute(self, tool_call, *, approval_granted=False):
    tool = self._tools[tool_call.name]
    decision = self.mode_policy.decide_tool(tool)

    if decision.type is DENY:
        return ToolResult(text="...", error_type="permission_denied")
    if decision.type is REQUIRE_APPROVAL and not approval_granted:
        return ToolResult(text="...", error_type="approval_required")

    result = await tool.execute(**tool_call.arguments)
    # 非 ToolResult 的返回值会被包装为 ToolResult
    return result
```

权限再次校验（防止绕过），然后调用 EditTool 的实际实现。返回值统一为 `ToolResult`（含 `text` 与 `error_type` 字段）。

#### 第 5 步：沙箱（仅 dangerous 工具）

对于 `ReadTool`、`EditTool`、`WriteTool` 等文件操作工具，沙箱不是必须的——它们在 Python 进程中直接执行。

对于 `BashTool`（`dangerous=True`），执行会经过 `agent/tools/sandbox/` 包（`ExecutionBackend` 协议）：

```
BashTool.execute()
  → ProcessBackend.run(cmd, timeout=30s)     # 默认超时 30 秒
    → asyncio.create_subprocess_shell()
      → 等待进程退出（带超时）
      → 返回 SandboxResult(exit_code, stdout, stderr, duration_ms,
                           timed_out, oom_killed, degraded)
```

沙箱包提供 `ProcessBackend`（子进程）和 `DockerBackend`（容器）两种实现，由 `build_sandbox_from_config()` 按配置构造。

同时 `WorkspacePolicy` 会在 Bash 执行前检查命令：
- 拒绝列表（正则）：`rm -rf /`、`chmod 777`、`curl ... | sh` 等 58 个唯一危险模式
- 路径策略：只允许在 workspace root 内操作

### 完整流程图

```
LLM 返回 tool_call: {name: "Edit", arguments: {...}}
  │
  ▼
AgentLoop Phase 1: 预处理
  ├─ JSON 解析 arguments → ToolCall 对象
  ├─ registry.get_tool("Edit") → Tool 实例
  ├─ ModePolicy.decide_tool(Edit)
  │   ├─ allowed_modes? → 通过
  │   ├─ deny list? → 通过
  │   ├─ capabilities? → 通过
  │   └─ risk level? → MEDIUM <= auto_approve(MEDIUM) → ALLOW（自动批准）
  │
  ├─ 对比：如果是 Bash（HIGH 风险）
  │   └─ risk level? → HIGH > auto_approve(MEDIUM) → REQUIRE_APPROVAL
  │       └─ ApprovalHandler.request_approval()
  │           ├─ CLI: 终端 stderr 打印摘要 → input("Approve? [y/N] ")
  │           ├─ Web: WebSocket → 浏览器弹窗 → 用户点击批准
  │           └─ FailClosed: 直接拒绝
  │       └─ approval_granted=True
  │
  ▼
AgentLoop Phase 2: 执行
  ├─ parallelizable? → 分组并行/串行（审批待决/被拒进串行组）
  ├─ registry.execute(tool_call, approval_granted=True)
  │   ├─ 再次权限校验（防绕过）→ ToolResult(text, error_type)
  │   └─ tool.execute(**arguments) → 实际修改文件
  └─ (如果是 Bash) ProcessBackend 子进程中执行（默认超时 30s）
  │
  ▼
AgentLoop Phase 3: 后处理
  ├─ trace_recorder.record_tool_call() / record_tool_result()
  ├─ on_event("tool_call") / on_event("tool_result")
  ├─ messages.append(tool_result_message(id, result))
  └─ tool_calls_made.append(ToolCallMade(name, arguments, result))
```

### 关键设计要点

| 要点 | 说明 |
|------|------|
| **五级权限决策链** | allowed_modes → deny_tools → profile.denied → capabilities → risk level，层层拦截 |
| **审批与执行分离** | 审批阶段只看 Tool 元数据，不执行；执行阶段再次校验权限 |
| **并行分组** | 连续的 `parallelizable=True` 工具用 `asyncio.gather` 并发，减少往返延迟 |
| **模式过滤** | `get_all_schemas()` 按 mode 过滤——LLM 根本看不到无权使用的工具 |
| **WorkspacePolicy** | 双重保护：路径策略（不越界）+ 命令拒绝列表（不跑危险命令） |
| **Edit vs Write** | Edit 做精确字符串替换（需要 old_string 精确匹配），Write 做整体覆写（仅用于创建新文件） |

---

## 第三章：上下文管理

### 3.1 项目指令发现与注入（ASTER.md）

**文件**：`agent/context/sources.py`
**核心类**：`AsterMdSource`

#### 它在做什么

ASTER.md 是 Asterwynd 的项目指令文件体系。它让每个项目（甚至每个子目录）都能告诉 agent "在这个目录下工作时要遵守什么规则"。运行时，agent 从 git 根目录向下遍历到当前工作目录，收集所有 ASTER.md 和 ASTER.local.md，按优先级拼接，注入到 LLM 的系统消息里。

#### 文件体系：四层结构

```
AGENTS.md   ← 人工维护的权威源（只有一个入口）
    │
    │  @AGENTS.md  (一行重定向，兼容 Claude Code)
    ▼
CLAUDE.md   ← 薄重定向文件，让 Claude Code 也能读到 AGENTS.md
    │
    │  /init 命令从 AGENTS.md + CLAUDE.md 导入 + 项目检测
    ▼
ASTER.md    ← 生成的指令文件（/init 命令产生）
ASTER.local.md ← 用户本地覆盖（gitignore，不提交）
```

**关键事实**：运行时 `AsterMdSource` 只扫描 `ASTER.md` 和 `ASTER.local.md`。AGENTS.md 和 CLAUDE.md 只在运行 `/init` 命令时作为导入源使用。

#### 实战例子：一个 monorepo，两个 ASTER.md

假设项目结构：

```
~/code/myproject/           ← git root
├── ASTER.md                ← "所有 Python 文件用 Black 格式化"
├── src/
│   ├── api/
│   │   ├── ASTER.md        ← "API 路由使用 FastAPI 的 APIRouter"
│   │   └── ASTER.local.md  ← "本地调试时关闭 rate limit"
│   │   └── main.py
```

当前工作目录 `cwd = ~/code/myproject/src/api/`。

#### 第 1 步：找上界（`_find_git_root`）

```python
def _find_git_root(path: Path) -> Path | None:
    current = path.resolve()
    while True:
        if (current / ".git").exists():
            return current          # → ~/code/myproject
        parent = current.parent
        if parent == current:
            return None
        current = parent
```

从 `src/api/` 向上走，在 `myproject/` 找到 `.git` → `upper_bound = ~/code/myproject`。

#### 第 2 步：收集文件（`_collect_aster_files`）

```python
# 构建目录链：从 upper_bound 到 cwd
chain = [myproject, myproject/src, myproject/src/api]  # root first

# 每个目录检查 ASTER.md 和 ASTER.local.md
result = [
    (myproject/ASTER.md,       myproject),         # 根
    (myproject/src/api/ASTER.md,      src/api/),   # 子目录
    (myproject/src/api/ASTER.local.md, src/api/),  # 本地覆盖
]
```

注意 `src/` 目录没有 ASTER.md，所以跳过了。`src/` 目录中也不会收集来自 `src/` 的文件。

#### 第 3 步：渲染（`_render_aster_md`）

```markdown
## ASTER.md (项目根)
所有 Python 文件用 Black 格式化

## ASTER.md (src/api/)
API 路由使用 FastAPI 的 APIRouter

## ASTER.local.md (src/api/)
本地调试时关闭 rate limit

> 以上 ASTER.md 文件中，越靠近当前工作目录的指令优先级越高。
> 如有冲突，以靠近工作目录的为准。
```

每个文件标注了来源路径。`项目根` 表示该文件在 `upper_bound` 目录。

#### 第 4 步：截断保护

两层限制：

1. **单文件上限**：`MAX_ASTER_SIZE_BYTES = 32 KiB`。超过 32 KiB 的单个文件被跳过并警告。
2. **总上限**：所有文件拼接后不超过 32 KiB。超限时**从祖先开始丢弃**（reverse 遍历），优先保留最靠近 cwd 的文件。

这意味着：根目录写了几十 KiB 的规则，子目录只有 2 KiB → 根目录被截断，子目录保留。

#### 第 5 步：注入到上下文

`AsterMdSource` 是 P1 优先级、`critical=True`。在上下文注入管线中，它排在系统提示词（P0）之后，且永远不会被 token 预算系统截断。

### 3.2 上下文注入管线

**文件**：`agent/context/builder.py`、`sources.py`

#### 它在做什么

每次 LLM 调用前，`ContextBuilder` 把多个上下文源按优先级渲染并拼成一条 system 消息注入到消息列表。这是一个"每次必做"的操作——agent 的每轮迭代都用最新的上下文。

#### 八层上下文源

```python
# loop.py:1339 — _make_default_context_builder()
builder = ContextBuilder(total_budget=injection_budget)
builder.register(SystemPromptSource())       # P0 — 系统提示词
builder.register(AsterMdSource())            # P1 — ASTER.md
builder.register(MemoryIndexSource(...))     # P2 — 持久记忆索引
builder.register(SkillIndexSource(...))      # P4 — 可用技能列表
builder.register(SkillActiveSource(...))     # P4 — 已激活技能内容
builder.register(PlanModeSource())           # P5 — Plan 模式提示
builder.register(PlanningStateSource(...))   # P5 — 计划状态
builder.register(TodoSource(...))            # P5 — 执行进度 Todo
```

注入预算计算：`injection_budget = min(20_000, context_window × 20%)`。例如 context_window=200K → 注入预算 = 20,000 tokens。

#### 实战例子：Token 不够时怎么裁

假设渲染后各层 token 消耗：

```
P0  SystemPrompt  : 1,500 tokens  [critical]
P1  AsterMd       : 3,000 tokens  [critical]
P2  MemoryIndex   : 2,000 tokens
P4  SkillIndex    : 2,500 tokens
P4  SkillActive   : 2,500 tokens
P5  PlanMode      : 2,500 tokens
P5  PlanningState : 1,500 tokens
P5  Todo          : 1,000 tokens
─────────────────────────────────
Total:             16,500 tokens  → 在 20,000 预算内，全部保留
```

如果某次渲染后 total 变成了 22,000 tokens（比如 ASTER.md 很大），超过 20,000 预算：

```python
# builder.py:132 — _apply_budget()
while total_tokens > self._total_budget and layers:
    trim_idx = self._find_trimmable_index(layers)  # 从后往前找第一个非 critical 且非 cacheable
    # → 找到 P5 Todo (最末尾的普通层)
    trimmed = self._truncate_tail(content, excess)
    # → 从 Todo 的尾部裁掉 2,000 tokens 等价字符
    if trimmed:
        layers[trim_idx] = trimmed   # Todo 被裁短了
    else:
        layers.pop(trim_idx)          # Todo 整层被移除
```

裁切顺序：**从低优先级的尾部开始**。先裁 Todo（P5），不够再裁 PlanningState（P5），再裁 SkillActive（P4）……`critical` 层（P0 系统提示词、P1 ASTER.md）和 `cacheable` 层（P2 MemoryIndex）都**永远不会被裁**——它们构成稳定的前缀供缓存命中。

#### 注入到消息列表

```python
# loop.py:1300 — _messages_with_run_context()
ctx = BuildContext(cwd=..., mode=..., context_window=..., ...)
blocks = await self.context_builder.build_blocks(ctx)   # 每层渲染为一个 TextBlock
context_message = Message(role="system", content=blocks)
return [*messages[:insert_at], context_message, *messages[insert_at:]]
```

渲染结果以 **TextBlock 列表** 的形式注入到一条 `system` 消息里，插入到已有 system 消息之后、第一条非 system 消息之前。cacheable 层（P0/P1/P2）的 TextBlock 会带上 cache 标志，作为 Anthropic `cache_control` 的断点。

### 3.3 上下文压缩（Compact）

> 详见前文的 compact 专题讲解。此处简述位置关系。

| 子章节 | 触发方式 | 时机 | 作用 |
|--------|---------|------|------|
| 3.1 ASTER.md | 每轮注入 | LLM 调用前 | 告诉 agent 项目规则 |
| 3.2 注入管线 | 每轮注入 | LLM 调用前 | 组装完整上下文 |
| 3.3 Compact | 触发式（默认 `max_tokens − 15_000`，可配置 `compact_trigger_tokens`） | 每轮结束后 | 压缩对话历史 |

三者合在一起，覆盖了"agent 看到什么上下文"这个核心问题的完整答案。

---

## 第四章：LLM 对接

**文件**：`agent/llm.py`、`openai_llm.py`、`anthropic_llm.py`

### 它在做什么

LLM 对接层在 Agent 和模型 API 之间做适配：统一的 `LLM` 协议 → `BaseLLM` 公共基类（httpx 连接池、SSE 流解析、超时策略）→ 两个具体 Provider（OpenAI / Anthropic）。

### 核心数据模型

```python
@dataclass
class LLMResponse:
    content: Optional[str]              # 文本回复
    tool_calls: list[ToolCallDelta]     # 工具调用列表（有默认工厂）
    stop_reason: Optional[str]          # "end_turn" | "max_tokens" | ...
    reasoning_content: Optional[str]    # 推理过程（o1 等模型）
    usage: Optional[Usage]              # token 用量（input/output）

@dataclass
class LLMStreamEvent:
    type: Literal["assistant_delta", "complete"]
    delta: str         # 增量文本（流式）
    content: str       # 累积文本（流式）
    stop_reason: Optional[str]
    response: Optional[LLMResponse]  # 仅在 complete 事件中非空
```

### 实战例子：一次流式 chat 的完整过程

假设 OpenAI provider，`stream=True`，用户说"帮我写一个 hello world"。

#### 第 1 步：AgentLoop 调用

```python
response, streamed = await self._call_llm(messages, tools, on_event)
```

`_call_llm()` 判断 `_should_stream_llm()` → True → 调 `llm.stream_chat()`。

#### 第 2 步：BaseLLM 发送请求

```python
# BaseLLM._get_client() — 懒初始化 httpx.AsyncClient
client = httpx.AsyncClient(
    headers={"Authorization": "Bearer sk-...", ...},
    timeout=httpx.Timeout(60.0, read=60.0),  # 流式用 60s read timeout
)
# BaseLLM._stream_events() — SSE 解析
async with client.stream("POST", url, json=payload) as response:
    async for line in response.aiter_lines():
        if line.startswith("data: "):
            data = json.loads(line[6:])
            yield event_type, data
```

非流式用 `read=180.0`（180 秒），因为大响应可能很长时间才返回。

#### 第 3 步：Provider 处理流事件

OpenAI 的 `stream_chat()` 实现：

```python
# OpenAI SSE 流中没有 "done" 事件类型；_stream_chat_impl 忽略 event_type，
# 在 _stream_events 迭代结束后统一 yield complete
async for _event_type, data in self._stream_events(url, payload):
    delta = data["choices"][0]["delta"]
    yield LLMStreamEvent(
        type="assistant_delta",
        delta=delta.get("content", ""),
        content=accumulated_content,
    )
yield LLMStreamEvent(
    type="complete",
    response=LLMResponse(content=..., tool_calls=..., stop_reason=...),
)
```

每个 delta 事件都通过 `on_event("assistant_delta", ...)` 实时推给 Web UI，所以用户在浏览器里可以看到 LLM 逐字输出。

#### 第 4 步：多模态处理

发送图片时，`Message.content` 是 `[TextBlock, ImageBlock]` 列表。Provider 需要将这个结构转换成 API 期望的格式。

**视觉模型检测**（`llm.py:147-168`，`VISION_MODEL_PREFIXES` / `supports_vision` / `vision_mode`）：

```python
VISION_MODEL_PREFIXES = ("gpt-4o", "gpt-4.1", "gpt-5", "claude-", "gemini-")

def vision_mode(model: str) -> str:
    return "vision" if model.startswith(VISION_MODEL_PREFIXES) else "try_vision"
```

- `vision`：已知视觉模型，直接发送图片
- `try_vision`：未知模型，先尝试发送图片；如果返回 400 错误则自动去掉图片重试（非流式 `chat()` 用内嵌的 `status_code == 400` 分支手动重试；流式 `stream_chat()` 用 `except` + `_is_400_error()` 兜底重试；没有独立的 `NonStreamingRetry` 类）

### 完整流程图

```
AgentLoop._call_llm(messages, tools)
  │
  ├─ 流式? → llm.stream_chat()
  │   ├─ httpx.AsyncClient.stream("POST", ...)
  │   ├─ SSE 逐行解析 ("data: ...", "event: ...")
  │   ├─ yield LLMStreamEvent(type="assistant_delta", delta="你")
  │   ├─ on_event("assistant_delta") → Web UI 实时渲染
  │   ├─ yield LLMStreamEvent(type="assistant_delta", delta="好")
  │   └─ yield LLMStreamEvent(type="complete", response=...)
  │
  └─ 非流式? → llm.chat()
      ├─ httpx.AsyncClient.post(...)
      ├─ read_timeout=180s（大响应容忍）
      └─ return LLMResponse(content=..., tool_calls=...)
  │
  ▼
AgentLoop 得到 LLMResponse
  ├─ content → 文本回复
  ├─ tool_calls → 进入工具执行管道
  └─ stop_reason="max_tokens" → 追加续接提示
```

### 关键设计要点

| 要点 | 说明 |
|------|------|
| **Protocol 抽象** | `LLM` 只是一个 `async chat()` 签名，换 provider 不需要改 AgentLoop |
| **懒初始化 httpx 客户端** | `_get_client()` 带 asyncio.Lock，只在首次使用时创建 |
| **流式 read timeout=60s vs 非流式=180s** | 流式 chunk 间隔短，非流式大响应可能超时 |
| **try_vision 降级** | 未知模型收到图片返回 400 时，自动移除图片重试 |
| **SSE 容错** | JSON 解析失败的行被跳过，不会中断整个流 |
| **日志脱敏** | `sanitize_payload_for_logging()` 把 base64 图片替换为 `[image data omitted]` |

---

## 第五章：消息与记忆

### 5.1 消息模型

**文件**：`agent/message.py`

#### 数据结构

```python
@dataclass
class Message:
    role: Literal["system", "user", "assistant", "tool"]
    content: str | list[ContentBlock]   # 纯文本 或 多模态内容块列表
    tool_call_id: Optional[str]         # tool 消息的回溯 ID
    reasoning_content: Optional[str]    # 推理过程
    tool_calls: list                     # assistant 消息的工具调用列表

# 内容块
TextBlock(text="...", cache=False)          # type 固定为 "text"，非构造参数
ImageBlock(image_url=ImageUrl(url="...", detail="auto"), file_path="/tmp/img.png")
```

`content` 可以是纯字符串（简单文本）或 content blocks 列表（多模态）。`tool_calls` 存储 assistant 消息中包含的 `ToolCallDelta` 列表——这是 LLM API 要求的 tool_call ↔ tool_result 配对的基础。`TextBlock.cache` 用于标记可作为 Anthropic `cache_control` 断点的稳定前缀层。

#### 序列化

```python
msg.to_dict()   # → {"role": "user", "content": "...", ...}
msg.from_dict(d)  # 反向还原，包括深层嵌套的 ContentBlock 和 ToolCallDelta
```

`to_dict()` 只在字段非 None / 非空时写入（`tool_call_id`、`reasoning_content`、`tool_calls`），不会输出 null 字段。序列化用于会话持久化（`messages.json`）和 WebSocket 传输。

### 5.2 Token 计数

**文件**：`agent/memory/manager.py:24-34`（两级 `_count_tokens`）、`agent/message.py:77-87`（`count_tokens_for_content`）

两级策略：

```python
# 第一级：tiktoken 精确计数（agent/memory/manager.py）
try:
    import tiktoken
    _enc = tiktoken.get_encoding("cl100k_base")
    def _count_tokens(text: str) -> int:
        return len(_enc.encode(text))
except ImportError:
    # 第二级：字符数 / 4 估算
    def _count_tokens(text: str) -> int:
        return len(text) // 4
```

图片 token 按固定 1,000 token/张估算（`agent/message.py:86`，`count_tokens_for_content` 中对 `ImageBlock` 的处理）。

### 5.3 跨会话持久记忆

**文件**：`agent/memory/persistent.py`
**核心类**：`PersistentMemory`

#### 它在做什么

`PersistentMemory` 让 agent 在会话之间"记住"东西。它兼容 Claude Code 的记忆格式，存储在 `~/.asterwynd/projects/<project-hash>/memory/` 下。

#### 四类记忆

| 类型 | 用途 | 例子 |
|------|------|------|
| `user` | 用户角色、偏好、知识背景 | "用户是后端工程师，偏好用 uv run" |
| `feedback` | 用户给出的反馈和纠正 | "用户说不喜欢用 class 风格，偏好函数式" |
| `project` | 项目约束、截止日期等 | "v2.0 必须在 8 月底前发布" |
| `reference` | 外部资源指针 | "监控面板: https://grafana.example.com/d/xxx" |

#### 实战例子：agent 学会用户的偏好

**会话 1**：用户说"以后都用 `uv run pytest -q` 跑测试，不要用 `pytest` 直接跑"

agent 调用 `SaveMemory` 工具：

```python
memory.save(
    type="feedback",
    name="use-uv-run-pytest",
    description="用户偏好使用 uv run pytest -q 而不是直接调用 pytest",
    body="用户明确表示测试命令要用 `uv run pytest -q`。**Why:** uv 管理依赖更可控。**How to apply:** 每次需要跑测试时，使用 `uv run pytest -q` 命令。"
)
```

`save()` 做的事：

1. 验证 type 和 name（name 必须是 kebab-case）
2. 在 `~/.asterwynd/projects/<hash>/memory/` 下写 `use-uv-run-pytest.md`，带 YAML frontmatter
3. 更新 `MEMORY.md` 索引，追加一行：`- [use-uv-run-pytest](use-uv-run-pytest.md) — 用户偏好使用 uv run pytest -q 而不是直接调用 pytest`

**会话 2**（第二天）：用户新开一个会话，问"帮我跑一下测试"

1. `MemoryIndexSource.render()` → `PersistentMemory.load_summary()`，生成按 importance 排序的约 50 token 全局摘要（不是原始 MEMORY.md 索引）
2. 摘要作为 P2 上下文注入到 system 消息中：

```
## Project Memory
Summary of persistent memories from prior sessions. Use SearchMemory to
semantically retrieve specific entries.
---
- use-uv-run-pytest — 用户偏好使用 uv run pytest -q 而不是直接调用 pytest
---
```

3. agent 看到这条记忆，知道要调用 `SearchMemory` 获取完整内容
4. agent 调用 `SearchMemory(...)` → 拿到完整 body → 用 `uv run pytest -q` 跑测试

#### 存储格式

```markdown
---
name: use-uv-run-pytest
description: 用户偏好使用 uv run pytest -q 而不是直接调用 pytest
metadata:
  type: feedback
---

用户明确表示测试命令要用 `uv run pytest -q`。
**Why:** uv 管理依赖更可控。
**How to apply:** 每次需要跑测试时，使用 `uv run pytest -q` 命令。
```

每一条记忆一个文件，`MEMORY.md` 是索引。支持 Claude Code 格式，所以两边共享记忆。

#### 关键保护

- **索引截断**：`MAX_INDEX_LINES=200`、`MAX_INDEX_BYTES=25,000`。超大索引自动截断并警告。
- **路径安全**：记忆名强制 kebab-case（`_validate_name`，正则 `^[a-z0-9-]+$`），索引解析时过滤 `..` 防目录穿越。
- **项目隔离**：不同项目用 SHA256 hash 区分，不会串。

---

## 第六章：子代理系统

**文件**：`agent/subagent/manager.py`
**核心类**：`SubAgentManager`

### 它在做什么

子代理系统让父 agent 能把独立任务派发给受限的子 agent 并行执行。每个子 agent 是一个独立的 `AgentLoop` 实例，有自己的工具注册表、消息列表和运行状态。

### 实战例子：父 agent 派子 agent 去搜索 TODO

假设用户在修一个大型项目，父 agent 想知道"整个项目里有哪些 TODO 注释需要处理"。与其自己一个一个搜，不如派一个子 agent：

```
用户: "帮我整理一下项目里所有的 TODO 注释，分个类"
父 agent: 创建子 agent "todo-scanner"，派它去搜索
子 agent: 独立搜索、分析、汇总 → 回报结果
父 agent: 根据结果生成分类报告
```

#### 第 1 步：创建子 agent（`manager.py:175`）

父 agent 调用 `CreateSubagentTool`，触发：

```python
def create_subagent(self, *, name, description="", mode=None):
    requested_mode = self._parent_mode() if mode is None else parse_agent_mode(mode)
    effective_mode = self._clamp_mode(requested_mode)
    subagent_id = uuid.uuid4().hex[:8]  # → "a1b2c3d4"
    session = SubagentSessionRecord(
        subagent_id=subagent_id,
        name=name,              # 如 "todo-scanner"
        description=description,
        mode=effective_mode,    # READ_ONLY（被父模式钳位）
        status="idle",
        messages=[system_message("你是一个受限的子 agent。按任务目标完成工作并汇报结果。")],
    )
    self._sessions[subagent_id] = session
    return session.to_summary_dict()
```

#### 第 2 步：模式钳位（`manager.py:697`）

```python
def _clamp_mode(self, requested: AgentMode) -> AgentMode:
    parent_mode = self._parent_mode()
    order = {READ_ONLY: 0, PLAN: 0, BUILD: 1, BYPASS: 2}
    if order[requested] > order[parent_mode]:
        return parent_mode  # 子代理不可超越父代理
    return requested
```

父 agent 在 BUILD 模式 → 子 agent 最高只能是 BUILD。父 agent 在 READ_ONLY → 子 agent 只能是 READ_ONLY。**子代理永远不能获得比父代理更高的权限。**

#### 第 3 步：运行子 agent（`manager.py:209`）

```python
async def run_subagent(self, *, subagent_id, task, wait=False, timeout_s=None,
                       max_tokens=None, max_time_s=None):
    # 薄封装：守卫活跃运行 + guardrails 检查 + _new_run() + _launch_run() + 信封格式化
    ...
```

消息追加、创建 `asyncio.Task`、waiter 等真正逻辑在 `_launch_run()`（`manager.py:319`）里；`run_subagent` 还支持 `max_tokens` / `max_time_s` 限制。

`_build_subagent_loop()`（`manager.py:503`）构建一个精简的 AgentLoop：

```python
def _build_subagent_loop(self, mode, budget=None):
    registry = build_default_tool_registry(
        policy=self.workspace_policy, mode_policy=ModePolicy(...),
        ignore_patterns=..., code_intelligence_config=...,
        browser_config=..., web_search_config=...,   # 含 WebSearch/WebFetch
        sandbox=self._resolve_sandbox(),
    )
    hooks = HookManager([TracingHook()])
    if budget is not None:
        hooks.hooks.append(BudgetHook(budget))
    return AgentLoop(
        llm=self.llm,                  # 共享父的 LLM 实例
        tool_registry=registry,         # 独立的工具注册表
        hooks=hooks,                    # TracingHook + BudgetHook
        memory=MemoryManager(max_tokens=80_000),  # 独立的记忆管理器
        run_config=AgentRunConfig(mode=mode),
        subagent_manager=self,          # 可以继续派孙代理
        expose_subagent_tools=True,     # 子代理控制工具
        cost_ledger=self.cost_ledger,
        ledger_tool_name="subagent",
    )
```

关键差异：
- `max_tokens=80_000`（与 CLI 主入口的父 agent 一致；`MemoryManager` 构造默认值 100K 仅在未显式传 memory 时生效）
- 工具集走 `build_default_tool_registry`（**包含** WebSearch/WebFetch、Code Intelligence、Browser），另有子代理控制工具（`expose_subagent_tools=True`）
- Hook 链是 `TracingHook` + `BudgetHook`（有预算时），没有 LoggingHook（减少噪音）
- 没有 SkillRuntime、没有 MCP（极简化）

#### 第 4 步：子 agent 自主执行

子 agent 在 `asyncio.Task` 中运行自己的 AgentLoop：

```
子 agent 迭代 1: LLM → Grep("TODO") → 找到 47 个匹配
子 agent 迭代 2: LLM → Read 几个关键文件 → 分析上下文
子 agent 迭代 3: LLM → "共找到 47 个 TODO，分为 3 类：bug 标记 12 个..."
```

#### 第 5 步：完成和回报（`manager.py:542`）

```python
def _complete_run(self, session, run, result, trace):
    run.status = "completed" if result.stop_reason is not StopReason.ERROR else "failed"
    run.summary = result.content           # "共找到 47 个 TODO..."
    run.finished_at = time.time()
    run.trace = trace.to_dict()
    run.reason = ...
    run.usage = ...
    session.active_run_id = None
    session.status = "idle"
```

父 agent 调用 `GetSubagentRunTool` 获取结果；子 agent 之间的通信/回报通过**消息总线**（`PublishBusMessage` / `ReadBus` 工具，`agent/subagent/bus.py`）完成，另有 `ParentChannel` 机制（`agent/subagent/parent_channel_hook.py`，当前仅定义、未接线）。

#### 第 6 步：查看转录

父 agent 可以调用 `InspectSubagentTranscriptTool` 查看子 agent 的对话记录：

```python
def inspect_transcript(self, *, subagent_id, scope="summary"):
    if scope == "summary":
        return {
            "subagent_id": subagent_id, "run_id": run_id, "scope": "summary",
            "summary": session.runs[-1].summary if session.runs else "",
            "truncated": ..., "included_tool_results": ...,
        }
    # scope == "recent_messages" → 返回最后 limit 条（默认 5），默认过滤 tool 结果
```

### 完整生命周期

```
父 AgentLoop
  │
  ├─ CreateSubagentTool → SubAgentManager.create_subagent()
  │   └─ 模式钳位 + 创建 SubagentSessionRecord
  │
  ├─ RunSubagentTool → SubAgentManager.run_subagent()
  │   ├─ _launch_run() → asyncio.create_task()
  │   ├─ _build_subagent_loop() → 独立的 AgentLoop 实例（build_default 工具集 + 子代理控制工具）
  │   └─ 子 agent 在自己的 AgentLoop 中自主执行
  │
  ├─ (可选) GetSubagentRunTool → 获取子 agent 运行状态
  ├─ (可选) ListSubagentsTool → 列出子 agent
  ├─ (可选) CancelSubagentRunTool → 取消运行中的子 agent
  ├─ (可选) InspectSubagentTranscriptTool → 查看子 agent 对话记录
  ├─ (可选) ResumeSubagentTool / RunPatternTool → 恢复/复用运行模式
  ├─ (可选) PublishBusMessageTool / ReadBusTool → 消息总线通信
  │
  └─ 子 agent 完成 → _complete_run() → status="completed" 或 "failed"
```

### 关键设计要点

| 要点 | 说明 |
|------|------|
| **模式钳位** | 子代理模式 ≤ 父代理模式，不可越权 |
| **独立 AgentLoop** | 每个子代理有独立的消息列表、记忆管理器、工具注册表 |
| **共享 LLM 实例** | 子代理复用父代理的 `self.llm`，不新建连接 |
| **asyncio.Task 隔离** | 子代理跑在独立 Task 中，父代理可以继续做其他事 |
| **可取消** | `cancel_subagent_run()` → `task.cancel()` → `CancelledError` 处理 |
| **转录可查** | 父代理可以事后检查子代理的完整对话记录 |

---

## 第七章：扩展机制

### 7.1 技能系统（Skills）

**文件**：`agent/skills/loader.py`、`runtime.py`

#### 它在做什么

Skill 是给 agent 注入领域知识的插件机制。每个 Skill 是一个目录，里面有一个 `SKILL.md` 文件，定义了技能的提示词、触发条件和工具要求。Skill 可以被自动激活（匹配触发器）或手动激活（用户输入 `/skill-name` 或 agent 调用 `ActivateSkillTool`）。

#### SKILL.md 格式

```markdown
---
name: dataviz
description: 当需要创建图表、图形或数据可视化时使用此技能
triggers:
  - "chart"
  - "graph"
  - "plot"
  - "可视化"
always: false
user_invocable: true
argument_hint: "[数据类型]"
tools:
  - "WebSearch"
  - "WebFetch"
---

# 数据可视化技能

当创建图表时：
- 使用 plotly 进行交互式图表
- 使用 matplotlib 进行静态图表
...
```

#### 生命周期

```
启动 → SkillRuntime.from_roots() → SkillLoader 加载所有 SKILL.md
  ↓
AgentLoop.run() → skill_runtime.begin_run(user_message)
  ├─ 自动激活: always=true 的技能
  └─ 触发匹配: 用户消息包含 trigger 关键词 → 自动激活
  ↓
运行时:
  ├─ 用户输入 /skill-name → SlashCommand 返回带 run_agent/skill_name 元数据的 CommandResult
  │     → main.py 调 skill_runtime.queue_activation() 排队 → 下一次 begin_run() 消费队列激活
  ├─ Agent 调用 ActivateSkillTool → skill_runtime.activate_skill(..., source="llm_tool") 立即激活
  └─ 激活后 → SkillActiveSource.render() → 技能提示词注入 P4 上下文
  ↓
恢复会话: skill_runtime.restore_skills(active_skills) → 还原已激活的技能
```

### 7.2 Hook 事件系统

**文件**：`agent/hooks/manager.py`

#### 七个生命周期钩子

```python
class Hook(Protocol):
    async def on_run_started(self, run_config) -> None: ...
    async def before_iteration(self, iteration, messages) -> None: ...
    async def after_llm_call(self, response) -> None: ...
    async def before_tool_execute(self, tool_call) -> None: ...
    async def after_tool_execute(self, tool_call, result, error_type=None) -> None: ...
    async def on_error(self, error) -> None: ...
    async def on_completion(self, result) -> None: ...
```

#### 内置 Hook

| Hook | 作用 |
|------|------|
| `LoggingHook` | 记录每个生命周期事件到日志 |
| `TracingHook` | 生成调试/可观测性追踪数据 |
| `RetryHook` | 工具执行失败时的指数退避重试（max_retries=3, base_delay=1.0s） |
| `TokenBudgetHook` | Token 预算监控 |

Hook 在 `HookManager` 中按注册顺序同步调用（非并发）。多数 hook 只观察和记录、不修改数据；`RetryHook` 例外——它的 `execute_with_retry()` 会真正重试工具执行（`loop.py` 在工具执行路径上调用），是行为修改型 hook。

### 7.3 Slash 命令系统

**文件**：`agent/commands/registry.py`

#### 命令注册

```python
class SlashCommandRegistry:
    def register(self, command: SlashCommand):
        # 注册主名和别名到 dict
        self._commands[command.canonical_name] = command

    async def try_execute(self, user_input: str, context: CommandContext):
        # 不以 / 开头 → 返回 None（视为普通对话，交给 AgentLoop）
        # 匹配命令 → 调用 handler → 返回 CommandResult
        # 未匹配 → 返回 CommandResult("Unknown command")
```

#### 内置命令

| 命令 | 作用 |
|------|------|
| `/help` | 列出所有可用命令 |
| `/exit` (`/quit`) | 退出会话 |
| `/status` | 显示 Session ID / Mode / Provider / Model / Messages / estimated tokens |
| `/mode <mode>` | 切换模式（build/read_only/plan/bypass） |
| `/clear` | 清空对话历史（保留 system 消息） |
| `/compact` | 手动触发上下文压缩 |
| `/skills` | 列出可用技能 |
| `/init` | 生成 ASTER.md |
| `/mcp` | 显示 MCP server 状态 |
| `/mcp-prompt` / `/mcp-resource` | 查看并注入 MCP prompt / resource 到当前会话 |
| `/session-workspace` | 查看/切换会话工作区 |

Skills 也自动注册为 slash 命令（`source="skill"`, `kind="prompt"`）。

#### 实战例子：`/compact` 的完整路径

```
用户输入 "/compact"
  ↓
CLI REPL: user_input.startswith("/") → registry.try_execute("/compact", ctx)
  ↓
registry: 匹配 "compact" → SlashCommand(handler=compact_handler)
  ↓
compact_handler(ctx, args):
    result = await ctx.agent.memory.compact_manually(ctx.messages)
    if result.compacted:
        return CommandResult(
            "Compacted conversation history. Messages: X -> Y; estimated tokens: A -> B.",
            metadata={...})
    else:
        return CommandResult(
            "Nothing to compact. Messages: X; estimated tokens: Y.", metadata={...})
  ↓
CLI REPL: 显示结果，continue_session=True（不退出 REPL）
```

---

## 第八章：会话持久化

**文件**：`agent/session.py`
**核心类**：`SessionStore`、`SessionSnapshot`

### 它在做什么

`SessionStore` 让用户可以中断会话（Ctrl+C、关闭终端），之后用 `--resume` 恢复，agent 能记得之前的所有对话、todo、技能状态和模式。

### 实战例子：用户修 bug 修到一半，Ctrl+C 退出，明天继续

#### 第 1 步：保存（`AgentLoop.run()` 的 finally 块）

```python
# loop.py:527
finally:
    if self.session_store is not None and session_id:
        self._save_session(messages, session_id, run_id, resume_snapshot)
```

`_save_session()` 构造 `SessionSnapshot`：

```python
snapshot = SessionSnapshot(
    schema_version="1.0",
    session_id="abc123",
    created_at="2026-07-19T10:30:00Z",
    updated_at="2026-07-19T11:45:00Z",
    messages=messages,            # 完整对话历史
    mode=AgentMode.BUILD,
    todos=[PlanItem(...)],        # 执行进度
    active_skills=["dataviz"],    # 已激活技能
    run_id="run-xyz",
    iteration=8,
    user_system_prompt="...",
    runtime_fingerprint={         # 环境指纹
        "cwd": "/Users/kaixing/code/asterwynd",
        "model": "gpt-4",
        "provider": "openai",
        "agent_version": "0.1.0",
    },
)
```

#### 第 2 步：去重写入（`session.py:88`）

```python
def save(self, snapshot: SessionSnapshot) -> bool:
    dedup_dict = {k: v for k, v in snapshot_dict.items() if k != "updated_at"}
    new_hash = _hash_dict(dedup_dict, snapshot.messages)

    if self._last_hash.get(snapshot.session_id) == new_hash:
        return False  # 内容无变化 → 跳过写入

    # tmp 文件 + os.replace（原子写入，防止写一半崩溃）
    with open(tmp_snapshot, "w") as f:
        json.dump(snapshot_dict, f)
    with open(tmp_messages, "w") as f:
        json.dump([m.to_dict() for m in messages], f)
    os.replace(tmp_snapshot, snapshot.json)
    os.replace(tmp_messages, messages.json)
```

去重策略：对比内容哈希（排除 `updated_at`），如果和上次保存一样就跳过——避免每次迭代都写磁盘。

`tmp + os.replace` 保证原子性：要么写入完成，要么旧文件不受影响。

#### 第 3 步：存储结构

```
.asterwynd/sessions/abc123/
├── snapshot.json    # 元数据（mode, todos, skills, iteration, fingerprint）
└── messages.json    # 完整对话历史（含 tool_calls 和 tool_call_id）
```

#### 第 4 步：恢复（`session.py:105`）

用户第二天运行：

```bash
asterwynd --resume abc123
```

`SessionStore.load("abc123")` 做三件事：

1. **Schema 兼容检查**：`stored_version.split(".")[0] == current_version.split(".")[0]` → 主版本必须一致
2. **运行时指纹对比**：比较 cwd、model、provider、agent_version，有差异时发出 warning（不阻止恢复）
3. **反序列化消息**：`Message.from_dict()` 还原完整对话历史（包括 ContentBlock 和 ToolCallDelta）

#### 第 5 步：AgentLoop 还原状态

```python
# loop.py:557-575
if resume_snapshot is not None:
    if resume_snapshot.mode != self.runtime_state.current_mode:
        self.set_mode(resume_snapshot.mode, source="resume")
    self._execution_todos = list(resume_snapshot.todos)
    if self.skill_runtime and resume_snapshot.active_skills:
        self.skill_runtime.restore_skills(resume_snapshot.active_skills)
    self._user_system_prompt = resume_snapshot.user_system_prompt
    # 拼接消息：system + 历史 + [Session resumed...] + 新用户输入
    messages = system + conversation + [Message(role="user", content="[Session resumed. Continuing from where we left off.]")] + new_input
```

`set_mode` 只在快照 mode 与当前 mode 不同时执行；`restore_skills` 只在 skill_runtime 非空且 active_skills 非空时执行；还会还原 `user_system_prompt`。

### 关键设计要点

| 要点 | 说明 |
|------|------|
| **原子写入** | tmp 文件 + `os.replace`，不会出现半写文件 |
| **去重跳过** | 内容哈希不变则跳过写入，避免无意义的磁盘 IO |
| **schema 版本检查** | 主版本不一致直接拒绝恢复，避免数据结构不兼容 |
| **指纹警告** | cwd/model 变了只警告不阻止，让用户知情 |
| **finally 块保存** | 即使崩溃也尝试保存，最大程度减少数据丢失 |

---

## 第九章：Web UI 实时通信

**文件**：`web/server.py`、`web/session.py`、`web/debug_hook.py`

### 它在做什么

Web UI 用 FastAPI + WebSocket 提供浏览器端的实时对话体验。核心挑战是：agent 的工具审批是阻塞式的——必须等用户在浏览器里点"批准"按钮——但 WebSocket 是异步消息通道。解决方案是用 `asyncio.Future` 做桥接。

### 架构

```
浏览器 (index.html + chat.js)
    │  WebSocket (/ws/{session_id})
    ▼
FastAPI WebSocket handler
    │  JSON 消息: chat / approval_response / reset / set_mode / ping
    ▼
SessionManager.create_session_async() → AgentSession
    ├─ AgentLoop 实例（完整工具链）
    ├─ messages: list[Message]
    └─ WebApprovalHandler（asyncio.Future 桥接）
```

### 事件流向

```
AgentLoop.run(on_event=send_to_ws)
  │
  ├─ "run_started"        → WebSocket → 浏览器显示"Agent 已启动"
  ├─ "assistant_delta"    → WebSocket → 浏览器逐字渲染 LLM 输出
  ├─ "llm_response"       → WebSocket → 浏览器显示完整回复 + tool_calls
  ├─ "approval_request"   → WebSocket → 浏览器弹出审批对话框
  │                           │
  │   用户点击"批准"  ←────────┘
  │                           │
  ├─ "approval_response"  ← WebSocket ← approval_response
  ├─ "tool_call"          → WebSocket → 浏览器显示工具调用
  ├─ "tool_result"        → WebSocket → 浏览器显示工具结果
  ├─ "memory_compaction"  → WebSocket → 浏览器显示压缩提示
  └─ "done"               → WebSocket → 浏览器显示完成
```

### 实战例子：用户在浏览器里点"批准"

#### 第 1 步：Agent 需要审批

AgentLoop Phase 1 对一个高风险的 `Bash` 工具调用（`COMMAND_EXECUTE` / `HIGH`，超过 build 的自动批准上限 `MEDIUM`）做出 `REQUIRE_APPROVAL` 决策：

```python
approval_request = build_approval_request(tool_call_id="call_abc", ...)
await on_event("approval_request", approval_request.to_event_data())
# → WebSocket 发送: {"type": "approval_request", "approval_id": "...", "tool_name": "Bash", ...}
```

#### 第 2 步：浏览器显示对话框

```javascript
// chat.js (伪代码)
ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (msg.type === "approval_request") {
        showApprovalDialog(msg);  // 弹出 "Bash 要执行 <命令>，批准?"（参数已脱敏）
    }
};
```

#### 第 3 步：Agent 阻塞等待

```python
# AgentLoop Phase 1
approval_response = await self.approval_handler.request_approval(approval_request)
```

此时 `WebApprovalHandler.request_approval()` 内部创建了一个 `asyncio.Future`，然后 `await` 它——agent 线程在此阻塞，等待 Future 被 resolve。

```python
class WebApprovalHandler:
    _pending: tuple[str, asyncio.Future[ApprovalResponse]] | None = None  # 单槽

    async def request_approval(self, request):
        if self._pending is not None:
            return ApprovalResponse(status=UNAVAILABLE, ...)  # 同一时刻只允许一个 pending
        future = asyncio.get_event_loop().create_future()
        self._pending = (request.approval_id, future)
        return await future  # ← 阻塞在这里，直到浏览器响应
```

#### 第 4 步：用户点击"批准"

```javascript
// 浏览器
function onApproveClick() {
    ws.send(JSON.stringify({
        type: "approval_response",
        approval_id: "approval-xxx",
        decision: "approved"   // wire 字段是 decision，不是 status
    }));
}
```

#### 第 5 步：WebSocket 收到响应，resolve Future

```python
# web/server.py — WebSocket handler
elif msg_type == "approval_response":
    approval_id = str(raw.get("approval_id", "")).strip()
    decision = str(raw.get("decision", "")).strip()   # "approved" | "denied"
    accepted = session.approval_handler.submit_response(approval_id, decision)
    # → 按 decision 归一化为 APPROVED / DENIED → future.set_result(approval_response)
```

`future.set_result()` 触发 → `await future` 返回 → agent 拿到 `approval_granted=True` → 继续执行工具。

### 关键设计要点

| 要点 | 说明 |
|------|------|
| **Future 桥接** | `asyncio.Future` 把异步 WebSocket 消息变成 agent 可 await 的同步等待 |
| **单槽审批** | 每个 Web session 同一时刻只允许一个 pending approval，重复请求直接返回 unavailable |
| **双向事件流** | agent → 浏览器（事件推送）+ 浏览器 → agent（审批、模式切换） |
| **SessionManager 缓存** | 每个浏览器 tab 一个 AgentSession，独立的消息列表和 agent 实例 |
| **图片上传** | chunked 上传 → 转 base64 → `create_image_message()` → 多模态 message |
| **Debug 模式** | `debug_enabled()` 时额外注入 `DebugHook`，推送详情到 debug 面板 |

---

## 第十章：Benchmark 评测系统

**文件**：`benchmarks/runner.py`、`task_schema.py`、`agent_runner.py`

### 它在做什么

Benchmark 系统量化评估 agent 的代码修改能力。它给 agent 一个 issue 描述，让 agent 修改代码，然后跑测试验证修改是否正确。

### 实战例子：一个 SWE-bench 任务的完整评测链路

#### 任务定义（`task.json`）

```json
{
  "id": "flask-404-fix",
  "repo": "https://github.com/pallets/flask",
  "base_commit": "abc123def456",
  "problem_statement_file": "problem_statement.md",
  "test_command": "cd tests && python -m pytest test_basic.py::test_404",
  "timeout_seconds": 300,
  "gold_patch_file": "gold.patch",
  "test_patch_file": "test.patch",
  "category": "bug-fix",
  "difficulty": "medium",
  "execution_environment": "local"
}
```

必填字段是 `id` / `repo` / `base_commit` / `problem_statement_file` / `test_command`——问题描述从 `problem_statement_file`（外部文件）读取，没有 `problem_statement` 内联字段；缺必填字段的 task.json 会直接抛 `ValueError`。

#### 第 1 步：准备环境

```python
# runner.py — 对应私有方法 _clone_external_repo / _create_worktree
loaded = load_task(task_dir)
if loaded.task.external_repo:
    # 外部仓库：从 clone cache 复用 bare clone，再 checkout base_commit
    worktree = self._clone_external_repo(loaded.task)
else:
    # 本地仓库：创建 git worktree
    worktree = self._create_worktree(loaded.task)
```

注意：runner **不应用 gold patch**。agent 直接在 base_commit（有 bug 的版本）上工作并修复；gold_patch_file 只在 task schema 里加载保存，评测阶段只应用 test patch 来验证修复是否正确。

#### 第 2 步：跑 agent

```python
result = await agent_runner.run(
    task=loaded.task,
    problem_statement=load_problem_statement(loaded.task),  # 从 problem_statement_file 读取
    workspace=worktree,
    output_dir=task_output,
    trace=trace_recorder,
)
```

`AsterwyndRunner` 创建新的 `AgentLoop` 实例，传入 problem_statement，然后在 worktree 中执行：

```
AgentLoop.run() → 多轮迭代
  → Read 相关文件
  → Edit 修改代码
  → Bash 跑测试验证
  → 输出最终 diff
```

#### 第 3 步：抓取变更

agent 完成后，`git diff` 抓取所有变更：

```python
diff = self._git_patch(worktree)
# → diff: "--- a/flask/app.py\n+++ b/flask/app.py\n@@ ..."
artifacts.final_diff.write_text(diff)
```

#### 第 4 步：评测

```python
# 应用 test patch（添加基准测试用例）
await asyncio.to_thread(self._apply_test_patch, workspace, loaded.test_patch_path, task_output)

# 跑测试
test_exit_code, test_output, test_duration_ms = await asyncio.to_thread(
    self._run_test_command, loaded.task.test_command, workspace,
    loaded.task.timeout_seconds, bool(loaded.task.external_repo),
)
# → test_exit_code == 0 → passed

# 评分
status = "passed" if test_exit_code == 0 else "failed"
task_result = TaskResult(
    task_id=loaded.task.id,
    agent=...,
    status=status,              # "passed" | "failed" | "error" | "passed_with_warnings" | "unsupported"
    test_exit_code=test_exit_code,
    reason=...,
)
```

#### 第 5 步：收集产物

```
runs/<run_id>/tasks/flask-404-fix/
├── result.json       # TaskResult（status, test_exit_code, reason, ...）
├── trace.json        # 完整 agent 执行追踪
├── final.diff        # agent 生成的 diff
├── test_output.txt   # 测试命令的标准输出
└── runner.log        # Runner 日志
```

注意目录结构：`runs/<run_id>/tasks/<task_id>/`，中间多一层 `tasks/`；`run_id` 是完整时间戳（如 `2026-07-19T10-30-00`，`%Y-%m-%dT%H-%M-%S` 格式，无毫秒、无 Z 后缀），不是纯日期。

#### 并行调度

```python
class BenchmarkRunner:
    async def run_all(self, tasks):
        semaphore = asyncio.Semaphore(self.parallel)  # 默认 parallel=1

        async def run_one(task):
            async with semaphore:
                return await self._run_task(task)

        results = await asyncio.gather(*[run_one(t) for t in tasks])
        return results
```

`asyncio.Semaphore` 控制并发数。每个任务跑在独立的 worktree 中，互不干扰。

### 完整流程图

```
BenchmarkRunner.run_all(tasks)
  │
  ├─ 预填充 clone cache（外部仓库）
  │
  └─ asyncio.gather(*[run_one(t) for t in tasks])  ← Semaphore 限流
      │
      ▼
  _run_task(task):
    ├─ 创建 worktree (git worktree add 或 clone 外部仓库)
    ├─ agent_runner.run(task, workspace)
    │   └─ AgentLoop 在 worktree 中自主执行多轮迭代
    ├─ git diff → final.diff
    ├─ 应用 test patch
    ├─ run test_command
    └─ 评分 → TaskResult(status="passed"/"failed"/..., test_exit_code=...)
      │
      ▼
  TaskArtifacts(result.json, trace.json, final.diff, test_output.txt, runner.log)
```

### 关键设计要点

| 要点 | 说明 |
|------|------|
| **Worktree 隔离** | 每个任务独立 worktree，并行执行互不干扰 |
| **Semaphore 限流** | `parallel=N` 控制同时跑的任务数，避免资源竞争 |
| **Clone 缓存** | 外部仓库的 bare clone 被缓存复用，避免重复 clone |
| **产物完整** | 每次评测保留 diff、trace、test output，便于事后分析 |
| **Docker 支持** | `execution_environment=docker` 时用 SWE-bench harness 在容器中评测 |
| **多 Agent Runner** | FakeAgentRunner（测试用）/ AsterwyndRunner / ClaudeCodeRunner / ShellCommandRunner 四种 runner |

---

## 附录：系统总览图

```
CLI (agent/main.py) / Web Server (web/server.py)
    │
    ▼
AgentLoop (agent/loop.py)  ←── 核心调度器
    │
    ├── LLM (agent/llm.py → agent/openai_llm.py / agent/anthropic_llm.py)
    │     └── BaseLLM: httpx 连接池 + SSE 流解析 + 超时策略
    │
    ├── ToolRegistry (agent/tools/registry.py)
    │     ├── 内置工具 (agent/tools/builtin/) — 默认注册 21 内置（含 6 LSP）+ 可选 MemoryGitBackend + 最多 7 浏览器
    │     ├── MCP 工具 (agent/mcp/tools.py)
    │     ├── ModePolicy (agent/run_config.py) — 权限决策链（4 个 mode / 3 种决策）
    │     ├── Sandbox (agent/tools/sandbox/) — ExecutionBackend 协议 + ProcessBackend / DockerBackend
    │     └── WorkspacePolicy (agent/workspace_policy.py) — 路径与命令安全
    │
    ├── ContextBuilder (agent/context/builder.py)
    │     ├── P0: SystemPromptSource — 身份 + 红线约束
    │     ├── P1: AsterMdSource — 多层 ASTER.md 发现与拼接
    │     ├── P2: MemoryIndexSource — 持久记忆摘要（cacheable）
    │     ├── P4: SkillIndexSource / SkillActiveSource — 技能上下文
    │     └── P5: PlanModeSource / PlanningStateSource / TodoSource — 规划状态
    │
    ├── MemoryManager (agent/memory/manager.py)
    │     ├── compact_if_needed() — 默认 max_tokens − 15_000 阈值自动触发
    │     ├── _recent_with_tool_chains() — tool chain 完整性保护
    │     └── Summarizer (agent/context/summarizer.py) — LLM/Truncation 双策略
    │
    ├── PersistentMemory (agent/memory/persistent.py)
    │     └── 四类记忆 + MEMORY.md 索引 + Claude Code 兼容
    │
    ├── HookManager (agent/hooks/manager.py)
    │     └── 7 个生命周期钩子
    │
    ├── SkillRuntime (agent/skills/runtime.py) + SkillLoader (agent/skills/loader.py)
    ├── SubAgentManager (agent/subagent/manager.py) — 受限子代理管理
    ├── PlanningManager (agent/planning/manager.py)
    ├── BackgroundTaskManager (agent/background.py)
    ├── ApprovalHandler (agent/approval.py)
    ├── TraceRecorder (agent/trace_recorder.py)
    └── SessionStore (agent/session.py) — 会话持久化

跨切面:
    Message (agent/message.py) — TextBlock / ImageBlock / ContentBlock
    RunResult (agent/result.py)
    Config (agent/config.py) — YAML + env + CLI 三层解析
```
