# MyAgent 新人上手指南

**项目**: myagent — 轻量级通用 AI Agent 框架（Python）
**分析时间**: 2026-05-07 | **Commit**: e967533

---

## 项目概述

MyAgent 是一个用 Python 构建的轻量级通用 AI Agent 框架，采用**插件化架构**，每个插件子系统独立可解释、可测试。核心约 100 行，唯一状态是 messages list，所有能力委托给插件。

| 信息 | 内容 |
|------|------|
| 语言 | Python ≥ 3.11 |
| 框架 | Aiohttp (HTTP client), Pytest (测试) |
| 依赖管理 | uv |
| 关键依赖 | httpx, typer, python-dotenv, tiktoken |

---

## 架构分层

```
┌─────────────────────────────────────────────┐
│  CLI Entry Point (cli.py)                   │
│    build_agent() → 实例化所有插件            │
└──────────────┬──────────────────────────────┘
               │
┌──────────────▼──────────────────────────────┐
│  Core Layer (agent/loop.py)                  │
│  AgentLoop: messages→LLM→tool_calls→执行循环 │
│  协议: LLM, Message, Result, ToolCall         │
└──────────────┬──────────────────────────────┘
               │ 委托给各 Plugin System
  ┌────────────┼────────────┬────────────┐
  ▼            ▼            ▼            ▼
Tool系统      Hook系统     Memory系统   Skills系统   SubAgent系统
(动态注册     (6个生命周期   (AutoCompact   (Markdown    (asyncio
 +沙箱执行)    扩展点)       token压缩)    skill加载)   任务委托)
```

### 各层职责

| 层级 | 文件 | 说明 |
|------|------|------|
| **Core** | `loop.py`, `llm.py`, `message.py`, `result.py` | AgentLoop 编排、LLM 协议、消息/结果数据类型 |
| **LLM Providers** | `openai_llm.py`, `anthropic_llm.py` | 实现 LLM Protocol，支持 OpenAI 和 Anthropic |
| **Tool System** | `base.py`, `registry.py`, `sandbox.py` | 动态工具注册、@tool_parameters 装饰器、沙箱执行 |
| **Hook System** | `manager.py` + `builtin/` | 6 个生命周期扩展点（Logging/Tracing/Retry/TokenBudget）|
| **Memory** | `memory/manager.py` | AutoCompact token 压缩，超预算时 LLM 生成摘要 |
| **Skills** | `skills/loader.py` | Markdown skill 文件解析，YAML frontmatter |
| **SubAgent** | `manager.py`, `protocol.py`, `parent_channel_hook.py` | asyncio 后台任务委托，ParentChannel mid-turn injection |
| **CLI** | `cli.py` | Typer CLI，提供 single/interactive 两种运行模式 |

---

## 引导教程（13 步）

1. **Project Overview** — `README.md` 项目整体介绍
2. **CLI Entry Point** — `cli.py` 初始化所有插件系统的入口
3. **AgentLoop Core** — `agent/loop.py` 唯一编排器，消息为唯一状态
4. **Core Types** — `llm.py`(LLM Protocol), `message.py`(Message), `result.py`(RunResult)
5. **LLM Providers** — `openai_llm.py`, `anthropic_llm.py` 实现 LLM 协议
6. **Tool Registry and Base** — `base.py`(Tool ABC + @tool_parameters), `registry.py` 动态注册
7. **Builtin Tools** — Read/Write/Bash/WebSearch/WebFetch/Grep + `sandbox.py` 沙箱
8. **Hook System** — `manager.py` + LoggingHook/TracingHook/RetryHook/TokenBudgetHook
9. **Memory Manager** — `memory/manager.py` AutoCompact token 压缩
10. **Skill Loader** — `skills/loader.py` Markdown+YAML skill 解析
11. **SubAgent System** — `manager.py` + `protocol.py`(ParentChannel) + `parent_channel_hook.py`
12. **Architecture Spec** — `docs/superpowers/specs/2026-05-06-general-purpose-agent-design.md`
13. **Project Configuration** — `pyproject.toml` 依赖声明和构建配置

---

## 关键设计模式

### 1. 协议 + 插件化 (`agent/llm.py`, `agent/hooks/manager.py`)
```python
class LLM(Protocol):
    async def chat(messages, tools, model) -> LLMResponse: ...

class Hook(Protocol):
    async def before_iteration(self, iteration, messages) -> None: ...
```
Structural typing，无需继承，通过 HookManager 委托调用。

