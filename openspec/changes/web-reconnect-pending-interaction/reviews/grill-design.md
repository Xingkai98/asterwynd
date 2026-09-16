# Grill: web-reconnect-pending-interaction 设计追问

## Reviewer
- run id: grill-web-reconnect-pending-interaction-2026-09-16
- 时间: 2026-09-16
- 对象: openspec/changes/web-reconnect-pending-interaction/{proposal,design,tasks}.md + specs/web-ui/spec.md
- 基线: 主分支 db162aa

## Meta-Review（独立审阅员，2026-09-16）

设计方向正确且证据充分：把 pending 交互与 run 事件出口从「绑死单条 ws」提升为 session 级状态、重连补发、按稳定 id 幂等渲染，三层判断我都用源码复核成立（`GraphEventForwarder` 确是 session 级 + `rebind`；`Question`/`ApprovalRequest.to_event_data()` 确是脱敏后的可重放快照；`renderHistory` 确实整体清空消息区）。调研档位 `full` 名副其实，findings 逐条带一手来源。

但**不建议按当前文本直接进入实现**。有四个具体空洞会直接卡住编码：

1. **D3 的断连检测点根本没有落点**。D3 移除了 drain 循环里唯一能感知断连的信号（`web/session.py:896-902` 的 `await ws_send` 抛异常），把接收循环挪到 session 级，而 `websocket_endpoint` 在 `await run_session` 期间根本不会调用 `ws.receive_json()`（`web/server.py:411`）——FastAPI 不会抛 `WebSocketDisconnect`。design.md:69 只写「`detach()` 解绑（断连时调用）」，没有说谁调用。不补这一条，实现会写成「断连后 sender 集合永不清空」。
2. **`run_session` 早期返回路径的投递语义丢失**。`web/session.py:741-746` 用调用方的 `ws_send` 把 "another run is already in progress" 回给**发起连接**；D3 若把 `ws_send` 参数整体换成 session 级广播 channel，这条错误会广播到别的 tab（`handleTabEvent` 会把 `error` 插进事件所属 tab 的 DOM，`chat.js:404-423` + `549-553`）。
3. **D7 的「终态广播」只有一半路径成立**。`web/server.py:533-552` 的 inline `approval_response` 分支只 `ws.send_json` 回提交者，不走 channel；run 不在时（审批已超时/run 已结束）其他 tab 的卡片永远停在 pending。
4. **前端有一个被低估的 bug**：`renderHistory` 清空 DOM（`chat.js:624`）但不重置 `currentAssistantMsg`（`session_history` 分支 `chat.js:443-447` 未处理），重连后到达的 `assistant_delta` 会写进**已脱离文档的僵尸节点**（`chat.js:503-513` → `appendAssistantContent(currentAssistantMsg, ...)`），用户重连后流式输出**完全不可见**。design 的 Risks 只写了「流式过程不可回放」，低估了这条。

另有一个需求错位：D2/D6 把审批超时定义为「等待总时长 300s」，而 issue #195 原文给的是「断开后留一段可恢复窗口」；两者在「手机离开 >5 分钟」场景下结果相反，且 300s 总时长对**未断连**的桌面用户也是回归（今天审批无限等）。这条必须由用户拍板（Q1）。

补齐 M1–M13（尤其 M1/M2/M3/M4/M7/M9/M10/M12）后可进入实现。

## Confirmed Decisions

- **决策**：D1 两个 handler 的 `_pending` 扩展为保留完整事件载荷、新增只读访问器，且**不新增第二个 pending 槽位**。理由: `ApprovalRequest.to_event_data()` 的载荷取自 `build_approval_request` 生成的 `redacted_args`（`agent/approval.py:132-146`），建立时快照即已脱敏，重放无泄露风险；单槽位与既有 spec 文本一致（`openspec/specs/web-ui/spec.md:267`「每个 Web session 同一时刻 SHALL 只有一个 pending approval」），加第二槽位会与 spec 冲突。；来源: grill-web-reconnect-pending-interaction-2026-09-16

- **决策**：D3 新写 session 级 run 事件出口，**不复用** `GraphEventForwarder`。理由: 复核源码，`GraphEventForwarder.__call__` 是同步 sink、按 workflow 分桶做时间窗合并（`web/session.py:291-341`）、`_send_now` 用 `ensure_future` fire-and-forget 且异常一律吞（`web/session.py:350-376`）；run 事件需要 `await` 的顺序投递（`assistant_delta` 顺序敏感）与失败感知，语义确实不同，硬塞合并/分桶会污染 run 事件路径。；来源: grill-web-reconnect-pending-interaction-2026-09-16

