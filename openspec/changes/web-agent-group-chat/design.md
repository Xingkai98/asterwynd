## Context

本项目当前是「单 agent + 单会话」为主的形态：Web 层 `AgentSession` 持一个 `AgentLoop`（`web/session.py:1335-1346`），多会话靠 `SessionManager` 并发；现成的多 agent 设施是 `SubAgentManager`（子 session + 多次 run，进程内存）与 workflow DSL（DAG 批处理，`agent/subagent/scheduler.py`）。

本 change 新增一种**长期存在、面向用户、可交互轮次**的多 agent 形态，参照 DS Bot（Fei2411/DeepSeek-Bot）。它与既有 subagent（一次性委托）和 workflow（批处理图）都不同，因此是新增能力域而非接入。

**两个必须正视的现状**（grill + 对抗验证逐条核实）：

1. **Web 路径今天没有长期记忆**：`_create_session` 构造工具注册表与 `AgentLoop` 时未传 `persistent_memory` / `memory_config` / `llm`（`web/session.py:1648-1688`），`MemoryIndexSource` 拿到 `None` 返回空串，记忆工具退化到工厂默认的**项目级**实例（`agent/tools/factory.py:319-327`），且**无 LLM 去重判官**（`agent/tools/factory.py:163-173`，`llm is None` ⇒ 返回 `None`）。CLI 路径已完整接线（`agent/main.py:255-289,325`）。⇒ 「人设级记忆」实为「**先补 Web 接线（多参数忠实移植），再加维度**」。
2. **分层是单向 `web/ → agent/`**：`agent/` 只在 CLI 入口函数内延迟 import web（`agent/main.py:684`，全仓唯一反向点）。⇒ 群聊编排器**不能**放在 `agent/` 里反向驱动 `web.AgentSession`。

用户诉求（issue #302）：单聊 + 群聊；群聊由 Chief 推进、可 `@` 成员；单聊与群聊内容不耦合；**记忆按「人设 × 会话面」独立**（每个群独立）。

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

每个 (persona, room) 持有独立会话；单聊另有会话。`run_lock` 与 `event_channel` 都是 per-`AgentSession`（`web/session.py:1359,1367`），不存在跨 pane 事件串流。记忆已按「人设 × 会话面」隔离（Decision 7），不再是跨会话泄漏面；**剩余**的跨人设共享面是 workflow 资产库（Decision 12）。

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

### Decision 7: 人设记忆——先补全 Web 接线，再按「人设 × 会话面」分 scope

**接线清单（SHALL 全部补齐，忠实移植 CLI 语义）**：人设会话构造时传 `persistent_memory` + `memory_config` + `llm`（+ 视需要 `quality_config`），对照 CLI 的 `agent/main.py:270-289`。只传 `persistent_memory` 会缺 LLM 去重判官（`agent/tools/factory.py:163-173`）与用户记忆配置（`agent/tools/factory.py:317-327`），落成与 CLI **不同策略**的人设记忆。

**接线范围**：仅人设会话（`persona_chat` / `room_member`）；**不**顺带给普通 Web 会话接线（会改变既有单会话 Web 行为与其测试面，属另一 change）。

**scope 粒度 = 人设 × 会话面**（用户 2026-10-12 拍板「每个群独立」）：
- 单聊一份：`~/.asterwynd/projects/<project-hash>/personas/<persona-id>/chat/memory`；
- 每个群各一份：`.../personas/<persona-id>/rooms/<room-id>/memory`；
- 单聊与各群之间、群与群之间**互不可见**。

**与参照的故意分歧（声明）**：DS Bot 的记忆是**每个 bot 一份**（跨它所有会话共享）+ 一份 team 共享（`ds-bot/src/host/memory.js`）；本 change 按用户拍板改为**每个群独立**，属故意分歧。

**同级布局**（不嵌在项目记忆目录内）：项目记忆目录自带 git commit-before-write，其 `git add -A` 会**递归**（`agent/memory/persistent.py:451-452`），把人设目录嵌在 `.../memory/` 内会形成嵌套仓库（gitlink + 警告）；同级目录不会被项目级非递归 `glob("*.md")` 误收（`:341`）。注入块标题改为 `## Persona Memory`（现硬编码 `## Project Memory`，`agent/context/sources.py:302`）。

