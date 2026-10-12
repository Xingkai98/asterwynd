## Why

用户希望本项目 Web 上有一个「群聊」板块：维护若干**长期存在的 agent 人设**，可以和人设**单聊**，也可以开**群聊**（由 Chief 主持、可 `@` 指定成员、成员轮流发言）；单聊与群聊的**对话内容互不耦合**，只有人设的**长期记忆**共享。参照实现是 DSH 的社区插件 **DS Bot**（Fei2411/DeepSeek-Bot）。

本 change 新增一个能力域级别的能力，不改变既有 AgentLoop / workflow DAG / subagent 语义。关联 issue #302。

## Change Type

- primary: feature
- secondary: []

## What Changes

- 新增**长期 agent 人设**（roster）：稳定标识、名称、角色标签、指令、模型绑定，跨进程持久化。
- 新增**会话式群聊编排器**：有序轮次、`@<名称>` 点名、成员静默（无新增内容不发言）、Chief/admin 默认应答并派活；与既有 DAG 调度器**并列**，不修改其语义。
- 每个 agent 人设 SHALL 拥有与用户的**单聊会话**，以及在其加入的每个群里的**独立群内会话**；单聊与群聊内容 SHALL NOT 互相泄漏。
- 记忆 SHALL 细分出**人设维**作用域：每个人设一份跨会话长期记忆，同一人设在单聊与群聊共享同一份记忆；为此 SHALL 先补上 Web 路径的长期记忆接线（现状 Web 未接）。
- 新增**房间日志**作为群时间线的权威有序数据（成员看到本轮此前内容、重连后还原有序群消息流）。
- 会话标识与 hub 可见性 SHALL 明确：人设单聊会话与 (人设, 群) 群内会话 SHALL NOT 以普通会话身份出现在 hub，且 SHALL NOT 可被会话删除接口直接删除。
- 群聊会话内的**交互式 pending（审批/提问）SHALL 显式降级**，不得让无人值守的轮次阻塞到超时。
- Web UI SHALL 新增**群聊 pane**（新 pane 类型 + 房间级 WS），展示消息流、成员与当前发言者，并按发言人区分不同 agent。

## Capabilities

### Modified Capabilities

- `multi-agent-collaboration`: 从空基线升级为「长期人设 + 会话式群聊编排」能力（新增 roster、房间日志、群聊轮次与终止条件、房间级互斥、两级主持角色、跨人设共享面声明）；并以 MODIFIED 澄清既有「Orchestration Reuses Workflow Persistence Discipline / SHALL NOT introduce a separate control plane」只约束 **subagent orchestration**，不覆盖本 change 的交互式编排器。
- `long-term-memory`: 记忆作用域从 project/repo 扩展出 persona 维（既有规格 `openspec/specs/long-term-memory/spec.md:74-83` 的 `Scope 隔离` 钉定 project/repo scope，故需 MODIFIED delta）。
- `web-ui`: 新增群聊视图 + 房间级 WS、人设/房间管理入口与单聊入口、内部会话列表过滤与生命周期保护、内部会话 pending 降级（后两项 respective 以 MODIFIED 收窄既有「审批必须暴露」与「pending 跨连接存活」两条 Requirement 到面向用户的会话）。

## Dependencies

- 复用既有（已实现）：多会话 `SessionManager` / `SessionStore`、会话级 `SessionEventChannel`、前端 per-tab（多 tab=多 WS）模型。
- 依赖既有 `long-term-memory` 的去重/衰减/检索能力；**并需先补一个现存缺口**：Web 路径今天**未接** `persistent_memory`（`web/session.py:1648-1688` 未传，CLI 路径 `agent/main.py:255,282,325` 已接），本 change 在人设会话上补齐并加 persona 维（普通 Web 会话的接线属另一 change）。

## Impact Analysis

- 影响代码：
  - `agent/`：新增人设/房间模型与持久化（**workspace 级**落点）、房间日志、群聊轮次编排器（新模块，如 `agent/team/`）；编排器依赖 `SessionRunner` 抽象（由 web 层注入），本模块不 import `web`。
  - `agent/session.py`：`SessionSnapshot` 增 `kind`；内部会话 id 前缀约定 + `remove`/`reset` 路径的内部会话保护。
  - `agent/memory/persistent.py`：记忆作用域扩展出 persona 维（同级布局 `<project-hash>/personas/<id>/memory`）。
  - `agent/context/sources.py`：记忆注入块标题区分（`## Persona Memory`）。
  - `web/session.py`：人设会话注入 `persistent_memory` + `memory_config` + `llm`；实现并注入 `SessionRunner`；房间级事件汇聚与房间级互斥。
  - `web/server.py`：群聊 HTTP/WS 端点 + 房间级 WS；hub 过滤内部会话；`DELETE` 与 WS `reset` 拒作用于内部会话。
  - `web/static/`：新增群聊 pane JS/CSS；扩展 WS 路由（房间级）。
- 影响测试：
  - 人设/房间 CRUD 与持久化（跨重启、跨 workspace）；删除级联（会话/房间日志/persona 记忆）；群聊编排（slot 序列、**轮次终止四出口**、**房间级互斥**、`@` 解析口径、静默含游标推进、上限、成员中途变更）；`SessionRunner` 四态契约（并发被拒不复用陈旧文本）；会话分离负向断言；记忆（人设间隔离 + 同人设共享 + 并发写 + 接线完整性 + 注入块标题）；共享面（workflow 资产库）；Web（群聊 pane + 房间 WS + hub 过滤含损坏快照 + `DELETE`/`reset` 拒作用于内部会话）。
