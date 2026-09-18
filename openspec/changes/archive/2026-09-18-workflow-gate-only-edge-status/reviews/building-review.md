# Building 审阅报告：workflow-gate-only-edge-status（issue #207）

## Verdict

**PASS**（Round 2，2026-09-18，head `bb3b9e9`）——R1 的唯一阻断项（`_source_collection` 三处记账点中两处零测试保护，变异 M5/M6 存活）已补齐并经**独立变异验证 + 行级分支追踪**确认全部为真保护：三条记账路径现各自被一条测试**唯一**覆盖。两条 R1 low 已修（docstring 五档→六档、tasks 全勾）；第三条 low（箭头编码无测试）经复审**接受其不做**并降级为观察项，理由见下。无新引入问题。

> 历史：Round 1 结论为 **CHANGES_REQUESTED**（head `35fe8cf`），含 1 条中等（覆盖洞）+ 3 条低。修复提交 `bb3b9e9`。

## 审阅基线

| 项 | 值 |
|---|---|
| reviewer | 独立零记忆审阅 subagent（本会话；R1/R2 同一审阅者） |
| change id | `workflow-gate-only-edge-status`（issue #207） |
| base sha | `a0b28ef9e9d26347dfab289f2ee3fd0588b2e229`（= `master`） |
| head sha | `bb3b9e94420c774d67e12d861682e968a30ceabf`（R1 审时为 `35fe8cf`） |
| 分支 | `gate-only-edge-status/2026-09-18`（worktree 干净，审阅全程 `git status --porcelain` 为空） |
| 审阅范围 | `git diff a0b28ef..bb3b9e9`；R2 重点复核 `git diff 35fe8cf..bb3b9e9` |
| 审阅方法 | 逐条 Read + **变异验证（11 项）** + **行级 trace 分支归属证明** + 真实 `scheduler.run()` 探针 + master 基线对照 |

## R2 修复核验（不采信自述，逐条实跑）

### 阻断项：两处记账点的覆盖洞

| 核验项 | 方法 | 结果 |
|---|---|---|
| 新增测试是否覆盖 **result 槽直取路径** | 变异 M5（删 `scheduler.py:2373` 的 `_consumed_edges.add`）→ 跑 `tests/agent/subagent/test_workflow_graph_snapshot.py` | ✅ **变红**：`test_dynamic_foreach_reads_aggregate_result_slot` FAILED（1 failed / 24 passed） |
| 新增测试是否覆盖 **非 subagent summary 路径** | 变异 M6（删 `scheduler.py:2377` 的 `_consumed_edges.add`） | ✅ **变红**：`test_dynamic_foreach_reads_non_subagent_summary` FAILED（1 failed / 24 passed） |
| 原测试仍守 `_read` 闭包路径 | 变异 M4（删 `:2360`） | ✅ **变红**：`test_dynamic_foreach_consumes_upstream_edge` FAILED |
| 是否**真的**走对分支（防「变红但走错分支」的假保护） | 自写 pytest 插件 `sys.settrace` 追踪 `_source_collection` 内**实际执行的行号**（`/tmp/branch_probe.py`），逐测试打印 | ✅ **三测试各自命中不同行，无串台**（见下表） |
| 是否 1:1 映射（一条测试唯一守一处） | 三次变异各只红**一条**、且红的正是对应那条 | ✅ 无重复覆盖、无遗漏 |

**行级分支追踪结果**（插件实测，非推演）：

| 测试 | 实际执行的打标行 | 归属分支 |
|---|---|---|
| `test_dynamic_foreach_consumes_upstream_edge` | `2360` | `_read` 闭包 |
| `test_dynamic_foreach_reads_aggregate_result_slot` | `2373` | `result` 槽直取 |
| `test_dynamic_foreach_reads_non_subagent_summary` | `2377` | 非 subagent `summary` 兜底 |

三条路径的执行行**互不重叠**——覆盖是真实的、且是**排他的**，不存在「一条测试顺带覆盖另一条」的水分。

### 提交信息里两条「踩坑」自述的独立核实

