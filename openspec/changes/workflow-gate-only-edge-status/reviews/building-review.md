# Building 审阅报告：workflow-gate-only-edge-status（issue #207）

## Verdict

**CHANGES_REQUESTED**

实现本体经逐行核验与 18 种状态组合的**全矩阵实跑**确认与 design D1/D4 **完全一致**，C5 隔离红线守住，无契约漂移；但 **9 个变异中有 2 个存活**——本 change 在 `_source_collection` 新增的 3 个记账点里，有 2 个（`result` 槽点、非 subagent `summary` 点）**零测试保护**，且实测这两处确实可达（去掉即把「产出被读了」错报成「产出未被下游读取」，正是本 change 立项要消灭的那类假话）。修法是补 2 条回归测试，成本极小，故不在本轮判 PASS。

详见下文「Issue 1（中等）」。

## 审阅基线

| 项 | 值 |
|---|---|
| reviewer | 独立零记忆审阅 subagent（本会话） |
| change id | `workflow-gate-only-edge-status`（issue #207） |
| base sha | `a0b28ef9e9d26347dfab289f2ee3fd0588b2e229`（= `master`，与 HEAD 的 merge-base 同为该 sha） |
| head sha | `35fe8cf95cf79dc74bd64fe07a3be72a2d69ce58` |
| 分支 | `gate-only-edge-status/2026-09-18`（worktree 干净，审阅全程 `git status --porcelain` 为空） |
| 审阅范围 | `git diff a0b28ef..35fe8cf`（实现 commit 35fe8cf + 前序文档 commit 6dea8a4 / 6540526 / 43f7fb6） |
| 审阅方法 | 逐条 Read 核验 + `_edge_status` 全状态矩阵实跑（128 组合）+ 真实 `scheduler.run()` 探针 + **9 项变异验证** |

## 任务逐项验证

逐条读代码 + 实跑确认（不采信任务自述；`tasks.md` 的 checkbox 全部未勾，见 Issue 4，此处按实现事实核验）。

### 0. 设计追问（实现前门禁）

| 任务 | 实现证据（`文件:行号`） | 结论 |
|---|---|---|
| 0.1 grill 产出 `reviews/grill-design.md`（≥3 决策 + Open Questions 停轮确认） | `reviews/grill-design.md:22-52`（9 条 Confirmed Decisions）、`:69-81`（3 条 Open Questions，每条配真实场景例子）、`:83-87`（User Confirmation 三条齐、带确认时间 2026-09-18） | ✅ 已做 |

### 1. 后端：`_edge_status` 加档

| 任务 | 实现证据（`文件:行号`） | 结论 |
|---|---|---|
| 1.1 `satisfied` 加在 `ready` 之后、兜底之前；判据含 Q1 的 `target.status != "skipped"`；docstring 优先级表五档→六档 | `agent/subagent/scheduler.py:2699-2704`（规则 5 `ready`）→ `:2712-2720`（新档）→ `:2721`（兜底 `inactive`）；判据四条件逐字一致：`edge.required` `:2715`、`source.status == "completed"` `:2716`、`target.status != "pending"` `:2717`、`target.status != "skipped"` `:2718`；`source/target is not None` 防御 `:2713-2714` + 注释 `:2709-2711`；docstring 优先级表 `:2662-2682`（列 7 条、六档） | ✅ 已做（唯 docstring 首行仍写「边五档状态」`:2663`，见 Issue 2） |
| 1.2（Q2 拍板 (b)）`_source_collection` 读出上游产出的返回点旁 `_consumed_edges.add`，旁加、`_mark_consumed` 本体不动 | `scheduler.py:2357-2361`（`_read` 闭包）、`:2370-2374`（`result` 槽点）、`:2376-2378`（非 subagent `summary` 点）；`_mark_consumed` 本体 `:765-774` 不在任何 diff hunk 内（diff hunk 头为 `2349`/`2357`/`2654`/`2678`），全 diff 中该名字只出现在一行新增**注释**里 | ✅ 已做 |
| 1.3 回归确认 `useful_runs`/`redundancy` 逐位不变（C5 零漂移） | `git diff a0b28ef..35fe8cf -- agent/subagent/scheduler.py` 全文中 `_consumed_run_ids`/`useful_runs`/`redundancy` 命中数 **= 0**（唯一命中是 `:2356` 的新增注释）；既有守卫测试 `tests/agent/subagent/test_workflow_graph_snapshot.py:383-392`（`useful_runs == 2`、`len(_consumed_run_ids) == 2`、`_consumed_edges == {("a","b"),("b","c")}`）与 `:408-423`（两集合同生命周期）实跑绿 | ✅ 已做（**红线守住**） |

