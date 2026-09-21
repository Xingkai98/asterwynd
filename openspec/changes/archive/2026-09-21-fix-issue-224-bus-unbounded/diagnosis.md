# 诊断：message bus 出口无界（issue #224）

## Symptom

父 agent 通过 `ReadBus` 工具读取编排消息时，单条消息的 `summary` 可原样返回 **30,000 字符**；
通过 `RunPattern` 拿到的编排结果里，`result["bus"]` 可一次性把 **100 条 × 1600 字 = 172,703 字符**
全部折进父 agent 上下文。这两个量都由**子 agent 撰写的内容**决定，父 agent 控制不了。

轮次记录：issue #213 的排查曾把 message bus 判为「已有 bounded 口径」而排除，**该判断是错的**——
#213 归档时已如实更正并把 bus 列为独立 PR2（另立 issue #224）。

## Reproduction

**出口 1 — `ReadBus` 单条无界**

```
bus = MessageBus(max_read_tokens=2000)
bus.publish(sender="worker", topic="finding", summary="x" * 30000)
ReadBusTool(manager).execute()   # manager 的 contextvar 装了该 bus
# 实测：json["messages"][0]["summary"] == "x" * 30000（原样 30,000 字符，无标志）
```

`read()` 的循环（`bus.py:117-133`）按 token 预算累计；当**单条**就超过预算时，`bus.py:122-127`
的规则让这条消息**整条**进入结果（注释：「A single message larger than the window still surfaces
(the newest) so the consumer is never blind to the latest state」）。设计意图（消费者不失明）合理，
但实现后果是**单条无上限**——`token_count` 只用于预算记账，从不截断 `summary` 本身。

**出口 2 — `snapshot_payload()` 无条数、无单条上限**

```
bus = MessageBus(max_messages=100)
for i in range(100):
    bus.publish(sender=f"w{i}", topic="t", summary="y" * 1600)
len(json.dumps(bus.snapshot_payload()))   # 实测：172703
```

`snapshot_payload()`（`bus.py:143-147`）把 `self._messages` 全量 `to_dict()`，两个维度都没有界。
唯一模型面调用点是 `patterns.py:458`（`RunPattern` 的 `result["bus"]`）。

**出口 3 — 发布侧 `max_tokens` 无上界**

`PublishBusMessageTool.execute()`（`subagents.py:261-269`）：`max_tokens = kwargs.get("max_tokens", 400)`，
只有 `estimate_tokens(content) > max_tokens` 时才调 `_summarize`。调用方传 `max_tokens=10**9` 时该
分支永不触发，`content` 原文直接 `bus.publish(summary=content)`。

**出口 4 — `ReadBus` 的**总量**同样无界（本次 grill 新增确认）**

```
bus = MessageBus()            # 默认满载 100 条
for i in range(100):
    bus.publish(sender=f"w{i}", topic="t", summary="z" * 30000)
len(bus.read(max_tokens=10**9))   # 实测：100 条 / 3000000 字符
```

`read()` 的 `max_tokens` / `limit` 两个参数（`subagents.py:306-307`）都由调用方（模型）给且无上界，
故「单条截断」修完后总量仍由被检视方决定。

## Evidence

复现全部在本 worktree 实跑（`PYTHONPATH=. python3`），原始输出：

```
R1 read() 返回同一对象: True                     # got[0] is bus._messages[0]
Q1 max_tokens=10**9 -> 100 条 / 3000000 字符
Q1 默认 kwargs      -> 1 条 / 30000 字符
Q1 snapshot_payload 现状 -> 3012804 字符
Q6 len=4000 -> estimate_tokens=1000  >1000? False
Q6 len=4001 -> estimate_tokens=1000  >1000? False
Q6 len=4003 -> estimate_tokens=1000  >1000? False
Q6 len=4004 -> estimate_tokens=1001  >1000? True
Q3 token_count=7500  (实际字符 30000)
```

`DeclareWorkflow` **不是** bus 出口（推翻初稿 design 的前提）：实跑
`DeclareWorkflowTool.execute()` 返回键为
`['entry','goal','max_nodes','max_runs','nodes','recursion_limit','spec_hash','status','terminal','workflow_id']`，
无 `bus`（`subagents.py:538-562` 手工构造固定 dict）。`scheduler.py:2955-2956` 的 `_envelope()["bus"]`
只经 `run()` 返回值流出，而 `run()` 的返回在 `subagents.py:620`、`:835` 两处都被丢弃，
`patterns.py:378-406` 的 `_legacy_result` 也从不解引用 `envelope["bus"]`，
`parent_envelope()` 在 `scheduler.py:2973` 又把它 pop 掉。**唯一模型面 bus 出口是 `patterns.py:458`。**

独立零记忆 subagent（run `grill-224-r1`）复核了上述全部结论并补充 8 条风险，
见 `reviews/grill-design.md`。

## Root Cause

**模型面出口直接暴露本该 bounded 的字段**——与 issue #212（`arguments`）、#213（`content`/`summary`/
run envelope）**完全同根**。

`#213` 已为仓库确立契约（`manager.py:82-88` 注释、`openspec/specs/subagents/spec.md`、
`openspec/specs/agent-runtime/spec.md`）：

