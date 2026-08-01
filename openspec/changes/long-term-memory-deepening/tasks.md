# Tasks: 长期记忆做深

## 1. 写入去重 + 冲突检测

- [ ] 1.1 schema 增加 importance/created_at/last_accessed_at/scope 字段
- [ ] 1.2 embedding 召回 top5 相似（复用 #77 `agent/embedding/`）
- [ ] 1.3 LLM 判断"补充/更新/矛盾"三分支
- [ ] 1.4 矛盾标记 + change log
- [ ] 1.5 SaveMemoryTool 去重语义升级
- [ ] 1.6 单元测试：三分支、矛盾标记、change log

## 2. 时效性衰减 + 归档

- [ ] 2.1 importance × recency 评分公式
- [ ] 2.2 超 30 天未检索自动归档 + 归档/恢复 API
- [ ] 2.3 单元测试：衰减公式、归档

## 3. 按需检索 + 全局摘要

- [ ] 3.1 search_memory 语义检索工具（top-k）
- [ ] 3.2 MemoryIndexSource 全局摘要 ~50 token
- [ ] 3.3 集成测试：摘要注入 + 检索

## 4. Scope 隔离

- [ ] 4.1 project/repo scope 标签 + 跨项目校验
- [ ] 4.2 单元测试：scope 隔离

## 5. 收尾

- [ ] 5.1 ADR：三层存储（Postgres+向量库）依赖成本论证（立项后置项）
- [ ] 5.2 OpenSpec spec 同步
- [ ] 5.3 全量 pytest + openspec validate + artifact checker
- [ ] 5.4 benchmark 量化（注入 2K→50 token、三分支闭环、衰减留存率）

## 8. 收尾校验（checker 要求项）

- [ ] 8.1 pre-implementation batch-grill-me 或等价设计审阅任务（进入 building 前）
- [ ] 8.2 benchmark smoke verification（coding-agent core change 要求）
- [ ] 8.3 当前规格同步：把 spec delta 合并到 `openspec/specs/<capability>/spec.md`
