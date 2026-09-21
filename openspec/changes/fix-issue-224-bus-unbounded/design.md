# Design: message bus 出口一律 bounded（fix-issue-224-bus-unbounded）

## 背景

`#213`（master `abdcedf`）把「模型面出现的子 agent 文本一律 bounded」执行到 4 个结果出口，但 bus 的
两条出口（`ReadBus`、`RunPattern`/`DeclareWorkflow` 的 `bus` 快照）被误判为「已有 bounded 口径」而
漏在交付边界外，另立 issue #224。本 change 补上这一维，**复用** `#213` 的常量与范式，不新造口径。

## 决策

### D1：单条上限复用 `TRANSCRIPT_ITEM_LIMIT`，不新造数字

**决策**：`BUS_MESSAGE_LIMIT = TRANSCRIPT_ITEM_LIMIT`（4000），在 `bus.py` 中通过
`from agent.subagent.manager import TRANSCRIPT_ITEM_LIMIT` 派生。

**理由**：`#213` 已把「模型面单条子 agent 文本只有一个数」写进注释与 spec
（`manager.py:62-63`：「『单条内容』在模型面与 HTTP 面是同一个概念，不该有两个数」）。bus 消息的
`summary` 正是「子 agent 撰写的单条文本」，与 `content` / `summary` / `arguments` 同质。新造一个数字
就是把 `#213` 刚消灭的口径分叉重新引入。

**备选与弃用**：
- *用 `BUS_MESSAGE_LIMIT = 2000`（独立数字）* → 弃用：制造「bus 单条上限 2000、其它出口 4000」的
  第二套口径，正是本 change 要根治的病。
- *用 `compact_summary(max_chars=2000)` 的 2000* → 弃用：那个 2000 是**会话恢复注入**的展示预算，
  与「模型面工具出口的单条内容上限」不是同一个概念，混用会让两个数互相牵制。

**导入方向**：`bus.py` 是零依赖叶子模块（只 import `time`/`uuid`/`collections`/`dataclasses`），
`manager.py` 不 import `bus`（`manager.py` 只在类型注解层通过 `agent.subagent.context` 间接关联），
故 `bus.py → manager.py` 的常量导入**无环**。已有先例：`patterns.py:342` 就
`from agent.subagent.manager import TRANSCRIPT_ITEM_LIMIT, _clip`。

### D2：截断发生在**出口投影**，队列保留全文

**决策**：`publish()` 仍原样入队 `summary`；`read()` 与 `snapshot_payload()` 在**返回时**截断。

**理由**：与 `#213` 的范式一致（「bounded 化只发生在出口投影，run 记录本身保留全文」）。bus 队列是
运行期内存结构，`compact_summary()`（会话恢复注入）需要看到相对完整的消息；在入口截断会**不可逆地**
丢失信息，且让「谁截的」难以追溯。

**代价**：内存占用不减（`max_messages` = 100 已兜住条数）。可接受——`max_messages` 本身的界让
极端内存风险不存在，本 change 针对的是**进入父 agent 上下文**的体量。

### D3：`read()` 保留「单条超窗仍返回最新一条」，但返回**截断后**的单条

**决策**：`bus.py:122-127` 的规则保留其**语义**（消费者不该因窗口小于单条而失明），但该条消息的
`summary` 经 `BUS_MESSAGE_LIMIT` 截断后返回，`truncated=True`。

**理由**：原规则的设计意图正确（`#213` 的解法也不是删掉它，而是在出口截断），问题只在于它成了
「单条无界」的后门。截断后，「最新状态可见」与「体量有界」同时成立。

**备选与弃用**：
- *删掉该规则、超窗就返回空* → 弃用：改变既有正确语义（消费者失明），且会让既有的
  `test_read_returns_newest_when_single_message_exceeds_window` 从「改断言」变成「删测试」，掩盖
  真实行为回归。
