# MyAgent — 简历项目描述

本文档用于把 MyAgent 讲成一个面向 Agent 相关开发岗位的 Coding Agent 系统项目，而不是“通用 AI Agent 框架”功能清单。

## 推荐写法（简洁版）

> **MyAgent** — 本地 Coding Agent 系统 | Python / asyncio / FastAPI
> 从零设计并实现面向代码仓库任务的 Agent 运行时，覆盖 LLM tool-call 循环、WorkspacePolicy 安全边界、代码理解工具、精确编辑、命令验证、轨迹记录、Web/CLI 入口和 benchmark 闭环。
> 内置 23 个 coding-agent 本地任务、SWE-bench Docker harness 路径，并接入 Claw-SWE-Bench 统一对比框架，用于评估 MyAgent 与 Aider、OpenCode 等外部 coding agent 在同类任务上的表现。

---

## 展开版（面试能聊的内容）

### 项目概述

MyAgent 是一个可运行、可观测、可评测的本地 Coding Agent 系统。项目目标不是做通用聊天机器人，而是围绕真实代码仓库任务构建一条完整链路：

```text
理解仓库 -> 调用工具 -> 修改代码 -> 运行验证 -> 记录轨迹 -> benchmark 评估
```

系统核心用 Python / asyncio 实现，包含 AgentLoop、工具协议、权限与工作区安全、上下文压缩、子 session runtime、CLI/Web 入口、代码理解能力和 benchmark 基础设施。当前测试集中约 450+ 个测试函数，覆盖工具、AgentLoop、Web session、benchmark runner、workspace safety 等关键路径。

### 核心架构

```text
AgentLoop.run()
  ├── LLM provider: OpenAI-compatible / Anthropic-compatible
  ├── ToolRegistry: schema 暴露、工具注册、工具执行
  ├── WorkspacePolicy: 路径、敏感文件、命令安全边界
  ├── MemoryManager: AutoCompact 上下文压缩
  ├── TraceRecorder: 迭代、工具调用、编辑、测试轨迹
  ├── SubAgentManager: 子 session、多次 run、transcript inspect
  └── CLI / Web / benchmark entrypoints
```

默认工具覆盖文件读取、搜索、精确编辑、命令执行、git diff 检查、repo map、符号搜索、LSP 语义查询、WebSearch 和 WebFetch。写入和命令执行受 WorkspacePolicy 与 mode policy 约束，benchmark 运行会输出 result、trace、runner log、final diff 和测试结果。

### 技术亮点（面试展开）

**1. AgentLoop 与 tool-call 协议**

- `AgentLoop` 负责 LLM -> tool call -> tool result -> next iteration 的主循环。
- 保持 assistant tool call 与 tool result 消息链合法，避免在 `max_iterations` 路径伪造最终回复。
- OpenAI-compatible 与 Anthropic-compatible provider 分别处理各自的 tool-call 序列化差异。

面试讲法：我把 AgentLoop 控制在清晰的协议层，工具、记忆、trace、Web 事件都通过独立模块接入，避免核心循环膨胀。

**2. WorkspacePolicy 与工具安全**

- 文件工具受 workspace root、敏感路径和路径穿越检查约束。
- `Write` 禁止覆盖已有文件，`Edit` 要求精确 old/new string，默认只允许唯一匹配。
- `Bash` 返回结构化 JSON，并经过命令 denylist / allowlist 检查。
- 工具风险、来源和能力正在向 permission profile 模型收敛，为 MCP、browser use 等外部能力预留安全边界。

面试讲法：Coding Agent 的风险不只在 prompt，而在运行时边界；路径、命令、工具来源和风险等级必须由系统层显式约束。

**3. Code Intelligence**

- `RepoMap` 生成仓库结构和顶层符号摘要。
- `SymbolSearch` 支持基于 Python AST 和 tree-sitter 的符号搜索。
- LSP 工具支持 Python 的 definition、references、hover、document symbols、workspace symbols 和 diagnostics。
- `Write` / `Edit` 后可触发 LSP 诊断反馈，帮助 agent 在修改后立即发现语义错误。

面试讲法：我没有一开始就做重型 RAG，而是先做适合 Coding Agent 的低成本代码理解能力，再逐步接 LSP 语义工具。

