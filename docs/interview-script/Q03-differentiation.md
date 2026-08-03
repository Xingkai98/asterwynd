# Q03: 与 Claude Code / Codex / Cursor 的差异化深度

## 讲稿

面试官常问"你和 Claude Code / Codex 有什么区别"。我的回答分三层。

**第一，定位不同**。Asterwynd 的目标不是复刻 Claude Code 的功能清单，而是做一个**可解释、可复现、可 benchmark 的本地 coding agent**。它的每个能力都设计成"能讲清楚怎么实现、为什么这么设计、踩过什么坑"，而不是堆功能点。核心流程是：`理解仓库 → 修改代码 → 运行验证 → 记录 trace → 报告结果`。

**第二，深度不同**。每条能力线都做深到能讲出设计取舍：上下文管理不是简单塞进 system prompt，而是做了四字段摘要 + 层级压缩 + 稳定前缀缓存命中；工具系统做了语义去重、Top-K 动态选择、质量评分软降级；长期记忆做了 LLM 三分支去重 + git 可逆写入（这个甚至比 mem0 的路线多考虑了可恢复性）；多 Agent 协作做了状态快照恢复 + 预算硬 kill + 消息总线。

**第三，工程闭环不同**。不是"写完就完"，而是有 OpenSpec 需求流程（先讨论需求再实现）、强制 subagent 审阅闭环（实现后独立 agent 审阅，抓真实 bug）、Benchmark 可复现评测。面试时我会讲：这个项目被要求"每次新 change 都要先做设计追问、实现后要有独立审阅证据、合入前要过 CI 门禁"——这种工程纪律本身就是面试想看的。

一句话总结：Claude Code 是产品，Asterwynd 是"你能讲清楚它怎么工作"的系统——这正是面试岗位（Agent 开发）要的能力证明。

## 代码走读

### 入口与调用链

```
docs/coding-agent-roadmap.md（定位演进）→ CONTEXT.md（词汇/口径）→ 各能力线实现
```

### 关键文件逐段

**`docs/coding-agent-roadmap.md`** — 定位演进记录。
- "New Positioning"（2026-06-15）：从通用 agent 框架转向 **local, benchmarkable coding agent framework**。
- "Core Product Thesis"（第 3 节）：差异化定位是 "An explainable, reproducible, benchmarkable local coding agent"——**可解释、可复现、可 benchmark**，这是核心叙事。
- 明确写："The goal is not to clone Claude Code or Codex feature-for-feature"——不是逐功能复刻。

**`CONTEXT.md`** — 项目词汇与口径。
- "目标岗位"条目：Agent 开发为主线，AI Infra/LLM/RAG/后端为支撑。
- "主线能力"条目：围绕 Agent 运行时、工具调用、上下文管理、任务执行、可观测性和评测闭环展开——**避免平均铺开**。

**`docs/project-positioning.md`** — 能力证明链。

**各能力线实现**（体现"做深"）：
- 上下文：`agent/context/`（Q04 展开）——四字段摘要 + 层级压缩 + 稳定前缀。
- 工具：`agent/tools/governance/`（Q05 展开）——语义去重 + Top-K + 质量评分。
- 记忆：`agent/memory/`（Q06/Q15 展开）——三分支去重 + git 可逆。
- 多 agent：`agent/subagent/`（Q08 展开）——快照 + 预算 + 消息总线。
- 可观测：`agent/trace_recorder.py`（Q09 展开）。
- 评测：`benchmarks/`（Q13 展开）。

**`AGENTS.md` 开发流程节** — 工程闭环的规则来源。
- OpenSpec 需求先行 + grill 设计追问 + 强制 subagent 审阅闭环。
- 这些是"工程纪律"叙事的事实来源，Q14 展开。

### 设计理由

- **"可解释"**：每条能力线有 OpenSpec 文档（proposal/design/spec），面试能引用"我们当时为什么这么设计、备选是什么"。这是 vs 黑盒产品最大的差异。
- **"可复现"**：CI 全量 pytest + OpenSpec validate + artifact checker 门禁，改动可验证。
- **"可 benchmark"**：benchmark harness 用可复现任务评测，能给出量化证据（Q13）。
- **教训驱动**：`docs/lessons-learned.md` 记录了真实踩过的坑（uv 隔离、Mock 异步、provider 字段透传等），面试讲"我踩过这些坑"有据可查。
