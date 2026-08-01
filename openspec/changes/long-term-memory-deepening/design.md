# Design: 长期记忆做深 — 去重冲突检测 + 时效性衰减 + 三层存储（后置）

## Context

当前跨 session 记忆是 Markdown 文件 + MEMORY.md 索引（`PersistentMemory`，YAML frontmatter + Markdown，类型 user/feedback/project/reference）。`SaveMemoryTool` 按 name 直接覆盖，无去重、无冲突检测、无衰减、无 scope 标签。`MemoryIndexSource` 注入 MEMORY.md 索引（200 行/25KB 截断）。面试表现"Markdown 存记忆 + search_memory 关键词匹配"与 Claude Code Dream 机制差距巨大。

## Goals / Non-Goals

**Goals:**

- 写入去重：embedding 召回 top5 相似 + LLM 判断"补充/更新/矛盾" + 矛盾标记 + change log。
- 时效性衰减：importance × recency 联合评分，超 30 天未检索自动归档。
- 按需检索：上下文只注入摘要索引（~50 token），模型主动调 search_memory 语义查询。
- Scope 隔离：project/repo scope 标签，跨项目不串数据。
- 三层存储（Postgres + 向量库 + 全局摘要）作为后置项，先 ADR 论证。

**Non-Goals:**

- 不默认引入 Postgres + 向量库（先 ADR，低风险切片先行）。
- 不重做 session 内 MemoryManager 压缩（属 #74）。

## Decisions

### Decision 1: 低风险切片先行，三层存储后置

**方案**：本 change 先做写入去重/冲突检测 + importance×recency 衰减 + 30 天归档 + search_memory 语义检索 + scope 标签（基于现有文件存储 + 复用 #77 embedding）。Postgres + 向量库三层存储作为后置项，先立 ADR 论证依赖成本。

**备选**：一步到位三层存储。被拒：Postgres+向量库是方向性重写，与项目 local/lightweight 定位冲突，未 ADR 前风险高。

**理由**：去重/衰减基于现有文件存储即可落地，三层存储是增量演进。

### Decision 2: 写入去重用 embedding 召回 + LLM 三分支判断

**方案**：新记忆 incoming → embedding 召回 top5 相似 → LLM 判断"补充/更新/矛盾" → 矛盾标记 + change log。补充=追加到已有记忆；更新=修改；矛盾=标记并保留双方。

**备选**：仅同名覆盖。被拒：无法处理语义相近但不同名的记忆，无法讲"补充/更新/矛盾"三分支。

**理由**：三分支判断是面试核心答案，也是记忆系统的必要语义。

### Decision 3: importance × recency 衰减 + 30 天归档

**方案**：schema 增加 importance/created_at/last_accessed_at，评分公式 importance × recency（recency 随未检索天数衰减），超 30 天未检索自动归档（提供归档/恢复 API）。

**备选**：无衰减。被拒：记忆无限增长，无法讲"时效性衰减"。

**理由**：衰减是记忆系统"遗忘"能力的核心。

### Decision 4: MemoryIndexSource 全局摘要 ~50 token

**方案**：把 MemoryIndexSource 从注入 200 行/25KB 索引改为注入 ~50 token 全局摘要，全文按需 search_memory 工具语义检索。

**备选**：注入全索引。被拒：占上下文太多，与 #74 注入顺序冲突。

**理由**：摘要注入 + 按需检索是工业级记忆的标准形态。

### Decision 5: Scope 隔离用 project/repo 标签

**方案**：schema 增加 scope（project/repo）标签，跨项目查询或写入时校验 scope，不串数据。

**备选**：仅目录隔离。被拒：无法显式表达 scope，无法跨项目安全查询。

**理由**：显式 scope 标签是记忆隔离的可讲可测方案。

## Pre-Implementation Review

- 待 planning 阶段（grill-with-docs）确认本设计，并补齐 Reference Implementation Research 实质 findings 与 design impact。

## Reference Implementation Research

- status: enabled
- reason: 长期记忆是 Claude Code Dream 机制、MemGPT 分层记忆的核心能力，需参考其去重/冲突处理、衰减/归档、三层存储取舍。
- research questions:
  - Claude Code Dream 机制的全局知识文档维护与去重/冲突处理？
  - MemGPT 分层记忆与衰减/归档策略？
  - Postgres+向量库 vs 轻量文件存储取舍（local/lightweight 定位）？
- findings: 待 planning 阶段补充（proposal 阶段已登记；实质调研在本 change planning 阶段完成）。
- design impact: 待 planning 阶段补充；先决条件是先立 ADR 论证三层存储依赖成本，复用 #77 embedding 模块。

## Risks / Trade-offs

- **[三层存储方向性重写] → 先 ADR 论证 Postgres+向量库依赖成本，未 ADR 前只做低风险切片（去重/衰减）。**
- **[LLM 冲突判断不准确] → 判断结果可人工复核，矛盾标记保留双方，change log 可回溯。**
- **[衰减误归档重要记忆] → importance 权重可调，归档提供恢复 API，30 天阈值可配置。**
- **[与 #74 注入层冲突] → MemoryIndexSource 全局摘要改造基于 #74 稳定后的注入管线。**
- **[embedding 依赖] → 复用 #77 `agent/embedding/` 模块，轻依赖起步。**

## Testing Strategy

- 单元测试：写入去重三分支、衰减评分公式、30 天归档、scope 隔离。
- 集成测试：SaveMemory 去重语义、search_memory 检索、MemoryIndexSource 摘要注入。
- 回归测试：既有 PersistentMemory/SaveMemory 测试不回归。
- benchmark 层级：去重/召回质量量化（复用 PR #80 statistics）。

## Impact Analysis

| 影响面 | 说明 |
|---------|------|
| `agent/memory/persistent.py` | 去重/冲突/衰减/scope |
| `agent/tools/builtin/memory.py` | SaveMemory 去重、search_memory 工具 |
| `agent/context/sources.py` | 全局摘要 ~50 token |
| `agent/embedding/`（#77） | 向量召回 |
| `agent/config.py` | 记忆配置段 |
| `benchmarks/` | 去重/召回量化 |
