# Design Grilling: 纯门控边的独立状态（workflow-gate-only-edge-status）

独立零记忆 subagent 设计追问记录。本审阅员不读此前任何对话，只以本 worktree
（分支 `gate-only-edge-status/2026-09-18`）的代码与文档为唯一事实来源；所有
`file:line` 均为**逐条 Read 核验**所得，不采信 design.md 的引用数字。

## Reviewer

- **run id**: `grill-workflow-gate-only-edge-status-2026-09-18`
- **时间**: 2026-09-18
- **审阅对象**: `openspec/changes/workflow-gate-only-edge-status/design.md` 的 D1–D4
  （判据与优先级位置、视觉编码、C5 隔离、边界表），并交叉核验 `proposal.md` /
  `tasks.md` / `specs/web-ui/spec.md` delta。
- **基线**: 分支 `gate-only-edge-status/2026-09-18`，HEAD `6dea8a4`（base `master`，
  工作区干净，`git status --porcelain` 为空）。`npx @fission-ai/openspec@1.4.1
  validate workflow-gate-only-edge-status --strict` → **valid**。
- **审阅方法**: (1) 逐条 Read 核验 `agent/subagent/scheduler.py::_edge_status` 及
  优先级链上的全部常量与写点；(2) 把 D1 判据以 **pytest 插件形式注入运行中的
  `_edge_status`**（只写 `/tmp`，不改仓库任何文件）跑真实测试与真实 `scheduler.run()`
  探针，用实测结果代替推演；(3) 用 node + vm 跑前端纯函数核对图例同源与既有断言影响。

## Confirmed Decisions

以下 9 条是本审阅员读代码 + 实跑后可自行收敛的结论，不需要用户拍板；实现时必须按此
写，否则会与既有代码/测试事实冲突。

- **决策**：**D1 的放位（`ready` 之后、兜底之前）与既有五档判据不冲突，`test_edge_status_inactive_fallback` 与 `test_edge_status_ready_and_active_mid_flight` 都不会被误伤——这一条是实测结论，不是推演。** 把 D1 判据注入 `_edge_status` 后跑 `tests/agent/subagent` **461 passed**、`tests/agent` + `tests/benchmark` 2286 passed（3 个失败全部与 `_edge_status` 无关，见下节）。逐条机理：`test_edge_status_inactive_fallback`（`tests/agent/subagent/test_workflow_graph_snapshot.py:265-271`）手工把 `_status` 置 `running` 但两个节点都还是 `pending`，新档要求 `source.status == "completed"` → 不命中，仍落兜底 `inactive`；`test_edge_status_ready_and_active_mid_flight`（同文件 `:230-243`）构造成 a=completed、b=pending，`ready` 分支（`agent/subagent/scheduler.py:2675-2680`）先返回，且新档自带 `target.status != "pending"` 门槛，两条路都不会误判。**审阅员注记**：`ready` 与新档的先后顺序在这里**不影响结果**（新档对 target 的约束已经覆盖），design D1 给出的「必须放 ready 之后」的理由是**语义**上的（进行中态 vs 已定局），不是逻辑上的必要性——实现按 design 放即可，但别把这条理由当成「不这么放就会出错」。
  来源: grill-workflow-gate-only-edge-status-2026-09-18

- **决策**：**D1 判据里的 `source is None` / `target is None` 是防御性分支，在真实图上是不可达路径，照写但必须加注释说明，不要让后续读者以为存在「边指向不存在的节点」这种状态。** `self._states` 由 `self._plan.nodes` 构造（`agent/subagent/scheduler.py:524`），`workflow_graph_snapshot()` 遍历的边也来自同一个 `plan.edges`（`:2536`），而边端点存在性在解析期已被 `_validate_edges` 校验（`agent/subagent/workflow.py:356-361`）。所以 `_edge_status` 里 `self._states.get(...)` 取到 `None` 只可能是「防御」，不影响任何一档的真实分类（design D1 代码块只写了 `target.status != "pending"` 而没有 `target is None` 兜底，实现时若省掉它，一旦发生会直接 `AttributeError` 打断整张图的快照推送——建议保留兜底）。
  来源: grill-workflow-gate-only-edge-status-2026-09-18

