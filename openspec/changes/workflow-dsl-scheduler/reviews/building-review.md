# Building Review: workflow-dsl-scheduler

- Reviewer: 独立零记忆 building 审阅员（/review-loop），不继承实现上下文
- 审阅时间: 2026-09-14
- base sha: `c662165`（C1 `subagent-concurrency-queue` merge，本分支真实 fork 点）
- head sha: `5ec9ade`（分支 `workflow-dsl-scheduler/2026-09-14`）
- 审阅范围: `git diff c662165...HEAD` — 36 files, +7008/-248（新增 `agent/subagent/workflow.py`、`agent/subagent/scheduler.py`；改 `manager.py` / `patterns.py` / `tools/builtin/subagents.py` / `loop.py` / `config.py`；5 个新测试文件 ~91 条）
- 验证方式: 全部结论均由本地实跑复现（三门禁 + 全量 pytest + 6 组独立探针脚本），未采信上一轮报告

## Verdict

**CHANGES_REQUESTED**

调度器骨架（依赖门控、超步计数、取消传播、身份 contextvar set 点、reducer 枚举、三闸配置落点）实现正确且有测试钉住，任务 0.1–1.2 / 2.1 / 2.3 / 3.1–3.3 / 4.x / 5.x / 6.1–6.3 / 6.5 均验证通过。但 `foreach` 节点——本 change 唯一的动态并行原语，也是 design D7 里 4 个 pattern 中 3 个的拓扑主体——存在 4 个相互关联的严重缺陷：

1. **`foreach` 展开项串行执行**，不是规格与设计承诺的「并行展开」；`run_pattern("orchestrator-worker")` 因此从旧的 `asyncio.gather` 并行退化为串行，`workers` 不再是并发旋钮（实测并发峰值 1，对照组 4）。
2. **`foreach` 绕过 `max_runs` 闸**：展开项的 run 计数只在 `_dispatch` 处校验，`foreach` 自身派发路径不校验；超限时图不是按设计报 `GraphRecursionError(max_runs)`，而是撞上 spawn 桶抛出 `RuntimeError("spawn budget exceeded ... workflow wf_xxx")`，语义错位且 envelope 仍报 `completed`。
3. **`max_nodes`（含 foreach 展开）未按确认口径执行**：`max_nodes=5` + 20 项 `foreach` 实测创建 20 个 session。
4. **`queue_full` 处理路径必然崩溃**：`_launch_run` 在判 `queue_full` 之前就索引 `session.runs[-1]`，而该状态下 run record 已被 manager 弹掉，实测抛 `IndexError: list index out of range`——「绝不静默丢记录」的承诺未兑现，且该路径可经「同 manager 两张并发图」真实触达。

缺陷 1 是功能级回归（对比 `c662165:agent/subagent/patterns.py:103-111` 的 `asyncio.gather`），缺陷 2/3 直接违反本 change 自己确认的 Q5/D6 三闸口径，缺陷 4 使 grill 标的严重风险之一（`queue_full` 静默丢记录）以另一种形式复发。修复需补回归测试后再审（见 Issues 的 Required fix 标记）。

---

## 任务逐项验证

