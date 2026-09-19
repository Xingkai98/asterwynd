# Building Review — workflow-budget-attribution (C4)

## Reviewer

- run id: review-workflow-budget-attribution-20260914-r2
- 时间: 2026-09-14
- 角色: 独立零记忆 building 审阅员（不继承实现上下文；任务书为唯一 brief）
- base: `73c4005`（= `origin/master`，PR #184 合入点，本 change 分支点）
- head: `443e1ff`（C4 building Round 2 修复 commit）
- 分支: `workflow-budget-attribution/2026-09-14`
- 审阅对象 diff: `git diff 32ea24f^..HEAD` = `git diff 73c4005..HEAD`，27 files / +4088 / −34
  （其中实现部分 `git diff 32ea24f..67d762b` 22 files / +3170 / −50；Round 2 修复 `443e1ff` 6 files）
- 环境: `uv sync --extra dev`；全量 pytest / OpenSpec strict validate / artifact checker 均在本 worktree 内执行

## Verdict

**PASS**（Round 2 复审，2026-09-14）

Round 1 判 `CHANGES_REQUESTED`：4 个缺陷（2 个严重到让 spec 的两条 Scenario 实际不可达），
均由修复 commit `443e1ff` 修复，Round 2 我逐条自写复现脚本独立核验通过（证据见文末「Round 2 复审」节）。
Round 1 判定与证据保留在下方作为历史记录。

Round 1 verdict（历史）: **CHANGES_REQUESTED** — 核心交付（D1–D7 + 9 条 Confirmed Decisions +
16 条 User Confirmation）整体扎实、任务无假勾选，但发现 4 个实现缺陷，其中 2 个让 spec delta 的
Scenario 在真实配置下**不可达**，必须修后复审。

---

## Round 1 判定（历史）

### 总评

四维预算账本、超限状态机、成本归因四维、动态 route `$ref`、动态 foreach 跨层 source / `max_items=0`
**主体落地且大部分设计点处理得比 design 更细**（例如 token/cost 记账点选 loop 层、`edge` 在派发点算、
`graph_distance` 独立 contextvar 不动 `spawn_depth`——grill 标的 3 个「照 design 字面实现会翻车」的
严重风险都真按 Q 结论绕开了）。19 项 tasks 无假勾选，8 个新测试文件覆盖各维度边界，兼容回归扎实。

但独立复现发现 4 个缺陷，其中 Issue 1/2 直接导致 spec delta 的两条 Scenario 在用户可配场景下**不可达**，
故不 PASS。

### 任务逐项验证（tasks.md 0.1–6.5）

