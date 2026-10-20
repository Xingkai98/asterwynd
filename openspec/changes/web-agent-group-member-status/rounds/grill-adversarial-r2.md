# 设计对抗 R2: web-agent-group-member-status

## Reviewer

- run id: adversarial-agent-paseo-r2
- 时间: 2026-10-20
- 零记忆: 是
- 方法: 完整读 `AGENTS.md`、本 change 的 proposal/design/tasks/两份 spec delta/`reviews/grill-design.md`/`reviews/grill-adversarial-r1.md`、issue #307 正文与调研 comment；独立核对 `agent/team/orchestrator.py`（`submit_user_message`/`_run_round`/`_drive`/`_run_slot`/`_append_called_slots`/`_emit`）、`agent/team/runner.py`、`agent/hooks/manager.py`、`agent/loop.py`（run/resume、`before_iteration`、`_call_llm` 流式事件、`_execute_single_tool`/`_execute_tool_calls`、`on_completion`/`on_error`）、`web/session.py`（`run_session`/`_run_session_locked`/`WebSessionRunner`）、`web/team.py`（`RoomEventBus`/`TeamSessionPool`/`_WorkspaceRunner`/`TeamService` 快照 helper）、`web/server.py`（事件 sink、房间 WS 握手/关闭）、`web/static/group.js`、`web/static/index.html`、`web/static/style.css`、既有 `openspec/specs/multi-agent-collaboration/spec.md`、相关测试与测试支撑（`tests/support/llm_harness.py` 等）、`.witnessloop` 门禁；只读运行 `npx @fission-ai/openspec@1.4.1 validate --all --strict`（29/29 通过）与 `uv run python scripts/check_openspec_artifacts.py --base-ref origin/master --require-base`（exit 0）。未写实现/测试代码。所有行号相对基线 `48d25f0`。

## F1–F13 修复验证

| 条目 | 当前证据（文件:行号） | 判定 | 备注 |
|---|---|---|---|
| F1 | `design.md:455-460`（删除 `member_speaking` 的头部文案、成员状态交给 presence、`round_ended` 仅在未被 seq 丢弃时更新头部）；`tasks.md:113-118`；`specs/web-ui/spec.md:42-48`；`tasks.md:58-62`（静默/失败后头部不残留的浏览器断言） | 已修复 | 头部单一归属与生命周期已写清；静默/失败/迟到终态三条路径都有落点 |
| F2 | `design.md:609-613`（跨轮迟到终态：gated review、旧终态 seq < 新轮首个 status、JS 丢弃、变异验证）；`design.md:633-636`（握手顺序：阻塞快照发送 + 并发 broadcast、断言锁挡住、变异验证）；`tasks.md:38-41`、`:49-51`；`tasks.md:63-64`（变异验证） | 已修复 | 两条顺序不变量都有确定性构造与变异口径，不再只靠概率性测试 |
| F3 | `design.md:308-310`（建会话失败改调 `_finish_member`）；`design.md:312-313`（统一 helper：重置→seq→flush→终态）；`tasks.md:33-35`、`:85-86` | 已修复 | 建会话失败不再是唯一绕过 helper 的出口 |
| F4 | `design.md:145-148`（`reset_member`/`reset_room_statuses` 表未变不递增、不标脏、不发射）；`tasks.md:81-82`；`specs/multi-agent-collaboration/spec.md:5` 末段 | 已修复（设计侧） | 但 spec 的 room 级 teardown 句仍要求「无条件递增」，见 N2 |
| F5 | `design.md:297-301`（所有出口同构：重置→flush→终态）；`design.md:328-333`（正常路径也 flush）；`tasks.md:81-82` | 已修复（引入新问题） | flush 被放在 `_rounds.pop` 之前，见 N1 |
| F6 | `design.md:496-499`（只调状态条自身 `scrollLeft`，或 `block:"nearest"`，仅目标超出可视区才滚）；`tasks.md:121-122`；`specs/web-ui/spec.md:50-55` | 已修复 | 纵向滚动不被状态条劫持 |
| F7 | `design.md:674-677`（checker 会触发 benchmark smoke，必须真跑并记录）；`tasks.md:153-156` | 已修复 | 口径与 checker 的全文扫描行为一致 |
| F8 | `design.md:821-822`（登记本 change 与 `AGENTS.md` 20 轮口径的差异，不单方面改仓库规则、达 20 轮上报用户）；`tasks.md:16-19` | 已修复 | 差异已显式登记，未把 change 文档当作规则更新 |
| F9 | `reviews/grill-design.md:45` 已无本地绝对路径；但 `reviews/grill-adversarial-r1.md:102` 仍含本地参考仓库绝对路径引用 | 部分 | 主设计记录已清理；R1 对抗记录仍会随 change 提交，见 N6 |
| F10 | `design.md:248-250`（不发送 `phase=idle` 条目；变 idle 时完整表缩减或由终态清除；重置幂等） | 已修复 | 与「相同表不重复」不再打架 |
| F11 | `design.md:484-487`（390px 头部收纳设置/删除、群名可截断、无横向溢出断言）；`tasks.md:59-60`、`:124`；`specs/web-ui/spec.md:71-78` | 已修复 | 头部溢出进入浏览器门禁 |
| F12 | `design.md:488-489`（移动端空状态改为「点左上角群聊」或提供抽屉入口）；`tasks.md:59-60`、`:124`；`specs/web-ui/spec.md:78` | 已修复 | 空状态不再指向被折叠的左侧面板 |
| F13 | `specs/web-ui/spec.md:5`（驱动源括号内补「旧服务端降级时另含 `member_speaking`」） | 已修复 | 清单与降级句不再字面冲突 |