### 2. 后端测试

| 任务 | 实现证据（`文件:行号`） | 结论 |
|---|---|---|
| 2.1 foreach 用字面 `items` → `scan→fan` 判 `satisfied`（实跑复现 issue 场景） | `tests/agent/subagent/test_workflow_graph_snapshot.py:448-462`，spec 构造 `_gate_only_spec()` `:428-443`（`scan` subagent + `fan` foreach 字面 `items`），`await scheduler.run(...)` 实跑后断言 | ✅ 已做 |
| 2.2 `required=False` 的未消费边仍 `inactive` | 同文件 `:465-475` | ✅ 已做 |
| 2.3 目标仍 `pending` → `ready`（不是 `satisfied`） | 同文件 `:478-487`（手工置 `a` completed / `_status = running`，取 mid-flight 快照） | ✅ 已做 |
| 2.5 目标 `skipped` → `inactive`（Q1 判据回归） | 同文件 `:490-527`（u + route gate + picked/t + 字面数据边 `u→t`，先断言 `nodes["t"] == "skipped"` 再断言边 `inactive`——断言链完整，不会因前置条件没达成就假绿） | ✅ 已做 |
| 2.6 动态 foreach（`source:`）读上游 → 该边判 `passed` | 同文件 `:530-555`（`planner` subagent + `fan` foreach `source:"planner"`，LLM 返回 `{"items": [...]}`，实跑断言边 `passed`） | ✅ 已做 |
| 2.4 `EDGE_STATUS_TIERS` 加 `satisfied`；既有五档判据回归全绿 | `:32-34`（frozenset 六档）、`:147`（快照每条边 `status in EDGE_STATUS_TIERS`）；既有五档用例 `:230-271` 等全部保留且绿 | ✅ 已做 |

### 3. 前端：词表 + 图例

| 任务 | 实现证据（`文件:行号`） | 结论 |
|---|---|---|
| 3.1 `EDGE_STYLES` 加 `satisfied`（`#86efac` / 0.55 / 1.6 / 实线） | `web/static/workflow_graph.js:74`（与 design D2 表逐值一致） | ✅ 已做 |
| 3.2 `EDGE_STATUS_TEXT` 加人话；图例自动跟随（不改图例代码） | `web/static/workflow_graph.js:205`（`'依赖已满足，但产出未被下游读取'`）；图例同源由 `legendModel()` 遍历 `Object.keys(EDGE_STYLES)`（`:243-250`）自动提供，diff 中**图例代码零改动** | ✅ 已做 |
| 3.3 前端纯函数单测：六档覆盖 + 非颜色维度可分辨 | `tests/web_tests/test_workflow_graph_js.py:100-114`（opacity 三者两两不同 + `inactive < satisfied < passed` 线宽）、`:116-119`（`satisfied` 是实线 `dash == []`） | ✅ 已做（明度与线宽两重都锁了，超出 task 的「或」要求） |
| 3.4 更新 grill 点名的那条既有断言（原 `test_edge_status_styles_cover_five_tiers`） | `tests/web_tests/test_workflow_graph_js.py:94-98`（已改名 `..._cover_six_tiers`，断言集合并入 `satisfied`） | ✅ 已做 |

### 4. 测试与收尾