| Task | 结论 | 证据 |
|------|------|------|
| 0.1 grill 追问 + Open Questions 停轮确认 | ✅ | `reviews/grill-design.md`：9 条 Confirmed Decisions + 16 条 Open Questions（Q1–Q16，含审阅员补充 Q12–Q16）+ 16 条 User Confirmation，非占位 |
| 1.1 `WorkflowBudget` 四维账本 + `WorkflowBudgetExceeded` | ✅ | `agent/subagent/workflow_budget.py:57-147`；四维 `0=不限`（`:112-120`）；`reserve_runs`（`:122-129`）；`to_dict` 带 used/limit（`:47-54`） |
| 1.2 调度器接线（建账本 / `_teardown` 结算 / loop 层记账 / C4 先于 C2） | ⚠️ | 建账本 `scheduler.py:546-551`；C4 先于 C2 `:994-1009`；**但 foreach 预扣路径完全绕过 C4**，见 Issue 2 |
| 1.3 超限状态机（显式闸 + 取消 queued + drain + 根节点 `budget_exceeded` + 不逃出 `run()`） | ⚠️ | 显式闸 `:650-652`、`:984-985`（真绕开了「`_accepting` 不 gate 派发」的坑）；`TERMINAL_NODE_STATUSES` 已加 `budget_exceeded`（`:70-73`）；**但权 `"runs"` 维度映射缺项 + 中途撞预算的节点状态规则分叉**，见 Issue 1/2b/2c |
| 2.1 `CostLedger.record` 增四键 + cache 参数；`bill()` 增四维 | ⚠️ | `cost_tracker.py:164-264`；四档按 `compute_cost_cached`（`:184-186`）、legacy 三维仍二档（`:180`）；**但 `bill()` 无 workflow 作用域→归因串账**，见 Issue 3 |
| 2.2 loop 层记归因键（一次查表） | ✅ | `loop.py:1068-1121` `_record_llm_cost`；`manager.attribution_for`（`manager.py:490-517`）走 `session.subagent_id → session 身份字段`一次查表（grill 决策 4） |
| 2.3 `SubagentRunRecord` 增 `edge` + `graph_distance` | ✅ | `manager.py:103-111`（字段）、`:700-708`（`_new_run` 读 contextvar）、`context.py:35-38,99-110`（新 contextvar）；`edge` 在 `scheduler._edge_for`（`:869-895`）派发点算出、`_launch_run` 透传（`:1449-1456`）——grill 决策 6 的「`_new_run` 推不出 edge」被正确绕过 |
| 2.4 修 C3 遗留：`_mark_budget_exceeded` 补填 usage | ✅ | `manager.py:1286-1298`；`BudgetTracker` 增 input/output 分量（`budget.py:55-62`）；三条收尾路径都传分量（`:1054-1071`）。⚠️ 有死分支（Round 2 已清，见「冗余清理」） |
| 3.1 动态 route `$ref` | ✅ | `workflow.py:83-113`（语法 + `declared_slots`）、`:813-838`（校验期「节点存在 + 槽已声明」）、`scheduler._route_case_label`（`:1756-1800`，先首行归一化再 `matches_route`、判定前不调 `bounded`）、`_note_route_ref_miss`（diagnostics 记原因） |
| 3.2 动态 foreach 跨层 source | ✅ | `scheduler._source_collection`（`:1900-1928`，只沿数据边、优先自身 result 槽、多入边歧义回退 `_node_output`）；环检测 `workflow._validate_foreach_source_cycles`（`:771-800`，复用 Tarjan SCC、在 `parse_workflow_spec` 校验期）；`source_field` 只应用一次（`:1890-1891`） |
| 3.3 `max_items=0` | ⚠️ | 单独非负解析函数 `_parse_max_items`（`workflow.py:574-586`，不动全局 `_positive_int`）；截断在 `_expand_plan` **之前**（`scheduler._resolve_items:1893-1898`）；上限取三者最小值（`:1930-1944`）。**但同一路径对 `max_items>0` 的展开不查 C4**，见 Issue 2 |
| 4.1 `WorkflowBudgetConfig` + 逐字段解析 + `0=不限` + 拒绝 `null` | ✅ | `config.py:280-295`（frozen dataclass）、`:1477-1512`（`_parse_workflow_budget`）、`:1624-1668`（`_parse_non_negative_int/float`，不动全局语义）；显式 `None` 被 `_expect_mapping`+类型检查拒 |
| 5.1 envelope 增 `budget` + `attribution` | ⚠️ | `_budget_summary`（`scheduler.py:956-965`）、`_attribution_summary`（`:906-944`，top-k + `counts` 显式报 omitted）；**但 attribution 无 workflow 作用域**，见 Issue 3 |
| 5.2 `GetWorkflow` detail + `WorkflowStore.save_attribution` | ⚠️ | `subagents.py:625-680`（`_DETAILS` 扩 `attribution`、非法值 `invalid_detail`）；`workflow_store.py:126-136` 原子写；**但落盘件是 top-k 摘要而非完整账单**，见 Issue 4 |
| 6.1 新增预算/归因/route/foreach 测试 | ✅ | 8 个新测试文件（约 1900 行）；`tests/agent/subagent/` + `test_cost_ledger.py` → 128 passed |
| 6.2 兼容回归 | ✅ | `test_budget_compat.py` 三条口径（三维账单不变 / C2 声明期校验不变 / `max_items>0` 保留 fail-fast）；既有 `test_foreach_run_budget_reports_graph_recursion_exceeded`、`test_auto_aggregates_consume_max_runs` 未破 |
| 6.3 benchmark smoke | ✅ | 我自跑：`asterwynd benchmark benchmarks/tasks --agent fake --source-repo .` → 72 tasks 执行完毕、无 crash |
| 6.4 spec sync | ✅ | `openspec/specs/multi-agent-collaboration/spec.md` 合入 4 Requirement + 9 Scenario（`git diff 32ea24f..HEAD`），与 spec delta 一致 |
| 6.5 全量 pytest + validate + checker | ✅ | 本 worktree 实测（Round 1 head）：pytest 2536 passed / 8 skipped；validate 30/30；checker 除「缺 building-review」外无其他错误 |

### Round 1 发现的 Issues

