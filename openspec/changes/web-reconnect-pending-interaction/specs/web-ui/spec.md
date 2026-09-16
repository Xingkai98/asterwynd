# web-ui spec delta: 断线重连恢复 pending 交互

## ADDED Requirements

### Requirement: pending 提问与审批跨 WebSocket 连接存活

Web session SHALL 把「运行中等待用户响应的 pending 提问/审批」当作 session 级状态，而不是某条 WebSocket 连接的状态。WebSocket 断开 SHALL NOT 让仍在等待用户响应的 pending 提问/审批失败；服务端 SHALL NOT 因断开而返回 `[Error: websocket disconnected]` 之类的失败答复给 AgentLoop。

pending 状态 SHALL 由 `WebQuestionHandler` / `WebApprovalHandler` 在建立时保留完整的可重放载荷（提问的 `title`/`body`/`options`、审批的 `tool_name`/`risk`/`redacted_args` 等 `to_event_data()` 全部字段），供重连补发使用。

#### Scenario: 切后台断连不判定 pending 审批失败

- **GIVEN** 一个 Web session 有 pending approval request，AgentLoop 正在等待用户决定
- **WHEN** 浏览器 WebSocket 断开（移动端切后台）
- **THEN** pending approval SHALL 保持有效，SHALL NOT 被判定为 `unavailable`
- **AND** AgentLoop SHALL 继续等待用户响应，SHALL NOT 收到 `websocket disconnected` 失败

#### Scenario: 切后台断连不判定 pending 提问失败

- **GIVEN** 一个 Web session 有 pending question，AgentLoop 正在等待用户作答
- **WHEN** 浏览器 WebSocket 断开
- **THEN** pending question SHALL 保持有效，SHALL NOT 被判定为超时或失败

### Requirement: 重连补发 pending 交互卡片

WebSocket 重连（`GET /ws/<session_id>` 命中同一内存 session）时，服务端 SHALL 在推送 `session_resumed` 与 `session_history` 之后，补发当前仍然 pending 的交互卡片事件：pending question 补发 `user_question`，pending approval 补发 `approval_request`。补发的载荷 SHALL 与首次发出时一致，并 SHALL 带上 `session_id` 字段。

补发 SHALL 排在 `session_history` 之后（前端收到 `session_history` 会整体重绘消息区）。

已作答、已超时、已被拒绝或已取消的请求 SHALL NOT 被补发。

#### Scenario: 重连后补发 pending 提问卡片

- **GIVEN** 一个 Web session 有 pending question，客户端 WebSocket 断开后重新连上同一 session
- **WHEN** 服务端完成 `session_resumed` 与 `session_history` 推送
- **THEN** 服务端 SHALL 补发一条 `user_question` 事件，`question_id` 与该 pending question 一致
- **AND** 前端 SHALL 重新渲染提问卡片，用户 SHALL 能提交答案

#### Scenario: 重连后补发 pending 审批卡片

- **GIVEN** 一个 Web session 有 pending approval request，客户端 WebSocket 断开后重新连上同一 session
- **WHEN** 服务端完成 `session_resumed` 与 `session_history` 推送
- **THEN** 服务端 SHALL 补发一条 `approval_request` 事件，`approval_id` 与该 pending approval 一致
- **AND** 用户 SHALL 能批准或拒绝，决定 SHALL 被路由回等待中的 AgentLoop

#### Scenario: 没有 pending 时不补发

- **GIVEN** 一个 Web session 没有 pending 提问也没有 pending 审批
- **WHEN** 客户端重连该 session
- **THEN** 服务端 SHALL NOT 发送 `user_question` 或 `approval_request` 事件

### Requirement: pending 交互的放弃语义

pending 审批 SHALL 有显式超时：等待时长 SHALL 由配置项 `WebConfig.approval_timeout_seconds` 决定（缺省 600 秒），从 pending 建立时开始计时，连接断开与保持 SHALL NOT 影响计时。超时且仍无用户响应时，服务端 SHALL 判定为失败（`ApprovalDecisionStatus.UNAVAILABLE`，fail-closed）并让 AgentLoop 继续。

