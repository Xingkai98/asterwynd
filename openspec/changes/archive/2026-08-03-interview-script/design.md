# Design: 面试讲稿文档 — 分层 15 问 + 代码走读

## Context

项目是面试驱动的 Coding Agent 系统。已实现大量能力（#74 上下文 / #75+99 记忆 / #76 沙箱 / #77 工具治理 / #78 可观测 / #79 多agent / #89 error_type），但缺少**面向面试叙述的分层讲稿**。面试官按"由浅入深"问顶层问题，需要能口头讲清"怎么实现 + 为什么 + 踩过什么坑"，并有代码证据支撑。

## Goals / Non-Goals

Goals:
- 15 个由浅入深的顶层问题，每问一个文件。
- 每问 = 讲稿（300-500 字）+ 代码走读（不限篇幅，讲清楚为止）。
- 走读覆盖：入口调用链 + 关键文件 + 关键函数 + 设计理由。
- AGENTS.md 记录维护约束（建议性）。

Non-Goals:
- 不覆盖全部源码，只覆盖面试叙述路径。
- 不替代 `docs/architecture.md` / docstring / OpenSpec 规格。
- 第一批固定 15 问，不扩展更多问题。

## Decisions

### Decision 1: 文档位置与单文件结构

`docs/interview-script/<Q编号>-<slug>.md`，每问一个文件。统一结构：

```markdown
# Q<NN>: <问题标题>

## 讲稿
（300-500 字，面试口头叙述，一段到两段）

## 代码走读
（不限篇幅，讲清楚为止）

### 入口与调用链
（一句话主链路：从哪进到哪出）

### 关键文件逐段
（每个文件：职责 + 关键函数:行号 + 为什么这么设计）
```

`docs/interview-script/README.md` 作索引，按五层分组列出 15 问，说明使用方式（先讲稿建叙事、再走读建证据）。

### Decision 2: 15 问清单（由浅入深，五层）

**第一层 开场必问**（讲清"这是什么项目"）
- Q01 `architecture-overview`：项目定位与模块全景
- Q02 `agent-loop`：AgentLoop 主循环，一次对话从输入到输出的完整链路
- Q03 `differentiation`：与 Claude Code / Codex / Cursor 的差异化深度

**第二层 核心运行时**（面试追问主体）
- Q04 `context-engineering`：上下文管理——怎么构造、压缩、注入
- Q05 `tool-system`：工具系统——注册、治理、动态选择
- Q06 `long-term-memory`：长期记忆——存储、去重、衰减、可逆
- Q07 `llm-provider`：LLM Provider 与多模型——抽象、错误、成本

**第三层 关键能力**（面试"有没有踩过坑"）
- Q08 `multi-agent`：多 Agent 协作——spawn、快照、预算、消息总线、编排模式
- Q09 `observability`：可观测性——trace、metrics、成本归属、异常分类
- Q10 `sandbox`：安全沙箱——命令护栏、隔离、资源限制
- Q11 `error-type`：工具错误处理——error_type 结构化

**第四层 工程化闭环**（面试"怎么保证质量"）
- Q12 `ci-testing`：CI 与测试体系
- Q13 `benchmark`：Benchmark 评测体系
- Q14 `dev-process`：开发流程——OpenSpec + grill + 审阅闭环

**第五层 深度亮点**（面试"讲一个踩过的坑"）
- Q15 `memory-reversibility`：长期记忆误判丢失 → git 可逆性设计权衡

### Decision 3: 每问内容规范

- **讲稿 300-500 字**：一条主线，能口头讲 1-2 分钟；包含"怎么实现 + 为什么这么设计 + 一个踩过的坑/取舍"。
- **代码走读"讲清楚为止"**：至少含入口调用链 + 关键文件逐段；关键函数给 `文件:行号`；解释设计理由（为何这样，备选是什么，为什么选它）。
- **讲稿与走读对应**：讲稿中提到的每个能力点，走读都有对应代码路径可查。

### Decision 4: 维护约束（建议性）

AGENTS.md 文档地图加 `interview-script`，并加一条**建议性维护约束**（非硬性门禁）：

> 每次有新的设计或架构变更后，应检查 `docs/interview-script/` 中对应问题是否需更新讲稿与代码走读；若变更引入新能力线，可新增问题文件。该约束为建议，不设机械门禁。

理由：讲稿文档随项目演进，若不同步会快速过时。但它是辅助材料，不设为 CI/checker 硬约束（避免过度仪式），以"检查清单"形式提示。

## Pre-Implementation Review

本 change 为纯文档。用户已确认：每问一个文件、讲稿 300-500 字、代码走读讲清楚为止、docs change 立项、AGENTS.md 加建议性维护约束。15 问清单与五层分组已与用户讨论确认。

## Risks / Trade-offs

- **[讲稿过时]**：随代码演进失真。以维护约束（建议性）缓解，不设硬门禁。
- **[走读篇幅膨胀]**：不限篇幅可能很长。以"讲清楚为止 + 只走面试叙述路径"约束，避免全量源码注释。
- **[与现有文档重复]**：architecture.md / roadmap 已有部分内容。走读聚焦"面试叙述路径"，architecture 是全景图，二者互补。

## Testing Strategy

纯文档 change，无代码测试。验证：
- `npx openspec validate --all --strict` 通过（change 文档完整）。
- `scripts/check_openspec_artifacts.py` 通过（docs change 豁免 grill 门禁，但需 proposal/design/tasks 完整）。
- 15 个问题文件 + README 存在，每问含 `## 讲稿` 与 `## 代码走读` 节。
- AGENTS.md 文档地图含 `interview-script` 与维护约束。

## Impact Analysis

| 影响面 | 说明 |
|---------|------|
| `docs/interview-script/` | 新增 15 问 + README |
| `AGENTS.md` | 文档地图 + 建议性维护约束 |
| `docs/openspec-change-backlog.md` | 未实现队列加本 change |
| 代码 | 无 |
