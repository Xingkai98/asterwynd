# Building Review: workflow-terminal-honesty

- **审阅者**: 独立零记忆 subagent（不继承开发上下文）
- **审阅时间**: 2026-09-19
- **审阅对象**: `git diff f7a248655033ee3f035b79915a1cc4bff69082db...644c7be`（base = merge-base with origin/master）
- **审阅期间工作区前进**: 审阅开始时 HEAD 为 `0b2181d`，期间实现方追加 `78cd082` / `5f15593` / `6a7819f` / `644c7be` 四个提交。本报告以 **最终 HEAD `644c7be`** 为准，此前基于 `0b2181d` 发现的两条问题中 **Issue 1 已被 `644c7be` 修复**（见下），Issue 2 仍存在。
- **工作区**: `/home/happy/.paseo/worktrees/0frj3kg8/workflow-terminal-honesty-2026-09-19`

## Verdict

**CHANGES_REQUESTED**

实现主体质量高：四档判据、因由分档、方案 D、三副本同步、前端 Q4 优先级全部真实落地且可被变异杀死；审阅者独立复核的 12 个变异全部 KILLED。但存在 **1 条未修复的中等问题**（Issue 2，benchmark 消费方漂移，会静默把「图没跑起来」判为通过——恰是本 change 要消灭的那类假话）和 1 条低等问题（Issue 3，跨层文案契约无测试锁定）。二者均不阻塞功能正确性，但 Issue 2 触及本 change 的核心命题，PR 前应修。

## Tasks Verification

逐条核对 `tasks.md` 的 `[x]`（读代码确认，非只看文件名）。**所有 1.1–6.3 均有真实实现**。

### 第 0 节（立项，主 session）

| 任务 | 实现 | 证据 |
|---|---|---|
| 0.1 业界调研 | ✅ | `proposal.md:97-119` RIR 全字段（Airflow `all_tasks_deadlocked` / Prefect / Argo `Omitted` 三条 findings + design impact + 本地参考仓库不可用说明） |
| 0.2 三 bug 复现 | ✅ | `diagnosis.md` Symptom/Reproduction/Evidence 三节；Evidence 含实测输出块 |
| 0.3 proposal/design/tasks/spec delta | ✅ | 四份文档齐全，`specs/web-ui/spec.md` 3 MODIFIED + 1 ADDED |
| 0.4 backlog + 事件 | ✅ | `docs/openspec-change-backlog.md:104-114`；`workflow-events.jsonl` 1 条 `backlog_updated` |
| 0.5 validate + checker | ✅ | 实测 `openspec validate workflow-terminal-honesty --strict` → `is valid`；`check_openspec_artifacts.py` → `passed` |
| 0.6 grill | ✅ | `reviews/grill-design.md` 6 Confirmed Decisions + 5 Open Questions + User Confirmation 5 条 |
| 0.7.1–0.7.6 立项修正 | ✅ | 逐条核对：User Confirmation 5 条已回填（`grill-design.md:95-99`）；spec delta 标题已改为目标 spec 既有名（见下）；`diagnosis.md:41` 已更正 #220 复现 spec；D5 三副本表述已更正；D2/D4/D3/D6 均已回写 |

**spec delta 标题逐字匹配核对**（grill 风险 1）：delta 的 4 个标题
`workflow 图级终态区分「有失败」` / `workflow 节点异常态语义表达` / `workflow 未选中分支状态（skipped）`
在 `openspec/specs/web-ui/spec.md` 中分别命中 `:685` / `:702` / `:649`；第 4 条
`回边重跑不得清空本次派发的发起者` 在 `## ADDED Requirements` 下、目标 spec 无同名条目 → **匹配正确**，`archive` 不会再报 `MODIFIED failed for header`。

### 第 1 节（复现与回归测试）

