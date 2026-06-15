# Reference Projects — AI Agent 设计模式分析

**Date:** 2026-05-06
**Projects Analyzed:** claude-code-haha, openclaw, hermes-agent, nanobot

---

## 1. Overview

四个项目代表了四种不同的 Agent 设计方向：

| 项目 | 语言 | 架构风格 | 核心创新 |
|------|------|---------|---------|
| claude-code-haha | TypeScript | QueryEngine async generator | 并发工具执行(10)、任务系统 |
| openclaw | TypeScript | Gateway + 嵌入式 Pi-runtime | 多渠道集成、技能快照 |
| hermes-agent | Python | AIAgent 类 + 模块化插件 | 完整工具生态、MemoryProvider |
| nanobot | Python | AgentLoop 消息总线 + AgentRunner | Hook 生命周期、AutoCompact |

---

## 2. Core Agent Loop Patterns

### 2.1 nanobot — 最干净的循环

```python
# agent/runner.py — AgentRunner
async def run(self, spec: AgentRunSpec) -> AgentRunResult:
    while iteration < spec.max_iterations:
        response = await self.llm.chat(spec.messages, tools=schemas)
        if not response.tool_calls:
            return response.content
        for tool_call in response.tool_calls:
            result = await registry.execute(tool_call)
            spec.messages.append(tool_result(tool_call.id, result))
        iteration += 1
```

**特点：** `AgentRunner` 是纯 LLM 循环，不感知消息来源（Channel）。`AgentLoop` 负责消息总线的消费和分发，两者分离。

### 2.2 hermes-agent — 最大全的循环

```python
# run_agent.py — AIAgent.run_conversation()
while api_call_count < max_iterations:
    if self._interrupt_requested: break
    response = client.chat.completions.create(messages, tools=schemas)
    if response.tool_calls:
        for tool_call in response.tool_calls:
            result = handle_function_call(tool_call.name, tool_call.args)
            messages.append(tool_result_message(result))
        api_call_count += 1
    else:
        return response.content
```

**特点：** 额外处理 interrupt（用户中断）、iteration budget、`_budget_grace_call`（预算宽限）。

### 2.3 claude-code-haha — QueryEngine async generator

```python
# QueryEngine.ts — submitMessage()
async *submitMessage(message: Message): AsyncGenerator<SDKMessage> {
    const response = await this.llm.chat(messages, tools);
    for (const toolCall of response.tool_calls) {
        const result = await toolOrchestration.runTools(toolCall);
        yield { type: 'tool_result', toolCall, result };
        messages.push(tool_result_message(toolCall.id, result));
    }
}
```

**特点：** 用 `AsyncGenerator` yield SDKMessage，支持流式 UI 更新。`runTools` 支持并发（最多 10 个 tool_calls 同时执行）。

### 2.4 共同模式

```
messages[] → LLM → tool_calls? → [execute tools] → append results → repeat
                                  ↓
                              no tools → return
```

所有项目都遵循这个"LLM → 工具调用 → 结果回写 → 重复"的循环。差异在于：
- nanobot 把循环拆成 `AgentLoop`（感知消息）和 `AgentRunner`（纯 LLM）
- hermes-agent 在 `handle_function_call` 前有 interrupt 检查
- claude-code-haha 用 async generator 支持流式

---

## 3. Tool System Patterns

### 3.1 nanobot — Tool 基类 + 装饰器

```python
# agent/tools/base.py
class Tool(ABC):
    name: str
    description: str
    parameters: dict  # JSON Schema
    read_only: bool = False
    dangerous: bool = False

    @abstractmethod
    async def execute(self, **kwargs) -> str: ...

@tool_parameters({
    "name": "Read",
    "description": "...",
    "parameters": {...}
})
class ReadTool(Tool):
    read_only = True
    async def execute(self, path: str, **kwargs) -> str:
        return Path(path).read_text()
```

**registry 缓存 schema，只在注册时构建一次。**

### 3.2 hermes-agent — 自注册 + Toolsets

