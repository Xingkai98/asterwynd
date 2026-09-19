# Grill: workflow-terminal-honesty 设计追问

## Reviewer

- run id: `9d6bcb36-5a53-494d-9748-476c68b092e0`（paseo agent id；零记忆独立评审者）
- 时间: 2026-09-19
- 审视对象: `design.md` 的 D1–D6 + Testing Strategy + spec delta（对照 `proposal.md` / `diagnosis.md` / `tasks.md` 与真实实现代码）
- 工作区: `/home/happy/.paseo/worktrees/0frj3kg8/workflow-terminal-honesty-2026-09-19`（分支 `workflow-terminal-honesty/2026-09-19`，HEAD `202f661`，工作区干净）

**评审方法**：不只看文档——把 D1/D4 作为插件补丁装到当前 scheduler 上跑既有全量测试（`SIM=D1` / `SIM=D1D4`），并用确定性脚本（`_LLM` 恒返回固定文本）复现三个 bug 的多形态。所有结论均标注了可复现的证据。

---

## Confirmed Decisions

- **决策**: D1 的四档判据在当前代码的收敛出口上确实可达，且不会误伤既有通过用例；`failed`（零 completed）一档在当前测试里**从未被触发**，属未被覆盖的真实缺口。
  理由: 给 `WorkflowScheduler._terminal_converged_status` 挂了记录形参的探针，跑全量 `tests/agent/subagent/`（468 用例）共捕获 **168 次收敛调用**：`{'completed': N}` 占绝大多数，另有 `{'completed': M, 'pending': K}`、`{'completed': N, 'failed': M}` 与 **一条 `{'failed': 1}`**（零 completed）。唯一那条零 completed 来自 `tests/agent/subagent/test_scheduler.py::test_queue_full_is_diagnosable_and_does_not_raise_index_error`（`scheduler.py:924`，单节点 `a` 撞 `queue_full` 被标 `failed`）——四档下它从 `completed_with_failures` 变成 `failed`，但该用例只断言 `node["status"]`，**不断言图级 status**，因此不会变红。以文件级探针复核，`tests/agent/subagent/test_workflow_semantics_m1.py` 里仅两条命中 `failed>0`（`test_blocked_takes_priority_over_skipped` → `completed_with_failures`、`test_graph_with_failed_node_is_completed_with_failures` → `completed_with_failures`），二者均保留 `completed>0`，四档下结论不变。
  来源: `9d6bcb36-5a53-494d-9748-476c68b092e0`（探针 `/tmp/probe_plugin2.py` 跑 `tests/agent/subagent/`）

- **决策**: D5 的「三副本」表述不准确，真实副本数是 **2 个**——`scheduler.py` 里**没有**名为 `TERMINAL_STATUSES` 的图级集合；`scheduler.py:83` 的 `TERMINAL_NODE_STATUSES` 是**节点**状态集合，与图级终态无关。真正需要同步的图级副本是 `scheduler.py:111` 的 `_SNAPSHOT_TERMINAL_STATUSES` 与前端两个文件里的两个字面表。
  理由: `grep -n "\bTERMINAL_STATUSES\b" agent/subagent/scheduler.py` 无匹配；仅存在 `TERMINAL_NODE_STATUSES`（`:83`，frozenset{"completed","failed","cancelled","blocked","budget_exceeded","skipped"}，注意它**不含**图级档）。前端则有**两处**图级终态词表：`web/static/workflow.js:21` 的数组 `TERMINAL_STATUSES`（`pruneGraphs` 消费方）与 `web/static/workflow_graph.js:983` 的 `isGraphTerminal()`（`graphTabMeta` 计时用，未导出到公共 API），二者当前都枚举了同样的 6 档。也就是说：设计里被称作「scheduler 侧 TERMINAL_STATUSES」的那个副本在代码中不存在，而前端的两个副本（不是一个）都没被 D5 数进去。
  来源: `9d6bcb36-5a53-494d-9748-476c68b092e0`（`grep`/读码验证，行号如上）