| 任务 | 测试 | 证据 |
|---|---|---|
| 1.1 #217 | `test_deadlock_graph_is_not_completed`（`test_terminal_honesty.py:148-153`）| 实跑 `_deadlock_spec()`，断言 `!= "completed"` 且 `== "stalled"` |
| 1.2 #218A | `test_route_cap_reason_pierces_graph_gate`（`:275-282`）| 断言图级 `graph_recursion_exceeded` + 节点 reason 含 `max_routes` |
| 1.3 #218B | `test_deadlock_reason_is_not_the_fallback_lie`（`:285-300`）| 先断 `not snapshot.get("diagnostics")`，再逐 blocked 节点断 `"workflow ended before" not in reason` |
| 1.4 #220 | `test_back_edge_does_not_wipe_the_dispatching_route`（`:308-319`）| `_spin_spec()` 的 `default` 确为 `body`（`test_terminal_honesty.py:109`），断言 gate `completed` + `targets==['body']` + 边 `passed` |
| 1.5 方案 D 组合回归 | `test_selected_and_executed_node_is_not_reported_skipped`（`:322-339`）| 先断前提（`targets` 含 body、`runs>0`），再断 `status != skipped` + reason 不含 `route did not select this branch`。**组合断言成立**（1.4 与 1.5 一起跑，只做豁免的中间态会红——见 Mutation M9） |

### 第 2 节（图级终态四档）

| 任务 | 证据 |
|---|---|
| 2.1 四档 | `scheduler.py:1238-1271`：`completed>0 and failed>0` → `completed_with_failures`；`completed>0` → `completed`；`failed>0` → `failed`；否则 `stalled`。**四档互斥且穷尽**（后三档覆盖 `completed==0` 的全部分支） |
| 2.2 口径 | `:1267-1269` 用 `sum(1 for state in states if state.status == "completed")`，是**节点**数、不含 `skipped`（`skipped` 是独立字符串，不参与计数）。**未复用 `_unit_counts()`**——与 D1 的口径澄清一致 |
| 2.3 调用点 | `:888` 仍在 `if self._budget_stop: ... else: self._status = self._terminal_converged_status()` 的 else 分支内。`test_budget_stop_wins_over_stalled`（`:225-267`）用「总返回 stalled」的探针把「调用点被移出 else」钉死，并断 `calls == []` |
| 2.4 边界矩阵 | 5 格齐全：`:180`（1 格）、`:170`（2 格）、`:203`（3 格）、`:149`（4 格）、`:225`（预算优先）。**第 3 格在首轮缺失**（见 `diagnosis.md` Mutation Verification 的 M3 说明），已由 `b2691ed` 补上 |

### 第 3 节（节点因由分档）

| 任务 | 证据 |
|---|---|
| 3.1 三档 | `scheduler.py:1328-1361` `_blocked_reason`：闸门穿透 / 入边互等 / 兜底三支；调用点 `:1326` `state.reason = state.reason or self._blocked_reason(state)`（保留既有 reason 优先） |
| 3.2 闸门穿透 | `:1352-1357`，注入 `diagnostics.reason` + `diagnostics.message`，`detail = message[:_SUMMARY_LIMIT]`（400，`scheduler.py:95`） |
| 3.3 入边互等 | `:1359-1360` + `_waiting_upstreams`（`:1363-1378`）列未就绪上游 id |
| 3.4 `state.reason` 语义不变 | `:1326` 仍走 `state.reason or ...`；截断只在 `_blocked_reason` 的**文案构造**里（不是改 `_envelope` 字段本身）；节点投影另有 `:2689-2691` 的 `[:_SUMMARY_LIMIT]` 出口截断 |

### 第 4 节（方案 D）

