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
- 记忆 SHALL 细分出**人设维**作用域：每个人设一份跨会话长期记忆，同一人设在单聊与群聊共享同一份记忆。
- Web UI SHALL 新增**群聊（Team）视图**，展示消息流、成员与当前发言者，并按发言人区分不同 agent。

## Capabilities

### Modified Capabilities

- `multi-agent-collaboration`: 从空基线升级为「长期人设 + 会话式群聊编排」能力（新增 roster、群聊轮次、人设级记忆作用域）。
- `web-ui`: 新增群聊视图与多 agent 消息按来源区分。

## Dependencies

- 复用既有（已实现）：多会话 `SessionManager` / `SessionStore`、会话级 `SessionEventChannel`、per-loop `persistent_memory`、前端多 tab=多 WS 模型。
- 依赖既有 `long-term-memory` 的内存去重/衰减/检索能力。

## Impact Analysis

- 影响代码：
  - `agent/`：新增人设/房间模型与持久化、群聊编排器（新建模块，如 `agent/team/` 或 `agent/groupchat/`）。
  - `agent/memory/persistent.py`：记忆作用域从项目级扩展出人设维。
  - `web/server.py`、`web/session.py`：新增群聊 HTTP/WS 端点与房间级事件通道。
  - `web/static/`：新增群聊视图 JS/CSS，聊天渲染 per-pane 化。
- 影响测试：
  - 人设/房间 CRUD 与持久化单测；群聊轮次编排单测（轮次、@接力、静默、上限）；记忆作用域隔离单测；Web 视图与 WS 端点测试；多 agent 并发 run 测试。
- 影响文档：`openspec/specs/multi-agent-collaboration/spec.md`、`openspec/specs/web-ui/spec.md` 同步；`docs/architecture.md` 增补群聊编排小节。
- 不改变：AgentLoop 主循环、工具协议、workflow DSL 与 DAG 调度器语义。

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
  - 本项目现状（只读调研，2026-10-12）：无 persona/roster 抽象；子 agent session 仅内存（`agent/subagent/manager.py:470`、`agent/subagent/snapshot.py:3`）；workflow 是 DAG 批处理（`agent/subagent/scheduler.py`）；Web 假设一 session 一 AgentLoop（`web/session.py:1335-1346`）；记忆为项目级作用域（`agent/memory/persistent.py:183`）。
  - 可复用：多会话并发 + `SessionStore`（`agent/session.py:81`）、会话级事件通道（`web/session.py:355`）、per-loop `persistent_memory`（`agent/loop.py:132`）、前端多 tab=多 WS（`web/static/chat.js:5-8`）。
- design impact:
  - 采用「每个 agent 人设 = 一个 AgentSession（各自 AgentLoop + 事件通道）」承载，而非扩展 `SubAgentManager`（后者不落盘、不面向用户）。
  - 记忆作用域需从项目级细分为「项目 × persona」。
  - 群聊编排器新建，与既有 DAG 调度器并列。
  - Web 聊天渲染需 per-pane 化（现为全局单会话假设，`web/static/chat.js:71-77`）。
