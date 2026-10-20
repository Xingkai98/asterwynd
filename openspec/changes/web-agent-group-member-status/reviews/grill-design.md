# Grill: web-agent-group-member-status 设计追问

## Reviewer

- run id: grill-agent-paseo
- 时间: 2026-10-20
- 方法: 完整读 `AGENTS.md`、change 的 proposal/design/tasks/两份 spec delta、issue #307 正文与 2026-10-20 前置调研 comment；逐行核实了 `agent/team/orchestrator.py`、`agent/team/runner.py`、`agent/team/sessions.py`、`agent/hooks/manager.py`、`agent/loop.py`（run/resume、Phase 1-3、`_call_llm`、`_execute_single_tool`/`_execute_tool_calls`、`_should_stream_llm`）、`web/session.py`（`SessionEventChannel`、`run_session`、`_run_session_locked`、`WebSessionRunner`）、`web/team.py`（`RoomEventBus`、`TeamService`、`_WorkspaceRunner`）、`web/server.py`（事件 sink、房间 WS 握手/关闭）、`web/static/group.js`、`index.html`、`style.css`、既有规格 `multi-agent-collaboration:1267/1304`、`web-ui:1595`、相关测试与 `tests/support/llm_harness.py`、`.witnessloop/policy.json`、RIR checker。只做只读核验，未写实现代码。所有行号相对基线 `48d25f0`。

## Confirmed Decisions

- **决策**: 工具的开始/结束必须取 `before_tool_execute` / `after_tool_execute`，不能取 `tool_call` / `tool_result`；`on_error` 不能当 run 终态；`typing` 只在流式开启时可观测。**理由**: `tool_call`/`tool_result` 在 Phase 3 后处理才发（`agent/loop.py:1013-1014`、`:1075-1089`），工具真正开始/结束的钩子在 `agent/loop.py:1417`、`:1447`；`on_error` 在参数解析错误（`:877`）和 Bash 异常/超时（`:1427`、`:1431`）都会触发；非流式时 `_should_stream_llm()` 为假（`:1389-1395`），`BaseLLM.stream` 默认 False（`agent/llm.py:98`），`ASTERWYND_STREAMING` 缺省 enabled（`agent/main.py:132-134`）。**来源**: grill-agent-paseo
- **决策**: 用 `SessionRunner.run(..., on_progress=...)` 回调而不是在 web 层合成 `ConnectionHandle`。**理由**: 群聊 runner 确实无连接驱动——`WebSessionRunner.run` 调 `manager.run_session(session, message)` 不传 handle（`web/session.py:2203-2206`），`SessionEventChannel.broadcast` 没有句柄时直接返回 0（`:420-437`），drain 循环把所有事件交给它（`:2125`）；回调把「成员进度」与「连接事件」分开，且 `agent/team` 不反向 import web 的分层约束成立（`agent/team/orchestrator.py:269`、`agent/team/runner.py:1-16`）。**来源**: grill-agent-paseo
- **决策**: 状态 reducer 放 `agent/team/` 编排器层、只消费无内容信号，是可测试且分层正确的选择。**理由**: reducer 只依赖 `(kind, data)`；`agent/team` 已有 `SessionRunner`/`SessionResolver` 的依赖倒置先例；纯函数可在无 provider、无 asyncio 的条件下覆盖优先级、并发工具计数与终态重置。**来源**: grill-agent-paseo
- **决策**: 服务端权威、只发状态迁移、不把 token 级 `assistant_delta`/`reasoning_delta` 转发到房间总线。**理由**: `RoomEventBus.broadcast` 对每个订阅者逐条 `await`（`web/team.py:112-121`），token 增量在多标签页下会线性放大并拖慢广播；业界矩阵/typing 与 presence 的租约模型也不要求转发内容（RIR 的 Matrix/Discord 引用成立）。**来源**: grill-agent-paseo
- **决策**: 用 `room_state` 快照恢复重连/第二标签页，并修正「先 subscribe 再发快照」的窗口。**理由**: 现状确实先 `room_bus.subscribe(room_id, ws.send_json)`（`web/server.py:651`）再 `await ws.send_json(room_state)`（`:652-661`），订阅后到快照前有并发发送窗口；快照字段只有 `workspace`/`room`/`members`/`timeline`/`round_active`，轮次中重连看不到谁在忙。**来源**: grill-agent-paseo
- **决策**: 桌面用独立 presence 列取代现有成员 chip 行，避免同一成员两处状态。**理由**: chip 行现在只承载成员身份/`speaking` 全局高亮（`web/static/group.js:306-324`、`index.html:188`），而 `state.speaking` 是单值（`group.js:19-20`），无法表达 per-member 五档；新模型必须替换它。**来源**: grill-agent-paseo
- **决策**: 移动端必须先修现有群聊布局（管理侧栏抽屉化），再谈状态形态；方案 A/B/C 的推荐 A 方向成立。**理由**: 群聊 CSS 位于最后一条 `@media (max-width: 720px)` 之后（`web/static/style.css:2064-2094` vs `:2096` 起），没有群聊移动端规则；`.group-sidebar` 固定 260px（`:2104-2112`），390px 下主区约 94px，抽屉化是必要前提；A 的 56px 横向成员条在 366px 主区下可显示约 3 人，取舍描述属实。**来源**: grill-agent-paseo
- **决策**: 取消/断线用既有 `round_ended` 承载 teardown 通知，而不是新增取消协议或用户打断出口。**理由**: 旧前端对 `round_ended` 已有「本轮结束」分支（`group.js:276-288`），新 termination 值对旧前端可降级；房间 WS 只处理 `chat`/`ping`（`web/server.py:678-690`），规格明确首版不提供轮次取消出口（`openspec/specs/multi-agent-collaboration/spec.md:1304`）；`round_ended(cancelled)` 不写日志、不产生 `RoundResult` 的隔离口径正确。**来源**: grill-agent-paseo

