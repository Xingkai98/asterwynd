# ADR-0001: 长期记忆三层存储（Postgres + 向量库 + 全局摘要）作为后置演进，不以默认依赖引入

- **Status**: accepted
- **Date**: 2026-08-02
- **Deciders**: 长期记忆深化 change（#75）设计评审

## Context

Issue #75 提出把长期记忆从"Markdown 文件 + MEMORY.md 关键词索引"升级到工业级形态：三层存储 = Postgres（结构化元数据）+ 向量库（语义检索）+ 全局摘要（注入上下文 ~50 token）。当前实现是本地文件存储（`~/.asterwynd/projects/<hash>/memory/`，YAML frontmatter + Markdown），项目定位是 **local/lightweight** 的 coding agent（见 `CONTEXT.md` 与 `docs/project-positioning.md`）。

需要决策：本 change 是否默认引入 Postgres + 向量库作为记忆后端？

## Decision

**本 change 不引入 Postgres + 向量库。** 三层存储作为后置演进项，由单独 change 立项后再实施。本 change 基于现有文件存储完成四件事：写入去重/冲突检测（embedding 召回 top5 + LLM 三分支）、importance × recency 时效性衰减 + 30 天归档、`SearchMemory` 按需语义检索 + ~50 token 全局摘要注入、project/repo scope 隔离。

向量召回能力通过复用 #77 已合入的 `agent/embedding/` 模块（`NGramEmbedding` 零依赖默认 + `InMemoryVectorStore`）获得，该模块的 `EmbeddingProvider` / `VectorStore` 协议即是为未来替换 pgvector/sqlite-vec 等后端预留的 seam。

## Alternatives Considered

| 备选方案 | 描述 | 拒绝原因 |
|----------|------|---------|
| 一步到位三层存储（Postgres + pgvector） | 本 change 直接引入 Postgres 常驻服务 + pgvector 向量列，作为记忆唯一存储 | 与项目 local/lightweight 定位冲突：单用户本地 agent 需运维常驻 DB，无收益。参考实现证据：Claude Code 自身即文件式存储；Letta 用纯文件 + gpt-4o-mini 在 LoCoMo 拿到 74.0% 准确率；sqlite-vec 暴力扫描到 ~100K-1M 向量仍 "fast enough"。方向性重写，未 ADR 前风险高 |
| SQLite + sqlite-vec 起步 | 用单 .db 文件承载元数据 + 向量 | 当前记忆规模（几十条）远未到 SQLite 线性扫描瓶颈；文件存储 + 内存向量索引足够，且保持 Markdown 可读/可审计的 Claude Code 兼容形态。作为中间态可留到后置 change 再评估 |
| 仅目录隔离 + 关键词检索（维持现状） | 不升级记忆系统 | 无法表达语义去重/冲突检测/衰减，面试与能力上无法对标 Claude Code Dream / MemGPT |

## Consequences

- 正面影响：
  - 保持零外部依赖、零常驻服务，符合 local/lightweight 定位。
  - 去重/衰减/scope 等能力在文件存储上即可落地，风险低、可测试。
  - `agent/embedding/` 协议层为未来切换到 pgvector/sqlite-vec 预留了 seam，迁移路径清晰（AgentOS 伸缩阶梯：单文件 → SQLite+HNSW → pgvector）。
  - 面试叙事完整：写入去重三分支、importance×recency 衰减、scope 隔离、~50 token 摘要注入均可讲可测。
- 负面影响：
  - NGramEmbedding 是 n-gram 哈希近似，不是真正语义 embedding，召回质量弱于向量模型；通过 config 可插拔 seam 缓解。
  - 文件扫描式召回在记忆量极大（万级+）时会退化；当前规模下可接受，量变时触发后置 change。
- 需要的相关变更：
  - `docs/adr/ADR-0001-long-term-memory-storage.md` 本文件。
  - change 内实现按 Decision 1 低风险切片落地。

## Revisit Conditions

在以下条件出现时重新审视本决策：
- [ ] 记忆规模增长到 ~10K+ 条，或出现多用户/多 agent 共享记忆需求（需要常驻 DB 与关系+向量联合查询）。
- [ ] 需要混合检索（全文 + 向量 + recency + scope affinity 融合）且文件实现无法满足。
- [ ] 有明确的外部部署/合规约束要求记忆落库（而非 Markdown 文件）。