提问保留既有超时，等待时长 SHALL 由配置项 `WebConfig.question_timeout_seconds` 决定（缺省 300 秒），该超时 SHALL NOT 因 WebSocket 断开而重置或提前。

会话被显式重置（`reset`）或取消（`cancel`）、或 run 真正结束时，pending SHALL 立即失败（保持既有语义）。

#### Scenario: 超时窗口内断连后仍可作答

- **GIVEN** 一个 Web session 有 pending approval，WebSocket 断开
- **WHEN** 用户在超时窗口内重连并提交决定
- **THEN** 该决定 SHALL 被接受并路由回 AgentLoop
- **AND** AgentLoop SHALL 按该决定执行或拒绝工具

#### Scenario: 超过超时窗口判定失败

- **GIVEN** 一个 Web session 有 pending approval，WebSocket 断开且用户始终未重连
- **WHEN** `approval_timeout_seconds` 到期
- **THEN** pending approval SHALL 被判定为 `unavailable`
- **AND** AgentLoop SHALL 收到失败答复并继续运行，SHALL NOT 永久挂起

#### Scenario: 超时时长可配置

- **GIVEN** 配置中将 `approval_timeout_seconds` / `question_timeout_seconds` 设为某正整数
- **WHEN** pending 审批或提问建立
- **THEN** 其超时窗口 SHALL 按该配置值生效
- **AND** 非法值（0 / 负数 / 非整数）SHALL 被拒绝并给出结构化错误

#### Scenario: reset 或 cancel 立即失败

- **GIVEN** 一个 Web session 有 pending 提问或审批
- **WHEN** 收到 `reset` 或 `cancel`
- **THEN** pending SHALL 立即被判定为失败
- **AND** SHALL NOT 等待超时窗口到期

#### Scenario: 多连接首答者胜

- **GIVEN** 一个 Web session 有多条连接且存在 pending 审批
- **WHEN** 两条连接先后提交了不同的决定
- **THEN** 先提交的决定 SHALL 胜出并路由回 AgentLoop
- **AND** 后提交者 SHALL 收到 `unavailable`，SHALL NOT 覆盖先到的决定
- **AND** 作答成功后所有连接 SHALL 收到该审批的终态事件

#### Scenario: 各作答路径的终态广播行为一致

- **GIVEN** 一个 Web session 有多条连接，存在 pending 审批
- **WHEN** 一条连接提交决定，无论 run 是否仍在执行
- **THEN** 所有连接 SHALL 收到一致的终态事件
- **AND** SHALL NOT 出现「run 存活广播、run 不存活只回提交者」的不一致

### Requirement: run 事件出口跨连接存活

Web session 的 run 事件出口 SHALL 是 session 级、与单条 WebSocket 连接解耦的：WebSocket 断开 SHALL 只解绑该连接，SHALL NOT 终止正在执行的 run。断连期间 run SHALL 继续执行；重连 SHALL 把新连接绑上同一个出口，之后产生的事件 SHALL 送达当前所有已绑定连接。

同一 session 存在多条已绑定连接（多 tab / 多设备）时，run 事件 SHALL 广播给全部连接；某条连接断开 SHALL NOT 影响其他连接继续接收。

断连期间无人接收的事件 SHALL 允许丢弃（该期间的消息历史由重连后的 `session_history` 兜底）。

#### Scenario: 断连不终止运行中的 run

- **GIVEN** 一个 Web session 的 run 正在执行
- **WHEN** WebSocket 断开
- **THEN** run SHALL 继续执行
- **AND** 重连后 SHALL 能继续收到该 run 的后续事件

#### Scenario: 多连接广播

- **GIVEN** 一个 Web session 有两条已绑定的 WebSocket 连接
- **WHEN** run 产生事件
- **THEN** 两条连接 SHALL 都收到该事件
- **AND** 其中一条断开后另一条 SHALL 继续收到后续事件

#### Scenario: 断连期间没有 pending 时 run 可正常跑完

