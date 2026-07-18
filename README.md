<p align="center">
  <img src="./docs/assets/asterwynd-wordmark.svg?v=20260628-centered" alt="Asterwynd" width="760" />
</p>

<p align="center">
  <a href="./README.md">简体中文</a>
  ·
  <a href="./README_EN.md">English</a>
</p>

<p align="center">
  <strong>以星为引，变更有证。</strong>
</p>

**Asterwynd** 是一个本地 Coding Agent 系统。它理解代码仓库、找到从问题到修复的路径、调用工具执行变更和验证，并留下完整的 diff、日志、工具 trace 与 benchmark 证据——让每次代码修改都是可证明的，而不只是“看起来对的”。

星辰定向，风推动前行，trace 证明来过。

## 功能特性

| 模块 | 说明 |
|------|------|
| **AgentLoop** | 核心循环约 100 行，消息是唯一状态，所有能力委托给插件 |
| **ToolRegistry** | 动态工具注册，`@tool_parameters` 装饰器声明工具，包含文件、命令、代码理解和联网研究工具 |
| **Code Intelligence** | Tree-sitter 多语言符号提取、Repo Map、Python AST 符号提取、LSP 语义工具（定义跳转、引用、hover、诊断） |
| **WorkspacePolicy** | 工作区安全边界，拒绝路径穿越、敏感文件写入、危险命令 |
| **Workflow Control Plane** | 独立事件驱动开发流程控制面，覆盖 WorkItem、human gate、worktree binding、Prompt Adapter 和签名 receipt |
| **SandboxExecutor** | subprocess 沙箱，结构化输出（exit_code/stdout/stderr/duration/timed_out） |
| **HookManager** | 6 个生命周期扩展点，内置日志/重试/追踪/预算监控 Hook |
| **MemoryManager** | 90% 阈值 AutoCompact、可插拔 Summarizer（LLM 四段式摘要 / 截断降级） |
| **ContextBuilder** | 上下文注入管线，统一编排 ASTER.md、记忆索引、技能、计划、待办等 ContextSource |
| **Browser** | 受控只读浏览器：导航、截图、内容提取、标签页管理，安全策略约束 |
| **SkillRuntime** | 目录式 Markdown skill 加载、index 注入、按需/always 激活、`/skill args` 显式调用 |
| **MCP Adapter** | 连接 stdio / Streamable HTTP MCP server，注册 MCP tools，并通过 `/mcp-prompt`、`/mcp-resource` 注入上下文 |
| **SubAgentManager** | 子 session runtime：独立 transcript、多个子 session、单 session 多次 run、显式 inspect |
| **TraceRecorder** | 全量轨迹记录，迭代/工具调用/编辑/测试完整可回溯 |
| **Benchmark** | 23 个本地 coding-agent 任务、SWE-bench Docker harness 任务，以及 Claw-SWE-Bench 多 agent 对比入口 |

## 快速开始

```bash
# 安装（使用 uv，更快）
uv sync --extra dev              # 运行时 + 开发/测试依赖

# 配置 API Key 和模型
cp .env.example .env
# 编辑 .env，填入 OPENAI_API_KEY 或 ANTHROPIC_API_KEY
# 可选：改 OPENAI_BASE_URL 指向其他 OpenAI 兼容 API（如 DeepSeek）
# 可选：设置 ASTERWYND_PROVIDER（openai / anthropic）和 ASTERWYND_MODEL 作为默认值

# 运行 CLI（OpenAI，默认；用 .env 配置的 ASTERWYND_MODEL）
uv run asterwynd run "Hello"

# 或覆盖模型/提供商
uv run asterwynd run --model gpt-4o-mini "Hello"
uv run asterwynd run --provider anthropic --model claude-sonnet-4-20250514 "Hello"

# 交互模式
uv run asterwynd

# 启动 Web UI（使用 .env 配置）
uv run asterwynd web --port 8000

# Web UI + 详细日志
ASTERWYND_LOG_LEVEL=DEBUG uv run asterwynd web --port 8000 --model deepseek-v4-pro

# 运行测试
uv run pytest -q

# 运行本地 coding-agent benchmark（fake runner smoke）
uv run asterwynd benchmark benchmarks/tasks \
  --agent fake \
  --source-repo . \
  --runs-dir /tmp/asterwynd-benchmark-smoke \
  --fake-edit-file README.md \
  --fake-old-string '# Asterwynd' \
  --fake-new-string '# Asterwynd Coding Agent'

# 运行 Claw-SWE-Bench 统一 harness（需先准备 Docker 镜像和环境变量）
cd claw-swe-bench
uv run python run_infer.py \
  --claw asterwynd \
  --dataset verified \
  --instance_file config/verified_mini_50.txt \
  --run_id asterwynd-lite \
  --model deepseek-v4-pro
```