- **决策**：**`WorkflowEdge.required` 的字段语义确实是「门控派发」，D1 拿它当必要条件是贴切的；`required=False` 的边在派发门控里被显式跳过。** 字段定义 `agent/subagent/workflow.py:197`（`required: bool = True`），序列化只在为假时输出（`:206-207`），解析期强校验必须是 bool（`:651-655`）。门控侧判据 `_data_deps_satisfied` 的第一句就是 `if not edge.required: continue`（`agent/subagent/scheduler.py:1222-1227`）——非 required 边既不参与派发门控、也不参与汇合语义。因此 D4 的「`required=False` → `inactive`」一行成立，且实现用 `edge.required` 是最省的口径（无需新记账）。
  来源: grill-workflow-gate-only-edge-status-2026-09-18

- **决策**：**目标 `blocked` / `budget_exceeded` 与源 `failed` / `cancelled` 确实被规则 3 先命中，永远到不了新档——D4 表里这两行「视规则 3」的裁决成立。** 两个集合定义在 `agent/subagent/scheduler.py:124-125`，判定位于 `:2667-2670`，在 `active`（`:2671-2674`）、`ready`（`:2675-2680`）与新档之前，且新档要求源 `completed`，与 `_EDGE_BLOCKED_SOURCE_STATUSES = {"failed","cancelled"}` 天然互斥。实现时**不要**在规则 3 之前插入新档——那会把「被连累」报成「依赖已满足」，正是 #197 才刚消灭的那类假话。
  来源: grill-workflow-gate-only-edge-status-2026-09-18

- **决策**：**D4 表「目标 `failed` → `satisfied`」这一行在标准形态下**不可达**，实测结果是 `passed`；实现者不要把「目标 failed」直接理解成 satisfied。** 实测探针（真实 `scheduler.run()`）：`u(subagent, produce) → v(subagent, task 含 BOOM)`，v 抛异常落 `failed`，边 `u→v` 的判定是 **`passed`** 而不是 `satisfied`。机理：`_execute_subagent` 在调用 `_launch_run` **之前**先求值 `task=self._node_task_text(node)`（`agent/subagent/scheduler.py:1541-1546`），而 `_node_task_text` 在 `if text:` 内就 `self._consumed_edges.add((edge.source, edge.target))`（`:2203-2204`）——记账发生在 run 真正跑起来之前，目标随后怎么失败都不影响规则 2 先返回 `passed`。只有「上游产出为空 (`if not text` 跳过) 或目标根本不读输入（如 foreach 字面 `items`）」的形态，目标失败才会落新档。design D4 那行的限定语「未读输入」是**必要条件**而非修饰，实现时按 D1 的完整判据写即可自然得到正确结果。
  来源: grill-workflow-gate-only-edge-status-2026-09-18

- **决策**：**D3 的 C5 隔离成立：新档纯读既有字段，`_consumed_run_ids` / `useful_runs` / `redundancy` 逐位不变。** 把写点穷举核实：`_consumed_edges` 的 `add` 只有 4 处（`agent/subagent/scheduler.py:2164`（`_collect_slots`）、`:2204`（`_node_task_text`）、`:2229`（`_aggregate_task_text`）、`:2318`（`_route_verdict`）），重置只有 1 处（`run()` 开头的 `:707`）；`_consumed_run_ids` 的 `add` 只有 `_mark_consumed` 内部两行（`:772`、`:774`），`useful_runs` 读 `len(self._consumed_run_ids)`（`:2735`），`_redundancy()` 的分子同源（`:2432`）。D1 判据只读 `edge.required` + `source.status` + `target.status` 三个既有字段，**既不写 `_consumed_edges` 也不碰 `_consumed_run_ids`**，所以 `_mark_consumed` 本体一行不改的既有红线（#190 决策 12）自动满足。这条也意味着「`_consumed_edges` 只读不写能否判『未被消费』」的答案是**能**：`passed` 判定（`:2665-2666`）在本档之前先返回，新档能被执行到本身就已经是「不在该集合里」的证明——不需要、也不应该再加一个显式的 `not in` 判断（加了反而制造两处真相）。
  来源: grill-workflow-gate-only-edge-status-2026-09-18

