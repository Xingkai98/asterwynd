# Proposal: message bus 出口一律 bounded（fix-issue-224-bus-unbounded）

## Change Type

- primary: bugfix
- secondary:
  - subagents

## Why

issue #224 报告：issue #213 的排查认定 message bus 属「已有 bounded 口径」而排除，**该判断是错的**
（#213 归档时已如实更正并把 bus 列为独立 PR2）。实测确认 `agent/subagent/bus.py` 的两条模型面出口
**没有单条 / 总量上限**，且这两个出口返回的都是**子 agent 撰写的内容**——父 agent 的上下文可被
子 agent 决定体量的文本撑爆，与 #213/#212 同根。

| # | 出口 | 现状 | 实测 |
|---|---|---|---|
| 1 | `ReadBusTool`（`subagents.py` → `bus.read`） | 单条 `summary` 无任何上限。`read()` 有一条「单条超窗仍返回最新一条」的规则（`bus.py:122-127`，由 `test_read_returns_newest_when_single_message_exceeds_window` 钉死） | 单条 30,000 字消息**原样返回** 30,000 字符 |
| 1b | `ReadBusTool` 的**总量**（`max_tokens` / `limit` 两个调用方参数） | 两个参数都由调用方（模型）给且无上界 | 满载 100 条 × 30000 字时 `ReadBus(max_tokens=10**9)` 返回 **100 条 / 3,000,000 字符** |
| 2 | `RunPattern` 返回体的 `result["bus"]`（`patterns.py:458` 的 `bus.snapshot_payload()`） | `snapshot_payload()` 既无条数上限也无单条上限 | 100 条 × 1600 字 → **172,703 字符**全部进父 agent 上下文 |
| 3 | 发布侧 `PublishBusMessageTool` 的 `max_tokens` | 调用方给、**无最大值约束**；只有 `estimate_tokens(content) > max_tokens` 时才 summarize | `max_tokens=10**9` 时该 summarize 分支永不触发，原文直入 bus |
| 4 | `PublishBusMessageTool` 的**回包**（`subagents.py:274` 的 `msg.to_dict()`） | 即发布者刚发的那条（含 `summary`），随 #3 一同无界 | `max_tokens=10**9` + 30,000 字 `content` → 回包 30,000 字符 |

**`snapshot_payload()` 是唯一的模型面 bus 出口来源**（唯一调用点是 `patterns.py:458` 的
`RunPattern`；`scheduler._envelope()` 也调它，但那条路径当前模型面不可达，加固后成为纵深防御）——只修
`patterns.py` 的调用点等于留一个同类漏口，必须在方法本身加固。

**出口 4（发布回包）是 #213 家族的同一形状**：它把子 agent 刚写的文本原样回给发起的模型，`max_tokens`
钳住后 ≤ 单条上限（与出口 1/2 同界）。

**唯一有界的** `compact_summary(max_chars=2000)` 只被 `manager.py:1492` 用于**会话恢复注入**，不是
`read()` / `RunPattern` / `DeclareWorkflow` 的路径——所以「bus 已有 bounded 口径」不成立。

### 与 #213 同根，且是同一条契约的延续

`#213` 给仓库确立的契约（`manager.py:62-63` 注释 + `openspec/specs/{subagents,agent-runtime}/spec.md`）：

> 模型面**单条内容**（`content` / `summary` / `arguments`）SHALL 有固定上限，上限 SHALL 独立于
> run 预算（`max_tokens` 由被检视方自设，界不可被被检视对象影响），截断 SHALL 回流布尔标志，
> 全文 SHALL 通过显式引用按需读取。

bus 的两条出口**逐条违反**：单条无上限、总量无上限、上限（发布侧）随 `max_tokens` 浮动、截断无标志、
无全文引用。`TRANSCRIPT_ITEM_LIMIT = 4000` 已是仓库对「模型面单条子 agent 文本」的固定口径，bus 出口
应当复用同一个数，而不是新造一个。

## What Changes

**A. `MessageBus.read()`：单条截断（+ 标志）与**总量**钳制**

`read()` 返回的每条 `BusMessage.summary` 截到 `BUS_MESSAGE_LIMIT`（= `TRANSCRIPT_ITEM_LIMIT` = 4000，
与模型面其它出口同数），新增 `BusMessage.truncated: bool` 布尔标志；`to_dict()` 透出
`summary_truncated`；被截断条的 `token_count` 同步为重算值。**保留**「单条超窗仍返回最新一条」的
既有语义（消费者不该因窗口小于单条而失明），但返回的是**截断后**的单条，而非全文。

**总量维**（`max_tokens` / `limit` 是调用方参数，单条截断不足以定界）：两个参数 SHALL 被钳到与
`snapshot_payload()` 同界的固定上界（`BUS_SNAPSHOT_LIMIT` 条 / `BUS_SNAPSHOT_LIMIT *
BUS_PUBLISH_MAX_TOKENS` token）。不钳则修完单条后总量**反而**比修复前更大（100 条 × 3000 字 →
3,000,000 字符），「界不可被被检视对象影响」不成立。