| 任务 | 证据 |
|---|---|
| 4.1 origin 参数 | `_reset_subtree(self, state, *, origin=None)`（`:1603`），`:1619` 提前 return |
| 4.2 三处调用点 | `:1601`（`_on_node_finished`）、`:1635`（自身递归）、`:1726`（`_execute_route` 派发循环）**全部透传**。`grep -n "_reset_subtree" agent/ web/ tests/` 确认只有这 3 处调用。**M7 变异证实 `:1726` 是生效关键**（见下） |
| 4.3 `_is_skipped` 条件 2 | `:1416-1418` `if node_id in source.targets: return False`，位于 `source.status != "completed"` 检查之后、数据上游「被连累」检查之前。**只读既有字段，无新记账** |
| 4.4 不做顺序调整 | 无相关代码改动；`design.md:103` 记录了否决理由与实测 |
| 4.5 G11 红线 | `:1623-1632` 仍逐一清 `status`/`activations`/`deadline_fired`/`verdict`/`targets`/`reason`/`error`/`summary`/`finished_at` 共 9 项，**只加了 `:1619` 的豁免 return，未减任何清理项**（读 diff 逐行确认） |
| 4.6 G11 回归 | `test_rerun_clears_stale_reason_and_finished_at`（`test_workflow_semantics_m1.py:364`）实测绿；本 change 另加 `test_reset_subtree_still_clears_stale_fields_on_rerun`（`test_terminal_honesty.py:358`） |

### 第 5 节（契约同步与用户可见性）

| 任务 | 证据 |
|---|---|
| 5.1 `_SNAPSHOT_TERMINAL_STATUSES` | `scheduler.py:117-119` 含 `stalled` |
| 5.2 `workflow.js` 数组 | `workflow.js:22-23` 含 `stalled` |
| 5.3 `isGraphTerminal()` | `workflow_graph.js:1038-1041` 含 `status === 'stalled'` |
| 5.4 三副本**集合相等** | `test_graph_terminal_status_copies_are_equal`（`:404-441`）。**审阅者独立复算三集合**：三份均为 `{budget_exceeded, cancelled, completed, completed_with_failures, failed, graph_recursion_exceeded, stalled}`，`SET-EQUAL: True`。是**真集合相等**断言（`values[0] == values[1] == values[2]`），不是各自「包含 stalled」 |
| 5.5 配色/文案/图例 | 色 `#92400e`（`workflow_graph.js:108`）；label `停滞（无节点完成）`（`:119`）；`GRAPH_STATUS_TEXT.stalled`（`:202`）；图例单列 `图状态` 一节（`workflow.js:334` + `legendGraphStatusItem` `:392`） |
| 5.6 前端测试 | `test_stalled_color_is_distinguishable_from_every_existing_graph_status`（`:161-174`）断 RGB 欧氏距离 ≥ 100；`test_stalled_color_does_not_reuse_budget_exceeded_orange`（`:177-181`）。**独立复算**：`#92400e` 到最近的 `graph_recursion_exceeded #f472b6` 距离 ≈ 140.7，全部 ≥ 100 |
| 5.7 Q4 优先级 | `workflow_graph.js:875` `if (isSpecificNodeReason(node.reason)) return truncateText(node.reason, 160);` 位于 `GRAPH_STOP_REASONS`（`:877`）与 `blockingUpstreams`（`:880`）**之前** |
| 5.8 Q4 验收 | `test_route_cap_reason_reaches_the_user_visible_text`（`:82`）+ `test_deadlock_reason_states_mutual_wait_not_upstream`（`:95`）。**断言的是 `explainNode()` 的返回值**（用户实际看到的那句），不是 `state.reason` |
| 5.9 消费方清单 | `test_stalled_is_treated_as_non_success_by_every_consumer`（`:402`）+ `benchmarks/runner.py:1043` 补 `stalled`。**但清单不完整**——见 Issue 2 |

### 第 6 节（验证与收尾）

| 任务 | 状态 |
|---|---|
| 6.1 变异验证 | ✅ 声明见 `diagnosis.md` 的 Mutation Verification 表（16 项）。**审阅者独立复跑 12 项，全部复现**（详见下节） |
| 6.2 subagent + web_tests 全量 | ✅ 实测 `tests/agent/subagent/` 482 passed；`tests/web_tests/` 338 passed（1 条与本次无关的 chrome-flaky 见 Test Results） |
| 6.3 全量 pytest | ✅ 实测 2938 passed, 2 failed（两条均为浏览器 flaky，单跑复现为绿） |
| 6.4–6.9 | 未勾选，**不在本次审阅范围**（收尾阶段任务） |

### 第 7 节