| 任务 | 实现证据 | 结论 |
|---|---|---|
| 4.1 `uv run pytest -q` 全绿；OpenSpec validate + artifact checker 通过 | 全量实跑 `2867 passed, 8 skipped, 3 failed`——3 条失败逐条排除：`test_tree_sitter_symbols.py::test_tree_sitter_extracts_java_and_kotlin_symbols`、`test_declarative_flow_engine.py::...test_engine_cli_validate_exit_code` 属已知 flake（干净树同样红）；`test_multi_session_browser.py::test_multi_tab_slash_suggestion_isolation` 单独重跑 **1 passed**（并发 flake，本 change 未触碰多 session 路径）。`openspec validate ... --strict` → **valid**；`scripts/check_openspec_artifacts.py` → **passed** | ✅ 已做 |
| 4.2 同步 current spec（`openspec/specs/web-ui/spec.md` 两处） | 尚未执行（`:527`、`:591` 仍为五档）——属**收尾阶段**任务，building 阶段未到，符合流程 | ⏳ 未到 |
| 4.3 文档影响检查（backlog 等） | `docs/openspec-change-backlog.md:104-125` 已登记本 change；grill 决策 8 判定 `:174` 的历史「边五档」属**历史口径**、按 AGENTS.md 不应改——核验同意 | ✅ 已做（归档清理待收尾） |
| 4.4 独立审阅闭环 + review manifest | 本报告即该闭环产出；manifest 待本报告定稿后生成 | ⏳ 本轮 |
| 4.5 归档 + 清 backlog + 建 PR | 未到 | ⏳ 未到 |

## Issues

### Issue 1（**中等**）：`_source_collection` 新增的 3 个记账点只有 1 个被测试保护，2 个变异存活

**证据（实现）**：本 change 在 `agent/subagent/scheduler.py::_source_collection` 新增 **3 处** `_consumed_edges.add`：

- `:2357-2361` `_read` 闭包（非 subagent 无槽 / 无上游歧义终止路径）
- `:2370-2374` `result` 槽路径
- `:2376-2378` 非 subagent `summary` 路径

**证据（测试）**：新增的 Q2 回归测试 `tests/web_tests/../test_workflow_graph_snapshot.py:530-555` 的形态是 `planner(subagent) → fan(source:"planner")`；实跑探针确认该形态走的是 **`_read` 闭包**分支（planner 是 subagent 且无 `slots`，`data_incoming("planner")` 为空 → `len(distinct) != 1` → `_read`），**不经过** `:2370` / `:2376` 两条分支。

**证据（变异验证）**：我删掉 `:2370-2374` 与 `:2376-2378` 两处记账后跑 `tests/agent/subagent tests/benchmark`（**941 passed, 1 skipped**）与 `tests/web_tests`——**全部绿**，无任何测试变红。（其余 7 个变异全部变红，见下节。）

**可达性实测（证明这不是死代码）**——两个真实 `scheduler.run()` 探针：

| 形态 | 基线 | 删掉对应记账后 |
|---|---|---|
| `a(subagent) → agg(aggregate, collect, outputs=["result"]) → fan(foreach, source:"agg", source_field:"result")` | `('agg','fan')` = **passed** | **satisfied**（图例断言「产出未被下游读取」——而 `agg.slots == ['result']`、foreach 确实展开了 3 项，是**假话**） |
| `a(subagent) → fan1(foreach, items=[...]) → fan2(foreach, source:"fan1", source_field:"items")` | `('fan1','fan2')` = **passed** | **satisfied**（同上，`fan1.summary` 确实被读走） |

**为什么这算中等**：本 change 的立项命题就是「不让图说假话」（proposal「Why」段的「误导」、design D2c 的「会得到一句假话」）。这两处新代码正是同一命题的实现，却零保护——一旦后续重构删掉，用户看到的正是这个 change 要消灭的那类假话，且与 #197 在 `_route_verdict` 补记账的缺口**同形**（该缺口正是被事后发现才补的）。design「Testing Strategy」未点名这两条路径、tasks 2.6 也只点名动态 foreach 主路径，所以这属于**超出既定测试计划的覆盖缺口**，但按本 change 自身的质量口径应当补上。

**建议修法**（2 条测试，复用上表两个已实跑通过的 spec 形态）：
1. `aggregate(collect, outputs=["result"]) → foreach(source:, source_field="result")`：断言该边 `passed`；
2. `foreach(字面 items) → foreach(source:, source_field="items")`：断言 `passed`。

> 附：`_read` 闭包与 `:2370-2378` 的内联写法是**同一逻辑的两种表达**（3 个打标点、2 种写法，且闭包的 `slot` 形参恒用默认值）。不影响正确性，补测试时可顺手统一（冗余度/可维护性，低）。

