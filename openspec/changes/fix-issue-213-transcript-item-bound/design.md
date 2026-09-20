# Design — fix-issue-213-transcript-item-bound

## 背景：三个「bounded」概念，两个数，一处漏执行

仓库里已有三处 bounded 预算，本 change 必须**复用而不是新增**：

| 概念 | 位置 | 数值 | 产物形态 |
|---|---|---|---|
| HTTP 单条内容上限 `TRANSCRIPT_CONTENT_LIMIT` | `web/session.py` | 4000（固定） | 截断 + `*_truncated` 布尔 |
| 生产者单条上限 `TOOL_CALL_ARGUMENT_LIMIT` | `manager.py:62-64` | 4000（固定，**与上者同值**） | `_bounded_arguments` → `(text, bool)` |
| run 摘要预算 `BOUNDED_SUMMARY_CHARS` / `_bounded_summary` | `manager.py:49-59` | `max(2000, max_tokens*4)`（**随节点预算浮动**） | 文本（自带截断标记） |

前两个是**同一个概念的模型面/HTTP 面两面**（注释已定死「不该有两个数」）；第三个是**另一个概念**
（落盘件与信封的摘要预算）。本 change 的四个出口里，出口 1 属于前者，出口 2/3/4 属于后者。

## 决策 D1：截断只发生在**出口投影**，记录层保持全文

`SubagentRunRecord.summary`（`manager.py:132`）是全文，经
`to_result_dict` → `_format_run_envelope` → `scheduler._execute_subagent`（`state.summary = ...`）
→ `_node_task_text` 传导到下游聚合。

**代码层依据（比初版列的测试更强，grill 补充）**：`scheduler.py:2260` 的
`_merge_contributions_bounded` 用 `len(merged) <= budget * CHARS_PER_TOKEN` 决定**是否调
summarizer 压缩**。若 `run.summary` 在记录层被截短，拼接结果会**静默低于**预算阈值而**跳过压缩**——
下游聚合质量无声下降（不报错、不告警）。

钉死记录层全文的是 `test_result_representations.py` 的 `run_a.summary == LONG`（`:90`）、
`test_workflow_result_refs.py` 的 `:101` / `:148`。

> **初版此处引用有误**（grill 纠正）：初版举 `run_envelope["summary"] == LONG`（`:84`）当证据，
> 但那断言的是 **envelope** 而非 `run.summary`——它恰恰是 D2 落地后**唯一会变红**的既有测试
> （grill 实跑确认）。已列入下方「测试影响」，需改为断言
> 「`run.summary` 全文 / `envelope["summary"]` bounded / `bounded_summary` 与之同值」。

在记录层截断 = 上述测试变红 + 聚合质量下降。**否决**。

## 决策 D2：`_format_run_envelope` 默认 bounded，调度器显式要全量

**问题**：`_format_run_envelope` 同时服务两类调用方——
- **工具面**（`GetSubagentRun` / `RunSubagent` / `CancelSubagentRun` 等，`manager.py` 的 7 处）：
  应 bounded
- **调度器内部**（`scheduler.py:2169`）：拿 envelope 喂 `state.summary`，应全量

**候选**：

- **A. 让每个工具调用点自己截** —— 否决。正是「把截断下放给调用方」这个模式导致了本 issue
  （`_project_tool_calls` 的 docstring 早就论证过这一点）。
- **B. 全部改 bounded，调度器改用 `to_result_dict()` 直取全文** —— 否决。调度器要的是完整 envelope
  结构（`subagent_id`/`run_id`/`status`/`reason`），绕开 formatter 会让它自己拼装，重复逻辑。
- **C. `_format_run_envelope(..., *, full_summary: bool = False)`**，默认 bounded，调度器传 `True`
  —— **采用**。

**为什么默认值取 bounded**：新增调用方忘记传参时，**安全侧**（bounded）是默认。
这与「默认无界」的现状相反，正是本 change 要修的方向——**默认值必须是安全的那一侧**。

## 决策 D3：出口 2/3/4 的上限**不能**直接复用 `bounded_summary`（grill 推翻初版）

