# Tasks: benchmark 三模式与 workflow 可重放

## 0. 设计追问（实现前门禁）

- [x] 0.1 跑 `batch-grill-me`（或等价设计追问）审视 design.md D1–D6，产出 `reviews/grill-design.md`（≥3 Confirmed Decisions + Open Questions 停轮确认）。

## 1. 三模式运行模型

- [x] 1.1 `benchmarks/workflow_replay.py`：`workflow_record.json` 落盘/读取（record 旁路采集 + replay 离线重放）。schema 为**一任务一文件、顶层 `workflows` 列表**（grill Q1 写法 B）；只记录真正 `run()` 过的图；`collection_status` 区分 `ok`/`no_workflow`/`failed`。
- [x] 1.2 BenchmarkRunner 增 workflow 模式分派（template / dynamic-record / dynamic-replay）。接线走 CLI 标志 `--workflow-mode` + `--workflow-record <run-dir>`，透传到 `AsterwyndRunner` 构造参数（`AgentRunner.run` 签名不动，grill Q8 推荐）。template 采用读法 1（pattern 当被测编排，`problem_statement` 作 `compile_pattern` 的 task，走既有 verifier）。
- [x] 1.3 dynamic-record 保存规范化记录（spec + spec_hash + scheduler_version + budget_config + seed/model/temperature）；dynamic-replay 不重跑规划模型。

## 2. 报告字段

- [x] 2.0 **给 `AsterwyndRunner` 注入 `CostLedger` 并透传到 `SubAgentManager`**——benchmark 路径今天没挂 ledger（`benchmarks/agent_runner.py:312-318` / `manager.py:345,358`），不修则 `workflow_cost_usd` 与 envelope `total_cost` 恒为 0（grill Confirmed Decision 14）。
- [x] 2.1 `TaskResult` 与 `AgentRunResult` **成对**增 workflow_* 字段（mode/spec_hash/scheduler_version/node_count/run_count/peak_active/queue_wait_s/critical_path_s/workflow_cost_usd），全部默认 `None`（另三个 runner 不建 manager，无默认值会构造失败）；`runner.py` 的 3 处 `TaskResult(...)` 完整重建点（`:377-398`、`:446-468`、`:530-552`）必须同步带上，否则字段被静默丢弃。
- [x] 2.2 AsterwyndRunner 从 scheduler/manager envelope 采集字段；scheduler 新暴露 `run_count` 与 workflow 级 `spawn_count` 快照（须在 `run()` finally 的 `release_workflow_bucket` 之前取值），`queue_wait_s` 在 scheduler 内由 `_run_refs` 零新字段算出。
- [x] 2.3 report.py 渲染 workflow 字段段。

## 3. 编排指标

- [x] 3.1 冗余度 = 有用产出 / spawn 总数（消费口径：`_collect_slots` 合并时打标被消费的 run，terminal 进 root result 亦算消费；分母用 workflow 级 spawn_count 快照，为 0 时记 None）。口径以 grill Q2 推荐为准，不写成 D4 原文的「或」双条件。
- [x] 3.2 图级步数 = 调度器 steps。
- [x] 3.3 拒绝降级计数（queue_full + 深度撤工具 + spawn 拒绝 + 图级超限）。四类里三类今天无现成信号，需在 manager/scheduler 既有分支加计数器（instrumentation，非新执行路径）：depth_capped_runs 计在 `manager._build_subagent_loop` 的 `depth >= max_depth` 分支（`manager.py:1136-1137`）并挂 workflow 桶；queue_full 在 scheduler `:1553-1563` 落账（workflow 内预期恒 0，须诚实报 0）；spawn 预算拒绝在 `_check_spawn_budget`（`manager.py:1453-1457`）自增。`queue_cancelled_runs` **单列、不并入**本总量。
- [x] 3.4 report.py 渲染编排指标段（粒度待 grill Q9 拍板：推荐独立 section + 主表加一列 workflow_mode）。

## 4. 比较口径

- [x] 4.1 compare/统计从 pass rate 扩展为：完成率 + 总 token + $/resolved-task + wall time + 节点数 + 峰值并发 + 关键路径 + 失败原因。`$/resolved-task` 分母复用 `PASS_STATUSES`（`benchmarks/report.py:36`）+ `is_valid_round`（`benchmarks/statistics.py:60-71`），不得自造（grill Confirmed Decision 9）。新增字段按 compare.py 的 raw-dict 宽松读风格。
- [x] 4.2 对照臂「小 k 高质量 vs 大 N 暴力」（`SubagentsConfig.max_active`/`max_spawns`，`agent/config.py:336-338`；通道用两份 config YAML，grill Q5 推荐通道 X；大 N 臂的 spawn budget exceeded 属预期压力结果，报告须标注）。

## 5. 端到端 fan-out 验证

- [x] 5.1 真实 LLM fan-out benchmark 验证任务（record → replay 可比性断言）。断言口径按 grill Q6：fake 场景全等（spec_hash/node_count/run_count/status），真实 LLM 只硬断言 spec_hash 相等 + 无异常完成。
- [x] 5.2 降级策略：真实 LLM 不可用时 fake round-trip + 在 `result.json` 记机器可读未验证事实（`e2e_llm_verified: false` / `e2e_verification_mode` / `e2e_skip_reason` / `e2e_assertions`），字段加进 `TaskResult`（非只在报告拼串）。

## 6. 测试与收尾

- [x] 6.1 新增三模式 round-trip、报告字段渲染、编排指标、replay 确定性测试。
- [x] 6.2 兼容回归：既有无 workflow 的 benchmark 任务字段为 None、报告不崩。
- [x] 6.3 benchmark smoke：`uv run asterwynd benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/smoke` 冒烟通过。
- [x] 6.4 同步 current spec：把 spec delta 合入 `openspec/specs/benchmark/spec.md`。（grill Q9 渲染粒度与 Q10 replay 判分边界两条 scenario 已按用户确认回写进 spec delta。）
- [x] 6.5 `uv run pytest -q` 全绿；OpenSpec validate + artifact checker 通过。
