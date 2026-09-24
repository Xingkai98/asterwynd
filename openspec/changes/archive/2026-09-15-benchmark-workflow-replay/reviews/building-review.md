# Building Review: benchmark-workflow-replay（C5）

- **verdict**: PASS
- **审阅员**: 独立零记忆 building 审阅（review-loop, issue #90 闭环）
- **base_sha**: `b00dffa`（立项 commit）
- **round 1 head_sha**: `93b88bd`
- **final head_sha**: `6da6969`
- **轮次**: 3 轮（CHANGES_REQUESTED → 修复 → 再审 …→ PASS）
- **依据**: proposal / design D1–D6 / tasks 21 项 / spec delta 5 个 Requirement /
  `reviews/grill-design.md` 的 14 条 Confirmed Decisions + Q1–Q10 用户确认

## 结论摘要

实现覆盖了 spec delta 的全部 5 个 Requirement 与 13 个 Scenario，14 条 Confirmed
Decision 与 Q1–Q10 逐条落实，tasks.md 21 项无假勾选。**但 Round 1 审出 8 处缺陷、
Round 2 审出 1 处、Round 3 审出 1 处，累计 10 处**，全部已修复并配可判别回归测试
（每条的回归测试都验证过：在缺陷代码上必失败、在修复后通过）。

其中最严重的一条是**并发重放串号**：`BenchmarkRunner` 只持有一个
`AsterwyndRunner`，而 `run_all` 用 `asyncio.gather` 并发跑任务，replay 的记录却挂在
runner 实例属性上——甲任务会读到乙任务的记录。

## 任务逐项验证

| # | 任务 | 结论 | 证据 |
|---|------|------|------|
| 0.1 | grill 设计追问 | ✅ | `reviews/grill-design.md`：14 CD + 10 Q 用户确认 |
| 1.1 | workflow_record 落盘/读取（Q1 写法 B） | ✅ | `benchmarks/workflow_replay.py:129-165`；`reviews/grill-design.md:211` |
| 1.2 | 三模式分派 + CLI 接线（Q8） | ✅（Round 3 修） | `benchmarks/agent_runner.py:390-411`、`agent/main.py:740-760,981-1007` |
| 1.3 | 规范化记录（spec_hash/scheduler_version/budget_config/seed/model/temperature） | ✅（Round 1 修 seed） | `benchmarks/workflow_replay.py:107-126` |
| 2.0 | 注入 CostLedger（CD14） | ✅ | `benchmarks/agent_runner.py:364-384` |
| 2.1 | TaskResult/AgentRunResult 成对加字段 + 3 处重建点 | ✅ | `benchmarks/models.py:50-76,172-190`；`benchmarks/runner.py:472,479,507,561,630` 全改 `replace` |
| 2.2 | 从 envelope 采集 + run_count/spawn 快照 | ✅（Round 1 修 declared 顶替） | `agent/subagent/scheduler.py:2019-2053,2158-2174` |
| 2.3 | report.py 渲染 workflow 字段段 | ✅ | `benchmarks/report.py:445-514` |
| 3.1 | 冗余度 = 有用产出/spawn（Q2 消费口径） | ✅ | `agent/subagent/scheduler.py:2036-2053,1791,1831,1855,2234` |
| 3.2 | 图级步数 = scheduler steps | ✅ | `agent/subagent/scheduler.py:2168` |
| 3.3 | 拒绝降级计数四类（Q3/Q4） | ✅ | `agent/subagent/manager.py:389-398,592-612,1177,1490,1499`；`scheduler.py:1616,2043-2052` |
| 3.4 | 报告渲染编排指标段（Q9 独立 section） | ✅ | `benchmarks/report.py:411-414,445-508` |
| 4.1 | 比较口径扩展 + $/resolved 分母复用（CD9） | ✅（Round 1 修分母漂移；Round 2 补 HTML） | `benchmarks/compare.py:200-260,268-330,540-560` |
| 4.2 | 对照臂两份 config YAML（Q5 取值） | ✅ | `configs/workflow-arm-small-k.yaml`（3/60）、`workflow-arm-large-n.yaml`（16/24） |
| 5.1 | 端到端 fan-out 验证任务（Q6 口径） | ✅ | `benchmarks/tasks-e2e/workflow-fanout/`、`benchmarks/workflow_e2e.py` |
| 5.2 | 降级策略机器可读字段（Q7 落点 A） | ✅ | `benchmarks/runner.py:295-375`、`agent_runner.py:471-477` |
| 6.1 | 三模式/报告/指标/replay 确定性测试 | ✅ | `tests/benchmark/test_workflow_replay.py` 30 个 + `test_workflow_modes.py` 21 个 |
| 6.2 | 兼容回归（旧 artefact 字段 None、报告不崩） | ✅ | `test_workflow_replay.py:585-599`、`test_workflow_modes.py::test_replay_without_record_dir_marks_not_executed` |
| 6.3 | benchmark smoke | ✅ | 见「验证命令输出」 |
| 6.4 | spec 同步到 `openspec/specs/benchmark/spec.md` | ✅ | 5 个 ADDED Requirement + 13 Scenario |
| 6.5 | pytest/validate/checker 全绿 | ✅ | 下方输出 |

