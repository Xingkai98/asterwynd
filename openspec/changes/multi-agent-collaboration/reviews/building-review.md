# Building Review: multi-agent-collaboration (Round 2)

## Reviewer
- run id: building-review-subagent-round2-2026-08-03
- 时间: 2026-08-03

## Verdict
CHANGES_REQUESTED

## Round 1 Issues Verification

- **M1 预算超限 run 的 usage 全 0** ✅ fixed + 回归测试。
  `_execute_run` 两条 kill 路径均向 `_mark_budget_exceeded` 传 `tokens=tracker.tokens`（`agent/subagent/manager.py:457-461` token 路径、`:464-468` 时间路径）；`_mark_budget_exceeded` 新增 `tokens` 参数并在 `if tokens:` 时回填 `run.usage = SubagentRunUsage(total_tokens=tokens, input_tokens=0, output_tokens=0)`（manager.py:592-610）。回归测试 `test_budget_kill_backfills_usage_in_envelope`（tests/agent/subagent/test_budget_snapshot.py:112-124）断言 token kill 后 envelope `usage.total_tokens >= 100`（实测 120 = 两轮各 60），可区分旧全 0 行为。说明：input/output 置 0 是合理近似——`BudgetTracker` 只累计总和（budget.py:57-58），未分维度；total_tokens 是成本归因的关键字段，不影响 spec "failure/cost summary" 语义。
- **M2 快照无总线摘要** ✅ fixed + 回归测试。
  `SessionSnapshot` 加 `bus_summary: str = ""`（agent/session.py:38，to_dict `:56`、from_dict `:77` 均透传）；`snapshot_for_run` 接受 `bus_summary` 参数（agent/subagent/snapshot.py:50,72）；`_write_checkpoint` 从 `current_bus()` 取 bus 写 `bus.compact_summary()`（manager.py:632-638，design D5 落实）。回归测试 `test_checkpoint_includes_bus_summary`（tests/agent/subagent/test_budget_snapshot.py:128-168）验证：空 bus → `bus_summary == ""`；发布消息后 kill → 快照含 `[w1/finding]`。**dedup hash 影响核查**：`SessionStore.save` 的 dedup hash 覆盖 to_dict 全字段（session.py:92-102），bus_summary 加入 hash 输入；同一 run 两次 `_write_checkpoint`（时间 kill 路径 monitor + cancel handler）bus 状态不变 → hash 相同 → 第二次 dedup 跳过，无重复写、无破坏；`from_dict` 用 `data.get("bus_summary","")` 兼容旧快照，schema 仍 v1.0，向后兼容。结论：不破坏 dedup。
- **M3 快照 created_at 恒空串** ✅ fixed + 回归测试。
  `snapshot_for_run` 用 `datetime.fromtimestamp(run.created_at, tz=timezone.utc).isoformat()`（snapshot.py:53-57），`run.created_at` 是 float（manager.py:62 default_factory=time.time），不再走失效的 `hasattr(float,"isoformat")` 分支。回归测试 `test_snapshot_created_at_not_empty`（tests/agent/subagent/test_budget_snapshot.py:251-259）断言非空且含 ISO "T" 分隔符。
- **M4 peer-review 合成条目 + history 死代码** ⚠️ 代码已修复，**缺 max_rounds 回退路径的回归测试**。
  代码层面修复真实存在：移除 `history` 只写不读死代码与合成条目，改为 `last_produced/last_review` 累计并在 max_rounds 达限后用真实 final runs 聚合（agent/subagent/patterns.py:122-149），`_aggregate` 只接真实 run dict。审查确认新逻辑正确：producer 任一迭代失败即提前返回；fallthrough 时 last_produced/last_review 必为已完成真实 run。**问题**：现有测试 `test_peer_review_approves_first_round` / `test_peer_review_critique_loop_until_approved`（tests/agent/subagent/test_patterns.py:83-102）只覆盖审批路径（改 `{**produced,"status":"completed"}` → `[produced, review]` 是行为保持的），**没有任何测试到达 max_rounds 达限回退**（全测试套件 grep `max_rounds`/`reached max review` 仅在旧审阅报告出现）。M4 是 bug fix，AGENTS.md 要求"每个 bug fix 必须新增回归测试"，此条未满足。建议补一个 ScriptedLLM 全 CRITIQUE + `max_rounds=2` 的测试，断言聚合 `workers` 均来自 session.runs 的真实 subagent_id 且无 `"reached max review rounds"` 摘要。