#### Issue 1 — 严重：`"runs"` 维度让 `KeyError` 逃出 `run()`（违反 spec Scenario「超限出口不逃出 run」）

`_raise_if_budget_exceeded` 的「维度 → 上限字段」映射只有 `tokens`/`cost_usd`/`wall_time_s` 三项，
但同函数调用的 `budget.exceeded_dimension(runs=self._runs)` **会返回 `"runs"`**（`workflow_budget.py:116-117`）。
触发路径真实存在：foreach 预扣把 `self._runs` 推过上限后（`_check_foreach_budget` 里 `self._runs += delta`），
下一次 `_dispatch` 调 `_check_budget_before_dispatch` → `_raise_if_budget_exceeded` → `{...}["runs"]` → `KeyError`。
`_dispatch` 只 `except WorkflowBudgetExceeded`，`_drive`/`run()` 只 `except GraphRecursionError`——`KeyError`
一路穿透 `run()`，父 agent 收到异常而非 envelope。

- 证据（Round 1 head `67d762b`）：`agent/subagent/scheduler.py:750-773`，映射表在 `:768-772`（缺 `"runs"` 键）。
- 复现（我自写脚本）：`max_total_runs=2` 的 `foreach + tail` 图 → `run()` 抛 `KeyError: 'runs'`，栈顶
  `scheduler.py:768 in _raise_if_budget_exceeded`。

#### Issue 2 — 严重：foreach 绕过 C4 `max_total_runs`（spec Scenario「runs 预算派发前预扣拒绝」不可达）

C4 的 runs 检查只在 `_dispatch`（`scheduler.py:994-1009`）。但 foreach 展开项经 `_run_foreach_item`
→ `_launch_run` **直接派发，不经 `_dispatch`**；而 `_check_foreach_budget`（`:1354-1398`）只查 C2 的
`spec.max_runs`/`spec.max_nodes`。于是当用户把 `budget.max_total_runs` 配得**小于** `spec.max_runs`（默认 300）时，
foreach 完全绕过 C4：

- 复现（我自写脚本）：`max_total_runs=3` + `foreach(items=10)` → `status=completed`、
  `budget.exceeded=False`、`dimensions.runs={limit:3, used:10}`——**envelope 自己就自相矛盾**（used > limit 却未超限）。
- 对照：同样 `max_total_runs=2` 的**链式**图正确报 `budget_exceeded`（`:994` 路径生效），证明缺口
  只在 foreach 的直达派发路径。

#### Issue 2b — 中：`_run_node` 撞预算时节点级状态规则与 `_teardown` 分叉（Q5）

Q5 确认「root（`plan.terminal`）未完成则改 `budget_exceeded`、非 root 仍 `blocked`」。
`_teardown`（`:609-626`）按此实现，但 `_run_node` 的 `WorkflowBudgetExceeded` 分支（`:1067-1072`）
把**所有**节点一律标 `blocked`。当 terminal 根节点本身已 `started`、在 LLM 调用后被预算抓住时，
它会被标 `blocked` 而非 `budget_exceeded`——`_unit_counts` 的 `budget_exceeded` 桶收不到它。

- 证据：`scheduler.py:1067-1072`（`state.status = "blocked"` 无条件）vs `:609-626`（`_teardown` 有 root 判定）。

#### Issue 2c — 中：envelope 的 `runs.used` 在预扣被拒时自相矛盾

pre-charge 拒绝时实际**没有**扣款（`self._runs += cost` 在 `:1029`，检查在其之前 return），
`_budget_summary`（`:956-965`）却直接报 `self._runs`，于是 `exceeded=true` 伴随 `used < limit`。
（这一条是我的修法引入的次生问题，与 Issue 2 同根，Round 2 一并修。）

#### Issue 3 — 严重：workflow 归因摘要跨 workflow 串账（违反 D7/Q15「本 workflow 的 attribution」）

`CostLedger` 是被同一个 manager 跨 workflow 共享的实例（子 loop 都用 `manager.cost_ledger`），
而 `bill()` 的 by_node/by_edge 是**全局累加**——不同 workflow 的 node id / edge 串会重名。
`_attribution_summary` 直接读 `ledger.bill()`（无过滤），于是本 workflow 的 attribution 快照
**把之前所有 workflow 的成本都算进来**。

- 复现（我自写脚本）：同一 manager 顺序跑两次单节点 workflow `n0` →
  第一次 `attribution.by_node.n0.cost = 0.00021`，第二次 = `0.00042`（= 两次之和，而非第二次自身）。

