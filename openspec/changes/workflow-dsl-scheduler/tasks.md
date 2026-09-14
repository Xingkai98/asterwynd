# Tasks: Workflow DSL 调度器

## 0. 设计追问（实现前门禁）

- [x] 0.1 跑 `batch-grill-me`（或等价设计追问）审视 design.md D1–D8，产出 `reviews/grill-design.md`（≥3 Confirmed Decisions + Open Questions 停轮确认）。

## 1. WorkflowSpec 数据结构与校验

- [x] 1.1 `agent/subagent/workflow.py`：WorkflowSpec dataclass + 节点/边模型（subagent/aggregate/route/foreach + channel/required）。
- [x] 1.2 schema 校验：非法环、未知节点、重复 id、超 max_nodes、多入边写同槽无 reducer → reject。

## 2. DAG 调度器

- [x] 2.1 `agent/subagent/scheduler.py`：ready 队列 + 依赖门控（required 上游全完成才进 ready）。
- [x] 2.2 复用 C1 的 max_active/max_queued_runs/许可绑执行；node 状态 node_queued/started/blocked/completed/failed。
- [x] 2.3 汇合语义：all_required + best_effort（失败不 fail-fast 只在 aggregate 层）。
- [x] 2.4 图级 recursion_limit（默认 25），超限 GraphRecursionError。

## 3. 节点执行

- [x] 3.1 subagent 节点：调 SubAgentManager run_subagent。
- [x] 3.2 aggregate 节点：多上游汇聚 + reducer 声明。
- [x] 3.3 route 节点：结构化标签/枚举路由 + default + max_routes。
- [x] 3.4 foreach 节点：动态展开 + max 展开数 + 模板化子任务。

## 4. 工具入口

- [x] 4.1 `agent/tools/builtin/subagents.py` 新增 DeclareWorkflow / StartWorkflow / GetWorkflow / CancelWorkflow / RunWorkflow 工具。
- [x] 4.2 RunWorkflow 内部走 Declare+Start；spec 可保存 + 哈希（`spec_hash`）。

## 5. pattern → DSL 模板 + 前置项

- [x] 5.1 4 pattern 编译成 WorkflowSpec 模板（orchestrator-worker/peer-review/hierarchical/bidding）。
- [x] 5.2 `run_pattern()` 兼容 adapter，返回字段兼容 + 新增 workflow_id/workflow_spec_hash/critical_path_s/peak_active/total_cost（Q9：`spec_hash` 改名避免与 OpenSpec artifact hash 冲突）。
- [x] 5.3 前置项（C1 遗留 D8）：累计 spawn 计数改「每 workflow run 复位 + `workflow_id` 计数桶」（grill 决策 7：`root_run_id` 无载体，桶键改用既有 `workflow_id`）。

## 6. 测试与收尾

- [x] 6.1 新增 DSL 校验测试 + 调度器测试（fan-out/join/route/foreach/递归上限）+ pattern 模板映射测试。
- [x] 6.2 适配既有 `test_patterns.py`（返回字段兼容）。
- [x] 6.3 benchmark smoke：`uv run asterwynd benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/smoke` 冒烟通过。
- [ ] 6.4 同步 current spec：把 spec delta 合入 `openspec/specs/multi-agent-collaboration/spec.md`（当前规格 sync 任务）。
- [x] 6.5 `uv run pytest -q` 全绿；OpenSpec validate + artifact checker 通过。
