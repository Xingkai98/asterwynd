## Context

本项目当前是「单 agent + 单会话」为主的形态：Web 层 `AgentSession` 持一个 `AgentLoop`（`web/session.py:1335-1346`），多会话靠 `SessionManager` 并发；现成的多 agent 设施是 `SubAgentManager`（子 session + 多次 run，进程内存）与 workflow DSL（DAG 批处理，`agent/subagent/scheduler.py`）。

本 change 新增一种**长期存在、面向用户、可交互轮次**的多 agent 形态，参照 DS Bot（Fei2411/DeepSeek-Bot）。它与既有 subagent（一次性委托）和 workflow（批处理图）都不同，因此是新增能力域而非接入。

**两个必须正视的现状**（grill + 对抗验证逐条核实）：

1. **Web 路径今天没有长期记忆**：`_create_session` 构造工具注册表与 `AgentLoop` 时未传 `persistent_memory` / `memory_config` / `llm`（`web/session.py:1648-1688`），`MemoryIndexSource` 拿到 `None` 返回空串，记忆工具退化到工厂默认的**项目级**实例（`agent/tools/factory.py:319-327`），且**无 LLM 去重判官**（`agent/tools/factory.py:163-173`，`llm is None` ⇒ 返回 `None`）。CLI 路径已完整接线（`agent/main.py:255-289,325`）。⇒ 「人设级记忆」实为「**先补 Web 接线（多参数忠实移植），再加维度**」。
2. **分层是单向 `web/ → agent/`**：`agent/` 只在 CLI 入口函数内延迟 import web（`agent/main.py:684`，全仓唯一反向点）。⇒ 群聊编排器**不能**放在 `agent/` 里反向驱动 `web.AgentSession`。

用户诉求（issue #302）：单聊 + 群聊；群聊由 Chief 推进、可 `@` 成员；单聊与群聊内容不耦合；人设长期记忆共享。

## Goals / Non-Goals

**Goals:**

- 长期 agent 人设的建模、持久化与 Web 管理（CRUD + 单聊入口 + 删除级联）。
- 单聊/群聊会话分离（结构性保证）。
- 会话式群聊编排：轮次、slot 序列、`@` 点名、静默、Chief 默认应答、明确的**轮次终止**（含失败/超时出口）与**房间级互斥**。
- 房间日志：群时间线的**权威**有序数据（含 schema 与有界切片注入）。
- 人设级长期记忆（含补全 Web 记忆接线）。
- Web 群聊 pane（新增 pane 类型 + 房间级 WS）。

**Non-Goals:**

- 不改 AgentLoop 主循环、工具协议、workflow DSL / DAG 调度器语义。
- 不复刻 DS Bot 的外围功能（浏览器面板、secrets、用量页、语音、定时任务、头像角色系统）。
- 不做多租户 / 鉴权；沿用现有单机本地 Web 的信任模型。
- 不把 workflow 资产库按人设分桶（显式声明为**共享面**，Decision 12）。
- 首版不做「引用另一段对话作为上下文」（Q5b 已拍板不做；不新开跨会话只读工具面）。

## Decisions

### Decision 1: 一个人设的每个会话面 = 一个 AgentSession

人设**不是**单个 `AgentSession`：一个人设有 1 个单聊会话 + 作为成员的每个群各 1 个群内会话。三者都是普通 `AgentSession`（各自 `AgentLoop` + messages + `event_channel`），`kind` 区分 `chat` / `persona_chat` / `room_member`。

**不**扩展 `SubAgentManager`。理由（三条代码级否证）：其 child session 被**父 `AgentLoop` 拥有**（`agent/loop.py:167`）、system prompt 硬编码为「受限子 agent」（`agent/subagent/manager.py:580,817`）、无会话快照（`_sessions` 是进程内存字典，`agent/subagent/manager.py:470`）。
承载可行性（已确认）：人设指令走现成注入面 `AgentSession.init_messages(<指令>)` → `agent._user_system_prompt` → `SessionSnapshot.user_system_prompt` 落盘 + resume 回灌（`web/session.py:1378-1380`、`agent/session.py:27`、`agent/loop.py:138,713-714`）。
**成本模型按会话数计**：人设数 N、平均群数 G ⇒ N×(1+G) 份 `AgentLoop`。⇒ 必须**懒构造 + 有上限**。**上限取值（Q4 已拍板）**：默认会话数上限 **50**，超出**排队**（不拒绝创建），上限做成可配置项。

