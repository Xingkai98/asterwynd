# Design: workflow 节点失败证据投影

## Context

归档 change `enhance-workflow-graph-ux`（issue #197）交付了 workflow 运行态流程图与节点详情抽屉。它的
M3.6（G9 `trace_digest`）标了 `[x]`，但**全仓零实现**——`openspec/specs/` 无对应 requirement，active 代码
无任何失败证据投影（issue #215）。

`diagnosis.md` 已用探针实测确认缺口：一个 `completed` 的 run 其 trace 里躺着 2 条失败步骤
（`"3 failed, 12 passed"` + `network_timeout`），而节点 transcript 载荷**一个字都不提**（无 `failure_evidence`
键，失败文本零命中）。用户看到的是绿色的节点。

**为什么这与 #213 不重叠**：#213 修的是「单条内容无上限」（长度），本条要的是「哪个工具失败了、为什么」
（投影）。`diagnosis.md` 的 Evidence §3/§4/§5 已逐条实证：Web 出口拿不到工具结果、`run.reason` 只覆盖
整个 run 失败、`StopReason.ERROR` 是死代码（`completed` 覆盖了「跑完了但中途有失败」的全部情况）。

本 change 是**收窄版**：只做归档 design.md:410 坑 (b) 点名的那一件事——节点详情里的 bounded 失败证据，
并区分「没有 trace」与「trace 里没有失败」。通用 `trace_digest`（含正常步骤）归 #202。

## Goals / Non-Goals

**Goals**

1. 节点详情里能读到该 run 的**失败证据**（`status != ok` 的 `tool_result` + 全部 `llm_error`），数据来自
   已经存在的 `run.trace.steps`，**不新增采集**。
2. 「无失败证据」用**显式状态枚举**表达，**SHALL NOT** 把「没有 trace」与「trace 里没有失败」折叠成同一个
   状态——用户在后者可以放心，在前者不能。
3. bounded：最近 N 条 + 单条文本截断 + 总数 + 截断标志，响应体积不随 trace 大小线性增长。
4. 只读，不调 LLM、不写盘、不改执行状态。

**Non-Goals**