## Design Corrections

### 高优先级（不修不建议进实现）

- **C1（seq 语义：房间级游标套在成员级事件上会误丢状态）**。Decision 4 用「每房间一个 `status_seq`」并规定客户端 `status_seq <= lastStatusSeq` 丢弃，但每个 `member_status` 只携带一个成员（`design.md:206-241`）。客户端推进的是**房间级**水位，事件却是**成员级**载荷：成员 A 的 seq=10 事件若晚于成员 B 的 seq=11 到达，会被整体丢弃，A 的最新状态丢失。当前串行编排下 A/B 同时非空闲不会发生，但设计明确宣称「为未来并发留出接口」（proposal 用户故事、design 1.4），这个游标模型在并发下是错的。**修法**：改为每成员序号（`lastSeqByMember`）或让每个 `member_status` 携带完整状态表（成员数是个位数到几十，带宽可接受）；`room_state` 的 `status_seq` 只用于快照与实时事件的整体比较。
- **C2（终态无条件清空 + 迟到终态可抹掉新一轮）**。客户端规则 3 规定收到终态「无条件清除对应成员」（`design.md:230-237`）。但服务端在 `_run_round` 中**先 `self._rounds.pop(...)`（`agent/team/orchestrator.py:361-362`），再 `await review_sink.on_round_end(...)`（`:372-376`），最后才 `await _emit("round_ended", ...)`（`:378-382`）**。pop 与终态发射之间存在真实 await 窗口：同房间另一条 WS 可在这段时间开启新一轮并先发出 `member_status`；旧轮的 `round_ended` 随后到达，客户端无条件清空，把新一轮的状态抹掉（直到下一次状态事件）。取消路径同样如此。**修法**：终态清空改为按 seq 条件执行（仅当 `terminal.status_seq >= lastStatusSeq` 时清空），或给事件增加 round epoch（例如 `round_start_seq = state.start_seq`），客户端只接受当前 epoch 的终态；服务端最好把终态发射放在释放房间认领之前（或至少把「重置 + 递增 seq」放在任何 await 之前）。
- **C3（客户端水位跨重连/进程重启不自洽）**。设计说进程重启后状态为空、`round_active=false` 全部空闲（`design.md:421-441`），但客户端 `lastStatusSeq` 是页面内存、重连时不重置：服务端重启后房间 seq 从 0/小值重新开始，`room_state.status_seq` 小于客户端旧水位，规则 4 会「只更新时间线、不用旧状态覆盖」（`design.md:230-241`），后续 `member_status` 也因 `<= lastStatusSeq` 被永久丢弃，直到 seq 涨过旧值。`TeamService.team_for` 的编排器是进程内缓存（`web/team.py:300-308`），只有进程重启才会触发，但这是设计自己列出的边缘场景。**修法**：每次新建房间 WS 连接时先清空状态表并把 `lastStatusSeq` 置 0，再把首帧 `room_state` 当作权威快照；或由服务端在快照/事件里带一个 epoch（进程/编排器实例 id）。
- **C4（合并发射器与 spec「每次状态变化 SHALL 发布」冲突）**。Decision 4 的发射器在发送时读**当前快照**（`design.md:243-255`），因此同一成员在发射任务两次运行之间发生的多次迁移会被合并，只发布最终状态；而 spec delta 写的是「**每次状态变化 SHALL 通过房间级 `member_status` 事件发布**」（`specs/multi-agent-collaboration/spec.md:5`）。Testing Strategy 2 又要求断言完整的 `running → thinking → typing → tool → ...` 序列（`design.md:456-471`），在 FakeRunner 连续发信号时中间状态会被合并，测试按现文案不可靠。**修法**：spec 改为「状态变化 SHALL 被发布，允许把同一成员的短窗口内多次变化合并为最新快照；最终状态 SHALL 与快照一致」，测试断言最终状态 + 单调子序列，而非完整逐迁移序列。若坚持逐迁移发布，发射器必须改成有界队列而不是「读当前快照」，并明确回压策略。
- **C5（空产出缺口在生产路径上已被归一，叙事不实）**。设计把「`outcome.status == "text"` 且文本为空时漏发 `member_silent`」列为三个真实缺口之一（`design.md:33-37`、`:267-270`）。但 `WebSessionRunner.run` 在返回前已经做 `if outcome.status == "text" and silent_marker and is_silent(outcome.text, silent_marker): return TurnOutcome(status="silent")`（`web/session.py:2226-2227`），而 `is_silent("")` 为真（`agent/team/runner.py:85-88`），编排器调用时始终传 `SILENT_MARKER`（`agent/team/orchestrator.py:443-447`）。因此生产路径上编排器看不到 `text + 空文本`；该分支只对自定义 runner 可达。**修法**：把设计/规格里的「修复既有缺口」改称「防御性契约」；新增的 `member_silent` 合成保留可以，但不要把它当作用户可见的 bug 修复，测试定位为 runner 契约测试。
- **C6（非 Bash 工具异常会跳过 `after_tool_execute`，工具状态可能卡死）**。`_execute_single_tool` 只对 Bash 捕获异常（`agent/loop.py:1420-1432`）；非 Bash 走 `_retry.execute_with_retry`（`:1434-1439`），异常会直接抛出，`after_tool_execute`（`:1447`）不会执行；`_execute_tool_calls` 用 `asyncio.gather(..., return_exceptions=True)` 吞掉异常继续（`:1500-1513`）。此时 reducer 的 `active_tools` 仍含该工具，下一次 `iteration_started` 的规则是「active_tools 非空 ⇒ 保持 tool」（`design.md:106-117`），成员会一直显示「正在使用工具 X」直到终态。Edge cases 里「工具错误后继续 → after_tool_execute 仍触发」（`design.md:431`）对这条路径是**假的**。**修法**：在 `iteration_started`（新一次 LLM 调用开始）时同步清空 `active_tools`——一次新的 LLM 调用意味着上一轮工具不可能仍在执行；并以 `tool_call.id` 兜底配对。这样工具状态的权威出口不依赖 `after_tool_execute` 是否触发。
- **C7（终态重置与 `status_seq` 的先后顺序自相矛盾）**。Decision 5.1 写 `text` 非空时「`member_post`（带 `status_seq`）→ 重置」，`silent`/`failed` 写「（带 `status_seq`，重置后）→ 重置」（`design.md:264-271`），而 Decision 4 与 spec delta 要求终态携带**重置后**的序号（`design.md:243-255`、spec delta:5）。如果实现按 5.1 先发后重置，终态携带的是旧 seq，与「重置后」不符，也可能让一个同 seq 的迟到状态被错误处理。**修法**：统一为单一 helper：同步清空 + 递增 seq + 清 dirty，**然后**用这个新 seq 发终态；所有出口都走它。
- **C8（意外异常路径没有清理事件，活动标签页会永久卡在忙）**。`_run_slot` 的 finally 只重置**内存**状态（`design.md:271`），但活动客户端只认事件；如果 `_run_slot`/`_run_round` 在 `member_speaking` 之后抛出意外异常（例如日志写入失败），`_run_round` 的 finally 清空内存并 pop，但没有 `round_ended`，`submit_room_message` 的后台 task 异常也不会被取回（`web/server.py:684-688` 只有 `rounds.discard`）。客户端会一直显示最后的状态，直到重连拿到快照或下一次状态事件。**修法**：定义意外异常的 teardown 通知（与 cancellation 共用一个「重置 + 发终态」路径；termination 值需要一个明确口径，见 Open Question 的替代方案），或至少在 spec 中明确「未发终态的异常下，客户端依赖重连快照」并加测试；不要把「内存已清」当作「客户端已回 idle」。
- **C9（取消 teardown 的 best-effort 可能让其他标签页永久忙）**。`design.md:276-279` 说取消时尽力发 `round_ended(cancelled)`，若发送本身被取消则以同步重置兜底。但同步重置对**其他标签页**不可见；发起连接的 WS 在取消前已经 `unsubscribe`（`web/server.py:695-699`），其他标签页正是唯一受众。一次二次取消/事件循环关闭就会让它们停在最后状态。**修法**：取消路径用 `asyncio.shield` + 有界 `wait_for` 发一次 teardown，或创建一个带强引用的后台清理 task；测试必须覆盖「两个标签页，关掉发起连接，另一条连接收到终态或重连后为 idle」。
- **C10（快照发送失败路径不在既有 unsubscribe 的 try 内）**。设计说「若快照发送失败，finally 走既有的 unsubscribe 路径」（`design.md:327-330`）。现状 `subscribe` 与 `await ws.send_json(room_state)` 在 `try` **之前**（`web/server.py:651-661`；`try` 从 `:662` 开始，unsubscribe 在 `:695-696`），握手阶段抛异常根本走不到这个 finally，会留下订阅。**修法**：把「构造快照 → 取锁 → subscribe → 发快照」放进一个显式的 `try/except/finally`，在异常路径 unsubscribe；或把整段移进现有 try。