## 新 Findings

### N1（severity: medium）正常路径的 flush 被放在 `_rounds.pop` 之前：收尾窗口内到达的用户消息会被排进一个已经跑完的轮次

- **问题**: `design.md:328-333` 的正常路径伪代码是「同步重置 → `await _flush_status_emits(room.id)` → 计算 termination → `_rounds.pop`」；`tasks.md:86-89` 也写「先于 `_rounds.pop` 同步重置，随后 flush、计算 termination、pop」。但 `design.md:355-356` 又声称「正常路径在 reset 之后、pop 之前没有 await」。这两处直接矛盾：flush 就是 await，而且它要等一次完整的状态广播（含所有房间订阅者）。在这个窗口里，`_rounds` 仍认领该房间，而 `_drive` 已经结束。
- **失败场景**: 一轮的最后一名成员已完成终态，`_run_round` 进入 flush（例如某个订阅者发送慢，flush 被拖长）。此时另一标签页/客户端发来一条消息：`submit_user_message` 看到 `_rounds` 仍活跃，走排队分支（`agent/team/orchestrator.py:318-332`），把消息追加进房间日志、把行首 `@` 插入 `state.slots`（`:493-531`），返回 `queued=True`；但 `_drive` 的循环已经在 `:393-399` 结束，没人再处理这些新 slot。用户看到自己的消息已发出，却没有任何成员回应。更糟的是，若该轮 `state.turns >= state.limit`，新插入的 slot 会让 `state.index < len(state.slots)` 重新成立（`:364-366`），termination 被误算成 `limit`，房间日志会被写入一条假的「本轮因达上限结束」。若未达 limit，消息也只是被记入日志后丢弃，必须再发一条才会开启新轮。
- **证据**: `design.md:328-333`（flush 在 pop 前）、`design.md:355-356`（谎称无 await）、`tasks.md:86-89`（同一顺序）；`agent/team/orchestrator.py:318-332`（排队分支）、`:393-399`（`_drive` 已返回）、`:364-366`（limit 判定）、`:493-531`（插入 slot）。基线里 `_drive` 返回后 `finally` 同步 pop（`:361-362`），没有这个窗口，因此这是 F5 引入的回归。
- **建议修法**: 把释放认领提前到 flush 之前：`reset_room_statuses`（同步，仍先于 pop）→ `_rounds.pop`（同步）→ `await _flush_status_emits` → 计算 termination/review/发 `round_ended`。seq 不变量只要求 reset 先于 pop，flush 放在 pop 之后完全安全（新轮首个状态 seq 仍更大；旧终态被客户端丢弃）。或者显式引入 closing 状态，让 `submit_user_message` 在收尾窗口开启新轮而不是排队。补一条确定性回归：用可阻塞的 send/emit 卡住 flush，在此期间提交一条消息，断言它不会被排进已结束的轮次（而是开启新轮或被处理），并断言不会产生假的 `limit` system 条目。