- *超窗时返回该条的前 N 字（不设标志）* → 弃用：无标志的截断是 #213 定义的「假话」来源。

### D4：`snapshot_payload()` 条数上限 = 20，超出显式报告（Q2/Q4 已确认）

**决策**：`BUS_SNAPSHOT_LIMIT = 20`；保留**最新** 20 条（与 `read()` 的「取最近」语义一致，与
`max_messages` 的 drop-oldest 一致），输出 `messages_total` / `messages_omitted`。界施加在
`snapshot_payload()` **方法本身**，SHALL NOT 只在调用点加固。

**修正（grill Q2）**：初稿写「`RunPattern` 与 `DeclareWorkflow` 走同一个方法，两个调用点同时受界」，
**与代码不符**。实跑 `DeclareWorkflowTool.execute()` 返回键无 `bus`（`subagents.py:538-562` 手工构造
固定 dict，从不调 `snapshot_payload()`）。**唯一模型面 bus 出口是 `patterns.py:458`（`RunPattern`）。**
`scheduler._envelope()` 的 `payload["bus"]`（`scheduler.py:2956`）当前**模型面不可达**——它只经
`run()` 返回值流出，而该返回在 `subagents.py:620`、`:835` 两处都被丢弃，`parent_envelope()` 又在
`scheduler.py:2973` 把它 pop 掉。加固放在方法本身，使这条不可达路径成为**纵深防御**（未来若有工具
直接吐出 `run()` 的返回值，不会成为新漏口）。用户确认：spec 措辞改为「界 SHALL 施加在
`snapshot_payload()` 本身」。

**理由**：
- **条数推导（Q4）**：20 条 × 4000 字 = **80,000 字符**。同仓库既有父面投影口径：图节点
  `_PARENT_NODES_LIMIT = 200` × `_PARENT_FIELD_LIMIT = 200` = **40,000 字符**，且被
  `test_bounded_envelope.py:166` 用 `< 60_000` 钉住。本项与节点投影合计 ≤ **120,000 字符**，低于
  `#213` 实测的修复前量级（172,703）的 **70%**——即「父面新增一条注入路径，仍把总量压回既有口径
  之下」。用户确认保留 20、以该推导替代拍脑袋。
- **方向**：取**最近** 20 条而非最早 20 条——与 `read()` 的「取最近」和 `max_messages` 的
  drop-oldest 一致（最新状态最相关）。
- **显式报告**：沿用 `parent_envelope()` 的 `nodes_total`/`nodes_omitted` 范式（archive
  2026-09-15 `workflow-graph-visualization`）。静默截断会把「没消息」与「消息被省略」报成同一件事。

**备选与弃用**：
- *上限 = `max_messages`（100，即不设条数界）* → 弃用：100 × 4000 = 400k 字符仍可撑爆父上下文，
  等于条数维没修。
- *上限 = `_PARENT_NODES_LIMIT`（200）* → 弃用：那是**图节点**的界（节点文本已裁到 200 字符），
  与 bus 的 4000 字符单条不可比；200 × 4000 = 800k，更糟。
- *改成 10（对齐节点投影 40k 量级）* → 弃用（用户确认）：20 的推导见上，改 10 需连带改 spec/测试，
  而 80k 在既定总量预算内。
- *不报告 omitted* → 弃用：静默截断违反 `#213` 的诚实原则与仓库「不报假话」规则。

### D4b：`read()` 的**总量**上限与快照同界（grill Q1 阻塞项，用户确认）

**决策**：`read()` 的 `max_tokens` / `limit` 两个调用方参数 SHALL 被钳到与 `snapshot_payload()` 同界
的上界——`max_tokens = min(max_tokens, BUS_SNAPSHOT_LIMIT * BUS_PUBLISH_MAX_TOKENS)`，
`limit = min(limit, BUS_SNAPSHOT_LIMIT)`。