`uv run` 不是业务运行的必需条件，而是推荐的环境隔离方式：它会使用 `uv` 管理的项目虚拟环境，依赖版本更可复现。如果你当前 shell 的 Python 环境已经安装好依赖，也可以直接运行等价命令，例如 `asterwynd run "Hello"` 或 `pytest -q`。

## 内置工具集

| 工具 | 权限级别 | 说明 |
|------|---------|------|
| `Read` | read_only | 读取文件，支持行数限制 |
| `Write` | read_write | 创建新文件，禁止覆盖已有文件 |
| `Edit` | read_write | 精确文本替换，要求 old_string 唯一匹配，支持 replace_all |
| `Bash` | command_execute / high | 沙箱执行 shell 命令，返回结构化 JSON（exit_code/stdout/stderr/duration/timed_out） |
| `Grep` | read_only | 正则搜索文件/目录 |
| `InspectGitDiff` | read_only | 查看当前工作区 git diff |
| `ListFiles` | read_only | 列出目录内容，自动忽略 .git/node_modules 等 |
| `Find` | read_only | 按 glob 模式递归搜索文件 |
| `RepoMap` | read_only | 生成仓库结构和已支持语言的顶层符号摘要 |
| `SymbolSearch` | read_only | 在仓库内按名称搜索已支持语言的符号 |
| `WebSearch` | read_only | DuckDuckGo HTML 搜索，返回带 provider 的稳定文本结果 |
| `WebFetch` | read_only | 获取网页正文，返回状态/类型/截断诊断 |
| `BrowserNavigate` | read_only | 浏览器导航到指定 URL |
| `BrowserScreenshot` | read_only | 截取当前页面视口截图 |
| `BrowserGetContent` | read_only | 提取页面可交互元素和文本内容 |
| `BrowserScroll` | read_only | 滚动页面指定像素 |
| `BrowserTabs` | read_only | 管理浏览器标签页（新建/切换/关闭） |