`#219` 正确标注为「不在本 change 范围」，非勾选项（`tasks.md:80-82`），**不算缺陷**。

## Issues

### Issue 1（中）：非闸门诊断被当作图级闸门 → 节点因由写出一次**未发生**的闸门 — ✅ **已由 `644c7be` 修复**

**位置**: `agent/subagent/scheduler.py:1344`（旧版 `if self._diagnostics:`）

**根因（审阅者独立复现）**：`_diagnostics` 不只在图级闸门触发时被填充。`_note_route_ref_miss`（`scheduler.py:2389-2391`）会把 `$ref` 槽未命中的**良性**诊断写进同一个 `_diagnostics` 字典——而这条路径恰好是 `tests/agent/subagent/test_dynamic_route.py:269` 明确要求存在的行为。旧实现按「`_diagnostics` 非空」判闸门，于是：

```
$ uv run python /tmp/repro_final.py     # 一个 $ref 未命中 + 一个无关的死锁
graph status : completed
diagnostics  : {"route_ref_misses": [{"route": "gate", "when": "$ref:producer:verdict",
                 "reason": "slot 'verdict' not materialised on 'producer'"}]}
  cycle_gate  blocked   reason='图级闸门 图级闸门 触发，本节点未派发'   ← 闸门名重复 + 闸门根本没发生
```

两个后果叠加：(a) **说了一次没发生的闸门**（`reason` 键不存在，`gate = reason or "图级闸门"` 退化成占位串）；(b) 该假话会经前端 `isSpecificNodeReason` 提权（`SPECIFIC_REASON_MARKERS` 命中 `图级闸门`），用户看到的就是「图级闸门 图级闸门 触发」这句坏文本。**这正是本 change 要消灭的那类假话，属于自伤**。

**修复核验（审阅者实测）**：`644c7be` 把判定改为 `reason = str(self._diagnostics.get("reason") or "").strip(); if reason:`。闸门诊断的唯一写入点 `_mark_graph_recursion_exceeded`（`:787`）走 `exc.to_dict()`，而 `GraphRecursionError.to_dict()`（`:171-181`）**必带** `reason` 键 → 判据与「闸门真的触发过」等价。同一 repro 复跑：

```
  cycle_gate  blocked   reason='入边互相等待（body），本节点永远未就绪'   ← 落到结构性成因
```

并补了 `test_non_gate_diagnostics_do_not_claim_a_graph_gate_fired`（`test_terminal_honesty.py:320-339`）。**我按 `644c7be` 前的旧实现复现了红、按新实现复现了绿**，修复有效。此条关闭，但记入本节以说明审阅期曾发现问题。

### Issue 2（中）：benchmark 有一个**「黑名单式」**消费方漏加 `stalled`，会把「图没跑起来」静默判为通过

**位置**: `benchmarks/workflow_e2e.py:41-43`

本 change 需要同步的**图级终态消费方其实有四类**（不是 spec/proposal 说的「三副本 + GetWorkflow/benchmark」那么笼统）。其中两个 benchmark 判据同名同义，**只同步了一个**：

| 文件 | 集合 | 语义 |
|---|---|---|
| `benchmarks/runner.py:1043-1045` | `{graph_recursion_exceeded, cancelled, error, declared, stalled}` | ✅ `644c7be` 已补 `stalled` |
| `benchmarks/workflow_e2e.py:41-43` | `{graph_recursion_exceeded, cancelled, error, declared}` | ❌ **缺 `stalled`**（`643c7be` 未触及） |

二者都是**黑名单**（`status not in SET` → 判「干净完成」），所以漏一档不是「多报一个异常」而是**少报一个异常**。`_status_comparable`（`workflow_e2e.py:133-147`）在 fake 场景下断 `_workflow_completed_cleanly(record)` 与 `_workflow_completed_cleanly(replay)`——判据是 `bool(status) and status not in UNHEALTHY_WORKFLOW_STATUSES`。

**实测影响**（审阅者跑的对照）：