- **决策**: spec delta 的三条 MODIFIED Requirement 用了**全新标题**（`workflow 图级终态如实反映「实际发生了什么」` / `workflow 节点因由如实指向真实成因` / `回边重跑不得清空本次派发的发起者`），与目标 spec `openspec/specs/web-ui/spec.md` 中任何既有 Requirement 标题都不匹配；这会让 `openspec archive`/`sync` 在**归档步骤直接失败**（不是 CI 告警，是硬失败）。
  理由: 逐条比对目标 spec 的要求标题名，三条新标题命中数均为 0；目标 spec 现有的对应条目是 `workflow 图级终态区分「有失败」`（`:685`）与另外两条其它命名。用同版本 CLI 做了最小复现：在 `/tmp/ossync` 造一个 change，delta 用 `## MODIFIED Requirements` + 标题 `workflow 图级终态如实反映「实际发生了什么」`，目标 spec 里只有 `workflow 图级终态区分「有失败」`——`npx @fission-ai/openspec@1.4.1 archive test-mod` 输出：`web-ui MODIFIED failed for header "...", not found` → `Aborted. No files were changed.`。也就是说 `openspec/changes/workflow-terminal-honesty/specs/web-ui/spec.md` 的三条 MODIFIED 标题必须**逐字改成目标 spec 里已有的 Requirement 名**（或改为 ADDED），否则 tasks 6.4/6.7/6.6 全部走不通。注意：`npx openspec validate workflow-terminal-honesty --strict` **会报 PASS**（validate 不校验标题是否落在目标 spec），所以这是「validate 绿灯但 archive 红」的陷阱。
  来源: `9d6bcb36-5a53-494d-9748-476c68b092e0`（`/tmp/ossync` 最小复现 + `grep -n "^### Requirement" openspec/specs/web-ui/spec.md`）

- **决策**: D4 的「只豁免 origin 一个节点」对**多节点环**（3/4 节点）是充分的，且 origin 在 `_on_node_finished` 调用点应取「刚完成的那个节点」——两个候选都只是使判定提前收敛，不会漏清任何「需要重跑的下游」。
  理由: 用 `data_outgoing` 递推，环上「走回 route」的那条链恰好经过 origin 自己，所以在链首拦住它就是拦住整条回环；而 `origin` 在 `_execute_route` 侧是 route 自己、在 `_on_node_finished` 侧是刚完成的节点，两者的 data_outgoing 子图在回环方向上是同一条链。用脚本对 `ring1/ring2/ring3`（2/3/4 节点环）× `max_routes∈{2,3,4}` × 三种策略（不豁免 / design 的 origin 语义 / 换成「派发者」语义）共 27 组跑了不变量检查：两种豁免策略在**全部 18 组豁免场景**下都保住了「route 保持 `completed` 且 `targets` 非空」；不豁免则 9 组全部违反。
  来源: `9d6bcb36-5a53-494d-9748-476c68b092e0`（`/tmp/probe_fuzz.py` 27 组矩阵）

- **决策**: D3 的因由分档在**前端实际可见的那条链路上**会被现有 `explainNode()` 的优先级覆盖——`blocked` 节点的因由优先取图级停止原因、其次沿边找上游，D3 写进 `state.reason` 的新文案**只在两个优先级都不命中时才会显示**。
  理由: `web/static/workflow_graph.js:803` 的 `explainNode()` 对 `status === 'blocked'` 的三级优先序是：① `GRAPH_STOP_REASONS[graphStatus]`（图级为 `budget_exceeded`/`cancelled`/`graph_recursion_exceeded` 时直接返回固定句）→ ② `blockingUpstreams()` 沿数据入边穿透收集未完成上游 → ③ 才用 `node.reason`。用真实快照跑了 `explainNode`：`max_routes` 超限的图（图级 `graph_recursion_exceeded`，三个节点 `reason` 全为兜底句），前端对三个节点都渲染成 **「流程因图超限被停止，该节点没来得及执行」**——D3-A 想要的 `max_routes`/上限值一个字都进不了 UI；`stalled` 死锁图（图级 `stalled`，priority ① 不命中）则渲染成 **「被上游 body 挡住，未执行」**，D3-B 的「入边互等」同样被 priority ② 覆盖。注意 `_envelope` 与快照都**不暴露 `raw`**（`workflow_graph.js:367` 附近的投影显式排除），所以节点自身 reason 是唯一可能承载「互等」信息的字段，而它被前端挡住了。
  来源: `9d6bcb36-5a53-494d-9748-476c68b092e0`（`/tmp/probe_218a.py` + `/tmp/explain_218a.js`；`/tmp/probe_217ui.py` + `/tmp/explain_217.js`）

