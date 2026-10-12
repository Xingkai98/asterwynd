## Context

本项目当前是「单 agent + 单会话」为主的形态：Web 层 `AgentSession` 持一个 `AgentLoop`（`web/session.py:1335-1346`），多会话靠 `SessionManager` 并发；现成的多 agent 设施是 `SubAgentManager`（子 session + 多次 run，进程内存）与 workflow DSL（DAG 批处理，`agent/subagent/scheduler.py`）。

本 change 新增一种**长期存在、面向用户、可交互轮次**的多 agent 形态，参照 DS Bot（Fei2411/DeepSeek-Bot）。它与既有 subagent（一次性委托）和 workflow（批处理图）都不同，因此是新增能力域而非接入。

**两个必须正视的现状**（grill 逐条核实，非 design 自述）：

1. **Web 路径今天没有长期记忆**：`_create_session` 构造工具注册表与 `AgentLoop` 时都**没传** `persistent_memory`（该参数两处都支持，见 `web/session.py:1648-1688`），`MemoryIndexSource` 拿到 `None` 返回空串，记忆工具退化到工厂默认的**项目级**实例（`agent/tools/factory.py:319-327`）。CLI 路径已接线（`agent/main.py:255,282,325`）。⇒ 「人设级记忆」实为「**先补 Web 接线，再加维度**」。
2. **分层是单向 `web/ → agent/`**：`agent/` 只在 CLI 入口函数内延迟 import web（`agent/main.py:684`，唯一反向点）。⇒ 群聊编排器**不能**放在 `agent/` 里反向驱动 `web.AgentSession`。

用户诉求（issue #302）：单聊 + 群聊；群聊由 Chief 推进、可 `@` 成员；单聊与群聊内容不耦合；人设长期记忆共享。

## Goals / Non-Goals

**Goals:**

- 长期 agent 人设的建模、持久化与 Web 管理。
- 单聊/群聊会话分离（结构性保证）。
- 会话式群聊编排：轮次、`@` 点名、静默、Chief 默认应答、**明确的轮次终止条件**。
- 房间日志：群时间线的**权威**有序数据。
- 人设级长期记忆（含补 Web 记忆接线）。
- Web 群聊 pane（新增 pane 类型 + 新 WS 协议）。

**Non-Goals:**

- 不改 AgentLoop 主循环、工具协议、workflow DSL / DAG 调度器语义。
- 不复刻 DS Bot 的外围功能（浏览器面板、secrets、用量页、语音、定时任务、头像角色系统）。
- 不做多租户 / 鉴权；沿用现有单机本地 Web 的信任模型。
- **首版不做**「引用另一段对话作为上下文」与「群共享 notice」（见 Open Question Q5）——参照实现的 relay 架构**不可移植**（它靠宿主 `llm/stream` 钩子合成假工具调用；本仓 `HookManager` 只有生命周期观察钩子，无流层拦截点，`agent/hooks/manager.py:15-64`）。
- 不把 workflow 资产库按人设分桶（首版显式声明其为**共享面**，见 Decision 12）。

## Decisions

### Decision 1: 一个人设 = 一个 AgentSession

每个人设由一个 `AgentSession`（各自 `AgentLoop` + messages + `event_channel`）承载，**不**扩展 `SubAgentManager`。

理由（三条代码级否证）：subagent 的 child session 被**父 `AgentLoop` 拥有**（`agent/loop.py:167` 构造时即 `configure_runtime`）、其 system prompt 硬编码为「受限子 agent」（`agent/subagent/manager.py:580,817`）、且**无会话快照**（`_sessions` 是进程内存字典，`agent/subagent/manager.py:470`；只有 run 级 checkpoint 落盘）。三者都与「长期、可跨进程恢复、面向用户」冲突。
承载可行性（已确认）：人设指令走现成注入面 `AgentSession.init_messages(<指令>)` → `agent._user_system_prompt`，随 `SessionSnapshot.user_system_prompt` 落盘、随 resume 回灌（`web/session.py:1378-1380`、`agent/loop.py:223,713-714`、`agent/session.py:27`），**不需要新运行时**。
代价：每人设一份 `AgentLoop`（含 MCP 子进程、独立 subagent 并发额度、工具注册表）。⇒ 必须**懒构造 + 有上限**（见 Decision 6 与 Open Question Q4）。