### N2（severity: medium）「重置幂等（表未变不递增）」与 spec 中三处「teardown 无条件递增 status_seq」互相矛盾

- **问题**: ADDED Requirement 明确规定「成员已处于 `idle` / 表为空时，重置 SHALL NOT 递增序号或产生额外状态事件（幂等）」（`specs/multi-agent-collaboration/spec.md:5`），设计 1.3 也按此实现（`design.md:145-148`）。但同一份 spec delta 还有三处无条件的「递增」：
  1. 快照 Requirement 正文：「轮次结束/取消/意外异常 SHALL 在任何 await 之前同步清空该房间的成员状态**并递增序号**」（`specs/multi-agent-collaboration/spec.md:76`）；
  2. 场景「取消/断线 teardown 对其他标签页可见」：「编排器 SHALL 同步清空全部成员状态**并递增 `status_seq`**」（`:111-112`）；
  3. MODIFIED「房间级互斥与轮次终止」：「系统 SHALL ... 同步清空全部成员状态**并递增状态序号**」（`:126`）。
  正常轮次结束时，最后一名成员的终态已经清空表，room 级 reset 按设计是 no-op、不递增；取消/异常发生在两个 slot 之间时同样可能是空表。三条场景/要求却要求 seq 必增。
- **失败场景**: 实现者照 MODIFIED/snapshot 句字面实现，无条件 `seq += 1`，就会重新产生 F4 要消灭的重复空表事件（正常回合末多一条同表 `member_status`，`design.md:148`/测试「相同表不重复」变红）；反过来照幂等实现，则无法满足这三条 SHALL，任何按 spec 写的「取消后 seq 必增」测试都会红。两种实现必有一边打脸，且归档评审无法机械判定哪边是权威。
- **证据**: `specs/multi-agent-collaboration/spec.md:5`（幂等）、`:76`（递增）、`:111-112`（递增）、`:126`（递增）；`design.md:145-148`、`:328`（「表实际变化才递增」）。R1 的 F4 只修了设计/ADDED 一侧，未清理这三处旧句。
- **建议修法**: 把三处改为「同步清空成员状态；**状态表实际发生变化时**递增 `status_seq`（空表/已 idle 的幂等重置不递增）」，并在取消/断线场景补一句「若表为空，终态可携带当前 seq」。这样既保留旧终态 seq 严格小于新轮首个状态的论证，也不与幂等条款冲突。

### N3（severity: low）迟到 `round_ended` 被 seq 丢弃时，`limit` 轮次的 system 条目不会进入实时时间线

- **问题**: 前端只在收到 `round_ended` 时按 `termination === 'limit'` 重拉时间线（`web/static/group.js:276-287`）。新设计规定旧轮次的 `round_ended` 若 `status_seq < lastStatusSeq` 就整体丢弃（`design.md:270-272`、`:457-459`）。服务端在 pop 之后、review（可能是 LLM）之后才发 `round_ended`（`agent/team/orchestrator.py:361-382`），用户在这段时间发新消息就会先收到新轮的 `member_status`，旧终态被丢弃，于是「本轮因达上限结束」的 system 条目在实时时间线里缺失，直到重连/刷新。
- **失败场景**: 达上限的一轮结束 → review 耗时数秒 → 用户立刻发下一条 → 新轮 `slot_started` 的 status seq 先到 → 旧 `round_ended`（带 limit）被丢弃 → 前端不重拉时间线；用户看不到上限提示。服务端日志是正确的，重连快照会补上，但实时视图与权威日志不一致。
- **建议修法**: 把「丢弃」限定为**状态副作用**：迟到终态仍保留非状态副作用（limit 时重拉时间线、`member_failed` 的系统条目等），或在新轮 `user_message` 到达时重拉一次时间线。至少在设计/测试里明确这一窗口的预期。

