# General Purpose Agent — Architecture Design

**Date:** 2026-05-06
**Status:** Draft
**Language:** Python (async)

---

## 1. Overview

**Purpose:** A lightweight, general-purpose AI agent suitable for CLI use, designed to demonstrate clean architecture patterns for interview discussions. Not bound to a specific domain (coding/research), but ships with a practical default tool set.

**Design Philosophy:** Simplicity with depth — the core loop is small and readable (~100 lines), but each plugin subsystem (tools, hooks, memory, skills, subagents) is a proper abstractions with clear interfaces.

**Non-Goals:** Persistence layer (no SQLite), vector/RAG search, production-grade auth. These are future extensions.

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────┐
│                     Agent                            │
│  ┌─────────────┐  ┌─────────────┐  ┌────────────┐  │
│  │HookManager  │  │SkillLoader  │  │SubAgentMgr │  │
│  └─────────────┘  └─────────────┘  └────────────┘  │
│                                                     │
│  ┌─────────────────────────────────────────────┐   │
│  │              AgentLoop (async)               │   │
│  │  messages → LLM → tool_calls → execute     │   │
│  └─────────────────────────────────────────────┘   │
│         │              │              │            │
│  ┌──────▼──────┐ ┌─────▼─────┐ ┌──────▼──────┐    │
│  │ToolRegistry │ │MemoryMgr  │ │SubAgentComm │    │
│  │ + Sandbox   │ │+AutoCompact│ │ + Protocol │    │
│  └─────────────┘ └───────────┘ └─────────────┘    │
└─────────────────────────────────────────────────────┘
```

**四大插件：**
- **ToolRegistry** — 动态工具注册、权限分级、沙箱执行
- **HookManager** — 生命周期钩子，插入自定义逻辑
- **MemoryManager** — 消息历史 + AutoCompact token 压缩
- **SkillLoader** — Markdown 技能动态加载与挂载
- **SubAgentManager** — 任务委托、父子通信、mid-turn injection

---

## 3. Core Agent Loop

**File:** `agent/loop.py`

```python
class AgentLoop:
    async def run(self, messages: list[Message], tools: list[Tool], model: str) -> RunResult:
        iteration = 0
        while iteration < self.max_iterations:
            # 1. Hook: before_iteration
            await self.hooks.before_iteration(iteration, messages)

            # 2. LLM call
            response = await self.llm.chat(messages, tools=tool_schemas, model=model)

            # 3. Hook: after_llm_call
            await self.hooks.after_llm_call(response)

            if not response.tool_calls:
                return RunResult(content=response.content, messages=messages)

            # 4. Tool execution loop
            for tool_call in response.tool_calls:
                # Hook: before_tool_execute
                await self.hooks.before_tool_execute(tool_call)

                result = await self.tool_registry.execute(
                    tool_call,
                    sandbox=self.tool_registry.get_sandbox(tool_call.name)
                )

                # Hook: after_tool_execute
                await self.hooks.after_tool_execute(tool_call, result)

                messages.append(tool_result_message(tool_call.id, result))

            # 5. Memory: AutoCompact check
            self.memory.compact_if_needed()

            iteration += 1
```

**核心职责：**
- 维护 `messages` 列表，是唯一的"状态"
- 不直接执�工具，委托给 `ToolRegistry`
- 不直接管理记忆，委托给 `MemoryManager`
- 通过 HookManager 暴露所有生命周期扩展点

---

## 4. Tool System

### 4.1 Tool Registry

**File:** `agent/tools/registry.py`

```python
class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get_schema(self, name: str) -> dict:
        return self._tools[name].schema

    async def execute(self, tool_call: ToolCall, sandbox: bool = False) -> str:
        tool = self._tools[tool_call.name]
        if sandbox:
            return await self._sandbox_execute(tool, tool_call.args)
        return await tool.execute(**tool_call.args)

    def get_sandbox(self, name: str) -> bool:
        return self._tools[name].dangerous
```

**工具接口：**

```python
class Tool(ABC):
    name: str
    description: str
    parameters: dict  # JSON Schema
    read_only: bool = False
    dangerous: bool = False  # True = run in sandbox

    @abstractmethod
    async def execute(self, **kwargs) -> str:
        ...