### 中优先级（应在设计/实现任务中明确）

- **C11（`on_event is None or 没有订阅者` 在编排器层不可判定）**。`design.md:248` 写「若 `on_event is None` 或没有订阅者，仍维护快照但不创建发射任务」。编排器只有 `on_event` 回调（`agent/team/orchestrator.py:283`、`:535-541`），看不到 `RoomEventBus.subscriber_count`（`web/team.py:109-110`）。**修法**：只要 `on_event is not None` 就调度发射任务（无人订阅时 broadcast 返回 0，成本可忽略），或注入一个 `has_subscribers(room_id)` 谓词；不要写一个无法实现的判断。
- **C12（`run_started` 钩子在 resume 分支不触发）**。`on_run_started` 只在非 resume 分支调用（`agent/loop.py:709-743` vs `:755`），`run_started` 事件同样只在 else 分支（`:758-762`）。群成员会话在进程重启后第一次 run 会走 `resume_snapshot`，因此拿不到 `run_started` 信号；状态会从 `running`（slot_started）直接到第一次 `before_iteration` 的 `thinking`。功能上可接受，但设计/测试若断言首个信号是 `run_started` 会假红。**修法**：把 `before_iteration` 作为 thinking 的权威信号，文档注明 resume 路径；测试覆盖「resumed session 的首个状态序列」。
- **C13（UI：`#group-room-status` 已被连接/错误状态占用）**。设计说房间头部 `#group-room-status` 保留为「优先级最高的非空闲成员」摘要（`design.md:349-351`），但该元素现在由 `setStatus()` 写入「已连接」「连接断开，重连中...」「本轮结束」「发送失败」等（`web/static/group.js:369-372`，调用点 `:218`、`:230`、`:254`、`:278`、`:393`）。presence 的状态更新若复用同一元素会覆盖连接/错误提示，反之摘要会被操作提示覆盖。**修法**：新增独立的摘要元素，或定义单一优先级规则（连接错误 > 轮次状态 > presence 摘要）并测试。
- **C14（UI：chip 行同时承载群公告）**。`renderMembers()` 除了 chip 还追加 `.group-notice`（`web/static/group.js:318-323`、`index.html:188`）。presence 取代 chip 行后，群公告需要新的承载位置；设计未提。**修法**：把公告移到房间头部下方/时间线顶部，或在 presence 内保留公告块，并加回归测试（现有群公告显示不丢）。
- **C15（UI：DOM 位置与移动端「房间头部下方」不自洽）**。设计把 `<aside class="group-presence">` 插在 `.group-sidebar` 与 `.group-main` 之间（`design.md:334-339`；现状 `index.html:162-179`，房间头部在 `.group-main` 内部 `:181-187`）。移动端 `.group-layout` 改单列后，这个 aside 作为 main 的**前置兄弟**会出现在房间头部**之上**，而不是设计要求的「房间头部下方、时间线上方」（`design.md:365-366`）。若不改 DOM，只能用绝对定位/JS 搬移，脆弱且难测试。**修法**：把 presence 放进一个能与 `.group-room` 一起网格化的结构（例如 `.group-main` 内 `header` + `presence + timeline` 的 grid，桌面用 CSS 把 presence 放到 main 左侧的独立列），或明确接受移动端「头部之上」并更新设计/规格措辞。
- **C16（spec：`round_ended(cancelled)` 应显式修改既有「三出口」要求）**。既有规格说「一轮 SHALL 在**三个出口**之一结束」且「首版不提供轮次取消出口」（`openspec/specs/multi-agent-collaboration/spec.md:1304`），delta 只以 `## ADDED Requirements` 增加一条并声明 `cancelled` 不是出口（`specs/multi-agent-collaboration/spec.md:51-57`）。逻辑上可自洽，但两条 Requirement 并存会让读者/后续实现把 `round_ended(cancelled)` 读成第四个出口。**修法**：在 delta 中增加 `## MODIFIED Requirements`，把既有「房间级互斥与轮次终止」要求改为「三出口 + 取消 teardown 通知（非出口，不写日志、不产生 `RoundResult`）」；保留 `round_ended` 事件名是为了旧前端兼容，不应换成旧前端会忽略的新事件类型（那会让旧标签页停在忙）。
- **C17（spec：断线清空与前端实现不一致）**。delta 要求「轮次结束、取消或**断线** SHALL 无条件清空该房间的成员状态」（`specs/multi-agent-collaboration/spec.md:68`），但设计的前端 `onclose` 只显示「连接断开，重连中...」并 2 秒后重连（`web/static/group.js:228-235`），没有清空状态表。**修法**：要么在 `onclose` 立即清空/标记「未知」（并定义此时显示什么），要么把 spec 改为「断线后重连时以 `room_state` 快照为准」，避免规格与实现互相打脸。
- **C18（`member_failed` 用于建会话失败是语义扩展，且实时/重载文案不一致）**。设计称「既有事件只增不改」，但给 `member_failed` 增加了一个新的触发路径（`ensure_room_session` 失败，`design.md:262-263`）。前端收到 `member_failed` 会**客户端合成**一条 system 条目，且用 `persona_id` 而非成员名（`web/static/group.js:268-274`）；服务端日志里是「成员 甲 运行失败：会话不可用」（`agent/team/orchestrator.py:422`）。实时看到 id、刷新/重连后看到 name，两者不一致；这不是新 bug，但本 change 让建会话失败也进入这条路径，放大了它。**修法**：给 `member_failed` 增加 `name` 字段（属于「只增字段」）并让前端优先使用；或顺手把 `group.js` 的合成条目改为 `speakerName(data.persona_id)`；在 spec/设计里明确 `member_failed` 的语义已扩展到会话构造失败。
- **C19（RIR 引用了不可提交的本地参考仓库绝对路径）**。`design.md:185-190` 在提交文档中写了一个本地参考仓库绝对路径（DeepSeek-Bot 的本地克隆）。AGENTS.md 明确「不要把参考仓库路径...作为可提交项目资产」。**修法**：改成仓库名 + 文件相对引用，或按门禁要求在 findings 记录「本地参考仓库不可用」及替代依据；不要把绝对路径留在 design 里。
- **C20（静态资源加载顺序与缓存版本）**。`index.html` 用带版本号的 script 标签加载 `group.js?v=2`（`web/static/index.html:223`）。新增 `group_status.js` 必须在 `group.js` **之前**加载，并给两个文件都更新 `?v=`（否则浏览器会缓存旧 `group.js`，出现找不到 `window.AsterwyndGroupStatus` 或旧渲染逻辑）。设计和 tasks 4.1/4.2 没有写这条。**修法**：在 index.html 变更任务中明确脚本顺序与版本号；浏览器 smoke 断言 `window.AsterwyndGroupStatus` 存在。

