# MyAgent

一个用 Python 构建的轻量级通用 AI Agent 框架。

## 功能特性

| 模块 | 说明 |
|------|------|
| **AgentLoop** | 核心循环约 100 行，消息是唯一状态，所有能力委托给插件 |
| **ToolRegistry** | 动态工具注册，`@tool_parameters` 装饰器声明工具，6 个内置工具 |
| **SandboxExecutor** | subprocess 沙箱，内存/CPU/超时限制，危险命令强制走沙箱 |
| **HookManager** | 6 个生命周期扩展点，内置日志/重试/追踪/预算监控 Hook |
| **MemoryManager** | AutoCompact token 压缩，超预算时用 LLM 生成摘要 |
| **SkillLoader** | Markdown 技能文件（YAML frontmatter + prompt），按需/always 加载 |
| **SubAgentManager** | asyncio 后台任务委托，ParentChannel 实现 mid-turn injection |

## 快速开始

```bash
# 安装
pip install -e ".[dev]"

# 运行（单次对话）
python cli.py --model gpt-4o-mini "用 Read 工具读取 /tmp 目录内容"

# 交互模式
python cli.py --interactive

# 运行测试
python -m pytest tests/ -v
```

## 内置工具集

| 工具 | 权限级别 | 说明 |
|------|---------|------|
| `Read` | read_only | 读取文件，支持行数限制 |
| `Write` | read_write | 写入文件，自动创建父目录 |
| `Bash` | dangerous | 沙箱执行 shell 命令（超时/资源限制）|
| `WebSearch` | read_only | DuckDuckGo HTML 搜索 |
| `WebFetch` | read_only | 获取网页内容，支持截断 |
| `Grep` | read_only | 正则搜索文件/目录 |

## 项目结构

```
agent/
├── loop.py              # AgentLoop 核心（~100行）
├── llm.py               # LLM Protocol + ToolCallDelta
├── openai_llm.py        # OpenAI Chat Completions 实现
├── message.py           # Message dataclass + 快捷构造
├── result.py            # RunResult + StopReason + ToolCallMade
├── tools/
│   ├── base.py          # Tool ABC + @tool_parameters 装饰器
│   ├── registry.py       # ToolRegistry
│   ├── sandbox.py        # SandboxExecutor
│   └── builtin/          # 6 个内置工具
├── hooks/
│   ├── manager.py        # HookManager + Hook Protocol
│   └── builtin/          # 4 个内置 Hook
├── memory/
│   └── manager.py        # MemoryManager + AutoCompact
├── skills/
│   └── loader.py        # SkillLoader + Skill dataclass
└── subagent/
    ├── manager.py         # SubAgentManager
    ├── protocol.py        # ParentChannel（asyncio.Queue）
    └── parent_channel_hook.py  # mid-turn injection 实现

skills/                   # 技能文件目录
├── code-review.md
└── research.md
```

## 架构设计

### 核心循环

```
messages → LLM → tool_calls? → [execute tools] → append results → repeat
                ↓
            no tools → return content
```

`AgentLoop.run()` 是唯一的状态管理者，`messages` 是唯一的可变状态。所有子系统（工具执行、记忆管理、子 Agent 委托）均通过依赖注入持有引用。

### 工具注册

```python
from agent.tools import Tool, tool_parameters, ToolRegistry

@tool_parameters(
    name="MyTool",
    description="做什么",
    parameters={"type": "object", "properties": {"arg": {"type": "string"}}}
)
class MyTool(Tool):
    read_only = True

    async def execute(self, arg: str, **kwargs) -> str:
        return f"result: {arg}"

registry = ToolRegistry()
registry.register(MyTool())
```

### Hook 扩展

```python
from agent.hooks import HookManager, Hook

class MyHook(Hook):
    async def before_iteration(self, iteration, messages): ...
    async def after_llm_call(self, response): ...
    async def before_tool_execute(self, tool_call): ...
    async def after_tool_execute(self, tool_call, result): ...
    async def on_error(self, error): ...
    async def on_completion(self, result): ...

agent = AgentLoop(hooks=HookManager([MyHook()]), ...)
```

### AutoCompact

`MemoryManager.compact_if_needed()` 在每次工具调用轮次后检查 token 预算，超限时触发压缩：

- 保留所有 `role=system` 消息
- 保留最近 N 条对话
- 中间部分调用 LLM 生成一段摘要

```python
memory = MemoryManager(max_tokens=80_000, recent_window=10, llm=openai_llm)
```

### 子 Agent 委托

```python
subagent_id = await subagent_manager.delegate(
    task="搜索相关信息",
    tools=[WebSearchTool(), WebFetchTool()],
    model="gpt-4o-mini",
    llm=openai_llm,
)
# 后台运行，结果通过 ParentChannel 注入父 agent 当前轮次
```

## 扩展指南

### 添加新工具

1. 创建 `agent/tools/builtin/my_tool.py`，继承 `Tool` ABC，使用 `@tool_parameters`
2. 在 `agent/tools/__init__.py` 中 import 并加入 `get_default_tools()`
3. 注册到 `ToolRegistry`

### 添加新 Hook

1. 实现 `Hook` Protocol（6 个方法，可以空实现）
2. 传入 `HookManager([MyHook()])`

### 添加新技能

在 `skills/` 目录创建 `.md` 文件：

```markdown
---
name: my-skill
description: 技能描述
tools: [Read, Bash]
always: false
---

# 技能标题

这里是指示 prompt...
```

## 技术栈

Python 3.11+ / asyncio / httpx / typer / tiktoken（可选）

## 设计文档

详细架构设计见 `docs/superpowers/specs/`：

- `2026-05-06-general-purpose-agent-design.md` — 架构设计
- `2026-05-06-reference-projects-analysis.md` — 参考项目分析