- **决策**: D6 的「深琥珀/暗橙」配色必须选足亮度差，否则会撞上既有档——现有 `completed_with_failures`(`#fbbf24`) 与 `budget_exceeded`(`#fb923c`) 的 RGB 距离仅 **51.0**，已是当前调色板里最接近的一对；若 `stalled` 落在同一橙带（如 `#d97706`，到 `budget_exceeded` 仅 Δ=69.3）会重复同类混淆。
  理由: 对 `GRAPH_STATUS_COLORS`（`web/static/workflow_graph.js:98-108`）做了逐对 RGB 欧氏距离计算，只有上述一对 < 60；再测候选色：`#b45309`（最近 `budget_exceeded` Δ=107.8）、`#92400e`（Δ=140.9）能拉开明显距离，而 `#d97706`/`#a16207` 仍在橙/卡其带内。D6 只写了「深琥珀/暗橙、不与 budget_exceeded 的橙复用」，没有给出可判定的阈值——`validate` 与测试都无法机械验证「可分辨」，需要把「到 `budget_exceeded` 的最小 RGB 距离」写成可断言的门槛。
  来源: `9d6bcb36-5a53-494d-9748-476c68b092e0`（色距计算脚本）

---

## Open Questions

> 每条均附本 change 真实场景 + 具体输入/输出。**请主 session 原样转达用户并等待答复**；答复回填到本文件 `## User Confirmation`。

- **Q1: D4 的 origin 豁免会让「空转环」提前收敛，从而改变 `#220` 那张图本来要撞的 `max_routes` 结果——这是要保留的行为变更，还是应当只修「显示」而不改「执行」？**
  **场景例子**：用 `diagnosis.md` 的真实复现 spec（`cycle_gate` 为 route、`max_routes=3`、`cases=[{when:CONTINUE,to:body}]`、**default 也是 `body`**，即无论判定如何都重选 `body`，回边 `body→cycle_gate` 为 `required:false` 数据边）。今天实跑的结果是：route 被派发 **3 次**、撞 `max_routes` → 图级 `graph_recursion_exceeded`，`cycle_gate` 为 `blocked`。加上 D4 豁免后同一份 spec 实跑变成：route 只被派发 **2 次**、**不再撞 `max_routes`**，图级变成 **`completed`**，`cycle_gate.status='completed'`、`targets=['body']`。也就是说：#220 的症状（route 被清空）确实没了，但代价是「本该被 `max_routes` 拦下的空转环」现在提前收敛、且被报成成功。`proposal.md` 的 Non-Goals 明确写着「不修空转环本身（它在语义上就该撞 `max_routes`）」，D1 的立项理由又是「零节点成功不得报 `completed`」——请确认：这个由 D4 引入的**行为**变化（不只是显示变化）是否是预期？（可选方向：只豁免「清空 origin 的字段」，但仍让 origin 保持可被再次派发/仍受 `max_routes` 约束；或豁免仅作用于 `_execute_route` 那一个调用点。）