- 不做通用 `trace_digest`（含 `llm_iteration` 等正常步骤的投影）。归 [#202](https://github.com/Xingkai98/asterwynd/issues/202)。
- 不做运行中实时失败可见性（`run.trace` 按设计只在终态写入）。归 #202。
- 不改 `run.trace` 的写入时机与结构（四个终态落点一行不动）。
- 不给 HTTP 路由加 `include_tool_results` 开关（那是「要不要在 UI 放全量工具结果」的另一条产品决策）。
- 不修 `StopReason.ERROR` 死分支（属 run 状态机语义，会改变 `completed`/`failed` 判据）。
- 不追溯修改归档 change 的 tasks.md / spec（受保护路径；用户已确认走「补实现收窄版」）。
- 不改 `_envelope` / `parent_envelope` 结构契约。

## 业界调研结论

调研对象：OTel GenAI 语义约定、LangSmith、LangFuse、W&B Weave、OpenAI Agents SDK、OpenInference / Arize
Phoenix，以及编码 agent 的用户面可见性现状。**本工作区无本地参考仓库**（`.dev/reference-repos.txt` 不存在），
findings 全部来自公开文档与规范原文；「本地参考仓库不可用」不构成豁免理由，但如实记录。

### F1 — 「完成但有隐藏的中间失败」是业界默认，不是本仓库特有的 bug

- **LangFuse**：tracing SDK 若不填 `level`，失败的 observation 停在 `level: DEFAULT, statusMessage: ""`，
  文档明确这「与成功的调用无法区分」；社区已就此立项
  ([hermes-agent#81731](https://github.com/NousResearch/hermes-agent/issues/81731))。
- **LangSmith**：子 `tool` run 可以是 `status:error` 而根 run 仍是 `success`——**根 run 的状态不会向上冒泡**；
  且 trace 列表默认按 **Root run** 过滤，文档直言这「rarely what you want」，要看深层失败必须切 **Any run**
  ([Filter traces](https://docs.langchain.com/langsmith/filter-traces))。
- **OTel**：规范**明确要求**「被重试或已处理的错误 SHOULD NOT 记在 span 上」——标准本身就在建议丢掉我们
  想要的证据 ([Recording errors](https://opentelemetry.io/docs/specs/semconv/general/recording-errors/))。

**对本 change 的意义**：需求成立，且「有界失败摘要」没有既有实现可抄——这是差异化，不是追赶。

### F2 — OTel 的 `OK` / `UNSET` 区分印证了「必须用枚举而非布尔」

OTel 三种 span status 构成全序 `Ok > Error > Unset`；`Unset` 是**默认值**，规范要求 instrumentation
「SHOULD NOT 设 `Ok`，除非显式配置」，于是 `Unset` **同时承担**「跑完了没事」与「我们没评估/没记录」两种含义。
这个重载是已知的真实故障源：OpenLit 专门立项要求停止依赖 `StatusCode = OK`，因为符合规范的 success span
留 `Unset`，按 `OK` 过滤的 UI 会静默丢掉健康 span
([OpenLit#300](https://github.com/openlit/openlit/issues/300)、[trace/api.md](https://github.com/open-telemetry/opentelemetry-specification/blob/main/specification/trace/api.md))。

**对本 change 的意义**：**这正是归档 design.md:410 坑 (b) 指出的问题**。OTel 没能区分开，本 change 有条件
区分开——用显式枚举，把「已检查、干净」与「没数据」分成不同取值。

### F3 — 错误字段命名：跟生态对齐，别造第二套词表

- OTel：`error.type` 为 **Conditionally Required**（仅当操作出错），值应为**低基数**标识符；MCP 语义约定里
  `CallToolResult.isError == true` 时 `error.type` SHOULD 为 **`tool_error`**；唯一 well-known 值是 `_OTHER`
  ([gen-ai/mcp.md](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/mcp.md))。
- OpenInference 保留异常属性集：`exception.type` / `exception.message` / **`exception.escaped`**——最后这个
  布尔表示异常**是否逃出了 span 的作用域**，即「被吸收/重试」与「传播出去干掉了 run」之分
  ([semantic_conventions.md](https://github.com/Arize-ai/openinference/blob/main/spec/semantic_conventions.md))。
- OpenAI Agents SDK：`trace_include_sensitive_data=False` 时**不省略错误**，而是用占位文本
  `"Tool execution rejected."` 替换——**证据不可得时给替代物，而不是留空**
  ([Tracing](https://openai.github.io/openai-agents-python/tracing/))。

**对本 change 的意义**：条目的错误字段沿用 trace step 的**既有键名** `status` / `error_type`（它们已经是
`manager.py` 与 `specs/observability/` 的既有词表），不改名；「证据不可得」的负向态**必须带可读原因文案**，
不返回空列表了事。

### F4 — bounded 摘要的通行形状

- 「结构化截断 + 显式省略标记」：保留头尾骨架、逆序回填中段，被省略处放**显式占位符**，**绝不静默丢弃**。
- 「始终报告被省略的数量」：`Parsed N entries, skipped M lines (reason: ...)`。
- LangFuse 的 API **拒绝**按 observation level 过滤 trace，理由是「需要对 observation 级数据做昂贵的 join
  聚合到 trace 上」——**join 应在写入时做，不是读取时**。

**对本 change 的意义**：采用「最近 N 条 + 总数 + 截断标志」三元组；`total` 是**真实失败总数**，不是返回条数
（这就是「报告被省略了多少」）。至于 F4 第三条：本 change 的数据源是**内存里的 `run.trace`**，读取时遍历
是 O(steps) 且不复制，不构成 LangFuse 那种跨存储 join，故仍在读取时投影（见 D5）。

## Decisions

### D1 — 状态枚举**七值**，每个负向态对应一个**实测确认过**的代码成因

字段名 `state`，取值（**Q4 已确认：扩到七个，新增 `not_applicable`**）：

| 取值 | 含义 | 代码成因（**grill 逐条复核后订正**） |
|---|---|---|
| `present` | trace 里有失败步骤 | — |
| `clean` | trace 已遍历、**零失败**（正向声明「检查过」） | — |
| `running` | run 未到终态，trace 按设计尚未写入 | 用 `web/session.py:1019-1021` 那份终态字面量判（见 D7），不新造第四份 |
| `empty_trace` | trace 存在但 `steps == []` | **两个**调用点：排队取消 `manager.py:**1086**`；`cancel_subagent_run` 的 running 分支 `manager.py:**1100**`（后者是第二道兜底，常规路径会被 `_run_loop` 的 CancelledError 处理器先置终态）。文案**不得**只写「排队阶段被取消」 |
| `no_trace` | 终态且 `run.trace is None` | `manager.py:1524` 传 `trace=None` 写法存在，但**前置条件 `run.status == "queued"` 恒假**（`_start_task` 在创建 monitor 前已把 status 置 `running`，全仓无写回点）——grill 判定该分支**当前无活跃生产者**，故成因按**防御性**口径写，spec 不得暗示存在活的触发路径 |
| `unavailable` | 该有 run 但**解析不到**记录 | 三条：`queue_full` 把 run 弹出 `session.runs`（`manager.py:**1035**`，守卫在 `:1034`；workflow 内因准入背压预期恒为 0 次，测试只能半合成）；`manager.find_run` 找不到 `run_id`（`manager.py:591-598`）；subagent session 已不在内存（`manager.py:1574-1583` 抛 KeyError 的降级路径）。**另含「该节点尚未派发」**（`not state.subagent_id` 且非结构上不产生 run，`web/session.py:951-961`）——它的文案要与「run 记录被弹出」区分开 |
| `not_applicable` | **结构上不可能**产生 run | route 节点（`web/session.py:940-947`）与 `aggregate(strategy="collect")`（`web/session.py:951-961` 的 `is_collect` 分支）。这两类节点「不产生 run」是设计使然，报 `unavailable` 会让用户以为数据丢了 |

**为什么是七个而不是 OTel 式的三四个**：这些取值不是分类学上的拆分，而是**代码里真实存在的路径**
（上表右列逐条复核）。少一个就会把某条路径错报成另一条——`empty_trace` 与 `no_trace` 尤其不能合并
（前者是「跑都没跑」，后者是「跑了但没留证据」，用户的下一步动作完全不同）；`not_applicable` 与
`unavailable` 也不能合并（前者是「本来就没有」，后者是「应该有但取不到」）。

**`none` 形态的判据（Q4 确认，按此落代码）**：

- `state is None`（节点不在当前执行计划里，`web/session.py:906-912`）→ `unavailable`
- `node.kind == "route"` 或 `aggregate(strategy="collect")` → `not_applicable`
- `not state.subagent_id` 且非上述 → `unavailable` + 文案「该节点尚未派发」
- 下钻时 subagent 已不在内存（`web/session.py:857-861`，`kind` 被改写成 `none`）→ `unavailable`

**`clean` 是正向声明**：只有在真的把 `steps` 走完、且零失败时才给。这条要写进 spec（见 spec delta 的
「已检查、未发现失败」Scenario）——对应 F2 的教训：`ok` 不能是默认值。

### D2 — bounded：最近 N 条 + 单条截断 + 总数 + 截断标志

- 条目上限 `FAILURE_EVIDENCE_LIMIT = 5`（业界常见的 last-N 默认值）。
- 取向：**最近** N 条（按 trace `step` 序号），显示顺序为**时间正序**——用户看失败序列是从因到果。
- 单条可变长文本（`tool_result.observation` / `llm_error.message`）截断到 `TRANSCRIPT_CONTENT_LIMIT`
  （4000，与节点 transcript 的单条上限**同口径**，复用既有常量而非新造数字），超出置
  `text_truncated`（**grill 订正**：原名 `observation_truncated` 对 `llm_error` 名实不符，见 D3）。
- 返回 `total`（**真实失败总数**，超过 N 时仍报真实值）+ `truncated`（`total > 返回条数`）。

### D3 — 条目字段沿用既有键名，不造第二套词表

每条：`type`（`tool_result` / `llm_error`）、`step`（trace 步骤序号）、`status`、`error_type`、
`tool_name`（`llm_error` 为 `None`）、`observation`（工具结果 truncated 文本）/ `message`（LLM 错误文本）、
`text_truncated`（本条可变长文本被截断）。

**grill 修正两处（原设计不成立）**：

- **`llm_error` 没有 `status`**。`record_llm_error` 只写 `error_type`/`message`（`agent/trace_recorder.py:226`），
  `data` 里**无 `status` 键**，直接 `get("status")` 会得 `None`，与「条目 SHALL 含 `status`」冲突。
  取值写死为：`llm_error` 条目的 `status` **恒为 `"error"`**（由投影合成，不假装来自 trace）。
- **截断标志不能叫 `observation_truncated`**。`llm_error` 被截断的是 `message` 不是 `observation`，
  用 `observation_truncated` 会让键名与被截字段对不上——正是 F3 警告的「同一个词指两件事」。
  统一改名 **`text_truncated`**（对两种条目同义：本条的可变长文本被截断）。
  也**不可**用 `truncated`：该键在载荷顶层已是「条数被截断」语义（`agent/subagent/manager.py:1158`），
  复用会造成语义碰撞。

**命名理由（F3）**：`status` / `error_type` 已是 trace step 与 `specs/observability/` 的既有键，改名会制造
第二套词表；`error_type` 的值域已含 `tool_error`（与 OTel MCP 约定的同名哨兵一致）。

**需要避免的坑（F3 的 LangFuse 教训）**：LangFuse 把 `level` 在 UI 里改名 "Status"，而搜索关键字 `status:`
仍指向 `statusMessage`，造成语义碰撞。本 change 里节点级字段叫 `state`（不是 `status`），条目级叫 `status`，
**两个名字不重名**，不会出现「同一个词指两件事」。

### D4 — 挂载位置：凡是载荷能识别出一个 run，就带上那个 run 的失败证据

规则统一为「与 `reason` 同落点」：

- `single` 形态 → 顶层 `failure_evidence`（**完整**：最近 5 条 × 单条 4000）
- `_item_drilldown_payload`（候选项下钻）→ 顶层 `failure_evidence`（**完整**）
- `candidates` 形态 → **每个候选**各自带**轻量** `failure_evidence`（**Q5 确认**：只带
  `state` / `total` / `truncated` + **至多 1 条**最新失败，单条 ≤400 字符；字段同 D3）。
  完整证据只在下钻与 `single` 形态给。理由：默认 `limit=50`、上限 200，若每候选都带完整证据
  （5 × 4000），最坏响应可达 ~4MB；轻量化后压到 ~90KB 量级。
- `none` 形态 → 顶层 `failure_evidence`，取值按 D1 的判据表（`not_applicable` / `unavailable`）

**理由**：用户点进某个候选，问的就是「这一项为什么不对」；把证据留在容器级会让他再点一次才能看见。
但容器级一次渲染 N 项，体积必须另设更小的预算——所以「容器轻量、下钻完整」。

### D5 — 纯读取侧投影，不动写入侧

`run.trace` 的四个终态落点（`manager.py:1334/1410/1425/1444`）**一行不改**。投影从 `run.trace`
（内存里的 dict）读取，O(steps) 遍历、不复制全量 steps（只复制被选中的条目并立即截断）。

**不做 F4 第三条的写入期物化**：那是为了解决跨存储 join 的代价；本 change 的数据源已在内存、且随 run
一起生命周期结束（HTTP 路由本身是内存口径，冷会话一律 404），读取期投影更简单且不引入新的持久化面。

### D6 — 前端落点：证据主体在「对话」tab，线索在「任务」tab（**Q6 已确认方案 D**）

**原方案（证据区直接放「任务」tab）经 grill 证伪并已废弃**：`renderDrawerTask`
（`web/static/workflow.js:1115-1165`）整个函数体**零 `fetch`**，唯一数据源是 `entry.snapshot` 投影出的
`node`；而 `failure_evidence` 按 D4 只挂在 `/nodes/{id}/transcript` 载荷上，该载荷全仓**唯一**取数入口是
「对话」tab 的 `fetchTranscript`（`web/static/workflow_transcript.js:55-82`）。两端不在同一条数据通路上。

叠加两条硬约束：抽屉**默认**打开在「任务」tab（`web/static/workflow.js:52`/`:1045`）；而正式 spec
明写「前端 SHALL 在切到「对话」tab 时才请求（懒加载）」（`openspec/specs/web-ui/spec.md:836`），
既有浏览器用例 `tests/web_tests/test_workflow_graph_browser.py:488-493` 直接断言打开面板时**不得**有
`/transcript` 请求（该决策的理由写在用例 docstring `:474-476`）。**这两条在本 change 里一个字都不动。**

**确认落地的方案 D（两段式）**：

1. **证据主体进「对话」tab**：在 `web/static/workflow_transcript.js` 的 `paint()` 里、
   `appendBackLink` 之后、按 `payload.kind` 分派之前挂一次 `appendFailureEvidence(host, payload, ctx)`
   ——三形态共用一段逻辑，`failure_evidence` 缺失时静默跳过（老载荷/降级路径不炸）。
   - `single`：区块放在 `transcript-item-note` 之后、`transcript-body` 之前——先看到「有 N 条失败」，
     再往下读对话。
   - `candidates`：每候选行只显示**计数线索**（复用既有 `cand-sub` 子行），详情靠下钻。
   - `none`：`not_applicable` 什么都不显示；`unavailable` 显示一行淡色文案。
2. **「任务」tab 加一行自快照的计数线索**（零请求）：`0` 显示淡色「已检查、无失败」，
   `N>0` 显示「⚠ 本 run 内 N 次工具/LLM 失败 →『对话』tab 查看」（措辞覆盖两种失败口径），`None`（无 trace / 不可用）**不显示**。

**快照计数（Q6 确认的粒度与埋点）**：

- 字段三态 `None` / `0` / `N`（`None` 不显示，避免把「没数据」与「没失败」混为一谈）。
- **在 `_launch_run` 的 `terminal = await self._await_run(...)`（`agent/subagent/scheduler.py:2167`）
  之后算一次**并存进 `reuse_state`（普通节点是 `NodeState`，展开项是 `_ItemRunSlot`）——
  `_run_foreach_item` 复用同一条路径，**一处埋点同时覆盖普通节点与 foreach 展开项**。
  **不**在 `_graph_node_projection` 里每帧现算（那会是每帧 O(节点数 × 步数)）。
- `queue_full` 的早退路径（`:2124-2136`）在 `_await_run` **之前** return，不经过埋点 → 计数为 `None`
  （正是「无数据」该有的取值）。
- 快照 requirement 的加法字段清单 ADDED 一项（`openspec/specs/web-ui/spec.md:497-499`），
  与归档 change 加 `item_states`/`budget` 时走的是同一条路。

**前端文案映射抽纯函数**：把「各 `state` → 文案」与「条目 → 一行摘要」抽成
`web/static/workflow_graph.js` 上的纯函数（先例：`nodeLabel`/`nodeColor`/`explainNode`），
用既有 node+vm harness（`tests/web_tests/test_workflow_graph_ux_js.py:20-33`）锁定——这样不加浏览器
smoke，前端也纳入了变异可见的测试面。

### D7 — 终态判据复用 web 层既有字面量，不新造第四份

`running` 的判据需要一份「run 终态」清单。项目里已有三份同义副本：`agent/subagent/manager.py:153-155`
（4 值）、`agent/subagent/scheduler.py:88-90`（5 值，含 `queue_full`）、以及 `web/session.py:1019-1021`
的硬编码字面量元组（`("completed", "failed", "cancelled", "budget_exceeded", "queue_full")`）。

本 change **复用 `web/session.py:1019-1021` 那份**（必要时提为模块级常量再引用），**不**在投影函数里
新写第四份字面量——同一语义四份副本会让后续改动漏改一处。

## Open Questions（**已全部确认，无未决项**）

7 条开放项经独立零记忆 subagent grill 后逐项抛用户确认，**用户全部采纳 grill 推荐**。答复原文与确认时间
记录在 `reviews/grill-design.md` 的 `## User Confirmation` 节（机械校验：7/7 已确认，0 未确认）。
结论已回写进上面的 Decision：**Q1 → D2/前端区块标题**、**Q2 → D2**、**Q3 → D6/前端文案**、
**Q4 → D1（七值）**、**Q5 → D4**、**Q6 → D6（含快照计数埋点）**、**Q7 → 收尾记 `docs/known-debt.md`**。

要点摘录：

| 项 | 结论 |
|---|---|
| Q1 `recovered` | **不加**。区块标题改为**事实**表述：「该 run 已完成（`completed`）；本 run 内出现 N 次工具失败」。重试轨迹语义归 #202 |
| Q2 条目上限 | `FAILURE_EVIDENCE_LIMIT = 5` 保留；载荷单条仍截 4000；**前端预览另设 300 字符** + note 标注 **「预览已截断（最多 300 字符）」**——R3 订正：「全文见 X」是假承诺，这条路径上并无读到更长文本的入口 |
| Q3 `clean` 显示 | **(b)** 一行淡色「已检查，无失败记录（trace N 步）」。**负向态（`running`/`no_trace`/`empty_trace`/`unavailable`/`not_applicable`）也必须各显示一行文案**，不得退化成「不显示 = 没事」 |
| Q4 `none` 形态 | **扩到七值**，新增 `not_applicable`；判据表见 D1 |
| Q5 candidates 体积 | 每候选只带**轻量**证据（`state`/`total`/`truncated` + 至多 1 条最新失败，≤400 字符）；完整证据只在下钻与 `single` |
| Q6 前端落点 | **方案 D**：「对话」tab 承载证据主体 + 「任务」tab 一行快照计数；计数在 `_launch_run` 的 `_await_run` 之后每 run 算一次 |
| Q6 计数粒度 | **None/0/N 三态**；`0` 显示淡色「已检查、无失败」，`None` 不显示 |
| Q7 死代码归档 | **记 `docs/known-debt.md` 一条**（合并 `StopReason.ERROR` 死分支 + `no_trace` 无活跃生产者），走 `artifact-event` 通道 |



## 审阅闭环记录（报告与 head 的对应关系）

审阅闭环共 6 轮，**每轮都在隔离检出（`/tmp/rev-215`）里跑，零记忆 subagent，审阅者不写本工作区**。
manifest 绑定的是**最终 head**；下表显式说明「PASS 的树」与「后续 commit」的关系（不留猜测空间）：

| 轮次 | verdict | 审阅范围 | 之后的改动 |
|---|---|---|---|
| R1 | CHANGES_REQUESTED（1 中 3 低） | `1a7df92..c37c267` | 修复 + 回归（`bea27d6`） |
| R2 | CHANGES_REQUESTED（2 中 4 低） | `..bea27d6` | 修复 + 回归（`80d2c2b`） |
| R3 | CHANGES_REQUESTED（1 中 5 低） | `..80d2c2b` | 修复 + 回归（`e892e00`） |
| R4 | **PASS**（37 变异 36 杀） | `1a7df92..e892e00` | 4 条低危修复（`63b098d`、`05882d9`，含一处线索措辞口径） |
| R5 | **PASS**（post-PASS 定向确认） | `e892e00..05882d9` | 测试基础设施改动（`91ce796`：确定性视图守卫 + **订正我自己写错的一条注释**） |
| R6 | **PASS**（定向确认，无中等及以上） | `05882d9..91ce796` | 仅订正 R6 指出的两处注释引用错误（本次 commit） |

**口径**：R4/R5/R6 均判 PASS；其后的 commit 都是**低危修复 / 测试基础设施 / 注释订正**，
不含行为变更（唯一的行为相关改动是 `failureCountHint` 的措辞从「工具失败」改为「工具/LLM 失败」，
已在 R5 定向确认）。R6 另报的第三条低危（`switchToWorkflowView` 无行为测试）是**既有**缺口，
按「PASS 后不追低危」的收敛纪律记入 `docs/known-debt.md`、本 change 显式不做。
历轮报告全部随 change 归档（`reviews/building-review.md` + `-r2`…`-r6`），其中 `building-review.md`
是 manifest 绑定的规范报告路径。

## Pre-Implementation Review

非平凡 change（新增 spec requirement + 新增用户面投影字段 + 动既有 HTTP 载荷契约），进入实现前由独立零记忆
subagent 执行 `/grill`，产出结构化决策记录到 `reviews/grill-design.md`（≥3 条 Confirmed Decisions），
Open Questions 停轮抛用户确认后写入 `## User Confirmation`。

**本 change 待 grill 的重点**（不是走过场，是真有开放项）：

1. **Q1 是否加「已恢复」标记**——调研发现的差异化点（F3 的 `exception.escaped`），但判据未定，是本 change
   最可能被砍也可能最被需要的一项。
2. **Q2 条目上限 N 的取值**——5 是调研里的常见默认，但要确认在本项目的实际 trace 规模下是否合适。
3. **Q3 `clean` 态的 UI 处理**——直接关系到 F2 的教训能否落地（用户是否知道系统**检查过**）。
4. **D1 六值枚举是否有过度设计**——需独立审阅者挑战：六个取值是否都有真实路径支撑（design 已逐条给成因，
   但要复审者复核代码）。

### Grill 执行结果（2026-09-23）

独立零记忆 subagent（paseo 托管 `claude/claude-fable-5[1m]`，plan 模式）逐条复核了 design 的代码事实断言，
产出 6 条 Confirmed Decisions 与 7 条 Open Questions，全文见 `reviews/grill-design.md`。**关键结果**：

- **一处阻塞性缺陷**：D6 的「任务」tab 落点在代码里**没有取数通路**（该 tab 零 `fetch`），且改走
  「打开即取数」会违反正式 spec 的懒加载条款（`openspec/specs/web-ui/spec.md:836`）与既有浏览器用例
  ——改判为 Q6 待用户拍板。原报告曾把 D6 列为 Confirmed，**该条已由审阅者主动撤回**。
- **三处代码事实订正**（已回写 D1/D3/D6/D7）：`empty_trace` 行号与第二调用点、`no_trace` 分支**不可达**、
  `queue_full` 弹出点行号。
- **两处字段契约缺口**：`llm_error` 没有 `status` 键；截断标志 `observation_truncated` 对 `llm_error`
  名实不符（改 `text_truncated`）。
- **三处测试/覆盖要求**：体积有界断言须按可杀变异的形状写、三态挂载要有用例、前端文案映射抽纯函数进
  既有 node+vm harness。
- **四个新开放项**（Q4–Q7）：`none` 形态的第七取值、candidates 体积放大、前端落点、两条死代码的去向。

## Risks / Trade-offs

| 风险 | 缓解 |
|------|------|
| 大 trace 把 HTTP 响应撑大（`to_dict()` 含全部 steps 的完整 arguments/observation） | 投影**只遍历不复制**，只对选中的 ≤N 条做单条截断；加「大 trace 响应体积有界」回归测试（任务已列） |
| 七个状态取值被后续改动悄悄合并（正是 issue #215 的失败模式：文档承诺了、实现漂了） | **变异验证**锁定：把 `no_trace`/`empty_trace` 折叠、把 `clean` 当 `no_trace` → 对应测试必须变红 |
| `observation` / `message` 缺失或为空导致投影抛异常 | 逐字段 `get` + 空值降级；专用测试「空 observation 不抛异常」 |
| 候选集 N 项 × 每项投影 → 请求放大 | 单条截断 + 既有 `CANDIDATE_MAX_LIMIT` 双重约束；响应体积仍线性有界 |
| 加键破坏既有 34 条 transcript 用例 | 已确认**无**载荷键集精确相等断言（`grep` 零命中）；全量回归兜底 |
| `clean` 被误当成默认值（F2 的 OTel 老路） | spec 明确 `clean` 是**正向声明**（必须走完 trace 且零失败）；「已检查、未发现失败」单独 Scenario |
| 范围蔓延回通用 `trace_digest` | Non-Goals 显式排除；Q1 若被否，核心需求仍完整成立 |
| 与 #202（运行内事件流）重叠 | 本 change 只投影**失败子集**且只读内存 trace；#202 做全量事件流，边界在 Non-Goals 写清 |

## Testing Strategy

**分层**（对应 `docs/testing-guide.md` 的 CLI/Web/工具协议/AgentLoop 覆盖要求——本 change 属 Web 层）：

| 层 | 测什么 | 落点 |
|---|---|---|
| **Web 路由投影（主）** | 六种状态取值各自的触发路径；bounded（最近 N 条 + 总数 + 截断标志）；单条截断；三态分支各自挂载 | `tests/web_tests/test_workflow_node_transcript.py` |
| **变异验证** | 折叠 `no_trace`/`empty_trace`、`clean` 当 `no_trace`、去掉截断、改成取最早 N 条 → 必红 | 同上（随用例注释标注变异点） |
| **体积有界** | 数百步大 trace 下响应体不随之线性增长 | 同上 |
| **回归** | `tests/web_tests/` 全量 + `tests/agent/subagent/` 全量 | 全套 |
| **端到端** | 与 `diagnosis.md` 相同形状的 trace 走真实 HTTP 路由，确认证据可读出 | 手工验收（tasks 已列） |

**参数教训**（沿用 #213 的教训）：测「超长 observation 被截断」时输入**必须真的超过上限**（用 30000 字），
否则「返回 ≤ 4000」是恒真断言，测不出东西。

**grill 追加的断言形状要求（「体积有界」那条）**：`run.trace` **从不进入 HTTP 响应**，体积有界完全由
「只取 ≤N 条 + 单条截断」保证，与「只遍历不复制」无关。因此**不得**写成
`len(json.dumps(payload)) < 宽松常数`（无失败时本来就小，杀不掉变异）。最小断言集：

1. `len(items) <= FAILURE_EVIDENCE_LIMIT`；
2. `sum(len(item["observation"] or "") + len(item["message"] or "")) <= N * content_limit`；
3. `total == 300`（真实总数，≠ 返回条数）；
4. 构造 **300 步全失败、每条 observation 各 30000 字** 的 trace，使「不截断」「不设上限」两条变异必红。

**grill 追加的覆盖要求**：三态挂载各要有用例（`candidates` 每候选各带、下钻顶层带、`none` 形态状态与文案）；
前端「各 `state` → 文案」的映射抽成 `web/static/workflow_graph.js` 的纯函数，用既有 node+vm harness
（`tests/web_tests/test_workflow_graph_ux_js.py:20-33`）锁定——这样既不加浏览器 smoke，又让
「把 `clean` 当 `no_trace`」这类变异在前端层也可见。

**不做**：不新增浏览器 smoke（前端改动是既有抽屉内加一个区，复用既有 DOM 模式；既有 smoke 已覆盖抽屉
开合与 tab 切换）。若审阅认为需要，可在收尾阶段追加。

## Impact Analysis

### 受影响文件

| 文件 | 改动性质 |
|---|---|
| `web/session.py` | 新增 `FAILURE_EVIDENCE_LIMIT` 常量 + `_failure_evidence(...)` 投影函数；`build_node_transcript_payload` 的三个形态分支 + `_item_drilldown_payload` + `_foreach_candidates` 挂载；复用 `:1019-1021` 的终态字面量（D7） |
| `web/static/workflow.js` | **原定** `renderDrawerTask` 新增「失败证据」区——**grill 判定取数通路不存在，落点待 Q6 拍板**（若走方案 A/D，实际改动落在 `workflow_transcript.js`） |
| `web/static/workflow_transcript.js` | 若 Q6 取方案 A/D：`paint()` 统一挂载失败证据区（三形态共用） |
| `web/static/workflow_graph.js` | 若按 grill 建议：新增「`state` → 文案」纯函数，供 node+vm 测试锁定 |
| `web/static/style.css` | 失败证据区样式（复用既有 drawer 类） |
| `tests/web_tests/test_workflow_node_transcript.py` | 新增回归测试（见 tasks.md） |
| `tests/web_tests/test_workflow_graph_ux_js.py` | 若抽纯函数：前端文案映射用例 |
| `agent/subagent/scheduler.py` | **仅当 Q6 取方案 D**：`NodeState`/`_ItemRunSlot` 加有界计数字段 + `_launch_run` 埋点 + `_graph_node_projection` 投影 |
| `openspec/specs/web-ui/spec.md` | 收尾阶段同步 ADDED requirement（若 Q6 取方案 D，快照加法字段清单另需 MODIFIED；若 Q4 增设第七取值，spec delta 相应扩 Scenario） |
| `docs/architecture.md` | 收尾阶段同步该路由返回形态的描述（grill 指出 `:105` 已不完整） |

### 契约影响

- **加性**：transcript 载荷新增 `failure_evidence` 键。已确认既有测试**无**载荷键集的精确相等断言
  （`grep "set(payload\|payload.keys()\|sorted(payload"` 零命中），加键不破坏既有 34 条用例。
- **`_envelope` / `parent_envelope` 逐字节不变**（不碰 scheduler 投影）。
- **模型面不受影响**：`InspectSubagentTranscript` 工具一行不动。

### 风险

| 风险 | 缓解 |
|---|---|
| `run.trace.to_dict()` 含每次 `tool_call` 的完整 arguments 与 `tool_result` 的 observation | **grill 订正**：真实成本是 **CPU**（O(steps) 遍历），不是响应体积——`run.trace` 从不进入响应。投影只遍历不复制、只对选中的 ≤N 条截断；「体积有界」测试按 Testing Strategy 的四条最小断言写（**不得**写成整包长度比较） |
| `observation` / `message` 可能缺失或为空 | 逐字段 `get` + 空值降级，测试覆盖「空 observation 不抛异常」 |
| 七个状态取值有被后续改动悄悄合并的风险 | 用**变异验证**锁定：把 `no_trace`/`empty_trace` 折叠、把 `clean` 当 `no_trace` → 对应测试必须变红 |
| 候选集 N 项 × 每项投影 → 请求放大 | 单条截断 + 候选数上限（既有 `CANDIDATE_MAX_LIMIT`）双重约束，响应体积仍线性有界 |

### 与既有 spec 的关系

- `openspec/specs/web-ui/spec.md` 的「workflow 节点 transcript 只读接口」requirement 保持不变，本 change
  是**新增**一条 requirement（ADDED），不修改它。
- `openspec/specs/observability/spec.md` 已有 trace 的 `tool_result` `status`/`error_type` 口径
  （`:115`/`:122`/`:147`），本 change **消费**它、不修改它。