### Decision 2: 单聊与群聊会话分离是结构性保证

每个 (persona, room) 持有一个独立会话；单聊另有一个会话。这不是「需要额外防护的性质」——`run_lock` 与 `event_channel` 都是 per-`AgentSession`（`web/session.py:1359,1367,1770-1780`），单聊 tab 与房间 WS 各自 attach 不同 session 的通道，不存在跨 pane 事件串流。

⇒ 真正的跨会话泄漏面在**共享存储**（记忆、workflow 资产库），不在会话通道；对应 Decision 6 / Decision 12 与 Testing Strategy。

### Decision 3: 群聊编排器与 DAG 调度器并列、新建

新建**轮次式**编排器，负责：定本轮发言者顺序、驱动各成员会话跑一轮、把产出写回房间日志、解析 `@` 点名与静默、施加每轮/每成员上限、判定轮次终止。

理由：调度器节点种类是**封闭四值**（`subagent`/`foreach`/`aggregate`/`route`，`agent/subagent/scheduler.py:1722-1732`），无交互节点、无轮次节点、无「跑完再追加」入口；塞进去会同时破坏两套语义。

### Decision 4: 编排器分层——依赖 `SessionRunner` 抽象，由 web 层注入

编排器依赖一个抽象 `SessionRunner`：`run(session_id, message) -> final_text`（「跑一个会话并拿回最终文本」）。该抽象由 **web 层实现并注入**（web 层持有 `AgentSession` / `SessionManager`）。

理由：本仓分层单向 `web/ → agent/`（`agent/main.py:684` 是唯一反向点）。若编排器放 `agent/` 却直接驱动 `web.AgentSession`，即为反向依赖。用注入抽象替代，编排器模块本身不 import `web`。

### Decision 5: 房间日志是群时间线的权威数据

新增**房间日志**：有序追加条目数组，每条含 `seq` / `speaker`（用户 or 人设 id）/ `kind`（`user` | `post` | `lookup`）/ `text` / 时间戳，随房间记录持久化。

- **权威关系**：房间日志是群时间线的唯一权威；重连后由它还原有序群消息流（不靠合并 N 份 per-`AgentSession` 历史——`Message` 无 timestamp/speaker 字段，`agent/message.py:147-155`；`build_history_payload` 只发 role，`web/session.py:62-94`）。
- **注入机制**：成员本轮看到的 = 房间日志中「该成员上次发言之后」的切片 + 本轮发言序位说明（参照 DS Bot 的 `unseenLines` / `roomPrompt`）。
- **写入**：编排器每个成员发言后 append，用户消息也 append。

### Decision 6: 人设级记忆——先补 Web 接线（仅人设会话），再加 persona 维

先修现存缺口：在**人设会话**的构造成本中注入 `persistent_memory`（`SessionRunner`/web 层负责），使 `MemoryIndexSource` 能注入索引、记忆工具落在人设实例上。**不**顺带给普通 Web 会话接线——那会改变既有单会话 Web 行为与提示词（多出一块 `## Project Memory`），与既有 `web-ui` 测试面冲突，属另一 change。

再在人设实例上细分 scope：`PersistentMemory` 增 **persona 维**（同一 store 类，目录布局细分：`<project-hash>/memory/personas/<persona-id>/`），单聊与群聊**共享同一 persona scope**。

理由：复用既有去重/衰减/检索能力；同时满足「人设间互不检索」与「同人设单聊/群聊共享」。注意既有规格把 scope 钉在 project/repo（`openspec/specs/long-term-memory/spec.md:76`），故本 change 需在 `long-term-memory` 上加 MODIFIED delta（见 Capabilities）。
风险：同一人设单聊/群聊并发写同一目录——参见 Risks。

### Decision 7: 会话标识与 hub 可见性

- 稳定映射：`persona → 单聊会话 id`、`(persona, room) → 群内会话 id`，分别存 roster 与房间记录（不靠随机 id 猜测）。
- 标记：`SessionSnapshot` 增 `kind`（`chat` / `persona` / `room_member` 等），人设/群内会话**不**以普通会话身份出现在 hub。
- 保护：`GET /api/sessions`（`web/server.py:320`）过滤内部会话；`DELETE /api/sessions/{id}`（`web/server.py:334`）拒删人设/群内会话底座（只能经人设/房间删除接口）。