- **M5 bus.read 最新单条超窗口返回空** ✅ fixed + 回归测试。
  `read()` 在首条超预算且 `not collected` 时先追加该条再 break（agent/subagent/bus.py:114-118），保证消费端至少看到最新状态。回归测试 `test_read_returns_newest_when_single_message_exceeds_window`（tests/agent/subagent/test_bus.py:43-50）断言 400 字符消息（~100 tokens）在 10-token 窗口下仍返回 1 条。逻辑核查：over-budget 分支直接 break，`used` 不累计、`limit` 不二次判定，均无影响。
- **M6 新工具注册断言缺失** ✅ fixed。
  `test_build_subagent_loop_exposes_subagent_tools`（tests/agent/subagent/test_guardrails.py:48-64）从 3 个旧工具扩展到 10 个，含 PublishBusMessage/ReadBus/ResumeSubagent/RunPattern。实现侧 `_ensure_subagent_tools_registered` 确实注册全部 10 工具（agent/loop.py:339-348），断言与实现一致。

## Tasks Verification

- **0.1 grill 设计** ✅ `reviews/grill-design.md` 存在，`## Confirmed Decisions` 5 条决策（D1/D3/D5/D7/D4）+ open questions 推荐答案，满足 checker ≥3 条机械要求。
- **0.2 Reference Implementation Research** ✅ design.md `## Reference Implementation Research` 含 status/reason/questions/findings/design impact，实质内容（Claude Code/Codex/LangGraph/crewAI/Swarm/OpenAI Swarm 对比），非占位。
- **1.1 状态快照** ✅ snapshot.py:46-73 `snapshot_for_run` 构建 SessionSnapshot（objective/blockers/next_steps/bus_summary）→ `SubagentSnapshotStore.for_workspace` 落盘 `<workspace_root>/.asterwynd/subagents/<run_id>/`（snapshot.py:34-35, session_id=run.run_id）；触发点 cancel/预算 kill/异常前 `_write_checkpoint`（manager.py:621-643）。
- **1.2 恢复** ✅ `resume_subagent`（manager.py:242-296）加载快照 → `_launch_run(resume_snapshot=...)` → loop.run 已有 resume 路径。测试 `test_cancel_writes_checkpoint_and_resume_completes`（test_budget_snapshot.py:266-292）覆盖取消后 resume 到 completed。
- **1.3 复用 SessionStore 纪律** ✅ `SubagentSnapshotStore` 包装 `SessionStore`（snapshot.py:27-44），复用 schema_version/fingerprint/dedup 原子写（session.py:88-103）。
- **1.4 快照序列化/恢复单测** ✅ `test_snapshot_store_roundtrip` + `test_snapshot_store_missing_returns_none`（test_budget_snapshot.py:214-248），含 bus_summary 往返。
- **2.0 嵌套 spawn 前置** ✅ `_build_subagent_loop` 设 `expose_subagent_tools=True`（manager.py:536）；depth contextvar（context.py:24-37）；`_launch_run` set/reset（manager.py:340-346）。测试 `test_depth_context_propagates_to_child_run`（test_guardrails.py:68-84）。
- **2.1 per-run token/时间预算** ✅ `BudgetTracker/BudgetHook`（budget.py）；config `subagents.budget`（config.py:244-262, 1293-1312）；per-run 覆盖（manager.py:224-237）。
- **2.2 超限硬 kill** ✅ token 路径 `BudgetHook.after_llm_call` 抛 `BudgetExceededError`（budget.py:86-94）→ `_execute_run` 捕获写快照+标 budget_exceeded（manager.py:457-461）；时间路径 `_monitor_run_timeout` cancel 前 `_budget_kill_reason`+快照（manager.py:645-666）。测试 test_token_budget_exceeded_marks_budget_exceeded / test_time_budget_exceeded_marks_budget_exceeded。
- **2.3 并发/深度护栏** ✅ `_check_guardrails`（manager.py:714-732）在 `_new_run` 前调用（run_subagent:222 / resume_subagent:266），拒绝不产生 run 记录。测试 `test_depth_guard_rejects_without_run_record`（test_guardrails.py:109-130）断言 session.runs == []。
- **2.4 预算/护栏单测** ✅ test_budget_snapshot.py + test_guardrails.py 覆盖 token/time kill、护栏拒绝、depth 传播、并发计数。
- **3.1 消息总线** ✅ `MessageBus`（bus.py）bounded/drop-oldest/TTL/摘要化；contextvar 接线（context.py:40-49）；PublishBusMessage/ReadBus 工具（subagents.py:181-280）。
- **3.2 token 预算** ✅ 三层：bounded（bus.py:78-80）、发布方摘要化（subagents.py:203-213）、消费端 token 窗口（bus.py:92-125）。
- **3.3 集成测试** ✅ `test_bus_tools_publish_and_read`（test_patterns.py:166-179）。
- **4.1 OrcPattern 抽象** ✅ patterns.py:38-97。
- **4.2 orchestrator-worker** ✅ patterns.py:100-111，测试 test_orchestrator_worker_aggregates。
- **4.3 peer-review** ✅ patterns.py:114-149，测试审批路径（test_patterns.py:83-102）。**max_rounds 达限路径无测试**（见 M4）。
- **4.4 hierarchical** ✅ patterns.py:152-164（依赖 2.0 嵌套 spawn，manager 层已开 expose_subagent_tools）。
- **4.5 竞标** ✅ patterns.py:167-200，selector 输入走摘要拼接非总线（design D6 要求）。测试 test_bidding_selects_best。
- **4.6 竞标 e2e** ✅ test_bidding_selects_best + test_worker_failure_not_fail_fast（test_patterns.py:106-148）。
- **5.1 spec 同步** ✅ spec delta 已合并 `openspec/specs/multi-agent-collaboration/spec.md`（6 requirements，含新增 Concurrency and Depth Guardrails requirement）；`workflow-events.jsonl` 有 `current_spec_synced` 结构化事件。
- **5.2 全量验证** ✅ 独立复跑全量 `tests/`：1761 passed / 7 skipped，2 failed 均为环境问题（tree-sitter java/kotlin grammar 缺失返回空符号、benchmark-gate p95 延迟 flake——与本 change 无关，详见 Test Results）。`openspec validate --all --strict` 28/0 通过。
- **5.3 benchmark** ✅ `benchmarks/tasks/asterwynd-022-collaborative-context-audit/` 新增（issue.md/task.json），协作上下文审计任务，test_command 机械可查。
- **6.1 Round 1 修复** ⚠️ M1/M2/M3/M5/M6 完成 + 回归测试；M4 代码修复但缺 max_rounds 回退路径回归测试。
- **8.1/8.2/8.3** ✅ grill 证据存在、benchmark task 加载、spec 已同步。