grill 14 条 Confirmed Decision 抽查复核：CD3（三处重建点改增量写法）、CD5
（queue_wait_s 零新字段）、CD7（spawn 快照在释放桶前取）、CD13（replay 走
`parse_spec_for_manager` 带 `_spec_bounds`）、CD14（ledger 注入）均逐条落到实现，
未发现偏离。

## Issues（Round 1–3 发现并修复，全部含可判别回归测试）

### 🔴 Round 1-1（严重）并发重放跨任务串号

- **文件**: `benchmarks/agent_runner.py:542`（原 `self._replay_record = record`）
- **问题**: `BenchmarkRunner` 只持有一个 `AsterwyndRunner` 实例，`run_all` 用
  `asyncio.gather` 并发跑任务（默认 `parallel` 由 `suggest_parallel()` 按机器内存/CPU
  推导，典型 >1）。把「本任务的记录」放在 runner 实例属性上，兄弟任务会互相覆盖：
  先起但跑得久的任务在自己的采集点读到的是后起任务刚写进去的记录。
- **实测**: 探针复现——taskA 报出 taskB 的 `workflow_spec_hash`；`workflow_count`
  同样串号。
- **修复**: 记录改在 `run()` 的**局部变量**里流转，经 `_run_dynamic_replay(record=…)`
  与 `_collect_workflow_fields(replay_record=…)` 显式传递。
- **回归测试**: `test_workflow_modes.py::test_parallel_replay_does_not_cross_contaminate_spec_hash`
  （相等节点数下用不等节点数制造「A 先起、B 先完」交错；验证过在缺陷代码上必失败）

### 🔴 Round 1-2（严重）replay 的 spec_hash 断言是同义反复

- **文件**: `benchmarks/agent_runner.py:627`（原抄 `entries[0]["workflow_spec_hash"]`）
- **问题**: Q6 明确规定真实 LLM 场景「只硬断言 `spec_hash` 相等」，但实现是把
  **record 里的值原样抄进** replay 结果的 `workflow_spec_hash`，再拿去和 record 比
  ——恒等成立。损坏/版本不兼容/被篡改的记录照样「通过」，该断言零鉴别力。
- **实测**: 探针把 record 里的 hash 换成 `TOTALLY-WRONG-HASH`，实现仍报该值并通过断言。
- **修复**: 改报**回放那次 envelope 的实测** `spec_hash`（来自真正 re-parse + 执行
  的 spec），record 里的值只作期望侧。
- **回归测试**: `test_workflow_replay.py` 既有 replay round-trip 用例 + 探针复验
  （修复后错误 hash 会被如实报为真值）。

### 🔴 Round 1-3（严重）declared 态图顶掉真实图的编排指标