### 低优先级（记录即可，不阻塞）

- **C21**: `Hook` 是 `runtime_checkable` 的完整协议（`agent/hooks/manager.py:14-27`），`HookManager` 直接调用每个方法（`:39-58`）。`ProgressHook` 必须把 `after_llm_call` / `on_error` 实现为 no-op，不能只实现「用到的」方法，否则会在 `after_llm_call`（`agent/loop.py:796`）处 AttributeError。
- **C22**: 设计称「现有实现只有 `web/team.py:222` 与 `tests/...:35` 两处」（`design.md:164-165`）。**不准确**：`web/session.py:2178` 的 `WebSessionRunner.run` 是第三个（也是基础）实现；grep 模式 `async def run(self, session_id` 因为该签名换行而漏掉。设计正文确实单独列了 `WebSessionRunner` 要改，所以实现计划是完整的，但请修正「只有两处」的结论，避免后续审阅者按错误范围检查。
- **C23**: `test_runner_contract.py` 的 docstring 明确「四态的完整验证在 `test_group_chat_team.py`」，该文件只测 `TurnOutcome`/常量/哨兵。`on_progress` 的「不传行为不变」「回调抛异常不影响 turn」应放到 `test_group_chat_team.py`（有真实 `AgentSession`）或 `test_orchestrator.py`，而不是 `test_runner_contract.py`。
- **C24**: `member_statuses()` 与 `status_seq()` 是两个同步读（`design.md:283-294`）。当前二者之间没有 await，是一致的；但建议合并成一个 `snapshot(room_id)` 返回 `(statuses, seq)`，避免未来在两者之间加入 await 后快照内部不一致。
- **C25**: `room_state.member_statuses` 的每项带 `status_seq`，同时房间级也有 `status_seq`（`design.md:296-304`），语义未定义。建议明确：每项 seq = 该成员最后一次迁移的 seq；房间 seq = 当前全局值；客户端只把房间 seq 用于快照/实时比较，成员 seq 用于每成员守卫（与 C1 的修法配套）。
- **C26**: `member_speaking` 兜底把成员置为 `running`（`design.md:395-397`）时，应只在成员当前为 idle/未知时生效，避免任何情况下把更细的状态降级；新服务端的事件顺序通常不会触发，但协议层应显式定义。
- **C27**: 既有测试循环上限实际在 `tests/web_tests/test_group_chat_server.py:244-251`（`for _ in range(12)`），不是设计写的 `:241-250`；行号漂移不影响结论，但请在 tasks 中改成函数名/「收集到 `round_ended`」而不是硬编码行号。