提交信息与测试注释断言了两个代码事实，我逐一实跑核对（`/tmp/probe_claims.py`），**两条都成立**：

1. **「aggregate 不行：`result` 槽恒被填充」**——实跑 `aggregate(outputs=["merged"])` 作 source：`agg.slots == ['result', 'merged']`，确认 `result` **恒在**（`_collect_slots` 先填 `:2157`，`outputs` 循环再填 `:1562`），必然先命中 `:2370` 分支、永远走不到 `:2376`。注释所述属实。
2. **「route 作 source 是假覆盖」**——`WorkflowPlan.is_control_edge`（`agent/subagent/workflow.py:243-245`）返回 `self._index[edge.source].kind == "route"`，即 **route 的每一条出边都是控制边**。实跑确认：`(gate,picked)/(gate,other)/(gate,fan)` 三条边 `kind` 全为 `control`，走 `_edge_status` 规则 1（`:2685-2688`）恒 `passed`，与消费记账无关。注释所述属实——这确实会是一条**恒真的假保护**，作者识别正确并规避了。

唯一需要的构造（`foreach → foreach(source:)`：外层无 slots、有 summary、出边是数据边）经行级 trace 确认命中 `:2377`，成立。

### 3 条 low 的处置

| R1 Issue | 修复证据 | R2 结论 |
|---|---|---|
| Issue 2（docstring 首行「边五档」） | `agent/subagent/scheduler.py:2663` → `"""边六档状态（决策 7 + Q5；第 6 档 ``satisfied`` 见 issue #207）。"""` | ✅ 已修 |
| Issue 4（tasks.md 全未勾，review 门禁失效） | `openspec/changes/workflow-gate-only-edge-status/tasks.md`：`grep -c "^- \[ \]"` **= 0**（全 `[x]`）；diff 确认**只改 checkbox**、无任务文本增删 | ✅ 已修，门禁已激活（见下） |
| Issue 3（spec 的第三重编码「有无流向箭头」无测试） | 未做，作者请我判断该补在哪一层 | ⚠️ **接受不做**，降级为观察项——理由见下 |

**Issue 3 的复审理由（为什么接受不做）**：R1 我把它列为**低**，现在的判断是它应当作为**已声明的残余风险接受**，而不是修复项。三条论据：

1. **该编码不是本 change 引入的，也不受本 change 影响**。`renderEdge` 的 marker 分支（`web/static/workflow.js:682-687`）**不在本 diff 内**（本 diff 只碰 `workflow_graph.js` 的 `EDGE_STYLES`/`EDGE_STATUS_TEXT` 两个词表）。`satisfied` 无箭头是既有渲染逻辑的**天然结果**，不是新增行为。本 change 没有让任何既有断言从真变假。
2. **测试成本与收益不匹配**。纯函数层测不到它：箭头是 `renderEdge` 内部对 SVG 元素 `setAttribute('marker-end', ...)` 的副作用，而 `renderEdge` 定义在 `workflow.js`（非 `workflow_graph.js`），且**不在任何 JS 测试 harness 的导出面上**（`window.AsterwyndWorkflow` 导出 11 项，`:1261-1273`，不含 `renderEdge`；`test_workflow_graph_js.py` 的 harness 只加载 `workflow_graph.js`）。要测就必须走 DOM/浏览器层（Playwright）或先为 `workflow.js` 建导出面——后者是为测试而改生产代码形状，前者引入浏览器依赖。**当前 change 的正确性不依赖它**（明度 + 线宽两重已在纯函数层锁定，`test_workflow_graph_js.py:100-119`）。
3. **风险是「未来有人改坏」而非「现在坏了」**。design D2b / grill 决策 9 已经明文记录「不要顺手补箭头」并说明了原因，属于有据可查的设计约束。

**结论**：接受不做。**但**记录为观察项——若后续有 change 需要改 `renderEdge` 的 marker 逻辑，应在那时补浏览器层断言（`tests/web_tests/test_workflow_graph_browser.py` 已有 Playwright 基建与 `.workflow-edge` 选择器，`test_workflow_graph_browser.py:177`，是自然的落点）。这是本次唯一未闭合的项，属**已知并接受**，不构成 CHANGES_REQUESTED。

