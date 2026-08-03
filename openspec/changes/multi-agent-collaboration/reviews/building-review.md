# Building Review: multi-agent-collaboration

## Reviewer
- run id: building-review-subagent-2026-08-03
- 时间: 2026-08-03

## Verdict
CHANGES_REQUESTED

## Tasks Verification

- **0.1 grill 设计**: ✅ `reviews/grill-design.md` 存在，`## Confirmed Decisions` 含 5 条决策（D1/D3/D5/D7/D4），open questions 均给出推荐答案，满足 checker 的 ≥3 条决策机械要求。
- **0.2 Reference Implementation Research**: ✅ `design.md` `## Reference Implementation Research` 有 status/reason/questions/findings/design impact，内容实质（Claude Code/Codex/LangGraph/crewAI/Swarm 对比），非占位。
- **1.1 状态快照**: ✅ `agent/subagent/snapshot.py:47-64` `snapshot_for_run` 构建 `SessionSnapshot`（含新增 objective/blockers/next_steps），经 `SubagentSnapshotStore.for_workspace` 落盘 `<workspace_root>/.asterwynd/subagents/<run_id>/`（snapshot.py:30-33）；`agent/session.py:29-35` 扩展 SessionSnapshot 字段。key 用完整 run_id（manager.py:615, snapshot.py:51 `session_id=run.run_id`）。触发点：cancel/预算 kill/异常前 `_write_checkpoint`（manager.py:607-620）。
- **1.2 恢复**: ✅ `resume_subagent`（manager.py:237-291）加载快照 → `_launch_run(resume_snapshot=...)` → 走 `loop.run` 已有 resume 路径（loop.py:535-554，重建 transcript + resume marker + 续接消息）。测试 test_cancel_writes_checkpoint_and_resume_completes 覆盖取消后 resume 到 completed。
- **1.3 复用 SessionStore 纪律**: ✅ `SubagentSnapshotStore` 包装 `SessionStore`（snapshot.py:16-29），复用 schema_version 兼容检查、dedup hash、原子 tmp+replace 写入（session.py:83-98, 200-215）。
- **1.4 快照序列化/恢复单测**: ✅ `tests/agent/subagent/test_budget_snapshot.py:153-186` roundtrip + missing→None。
- **2.0 嵌套 spawn 前置**: ✅ `_build_subagent_loop` 设 `expose_subagent_tools=True`（manager.py:528）；`agent/subagent/context.py` spawn_depth contextvar；`_launch_run` set/reset depth（manager.py:335-341）。测试 test_depth_context_propagates_to_child_run。
- **2.1 per-run token/时间预算**: ✅ `BudgetTracker/BudgetHook`（budget.py），config 段 `subagents.budget`（config.py:1293-1312），per-run 覆盖（manager.py:219-233）。
- **2.2 超限硬 kill**: ✅ 两条路径：token 超限 loop 内 `BudgetHook.after_llm_call` 抛 `BudgetExceededError`（budget.py:94-98）→ `_execute_run` 捕获写快照+标 `budget_exceeded`（manager.py:452-454）；时间超限 `_monitor_run_timeout` cancel（manager.py:622-643，cancel 前 `_budget_kill_reason`+快照）。测试 test_token_budget_exceeded_marks_budget_exceeded / test_time_budget_exceeded_marks_budget_exceeded。详见 Issues（M1：usage 未回填）。
- **2.3 并发/深度护栏**: ✅ `_check_guardrails`（manager.py:691-709）在 `_new_run` 前调用（run_subagent:217 / resume_subagent:261），拒绝不产生 run 记录。测试 test_depth_guard_rejects_without_run_record。
- **2.4 预算/护栏单测**: ✅ test_budget_snapshot.py + test_guardrails.py 覆盖 token/time kill、护栏拒绝、depth 传播。
- **3.1 消息总线**: ✅ `MessageBus`（bus.py）bounded/drop-oldest/TTL/摘要化，contextvar 接线（context.py:32-35），PublishBusMessage/ReadBus 工具（subagents.py:182-274）。
- **3.2 token 预算**: ✅ 三层：bounded 队列（bus.py:59-61）、发布方摘要化（subagents.py:218-226）、消费端 token 窗口（bus.py:88-99）。测试 test_read_token_window_keeps_most_recent 等。
- **3.3 集成测试**: ✅ test_bus_tools_publish_and_read（subagents 工具层交换摘要）。
- **4.1 OrcPattern 抽象**: ✅ `OrcPattern`（patterns.py:22-91）。
- **4.2 orchestrator-worker**: ✅ patterns.py:93-102，测试 test_orchestrator_worker_aggregates。
- **4.3 peer-review**: ✅ patterns.py:113-161，测试 test_peer_review_approves_first_round / critique_loop。见 Issues（M4 合成条目）。
- **4.4 hierarchical**: ✅ patterns.py:164-176（依赖嵌套 spawn，manager 层已开 expose_subagent_tools）。
- **4.5 竞标**: ✅ patterns.py:179-212，selector 输入走摘要拼接非总线（设计 D6 要求）。测试 test_bidding_selects_best。
- **4.6 竞标 e2e**: ✅ test_bidding_selects_best + test_worker_failure_not_fail_fast。
- **5.1 spec 同步**: ✅ spec delta 已合并 `openspec/specs/multi-agent-collaboration/spec.md`（6 requirements），`workflow-events.jsonl` 有 `current_spec_synced` 结构化事件。
- **5.2 全量验证**: ✅ 独立复跑全量 `tests/`（忽略 tree-sitter）1753 passed / 7 skipped；`openspec validate --all --strict` 28/0 通过。
- **5.3 benchmark**: ✅ `benchmarks/tasks/asterwynd-022-collaborative-context-audit/` 新增（issue.md/task.json），协作上下文审计任务，test_command 机械可查。
- **8.1/8.2/8.3**: ✅ grill 证据存在、benchmark task 加载、spec 已同步。