| Task | 状态 | 证据 |
|------|------|------|
| 0.1 grill 产出 | ✅ | `reviews/grill-design.md` 存在：7 条 Confirmed Decisions + 9 条 Open Questions + 9 条 User Confirmation（均带 `确认时间: 2026-09-14`，无 `待确认`/`待主 agent 提交` 等占位文本）。7 条决策逐条核验落地情况见下节 |
| 1.1 WorkflowSpec 数据结构 | ✅ | `agent/subagent/workflow.py:80-253`；`WorkflowNode`/`WorkflowEdge`/`RouteCase` + `to_dict`/`spec_hash`/`lookup` helper。round-trip 测试 `test_workflow_spec.py:65-77` |
| 1.2 schema 校验 | ✅ | 非法环（不含 route，`workflow.py:589-607` 迭代 Tarjan SCC）、未知节点（`:311-316`）、重复 id（`:296-304`）、超 max_nodes（`:324-327`）、多入边写同槽无 reducer（`:661-690`）、reducer 非法枚举（`:578-583`）、best_effort 缺 deadline（`:696-699`）。逐项有测试 |
| 2.1 ready 队列 + 依赖门控 | ✅ | `scheduler.py:451-486` `_data_deps_satisfied`/`_ready_nodes`，只看 required 数据入边；`test_downstream_runs_only_after_required_upstreams` 钉住「join 等齐 3 臂」 |
| 2.2 复用 C1 并发约束 | ⚠️ | 准入背压 `scheduler.py:491-492,519-520,876-886` 实现正确（`test_admission_backpressure_never_hits_queue_full` 通过，该测试自洽）；但 `queue_full` 兜底分支本身崩溃（Issue 3），「复用」在边界上不成立 |
| 2.3 汇合语义 all_required / best_effort | ✅ | `scheduler.py:451-460`（all_required 等终态，失败不 fail-fast）+ `:836-861`（best_effort 超时取消臂）。`test_all_required_waits_and_records_failure`、`test_best_effort_times_out_and_cancels_slow_arm`（断言超时臂 session 真被取消、aggregate 只消费已完成结果）通过 |
| 2.4 图级 recursion_limit | ⚠️ | dispatch 路径正确（`scheduler.py:381-392` 超步计数 → `GraphRecursionError`，envelope `status=graph_recursion_exceeded` + diagnostics，符合 Q8）。但 `foreach` 路径不受该闸约束（Issue 2） |
| 3.1 subagent 节点 | ✅ | `scheduler.py:622-635` + `_launch_run:744-805`；`test_subagent_node_records_session_identity` 断言 session 带 workflow_id/node_id |
| 3.2 aggregate 节点 + reducer | ✅ | `scheduler.py:637-666` + `aggregate_slots:159-184`（受限枚举，不执行模型代码）；concat/merge_dict/first_non_empty/last 均有测试 |
| 3.3 route 节点 | ✅ | `scheduler.py:668-695`；cases/default/max_routes 齐备，`test_route_takes_matching_case`/`test_route_default_branch_loops_back`/`test_max_routes_caps_a_single_route_node` 通过。标签匹配用子串包含（Issue 7，低危） |
| 3.4 foreach 动态展开 | ❌ | 展开集合解析（`items`/`source`+`source_field`）、`max_items`、`{item}`/`{index}` 模板替换均正确；但**展开项串行执行**且**绕过 max_runs/max_nodes**（Issues 1/2/4） |
| 4.1 5 个工具入口 | ✅ | `tools/builtin/subagents.py:444-659`；`loop.py:387-395` 注册 5 个工具。`test_declare_start_get_roundtrip` 等通过 |
| 4.2 RunWorkflow = Declare+Start + spec 哈希 | ✅ | `subagents.py:641-659`；`WorkflowSpec.spec_hash` 用 canonical JSON（sort_keys）内容寻址，`test_spec_hash_is_stable_and_content_addressed` 钉住 |
| 5.1 4 pattern → DSL 模板 | ✅ | `patterns.py:65-211`；bidding 的 selector 是真实 subagent 节点（grill 决策 5 落地），peer-review 是 `subagent+subagent+route` 有限循环（决策 4 落地），4 模板均过 schema round-trip |
| 5.2 run_pattern 兼容 adapter | ⚠️ | 返回字段兼容 + 新增 5 字段（`workflow_spec_hash` 改名落地，`"spec_hash" not in result` 有断言）。但 `worker_max_tokens`/`worker_max_time_s` 两个文档化的 pattern 参数被静默丢弃（Issue 6） |
| 5.3 D8 spawn 计数桶 | ⚠️ | 桶键 `workflow_id`、`release_workflow_bucket` 复位、嵌套独立桶均已实现且有测试（`test_workflow_spawn_bucket.py` 5 条）。但「上限 = max_runs*2 的校准承诺」在 foreach 路径上反向成立（Issue 2） |
| 6.1 新测试 | ✅ | 5 个新文件，实跑 100 passed。测试覆盖行为（非实现细节），但 `test_foreach_expands_items_into_parallel_nodes` 名不副实——只断言数量，从不验证并行（Issue 1 因此漏网） |
| 6.2 test_patterns 适配 | ✅ | 既有 `test_patterns.py` 100 passed（含在 6.1 实跑清单内），返回字段兼容断言通过 |
| 6.3 benchmark smoke | ✅ | 独立实跑 `uv run asterwynd benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/smoke-c2` → `passed: 5 / failed: 29 / unsupported: 38`，exit 0 |
| 6.4 spec sync | ⏸️ | tasks 声明留 closing，不计缺 |
| 6.5 全量 pytest + 门禁 | ✅ | 独立实跑 2316 passed, 8 skipped（详见「门禁复跑结果」） |

