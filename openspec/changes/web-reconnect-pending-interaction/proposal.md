# Proposal: 移动端切后台重连后恢复 pending 的提问/审批卡片

关联跟踪 issue：[#195](https://github.com/Xingkai98/asterwynd/issues/195)，标题以【feature】开头。

## Change Type

- primary: feature
- secondary:
  - web-ui
  - agent-runtime

## Why

移动端（手机/平板）访问 Web UI 时，用户切后台/锁屏会让 WebSocket 断开。重连后前端会自动恢复消息历史（`session_history`）与 workflow 流程图快照，但**运行中等待用户响应的「提问/审批」卡片不会恢复**。

现状链路（`web/session.py`）：

1. 模型调用 `AskUserQuestionTool` 或触发需审批工具 → `WebQuestionHandler.ask_question` / `WebApprovalHandler.request_approval` 建立 `_pending` 状态，发 `user_question` / `approval_request` 事件等用户响应。
2. 用户切后台、ws 断开 → `receive_approval_responses` 的 except 分支执行 `fail_pending("websocket disconnected")`，把 pending 的提问/审批**判定为失败**（`WebQuestionHandler` 返回 `[Error: websocket disconnected]`）。
3. 同时 drain 循环里 `ws_send` 抛异常（issue #193 引入的 `break`）→ `finally` 执行 `fail_pending("session run ended")` 并 `agent_task.cancel()`——**整个 run 被取消**。
4. 用户切回来重连 → 只收到 `session_history` 与 workflow 快照，**没有「有一个提问/审批在等你」的恢复**。

结果：切后台期间错过的提问/审批，回来后看不到也答不了，run 已带着失败答案继续（或直接被取消）。

这不是个别协议细节，而是把「等待人类响应」这种**本该是 session 级状态**的东西绑在了单条 WebSocket 连接上。WebSocket 本身不提供投递保证，事件发生时 emit 一次、连接不在就永久丢失。

## What Changes

- **pending 跨连接存活**：`WebQuestionHandler` / `WebApprovalHandler` 建立 pending 时保留完整可重放载荷；WebSocket 断开 SHALL NOT 让 pending 失败。
- **run 事件出口 session 化**：新增 session 级、可重新绑定的 run 事件出口，断连只解绑出口、不终止 run；重连重新绑定后事件继续送达。
- **重连补发**：`GET /ws/<session_id>` 命中同一内存 session 时，在 `session_resumed` 与 `session_history` 之后补发仍 pending 的 `user_question` / `approval_request` 卡片。
- **放弃语义**：审批从「无限等待」改为有显式超时（缺省 **600 秒**总等待时长、可配置，fail-closed）；`reset`/`cancel`/run 真正结束仍立即失败 pending。
- **前端卡片幂等**：按 `question_id` / `approval_id` 幂等渲染；`session_history` 重绘时清理卡片注册表并重置 `currentAssistantMsg`（修僵尸 DOM）；ws 未就绪时提交给出可见反馈而不是静默丢弃。

## Capabilities

### New Capabilities

无新能力域；在既有 `web-ui` 能力域上深化。

### Modified Capabilities

- `web-ui`: 从「审批/提问只在事件发生时推送一次」演进为「pending 交互是 session 级状态，断线重连后补发并且仍可作答」。
- `agent-runtime`: Web session 的 run 事件出口从「绑死单条 ws」演进为「session 级、可重新绑定」，断连不再终止 run。

## Reference Implementation Research

- status: enabled
- research_tier: full
- reason: 涉及 WebSocket 事件协议、session 级 pending 生命周期、run 执行与连接解耦三层联动，走 grill 的非平凡 change，命中 `full` 判据。
- research questions:
  1. 等待人类响应的 pending 请求，业界如何建模、持久化与路由（按什么 key）？
  2. 客户端重连/换设备后怎么拿到「还没答」的请求？为什么「事件发生时 emit 一次」必然丢？
  3. 移动端浏览器切后台时 WebSocket 的真实行为，以及业界如何应对（心跳、重连退避、生命周期事件）？
  4. 「多久不响应算放弃」以及多客户端并发时谁有资格作答？
  5. 前端「先整体重绘快照、再叠加仍然有效的交互态」的排序约束与幂等模式？
- findings: 4 视角并行调研 + 逐条对抗式核验（79 条 finding / 77 条成立），完整结论与来源见 design.md 的「Reference Implementation Research」章节。要点：
  1. 推送通道默认不保证投递、服务端不为断线客户端缓冲，「事件发生时 emit 一次」在协议层就注定丢（Socket.IO delivery-guarantees 官方文档、WHATWG SSE 只规范客户端 `Last-Event-ID`）。
  2. 等待人类响应的 pending 必须是服务端权威状态、UI 事件只是可重放的投影（Ably AI Transport、LangGraph durable checkpointer、Temporal；反面证据 openhuman PR #6212 记录了同一 bug 的根因）。
  3. 重连的正确做法是服务端主动重放仍 pending 的请求，而不是等下一次事件（openhuman #6212、hermes-agent #86596、DeepSeek Harness 排障文档）。
  4. 重放幂等性来自「稳定 request id 作 key」+「已决策的请求不再处于 pending 集合」。
  5. 补发必须应用在历史快照**之上**；「清空本地 pending」要绑定连接断开而非重连 resync（DeepSeek Discussion #3102 的竞态复现）。
  6. 多连接应广播给同一 session 的所有连接、首个作答原子胜出、终态广播回去让其余卡片失效（Ably、Microsoft agent-host-protocol；WICKET-6761 的反面教训是注册表只留最新一条连接）。
  7. 超时两派并存（无限等待 vs 应用层显式 TTL），共同底线是**超时 fail-closed、绝不放行不可逆操作**。
  8. 终态单向推进，陈旧重放不得把已完成拉回 pending；「卡片缺失不等于同意」，绝不能用合成审批解开 agent。
  9. 移动端切后台的 ws 断开应按「必然发生」设计，且断开信号本身不可信（MDN visibilitychange、WebKit Bug 308073）。
- design impact: 见 design.md 的 D1–D8；调研对本 change 的关键影响为 D2（断开不失败 pending、超时 fail-closed）、D4（补发排在 `session_history` 之后）、D5（按稳定 id 幂等渲染）、D7（多连接广播 + 先答者胜）。

## Impact Analysis

| 影响面 | 说明 |
|--------|------|
| `web/session.py` | `WebApprovalHandler` / `WebQuestionHandler` 保留 pending 载荷、新增超时；新增 session 级 run 事件出口；`_run_session_locked` 的 drain 循环与 `receive_approval_responses` 不再因断连失败 pending / 取消 run；新增待补发载荷构造纯函数。 |
| `web/server.py` | 新增 `bind_pending_interaction_channel`，在 `session_history` 之后补发 pending 卡片。 |
| `web/static/chat.js` | `renderApprovalRequest` / `renderQuestionCard` 幂等；`renderHistory` 清理卡片注册表；ws 未就绪时提交给出可见反馈。 |
| `agent/config.py` | `WebConfig` 新增 pending 可恢复窗口/超时配置项（缺省值见 design.md）。 |
| 测试 | 新增 `tests/web_tests/` 重连补发测试（套 `test_reconnect_resends_running_snapshot` 骨架），更新 issue #193 回归测试语义。 |
| 兼容性 | 事件形状 `{"type": ..., "data": {...}}` 与 `session_id` 归属约定不变；不触及 AgentLoop 主循环协议与 tool-call 消息链。**行为变更**：审批从「无超时」变为「缺省 600 秒超时」，语义是**总等待时长**（从 pending 建立时起算，连接断开与保持都不影响计时，不会因断连重置而延长）——今天挂着卡片 10 分钟以上回来点批准仍生效的桌面用户，改后会得到 `unavailable`；提问超时同步从硬编码 300 秒抽为可配置项（缺省值不变）。两项均由用户确认（grill Q1），已在 README / README_EN / docs/architecture.md 同步。 |
| 安全 | 审批是「同意」的唯一来源，补发的卡片 SHALL NOT 被解释为已批准；已答请求 SHALL NOT 被重放成可再次执行；超时一律 fail-closed，绝不放行不可逆操作。 |
