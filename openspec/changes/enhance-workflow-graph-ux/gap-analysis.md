# 设计完备性审查（2026-09-17）

用户诉求原话：

> **「目标就是尽可能地对整个 workflow 的流程有更多的掌控感，能看到每个节点运行过程中的情况，如果报错了，为什么报错」**

本审查以此为准绳，派三个独立只读 agent 从三个视角（**运行过程可见性** / **错误可诊断性** / **掌控与操作**）对 design.md 做查漏，逐条 Read 代码核验。结论：**design 在「把已发生的事画好看」上很完整，在三处有系统缺口**——运行中的活信息几乎为零、失败因由断链、控制面 0 覆盖。

严重度：**P0 = 按现 design 实现完仍然看不到 / 是设计错误**；**P1 = 明显影响用户判断**；**P2 = 有价值但可延后**。

---

## 一、「看到每个节点运行过程中的情况」

| # | 严重度 | 问题 | 依据 |
|---|---|---|---|
| G1 | **P0（设计错误）** | **foreach 计数记账点选在唯一不可能产生中间值的时刻**。design/tasks 写「在 gather 结果循环里旁加自增」，而该循环在 `await asyncio.gather(...)` **之后** → `完成 M/N` 整段运行期恒为 0，全部跑完才一次性跳到 N。D5 的立项动机（「看到并行」）在时间维度上落空。 | `scheduler.py:1482`（gather）→ `:1485-1497`（结果循环）；design.md 原 D5、tasks 1.3 |
| G2 | **P0** | **快照只在 7 个迁移点推送**（cancel/run 起/run 止/图超限/预算停/dispatch/节点终态），迁移点之间的内部变化永不外发 → 交互是**跳变**不是渐进。`web/session.py` 的 0.1s 合并窗只去重「已发出的帧」，救不了「从未发出的帧」。design 讨论了合并窗却从未讨论**发射频率本身**。 | `_emit_graph_snapshot` 的 7 个调用点；design.md Q4 段 |
| G3 | **P0** | **`started` 语义错位**：`_dispatch_capacity = max_active(5) + max_queued_runs(20) = 25`，但真正在执行只有 5（manager 的许可池）。最多 25 个节点同时显示蓝色「running」，其中 20 个其实在排队。且 `NodeState.status` **从不写 `queued`**（全仓 `"queued"` 只在读取侧），「等 slot」与「等上游」在图上完全同形。 | `scheduler.py:1199-1200`、`config.py:341-342`、`manager.py:389`；所有 status 赋值点 |
| G4 | P1 | **节点级 elapsed 缺失**。`started_at` 早在快照里，但前端从不读、无计时器 → 跑 90 秒的节点从蓝变绿，中间无信息。design 只在 **tab** 上写了「已跑 42s」，节点本身没有等价要求。 | `_graph_node_projection`；`workflow.js` 全文无 `setInterval/setTimeout` |
| G5 | P1 | **详情面板的 task 模板无数据源**。spec 要求详情显示 task，但快照节点无 `task` 字段，D4 路由三态也不含 → 运行中节点连 summary 都空时，「任务」tab 只剩 id 和状态。 | `scheduler.py:2261-2279`；spec delta 详情 Requirement |
| G6 | P1 | **running 帧不带 `total/completed/failed`**（`_SNAPSHOT_TERMINAL_STATUSES` 门控，#190 明确「running 中带计数会误导」）。而 D6 要求多图 tab 显示 `M/N` 且运行中排在前面——**与 #190 既有决策直接冲突，design 未裁决**。 | `scheduler.py:2252-2256`、`:105-109`；design D6 |
| G7 | P1 | **无 per-item 状态** → D5.2 的迷你堆叠条（「N 个小格各按自身状态着色」）**没有数据源**，只能画全灰。 | 快照无 per-item 字段；spec delta 「表达并行项状态分布」 |
| G8 | P2 | 无「最后更新于 N 秒前」/心跳 → 图卡住时无法区分「慢」与「死」。payload 里其实有 `timestamp`，前端不读。 | `scheduler.py:2250`；`workflow_graph.js` 注释提到但未用 |

## 二、「报错了，为什么报错」