```
$ uv run python -c "from benchmarks.workflow_e2e import _status_comparable, _workflow_completed_cleanly"
_workflow_completed_cleanly('stalled')  = True      ← stalled 被判「干净完成」
_status_comparable('completed','stalled') = True    ← record 干净 + replay 零节点成功 → 判「两侧一致，通过」
_status_comparable('failed','stalled')    = True    ← 同样判「两侧一致」
```

对照 `_replay_completed_cleanly`（`runner.py`，已补 `stalled`）返回 `False`——**同仓库两个同名判据对同一输入给出相反结论**。这正是本 change 的 Impact Analysis 与 spec 正文（`specs/web-ui/spec.md:14`）明确禁止的形态：「消费方 SHALL NOT 用『`status == "failed"` 才算失败』判定整图结果（该写法会把 `stalled` 悄悄算成成功，等于换一种骗法）」。

`benchmarks/workflow_e2e.py` 是 `compare_record_and_replay` 的宿主，被 `benchmarks/runner.py` 的 `_annotate_e2e_verification` 调用，是 C5 e2e 回放链路的判据宿主。

**建议**：`benchmarks/workflow_e2e.py:41` 加 `"stalled"`（与 `runner.py:1043` 逐字一致），并在 `tests/benchmark/test_workflow_modes.py` 里对 `UNHEALTHY_WORKFLOW_STATUSES` 也补一条与 `_REPLAY_UNHEALTHY_STATUSES` 同构的断言；更根本的做法是把两处集合抽成**单一源**（`workflow_e2e.py` 已被 `runner.py` import，反向引用会成环，可下沉到 `benchmarks/models.py`），否则「新增档位要同步 N 个黑名单」这个坑还会再踩（本 change 已在 `runner.py` 和前端三副本上各踩过一次）。

### Issue 3（低）：前后端因由标记是**字符串耦合**，无任何测试锁定

**位置**: `agent/subagent/scheduler.py:1356-1357`（后端产出 `图级闸门` / `入边互相等待`） ↔ `web/static/workflow_graph.js:892`（`SPECIFIC_REASON_MARKERS` 硬编码同样两个字面串）

前端判断「这条 reason 是否携带具体成因」靠的是 `value.includes('图级闸门')`，即**后端的文案前缀是前端的协议**。但这是一个**无人测试的隐式契约**：

```
# 变异：后端把前缀改成「图形层限制」（措辞微调，语义不变）
$ pytest tests/agent/subagent/test_terminal_honesty.py tests/web_tests/test_terminal_honesty_js.py -q
26 passed    ← 全绿，没有任何测试发现前后端已脱钩
```

后果的严重度低于 Issue 1（后端仍写对文案，只是前端会退回泛化路径），但它是 Issue 1 那类「后端修了、前端看不到」问题的**复发通道**——正是 Q4 用户拍板要防的事。另注：`test_terminal_honesty_js.py` 的 `_max_routes_snapshot()`（`:51-64`）用的是**手写** reason 串，不是 `_blocked_reason` 的真实输出，所以后端措辞变化不会传导到该测试。

**建议**（二选一，均为小改）：(a) 后端把标记做成显式结构化字段（如 `state.reason_code = "graph_gate" | "mutual_wait"`）而非文案前缀，前端读字段；(b) 若维持文案耦合，补一条跨层测试：从 `_blocked_reason` 的真实输出里抽取前缀，断言它出现在 `SPECIFIC_REASON_MARKERS` 中（同构于 `test_graph_terminal_status_copies_are_equal` 的源文本抽取范式）。

### Issue 4（低，记录）：图级闸门 `recursion_limit` 的因由会顶满前端 160 字符预算，尾部被切

**位置**: `scheduler.py:1348`（`message[:_SUMMARY_LIMIT]`，400） ↔ `workflow_graph.js:875`（`truncateText(node.reason, 160)`）

D3 的设计要求是「按前端展示预算压缩，SHALL NOT 直接塞入整段异常文本（否则关键信息会被 160 字符切掉）」。实测：`max_routes` 形态 93 字符（OK），但 `recursion_limit` 形态的 `message` 会列出全部 ready 节点：

