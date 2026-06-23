# MyAgent — 简历项目描述

## 推荐写法（简洁版）

> **MyAgent** — 通用 AI Agent 框架 | Python / asyncio
> 从零设计实现轻量级通用 AI Agent 框架，参考 nanobot/hermes-agent/openclaw/claude-code-haha。
> 核心循环约 100 行，采用分层插件架构：ToolRegistry（动态注册 + 三级权限 + 沙箱）、
> HookManager（6 个生命周期扩展点）、MemoryManager（AutoCompact token 压缩）、
> SkillLoader（Markdown 技能）、SubAgentManager（后台委托 + mid-turn injection）。
> 176 个测试全部通过，CLI 开箱即用。

---

## 展开版（面试能聊的内容）

### 项目概述

从零设计并实现了一个通用 AI Agent 框架（~1500 行 Python），参考了 nanobot、hermes-agent、openclaw、claude-code-haha 四种主流开源 Agent 架构。核心原则：**简洁可扩展，每个子系统职责单一，接口清晰，100% TDD 开发，176 个测试全部通过**。

### 核心架构

```
AgentLoop.run()  # ~100行，唯一的状态管理者
  ├── llm.chat() → LLMResponse
  ├── for tool_call in response.tool_calls:
  │     tool_registry.execute(tool_call)
  │     hooks.before/after_tool_execute()
  ├── memory.compact_if_needed()  # AutoCompact
  └── subagent_manager.delegate()  # 后台任务

工具注册    → Tool ABC + @tool_parameters 装饰器
生命周期    → Hook Protocol (6 个扩展点)
上下文管理  → MemoryManager + AutoCompact
技能系统    → Markdown YAML frontmatter
子 Agent    → asyncio.Task + ParentChannel mid-turn injection
```

### 技术亮点（面试展开）

**1. 分层插件架构**
- `AgentLoop` 是纯 orchestrator，不直接执�工具、不管理记忆
- 5 个插件各司其职：`ToolRegistry` / `HookManager` / `MemoryManager` / `SkillLoader` / `SubAgentManager`
- 扩展方式：注册 Tool 子类或传入 Hook 实例，无需改核心代码
- 面试题："如果要加监控/重试/限流，怎么做？" → 传不同 Hook

**2. 工具系统：三级权限 + 沙箱隔离**
- `read_only=True`：只读工具（Read、Grep、ListFiles、Find、RepoMap、SymbolSearch、WebSearch、WebFetch）
- `dangerous=True`：强制走 subprocess 沙箱，限制超时和资源（Bash）
- `Tool` ABC 定义统一接口，`@tool_parameters` 装饰器声明 JSON Schema
- `ToolRegistry.get_all_schemas()` 一次性获取所有工具定义给 LLM
- 面试题："如何防止恶意工具破坏系统？" → 沙箱 + 最小权限原则

**3. Hook 生命周期系统**
- `Hook` Protocol + `runtime_checkable`，结构类型安全
- 6 个扩展点：`before_iteration` / `after_llm_call` / `before_tool_execute` / `after_tool_execute` / `on_error` / `on_completion`
- 4 个内置 Hook：`LoggingHook`（结构化日志）、`TracingHook`（耗时追踪）、`RetryHook`（指数退避重试）、`TokenBudgetHook`（token 预算监控）
- 面试题："如何给 agent 加断点调试？" → `before_tool_execute` hook

**4. AutoCompact 上下文压缩**
- `MemoryManager` 在每次工具调用轮次后调用 `compact_if_needed()`
- 超过 `max_tokens` 预算时：保留 system 消息 + 最近 N 条，中间段调用 LLM 生成一段摘要
- 不依赖 TF-IDF 等传统 NLP，直接用 LLM 本身做有损压缩
- 面试题："context 越来越长怎么办？" → 工业标准方案（GPT-4o、Claude 都在用）

**5. 子 Agent 委托 + Mid-turn Injection**
- `SubAgentManager.delegate()` 用 `asyncio.create_task` 后台运行，不阻塞父 agent
- 父子通过 `ParentChannel`（`asyncio.Queue`）通信
- `ParentChannelHook` 在 `after_tool_execute` 时检查 channel，注入子 agent 结果到父 agent 当前轮次
- `role=leaf` 约定禁止递归委托
- 面试题："为什么需要子 agent？" → 并行化、专业化、责任分离

**6. Markdown 技能系统**
- 技能文件格式：YAML frontmatter（name/description/tools/always）+ Markdown prompt body
- `always=true`：每次加载；`always=false`：按需匹配注入
- `SkillLoader.match_skills()` 根据用户 query 做 string match
- 面试题："如何让 agent 调用特定技能？" → SkillLoader 解析 + 注入消息历史

### 内置工具集

`Read` / `Write` / `Edit` / `Bash`（沙箱+结构化输出） / `InspectGitDiff` / `Grep` / `ListFiles` / `Find` / `RepoMap` / `SymbolSearch` / `WebSearch` / `WebFetch`

### 技术栈

Python 3.11+ / asyncio / httpx / typer / pytest + pytest-asyncio / tiktoken（可选）

---

## 简历示例

### 选项 A — 偏架构/框架方向

```
MyAgent  |  通用 AI Agent 框架  |  Python / asyncio
从零设计实现轻量级通用 AI Agent 框架，参考 nanobot/hermes-agent/openclaw/claude-code-haha。
采用分层插件架构（ToolRegistry / HookManager / MemoryManager / SubAgentManager），
核心循环约 100 行。100% TDD 开发（44 tests）。
内置工具沙箱（subprocess + asyncio）、AutoCompact token 压缩（LLM 摘要）、
Markdown 技能系统、子 Agent 委托（mid-turn injection）。
```

### 选项 B — 偏项目经历方向

```
MyAgent  |  AI Agent 系统设计  |  Python / asyncio
独立完成通用 AI Agent 框架设计及实现（~1500 行，44 tests）

• 设计 Agent 核心循环：LLM → 工具调用 → 结果回写 → 循环，约 100 行
• 实现工具系统：动态注册（@tool_parameters）、JSON Schema 参数校验、三级权限模型（read_only/read_write/dangerous）、subprocess 沙箱隔离
• 实现 Hook 生命周期：6 个扩展点，内置 LoggingHook / RetryHook（指数退避）/ TracingHook / TokenBudgetHook
• 实现 AutoCompact：token 预算超限时用 LLM 生成摘要，不依赖传统 NLP
• 实现子 Agent 委托：asyncio.create_task 后台运行 + ParentChannel mid-turn injection
• 实现 Markdown 技能系统：YAML frontmatter 声明元信息，支持 always/按需两种加载模式
• 100% TDD 开发：每个模块先写失败测试，再写最小实现，176 个测试全部通过

参考项目：nanobot（Hook/AutoCompact）、hermes-agent（模块化架构）、openclaw（沙箱）、claude-code-haha（并发工具执行）
```

### 选项 C — 最简版（一行）

```
MyAgent：参考 nanobot/hermes-agent/openclaw/claude-code-haha 的通用 AI Agent 框架，
        分层插件架构（ToolRegistry/HookManager/MemoryManager/SubAgentManager），
        支持三级权限沙箱、Hook 生命周期扩展、AutoCompact token 压缩、Markdown 技能系统、子 Agent 委托（Python/asyncio，44 tests）
```