**实例化形态（钉死，Issue 36）**：`PersistentMemory` 现无 scope 目录注入口——`memory_dir` 恒为 `_MEMORY_DIR_BASE / _compute_project_hash(scope_root 或 project_root) / "memory"`（`agent/memory/persistent.py:180-183`，全仓唯一赋值点），**传一个 scope 目录进去只会被再 hash 成另一个顶层目录**（实测：以 `.../personas/p1/chat` 构造得到 `<BASE>/<另一个 hash>/memory`，落在 `personas/<id>/` 子树之外 ⇒ 级联永远删不到）。本 change SHALL：
- 为 `PersistentMemory` 新增**显式 scope 目录入参**（如 `memory_dir: Path | None`）：给定即**原样**用作 `memory_dir`（跳过 project-hash 推导）；未给时保持现状（项目 scope，零回归）。
- 人设 scope 的 `scope` 取值 SHALL 形如 `<project-scope>:persona:<pid>`（单聊）/ `<project-scope>:persona:<pid>:room:<rid>`（群），写入记忆 frontmatter，与既有 `scope` 语义对齐。

### Decision 8: 会话标识与 hub 可见性（含破坏性路径全保护）

- 稳定映射：`persona → 单聊会话 id`、`(persona, room) → 群内会话 id`，分别存 roster 与房间记录。
- **id 前缀约定（钉死取值）**：人设单聊会话 id 前缀 `persona-`、群内会话 id 前缀 `room-`（`_validate_session_id` 只挡空/绝对/逃逸，`agent/session.py:236-243`）。使 hub 过滤与保护判定退化为**纯字符串 + roster 映射**，不依赖读快照（避开损坏快照读不出 `kind` 的问题，`agent/session.py:169-182`）。
- 标记：`SessionSnapshot` 增 `kind`。
- **破坏性路径全保护**：不止 `DELETE /api/sessions/{id}`（`web/server.py:334`），还包括 **WS `reset`**（`web/server.py:724-760` → `remove_session` → `shutil.rmtree` → 换随机新 id，`agent/session.py:208-221`、`web/session.py:1627`）。内部会话 SHALL 拒绝 `reset`（或 reset 后复用原 id 并回写 roster），否则 Decision 8 的稳定映射被击穿。
- hub：`GET /api/sessions`（`web/server.py:320`）SHALL NOT 列出内部会话；同一 store 口径的其它出口 SHALL 一致过滤——`GET /api/workspaces` 的 `session_count`（`web/server.py:280`）与 CLI `session list`（`agent/main.py:1389-1395`）SHALL NOT 计入内部会话。
- **本条收窄既有 `web-ui` 的两条无条件 Requirement**（hub 列表 / 会话删除）⇒ spec delta 以 **MODIFIED** 落地（见 `specs/web-ui/spec.md`）。

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
  - 删除人设 ⇒ 删除其单聊会话底座 + **该人设的全部记忆 scope**（`personas/<persona-id>/` 整棵子树，含 `chat/` 与 `rooms/<rid>/`）+ 从所有房间移除该成员（并删除其群内会话底座）。
  - 删除房间 ⇒ 删除房间记录 + 房间日志 + 所有 (persona, room) 群内会话底座 + **所有该房间的 (persona, room) 记忆目录**（`personas/<pid>/rooms/<rid>/`）。
  - **顺序与幂等（钉死）**：级联 SHALL **先删会话底座与该人设/房间的全部记忆 scope，最后删 roster/房间条目**；且 SHALL 幂等——中断后重试从当前状态继续。理由：若先删 roster 条目再删底座，中途失败会留下「hub 不列（id 前缀过滤）、接口又拒删」的**孤儿内部会话**；先删底座则中断时 roster 仍在，可重试且可被发现。
  - 删除 SHALL 经人设/房间接口进行（不得走 `DELETE /api/sessions` 或 WS `reset`）。
  理由：否则「不可直接删除」的反面（正当删除）无规格可依，且删除人设后 persona 记忆长期残留（未声明的隐私面）。

### Decision 16: 群共享 notice（群公告，首版做）

房间 SHALL 支持一条**群级共享指令**（`notice`），在该房间每个成员发言前注入其群内会话的 prompt，使约束只需写一次。
- 注入位置：群内会话本轮 user 消息的群上下文前缀（与房间日志切片并列），不写入单聊。
- 与参照同形（`ds-bot/src/host/groups.js:161` 的 `room.notice`「Group notice (shared instructions for every member)」）。
- 与房间日志 `kind: "system"` 命名区分（那里是系统条目，此处是用户配置的群指令）。
（Q5a 已拍板首版做。）