```
$ node /tmp/jsprobe3.js
backend reason len : 299
user-visible text  : 图级闸门 recursion_limit 触发（GraphRecursionError: workflow reached recursion_limit 25
                     supersteps; ready nodes: ['worker_0', 'worker_1', 'worker_2', 'worker_3', 'wor…
tail preserved?    : false      ← 「本节点未派发」被切掉
```

关键信息（闸门名 + 上限）仍在，所以用户仍能定位问题，**未构成假话**，故只记低。但设计里「SHALL NOT 直接塞入整段异常文本」这条没被完全遵守，且 `max_routes` 的 93 字符余量说明这是**取值依赖**的（换个更宽的上游列表就超）。建议在 `_blocked_reason` 里对 `message` 再加一道更紧的上界（如 80），或只保留 `reason` + `limit`。

### 非问题（审阅者主动核查后排除）

- **`_waiting_upstreams` 的过滤条件（只列 `blocked`/`pending`/`skipped`）是否误伤**：核查后认为**合理**。`completed` 上游说明这条边送过数据、「互等」不成立；`failed`/`cancelled` 已有独立语义（被连累优先），会有自己的因由通道——把它们纳入会让「被上游失败挡住」与「入边互等」两类成因再度混为一谈（正是 #218 要消灭的）。对「只有部分入边互等」的图，文案「入边互相等待」略宽于实际（只有子集在互等），属可接受的措辞近似，**不记为缺陷**。
- **`_is_skipped` 条件 2 与「被连累优先于未选中」是否冲突**：核查后认为**不冲突**。条件 2 在 `return False`（不是 skipped）后，控制流会继续走到数据上游的「被连累」检查——两条路径都指向「不是 skipped」，语义同向，无矛盾。
- **`_reset_subtree` 的 origin 豁免是否会漏清本该清的节点**：核查后认为**不会**。豁免只对 `state.node.id == origin` 生效，而 `origin` 是**本次派发链的发起者**（刚完成、正在写结果的节点）；其它环上节点沿 `data_outgoing` 递归时逐层透传同一个 `origin`，只要 id 不等就不会提前 return。G11 的 9 项清理逐行确认未减。
- **XSS / 注入**：核查后认为**无风险**。注入到 `state.reason` 的 `diagnostics.message` 全链路走 DOM `textContent`（`workflow.js:365/370` `legendItem`、`:1105-1112` `kvRow`、`:861-866` 节点小字），无 `innerHTML`；`svgEl('title')` 也走 `textContent`。同源内容（本地 scheduler 产出）不构成越权面。
- **CI 配置弱化**：核查后认为**无**。diff 未触及 `.github/`、`scripts/`、`pyproject.toml`、`flow/`（`git diff --name-only | grep -E "\.github|scripts/|pyproject|flow/"` 为空）。

## Mutation Spot-Check

审阅者**独立动手**跑了 12 个变异（改坏实现 → 跑目标测试 → 期望变红 → 还原），不是只读文档。文件每次用 md5 校验还原（`scheduler.py` 恒为 `52979333…`，`workflow_graph.js` 恒为 `50149b43…`）。

