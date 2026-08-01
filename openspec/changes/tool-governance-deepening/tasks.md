# Tasks: 工具治理做深

## 1. `agent/embedding/` 公共模块

- [ ] 1.1 定义 `agent/embedding/` 接口（embedding 计算 + 向量相似度），供 #75 复用
- [ ] 1.2 实现 embedding 计算与余弦相似度（轻依赖，纯 Python 或最小依赖）
- [ ] 1.3 单元测试：相似度计算、阈值判定

## 2. 语义去重

- [ ] 2.1 工具描述 embedding → 余弦 >0.9 自动标记 duplicate_of
- [ ] 2.2 生成差异说明注入 prompt
- [ ] 2.3 单元测试：去重标记、差异说明

## 3. 动态选择流水线

- [ ] 3.1 BM25 粗筛（全部 → Top50）
- [ ] 3.2 embedding 精排 → reranker 重排 → Top5
- [ ] 3.3 注入 loop 的 get_all_schemas 入口，选择延迟纳入 trace
- [ ] 3.4 集成测试：Top-K 注入 loop 集成
- [ ] 3.5 延迟预算验证（选择延迟可控）

## 4. 质量评分

- [ ] 4.1 按 run 聚合 status/duration_ms/approval 计算 quality score
- [ ] 4.2 低分自动降级（从 get_all_schemas 排除或降优先级）
- [ ] 4.3 与 tool_permissions 权限判定组合
- [ ] 4.4 单元测试：quality score 计算、降级

## 5. 生命周期状态机

- [ ] 5.1 four-state 状态机（low_traffic → deprecation → grace → removed）
- [ ] 5.2 deprecation notice 注入 schema/上下文
- [ ] 5.3 单元测试：状态机流转、自动移除

## 6. MCP 运行期健康检查

- [ ] 6.1 McpServerStatus 增加 health ping、失败率窗口、degraded 字段
- [ ] 6.2 失败率超阈值自动降级（隐藏 server tools）
- [ ] 6.3 单元测试：健康检查、失败率降级

## 7. 配置与收尾

- [ ] 7.1 config 新增工具治理配置段（cosine 阈值/质量窗口/生命周期时长）
- [ ] 7.2 OpenSpec spec 同步
- [ ] 7.3 全量 pytest + openspec validate + artifact checker
- [ ] 7.4 benchmark 量化（工具选择延迟/去重率/质量分布）

## 8. 收尾校验（checker 要求项）

- [ ] 8.1 pre-implementation grill-with-docs 或等价设计审阅任务（进入 building 前）
- [ ] 8.2 benchmark smoke verification（coding-agent core change 要求）
- [ ] 8.3 当前规格同步：把 spec delta 合并到 `openspec/specs/<capability>/spec.md`