**理由（阻塞项）**：初稿只界住了「单条」，而 `max_tokens` / `limit` 均由调用方（模型）给。
实测：bus 满载 100 条 × 30,000 字时，`ReadBus(max_tokens=10**9)` 返回 **100 条 / 3,000,000 字符**
——单条截断后总量**反而比修复前的 172,703 更大**（因为条数没界）。这与 `manager.py:82-88` 的
「界不可被被检视对象影响」直接冲突：同一个工具，父上下文被灌多少仍由被检视方决定。issue #224 的
标题与 proposal 的核心主张是「出口一律 bounded」，只修单条等于把 #213 的漏口换个坐标留下。
用户确认：一并钳死。

**备选与弃用**：
- *只修单条，总量另开 issue* → 弃用（用户确认）：会让 proposal/spec 的「所有出口」「一律 bounded」
  变成不实陈述，需同步改措辞；且父上下文仍可被 40 万字符灌爆。

### D5：发布侧 `max_tokens` 钳到 `BUS_MESSAGE_LIMIT // 4`

**决策**：`PublishBusMessageTool` 中 `max_tokens = min(max(int(max_tokens), 1), BUS_PUBLISH_MAX_TOKENS)`，
其中 `BUS_PUBLISH_MAX_TOKENS = BUS_MESSAGE_LIMIT // 4`（= 1000，按 `estimate_tokens` 的 4 chars/token 等价于
单条字符上限）。

**理由**：`max_tokens` 是 summarize 的**阈值**——阈值高于单条上限时 summarize 不触发，原文直入 bus。
钳住阈值就堵住了出口 4。

**闸门改 `>=`（grill Q6，用户确认）**：`estimate_tokens` 是 `max(1, len // 4)`（`bus.py:36-38`），
向下取整，而原闸门是**严格大于**（`subagents.py:265`：`if token_count > max_tokens`）。实推：
`content` 长 4001/4002/4003 → `estimate_tokens` = 1000，**不**满足 `> 1000` → 不 summarize，原文直入
bus → 仍需 `read()` 再截一次，即「发布侧承诺 ≤N、消费侧再截一次」的双重截断。初稿 proposal 声称
「两侧同界、不存在双重截断」**是假话**。改为 `if token_count >= max_tokens` 后，4000 字即触发
summarize，发布侧严格 ≤ 单条上限。

**边界补充**：`_summarize` 的 LLM 分支是 **advisory、非硬界**——`agent/context/summarizer.py:33-35`
明说预算「not a hard guarantee」，只把它拼进 prompt（`:169-172`）。故**单条的硬保证在消费侧
`read()`**；发布侧是「阈值对齐 + 消费侧兜底」，design 与 spec 均不得声称发布侧对 LLM 摘要分支有硬界。

**备选与弃用**：
- *不管发布侧，只在消费侧截* → 部分弃用：消费侧截断是**兜底**，但发布侧无界会让 bus 内存里塞满
  无用长文，且 `#213` 的教训是「只修一条路径 = 没修」。两侧同界最稳。
- *闸门保持 `>`、只改措辞为「±3 字内一致」* → 弃用（用户确认）：留一个明知的小缝，后续读者需重推
  才知为何不同界。
- *钳到 `BUS_PUBLISH_MAX_TOKENS = 400`（现默认值）* → 弃用：400 tokens ≈ 1600 字符，比单条上限窄
  4 倍，会把本来合规的消息也强行 summarize，改变默认行为。
- *给 `max_tokens` 加 schema `maximum`* → 弃用：JSON Schema 的 `maximum` 不被所有 provider 强制，
  且工具参数校验不是当前架构的既有闸门；在 `execute()` 内钳是唯一可靠点。

### D6：不设「全文引用」——bus 无落盘件，截断只报事实

**决策**：bus 的截断**不**提供 `*_ref`，也不在文本里声称「全文在 X」；只回流 `summary_truncated`
布尔标志。

