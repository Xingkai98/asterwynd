# Tasks: 长期记忆做深

## 1. 写入去重 + 冲突检测

- [x] 1.1 schema 增加 importance/created_at/last_accessed_at/scope 字段（frontmatter metadata 下，用 pyyaml 解析/序列化）
- [x] 1.2 embedding 召回 top5 相似（复用 #77 `agent/embedding/`：NGramEmbedding + InMemoryVectorStore）
- [x] 1.3 LLM 判断"补充/更新/矛盾"三分支（`agent/memory/dedup.py` `MemoryDedupJudge`，llm 可空，fallback 直接写）
- [x] 1.4 矛盾标记 + change log（frontmatter `metadata.conflict_with` + `memory_dir/changelog.md`）
- [x] 1.5 SaveMemoryTool 去重语义升级（factory 注入 llm）
- [x] 1.6 单元测试：三分支、矛盾标记、change log

## 2. 时效性衰减 + 归档

- [x] 2.1 importance × recency 评分公式（recency = 0.5^(days/30)，时钟可注入）
- [x] 2.2 超 30 天未检索自动归档 + 归档/恢复 API（run_decay() 惰性执行）
- [x] 2.3 单元测试：衰减公式、归档

## 3. 按需检索 + 全局摘要

- [x] 3.1 SearchMemory 语义检索工具（工具名 `SearchMemory`，top-k，可带 scope/type 过滤）
- [x] 3.2 MemoryIndexSource 全局摘要 ~50 token（`agent/memory/summary.py` 启发式生成）
- [x] 3.3 集成测试：摘要注入 + 检索

## 4. Scope 隔离

- [x] 4.1 project/repo scope 标签 + 跨项目校验
- [x] 4.2 单元测试：scope 隔离

## 5. 收尾

- [x] 5.1 ADR：三层存储（Postgres+向量库）依赖成本论证（docs/adr/ADR-0001）
- [x] 5.2 OpenSpec spec 同步
- [x] 5.3 全量 pytest + openspec validate + artifact checker
- [x] 5.4 benchmark 量化（`benchmarks/tasks/asterwynd-022-long-term-memory/`：注入 2K→50 token、三分支闭环、衰减留存率）

  实测数据（15 条记忆场景，tiktoken cl100k_base）：
  - **注入 token 节省**：MEMORY.md 全索引 344 tokens → 全局摘要 57 tokens，节省 83.4%；记忆量增大到 200 行/25KB 索引上限时节省 >97%（规格口径 2K→50）。
  - **三分支闭环**：update/supplement/conflict/new 四种判断全部产生正确存储结果（4/4），`metadata.conflict_with` 双向标记正确，change log 记录 4 条。
  - **衰减留存率**：30 天窗口内访问过的记忆 100% 保留；40 天未访问的 cold 记忆被归档、恢复 API 可还原。

## 8. 收尾校验（checker 要求项）

- [x] 8.1 pre-implementation batch-grill-me 或等价设计审阅任务（进入 building 前）— 2026-08-02 完成，确认记录见 design.md `## Pre-Implementation Review`
- [x] 8.2 benchmark smoke verification（coding-agent core change 要求）
- [x] 8.3 当前规格同步：把 spec delta 合并到 `openspec/specs/<capability>/spec.md`

## 9. 审阅修复（Round 1 → Round 2）

- [x] 9.1 Major: run_decay() 无生产调用点 → `_run_decay_if_due()` 节流后接入 load_index/load_summary/recall/search 读入口
- [x] 9.2 Major: dedup judge 硬编码 model="gpt-4" → 传 model=None 让 LLM 用自己的模型 + 回归测试
- [x] 9.3 MemoryConfig 死配置 → `_parse_memory_config` 接入 yaml 解析 + main.py 传给 PersistentMemory
- [x] 9.4 dedup_recall_threshold 未应用 → MemoryDedupJudge.recall_threshold 短路 + 回归测试
- [x] 9.5 summary.py 死代码 → PersistentMemory.load_summary 委托 summary.build_summary
- [x] 9.6 apply_judgment LLM target_name 路径安全 → _validate_name 校验
- [x] 9.7 save() update 丢失 type 参数 → 更新 existing.type + 回归测试
- [x] 9.8 backlog `search_memory` → `SearchMemory` 更新