理由：`SessionStore.list_sessions()` 会枚举 workspace 下**全部**会话目录（`agent/session.py:146-206`）并被 hub 直接暴露；不处理会污染会话列表并可被误删。

### Decision 8: 群聊会话内的 pending 交互显式降级

群内会话**不暴露**交互式提问（ask 类工具从群聊会话工具面撤除）与**阻塞式**审批等待：审批类调用在群聊会话按 **fail-closed 立即判定为 unavailable**，不阻塞整轮。

理由：成员 run 走同一套 `_create_session`，会装上 `WebApprovalHandler`（默认 600s 超时、fail-closed）与 `WebQuestionHandler`（默认 300s，`web/session.py:1630-1637`、`agent/config.py:398-399`）。无人值守的轮次里成员一触发审批就会阻塞到超时（最长 600s）。
已知限制（记入 Risks）：群聊成员因此**不能**执行需审批的高风险操作。后续可接房间 WS 承载 pending 并按成员区分来源。

### Decision 9: 前端 = 新增 pane 类型 + 新 WS 协议

**修正前提**：`web/static/chat.js:71-77` 的模块级 DOM 引用**已被 per-tab 重绑**（`createTab` 每 tab 持自己的 `messagesEl`/`ws`，`bindActiveTab` 切换时重指向，`chat.js:144,211-229`）；`web-ui` 规格已有「多标签会话」与「多标签瞬态状态隔离」两条 Requirement。⇒ 不是「把全局单会话改成 per-pane」。

真正的工作：新增一种 **pane 类型**（群聊 pane），并把 WS URL 从写死的 `/ws/${sessionId}`（`chat.js:436`）扩展出**房间级 WS**（如 `/ws/room/{room_id}`）。房间 WS 按其成员 session 的 `event_channel` 汇聚并按发言人标注输出。

### Decision 10: 静默 = 哨兵文本 + 解析最终 content

成员被提示「无新增内容时回复 `[PASS]`」；编排器解析成员 run 的最终 content 判静默。**不**新增控制工具（会污染所有既有 agent 的工具面）。
理由：与参照实现一致（`ds-bot/src/host/groups.js:99` 的 `ROOM_REPLY`），本仓无同类控制工具先例。

### Decision 11: 每轮预算与轮次终止

- **每轮上限** = 成员数 + 固定额外轮次（群有 admin 时再加固定额度），并按成员分别计数封顶（参照 `ds-bot/src/host/groups.js:24-25,262`、`constants.js:54`）。
- **轮次终止**：一轮在所有 slot 走完（或触上限）时结束；**用户再次发言才开启新一轮**；触上限时静默停止并在房间日志记一条「轮次因达上限结束」。

理由：spec delta 若无终止条件，tasks 的「轮次顺序」测试没有可断言的终点。

### Decision 12: 跨人设共享面显式声明

workflow 资产库是**仓库级共享**（`~/.asterwynd/projects/<hash>/workflow-assets/`，`agent/subagent/workflow_assets.py:26-38`），且资产索引默认注入每个 loop 的上下文（`agent/loop.py:155`，默认 `True`）。首版**不**按人设分桶，但 SHALL 在 spec delta 里**显式声明其为共享面**，避免「人设隔离」验收只测记忆而漏掉这条隐式通道。

## Pre-Implementation Review

- Questions resolved:
  - Q1（编排器形态）：**新建独立模块**，否证 `SubAgentManager` 复用（父 loop 拥有 / 硬编码受限 prompt / 无会话快照）。
  - Q2（记忆作用域）：**同一 `PersistentMemory` 加 persona 维**；且必须先补 Web 接线（仅人设会话）。
  - Q3（Chief 角色）：**被指派的普通人设**（可指定、可多个），非系统内置不可删角色（`mainBotIds` 是 roster 上的 id 列表）。
  - 静默机制、每轮预算形态、编排器与 DAG 并列—均经代码核实确认。