**理由**：`#213` 修掉的一类 bug 正是「声称全文在 `result_ref`、而 `result_ref is None`」。bus 消息
**不落盘**（`bus.py` 文档头：「The bus is not persisted across runs」），没有权威件可指。任何 ref
字样都是假话。spec 措辞必须只说「单条 SHALL bounded + SHALL 有标志」，**不写**「全文经 ref 按需读取」。

**对 spec 的影响**：`agent-runtime` 的既有 Requirement 「父 run 通过显式运行时接口管理子 session」
里有一句「全文 SHALL 通过 envelope 里的显式引用按需读取」——那是针对 **run envelope** 的（有
`result_ref`/`summary_ref`）。bus 是新 Requirement，措辞须避开这句，只承诺 bounded + 标志。

### D7：常量放 `bus.py`，不在 `manager.py`

**决策**：`BUS_MESSAGE_LIMIT` / `BUS_SNAPSHOT_LIMIT` / `BUS_PUBLISH_MAX_TOKENS` 定义在
`agent/subagent/bus.py`。

**理由**：这三个常量描述的是 **bus 出口**，与 bus 的实现内聚；放 `manager.py` 会让 manager 承担与
它无关的 bus 知识。`manager.py` 只需保留 `TRANSCRIPT_ITEM_LIMIT`（bus 从它派生）。

**导入**：`bus.py` 顶部 `from agent.subagent.manager import TRANSCRIPT_ITEM_LIMIT` 会引入
`bus → manager` 的 import；已确认 `manager.py` 不 import `bus`（D1），无环。若未来成环，退路是在
`bus.py` 内 inline `BUS_MESSAGE_LIMIT = 4000` 并加一条 parity 测试锁两处相等（已在 tasks 记为
回退方案）。

### D8：`truncated` 放在 `BusMessage` 上，而非 `read()` 的返回壳

**决策**：`BusMessage` dataclass 增 `truncated: bool = False`；`to_dict()` 增
`"summary_truncated": self.truncated`。

**理由**：
- `read()` 返回 `list[BusMessage]`，`ReadBusTool` 与 `snapshot_payload()` 都经 `to_dict()` 出口——
  标志挂在消息上，两条路径自动同时拿到，不会「一条路径有标志、另一条没有」（`#213` 的教训）。
- 命名 `summary_truncated` 而非 `truncated`：bus 消息的可截断字段只有 `summary`，但沿用 `#213` 的
  `<字段>_truncated` 命名家族（`content_truncated` / `summary_truncated` / `arguments_truncated`），
  便于跨出口统一读取；`snapshot_payload()` 已有顶层 `truncated` 语义沿用者需注意区分——本 change
  在 `BusMessage` 上不用裸 `truncated` 作为**键名**，避免与未来「快照整体被截」混淆。

**备选与弃用**：
- *用裸 `truncated` 键* → 弃用：语义太宽（是「这条消息被截」还是「整个快照被截」？），且不在
  `#213` 的命名家族里。

### D9：截断后 `token_count` 同步为重算值（grill Q3，用户确认）

**决策**：`read()` 返回前，对**被截断过的**消息用 `estimate_tokens(截断后文本)` 重算 `token_count`。
未被截断的消息保持原值。`read()` **内部挑消息**时的预算累计仍用原始 `token_count`（更保守，不影响
正确性）。

**理由**：`token_count` 在 `bus.py` 里本就是「这条消息占多少预算」的记账口径（`bus.py:93-95`）。
一条 30,000 字消息 `token_count=7500`，截到 4000 字后若仍报 7500，调用方按它累计预算会把「实际
1000 token 的返回」记成 7500——记账与实际返回体脱钩；`snapshot_payload()` 里同一对字段
（`summary` 长度 vs `token_count`）也不再自洽。

**备选与弃用**：
- *保留原值，另加 `token_count_full` 字段* → 弃用（用户确认）：模型面多一个数字字段，与「模型面
  数字越少越好」相悖，且本 change 的目标是减少注入面而非增加。