Bash 工具内置命令安全策略：先经过 mode permission profile 判权；默认 `build` mode 下 high risk 命令执行需要审批，CLI 单轮和 benchmark 等无人值守入口 fail closed。实际执行前仍会检查正则黑名单（覆盖 rm -rf /、fork 炸弹、curl \| sh 等），再匹配安全命令前缀白名单（git status/pytest/uv/npm...）。项目级命令拒绝规则、permission profile 和 ListFiles / Find 忽略规则通过 `asterwynd.yaml` 配置扩展，见 `asterwynd.example.yaml`。

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
├── config.py                # 配置加载（asterwynd.yaml）
├── session.py               # SessionStore 会话持久化
├── approval.py              # ApprovalHandler 工具审批
├── background.py            # BackgroundTaskManager 后台任务
├── run_config.py            # AgentRuntimeState + mode transition
├── run_identity.py          # RunId / SessionId 标识
├── tool_permissions.py      # ToolPermission + ModePolicy
├── tool_result_display.py   # ToolResultDisplayConfig
├── branding.py              # Asterwynd 品牌信息
├── assets/                  # 品牌资源
├── commands/
│   ├── registry.py          # SlashCommandRegistry
│   └── init.py              # /init 命令（ASTER.md 生成）
├── context/
│   ├── protocol.py          # BuildContext + ContextSource Protocol
│   ├── builder.py           # ContextBuilder 管线编排
│   ├── sources.py           # 8 个内置 ContextSource
│   └── summarizer.py        # Summarizer Protocol + LLMSummarizer + TruncationSummarizer
├── tools/
│   ├── base.py              # Tool ABC + @tool_parameters 装饰器
│   ├── registry.py          # ToolRegistry
│   ├── sandbox.py           # SandboxExecutor + SandboxResult
│   └── builtin/             # 内置工具（文件/命令/浏览器/搜索等）
├── hooks/
│   ├── manager.py           # HookManager + Hook Protocol
│   └── builtin/             # 4 个内置 Hook
├── memory/
│   └── manager.py           # MemoryManager + AutoCompact
├── planning/
│   └── manager.py           # PlanningManager 结构化计划状态
├── mcp/
│   ├── manager.py           # MCP server 连接、discovery 和调用
│   └── tools.py             # MCP-backed Tool wrapper
├── skills/
│   ├── loader.py            # SkillLoader + Skill dataclass
│   └── runtime.py           # SkillRuntime + 当前 run skill 激活
├── subagent/
│   └── manager.py           # SubAgentManager 子 session runtime
├── browser/
│   ├── service.py           # BrowserService 浏览器进程管理
│   ├── session.py           # BrowserSession 标签页/导航管理
│   └── policy.py            # BrowserPolicy 安全策略
├── code_intelligence/
│   └── ...                  # RepoMap / SymbolSearch 实现
├── lsp/
│   └── ...                  # LSP server 管理与语义工具
├── workflow/
│   └── ...                  # Handoff 状态机 + 生命周期追踪
└── tui/
    └── ...                  # 终端 UI 运行时视图

workflow_control/            # Workflow Control Plane 领域模型、CLI adapter、receipt 签名审计

benchmarks/                  # 本地 benchmark runner
├── tasks/                   # 34 个编码任务（asterwynd-* + swebench-*）
├── runner.py                # BenchmarkRunner + SWE-bench 风格隔离
├── agent_runner.py          # AgentRunner（fake/shell/asterwynd 适配器）
├── models.py                # 失败分类 + 指标模型
├── prompt.py                # 编码 agent 提示词构建器
└── task_schema.py           # 任务 schema 加载

claw-swe-bench/              # Claw-SWE-Bench 统一 harness 副本和 adapter
└── claw_swebench/claws/
    ├── asterwynd.py           # Asterwynd adapter
    ├── aider.py             # Aider adapter
    └── opencode_adapter.py  # OpenCode adapter（受 endpoint 支持限制）

skills/                      # 技能文件目录
├── code-review/
│   └── SKILL.md
└── research/
    └── SKILL.md
```

## 架构设计

### 核心循环

```
messages → LLM → tool_calls? → [execute tools] → append results → repeat
                ↓
            no tools → return content
```

`AgentLoop.run()` 是唯一的状态管理者，`messages` 是唯一的可变状态。所有子系统（工具执行、记忆管理、子 session runtime）均通过依赖注入持有引用。

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

`MemoryManager.compact_if_needed()` 在每次工具调用轮次后检查 token 预算，达到 90% 阈值时触发压缩：

- 保留所有 `role=system` 消息
- 保留最近 N 条对话（含 tool-call 链完整性保护）
- 中间部分通过可插拔 `Summarizer` 生成摘要（LLM 四段式结构化摘要，无 LLM 时截断降级）
- 摘要以 `role=user` 消息注入（语义上为"前序会话上下文"）

```python
memory = MemoryManager(max_tokens=80_000, recent_window=10, llm=openai_llm)
```

### 子 Session Runtime

```python
subagent = subagent_manager.create_subagent(
    name="research",
    description="只读调查代码和文档",
    mode="read_only",
)

