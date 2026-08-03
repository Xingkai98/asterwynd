# Building Review: multi-agent-collaboration (Round 3)

## Reviewer
- run id: building-review-subagent-round3-2026-08-03
- 时间: 2026-08-03
- 审阅范围: `git diff origin/master...HEAD`（4 个提交：904cbe0 grill 证据 → 2a1766e 实现 → 9091e86 Round 1 修复 → c8c6727 Round 2 修复）

## Verdict
PASS

## Round 2 Issue Verification

- **N1 peer-review max_rounds 回退路径缺回归测试** ✅ fixed + 回归测试真实有效。
  新增 `test_peer_review_max_rounds_falls_back_to_real_runs`（tests/agent/subagent/test_patterns.py:106-131）：`ScriptedLLM` 全 CRITIQUE（"draft v1"→"CRITIQUE needs work"→"draft v2"→"CRITIQUE still needs work"）+ `params={"max_rounds": 2}`。代码路径追踪确认**确实到达回退路径**：`PeerReviewPattern.run`（agent/subagent/patterns.py:117-149）两次迭代 review_text 均非 APPROVED，`range(2)` 耗尽后落入 `real_runs = [last_produced, last_review]`（patterns.py:147-149）聚合两个真实 run，无合成条目。断言与回退语义一一对应：
  - `result["completed"] == 2`（producer + reviewer 各一次真实 run）；
  - 每个 worker `status == "completed"` 且 `summary` 不含 `"reached max review rounds"`（可捕获旧 M4 合成摘要行为）；
  - 每个 worker `subagent_id in manager._sessions`（证明聚合来自真实 session run，非构造条目）。
  独立运行 `pytest tests/agent/subagent/test_patterns.py::test_peer_review_max_rounds_falls_back_to_real_runs -v` → **PASSED**。修复提交 c8c6727 只新增该测试 + 更新 tasks.md（6.2）/review 文档，无生产代码改动，无新副作用。

## Tasks Verification

- **0.1 grill 设计** ✅ `reviews/grill-design.md` 存在，`## Confirmed Decisions` 5 条决策（D1/D3/D5/D7/D4）+ 5 个必须修改项已整合进 design.md，满足 checker ≥3 条机械要求。
- **0.2 Reference Implementation Research** ✅ design.md `## Reference Implementation Research` 含 status=enabled/reason/questions/findings（Claude Code/Codex/LangGraph/crewAI/AutoGen/OpenAI Swarm 对比）/design impact，实质内容非占位。
- **1.1 状态快照** ✅ snapshot.py:46-73 `snapshot_for_run` 构建 SessionSnapshot（objective/blockers/next_steps/bus_summary）→ `SubagentSnapshotStore.for_workspace` 落盘 `<workspace_root>/.asterwynd/subagents/<run_id>/`；触发点 cancel/预算 kill/异常前 `_write_checkpoint`（manager.py:621-643）。
- **1.2 恢复** ✅ `resume_subagent`（manager.py:242-296）加载快照 → `_launch_run(resume_snapshot=...)` → loop.run 已有 resume 路径；测试 `test_cancel_writes_checkpoint_and_resume_completes`（test_budget_snapshot.py:266-292）覆盖取消后 resume 到 completed。
- **1.3 复用 SessionStore 纪律** ✅ `SubagentSnapshotStore` 包装 `SessionStore`（snapshot.py:27-44），复用 schema_version/fingerprint/dedup 原子写。
- **1.4 快照序列化/恢复单测** ✅ `test_snapshot_store_roundtrip` + `test_snapshot_store_missing_returns_none`（test_budget_snapshot.py:214-248）。
- **2.0 嵌套 spawn 前置** ✅ `_build_subagent_loop` 设 `expose_subagent_tools=True`（manager.py:536）；depth contextvar（context.py:24-37）；`_launch_run` set/reset（manager.py:340-346）；测试 `test_depth_context_propagates_to_child_run` + `test_build_subagent_loop_exposes_subagent_tools`（test_guardrails.py:48-84）。
- **2.1 per-run token/时间预算** ✅ `BudgetTracker/BudgetHook`（budget.py）；config `subagents.budget`（config.py:244-262, 1290-1322 + 解析 1293-1312）；per-run 覆盖（manager.py:224-237）；config 解析/默认/非法值三测试（test_config.py:114-150）。
- **2.2 超限硬 kill** ✅ token 路径 `BudgetHook.after_llm_call` 抛 `BudgetExceededError`（budget.py:86-94）→ `_execute_run` 捕获写快照 + `_mark_budget_exceeded`（manager.py:457-461）；时间路径 `_monitor_run_timeout` 先标 `_budget_kill_reason` + 落快照再 cancel（manager.py:645-666）。两条路径均先落快照。测试 test_token_budget_exceeded_marks_budget_exceeded / test_time_budget_exceeded_marks_budget_exceeded / 两路径 kill 均写 checkpoint。
- **2.3 并发/深度护栏** ✅ `_check_guardrails`（manager.py:714-732）在 `_new_run` 前调用（run_subagent:222 / resume_subagent:266），拒绝不产生 run 记录；测试 `test_depth_guard_rejects_without_run_record`（test_guardrails.py:109-130）断言 session.runs == []，另有 concurrency overflow 与活跃计数语义测试。
- **2.4 预算/护栏单测** ✅ test_budget_snapshot.py + test_guardrails.py 覆盖 token/time kill、护栏拒绝、depth 传播、并发计数。
- **3.1 消息总线** ✅ `MessageBus`（bus.py）bounded/drop-oldest/TTL/摘要化；contextvar 接线（context.py:40-49）；PublishBusMessage/ReadBus 工具（subagents.py:181-280）。
- **3.2 token 预算** ✅ 三层：bounded（bus.py:78-80）、发布方摘要化（subagents.py:203-213 + LLMSummarizer 回退截断）、消费端 token 窗口（bus.py:92-125）。
- **3.3 集成测试** ✅ `test_bus_tools_publish_and_read`（test_patterns.py:166-179）+ test_bus.py 10 个单测（roundtrip/drop-oldest/token 窗口/单条超窗/ttl/summary/截断/token 估算）。
- **4.1 OrcPattern 抽象** ✅ patterns.py:38-97。
- **4.2 orchestrator-worker** ✅ patterns.py:100-111；测试 test_orchestrator_worker_aggregates + test_worker_failure_not_fail_fast。
- **4.3 peer-review** ✅ patterns.py:114-149；审批路径 + 迭代路径 + **max_rounds 回退路径**三测试（test_patterns.py:83-131）。
- **4.4 hierarchical** ✅ patterns.py:152-164（依赖 2.0 嵌套 spawn，manager 已开 expose_subagent_tools）。
- **4.5 竞标** ✅ patterns.py:167-200，selector 输入走紧凑摘要拼接非总线（design D6 要求）；测试 test_bidding_selects_best。
- **4.6 竞标 e2e** ✅ test_bidding_selects_best + test_worker_failure_not_fail_fast（test_patterns.py:106-148）+ test_run_pattern_tool。
- **5.1 spec 同步** ✅ spec delta 已合并 `openspec/specs/multi-agent-collaboration/spec.md`（5 ADDED + 1 MODIFIED requirement）；`workflow-events.jsonl` 有 `current_spec_synced` 结构化事件（含 reason，approved_by=human）。
- **5.2 全量验证** ✅ 独立复跑（见 Test Results）；`openspec validate --all --strict` 28/0 通过。
- **5.3 benchmark** ✅ `benchmarks/tasks/asterwynd-022-collaborative-context-audit/`（issue.md/task.json），test_command 机械可查（grep 'summarizer' + 'compact'），problem_statement 要求真实反映当前 commit 代码。
- **6.1/6.2 Round 1/2 修复** ✅ M1/M2/M3/M5/M6 回归测试已确认（Round 2）；N1 回归测试本轮确认真实有效且通过。
- **8.1/8.2/8.3** ✅ grill 证据存在、benchmark task 加载、spec 已同步。