- **决策**：D4 补发必须排在 `session_resumed` → `session_history` **之后**。理由: `renderHistory`（`chat.js:623-631`）第一行就是 `messagesEl.textContent = ''`，早于它补发的卡片会被整体清掉；`bind_workflow_graph_channel` 的先补发后 `rebind` 顺序（`web/server.py:35-59`）是同类范式的既有正确实现。；来源: grill-web-reconnect-pending-interaction-2026-09-16

- **决策**：D5 用 `approval_id` / `question_id` 作幂等 key，并在 `renderHistory` 清空消息区时同步清空 `approvalCards` / `questionCards`。理由: 两个 id 都是服务端生成的 uuid（`agent/approval.py:136`、`agent/tools/builtin/ask_user.py:46`），天然稳定；现有渲染函数**确无**去重守卫（`chat.js:815-880`、`906-991` 直接 append DOM + `set`）且 `renderHistory` 不清 map，会留指向已移除 DOM 的僵尸条目。；来源: grill-web-reconnect-pending-interaction-2026-09-16

- **决策**：D7 run 事件出口取广播语义，而非沿用 `GraphEventForwarder.rebind` 的「最后连接胜出」。理由: `rebind` 只是覆盖单一 `_ws_send`（`web/session.py:275-278`），若 run 出口沿用，第二个 tab 一连上就抢走第一个 tab 的事件流，比现状（每次 run 有自己的 queue，`web/session.py:764`）更差；多连接广播 + 首答胜出的方向与调研 finding 6 一致。；来源: grill-web-reconnect-pending-interaction-2026-09-16

- **决策**：D8 保留 issue #193 回归测试 `test_run_session_survives_ws_send_failure_after_disconnect` 的「run 正常返回、锁已释放」断言。理由: 该断言（`tests/web_tests/test_session.py:632-636`）在新语义下仍成立——run 不再因断连被 cancel，锁由 run 自己跑完后释放；测试需要的是补充断言而非删除。；来源: grill-web-reconnect-pending-interaction-2026-09-16

## Open Questions

- **Q1: 审批的可恢复窗口到底怎么算——「总等待时长 300 秒」还是「断开后宽限窗口」？**
  - 场景：你在手机上收到一个高风险工具的审批卡片 → 锁屏去接孩子 → 20 分钟后回来点「Approve」。**改前**（审批无超时，`web/session.py:114-127` 没有 `wait_for`）：批准生效，工具执行。**按当前 design D2/D6**（`design.md:57`、`design.md:99-106`，`approval_timeout_seconds=300` 从 pending 建立时计时）：20 分钟 > 300 秒 → 判定 `unavailable` → agent 收到「审批失败」的答复继续跑，工具被拒。更值得注意的是**桌面端也是回归**：今天挂着卡片 10 分钟回来点批准是生效的，改后失效。issue #195 原文写的是「ws 断开**不应**立刻 fail_pending（**或改为「断开后留一段可恢复窗口」**，超时才判定失败）」——即它期望的是「断连宽限」，而 D6 明确否决了「断连重置计时」。
  - 需要你拍板：审批默认等多久？三个选项：(a) 保持 design 现状「总时长 300s，连接存亡不影响计时」；(b) 「断连后 300s 宽限，但连续连通时无限等待」；(c) 「审批继续无限等待，只对提问加超时」（最小改动，零回归，但设计里 D2 提到的「无人重连则 run 永久挂住」风险保留）。
- **Q2: 断连期间正在流式输出的 assistant 内容，要不要在重连补发时一起带回来？**
  - 场景：你在手机上发了一个长问题，agent 流式打字打到一半（比如已经输出「我先读一下 web/session.py 里…」）你切后台；1 分钟后切回来重连。服务端只发 `session_history`，而 `session_history` 来自 `session.messages`——**流式期间 assistant 消息还没写进 `messages`**（`agent/loop.py:736`/`:750` 只在 LLM 调用结束后 append）。所以重连后看到的可能是：你的提问 + 一个**从中间开始、缺前半段**的 assistant 气泡（甚至按 M12 是空的僵尸气泡）。选项：(a) 接受（design 现状，但必须先把 M12 的僵尸气泡修掉）；(b) 让 `session_history` 额外附上当前 run 的 in-flight assistant 文本（服务端做得到——`assistant_delta` 事件本身带累计 `content`，`agent/loop.py:1146-1148`，出口缓存即可）。
