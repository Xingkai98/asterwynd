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

> 按 AGENTS.md 规则，进入 building 前以 `batch-grill-me` 审视本设计。本 change 在自主模式下执行（用户已授权"开始开发"），因此以推荐答案形式逐项确认并记录为最终方案；实现中若需偏离任一决策，必须回写本记录并说明原因。事实性输入（现有代码、参考实现调研）由 sub-agent 收集，不依赖用户回答。

### Round 1 确认结果

- **R1-Q1 三层存储后置**：✅ 确认。Postgres+pgvector 依赖成本由 ADR-0001 论证，本 change 只做基于现有文件存储的低风险切片。调研佐证：Claude Code 自身即文件式存储（CLAUDE.md + 有 cap 的 MEMORY.md 索引）；Letta 用纯文件 + gpt-4o-mini 在 LoCoMo 拿到 74.0% 准确率，反超无强 context management 的专用记忆工具。
- **R1-Q2 Embedding 后端**：✅ 复用 #77 `agent/embedding/` 的 `NGramEmbedding`（零依赖默认）+ `InMemoryVectorStore`；config 预留 `memory.embedding` 可插拔 seam（未来可换 sentence-transformers / ollama / pgvector）。阈值沿用 #77 标定（语义等价≈0.86、完全不同≈0.11），去重候选召回阈值默认 0.5。
- **R1-Q3 去重触发时机与 fallback**：✅ `SaveMemory` 流程：incoming → embedding 召回 top5 → 无相似候选（max_sim < recall_threshold）→ 直接新建；有候选 → LLM 三分支判断；LLM 不可用（judge 为 None）→ 回退为按 name 直接写入（保留现行为），不阻塞、不额外花 LLM 调用。
- **R1-Q4 三分支动作语义**：✅ 补充（supplement）= 合并追加到既有记忆 body；更新（update）= 整体替换 description + body；矛盾（conflict）= 双方保留 + 双方 frontmatter `metadata.conflict_with` 互相标记 + change log 记录。矛盾不自动消解，检索 ranker 决定当前事实（对齐 Claude Code latest-wins 矛盾策略）。
- **R1-Q5 Change log 格式**：✅ 新增 `memory_dir/changelog.md`，每行一条 `- [ISO时间] <action> <name> → <reason>`，可 grep、可审计；测试用正则断言。
- **R1-Q6 衰减公式与阈值**：✅ `recency(days) = 0.5 ^ (days / RECENCY_HALFLIFE_DAYS)`（半衰期 30 天）；`score = importance × recency`；importance ∈ {1..5}，默认 3。归档触发：`days_since_last_access > ARCHIVE_AFTER_DAYS`（默认 30，可配置）；`decay_threshold` 评分下限默认关闭，不额外拦截。
- **R1-Q7 衰减执行时机**：✅ 惰性执行——`run_decay()` 在 `load_index` / `recall` / `search` / 摘要生成前调用；时钟通过 `time_source` callable 注入，测试可控。
- **R1-Q8 工具命名**：✅ 新工具类 `SearchMemoryTool`，工具名 `SearchMemory`（对齐库内 PascalCase 约定：SaveMemory/RecallMemory/WebFetch）。保留 `RecallMemory`（全量读取）向后兼容。spec 中 `search_memory` 措辞在 spec 同步时更新为 `SearchMemory`。
- **R1-Q9 全局摘要生成**：✅ 启发式确定性摘要：按 importance 降序取 `name: description` 行，token 预算 ~50（`MAX_SUMMARY_TOKENS=50`），末尾提示 `Use SearchMemory for details`。不依赖 LLM，测试确定。
- **R1-Q10 Scope 值**：✅ scope = git root 解析路径（`PersistentMemory.scope`），frontmatter 增加 `metadata.scope`；迁移时旧记忆默认补当前项目 scope。SearchMemory / RecallMemory 支持 scope 参数，跨 scope 请求直接拒绝，不串数据。
- **R1-Q11 配置段**：✅ 新增 `MemoryConfig` dataclass（archive_after_days / recency_halflife_days / importance_default / recall_top_k / summary_tokens / dedup_recall_threshold），挂到 `AsterwyndConfig.memory`。
- **R1-Q12 LLM 注入**：✅ 新增 `MemoryDedupJudge(llm | None)`，经 tools factory 把 llm 注入 SaveMemoryTool / SearchMemoryTool（`_build_agent_core` 已有 llm 实例）。judge 失败不阻塞写入（回退直接写）。
- **R1-Q13 基准量化**：✅ 新增 `benchmarks/tasks/asterwynd-022-long-term-memory/`：量化注入 token 节省（2K→50）、三分支闭环准确率、衰减留存率。
- **R1-Q14 迁移兼容**：✅ 旧记忆无新字段时默认 importance=3、created_at=file mtime、last_accessed_at=file mtime、scope=当前项目；写入时升级 frontmatter，既有测试不回归。