### Decision 17: 记忆 review（仅「实际发言」的回合触发 + 静默成员落后补齐）

- **主触发（钉死）**：一个人设会话（其单聊，或它在某群的群内会话）的一个回合结束、且该回合**实际产生了发言**（`TurnOutcome.status == "text"`）时，为该会话对应的**记忆 scope** 排一次 review（延迟后执行）。`silent` / `timeout` / `failed` 出口**不**触发——这类成员的记忆停滞由「落后补齐」兜底。
  （与参照的差异：参照对**任何** idle 都触发，`ds-bot/src/host/memory.js:1326-1339`；本 change 收紧为仅实际发言，以与「①+兜底」语义自洽并控制成本。）
- **落后补齐**：某房间某成员在该房间的 **review 游标**上落后达到阈值时，为它的 (persona, room) scope 排一次 review。**度量基准钉死为 review 游标 `reviewed`**（**非** Decision 6 的 `seen`——后者每回合推进、含静默，用它作基准则落后恒为 0、补齐永不触发）；**落后 = `room.seq − reviewed[(persona, room)]`**，单位 = 房间日志条目数，缺省阈值 **30**（参照 `REVIEW_GROUP_LAG`，`ds-bot/src/host/memory.js:71,1281-1284`）。`seen`（注入用）与 `reviewed`（review 用）是两份互不替代的游标。
- **机制**：review 是一次**独立小模型调用**（可配置模型；缺省用该人设会话模型亦可），读「该 scope 自上次 review 进度之后的新增内容」（群 = 房间日志切片；单聊 = 该 scope 的**待 review 缓冲**），产出 add/update/remove 变更。
- **写回（钉死映射）**：
  - add/update/supplement/conflict → 走既有 `save` / `apply_judgment` 路径（沿用去重判官、尺寸上限、git 可逆写保护，`agent/memory/persistent.py:502,548`）。
  - **remove → `archive(name, reason)`**（软删、可 `restore`，`:776,797`）。`archive` 目前**不含** git 前像提交（`:776-796`），本 change SHALL 连带补上（使 remove 也可回退）；注意 `archive` 是 `_write_entry_to` + `unlink` 的 move，加 commit 的位置与 `save` 的 commit-before-write 语义不同，SHALL 在 move 前快照。
  - 不得引入新的记忆删除原语（工具面无 forget/delete，全仓零命中）。
- **成本口径**：review 本身 1 次 LLM 调用；写回若命中**去重判官**（embedding 召回命中）则 **+1 次** LLM 调用（判官用会话注入的 `llm`，即人设自己的模型，`agent/tools/builtin/memory.py:79-93`、`agent/memory/dedup.py:84-90`）⇒ 单回合成本 = **1 + k** 次；需**额外接线**计入 `CostLedger`（其在 loop 内记账，`agent/loop.py:1216-1218`）。
- **游标 / review 输入（钉死，Issue 35）**：每个 scope 一个进度记录（落在该 scope 记忆目录内，如 `<scope>/reviewed.json`）。
  - **群 scope** 以**房间日志 seq** 为单位（稳定）。
  - **单聊 scope SHALL NOT 用消息表下标**——`Message` 无 id/timestamp/seq（`agent/message.py:144-155`），而本仓上下文压缩会**就地缩短**消息表（`agent/memory/manager.py:307-313` 等分支 `msgs[:] = system + [summary] + recent`）、session resume 会**重建**消息表（`agent/loop.py:717-720`），下标语义必漂移（压缩后游标越过表尾、列表再长不回去 ⇒ review **永久停摆**）。故**单聊 scope 的 review 输入 = 该 scope 的持久化「待 review 缓冲」**（运行期在向该 scope 追加消息时写入、review 消费后清空），**与消息表下标解耦**；压缩 / resume 不影响该缓冲。