```

### 4.2 Permission Levels

| Level | Flag | Behavior |
|-------|------|----------|
| `read_only` | `read_only=True` | 文件读、Bash 只读命令 |
| `read_write` | (default) | 文件写、Bash 读写 |
| `dangerous` | `dangerous=True` | 强制 subprocess 沙箱执行，限制权限 |

### 4.3 沙箱执行

**File:** `agent/tools/sandbox.py`

使用 `subprocess` + `psutil` 限制资源：
- 内存上限: 512MB
- CPU 时间上限: 30s
- 网络: 禁止（`NET_ADMIN` capability drop）
- 文件系统: `chroot` 或 `seccomp` profile（简化版: 只限制写入特定目录）

**默认工具集（6个）：**
- `Read` — 读文件（read_only）
- `Write` — 写文件（read_write）
- `Bash` — 执行 shell 命令（dangerous，沙箱）
- `WebSearch` — 网页搜索（read_only）
- `WebFetch` — 获取网页内容（read_only）
- `Grep` — 文本搜索（read_only）

---

## 5. Hook System

**File:** `agent/hooks/manager.py`

```python
class HookManager:
    async def before_iteration(self, iteration: int, messages: list[Message]) -> None: ...
    async def after_llm_call(self, response: LLMResponse) -> None: ...
    async def before_tool_execute(self, tool_call: ToolCall) -> None: ...
    async def after_tool_execute(self, tool_call: ToolCall, result: str) -> None: ...
    async def on_error(self, error: Exception) -> None: ...
    async def on_completion(self, result: RunResult) -> None: ...
```

**内置 Hook 实现：**

| Hook | 用途 |
|------|------|
| `LoggingHook` | 记录每次 iteration 的输入输出 |
| `RetryHook` | 工具执行失败时自动重试（最多 2 次） |
| `TokenBudgetHook` | 监控 token 使用，超预算触发压缩 |
| `TracingHook` | 收集每次 tool call 的耗时，输出结构化日志 |

**使用方式：**

```python
agent = AgentLoop(
    hooks=HookManager([
        LoggingHook(),
        TokenBudgetHook(budget=100_000),
    ])
)
```

**面试扩展点：** "如何给 agent 加监控/重试/限流？" → 答案就是传不同的 Hook。

---

## 6. Memory System (AutoCompact)

**File:** `agent/memory/manager.py`

```python
class MemoryManager:
    def __init__(self, max_tokens: int = 100_000):
        self.messages: list[Message] = []
        self.max_tokens = max_tokens

    def add(self, message: Message) -> None:
        self.messages.append(message)

    def compact_if_needed(self) -> None:
        total = self.count_tokens(self.messages)
        if total > self.max_tokens:
            self.compact()

    def compact(self) -> None:
        """保留系统消息 + 最近 N 条对话，压缩中间部分为摘要"""
        system = [m for m in self.messages if m.role == "system"]
        recent = self.messages[-10:]
        summary = self.summarize(self.messages[:-10])
        self.messages = system + [summary] + recent
```

**关键设计：**
- `compact()` 是整个 Memory 系统唯一 public API，其他地方不直接操作消息
- 摘要生成用 `LLM` 调用，不做 TF-IDF 等传统 NLP
- 压缩触发时机: LLM 返回 tool_calls 后，下一轮 LLM call 前

---

## 7. Skill System

**File:** `agent/skills/loader.py`

```python
@dataclass
class Skill:
    name: str
    description: str
    prompt: str          # system prompt fragment
    tools: list[str]     # 技能关联的工具名列表
    always: bool = False  # True = 每次都加载，False = 按需加载

class SkillLoader:
    def load(self, skills_dir: str) -> list[Skill]:
        skills = []
        for path in Path(skills_dir).glob("*.md"):
            skill = self._parse_skill_md(path)
            skills.append(skill)
        return skills

    def get_system_prompt(self, skills: list[Skill]) -> str:
        """生成 system prompt 片段"""
        parts = [f"## Skill: {s.name}\n{s.prompt}" for s in skills if s.always]
        return "\n\n".join(parts)
```

**技能文件格式（`skills/` 目录）：**

```markdown
---
name: code-review
description: 执行代码审查，发现潜在 bug
tools: [Read, Bash]
always: false
---

# Code Review Skill