### N4（severity: low）测试口径「member_status 的最终表含 thinking/typing」按字面不可实现

- **问题**: `design.md:627-629` 与 `tasks.md:45-47` 写「断言 `member_status` 的**最终表**含 thinking/typing」。回合正常结束后最终表应为空（terminal reset 后所有成员 idle）；若按字面断言最后一条 `member_status` 的 `statuses` 含 thinking/typing，测试必然假红或被迫改成「出现过」。
- **失败场景**: 测试实现者照字面取最后一条事件，得到空表，误判实现失败；或反过来放宽断言，失去对 thinking/typing 的覆盖。
- **证据**: `design.md:627-629`；`tasks.md:45-47`；`design.md:248-250`（idle 条目不发送）。
- **建议修法**: 改成「收集全程 `member_status`，断言至少出现过含该成员 `thinking` 与 `typing` 的表，且回合结束后最终表为空」。

### N5（severity: low）`group_status.js` 纯函数的返回值契约未定义，头部/aria-live 依赖它区分「终态被丢弃」

- **问题**: 设计要求 `round_ended` 的头部文案「仅在终态未被 seq 丢弃时更新」（`design.md:457-459`），aria-live「只在某成员 phase 变化时写入单条文案」（`design.md:533-534`）。但纯函数 API 清单（`design.md:545-552`）只给函数名与输入，没有定义 `applyTerminal` 是否返回「是否接受」、`applyStatusEvent` 是否返回变更集合。实现者若返回 `undefined`，`group.js` 无法在不重复实现 seq 逻辑的前提下决定是否更新头部/播报。
- **失败场景**: 终态被 seq 丢弃后，`group.js` 仍更新头部为「本轮结束」或在 aria-live 里播报旧成员，重新引入 F1 要消除的同视图矛盾；或者为了实现判断，把 seq 规则抄进 `group.js`，破坏「纯函数单一职责」的设计。
- **建议修法**: 在 Decision 10 明确返回值：例如 `applyTerminal(state, data) -> bool`（是否接受）、`applyStatusEvent(state, data) -> {accepted, changed:[persona_id]}`；`applySnapshot` 返回被重置的成员集合（用于不再播报旧状态）。JS 单测覆盖这些返回值。

### N6（severity: nit）R1 对抗记录仍包含本地参考仓库绝对路径

- **问题**: `reviews/grill-design.md` 已清理，但 `reviews/grill-adversarial-r1.md:102` 仍保留本地参考仓库绝对路径引用；该文件会随 change 进入 PR/归档，与「不要把参考仓库路径作为可提交项目资产」的约束不一致。
- **证据**: `reviews/grill-adversarial-r1.md:102`（为避免再次复制，本报告不复述具体路径）。
- **建议修法**: 把 R1 报告中的路径替换为“本地参考仓库（路径略）”一类占位，或在收口合并进 `grill-adversarial.md` 时删除该引用。

## 已确认站得住的部分