## New Issues

- 无未解决中等以上问题。Round 2 → Round 3 唯一代码变更（c8c6727）是 N1 回归测试的纯新增，未引入任何副作用。
- 复核 8 维度：
  - **正确性**：预算两条 kill 路径先落快照再标终态；`_mark_cancelled`/`_mark_budget_exceeded` 对非 running 终态 no-op（manager.py:583-584, 600-601），无双重标记；`_monitor_run_timeout` cancel 前设 `_budget_kill_reason`，cancelled-handler 正确归为 budget_exceeded；护栏纯前置守卫（拒绝不产生 run 记录）。竞标 selector 走摘要拼接（防 drop-oldest 丢关键 proposal）符合 D6。
  - **Spec 对齐**：change spec delta 5 ADDED + 1 MODIFIED 与 `openspec/specs/` 合入后一致；"reuse agent/workflow/ persistence discipline（非阶段机器）"措辞已按 grill 修正落实（spec + design D1 + snapshot.py 复用 SessionStore）。
  - **冗余度**：patterns.py 无死代码（M4 history 已清理）；snapshot.py 全函数被调用；无重复工具面。
  - **安全性**：全部 4 个新工具（PublishBusMessage/ReadBus/ResumeSubagent/RunPattern）`read_only=True` + `SUBAGENT_CONTROL_PERMISSION`；bus 无活跃实例时返回显式 error 而非异常；`_summarize` LLM 失败回退截断，无越权/注入面。
  - **可维护性**：模块化清晰（budget/bus/snapshot/patterns/context 各司其职），docstring 完整；config 段有类型校验与 fail-fast 测试。
  - **CI 完整性**：OpenSpec validate 28/0；artifact checker 仅报 review manifest 缺失（PASS 后由 review-loop 生成的预期状态）。
  - **测试覆盖**：target 范围 95 passed；加既有回归（test_subagent_manager/test_protocol/test_loop）157 passed。

## Test Results

- `tests/agent/subagent/` + `tests/agent/test_config.py`：**95 passed**
- 追加既有回归 `tests/agent/subagent/test_subagent_manager.py` + `test_protocol.py` + `tests/agent/test_loop.py`：**157 passed（合计）**
- N1 回归用例独立运行 `test_peer_review_max_rounds_falls_back_to_real_runs`：**PASSED**
- `npx @fission-ai/openspec@1.4.1 validate --all --strict`：**28 passed / 0 failed**
- `scripts/check_openspec_artifacts.py`：仅报 review manifest 缺失（`reviews/building-review-manifest.json`），属 PASS 后生成项，非本报告职责。
- 已知环境失败（与本 change 无关，Round 2 已标注）：tree-sitter java/kotlin grammar 缺失、benchmark-gate p95 时序 flake。

## 结论

N1 已确认修复：新增回归测试真实到达 peer-review max_rounds 回退路径、断言聚合 workers 均为真实 session run 且无合成摘要，独立运行与全量均通过；Round 2 → Round 3 无生产代码变更，无新副作用。完整重审 8 维度无未解决中等以上问题，tasks 全部 `[x]` 均有真实实现，spec 已同步且 OpenSpec validate 通过。前两轮全部 issue（M1-M6 + N1）均已修复并有有效回归测试。达到 PASS 标准，可以生成 review manifest。