## Reference Implementation Research

- status: enabled
- reason: 长期记忆是 Claude Code Dream 机制、MemGPT 分层记忆的核心能力，需参考其去重/冲突处理、衰减/归档、三层存储取舍。
- research questions:
  - Claude Code Dream 机制的全局知识文档维护与去重/冲突处理？
  - MemGPT 分层记忆与衰减/归档策略？
  - Postgres+向量库 vs 轻量文件存储取舍（local/lightweight 定位）？
- findings:

### Claude Code Dream 机制

- **两层存储结构**：Claude Code 记忆分两层——(a) 人工编写的 CLAUDE.md 规则文件；(b) Claude 自主编写的 "Auto Memory" 笔记，存放在 `~/.claude/projects/<project>/memory/`，以 git root 为 key，同一仓库所有 worktree 共享一个目录；非 git 仓库时用 project root（[vectorize.io](https://vectorize.io/articles/claude-code-memory)、[官方文档 code.claude.com/docs/en/memory](https://code.claude.com/docs/en/memory)）。Auto Memory 由 `MEMORY.md` 索引 + 主题 topic 文件构成；会话启动时注入完整 CLAUDE.md 集合 + auto-memory 索引，`MEMORY.md` 超过前 200 行 / 25KB 即截断并告警（[code.claude.com/docs/en/claudemd](https://code.claude.com/docs/en/claudemd)）。注：上述官方 URL 在本环境直接抓取被网络阻断，内容由 vectorize.io 与 [SFEIR 文章](https://institute.sfeir.com/en/articles/claude-code-dream-auto-dream-memory-consolidation/) 等镜像佐证，也符合本仓库自身 CLAUDE.md/AGENTS.md 结构。
- **不做语义检索**：召回依赖模型从索引和对话中自行判断相关性，显式不用 vector RAG——索引条目和 topic 头部必须以"未来查询会用的词汇"来写（[vantaige.io](https://vantaige.io/blog/claude-code-dreaming-memory-consolidation-setup-2026)、[mindstudio.ai](https://www.mindstudio.ai/blog/what-is-claude-code-autodream-memory-consolidation)）。这验证了"小索引 + 按需 topic 读取"优于全量注入与逐 prompt 向量检索。
- **去重/冲突后置到独立 "dream" pass**：每轮自由采集，去重与冲突消解全部推迟到后台 consolidation；矛盾采用 latest-wins 策略，保留 provenance/version 历史（[github issue #40614](https://github.com/anthropics/claude-code/issues/40614)、[mnemo 对比文档](https://raw.githubusercontent.com/sattyamjjain/mnemo/bbda7df8295febc08d8d15b61191f4fa4d110f62/docs/comparisons/anthropic-dreams.md)）。
- **淘汰是 consolidation 驱动的，不是时间衰减函数**：prune 过期/被取代/已删除文件引用、压缩过长索引行、消解矛盾，外加 size cap；consolidation 以沙箱化后台 subagent 运行（只读 bash、写仅限 memory 目录、PID lock file），产出全新 store 而非原地变更，结果可审阅/可丢弃。
- **Scope 隔离缺口**：per-repo keying 会割裂跨项目记忆，且 Dreams 原语一次只 consolidate 一个 store——本地 agent 应显式设计跨 project/user/agent 的 scope，而不是假设 consolidation 会替它调和。

### MemGPT 分层记忆

- **OS 式虚拟上下文管理**：MemGPT（[arXiv:2310.08560](https://arxiv.org/abs/2310.08560)，Packer et al.）把上下文窗口当 RAM（main context = system 指令 + working context + FIFO queue），外部存储当 disk（recall storage DB + archival storage DB），数据由 LLM 生成的 function call 在层间搬运（[ar5iv 全文](https://ar5iv.labs.arxiv.org/html/2310.08560)）。
- **Eviction 是阈值触发 + LLM 中介**：prompt token 超过 warning 阈值（论文示例 70% 上下文）时注入 memory-pressure 系统消息；超过 flush 阈值（示例 100%）时 evict 一批消息并用"旧摘要 + 被 evict 消息"生成新递归摘要。
- **Letta 三层记忆标准化**（[context hierarchy](https://docs.letta.com/guides/core-concepts/memory/context-hierarchy/)）：core memory（可编辑 blocks，始终钉在 system prompt）、recall memory（SQL 会话历史，hybrid `conversation_search`）、archival memory（向量库长程 passages，按需查询）。core memory blocks 以 XML 式 `<memory_blocks>` 注入，每块有字符上限（schema 默认 2000 字符），经 `memory_insert/memory_replace/memory_rethink/memory_finish_edits` 编辑。
- **Archival 写入不去重**：`archival_memory_insert` 每次调用都新建 ArchivalPassage，只有 tags 去重；社区官方建议 insert 前先 `archival_memory_search` 防重复（[DeepWiki archival memory](https://deepwiki.com/letta-ai/letta/3.2-archival-memory-and-passages)）。
- **默认 embedding** 为 OpenAI text-embedding-3-small（1536 维），endpoint 支持含 ollama 在内的多 provider，可完全本地。
- **无自动衰减/TTL**：archival memory 被描述为 "unlimited storage" 且 agent 不可改；[Engram 竞品分析](https://github.com/ashita-ai/engram/blob/main/docs/research/competitive.md) 给 Letta/MemGPT 的遗忘能力评 "No"（"No principled forgetting"）。上下文压缩反而偏阈值触发（90% 预触发，`SUMMARIZATION_TRIGGER_MULTIPLIER=0.9`）。
- **注入模型**：core memory blocks 永远在 system prompt（完整核心事实索引）；archival 与文件永不注入，全部按需经工具取。**结构性缺口**：论文与 Letta 均无 archival 写入的内容级去重/冲突消解——这是 coding agent 应自补 dedup 策略的地方。

### Postgres+pgvector vs 轻量文件存储

- **pgvector 是 Postgres 扩展而非独立数据库**：向量作为普通列存在普通表中，关系元数据/JSONB/全文/向量共存一个 SQL store，但需要一个常驻 Postgres server（[pgvector README](https://github.com/pgvector/pgvector)）。ANN 用 HNSW（无训练步骤）或 IVFFlat（需训练）。
- **sqlite-vec 是 pre-v1、纯 C、零依赖的 SQLite 扩展**：单 .db 文件即可跑 laptop/mobile/WASM/Raspberry Pi，无 server、零配置；v0.1.x 的 KNN 走 brute-force 线性扫描，作者称对数十万~100 万向量 "fast enough"（[sqlite-vec](https://github.com/asg017/sqlite-vec)、[HN 评论](https://news.ycombinator.com/item?id=40244002)）。
- **AgentOS 的伸缩阶梯**：单 SQLite ~0-1K 向量（零配置）→ SQLite + HNSW sidecar ~1K-500K → Postgres+pgvector ~500K-10M（多租户、原生 HNSW）→ 专用 Qdrant 1B+，每级迁移就是一次 `migrate()` 调用（[docs.agentos.sh sql-storage](https://docs.agentos.sh/features/sql-storage)）。
- **去重：写时 vs 读时是核心分叉**（[Field Guide to AI Memory](https://www.memoryplugin.com/wiki/updates-and-conflicts.html)）。写时清理保持库干净但每次写多花一次 LLM 调用；读时全存、靠 ranker 挑当前事实。mem0 现行为 single-pass ADD-only（dedup 仅精确 MD5 哈希，近重复/矛盾并列存储、读时 ranker 解决），其 legacy 算法曾写时用第二遍 LLM diff top-K 并输出 ADD/UPDATE/DELETE/NONE（[mem0 migration](https://mem0.mintlify.app/migration)）。Engram 走低成本写时去重：cosine >0.88 就地更新、>0.95 跳过插入。
- **衰减/归档**：Engram 按 source_type 分半衰期——decision/preference/architecture 约 1 年、fact 90 天、bug_fix 30 天，`memory_forget` 软删除（行归档而非销毁）。r2mcp 按 tier 自动归档：preferences 永不归档、project-context 180 天、conversations 90 天，另有 `meditate` 工具归档过期条目。Zep/Graphiti 用双时态事实失效（valid_at/invalid_at，历史永不丢失）——但需图数据库。MemGPT/Letta 则只按上下文压力 evict。
- **注入**：mem0 完全按需（无自动注入）；Letta 只常驻 core blocks；Claude Code 会话启动注入全套 CLAUDE.md + 索引（MEMORY.md 超 200 行/25KB 截断）。**token-budgeted 渐进披露是通用模式**：Engram 三层 `memory_index → memory_timeline → memory_get`（命中先回 ~80-120 tokens）；r2mcp recall 逐条并入结果，超 max_tokens 即停。
- **横切证据**：Letta 用纯文件存会话历史测 LoCoMo，gpt-4o-mini 拿到 74.0% 准确率，反超那些"没有强 agentic context management"评估下的专用记忆工具（[letta blog](https://www.letta.com/blog/benchmarking-ai-agent-memory)）——结论：小规模本地 agent，context 管理方式比具体检索/存储机制更关键。

### Design Impact

- **文件存储起步有充分依据**：Claude Code 自身就是文件式（CLAUDE.md + 有 cap 的 MEMORY.md 索引），Letta 用纯文件 + gpt-4o-mini 在 LoCoMo 拿到 74.0%，sqlite-vec 暴力扫描到 ~100K-1M 向量仍 "fast enough"——支持本 change"低风险切片先行、Postgres+pgvector 后置 ADR"的决策，本地单用户不需要常驻 Postgres。
- **写入去重：我们选写时 LLM 三分支，需用工程手段对冲其代价**。字段证据显示写时 reconciliation 是"每次写多花一次 LLM 调用 + 判错会静默污染"的路线，mem0 已从它转向 ADD-only + 读时 ranker。我们的"补充/更新/矛盾"三分支恰好是该路线的强形态，因此必须配套：矛盾标记保留双方、change log 可回溯、结果可人工复核（对应 Risks 表），用可逆性吸收 LLM 误判；同时可用 Engram 的 cosine 0.88/0.95 阈值或 mem0 精确哈希做零 LLM 成本的第一道快速去重，再对 top5 召回走 LLM 三分支。
- **Embedding 召回复用 #77**：MemGPT 论文与 Letta 都验证了"向量相似度召回"是记忆检索的工业标准路径（pgvector cosine + HNSW；text-embedding-3-small/1536d 或 ollama 本地）。我们无需独立向量库——先落在现有文件存储 + embedding 召回，正好对应 Decision 2 的 top5 相似召回。
- **importance × recency 衰减 = 主动补上各参考实现的共同缺口**：Claude Code（consolidation 驱动淘汰）、Letta/MemGPT（无 TTL、"No principled forgetting"）、mem0（无自动衰减）都没有时间/重要度衰减，只有 Engram/r2mcp 实现分 tier 半衰期 + 软删除（archive-not-destroy）。我们的 importance×recency 评分 + 30 天未检索自动归档 + 归档/恢复 API 映射的正是 Engram（decision~1yr / fact~90d / bug_fix~30d）与 r2mcp 的 tiered soft-delete 模式。不采用 Graphiti 双时态图（需图库，本地过重），也不照搬 MemGPT 上下文压力压缩（那是 session 内摘要，属 #74 范畴）。
- **注入形态对齐 Decision 4**：Claude Code 的 200 行/25KB 索引 cap、Letta 的 core blocks 常驻、Engram 的渐进披露（memory_index→memory_get，~80-120 tokens）共同支持"~50 token 全局摘要常驻 + SearchMemory 按需语义检索"的注入模型；其中"索引条目要为未来查询词汇而写"这一点应写进我们的摘要生成规范。
- **Scope 隔离要显式设计**：Claude Code 的 per-repo keying 会割裂跨项目记忆且 Dreams 只按单 store consolidate——佐证 Decision 5 需要显式 project/repo scope 标签而不是仅目录隔离。未来若加后台 consolidation，应按 Claude Code 模式做成沙箱化、只读 bash、写限定 memory 目录、产出新 store 而非原地变更。
- 调研可信度注记：除 code.claude.com 两个文档 URL（本环境网络阻断，已用镜像与本仓库 CLAUDE.md/AGENTS.md 佐证）外，其余来源均直接抓取验证。

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
| `agent/memory/persistent.py` | schema 扩展（importance/created_at/last_accessed_at/scope/conflict_with/archived）、衰减、归档/恢复、change log、scope 校验、相似召回 |
| `agent/memory/dedup.py`（新增） | `MemoryDedupJudge` LLM 三分支判断（补充/更新/矛盾） |
| `agent/memory/summary.py`（新增） | `MemorySummary` ~50 token 全局摘要生成 |
| `agent/tools/builtin/memory.py` | SaveMemory 去重语义、新增 `SearchMemory` 工具 |
| `agent/tools/factory.py` | 注入 llm、注册 SearchMemoryTool、KNOWN_BUILTIN_TOOL_NAMES |
| `agent/context/sources.py` | MemoryIndexSource 全局摘要 ~50 token |
| `agent/embedding/`（#77） | 向量召回复用（NGramEmbedding + InMemoryVectorStore） |
| `agent/config.py` | `MemoryConfig` 配置段 |
| `agent/main.py` | llm 注入 registry |
| `benchmarks/tasks/asterwynd-022-long-term-memory/`（新增） | 注入 token 节省 / 三分支闭环 / 衰减留存率量化 |
