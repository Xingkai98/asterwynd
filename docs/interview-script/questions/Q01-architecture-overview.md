# Q01: 项目定位与模块全景

## 讲稿

Asterwynd 是一个以拿到大厂 Agent 相关开发岗位 offer 为目标的 Coding Agent 系统。它不是一个通用 agent 框架，而是围绕一条主线能力链做深：**Agent 运行时 → 工具调用 → 上下文管理 → 记忆 → 多 Agent 协作 → 可观测性 → 评测闭环**。

整个系统按"核心循环 + 协作模块"组织。核心是 `AgentLoop`——一个消息驱动的调度器：`messages → LLM → tool_calls → 执行工具 → 结果回填 → 循环`。LLM 调用、工具执行、上下文注入、记忆压缩、轨迹记录都通过独立模块协作，AgentLoop 只负责编排。

围绕核心循环的模块分几类。**上下文层**：ContextBuilder 统一编排所有注入源（ASTER.md、记忆索引、技能、计划），并做缓存感知的分层注入，保证稳定前缀字节级稳定以命中 LLM Prefix Cache。**工具层**：ToolRegistry 注册 + WorkspacePolicy 安全边界 + 工具治理（语义去重、Top-K 选择、质量评分软降级）。**记忆层**：长期记忆做语义去重、时效衰减、git 可逆写入。**协作层**：SubAgentManager 支持多 Agent 编排，带状态快照恢复和预算硬 kill。**工程闭环**：TraceRecorder 记录轨迹、CI 跑全量测试 + OpenSpec 门禁、Benchmark 做可复现评测。

面试时我会强调：这个项目不是堆功能点，而是每条能力线都做到"能讲出设计取舍和踩过的坑"的深度——后面每个问题都会展开。

## 代码走读

### 入口与调用链

```
CLI (agent/main.py) → AgentLoop (agent/loop.py) → 上下文构造 (agent/context/) → LLM (agent/llm.py)
  → 工具执行 (agent/tools/registry.py) → 记忆/压缩 (agent/memory/) → trace (agent/trace_recorder.py)
```

### 关键文件逐段

**`CONTEXT.md`** — 项目词汇表，定义"目标岗位 / 主线能力 / 支撑能力 / Coding Agent 系统"等核心语言。面试叙事的口径都来自这里。关键点：项目是 **offer 导向**，每条能力选择都要服务于"能证明面试深度"。

**`docs/project-positioning.md`** — 项目定位：目标岗位（Agent 开发为主线，AI Infra/LLM/RAG/后端为支撑）、主线能力链、能力证明链。

**`agent/loop.py`** — 核心调度器（核心循环）。
- `AgentLoop` 类：持有 `messages`（主要状态）、调用 LLM、执行工具、记录 trace。
- 核心原则（`docs/architecture.md:15-17`）：`messages` 是主状态；tool-call 消息链必须合法（assistant 的 tool call 必须对应 tool result）；LLM/工具/记忆/压缩/轨迹通过独立模块协作。

**`agent/context/builder.py`** — 上下文注入管线。
- 所有 `ContextSource` 统一编排（ASTER.md、记忆索引、技能、计划、待办）。
- `build_blocks`：静态源缓存 + cache 感知分层注入（P0/P1/P2 稳定前缀），保证稳定前缀字节级稳定命中 Prefix Cache。

**`agent/tools/registry.py`** — 工具注册与执行。
- 工具 schema 暴露给 LLM；`ToolPermission` 记录 capability/risk/origin 三要素；`ModePolicy` 产生 allow/deny/require_approval 三值判定。

**`agent/memory/`** — 长期记忆 + 上下文记忆。
- `persistent.py`：跨 session 记忆（文件存储 + 语义去重 + 衰减 + git 可逆）。
- `manager.py`：消息历史 + AutoCompact（四字段摘要 + L1/L2 层级压缩 + 增量 token 计数）。

**`agent/trace_recorder.py`** — 可观测性。每步 tool call 的耗时/成功/token 记录，供 Session 看板与成本归属。

**`agent/subagent/manager.py`** — 多 Agent 协作。子 session 创建/运行/查询，配套快照恢复、预算、消息总线。

### 设计理由

- **消息驱动而非状态机驱动**：`messages` 是唯一主状态，天然适配 LLM 的输入输出格式，工具调用的合法性靠消息链约束（`docs/architecture.md:15-17`）。
- **模块围绕核心循环**：AgentLoop 只编排，具体能力（上下文/工具/记忆/可观测）全部独立模块，便于每块单独做深、单独测试、单独讲面试。
- **支撑能力服务主线**：AI Infra（LLM 抽象）、RAG（记忆检索）、后端（Web/CLI）都服务于"能让 Agent 跑起来且可证明"这条主线，而不是平均铺开（`CONTEXT.md` "主线能力"条目）。