run = await subagent_manager.run_subagent(
    subagent_id=subagent["subagent_id"],
    task="搜索相关信息",
    wait=True,
)

print(run["status"], run["summary"])
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

在 `skills/<name>/SKILL.md` 创建目录式 skill：

```markdown
---
name: my-skill
description: 技能描述
tools: [Read, Bash]
always: false
user_invocable: true
argument_hint: <request>
triggers:
  - 触发词
---

# 技能标题

这里是指示 prompt...
```

每次 run 都会向模型注入简短 skill index。完整 skill prompt 只在 `always: true`、本地匹配、显式 `/my-skill ...` 或 `ActivateSkill` 工具激活时进入当前 run context。交互模式可用 `/skills` 查看加载结果、`/skills reload` 重新加载 configured skill roots。

## Web UI

启动 Web 界面：

```bash
# 基本启动（使用 .env 中的 ASTERWYND_PROVIDER 和 ASTERWYND_MODEL）
uv run asterwynd web --port 8000

# 覆盖模型
uv run asterwynd web --port 8000 --model deepseek-v4-pro

# 覆盖 provider
uv run asterwynd web --port 8000 --provider anthropic --model claude-sonnet-4-20250514

# 调试模式（Chat + Debug 双界面）
ASTERWYND_DEBUG=enabled uv run asterwynd web --host 127.0.0.1 --port 8000

# 详细日志（记录 LLM 输入/输出到文件）
ASTERWYND_LOG_LEVEL=DEBUG uv run asterwynd web --port 8000
```

- **Chat 界面**：正常对话，assistant Markdown 渲染，工具调用可视化，长工具结果按展示策略折叠，展示当前 session id / run id / session mode，支持切换 `build` / `read_only` / `plan`，展示 Plan Document 和 planning state，并在工具需要审批时显示审批卡片
- **Debug 界面**：环境变量 `ASTERWYND_DEBUG=enabled` 开启，逐轮展示：
  - 发送给 LLM 的完整消息列表（system prompt、历史对话、工具结果）
  - LLM 响应（content、stop_reason、tool_calls；工具参数按审批脱敏规则展示）
  - 工具调用详情（名称、脱敏参数、结果）
  - AgentLoop 通过 Web session 事件流发送的 Memory 压缩事件

CLI 交互模式支持在同一 session 内通过 `/mode build`、`/mode read_only` 和 `/mode plan` 切换当前 session mode；CLI 单轮模式仍通过 `--mode` 指定初始 mode。

### 日志

每次启动在 `logs/` 目录生成独立日志文件（如 `asterwynd-20260526-123456.log`）：

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `ASTERWYND_PROVIDER` | `openai` | LLM 提供商: `openai` 或 `anthropic` |
| `ASTERWYND_MODEL` | (各 provider 默认值) | 使用的模型名称 |
| `ASTERWYND_LOG_LEVEL` | `INFO` | `DEBUG` 时记录 LLM 请求 payload 和原始响应 JSON |
| `ASTERWYND_DEBUG` | `disabled` | `enabled` 时开启 Debug Web UI 界面 |

配置优先级：CLI 显式参数 > 进程环境变量 > `.env` 加载值 > `asterwynd.yaml` > 代码默认值。API key、base URL、provider、model、debug 和 log level 继续使用 `.env` 或环境变量；agent mode、permission profile、mode deny override、工具策略、工具结果展示阈值和 benchmark 默认参数使用 `asterwynd.yaml`。

- 日志同时输出到终端和文件
- HTTP 4xx/5xx 错误始终记录请求 payload 和响应 body
- 单文件最大 5MB，保留最近 5 个滚动文件

浏览器测试：

```bash
playwright install chromium
ASTERWYND_DEBUG=enabled uv run pytest tests/web_tests/test_browser.py --run-real-api -v
```

## Benchmark