### Decision 2: 单聊与群聊会话分离是结构性保证

每个 (persona, room) 持有独立会话；单聊另有会话。`run_lock` 与 `event_channel` 都是 per-`AgentSession`（`web/session.py:1359,1367`），不存在跨 pane 事件串流。真正的跨会话泄漏面在**共享存储**（记忆、workflow 资产库）。

### Decision 3: 群聊编排器与 DAG 调度器并列、新建；并声明其不属既有控制面

新建**轮次式**编排器。理由：调度器节点种类封闭四值（`agent/subagent/scheduler.py:1722-1732`），无交互/轮次节点。

**与既有 `multi-agent-collaboration` 的「Orchestration Reuses Workflow Persistence Discipline / SHALL NOT introduce a separate control plane」的关系**（`openspec/specs/multi-agent-collaboration/spec.md:80-89`）：该 Requirement 主语是 **Subagent orchestration**，本编排器**不复用 `SubAgentManager`、不属 subagent orchestration 范畴**，故不与之冲突。此澄清 SHALL 以 MODIFIED delta 写进规格（见 spec delta），避免读者读成矛盾。

### Decision 4: 编排器分层——依赖 `SessionRunner` 抽象，由 web 层注入

编排器依赖抽象 `SessionRunner`，web 层实现并注入（web 层持有 `AgentSession` / `SessionManager`）；编排器模块不 import `web`（本仓分层单向 `web/ → agent/`，`agent/main.py:684` 是唯一反向点）。

**`SessionRunner.run(session_id, message) -> TurnOutcome` 的契约（四态，返回值而非异常）**：

- `{status: "text", text}` —— 正常发言。
- `{status: "silent"}` —— 命中静默（Decision 10）。
- `{status: "failed", code, message}` —— 模型调用/工具失败，或被 `_git_commit` 之类 `RuntimeError` 中止。
- `{status: "timeout"}` —— 单轮超时。

**关键约束**：`text` SHALL 只来自**本次 run** 的产出，SHALL NOT 退化为「读 session 最后一条 assistant」。理由：同 session 并发 run 被 `run_lock` 拒时 `run_session` 只发 `run_in_progress` 事件并 `return None`（`web/session.py:1736-1757,1770-1782`），若取「最后一条 assistant」会把**陈旧内容**当本轮发言写进房间日志。⇒ web 层实现 SHALL 从本次 run 的事件流捕获最终文本，并把「被拒/无产出」映射为 `failed`/`timeout` 而非复用旧文本。

**单轮超时**：参照实现为 240s（`ds-bot/src/host/constants.js:25` `ROOM_REPLY_TIMEOUT_MS`），本 change 沿用可配置超时，超时按 `timeout` 出口处理。

### Decision 5: 房间级互斥

同一房间**同一时刻至多一轮**。用户并发发消息 / 多 tab 同房间时，后到的消息 SHALL 排队进入**本轮**（不并行开第二轮），不得因第二个 run 去撞成员 session 的 `run_lock`。

理由：成员 session 每群一份，两轮并存必有一个成员 run 被拒（`web/session.py:1770-1782`），且会污染本轮顺序。

### Decision 6: 房间日志是群时间线的权威数据（含 schema 与有界切片）

**schema**（SHALL 写进 spec delta）：有序条目数组，每条 `{seq, speaker, kind, text, ts}`；`kind ∈ {"user","post","system"}`——`user` 为用户消息（`speaker = "user"`）、`post` 为成员发言（`speaker = persona_id`）、`system` 为系统条目（如「因达上限结束」「成员运行失败」，`speaker = null`）。取值用 `system` 而非 `notice`，以避开与 Q5a「群共享 notice」的同名歧义。首版**不**引入 `lookup` 类条目。

