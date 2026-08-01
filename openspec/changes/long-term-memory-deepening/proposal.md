# Proposal: 长期记忆做深 — 去重冲突检测 + 时效性衰减 + 三层存储（后置）

## Change Type

primary: feature
secondary:
  - memory
  - tools

## 需求

1. 写入去重：新记忆 incoming → embedding 召回 top5 相似 → LLM 判断"补充/更新/矛盾" → 矛盾标记 + change log
2. 时效性衰减：importance × recency 联合评分，超 30 天未检索自动归档
3. 按需检索：上下文只注入摘要索引（~50 token），模型主动调 search_memory 工具做语义查询
4. Scope 隔离：记忆带 project/repo scope 标签，跨项目不串数据
5. （后置，非本 change 必交付）三层存储：Postgres（结构化元数据）+ 向量库（语义检索）+ 全局摘要（注入上下文）

## 背景

当前跨 session 记忆是 Markdown 文件 + MEMORY.md 索引（`PersistentMemory`，YAML frontmatter + Markdown，类型 user/feedback/project/reference）。`SaveMemoryTool` 按 name 直接覆盖，无去重、无冲突检测、无衰减、无 scope 标签。`MemoryIndexSource` 注入 MEMORY.md 索引（200 行/25KB 截断）。

面试表现：说"Markdown 存记忆 + search_memory 关键词匹配"，与 Claude Code 的 Dream 机制差距巨大。

## 非目标

- 不默认引入 Postgres + 向量库（先 ADR 论证依赖成本，与项目 local/lightweight 定位冲突，低风险切片先行）。
- 不重做 session 内 MemoryManager 压缩（属 #74 上下文工程）。

## Impact Analysis

| 影响面 | 说明 |
|---------|------|
| `agent/memory/persistent.py` | 写入去重、冲突检测、衰减、scope 标签 |
| `agent/tools/builtin/memory.py` | SaveMemory 去重语义、search_memory 新工具 |
| `agent/context/sources.py` | MemoryIndexSource 全局摘要 ~50 token |
| `agent/embedding/`（#77 提供） | 向量召回复用 |
| `agent/config.py` | 记忆配置段（衰减阈值/归档周期/scope） |
| `benchmarks/` | 去重/召回质量量化（复用 PR #80 statistics） |

## Reference Implementation Research

- status: enabled
- reason: 长期记忆（去重冲突检测、时效性衰减、三层存储）是 Claude Code Dream 机制、MemGPT 分层记忆的核心能力，应参考其实现。
- research questions:
  - Claude Code Dream 机制的全局知识文档维护与去重/冲突处理？
  - MemGPT 的分层记忆与衰减/归档策略？
  - Postgres+向量库 vs 轻量文件存储的取舍（local/lightweight 定位）？
- findings:
  - 待 planning 阶段补充（本 proposal 阶段完成 status/reason/questions 登记；实质调研在本 change planning 阶段完成）。
- design impact:
  - 待 planning 阶段补充；先决条件：先立 ADR 论证三层存储依赖成本；低风险切片（去重/衰减）基于现有文件存储 + 复用 #77 embedding 模块。

## Dependencies

- 依赖 add-workspace-param（已合入）：PersistentMemory 已用 workspace_root 构造，scope 隔离以此为基。
- 依赖 #77 工具治理：复用 `agent/embedding/` 模块（向量召回）。
- 与 #74 上下文工程共享 memory 子系统（MemoryIndexSource 注入层）。

## 验收

- 能解释"补充/更新/矛盾"三种分支，并给出一组去重/冲突处理的样例。
- 面试可引用注入 2K→50 token（>97% 节省）、三分支去重闭环、衰减留存率数据。
