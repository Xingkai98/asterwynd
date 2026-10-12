## Context

本项目当前是「单 agent + 单会话」为主的形态：Web 层 `AgentSession` 持一个 `AgentLoop`（`web/session.py:1335-1346`），多会话靠 `SessionManager` 并发；多 agent 的现成设施是 `SubAgentManager`（子 session + 多次 run，但**仅内存、不面向用户**，`agent/subagent/manager.py:470`）与 workflow DSL（**DAG 批处理**，`agent/subagent/scheduler.py`）。

本 change 要新增的是一种**长期存在、面向用户、可交互轮次**的多 agent 形态，参照 DS Bot。它与既有 subagent（一次性委托）和 workflow（批处理图）都不同，因此是新增能力域而不是接入。

用户诉求（issue #302）：单聊 + 群聊；群聊由 Chief 推进、可 `@` 成员；单聊与群聊内容不耦合；人设长期记忆共享。

## Goals / Non-Goals

**Goals:**

- 长期 agent 人设的建模、持久化与 Web 管理。
- 单聊/群聊会话分离，人设级长期记忆。
- 会话式群聊编排：有序轮次、`@` 点名、静默、Chief 默认应答。
- Web 群聊视图。

**Non-Goals:**

- 不改 AgentLoop 主循环、工具协议、workflow DSL / DAG 调度器语义。
- 不复刻 DS Bot 的外围功能（浏览器面板、secrets、用量页、语音、定时任务、头像角色系统）。
- 不在本 change 中做多租户 / 鉴权；沿用现有单机本地 Web 的信任模型。
- 不与既有 `subagents` / `multi-agent-collaboration` 的 DAG 编排混做。

## Decisions

### Decision 1: 一个人设 = 一个 AgentSession

每个长期人设由一个 `AgentSession`（各自 `AgentLoop` + messages + `event_channel`）承载，而非扩展现有 `SubAgentManager`。

理由：subagent 会话仅内存、system prompt 硬编码为「受限子 agent」、不面向用户、不可跨进程恢复，与「长期人设」语义冲突。`AgentSession` 已有落盘（`SessionStore`）与事件通道，复用面最大。
代价：每人设一份 `AgentLoop`（含 MCP/工具注册表/Sandbox），构造成本随人设数增长——上限待定（见 Open Questions）。

### Decision 2: 群内会话与单聊会话分离

每个 (persona, room) 组合持有一个独立会话；单聊另有一个会话。群聊内容不写入单聊会话，反之亦然。

理由：这是用户明确诉求，也是 DS Bot 的核心机制（`groups.js:128-145`）；保证「单聊上下文」不被群聊噪声污染。

### Decision 3: 群聊编排器与 DAG 调度器并列、新建

新建一个**轮次式**编排器（turn-based），负责：决定本轮发言者顺序、驱动每个成员的人设会话各跑一轮、把产出写回房间日志、解析 `@` 点名与静默（PASS）、施加每轮/每成员上限。

理由：现有 workflow 是数据依赖驱动的 DAG，无交互/轮次节点、跑完不可追加，语义不匹配；强行复用会把两种模型揉坏。

### Decision 4: 记忆作用域细分为「项目 × persona」

在既有 `PersistentMemory`（项目级，`agent/memory/persistent.py:183`）之上引入人设维作用域：每个人设一份长期记忆（+ 可选 team 共享），单聊与群聊共享同一份。

理由：匹配「记忆属于这个人设」的诉求；复用既有去重/衰减/检索能力而非另起一套。

### Decision 5: Web 承载 = 房间级 WebSocket + 渲染 per-pane 化

新增房间级端点/WS；前端聊天渲染从「全局单会话」改为 per-pane（现为全局变量，`web/static/chat.js:71-77`）。

理由：既有 `/ws/{session_id}` 与「session = 一个 AgentLoop」语义绑死，群聊需要按房间聚合多个 agent 的输出。

## Pre-Implementation Review

- Questions resolved:
  - 本 change 尚未经过 `grilling` 设计追问闭环；下列 Open Questions 未拍板前不得进入实现。
- Options considered:
  - 以 `AgentSession` 承载人设（本设计）vs 扩展 `SubAgentManager` 为长期实体 vs 新起独立运行时。
- Rejected alternatives:
  - 扩展 `SubAgentManager`：其会话不落盘、system prompt 受限、不面向用户，改造成本高于另建。
- Final confirmations:
  - 实现前必须用 `grilling` 逐项确认 Open Questions，并跑设计阶段对抗闭环（`reviews/grill-design.md` + `reviews/grill-adversarial.md`）。
- Remaining risks:
  - N 份 AgentLoop 的资源上限、群聊成本、以及既有 `run_lock`/并发语义的交互尚未验证。

## Risks / Trade-offs

- [Risk] 群聊 token 成本随发言者数放大。Mitigation: 默认 Chief/admin 模式 + 静默 + 每轮每成员发言上限（参照 DS Bot `constants.js:23,54`）。
- [Risk] 每人设一份 AgentLoop 导致内存/启动开销线性增长。Mitigation: 人设数上限 + 懒构造（人设被首次使用才建 loop 并缓存）。
- [Risk] 群聊内容意外泄漏进单聊（或反向）。Mitigation: 会话物理分离 + 单测断言隔离。
- [Risk] 记忆作用域改造触碰既有记忆系统。Mitigation: 只做作用域维度扩展，复用现有 API；回归既有 `long-term-memory` 测试。
- [Risk] 渲染 per-pane 化回归既有 Chat 视图。Mitigation: 保留现有单会话路径，新增抽象并复用 `tool_rows.js` 等纯函数；Web smoke 覆盖。

## Testing Strategy

- 人设/房间 CRUD 与持久化：单测 + 重启后恢复测试。
- 群聊编排：轮次顺序、`@` 点名、静默、每轮/每成员上限、成员新增/移除中途变更。
- 会话分离：单聊/群聊内容互不泄漏的负向断言。
- 记忆作用域：人设间记忆隔离 + 同人设单聊/群聊共享。
- Web：群聊端点 + WS 事件 + 视图渲染 smoke（含多 agent 按来源区分）。
- 并发：多人设并发 run 与既有 `run_lock` 语义不冲突。
- 收尾：全量 pytest + `openspec validate --strict` + artifact checker。

## Open Questions

- **Q1**: 群聊编排器是**全新独立模块**，还是先复用 `SubAgentManager` 的「session+runs」双层骨架扩成人设？（涉及是否新建运行时）
- **Q2**: 人设级记忆是在现有 `PersistentMemory` 上加「persona 维」，还是另起独立 store？
- **Q3**: Chief/admin 是**普通人设兼任**（可指定），还是**系统内置角色**（不可删）？
- **Q4**: 首版人设数量上限与「一个群 = N 个 AgentLoop」的并发上限取多少？是否接受懒构造 + 上限（vs 全量常驻）？
- **Q5**: 首版范围是否排除「引用另一段对话作为上下文」（DS Bot 的 + → Reference）与「群共享 notice」？

（Q1/Q2 若能由代码在 grill 阶段判定则移出本队列并记入 `## Code-Resolved Questions`；真正需用户取舍的才停轮确认。）
