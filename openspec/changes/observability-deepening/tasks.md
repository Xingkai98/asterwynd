# Tasks: 可观测性做深

## 1. 结构化 Metrics + token 记录

- [ ] 1.1 TraceRecorder 的 llm_iteration 与 tool_result 记录 token
- [ ] 1.2 结构化事件 schema（含 token/phase/tool 维度）扩展 TraceRecorder
- [ ] 1.3 时间序列输出
- [ ] 1.4 单元测试：token 记录、schema

## 2. 成本归属

- [ ] 2.1 定义 phase 语义（映射 AgentMode）
- [ ] 2.2 cost_tracker.compute_cost 按 session/phase/tool 分组记账
- [ ] 2.3 账单输出（CLI/web）
- [ ] 2.4 单元测试：成本归属分组

## 3. 异常自动分类

- [ ] 3.1 结构化分类器（权限拒绝/网络超时/模型幻觉/参数错误）
- [ ] 3.2 差异化告警策略
- [ ] 3.3 单元测试：分类器、告警

## 4. CI 回归门禁

- [ ] 4.1 基线持久化（P95 延迟/成功率）
- [ ] 4.2 CI 跑 benchmark → 对比基线 → 劣化 >5% 拦截（返回非零）
- [ ] 4.3 复用 PR #80 statistics（bootstrap CI）
- [ ] 4.4 集成测试：门禁命令

## 5. Session timeline 看板

- [ ] 5.1 单个 session timeline 可视化（tool call 耗时排序/条形）
- [ ] 5.2 与 add-minimal-tui-runtime-view 对齐事件粒度
- [ ] 5.3 集成测试：看板渲染

## 6. 收尾

- [ ] 6.1 OpenSpec spec 同步
- [ ] 6.2 全量 pytest + openspec validate + artifact checker
- [ ] 6.3 benchmark 量化（session 账单、P95 对比、异常分类准确率）

## 8. 收尾校验（checker 要求项）

- [ ] 8.1 pre-implementation grill-with-docs 或等价设计审阅任务（进入 building 前）
- [ ] 8.2 benchmark smoke verification（coding-agent core change 要求）
- [ ] 8.3 当前规格同步：把 spec delta 合并到 `openspec/specs/<capability>/spec.md`
