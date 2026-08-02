# Tasks: 工具治理做深

> **批次范围**：第一批 = 第 1-3、5 节（embedding 模块 + 语义去重 + 动态选择 + 生命周期状态机）；第 4 节（quality score）与第 6 节（MCP 健康）为后续批，本 change 先占位标注。

## 1. `agent/embedding/` 公共模块 ✅

- [x] 1.1 定义 `EmbeddingProvider` 协议（`embed(texts) -> list[Vector]`）+ `VectorStore`/`SimilarityIndex`（`query(vector, top_k)`）两层接口，供 #75 复用
- [x] 1.2 实现 `NGramEmbedding`（字符 n-gram 哈希向量，零外部依赖）+ `InMemoryVectorStore`（内存余弦）
- [x] 1.3 单元测试：相似度计算、阈值判定（12 passed）

## 2. 语义去重（软提示） ✅

- [x] 2.1 注册时对全体工具 embedding 预计算，cosine > 阈值（n-gram 默认 0.7）标记 `duplicate_of`（ToolMetadata 旁路表）
- [x] 2.2 选择时若 Top5 选中被标记工具，追加 `duplicate_of: <primary> + 差异说明` 注入 prompt
- [x] 2.3 单元测试：去重标记、差异说明生成（6 passed）

## 3. 动态选择流水线（ToolSelector） ✅

- [x] 3.1 `selector.py`：BM25 粗筛（全部 → Top50）→ embedding 精排 → Top5
- [x] 3.2 query 构造：最近 user 消息 + 最近工具调用名/参数摘要拼接（每次迭代在 loop 注入点 `_select_tool_schemas`）
- [x] 3.3 稳定层/可变层分层：稳定层核心工具白名单确定性排序始终注入；可变层 Top-K
- [x] 3.4 延迟预算可配置（`config.tool_selection.latency_budget_ms` 默认 50ms）；超预算降级全量注入；选择延迟记录
- [x] 3.5 接入 loop 注入缝（registry.select_schemas(query, k=5)）
- [x] 3.6 集成测试：Top-K 注入 registry、稳定层保持、降级路径（5 passed）
- [x] 3.7 延迟预算实测验证（1000 工具下选择延迟 ~5-7ms < 50ms 预算，本 change 开发前已实测校准）

## 4. 质量评分（后续批）

- [ ] 4.1 按 run 聚合 status/duration_ms/approval 计算 quality score
- [ ] 4.2 低分自动降级（从 get_all_schemas 排除或降优先级）
- [ ] 4.3 与 tool_permissions 权限判定组合
- [ ] 4.4 单元测试：quality score 计算、降级

## 5. 生命周期状态机 ✅

- [x] 5.1 `lifecycle.py`：four-state 状态机（low_traffic → deprecation → grace → removed）
- [x] 5.2 触发：新工具默认 low_traffic；deprecation = 人工标记/注册声明/quality 钩子（后续）；grace 时长可配置（如 7 天）
- [x] 5.3 removed 从 get_all_schemas 排除；deprecation notice 注入选择时上下文
- [x] 5.4 单元测试：状态机流转、自动移除（13 passed）

## 6. MCP 运行期健康检查（后续批）

- [ ] 6.1 McpServerStatus 增加 health ping、失败率窗口、degraded 字段
- [ ] 6.2 失败率超阈值自动降级（隐藏 server tools）
- [ ] 6.3 单元测试：健康检查、失败率降级

## 7. 配置与收尾 ✅

- [x] 7.1 config 新增工具治理配置段（`ToolSelectionConfig`：enabled/top_k/latency_budget_ms/dedup_threshold）
- [x] 7.2 OpenSpec spec 同步（tool-governance 主 spec + workflow-events.jsonl）
- [x] 7.3 全量 pytest（1288 passed，9 个既有环境失败挂 issue #82）+ openspec validate（33/33）+ artifact checker
- [x] 7.4 benchmark smoke 验证（fake agent 跑通 34 任务链路，结果与 baseline 一致：24 failed 为 fake agent 预期 + 10 unsupported 为无 Docker；无 governance 相关崩溃）

## 8. 收尾校验（checker 要求项）

- [x] 8.1 pre-implementation batch-grill-me 或等价设计审阅任务（进入 building 前）✅ 已完成三轮
- [x] 8.2 benchmark smoke verification（coding-agent core change 要求）— fake agent 跑通，结果与 baseline 一致
- [x] 8.3 当前规格同步：把 spec delta 合并到 `openspec/specs/tool-governance/spec.md` ✅