#### Issue 4 — 严重：`attribution_ref` 落盘件是 top-k 摘要而非完整账单（违反 D7/Q15）

D7/Q15 口径：envelope 只回 bounded 摘要，**完整**归因走 `attribution_ref` 落盘件（父按需 inspect）。
但 `_write_attribution`（`:899-911`）落盘的就是 `_attribution_summary()`——同一份 top-k 截断件。
超过 k=5 个 node/edge 的部分**永久取不回**。

- 复现（我自写脚本）：8 节点图 → envelope `by_node` 5 键 + `by_node_omitted: 3`；
  从 `attribution_ref` 读回落盘件，`by_node` 仍只有 5 键——被省略的 3 个节点在落盘件里也缺失。

### Round 1 通过的核验点（特别关注 4 条）

1. **legacy 三维 vs 四维归因的 cost 口径分叉**：**判定合理，非缺陷**。四维分桶走 `compute_cost_cached`
   四档（cache-aware），legacy 三维仍走二档 `compute_cost`——后者被既有断言
   `tests/benchmark/test_observability_quantification.py:54`（未知模型→三维账单记 0 成本）锁定，
   而 Q12 只要求「by_node/by_edge 与 workflow 账本对得上」，并未要求改三维账单。Q12 四项要求
   （①workflow 账本权威 ②`record` 扩 cache 参数 ③修 `_mark_budget_exceeded` 写 0 ④不要求两份账相等）
   **逐条落地**：①见 `workflow_budget.record_llm_call:77-100`；②见 `cost_tracker.record:164-203`；
   ③见 `manager.py:1286-1298`。`bill()` 的 by_node/by_edge 与 workflow 账本用的是同一套
   `compute_cost_cached`、同一批 usage——**口径一致、不会对不上**（我已用脚本核对同一 run 的两处 cost 相等）。
2. **spec sync 的受保护事件**：**判定「留 closing 补」成立，building 阶段不拦截**。核验事实：
   - **(a) checker 不拦截，但绿灯是历史事件兜底。** `_protected_artifact_explanation_errors`
     （`scripts/check_openspec_artifacts.py:1106-1141`）只要**任一** `workflow-events.jsonl` 里有覆盖该路径的
     合法事件即返回 `[]`。我实测：覆盖 `openspec/specs/multi-agent-collaboration/spec.md` 的
     `current_spec_synced` 事件来自 4 个**已归档** change（`multi-agent-collaboration`、C2、C3、
     `subagent-concurrency-queue`），**没有一条来自 C4**——即本 change 对该受保护路径的修改目前无自己的解释。
   - **(b) guard 的 CLI 通道在本 flow 不可用。** `scripts/workflow_guard.py` 把 `workflow-events.jsonl`
     列为 `cli_written`（只准 CLI 写），但 `workflow_state.py artifact-event`（`cmd_artifact_event`）
     硬性要求 change 目录有 `handoff.json`——本 change 没有（新流程不再产出 handoff.json），
     故 CLI 直接拒绝：「change 'workflow-budget-attribution' 没有 handoff.json」。
   - **(c) C2/C3 先例确为 closing 创建。** `git show --summary b419e83` / `--stat 2fb74a0`：两代都在
     **closing commit**（= 归档 spec sync + backlog + `workflow-events.jsonl` 的同一提交）里
     `create mode` 出该文件，且当时都没有 handoff.json。C4 只是把 spec sync 提前到 building commit
     `67d762b`（tasks 6.4 归在「测试与收尾」），**事件本身仍应随 closing 的归档动作一并写**。
   - **结论**：不构成 building 阶段的缺陷；但它是 **closing 的硬性义务**——归档 C4 时必须在本 change 的
     `workflow-events.jsonl` 写 `current_spec_synced`（+ `backlog_updated` + `change_archived`），
     格式对齐 C2/C3。若届时漏写，checker 仍会因历史事件兜底而绿灯（掩盖问题），
     故这里显式记入「Round 2 残留/移交项」。**我不在 building 阶段手工写该文件**：它是 `cli_written`
     治理路径，CLI 通道不可用时手工写属治理偏离，且与 C2/C3 先例不符。
3. **runs 计数器复用 `self._runs` + C4/C2 顺序 + foreach 预扣**：顺序正确（C4 在 C2 之前，同值由 C4
   触发 drain，`test_c2_max_runs_still_wins_when_explicitly_smaller` 锁定反向）；计数器复用正确
   （单一 `self._runs`，无第二计数器漂移）；**但 foreach 预扣路径漏接 C4**，即 Issue 2。
