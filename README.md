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
# 安装（使用 uv，更快）
uv sync --extra dev              # 运行时 + 开发/测试依赖

# 配置 API Key 和模型
cp .env.example .env
# 编辑 .env，填入 OPENAI_API_KEY 或 ANTHROPIC_API_KEY
# 可选：改 OPENAI_BASE_URL 指向其他 OpenAI 兼容 API（如 DeepSeek）
# 可选：设置 MYAGENT_PROVIDER（openai / anthropic）和 MYAGENT_MODEL 作为默认值

# 运行 CLI（OpenAI，默认；用 .env 配置的 MYAGENT_MODEL）
uv run python cli.py main "Hello"

# 或覆盖模型/提供商
uv run python cli.py main --model gpt-4o-mini "Hello"
uv run python cli.py main --provider anthropic --model claude-sonnet-4-20250514 "Hello"

# 交互模式
uv run python cli.py main --interactive

# 启动 Web UI（使用 .env 配置）
uv run python cli.py web --port 8000

# Web UI + 详细日志
MYAGENT_LOG_LEVEL=DEBUG uv run python cli.py web --port 8000 --model deepseek-v4-pro

# 运行测试
uv run pytest -q

# 运行本地 coding-agent benchmark（fake runner smoke）
uv run python cli.py benchmark benchmarks/tasks \
  --agent fake \
  --source-repo . \
  --runs-dir /tmp/myagent-benchmark-smoke \
  --fake-edit-file README.md \
  --fake-old-string '# MyAgent' \
  --fake-new-string '# MyAgent Coding Agent'
```

`uv run` 不是业务运行的必需条件，而是推荐的环境隔离方式：它会使用 `uv` 管理的项目虚拟环境，依赖版本更可复现。如果你当前 shell 的 Python 环境已经安装好依赖，也可以直接运行等价命令，例如 `python3 cli.py main "Hello"` 或 `pytest -q`。

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
├── anthropic_llm.py     # Anthropic Messages API 实现
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

## Web UI

启动 Web 界面：

```bash
# 基本启动（使用 .env 中的 MYAGENT_PROVIDER 和 MYAGENT_MODEL）
uv run python cli.py web --port 8000

# 覆盖模型
uv run python cli.py web --port 8000 --model deepseek-v4-pro

# 覆盖 provider
uv run python cli.py web --port 8000 --provider anthropic --model claude-sonnet-4-20250514

# 调试模式（Chat + Debug 双界面）
MYAGENT_DEBUG=enabled uv run python cli.py web --host 127.0.0.1 --port 8000

# 详细日志（记录 LLM 输入/输出到文件）
MYAGENT_LOG_LEVEL=DEBUG uv run python cli.py web --port 8000
```

- **Chat 界面**：正常对话，流式文本输出，工具调用可视化
- **Debug 界面**：环境变量 `MYAGENT_DEBUG=enabled` 开启，逐轮展示：
  - 发送给 LLM 的完整消息列表（system prompt、历史对话、工具结果）
  - LLM 原始响应（content、stop_reason、tool_calls）
  - 工具调用详情（名称、参数、结果）
  - Memory 压缩事件

### 日志

每次启动在 `logs/` 目录生成独立日志文件（如 `myagent-20260526-123456.log`）：

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `MYAGENT_PROVIDER` | `openai` | LLM 提供商: `openai` 或 `anthropic` |
| `MYAGENT_MODEL` | (各 provider 默认值) | 使用的模型名称 |
| `MYAGENT_LOG_LEVEL` | `INFO` | `DEBUG` 时记录 LLM 请求 payload 和原始响应 JSON |
| `MYAGENT_DEBUG` | `disabled` | `enabled` 时开启 Debug Web UI 界面 |

配置优先级：CLI 参数 `--provider` / `--model` > 环境变量 > 构造函数默认值。

- 日志同时输出到终端和文件
- HTTP 4xx/5xx 错误始终记录请求 payload 和响应 body
- 单文件最大 5MB，保留最近 5 个滚动文件

浏览器测试：

```bash
playwright install chromium
MYAGENT_DEBUG=enabled uv run pytest tests/web_tests/test_browser.py --run-real-api -v
```

## Local Benchmark

MyAgent includes a local coding-agent benchmark harness and task pack under
`benchmarks/`. The harness evaluates agents in detached git worktrees, applies
hidden evaluator tests after the agent finishes, and writes per-task artifacts.

Run the deterministic fake-runner smoke test:

```bash
uv run python cli.py benchmark benchmarks/tasks \
  --agent fake \
  --source-repo . \
  --runs-dir /tmp/myagent-benchmark-smoke \
  --fake-edit-file README.md \
  --fake-old-string '# MyAgent' \
  --fake-new-string '# MyAgent Coding Agent'
```

Run the real MyAgent runner manually when API credentials are configured:

```bash
MYAGENT_PROVIDER=openai OPENAI_API_KEY=... \
uv run python cli.py benchmark benchmarks/tasks \
  --agent myagent \
  --source-repo . \
  --runs-dir /tmp/myagent-benchmark-myagent \
  --max-iterations 30
```

Each run writes `run.json`, `summary.md`, and task-level `result.json`,
`trace.json`, `final.diff`, `test_output.txt`, and `runner.log`. Task statuses
are `passed`, `passed_with_warnings`, `failed`, or `error`; warnings mean the
hidden tests passed but the agent run still reported an issue such as
`max_iterations`.

## 技术栈

Python 3.11+ / asyncio / FastAPI / httpx / typer / tiktoken（可选）

## 设计文档

详细架构设计见 `docs/superpowers/specs/`：

- `2026-05-06-general-purpose-agent-design.md` — 架构设计
- `2026-05-06-reference-projects-analysis.md` — 参考项目分析
