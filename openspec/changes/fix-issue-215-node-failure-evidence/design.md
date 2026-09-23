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

### D1 — 状态枚举六值，每个负向态对应一个**实测确认过**的代码成因

字段名 `state`，取值：

| 取值 | 含义 | 代码成因（**grill 逐条复核后订正**） |
|---|---|---|
| `present` | trace 里有失败步骤 | — |
| `clean` | trace 已遍历、**零失败**（正向声明「检查过」） | — |
| `running` | run 未到终态，trace 按设计尚未写入 | 用 `web/session.py:1019-1021` 那份终态字面量判（见 D7），不新造第四份 |
| `empty_trace` | trace 存在但 `steps == []` | **两个**调用点：排队取消 `manager.py:**1086**`；`cancel_subagent_run` 的 running 分支 `manager.py:**1100**`（后者是第二道兜底，常规路径会被 `_run_loop` 的 CancelledError 处理器先置终态）。文案**不得**只写「排队阶段被取消」 |
| `no_trace` | 终态且 `run.trace is None` | `manager.py:1524` 传 `trace=None` 写法存在，但**前置条件 `run.status == "queued"` 恒假**（`_start_task` 在创建 monitor 前已把 status 置 `running`，全仓无写回点）——grill 判定该分支**当前无活跃生产者**，故成因按**防御性**口径写，spec 不得暗示存在活的触发路径 |
| `unavailable` | 解析不到 run 记录 | 至少三条：`queue_full` 把 run 弹出 `session.runs`（`manager.py:**1035**`，守卫在 `:1034`；workflow 内因准入背压预期恒为 0 次，测试只能半合成）；`manager.find_run` 找不到 `run_id`（`manager.py:591-598`）；subagent session 已不在内存（`manager.py:1574-1583` 抛 KeyError 的降级路径） |

**为什么是六个而不是 OTel 式的三四个**：这六个不是分类学上的拆分，而是**代码里真实存在的六条路径**
（上表右列逐条复核）。少一个就会把某条路径错报成另一条——`empty_trace` 与 `no_trace` 尤其不能合并
（前者是「跑都没跑」，后者是「跑了但没留证据」，用户的下一步动作完全不同）。

**grill 反向挑战的缺口（Q4）**：上表漏了 `none` 形态的**四条**路径（route / collect / 未派发 / 下钻时
session 不在内存，`web/session.py:940-947`/`:951-961`/`:906-912`/`:857-861`）。把「route/collect 结构上
不产生 run」与「run 记录解析不到」折叠进同一个 `unavailable`，正是本 Decision 自己禁止的折叠。
grill 推荐新增第七个取值 `not_applicable`，**待用户拍板**。

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

- `single` 形态 → 顶层 `failure_evidence`
- `candidates` 形态 → **每个候选**各自带 `failure_evidence`（`_foreach_candidates` 已经解析出 `run`，
  顺手投影，不新增解析）
- `_item_drilldown_payload`（候选项下钻）→ 顶层 `failure_evidence`
- `none` 形态 → 顶层 `failure_evidence`，按节点类型给 `unavailable` 或「该节点不产生 run」的说明

**理由**：用户点进某个候选，问的就是「这一项为什么不对」；把证据留在容器级会让他再点一次才能看见。

### D5 — 纯读取侧投影，不动写入侧

`run.trace` 的四个终态落点（`manager.py:1334/1410/1425/1444`）**一行不改**。投影从 `run.trace`
（内存里的 dict）读取，O(steps) 遍历、不复制全量 steps（只复制被选中的条目并立即截断）。

**不做 F4 第三条的写入期物化**：那是为了解决跨存储 join 的代价；本 change 的数据源已在内存、且随 run
一起生命周期结束（HTTP 路由本身是内存口径，冷会话一律 404），读取期投影更简单且不引入新的持久化面。

### D6 — 前端落点：**grill 判定原方案不成立，待 Q6 拍板**

原方案是「在既有『任务』tab 里、`drawer-why` 之后加失败证据区，不新增 tab」（理由：F4 显示 W&B Weave
把错误放在 Call tab；「任务」tab 已承载状态/因由/任务，同属「这个节点发生了什么」的问题域）。

