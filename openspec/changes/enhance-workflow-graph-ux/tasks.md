# Tasks: Workflow 流程图可视化体验增强

> **范围裁决（2026-09-17）**：本 change **不切分**，保持「观测面」定位，按三个里程碑推进，**每个里程碑以实跑收口**（这正是发现 G1 的方式）。`reviews/scope-review.md` 记录了范围审阅的完整论证与两条省法（G3 走投影层、G18 走 WS）。
>
> **里程碑依赖**：M1（语义层）→ M2（展示层）/ M3（下钻层），M2 与 M3 可并行但**都必须等 M1**——否则详情面板会显示陈旧 `reason`（G11）、因果句基于错误规则（G12）。

## 0. 设计追问与审阅（实现前门禁）

- [ ] 0.1 跑独立零记忆 subagent 设计追问 + 完备性查漏 + 范围审阅，产出 `reviews/grill-design.md`（≥3 Confirmed Decisions + Open Questions 停轮确认）、`gap-analysis.md`、`reviews/scope-review.md`。

---

## M1 · 语义层（状态口径与因由正确性）

- [ ] M1.1 **G11** `_reset_subtree` 一并清 `reason`/`error`/`finished_at`/`summary`，以及 foreach 容器的 `items_completed`/`items_failed`/`item_states`（现在只清 status/activations/verdict/targets → 重跑显示上一轮因由 + 负耗时）。回归「route 回边重跑后 `finished_at >= started_at`」。
- [ ] M1.2 **D2b** `TERMINAL_NODE_STATUSES` 加 `skipped`；`_teardown` 的 `pending` 分支加判据（三个条件：`_has_control_incoming` + `activations <= 0` + **每条控制入边的源头 route 都已 `completed`**）；**skipped 判定必须先于 `_budget_stop` 分支**；`_unit_counts` 加独立 `skipped_units` 桶（**不得落 `pending_units`**）。
- [ ] M1.3 **D2b** `_route_verdict` 读上游产出处**旁加** per-edge 记账（`_consumed_edges.add(...)`，`_mark_consumed` 本体不改，只在 `if text:` 内记账与既有三处同构）；回归 C5 `useful_runs`/`redundancy` 逐位不变。
- [ ] M1.4 **G12** `explainNode` **扩签名**（现签名看不到图级 status/diagnostics，「图级停止原因优先」无法实现）；`blocked` 因果沿数据入边**穿透 `blocked` 上游**、收集**全部**未完成/失败上游；**去掉「取 `finished_at` 最早」**（无依据，且 G11 修好前不可信）。
- [ ] M1.5 **G26** 新增图级终态 **`completed_with_failures`**（用户 2026-09-17 拍板，**独立档、不与 `completed` 混用**）：`_drive` 收敛出口若存在任何节点 `failed` → `completed_with_failures`，否则 `completed`；**`budget_exceeded`/`cancelled`/`graph_recursion_exceeded` 仍优先于它**。该档不使整图算失败，但必须让用户一眼看到「有东西没成功」。消费方（benchmark 报告 / `GetWorkflow`）需容忍新值。
- [ ] M1.6 测试：route 未选中分支记 `skipped`（`_route_spec()` 实跑断言 `no` 节点 status）；「route 从未运行时下游不报 skipped」对照用例；「被上游连累优先」对照用例（**须叠一个未满足的 required 依赖**，见 spec 验收构造说明）；有失败节点的图级 status 用例。
- [ ] M1.7 契约影响：确认 `NodeState.to_dict()` 直出 status 无需改码，但 `_envelope` 消费方（benchmark 报告 / `GetWorkflow`）容忍新值；docstring/spec 说明。

## M2 · 展示层（运行可见性 + 诊断数据面）