## Risks

- **合并发射器 + 串行执行仍可能让「思考」不可见**：真实 LLM 调用有 await，通常能看到；但脚本化/极快 provider 下 `running → thinking → running → idle` 可能被合并成 `running → idle`。这是可接受的产品折衷，但必须在 spec/测试里承认，否则「每次变化都发布」的断言必然假红。
- **`status_seq` 的三处问题（C1/C2/C3）叠加**会造成：服务端重启后旧 tab 永久脏状态、跨轮终态抹掉新轮、未来并发下误丢成员状态。它们都不是靠客户端「再检查一次」能兜住的，应在实现前定案。
- **取消 teardown 的投递不可靠（C9）** 会让「断线后其他标签页」成为最容易被忽略的脏状态来源；现有测试没有双标签页 + 断线的覆盖。
- **移动端重构的 DOM 位置（C15）** 可能迫使实现用绝对定位/JS 搬移，破坏键盘焦点、滚动容器与 Playwright 可测性；应在设计阶段定下结构，而不是留给实现临场决定。
- **UI 两处状态源（C13/C14）** 会让「状态栏显示 busy，但头部显示连接断开/公告消失」这类矛盾被浏览器 smoke 漏掉，因为现有测试只断言宽度与文字。
- **`aria-live` 的「只在状态变化时播报」不可机械判定**：屏幕阅读器行为无法在 Playwright 中断言。设计说「可只断言 class/属性」（`design.md:503`）等于没有验收口径；建议改为一个独立的隐藏 live region，文本是「甲 正在使用工具 Bash」这类单条消息，并断言它只在 phase 变化时改变。
- **事件量与慢客户端**：状态事件被合并后条数有界，但 `broadcast` 逐连接 await，慢订阅者仍会拖慢终态发射与其他标签页；设计已登记为既有风险，本 change 不新增协议级超时，但应在实现中避免在工具钩子里直接 await 广播（设计的合并发射器正是为此，保留）。
- **浏览器测试的假服务器成本**：现有 `fake_web_server` 在 `tests/web_tests/test_workflow_graph_browser.py:35`，只覆盖 workflow；群聊的 `/ws/room`、team API 与状态推送需要另建/抽取 fixture，设计只写了「复用 fake_web_server 模式」，低估了工作量与 flaky 风险。
- **hook 生命周期**：`DebugHook` 的摘除在 drain 之后、不是 finally（`web/session.py:2143-2148`）；`ProgressHook` 必须放在覆盖整个 run 的 finally 中，且测试连续两次 run 只能看到一组信号，否则后续 run 会重复触发并向旧房间发状态。