| # | 变异 | 目标测试 | 期望 | 实际 | 结论 |
|---|---|---|---|---|---|
| M1 | `stalled` 分支改返回 `completed` | `test_deadlock_graph_is_not_completed` | 红 | `assert 'completed' != 'completed'` → FAILED | ✅ 杀死 |
| M2 | 去掉 origin 豁免 `return` | `test_back_edge_does_not_wipe_the_dispatching_route` | 红 | `+ blocked` → FAILED | ✅ 杀死 |
| M3 | 去掉 `_is_skipped` 条件 2 | `test_selected_and_executed_node_is_not_reported_skipped` | 红 | `assert 'skipped' != 'skipped'` → FAILED | ✅ 杀死 |
| M4 | `workflow.js` 副本去掉 `stalled` | 三副本等价 | 红 | `Extra items in the left set: 'stalled'` | ✅ 杀死 |
| M5 | 前端优先级 0 提权删除 | Q4 两条 | 红 | `'被上游 body 挡住，未执行'` → 2 FAILED | ✅ 杀死 |
| M6 | **仅** scheduler 副本去掉 `stalled` | 三副本等价 | 红 | `Extra items in the right set: 'stalled'` | ✅ 杀死 |
| M7 | **仅** `isGraphTerminal` 去掉 `stalled` | 三副本等价 | 红 | `Extra items in the left set: 'stalled'` | ✅ 杀死 |
| M8 | **仅** `_execute_route` 调用点不透传 origin（**关键那处**） | #220 四条 | 红 | 4 FAILED（含 `test_back_edge_…`） | ✅ 杀死 |
| M9 | `_blocked_reason` 恒返回兜底句（两分支都封死） | #218 A/B | 红 | 2 FAILED | ✅ 杀死 |
| M10 | 去掉 `failed` 分支（四档第 3 格） | `test_zero_completed_with_failures_is_failed` | 红 | FAILED | ✅ 杀死 |
| M11 | `stalled` 配色复用 `budget_exceeded` 橙 | D6 配色门槛两条 | 红 | 2 FAILED | ✅ 杀死 |
| M12 | **后端 marker 文案与前端解耦**（`图级闸门` → `图形层限制`） | 全部新增测试 | **期望红** | **26 passed（存活）** | ❌ **杀死失败 → Issue 3** |

**关于实现方声明的 16 变异**：`diagnosis.md` 的 Mutation Verification 表声称 16/16 杀死。我按 `/tmp/mut/mutate.py`（实现方脚本，仍在磁盘上）复核：

- **可复现**（我独立跑或按同脚本跑出红）：M1–M13、M15。
- **M14 与 M16 在实现方脚本下确实为红**（我跑 `python3 /tmp/mut/mutate.py "M14" "M16"` → 均 `KILLED(红)`）。但需要说明**杀死它们的不是我以为的那个断言**：
  - M14（删掉 `isSpecificNodeReason` 里的兜底句白名单）之所以红，是因为测试用 `assert ... is False`（严格布尔），而删除白名单后函数返回的是 `SPECIFIC_REASON_MARKERS.some(...)` 的结果——对兜底句恰好仍是 `false`，但**我另做的「把兜底句加进 markers」变异存活了**（11 passed）。也就是说：**M14 保护的是「返回值类型/白名单没被整体删掉」，不保护「兜底句被正确排除」**。
  - M16（`waiting` 分支放宽为 `if True:`）之所以红，是因为 `_deadlock_spec` 里每个节点都有上游、放宽后列表内容变化触发断言；**我另做的「加入 `completed`」变异存活了**（25 passed）。
  - 结论：M14/M16 的**声明机制**与**实际杀的机制**不完全对应，但两条机制**都**被某个变异覆盖（白名单整体删除被我复核为红；`if True:` 被实现方脚本复核为红）。属**表述不精确**，不构成假保护。记为观察项，不单列 Issue。
- **未被声明覆盖的存活变异**：M12（跨层文案契约）——这是 16 项里**唯一**我找到的、既未声明也实际存活的缺口，即 Issue 3。

## Test Results

HEAD = `644c7be`（审阅期间从 `0b2181d` 前进 4 个提交；下述结果均为最终 HEAD 上重跑）。

