# Design: 移动端切后台重连后恢复 pending 的提问/审批卡片

## Context

Web UI 的一条 WebSocket 连接同时承担三件事：接收用户消息、把 AgentLoop 的事件推给浏览器、接收用户对提问/审批的响应。当前实现把第三件事的**等待状态**绑死在这条连接上：

- `WebQuestionHandler._pending` / `WebApprovalHandler._pending`（`web/session.py:106`、`:168`）是单槽位的 `(id, Future)`，只存 id 和 future，不保留可重放的载荷。
- 断连时 `receive_approval_responses` 的 `except Exception` 分支执行 `fail_pending("websocket disconnected")`（`web/session.py:883-884`），把 pending 判定为失败。
- drain 循环里 `ws_send` 抛异常时 `break`（`web/session.py:896-902`，issue #193 引入），`finally` 再执行 `fail_pending("session run ended")` 并 `agent_task.cancel()`（`:904-917`）——**断连即杀 run**。
- 前端重连时 `session_history` → `renderHistory` 会 `messagesEl.textContent = ''` 清空整个消息区（`web/static/chat.js:623-631`），卡片 DOM 全丢；`approvalCards` / `questionCards` 里留下指向已移除 DOM 的僵尸条目，且渲染函数没有去重守卫（`:815`、`:906`）。

已有的正确范式在同仓库内：workflow 图事件出口 `GraphEventForwarder`（`web/session.py:233-386`）是 **session 级、跨 run 存活**的，`rebind()` 让重连把新的 `ws_send` 接上同一个 forwarder，重连时 `bind_workflow_graph_channel`（`web/server.py:35-59`）**先补发当前快照再 rebind**。本 change 把 pending 交互与 run 事件出口按同样的思路 session 化。

约束：

- 单 session 单槽位 pending（spec `openspec/specs/web-ui/spec.md:267`：每个 Web session 同一时刻 SHALL 只有一个 pending approval）。
- 提问已有 5 分钟自身超时（`web/session.py:189` 的 `asyncio.wait_for(..., timeout=300.0)`）；审批目前**没有超时**。
- 同一 session 可能被多个 tab / 多条 ws 连接打开（issue #117 多标签会话）。
- `run_session` 用 `session.run_lock` 做 per-session 互斥（`web/session.py:741-753`）。

## Goals / Non-Goals

### Goals

- WebSocket 断开不再让 pending 提问/审批失败，也不再终止正在执行的 run。
- 重连同一 session 后，服务端补发仍然 pending 的 `user_question` / `approval_request` 卡片，用户能作答。
- pending 审批获得显式超时（可恢复窗口），避免「永不放弃」地无限等待。
- 前端幂等渲染卡片，重连重绘后不重复、不留僵尸条目；ws 未就绪时提交有可见反馈。

### Non-Goals

- 不改 AgentLoop 主循环协议、tool-call 消息链与 `max_iterations` 路径。
- 不做跨进程/跨重启的 pending 持久化（进程重启后 run 本身已不存在，pending 无宿主）。
- 不做「断连期间无人接收的事件缓存重放」——该期间的普通事件由 `session_history` 兜底，不逐条补发。
- 不改多 tab 的会话归属模型（沿用现有 per-tab ws + per-session run_lock）。
- 不改 workflow 图事件通道（已正确，保持不动）。

## Decisions

### D1: pending 载荷保留与可重放性

两个 handler 的 `_pending` 从 `(id, future)` 扩展为保留完整事件载荷：

- `WebQuestionHandler` 存 `Question.to_event_data()` 的结果（`question_id`/`title`/`body`/`options`）。
- `WebApprovalHandler` 存 `ApprovalRequest.to_event_data()` 的结果（含 `tool_name`/`risk`/`capability`/`mode`/`origin`/`reason`/`redacted_args`/`args_summary`，已脱敏）。

新增只读访问器（例如 `pending_question_payload()` / `pending_approval_payload()`）。**不新增第二个 pending 槽位**，维持「同一时刻最多一个」的既有 spec 语义。

载荷以「建立时快照」的形式保留——`ApprovalRequest.redacted_args` 已经是脱敏后的参数（`agent/approval.py:132`），直接复用不会泄露原始敏感值。

### D2: 断连不失败 pending，改由显式窗口放弃

`receive_approval_responses` 的 `except` 分支不再调用 `fail_pending("websocket disconnected")`。断开只意味着「本连接的接收端没了」，不意味着用户放弃。