> 模型面**单条内容** SHALL 有固定上限（`TRANSCRIPT_ITEM_LIMIT = 4000`）；该上限 SHALL **独立于
> `max_tokens`**（「界不可被被检视对象影响」）；截断 SHALL 回流布尔标志；全文 SHALL 通过显式引用按需读取。

逐条核对 bus 出口（含 grill 新增的总量维）：

| 契约条目 | bus 出口现状 |
|---|---|
| 单条内容有固定上限 | ✗ `read()` 单条无界；`snapshot_payload()` 单条无界 |
| **总量有固定上限** | ✗ `read()` 的 `max_tokens`/`limit` 由调用方给；`snapshot_payload()` 无条数上限 |
| 上限独立于 `max_tokens` | ✗ 发布侧 `max_tokens` 无上界，可把它调到单条之上；`read(max_tokens=10**9)` 实测 300 万字符 |
| 截断回流布尔标志 | ✗ 根本没有截断，也没有标志 |
| 全文经显式引用按需读取 | N/A（bus 不落盘）——因此**不得**声称有 ref |

唯一的 bounded 口径 `compact_summary(max_chars=2000)` 只被 `manager.py:1492` 用于会话恢复注入，
**不在** `read()` / `snapshot_payload()` 的路径上。

**为什么 `#213` 会漏掉**：`#213` 的排查与修法都围绕 `RunSubagent` 家族的结果出口
（`to_result_dict` → `_format_run_envelope`）展开，那是一条**落盘 + ref** 的路径。bus 是另一条路径——
内存队列、无落盘、无 ref，因此在「按结果出口盘点」时被划到圈外，且其「非权威通道」（D4）的定位被
误读成「已经安全」。二者是不同的数据结构、不同的消费面。

## Recommended Direction

复用 `#213` 的既有契约与常量，不新造口径：

1. **`read()` 单条截断**：返回的每条 `summary` 截到 `BUS_MESSAGE_LIMIT`（= `TRANSCRIPT_ITEM_LIMIT`
   = 4000），`BusMessage` 新增 `truncated: bool`，`to_dict()` 透出 `summary_truncated`。保留「单条
   超窗仍返回最新一条」语义（改为返回**截断后**的最新一条）。**实现必须用 `dataclasses.replace`
   构造新实例**——`read()` 现在返回的是队列里的同一对象（实测 `is` 为 True），原地赋值会污染
   `compact_summary()` 与 checkpoint。
2. **`read()` 总量设界**（grill Q1，待用户确认）：`max_tokens` / `limit` 钳到与 `snapshot_payload()`
   同界的上界，否则单条截断不改变「总量由被检视方决定」这一事实。
3. **`snapshot_payload()` 二维设界**：条数上限 `BUS_SNAPSHOT_LIMIT` + 单条上限，超出部分用
   `messages_total` / `messages_omitted` 显式报告（沿用 `parent_envelope()` 的 `nodes_omitted` 范式）。
   加固在方法本身 → `RunPattern` 与 `scheduler._envelope()` **同时**受界。
4. **发布侧 `max_tokens` 钳上界**：钳到 `BUS_PUBLISH_MAX_TOKENS`，使 summarize 阈值不可能高于单条
   上限。（LLM 摘要分支是 advisory、非硬界，硬界在消费侧 `read()`——措辞须如实。）
5. **常量单一源**：定义在 `bus.py`（零依赖叶子模块），从 `manager.TRANSCRIPT_ITEM_LIMIT` 派生
   （import 无环已由 grill 动态验证）。

## Regression Tests

- `read()`：单条 30,000 字消息 → 返回的 `summary` ≤ `TRANSCRIPT_ITEM_LIMIT` 且 `summary_truncated`
  为 `True`；**且队列原对象未被改动**（`bus._messages[0].summary` 仍为全文，`compact_summary()`
  不受影响）——锁住「不得原地截断」。
- `read()` 总量：满载 100 条 × 30000 字，`read(max_tokens=10**9)` 的返回总量 ≤ 固定上界。
- 改造 `test_read_returns_newest_when_single_message_exceeds_window`：**输入必须真的越界**
  （400 字不越 4000 的界，会让断言恒真而失去判别力）——改用 30,000 字，断言「最新一条仍可见」
  且「已截断」。
- `snapshot_payload()`：100 条满载 → 条数 ≤ `BUS_SNAPSHOT_LIMIT`、`messages_total == 100`、
  `messages_omitted` 正确；单条 30,000 字 → 该条 `summary` ≤ 上限且标志为 `True`。
- `PublishBusMessage`：`max_tokens=10**9` → 读回不超单条上限。
- 常量：`BUS_MESSAGE_LIMIT == TRANSCRIPT_ITEM_LIMIT` 机械锁定（形式按 design D7 定稿的路径）。
- **契约测试**：构造同一份 bus 内容（1 条 30k + 满载 100 条），断言 `ReadBusTool.execute()` 与
  `RunPattern` 的 `result["bus"]` 两条**模型面出口**均不超过固定上限。
- 变异验证：`read()` 截断改 identity / `snapshot_payload()` 去条数上限 / `max_tokens` 不钳 /
  原地截断（`replace` 改回直接赋值）→ 对应测试各自变红。