你是一个专业的代码审查专家。当用户要求审查代码时：
1. 先用 Read 工具阅读代码
2. 使用 Bash 执行测试
3. 总结发现的问题
```

**按需加载：** agent 发现用户意图匹配时，`SkillLoader` 把完整 skill prompt 注入到消息历史。

---

## 8. SubAgent System

### 8.1 SubAgentManager

**File:** `agent/subagent/manager.py`

```python
class SubAgentManager:
    async def delegate(
        self,
        task: str,
        tools: list[Tool],
        model: str,
        parent_msg_id: str,
    ) -> str:
        """
        Spawn a background agent for `task`.
        Returns subagent_id for tracking.
        """
        subagent_id = uuid4().hex[:8]
        sub_agent = AgentLoop(
            hooks=HookManager([ParentChannelHook(subagent_id)]),
            subagent_mode=True,
        )
        asyncio.create_task(sub_agent.run(...))
        return subagent_id
```

### 8.2 父子通信协议

**File:** `agent/subagent/protocol.py`

父子 agent 通过 `asyncio.Queue` 通信：

```
Parent Agent                          Sub Agent
    │                                      │
    │───── delegate(task) ─────────────────►│
    │                                      │
    │◄───── result_queue.get() ─────────────│
    │     (mid-turn injection)              │
    │                                      │
```

**mid-turn injection 实现：**

```python
class ParentChannelHook(Hook):
    """把子 agent 结果注入父 agent 的当前轮次"""
    async def after_tool_execute(self, tool_call, result):
        if "subagent_result" in result:
            # 构造 tool_result message，塞入父 agent 当前 messages
            self.parent_messages.append(
                Message(role="tool", tool_call_id=..., content=result)
            )
```

### 8.3 SubAgent 生命周期

1. `delegate()` 创建 subagent，传入 task + tools + parent channel
2. subagent 在后台 `asyncio.create_task` 运行，不阻塞父 agent
3. subagent 完成后，结果通过 `ParentChannelHook` 注入父 agent 当前轮
4. 父 agent 继续 LLM 循环，最终把 subagent 结果包含在回复中

---

## 9. Project Structure

```
general_agent/
├── agent/
│   ├── __init__.py
│   ├── loop.py              # AgentLoop 核心
│   ├── llm.py               # LLM 接口抽象（OpenAI/Anthropic）
│   ├── message.py           # Message dataclass
│   ├── result.py            # RunResult dataclass
│   │
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── registry.py       # ToolRegistry
│   │   ├── base.py           # Tool ABC
│   │   ├── sandbox.py        # 沙箱执行器
│   │   └── builtin/          # 内置 6 个工具
│   │       ├── read.py
│   │       ├── write.py
│   │       ├── bash.py
│   │       ├── web_search.py
│   │       ├── web_fetch.py
│   │       └── grep.py
│   │
│   ├── hooks/
│   │   ├── __init__.py
│   │   ├── manager.py        # HookManager
│   │   └── builtin/          # 内置 Hook 实现
│   │       ├── logging.py
│   │       ├── retry.py
│   │       ├── token_budget.py
│   │       └── tracing.py
│   │
│   ├── memory/
│   │   ├── __init__.py
│   │   └── manager.py        # MemoryManager + AutoCompact
│   │
│   ├── skills/
│   │   ├── __init__.py
│   │   └── loader.py         # SkillLoader
│   │
│   └── subagent/
│       ├── __init__.py
│       ├── manager.py        # SubAgentManager
│       └── protocol.py       # 父子通信协议 + mid-turn injection
│
├── skills/                   # 默认技能目录
│   ├── code-review.md
│   └── research.md
│
├── cli.py                    # CLI 入口
├── pyproject.toml
└── README.md
```

**预计代码量：** ~1500-2000 行 Python（不含测试），每个模块 80-200 行。

---

## 10. Tech Stack

| 组件 | 选择 |
|------|------|
| 语言 | Python 3.11+ |
| 异步 | `asyncio` + `asyncpg` / `aiohttp` |
| LLM 接口 | OpenAI Chat Completions API（兼容 Anthropic/Gemini） |
| 类型 | `dataclasses`, `typeddict`, `Protocol` |
| CLI | `typer`（简化版）或纯 argparse |
| 测试 | `pytest` + `pytest-asyncio` |
| 沙箱 | `subprocess` + `psutil` |

---

## 11. Extension Points (面试可展开)

| 方向 | 如何扩展 |
|------|---------|
| 新工具 | 注册 `Tool` 子类到 `ToolRegistry` |
| 新 Hook | 实现 `Hook` 接口，加入 `HookManager` |
| 持久化记忆 | `MemoryManager` 加一层 SQLite storage |
| 向量检索 | `SkillLoader` 加 `chromadb` 语义匹配 |
| 多模态 | `Tool` 接口扩展 `media` 字段 |
| 沙箱加固 | `pytest-bubble` 或 `syscall filtering` |