### grill 7 条 Confirmed Decisions 逐条核验

| 决策 | 状态 | 证据 |
|------|------|------|
| 1. 身份必须在调度器调用 `run_subagent` 的上下文里 set | ✅ | `scheduler.py:768-790` 在 `run_subagent` 前 set、finally reset；`test_workflow_and_node_identity_visible_inside_the_run` 用 LLM 内探针断言子 run 执行期读得到 `(workflow_id, node_id)`，并断言退出后不残留 |
| 2. C1 预留 contextvar 零生产调用点，C2 必须新建包裹点 | ✅ | `scheduler.py` 是全仓唯一 `set_workflow_id`/`set_node_id`/`set_bus` 调用点；`_launch_run` 的 finally 是唯一 reset 点。链路首次接通且被测试钉住 |
| 3. 调度器自持 ready 集合，不把 manager 队列当数据结构 | ✅ | `scheduler.py:101-129` 自持 `NodeState` 状态机；`manager` 仅作并发背闸。结构清晰（`_drive`/`_ready_nodes`/`_dispatch`/`_run_node` 分层合理） |
| 4. pattern 聚合语义 = 每节点取最新一次 run | ✅ | `patterns.py:298-314` `_workers_from_node` 取 `session.runs[-1]`；`test_peer_review_reuses_sessions_across_rounds` 断言 `completed == 2`（producer 跑 2 次仍只算 1 个 worker） |
| 5. bidding selector 必须是真实 subagent 节点 | ✅ | `patterns.py:132-143`（kind=subagent）；`test_compile_bidding_uses_a_real_selector_subagent_node` + `test_bidding_keeps_selector_shape`（断言 `selector["subagent_id"]` 存在、`completed == 3` 只数 proposers） |
| 6. 新工具须进 `SPAWN_TOOL_NAMES` + loop 注册 + MODIFIED spec | ⚠️ | `SPAWN_TOOL_NAMES`（`manager.py:282-289`）与 loop 注册（`loop.py:387-395`）已改，`test_depth_limited_child_has_no_workflow_spawn_tools` 通过（深度到限子 agent 无 `StartWorkflow`/`RunWorkflow`，保留 `DeclareWorkflow`/`GetWorkflow`/`CancelWorkflow`）——**深度闸绕过风险已封堵，grill 标的严重风险 1 解除**。但 spec delta 的 MODIFIED 落到了 `multi-agent-collaboration/specs/` 下（见 Issue 9） |
| 7. `root_run_id` 无载体，桶键改用 `workflow_id` | ✅ | `manager.py:1241-1275`；`test_workflow_bucket_is_keyed_by_workflow_id` 钉住；无 workflow 时回退 manager 生命周期语义（`test_no_workflow_context_keeps_manager_lifetime_semantics`） |

### grill 9 条 User Confirmation 核验

Q1 注册表 manager 内存 ✅（`manager.py:457-466` + `test_registry_is_manager_scoped`）｜Q2 准入背压 ✅ 实现（Issue 3 是兜底分支而非背压本身）｜Q3 `deadline_s` + 超时臂取消标 `cancelled` ✅（`scheduler.py:836-874`）｜Q4 节点 `outputs` + 受限 reducer 枚举 ✅｜Q5 三闸默认值 25/200/300 + superstep 计数 ✅ 默认值（Issue 2/4 是两闸的执行缺口）｜Q6 桶键/共享/嵌套 ✅｜Q7 5 工具全不 parallelizable ✅（`test_workflow_tools_are_never_parallelizable`）｜Q8 取消立即返回 + 超限走 envelope ✅（`scheduler.py:301-318`，`test_cancel_workflow_returns_cancelling_immediately`）｜Q9 三度量口径 + `spec_hash` 改名 ✅

