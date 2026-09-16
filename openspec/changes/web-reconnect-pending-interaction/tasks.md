# Tasks: 移动端切后台重连后恢复 pending 的提问/审批卡片

## 0. 设计追问（实现前门禁）

- [ ] 0.1 跑 `batch-grill`（独立零记忆 subagent 审视 design.md），产出 `reviews/grill-design.md`（≥3 Confirmed Decisions + Open Questions 停轮确认）。
- [ ] 0.2 停轮把 `## Open Questions` 逐条抛给用户（每条配具体场景例子），答复记录进 `## User Confirmation`；按 Q1 的答复定稿 D2/D6 的超时口径。

## 1. pending 载荷保留与超时（D1/D2/D6）

- [ ] 1.1 `WebQuestionHandler` 保留 `Question.to_event_data()` 载荷，`_pending` 结构扩展；新增**原子**访问器（一次返回 `(question_id, payload)` 快照，不做两次读取）；`question_id` 不变。
- [ ] 1.2 `WebApprovalHandler` 保留 `ApprovalRequest.to_event_data()` 载荷；新增原子访问器（一次返回 `(approval_id, payload)`）。
- [ ] 1.3 两个 handler 的等待按 Q1 定稿的口径实现超时（`asyncio.wait_for`），超时一律 fail-closed（`UNAVAILABLE` / `[Error: ... timed out ...]`）。
- [ ] 1.4 `WebConfig` 新增超时配置项（按 Q1 口径），`_parse_web_config` 补正整数校验（`_parse_positive_int`），`create_session` 传入 handler；加配置解析测试。
- [ ] 1.5 `reset` / `cancel` 仍立即 `fail_pending`（既有语义）；`fail_pending` 清理 `_pending` 时机与既有 `finally` 保持一致，避免 race。

## 2. run 事件出口 session 化（D3/D7/D8）

- [ ] 2.1 新增 session 级 run 事件出口（`ConnectionHandle{send, receive, detach}` + sender 集合），由 `AgentSession` 持有；run 事件经它广播，且提供定点发送能力。
- [ ] 2.2 `_run_session_locked` 的 drain 循环改为经出口广播；**drain 永不退出、永远消费 queue**（无界 queue 防内存堆积）；某连接 detach 后只对该连接丢弃，SHALL NOT break / SHALL NOT cancel `agent_task`。
- [ ] 2.3 **断连检测点唯一**：session 级接收任务 `await ws_receive()` 抛异常时对**该连接** `channel.detach(handle)`，不再 `fail_pending("websocket disconnected")`。（`websocket_endpoint` 在 `await run_session` 期间不会调用 `ws.receive_json`，不能依赖它检测断连。）
- [ ] 2.4 `finally` 的 `fail_pending("session run ended")` 仅在 run 真正结束时执行（保持），不因断连提前触发。
- [ ] 2.5 重连时把新连接绑到出口（`websocket_endpoint` 内），多条连接并存时广播；断连期间无观察者的事件允许丢弃。
- [ ] 2.6 `run_session` 的 `run_lock` 占用错误**只回发起连接**（定点发送），不走广播（否则别的 tab 会莫名出现错误消息）。
- [ ] 2.7 多连接仲裁：先答者胜、后提交者得 `unavailable`（沿用既有 `submit_*` 一次性语义）；终态广播的保证边界按 Q3 定稿（run 存活时天然广播，run 不在时是否扩展 inline 分支按 Q3 结论）。
- [ ] 2.8 `SessionManager.remove_session` 同步摘掉新出口（与 `graph_forwarder.detach()` 同处），避免 reset / hub DELETE 后旧 sender 仍被引用。

## 3. 重连补发 pending 卡片（D4）

- [ ] 3.1 `web/session.py` 新增待补发载荷构造纯函数（原子读取两个 handler 的当前 pending，返回 `{"type": ..., "data": {...session_id...}}` 列表；无 pending 返回空列表）。
- [ ] 3.2 `web/server.py` 新增 `bind_pending_interaction_channel(ws, session)`，顺序钉死为 `session_resumed → session_history → 补发卡片 → workflow 快照`。
- [ ] 3.3 补发容错：单条发送失败不影响后续事件与连接（对齐 `bind_workflow_graph_channel` 的尽力而为语义）。