- **Q2: D1 的 `completed_count` 用「节点 `status == "completed"`」计数，是否会把「只跑了一个空的 route/聚合节点、其它节点全被挡」的图报成 `completed`？**
  **场景例子**：一张图 `gate(route) -> work(subagent) -> loop(aggregate)`，且 `loop→gate` 是一条 `required:false` 数据回边。`gate` 是纯逻辑节点（`runs=0`，不消耗 run），它先完成判定；`work` 因路由未命中而永远没被派发、最终 `blocked`。实跑：`completed_count` 只数到 `gate` 这一个「没干活」的节点 → 图级报 **`completed`**；而真正会干活的 `work`（`runs=0`、`blocked`）、`loop`（`blocked`）都没跑。对照 `diagnosis.md` 提出的「同源」口径，快照的 `completed` 字段来自 `_unit_counts()['completed_units']`（按 `_logical_units` 口径），与「节点数」并**不同源**（foreach 容器按 N+1 计），因此「与快照 completed 计数同源」这句表述也需要一并澄清。请确认：`completed` 的计数口径是否应当进一步排除「零产出的 route/聚合节点」？（或者接受「只要有一个节点成功就算跑了」。）

- **Q3: `#220` 的复现 spec 在 `diagnosis.md` 里前后不一致——应该以哪一份为准，以及回归测试要钉住的是「症状」还是「机制」？**
  **场景例子**：`diagnosis.md` 的 `Reproduction` 段落字面写的是「回边加 `required:false`，`cycle_gate` 加 `max_routes:3`」（即在 #217 的 spec 上只改这两点，而 #217 的 spec 中 `cycle_gate` 的 **default 是 `end`**）。我用这份字面 spec 实跑：route 只派发 **1 次**、`_reset_subtree` **一次都没被调用**，`cycle_gate.status='completed'`、`targets=['end']`，**完全复现不出 #220**。而 `diagnosis.md` 的 `Evidence` 块记录的却是 `summary="default -> ['body']"`、`targets=['body']`、`_reset_subtree` 被调用于 `['cycle_gate','body','cycle_gate','cycle_gate']`——这要求 **default 是 `body`**（回边分支被选中、环真的空转起来），我用这一份实跑：route 派发 3 次、`_reset_subtree` 命中 `['cycle_gate','body','cycle_gate','cycle_gate']`、`cycle_gate` 变 `blocked`/`targets=[]`，**症状精确复现**。请确认：以 Evidence 块（default=`body`）为准修正 `diagnosis.md` 的 Reproduction 段，且 tasks 1.4 的回归测试按这份 spec 来写？（否则测试会「照着文档写、永远是绿的」。）

- **Q4: D3 的新因由文案是只进 `state.reason`（被前端覆盖），还是必须同时改前端 `explainNode()` 的优先级，让用户真正看到 `max_routes` / 「入边互等」？**
  **场景例子**：`max_routes` 形态（图级 `graph_recursion_exceeded`）。D3 落地后 `cycle_gate.reason` 会是 `图级闸门 max_routes 触发（GraphRecursionError: route node 'cycle_gate' exceeded max_routes 2），本节点未派发`。但把这些数据喂给今天的前端 `explainNode()`，用户点开详情抽屉看到的是 **「流程因图超限被停止，该节点没来得及执行」**——`max_routes` 和上限 2 都不出现；`node.reason` 只在抽屉里没有其它命中项时才显示（`drawerWhy()` 直接调 `explainNode`，全文永远不展示 `node.reason`）。另一形态（无闸门死锁）同理：图级 `stalled` 时前端渲染 **「被上游 body 挡住，未执行」**，也不是「入边互等」。请确认：D3 的验收是否要覆盖前端这条链路（spec 的 Scenario 写的是「查看节点的 `reason`」，可 `reason` 并不直接等于用户看到的那句话）？（若只改后端，建议在 spec/diagnosis 里明确「UI 文案不在本 change 范围」，别让 spec 的 Scenario 与用户可见现象脱节。）