### 实现 agent 自报「3 个实现中修掉的真 bug」核验

三条均**真实且被回归测试钉住**，未引入新问题：

1. **入口推导**：`workflow.py:341-351` 隐式入口排除「只被 route 控制边指向」的节点（回边目标不该是入口），无入口时显式报错。`test_entry_and_terminal_derived_when_omitted` 钉住。
2. **run_id 未登记**：`scheduler.py:795-798` 在派发成功那一刻就回写 `reuse_state.run_id`（而非等终态），使 best_effort 截止时间到点能按 run_id 找到并取消在跑的 run。`test_best_effort_times_out_and_cancels_slow_arm` 断言超时臂 `session.runs[-1].status == "cancelled"` 且 `active_run_id is None`，确实钉住。
3. **取消后状态矛盾**：`scheduler.py:588-591` `_on_node_finished` 在 `not self._accepting` 时提前返回，避免收尾把已标 `blocked` 的下游复活成 `pending`。`test_cancel_marks_workflow_and_stops_dispatch` 断言取消后所有节点状态 ∈ {cancelled, failed, blocked}，钉住。

---

## Issues

### Issue 1 — `foreach` 展开项串行执行，动态并行原语失效（严重：功能回归 + Spec 不符）

**Required fix.**

`agent/subagent/scheduler.py:697-741`：`_execute_foreach` 在 `for index, item in enumerate(items)` 循环里 `await self._acquire_slot()`（`:712`）→ `await self._launch_run(...)`（`:718`）→ `await self._await_run(...)`（`_launch_run` 内部），**每次迭代都等到该 run 终态才进入下一项**。`foreach` 节点因此是一个接一个跑的串行循环。

实测（`max_active=5`，每项 `asyncio.sleep(0.08)`）：

| 场景 | 墙钟 | LLM 并发峰值 |
|------|------|-------------|
| 4 项 `foreach` | 1.29s | **1** |
| `run_pattern("orchestrator-worker", workers=4)` | 0.76s | **1** |
| 对照组：4 个独立 subagent 节点 | 0.45s | 4 |

影响面：

- `openspec/changes/workflow-dsl-scheduler/specs/multi-agent-collaboration/spec.md:18` 明确写「`foreach`（对有限集合展开**并行**）」，`:20-24` 的 scenario 也以「展开一个子任务」承诺动态并行——实现不符。
- design.md:78-81 的 D7 把 orchestrator-worker / hierarchical / bidding 三个 pattern 全部建在 `foreach` 上；`c662165:agent/subagent/patterns.py:103-111` 的旧 `OrchestratorWorkerPattern` 用 `asyncio.gather` 真并行，新实现退化为串行——**这是相对 C1 基线的功能回归**，`workers` 参数不再是并发旋钮。
- C5 `benchmark-workflow-replay` 依赖本调度器的图级并行度做指标，当前 `peak_active` 恒等于「同时就绪的节点数」，对 foreach 恒为 1。

测试漏网原因：`test_foreach_expands_items_into_parallel_nodes`（`test_scheduler.py:698`）只断言 `items`/`subagent_ids`/`summary` 的数量，从不测量并发——测试名承诺的行为未被验证。

### Issue 2 — `foreach` 绕过 `max_runs` 闸，且超限时暴露错误的失败语义（严重：违反 Q5/D6 三闸口径）

**Required fix.**

`max_runs` 只在 `_dispatch`（`scheduler.py:508`）校验。`foreach` 的展开项**不经过** `_dispatch`，而是走 `_launch_run`；`_acquire_slot`（`scheduler.py:876-887`）只做 `self._runs += cost`，不校验 `spec.max_runs`。

实测（`max_runs=3`，`foreach` 展开 8 项，`max_spawns` 抬高排除干扰）：

```
envelope status: completed            ← 图报「完成」
  node fan: status=failed, runs=3
  error: RuntimeError: subagent spawn budget exceeded: 6 spawns >= max_spawns 6 (workflow wf_30f8573a)
```

三重错位：

