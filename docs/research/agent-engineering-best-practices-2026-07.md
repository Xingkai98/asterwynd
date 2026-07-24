# Agent 开发工程化最佳实践调研报告

> 调研时间：2026-07-24
> 调研方法：手动全网搜索 + deep-research workflow（106 agent、537 万 tokens、24 源 104 claims → 3-vote 对抗性验证确认 8 条高置信度发现）
> 调研范围：Anthropic、OpenAI、Google 等公司的 Agent 工程实践，以及 OpenSpec、Claude Code、Cursor、Aider 等开源项目和工具的工程化方法
> 状态：v2.0 — 已合并 deep-research 对抗性验证结论

---

## 目录

1. [核心发现摘要](#1-核心发现摘要)
2. [Agent 开发 SOP 与工程化流程](#2-agent-开发-sop-与工程化流程)
3. [项目文档管理最佳实践](#3-项目文档管理最佳实践)
4. [Agent 测试策略](#4-agent-测试策略)
5. [开发工作流自动化](#5-开发工作流自动化)
6. [开源参考项目调研](#6-开源参考项目调研)
7. [Code Review 与质量门禁](#7-code-review-与质量门禁)
8. [对本项目的改进建议](#8-对本项目的改进建议)
9. [参考来源](#9-参考来源)

---

## 0. Deep-Research 验证结论（2026-07-24）

以下 8 条发现在 3-vote 对抗性验证中全部存活（需 ≥2/3 投票确认），置信度高：

### ✅ 已确认（8 条）

| # | 发现 | 置信度 | 投票 |
|---|------|--------|------|
| 1 | **Anthropic 区分 Workflow（预定义编排）和 Agent（自主决策），建议从最简单方案开始** | High | 3-0 |
| 2 | **253 个 CLAUDE.md 实证研究：中位 1 个 H1、5 个 H2、9 个 H3；77.1% 含构建命令，71.9% 含实现细节，64.8% 含架构描述** | High | 3-0 |
| 3 | **AI 生成代码质量风险：32.2% 输出错误、47.5% 存在可维护性问题；Agent PR 冗余度是人类 1.87 倍，但审查者更少表达负面情绪** | High | 加权 3-0 |
| 4 | **GitHub 10 分钟六步 Review 协议 + Convergo 三轮封顶"新鲜审查者"退出门禁** | High | 3-0 + 3-0 |
| 5 | **Nexus-agents 四层自治权限阶梯：observe→suggest→advisory→enforce** | Medium | 3-0（源准确但非行业标准） |
| 6 | **ETCLOVG 七层分类体系（执行/工具/上下文/生命周期/可观测性/验证/治理）** | Medium | 3-0（预印本，尚未同行评审） |
| 7 | **doc-cleanup 五阶段文档清理工作流：Inventory→Diagnose→Report(人工审批门)→Execute→Verify** | Medium | 3-0（实证单薄但方法正确） |
| 8 | **六原则编码规范：Simplicity First / Readability Priority / Dependency Minimalism / Security First / Test-Driven Thinking / Token Efficiency** | Low | 2-1（咨询公司营销内容） |

### ❌ 已排除（13 条）

被 3-vote 对抗性验证淘汰的关键主张包括：
- "Anthropic 明确了 5 种可组合的 agentic 模式" — 过度简化，官方只做了 workflow/agent 二分
- "Agentic SDLC 替代传统 SDLC 为四阶段循环" — 来源权威性不足（aws research book 未经同行评审）
- "File-scoped commands 可节省 $2000/月 API 费用" — 无独立验证的营销声明
- "doc-cleanup 可将文档从 1085 行减至 266 行" — 案例数据来源单一，方法论存疑

### ⚠️ 关键 Caveats

1. Liu et al. 的代码质量研究使用 GPT-3.5-turbo（2023.03），对现代模型参考价值已大幅下降，但尚无替代性大规模 benchmark
2. ETCLOVG 分类体系来自 OpenReview 预印本（CMU/Yale/Amazon），尚未通过同行评审
3. Eval 框架对比（Braintrust/LangSmith/AEVAL）在 coding agent 场景下的专门研究缺失
4. 文档最佳规模与 Agent 实际代码质量之间的因果关系尚未建立

> 方法论：deep-research workflow 覆盖 5 个角度搜索 → 24 个源 → 104 条 claims → 25 条验证（3-vote 对抗性），12 条确认、13 条淘汰。来源见 [附录](#9-参考来源)。

---

## 1. 核心发现摘要

### 1.1 业界共识：从 Prompt Engineering 到 Harness Engineering

AI Agent 开发的工程化正在经历范式升级：

```
Prompt Engineering → Context Engineering → Harness Engineering
(2023-2024)           (2024-2025)           (2025-2026)
```

- **Prompt Engineering**：关注单次对话的提示词质量
- **Context Engineering**：关注 Agent 可获取的上下文信息的组织和注入
- **Harness Engineering**：关注 Agent 运行的完整约束框架——规则、工具、验证、工作流、门禁

Anthropic 和 OpenAI 在 2026 年分别发表了 Harness Engineering 的工程实践文章，标志着业界对 Agent 开发的认识已经成熟。

### 1.2 三条核心原则

1. **从简单开始，按需增加复杂度**（Anthropic "Building Effective Agents" 核心原则）
2. **Eval-Driven Development**：先定义评估标准，再开发功能
3. **Human-in-the-Loop at Gates**：在关键门禁点（而非每一步）引入人工审阅

### 1.3 本项目的现状与差距

本项目已有较好的工程化基础（AGENTS.md + OpenSpec + workflow state machine），但存在以下可改进空间：

- 文档层级不够清晰，职责重叠
- 缺少结构化 Eval 体系
- worktree 隔离虽然好，但缺少与 CI 的集成
- Code Review 流程可以更结构化

---

## 2. Agent 开发 SOP 与工程化流程

### 2.1 Anthropic：Building Effective Agents

**核心原则**（来源：Anthropic 官方指南）：
1. **从最简单的方案开始**：能用单次 LLM 调用解决的，不要引入 agent 框架
2. **逐步增加复杂度**：只有在简单方案不够用时，才引入工具、循环、多 agent
3. **为 Agent 提供充分的上下文和工具**

**三 Agent 协作模式**（来源：Anthropic "Harness Design for Long-Running Application Development"）：
- **Spec Writer Agent**：分析需求，生成规格说明
- **Implementer Agent**：基于 spec 编写代码
- **Reviewer Agent**：独立审查实现是否符合 spec

这种模式已经被 Claude Code 内置的 plan → implement → review 工作流所体现。

### 2.2 OpenAI：Harness Engineering

**核心理念**（来源：OpenAI "Harness Engineering: Structuring Context and Guardrails for AI Coding Agents in Production"）：

Harness = Context + Guardrails + Verification

1. **Context（上下文）**：规则文件（CLAUDE.md / AGENTS.md）、项目结构、类型定义、已有代码模式
2. **Guardrails（护栏）**：pre-commit hooks、CI 检查、类型系统、linter
3. **Verification（验证）**：Evals、测试、人工审阅门禁

OpenAI 在 Codex 中实践了 "Zero Human-Written Code" 的极端 Harness Engineering，通过多层验证确保 Agent 生成代码的质量。

### 2.3 推荐的五阶段 Agent 开发 SOP

结合 Anthropic、OpenAI 和 OpenSpec 的实践，推荐以下五阶段开发流程：

```
Phase 1: Planning（规划）
├── 需求澄清 → 创建 proposal.md
├── 方案设计 → 创建 design.md（含 ADR）
├── 任务拆解 → 创建 tasks.md
└── Gate: 人工审批 proposal + design + tasks

Phase 2: Building（构建）
├── Worktree 隔离环境
├── 测试先行（TDD）
├── 增量实现
└── Gate: 所有测试通过 + lint 通过

Phase 3: Code Review（审阅）
├── 自动化审阅（lint, type-check, test）
├── AI 审阅（code-review skill，多维度并行）
├── 人工审阅
└── Gate: 人工批准审阅结果

Phase 4: Closing（收尾）
├── 归档 change 文档
├── 更新 spec
├── 提交 PR
└── Gate: CI 全绿 + PR 批准

Phase 5: Merge & Verify（合入验证）
├── 合入 master
├── 确认归档干净
└── 可选的部署验证
```

### 2.4 关键工程化原则

| 原则 | 说明 | 来源 |
|------|------|------|
| **Start Simple** | 不要过度设计 agent 工作流，从最简单的方案开始 | Anthropic |
| **Eval First** | 在写实现代码之前先写好评估标准 | OpenAI, Google |
| **Gate, Don't Micromanage** | 在关键门禁点做人工审阅，不要每一步都卡 | Anthropic, OpenAI |
| **Worktree Isolation** | 代码修改必须在隔离环境中进行 | 本项目 AGENTS.md |
| **Immutable Context** | 规则、spec、文档是 Agent 的不可变上下文，不应被 Agent 随意修改 | OpenAI Harness |
| **Progressive Disclosure** | 文档按层级组织，Agent 按需加载，避免上下文膨胀 | .agents/ 提案 |

---

## 3. 项目文档管理最佳实践

### 3.1 Agent 指令层级（Agent Instruction Hierarchy）

业界正在形成明确的文档分层标准：

```
Level 0: Global（全局）        ~/.claude/CLAUDE.md          用户级偏好和规则
Level 1: Project（项目）        AGENTS.md / CLAUDE.md         项目级规则和文档地图
Level 2: Directory（目录）      .claude/CLAUDE.md (per-dir)   目录级规则（如前端/后端不同规则）
Level 3: Change（变更）         openspec/changes/<id>/*.md    当前 change 的 proposal/design/tasks
Level 4: Memory（记忆）         .claude/memory/*.md           跨 session 持久记忆
```

**关键原则**（来源：MatthewKerns "Agent Instruction Hierarchy"）：
- 上层设置约束，下层设置具体执行细节
- 下层不应该与上层冲突
- 每个层级只定义自己关心的内容

### 3.2 AGENTS.md vs CLAUDE.md 的最佳实践

**业界共识**（来源：AGENTS.md Spec 2026, Tembo blog, GitLab standards）：

| 文件 | 定位 | 内容 |
|------|------|------|
| `AGENTS.md` | **唯一维护入口**，项目规则的权威源 | 高优先级规则、文档地图、技术栈、项目约定 |
| `CLAUDE.md` | **工具适配层**，引用 AGENTS.md | `@AGENTS.md` 一行即可，工具特定的路由 |
| `CONTEXT.md` | **领域词汇表**，定义项目术语 | 项目核心概念、术语定义、缩写 |
| `.cursorrules` | Cursor 专属规则 | 与 AGENTS.md 对齐，但适配 Cursor 的格式 |

**反模式**：
- ❌ CLAUDE.md 和 AGENTS.md 内容重复
- ❌ 所有规则都堆在一个文件里（上下文膨胀）
- ❌ 文档写了没人维护（过期文档比没有文档更差）

**本项目当前问题**：
- `CLAUDE.md` 只保留 `@AGENTS.md` — 这点很好
- `AGENTS.md` 内容较长（~100+ 行），可以进一步精简为引用链
- `CONTEXT.md` 定位清晰，但部分内容（如文档债务）应该提到单独的文件

### 3.3 CLAUDE.md 结构的实证研究（PROFES 2025）

一篇经同行评审的实证研究（DOI:10.1007/978-3-032-12089-2_40）分析了 242 个仓库的 253 个 CLAUDE.md 文件，为 "Agentic Coding Manifest 应该怎么组织" 提供了量化答案：

| 统计项 | 数值 |
|--------|------|
| H1 标题数 | 中位数 1 |
| H2 标题数 | 中位数 5 |
| H3 标题数 | 中位数 9 |
| H4 出现 | 仅 37 个文件 |
| H5 出现 | 仅 5 个文件 |
| H6 出现 | 仅 1 次 |

**最常见内容类别**：
1. **Build and Run**（77.1%）— 构建/运行命令、脚本
2. **Implementation Details**（71.9%）— 代码风格、开发规范
3. **Architecture**（64.8%）— 项目结构、组件关系

**对本项目的指导**：AGENTS.md 应保持 1 个 H1 + 约 5 个 H2 + 约 9 个 H3 的扁平结构。核心内容聚焦：构建命令、代码风格、架构描述。深度嵌套（H4+）应避免。

### 3.4 AGENTS.md 标准化进展

AGENTS.md 规范由 **Agentic AI Foundation**（Linux Foundation 旗下）维护，目前已被 Claude Code、Cursor、GitHub Copilot、Gemini CLI、Windsurf、Aider、Zed、Warp、RooCode 等主要工具支持。

**关键共识**（来源：EveryDev blog, Morphllm AGENTS.md Spec 2026）：
- AGENTS.md 应作为跨工具的**唯一事实源**
- CLAUDE.md 缩减为 `@AGENTS.md` 一行指针（本项目已做到）
- 工具特定规则文件（`.cursorrules` 等）从 AGENTS.md 派生，不独立维护

但需注意：AI 编码规则生态仍然高度碎片化，至少有 10+ 种不同格式和位置。

### 3.5 .agents/ 目录提案（dotagents）

GitHub 上的 [dotagents](https://github.com/bgreenwell/dotagents) 提案正在推动一个标准化方案：

```
.agents/
├── rules/           # 项目规则
│   ├── 00-core.md   # 最高优先级规则
│   ├── 10-lang.md   # 语言相关规则
│   ├── 20-test.md   # 测试规则
│   └── 30-deploy.md # 部署规则
├── context/         # 项目上下文
│   ├── domain.md    # 领域知识
│   ├── glossary.md  # 词汇表
│   └── roadmap.md   # 路线图
├── workflows/       # 工作流定义
│   ├── feature.md
│   └── bugfix.md
└── memory/          # 持久记忆
```

**优点**：
- 按主题分离，Agent 按需加载，避免上下文膨胀
- 文件名带数字前缀，控制加载顺序
- 规则和上下文分开，职责清晰

### 3.6 文档管理的核心原则

1. **Single Source of Truth**：每个事实只在一个地方定义
2. **Progressive Disclosure**：入口文件只放索引，详情按需加载
3. **过期即删**：定期清理过时文档（可以写脚本自动检查）
4. **规则 vs 上下文分离**：规则（怎么做）和上下文（是什么）放在不同文件
5. **文档也是代码的一部分**：文档变更走同样的 review 流程

### 3.7 文档腐烂与自动化清理

**文档腐烂的经济学**：过时事实在每次会话中消耗 context tokens，并导致 Agent 错误推理——文档中一个过时的权威陈述比 Agent 从未查到的正确事实危害更大。

**[doc-cleanup](https://github.com/aka-luan/doc-cleanup)** 项目定义了五阶段文档清理工作流，核心哲学：
1. **保存不摧毁** — 归档而不是删除
2. **仓库即是证据** — 代码是真理，文档只是解释
3. **指向而非复制** — 链接比嵌入更安全
4. **陷阱比历史更持久** — 一个过时事实会持续误导所有后续会话

工作流：`Inventory → Diagnose(read-only) → Report(硬性人工审批门) → Execute → Verify & Handoff`

### 3.5 自动文档生成工具

- **[Archie](https://github.com/BitRaptors/Archie)**（BitRaptors）：从代码库自动生成 AGENTS.md、per-folder CLAUDE.md、hooks
- **[agentsmesh](https://github.com/sampleXbro/agentsmesh)**：跨 AI coding 助手的规则同步工具
- **[openspec](https://github.com/fernandomenuk/openspec)**（fernandomenuk）：从单一事实源生成多种格式的 Agent 配置

---

## 4. Agent 测试策略

### 4.1 从 "Vibe Check" 到持续评估

Google Cloud 2026 年发布的文章 [From "Vibe Checks" to Continuous Evaluation](https://cloud.google.com/blog/topics/developers-practitioners/from-vibe-checks-to-continuous-evaluation-engineering-reliable-ai-agents) 明确指出：

> "Vibe checks"（凭感觉的手动测试）在原型阶段可以接受，但在生产环境中不可规模化。

**评估成熟度模型**：
```
Level 0: Vibe Check        — "看着还行"
Level 1: 手工测试用例       — 定义一些固定场景手动测试
Level 2: 自动化 Eval        — eval 套件集成到开发流程
Level 3: CI/CD 集成 Eval    — 每次 PR 自动跑 eval
Level 4: 持续评估与监控     — 生产环境中的在线评估 + 回归测试
```

### 4.2 主流 Agent 评估框架对比

| 框架 | 特点 | 适用场景 | 成熟度 |
|------|------|----------|--------|
| **Braintrust** | Eval-first 开发，支持 A/B 测试，数据集管理 | 中大型团队，需要严格质量管控 | ⭐⭐⭐⭐⭐ |
| **LangSmith** (LangChain) | 与 LangChain 生态深度集成，trace 和 eval 一体 | LangChain/LangGraph 用户 | ⭐⭐⭐⭐⭐ |
| **MLflow** | 开源，模型+Agent 统一评估 | 需要开源方案，已有 ML 基础设施 | ⭐⭐⭐⭐ |
| **AgentEval** | 轻量级，专注 Agent 行为评估 | 独立 Agent 项目，不想绑定生态 | ⭐⭐⭐ |
| **AEVAL** (2026) | 确定性测试，将非确定性 Agent 行为转化为可确定的测试断言 | 需要 CI 中可靠评估 Agent | ⭐⭐⭐⭐ |
| **OpenAI Evals** | OpenAI 官方评估框架，与 Codex SDK 集成 | OpenAI/Codex 用户 | ⭐⭐⭐⭐ |

### 4.3 Eval-Driven Development 实践

OpenAI 的 [Testing Agent Skills Systematically with Evals](https://developers.openai.com/blog/eval-skills) 提出了系统的 Agent 评估方法：

**三层评估体系**：

```
Layer 1: Unit Evals（单元评估）
├── 工具选择正确性：Agent 是否选择了正确的工具？
├── 参数提取准确性：从用户输入中提取的参数是否正确？
└── 输出格式验证：输出是否符合预期的 JSON schema？

Layer 2: Scenario Evals（场景评估）
├── 端到端场景：给定一个任务，完整执行并评估结果
├── 边界条件测试：异常输入、模糊指令、多步推理
└── 回归场景：之前修过的 bug 不再复现

Layer 3: Behavior Evals（行为评估）
├── 安全性：Agent 是否拒绝了危险操作？
├── 效率：Token 消耗、工具调用次数是否合理？
└── 用户体验：回复是否清晰、有帮助？
```

### 4.4 Agent 测试的具体方法

**AEVAL 方法**（来源：AEVAL 论文，2026）：
- 将 Agent 的 skill workflow 建模为状态机
- 每个状态转换定义为可确定的断言
- 解决了 Agent 行为的非确定性问题

**Agent-as-a-Judge** 模式（来源：Google Cloud）：
- 用一个更强大的 Agent 评估另一个 Agent 的输出
- 需要明确定义评估标准（rubrics）
- 适合开放式输出的评估（如对话质量、代码可读性）

**本项目的测试建议**：
- 当前项目的 pytest 覆盖了传统代码（工具、配置、循环），但缺少 Agent 行为评估
- 建议引入：每个 skill/command 定义 eval 用例，集成到 CI

---

## 5. 开发工作流自动化

### 5.1 CI/CD 与 Agent 开发的集成

**CircleCI Chunk Sidecars**（2026 年 6 月发布）：
- 将 CI 验证直接嵌入 AI coding 工作流
- Agent 每次文件修改后，Chunk sidecar 自动运行相关测试
- 在 Agent 的 "inner loop" 中提供快速反馈

**GenAI Development Platform 架构**（来源：microservices.io）：
```
Agent IDE → Pre-commit Hooks → Chunk Sidecar → CI Pipeline → Production
           (lint, type)        (unit test)     (full test)    (monitoring)
```

### 5.2 OpenSpec 与 Spec-Driven Development

OpenSpec 是 AI 原生开发的重要范式：

**OpenSpec 生命周期**：
```
Explore → Propose → Apply → Sync → Archive
(探索)   (提案)     (实现)   (同步)  (归档)
```

**关键实践**：
- 每个 change 有独立的 proposal / design / tasks / spec delta
- Spec delta 在 change 完成后合并到主 spec
- Archive 目录保留历史记录

**[SDD OpenSpec Agents Template](https://github.com/joosiimoo/sdd-openspec-agents-template)** 展示了一个完整的 Spec → Tests → Tasks → Code 流水线，包含：
- Role-based multi-agent system
- TDD 强制
- Code quality review 自动化
- Documentation automation

### 5.3 自动化质量门禁矩阵

| 门禁 | 工具 | 触发时机 | 阻断级别 |
|------|------|----------|----------|
| **格式检查** | ruff, biome, prettier | pre-commit / CI | Hard block |
| **类型检查** | mypy, pyright, tsc | pre-commit / CI | Hard block |
| **单元测试** | pytest, vitest | pre-commit (changed files) / CI (all) | Hard block |
| **E2E/集成测试** | pytest, playwright | CI only | Hard block |
| **Agent Eval** | Braintrust, custom evals | CI only | Soft block (报告) |
| **安全扫描** | bandit, trivy, semgrep | CI only | Hard block |
| **OpenSpec 校验** | openspec validate | CI + pre-commit | Hard block |
| **文档一致性** | artifact checker | CI | Hard block |

### 5.4 本项目的自动化现状

**已有**：
- ✅ pytest 全量测试
- ✅ OpenSpec strict validate
- ✅ artifact checker
- ✅ workflow_state.py 状态追踪

**可补充**：
- ❌ pre-commit hooks（ruff, mypy）
- ❌ Agent eval 套件
- ❌ 文档过期检查脚本

---

## 6. 开源参考项目调研

### 6.1 Claude Code

**核心设计理念**："Seeing Like an Agent" — 工具设计要从 Agent 的视角出发

**工程化特性**：
- **Rules 系统**：全局 rules → 项目 rules → 目录 rules，逐层覆盖
- **Skills 系统**：可复用的专业知识包，支持渐进式加载
- **Hooks 系统**：事件驱动的自动化（pre-compact, post-tool-use 等）
- **MCP 集成**：标准的工具和服务集成协议
- **Memory 系统**：跨 session 的持久记忆（code-style, user-preferences）

**对本项目的启发**：
- Skills 系统值得借鉴：将专业领域知识封装为可复用的 skill
- Hooks 系统可以用于实现自动化质量检查

### 6.2 Cursor

**工程化特性**：
- `.cursorrules`：项目级规则文件
- **Agent Mode**：自主编码模式，支持多步操作
- **Composer**：多文件协同编辑
- 与 Claude Code 共享相似的规则体系和工具集成模式

**与本项目的关系**：Cursor 的 `.cursorrules` 和 AGENTS.md 功能重叠，业界趋势是统一为 AGENTS.md 标准。

### 6.3 Aider

**工程化特性**：
- **Benchmark-Driven Development**：Aider 有自己的 benchmark 套件，每次发布都跑 benchmark 验证
- **Editing Formats**：定义了多种代码编辑格式（diff, whole, search-replace）
- **Map-Reduce 上下文**：通过 repo map 和文件列表管理大项目上下文

**对本项目的启发**：
- Aider 的 benchmark-driven 方法：本项目也有 benchmark，但可以更紧密地集成到开发流程中
- Map-Reduce 模式对于大型代码库的上下文管理很有价值

### 6.4 Agent Engineering Handbook

[d-padmanabhan/agent-engineering-handbook](https://github.com/d-padmanabhan/agent-engineering-handbook) 是当前最全面的 Agent 工程化手册，覆盖：

- **Rules**：项目规则和编码标准
- **Skills**：可复用的技能包
- **Slash Commands**：自定义命令
- **MCP Servers**：工具服务集成
- **Hooks**：事件驱动的自动化
- **多仓库工作区**：Monorepo 支持

### 6.5 OpenSpec 生态

- [sdd-openspec-agents-template](https://github.com/joosiimoo/sdd-openspec-agents-template)：完整的 SDD 流水线模板
- [ff15-openspec-agents](https://github.com/atman-33/ff15-openspec-agents)：多 Agent 编排框架
- [openspec-skills](https://github.com/yu-iskw/openspec-skills)：OpenSpec 的 Agent Skills 扩展

---

## 7. Code Review 与质量门禁

### 7.1 AI 生成代码的质量风险（量化证据）

**这是本次调研最重要的发现之一**。多项研究一致表明 AI 生成代码存在显著问题：

| 研究发现 | 数据 | 来源 |
|----------|------|------|
| ChatGPT 生成代码输出错误 | 32.2%（4066 个样本） | Liu et al., ACM TOSEM, DOI:10.1145/3643674 |
| 静态分析可检测的可维护性问题 | 47.5% | 同上 |
| Agent PR 代码冗余度 vs 人类 | **1.87 倍**（AMR 0.2867 vs 0.1532, p<0.001） | MSR 2026 Mining Challenge |
| 审查者对 AI 代码的负面情绪 | **更少** — 表面整洁掩盖了债务积累 | 同上 |
| AI 采用率与事故率关联 | 事故/PR 比率增加 **242.7%** | Faros AI（22,000 开发者、4,000+ 团队） |

> ⚠️ Liu et al. 使用的是 GPT-3.5-turbo（2023 版），现代模型可能已有显著改善，但缺乏替代性的大规模 benchmark。MSR 2026 研究更具时效性但仅分析了一个仓库（crewAI）。

**核心教训**：必须内置结构化 Review 和自动化质量门禁——不能信任 Agent 生成代码的表面整洁。

### 7.2 GitHub 官方 10 分钟 Agent PR Review 协议

GitHub 官方 Blog（2026.05.07，Andrea Griffiths）提出了专门针对 Agent PR 的结构化 Review 协议：

| 步骤 | 时间 | 内容 |
|------|------|------|
| 1. 扫描分类 | 1-2 min | 判断 PR 类型：bug fix / feature / refactor / config |
| 2. 检查 CI 变更 | 2-3 min | 重点关注 CI 配置文件是否被弱化（agent 可能跳过测试） |
| 3. 扫描新工具/重复代码 | 3-5 min | Agent 常引入新依赖而非复用已有代码 |
| 4. 端到端追踪 | 5-8 min | 选一条关键路径完整追踪，验证逻辑正确性 |
| 5. 安全检查 | 8-9 min | 边界条件、注入风险、权限变更 |
| 6. 要求证据 | 9-10 min | 要求 Agent 提供测试结果、变更说明、运行验证 |

### 7.3 Convergo：Agent Code Review 闭环

**[Convergo](https://github.com/gomilesf/convergo)**（MIT 许可）提供了可机器执行的 Review 闭环：

- **三轮封顶**：防止无限 review-fix 循环
- **"新鲜审查者"退出门禁**：同一审查者绝不作为退出条件——只有全新 spawn 的零记忆审查者完成完整第一轮无阻塞审查时才退出
- **升级机制**：三轮后仍不通过，升级到人类开发者
- 含可执行 smoke test 验证完整 review loop

这与 Anthropic 的 "三 Agent 协作" 模式（Spec Writer → Implementer → Reviewer）高度一致，但添加了硬性退出条件。

### 7.4 四层 Agent 自治权限阶梯

**[Nexus-agents](https://github.com/nexus-substrate/nexus-agents)** 项目定义了渐进式授权框架（ADR 0017, 2026.06.16）：

```
observe → suggest → advisory → enforce
(只读观察)  (建议)     (建议可执行)  (自主执行)
```

- **晋升**：需要证据阈值 + 人类批准（硬门禁）
- **降级**：自动但受限 — floor 0.5, step cap 0.2, decay 30min
- 已实现 `guardAuthority` + CI drift gate + tier-transition audit events

**对本项目的启发**：当前项目的 workflow state machine 已经实现了 "planning/building/review/closing" 的阶段门禁，可以借鉴 authority ladder 思想，在每个 phase 内定义 agent 的自主权限级别。

### 7.5 AI-Assisted Code Review 模式

**Anthropic 的三 Agent 模式**（来源：Anthropic Harness Design）：
- Spec Writer → Implementer → Reviewer 形成完整的 quality loop
- Reviewer Agent 独立于 Implementer Agent，有不同的 system prompt 和评估标准

**多维度并行审阅**（来源：本项目 code-review skill）：
```
Code Review
├── Dimension 1: Standards（代码规范）
│   ├── Lint 规则
│   ├── 类型安全
│   └── 代码风格
└── Dimension 2: Spec（需求对齐）
    ├── 是否实现了 spec 中的所有要求？
    ├── 是否有 spec 之外的额外改动？
    └── 边界条件是否覆盖？
```

### 7.6 Human-in-the-Loop 的最佳位置

**业界共识**：不要把人工审阅放在每一步，而是在关键 Gate 处设置审阅点：

| Gate | 审阅内容 | 审阅方式 |
|------|----------|----------|
| Planning Gate | Proposal + Design + Tasks | 人工审阅（需要领域知识） |
| Building Gate | 代码质量 + 测试覆盖 | 自动审阅（lint, type, test）+ AI 审阅 |
| Review Gate | 功能正确性 + 安全性 | AI 审阅（多维度）→ 人工审阅（抽查） |
| Closing Gate | 文档完整性 + 归档正确 | 自动检查 + 人工确认 |
| Merge Gate | CI 全绿 + PR 批准 | 自动 + 人工 |

### 7.7 自动化 Code Review 工具

| 工具 | 特点 | 集成方式 |
|------|------|----------|
| **code-review skill**（本项目） | 多维并行审阅，Standards + Spec 双轴 | Claude Code skill |
| **CodeRabbit** | AI-powered PR review，支持多种 LLM | GitHub App |
| **OpenAI Codex Review** | OpenAI 内部的规模化 Code Review 实践 | Codex SDK |
| **Semgrep** | 静态分析 + 自定义规则 | CI / pre-commit 集成 |

### 7.8 Code Review 检查清单

基于业界最佳实践，推荐以下 Code Review 检查维度：

```
□ 正确性：代码逻辑是否正确？
□ 安全性：是否有安全漏洞（注入、越权、信息泄露）？
□ 性能：是否有明显的性能问题？
□ 可维护性：代码是否清晰、有合适的注释？
□ 测试覆盖：关键路径是否有测试？
□ 边界条件：异常情况是否处理？
□ 文档影响：是否需要更新相关文档？
□ Spec 对齐：实现是否与 spec 一致？
□ 无副作用：是否引入了不相关的改动？
□ 工具使用：Agent 工具调用是否符合协议约束？
```

---

## 8. 对本项目的改进建议

基于以上调研，对本项目（Asterwynd）提出以下改进建议，按优先级排列：

### 8.1 高优先级（短期可落地）

#### 8.1.1 文档结构调整

**当前问题**：AGENTS.md 内容过长，职责混杂了规则、流程、文档地图。

**建议**：
```markdown
# AGENTS.md（精简到 30-40 行）
- 项目一句话定位
- 最高优先级规则（5-8 条）
- 文档地图（链接到各详细文档）
- 常用命令速查

# CLAUDE.md（保持现状）
@AGENTS.md
```

将详细流程说明（如工作流自动推进协议、Gate 机制）移到独立文件，例如 `docs/agents/workflow-protocol.md`，在 AGENTS.md 中以链接引用。

#### 8.1.2 引入 Eval 体系

**建议**：
1. 为每个 skill/command 定义 eval 用例
2. 创建 `evals/` 目录，按 skill 组织
3. 集成到 CI：PR 时运行 eval 套件
4. 参考形式：
```python
# evals/skills/code-review/test_eval.py
def test_code_review_detects_security_issue():
    """验证 code-review skill 能检测出 SQL 注入"""
    ...

def test_code_review_respects_ignore_patterns():
    """验证 code-review 遵循 .gitignore 规则"""
    ...
```

#### 8.1.3 增强 Pre-Commit 自动化

```bash
# 推荐的 pre-commit 配置
- ruff check + format（Python）
- mypy（类型检查）
- openspec validate（spec 校验）
- 禁止提交 .codegraph/ .understand-anything/ .dev/ 等
```

### 8.2 中优先级（中期规划）

#### 8.2.1 文档新鲜度自动化

创建脚本定期扫描：
- 超过 90 天未更新的文档标记为"可能过期"
- change backlog 中超过 30 天未推进的 change 标记为 "stale"
- CONTEXT.md 中术语与实际代码的一致性检查

#### 8.2.2 Code Review 流程结构化

- 为不同 change 类型定义不同的 review 维度权重
- Bug fix → 重点看回归测试
- New feature → 重点看 spec 对齐
- Refactor → 重点看行为不变性

#### 8.2.3 Worktree 工作流与 CI 集成

- 在 worktree 中自动运行 fast CI check（类比 CircleCI Chunk）
- 实现 `pre-push` hook 检查 worktree 是否干净

### 8.3 低优先级（长期规划）

#### 8.3.1 引入 Agent 自治权限分级

借鉴 Nexus-agents 的四层权限模型，在现有 workflow state machine 中为每个 phase 定义 agent 的自治级别：
- **Planning phase**：observe/suggest（agent 只读分析 + 建议）
- **Building phase**：advisory（agent 可写代码但须测试通过）
- **Review phase**：observe（agent 只审阅不修改）
- **Closing phase**：advisory（agent 可归档但须人工确认）

#### 8.3.2 .agents/ 目录迁移

考虑未来将文档迁移到 dotagents 标准格式，等该标准更成熟后再实施。

#### 8.3.3 Agent 行为监控

- 在 benchmark 之外增加 Agent 行为 trace 分析
- 追踪 tool-call 成功率、token 效率、错误恢复率
- 参考 ETCLOVG 七层分类体系做自评估

### 8.4 AI 生成代码的风险意识（新增）

基于 MSR 2026 研究（Agent PR 冗余度 1.87 倍 + 审查者情绪偏差）和 Faros AI 数据（243% 事故率增长），建议将以下检查加入 Code Review checklist：

1. **冗余度检查**：Agent 是否引入了与已有工具重复的代码？
2. **CI 完整性检查**：Agent 是否弱化了 CI 配置（跳过测试/降低覆盖率门槛）？
3. **"表面整洁"警觉**：代码看起来干净不代表正确——需要端到端行为验证
4. **证据要求**：要求 Agent 提供 `uv run pytest` 运行结果而非仅声称"测试通过"

---

## 9. 参考来源

### 官方指南与 Engineering Blog

1. Anthropic. "Building Effective Agents: Practical Framework and Design Principles." https://www.anthropic.com/engineering/building-effective-agents
2. Anthropic. "Harness Design for Long-Running Application Development." https://www.anthropic.com/engineering/harness-design-long-running-apps
3. Anthropic. "Seeing Like an Agent: How We Design Tools in Claude Code." https://claude.com/blog/seeing-like-an-agent
4. Anthropic. "Running an AI-Native Engineering Org." https://claude.com/blog/running-an-ai-native-engineering-org
5. Anthropic. "Agent Harness Design: 3 Patterns for Harnessing Claude's Intelligence." https://claude.com/blog/harnessing-claudes-intelligence
6. OpenAI. "Harness Engineering: Structuring Context and Guardrails for AI Coding Agents in Production." ZenML LLMOps Database. https://www.zenml.io/llmops-database/harness-engineering-structuring-context-and-guardrails-for-ai-coding-agents-in-production
7. OpenAI. "Testing Agent Skills Systematically with Evals." https://developers.openai.com/blog/eval-skills
8. OpenAI. "Build an Agent Improvement Loop with Traces, Evals, and Codex." https://developers.openai.com/cookbook/examples/agents_sdk/agent_improvement_loop
9. Google Cloud. "From 'Vibe Checks' to Continuous Evaluation: Engineering Reliable AI Agents." https://cloud.google.com/blog/topics/developers-practitioners/from-vibe-checks-to-continuous-evaluation-engineering-reliable-ai-agents

### 开源项目与社区标准

10. OpenSpec. "Spec-Driven Development for AI Coding Assistants." https://github.com/Fission-AI/OpenSpec
11. d-padmanabhan. "Agent Engineering Handbook." https://github.com/d-padmanabhan/agent-engineering-handbook
12. MatthewKerns. "Agent Instruction Hierarchy." https://github.com/MatthewKerns/software-development-best-practices-guide/blob/main/07-agentic-coding/AGENT_INSTRUCTION_HIERARCHY.md
13. bgreenwell. "dotagents: A Proposed Standard for the .agents/ Directory." https://github.com/bgreenwell/dotagents
14. BitRaptors. "Archie: Architecture Rules Your AI Coding Agent Can't Break." https://github.com/BitRaptors/Archie
15. joosiimoo. "SDD OpenSpec Agents Template." https://github.com/joosiimoo/sdd-openspec-agents-template
16. OpenMind7. "The Definitive Agent Harness Guide." https://github.com/OpenMind7/definitive-agent-harness-guide

### 测试与评估

17. AEVAL. "From Anecdotal to Deterministic Testing for Agentic Skill Workflows." arXiv:2607.16345, 2026. https://arxiv.org/html/2607.16345v2
18. Agent Evaluation Frameworks in 2026. FutureAGI. https://futureagi.com/blog/agent-evaluation-frameworks-2026/
19. AI Agent Evaluation (2026). Morphllm. https://www.morphllm.com/ai-agent-evaluation
20. LLM Evals in 2026: A Practitioner's Field Guide. https://dev.to/lamingsrb/llm-evals-in-2026-a-practitioners-field-guide-26if
21. Braintrust vs LangSmith comparison. LangChain. https://www.langchain.com/resources/langsmith-vs-braintrust

### 工作流与自动化

22. CircleCI. "Introducing Chunk Sidecars: Inner Loop Validation That Keeps Up with Your Agents." https://circleci.com/blog/chunk-sidecars/
23. CircleCI. "Stop Pushing Broken Code to CI: Wire Chunk Sidecars into Agent Hooks." https://circleci.com/blog/chunk-sidecar-agent-hooks/
24. OpenAI. "OpenAI Introduces Harness Engineering: Codex Agents Power Large-Scale Software Development." InfoQ, 2026. https://www.infoq.com/news/2026/02/openai-harness-engineering-codex/
25. Anthropic. "Anthropic Designs Three-Agent Harness Supports Long-Running Full-Stack AI Development." InfoQ, 2026. https://www.infoq.com/news/2026/04/anthropic-three-agent-harness-ai/

### 文档管理

26. AGENTS.md Spec (2026). Morphllm. https://www.morphllm.com/agents-md-guide
27. Tembo. "What Is AGENTS.md? How to Write One in 2026." https://www.tembo.io/blog/agents-md
28. GitLab. "AGENTS.md Standards." https://gitlab-com.gitlab.io/public-sector/reference/standards/agents-md/
29. Layer5. "AGENTS.md: One File to Guide Them All." https://layer5.io/blog/ai/agentsmd-one-file-to-guide-them-all

---

## 10. Matt Pocock Skills 深度分析

> 仓库：https://github.com/mattpocock/skills（80,000+ Stars，2026.07）
> 定位：真实工程开发（Real Engineering），不是 Vibe Coding
> 设计哲学：**人类主动编排整个流程，Agent 执行每一步**

### 10.1 设计哲学

Matt Pocock 的 skills 与 GSD、BMAD、Spec-Kit 等"全自动流程"走的是完全不同的路线：

| 维度 | Matt Pocock Skills | GSD / BMAD / Spec-Kit |
|------|-------------------|----------------------|
| 控制权 | **人类主导**，agent 执行每一步 | 流程框架主导，人类只是输入意图 |
| 粒度 | 小而独立、可组合 | 大一统的自动化流水线 |
| 可调试性 | 每步可独立回溯、修改 | 流程中的 bug 难以定位 |
| 适配性 | 纯 Markdown，可随意修改 | 框架约束，难以定制 |

核心理念引用自《程序员修炼之道》和《领域驱动设计》，把软件工程几十年的最佳实践压缩为 Agent 可执行的 skill。

**与其他框架的本质区别**：
- "这些 skills 设计得小而易于修改和组合。它们基于几十年的工程经验。你可以随意 hack 它们，让它们成为你自己的。"
- 区分 **User-invoked**（人类显式调用，负责编排）和 **Model-invoked**（Agent 自动触达，负责执行）

### 10.2 完整 Skills 目录

#### 工程开发核心流（Engineering）

**User-invoked（人类驱动，负责编排）**：

| Skill | 用途 | 本项目状态 |
|-------|------|-----------|
| **ask-matt** | 路由器：根据场景推荐该用哪个 skill | ❌ 缺失 — 本项目无路由分发机制 |
| **grill-with-docs** | 设计追问 + 构建共享语言 + 写 ADR | ✅ 已安装 |
| **to-spec** | 将讨论内容合成 spec 发布到 issue tracker | ❌ 缺失（有旧版 `to-prd`） |
| **to-tickets** | 把 spec 拆成 tracer-bullet tickets（声明依赖边） | ❌ 缺失（有旧版 `to-issues`） |
| **implement** | 按 ticket 构建 → 驱动 `/tdd` → 收尾 `/code-review` | ❌ 缺失 — **核心缺失** |
| **triage** | Issue 状态机流转 | ✅ 已安装 |
| **improve-codebase-architecture** | 扫描代码库找深化机会，生成 HTML 报告 | ✅ 已安装 |
| **setup-matt-pocock-skills** | 初始化：配置 issue tracker / labels / doc 布局 | ✅ 已安装 |
| **wayfinder** | 规划超大任务（跨 session）→ 决策地图 + 探索 tickets | ❌ 缺失 — 对标 OpenSpec explore |

**Model-invoked（Agent 自动触达，负责执行）**：

| Skill | 用途 | 本项目状态 |
|-------|------|-----------|
| **prototype** | 构建一次性原型回答设计问题 | ✅ 已安装 |
| **diagnosing-bugs** | 规范化 bug 诊断循环 | ⚠️ 有旧版 `diagnose` |
| **research** | 委托后台 agent 调研 + 输出引用 Markdown | ❌ 缺失 — **本项目高频需求** |
| **tdd** | TDD 红绿重构循环 | ✅ 已安装 |
| **domain-modeling** | 主动构建和打磨领域模型 → 更新 CONTEXT.md | ❌ 缺失 — 与 `grill-with-docs` 互补 |
| **codebase-design** | 深度模块设计词汇（module, interface, depth, seam） | ❌ 缺失 |
| **code-review** | 双轴审阅：Standards + Spec（并行子 agent） | ⚠️ 有旧版 `review` |
| **resolving-merge-conflicts** | 结构化合并冲突解决（逐 hunk，按意图选择） | ❌ 缺失 |

#### 生产力工具（Productivity）

| Skill | 用途 | 本项目状态 |
|-------|------|-----------|
| **grill-me** | 纯追问（无文档产出，适合无代码库场景） | ✅ 已安装 |
| **handoff** | 会话压缩为交接文档 | ✅ 已安装 |
| **teach** | 多 session 教学 | ✅ 已安装 |
| **writing-great-skills** | Skill 编写规范和词汇表 | ⚠️ 有旧版 `write-a-skill` |
| **grilling** | grilling 循环的可复用原语（model-invoked） | ❌ 缺失 |

#### 杂项（Misc）

| Skill | 用途 | 本项目状态 |
|-------|------|-----------|
| **git-guardrails-claude-code** | 阻止危险 git 操作 | ✅ 已安装 |
| **migrate-to-shoehorn** | `as` 断言 → shoehorn 迁移 | ✅ 已安装 |
| **scaffold-exercises** | 创建练习题结构 | ✅ 已安装 |
| **setup-pre-commit** | 配置 Husky pre-commit hooks | ✅ 已安装 |

#### 已废弃（Deprecated）

| Skill | 替代 | 本项目状态 |
|-------|------|-----------|
| `ubiquitous-language` | → `grill-with-docs` | ⚠️ 仍安装旧版 |
| `design-an-interface` | → 无直接替代（功能分散） | ⚠️ 仍安装旧版 |
| `qa` | → 无直接替代 | ⚠️ 仍安装旧版 |
| `request-refactor-plan` | → 无直接替代 | ⚠️ 仍安装旧版 |

### 10.3 核心工作流：Idea → Ship

Matt Pocock 定义了一条 "主流程 + 匝道" 的开发路径：

```
                     ┌─────────────────────┐
                     │   /grill-with-docs   │ ← 入口：对齐需求 + 构建共享语言
                     └──────────┬──────────┘
                                │
                    ┌───────────▼───────────┐
                    │ 需要原型验证设计问题？  │
                    └───┬───────────────┬───┘
                    Yes │               │ No
              ┌────────▼────────┐      │
              │  /handoff →     │      │
              │  /prototype →   │      │
              │  /handoff back  │      │
              └────────┬────────┘      │
                       └───────┬───────┘
                               │
                   ┌───────────▼───────────┐
                   │ 多 session 大任务？     │
                   └───┬───────────────┬───┘
                   Yes │               │ No
             ┌─────────▼────────┐     │
             │ /to-spec →       │     │
             │ /to-tickets →    │     │
             │ /implement × N   │     │
             │ (每个 ticket      │     │
             │  新鲜 context)   │     │
             └──────────────────┘     │
                                      │
                              ┌───────▼───────┐
                              │  /implement   │ ← 直接在当前 context
                              │  (tdd +       │    构建
                              │   code-review)│
                              └───────────────┘
```

**两条匝道**：
- **有 bug / 需求涌入** → `/triage` → 产生 agent-ready issues → `/implement`
- **出现问题定位** → `/diagnosing-bugs` → 修复 + 回归测试
- **超大模糊任务** → `/wayfinder` → 决策地图 → `/to-spec`

**上下文管理原则**（对本项目至关重要）：
- Step 1-3（grilling → spec → tickets）保持 **一个完整 context 窗口**，不 compact 不清除
- 每个 `/implement` 用**全新 context**，只读 ticket 就开始
- 跨窗口用 `/handoff` 桥接

### 10.4 与项目现状的融合分析

#### 10.4.1 本项目已有但需要升级的

| 旧 Skill | → 新 Skill | 升级原因 |
|----------|-----------|---------|
| `review` | `code-review` | 双轴并行审阅（Standards + Spec），旧版只有单轴 |
| `diagnose` | `diagnosing-bugs` | 新版强调"拒绝猜测直到有 tight feedback loop" |
| `to-prd` | `to-spec` | 新版有 seam 分析 + 模板更结构化 |
| `to-issues` | `to-tickets` | 新版支持依赖边 + 本地文件/远程 tracker 双模式 |
| `write-a-skill` | `writing-great-skills` | 新版是完整的 skill 编写参考 |
| `ubiquitous-language` | `grill-with-docs` | 功能已内置到 grill-with-docs |

#### 10.4.2 本项目缺失但强烈推荐引入的

按对本项目的价值排序：

| # | Skill | 为什么需要 | 与本项目的契合度 |
|---|-------|-----------|----------------|
| **1** | **research** | 调研类任务（如本次调研）每次都是手动搜，有了它可以直接委托后台 agent 出引用报告 | ⭐⭐⭐⭐⭐ |
| **2** | **implement** | 串联 `/tdd` + `/code-review`，是目前手动编排的 '写代码→写测试→审阅' 循环的标准化版本 | ⭐⭐⭐⭐⭐ |
| **3** | **domain-modeling** | 本项目有 `CONTEXT.md` 但缺少主动打磨领域模型的机制 | ⭐⭐⭐⭐ |
| **4** | **codebase-design** | 本项目做 coding agent 系统，模块设计深度是关键 | ⭐⭐⭐⭐ |
| **5** | **code-review** | 替代旧 `review`，双轴审阅更适合 spec-driven 开发 | ⭐⭐⭐⭐ |
| **6** | **to-spec + to-tickets** | 与 OpenSpec 的 propose→apply 互补：Matt 的版本更轻量、更面向 issue tracker | ⭐⭐⭐ |
| **7** | **diagnosing-bugs** | 替代旧 `diagnose`，规范化 bug 诊断 | ⭐⭐⭐ |
| **8** | **ask-matt** | 本项目 skills 已经很多（50+），缺少路由会让用户不知所措 | ⭐⭐⭐ |
| **9** | **resolving-merge-conflicts** | 日常开发高频场景 | ⭐⭐ |

#### 10.4.3 Matt Pocock Skills vs OpenSpec：互补 vs 替代

这是最重要的架构决策。两者解决不同的问题：

| 维度 | OpenSpec | Matt Pocock Skills |
|------|----------|-------------------|
| **定位** | 需求→代码的**规格化管理**（spec lifecycle） | 人→Agent 的**对话式协作**（conversation flow） |
| **核心产物** | proposal.md / design.md / tasks.md / spec delta | CONTEXT.md / ADR / issue / handoff note |
| **状态追踪** | 五阶段 workflow state machine | 无内置状态机，依赖 issue tracker |
| **粒度** | Change 级别（大） | Conversation 级别（灵活） |
| **人工审批** | Gate-based（每个 phase 有 ready_for_review） | 自由选择（grill-me 中有追问，但无强制门禁） |
| **适合场景** | 中大型功能开发、需要结构化 spec | 日常开发、快速迭代、小修小补 |

**推荐融合方式**（非二选一）：
- **OpenSpec** 继续作为 change-level 的规格管理框架
- **Matt Pocock Skills** 作为 conversation-level 的协作工具
- 具体来说：OpenSpec 的 `propose` 阶段用 `/grill-with-docs` 做设计追问；`apply` 阶段用 `/implement` 替代纯手动构建；`code-review` 阶段用 `/code-review` 做双轴审阅

### 10.5 可执行的升级路径

```
Phase 1: 升级已安装的旧版 skills
├── review → code-review
├── diagnose → diagnosing-bugs
├── to-prd → to-spec
├── to-issues → to-tickets
├── write-a-skill → writing-great-skills
└── 移除 deprecated: ubiquitous-language, design-an-interface, qa, request-refactor-plan

Phase 2: 引入核心缺失 skills
├── research（最高优先级 — 每次调研都用）
├── implement（标准化 build 流程）
├── domain-modeling（打磨 CONTEXT.md）
└── codebase-design（模块设计词汇）

Phase 3: OpenSpec + Matt Skills 融合
├── /grill-with-docs 作为 OpenSpec planning 的前置追问
├── /implement 作为 OpenSpec building 的执行引擎
├── /code-review 作为 OpenSpec code-review 的审阅工具
└── 对比 OpenSpec wayfinder vs Matt wayfinder，选其一或互补使用
```

### 10.6 参考来源

- Matt Pocock Skills 仓库：https://github.com/mattpocock/skills
- DeepWiki 全解析：https://deepwiki.com/mattpocock/skills
- Skills 映射与废弃记录 (v1.1)：https://dev.to/skillselion/matt-pococks-skills-mapped-the-flow-he-teaches-every-deprecation-and-what-replaced-what-v11-2883
- 中文精读文章（腾讯云）：https://cloud.tencent.com.cn/developer/article/2704288
- 中文分析文章（colobu）：https://colobu.com/2026/06/28/mattpocock-skills-real-engineering-not-vibe-coding/
- ask-matt 路由说明：https://raw.githubusercontent.com/mattpocock/skills/main/skills/engineering/ask-matt/SKILL.md