| # | 严重度 | 问题 | 依据 |
|---|---|---|---|
| G9 | **P0** | **失败原因只有一句 `str(exc)`，没有位置**。用户答不出「哪次 LLM 调用/哪个工具」。数据其实存在：`TraceRecorder` 记 `tool_result`（含 `status`/`error_type`/`duration_ms`）与 `llm_error`/`llm_iteration`，run 终态写进 `run.trace`——**全仓 `web/` 对 trace 零引用**。另：`inspect_transcript` 默认剔除 tool 角色消息，而工具报错只在 tool 消息里。 | `scheduler.py:1307-1310`、`manager.py:1215`/`:1124-1126`、`trace_recorder.py:100-129`/`:220-226`、`manager.py:1036-1037` |
| G10 | **P0** | **foreach 项级因由缺失**：候选 `{index, subagent_id, run_id, status, label, summary, started_at, finished_at}` **无 `reason`、无 `item`/`task`**；失败项 `summary` 通常为空（异常 envelope 分支 `append("")`）。点进单项的 `single` union **同样没有 `reason`**（失败原因从不追加进 `session.messages`）。→ issue 原始场景「12 文件 3 个红点」点开每行空白、逐个也不知道是哪个文件。 | design D4 schema；`scheduler.py:1490`；`manager.py:1285-1297` |
| G11 | **P0（设计错误）** | **`_reset_subtree` 不清 `reason`/`error`/`finished_at`**，只清 status/activations/verdict/targets。叠加 `state.reason = state.reason or state.error` 的 `or` 语义 → route 回边重跑（review 循环，本项目常见形态）后，节点显示**上一轮的失败因由**，且 `finished_at < started_at`（**耗时负数**）。D4 面板要显示起止耗时、D6 要显示耗时，全部踩坑。**答错比答不出更糟。** | `scheduler.py:1349-1361`、`:1310`、`:1312-1313`、`:1260` |
| G12 | P1 | **D2 的 blocked 因果规则前提常不成立**：本调度器里**上游 failed 时下游会被派发**（`failed` 在 `TERMINAL_NODE_STATUSES`，门控只要求上游终态），不是 blocked。`blocked` 的真正来源是 `_teardown` 的 pending 分支 + 预算路径，reason 固定为通用句。→ 「沿入边找 failed 上游」多数实跑找不到，落到兜底句「流程结束前该节点一直未就绪」= 没回答。 | `scheduler.py:79-81`、`:1161-1168`、`:750-771`、`:980-984`；design D2 |
| G13 | P1 | **预算只有维度、没有数字**：`reason` 是 `budget exceeded (tokens)`，用户看不到用掉多少/上限多少/哪个节点最贵。`_budget_summary()` 已算出 `{dimensions: {tokens/cost_usd/runs/wall_time_s: {limit, used}}, exceeded, exceeded_dimension}`，但**只挂 `_envelope`（父 agent 面），不进图快照**。本 change 整节解释「为什么停」却不给「花了多少」。 | `scheduler.py:1138-1157`（summary）、`:2243-2259`（快照无 budget）、`:2381` |
| G14 | P1 | **图级超限时不画图**：`graphNotice` 命中即 `renderMessage(...); return` → 用户**失去整幅画面**，看不到哪些节点已完成、卡在哪个环。且 `current_nodes`（超限那刻的 ready 节点 = 回边死循环的直接答案）与 `steps`/`message` 被前端丢弃。`graph_recursion_exceeded` 也不在 `NODE_COLORS`/`NODE_LABELS` → tab 徽标显示裸字符串 + 圆点退化成灰。 | `workflow.js:225-231`、`workflow_graph.js:528-537`、`scheduler.py:138-148` |
| G15 | P1 | **route 判定失败无渲染落点**：`route_ref_misses` 进了快照，但前端唯一读 `diagnostics` 的地方 gate 在 `graph_recursion_exceeded` → 图正常完成时一个字都不显示。且**字面标签不匹配零记录**（只有 `$ref` 未命中记），诊断只覆盖半张网。`state.raw`（上游原文）被显式排除出快照，用户无法理解「为什么走了 default」。 | `scheduler.py:2014-2017`、`:1989-1990`、`:2257-2258`；`workflow_graph.js:528-534` |
| G16 | P2 | **`failed` 混装三种**：per-run 预算超限（`run.status="budget_exceeded"`）与 `queue_full` 都经 `_apply_run_status` 落成节点 `failed` → 用户看到红 ✕，reason 却是「budget exceeded (max_tokens)」，与 D2b 要解决的「分不清」同类。 | `scheduler.py:1748-1750`、`manager.py:1326-1327`/`:931` |
| G17 | P2 | **reason 全文无出口**：400 截断在投影层做，但 D4 路由三态**都没有 `reason` 字段**，transcript 也不含 → codex 的 Q4 建议（详情接口给全文）在 design 里**没有落地路径**。 | design D3/D4；tasks 1.1 |

## 三、「掌控感」——控制面（当前 **0 覆盖**）

全 spec 的用户动作只有 5 个，**没有一个能改变后端任何状态**。设计定位是「把图看懂」（只读观测），Non-Goals 只排除了「编辑拓扑」，**从未写下「本 change 不含运行时控制面」**——所以控制面从未进入讨论。