- **GIVEN** 一个 Web session 的 run 正在执行且没有 pending 交互
- **WHEN** WebSocket 断开且 run 在断连期间完成
- **THEN** run SHALL 正常结束并释放 session 的 run 锁
- **AND** 重连后 SHALL 通过 `session_history` 看到完整消息历史

#### Scenario: run 进行中断连重连后发新消息被拒

- **GIVEN** 一个 Web session 的 run 因断连仍在后台执行
- **WHEN** 用户重连后在页面发送新消息
- **THEN** 服务端 SHALL 拒绝该 run（同一 session 并发 run 被拒）
- **AND** SHALL 把拒绝错误只回发起连接，SHALL NOT 广播到其他连接
- **AND** 前端 SHALL 给出用户可读的提示

### Requirement: 前端交互卡片幂等渲染

前端 SHALL 按 `question_id` / `approval_id` 幂等渲染交互卡片：同一 id 的卡片事件重复到达时 SHALL NOT 产生第二张卡片，SHALL 复用已存在的卡片。

前端收到 `session_history` 整体重绘消息区时 SHALL 清理该会话的卡片注册表，避免留下指向已移除 DOM 的条目。

交互卡片提交时若 WebSocket 未处于 OPEN 状态，前端 SHALL 给出可见反馈并保留卡片可提交（SHALL NOT 静默丢弃用户的决定）。

#### Scenario: 重复卡片事件不产生第二张卡片

- **GIVEN** 前端已经渲染了某个 `approval_id` 的审批卡片
- **WHEN** 服务端因重连补发再次推送同一 `approval_id` 的 `approval_request`
- **THEN** 消息区 SHALL 只有一张该 `approval_id` 的卡片
- **AND** 该卡片 SHALL 可正常提交决定

#### Scenario: ws 未就绪时提交不被静默丢弃

- **GIVEN** 前端渲染了提问卡片但 WebSocket 尚未重连完成
- **WHEN** 用户提交答案
- **THEN** 前端 SHALL 给出可见反馈（例如提示连接未就绪）
- **AND** 卡片 SHALL 保持可提交状态，用户 SHALL 能在重连后再次提交

## MODIFIED Requirements

### Requirement: Web UI SHALL support tool approval requests

Web UI run SHALL 将需要审批的工具调用暴露为 pending approval request，并关联正确的 session 和 run。用户决定 SHALL 被路由回等待中的 AgentLoop instance，然后工具才能被执行或拒绝。每个 Web session 同一时刻 SHALL 只有一个 pending approval。WebSocket 断开 SHALL NOT 让 pending approval 立即失败；重连后服务端 SHALL 补发该卡片（见「pending 提问与审批跨 WebSocket 连接存活」与「重连补发 pending 交互卡片」）。

#### Scenario: Web 用户批准 pending 工具调用

- **GIVEN** 一个 Web UI session 有 pending approval request
- **AND** 用户批准该请求
- **WHEN** 决定被投递给 AgentLoop
- **THEN** AgentLoop SHALL 执行被批准的工具
- **AND** Web UI SHALL 展示该审批已批准

#### Scenario: Web 用户拒绝 pending 工具调用

- **GIVEN** 一个 Web UI session 有 pending approval request
- **AND** 用户拒绝该请求
- **WHEN** 决定被投递给 AgentLoop
- **THEN** AgentLoop SHALL NOT 执行工具
- **AND** Web UI SHALL 展示该审批已拒绝

#### Scenario: 并发 session 的审批路由互相隔离

- **GIVEN** 两个 Web UI session 都有 pending approval request
- **WHEN** 用户处理其中一个请求
- **THEN** 该决定 SHALL 只恢复匹配的 session/run
- **AND** SHALL NOT 影响其他 session 的 pending approval

#### Scenario: 断连重连后审批仍可作答

- **GIVEN** 一个 Web UI session 有 pending approval request
- **AND** 浏览器 WebSocket 断开后重连同一 session
- **WHEN** 用户在重连后的页面批准该请求
- **THEN** AgentLoop SHALL 执行被批准的工具
- **AND** Web UI SHALL 展示该审批已批准