**B. `snapshot_payload()`：加条数上限 + 单条上限**

- 条数上限 `BUS_SNAPSHOT_LIMIT`（默认 20，与 `_PARENT_NODES_LIMIT=200` 同属「父面投影条数上限」
  家族但更小——bus 是非权威通道，不值得占父上下文太多）；超出部分不静默丢弃，用
  `messages_total` / `messages_omitted` 显式报告（沿用 `parent_envelope()` 的 `nodes_omitted` 范式）。
- 单条上限同上（`BUS_MESSAGE_LIMIT`），复用 `read()` 的同一截断路径。
- **只截 bus 消息**，不动 `max_read_tokens` 等既有键。

**C. 发布侧 `max_tokens` 补上界 + 闸门含等号**

`PublishBusMessageTool` 的 `max_tokens` 钳到 `BUS_PUBLISH_MAX_TOKENS`（= `BUS_MESSAGE_LIMIT // 4`，
即与单条字符上限等价的 token 数），使「summarize 阈值」不可能被调到单条上限之上；summarize 闸门由
严格大于改为**大于等于**（`estimate_tokens` 向下取整，`>` 会留 4001–4003 字的缝）。

**如实措辞**：这只对齐了**阈值**——`_summarize` 的 LLM 分支是 advisory、非硬界
（`agent/context/summarizer.py`：预算「not a hard guarantee」），单条的**硬保证在消费侧 `read()`**。
发布侧是「阈值对齐 + 消费侧兜底」，**不是**「发布侧也有硬界」。

**D. 常量单一源**

`BUS_MESSAGE_LIMIT` / `BUS_SNAPSHOT_LIMIT` / `BUS_PUBLISH_MAX_TOKENS` 定义在 `agent/subagent/bus.py`
（零依赖叶子模块，无环风险），从 `manager.TRANSCRIPT_ITEM_LIMIT` **派生**（`BUS_MESSAGE_LIMIT =
TRANSCRIPT_ITEM_LIMIT`），保持「模型面单条内容只有一个数」的既成口径。

## Non-Goals

- **不改 `bus.publish()` 的入参契约**：`publish(summary=...)` 仍原样入队（bus 是内存队列，记录本身可
  保留全文）；bounded 化只发生在**出口投影**（`read()` / `snapshot_payload()`），与 #213 的
  「记录保留全文、出口界住」范式一致。
- **不把 bus 变成权威通道**：`workflow-result-aggregation` D4 已定 bus 为非权威，丢消息不影响完成与
  结果正确性。本 change 只加界，不改权威性。
- **不动 `compact_summary()`**：它已有 `max_chars` 口径且只用于会话恢复注入（非模型面工具出口）。
- **不动 `parent_envelope()`**：它已 `payload.pop("bus", None)`，bus 本就不进父 envelope（D4 自洽）。
- **不为 `read()` 新增分页 / 全文引用**：bus 消息**本来就不落盘**（`bus.py` 文档头：「The bus is not
  persisted across runs」）。没有权威落盘件可指，因此**不得**声称「全文在 X」——#213 修掉的
  「假话」不得在 bus 出口复现。截断就是截断，只回流标志。
- **不截 `message_id` / `sender` / `topic`**：它们是调用方与运行时的短标识，不是放大路径。
- **`RunPattern` 仍未 bounded**（grill R2，务必别读成「本 change 修好了 RunPattern」）：实测
  `run_pattern(pattern="orchestrator-worker", params={"workers": 300})` 的总返回体是 165,763 字符，
  其中 `workers[]` **85,180**、顶层 `summary` **80,239**、`bus` 仅 **41**。`workers[]` 的条数由
  `params["workers"]`（无上限）决定，`_legacy_result` 再把 N 条 summary 拼成顶层 `summary`——
  `BUS_SNAPSHOT_LIMIT = 20` 一个字都碰不到这两项。本 change 的标题与范围限定为 **bus 出口**
  （issue #224），`workers[]` / 顶层 `summary` 的条数维**仍无界，另案处理**。
- **`DeclareWorkflow` 不在范围内**：实测其返回键无 `bus`（`subagents.py:538-562` 手工构造固定
  dict，从不调 `snapshot_payload()`）。它**不是** bus 出口，本 change 不改它。

## Capabilities

### Modified Capabilities

- `subagents`：新增 Requirement「message bus 出口 SHALL bounded」——bus 的模型面出口（`ReadBus` 与
  运行结果里的 `bus` 快照）SHALL 对**单条内容**与**条数**同时设固定上限，且该上限 SHALL 与
  `TRANSCRIPT_ITEM_LIMIT` 同值；被截断的单条 SHALL 携带布尔标志。
- `agent-runtime`：新增 Requirement「编排运行结果里的 bus 快照 SHALL bounded」——`RunPattern` /
  `DeclareWorkflow` 返回体中的 `bus` 是父 agent 上下文的一条注入路径，SHALL 受与其它模型面出口同值的
  条数 / 单条上限，SHALL NOT 把无界子 agent 文本折进父上下文。