```python
# tools/registry.py
registry = ToolRegistry()

# tools/ 目录下的模块在 discover_builtin_tools() 时自动注册
def register(name, toolset, schema, handler, check_fn=None):
    registry._tools[name] = ToolDef(...)

# toolsets.py
_HERMES_CORE_TOOLS = ["Read", "Write", "Bash", "Grep", ...]
WEB_TOOLS = ["WebSearch", "WebFetch", ...]
```

**工具定义分散在各个 `tools/*.py` 文件，通过 import 触发注册。** 这是一个"插件"模式：工具模块是独立的，导入即注册。

### 3.3 claude-code-haha — ToolDef + ToolOrchestration

```python
# Tool.ts
interface ToolDef {
    name: string
    inputSchema: object
    description: string
    render(): React.ReactNode  # TUI 渲染
}

# services/tools/toolOrchestration.ts
runTools(toolCalls: ToolCall[]): Promise<ToolResult[]> {
    // 1. 按 read_only 分组（read-only 可并行）
    // 2. 最多 10 个并发
    // 3. 执行后 append 到 messages
}
```

**特色：** `render()` 方法让每个工具在 TUI 中有自定义渲染（diff 视图等）。`ToolOrchestration` 把工具按只读/写分组，read-only 工具可以并行执行。

### 3.4 openclaw — ToolPlan + Availability

```python
# tools/planner.ts
interface ToolPlan {
    visible: ToolDescriptor[]   # 对 LLM 可见
    hidden: ToolDescriptor[]    # 隐藏（不暴露给 LLM，但仍可调用）
}

function buildToolPlan(ctx: Context): ToolPlan {
    return ToolPlan(
        visible=ctx.available_tools.filter(t => t.isAvailable(ctx)),
        hidden=ctx.system_tools.filter(t => t.isAvailable(ctx))
    )
}
```

**特色：** `ToolAvailabilityExpression` 决定工具是否对当前 context 可见。LLM 只看到 `visible` 列表，但 agent 可以主动调用 `hidden` 工具。

### 3.5 共同模式

| 维度 | nanobot | hermes | claude-code-haha | openclaw |
|------|---------|--------|-----------------|---------|
| Schema 定义 | Tool class + decorator | register() call | ToolDef interface | ToolDescriptor |
| 权限模型 | read_only/dangerous flag | 工具内部处理 | ToolPermissionRules | ToolAvailabilityExpression |
| 并发控制 | 无（串行） | 无 | 10 并发分组 | 无 |
| 沙箱 | 无 | 无 | 无 | Docker support |

---

## 4. Memory System Patterns

### 4.1 nanobot — 两级记忆 + AutoCompact

```python
# agent/memory.py
class MemoryStore:
    def __init__(self, max_tokens: int = 80_000):
        self.messages: list[Message] = []
        self.max_tokens = max_tokens

    def compact_if_needed(self):
        if self.count_tokens(self.messages) > self.max_tokens:
            self.compact()

    def compact(self):
        """保留 system + 最近 10 条，其余压缩"""
        system = [m for m in self.messages if m.role == "system"]
        recent = self.messages[-10:]
        summary = self.llm.summarize(self.messages[:-10])
        self.messages = system + [summary] + recent
```

**AutoCompact = token 预算超限后，用 LLM 做有损压缩。**

### 4.2 hermes-agent — MemoryProvider ABC

```python
# agent/memory_provider.py
class MemoryProvider(ABC):
    @abstractmethod
    async def fetch(self, query: str, session_id: str) -> list[Message]: ...

class MemoryManager:
    def __init__(self, providers: list[MemoryProvider]):
        self.providers = providers

    async def prefetch_all(self, query: str, session_id: str):
        """每轮 LLM call 前执行"""
        return [p.fetch(query, session_id) for p in self.providers]

    async def sync_all(self, session_id: str):
        """每轮 LLM call 后执行"""
        [p.save(session_id) for p in self.providers]
```

**特点：** 插件化记忆系统，可以同时启用多个 provider（但只支持一个外部 plugin）。内置 Honcho dialectic。

### 4.3 openclaw — 文件 + SQLite

```
~/.openclaw/agents/<agentId>/memory/
├── MEMORY.md              # 入口文件（最多 25KB）
├── memory/YYYY-MM-DD.md   # 每日记忆文件
├── DREAMS.md               # 长期记忆
└── sessions/*.jsonl        # SQLite 存储的 session 历史
```