初版的理由是「避免模型面出现第三个数」。但 **grill 实测证伪**（主 agent 已独立复现）：

`bounded_summary` 的预算 `max(BOUNDED_SUMMARY_CHARS, max_tokens * 4)` 里的 `max_tokens` 是
**run 预算**，而 run 预算由**发起调用的模型自己**设定，两条路径都无上界校验：

- `RunPatternTool.params.worker_max_tokens`（`subagents.py` 的 params 是无约束 `object`）
- `DeclareWorkflow` / `RunWorkflow` 的 `spec.nodes[].max_tokens` → `_positive_int` 只校验
  「正整数」（`workflow.py:451-454`），**无 maximum**

**实测**：

```
parse_workflow_spec({... 'max_tokens': 500000 ...})  → 被接受
_bounded_summary('字'*30000, 500000)                 → 30000 字符（完全没截）
```

即：同一份 30,000 字输出走 `GetSubagentRun`，`max_tokens=None` 时返回 2,040 字符（真的 bounded），
`max_tokens=50000` 时**返回 30,000 字符——与现状一模一样**。

**照初版字面落地，issue #213 的场景在大 `max_tokens` 下不会被修复，而且是静默的**
（测试若只用默认 `max_tokens=None` 构造会全绿）。这直接推翻本 change 的标题承诺
「模型面子 agent 文本**一律** bounded」——那不是界，是调用方可调的旋钮。

**修正**：出口 2/3/4 需要一个**独立于 run 预算的硬上限**。具体取值与是否同时给 `max_tokens`
加上界校验，见 Open Question Q1（需用户拍板）。

## 决策 D3b：`_bounded_summary` 的「ref 是否存在」不能靠读属性（grill 发现顺序陷阱）

`manager.py:1308` 的 `_bounded_summary(run.summary, run.max_tokens)` 调用发生在
`run.result_ref = result_ref`（`:1311`）与 `run.summary_ref = summary_ref`（`:1313`）**之前**。

若按初版 D4 的字面实现「传 `self.result_ref` / `self.summary_ref`」，此刻两者**都是 `None`**，
落盘件会**永远**只说「已截断」而不给导航——恰好与 D4 的意图相反。

**修正**：落盘路径必须**显式传**「ref 必然存在」（该分支 `store.save_result` 已成功，`manager.py:1301`），
不能读属性。且 D9 落地后调用点是**三个**（`to_result_dict` / `_write_result_artifacts` /
`patterns._worker_entry`），第三个的语义见 Open Question Q4。

## 决策 D4：`_bounded_summary` 的截断标记不再撒谎

现状：截断后无条件追加 `"\n…[truncated; full result in result_ref]"`，但 `result_ref` 在
无 workflow 身份时是 `None`（`_write_result_artifacts` 早退）——**全文根本没落盘**。

**候选**：

- **A. 标记改成中性 `"\n…[truncated]"`** —— 简单，但丢掉了「哪里能拿全文」的导航信息，
  在**有** ref 的常见情形下是信息损失。
- **B. 把「ref 是否存在」传进来，按需拼标记** —— **采用**。有 ref 时说全文在哪，
  没有时只说已截断。两个调用点都能判：`to_result_dict()` 有 `self.result_ref`/`self.summary_ref`，
  落盘件路径（`manager.py:1308`）的 ref 必然存在。

**边界**：`to_result_dict()` 里判的是 `summary_ref or result_ref`——**任一存在**即可导航
（`summary_ref` 是摘要件、`result_ref` 是全文，两者都能带读者找到内容）。

## 决策 D5：常量改名 `TRANSCRIPT_ITEM_LIMIT`，旧名保留别名

`TOOL_CALL_ARGUMENT_LIMIT` 现在实际约束 `arguments` / `content` / `summary` 三处，名字误导。

- 新增 `TRANSCRIPT_ITEM_LIMIT = 4000` 承载语义（与 web 的 `TRANSCRIPT_CONTENT_LIMIT` 同族命名，
  一眼能看出是同一契约的两面）
