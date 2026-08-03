# Tasks: 多Agent协作做深

## 0. 前置决策

- [x] 0.1 grill 设计（wayfinder:grilling 标签；独立 subagent 已产出 `reviews/grill-design.md`，5 个修改项已整合进 design.md）
- [x] 0.2 Reference Implementation Research 实质调研（Claude Code/Codex/LangGraph/crewAI/Swarm；findings 落进 design.md）

## 1. 状态快照与恢复

- [ ] 1.1 子 agent 中断 → JSON 快照（扩展现有 SessionSnapshot，加 objective/blockers/next_steps；落盘 `<workspace_root>/.asterwynd/subagents/<id>/`，key 用 run_id）
- [ ] 1.2 恢复时从断点继续（走 loop.run 已有 resume 路径，重建 transcript + 重试进行中 tool_call_id）
- [ ] 1.3 复用 SessionStore 的 schema_version/fingerprint/dedup 模式
- [ ] 1.4 单元测试：快照序列化/恢复

## 2. 成本控制

- [ ] 2.0 嵌套 spawn 前置（`_build_subagent_loop` 开 `expose_subagent_tools=True` + depth contextvar spawn_depth；grill 确认的 building 首个前置，hierarchical 模式与 max_depth 均依赖）
- [ ] 2.1 每子 agent token/时间预算上限（per-run 双维度；token 计数走 loop hook + TraceRecorder token 字段；config 新段 `subagents.budget`）
- [ ] 2.2 超限硬 kill（token 超限 loop 内抛 BudgetExceededError 自终止 + 时间超限 manager monitor task.cancel，两条路径均先落快照）+ `budget_exceeded` 终态 + 失败/成本摘要
- [ ] 2.3 并发/深度护栏（max_concurrent_runs=4 / max_depth=3，spawn 前置守卫，拒绝不产生 run 记录）
- [ ] 2.4 单元测试：预算硬 kill、护栏拒绝

## 3. 消息总线

- [ ] 3.1 多子 agent 间轻量消息总线（bounded/可丢弃/摘要化）
- [ ] 3.2 严格 token 预算防上下文爆炸
- [ ] 3.3 集成测试：多子 agent 交换摘要

## 4. 编排模式库

- [ ] 4.1 OrcPattern 抽象接口
- [ ] 4.2 orchestrator-worker 模式
- [ ] 4.3 peer-review 模式
- [ ] 4.4 hierarchical 模式（依赖 2.0 嵌套 spawn）
- [ ] 4.5 竞标模式
- [ ] 4.6 集成测试：竞标模式端到端

## 5. 收尾

- [ ] 5.1 OpenSpec spec 同步
- [ ] 5.2 全量 pytest + openspec validate + artifact checker
- [ ] 5.3 benchmark 量化（预算方差、快照恢复、模式对比完成率/成本）

## 8. 收尾校验（checker 要求项）

- [x] 8.1 pre-implementation batch-grill-me 或等价设计审阅任务（独立 subagent 已产出 `reviews/grill-design.md`）
- [ ] 8.2 benchmark smoke verification（coding-agent core change 要求）
- [ ] 8.3 当前规格同步：把 spec delta 合并到 `openspec/specs/<capability>/spec.md`