- **Q3: 多 tab 的「卡片失效」保证边界在哪？**
  - 场景：手机和桌面同时开着同一个 session。手机上弹出审批卡片，但**你已经用另一台设备/另一个 tab 处理过了**（或者卡片因为超时已失效）。此时桌面那张卡还显示 pending、按钮可点。按 D7 设计「作答成功后向所有连接广播终态」，但终态事件只在 run 仍活着时经 queue 广播；run 不在时走的是 `web/server.py:533-552` 的 inline 分支，**只回提交者**。选项：(a) 接受「run 存活时才有广播保证」，把这条收窄写进 spec delta；(b) 要求 inline 分支也广播（需要把 `ws_send` 换成 channel，实现量更大）。
- **Q4: 断连后 run 要不要继续跑到结束？**
  - 场景：你切后台前 agent 刚进入一个 12 步的工具链（或刚被判 `unavailable` 的审批后继续跑）。按 D8/非目标，run 会**在没有任何观察者的情况下继续消耗 token 跑到结束**；你 5 分钟后切回来，可能看到一大段自己没见证过的过程，同时想发新消息会被拒（`web/session.py:741-746` 回 "another run is already in progress"）。选项：(a) 接受（design 现状，理由是「这正是切后台继续跑的期望行为」）；(b) 仅在「断连且无 pending」时暂停/中止 run（实现复杂度显著上升）；(c) 接受继续跑，但前端把 "another run is already in progress" 的文案改得可读（当前是原始英文，`chat.js:549-553` 直接插错误消息）。

## 必须修改（已/待整合进 design.md）

- **M1（必须改，阻塞实现）D2/D6 的超时语义是需求错位 + 未声明回归**。`design.md:57-61`、`design.md:99-106`、`design.md:137`。证据：审批当前**无**超时（`web/session.py:114-127` 直接 `await future`），提问有 300s（`web/session.py:189`）。加 300s 总时长后，桌面端「挂 6 分钟回来点批准」从生效变为 `unavailable`，这超出 issue #195 范围且未在 Risks 里被标为「行为变更」。改法：由 Q1 拍板；若维持总时长语义，Risks 必须写成明确的「已知行为变更（非本 issue 引入但由本 change 引入）」+ 在 proposal 的 Impact Analysis「兼容性」行补一句。
- **M2（必须改，阻塞实现）D3 缺断连检测点与 drain 循环存续约束**。`design.md:67-69`。证据：现断连检测只有两处——drain 的 `await ws_send` 抛异常 `break`（`web/session.py:896-902`）与 `ws_receive()` 抛异常（`web/session.py:881-884`）；D3 移除前者，而 `websocket_endpoint` 在 `await run_session(...)` 期间不会调用 `ws.receive_json()`（`web/server.py:411`），FastAPI 不会抛 `WebSocketDisconnect`。必须写明：(1) session 级 receiver 是唯一断连检测点，异常时对该连接 `channel.detach(connection)`；(2) drain 循环**永不退出**、永远消费 `queue`（`web/session.py:764` 是**无界** `asyncio.Queue()`，若实现成「无连接就不 drain」会内存无界增长）；(3) 该行为要有测试。
- **M3（必须改）`run_session` 早期返回的投递语义**。`web/session.py:741-746`。D3 若把 `ws_send` 参数整体替换为广播 channel，锁占用错误会广播到所有 tab，而 `handleTabEvent`（`chat.js:404-423`）会把它渲染进事件来源 tab 的 DOM——别的 tab 会莫名出现错误消息。改法：保留 per-call sender（例如 `run_session(..., reply_send=...)`）或在 design 里显式声明广播语义并说明可接受。
- **M4（必须改）D7 终态广播有两条路径，只有一条走 channel**。`design.md:114`（「作答成功后向所有连接广播终态」）vs `web/server.py:533-552` / `:554-564`（inline 分支只 `ws.send_json` 回提交者）。必须二选一：让 inline 分支也广播，或在 design + spec delta 里收窄保证（并让 spec delta 的「多连接首答者胜」scenario 补一句「run 不在时不保证其他连接收到终态」）。
- **M5（必须改）D5 的前端「可见反馈」在当前代码结构下做不到**。证据：`chat.js:980-982` 在调用 `sendQuestionAnswer` **之前**就 `submitBtn.disabled = true; submitBtn.textContent = 'Submitted'`，而 `sendQuestionAnswer` 在 ws 非 OPEN 时静默 return（`chat.js:994`）——用户会看到 "Submitted" 但什么都没发出去，与 spec delta 新 scenario「ws 未就绪时提交不被静默丢弃」（`specs/web-ui/spec.md:133-138`）直接冲突。审批侧同理（`chat.js:883-889`）。改法：判定顺序改为**先查 ws、再改 UI**；并在 tasks 4.3 里点名这两个函数。
- **M6（应该改）D5 漏了第二条清空路径**。`chat.js:471-473`（`command_result` 的 `metadata.command === 'clear'`）同样 `messagesEl.textContent = ''` 却不清卡片注册表。tasks 4.2 只覆盖 `renderHistory`。
- **M7（必须改）D4 的补发载荷读取需要原子快照**。`design.md:85-87` 说「先记录补发时的 pending id，只补这一条」，但载荷来自 D1 的访问器（第二次读取）。`_pending` 在 resolve 的 `finally` 里被清（`web/session.py:126-127`、`:196-197`），两次读取之间会得到「有 id 无载荷」。改法：访问器返回 `(id, payload)` 的原子快照，design 写明这一点；tasks 3.1 的纯函数签名相应固定。
- **M8（必须改）spec delta 缺「run 进行中断连重连后发消息」的 scenario**。current spec 的「同一 session 并发发送被拒绝」（`openspec/specs/web-ui/spec.md:414-423`）只覆盖同连接并发；新语义下「run 因断连继续跑 → 用户重连后发消息」是新的高频路径（见 Q4），应补 scenario。（注：**MODIFIED requirement 与 current spec 不冲突**——我实跑 `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`，当前 30/30 通过，delta 文本是 current `openspec/specs/web-ui/spec.md:265-290` 的超集且保留了「只有一个 pending approval」那句。）
- **M9（必须改，checker 现在真的报错）tasks.md 缺 benchmark smoke**。我实跑 `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py`，输出：
  `ERROR: web-reconnect-pending-interaction: tasks.md missing benchmark smoke verification item for coding-agent core change`。
  触发原因：`proposal.md:10` 声明了 `- agent-runtime`，命中 `BENCHMARK_SMOKE_CAPABILITIES`（`scripts/check_openspec_artifacts.py:35-37`）；判定只看 proposal 文本，与是否真改 `agent/` 无关。改法：加一条含 "benchmark" 与 "smoke" 的 task（`scripts/check_openspec_artifacts.py:640-642` 只做这两个词的包含判断）。