- **文件**: `benchmarks/agent_runner.py:664`（原 `_envelope_fields` 取 `list_workflows()[0]`）
- **问题**: `DeclareWorkflow` 只注册不执行，但按注册顺序常排第一（grill Q1 的原场景
  就是「先声明后启动」）。取第一张会让**全部**编排字段静默变 `None`——`node_count`
  /`run_count`/`peak_active`/`critical_path_s`/`cost` 全部丢失，而同一份记录里数据是
  完整的。
- **实测**: 探针复现——注册 `declared` + 真跑一张图后，`workflow_node_count` 为 `None`。
- **修复**: 新增 `_first_started_scheduler()`，跳过 `declared` 态。
- **回归测试**: `test_workflow_modes.py::test_declared_graph_does_not_shadow_metrics_of_the_graph_that_ran`

### 🟠 Round 1-4（中）fake 场景的 status 全等断言恒假

- **文件**: `benchmarks/workflow_e2e.py:57-64`
- **问题**: Q6 要求 fake 场景对 `status` 做全等断言，但 record 侧 `observed.status` 是
  scheduler 的**图级状态**（`completed`），replay 侧 `TaskResult.status` 被 Q10 读法 A
  固定成 `replayed` 专值——两者永远不可能相等。原实现直接把 `status` 从断言里
  `continue` 掉，等于该字段从未被验证。
- **修复**: 基准统一为**图级状态**（`_status_comparable`）：两侧都无异常完成即通过；
  两侧同一种异常状态也通过；一侧正常一侧异常则失败。
- **回归测试**: `test_fake_status_assertion_compares_workflow_status_not_task_status`
  + `test_fake_status_assertion_fails_when_replay_did_not_reproduce_record`

### 🟠 Round 1-5（中）compare 的 $/resolved 分母自造口径（违反 CD9）

- **文件**: `benchmarks/compare.py:274`（原手抄 `{"docker_unavailable","task_family_unsupported","approval_unavailable"}`）
- **问题**: CD9 明写「分母必须复用 `PASS_STATUSES` + `is_valid_round`，不得自造」。
  手抄副本今天恰好等价，但会在 `INVALID_ROUND_REASONS` 演进时**静默漂移**，导致
  compare 的 `$/resolved-task` 与 report 的 pass@k 对不上。
- **修复**: 直接复用 `benchmarks.statistics.is_valid_round`。
- **回归测试**: `test_compare_resolved_count_tracks_invalid_round_reasons`
  （monkeypatch 扩展 `INVALID_ROUND_REASONS`，断言 compare 自动跟随）

### 🟠 Round 1-6（中）workflow_record 的 seed 恒为 None

- **文件**: `benchmarks/runner.py`（原无 seed 传递路径）
- **问题**: D2 schema 的 `seed` 字段是必填项，`AsterwyndRunner.__init__` 也收了
  `seed` 参数——但**没有任何调用方传它**：`AgentRunner.run` 的五参签名按 Q8 不动，
  `_build_benchmark_runner` 也没接。CLI 的 `--seeds` 到不了记录里。
- **修复**: 新增 `AsterwyndRunner.set_run_seed()`，由 `BenchmarkRunner._run_agent`
  在每次 run 前设置。
- **回归测试**: `test_workflow_modes.py::test_run_task_seed_reaches_the_record`
  （走完整 `run_task` 路径——只调 setter 会漏掉「没人调用它」这个真实缺陷）

### 🟡 Round 1-7（轻）template 模式落盘了不该写的记录

- **文件**: `benchmarks/agent_runner.py:644`
- **问题**: 模块 docstring（`workflow_replay.py:5`）与运行协议文档
  （`docs/benchmark-run-protocol.md`）都明确写 template **不落盘记录**，实现却顺路
  写了 `workflow_record.json`——留下没人读的文件，且让人误以为 template 也能 replay。
- **修复**: 只有 `dynamic-record` 落盘。
- **回归测试**: `test_workflow_modes.py::test_template_mode_does_not_write_a_replay_record`

### 🟡 Round 1-8（轻）死代码与未使用 import

- `AsterwyndRunner._replayed_count` 赋值后无人读；`benchmarks/runner.py` 的
  `COLLECTION_STATUS_MISSING`、两个测试文件的多余 import。
