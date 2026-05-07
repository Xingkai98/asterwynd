# MyAgent — 简历项目描述

## 推荐写法（简洁版）

> **MyAgent** — 通用 AI Agent 框架
> Python / asyncio / OpenAI Chat Completions API
> GitHub: github.com/your-username/MyAgent
>
> 设计并实现了一个轻量级通用 AI Agent 框架，采用分层插件架构，核心循环仅约 100 行代码。支持：动态工具注册与沙箱执行（read_only/read_write/dangerous 三级权限）、Hook 生命周期扩展机制（before_iteration / before_tool_execute / after_tool_execute 等）、基于 token 预算的 AutoCompact 上下文压缩、Markdown 格式技能系统（运行时动态加载）、子 Agent 任务委托与 mid-turn injection 通信协议。参考了 nanobot、hermes-agent、openclaw、claude-code-haha 等主流开源 Agent 设计。

---

## 展开版（面试能聊的内容）

### 项目概述
从零设计并实现了一个通用 AI Agent 框架，参考了 nanobot、hermes-agent、openclaw、claude-code-haha 四种主流开源 Agent 架构。核心原则：**简洁可扩展，每个子系统职责单一，接口清晰**。

### 核心架构（面试可展开）
```
AgentLoop（核心，约100行）
  ├── ToolRegistry（工具注册 + 沙箱执行 + 权限分级）
  ├── HookManager（生命周期扩展点）
  ├── MemoryManager（AutoCompact token压缩）
  ├── SkillLoader（Markdown技能动态加载）
  └── SubAgentManager（后台委托 + mid-turn injection）
```

### 技术亮点（面试时能展开讲的点）

**1. 分层插件架构**
- 核心循环不直接执�工具、不直接管理记忆，全部委托给专用插件
- 新增工具：注册 Tool 子类即可；新增扩展：实现 Hook 接口
- 面试题："如果要加监控/重试/限流，怎么做？" → 传不同 Hook

**2. 工具沙箱 + 权限分级**
- `read_only` / `read_write` / `dangerous` 三级，危险操作强制 subprocess 沙箱
- 使用 psutil 限制内存/CPU，能力降级（capability drop）
- 面试题："如何防止恶意工具破坏系统？" → 沙箱 + 最小权限

**3. Hook 生命周期系统**
- 5 个扩展点：before_iteration、after_llm_call、before_tool_execute、after_tool_execute、on_error、on_completion
- 内置 LoggingHook、RetryHook（失败重试2次）、TokenBudgetHook、TracingHook
- 面试题："如何给 agent 加断点调试？" → before_tool_execute hook

**4. AutoCompact 上下文压缩**
- token 预算超限时，保留 system + 最近10条，中间压缩为 LLM 摘要
- 不做 TF-IDF 等传统 NLP，用 LLM 本身做压缩
- 面试题："context 越来越长怎么办？" → 工业标准方案

**5. 子 Agent 委托 + Mid-turn Injection**
- asyncio.create_task 后台运行，不阻塞父 agent
- ParentChannelHook 把子 agent 结果注入父 agent 当前轮次
- 面试题："为什么需要子 agent？" → 并行化、专业化、责任分离

**6. Markdown 技能系统**
- 技能以 .md 文件存储，YAML frontmatter 定义元信息
- always=true 每次加载，always=false 按需加载
- 面试题："如何让 agent 调用特定技能？" → SkillLoader 匹配注入

### 内置工具集
Read、Write、Bash（沙箱）、WebSearch、WebFetch、Grep

### 技术栈
Python 3.11+ / asyncio / OpenAI Chat Completions API / typer / pytest

---

## 简历示例

### 选项 A — 偏架构/框架方向
```
MyAgent  |  通用 AI Agent 框架  |  Python / asyncio
[项目地址]

从零设计实现轻量级通用 AI Agent 框架，参考 nanobot/hermes-agent/openclaw/claude-code-haha。
采用分层插件架构（ToolRegistry / HookManager / MemoryManager / SubAgentManager），
核心循环约 100 行。新增功能通过注册扩展实现，无需修改核心代码。
内置工具沙箱（subprocess + psutil）、AutoCompact token 压缩、Markdown 技能系统、子 Agent 委托。
```

### 选项 B — 偏能力/项目经历方向
```
MyAgent  |  AI Agent 系统设计  |  Python / asyncio
[项目地址]

独立完成通用 AI Agent 框架设计及实现，主要工作：
• 设计 Agent 核心循环（LLM → 工具调用 → 结果回写 → 循环，约 100 行）
• 实现工具系统：动态注册、JSON Schema 参数校验、三级权限模型、沙箱隔离执行
• 实现 Hook 生命周期系统：5 个扩展点，支持日志、重试、追踪、预算监控
• 实现 AutoCompact：token 预算超限时自动压缩上下文为 LLM 摘要
• 实现子 Agent 委托：asyncio 后台运行 + mid-turn injection，父 agent 无需等待
• 实现 Markdown 技能系统：运行时动态加载，always/按需两种加载模式
参考项目：nanobot（Hook/AutoCompact）、hermes-agent（模块化架构）、openclaw（沙箱）。
```

### 选项 C — 最简版（一行）
```
MyAgent：参考 nanobot/hermes-agent/openclaw/claude-code-haha 设计的通用 AI Agent 框架，
        支持插件化工具注册、Hook 扩展、AutoCompact 上下文压缩、子 Agent 委托（Python/asyncio）
```
