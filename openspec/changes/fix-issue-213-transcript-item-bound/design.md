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

**两条既有测试直接钉死该不变量**：`tests/agent/subagent/test_result_representations.py` 的
`run_envelope["summary"] == LONG`（9600 字）与 `test_run_summary_keeps_full_text`。

在记录层截断 = 这两条变红 + 聚合质量下降。**否决**。

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

## 决策 D3：run envelope 复用 `bounded_summary` 的值，不引入新常量

出口 2/3/4 的文本是「**一次 run 的结果摘要**」——与 `bounded_summary`（落盘件/信封摘要件）
是同一个产品概念，数值也应一致（`max(2000, max_tokens*4)`）。

若给它们另起一个固定 4000 的预算，模型面的 summary 上限就变成**第三个数**，
恰好违背 #213 要消灭的「两个数」问题。

**实现**：`_format_run_envelope` 在 `full_summary=False` 时把 `summary` 键**替换为**
`bounded_summary` 的值；**保留 `bounded_summary` 键本身**（既有测试
`tests/agent/subagent/test_workflow_result_refs.py:58` 依赖它）。

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
- **不动 bus / `ReadWorkflowResult` / `GetWorkflow`**：已有各自的 bounded 口径
- **不修 `web/session.py:992` 的 `payload["status"]` 覆盖问题**：与 bounded 无关的既有瑕疵

## 风险

| 风险 | 说明 | 处置 |
|---|---|---|
| 默认值翻转影响未知调用方 | `_format_run_envelope` 默认从「全文」变「bounded」 | 全仓只有 8 处调用（7 工具面 + 1 调度器），已逐一确认；调度器显式要全量 |
| `bounded_summary` 文本变化 | 修假话会改可见文本 | 检查既有测试是否断言了该字样，同步更新 |
| 新标志在 HTTP 层被丢 | `projected` 重建 dict | D7 显式透传 + 取或 |
| UI 无提示 | 前端只对 `arguments_truncated` 提示 | 记入 design 的有意边界（content 截断在 UI 上暂无提示），避免范围蔓延 |
| 「响应总量」措辞过满 | tool_calls 条数无上限 | spec 措辞限定为「单条内容」 |

## Open Questions

1. **`GetSubagentRun` 的 `summary` 变 bounded 后，要不要同时保留一个「全文长度」的提示**，
   让模型知道被截了多少？（还是只靠 `summary_truncated` 布尔 + ref 导航？）
2. **`RunPattern` 的 worker summary 上限取哪个**：`bounded_summary`（随节点预算浮动，与出口 2/3
   一致）还是固定 4000（与 inspect 出口一致）？
3. **超长 content 在 UI 上是否要提示**：前端目前只对 `arguments_truncated` 显示「（参数已截断）」，
   content 截断无提示——本次补，还是记为有意边界另开 issue？