## New Issues

- **中 N1（承接 M4 测试缺口）**: peer-review `max_rounds` 达限回退路径无任何回归测试。`git grep` 全测试套件无 `max_rounds` 参数用例，M4 修复（patterns.py:147-149）的行为只能靠代码审查验证，未来引入合成条目或破坏回退逻辑不会触发任何失败。违反 AGENTS.md "每个 bug fix 必须新增回归测试"。建议：`ScriptedLLM` 全返回 CRITIQUE + `params={"max_rounds": 2}`，断言 `result["workers"]` 的每个 `subagent_id` 都在 session.runs 中、无 `"reached max review rounds"` 摘要、`completed+failed` 与实际 run 一致。
- 其余修复未发现副作用：M1 input/output=0 是 tracker 只累计总和的合理近似；M2 bus_summary 不破坏 dedup 且向后兼容；M5 over-budget 分支与 limit/TTL/topic filter 组合无逻辑问题；M6 断言与实现一一对应。

## Test Results

- `tests/agent/subagent/`（含新增回归）：**55 passed**
- `tests/agent/test_config.py`：**39 passed**
- 既有回归 `tests/agent/subagent/test_subagent_manager.py` + `test_protocol.py` + `tests/agent/test_loop.py`：**76 passed**
- 独立跑 5 个 M1/M2/M3/M5/M6 回归用例：全部 PASSED
- 全量 `tests/`：**1761 passed, 7 skipped, 2 failed**。2 failed 均为环境问题与本 change 无关：
  - `test_tree_sitter_extracts_java_and_kotlin_symbols`：tree-sitter 返回空符号（本机缺 java/kotlin grammar），首轮即按"忽略 tree-sitter"处理。
  - `test_gate_pass_when_matches_baseline`：p95_latency baseline 0.001s vs current 2.0s，纯时序 flake（在跑完 1761 用例的高负载机上复现）。
- `npx @fission-ai/openspec@1.4.1 validate --all --strict`：**28 passed / 0 failed**
- `scripts/check_openspec_artifacts.py`：当前仅报 review manifest 缺失（`reviews/building-review-manifest.json`），属 PASS 后由 review-loop 生成的预期状态，非本报告职责。

## 结论

Round 1 的 6 个 issue 中 5 个（M1/M2/M3/M5/M6）已确认修复且有对应回归测试、无副作用；M4 的代码修复真实且正确，但**未为 max_rounds 达限回退路径新增回归测试**，违反项目"每个 bug fix 必须新增回归测试"规则，也未满足"6 issue 全部修复且有回归测试"的 PASS 标准。这是唯一剩余的中等问题（N1），修复成本极低（一个 ScriptedLLM 用例）。其余维度（任务逐项、Spec 对齐、冗余度、安全性、可维护性、CI）均无未解决中等以上问题，全量测试与 OpenSpec validate 通过。补齐 M4 回归测试后即可 PASS。
