## 1. 规格

- [ ] 1.1 修改 `multi-agent-collaboration` 规格，定义长期 agent 人设、单聊/群聊会话分离、会话式群聊轮次编排、人设级长期记忆。
- [ ] 1.2 修改 `web-ui` 规格，定义群聊视图与多 agent 消息按来源区分。
- [ ] 1.3 同步对应 current spec 到 `openspec/specs/<capability>/spec.md`。
- [ ] 1.4 开发前使用 `grilling` 审视 `design.md`，逐项确认实现细节、依赖、风险、测试策略和文档影响，并跑设计阶段对抗闭环（`reviews/grill-design.md` + `reviews/grill-adversarial.md`）。
- [ ] 1.5 在停轮确认里逐项拍板 `design.md` 的 Open Questions，并把答复记录进 `grill-design.md` 的 `## User Confirmation`。

## 2. 测试

- [ ] 2.1 人设/房间 CRUD 与持久化单测（含重启后恢复）。
- [ ] 2.2 群聊编排单测：轮次顺序、`@` 点名、静默、每轮/每成员上限、成员中途变更。
- [ ] 2.3 单聊/群聊内容互不泄漏的负向断言。
- [ ] 2.4 人设级记忆作用域：人设间隔离 + 同人设单聊/群聊共享。
- [ ] 2.5 Web 端点 + WS 事件 + 视图渲染（多 agent 按来源区分）测试。
- [ ] 2.6 多人设并发 run 与既有并发语义不冲突的测试。

## 3. 实现

- [ ] 3.1 新增人设（roster）模型与持久化。
- [ ] 3.2 会话分离：为每个人设建立单聊会话与 (persona, room) 群内会话。
- [ ] 3.3 新增会话式群聊编排器（轮次、`@` 接力、静默、上限）。
- [ ] 3.4 记忆作用域扩展：项目 × persona。
- [ ] 3.5 Web：群聊端点 + 房间级 WS + 群聊视图（渲染 per-pane 化）。

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
