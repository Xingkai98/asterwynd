# MyAgent

一个用 Python 构建的轻量级通用 AI Agent 框架。

## 功能特性

| 模块 | 说明 |
|------|------|
| **AgentLoop** | 核心循环约 100 行，消息是唯一状态，所有能力委托给插件 |
| **ToolRegistry** | 动态工具注册，`@tool_parameters` 装饰器声明工具，10 个内置工具 |
| **WorkspacePolicy** | 工作区安全边界，拒绝路径穿越、敏感文件写入、危险命令 |
| **SandboxExecutor** | subprocess 沙箱，结构化输出（exit_code/stdout/stderr/duration/timed_out） |
| **HookManager** | 6 个生命周期扩展点，内置日志/重试/追踪/预算监控 Hook |
| **MemoryManager** | AutoCompact token 压缩，超预算时用 LLM 生成摘要 |
| **SkillLoader** | Markdown 技能文件（YAML frontmatter + prompt），按需/always 加载 |
| **SubAgentManager** | asyncio 后台任务委托，ParentChannel 实现 mid-turn injection |
| **TraceRecorder** | 全量轨迹记录，迭代/工具调用/编辑/测试完整可回溯 |
| **Local Benchmark** | 23 个 coding-agent 任务，SWE-bench 风格隔离评测，多 agent 适配器 |

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
| `Write` | read_write | 创建新文件，禁止覆盖已有文件 |
| `Edit` | read_write | 精确文本替换，要求 old_string 唯一匹配，支持 replace_all |
| `Bash` | dangerous | 沙箱执行 shell 命令，返回结构化 JSON（exit_code/stdout/stderr/duration/timed_out） |
| `Grep` | read_only | 正则搜索文件/目录 |
| `InspectGitDiff` | read_only | 查看当前工作区 git diff |
| `ListFiles` | read_only | 列出目录内容，自动忽略 .git/node_modules 等 |
| `Find` | read_only | 按 glob 模式递归搜索文件 |
| `WebSearch` | read_only | DuckDuckGo HTML 搜索 |
| `WebFetch` | read_only | 获取网页内容，支持截断 |

Bash 工具内置命令安全策略：前缀白名单（git status/pytest/uv/npm...）+ 正则黑名单（42 条，覆盖 rm -rf /、fork 炸弹、curl \| sh 等）。黑名单可通过 `MYAGENT_COMMAND_DENYLIST` 环境变量追加。

## 项目结构

```
agent/
├── loop.py                  # AgentLoop 核心（~100行）
├── llm.py                   # LLM Protocol + ToolCallDelta
├── openai_llm.py            # OpenAI Chat Completions 实现
├── anthropic_llm.py         # Anthropic Messages API 实现
├── workspace_policy.py      # WorkspacePolicy 工作区安全边界
├── trace_recorder.py        # TraceRecorder 全量轨迹记录
├── message.py               # Message dataclass + 快捷构造
├── result.py                # RunResult + StopReason + ToolCallMade
├── tools/
│   ├── base.py              # Tool ABC + @tool_parameters 装饰器
│   ├── registry.py          # ToolRegistry
│   ├── sandbox.py           # SandboxExecutor + SandboxResult
│   └── builtin/             # 10 个内置工具
├── hooks/
│   ├── manager.py           # HookManager + Hook Protocol
│   └── builtin/             # 4 个内置 Hook
├── memory/
│   └── manager.py           # MemoryManager + AutoCompact
├── skills/
│   └── loader.py            # SkillLoader + Skill dataclass
└── subagent/
    ├── manager.py           # SubAgentManager
    ├── protocol.py          # ParentChannel（asyncio.Queue）
    └── parent_channel_hook.py  # mid-turn injection 实现

benchmarks/                  # 本地基准测试
├── tasks/                   # 23 个编码任务（6 类别 3 难度）
├── runner.py                # BenchmarkRunner + SWE-bench 风格隔离
├── agent_runner.py          # AgentRunner（fake/shell/myagent 适配器）
├── models.py                # 失败分类 + 指标模型
├── prompt.py                # 编码 agent 提示词构建器
└── task_schema.py           # 任务 schema 加载

skills/                      # 技能文件目录
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

MyAgent 内置本地 coding-agent 基准测试系统，位于 `benchmarks/`。评测在独立 git worktree 中运行，agent 完成后应用隐藏测试补丁，产出结构化 trace 和指标。

### 快速验证（fake agent，确定性地）

```bash
uv run python cli.py benchmark benchmarks/tasks \
  --agent fake \
  --source-repo . \
  --runs-dir /tmp/myagent-benchmark-smoke \
  --fake-edit-file README.md \
  --fake-old-string '# MyAgent' \
  --fake-new-string '# MyAgent Coding Agent'
```

### 真实 agent 评测

```bash
uv run python cli.py benchmark benchmarks/tasks \
  --agent myagent \
  --source-repo . \
  --runs-dir /tmp/myagent-benchmark \
  --max-iterations 80
```

### 任务集

23 个任务从项目 git 历史中提取，覆盖 6 个类别：

| 类别 | 数量 | 示例 |
|------|------|------|
| 工具实现 | 5 | ToolRegistry, SandboxExecutor, Read/Write 工具, Bash workspace |
| 安全策略 | 3 | .env 写入拒绝, 路径穿越防护, Bash 命令策略 |
| Agent 核心 | 7 | AgentLoop, MemoryManager, SkillLoader, SubAgent 系统 |
| 可观测性 | 3 | HookManager, 日志/追踪 Hook, 重试/预算 Hook |
| 基准设施 | 3 | 失败分类, Runner timeout, 资源泄漏修复 |
| 提示词 | 2 | 编码系统提示词, 验证命令注入 |

### 评测流程（SWE-bench 风格）

1. 在任务 base_commit 创建独立 git worktree
2. 隐藏 `benchmarks/tasks/`（agent 看不到评测文件）
3. Agent 在 worktree 中运行
4. 捕获 agent 改动 diff（`:!tests/` 排除测试文件）
5. 重置 worktree，重放源码改动
6. 应用 `test.patch`（隐藏评测测试）
7. 运行验证命令
8. 写入 `result.json`、`trace.json`、`final.diff`、`test_output.txt`、`runner.log`

结果状态：`passed`、`passed_with_warnings`、`failed`、`error`。

## 技术栈

Python 3.11+ / asyncio / FastAPI / httpx / typer / tiktoken（可选）

## 设计文档

- `docs/coding-agent-roadmap.md` — 编码 Agent 路线图（P0 已完成 / P1 进行中）
- `docs/benchmark-plan.md` — 基准测试设计（SWE-bench 参考、任务结构、评估指标）
- `docs/discussions/2026-06-15-p1-p3-scope-review.md` — P1 开发方案讨论纪要
- `docs/discussions/2026-06-15-p1-p3-scope-review.md` — P1 设计决策记录