### D10：截断**不得原地**修改队列中的对象（grill R1，最关键落地坑）

**决策**：`read()` 必须用 `dataclasses.replace(msg, summary=截断后, token_count=重算,
truncated=True)` 构造**新实例**返回，SHALL NOT 直接对 `msg.summary` 赋值。

**理由（实测确认）**：`read()` 目前把**同一个** `BusMessage` 实例放进 `collected`
（`bus.py:126`），实测 `bus.read()[0] is bus._messages[0]` 为 `True`。若原地截断，会同步改写
`bus._messages` 里的那条 → `compact_summary()`（`bus.py:137`）与 checkpoint 的 `bus_summary`
（`manager.py:1492`）一起被截短 → **D2（队列保留全文）与 D3（read 返回截断后）在实现上互相冲突**。
`dataclasses.replace` 使「返回截断件」与「队列保留全文」同时成立。

**测试**：回归须断言 `bus._messages[0].summary` 在 `read()` 后仍为全文、`compact_summary()` 不变
（变异：把 `replace` 改回直接赋值 → 该测试变红）。

## Pre-Implementation Review

独立零记忆 subagent（run `grill-224-r1`）已挑战本 design，完整记录见
`reviews/grill-design.md`（6 Confirmed Decisions / 6 Open Questions / 8 风险，均带 `文件:行号`）。

### 已确认（grill 独立复核成立）

- **D1/D7 导入无环**：AST 建 `manager.py` 的 import-time 闭包，`agent.subagent.bus` 不在闭包内
  （`manager.py:1268` 的 `from agent.loop import AgentLoop` 是函数内延迟导入）；动态验证三种加载顺序
  注入该 import 后全部成功。
- **D6 不设 ref 正确**：bus 确无落盘件（`bus.py:25-26`）；唯一持久化的是 `compact_summary()` 产物
  （已被 `max_chars` 界住、仅用于 checkpoint 写入）。
- **D8 命名正确**：`summary_truncated` 是 `patterns.py:366` 既有家族，非新造。
- **新增两键不破坏消费者**：全仓无键集合全等断言。
- **不影响门禁**：`scripts/` + `flow/` 对 `MessageBus`/`snapshot_payload`/`BUS_` **零命中**，无死锁。
- **D2 方向正确**：出口投影截断、队列保留全文，与 #213 范式一致。

### 必须修改（grill 发现的阻塞项）

1. **`DeclareWorkflow` 不是 bus 出口——原 D4 与 `specs/agent-runtime/spec.md` 前提与代码不符。**
   实跑 `DeclareWorkflowTool.execute()` 返回键**无 `bus`**（`subagents.py:538-562` 手工构造固定 dict）；
   `scheduler.py:2955-2956` 的 `_envelope()["bus"]` 只经 `run()` 返回值流出，而 `run()` 的返回在
   `subagents.py:620`、`:835` 两处都被丢弃，`patterns.py:378-406` 的 `_legacy_result` 也从不解引用
   `envelope["bus"]`，`parent_envelope()` 在 `scheduler.py:2973` 又把它 pop 掉。
   **→ 唯一模型面 bus 出口是 `patterns.py:458`（`RunPattern`）。** 待 Q2 确认后修正 spec 措辞。
2. **`ReadBus` 的**总量**仍无界——原 D2/D3/D8 只界住单条。**
   `max_tokens` / `limit` 均由调用方（模型）给；实测满载 100 条 × 30000 字时
   `ReadBus(max_tokens=10**9)` 返回 **100 条 / 3,000,000 字符**（单条截断后仍约 40 万）。这与
   `manager.py:82-88` 的「界不可被被检视对象影响」直接冲突。待 Q1 确认。

### 必须落实（grill 发现的落地坑，非阻塞但会真踩）