**但那条只证明了*渲染*可行，没证明*取数*可行——这是阻塞性缺陷**：

- `renderDrawerTask`（`web/static/workflow.js:1115-1165`）整个函数体**零 `fetch`**，唯一数据源是
  `entry.snapshot` 投影出的 `node`；
- 而 `failure_evidence` 按 D4 只挂在 `/nodes/{id}/transcript` 载荷上，该载荷全仓**唯一**取数入口是
  「对话」tab 的 `fetchTranscript`（`web/static/workflow_transcript.js:55-82`）；
- 两端不在同一条数据通路上，不是「顺手多渲染一段」能补的。

叠加两条硬约束：抽屉**默认**打开在「任务」tab（`web/static/workflow.js:52`/`:1045`）；而正式 spec
明写「前端 SHALL 在切到「对话」tab 时才请求（懒加载）」（`openspec/specs/web-ui/spec.md:836`），
既有浏览器用例 `tests/web_tests/test_workflow_graph_browser.py:488-493` 直接断言打开面板时**不得**有
`/transcript` 请求（该决策的理由写在用例 docstring `:474-476`）。因此「保留任务 tab + 打开即取数」
等于反转一条有成本理由的既往决策。

grill 的推荐是**方案 D**：「对话」tab 承载证据主体 + 「任务」tab 一行来自快照的**有界计数**线索。
逐方案的成本/收益/违反面与三个具体场景例子见 `reviews/grill-design.md` 的 Q6。**待用户拍板后本节重写。**

### D7 — 终态判据复用 web 层既有字面量，不新造第四份

`running` 的判据需要一份「run 终态」清单。项目里已有三份同义副本：`agent/subagent/manager.py:153-155`
（4 值）、`agent/subagent/scheduler.py:88-90`（5 值，含 `queue_full`）、以及 `web/session.py:1019-1021`
的硬编码字面量元组（`("completed", "failed", "cancelled", "budget_exceeded", "queue_full")`）。

本 change **复用 `web/session.py:1019-1021` 那份**（必要时提为模块级常量再引用），**不**在投影函数里
新写第四份字面量——同一语义四份副本会让后续改动漏改一处。

## Open Questions

**独立零记忆 subagent 的 grill 已完成**（`reviews/grill-design.md`，6 条 Confirmed Decisions）。逐项确认中；
每条配具体场景例子，grill 的推荐答案一并记在各条末尾（推荐≠确认，须用户答复后才写进
`reviews/grill-design.md` 的 `## User Confirmation`）。Q4–Q7 为 grill 新发现的开放项，全文见 grill 记录。

### Q1 — 是否加「已恢复」标记（`recovered`）？

**背景**：调研的 F3 发现 OpenInference 用 `exception.escaped: bool` 区分「异常被吸收（重试后成功）」与
「异常逃出去干掉了 run」。对绿色节点而言，「失败了 3 次但最后成功了」与「失败了 3 次就没再管」是完全不同的
两件事——前者是健康的自愈，后者是隐患。

**场景例子**：节点 A 的 trace 里 `Bash` 在 step 7 失败（`3 failed`）、step 13 同样命令成功 → 若只报
「失败 1 条」，用户会以为这个绿节点有问题；若报「失败 1 条（已恢复）」，用户就知道 agent 重试成功了。
节点 B 的 trace 里 `Bash` 在 step 7 失败后再没有同工具的成功步骤 → 报「失败 1 条（未恢复）」。

**代价**：要定义「恢复」判据（同 `tool_name` 的后继 `status == ok`？还是任意后继成功？）并多一轮
trace 扫描。是本 change 的**可选增强**，不加也不影响核心需求成立。

**grill 推荐：不加**——判据在代码上可算（`agent/loop.py:920-926` 的 `tool_call` 步带完整 `arguments`），
但**语义不可靠**：同工具的后继成功可能是另一次不同的调用。改用**事实性**替代：区块标题带 run 上下文
（「该 run 已完成（`completed`）；本 run 内出现 3 次工具失败」）。详细反例见 `reviews/grill-design.md` Q1。