- **权威关系**：房间日志是群时间线的唯一权威；重连后由它还原有序群消息流（`Message` 无 timestamp/speaker，`agent/message.py:144-155`；`build_history_payload` 只发 role）。
- **写入**：编排器每成员发言后 append；用户消息也 append。
- **切片注入（有界 + 游标语义）**：每个成员持**持久化游标** `seen[member]`，在**回合开始**推进（含静默/超时回合也推进）——与参照实现一致（`ds-bot/src/host/groups.js:44-45,183`）。成员本轮看到的 = `seq > seen[member]` 且非本人发言的切片，并施加与参照同形的**三层上限**：首见 `12` / 单次增量 `24` / 往轮上下文 `8`（`ds-bot/src/host/groups.js:21-23`），且把「本轮」与「往轮（仅上下文）」分开标注。
  理由：若按「上次**发言**之后」推进，连续静默的成员切片边界永不前进 ⇒ 同段内容被反复重复注入，上下文随静默次数无界增长（与 issue #278「上下文无界」同类风险）。

### Decision 7: 人设级记忆——先补全 Web 接线，再加 persona 维

**接线清单（SHALL 全部补齐，忠实移植 CLI 语义）**：人设会话构造时传 `persistent_memory` + `memory_config` + `llm`（+ 视需要 `quality_config`），对照 CLI 的 `agent/main.py:270-289`。只传 `persistent_memory` 会缺 LLM 去重判官（`agent/tools/factory.py:163-173`）与用户记忆配置（`agent/tools/factory.py:317-327`），落成与 CLI **不同策略**的人设记忆。

**接线范围**：仅人设会话（`persona_chat` / `room_member`）；**不**顺带给普通 Web 会话接线（会改变既有单会话 Web 行为与其测试面，属另一 change）。

**persona 维落点（同级布局，不嵌在项目记忆目录内）**：`~/.asterwynd/projects/<project-hash>/personas/<persona-id>/memory`。
理由：项目记忆目录自带 git commit-before-write（`agent/memory/persistent.py:452` 的 `git add -A` 会**递归**），把人设目录嵌在 `.../memory/` 内会形成嵌套仓库（gitlink + 警告），并使项目级可逆快照语义含糊。同级布局 + 注入块标题改为 `## Persona Memory`（现为硬编码 `## Project Memory`，`agent/context/sources.py:302`），语义可区分。
（无泄漏副作用：`load_entries` 用非递归 `glob("*.md")`（`agent/memory/persistent.py:341`），同级目录不会被项目级检索误收。）

**同一人设共享同一实例**：单聊与群聊会话 SHALL 共享同一个 `PersistentMemory` 实例（避免并发写同一目录与 `_last_decay_run` 重复衰减；见 Risks）。

### Decision 8: 会话标识与 hub 可见性（含破坏性路径全保护）

- 稳定映射：`persona → 单聊会话 id`、`(persona, room) → 群内会话 id`，分别存 roster 与房间记录。
- **id 前缀约定（钉死取值）**：人设单聊会话 id 前缀 `persona-`、群内会话 id 前缀 `room-`（`_validate_session_id` 只挡空/绝对/逃逸，`agent/session.py:236-243`）。使 hub 过滤与保护判定退化为**纯字符串 + roster 映射**，不依赖读快照（避开损坏快照读不出 `kind` 的问题，`agent/session.py:169-182`）。
- 标记：`SessionSnapshot` 增 `kind`。
- **破坏性路径全保护**：不止 `DELETE /api/sessions/{id}`（`web/server.py:334`），还包括 **WS `reset`**（`web/server.py:724-760` → `remove_session` → `shutil.rmtree` → 换随机新 id，`agent/session.py:208-221`、`web/session.py:1627`）。内部会话 SHALL 拒绝 `reset`（或 reset 后复用原 id 并回写 roster），否则 Decision 8 的稳定映射被击穿。
- hub：`GET /api/sessions`（`web/server.py:320`）SHALL NOT 列出内部会话；同一 store 口径的其它出口 SHALL 一致过滤——`GET /api/workspaces` 的 `session_count`（`web/server.py:280`）与 CLI `session list`（`agent/main.py:1389-1395`）SHALL NOT 计入内部会话。