放弃由**显式超时**驱动。**超时的具体口径由 grill Q1 停轮确认后定稿**（见下），三种候选：

- **(a) 总等待时长**：审批新增 `asyncio.wait_for(future, timeout=approval_timeout_seconds)`（缺省 300s，与提问对齐），计时从 pending 建立时开始，连接存亡不影响计时。提问保留既有 5 分钟 `wait_for` 并抽成 `WebConfig.question_timeout_seconds`。
- **(b) 断连宽限窗口**：连续连通时无限等待；仅在断连后启动一个宽限计时，超时才失败。
- **(c) 审批继续无限等待**：只对提问保留超时，审批零回归（但保留「无人重连则 run 永久挂住」的风险）。

无论选哪种，`reset` / `cancel` / run 真正结束仍立即 `fail_pending`（既有语义不变），且超时一律 **fail-closed**（判定 `unavailable`，绝不放行不可逆操作）——这是调研 finding 7/8 的共同底线。

**为什么倾向给审批加超时而不是让它无限等**：审批当前无超时，一旦断连后无人重连，`await future` 会让 run 永久挂住，占用 `run_lock` 且用户无从察觉。业界（Ably）默认不施加超时并建议应用层自行清理 stale pending；Temporal / agent-governance-toolkit 等默认 300s。**但**注意这与 issue #195 原文「或改为『断开后留一段可恢复窗口』」的措辞可能错位，且「总等待时长」对今天「挂着卡片 10 分钟回来点批准」的桌面用户是行为回归——这是必须由用户拍板的点（grill Q1）。若最终维持「总时长」语义，Risks 必须显式标注该行为变更，并在 proposal 的 Impact Analysis 兼容性行补一句。

### D3: run 事件出口 session 化（`SessionEventChannel`）

新增 session 级事件出口，把「连接」建模为显式对象（`ConnectionHandle{send, receive, detach}`）而不是裸 callable——M2 的 per-connection detach 与 D7 的定向补发都依赖「能定位到具体连接」。

- `attach(handle)` 把一条连接加入 sender 集合；`detach(handle)` 只移除该连接，其余连接不受影响。
- drain 循环从「捕获的 `ws_send`」改为「向出口的 sender 集合广播」；某条连接已 detach 时**只对该连接丢弃、不 break、不 cancel run**。
- **断连检测点唯一**（必须写明，否则实现会写成「sender 集合永不清空」）：`websocket_endpoint` 在 `await run_session(...)` 期间**不会**调用 `ws.receive_json()`（`web/server.py:411`），FastAPI 不会抛 `WebSocketDisconnect`。唯一可靠的断连信号来自 session 级接收循环——`await ws_receive()` 抛异常时，对该连接执行 `channel.detach(handle)`，由该连接自己带来的接收任务退出（不再是 `fail_pending("websocket disconnected")`）。
- **drain 循环永不退出、永远消费 `queue`**：`queue` 是无界 `asyncio.Queue`（`web/session.py:764`）。若实现成「出口没有绑定连接就不 drain」，断连期间事件会无界堆积到内存。正确做法是 drain 一直消费到 sentinel，拿到事件后广播给当前 sender 集合（集合为空则丢弃该事件）。
- `receive_approval_responses` 的逻辑移出 `_run_session_locked` 的函数局部，改为与连接绑定的接收任务：消费 `ws_receive()` 并把 `approval_response` / `user_answer` 投给对应 handler；连接断开时干净退出、**不失败 pending**。

`GraphEventForwarder` 已经证明了这个模式的可行性（跨 run 存活 + rebind），但它的 sink 语义是「同步、绝不抛、失败即丢 + 按 workflow 分桶合并」，与 run 事件出口需要「顺序投递、失败感知」不同——因此**新写一个出口对象**而不是复用 `GraphEventForwarder`（避免把 forwarder 的合并/分桶逻辑硬塞进 run 事件路径）。

**run_session 早期返回的投递语义（M3）**：`run_session` 在 `run_lock` 被占用时（`web/session.py:741-746`）要回一条 "another run is already in progress" 错误。这条错误**必须只回发起连接**（per-call `reply_send`），不能走广播——否则 `handleTabEvent`（`chat.js:404-423`）会把它插进别的 tab 的 DOM，用户看到莫名其妙的错误。因此出口同时提供「广播」（run 事件）与「定点发送」（对发起连接的即时错误应答）两种能力。