1. 声明的 `max_runs=3` 没有拦截展开（实际跑了 3 个 item = 6 次 spawn）。
2. 拦截它的是 spawn 桶（`scheduler.py:338` `register_workflow_bucket(workflow_id, spec.max_runs * 2)`），错误文案是「spawn budget exceeded … workflow wf_xxx」——不是 Q8 确认的 `GraphRecursionError` envelope（`reason="max_runs"`），模型拿到的是无法判断「该缩小图还是减少 foreach 项」的底层文案。
3. workflow 顶层 `status` 仍报 `completed`、`diagnostics` 为空，节点失败被折叠进 `failed` 计数；父 agent 无法从 envelope 判断图是「跑完了」还是「预算炸了」。

这正好复现 design.md:99 与 grill 风险 2 描述的场景（「图还没跑完但 spawn 预算先耗尽」），只是方向相反：本该是 `max_runs` 先响，实际是 spawn 桶先响——`max_runs*2` 的校准假设「foreach 展开计入 max_runs」不成立，校准因此失效。

### Issue 3 — `queue_full` 处理路径必然抛 `IndexError`（严重：grill 标的严重风险 3 复发）

**Required fix.**

`scheduler.py:792`：

```python
run_id = launched["run_id"]
self._run_refs.append(manager._sessions[subagent_id].runs[-1])   # ← 792
...
if launched["status"] == "queue_full":                            # ← 800
    return {"subagent_id": subagent_id, "run_id": run_id, **launched}
```

`queue_full` 判定在 `:800`，但 `:792` 已经先索引了 `session.runs[-1]`。manager 的 `_take_back_if_queue_full`（`manager.py:778-779`）在该状态下会把刚 append 的 run **弹掉**（`session.runs.pop()`），于是 `runs[-1]` 越界。

实测（`max_active=1`, `max_queued_runs=0`，一个非 workflow 的 run 占住许可，再由调度器派发一个 subagent 节点）：

```
  foreign run status: running | pending: 0 | max_queued_runs: 0
  workflow status: completed
   node: a failed error= IndexError: list index out of range reason= IndexError: list index out of range
```

可达路径是真实存在的——同 manager 上两张并发图（Q9 已确认 `max_active` 池是全 manager 共享，`peak_active` 才需要按 workflow 隔离）：

```
=== 两张并发图，max_active=2, max_queued_runs=0 ===
  workflow A: completed | 4/4 nodes completed
  workflow B: completed | n0 failed(IndexError), n1 failed(IndexError), n2 blocked, n3 blocked
```

B 的节点报 `IndexError` 而不是可诊断的 `queue_full` 失败。虽然 Q7 已让 5 个工具全不 parallelizable 以降低「一轮多图」概率，但 `StartWorkflow(wait=false)` / `RunWorkflow(wait=false)` + 后续 turn 再起一张图，或 `run_pattern` 与 workflow 混用，都绕不过这条路径。

修法建议：把 `_run_refs.append` 挪到 `queue_full` 判定之后（`queue_full` 无 run record 可登记，直接按失败记账并写 `state.error = "queue_full"`），并按 design.md:96 的要求让 `GetWorkflow` 能看到该节点的 `queue_full` 原因。

### Issue 4 — `max_nodes`（含 foreach 展开）未执行（严重：违反 Q5 user confirmation）

`workflow.py:324-327` 只比较**声明节点数**与 `max_nodes`；`foreach` 展开项从不计入 `_expanded_nodes`。`scheduler.py:299,332` 给 `_expanded_nodes` 赋了初值后**全仓无任何读取点**（死字段），说明「展开后复检」这一步从未接上。

实测：`max_nodes=5` + `foreach(items=20)` → 实际创建 **20** 个 session，`max_nodes` 完全没拦。

`agent/config.py:250` 的 docstring 与 design.md:73 / grill Q5 都明确写「`max_nodes=200`（节点数，**含 foreach 展开**）」——实现与已确认口径不符。

### Issue 5 — `peak_active` 在 foreach 路径下恒为 1（中）

`_refresh_peak`（`scheduler.py:1001-1005`）按 `self._run_refs` 里 `status == "running"` 的条数统计——口径本身符合 Q9（不污染其它 pattern）。但 Issue 1 导致 foreach 任意时刻只有 1 个 run 在跑，`run_pattern` 新增返回的 `peak_active` 对 3 个基于 foreach 的 pattern 恒为 1，C4/C5 的成本/冗余度指标会失真。修 Issue 1 后可一并解决；否则该字段应在文档里降级说明。