## 任务逐项验证（R2 复核）

R1 已逐条核验 1.1–1.3 / 2.1–2.6 / 3.1–3.4 全部真实实现；R2 复核确认**实现代码未再改动**（`git diff 35fe8cf..bb3b9e9 -- agent/ web/` 仅 docstring 一行，无功能性变更），故原结论全部维持，不再重复粘贴证据表。R2 增量：

| 任务 | R2 状态 | 证据 |
|---|---|---|
| 2.6（Q2 记账回归）| ✅ **由「部分」升为「完整」** | 三条记账路径现各有专属回归：`test_workflow_graph_snapshot.py:530`（`_read`）/`:559`（result 槽）/`:587`（summary），行级 trace 确认互不重叠 |
| 1.1（docstring 五档→六档） | ✅ 补完 | `scheduler.py:2663` |
| 4.1（全量测试 + 门禁） | ✅ | 见「回归结果」 |
| 4.2 / 4.4 / 4.5（spec 同步 / manifest / 归档） | ⏳ 收尾阶段 | 未到，见「残余事项」 |

## 变异验证汇总（累计 11 项）

R1 的 9 项结论维持不变（7 红 2 存活）；R2 对修复后的 3 个后端打标点重跑：

| # | 变异 | 结果 |
|---|---|---|
| M1 | 删 `satisfied` 整段分支 | 🔴 `test_gate_only_edge_is_satisfied_not_inactive` |
| M2 | 删 `target.status != "skipped"` | 🔴 `test_skipped_target_edge_stays_inactive` |
| M3 | `edge.required` 反转 | 🔴 2 条（gate-only + optional-unconsumed） |
| M4 | 删 `_read` 闭包打标（`:2360`） | 🔴 `test_dynamic_foreach_consumes_upstream_edge` |
| **M5** | **删 result 槽打标（`:2373`）** | **🔴 由 R1 的「存活」转为变红**：`test_dynamic_foreach_reads_aggregate_result_slot` |
| **M6** | **删 summary 打标（`:2377`）** | **🔴 由 R1 的「存活」转为变红**：`test_dynamic_foreach_reads_non_subagent_summary` |
| M7 | `satisfied.opacity` 同 `passed` | 🔴 `test_satisfied_is_distinguishable_from_passed_and_inactive` |
| M8 | `satisfied.width` 同 `inactive` | 🔴 同上 |
| M9 | 删 `satisfied` 样式项 | 🔴 3 条 |

**9/9 实现逻辑变异现全部变红**（R1 为 7/9）。所有变异经 `git checkout HEAD -- <file>` 还原，收尾核验 `git status --porcelain` 为空（实现代码零残留；本报告为唯一新增未跟踪文件）。

## 回归结果

| 套件 | 结果 |
|---|---|
| `tests/agent/subagent` + `tests/benchmark` | **943 passed, 1 skipped** |
| `tests/agent/subagent/test_workflow_graph_snapshot.py` | **25 passed**（R1 时 23 条，+2 新测试） |
| `tests/web_tests/test_workflow_graph_js.py` + `test_workflow_graph_ux_js.py` | **76 passed** |
| 全量 `uv run pytest -q` | **2866 passed, 8 skipped, 6 failed** |
| `npx @fission-ai/openspec@1.4.1 validate --strict` | **valid** |
| `scripts/check_openspec_artifacts.py` | **exit 1**：`review manifest missing`（见下「残余事项」） |

**6 条失败逐条独立排除**（不采信自述，全部实跑核对）：