## 4. 前端卡片幂等与反馈（D5）

- [ ] 4.1 `renderApprovalRequest` / `renderQuestionCard` 加同 id 去重守卫（复用已存在卡片，不产生第二张）。
- [ ] 4.2 两条清空路径都清卡片注册表：`renderHistory` **与** `command_result` 的 `/clear` 分支。
- [ ] 4.3 `session_history` 分支重置 `currentAssistantMsg = null`（否则后续 `assistant_delta` 写进僵尸 DOM，重连后流式内容不可见）。
- [ ] 4.4 `sendApprovalDecision` / `sendQuestionAnswer` 调整为**先判 `ws.readyState`、再改 UI**；未就绪时给出可见反馈并保留卡片可提交（不再静默 return / 假 Submitted）。
- [ ] 4.5 补发卡片在重连后能正确渲染（`handleTabEvent` 的 rekey 逻辑不受影响）。
- [ ] 4.6 `chat.js` 改动后 bump `web/static/index.html` 的 `/static/chat.js?v=21 → v=22`，同步更新 `tests/web_tests/test_server.py:438` 的断言。

## 5. 测试

- [ ] 5.1 单元测试：handler 载荷保留、原子访问器 `(id, payload)`、超时返回、`reset`/`cancel` 立即失败、配置正整数校验、补发纯函数（有/无 pending、字段与 `session_id`）。
- [ ] 5.2 服务端重连测试：造 pending → 断连 → 重连 → **断言事件类型序列** `["session_resumed","session_history",<卡片>]`；反例「无 pending 不补发」用 `ping`/`pong`。
- [ ] 5.3 断连不杀 run 测试：ws_send/receive 失败后 run 继续执行完毕、`run_lock` 正常释放；drain 在无连接时仍消费（防无界堆积）。
- [ ] 5.4 多连接测试：广播到两条连接、断开其一不影响另一条、先答者胜后提交者 `unavailable`；既有 `test_multi_tab_approval_isolation` 保持通过。
- [ ] 5.5 前端契约测试：优先 Playwright 行为断言——卡片幂等、重连后卡片重新出现且可提交、ws 未就绪提交有反馈、`session_history` 后 `currentAssistantMsg` 重置；chat.js 源码字符串断言只作补充。
- [ ] 5.6 更新 issue #193 回归测试 `test_run_session_survives_ws_send_failure_after_disconnect` 到新语义（run 不被取消）。
- [ ] 5.7 `reset` 在 run 期间的语义测试（reset 后 run 仍跑完、pending 已失败），固化 D8 的边界。

## 6. 收尾

- [ ] 6.1 `uv run pytest -q` 全绿。
- [ ] 6.2 benchmark smoke：`uv run asterwynd benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/smoke` 冒烟通过（proposal 声明了 `agent-runtime`，命中 artifact checker 的 benchmark smoke 门禁）。
- [ ] 6.3 OpenSpec strict validate（`npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`）通过。
- [ ] 6.4 项目 artifact checker（`PYTHONPATH=. python3 scripts/check_openspec_artifacts.py`）通过。
- [ ] 6.5 文档影响检查（点名，非泛查）：`README.md`（Web Chat 功能描述）、`README_EN.md`（README 改必须同步英文）、`docs/architecture.md`（Web 事件通道 / pending approval 段落）、`AGENTS.md`、`CONTEXT.md`；只更新本变更造成的事实变化。
- [ ] 6.6 若 Q1 采「总时长」语义，在 proposal 的 Impact Analysis 兼容性行补「审批超时为行为变更」的说明。
- [ ] 6.7 同步 current spec：把本 change 的 spec delta 合入 `openspec/specs/web-ui/spec.md`（并落 `current_spec_synced` 事件）。
- [ ] 6.8 归档收尾：change 归档到 `openspec/changes/archive/YYYY-MM-DD-web-reconnect-pending-interaction/`，从 `docs/openspec-change-backlog.md` 移除（落 `change_archived` / `backlog_updated` 事件）。
- [ ] 6.9 实现 PR 合入后给 issue #195 添加完成说明 comment 并关闭。