- **决策**：**前端图例确实自动跟随（`legendModel` 遍历 `Object.keys(EDGE_STYLES)`），但「加档必红」的既有断言只有 1 条，且 tasks 只点名了后端那条、前端那条没点名。** 同源性已实测：node + vm 加载加了第六档的 `workflow_graph.js` 后，`legendModel().edges` 的 key 集合与 `edgeStatusStyles()` 的 key 集合**完全一致**（`web/static/workflow_graph.js:243-250` 遍历 `Object.keys(EDGE_STYLES)`，`:249` 对缺失文案 `|| ''` 兜底）。会红的既有断言：`tests/web_tests/test_workflow_graph_js.py:94-96` 的 `assert set(styles) == {"inactive","ready","active","passed","blocked"}`（实测加 key 后为 **False**）。**不会**红的两条：`tests/web_tests/test_workflow_graph_ux_js.py:88-96` 的图例断言是动态的（`== set(call("edgeStatusStyles"))`），`tests/web_tests/test_workflow_graph_browser.py:451-467` 只断言图例文本含「未选中/预算超限/blocked/passed」这 4 个标签，均仍在。**审阅员注记**：design 风险节写「前端既有测试有『边五档』的精确断言（`EDGE_STATUS_TIERS` frozenset、图例覆盖五档），加档必红 → 并在 tasks 里点名」——前半句对，后半句**只对后端成立**：tasks 2.4 确实点名了 `EDGE_STATUS_TIERS`（`tests/agent/subagent/test_workflow_graph_snapshot.py:32`），但前端那条既有断言（`test_edge_status_styles_cover_five_tiers`）没有被任何 task 点名，tasks 3.3 只说「覆盖六档」（新断言口径）。实现时按 tasks 3.3 顺带把它改名/更新即可，不必回改 design。
  来源: grill-workflow-gate-only-edge-status-2026-09-18

- **决策**：**当前 spec 里只有两处列举边状态档位，delta 的两条 MODIFIED 正好覆盖，没有第三处「五档」漏改。** 全仓扫描 `openspec/specs/`：命中「边状态」词表的只有 `openspec/specs/web-ui/spec.md:527`（「边 SHALL 按状态高亮（inactive / ready / active / passed / blocked）」）与 `:591`（「节点状态八档、边状态五档」）。其余 capability（subagents / observability / benchmark 等）的 spec 无任何边档列举。delta 的两条 Requirement 标题 `节点与边状态高亮`、`workflow 图图例` 与 current spec 的标题**逐字一致**（`openspec/specs/web-ui/spec.md:525`、`:589`），`validate --strict` 通过。收尾同步时直接替换这两处即可。**审阅员注记**：delta 里新写的 `satisfied` 语义句中有一处「SHALL NOT 显示为『没有参与』」的措辞，与 Q1 的场景有张力（见 Open Questions）。另：`docs/openspec-change-backlog.md:174` 与已归档 change 的历史记录里也有「边五档」字样，但那是**历史口径**（描述 #189 当时交付的事实），不属于本 change 的事实变化，按 AGENTS.md「只更新当前变更造成的事实变化，历史口径问题另记债务」**不应修改**。
  来源: grill-workflow-gate-only-edge-status-2026-09-18

- **决策**：**渲染层有一个 design D2 未列出的既成事实：`satisfied` 边不会有箭头 marker——这应被视为「明度 + 线宽」之外的第三重编码，而不是缺陷。** `renderEdge` 只给 `edge.status === 'passed' || edge.status === 'active'` 的数据边挂 `marker-end="url(#workflow-arrow-active)"`（`web/static/workflow.js:685-687`）；控制边另挂空心箭头（`:682-684`），其余一律无箭头。所以按 D2/D3 的最小改（只加 `EDGE_STYLES`/`EDGE_STATUS_TEXT` 两项）落地后，`satisfied` 天然无箭头，`passed` 有实心箭头——语义上正好是「有没有数据流过去」，与设计意图一致。tasks 无需为箭头加改动。这条写进记录是为了防止实现者误以为漏了渲染改动，或反过来「顺手补个箭头」把第三重编码抹掉（相关用户选择见 Q3）。
  来源: grill-workflow-gate-only-edge-status-2026-09-18