- **Q5: D1 新增 `stalled` 后，`GET /workflow` / benchmark 等「拿图级 status 判成败」的消费方要不要同步？**
  **场景例子**：一张三节点全 `blocked` 的死锁图，今天 `GetWorkflow` 返回 `status: "completed"`；D1 之后同一张图返回 `status: "stalled"`。若有任何调用方写的是「`status == "completed"` 即通过 / 否则失败」，它会从「误判成功」变成「判为失败」——这是语义收窄想要的效果；但若写的是「`status == "failed"` 才算失败」，`stalled` 会被悄悄算成**非失败=成功**，等于换了一种骗法。我在仓库里 grep 到的图级终态消费方只有前端的两份词表与 `_SNAPSHOT_TERMINAL_STATUSES`，未发现 benchmark 侧有显式的图级状态分支，所以需要设计上明确一句「`stalled` 对消费方的语义 = 非成功」，并确认 `tasks` 里是否需要补一条「消费者清单核对」。请确认是否要把它写进 spec 的 Requirement 正文。

---

## 风险

按严重度排序（均带 `文件:行号` 证据）。

1. **【高·阻塞归档】spec delta 的三条 MODIFIED 标题与目标 spec 不匹配，`openspec archive` 会硬失败（不是告警）。**
   `openspec/changes/workflow-terminal-honesty/specs/web-ui/spec.md` 的三条标题 `workflow 图级终态如实反映「实际发生了什么」` / `workflow 节点因由如实指向真实成因` / `回边重跑不得清空本次派发的发起者` 在 `openspec/specs/web-ui/spec.md` 中命中数为 0；目标 spec 现有的对应条目是 `workflow 图级终态区分「有失败」`（`openspec/specs/web-ui/spec.md:685`）。最小复现（`/tmp/ossync`，同版本 CLI）显示 `archive` 会报 `MODIFIED failed for header "...", not found` → `Aborted. No files were changed.`。而 `openspec validate --strict` 对该 change **报 PASS**，形成「绿灯 → 归档才炸」的陷阱。修法：三条 MODIFIED 的标题逐字改为目标 spec 的既有 Requirement 名（图级终态那条显然是 `workflow 图级终态区分「有失败」`），或在 delta 里拆分/新增。

2. **【高】D4 引入的副作用改变了「空转环」的终态：本该 `graph_recursion_exceeded` 的图变成 `completed`（且无任何节点真跑过）。**
   同一 `max_routes=3` 空转环 spec：基线 `graph_recursion_exceeded`、route 派发 3 次；D1+D4 后 `completed`、route 派发 2 次、`真正跑过(runs>0) 的节点数 = 0`（脚本 `/tmp/probe_d4_endstate.py`）。这把 `#217` 要消灭的「零节点成功却报成功」从 D4 的门又放回来了一次，且与 `proposal.md` 的 Non-Goals「不修空转环本身」直接冲突。证据：`agent/subagent/scheduler.py:1620-1626`（route 派发循环里对已是终态的后继调 `_reset_subtree`）与 `:1504-1509`（`_on_node_finished` 的同类调用）叠加 D4 的提前 return。→ 见 Q1。

3. **【高】前端对 `blocked` 节点的因由合成会**遮蔽** D3 的新文案，使 #218 在用户可见层面修不掉。**
   `web/static/workflow_graph.js:836-846` 的 `explainNode()` 对 `blocked` 的优先序把图级停止原因与上游穿透排在 `node.reason` 之前；实跑快照验证：`max_routes` 图 → 三个节点 UI 文案都是「流程因图超限被停止…」（不含 `max_routes`）；`stalled` 图 → 「被上游 body 挡住，未执行」（不含「入边互等」）。`drawerWhy()`（`web/static/workflow.js:1087`）与节点小字（`:848`/`:867`）都走同一函数。→ 见 Q4。