## Dependencies

- 无新依赖。依赖 #213 已合入的 `TRANSCRIPT_ITEM_LIMIT` 口径（master `abdcedf`）。

## Impact Analysis

**代码影响**

| 文件 | 改动 | 风险 |
|---|---|---|
| `agent/subagent/bus.py` | 新增三个常量（从 `TRANSCRIPT_ITEM_LIMIT` 派生）+ `BusMessage.truncated` + `read()` 单条截断 + `snapshot_payload()` 条数/单条上限 | **中**（`snapshot_payload` 输出形状变化：新增 `messages_total`/`messages_omitted`，`messages` 可能变短） |
| `agent/tools/builtin/subagents.py` | `ReadBusTool` 描述校正（明说单条有上限、截断有标志）；`PublishBusMessageTool` 的 `max_tokens` 钳上界 | 低 |
| `agent/subagent/scheduler.py` | 无需改（`snapshot_payload()` 加固后 #3 自动受界）；仅补回归测试锚点 | 低 |

**契约影响（对外）**

- **模型面 bus 返回变短**：`ReadBus` 单条从「全文」变为 ≤4000 字符并带 `summary_truncated`；
  `RunPattern`/`DeclareWorkflow` 的 `bus.messages` 条数从「最多 `max_messages`(=100)」变为 ≤20（默认），
  且单条 ≤4000。这是**有意的**（现状是父上下文可被子 agent 撑爆），属可观测行为变更，已在 spec 写明。
- **`snapshot_payload()` 新增键**（`messages_total` / `messages_omitted`）：既有消费者若严格断言键集合需
  同步；已 grep 确认当前无生产消费者读这些新键。
- **`bus` 队列本身不变**：`publish()` 仍存全文、`size`/`compact_summary`/drop-oldest 语义不变。

**测试影响**

- 新增：`read()` 单条截断 + 标志；`snapshot_payload()` 条数上限 + `messages_omitted` 正确；单条上限；
  `PublishBusMessage` 的 `max_tokens` 钳上界；契约测试「同一份 bus 内容在模型面出口不超过固定上限」。
- 改造：`test_bus.py::test_read_returns_newest_when_single_message_exceeds_window`（原断言
  `summary == "x"*400` 全文，需改为断言**截断后**长度 + 标志，并保留「最新一条仍可见」语义）。
- 回归：`tests/agent/subagent/`（重点 `test_bus.py`、`test_patterns.py`、`test_scheduler.py`、
  `test_workflow_graph_snapshot*.py`）、`tests/agent/tools/`。
- **参数选择教训（沿用 #213）**：新测试输入必须**真的**超过上限（用 30,000 字，不用 5000），否则
  「返回 ≤4000」恒真。
- **变异验证**：`read()` 截断改回 identity / `snapshot_payload()` 去掉条数上限 / `max_tokens` 不钳
  → 对应测试必须变红。

**文档影响**

- `docs/agent-internals.md` 若描述 bus 的 bounded 口径，需同步（关键词扫描确认）。
- 关键词扫描 `docs/`、`README.md`、`CONTEXT.md` 中与 message bus / 子 agent 结果 / bounded 相关的段落。

## Reference Implementation Research

- research_tier: exempt
- status: disabled
- reason: 属 bugfix（无新增能力面），根因与修法已由 issue #224 给出（复用 #213 的固定上限口径）。上游
  决策已锁定——同根的 issue #213（PR #225，已合入 master `abdcedf`）在同一仓库确立了「模型面出口
  无条件截断 + 标志随文本回流 + 上限独立于 `max_tokens`」的契约与实现范式（`agent/subagent/manager.py`
  的 `_clip` / `TRANSCRIPT_ITEM_LIMIT`，含 `openspec/changes/archive/2026-09-21-fix-issue-213-transcript-item-bound/`
  的完整决策记录）；条数上限的省略报告沿用 `workflow-graph-visualization`（archive 2026-09-15）确立的
  `nodes_omitted` 范式。本 change 是把该既有契约执行到漏掉的 bus 出口，无待定设计项。
- findings（本地参考仓库不可用的事实与替代依据）：本工作区**无** `.dev/reference-repos.txt`，也**无**
  `.codegraph/`（均已确认不存在），故无本地参考仓库可对比。替代依据为业界两处明确范式：
  ① NATS 的 `DiscardOld` / JetStream `max_msgs` + 消息大小上限——本仓库 `bus.py` 文档头已自陈
  「NATS DiscardOld semantics」，即发布侧 / 消费侧双重界；② LangGraph `trim_messages` 的
  token-window 语义（`bus.py` 文档头同样自陈），其 `max_tokens` 是**消费**侧界、不与**单条**大小上限
  混同——这正是本 change 要补的那一维（现状 `read()` 的 token window 被「单条超窗仍返回全文」规则
  单点击穿）。