4. **`budget_exceeded` 节点级状态 + `_unit_counts` 桶**：`TERMINAL_NODE_STATUSES` **已**加
   `budget_exceeded`（`scheduler.py:70-73`）；`_unit_counts` 的 `budget_exceeded_units` 分支**已接上**
   （`:1885,1899-1900`）；与 `blocked` **不抢位**（`if/elif` 互斥，`:1893-1904`）。判定正确，但
   Issue 2b 指出「中途撞预算的 root」会绕过这个桶。

### 安全性 / 可维护性 / 冗余度（Round 1）

- **安全**：`$ref`/跨层 source/`max_items=0` 三条新路径均**不执行模型生成代码**——`$ref` 只读
  `NodeState.slots`（`scheduler.py:1786-1794`，不走 `_node_output` 跨节点回退、不落盘不读文件）；
  跨层 source 只沿已声明的数据边迭代、有 `visited` 环终止（`:1900-1928`）；`max_items=0` 的截断是纯算术。
  `grep -E "\beval\(|\bexec\(|__import__"` 在新代码零命中。落盘路径走 `WorkflowStore.path_for` 的
  段级白名单 + 逃逸拒绝（C3 既有）。无预算绕过面（除 Issue 2）。
- **可维护性**：分层清晰——`WorkflowBudget` 只管账本 + 判定、`scheduler` 管执行与接线、`CostLedger`
  管财务记账，依赖方向无环（`workflow_budget.py` 明写不 import 调度器/manager）。
- **冗余度**：整体无重复实现。两处小冗余（Round 2 已清）：`_mark_budget_exceeded` 的
  `if input_tokens is None and output_tokens is None` 与外层 `resolved_input` 赋值重复；
  `_enforce_c4_runs` 复刻了 `WorkflowBudget.reserve_runs` 的上限判定。

### Round 1 门禁输出

- `uv run pytest -q` → **2536 passed, 8 skipped**（178s）
- `npx openspec validate --all --strict` → **30 passed, 0 failed**
- `check_openspec_artifacts.py --base-ref master` → 仅 1 条 `building-review.md missing`（本报告补齐）

---

## Round 2 复审（2026-09-14，verdict = PASS）

修复 commit：`443e1ff`（6 files）。修法与 Round 1 issue 的对应：

| Issue | 修法 | 位置（Round 2 head `443e1ff`） | 回归测试 |
|-------|------|------|---------|
| 1（`runs` KeyError 逃出） | 映射表补全为四维 dict（含 `"runs": (self._runs, budget.max_runs)`），异常构造收口到单点 | `agent/subagent/scheduler.py:773-796` | `tests/agent/subagent/test_workflow_budget.py:359`（4 维参数化） |
| 2（foreach 绕过 C4） | 抽 `_enforce_c4_runs` 作**唯一**预扣落点；`_execute_foreach` 在 `_expand_plan` **之前**用同一 `delta`（与 `_charged_expansions` 同源）检查 | `agent/subagent/scheduler.py:748-770`、`:1319-1327` | `test_workflow_budget.py:386`（10 项全不跑、`completed==0`）、`:428`（不逃出 `run()`） |
| 2b（节点状态规则分叉） | 抽 `_apply_budget_exhausted_status`，`_teardown` 与 `_run_node` 共用同一 Q5 规则 | `agent/subagent/scheduler.py:819-840`（调用点 `:615-623`、`:1085`） | `test_workflow_budget.py:386`（`fan == budget_exceeded`）、`:428`（`tail == budget_exceeded`） |
| 2c（envelope 自洽） | `_budget_summary` 的 runs.used 取「实际累计 vs 触发拒绝的预扣值」较大者 | `agent/subagent/scheduler.py:996-1013` | `test_workflow_budget.py:386`（断言 `used > limit`） |
| 3（归因串账） | `CostLedger.bill()` 增 `workflow_id` 过滤参数；`_attribution_summary` 按 `self.workflow_id` 取 | `agent/cost_tracker.py:211-263`、`scheduler.py:909-932` | `tests/agent/test_cost_ledger.py:227`、`tests/agent/subagent/test_cost_attribution_runtime.py:276` |
| 4（落盘件被截断） | 拆 `_attribution_full`（不截断）供落盘，envelope 仍用 `_attribution_summary`（top-k） | `agent/subagent/scheduler.py:934-990` | `test_cost_attribution_runtime.py:302`（落盘 8 键 vs 摘要 5 键） |
| 冗余清理 | `_mark_budget_exceeded` 死分支删；`_enforce_c4_runs` 委托 `WorkflowBudget.reserve_runs`（上限语义单点定义） | `agent/subagent/manager.py:1286-1298`、`scheduler.py:759-770` | 既有 `test_budget_snapshot.py` 覆盖 |