### Decision 9: 群内会话（`kind: room_member`）内的 pending 交互显式降级（须 MODIFIED 既有规格）

**范围严格限定为群内会话**（`kind: room_member`）：它**不暴露** ask 类工具（从工具面撤除）；审批类调用按 **fail-closed 立即判定为 unavailable**（复用 `openspec/specs/agent-runtime/spec.md:356-362` 既有「审批不可用时 fail closed」Scenario），不阻塞整轮。理由：群聊轮次可能无人值守，走既有 `WebApprovalHandler`（600s）/`WebQuestionHandler`（300s，`web/session.py:1630-1637`、`agent/config.py:398-399`）会阻塞到超时。

**人设单聊会话（`kind: persona_chat`）不降级**：它是用户在场的会话，照常暴露交互式 pending。理由：降级理由是「无人值守」，对用户就在页面上的单聊不成立；撤掉提问工具、审批一律 fail-closed 是对用户的可见能力损失，无正当理由。

**这收窄了既有 `web-ui` 两条无条件 Requirement**：「Web UI SHALL support tool approval requests」（`openspec/specs/web-ui/spec.md:360-394`）与「pending 提问与审批跨 WebSocket 连接存活」（`:1120+`）⇒ spec delta SHALL 用 **MODIFIED** 给两条加「群内会话除外」scope 限定 + 降级 Scenario。
已知限制：**群聊成员**不能执行需审批的高风险操作（单聊不受此限）。

### Decision 10: 静默 = 哨兵文本 + 解析最终 content

成员被提示「无新增内容时回复 `[PASS]`」；编排器解析 `TurnOutcome.text` 判静默（与参照 `ds-bot/src/host/groups.js:99` 同形）。不新增控制工具（会污染所有既有 agent 工具面）。

### Decision 11: 每轮预算、slot 序列、`@` 解析与轮次终止

- **slot 序列算法（钉死）**：一轮的初始 slot = `openingSpeakers(用户消息)`——用户消息行首 `@Name`（多个则按出现顺序、去重）→ 否则房间 admin（无 admin 则 roster 第一个 `mainBot`）→ 否则按成员顺序。成员发言中 `@Name` **追加**到当前位次之后、去重、且每人每轮发言数 ≤ 上限。**同一人被 @ 两次只追加一次**。
- **`@` 解析口径**：用户消息**行首**的 `@` 触发点名（`web-ui` delta）；成员发言**句中**的 `@` 也触发接力（`multi-agent-collaboration` delta）——此差异 SHALL 在两处 spec 写明。点名不在列表的人 / 自己 / 多人：只取「属于本群成员且非自己」者，不报错。
- **每轮上限** = `初始 slot 数 + 固定额外轮次`（群有 admin 时再加固定额度），并按成员分别计数封顶（参照 `ds-bot/src/host/groups.js:24-27,262`）。
- **轮次终止（三出口）**：① 所有 slot 走完；② 达上限（房间日志记 `system`「因达上限结束」）；③ 全部剩余成员 run 失败或超时（各记 `system` 后结束）。单个成员失败/超时只记 `system` 并继续（不挂死整轮）。**首版不提供轮次取消出口。** 用户再次发言才开新一轮。
- **轮次进行中到达的用户消息**：只追加进房间日志；其行首 `@` 追加为**当前位次之后**的 slot（去重、受每人每轮上限约束）；SHALL NOT 改变本轮上限基数（上限按**开局** slot 数计算）。
- **与参照的故意分歧（声明）**：本 change **不**允许成员自行开轮次（参照允许、上限 3，`ds-bot/src/host/constants.js:53-54` `ROOM_BOT_ROUNDS`）。理由：无人值守的 Web 面板下，成员互开轮次会放大成本且无用户在场收敛；收紧为仅用户开轮。

### Decision 12: 跨人设共享面声明