- [ ] M2.1 **G1（D3 修正）** foreach 计数记账点改为 **task `add_done_callback`**（`_run_foreach_item` **没有 `state` 形参**，「返回处 +1」落不了地）；回调**显式排除** `CancelledError`/`GraphRecursionError`/`WorkflowBudgetExceeded` 计成「失败」。
- [ ] M2.2 **G7** `item_states`（按 index 维护的 per-item 状态）+ `items_running`/`items_completed`/`items_failed`；`items_running` **从 run record 取**（`find_run(...).status == "running"`），不用「已派发未终态」（含 20 个排队）；计数与 `item_states` 投影**只对 `kind == "foreach"`**，不连 `__auto_agg__`。
- [ ] M2.3 **G2/D2c** 项级迁移推帧 + **调度器侧限频**（`_emit_graph_snapshot` 全量重建且无节流；0.1s 窗只合并发送不合并构建）。复用 `GraphEventForwarder` 的 0.1s 窗削峰。
- [ ] M2.4 **D3** 快照加法字段：节点 `reason`（**投影层截断** `_SUMMARY_LIMIT`）、**D3b 图的 `started_at`/`finished_at`（哨兵统一 `null`）**、foreach 计数；白名单同步（节点 `SNAPSHOT_NODE_KEYS` + **图级内联字面量** `:173-176`）。
- [ ] M2.5 **G13** 图级 `budget` 进快照（复用 `_budget_summary()`）；`declared` 态返回 `{}`，前端容忍空 dict。
- [ ] M2.6 **G3** 「排队 vs 在跑」**走投影层省法**（`_graph_node_projection` 里按 run record 投影 `queued`）——**不动状态机、不动 `_dispatch_capacity`**。
- [ ] M2.7 **G14** 图级超限**仍画图** + 告警条补 `current_nodes`/`steps`；图级 status 配色走**独立 `GRAPH_STATUS_COLORS`/`GRAPH_STATUS_LABELS`**，不塞 `NODE_COLORS`。
- [ ] M2.8 **D1** `legendModel()` 从词表同源生成（节点类型 + **8 档**状态 + 5 档边 + channel 线型）+ 图例条 DOM/CSS（桌面展开 / 手机折叠）。
- [ ] M2.9 **D2** 异常态四重编码（色 + 角标 + 边框形状 + 状态词）；**角标字形只用默认字体普遍覆盖的字符**（`⏸` U+23F8 实测渲染成豆腐块，已改 `‖`）。
- [ ] M2.10 **G4/G8** 节点 elapsed（**独立于快照的本地计时器**，终态冻结）+「最后更新于 N 秒前」。
- [ ] M2.11 **D6/D7** 多图 tab 元信息 + 边统计口径 + 并行边等距偏移（在 `layoutGraph` 的 `layoutEdges` 里按 `(from,to)` 分组预扫；`edgePath` 加可选参数保持导出兼容）。**D6 按 Q3 判定（选 A）**：`#N` = 按 `started_at` 排序的秩，**排序也按编号**，运行中用徽标区分；`started_at == null` 排最后；`M/N` 由前端从 `snapshot.nodes` 自算（**不用**快照的 `total/completed/failed`——那是逻辑单元口径且 running 帧不带）；**`TERMINAL_STATUSES`（`workflow.js:16`）加 `completed_with_failures`**。
- [ ] M2.12 **G15** route 判定诊断的渲染落点（route 节点详情 + 图级告警）；`none` union 补 `verdict`/`targets`/`raw` excerpt；**字面标签不匹配也记 miss**。
- [ ] M2.13 **G5** 节点 `task` 字段进快照（详情面板「任务」tab 的数据源）。

## M3 · 下钻层（详情面板 + transcript 路由）