| # | 严重度 | 问题 | 依据 |
|---|---|---|---|
| G18 | **P0** | **不能取消正在跑的图**。后端 `scheduler.cancel()` 与 `CancelWorkflowTool` 已就绪且立即返回，但 `web/server.py` **零 workflow 路由**、WS 无 workflow 命名空间、前端面板**一个按钮都没有**。命中 issue 主线场景：预算超限是**粘性 stop_new + drain**（只停派发、**不取消在跑的 run**，要等 `_in_flight_nodes==0` 才落终态）→ 用户看着橙图继续烧 token 只能干等。**更糟**：`reset`（最接近「停止」的操作）只 `remove_session` + 重建，**从不调 `cancel()`** → 后台 workflow 继续跑、继续烧，而用户已看不到图。手机端无法 kill。 | `scheduler.py:594-620`、`:936-952`、`:786-796`；`subagents.py:699-724`；`web/server.py` 12 条路由无 workflow；`web/session.py:1016-1034` |
| G19 | P1 | **不能定位/聚焦异常节点**。50–200 节点图上从统计行知道「有 3 个 failed」却**找不到它们在哪**；手机更糟（抽屉占 70vh 盖住图）。零后端成本：节点坐标已在 `layoutGraph` 产物里，viewBox 已有现成设置函数。 | `workflow_graph.js:224-245`、`workflow.js:298-306` |
| G20 | P2 | 无筛选/聚焦。「只看失败的」——建议**压暗（dim）而非过滤**（真过滤会破坏 DAG 布局：隐藏节点需重连边、重算层级）。 | 全前端无 filter/search |
| G21 | P2 | 无复制动作。用户拿到错误最想「贴出去」——详情面板无 copy affordance。成本极低。 | design D4 三 tab 无 copy |
| G22 | P2 | **被淘汰的图找不回来**：`pruneGraphs` 静默 `delete` 第 6 张终态图，无任何「另有 N 张已结束」入口。这与 Non-Goal「不做跨 session 历史」**是两件事**（同 session 内）。最小补法：淘汰时标记 `evicted` 而非 `delete`（内存里 snapshot 还在）。 | `workflow.js:16-19`、`:123-135`、`:320` |

## 四、文档自洽（必须修）

| # | 问题 |
|---|---|
| G23 | **7 档 vs 8 档自相矛盾**：D2b 新增 `skipped`（第 8 档），但 D1 图例、tasks 3.1、spec delta 两处仍写「节点状态七档」（tasks 3.3 又写「八档」）。用户最容易误解的「未选中」可能没有图例行；`NODE_COLORS`/`NODE_LABELS` 需补 `skipped`，`groupStatus` 排除 `skipped` 只写在 design 散文、**tasks 无对应项**。 |
| G24 | **暂停按钮在 spec 里没有验收锚点**：design/tasks 写了「transcript 重排时给暂停按钮」，但 spec 的 Requirement 里**没有任何一条**提到它 → 做了守不住、改了没人拦。另 design 措辞暗示存在自动刷新，但**刷新节律与机制未定**，实现者很可能做成「打开时取一次，之后永不更新」。 |
| G25 | **Non-Goals 措辞两处会导致遗漏**：(a) 没有「运行时控制面」这一栏 → 造成 G18 从未被讨论；(b) 「不做图历史回放（快照只表达当前态）」**连坐**了「同一次运行内的事件流/状态迁移序列」——那恰是「为什么报错」最直接的答案（数据已存在于 `latest_events` 与 `events.jsonl`）。建议收窄为「不做时间轴回放（snapshot scrubber）」。 |

## 五、复核结论

三条 G1/G11 G18 为**最高优先**：
- **G1 是我自己 design 里的硬错误**——按现文档实现完，「完成 M/N」在整段运行期仍是 0，必须改设计（记账点挪到每项完成点 + 项级推帧），不是改实现。
- **G11 会给出错误答案**（陈旧 reason + 负耗时），比不给更糟，且 route 回边重跑是本项目常见形态。
- **G18 是掌控感的硬缺口且后端已就绪**，成本最低、命中 issue 主线场景。

## 六、建议拆分

**纳入本 change**（后端已就绪或纯前端，且直击用户三诉求）：
G1、G2、G3（运行可见性）；G9、G10、G11、G12、G13、G14、G15、G17（可诊断性）；G18、G19（掌控）；G23、G24、G25（自洽）。

**另立 change**（需要新调度器原语或独立决策）：
- 节点级重跑/重试（要新原语 + 一堆语义决策：重跑已完成的节点？下游全级联？预算耗尽后？）
- 运行内事件流/状态迁移时间线（数据齐备，但要先定暴露口径与容量）
- 节点搜索/筛选（真过滤破坏 DAG 布局）
- 导出/分享（PNG/JSON，要定形态）
- 长跑完成通知（与图耦合度低）