workflow 资产库是**仓库级共享**（`agent/subagent/workflow_assets.py:31-38`），资产索引默认注入每个 root loop（`agent/loop.py:155`）。首版**不**按人设分桶，但 SHALL 在 spec delta 显式声明其为共享面，避免「人设隔离」验收只测记忆而漏掉这条隐式通道。

### Decision 13: Chief/admin 归属（roster 与房间两级，均可多个）

**两级并存，各司其职**（与参照同形：`ds-bot/src/host/prompt.js:25-36` 的 roster 级 Main Bot vs `ds-bot/src/host/groups.js:261-262` 的 `room.admin`）：

- **Chief = roster 级 `mainBotIds`（复数，可多个）**：管理所有 bot 与房间、可创建/删除；体现在 roster 字段。
- **房间 admin = 房间属性（单个，可为空）**：`room.admin` 取值是某个成员人设 id；决定该房间「用户消息默认由谁应答」与每轮额外额度；创建房间时默认把创建者的 Chief 身份者设为 admin，也 SHALL 可显式指定/更换。
- spec 的「用户消息 SHALL 默认由群管理员（Chief）应答」SHALL 以「房间 admin；无 admin 时回落 roster 第一个 mainBot」为可测口径。

### Decision 14: 持久化位置与多 workspace 语义

roster 与房间日志/房间记录 SHALL 落在 **workspace 级**目录（与会话同域，`<workspace>/.asterwynd/` 下），SHALL NOT 落在仓库哈希目录。
理由：会话按 workspace 存（`web/session.py:1422-1433`），记忆/资产按仓库哈希存（`agent/memory/persistent.py:180-185`）；若 roster 落在仓库级，用户切到另一 allowlist workspace 时 roster 里的会话 id 全部悬空。hub 过滤 SHALL 按 workspace 正确实现。

### Decision 15: roster / 房间的 Web 管理、单聊入口与删除级联

- Web UI SHALL 提供 roster 与房间的 CRUD 管理入口（创建/改名/改指令/改模型/加删成员/删除），以及**进入某人设单聊**的入口。
- **删除级联（SHALL 定义）**：
  - 删除人设 ⇒ 删除其单聊会话底座 + 该人设的 persona 记忆目录 + 从所有房间移除该成员（并删除其群内会话底座）。
  - 删除房间 ⇒ 删除房间记录 + 房间日志 + 所有 (persona, room) 群内会话底座。
  - **顺序与幂等（钉死）**：级联 SHALL **先删会话底座与 persona 记忆，最后删 roster/房间条目**；且 SHALL 幂等——中断后重试从当前状态继续。理由：若先删 roster 条目再删底座，中途失败会留下「hub 不列（id 前缀过滤）、接口又拒删」的**孤儿内部会话**；先删底座则中断时 roster 仍在，可重试且可被发现。
  - 删除 SHALL 经人设/房间接口进行（不得走 `DELETE /api/sessions` 或 WS `reset`）。
  理由：否则「不可直接删除」的反面（正当删除）无规格可依，且删除人设后 persona 记忆长期残留（未声明的隐私面）。

### Decision 16: 群共享 notice（群公告，首版做）

房间 SHALL 支持一条**群级共享指令**（`notice`），在该房间每个成员发言前注入其群内会话的 prompt，使约束只需写一次。
- 注入位置：群内会话本轮 user 消息的群上下文前缀（与房间日志切片并列），不写入单聊。
- 与参照同形（`ds-bot/src/host/groups.js:161` 的 `room.notice`「Group notice (shared instructions for every member)」）。
- 与房间日志 `kind: "system"` 命名区分（那里是系统条目，此处是用户配置的群指令）。
（Q5a 已拍板首版做。）

## Pre-Implementation Review

- Questions resolved:
  - Q1 编排器形态：**新建独立模块**（否证 `SubAgentManager`）。
  - Q2 记忆作用域：**同一 `PersistentMemory` 加 persona 维**；先补全 Web 接线（多参数）。
  - Q3 Chief 角色：roster 级 `mainBotIds`（可多个）+ 房间级 `admin`（单个，可空），**非**内置不可删角色。
  - 静默机制、每轮预算、slot 序列、轮次终止、房间级互斥、控制面澄清—均经代码核实。