**Dreaming：** 后台进程把短时记忆合并到长期记忆文件。

### 4.4 claude-code-haha — memdir

```
MEMORY.md (入口，最多 200 行)
├── memdir.ts — 加载 + 截断
├── memoryScan.ts — 相关记忆检索
└── teamMemPaths.ts — 团队记忆路径
```

**特点：** 最简单。所有 agent 共享同一个 `MEMORY.md`，没有 session 隔离。

---

## 5. Multi-Agent Patterns

### 5.1 hermes-agent — 同步委托

```python
# tools/delegate_tool.py
def delegate_task(task: str, model: str, role: str):
    if role == "leaf":  # worker，不允许再委托
        subagent = spawn_leaf_agent(task, model)
    else:  # orchestrator
        subagent = spawn_orchestrator_agent(task, model)

    result = subagent.run_sync()  # 阻塞等待结果
    return result.summary
```

**特点：** 同步等待，父 agent 在 `run_sync()` 返回前不返回。`role=leaf` 强制禁止递归委托。

### 5.2 nanobot — 异步后台 + mid-turn injection

```python
# agent/subagent.py
async def delegate(self, task: str, ...):
    subagent_id = uuid4().hex[:8]
    asyncio.create_task(
        sub_agent.run()  # 后台运行，不阻塞
    )
    return subagent_id

# agent/hook.py — ParentChannelHook
async def after_tool_execute(self, tool_call, result):
    if result.get("type") == "subagent_result":
        # 注入父 agent 当前轮次
        self.parent_messages.append(
            Message(role="tool", content=result["content"])
        )
```

**特点：** subagent 在后台运行，结果通过 Hook 注入父 agent 当前轮次（mid-turn injection）。父 agent 不需要等待。

### 5.3 claude-code-haha — Coordinator 模式

```python
# coordinator/coordinatorMode.ts
// 一个 coordinator agent 协调多个 LocalAgentTask
// LocalAgentTask 通过 Task IPC 通信
// coordinator 负责组合最终结果
```

---

## 6. Hook / Lifecycle Patterns

### 6.1 nanobot — 最完整的 Hook 系统

```python
# agent/hook.py
class Hook(Protocol):
    async def before_iteration(self, iteration: int, messages: list[Message]) -> None: ...
    async def after_iteration(self, iteration: int, messages: list[Message]) -> None: ...
    async def before_execute_tools(self, tool_calls: list[ToolCall]) -> None: ...
    async def on_stream(self, token: str) -> None: ...
    async def on_stream_end(self, response: LLMResponse) -> None: ...
    async def finalize_content(self, content: str) -> str: ...

class CompositeHook:
    def __init__(self, hooks: list[Hook]):
        self.hooks = hooks

    async def before_iteration(self, ...):
        for h in self.hooks:
            await h.before_iteration(...)
```

**内置 Hook：**
- `LoggingHook` — 结构化日志
- `RetryHook` — 失败重试
- `TokenBudgetHook` — token 预算监控
- `TracingHook` — 调用链追踪

### 6.2 hermes-agent — Skill Nudge

```python
# 不是通用 Hook，是针对 Skill 的定时 nudging 机制
self._skill_nudge_interval  # 每 N 轮触发一次 skill_manage
curator = Curator()          # 后台 skill 生命周期管理
curator.archive_stale_skills()
```

---

## 7. Skill System Patterns

### 7.1 nanobot — Markdown Skill Loader

```markdown
<!-- skills/code-review.md -->
---
name: code-review
description: 执行代码审查
tools: [Read, Bash]
always: false
---

# Code Review Skill

你是一个专业的代码审查专家...
```

```python
# agent/skills.py
class SkillLoader:
    def load(self, skills_dir: str) -> list[Skill]:
        for path in Path(skills_dir).glob("*.md"):
            skill = self._parse_frontmatter(path)
            skills.append(skill)

    def get_active_skills(self, query: str, skills: list[Skill]) -> list[Skill]:
        """根据 query 意图匹配 skill（简单 string match）"""
        return [s for s in skills if s.always or query matches s.description]
```