**4. 上下文与子 session runtime**

- `MemoryManager` 在 token 超预算时保留 system 消息和最近窗口，中间历史由 LLM 摘要压缩。
- `SubAgentManager` 把子 agent 建模成可 inspect 的子 session，而不是一次性 helper。
- 子 session 有独立 transcript、mode、run history 和 trace 关联，适合后续 CLI/Web/TUI 统一展示。

面试讲法：子 agent 的关键不是“并发调用一次 LLM”，而是运行时边界、可观察性和可恢复的 transcript。

**5. 可观测性与 Web/CLI**

- `TraceRecorder` 记录 LLM iteration、工具调用、工具结果、编辑和测试信息。
- Web UI 使用 FastAPI / WebSocket，包含 Chat 和 Debug 视图。
- Chat 展示 session id、run id、mode、Plan Document、planning state、assistant streaming 和工具结果折叠。
- Debug 视图可查看每轮 LLM 输入输出、工具调用和 Memory compact 事件。

面试讲法：Agent 系统必须能解释自己做过什么，否则 benchmark 失败时无法定位是模型、工具、prompt 还是环境问题。

**6. Benchmark 闭环**

- 内置 `benchmarks/` runner：23 个本地 coding-agent 任务，支持 worktree 隔离、hidden `test.patch`、fake/shell/MyAgent runner、结构化 artifact。
- 外部 `swebench-*` 任务：通过 Docker preflight 和 SWE-bench harness 验证 patch。
- Claw-SWE-Bench 集成：`claw-swe-bench/` 注册 MyAgent、Aider、OpenCode adapter；MyAgent 通过 `agent/claw_solve.py` 在目标容器内运行 headless solver。
- 结果状态区分 `passed`、`passed_with_warnings`、`unsupported`、`failed`、`error`，失败原因写入 `reason`。

面试讲法：我用 benchmark 把 Agent 能力从“看起来能跑”变成可量化证据，能比较不同 agent、模型和失败模式。

---

## 简历示例

### 选项 A — 偏 Agent 工程方向

```text
MyAgent | 本地 Coding Agent 系统 | Python / asyncio / FastAPI
从零设计实现面向代码仓库任务的 Agent 运行时，覆盖 LLM tool-call 循环、
WorkspacePolicy 安全边界、代码理解工具、精确编辑、命令验证、轨迹记录和 CLI/Web 入口。
内置 23 个本地 coding-agent benchmark 任务、SWE-bench Docker harness 路径，
并接入 Claw-SWE-Bench 对比 MyAgent / Aider / OpenCode 等 agent 的解题表现。
```

### 选项 B — 偏 AI Infra / Runtime 方向

```text
MyAgent | Agent Runtime / AI Infra 项目 | Python / asyncio
独立实现 Coding Agent 运行时和工具系统：AgentLoop 维护合法 tool-call 消息链，
ToolRegistry 暴露 JSON Schema 并执行 Read/Edit/Bash/RepoMap/LSP/Web 工具，
WorkspacePolicy 统一约束路径、敏感文件和命令风险。
实现 TraceRecorder、AutoCompact、SubAgent session runtime、WebSocket Debug UI 和 benchmark artifact，
用约 450+ 回归测试覆盖核心协议、工具安全、Web session 和 benchmark runner。
```

### 选项 C — 偏 Benchmark / 评测方向

```text
MyAgent | Coding Agent Benchmark 闭环 | Python / Docker / SWE-bench
设计实现可复现 benchmark runner：本地任务使用 git worktree 隔离和 hidden test patch，
外部任务接 SWE-bench Docker harness，输出 result.json / trace.json / final.diff / runner.log。
集成 Claw-SWE-Bench，新增 MyAgent headless solver 与 MyAgent/Aider/OpenCode adapter，
用于在同一批 SWE-bench Verified 实例上比较不同 coding agent 的 pass rate 和失败原因。
```

### 选项 D — 一行版

```text
MyAgent：本地 Coding Agent 系统，覆盖 AgentLoop、工具协议、WorkspacePolicy、Code Intelligence、AutoCompact、SubAgent runtime、Web Debug 和 benchmark 闭环，并接入 SWE-bench / Claw-SWE-Bench 做可复现评测。
```