1. `test_tree_sitter_symbols.py::test_tree_sitter_extracts_java_and_kotlin_symbols`——R1 已确认为干净树同样红，与 scheduler 无交集。
2. `test_declarative_flow_engine.py::...test_engine_cli_validate_exit_code`——同上。
3–6. `test_workflow_graph_browser.py` 的 4 条（`test_workflow_view_auto_opens_and_draws_svg` / `test_click_any_node_opens_detail_drawer` / `test_legend_is_visible_and_collapsible` / `test_collapsed_group_shows_aggregated_status`）——**我在 master（base sha `a0b28ef`）上建了独立 worktree 实跑同一文件，同样 4 failed / 14 passed，且失败用例集与本 worktree 不同**（master 是 recursion + collapsed_group_expands + foreach_drilldown + collapsed_group_aggregated；本 worktree 是 auto_opens + click_any_node + legend + collapsed_group_aggregated）。既是**基线同样失败**、又是**失败集随运行漂移**，坐实为 harness 竞态，与本 change 无关（本 diff 未碰该文件、未碰 `workflow.js`）。本 change 未使任何测试从通过变失败。

## 残余事项（不阻塞 building 审阅，归档前须了结）

1. **`check_openspec_artifacts.py` 现在会 exit 1**——task 4.4 的 review manifest 尚未生成。这是 tasks 全勾的**预期后果**（R1 Issue 4 指出门禁此前失效，现已激活正常工作）。manifest 需在 gate 通过后生成：`workflow_state.py review-manifest` 的 CLI 路径要求 change 目录存在 `handoff.json`（`:964-967`），本 change **无** `handoff.json`（与上一个已归档的 `enhance-workflow-graph-ux` 一致，它也没有）；但底层库 `agent.workflow.review_manifest.write_review_manifest` 无此要求——我已用库函数 dry-run 成功构建出完整 manifest（`base_sha=a0b28ef`、`head_sha=bb3b9e9`、`report_hash`/`tasks_hash`/`spec_hash`/`diff_hash` 全字段可解析），说明**该事项可解、不是阻塞**，只是收尾时需注意走库函数而非 CLI、或先补 `handoff.json`。留待 `/review-loop` 的 manifest 步骤处理。
2. **task 4.2**（spec delta 合入 `openspec/specs/web-ui/spec.md` 的 `:527`/`:591` 两处「五档」→「六档」）+ 受保护路径结构化事件）——收尾阶段。
3. **task 4.5**（归档 + 清 backlog + 建 PR）——收尾阶段。
4. **（观察项）** Issue 3 的箭头编码无测试，已知并接受；若未来有 change 改 `renderEdge` marker 逻辑，应在 `test_workflow_graph_browser.py` 补断言。
5. **（低，非本 change 引入）** 同一 change 造成的口径残留还剩 3 处「五档」字样未跟改：`web/static/workflow_graph.js:65`（`EDGE_STYLES` 上方注释，其下已是 6 项）、`tests/agent/subagent/test_workflow_graph_snapshot.py:8`（模块 docstring）与 `:201`（段落标题）。不影响功能与门禁，R1 已提；作者只修了 `_edge_status` 那处。建议随收尾顺手扫干净，或明确接受为无害残留。**注**：`docs/openspec-change-backlog.md:174` 的「边五档」属**历史口径**、按 AGENTS.md 不应改（grill 决策 8 已判定），不在本项内。

## Round 记录

- **Round 1（head `35fe8cf`）**：**CHANGES_REQUESTED**。1 中等（覆盖洞：`_source_collection` 三处记账点中两处零保护，M5/M6 变异存活）+ 3 低（docstring 五档残留、箭头编码无测试、tasks.md 未勾致 review 门禁失效）。实现本体、spec 对齐、C5 隔离、Q1/Q2/Q3 拍板落实均无问题。
- **Round 2（head `bb3b9e9`，2026-09-18）**：**PASS**。阻断项经变异验证 + 行级 trace 双证据确认修复（三条记账路径 1:1 排他覆盖，9/9 变异全红）；两条 low 已修；第三条 low 经复审接受不做并降级为观察项（既有渲染代码、不受本 change 影响、纯函数层测不到、且有设计记录约束）。无新引入问题。实现代码自 R1 起除 docstring 一行外零变更，故 R1 对实现本体的全部核验结论继续有效。