- **全量表 + 房间级 `status_seq` 在单进程单事件循环下自洽**：状态变更同步完成、发射器在同一同步段读表与 seq、flush 等待在途发射后再发终态；终态 `status_seq` 为重置后的值，新轮 `slot_started` 必然得到更大 seq。跨成员、跨轮、双标签页、服务端重启、慢客户端（除 N1 的窗口外）逐条核对未找到新的丢事件/错误清空/错误接受旧快照。
- **握手顺序修正正确**：取锁 → 持锁同步构造快照 → 同步 subscribe → 首帧 → 释放锁；构造与订阅之间无 await，订阅后所有发送走同一把每连接锁；握手异常有显式 unsubscribe。R1 的 F2 测试（阻塞首帧 send + 并发 broadcast、变异验证）能确定性锁住该不变量。
- **teardown 的异常矩阵基本闭合**：正常 / CancelledError / 意外异常 / 终态发送失败 / review 抛异常/超时 各有同步重置与尽力通知；取消/异常使用强引用后台 task + 2s 限界，避免在已取消 task 里 await 广播。未发现新的死锁或丢终态（N1 是正常路径的排队窗口，不是 teardown 丢事件）。
- **reducer 规则与代码事实一致**：`before_tool_execute`/`after_tool_execute` 是工具开始/结束的权威信号（`agent/loop.py:1417`、`:1447`）；`iteration_started` 清空在途工具覆盖非 Bash 异常跳过 after 的路径（`:1420-1439`、`:1500-1513`）；resume 无 `run_started`、`before_iteration` 是 thinking 的权威信号（`:709-743` vs `:790`）；`on_error` 不映射 run 终态（`:877`、`:1427`、`:1431`）；非流式无 `assistant_delta`（`:1262-1266`、`:1389-1395`）。
- **Hook/生命周期**：`Hook` 七个方法必须全实现、逐 run 新实例、覆盖整个 run 的 `try/finally` 按身份摘除、进度回调不抛出、连续两次 run 只一组信号的测试口径都正确；三处 `SessionRunner` 实现（`web/session.py:2178`、`web/team.py:222`、`tests/agent/team/test_orchestrator.py:35`）已列全。
- **UI/DOM 的关键结论成立**：presence 放进 `#group-room` 内、头部之后、`.group-room-body` 内；公告移到独立 `#group-room-notice`；presence 取代 chip 行；F1 删除头部发言文案；F6 只动横向滚动；F11/F12 的移动端头部收纳与空状态入口；脚本顺序与 `?v=` 递增；独立 aria-live 区域；`prefers-reduced-motion`。1000/720/390 三个断点在现有 flex 结构上可实现，Q1 的 A/B/C 尺寸描述可信。
- **测试可执行性**：`ScriptedLLM(stream=True)` + `StreamScript` 能产生 `assistant_delta`/`complete`（`tests/support/llm_harness.py:77-104`、`:145-178`）；流式/非流式/工具调用均可脚本化；握手与跨轮用例可抽 helper 或注入可阻塞 send/gated review 确定性复现；node + vm harness 已有先例（`tests/web_tests/test_workflow_graph_js.py`）；浏览器群聊 fixture 成本已在设计中承认。
- **门禁自洽**：OpenSpec strict 29/29 通过；瘦 checker exit 0；RIR `full` 字段完整；backlog 已登记并带 `backlog_updated` 事件；benchmark smoke 按 checker 文本触发口径列入 tasks 6.6；`require_change_for` 覆盖本 change。
- **Q1/Q2/Q3 停轮**：Q1（移动端形态）与 Q2（失败标记）是真实产品取舍；Q3 确实需要用户确认——issue #307 原文用了「多成员并发」，而现行规格钉死「同一时刻至多一个成员发言」，不能由 agent 单方面解释掉。

## Verdict

CHANGES_REQUESTED

- 理由: F1–F13 中 12 条已修复或合理处置，F9 仍有 R1 记录残留（low）；**F5 的修复引入了 N1（medium）**：正常路径 flush 放在 `pop` 之前，收尾窗口内到达的用户消息会被排进已跑完的轮次、可能产生假的「达上限」条目，且与设计自身「reset 之后、pop 之前没有 await」的陈述矛盾。**N2（medium）**：spec delta 的幂等重置与三处「teardown 无条件递增 status_seq」互相矛盾，实现与测试必有一边无法同时满足。
- 没有 high，也没有协议/规格的根本性冲突；N1、N2 都是局部可收敛的修法（N1 把 pop 提前到 flush 前；N2 给三处递增句加「表实际变化时」限定），补齐后重跑一轮对抗即可收口，不判 BLOCKED。