| 命令 | 结果 |
|---|---|
| `uv run pytest tests/agent/subagent/ -q` | **482 passed** （21.9s） |
| `uv run pytest tests/web_tests/test_terminal_honesty_js.py tests/web_tests/test_workflow_graph_ux_js.py tests/web_tests/test_workflow_graph_js.py -q` | **87 passed** （9.3s） |
| `uv run pytest tests/agent/subagent/ tests/web_tests/test_terminal_honesty_js.py tests/benchmark/ -q` | **969 passed, 1 skipped** （31.4s） |
| `uv run pytest tests/web_tests/ -q` | 338 passed, 7 skipped, **1 failed**（`test_reconnect_pending_interaction_browser.py::test_approval_submit_when_ws_down_shows_feedback`，与本次改动无关——该文件未被 diff 触及；单跑 3 次为 1 红 1 绿 1 红，chrome/时序 flaky） |
| `uv run pytest -q`（全量） | **2938 passed, 8 skipped, 2 failed**（`test_browser.py::test_fake_llm_browser_smoke` + `test_multi_session_browser.py::test_multi_tab_exit_does_not_affect_other_tab_reconnect`；**两条单跑各 2 次均绿**，属全量并发下的浏览器 flaky，与本次改动无关） |
| `uv run pytest tests/web_tests/test_workflow_graph_browser.py -q` × 重复单跑 | **20 passed**（每次 ~67s）。未复现 issue #191 的偶发失败；即便偶发也与 master 同源、与本次改动无关 |
| `npx @fission-ai/openspec@1.4.1 validate workflow-terminal-honesty --strict` | `Change 'workflow-terminal-honesty' is valid` |
| `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py` | `OpenSpec artifact checks passed` |
| `git status --short`（审阅结束时） | 干净——所有变异已还原，工作区无残留改动 |

**已知无关失败核对**：`tests/web_tests/test_workflow_graph_browser.py` 全文件跑在本次 3 次重复中**未失败**；`tests/test_declarative_flow_engine.py::TestE2eEngineCliSmoke::test_engine_cli_validate_exit_code` 在全量跑中**未出现在失败列表**（本次全量失败仅上述 2 条浏览器用例）。两条被预告的已知红都未干扰判定。

## 结论

**CHANGES_REQUESTED**。

实现的核心目标是达成的，且经得起对抗性检验：

- **四档判据**互斥穷尽、口径正确（节点数、不含 `skipped`、不复用 `_unit_counts`），5 格边界矩阵全覆盖，预算优先由探针测试锁死。
- **因由分档**真实穿透到用户可见层——`explainNode()` 的优先级 0 提权与 `GRAPH_STOP_REASONS` 的先后关系有断言锁定，用户的验收口径（「实际看到的那句话」）被直接断在 `explainNode()` 返回值上，不是断在 `state.reason` 字段上。
- **方案 D** 的三处调用点全部透传，`_is_skipped` 条件 2 只读既有 `targets`；「只做豁免」的中间态由 1.4+1.5 的组合断言拦住（M3 独立复现为红）。
- **G11 红线**保持：9 项清理逐行未减，既有回归绿，新增回归覆盖同一语义。
- **三副本**是真·集合相等断言，我独立复算三集合一致；任一副本漂移都能杀死（M4/M6/M7 三种漂移方向各自为红）。

审阅期间发现并已修复一条**中等**问题（Issue 1，非闸门诊断冒充闸门），实现方在 `644c7be` 中修正为「按 `reason` 键存在判闸门」——该修法与 `_mark_graph_recursion_exceeded` 的唯一写入点语义等价，我已用同一 repro 复核修前红/修后绿。

仍需在 PR 前处理：

1. **Issue 2（中）**：`benchmarks/workflow_e2e.py:41` 的 `UNHEALTHY_WORKFLOW_STATUSES` 漏 `stalled`。它和已修的 `runner.py:_REPLAY_UNHEALTHY_STATUSES` 是同义黑名单，现在两处对 `stalled` 结论相反；`_status_comparable` 会把「record 干净完成 + replay 零节点成功」判为**两侧一致、通过**——这是本 change 明令禁止的「换一种骗法」形态。建议同时把两处集合抽成单一源，避免下次再漂移。
2. **Issue 3（低）**：前后端因由标记是纯字符串耦合且无测试锁定（M12 变异存活），建议结构化（`reason_code`）或补跨层源文本断言。
3. **Issue 4（低，可选）**：`recursion_limit` 形态下因由 299 字符、被前端 160 截掉尾部的「本节点未派发」，与 design 里「按前端展示预算压缩」的自我要求不符。

以上三条修完后可直接进收尾（tasks 6.4–6.9）。第 0–6.3 节的任务全部有真实实现与测试支撑，无未实现项。