## Code-Resolved Questions

以下问题已由代码/规格定案，不占用用户时间：

- **`tool_call` 能否作为工具开始？** 不能（正常执行路径在 `agent/loop.py:1075-1089`，工具在 Phase 2 已执行完）。解析失败路径在 `:888-904` 提前发 `tool_call`/`tool_result`，但那个工具根本没执行，仍不能当开始信号。
- **`on_error` 能否当 run 终态？** 不能。参数解析错误（`:877`）、Bash 超时/异常（`:1427`、`:1431`）都会触发；非 Bash 的异常还可能根本不触发 `on_error`（`_execute_single_tool` 的通用分支没有 try，`:1434-1439`）。run 级失败由 runner 四态出口兜底。
- **非流式时能否显示 typing？** 不能（`agent/loop.py:1389-1395`；`agent/llm.py:98`；`agent/main.py:132-134`）。
- **空产出回合是否真的漏发 `member_silent`？** 生产路径不会：`WebSessionRunner` 在 `web/session.py:2226-2227` 已把空文本映射为 `silent`（`is_silent("")` 为真，`agent/team/runner.py:85-88`）。编排器 475-477 的空文本分支只对自定义 runner 可达，应作为防御性契约而非既有缺口。
- **建会话失败是否真的没有终态事件？** 是（`agent/team/orchestrator.py:415-423` 只写 system 日志并 return）；补 `member_failed` 需同时处理 C18 的文案/语义问题。
- **取消是否真的跳过 `round_ended`？** 是（`agent/team/orchestrator.py:361-362` 只 pop，正常出口在 `:378-382`）；但注意 pop 与终态之间的 await 窗口（C2）。
- **`room_state` 是否真的是先订阅后快照？** 是（`web/server.py:651-661`）。
- **`SessionRunner` 是否只有两个实现？** 不是：`web/session.py:2178` 是基础实现，`web/team.py:222` 是子类，`tests/agent/team/test_orchestrator.py:35` 是 Fake；grep 模式因换行漏了第一个（C22）。
- **`run_started` 是否总在群成员 run 上触发？** 不是：resume 分支不调用 `on_run_started`（`agent/loop.py:709-743` vs `:755`），首次从快照恢复的回合以 `before_iteration` 作为 thinking 的首个信号（C12）。
- **同一时刻能否多人发言？** 不能：`_drive` 串行（`agent/team/orchestrator.py:393-399`），规格 1267 钉死。真正并发需改编排语义，另立 change。
- **`slot_skipped` 需要清状态吗？** 不需要：当前 slot 在 `ensure_room_session` 之前就被 membership check 跳过（`agent/team/orchestrator.py:404-409`），该成员从未被置为忙。
- **`session_not_found` / `run_in_progress` 怎么处理？** `WebSessionRunner.run` 返回 `failed`（`web/session.py:2186-2198`），编排器的 `failed` 出口会发 `member_failed` 并重置；无需额外状态出口。