### Issue 6 — 文档化的 pattern 参数 `worker_max_tokens` / `worker_max_time_s` 被静默丢弃（中）

`RunPatternTool` 的 description（`tools/builtin/subagents.py:370`）仍向模型承诺 `worker_max_tokens, worker_max_time_s`。旧实现会传给每个 worker（`c662165:agent/subagent/patterns.py:69-70`），新模板（`patterns.py:65-88`）只读 `workers`/`teams`/`proposers`/`max_rounds`，编译出的 spec 里没有任何预算字段。

实测：`compile_pattern("orchestrator-worker", params={"workers":2,"worker_max_tokens":100,"worker_max_time_s":5})` → 节点只有 `id/kind/task/name/outputs/items/max_items`，无预算字段。

参数被静默忽略比报错更糟：模型以为已给 worker 设了预算。要么把这两个参数接进节点（需要在 `_NODE_FIELDS` 加字段 + `_launch_run` 透传 `max_tokens`/`max_time_s`），要么从工具 description 里删掉。

### Issue 7 — route 标签匹配用子串包含，`NOT APPROVED` 命中 `APPROVED`（中低）

`scheduler.py:187-191`：

```python
return label.strip().upper() in verdict.upper()
```

实测 `matches_route("NOT APPROVED at all", "APPROVED") == True`、`matches_route("DISAPPROVED", "APPROVED") == True`。

peer-review 模板的 reviewer 指令是「Reply with exactly one line starting with APPROVED if it is acceptable, or CRITIQUE …」，但模型实际常写「NOT APPROVED — 需要修改」。此时 route 走 APPROVED 分支直接汇合，review 循环提前终止并把未达标的产出报成成功。design.md:100 与 Risks 都说「只匹配结构化标签/受限枚举」——子串包含不是结构化匹配。建议改为行首/词边界匹配（如 `re.match(rf"^{label}\b", verdict.strip(), re.I)`）。

### Issue 8 — 死代码与 write-only 字段（低：可维护性）

- `scheduler.py:124,601,608`：`NodeState.stale` 只写不读——`_on_node_finished` 把在途下游标 `stale`，但没有任何路径消费该标记，下游**不会**在跑完后用新输入重跑。当前模板不受影响（peer-review 的回边是 route 控制边），但这是 DAG 数据边语义的潜伏缺口，且给人「已处理」的错觉。
- `scheduler.py:278,699`：`_foreach_state` 只写不读。
- `scheduler.py:269,299,332`：`_expanded_nodes` 只写不读（见 Issue 4，建议直接接上而非删除）。
- `patterns.py:245-256`：`OrcPattern.__init__` 保留 `manager`/`bus` 但全类无消费点；`task`/`params` 只有 `compile()` 用。
- `scheduler.py:54`：`NODE_STATUSES` 无引用点。
- `workflow.py:89-96`：`WorkflowSpec._index` 用 `field(default_factory=dict, compare=False)` 存查找表，但 `to_dict`/`spec_hash` 走 `self.nodes`——可接受，惟 `dataclasses.replace`（`with_limits:717-723`）会保留同一 `_index` 引用；当前只用于改 limits（不改 nodes），暂无 bug，但值得留意。

### Issue 9 — 深度闸 spec delta 落在错误的能力域，sync 后会留矛盾口径（中：Spec 对齐）

`SPAWN_TOOL_NAMES` 的实现改对了（Issue 清单里 grill 严重风险 1 已解除），spec delta 也补了对应的 MODIFIED requirement——但它写在 `openspec/changes/workflow-dsl-scheduler/specs/multi-agent-collaboration/spec.md:59-70`。

「深度到限撤 spawn 工具」这条 requirement 在正式规格里位于 **`openspec/specs/subagents/spec.md:70-79`**（C1 就是这么分的：C1 的 delta 目录下同时有 `specs/multi-agent-collaboration/` 与 `specs/subagents/` 两个文件）。本 change 的 delta 目录只有 `specs/multi-agent-collaboration/`。

