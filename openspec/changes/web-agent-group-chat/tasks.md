## 1. 规格

- [x] 1.1 修改 `multi-agent-collaboration` 规格：长期人设与两级主持角色（roster `mainBotIds` + 房间 `admin`）、单聊/群聊会话分离、房间日志 schema（`kind: user|post|system`）、轮次编排与 slot 序列、`@` 解析口径、房间级互斥与**轮次终止三出口**（走完 / 达上限 / 失败或超时）、跨人设共享面声明；并以 MODIFIED 澄清既有「SHALL NOT introduce a separate control plane」只约束 subagent orchestration。
- [x] 1.2 修改 `long-term-memory` 规格：`Scope 隔离` 增「人设 × 会话面」scope（MODIFIED，匹配既有 Requirement 名，保留原 Scenario）；并新增「人设记忆的 review 触发与游标」。
- [x] 1.3 修改 `web-ui` 规格：群聊视图 + 房间级 WS、多 agent 按来源区分、人设/房间管理入口与单聊入口、内部会话列表过滤与生命周期保护（含 WS `reset`）、内部会话 pending 降级；后两项以 MODIFIED 收窄既有「审批必须暴露」与「pending 跨连接存活」两条 Requirement。
- [x] 1.4 同步对应 current spec 到 `openspec/specs/<capability>/spec.md`（含 `long-term-memory`）。
- [x] 1.5 开发前使用 `grilling` 审视 `design.md`，逐项确认实现细节、依赖、风险、测试策略和文档影响，并跑设计阶段对抗闭环（`reviews/grill-design.md` + `reviews/grill-adversarial.md`）。
- [x] 1.6 在停轮确认里逐项拍板 `design.md` 的 Open Questions，并把答复记录进 `grill-design.md` 的 `## User Confirmation`；答复后清理 `design.md` Non-Goals 与 Open Question 的口径冲突。

## 2. 测试

- [x] 2.1 人设/房间 CRUD 与持久化单测（跨重启、跨 workspace；人设指令恢复）；删除级联（单聊会话 + 群内会话 + 房间日志 + 该人设/房间的**全部记忆 scope**）+ **级联顺序（先底座/记忆、后 roster/房间条目）+ 中断后重试不留孤儿 + 幂等**（含「删群后 room-id 复用不继承旧记忆」）。
- [x] 2.2 群聊编排单测：slot 序列、`@` 解析（用户行首 / 成员句中 / 不在列表 / 多人 / 自己）、静默（含**游标随静默回合推进、不重复注入**）、每轮每成员上限、**轮次终止三出口**（走完 / 达上限 / 失败或超时）、轮次中到达的用户消息（追加进日志 + `@` 追加为当前位次之后的 slot、不改上限基数）、**房间级互斥**（并发不并行开两轮、用户消息排队进本轮）、成员中途变更。
- [x] 2.3 会话分离：单聊/群聊内容互不泄漏的负向断言。
- [x] 2.4 `SessionRunner` 契约：四态映射；`text` 只来自本次 run（**同 session 并发被拒时不复用陈旧文本**）。
- [x] 2.5 记忆 scope：人设间隔离 + **同一人设的单聊/各群之间互相不可见**（每个群独立）；接线完整性（LLM 去重判官存在、`memory_config` 生效）；注入块标题为 `## Persona Memory`；进度推进。记忆 review：**仅实际发言回合**触发、静默成员落后补齐、失败不中断轮次；**上下文压缩 / session resume 后 review 仍推进且不漏读不重读**。
- [x] 2.6 共享面：workflow 资产库跨人设可见性（按「共享面」声明断言，防未声明泄漏）。
- [x] 2.7 Web：群聊 pane + 房间级 WS + hub 过滤内部会话（含**损坏快照**经 id 前缀/roster 判定）+ `DELETE` 拒删 + **WS `reset` 拒改内部会话**。
- [x] 2.8 多人设并发 run 与既有 `run_lock` / 并发语义不冲突。
- [x] 2.9 会话数上限：达上限排队而非拒绝、懒构造未使用的会话面；群共享 notice：注入群内会话且不影响单聊。
- [ ] 2.10 人设运行模式：按人设 `mode` 构造会话（默认 `bypass`）、模式变更生效；房间应答模式：`admin` 仅 admin 应答、`everyone` 全员各得一次机会且可静默。

## 3. 实现