**run 与连接的解耦边界**：run 的生命周期由 AgentLoop 决定（正常结束 / 异常 / 用户 cancel），不再由 WebSocket 连接决定。断连期间 run 继续跑完，重连后用 `session_history` 补历史。

### D4: 重连补发时机与顺序

在 `web/server.py` 的 `websocket_endpoint` 里新增 `bind_pending_interaction_channel(ws, session)`，**顺序钉死为**：

```
session_resumed → session_history → pending 卡片补发 → workflow 快照补发
```

理由：`session_history` 会触发前端 `renderHistory` 整体清空消息区；补发若排在它之前会被清掉。钉死这个顺序（而不是「先后皆可」）是为了让服务端测试能做**事件类型序列断言**——这也是调研 finding 5 的竞态教训唯一可机械固化的形式。

补发内容来自 D1 的载荷访问器：pending 提问发 `user_question`，pending 审批发 `approval_request`，载荷里补 `session_id`（提问的 `to_event_data()` 原本不含 `session_id`）。没有 pending 时不发任何事件。

**载荷读取必须原子（M7）**：D1 的访问器不能在「读 id」和「读载荷」之间分两次取——`_pending` 在 resolve 的 `finally` 里被清（`web/session.py:126-127`、`:196-197`），两次读取之间会读到「有 id 无载荷」。访问器签名固定为「一次性返回 `(id, payload)` 快照」，纯函数按这个签名实现。

若补发期间该 pending 被作答/超时，前端拿到卡片后提交会得到 `unavailable`——这与既有的「答到已结束的 pending」路径一致（`web/server.py:545`），不额外引入新状态。

### D5: 前端卡片幂等、注册表清理与可见反馈

- `renderApprovalRequest` / `renderQuestionCard` 开头加 `if (approvalCards.has(id)) return;` / `if (questionCards.has(id)) return;`——同一 id 重复事件复用已存在的卡片，不产生第二张。
- **清空消息区的两条路径都要清卡片注册表（M6）**：`renderHistory`（`chat.js:623-631`）与 `command_result` 的 `/clear` 分支（`chat.js:471-473`）都执行 `messagesEl.textContent = ''`，两处都要同步 `approvalCards.clear()` / `questionCards.clear()`，否则留下指向已移除 DOM 的僵尸条目。
- **`session_history` 分支要重置 `currentAssistantMsg = null`（M12）**：`renderHistory` 清空 DOM 但不重置 `currentAssistantMsg`，随后到达的 `assistant_delta` 会 `appendAssistantContent(currentAssistantMsg, ...)` 写进**已脱离文档的僵尸节点**（`chat.js:503-513`），用户重连后完全看不到流式增量。这是比重连后「流式过程不可回放」更严重的可见缺陷，必须在 `session_history` 分支修掉。
- **ws 未就绪时的反馈要「先判连接、再改 UI」（M5）**：当前 `chat.js:980-982` 先把按钮置为 `Submitted` 再调用 `sendQuestionAnswer`，后者在 ws 非 OPEN 时静默 return——用户看到假的「已提交」。审批侧 `chat.js:885-889` 同理。正确顺序是**先检查 `ws.readyState`，未就绪则给出可见提示并保持卡片可提交，就绪才置 UI 状态并发消息**。

去重的 key 用 `approval_id` / `question_id`（服务端生成的 uuid，天然稳定），与业界「按稳定 request_id 建立卡片、已决请求自然不重放」一致。

### D6: 配置项

`WebConfig`（`agent/config.py:351`）新增（**具体项取决于 D2 的 Q1 口径选择**）：

| 配置项 | 缺省 | 含义 |
|--------|------|------|
| `question_timeout_seconds` | `300` | 提问等待用户作答的上限（原为硬编码 300） |
| `approval_timeout_seconds` | `300` | 审批等待用户决定的上限（原为无超时；若 Q1 选 (c) 则此项不存在） |

若采用「总等待时长」语义：连接断开与保持对计时没有影响（计时从 pending 建立时开始），语义更简单、也避免「断连重置计时」导致的无限延长。

**必须做正整数校验（M15）**：`_parse_web_config`（`agent/config.py:1294`）目前只解析 `workspaces`；新配置项配 0 或负值会退化成「立即超时」。需按既有 `_parse_positive_int`（用法见 `agent/config.py:526-530`）补校验，并加配置测试。

### D7: 多连接（同 session 多 tab / 多设备）

