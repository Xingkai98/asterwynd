## 1. 规格

- [ ] 1.1 修改 `multi-agent-collaboration` 规格：长期人设、单聊/群聊会话分离、房间日志、轮次编排与终止、`@` 边界、跨人设共享面声明。
- [ ] 1.2 修改 `long-term-memory` 规格：`Scope 隔离` 增 persona 维（MODIFIED，匹配既有 Requirement 名）。
- [ ] 1.3 修改 `web-ui` 规格：群聊 pane、多 agent 按来源区分、单聊/群聊共存、内部会话不出现在会话列表。
- [ ] 1.4 同步对应 current spec 到 `openspec/specs/<capability>/spec.md`（含 `long-term-memory`）。
- [ ] 1.5 开发前使用 `grilling` 审视 `design.md`，逐项确认实现细节、依赖、风险、测试策略和文档影响，并跑设计阶段对抗闭环（`reviews/grill-design.md` + `reviews/grill-adversarial.md`）。
- [ ] 1.6 在停轮确认里逐项拍板 `design.md` 的 Open Questions，并把答复记录进 `grill-design.md` 的 `## User Confirmation`。

## 2. 测试

- [ ] 2.1 人设/房间 CRUD 与持久化单测（含人设指令跨重启恢复）。
- [ ] 2.2 群聊编排单测：轮次顺序、**轮次终止条件**（用户再发言才开新一轮 / 触上限静默停止）、`@` 接力边界（不在列表 / 多人 / 自己 / 句中）、静默、每轮每成员上限、成员中途变更。
- [ ] 2.3 单聊/群聊内容互不泄漏的负向断言。
- [ ] 2.4 记忆：人设间隔离 + 同人设单聊/群聊共享 + **同一人设并发写记忆**。
- [ ] 2.5 共享面：workflow 资产库跨人设可见性（按「共享面」声明断言，防未声明泄漏）。
- [ ] 2.6 Web：群聊 pane + 房间 WS + hub 过滤内部会话 + `DELETE` 拒删内部会话。
- [ ] 2.7 多人设并发 run 与既有 `run_lock` / 并发语义不冲突。

## 3. 实现

- [ ] 3.1 新增人设（roster）模型与持久化（稳定 id、名称、角色、指令、模型绑定）。
- [ ] 3.2 会话标识与 hub 可见性：`SessionSnapshot` 增 `kind`；稳定映射 persona↔单聊会话、(persona, room)↔群内会话；`GET /api/sessions` 过滤 + `DELETE` 拒删。
- [ ] 3.3 会话分离：为每个人设建立单聊会话与 (persona, room) 群内会话。
- [ ] 3.4 房间日志：有序条目（seq / speaker / kind / text / 时间戳）+ 持久化 + 本轮切片注入。
- [ ] 3.5 会话式群聊编排器（新模块）：轮次、`@` 接力、静默（`[PASS]` 哨兵）、每轮每成员上限、轮次终止。
- [ ] 3.6 编排器分层：定义并注入 `SessionRunner` 抽象（`run(session_id, message) -> final_text`），编排器不 import `web`。
- [ ] 3.7 记忆：人设会话注入 `persistent_memory`；`PersistentMemory` 加 persona 维；同一人设共享同一实例。
- [ ] 3.8 群聊会话 pending 交互降级：撤 ask 类工具；审批类 fail-closed 立即判定，不阻塞轮次。
- [ ] 3.9 Web：群聊 pane + 房间级 WS（扩展写死的 `/ws/${sessionId}` 路由）。

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