- Options considered / Rejected:
  - 承载：`AgentSession`（本设计）vs 扩展 `SubAgentManager`（否：父 loop 拥有 / 硬编码受限 prompt / 无会话快照）vs 新起运行时。
  - 编排器位置：`agent/` 新模块 + 注入抽象（本设计）vs 放 web 层（否：与「会话面」耦合过深）。
  - 记忆落点：同级 `personas/<id>/memory`（本设计）vs 嵌在项目 `memory/` 内（否：嵌套 git 仓库）。
- Final confirmations:
  - 已完成独立零记忆 grill（`reviews/grill-design.md`）+ 设计阶段对抗验证（`reviews/grill-adversarial.md`）；实现前停轮拍板 Open Questions。
- Remaining risks: 见 Risks。

## Risks / Trade-offs

- [Risk] 群聊 token 成本随发言者数放大。Mitigation: Chief/admin 模式 + 静默 + 每轮每成员上限（Decision 11）。
- [Risk] 会话数 = N×(1+G)，每会话一份 AgentLoop（MCP 子进程 + 独立并发额度 + 工具注册表）。Mitigation: 懒构造 + 上限（Q4）。
- [Risk] **同一人设单聊/群聊并发写同一份记忆**：`_git_commit` 在提交失败时抛 `RuntimeError` 中止写入（不是降级，`agent/memory/persistent.py:433-465`）。Mitigation: 同一人设共享同一 `PersistentMemory` 实例（Decision 7）+ 并发写测试。
- [Risk] **跨人设隐式通道不止记忆**：workflow 资产库仓库级共享（Decision 12）。
- [Risk] 群聊 pending 降级 ⇒ 成员不能做需审批的高风险操作（Decision 9，已记已知限制）。
- [Risk] **WS `reset` 可击穿内部会话保护**（Decision 8）——须在实现与测试中显式覆盖。
- [Risk] 记忆作用域改造触碰既有 `long-term-memory` 规格与测试。Mitigation: MODIFIED delta + 回归。
- [Risk] 新增群聊 pane / 房间 WS 回归既有 Chat。Mitigation: 复用 per-tab 机制与 `tool_rows.js`；Web smoke。

## Testing Strategy

- roster/房间 CRUD + 持久化（跨重启、跨 workspace；人设指令恢复）；删除级联（会话/房间日志/persona 记忆）。
- 群聊编排：slot 序列、`@` 解析（行首 vs 句中 / 不在列表 / 多人 / 自己）、静默、每轮每成员上限、**轮次终止三出口**（走完 / 达上限 / 失败或超时）、轮次中用户消息处理、**房间级互斥**（并发不发两轮、用户消息排队进本轮）。
- `SessionRunner` 契约：`text` 只来自本次 run（**并发被拒时不复用陈旧文本**）；四态映射。
- 会话分离：单聊/群聊内容互不泄漏的负向断言。
- 记忆：人设间隔离 + 同人设单聊/群聊共享 + 并发写；接线完整性（LLM 去重判官存在、memory_config 生效）；注入块标题为 `## Persona Memory`。
- 共享面：workflow 资产库跨人设可见性（按声明断言）。
- Web：群聊 pane + 房间 WS + hub 过滤（含**损坏快照**）+ `DELETE` 拒删 + **WS `reset` 拒改内部会话**。
- 收尾：全量 pytest + `openspec validate --strict` + artifact checker + benchmark smoke。

## Open Questions

（无。Q4 / Q5a / Q5b 已由用户于 2026-10-12 拍板，答复记录见 `reviews/grill-design.md` 的 `## User Confirmation`。）

## Confirmed Answers（用户拍板，2026-10-12）

- **Q4**: 首版会话数上限 = **50**，超出**排队**；做成可配置项。
- **Q5a**: 首版**做**群共享 notice（Decision 16）。
- **Q5b**: 首版**不做**「引用另一段对话作为上下文」（Non-Goals）。