### Q2 — 条目上限 N 取多少？

`FAILURE_EVIDENCE_LIMIT = 5` 是调研里见到的通行默认。取值影响：N 越大用户越不容易漏掉早期失败，但抽屉里
的列表越长。**场景例子**：一个 40 步的 run 里有 9 条失败 → N=5 时用户看到最近 5 条 + 「共 9 条，已截断」。

**grill 推荐：保留 5**，但**前端预览另设短上限**（约 300 字符 + 「预览已截断」note）。理由：4000 是
「单条消息」口径（`web/session.py:727-731`），不是「抽屉里一行」口径；N 只该决定条目数、不该决定体积。

### Q3 — `state == "clean"` 时前端显示什么？

三种候选：(a) 什么都不显示（「没失败」是常态，不占空间）；(b) 显示一行淡色「已检查，无失败记录」；
(c) 只在用户展开时显示。**场景例子**：用户点开一个正常完成的节点，`clean` 态下他应该看到「没有需要担心的
东西」的明确信号，还是干脆看不到这一区（因而也无从知道系统**检查过**）？F2 的教训倾向 (b)——但 (a) 更省
空间。

**grill 推荐：(b)**，且**负向态也必须各显示一行文案**（不能只有 `clean` 显示），否则会退化成
「不显示 = 没事」。详细场景见 `reviews/grill-design.md` Q3。

### Q4 — `none` 形态（route / collect / 未派发）往哪放？（grill 新发现）

D1 的六值里没有它们的容身之处（详见 D1 后的「grill 反向挑战的缺口」）。**grill 推荐扩到 7 个取值**，
新增 `not_applicable`：`state is None` → `unavailable`；`route` / `aggregate+collect` → `not_applicable`；
`not state.subagent_id` 且非上述 → `unavailable` + 「该节点尚未派发」。场景例子见
`reviews/grill-design.md` Q4。

### Q5 — `candidates` 形态每候选带完整证据会放大响应？（grill 新发现）

最坏 200 候选 × 20KB ≈ **4MB** 单个 JSON 响应。**grill 推荐每项带轻量证据**（`state`/`total`/`truncated`
+ 至多 1 条最新失败，单条 ≤400 字符），完整证据只在下钻与 `single` 形态给。详见 `reviews/grill-design.md` Q5。

### Q6 —（阻塞）失败证据的前端落点（grill 判定原 D6 不成立）

见 D6。grill 推荐方案 D，四个方案的改动面/违反面/场景对比见 `reviews/grill-design.md` Q6。

### Q7 — `diagnosis.md` 的两条「死代码」发现怎么归档？（grill 新发现）

`StopReason.ERROR` 死分支（已排除在范围外）+ grill 新发现的 `no_trace` 无活跃生产者。
**grill 推荐记 `docs/known-debt.md` 一条**（受保护路径，需 `artifact-event` 结构化事件）。
拍板：记或不记（不记须说明理由）。详见 `reviews/grill-design.md` Q7。

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
| 六个状态取值被后续改动悄悄合并（正是 issue #215 的失败模式：文档承诺了、实现漂了） | **变异验证**锁定：把 `no_trace`/`empty_trace` 折叠、把 `clean` 当 `no_trace` → 对应测试必须变红 |
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
| 六个状态取值有被后续改动悄悄合并的风险 | 用**变异验证**锁定：把 `no_trace`/`empty_trace` 折叠、把 `clean` 当 `no_trace` → 对应测试必须变红 |
| 候选集 N 项 × 每项投影 → 请求放大 | 单条截断 + 候选数上限（既有 `CANDIDATE_MAX_LIMIT`）双重约束，响应体积仍线性有界 |

### 与既有 spec 的关系

- `openspec/specs/web-ui/spec.md` 的「workflow 节点 transcript 只读接口」requirement 保持不变，本 change
  是**新增**一条 requirement（ADDED），不修改它。
- `openspec/specs/observability/spec.md` 已有 trace 的 `tool_result` `status`/`error_type` 口径
  （`:115`/`:122`/`:147`），本 change **消费**它、不修改它。