- `TOOL_CALL_ARGUMENT_LIMIT = TRANSCRIPT_ITEM_LIMIT` 保留为**兼容别名**（测试 import 旧名仍通过，
  churn 最小）
- 既有断言 `TOOL_CALL_ARGUMENT_LIMIT == TRANSCRIPT_CONTENT_LIMIT` 升级为**三处同值**

理由：名字误导的执行成本由每个未来读者承担，而 alias 只有一行。
**不**只扩写 docstring 保留骗人的名字。

## 决策 D6：抽取 `_clip(text, limit)`，`_bounded_arguments` 降为薄封装

`_bounded_arguments`（`manager.py:67-77`）本身就是「按上限截断 + 回流标志」的通用逻辑，
与 `arguments` 无耦合。抽成 `_clip(text, limit) -> (text, bool)`：

- `_bounded_arguments(text)` → `_clip(text, TRANSCRIPT_ITEM_LIMIT)`（**签名与返回值不变**，
  保住 #212 的既有断言）
- `_bounded_content(text)` → `_clip(text, TRANSCRIPT_ITEM_LIMIT)`

`_bounded_arguments` 的 docstring 已把「标志必须随文本回流」的理由写死（下游再截时不能把
「其实截过」报成「没截断」）——`_clip` 继承该语义。

## 决策 D7：HTTP 层截断标志改为取或（与 arguments 对称）

生产者开始截 `content` 后，`web/session.py` 的
`"content_truncated": len(content) > content_limit` 会在「生产者截了、本层预算更宽」时报
**false**——谎报。这与 #212 在 `arguments` 上修过的是同一个 bug 的第二例。

改为：`bool(message.get("content_truncated")) or len(content) > content_limit`，
与同函数内 `arguments_truncated` 的写法完全对称。

**注意**：`web/session.py:755-759` 的 `projected` 是**新建** dict（只读 `role`/`content`），
上游的 `content_truncated` 键会被**静默丢弃**——不是覆盖，是丢弃。必须显式透传。

## 决策 D8：不在工具侧加第二道截断

生产者已兜底，工具侧再加一层会产生「谁的标志为准」的新问题（两层各自截、各自报标志，
取或又得再写一遍）。**生产者无条件截断**是 `_project_tool_calls` docstring 已确立的契约，
本 change 只是把 `content` 纳入该契约。

工具描述（description）要同步校正：明说单条内容有上限、全文走 ref——否则模型不知道自己看的是
截断版，可能基于残缺信息下判断。

## 决策 D9：`RunPattern` 的 worker summary 走 bounded

`patterns.py:345` 的 `_worker_entry` 把 `run.summary` 全文塞进 worker dict，`:366-372` 再拼成
一条长文本——**N 个 worker × 全文**，一次调用放大 N 倍。

与出口 2/3 同口径（同一个「run 结果摘要」概念）→ 复用 `_bounded_summary(run.summary, run.max_tokens)`。

## 明确不做

- **不减小 `run.summary`**（D1）
- **不承诺「响应总量有上限」**：单条消息里 `tool_calls` 的**条数**没有代码上限，
  spec 措辞只能是「单条内容」
- **不截 `run_id`**：调用方传入的回显参数，不是放大路径
- **不修 `web/session.py:992` 的 `payload["status"]` 覆盖问题**：与 bounded 无关的既有瑕疵
- **`ReadWorkflowResult` / `GetWorkflow` 已有 bounded 口径**（前者分页 + `total_chars`/`truncated`；
  后者走 `parent_envelope()`，节点文本裁到 `_PARENT_FIELD_LIMIT`）——经 grill 逐条复核成立，不在本次范围

## **初版 Non-Goal 被 grill 证伪**：bus 出口其实无界

初版写「不动 bus……已有各自的 bounded 口径」。grill 实测**推翻**（主 agent 已独立复现）：

| 路径 | 实测 |
|---|---|
| `RunPattern` 返回体的 `result["bus"] = bus.snapshot_payload()` | 100 条 → **172,700 字符**全部进模型上下文 |
| `ReadBus` 的单条 | 30,000 字消息**原样返回** 30,000 字符 |