### 7.2 openclaw — Skills Snapshot

```python
# agents/skills.ts
async function loadSkillsSnapshot(workspace: Workspace): Promise<SkillsSnapshot> {
    // 1. 从 workspace 加载技能文件
    // 2. 从 project 加载
    // 3. 从 personal 目录加载
    // 4. 生成 snapshot（固定版本，不实时更新）
}
```

**特点：** Skills 以 snapshot 形式传给 agent runtime，不实时同步。保证 agent 看到的技能集合在同一次运行中稳定。

### 7.3 claude-code-haha — Bundled Skills

```
src/skills/bundled/
├── skill-name/
│   ├── instructions.md
│   └── tools.ts  # 技能专属工具
```

---

## 8. Session Model Patterns

| 项目 | Session ID | 存储 | 隔离 |
|------|-----------|------|------|
| nanobot | `session_key` (channel+chat_id) | 内存（可扩展持久化） | per-session lock |
| hermes-agent | UUID | SQLite + FTS5 | 每个 session 独立 |
| openclaw | stable session ID | JSONL transcript files | per-session write lock |
| claude-code-haha | conversation ID | 内存（QueryEngine 实例） | 无显式隔离 |

---

## 8.5. Updated Analysis (2026-06-15)

Seven repos now available at `/home/shared/agent-study/repos/` (added codex,
opencode, pi-mono). Key findings from the expanded review:

### Tool Design

| Decision | Finding |
|----------|---------|
| RunTestsTool | None of 7 repos has a dedicated test runner tool. All use shell/bash. |
| PatchTool | Claude Code, nanobot, pi-mono use Edit-only. Models produce malformed patches more often than exact replacements. |
| File listing | 4/7 repos provide dedicated ls/glob tools. MyAgent has none — ListFilesTool + FindTool needed. |
| Shell output format | Three tiers: raw text (nanobot, openclaw, pi-mono), JSON structured (hermes-agent), fully typed internal (codex). |
| Command filtering | Claude Code has most sophisticated (flag-level allowlist). hermes/nanobot use regex deny patterns with user overrides. |

### Naming Convention

MyAgent uses `FindTool` (not `GlobTool`) for recursive file search — more
intuitive, consistent with Unix `find`. `ListFilesTool` for flat directory
listing.

These findings informed the P1 scope documented in
`docs/coding-agent-roadmap.md` and `docs/benchmark-plan.md`.

---

## 9. Common Architectural Insights

### 9.1 所有项目都遵循的核心原则

1. **Agent Loop 是中心** — 所有外部复杂性（消息总线、CLI、TUI）都在循环之外
2. **工具是插件** — `Tool` 接口 + 注册机制是通用模式
3. **记忆是委托** — Agent Loop 不直接管理记忆，委托给专门组件
4. **Hooks 用于扩展** — nanobot 最彻底；hermes 用 skill nudge；openclaw 用可用性表达式

### 9.2 差异的根源

| 维度 | Python 项目 (hermes/nanobot) | TypeScript 项目 (openclaw/claude-code-haha) |
|------|-----------------------------|-------------------------------------------|
| 工具执行 | 同步/async 函数 | 更强调并发和 streaming |
| 类型系统 | dataclass + Protocol | TypeScript interface + 泛型 |
| 项目规模 | nanobot ~6 核心文件；hermes 超大单体 | 适度模块化 |
| 生态定位 | 偏底层框架 | 偏上层应用（TUI、Gateway） |

### 9.3 本新项目的设计决策依据

| 设计决策 | 参考来源 | 理由 |
|---------|---------|------|
| HookManager | nanobot | 最灵活的扩展机制 |
| AutoCompact | nanobot | token 预算管理的工业标准方案 |
| Tool 基类 + Registry | nanobot + hermes | 简单且类型安全 |
| Markdown Skill | nanobot + openclaw | 无需额外 DSL |
| 子 Agent 后台运行 | nanobot | mid-turn injection 是高级特性 |
| 分层插件架构 | hermes | 模块边界最清晰 |
| Sandbox | 参考 openclaw | 演示安全意识 |