### 核验方法与既有失败的排除

- **实跑基线（干净树）**：`uv run pytest -q tests/agent/subagent -p gate_patch` → **461 passed**；
  `tests/agent + tests/benchmark` → 2286 passed / 3 failed。
- **3 个失败全部与 `_edge_status` 无关**：
  `tests/agent/code_intelligence/test_tree_sitter_symbols.py::test_tree_sitter_extracts_java_and_kotlin_symbols`
  在**不注入任何补丁**的干净树上同样失败（tree-sitter 语法/版本问题，与 scheduler 无交集）；
  另两条 `tests/benchmark/test_gate_cli.py::test_gate_pass_when_matches_baseline`、
  `tests/agent/test_background.py::test_task_output_truncated` 单独重跑**通过**（顺序/并发
  flake，同样与 `_edge_status` 无交集）。
- **补丁注入方式**：`/tmp/gate_patch.py`（pytest 插件，`PYTHONPATH=/tmp`）在 `_edge_status`
  返回 `inactive` 后追加 D1 判据；未修改仓库任何文件，`git status --porcelain` 全程为空。
- **两个真实 `scheduler.run()` 探针**（`/tmp/probe_gate.py`、`/tmp/probe2.py`、`/tmp/probe3.py`）
  用于核验 D4 边界表与 issue 场景可复现性，结果见上文各决策与 Open Questions 的「场景」。

## Open Questions

> 以下 3 条是本审阅员**无法从代码收敛**的设计选择，必须由用户拍板。每条配一个用本
> change 真实场景构造的具体例子（含参数/输入输出/前后对比）。

- **Q1**: 目标节点是 `skipped`（route 没选它）时，这条 required 数据边该判 `satisfied` 还是 `inactive`？**场景**: 图 `u(scan) → t`（required 数据边），同时 `u → gate(route)`、`gate --default--> t`；`gate` 的 case 是 `{when: "APPROVED", to: "picked"}`，LLM 产出以 `APPROVED` 开头。实跑结果：`picked` 被选中跑完，**`t` 从未被激活**，收尾走 `_is_skipped` 记 `skipped`（节点显示冷灰蓝 + `—` 角标）。此刻 `u→t` 这条 **required 数据边**：`u` 是 `completed`、`t` 已越过 `pending`（= `skipped`），按 D1 判据命中 → 判 **`satisfied`**（实测确认）。两种选择的差别：**(A) 判 `satisfied`** —— 淡绿细线进一个「未选中」节点，图例说「依赖已满足，但产出未被下游读取」；字面为真，但 spec delta 新 Scenario 的 GIVEN 写的是「目标节点**已因该依赖被放行**并越过 pending」，而这里 `t` 根本不是被 `u` 放行的、是 route 没选它，spec 措辞与实现会互相打脸（需同步收紧 GIVEN）。**(B) 判 `inactive`** —— 保持暗灰，理由是这条边**从未起过门控作用**：`_data_deps_satisfied(t)` 虽然为真，但决定 `t` 不跑的是 route 控制边，不是 `u`；这正是本 change 的立项命题（「只标真正起了作用的边」）本身要求的严格性，且无需改 spec 措辞。**推荐 (B) `inactive`**：在 D1 判据上加一条 `target.status != "skipped"` 即可（`skipped` 是 `_resolve_pending_status` 明确定义的「route 判定没走这条」良性终态，`agent/subagent/scheduler.py:1287-1297`、`:1298-1334`）。若选 (A)，则必须同时把 spec delta 与 design D4 表的 GIVEN/措辞从「已因该依赖被放行」改成「已越过 pending」。
  来源: grill-workflow-gate-only-edge-status-2026-09-18