- **M10（必须改）tasks 缺 `index.html` 缓存版本号更新**。`chat.js` 改动必须 bump `web/static/index.html:125` 的 `/static/chat.js?v=21` → `?v=22`；且 `tests/web_tests/test_server.py:438` 硬断言 `"/static/chat.js?v=21"`，不同步改测试会红。历史先例：commit `31c644d` 的 v20→v21。
- **M11（应该改）`remove_session` 未纳入新 channel 的 detach**。`web/session.py:697-703` 只 `detach()` 了 `graph_forwarder`；新 channel 必须在同处摘掉，否则 reset / hub DELETE 后旧 ws sender 仍被 session 引用。
- **M12（必须改）重连后 in-flight 流式内容会写进僵尸 DOM（design Risks 低估）**。证据链：`renderHistory` 清空 `messagesEl` 子节点（`chat.js:624`）但不重置 `currentAssistantMsg`，`session_history` 分支（`chat.js:443-447`）也不重置；随后到达的 `assistant_delta`（`chat.js:503-513`）在 `currentAssistantMsg` 非 null 时直接 `appendAssistantContent(currentAssistantMsg, ...)` 写进已脱离文档的节点——用户重连后看不到任何流式增量；`llm_response` 的 `streamed` 分支又直接 `break`（`chat.js:490-492`）不复原。改法：在 `session_history` 分支重置 `currentAssistantMsg = null`，并把这条写进 D5 + tasks 4.x + 测试 5.5。
- **M13（应该改）文档影响面要点名**。D2 的超时语义 + 重连补发是用户可见事实变化，至少涉及 `README.md:336`（Web Chat 功能描述）、`README_EN.md:337`（README 改必须同变更同步英文，AGENTS.md 维护规则）、`docs/architecture.md:90`（「每个 Web session 同一时刻只允许一个 pending approval」段落）。tasks 6.4 应点名这三处而不是泛写「相关段落」。
- **M14（建议）tasks 0.1 的措辞不满足 checker 字面匹配**。`tasks.md:5` 写的是「跑 `/grill`」，而 `scripts/check_openspec_artifacts.py:645-651` 的 fallback 只认 `grill-with-docs` / `batch-grill` / `等价设计追问`。有了本文件（≥3 条 Confirmed Decisions）会走证据分支绕过该检查，但建议顺手把 0.1 改成含 `batch-grill` 字样，避免将来证据文件缺失时连环报错。
- **M15（建议）D6 新配置项需要正整数校验**。`web/session.py:99` 建议的 `question_timeout_seconds` / `approval_timeout_seconds` 若配 0 或负值会退化为「立即超时」。`_parse_web_config`（`agent/config.py:1294`）目前只解析 `workspaces`，需按既有 `_validate_positive_int`（如 `agent/config.py:772-789` 的用法）补校验，并加配置测试。