### Issue 2（**低**）：`_edge_status` docstring 首行仍写「边五档状态」，task 1.1 的「更新 docstring」未做完

**证据**：`agent/subagent/scheduler.py:2663` 首行＝`"""边五档状态（决策 7 + Q5）。"""` 的开头，而函数体 `:2662-2682` 的优先级表已改为 **7 条规则 / 6 档**、并新增 `satisfied` 段落。task 1.1 明文要求「更新 docstring 的优先级表（五档 → 六档）」——表更新了，首行的档位口径没跟着改。同一 change 内 docstring 自相矛盾（表里有 6 档，首行说 5 档）。

同类残留（同一 change 造成的口径漂移，建议一并扫掉）：`web/static/workflow_graph.js:65`（`//: 边五档`，其下 `EDGE_STYLES` 已 6 项）、`tests/agent/subagent/test_workflow_graph_snapshot.py:8`（模块 docstring「边五档状态」）与 `:201`（段落标题「节点八档 / 边五档」）。

> 注：`docs/openspec-change-backlog.md:174` 的「边五档」**不应改**（历史口径，grill 决策 8 已判定）；`openspec/specs/web-ui/spec.md:527`/`:591` 待 task 4.2 收尾同步。这两处不属本 Issue。

### Issue 3（**低**）：spec delta 明文的第三重编码「有无流向箭头」无任何测试保护

**证据**：`openspec/changes/workflow-gate-only-edge-status/specs/web-ui/spec.md:11` 写「`satisfied` SHALL 与 `inactive`、`passed` 在**非颜色维度**上可分辨（明度差 + 线宽差 + **有无流向箭头**）」。实现侧该编码确实成立且**未被改动**——`web/static/workflow.js:685` 只给 `passed`/`active` 挂箭头（不在本 diff 内），`satisfied` 天然无箭头。

但**无测试锁定它**：新增的两条前端测试只覆盖明度与线宽，且 `tests/web_tests/test_workflow_graph_js.py:103-104` 显式声明箭头「属渲染层」而不测。若后续有人给 `:685` 加上 `|| edge.status === 'satisfied'`（正是 design D2b/grill 决策 9 警告过的那类「顺手补个箭头」），**没有任何测试会变红**，spec 的 SHALL 静默退化。

**建议**：在 `tests/web_tests/test_workflow_graph_browser.py` 加一条断言（该文件已有 Playwright smoke 基建），或退一步在纯函数层断言「只有 `passed`/`active` 进箭头白名单」。

### Issue 4（**低**，流程/CI 完整性）：`tasks.md` 全部 checkbox 未勾，与实现事实不符

**证据**：`openspec/changes/workflow-gate-only-edge-status/tasks.md:5-35` 全部为 `- [ ]`，其中 0.1 / 1.1 / 1.2 / 1.3 / 2.1–2.6 / 3.1–3.4 均已确证完成（见上表）。

**影响**：`scripts/check_openspec_artifacts.py:983-988` 只在「tasks.md 每一行都是 `[x]`」时才认定实现完成、进而强制 `building-review.md` + manifest 存在。当前全未勾 → 本 report 与后续 manifest **不会被门禁强制校验**，等于审阅闭环的机械保障暂时失效。归档前（task 4.4/4.5）必须把已完成项勾上，否则门禁形同虚设。

## 变异验证结果

**方法**：`/tmp/mutate.py` 精确替换（每处 `assert count == 1` 保证只改一处），每轮跑完用 `git checkout HEAD -- <file>` 还原（**未使用** `git checkout origin/master`）；9 轮结束后 `git status --porcelain` 为空，实现代码零残留。