- 影响文档：`openspec/specs/{multi-agent-collaboration,long-term-memory,web-ui}/spec.md` 同步；`docs/architecture.md` 增补群聊编排小节。
- 不改变：AgentLoop 主循环、工具协议、workflow DSL 与 DAG 调度器语义、普通 Web 会话的既有行为（记忆接线仅限人设会话）。

## Reference Implementation Research

- research_tier: full
- status: enabled
- reason: 架构级新能力（新增人设/房间模型 + 会话式编排器 + Web 视图），并直接对标一个成熟社区实现（DS Bot），需完整参考实现调研。
- research questions:
  - 长期 agent 人设如何建模与持久化？单聊与群聊的会话如何分离？
  - 群聊如何编排轮次、@点名与静默，并控制成本（防无限互相应答）？
  - 群聊与单聊如何共享同一人设的记忆？
  - 在「一 session 一 AgentLoop」的既有 Web 架构上如何承载多个 agent？
- findings:
  - 参考实现 **Fei2411/DeepSeek-Bot**（本地克隆 `/home/shared/agent-study/dsh-bot-research/DeepSeek-Bot-main/`，Apache-2.0）：每个 bot = 一个长驻会话；群聊 = 一个不调模型的 relay 会话（`ds-bot/src/host/groups.js:493-518` 钩 `llm/stream` 合成 `group_relay` 工具调用）+ 每成员每群的隐藏会话（`groups.js:128-145`）；轮次/`@接力`/`[PASS]静默`在 `groups.js:261-321`；Chief = `mainBotIds`（`src/host/prompt.js:25-36`）；记忆两层且按人设分（bot 自有 + team 共享）；成本控制靠 admin 模式 + `[PASS]` + 每轮每成员发言上限（`src/host/constants.js:23,54`、`groups.js:26-27`）。
  - 本项目现状（只读调研 + grill 核实，2026-10-12）：无 persona/roster 抽象；**不复用 `SubAgentManager`**（child session 被父 `AgentLoop` 拥有（`agent/loop.py:167`）、system prompt 硬编码「受限子 agent」（`agent/subagent/manager.py:580,817`）、无会话快照——`_sessions` 是进程内存字典（`agent/subagent/manager.py:470`），仅 run 级 checkpoint 落盘）；workflow 是节点种类封闭四值的 DAG 批处理（`agent/subagent/scheduler.py:1722-1732`）；Web 假设一 session 一 AgentLoop（`web/session.py:1335-1346`）；记忆为项目级作用域（`agent/memory/persistent.py:180-185`）且 **Web 路径未接 `persistent_memory`**（`web/session.py:1648-1688` 未传）；前端已 per-tab（`web/static/chat.js:144,211-229`）但 WS URL 写死 `/ws/${sessionId}`（`chat.js:436`）；`Message` 无 timestamp/speaker（`agent/message.py:147-155`）。
  - 可复用：多会话并发 + `SessionStore`（`agent/session.py:81`）、会话级事件通道（`web/session.py:355`）、per-loop `persistent_memory` 注入面（`agent/loop.py:138`，需本 change 在 Web 侧接上）、前端 per-tab 模型（`web/static/chat.js:144,211-229`）。
  - **同类实现对照**（本地 `/home/shared/agent-study/dsh-bot-research/`，四个轴）：
    - **轮次终止**：DS Bot 靠「slot 走完 / 上限（成员数 + 固定额外轮次）」；`dsh-agent-group` 用显式 `maxRounds` 撞限返回 `{kind:'round-limit'}`（`packages/group-chat/src/scheduler.ts:217`）；`dsh-adrian-agents-group-work` **无内建终止策略**——「the brief carries the job and the stop condition」（`SPEC.md`）。⇒ 本 change 取**显式上限**（无人值守 Web 面板需要确定终止）。
    - **静默机制**：仅 DS Bot 有显式 `[PASS]` 哨兵（`groups.js:99`）；`dsh-agent-group` 用「连续失败预算暂停房间」而非静默；adrian 用「失败必重入队」。⇒ 本 change 取 `[PASS]` 哨兵。
    - **成本上限**：DS Bot = 每轮每成员额度 + 成员数上限 12 + 240s 单轮超时；`dsh-agent-group` = `maxRounds` + 连续失败预算；adrian = 无。⇒ 本 change 取显式上限 + 单轮超时。
    - **成员能否自开轮次**：DS Bot **可以**（`ROOM_BOT_ROUNDS = 3`，`constants.js:53-54`）；adrian 由 chair 驱动、成员不自开。⇒ 本 change **收紧为仅用户开轮**（与参照的**故意分歧**，理由：无人值守面板下成员互开轮次放大成本且无用户在场收敛）。
- design impact:
  - 采用「每个 agent 人设 = 一个 AgentSession（各自 AgentLoop + 事件通道）」承载，而非扩展 `SubAgentManager`。
  - 记忆作用域需从 project/repo 细分出 persona 维，且**先补 Web 记忆接线**（仅人设会话）。
  - 群聊编排器新建，与既有 DAG 调度器并列；依赖 `SessionRunner` 抽象由 web 层注入（避免 `agent/ → web/` 反向依赖）。
  - Web 前端**已 per-tab**，无需重构渲染；真正工作是新增**群聊 pane 类型 + 房间级 WS**（现 WS 路由写死 `/ws/${sessionId}`）。