## 风险

- **无界 queue + 无消费者**：`web/session.py:764` 的 `asyncio.Queue()` 无容量上限。若实现把 drain 循环写成「出口未绑定就退出」，断连期间事件会无界堆积到内存。必须靠 M2 的「永远消费」约束兜住，并加回归测试。
- **reset/cancel 在 run 期间的语义窗口**：run 期间消息由 session 级 receiver 消费，`reset` 只做 `fail_pending`（`web/session.py:869-876`），**不做会话替换**（替换在 endpoint 分支 `web/server.py:566-584`，run 期间不执行）。新语义下用户点 reset 后 run 仍会继续跑到结束、且 pending 已失败，行为需要一次实测确认，design 未覆盖。
- **审批 fail-closed 后的连锁**：超时 → `UNAVAILABLE` → `agent/loop.py:873-879` 生成 `[Approval unavailable: ...]` 并标记 `approval_unavailable`，run 继续。若同一轮有多个高风险工具，会逐个各等 300s，总耗时可能远超用户预期。
- **`unavailable` 的语义混淆**：现有 `unavailable` 同时表示「无匹配 pending」（`web/server.py:544-549`）、「另一个审批已 pending」（`web/session.py:118-120`）与新的「超时」。前端 `renderApprovalResponse` 一律显示 `data.status`（`chat.js:903`），用户看到裸英文状态。建议 spec delta 或 design 里区分 reason。
- **补发与 `bind_workflow_graph_channel` 的相对顺序未定**：`design.md:77` 说两者先后皆可，但 `bind_workflow_graph_channel` 内部先补发快照再 `rebind`（`web/server.py:50-59`）；若 pending 补发排在它**之后**，则该函数内的补发发生在 `renderHistory` 之后、pending 卡片之前——顺序仍满足，但两者都在同一次事件循环内连续推，前端 `handleTabEvent` 逐条处理无并发问题。**结论：无冲突**，但建议 design 直接钉死顺序以免实现者自由发挥。

## User Confirmation

（待主 agent 停轮把 `## Open Questions` 逐条抛给用户；用户答复后按 `- **Q<n>**: 用户答复：<实质内容>；确认时间: <date>` 格式追加于此。）

## Codex Recommendations

- 把「连接」建模成显式对象（`ConnectionHandle{send, detach}`）而不是往集合里塞裸 callable：M2 的 per-connection detach、M4 的 inline 路径统一广播都依赖「能定位到具体连接」。
- 补发顺序建议在服务端测试里做**序列断言**（重连后前 N 条事件的类型序列 == `["session_resumed","session_history", ...卡片...]`），比「最终收到了卡片」更能锁住 `design.md:79-83` 的排序不变量——这也是调研 finding 5 的竞态教训唯一可机械固化的形式。
- 前端新增断言优先用 Playwright 行为断言（本项目已有 `tests/web_tests/test_multi_session_browser.py` 的真实 ws 断连骨架，如 `test_multi_tab_exit_does_not_affect_other_tab_reconnect`），源码字符串断言（`tests/web_tests/test_server.py:524` 风格）只作补充——字符串断言对 `chat.js` 重构脆弱，且历史上出现过「只在 CI 挂」的着色类陷阱。
- 若采纳 Q2 的选项 (b)，注意 `assistant_delta` 的累计 `content` 来自 `agent/loop.py:1145-1148`，缓存点应放在新 channel 里按 run 维度存，不要侵入 AgentLoop。