- **修复**: 删除；`ruff --select F401,F811,F841,E722` 对全部改动文件通过。

### 🟠 Round 2-1（中）compare 的 HTML 报告漏掉编排段

- **文件**: `benchmarks/compare.py:build_html`（原无编排段）
- **问题**: `build_summary`（markdown）加了「Orchestration Metrics」段，`build_html`
  没加，而 `compare.py` 的 `main()` 一次写两份报告
  （`benchmarks/reports/comparison.md` / `.html`）。同一批 run 的两份报告因此互相
  矛盾：HTML 看起来像从没跑过 workflow。
- **修复**: 抽 `_orchestration_rows()` 为两份报告共用的行构造（表头与口径说明只声明
  一份），HTML 侧补渲染同一段。
- **回归测试**: `test_compare_html_matches_markdown_orchestration_section`

### 🟠 Round 3-1（中）非 asterwynd runner 的 workflow 三模式静默空跑

- **文件**: `agent/main.py:994`（原只对 `dynamic-replay` 校验 agent）
- **问题**: `--workflow-mode dynamic-record|template` 配 `--agent fake|shell|claude`
  时不会报错，但三个 runner 都不构造 `SubAgentManager`——workflow 从不被驱动，
  命令**静默**跑成一次普通单 agent benchmark，`result.json` 里一个 workflow 字段都
  没有，用户却以为编排测过了。`dynamic-replay` 有这道校验，另两个模式没有。
- **实测**: `--agent fake --workflow-mode dynamic-record` 退出码 0、`result.json`
  无任何 `workflow_*` 字段。
- **修复**: 三个模式统一在校验期拒绝非 asterwynd。
- **回归测试**: `test_cli_benchmark.py::test_workflow_mode_rejects_non_asterwynd_agent`
  + `test_dynamic_replay_requires_a_record_directory` + `test_unknown_workflow_mode_is_rejected`

## 专项核验（任务书「特别关注」逐条回应）

1. **README.md / README_EN.md 同步**：✅ 两侧新增段落一一对应——同样的 3 行模式表、
   同样的两条命令与标志（`--workflow-mode`/`--workflow-record`/`--agent`/`--provider`
   /`--model`/`--runs-dir`）、同样提到两份 config 与「独立 section / 不进 pass@k 分母」
   口径。脚本化比对标志集合一致。

2. **`benchmarks/tasks-e2e/workflow-fanout/` 是否该保留**：**保留**，且已补
   `benchmarks/tasks-e2e/README.md`。理由：它不在主任务集 `benchmarks/tasks/` 下，
   主命令与 CI 门禁（`benchmarks/tasks/gate-smoke`）都不扫该目录，目录内也没有
   `manifest.json`、不参与 `validate_coverage`——不会被主 benchmark 意外纳入。
   README 记录了它的用途、真实 LLM 跑法（约 40s/次、不属常规回归），并**警示**
   `base_commit`（`683e604`）是分支内提交：已核实它**不在** `origin/master` 上
   （`origin/master` 现为 `979fd1b`），若本 change 以 squash/rebase 合入则该提交
   不进入 master，任务会以 `setup_error` 失败，届时需把 `base_commit` 改成 master
   上必然存在的提交。

3. **两个真实 LLM e2e 才暴露的缺陷**：✅ 两者都已核验修复到位——
   - CountingLLM 的 `__getattr__` 透传（`agent_runner.py:267-280`）确实让
     `model` 属性可达。核验：`test_counting_llm_delegates_model_so_cost_is_not_a_fake_zero`
     断言 `CountingLLM(PricedLLM()).model == "deepseek-v4-flash"`；`__getattr__`
     只在常规属性查找失败后触发，不影响 `llm`/`call_count` 与 `chat`。
   - replay 的 `TaskResult.status` 停在默认 `error`：核验 `runner.py:474-486` 现在
     在 replay 分支 `replace(status=REPLAY_STATUS, …)`，且回归测试走**完整
     `run_task` 路径**（`test_replay_task_result_status_is_replayed`）——任务书要求
     的「不能只调 `_annotate_e2e_verification`」这点做到了。

