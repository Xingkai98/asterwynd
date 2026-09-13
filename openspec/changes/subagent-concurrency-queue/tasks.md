# Tasks: subagent 并发队列化

## 0. 设计追问（实现前门禁）

- [ ] 0.1 跑 `batch-grill-me`（或等价设计追问）审视 design.md D1–D7，产出 `reviews/grill-design.md`（≥3 条 Confirmed Decisions + Open Questions 停轮确认）。

## 1. 配置与状态机

- [ ] 1.1 `SubagentsConfig` 增 `max_active=5` / `max_queued_runs=20` / `max_spawns=200`（保留 `max_concurrent_runs` 作兼容别名或迁移），`_parse_subagents_config` 同步解析（`agent/config.py:1334`）。
- [ ] 1.2 `SubagentRunRecord.status` 增加 `queued` 态；`run_subagent` 入队即返回 `queued` + `run_id`。
- [ ] 1.3 `SubagentSessionRecord` 增 `parent_run_id`/`workflow_id`/`node_id`/`depth` 显式字段。

## 2. 队列化并发（D2/D3）

- [ ] 2.1 `_check_guardrails` 拆准入层（仍 fail-fast）与排队层（进 `asyncio.Queue`）。
- [ ] 2.2 实现有界队列：`max_active` 物理并发 + `max_queued_runs` 队列上限，满返回 `queue_full` 信号。
- [ ] 2.3 `_active_tasks` 只记实际执行任务；排队 run 有独立 RunRecord。

## 3. 许可绑执行不绑等待（D1）

- [ ] 3.1 并发许可在 `_execute_run` 调用 `loop.run()` 前 acquire、返回后 release；`run_subagent` 排队/等待路径不持许可。
- [ ] 3.2 回归测试：父等子不自我饥饿（父阻塞等 4 个 worker，4 个全跑完不抛错）。

## 4. 深度撤工具 + 累计计数（D4/D5）

- [ ] 4.1 `_build_subagent_loop` 按 `current_spawn_depth() >= max_depth` 关 `expose_subagent_tools`。
- [ ] 4.2 per-orchestration 累计 spawn 计数（`max_spawns`），超限拒绝。
- [ ] 4.3 保留 `max_depth` 程序性超限 fail-fast（防御性）。

## 5. 工具 parallelizable（D7）

- [ ] 5.1 `RunSubagent`/`GetSubagentRun` 标 `parallelizable=True`；`RunPattern` 不标。

## 6. 测试与收尾

- [ ] 6.1 新增回归测试（G2 决议 7 条）：队列化、wait 语义、父等子、深度撤工具、累计计数、queue_full、depth fail-fast。
- [ ] 6.2 适配既有测试（grill 已定位 4 处破坏 + 1 处签名兼容）：`test_guardrails.py:133-153`/`:156-171`（超限抛错 → 队列化 envelope）、`test_subagent_manager.py:85-96`（条件性，max_active 默认值决定）、`test_config.py:119/128/140`（max_concurrent_runs → max_active 迁移）；`_build_subagent_loop` 签名兼容（`test_guardrails.py:50`、`test_loop.py:2144` 给 depth 默认值）。
- [ ] 6.3 benchmark smoke：`uv run asterwynd benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/smoke` 冒烟通过（coding-agent core 变更）。
- [ ] 6.4 同步 current spec：把 spec delta 合入 `openspec/specs/subagents/spec.md`，并同步修订 `openspec/specs/multi-agent-collaboration/spec.md:43` 的「SHALL reject spawns exceeding the limits」——该旧口径与本 change「排队而非失败」矛盾（grill 已定位，sync 时必须处理）。
- [ ] 6.5 `uv run pytest -q` 全绿；OpenSpec validate + artifact checker 通过。
