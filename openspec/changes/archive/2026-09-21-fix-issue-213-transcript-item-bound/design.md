# Design — fix-issue-213-transcript-item-bound

## 背景：三个「bounded」概念，两个数，一处漏执行

仓库里已有三处 bounded 预算，本 change 必须**复用而不是新增**：

| 概念 | 位置 | 数值 | 产物形态 |
|---|---|---|---|
| HTTP 单条内容上限 `TRANSCRIPT_CONTENT_LIMIT` | `web/session.py` | 4000（固定） | 截断 + `*_truncated` 布尔 |
| 生产者单条上限 `TOOL_CALL_ARGUMENT_LIMIT` | `manager.py:62-64` | 4000（固定，**与上者同值**） | `_bounded_arguments` → `(text, bool)` |
| run 摘要预算 `BOUNDED_SUMMARY_CHARS` / `_bounded_summary` | `manager.py:49-59` | `min(max(2000, max_tokens*4), TRANSCRIPT_ITEM_LIMIT)`（**上限被钳死**，见 D3） | 文本（自带截断标记） |

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

**修正（用户已拍板）**：出口 2/3/4 用一个**独立于 run 预算的固定上限**
`TRANSCRIPT_ITEM_LIMIT = 4000`。

## 决策 D3c：`summary` 与 `content` 是同一类数据，本就该同口径

**这条推翻了初版把 `summary` 当「派生数据」的论证。** 追赋值链发现字段名在骗人：

```
AgentLoop.run() → RunResult(content=response.content)   # 子 agent 最后那条 assistant 消息
manager.py:1264 → run.summary = result.content          # 原样存下，无任何压缩
to_result_dict() → "summary": self.summary              # 全文
                   "bounded_summary": _bounded_summary  # 同一份文本的截断版
```

`_bounded_summary`（`manager.py:52-59`）只是 `text[:n] + "…[truncated]"`——**是纯截断，不是语义摘要**。
仓库里真正的 LLM 摘要在 `agent/context/summarizer.py`，只被 workflow 聚合器用。

所以：**`summary` 是原始输出，与 `inspect_transcript` 的 `content` 同源同质**。
既然 `arguments` / `content` 已有「模型面与 HTTP 面同数」的既定契约，把 `summary` 一并纳入
是**让口径统一，而不是引入第三个数**——初版担心的「第三个数」是伪问题（它本来就不该分家）。

> 这也更正了主 agent 早先「summary 是派生数据、契约不同」的说法——该说法错误，已作废。

## 决策 D3d：仓库已有「记录存全文、消费时裁剪」的成熟模式

`scheduler.py:2393` 的 `_bounded_output` 就是这条模式（下游视角按节点预算档裁剪），
其 docstring 写明理由是「100 个 leaf 会把 100 份完整结果灌进一个 prompt」。

**本 change 只是把这条已确立的模式补到模型面出口**——那里缺的正是这一道。

**副作用需处理**：`state.summary` 若被提前裁短，聚合器 `_merge_contributions_bounded` 会用
`len(merged) <= budget*4` 误判「没超预算」而**跳过语义压缩**（grill 实测：不传 `full_summary=True`
时 `test_collect_aggregate_compresses_through_the_summarizer` 变红）。故调度器那一处必须显式要全量。

## 决策 D3b：`_bounded_summary` 的「ref 是否存在」不能靠读属性（grill 发现顺序陷阱）

`manager.py:1308` 的 `_bounded_summary(run.summary, run.max_tokens)` 调用发生在
`run.result_ref = result_ref`（`:1311`）与 `run.summary_ref = summary_ref`（`:1313`）**之前**。

若按初版 D4 的字面实现「传 `self.result_ref` / `self.summary_ref`」，此刻两者**都是 `None`**，
落盘件会**永远**只说「已截断」而不给导航——恰好与 D4 的意图相反。

**修正**：落盘路径必须**显式传**「ref 必然存在」（该分支 `store.save_result` 已成功，`manager.py:1301`），
不能读属性。**实际调用点是两个**：`to_result_dict`（按 `result_ref or summary_ref` 判）与
`_write_result_artifacts`（显式传 `True`）。`patterns._worker_entry` **不走** `_bounded_summary`
——D9 落地时它改用 `_clip` + 手工补 `result_ref` 键，故不涉及 `has_ref` 参数。

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

与出口 2/3 同口径（同一个「run 结果摘要」概念）→ 走**固定的** `TRANSCRIPT_ITEM_LIMIT`
（经 `_clip`），不读 `run.max_tokens`——理由同 D3：界不可被被检视对象放大。