run 事件出口从「单订阅者、最后连接胜出」改为**多订阅者广播**：出口持有一个 sender 集合，run 事件与补发的卡片投给该 session 的所有已绑定连接；连接断开只把自己从集合移除。

理由：现有 `GraphEventForwarder.rebind` 是最后连接胜出，若 run 出口沿用该语义，**第二个 tab 连上会抢走第一个 tab 的事件流**，比现状（每个 run 有自己的 per-run queue）更差。调研 finding 6 的业界做法也是广播 + 首答胜出；WICKET-6761 记录的正是「注册表只留最新连接」导致的反面教训。

作答仲裁沿用既有的一次性语义：`submit_response` / `submit_answer` 对已 done 的 future 返回 `False`，后提交者得到 `unavailable`（**先答者胜**），不新增仲裁状态。

**终态广播的保证边界（M4/Q3）**：现状有两条作答路径——run 存活时走 `web/session.py:842-867` 的 run 内接收循环（终态 `approval_response` 由 `agent/loop.py` 发进事件流，天然能广播）；run 不在时走 `web/server.py:533-564` 的 inline 分支，它只 `ws.send_json` 回**提交者**。因此「作答成功后所有连接都收到终态」**只在 run 存活时天然成立**。二选一（grill Q3）：让 inline 分支也经 channel 广播，或在 design + spec delta 收窄保证为「run 存活时保证广播，run 不在时不保证其他连接收到终态」。**倾向后者**（改动小、且 run 不在时的陈旧卡片本就是次要场景），但需用户确认。

`GraphEventForwarder` 本 change **不动**（保持单订阅者 rebind）——它是 workflow 图的既有设计，改动它超出本 issue 范围；若后续要统一，另立 change。

### D8: 会话级资源的统一清理与 reset 语义

新 channel 必须随 session 一起被清理：`SessionManager.remove_session`（`web/session.py:697-703`）目前只 `graph_forwarder.detach()`，新增的 run 事件出口要在同一处摘掉，否则 `reset` / hub DELETE 之后旧 ws sender 仍被 session 引用（M11）。

`reset` 在 run 期间的语义窗口需要显式对待：run 期间消息由 session 级接收任务消费，`reset` 只做 `fail_pending`（`web/session.py:869-876`），**不做会话替换**（替换在 endpoint 分支 `web/server.py:566-584`，run 期间不执行）。新语义下用户点 reset 后 run 仍会跑到结束、且 pending 已失败——这条路径要有测试固化，避免实现者误以为 reset 会终止 run。

### D9: 与 issue #193 的关系

issue #193 的修复（`ws_send` 失败时 `break` 而不是让异常逃逸）解决的是「run 悬空」；本 change 把同一处逻辑推进为「断连不终止 run」。issue #193 的回归测试 `test_run_session_survives_ws_send_failure_after_disconnect`（`tests/web_tests/test_session.py:605-636`）断言「run 正常返回、锁已释放」，这条断言在新语义下**依然成立且必须保留**——只是「正常返回」的原因从「断连即收尾」变为「run 自己跑完」。测试本身需要按新语义更新（例如同时断言 ws_send 失败后 run 仍继续执行、重连后能收到后续事件）。

## Pre-Implementation Review

开发前已完成独立零记忆 subagent 的设计追问（`/grill`，产出 `reviews/grill-design.md`，run `grill-web-reconnect-pending-interaction-2026-09-16`），并停轮逐项获得用户确认（记录于该文件 `## User Confirmation` 节）。

- 已确认（grill Confirmed Decisions）：pending 载荷保留与重放且不新增第二槽位；run 事件出口新写对象不复用 `GraphEventForwarder`；补发排在 `session_history` 之后；按稳定 uuid 幂等去重 + 清空注册表；多连接广播而非最后连接胜出；保留 issue #193 测试断言。
- 必须修改项（已整合进 D2/D3/D4/D5/D6/D8 与 Risks）：断连检测点唯一（session 级 receiver）+ drain 循环永不退出；`run_session` 早期返回走定点发送；终态广播的保证边界；`session_history` 重置 `currentAssistantMsg`；ws 未就绪「先判连接再改 UI」；补发载荷原子读取；`remove_session` 统一清理；配置正整数校验；`tasks.md` 补 benchmark smoke。
- 待用户拍板（grill Open Questions，见 `grill-design.md`）：Q1 审批超时口径、Q2 断连期间 in-flight 流式文本是否补发、Q3 多 tab 卡片失效的保证边界、Q4 断连后 run 是否继续跑完。
- 剩余风险见下节。