- Options considered:
  - 人设承载：`AgentSession`（本设计）vs 扩展 `SubAgentManager` vs 新起运行时。
  - 记忆：同一 store 加维度 vs 另起独立 store。
  - 编排器位置：`agent/` 新模块 + 注入抽象（本设计）vs 放 web 层。
- Rejected alternatives:
  - 扩展 `SubAgentManager`：父 loop 拥有 + 硬编码受限 prompt + 无会话快照，改造成本高于另建。
  - 编排器直接放在 `agent/` 并 import web：反向依赖，违反分层。
- Final confirmations:
  - 本 change 已经过独立零记忆 grill（`reviews/grill-design.md`，5 Confirmed Decisions）；实现前 SHALL 完成设计阶段对抗闭环（`reviews/grill-adversarial.md`）并停轮拍板 Open Questions。
- Remaining risks:
  - 见 Risks（并发写记忆、资产库共享面、群聊 pending 降级限制、人设数上限）。

## Risks / Trade-offs

- [Risk] 群聊 token 成本随发言者数放大。Mitigation: Chief/admin 模式 + 静默 + 每轮每成员上限（Decision 11）。
- [Risk] 每人设一份 AgentLoop（MCP 子进程 + 独立并发额度 + 工具注册表）线性增长。Mitigation: 懒构造 + 人设数上限（Q4）。
- [Risk] **同一人设的单聊与群聊并发写同一份记忆**：`PersistentMemory` 的可逆写保护是 `git commit-before-write`，`_git_commit` 在提交失败时**抛 `RuntimeError` 中止写入**（不是降级，`agent/memory/persistent.py:433-465`）；并发写会命中竞态，且每实例各有一份 `_last_decay_run` 会重复衰减扫描。Mitigation: 明确「同一人设 SHALL 共享同一个 `PersistentMemory` 实例」+ 并发写测试。
- [Risk] **跨人设隐式通道不止记忆**：workflow 资产库仓库级共享（Decision 12）。Mitigation: spec delta 显式声明共享面；验收须覆盖。
- [Risk] 群聊会话 pending 降级后成员**不能做需审批的高风险操作**（Decision 8）。Mitigation: 记入已知限制；后续接房间 WS。
- [Risk] 群聊内容意外泄漏进单聊（或反向）。Mitigation: 会话物理分离（结构性保证，Decision 2）+ 负向单测。
- [Risk] 记忆作用域改造触碰既有 `long-term-memory` 规格与测试。Mitigation: 加 MODIFIED delta + 回归既有测试。
- [Risk] 新增群聊 pane / 房间 WS 回归既有 Chat。Mitigation: 复用 per-tab 机制与 `tool_rows.js` 纯函数；Web smoke 覆盖。

## Testing Strategy

- 人设/房间 CRUD 与持久化：单测 + 重启后恢复（含人设指令跨重启）。
- 群聊编排：轮次顺序、**轮次终止条件**（用户再发言才开新一轮 / 触上限静默停止）、`@` 接力边界（点不在列表的人 / 点名多人 / 点自己 / `@` 在句中）、静默、每轮/每成员上限、成员中途变更。
- 会话分离：单聊/群聊内容互不泄漏的负向断言。
- 记忆：人设间隔离 + 同人设单聊/群聊共享 + **同一人设并发写记忆**。
- 共享面：workflow 资产库的跨人设可见性（按声明断言，防未声明泄漏）。
- Web：群聊 pane + 房间 WS + hub 过滤（内部会话不出现在 `/api/sessions`）+ `DELETE` 拒删。
- 并发：多人设并发 run 与既有 `run_lock` 语义不冲突。
- 收尾：全量 pytest + `openspec validate --strict` + artifact checker + benchmark smoke。

## Open Questions

- **Q4**: 首版默认**人设数量上限**取多少？是否暴露为配置项？是否把「每群 × 每成员」的群内会话计入？超限行为是拒绝创建还是排队？（机制半边已定死：必须懒构造 + 必须有上限，全仓无现成会话数闸门。）
- **Q5**: 首版是否排除「引用另一段对话作为上下文」与「群共享 notice」？（两者本仓无可复用 primitive，参照实现 relay 架构不可移植 ⇒ 纯范围取舍；不做则记入 Non-Goals。）