`bus.py` 只有 `compact_summary(max_chars=2000)` 是有界的，但它被 `manager.py:1427` 用于
**会话恢复注入**，不是 `ReadBus` / `RunPattern` 的路径。

这两处返回的都是**子 agent 撰写的内容**，落在本 change 标题「模型面子 agent 文本一律 bounded」
的字面范围内。**纳入本 change 还是如实改写 Non-Goal 措辞另开 issue，见 Open Question Q2。**

## 风险

| 风险 | 说明 | 处置 |
|---|---|---|
| **界可由模型自己放大** | `bounded_summary` 的预算随 `max_tokens` 浮动，而 `max_tokens` 无上界校验 | **D3 已推翻**，改为独立硬上限（Q1 定值） |
| **唯一变红的既有测试被漏列** | `test_result_representations.py:84` 断言 envelope 全文 | 已列入测试影响（初版漏了） |
| **bus 出口无界被写成 Non-Goal** | 初版声称「已有 bounded 口径」，实测 172,700 字符无界 | 已改写该节；纳管与否见 Q2 |
| **_bounded_summary 顺序陷阱** | `:1308` 早于 `:1311` 赋值，读属性恒 `None` | D3b：落盘路径显式传「有 ref」 |
| 默认值翻转影响未知调用方 | `_format_run_envelope` 默认从「全文」变「bounded」 | 全仓只有 8 处调用（7 工具面 + 1 调度器），grill 已逐一复核；`scheduler.py:2108` 那处虽被 bounded 但只消费 `run_id`/`status`/`reason`，`summary` 无人读，不构成功能 bug |
| `bounded_summary` 文本变化 | 修假话会改可见文本 | 检查既有测试是否断言了该字样，同步更新 |
| 新标志在 HTTP 层被丢 | `projected` 重建 dict | D7 显式透传 + 取或 |
| UI 无提示 | 前端只对 `arguments_truncated` 提示 | 记入 design 的有意边界（content 截断在 UI 上暂无提示），避免范围蔓延 |
| 「响应总量」措辞过满 | tool_calls 条数无上限 | spec 措辞限定为「单条内容」 |

## Open Questions（grill 产出，需用户拍板）

1. **出口 2/3/4 的「界」由谁定？**（最关键，grill 推翻了初版 D3）实测：
   `RunPattern(params={"workers":1,"worker_max_tokens":50000})` → 单 worker 上限 **200,000 字符**；
   `RunWorkflow` 的 `nodes[0].max_tokens=500000` → 上限 **2,000,000 字符**，都可由模型自己写。
   三选一：(a) 出口加**独立硬上限**（如 4000，与 `TRANSCRIPT_ITEM_LIMIT` 同值）；
   (b) 保留「随 run 预算」但对 `max_tokens` 加显式上界校验；(c) 接受现状 + 如实写明边界
   （则本 change 不能声称「一律 bounded」）。**`RunPattern` 的 worker 上限取值随本决策确定。**
2. **bus（`ReadBus` + `RunPattern` 的 `result["bus"]`）是否纳入本 change？**
   （实测 172,700 字符无界，见上节）
3. **`GetSubagentRun` 的 `summary` 变 bounded 后，要不要给「被截掉了多少」的元数据**，
   还是只给布尔 + ref？
4. **UI 上要不要提示 content 被截断？** 现状前端只对 `arguments_truncated` 显示「（参数已截断）」，
   content 截断无提示且是裸切（截断处没有省略号）。
5. **`_bounded_summary` 新增参数的第三个调用点（`patterns._worker_entry`）传什么？**
   该 dict 不含 `result_ref` 字段——传「有 ref」会让模型看到「全文在 result_ref」却拿不到该 ref，
   等于在出口 4 复制本 change 正要消灭的假话。
6. **`TRANSCRIPT_ITEM_LIMIT` 的 docstring 措辞**：不得声称它约束 `summary`（出口 2 的 summary
   由 run 预算决定，不受该常量管），否则是**用新名字说同一句旧谎**。