- **Q2**: 动态 foreach（`source:` 形式）**确实读了上游产出**却因为没记 per-edge 账，本 change 后会显示 `satisfied`（图例文案「产出未被下游读取」是**假话**）——要在本 change 顺带补上记账，还是接受并另立 issue？**场景**: spec `planner(subagent) → fan(foreach, task:"work {item}", source:"planner", source_field:"items")`，`planner` 返回 `{"items": ["one","two","three"]}`。**当前 master 实测**：`fan.items == 3`（foreach 展开**确实读了** planner 的产出）、但 `scheduler._consumed_edges == set()`，该边今天判 `inactive`（灰）。**套上 D1 判据后实测**：该边判 **`satisfied`**，手机上显示淡绿细线 + 图例说明「依赖已满足，但产出未被下游读取」——而产出**被读取了**。根因是既有记账缺口：`_source_collection`（`agent/subagent/scheduler.py:2343-2370`）经 `_node_output` 读上游 `summary`/`slots` 时不 `_consumed_edges.add`（对比 `_route_verdict` 在 #197 里补过这处，`:2311-2318`），不是本 change 引入。三个选项：**(a)** 本 change 只加一档，把这个记账缺口另立 issue（cost：本 change 会把「无害的灰」升级成「断言式的错话」）；**(b)** 在本 change 里于 `_source_collection` 真正读出上游产出的返回点旁加 `_consumed_edges.add((<被读节点 id>, node.id))`——与 #197 在 `_route_verdict` 的修法完全同构（旁加，`_mark_consumed` 本体不动 → C5 的 `_consumed_run_ids`/`useful_runs`/`redundancy` 仍零漂移），一行改动，且该边会从「灰」直接变成**正确**的 `passed`；**(c)** 把 `source:` foreach 排除出新档（等于承认这块要等记账修好）。**推荐 (b)**，一行且同构、把假话变成真话；(a) 作为最小 scope 的备选也可接受，但那时必须在 change 里写明这条 known-debt 并开 issue，否则用户下次看到淡绿线会以为「确实没被读」。
  来源: grill-workflow-gate-only-edge-status-2026-09-18

- **Q3**: `satisfied` 边要不要挂箭头 marker？**场景**: 手机端（≤720px 纵向 DAG）看一张跑完的图：`scan→fragile` 是 `passed`（深绿 `#4ade80`、2.2px 粗、**实心箭头**），`scan→fan` 是 `satisfied`（淡绿 `#86efac`、1.6px 细、**无箭头**）。实测灰度合成后（深色画布 `#0b1220`，按各自 opacity 合成）：`passed` 灰阶亮度 0.448、`satisfied` 0.215、`inactive` 0.018——三者可分，但 `satisfied`(0.215) 与 `inactive`(0.018) 的差距在小屏 + 低亮度下主要靠**线宽 1.6 vs 1.4**（差 0.2px）与有无箭头来撑。两种选择：**(A) 保持无箭头**（当前渲染层的天然结果，`web/static/workflow.js:685-687` 只给 `passed`/`active` 挂箭头）——语义正好（没有数据流过去，线端就不画流向箭头），且自动获得第三重编码；**(B) 给 `satisfied` 也挂箭头**——视觉上更强调「这条边是活的」，但会削弱与 `passed` 的区分，且需要显式扩 `:685` 的判断。**推荐 (A) 保持无箭头**，并把「线宽 + 有无箭头」一起写进 spec delta 的「非颜色维度可分辨」口径（现在只写了「明度差或线宽差」）；若用户实测手机上淡绿细线仍与灰难分，再回到 D2 表补一行。
  来源: grill-workflow-gate-only-edge-status-2026-09-18

## User Confirmation

本节先留空：Q1–Q3 需要在停轮确认中由用户逐条答复后，由主 session 回填为
`- **Q1**: 用户答复：<实质内容>；确认时间: <date>` 形式的记录（每条一行，索引与
Open Questions 一一对应，缺一条不得进入实现，`workflow_guard` 会在 Open Questions
未全部确认时拦截代码写入）。审阅员不代用户拍板，以上推荐答案仅是审阅意见。