## Issues

- **中 M1: 预算超限 run 的 cost summary usage 为全 0**（`agent/subagent/manager.py:584-598`）。`_mark_budget_exceeded` 只写 status/reason/finished_at/trace，未回填 `run.usage`；`BudgetExceededError.used/limit` 也只在 except 分支提取 dimension（manager.py:452-454）。实测 token kill（100 budget，两轮各 60 tokens）后 envelope `usage={total_tokens:0,...}`，与真实消耗 120 tokens 不符。成本数据仅在 trace 的 iteration step `data.input_tokens/output_tokens`（已实测 30/30 存在）和 CostLedger 可查，但 spec 要求 "SHALL generate failure/cost summaries" 的返回 envelope 字段不准确。建议 kill 时从 tracker 回填 `run.usage.total_tokens`（或存 `BudgetExceededError.used`）。
- **中 M2: 设计 D5 的"快照记录总线摘要"未实现**（`agent/subagent/snapshot.py:47-64`）。design.md Decision 5 与风险项要求"每次 bus 写后同步维护紧凑 bus 摘要字段"，防恢复后缺上下文；但 `snapshot_for_run` 只写 SessionSnapshot 字段，无任何 bus 摘要；`_write_checkpoint` 也拿不到当前 bus。`run_pattern` 只在 result envelope 里放 `bus.snapshot_payload()`（patterns.py:244），不落快照。实际影响有限（bus 不跨 run 持久化、编排级 resume 未实现），但属 design 已声明的降级点。若保留该语义，建议在 snapshot 增加可选 `bus_summary` 字段并在 kill 前写入。
- **低 M3: 快照 created_at/updated_at 恒为空字符串**（`agent/subagent/snapshot.py:51-52`）。`run.created_at` 是 float（time.time），`hasattr(float, "isoformat")` 恒 False → 两个字段均为 ""；SessionStore.save 会覆盖 updated_at，created_at 永远为空。不影响恢复，属数据完整性小瑕疵。
- **低 M4: peer-review 达 max_rounds 时聚合含非真实 run 记录**（`agent/subagent/patterns.py:158-161`）。`results` 手工构造 `{"subagent_id": producer, "status": "completed", "summary": "reached max review rounds"}`，不是 session.runs 里的真实 run；`completed` 计数因此虚报（2 = 1 合成 + 1 reviewer，实际 producer/reviewer 各跑 max_rounds 次）。`history` 列表（patterns.py:122-141）只写不读，属死代码。
- **低 M5: bus.read() 当最新单条消息超 token 窗口时返回空**（`agent/subagent/bus.py:94-97`）。`if used + msg.token_count > budget: break` 在第一条（最新）就超预算时立即 break 返回 []。调用方传 `max_tokens < 单条 token_count` 时读不到任何消息。可考虑至少保留最新一条。
- **低 M6: 测试断言未覆盖新工具注册**（`tests/agent/subagent/test_guardrails.py:48-54`）。`test_build_subagent_loop_exposes_subagent_tools` 只断言 CreateSubagent/RunSubagent/ListSubagents 三个旧工具，未断言 PublishBusMessage/ReadBus/ResumeSubagent/RunPattern 在子代理 loop 中已注册（实现位于 loop.py:345-348，是正确接线，仅测试覆盖不足）。

## Test Results

- `tests/agent/subagent/`（含新增 test_budget_snapshot/test_bus/test_guardrails/test_patterns）: 51 passed
- `tests/agent/test_config.py`: 39 passed
- 既有回归 `tests/agent/subagent/test_subagent_manager.py` + `test_protocol.py` + `tests/agent/test_loop.py`: 76 passed
- 全量 `tests/`（--ignore=tree-sitter）: **1753 passed, 7 skipped**（含 test_background.py::test_task_output_truncated，本次通过）
- `npx @fission-ai/openspec@1.4.1 validate --all --strict`: 28 passed / 0 failed

## 结论

实现覆盖面完整：tasks.md 全部 `[x]` 均有真实实现，测试全绿（全量 1753 passed），OpenSpec validate 通过，5 大块（快照/预算/总线/模式/护栏）的 spec 要求均有对应代码与测试。核心正确性点（depth token save/reset、BudgetExceededError 自终止、time monitor 与 cancel 竞态、resume 消息重建、护栏前置守卫、bus contextvar finally、竞标 selector 走摘要）均经代码核对与实测确认无误，无阻塞性缺陷与安全问题。

CHANGES_REQUESTED 的依据是 M1（预算超限 run 的 cost summary usage 全 0，与 spec "failure/cost summary" 要求不符）与 M2（design D5 声明的快照总线摘要桥接未实现）。两者均为小改动可修、不阻塞整体功能；修复后即可进入下一轮。