4. **【中】`#220` 在 `diagnosis.md` 中的复现 spec 与其实证证据自相矛盾，照文档写回归测试会得到永远为绿的假测试。**
   `openspec/changes/workflow-terminal-honesty/diagnosis.md:29`（Reproduction）与 `:69-80`（Evidence）不一致；字面 spec 实跑无法复现（route 只派发 1 次、`_reset_subtree` 从未调用），需 default=`body` 才复现。`tasks.md:21`（1.4）与 Testing Strategy 都依赖这份 spec。→ 见 Q3。

5. **【中】D5 的「三副本」命名与现实不符，按文档实现会漏掉前端的第二个副本。**
   `agent/subagent/scheduler.py` 无图级 `TERMINAL_STATUSES`（`grep "\bTERMINAL_STATUSES\b"` 无匹配；`:83` 是节点级 `TERMINAL_NODE_STATUSES`）。真实图级副本：`agent/subagent/scheduler.py:111` `_SNAPSHOT_TERMINAL_STATUSES` + `web/static/workflow.js:21` `TERMINAL_STATUSES` + `web/static/workflow_graph.js:983` `isGraphTerminal()`。tasks 5.4 的「三副本等价断言」也会因此指向错误的三个对象；且 `workflow*.js` 是 IIFE，`workflow.js` 的 `TERMINAL_STATUSES` 虽在 `window.AsterwyndWorkflow`（`:1270`）暴露，`isGraphTerminal` **未**出现在 `window.AsterwyndWorkflowGraph` 的导出里（`web/static/workflow_graph.js:1075-1116`），跨文件等价断言需要走正则源文本（既有范式见 `tests/web_tests/test_workflow_graph_ux_js.py:444-455`）或补导出。

6. **【中】因由注入会把带换行/超长的 `diagnostics.message` 塞进 `state.reason`，而节点投影在 400 字符处硬切、前端再在 160 字符处硬切——可能切在句子中间。**
   `agent/subagent/scheduler.py:1293`（`state.reason` 赋值点）、`web/static/workflow_graph.js:843`（`truncateText(node.reason, 160)`）。D3 只写了「复用 `_SUMMARY_LIMIT` 截断」（400），但前端展示上限是 160，实际可见长度不一致。建议在写 `state.reason` 时就按「前端展示预算」压缩（例如只留 `reason` + 上限值，不带整段异常文本）。

7. **【中】D1 的 `completed_count` 口径与「快照 `completed` 计数同源」的表述不成立。**
   快照 `completed` 来自 `_unit_counts()['completed_units']`（`agent/subagent/scheduler.py:2523-2524` → `_logical_units` `:2469`，foreach 容器按 `items+1` 计），与「`status=='completed'` 的节点数」并不同源。若实现时误用 `_unit_counts`，`foreach` 图上的判据会与设计不符（例如容器 `completed` 但展开项全 `failed` 时两口径给出不同结果）。→ 见 Q2。

8. **【低】D6 的配色约束缺少可机械断言的阈值。**
   `web/static/workflow_graph.js:98-108` 的现有最接近一对是 `completed_with_failures #fbbf24` vs `budget_exceeded #fb923c`，RGB 距离 51.0；`validate` 与现有前端测试都无法判定「深琥珀够不够深」。建议在 Testing Strategy 里把「到 `budget_exceeded` 的最小 RGB 距离 ≥ 某阈值」写成断言，否则 `test_graph_status_colors_are_a_separate_table`（`tests/web_tests/test_workflow_graph_ux_js.py:399`）只能验证「存在」、验证不了「可分辨」。

---

## User Confirmation

> 本节由**主 session** 收集用户对上方 `## Open Questions`（Q1–Q5）的答复后回填；本评审者**不**代替用户作答。
> 每条格式：`- **Q<n>**: 用户答复：<实质内容>；确认时间: 2026-09-19`
> （占位文本如「待确认」「待主 agent 提交」不计入确认；tasks 全部勾选后 artifact checker 会强制校验每条 Open Question 都有确认记录。）