- **待 review 缓冲（单聊）**：落点 = 该 scope 记忆目录内（如 `<scope>/pending_review.jsonl`）；运行期向该 scope 追加消息时写入；review **消费后删除已消费部分**（部分消费：本次读入上限内消费、其余留待下次）。
- **初值**：scope 建立时进度初值 = 该 scope 的当前起点（**不**回溯建库前的历史），以控成本。
- **读入上限**：review 单次读入的「新增内容」SHALL 有上限（可配置，缺省与注入侧同量级）；超出部分留待下一次 review。
- **scope 取值与记忆工具一致性**：记忆工具（`RecallMemory` / `SearchMemory`）的 `scope` 参数匹配 SHALL 使用本 change 的 scope 取值（`<project-scope>:persona:<pid>[:room:<rid>]`），否则新 scope 下人设会话的记忆检索会**静默返空**；同时 `PersistentMemory` SHALL 新增 `scope: str | None` 入参以注入该取值。
- **房间日志保留**：房间日志 SHALL 保留全部条目（是「群时间线唯一权威、重连还原」的前提）；即「落后补齐」的理由是**避免静默成员记忆长期停滞**，**不**依赖日志滚动。
- **可关闭**：默认开启，可配置关闭（`MemoryConfig` 现无此字段，`agent/config.py:248-256`，需新增配置位）。

（用户 2026-10-12 拍板选「①+兜底」。）

## Pre-Implementation Review

- Questions resolved:
  - Q1 编排器形态：**新建独立模块**（否证 `SubAgentManager`）。
  - Q2 记忆作用域：**按「人设 × 会话面」分 scope**（同一 `PersistentMemory` 类，按 scope 目录实例化；单聊/各群互不可见）；先补全 Web 接线（多参数）。
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
- [Risk] **同一记忆 scope 的并发写**：scope 已按「人设 × 会话面」拆分，单聊与各群不再共享目录 ⇒ 跨面争用消除；同一 scope 内的并发（turn review 与落后补齐同时排）由 **review 队列按 session 合并/串行化**（参照 `queueReview` 的合并语义）。底层 `_git_commit` 提交失败仍抛 `RuntimeError` 中止写入（`agent/memory/persistent.py:433-465`），故 review 失败 SHALL 只记日志、不中断轮次。
- [Risk] **memory review 的成本**：每「成员发言回合」一次额外小模型调用（+ 落后补齐）；一轮 N 个成员发言 = N 次额外调用。Mitigation: 用独立小模型 + 可配置关闭（Decision 17）。
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
- 记忆 scope：**人设间隔离 + 同一人设的单聊/各群之间也互相不可见**（每个群独立）；接线完整性（LLM 去重判官存在、`memory_config` 生效）；注入块标题为 `## Persona Memory`。
- 记忆 review：**仅实际发言的回合**触发（`text` 出口；`silent`/`timeout`/`failed` 不触发）；单聊 scope 与群 scope 各自触发；静默成员落后达阈值（以 **review 游标**为基准，阈值 30）被补齐；`remove` 映射到 `archive`（含 git 前像）；review 经既有 save 路径写入并推进游标；review **失败不中断轮次**；同一 scope 的并发 review 由队列合并/串行化；成本按 **1 + k** 口径记账。
- **游标稳定性**：上下文压缩 / session resume 之后，单聊 scope 的 review SHALL 仍能推进且**不重读已换出上下文、不漏读未 review 的消息**（单聊输入走持久化待 review 缓冲，与消息表下标解耦）。
- 共享面：workflow 资产库跨人设可见性（按声明断言）。
- Web：群聊 pane + 房间 WS + hub 过滤（含**损坏快照**）+ `DELETE` 拒删 + **WS `reset` 拒改内部会话**。
- 收尾：全量 pytest + `openspec validate --strict` + artifact checker + benchmark smoke。

## Open Questions

（无。Q4 / Q5a / Q5b 已由用户于 2026-10-12 拍板，答复记录见 `reviews/grill-design.md` 的 `## User Confirmation`。）

## Confirmed Answers（用户拍板，2026-10-12）

- **Q4**: 首版会话数上限 = **50**，超出**排队**；做成可配置项。
- **Q5a**: 首版**做**群共享 notice（Decision 16）。
- **Q5b**: 首版**不做**「引用另一段对话作为上下文」（Non-Goals）。
- **Q6**（记忆粒度）: 记忆**每个群独立**——同一人设的单聊 / 各群各一份、互不可见（与 DS Bot 故意分歧，Decision 7）。
- **Q7**（记忆 review 触发）: **每人自己发言后 review 自己 + 静默成员落后补齐**（Decision 17）。