后果：`npx openspec validate --all --strict` 检查的是「change delta 的文件能否解析 + 正式 spec 是否 valid」，不会发现这条 requirement 在能力域上的错位（独立实跑确认 30 passed）；但 closing 阶段 `opsx:sync` 会把这条 MODIFIED 合进 `openspec/specs/multi-agent-collaboration/spec.md`，而 `openspec/specs/subagents/spec.md:70-72` 的旧口径（只有 4 个工具名）原样保留 —— 正式规格里出现两条描述同一行为、口径不一的要求。

修复：把这段 MODIFIED 移到 `openspec/changes/workflow-dsl-scheduler/specs/subagents/spec.md`（新建该 delta 文件），与 C1 的目录结构对齐。task 6.4 尚未勾选，可在 closing 前一并处理。

### Issue 10 — 两处次要一致性（低）

- `scheduler.py:88-98`：`GraphRecursionError.to_dict()` 同时输出 `limit` 与 `recursion_limit` 两个同值键（注释说明为兼容 Q8 与异常自身口径）。可用，但下游若按 `limit` 消费会在 `reason="max_runs"`/`"max_routes"` 时误读成「递归上限」。
- `scheduler.py:381`：recursion_limit 判定在派发**之前**用 `self._steps >= limit` 拦截，语义是「已达上限就不再进新的一步」，与 spec delta:43-46 的「尝试再前进一步时」表述一致，无问题；仅记录已核验。

---

## 门禁复跑结果（独立执行，不采信上一轮）

| 门禁 | 命令 | 结果 |
|------|------|------|
| 目标测试集 | `uv run pytest tests/agent/subagent/test_workflow_spec.py test_scheduler.py test_workflow_tools.py test_pattern_templates.py test_workflow_spawn_bucket.py test_patterns.py -q` | ✅ **100 passed** in 4.70s |
| 全量 pytest | `uv run pytest -q` | ✅ **2316 passed, 8 skipped** in 182.21s（exit 0） |
| 浏览器 flake 复现 | `uv run pytest tests/web_tests/test_browser.py tests/web_tests/test_multi_session_browser.py -q` ×3 | ✅ 3 次均 `10 passed, 7 skipped`，**未复现**上一轮报告的浏览器 flake。全量跑内该文件也是 passed |
| OpenSpec strict validate | `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` | ✅ **30 passed, 0 failed** |
| 项目 artifact checker | `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py` | ✅ `OpenSpec artifact checks passed`（exit 0） |
| benchmark smoke | `uv run asterwynd benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/smoke-c2` | ✅ `Tasks: 72 | passed: 5 | warnings: 0 | unsupported: 38 | failed: 29`，exit 0 |

三门禁全绿。注意：**门禁全绿并不代表实现正确**——Issue 1–4 都是门禁与现有测试覆盖不到的行为缺口（Issue 1 的测试名承诺了并行但只数数量；Issue 2/4 的三闸校验现有测试只测了声明节点数上限，未测 foreach 展开后的复检）。

---

## 复审指引

修复后请附回归测试，且测试必须能证伪当前实现：

- Issue 1：并发探针断言 foreach 展开项 LLM 并发峰值 > 1（对照当前实测 1）；`run_pattern("orchestrator-worker", workers=N)` 的墙钟应显著短于串行和。
- Issue 2：`max_runs` 小于 foreach 展开项数时，envelope 必须是 `status="graph_recursion_exceeded"` + `diagnostics.reason == "max_runs"`（当前是 `completed` + 节点 `RuntimeError`）。
- Issue 3：构造「池被占满 + 调度器派发」场景，断言节点失败原因可诊断（不是 `IndexError`），且 `GetWorkflow` 能看到 `queue_full`。
- Issue 4：`max_nodes=5` + `foreach(items=20)` 必须拒绝或截断（当前创建 20 个 session）。
- Issue 6/7：分别为参数透传与 `NOT APPROVED` 不命中 `APPROVED` 各加一条断言。

修完后重新跑 round 2 复审；本轮 verdict 为 CHANGES_REQUESTED，未生成 review manifest（manifest 只在 PASS 时产出）。