## Risks / Trade-offs

- **断连期间流式输出不可见（中，已知取舍）**：run 继续跑但没人接收事件，断连期间的 `assistant_delta` / `tool_call` 等丢失；重连后靠 `session_history` 恢复消息，但**流式过程**不可回放。另外 `session_history` 分支必须重置 `currentAssistantMsg`（否则后续增量写进僵尸 DOM，见 D5/M12）。是否把 in-flight 文本一并补发见 grill Q2。
- **run 生命周期延长（中）**：断连不再杀 run，可能让后台 run 在无观察者的情况下继续消耗 token；用户重连后想发新消息会被 `run_lock` 拒绝（原始英文错误）。缓解：这正是「切后台继续跑」的期望行为；预算/迭代上限仍由 AgentLoop 既有机制约束。完整取舍见 grill Q4。
- **审批超时的行为回归（中，取决于 Q1）**：若采「总时长 300s」语义，今天「挂 10 分钟回来点批准」的桌面用户会从生效变为 `unavailable`——这是本 change 引入的行为变更，必须在 proposal Impact Analysis 兼容性行与 README 文档同步标注。
- **多 tab 终态广播不完整（中，取决于 Q3）**：run 不在时的 inline 作答分支只回提交者，其他 tab 的陈旧卡片不会自动失效。收窄保证或扩展广播，见 grill Q3。
- **多 tab 竞态（中）**：两个 tab 同时收到同一张卡片、都提交 → 服务端 `submit_*` 对已 done 的 future 返回 `False` → 后提交者得到 `unavailable`。符合「先答者胜」，需在测试中固化。
- **`unavailable` 语义混淆（低）**：现有 `unavailable` 同时表示「无匹配 pending」「另一个审批已 pending」与新的「超时」，前端一律显示裸英文状态。建议在 design/spec 里区分 reason。
- **fail-closed 后的连锁耗时（低）**：超时 → `UNAVAILABLE` → run 继续；同一轮多个高风险工具会逐个各等一个超时周期，总耗时可能远超用户预期。
- **无界 queue 内存风险（中，实现约束）**：`web/session.py:764` 的 `asyncio.Queue()` 无容量上限；drain 必须永远消费，否则断连期间事件无界堆积（D3/M2）。
- **`ask_user` 在 web-ui spec 无既有需求（低）**：AskUserQuestion 此前没有 spec 覆盖，本 change 通过 ADDED requirement 补齐。
- **替代方案权衡**：
  - 复用 `GraphEventForwarder` 承载 run 事件：其 sink 是同步、fire-and-forget、失败即丢 + 分桶合并的语义，run 事件需要顺序投递与失败感知——否决，新写出口对象。
  - pending 跨进程持久化：进程重启后 run 本身已不存在，pending 无宿主——超出本 issue 范围，否决（与业界 durable 方案的差异已显式声明）。
  - 断连后设独立「宽限窗口」再失败：引入两个计时器与「断连重置计时」的复杂度——**保留为 Q1 的候选 (b)**，不再默认否决。

## Testing Strategy

- **单元测试**（`tests/web_tests/test_session.py`）：
  - `WebApprovalHandler` / `WebQuestionHandler` 保留载荷、超时返回 `UNAVAILABLE`、`reset`/`cancel` 立即失败；访问器原子返回 `(id, payload)`。
  - 断连（`ws_receive` 抛异常）后 pending 不被失败、run 不被取消；sender 集合正确移除该连接且不影响其他连接。
  - drain 循环在无绑定连接时仍消费队列（防无界堆积）。
  - 待补发载荷构造纯函数：有 pending / 无 pending / question 与 approval 各自的字段与 `session_id`。