- **R1（最关键）：`read()` 返回的是队列里的同一对象**（实测 `bus.read()[0] is bus._messages[0]` 为
  `True`）。**实现必须用 `dataclasses.replace(msg, summary=..., truncated=True)` 构造新实例**，
  不得原地赋值——否则会污染 `compact_summary()`（`bus.py:137`）与 checkpoint 的 `bus_summary`
  （`manager.py:1492`），D2 与 D3 将互相冲突。
- **R2：`RunPattern` 的主要放大项不是 bus**（实测 `workers=300`：总 165,763 字符，`workers[]` 85,180 /
  顶层 `summary` 80,239 / `bus` 仅 41）。本 change 只修 bus 出口合理，但 spec 措辞不得读起来像
  「`RunPattern` 已 bounded」——须在 Non-Goals 显式写明 `workers[]` 与顶层 `summary` 的条数维仍无界。
- **R3：文档扫描清单漏了真正命中的文件**——`docs/interview-bullets/interview-prep.md:219,221`（发布侧
  400 token 上限、单条超预算保留最新一条）、`docs/interview-bullets/walkthrough.md:750-808`（贴
  `MessageBus` 代码与 `result["bus"] = bus.snapshot_payload()`）、
  `docs/interview-script/walkthrough/W03-multi-agent.md:40`、
  `docs/interview-script/questions/Q08-multi-agent.md:49`（写 `MessageBus` 53 行，实为 147 行）。
- **R5：`_summarize` 的 LLM 分支是 advisory，不是硬界**——`agent/context/summarizer.py:33-35` 明说
  budget「not a hard guarantee」。发布侧对 LLM 摘要路径**只有建议、没有保证**；单条的硬保证在消费侧
  `read()`。design D5 不得声称发布侧「两侧同界」，须如实写成「阈值对齐 + 消费侧兜底」。
- **R6：`PublishBusMessageTool` 的回包（`subagents.py:274` 的 `msg.to_dict()`）是第 5 条模型面出口**，
  出口盘点表（proposal.md:16-21）只列了 4 条。D5 钳住后它 ≤ 单条上限，无新增漏洞，但须补入清单。
- **R7：常量 parity 测试的形式须写明**——主方案（派生）下该测试锁的是「派生关系没被改成字面量」，
  回退方案（inline + parity）下锁的是「两处数值相等」，判别对象不同，tasks 须写明按哪条落。

### 待用户确认（阻塞，见 `## User Confirmation`）

Q1（ReadBus 总量是否一并钳死）、Q2（DeclareWorkflow 措辞修正方式）、Q3（截断后 `token_count` 是否同步）、
Q4（既有测试改造 + 发布侧闸门取 `>=` 两处小修正）。

## Impact Analysis

见 `proposal.md` 的 `## Impact Analysis` 节（同源，避免两处漂移）。补充设计侧要点：

- `snapshot_payload()` 的返回形状新增 2 键，是**对外可观测**变更；已 grep 确认无生产消费者读新键。
- `BusMessage` 加字段对既有构造点透明（有默认值 `truncated=False`）；既有测试若做 dataclass 全等
  断言需同步。

## 测试策略

- **判别性输入**：单条用 30,000 字（真超 4000），条数用 >20（真超快照上限）。
- **契约测试**（issue 建议的核心）：构造同一份 bus 内容（1 条 30k + 满载 100 条），断言
  `ReadBusTool.execute()` 与 `snapshot_payload()` 两条**模型面出口**的每条 `summary` ≤
  `TRANSCRIPT_ITEM_LIMIT`、条数 ≤ `BUS_SNAPSHOT_LIMIT`。
- **变异验证**：`read()` 截断改 identity、`snapshot_payload()` 去条数上限、`max_tokens` 不钳 →
  三个测试各自变红。
- **回归**：`test_bus.py` 既有 10 条 + `test_patterns.py` + `test_scheduler.py` +
  `test_workflow_graph_snapshot*.py`。