### 2. @tool_parameters 装饰器 (`agent/tools/base.py`)
```python
@tool_parameters(name="Read", description="读取文件", ...)
class ReadTool(Tool):
    ...
```

### 3. AutoCompact (`agent/memory/manager.py`)
消息超 token 预算时 → 保留 system + recent → 中间部分 LLM 压缩为摘要。

### 4. ParentChannel (`agent/subagent/protocol.py`)
asyncio.Queue 实现 parent↔subagent 双向通信，ParentChannelHook 桥接到 Hook 生命周期。

---

## 文件地图

### Core
| 文件 | 作用 |
|------|------|
| `agent/loop.py` | AgentLoop 核心编排，~100 行，唯一状态是 messages |
| `agent/llm.py` | LLM Protocol + ToolCallDelta, LLMResponse |
| `agent/message.py` | Message dataclass (role/content/toolCall)，快捷构造器 |
| `agent/result.py` | StopReason, ToolCallMade, RunResult |

### LLM Providers
| 文件 | 作用 |
|------|------|
| `agent/openai_llm.py` | OpenAI Chat Completions API，httpx AsyncClient |
| `agent/anthropic_llm.py` | Anthropic Messages API，格式转换层 |

### Tool System
| 文件 | 作用 |
|------|------|
| `agent/tools/base.py` | Tool ABC + @tool_parameters + ToolCall |
| `agent/tools/registry.py` | 动态注册 + 按名执行工具 |
| `agent/tools/sandbox.py` | subprocess 沙箱（timeout/CPU/内存限制）|
| `agent/tools/builtin/read.py` | ReadTool — pathlib 读文件 |
| `agent/tools/builtin/write.py` | WriteTool — pathlib 写文件（自动创建父目录）|
| `agent/tools/builtin/bash.py` | BashTool — 沙箱执行 shell 命令 |
| `agent/tools/builtin/grep.py` | GrepTool — 正则搜索文件/目录 |
| `agent/tools/builtin/web_search.py` | WebSearchTool — DuckDuckGo HTML 搜索 |
| `agent/tools/builtin/web_fetch.py` | WebFetchTool — httpx 获取网页内容 |

### Hook System
| 文件 | 作用 |
|------|------|
| `agent/hooks/manager.py` | HookManager 持有 list[Hook]，广播到所有 Hook |
| `agent/hooks/builtin/logging.py` | LoggingHook — 日志记录所有生命周期事件 |
| `agent/hooks/builtin/tracing.py` | TracingHook — 工具执行耗时追踪 |
| `agent/hooks/builtin/retry.py` | RetryHook — 指数退避重试 |
| `agent/hooks/builtin/token_budget.py` | TokenBudgetHook — token 预算警告 |

### Memory
| 文件 | 作用 |
|------|------|
| `agent/memory/manager.py` | MemoryManager — 消息历史 + AutoCompact |

### Skills
| 文件 | 作用 |
|------|------|
| `agent/skills/loader.py` | SkillLoader — 解析 Markdown+YAML skill 文件 |

### SubAgent
| 文件 | 作用 |
|------|------|
| `agent/subagent/manager.py` | SubAgentManager — asyncio 后台任务委托 |
| `agent/subagent/protocol.py` | ParentChannel (Queue) + SubAgentResult |
| `agent/subagent/parent_channel_hook.py` | ParentChannelHook — 桥接 Hook 生命周期 |

### CLI
| 文件 | 作用 |
|------|------|
| `cli.py` | build_llm/build_agent + single/interactive 命令 |

---

## 复杂度热点

以下文件较复杂，新人应谨慎修改：

| 文件 | 复杂度 | 原因 |
|------|--------|------|
| `agent/anthropic_llm.py` | 较高 | 格式转换逻辑（OpenAI ↔ Anthropic message schema）|
| `agent/memory/manager.py` | 中等 | AutoCompact LLM 摘要逻辑 |
| `agent/subagent/parent_channel_hook.py` | 中等 | 多 hook 点同时注册，mid-turn injection |
| `agent/tools/sandbox.py` | 中等 | subprocess 资源限制（CPU/内存/超时）|