特别关注 2（spec sync 事件）经复核**不是 building 缺陷**（checker 由历史事件兜底、guard CLI 需
handoff.json 不可用、C2/C3 先例为 closing 创建），故不在 Round 2 修复集内——详见上方「Round 1 通过的
核验点」第 2 条与「Round 2 残留」。

### Round 2 独立复现（不采信实现 agent 的 claim，全部自写脚本重跑）

1. **Issue 1**：`_raise_if_budget_exceeded` 单测四维参数化 → 全通过；纯 asyncio 脚本 `foreach+tail` +
   `max_total_runs=2` → 返回 envelope（`status=budget_exceeded`），**不再抛 `KeyError`**。
2. **Issue 2**：纯 asyncio 脚本 `foreach(items=10)` + `max_total_runs=3` →
   修复前 `status=completed / exceeded=False / used=10`；修复后 `status=budget_exceeded /
   exceeded=True / exceeded_dimension=runs / used=10 > limit=3 / completed==0`（**零展开项被跑**）。
3. **Issue 3**：同 manager 顺序跑两次 `n0` → 修复前 `0.00021 / 0.00042`（翻倍）；修复后
   `0.00021 / 0.00021`（相等），`by_workflow` 只含本 workflow id。
4. **Issue 4**：8 节点图 → envelope `by_node` 5 键 + `by_node_omitted=3`；从 `attribution_ref`
   读回落盘件 → **8 键齐全**（`store.path_for(ref)` 真读文件）。同时核验 `GetWorkflow(detail="attribution")`
   端到端返回 `attribution_ref`、非法 detail 返回 `invalid_detail`。
5. **spec sync 事件**：复核确认「留 closing」成立（C2/C3 先例 + CLI 通道需 handoff.json 不可用 +
   checker 由历史事件兜底），building 阶段不手工写；已作为 **closing 硬性义务**记入「Round 2 残留」。

### Round 2 门禁输出（head `443e1ff`）

- `uv run pytest -q` → **2545 passed, 8 skipped**（178s，比 Round 1 多 9 例 = 新增回归测试）
- `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` → **30 passed, 0 failed**
- `check_openspec_artifacts.py --base-ref master` → **passed**（本报告 + manifest 补齐后重跑）
- `uv run asterwynd benchmark benchmarks/tasks --agent fake --source-repo .` → 72 tasks 执行完毕、无 crash

### Round 2 残留（不阻塞 PASS，供 closing 参考）

- **closing 硬性义务（移交项）**：归档 C4 时必须在本 change 的 `workflow-events.jsonl` 写
  `current_spec_synced`（`artifact_path=openspec/specs/multi-agent-collaboration/spec.md`，reason 逐条列
  ADDED 4 条）、`backlog_updated`、`change_archived` 三条结构化事件，对齐 C2/C3 的 closing 先例
  （`b419e83` / `2fb74a0`）。当前 C4 对该受保护路径的改动**无自己的解释事件**，仅靠历史 change 的
  归档事件让 checker 绿灯——若 closing 漏写，此债会随 change 归档固化。
- `tests/agent/subagent/test_cost_attribution_runtime.py` 等用例收尾时 pytest 打印
  `Task was destroyed but it is pending!`（`manager._execute_run_in_context`）——是既有测试清理时序
  噪音，非本 change 引入，全量套件不受影响（Round 1 也有）。属既有债务，本 change 不扩范围处理。
- 三处 `max_runs=300` 默认值（`config.WorkflowLimitsConfig` / `_parse_workflow_limits` 的
  `mapping.get` / `workflow.DEFAULT_MAX_RUNS` / 新增 `WorkflowBudgetConfig.max_total_runs`）仍是四处
  独立字面量。grill 已把它列为「低：可能漂移」，本 change 按 Q4/Q14 保持它们同值，未引入单点常量——
  **维持现状**（改动面超出本 change 范围），建议后续 change 收敛。
