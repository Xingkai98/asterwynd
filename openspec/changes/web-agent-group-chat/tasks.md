## 1. 规格

- [ ] 1.1 修改 `multi-agent-collaboration` 规格：长期人设与两级主持角色（roster `mainBotIds` + 房间 `admin`）、单聊/群聊会话分离、房间日志 schema、轮次编排与 slot 序列、`@` 解析口径、房间级互斥与轮次终止四出口、跨人设共享面声明；并以 MODIFIED 澄清既有「SHALL NOT introduce a separate control plane」只约束 subagent orchestration。
- [ ] 1.2 修改 `long-term-memory` 规格：`Scope 隔离` 增 persona 维（MODIFIED，匹配既有 Requirement 名，保留原 Scenario）。
- [ ] 1.3 修改 `web-ui` 规格：群聊视图 + 房间级 WS、多 agent 按来源区分、人设/房间管理入口与单聊入口、内部会话列表过滤与生命周期保护（含 WS `reset`）、内部会话 pending 降级；后两项以 MODIFIED 收窄既有「审批必须暴露」与「pending 跨连接存活」两条 Requirement。
- [ ] 1.4 同步对应 current spec 到 `openspec/specs/<capability>/spec.md`（含 `long-term-memory`）。
- [ ] 1.5 开发前使用 `grilling` 审视 `design.md`，逐项确认实现细节、依赖、风险、测试策略和文档影响，并跑设计阶段对抗闭环（`reviews/grill-design.md` + `reviews/grill-adversarial.md`）。
- [ ] 1.6 在停轮确认里逐项拍板 `design.md` 的 Open Questions，并把答复记录进 `grill-design.md` 的 `## User Confirmation`；答复后清理 `design.md` Non-Goals 与 Open Question 的口径冲突。

## 2. 测试

- [ ] 2.1 人设/房间 CRUD 与持久化单测（跨重启、跨 workspace；人设指令恢复）；删除级联（单聊会话 + 群内会话 + 房间日志 + persona 记忆）。
- [ ] 2.2 群聊编排单测：slot 序列、`@` 解析（用户行首 / 成员句中 / 不在列表 / 多人 / 自己）、静默（含**游标随静默回合推进、不重复注入**）、每轮每成员上限、**轮次终止四出口**（走完 / 达上限 / 失败 / 超时）、**房间级互斥**（并发不并行开两轮、用户消息排队进本轮）、成员中途变更。
- [ ] 2.3 会话分离：单聊/群聊内容互不泄漏的负向断言。
- [ ] 2.4 `SessionRunner` 契约：四态映射；`text` 只来自本次 run（**同 session 并发被拒时不复用陈旧文本**）。
- [ ] 2.5 记忆：人设间隔离 + 同人设单聊/群聊共享同一实例 + **并发写**；接线完整性（LLM 去重判官存在、`memory_config` 生效）；注入块标题为 `## Persona Memory`。
- [ ] 2.6 共享面：workflow 资产库跨人设可见性（按「共享面」声明断言，防未声明泄漏）。
- [ ] 2.7 Web：群聊 pane + 房间级 WS + hub 过滤内部会话（含**损坏快照**经 id 前缀/roster 判定）+ `DELETE` 拒删 + **WS `reset` 拒改内部会话**。
- [ ] 2.8 多人设并发 run 与既有 `run_lock` / 并发语义不冲突。

## 3. 实现

- [ ] 3.1 人设（roster）模型与持久化（workspace 级）：稳定 id、名称、角色、指令、模型绑定；`mainBotIds`（可多个）。
- [ ] 3.2 房间模型与持久化（workspace 级）：成员、`admin`（单个、可空）、notice、模式；room 记录含 `(persona, room) → 群内会话 id` 映射。
- [ ] 3.3 会话标识与生命周期保护：`SessionSnapshot` 增 `kind`；内部会话 id 前缀约定；hub 过滤（`GET /api/sessions`）+ `DELETE` 拒删 + WS `reset` 拒绝（或复用原 id 并回写 roster）。
- [ ] 3.4 会话分离：为每个人设建立单聊会话与 (persona, room) 群内会话。
- [ ] 3.5 房间日志：schema（seq / speaker / kind / text / ts）+ 持久化 + 游标（回合推进）+ 有界分层切片（首见 / 增量 / 往轮）。
- [ ] 3.6 会话式群聊编排器（新模块）：slot 序列算法、`@` 解析、静默（`[PASS]`）、每轮每成员上限、轮次终止四出口、**房间级互斥**。
- [ ] 3.7 编排器分层：定义并注入 `SessionRunner`（`run(session_id, message) -> TurnOutcome` 四态；web 层从本次 run 事件流取最终文本），编排器不 import `web`。
- [ ] 3.8 记忆：人设会话注入 `persistent_memory` + `memory_config` + `llm`（+ 视需要 `quality_config`）；`PersistentMemory` 加 persona 维（同级布局）；同一人设共享同一实例；注入块标题 `## Persona Memory`。
- [ ] 3.9 群聊会话 pending 降级：撤 ask 类工具；审批类 fail-closed 立即判定。
- [ ] 3.10 Web：群聊 pane + 房间级 WS（扩展写死的 `/ws/${sessionId}`）；人设/房间管理入口 + 单聊入口 + 删除级联。

## 4. 文档

- [ ] 4.1 更新 `docs/architecture.md`，增补多 agent 群聊编排小节。
- [ ] 4.2 检查并更新 `docs/interview-script/` 中相关讲稿（建议性）。

## 5. 验证

- [ ] 5.1 运行群聊/Web/记忆相关测试。
- [ ] 5.2 运行全量 `uv run pytest -q`。
- [ ] 5.3 手动启动 Web，验证单聊 + 群聊 + `@` 点名 golden path 与边缘场景。
- [ ] 5.4 运行 OpenSpec strict validate。
- [ ] 5.5 运行项目 artifact checker。
- [ ] 5.6 跑通至少一个 benchmark smoke（本 change 触碰 AgentLoop / 记忆 / Web session 路径）。
- [ ] 5.7 运行 Web session/server 测试；必要时运行浏览器 smoke。
- [ ] 5.8 (post-merge) 给 issue #302 加完成说明 comment 并关闭。