## Open Questions

- **Q1（原 Q1）：移动端成员状态的呈现形态**；**例子**: 390×844 手机，房间 5 名成员（甲/乙/丙/丁/戊），甲正在跑一个 1.2s 的 Bash，其余空闲；现状群聊主区约 94px（390 − 24 padding − 260 sidebar − 12 gap），必须先抽屉化侧栏（约 366px 主区）。A 顶部 56px 横向条：每项 104px，390px 下约 3 人可见，5 人滑一次，时间线少 56px，所有成员始终可见；B 36px 摘要条变 60vh bottom sheet：默认只看到「5 名成员 · 甲 正在使用工具 Bash」，需一次点击；C 输入框上方 44px 只显示非空闲成员 + 「全部成员」按钮，默认看不到空闲成员。**选项**: A（推荐）/ B / C。**我的推荐**: A——最贴合「每个成员实时可见」，且与桌面 presence 共享排序/文案逻辑；B 适合更在意垂直空间的用户，C 适合只关心「谁在忙」的用户。无论选哪个，C15 的 DOM 结构要先定。
- **Q2（原 Q2）：失败/超时是否在状态栏保留可见标记**；**例子**: 甲执行一个 240s 工具后超时，`member_failed {status: "timeout"}` 到达；时间线新增一条「成员 甲 运行失败：超时」的 system 条目。A 立即回「空闲」，不在状态栏保留失败；B 保留「上次失败」红色标记直到甲下一次进入运行或用户重新进入房间。**选项**: A（推荐）/ B。**我的推荐**: A——五档状态语义干净，错误由时间线承载；B 是第六种展示态，要额外定义清除规则，且容易与「成员已空闲」矛盾，建议另立 follow-up。若选 A，同时修 C18 的实时文案（用成员名而不是 persona_id）。
- **Q3（新增）：issue #307 的「多成员并发」按「每人独立一行、但同一时刻至多一人忙」理解，还是要求真正并行？**；**例子**: 房间 3 名成员，用户发「@甲 @乙 @丙 各自说说」；当前编排器严格串行（`agent/team/orchestrator.py:393-399`），甲完整跑完（1.2s 工具 + LLM）才轮到乙，任何时刻只有一行非空闲；issue 的需求方向 3 写「多成员并发：一轮里多个成员各自有独立状态；不是全局只有一个人正在发言」。设计把它列成 Code-Resolved「不做并发」，但这是对 issue 需求的一种解释，且规格 1267 钉死了「同一时刻至多一个成员在发言」。**选项**: A 接受串行 + per-member 独立状态（推荐；本 change 只做状态可观测性，真正并发另立 change 并修改规格 1267）；B 在本 change 内改编排为并行（会违反现有规格、放大成本与失败面，不建议）。**我的推荐**: A，但需要用户明确确认这个解释，因为 issue 原文用了「并发」二字；确认后把设计里的 Code-Resolved 改成 User Confirmation。

## User Confirmation

- 待用户答复（本 change 处于停轮前；Open Questions 尚未确认）。