4. **`--workflow-record <run-dir>` 路径解析**：✅ 定位健壮。`_read_replay_record`
   →`read_workflow_record`（`workflow_replay.py:188-196`）缺文件/JSON 损坏一律返回
   `None`，采集侧落 `collection_status="missing"`、不崩、不静默（
   `test_dynamic_replay_missing_record_is_reported_not_silent`）。另核验**无路径逃逸**：
   task_id 里的 `../` 无法读到目录外文件（`read_workflow_record(rec/'tasks'/'../../secret')`
   实测返回 `None`——因为 `path.exists()` 用的是未解析路径）。task_id 本身来自仓库内
   `task.json`、非不可信输入。
   - **附带核验**：`dynamic-replay` 的缺记录路径**仍返回 `replayed` 状态**（不判分、
     不进分母），同时 e2e 标注为「未执行 + 原因」——降级语义一致。

5. **对照臂两份 yaml**：✅ 真被读进且取值与 Q5 一致。`load_config` 实测
   `workflow-arm-small-k.yaml` → `max_active=3, max_spawns=60`；
   `workflow-arm-large-n.yaml` → `max_active=16, max_spawns=24`。两者都带注释说明
   「大 N 臂的 spawn budget exceeded 属预期压力结果」，报告侧在
   `_ORCHESTRATION_NOTE` 有对应标注。

## 其他核验

- **测试覆盖**：`test_workflow_replay.py` 30 个 + `test_workflow_modes.py` 21 个 +
  `test_cli_benchmark.py` 新增 3 个。覆盖三模式 round-trip、record schema、采集失败
  降级、replay 确定性、冗余度消费口径、四类拒绝计数、queue_wait_s max 口径、
  报告/比较渲染、对照臂 config、旧 artefact 兼容。
- **安全性**：record 路径无逃逸（见上）；replay 只走 `parse_spec_for_manager` +
  `WorkflowScheduler`，无模型生成代码执行路径；`--workflow-record` 校验必须是目录。
- **可维护性**：`benchmarks/` 侧只做记录/采集/报告，`agent/subagent/` 侧只加
  instrumentation 计数器（`_count_rejection` 镜像 `_count_spawn` 的分桶），分层清晰。
- **冗余度**：未发现重复实现；`_orchestration_rows` 的抽取消除了 Round 2 发现的
  markdown/HTML 分叉。
- **CI 完整性**：pytest 全绿、OpenSpec strict validate 通过；artifact checker 除
  「缺 building-review.md」（本文件）外无其他错误。ruff 对全部改动文件
  `--select F401,F811,F841,E722` 通过（`agent/main.py` 的两条 `sys` 报错在
  `b00dffa` 上已存在，非本次引入）。

## 验证命令输出

```
$ uv run pytest -q -p no:randomly
2599 passed, 8 skipped, 19 warnings in 154.88s

$ npx --yes @fission-ai/openspec@1.4.1 validate --all --strict
Totals: 30 passed, 0 failed (30 items)

$ uv run asterwynd benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/smoke-c5-review
Tasks: 72 | passed: 5 | warnings: 0 | unsupported: 38 | failed: 29
（72 个任务全部跑完，无 setup/crash error；与 C5 前的既有基线同形）

$ PYTHONPATH=. uv run python scripts/check_openspec_artifacts.py --base-ref master
ERROR: benchmark-workflow-replay: building-review.md missing
（本文件写入前的唯一报错；写入后由 manifest 绑定，见 building-review-manifest.json）
```

## 未决 / 遗留（不阻塞本 change）

- `docs/benchmark-run-protocol.md`、`benchmarks/workflow_replay.py` 的 docstring、
  实际行为在 template 是否落盘上已一致（Round 1-7 修）。无遗留文档漂移。
- `agent/main.py:15,81` 的 `sys` 重复 import 是 C5 之前就存在的仓库债务，已按
  「只更新当前变更造成的事实变化」原则不在本 change 内顺手修（会扩大 diff 面）。
