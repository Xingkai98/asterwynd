# Tasks: 多Agent协作做深

## 0. 前置决策

- [ ] 0.1 grill 设计（wayfinder:grilling 标签，明确复用 `agent/workflow/` 与两个 scope）
- [ ] 0.2 Reference Implementation Research 实质调研（Claude Code/Codex/LangGraph/crewAI/Swarm）

## 1. 状态快照与恢复

- [ ] 1.1 子 agent 中断 → JSON 快照（迭代/工具状态/对话）
- [ ] 1.2 恢复时从断点继续
- [ ] 1.3 复用 SessionStore 的 schema_version/fingerprint/dedup 模式
- [ ] 1.4 单元测试：快照序列化/恢复

## 2. 成本控制

- [ ] 2.1 每子 agent token/时间预算上限
- [ ] 2.2 超限硬 kill（真正终止后台任务）+ 失败/成本摘要
- [ ] 2.3 单元测试：预算硬 kill

## 3. 消息总线

- [ ] 3.1 多子 agent 间轻量消息总线（bounded/可丢弃/摘要化）
- [ ] 3.2 严格 token 预算防上下文爆炸
- [ ] 3.3 集成测试：多子 agent 交换摘要

## 4. 编排模式库

- [ ] 4.1 OrcPattern 抽象接口
- [ ] 4.2 orchestrator-worker 模式
- [ ] 4.3 peer-review 模式
- [ ] 4.4 hierarchical 模式
- [ ] 4.5 竞标模式
- [ ] 4.6 集成测试：竞标模式端到端

## 5. 收尾

- [ ] 5.1 OpenSpec spec 同步
- [ ] 5.2 全量 pytest + openspec validate + artifact checker
- [ ] 5.3 benchmark 量化（预算方差、快照恢复、模式对比完成率/成本）

## 8. 收尾校验（checker 要求项）

- [ ] 8.1 pre-implementation grill-with-docs 或等价设计审阅任务（进入 building 前）
- [ ] 8.2 benchmark smoke verification（coding-agent core change 要求）
- [ ] 8.3 当前规格同步：把 spec delta 合并到 `openspec/specs/<capability>/spec.md`