- **服务端重连测试**（`tests/web_tests/test_server.py` 或新文件）：套 `test_reconnect_resends_running_snapshot`（`tests/web_tests/test_workflow_graph_server.py:117-149`）骨架——第一条 ws 造出 pending → 关闭 → 重连同一 session → **断言事件类型序列** `["session_resumed", "session_history", <补发卡片>]`（序列断言锁住排序不变量，比「最终收到了卡片」更强）；反例：无 pending 时用 `ping`/`pong` 证明没有多余事件。
- **多连接测试**：两条 ws 同时连同一 session，run 事件广播到两者；断开其一后另一个仍收到；先后提交决定时先答者胜。
- **前端契约测试**：优先 Playwright 行为断言（复用 `test_multi_session_browser.py` 的真实 ws 断连骨架，如 `test_multi_tab_exit_does_not_affect_other_tab_reconnect`）——卡片幂等（重复事件只有一张卡）、重连后卡片重新出现且可提交、ws 未就绪时提交有可见反馈、`session_history` 后 `currentAssistantMsg` 被重置；`tests/web_tests/test_server.py` 的 chat.js 源码字符串断言只作补充（对重构脆弱）。
- **回归**：issue #193 测试按新语义更新；`test_multi_tab_approval_isolation` 保持通过；`test_run_session_accepts_web_approval_response_for_high_risk_tool` 保持通过；`index.html` 的 `chat.js?v=21 → v=22` 同步更新 `tests/web_tests/test_server.py:438` 的断言。
- **全量**：`uv run pytest -q` 全绿；OpenSpec strict validate + artifact checker 通过。

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
- findings:

### 业界调研发现

1. **推送通道默认不保证投递，服务端也不为断线客户端缓冲；因此「只在事件发生那一刻 emit 一次」在协议层就注定会丢。** 依据：Socket.IO v4 官方文档 Delivery guarantees（https://socket.io/docs/v4/delivery-guarantees/）逐字写明「By default, Socket.IO provides an at most once guarantee of delivery」「there is no such buffer on the server」，断线期间 emit 的事件重连后不会补发；WHATWG HTML Standard 的 Server-sent events 只规范了客户端重连时携带 `Last-Event-ID`，明确「The specification itself only defines the client sending the value; it does not define server behavior」；Ably 亦指出「WebSockets don't include resume semantics」。**强度：官方文档/规范级（对「必须自建重放」给出的是否定式证据）。**

2. **等待人类响应的提问/审批必须是服务端的权威状态，投递给 UI 的事件只是可重放的投影；把 pending 绑在连接生命周期上必然丢状态。** 依据：Ably AI Transport 官方文档（https://ably.com/docs/ai-transport/features/human-in-the-loop.md）「Approval requests survive disconnections」「the pending tool call persists in the channel history」；LangGraph Interrupts 官方文档（https://docs.langchain.com/oss/python/langgraph/interrupts.md）要求 durable checkpointer 持久化中断态、「The `thread_id` you choose is effectively your persistent cursor」；Temporal 把「等待一个条件」持久记录进 workflow history；bamboo-engine（docs.rs）用 `(child_id, request_id)` 记录 pending 并在投递前一次性消费；semstreams 把 `LoopEntity.PendingApproval` 放进 KV bucket 以跨进程重启。**反面证据：** openhuman PR #6212（https://github.com/tinyhumansai/openhuman/pull/6212）逐字记录同一 bug 的根因——「A parked chat approval is durable server-side state but reaches the UI as exactly one fire-and-forget socket emit」。

3. **重连的正确做法是服务端主动重放仍处于 pending 的请求，而不是等下一次事件。** 依据：openhuman PR #6212「`thread:subscribe` now replays whatever the approval gate still holds parked on that thread」；hermes-agent PR #86596（https://github.com/NousResearch/hermes-agent/pull/86596）「the renderer replays pending approvals on `gateway.ready` / `session.info`」；DeepSeek Harness 排障文档（https://raw.githubusercontent.com/sandbaseai/deepseek-harness-handbook/refs/heads/main/docs/en/troubleshooting/missing-question-approval-after-reconnect.md）「The Host pushes them over the mux stream and replays still-pending entries whenever a new mux consumer opens」「This replay contract is why a refresh can recover the card」；runtypelabs/persona durable-reconnect 文档「the resume handle has to be persisted and replayed on boot」。**强度：多个知名项目的共识做法。**

4. **重放的幂等性来自「稳定 request id 作为 key」加「已决策的请求不再处于 pending 集合」，两者合起来使重复重放只是无害重渲染。** 依据：openhuman PR #6212 称之为「Idempotent by construction」——「the client keys the card by `request_id`, and a decided request is no longer parked」；hermes-agent PR #86596 用 `approval.respond {request_id}` 做精确关联、「stale responses can no longer resolve the wrong approval」；bamboo-engine 在投递前一次性 take 掉条目使同一 request 无法被二次作答；前端合并层面 Centrifugo 官方博客（https://centrifugal.dev/blog/2026/07/27/app-owned-state-stream-subscriptions）「Apply by id, keep the newer updated_at. Last write wins.」；框架层 React 官方要求 key 稳定且唯一、Svelte 官方建议用字符串/数字 id 作 keyed each 的 key。