## 决策 D10：`bounded_summary` 的预算也要钳（审阅 R1 blocker 的修法）

初版只裁了 `_format_run_envelope` 的 `summary` 键，**同 payload 的 `bounded_summary` 没动**
——它仍由 `max(2000, max_tokens*4)` 生成，`max_tokens` 够大时就是全文。审阅 R1 端到端实测：
模型自撰 `max_tokens=500000` 时 `GetSubagentRunTool` 返回 **34,394 字符**
（`summary=4000` 修好了，`bounded_summary=30000` 是全文）——**比 issue 报告的修复前 34,507 还大**。
「只修一个键 = 没修」。

修法：`_bounded_summary` 的预算钳到 `TRANSCRIPT_ITEM_LIMIT`：
`budget_chars = min(budget_chars, TRANSCRIPT_ITEM_LIMIT)`。
回归测试改成**整包断言**（`HUGE not in json.dumps(payload)`）——因为「只断言一个键」
正是这个洞上一轮溜过去的原因。

**已知副作用（审阅 R2 复核为良性，如实记录以免后人误判为回归）**：`bounded_summary` 同时是
落盘件 `summary_ref` 的来源，钳制后大预算节点的落盘摘要件会**变短**（如 30000 → 4040 字）。
审阅 R2 核对：`save_summary` 只有一个生产写入点、**没有任何生产代码读取其内容**
（下游聚合走 `_bounded_output` 与 `result_ref`，不是 `summary_ref`），全文仍由 `result_ref`
完整保留，故无功能破坏。

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
的字面范围内。

**用户已拍板（Q2）：本 change 不纳入 bus，但措辞必须如实。** 原 Non-Goal 那句
「bus 已有各自的 bounded 口径」是**假话**，已删除；改为下面的如实描述，并另立 issue **#224** 跟踪
（对应 codex 建议的 PR2）。本 change 的标题承诺相应收敛为
「**结果出口**的模型面文本一律 bounded」。

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

## 用户已拍板（grill 停轮确认）

**Q1｜出口 2/3/4 的界由谁定 → 固定硬上限 `TRANSCRIPT_ITEM_LIMIT = 4000`。**
理由（用户认可）：界**不可被被检视对象影响**——子 agent 产出多长不该决定父 agent 收到多少。
`max_tokens` 恰好是被检视侧能影响的参数，当不了安全阀。且经 D3c 更正后，4000 不是「第三个数」
（`summary` 与 `content` 本就同口径）。

**Q2｜bus 是否纳入 → 不纳入本 change，但 Non-Goal 措辞必须改成如实描述。**
本 change 聚焦 PR1（4 个结果出口）；bus 另立 issue。（见「明确不做」节已改写。）

**Q3｜要不要给「被截掉多少」的元数据 → 给。**
只给布尔时模型不知道被裁了 28000 字，可能误判「这就是全部」。补 `summary_full_chars`（全文长度），
让模型能判断值不值得翻页。

**Q4｜UI 是否提示 content 截断 → 补。**
对称于既有的 `arguments_truncated` 提示（约 3 行 JS）。

**Q5｜第三个调用点（`patterns._worker_entry`）传什么 → 补 `result_ref` 字段再传「有 ref」。**
不给 ref 却说「全文在 result_ref」，等于在出口 4 复制本 change 正要消灭的那句假话。

**Q6｜`TRANSCRIPT_ITEM_LIMIT` 的 docstring → 按 D3c 更正后可如实写。**
`summary` 与 `content` 同口径（都是子 agent 原始文本），故 docstring 可写
「约束模型面单条内容：消息 `content`、`summary`、工具调用 `arguments`」——
**这不是说谎，因为 D3c 已确立三者同质**（初版担心「summary 由 run 预算决定」已被 D3 的固定上限取代）。

## 本 change 的交付边界（对应 codex 建议的 PR1）

只做 4 个**结果出口**（`InspectSubagentTranscript` / `GetSubagentRun` / `RunSubagent` /
`CancelSubagentRun`）+ 固定安全阀 + 修假话 + HTTP 取或。

**不在本 change**（各立 issue，codex 建议的 PR2/PR3/PR4）：
- bus（`ReadBus` + `RunPattern.result.bus`）——PR2
- `loop.py` 的工具响应总预算第二道防线——PR3
- `max_tokens` 可达范围约束——PR4（独立的运行资源边界，与本 change 动机不同）