- [x] 3.1 人设（roster）模型与持久化（workspace 级）：稳定 id、名称、角色、指令、模型绑定；`mainBotIds`（可多个）。
- [x] 3.2 房间模型与持久化（workspace 级）：成员、`admin`（单个、可空）、模式、**群共享 `notice`**（Q5a 首版做）；room 记录含 `(persona, room) → 群内会话 id` 映射。
- [x] 3.3 会话标识与生命周期保护：`SessionSnapshot` 增 `kind`；内部会话 id 前缀约定；hub 过滤（`GET /api/sessions`）+ `DELETE` 拒删 + WS `reset` 拒绝（或复用原 id 并回写 roster）。
- [x] 3.4 会话分离：为每个人设建立单聊会话与 (persona, room) 群内会话。
- [x] 3.5 房间日志：schema（seq / speaker / kind / text / ts）+ 持久化 + 游标（回合推进）+ 有界分层切片（首见 / 增量 / 往轮）。
- [x] 3.6 会话式群聊编排器（新模块）：slot 序列算法、`@` 解析、静默（`[PASS]`）、每轮每成员上限、轮次终止三出口、轮次中用户消息处理、**房间级互斥**。
- [x] 3.7 编排器分层：定义并注入 `SessionRunner`（`run(session_id, message) -> TurnOutcome` 四态；web 层从本次 run 事件流取最终文本），编排器不 import `web`。
- [x] 3.8 记忆：人设会话注入 `persistent_memory` + `memory_config` + `llm`（+ 视需要 `quality_config`）；`PersistentMemory` 新增显式 scope 目录入参（给定即原样用作 `memory_dir`；未给保持现状）；scope 按「人设 × 会话面」（`personas/<id>/chat/memory` + `personas/<id>/rooms/<rid>/memory`，同级布局，每 scope 一个实例 + 进度记录，`scope` 取值 `<project-scope>:persona:<pid>[:room:<rid>]`，并新增 `scope` 入参；**记忆工具（`RecallMemory`/`SearchMemory`）的 scope 匹配须用该取值**，否则人设会话检索静默返空）；注入块标题 `## Persona Memory`。
- [x] 3.9 群内会话（`kind: room_member`）pending 降级：撤 ask 类工具；审批类 fail-closed 立即判定。人设单聊（`kind: persona_chat`）**不**降级，照常暴露 pending。
- [x] 3.10 Web：群聊 pane + 房间级 WS（扩展写死的 `/ws/${sessionId}`）；人设/房间管理入口 + 单聊入口 + 删除级联。
- [x] 3.11 会话数上限（默认 50，可配置）+ 超出排队 + 懒构造。
- [x] 3.12 群共享 notice：房间模型字段 + 注入群内会话 prompt（不影响单聊）。
- [x] 3.13 记忆 review：**仅实际发言回合**触发（单聊/群各触发）+ 静默成员按 **review 游标**落后补齐（阈值 30）+ 独立小模型调用 + 写回映射（add/update 走 save、remove→`archive` 并补其 git 前像）+ 进度推进（群=room seq；**单聊=持久化待 review 缓冲，落点 scope 目录内、消费后删已消费部分、部分消费，不用消息表下标**）+ 初值=scope 起点 + 单次读入上限 + review 队列按 scope 合并/串行化（**scope 已被删除则丢弃该次 review**）+ 成本按 1+k 计入账本 + `MemoryConfig` 新增开关。

- [ ] 3.14 人设运行模式：`Persona.mode` 字段（默认 `bypass`）+ 建会话时用 `AgentRunConfig(mode=persona.mode)` + roster CRUD 持久化 + 设置对话框字段。
- [ ] 3.15 房间应答模式：`Room.reply_mode` 字段（默认 `admin`）+ 编排器 `openingSpeakers` 的 `everyone` 分支 + 房间设置对话框字段。

## 4. 文档

- [x] 4.1 更新 `docs/architecture.md`，增补多 agent 群聊编排小节。
- [x] 4.2 检查并更新 `docs/interview-script/` 中相关讲稿（建议性）。

## 5. 验证

- [x] 5.1 运行群聊/Web/记忆相关测试。
- [x] 5.2 运行全量 `uv run pytest -q`。
- [x] 5.3 手动启动 Web，验证单聊 + 群聊 + `@` 点名 golden path 与边缘场景。
- [x] 5.4 运行 OpenSpec strict validate。
- [x] 5.5 运行项目 artifact checker。
- [x] 5.6 跑通至少一个 benchmark smoke（本 change 触碰 AgentLoop / 记忆 / Web session 路径）。
- [x] 5.7 运行 Web session/server 测试；必要时运行浏览器 smoke。
- [ ] 5.8 (post-merge) 给 issue #302 加完成说明 comment 并关闭。