5. **快照与增量重放有确定的排序不变量：补发必须在快照之上应用；「清空本地 pending」必须绑定连接代际的死亡，而不是绑定 resync。** 依据：Centrifugo 博客把该规则表述为「it has to be applied on top of the fetch result, not before it — otherwise a fresh value gets overwritten by an older one」，取舍是「Seeing an update twice is harmless, missing one is not」；DeepSeek Harness Discussion #3102（https://github.com/deepseek-ai/deepseek-harness/discussions/3102）复现完整竞态——宿主重放 pending 帧重建 PendingWait 后，`Session.resync()` 无条件 `this.pending.clear()` 把刚重建的卡片擦掉；修复是把 clear 前移到连接断开处（`handleDisconnected()`），resync 不再清 pending。runtypelabs/persona 用「服务端严格重放 `seq > after`」做到「No gaps, no dupes」。

6. **多 tab / 多连接：请求应广播到同一 session 的所有连接，首个作答原子胜出，并把终态广播回去让其余卡片失效；连接注册表必须按连接区分，不能只保留最新一条。** 依据：Ably AI Transport 官方文档「The session is a shared Ably channel, so the approval request is visible on every connected device」「Any device submits the approval; the first response wins」，同时提示需应用层「guard against double-submit」；Microsoft agent-host-protocol 的 Elicitation 文档（https://microsoft.github.io/agent-host-protocol/guide/elicitation.html）用共享 drafts 支持「a user can answer one question on client A and another on client B」；Apache WICKET-6761 记录反面教训——只按 resource 名做 key 会让「only the newest connection survives in the connection registry」，修复是加 connectionToken。**个别项目做法（不作为标准）：** openai/codex PR #10693 的「broadcast + first response wins」出自自动审查 bot 的转述且 7 天后 PR #11474 即改为按 `(thread_id, connection_id)` 定向投递。

7. **人类等待的超时存在两派实践：运行时层无限期等待（状态靠持久化存活），或应用层设显式 TTL 且超时 fail-closed；无论哪派，超时都绝不等于对不可逆操作放行。** 依据：无限等待派——LangGraph Interrupts 无任何 TTL 章节、「waits indefinitely until you resume execution with a response」；OpenAI Agents SDK HITL 指南把长等待交给 `RunState` 序列化；Claude Agent SDK 官方文档「The callback can stay pending indefinitely.」并建议改用返回 `defer` 的 hook。应用层 TTL 派——Temporal HITL cookbook 示例默认 5 分钟后以 timeout 结果收尾、Temporal 官方 Approval pattern 给出「超时→升级→再超时→auto-rejected」链路；microsoft/agent-governance-toolkit 的 `EscalationPolicy.timeout_seconds` 默认 300 且 `default_on_timeout="deny"`（自称 safe default）；Cloudflare Agents 的 `waitForApproval({ timeout: "7 days" })` 超时后走升级或自动拒绝，并建议「Store pending approvals in agent state so they survive disconnections」；Ably 明确传输层不设超时、建议应用层自加。**强度：框架级两派并存，「超时不得放行不可逆操作」是共同底线。**

8. **终态必须单调推进，陈旧重放绝不能把已完成拉回 pending；且「卡片缺失」不等于用户同意，绝不能用合成审批去解开 agent。** 依据：HackerNoon《Designing Reconnect-Safe Event Streams for Remote Coding Agents》（https://hackernoon.com/designing-reconnect-safe-event-streams-for-remote-coding-agents）「A stale replay must never move completed back to pending」「Treat terminal states as terminal.」，并指出实时投递与历史重放必须共享同一去重 key；Cordum 对安全重放返回确定性的 `already_approved` 而非错误；DeepSeek Harness 文档「The missing UI is not consent.」「Never synthesize an approval or answer through an API call to unstick the Agent.」。