Asterwynd 当前有两条 benchmark 路径：

- `benchmarks/`：项目内置 runner，用 34 个本地任务和少量 `swebench-*` 外部任务验证 Asterwynd 的 coding-agent 闭环。
- `claw-swe-bench/`：Claw-SWE-Bench 统一 harness，用同一批 SWE-bench Verified 实例对比 Asterwynd、Aider、OpenCode 等外部 coding agent。

### 快速验证（fake agent，确定性地）

```bash
uv run asterwynd benchmark benchmarks/tasks \
  --agent fake \
  --source-repo . \
  --runs-dir /tmp/asterwynd-benchmark-smoke \
  --fake-edit-file README.md \
  --fake-old-string '# Asterwynd' \
  --fake-new-string '# Asterwynd Coding Agent'
```

### 真实 agent 评测

```bash
uv run asterwynd benchmark benchmarks/tasks \
  --agent asterwynd \
  --source-repo . \
  --runs-dir /tmp/asterwynd-benchmark \
  --max-iterations 80
```

### Claw-SWE-Bench 对比评测

详细环境准备见 [CLAW-SWE-BENCH.md](./CLAW-SWE-BENCH.md)。最小命令形态：

```bash
cd claw-swe-bench
uv run python run_infer.py \
  --claw asterwynd \
  --dataset verified \
  --instance_file config/verified_mini_50.txt \
  --run_id asterwynd-lite \
  --model deepseek-v4-pro

uv run python run_eval.py --run_id asterwynd-lite --dataset verified
```

### 任务集

34 个任务从项目 git 历史中提取，覆盖多个类别：

| 类别 | 示例 |
|------|------|
| 工具实现 | ToolRegistry, SandboxExecutor, Read/Write 工具, Bash workspace, Browser 工具 |
| 安全策略 | .env 写入拒绝, 路径穿越防护, Bash 命令策略, Browser 安全策略 |
| Agent 核心 | AgentLoop, MemoryManager, SkillRuntime, SubAgent 系统, 上下文注入管线 |
| 可观测性 | HookManager, 日志/追踪 Hook, 重试/预算 Hook |
| 基准设施 | 失败分类, Runner timeout, 资源泄漏修复, Docker preflight |
| 提示词与输入 | 编码系统提示词, 验证命令注入, 多模态输入 |

### 评测流程

本地 `asterwynd-*` 任务：

1. 在任务 base_commit 创建独立 git worktree
2. 隐藏 `benchmarks/tasks/`（agent 看不到评测文件）
3. Agent 在 worktree 中运行
4. 捕获 agent 改动 diff（`:!tests/` 排除测试文件）
5. 重置 worktree，重放源码改动
6. 应用 `test.patch`（隐藏评测测试）
7. 运行验证命令
8. 写入 `result.json`、`trace.json`、`runner.log`；`final.diff` 在 diff capture 完成后写入，`test_output.txt` 在验证命令实际运行后写入

外部 `swebench-*` 任务：

1. clone 任务指定的外部仓库并切到 `base_commit`
2. Agent 在 benchmark workspace 中修改代码并产出最终 git patch
3. runner 做一次 run 级 Docker preflight
4. Docker 可用时，将 patch 交给 SWE-bench Docker harness 验证
5. Docker 不可用时，写出 `result.json`、`trace.json`、`runner.log`，并将结果标记为 `unsupported`

结果状态：`passed`、`passed_with_warnings`、`unsupported`、`failed`、`error`；细节归因统一写入 `reason` 字段。

## 技术栈

Python 3.11+ / asyncio / FastAPI / httpx / typer / tiktoken（可选）

## 设计文档

- `docs/coding-agent-roadmap.md` — 编码 Agent 路线图
- `docs/benchmark-plan.md` — benchmark 设计（本地 runner、SWE-bench Docker harness、Claw-SWE-Bench 对比入口）
- `CLAW-SWE-BENCH.md` — Claw-SWE-Bench 集成和运行指南