- [ ] M3.1 **D4** 详情抽屉（桌面右 / 手机底，同一 DOM 切 class）+ 分 Tab（任务 / 产出 / 对话）+ `role="dialog"`/`aria-modal`/focus trap/Esc/遮罩关闭；抽屉开合**不改 viewBox**。
- [ ] M3.2 **D4 点击语义拆分（Q2 判定：选 B）**：点节点 = 开详情；**折叠组展开/收起收进详情抽屉**（抽屉里给 `groupLeader` 一个「展开成员 / 收起成员」动作，切换 `expandedGroups` 并重绘）——**不在节点上画独立控件**。**同步更新浏览器 smoke** `tests/web_tests/test_workflow_graph_browser.py:343-369`（`test_collapsed_group_click_expands_members` 现在靠点节点展开，要改成经抽屉展开）+ `style.css:1482` 的 cursor 口径（普通节点也要可点）。（`test_workflow_graph_js.py` 是纯函数单测，无 click 用例，不需改。）
- [ ] M3.3 **D4 只读 transcript 路由**（三态 union）+ **候选集以 `NodeState.subagent_ids` 为权威，不反查 `_sessions`**（孙代 session 会污染）；`index`/`task` 从 run record 取，不靠 `name` 反解；bounded（limit 50 / max 200）。
- [ ] M3.4 **G10** `candidates` 每条补 `reason`（取 `run.reason`，bounded）+ `task`；`single` union 补 `reason`。
- [ ] M3.5 **G17** `reason` **全文出口**（scheduler 侧 reason 从不出现在 transcript 里）；`reason_truncated`/`reason_length`。
- [ ] M3.6 **G9** `trace_digest`（bounded：最近 N 条 `status != ok` 的 `tool_result` + `llm_error`）；**区分 `trace is None` 的三种成因**；**写进 spec**：trace 只在 run 终态可用，故「运行中看此刻在干什么」**做不到**。
- [ ] M3.7 **G18** WS `cancel_workflow` + 前端「停止」按钮（二次确认，文案说清不可逆）+ **修 `reset`**（`remove_session` 前遍历 `list_workflows()` 逐个 `cancel()`）；**与既有 `{"type":"cancel"}` 语义划清边界**（现在它只让待审批失败、run 照跑）。
- [ ] M3.8 「对话」tab transcript 懒加载 + **仅 UI 虚拟化**（50 行聚簇、按簇增删 DOM）+ 刷新节律**定死**（design 现措辞暗示自动刷新但机制未定）+ 暂停按钮**写进 spec**（现在无验收锚点）。

## M4 · 测试、文档与收尾

- [ ] M4.1 前端 node+vm 单测覆盖 M2/M3 各项；**`test_node_colors_cover_seven_tiers`（`test_workflow_graph_js.py:73-80`）是精确相等断言，加第 8 档必红——同步改名/改断言**（design/tasks 此前未点名这个测试）。
- [ ] M4.2 浏览器 smoke（Playwright）：图例可见可折叠、点节点开抽屉、切「对话」tab 触发请求、折叠组独立控件展开。
- [ ] M4.3 benchmark smoke：`uv run asterwynd benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/smoke` 冒烟通过。
- [ ] M4.4 兼容回归：既有无 workflow 会话前端不崩；`_envelope`/`parent_envelope` 结构不变（status 多一个取值）；`test_workflow_graph_js.py` 既有用例继续绿。
- [ ] M4.5 `uv run pytest -q` 全绿；OpenSpec validate + project artifact checker 通过。
- [ ] M4.6 同步 current spec：把 spec delta 合入 `openspec/specs/web-ui/spec.md`；`skipped` 的 MODIFIED 若定在 `multi-agent-collaboration`/`subagents` 同步。
- [ ] M4.7 文档影响检查：`docs/openspec-change-backlog.md`、`docs/architecture.md`、`docs/development-guide.md`。
- [x] M4.8 **补开另立 change 的 GitHub issue**（已完成 2026-09-18）：节点级重跑 [#201](https://github.com/Xingkai98/asterwynd/issues/201) / 运行内事件流 [#202](https://github.com/Xingkai98/asterwynd/issues/202) / 搜索筛选与异常定位 [#203](https://github.com/Xingkai98/asterwynd/issues/203) / 复制与导出 [#204](https://github.com/Xingkai98/asterwynd/issues/204) / 长跑完成通知 [#205](https://github.com/Xingkai98/asterwynd/issues/205)。design Non-Goals 已回写 issue 号。

## 五类另立 change 的 Non-Goals（见 design Non-Goals 节）

节点级重跑 / 运行内事件流 / 搜索筛选（只做压暗）/ 导出分享 / 完成通知 —— 均写进 design Non-Goals 并各开 issue（M4.8）。