9. **移动端切后台/锁屏导致的 WebSocket 断开应按「必然发生」设计，且断开信号本身不可信；应对手段是页面生命周期事件驱动 + 自建应用层心跳 + 指数退避重连。** 依据：MDN visibilitychange（https://developer.mozilla.org/en-US/docs/Web/API/Document/visibilitychange_event）「Transitioning to hidden is the last event that's reliably observable by the page」；RFC 6455 §5.5.2 规定收到 Ping MUST 回 Pong，但 WHATWG WebSocket API 不向脚本暴露 ping/pong（whatwg/websockets#10），浏览器只能自建应用层心跳；Chrome Page Lifecycle 官方文档要求把「关闭 WebSocket」放在 hidden/冻结前完成，web.dev 的 bfcache 文档把「打开的 WebSocket」列为部分浏览器不进 bfcache 的原因并建议在 pagehide/pageshow 重连；WebKit Bug 308073（https://bugs.webkit.org/show_bug.cgi?id=308073）记录 iOS Safari 后台恢复后新 WebSocket 永久卡在 CONNECTING、onopen/onerror/onclose 全不触发；重连退避的业界主流建议是「指数退避 + 抖动」（AWS 架构博客「The solution isn't to remove backoff. It's to add jitter.」）。

### 对本地参考仓库的对比

本次工作区的 `.dev/reference-repos.txt` **不存在**，本地参考仓库不可用。按项目规则这不构成豁免理由，须记录不可用事实与替代依据：本轮调研改用「公开规范 + 知名开源项目文档/源码」两层替代渠道——规范层包括 WHATWG HTML Standard（SSE `Last-Event-ID`）、RFC 6455 §5.5.2/§5.5.3、MDN（visibilitychange）、Chrome Page Lifecycle 与 web.dev bfcache；项目层包括 LangGraph / Temporal / OpenAI Agents SDK / Claude Agent SDK 官方文档、Socket.IO v4 delivery-guarantees、Ably AI Transport、Centrifugo、Microsoft agent-host-protocol，以及 openhuman / hermes-agent / deepseek-harness / bamboo-engine 等具体实现的 PR 与 issue。

未取到一手证据的缺口（如实记录）：Cloudflare resumable-streams 文档页 404（未采用）；MCP elicitation 规范本身不含断线重放语义；未找到规范级结论支撑「审批无超时」，只能用 Ably 的「传输层不设超时、应用层自加」作对照；WebKit/Chromium 没有「后台即杀 WebSocket」的规格级保证条款，该行为经 bug tracker 与官方博客描述。

### 对本 change 的设计影响

1. **pending 的权威状态。** 倾向：以服务端为唯一权威，前端卡片只是可重放的投影，绝不能用「前端是否渲染出卡片」判断请求是否还 pending；落一个 session 级 pending 记录（稳定 request id + 类型 question/approval + 状态 + 归属 session）。**本 change 的边界**：项目是单进程内存 session，进程重启后 run 本身已不存在、pending 无宿主，因此不做跨进程持久化（记为 Non-Goal）——与业界 durable 方案的差异显式声明。

2. **可恢复窗口怎么定。** 倾向（与业界一致）：**连接断开本身不触发任何失败或超时**，可恢复窗口与连接存亡解耦，由提问/审批自身的业务超时决定，而不是由断线时长决定；重连只要请求仍 pending 就补发。审批从「无超时」改为有显式超时是可接受的（Temporal/governance-toolkit 等默认 300s），但超时**必须 fail-closed**（判定 `unavailable`、绝不放行），且不得把「长时间无连接」解释为拒绝或同意。

3. **补发排序与幂等。** 倾向（与业界一致）：先建立历史/会话快照，再在其之上应用补发的 pending 帧；补发帧携带稳定 id，前端按 id 做 keyed 幂等 upsert（重复补发只是无害重渲染）；终态单向推进，陈旧重放不得把已答拉回 pending。特别注意 DeepSeek 的竞态教训——「清空本地 pending」应绑定连接断开而不是重连 resync；本 change 的顺序设计（history → 补发）天然规避该竞态，需在测试中固化。

4. **多连接。** 倾向（与业界一致）：把 run 事件与补发卡片投给该 session 的**所有**连接，服务端用一次性消费让首个有效作答胜出、落败者得到可幂等的终态；作答成功后向所有连接广播终态让其余卡片失效。这一条比现有 `GraphEventForwarder` 的「最后连接胜出」更强，是与 grill 讨论的重点取舍。

5. **已答/已过期请求绝不重放。** 倾向：重放只针对服务端「仍处于 pending」集合中的条目，已答/已超时/已取消的请求从集合移除即天然不重放；守住安全线——卡片缺失不等于同意，绝不用合成审批/合成回答去解开 agent。