| # | 变异 | 目标 | 结果 |
|---|---|---|---|
| M1 | 整段删除 `satisfied` 分支（`:2712-2720`） | 新档存在性 | 🔴 `test_gate_only_edge_is_satisfied_not_inactive` 红（1 failed / 22 passed） |
| M2 | 删 `target.status != "skipped"`（`:2718`） | Q1 用户拍板 B | 🔴 `test_skipped_target_edge_stays_inactive` 红 |
| M3 | `edge.required` 反转为 `not edge.required`（`:2715`） | required 必要条件 | 🔴 2 条红（gate-only + optional-unconsumed） |
| M4 | `_read` 闭包去掉打标（`:2359-2360`） | Q2 主路径记账 | 🔴 `test_dynamic_foreach_consumes_upstream_edge` 红 |
| **M5** | **`result` 槽路径去掉打标（`:2372-2373`）** | **Q2 记账点之一** | **🟢 存活：`tests/agent/subagent` + `tests/benchmark` 941 passed，全仓无测试变红（Issue 1）** |
| **M6** | **非 subagent `summary` 路径去掉打标（`:2377`）** | **Q2 记账点之一** | **🟢 存活：同上 941 passed（Issue 1）** |
| M7 | `satisfied.opacity` 改成与 `passed` 相同（0.55→0.9） | 明度编码 | 🔴 `test_satisfied_is_distinguishable_from_passed_and_inactive` 红（:111） |
| M8 | `satisfied.width` 改成与 `inactive` 相同（1.6→1.4） | 线宽编码 | 🔴 同上（:113） |
| M9 | 删除整个 `satisfied` 样式项 | 前端词表 | 🔴 3 条红（six_tiers / distinguishable / solid_line） |

**结论**：7/9 变异变红——已写下的测试**均为真保护**（非恒真断言），后端状态机判据与前端视觉编码两个方向都锁得住；2 个存活突变对应 Issue 1 的覆盖缺口。

## 其它核验（无问题项）

- **正确性全矩阵**：把 `_edge_status` 在 `source × target × 是否被消费` 的 **128 种组合**下实跑（`/tmp/probe_matrix.py`，真实 `WorkflowEdge`），结果与 design D1 优先级链 + D4 边界表**逐格一致**：`required=False`→`inactive`；目标 `pending`→`ready`；目标 `skipped`→`inactive`（Q1=B）；目标 `blocked`/`budget_exceeded`、源 `failed`/`cancelled`→`blocked`；源 `blocked`/`skipped` 等非 completed→`inactive`；被消费一律 `passed`（规则 2 先于本档）。无边界错漏。
- **Spec 对齐**：delta 的 `节点与边状态高亮` 与 `workflow 图图例` 两条 MODIFIED 的每一句与实现逐条对上，5 条新 Scenario（动态 foreach 记 passed / 纯门控边不显示死线 / required:false 仍 inactive / 未选中目标不染绿 / 等待消费仍是 ready）全部有对应测试；`validate --strict` 通过。
- **Q1/Q2/Q3 实现符合用户拍板**：Q1=B（`:2718` 排除 `skipped` + 测试 `:490-527`）、Q2=b（`:2357-2378` 三处记账，`_mark_consumed` 本体零改动）、Q3=A（`web/static/workflow.js:685` 未改，`satisfied` 天然无箭头；明度 + 线宽 + 无箭头三重编码成立）。
- **C5 隔离（#190 决策 12 红线）**：`_mark_consumed` 函数体 `:765-774` 逐字节未变；`_consumed_run_ids` / `useful_runs` / `redundancy` 在 diff 中命中数为 0；既有守卫测试绿。
- **安全性 / 契约**：`_envelope` / `parent_envelope` 契约未变（`test_snapshot_does_not_drift_envelope_contract` 绿）；`_source_collection` 改动只新增 `set.add`，返回值与原实现语义等价（`value` 真值时行为不变，`""` 原样返回）；快照仍是只读投影（`test_snapshot_is_idempotent_and_read_only` 绿）；无新增依赖、无外部输入面变化。
- **取消路径**：实跑探针（`u`/`w` 并发 + `cancel()`）确认源 `cancelled` → 边 `blocked`（规则 3 先于新档），与 D4 一致，新档不误报。

## Round 记录

- **Round 1（2026-09-18，head `35fe8cf`）**：verdict = **CHANGES_REQUESTED**。1 条中等（Issue 1：2 处 Q2 记账点零测试保护，M5/M6 变异存活）+ 3 条低（Issue 2 docstring 五档残留、Issue 3 箭头编码无测试、Issue 4 tasks.md 未勾）。实现本体、spec 对齐、C5 隔离、Q1/Q2/Q3 拍板落实均**无问题**——修复面仅限补测试与文案，不动实现逻辑。
