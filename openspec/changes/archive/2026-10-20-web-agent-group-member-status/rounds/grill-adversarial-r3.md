# 设计对抗 R3（收口）: web-agent-group-member-status

## Reviewer

- run id: adversarial-agent-paseo-r3
- 时间: 2026-10-20
- 零记忆: 是
- 方法: 完整读 `AGENTS.md`、本 change 的 proposal / design / tasks / 两份 spec delta /
  `reviews/grill-design.md` / `reviews/grill-adversarial-r1.md` / `reviews/grill-adversarial-r2.md`；
  用 `gh api` 读 issue #307 正文与全部评论；独立核对 `agent/team/orchestrator.py`（`submit_user_message`
  / `_run_round` / `_drive` / `_run_slot` / `_append_called_slots` / `_emit`）、`agent/team/runner.py`、
  `agent/hooks/manager.py`、`web/session.py`（`run_session` / `_run_session_locked` / `WebSessionRunner`）、
  `web/team.py`（`RoomEventBus` / `_WorkspaceRunner` / `MemoryReviewService.on_round_end`）、
  `web/server.py`（房间 WS 握手、断线取消）、`web/static/group.js`、`web/static/index.html`、
  `web/static/style.css`、`agent/team/roomlog.py`、既有规格、相关测试与测试支撑；
  只读运行 `npx @fission-ai/openspec@1.4.1 validate --all --strict`（29/29 通过）与
  `uv run python scripts/check_openspec_artifacts.py --base-ref origin/master --require-base`（exit 0）。
  未写实现/测试代码。所有代码行号相对基线 `48d25f0`。

## N1–N6 修复验证

| 条目 | 当前证据（文件:行号） | 判定 | 备注 |
|---|---|---|---|
| N1 | `design.md:330-335`（reset → pop → flush → termination → review → emit）；`design.md:357-361`（reset/pop 之间无 await，flush/review/终态在 pop 之后）；`design.md:624-626`（阻塞 flush 的确定性回归 + 变异口径）；`tasks.md:89-94`（2.7 同序）、`tasks.md:42-44`（1.2.2） | 已改序，但**引入了新 high**（X1） | 顺序本身符合 R2 的修法，「收尾窗口不吞新消息」的构造也可行；但 `finally` 的兜底 pop 没有身份判断，会在新一轮已认领后把它 pop 掉。见新 Findings X1。测试还需补「新轮认领不被旧轮 finally 抢走」的断言（见 L4）。 |
| N2 | `specs/multi-agent-collaboration/spec.md:76`（「状态表实际发生变化时 SHALL 递增……空表/已全部 idle 时 SHALL NOT 递增」）、`:111`（同口径）、`:126`（同口径）；`design.md:145-148`、`:330`；`spec.md:5` 幂等条款 | 已修复 | 三处无条件递增已全部改为条件递增，与 ADDED Requirement、设计 1.3/5.2 自洽。空表取消终态携带当前 seq 的规则见 `spec.md:126`。残余措辞见 L5（nit）。 |
| N3 | `design.md:271-275`（迟到 `round_ended(limit)` 仍重拉时间线、不改状态）；`design.md:561-563`（`applied=false` 只抑制头部/aria-live）；`tasks.md:121-127`（4.3 明确覆盖） | 已修复 | 行为口径清楚。缺少一条显式回归测试（L3）。 |
| N4 | `design.md:640-642`（断言事件流中**曾出现** thinking/typing，最终表与快照一致，不能要求最终表仍含）；`tasks.md:48-50`（1.4 同口径） | 已修复 | 与「idle 成员不发送条目」不再矛盾。 |
| N5 | `design.md:552-563`（逐函数返回契约：`applyStatusEvent`/`applyTerminal` 含 `applied`，`applySnapshot`/`applySpeakingFallback` 为 `{state, changed}`；`describeChange`；`applied=false` 时仍执行 limit 重拉）；`tasks.md:112-117`（4.1） | 已修复（有 low 级措辞不一致） | tasks 4.1 把契约泛化为「apply* 均返回 `{state, changed, applied}`」，与 Decision 10 的逐函数定义不完全一致，见 L2。 |
| N6 | 对 change 目录全量 `grep -RnE '/home/|/Users/|/mnt/|reference-repos|agent-study'` 无命中（含 `reviews/grill-adversarial-r1.md` / `r2.md`） | 已修复 | R1/R2/grill-design 中的本地绝对路径均已清理。 |

## F1–F13 关键项复核

| 条目 | 判定 | 备注 |
|---|---|---|
| F1 头部文案单一归属 | 未被破坏 | `design.md:459-464` 仍删除 `member_speaking` 的头部文案、`round_ended` 仅在终态未被丢弃时更新头部；`tasks.md:125-126`；`specs/web-ui/spec.md:42-48`、`:5`。 |
| F2 两条确定性顺序测试 | 未被破坏 | 跨轮迟到终态：`design.md:619-625`、`tasks.md:38-41`；握手首帧：`design.md:646-650`、`tasks.md:53-55`；两条都保留变异验证。 |
| F4 重置幂等 | 未被破坏 | `design.md:145-148`、`tasks.md:85-86`、`spec.md:5`；与 N2 的三处修法一致。 |
| F5 正常 `round_ended` 前 flush | 未被破坏 | `design.md:297-303`、`:328-335`、`tasks.md:85-86`；flush 仍在终态之前，只是移到了 pop 之后（N1 要求的顺序）。 |
| 其余 F3/F6/F7/F8/F10–F13 | 未被破坏 | F3 `_finish_member`（`design.md:310-312`）；F6 仅横向滚动（`:503-505`）；F7 benchmark smoke 触发口径（`:688-691`、`tasks.md:162-165`）；F8 20 轮差异登记（`:840-841`、`tasks.md:16-19`）；F10 idle 条目措辞（`:248-250`）；F11/F12 390px 头部与空状态（`:491-496`、`specs/web-ui/spec.md:71-78`）；F13 降级源清单（`specs/web-ui/spec.md:5`）。 |

## 新 Findings

### X1（severity: high）`_run_round` 的 `finally` 兜底 pop 没有身份判断：收尾窗口内启动的新一轮会被旧轮抢走房间认领，导致同房间并行两轮

- **问题**: N1 的修法把正常路径的 `_rounds.pop` 提前到 flush 之前（`design.md:331`），这是对的；但伪代码的 `finally` 仍无条件执行 `self._rounds.pop(room.id, None)`（`design.md:350`），而 `_rounds` 只以 `room_id` 为键（`agent/team/orchestrator.py:295`）。设计同时明确承认「flush、review 与正常 `round_ended` 的发送在 pop 之后，**可能放行新一轮**」（`design.md:357-359`）。于是旧轮在 `try` 内已经释放认领、新一轮在新一轮任务里重新写入 `_rounds[room_id]` 之后，旧轮的 `finally` 仍会在自己返回时把**新一轮的 `_RoundState`** 删掉。`tasks.md:95-96` 要求「`RoundResult` 与 `is_round_active` 语义不变」，该伪代码在时间窗口成立时违反它。
- **失败场景**（正常路径，无需异常）：
  1. 轮次 R1 的 `_drive` 结束，`reset_room_statuses`（seq=N）→ `_rounds.pop`（同步）完成；
  2. R1 停在 `await _flush_status_emits(room.id)`（`design.md:332`），此时某个房间订阅者发送慢（`RoomEventBus.broadcast` 逐连接 `await`，`web/team.py:112-121`），flush 可能持续数秒；
  3. 用户在另一标签页发来消息 M2。`submit_user_message` 看到 `_rounds` 为空（`orchestrator.py:318-333`），`_run_round` 在任何 await 之前把 `_rounds[room.id] = R2`（`:352`）；
  4. R1 的 flush/review/`round_ended` 完成后返回，`finally`（`design.md:350`）把 `_rounds[room.id]` 删掉——删的是 R2；
  5. R2 仍在 `_drive` 中，但 `is_round_active(room)` 已为假。此时用户再发 M3，`submit_user_message` 再次看到空认领并开启 R3。R2 与 R3 并发驱动同一房间：两条 `member_speaking`、房间日志交错、两个 `round_ended`，并与 `specs/multi-agent-collaboration/spec.md:126` 的「同一房间同一时刻 SHALL 至多存在一个进行中的轮次」直接冲突。副作用还包括 R2 期间的 `room_state.round_active` 为 false（`web/server.py:659`），重连/新标签页会收到「无轮次」快照。
- **证据**: `design.md:331`、`:350`、`:357-359`；`tasks.md:91-96`；`agent/team/orchestrator.py:295`、`:318-333`、`:352`、`:361-362`；`web/team.py:112-121`；`web/server.py:659`；`specs/multi-agent-collaboration/spec.md:126`。
- **建议修法**:
  - 两处 pop 都做**身份判断**，例如 `if self._rounds.get(room.id) is state: self._rounds.pop(room.id, None)`（正常路径与 `finally` 共用一个小 helper），取消/异常路径同样走它；这样兜底 pop 只清理「仍是本轮」的认领。
  - 在 N1 的回归里补断言：R1 返回后、R2 仍 gated 时，`orchestrator.is_round_active(room)` SHALL 为真；此时提交第三条消息应得到 `queued=True` 且不新增第三个 `_run_round`。变异验证：去掉身份判断 → 变红。
  - 顺带把 termination 计算与 limit system 条目追加移到 pop 之前（同步段），见 L1。

### L1（severity: low）termination 计算与「达上限」system 条目被移到 flush 之后，新轮可能先写入自己的 `user_message`

- **问题**: `design.md:332-335` 把 `termination` 计算与 limit 日志追加放在 flush 之后；`agent/team/orchestrator.py:364-366` 在该位置追加 `LIMIT_ENTRY_TEXT`。pop 提前后，新轮可以在 flush 窗口内写入自己的 `user_message`；R1 随后追加的「本轮因达上限结束」会排在新用户消息之后。R2 的 `state.start_seq` 早于该条目，`build_injection` 会把 seq ≥ start_seq 的条目算作「本轮」（`agent/team/roomlog.py:118-132`），R2 的成员提示可能看到上一轮的 limit 条目。基线也在 pop 之后追加，但新设计把该窗口从同步段拉长到一次完整 flush。
- **失败场景**: 达上限的 R1 在 flush 中遇到慢订阅者；用户发 M2 开启 R2；R2 的 user_message 先落日志；R1 再追加 limit system 条目。房间时间线顺序错乱，R2 首个成员的 prompt 中出现「[system] 本轮因达上限结束」。
- **证据**: `design.md:332-335`、`:357-359`；`agent/team/orchestrator.py:364-366`、`:426`；`agent/team/roomlog.py:118-132`。
- **建议修法**: 在 pop 之前（reset 之后、无 await 的同步段）完成 termination 计算与 limit system 条目追加，再 pop → flush → review → emit；这些步骤都是同步的，不违反 N1 的顺序不变量。

### L2（severity: low）tasks 4.1 的返回契约泛化与 Decision 10 的逐函数契约不一致

- **问题**: `design.md:554-557` 只对 `applyStatusEvent` / `applyTerminal` 定义了 `applied`，`applySnapshot` / `applySpeakingFallback` 返回 `{state, changed}`；`tasks.md:114-116` 写「apply* 返回 `{state, changed, applied}`」。实现/测试若按 tasks 写，会与设计不一致。
- **失败场景**: JS 单测按 tasks 断言 `applySnapshot(...).applied === true`，而实现按 Decision 10 返回 `undefined`；或实现者为了满足 tasks 给快照加 `applied`，使「新快照即使 seq 更小也必须接受」的语义变得含糊。
- **证据**: `design.md:552-563`；`tasks.md:112-117`。
- **建议修法**: 把 tasks 4.1 改为「`applyStatusEvent` / `applyTerminal` 返回 `{state, changed, applied}`（终态另含 `clearedAll`）；`applySnapshot` / `applySpeakingFallback` 返回 `{state, changed}`」。

### L3（severity: low）N3 的「迟到 limit 终态仍重拉时间线」没有对应的回归测试

- **问题**: 行为已写进 `design.md:271-275` 与 `tasks.md:123-124`，但 Testing Strategy 的编排器/WS/JS/浏览器清单（`design.md:596-680`、`tasks.md:28-68`）没有一条覆盖「`applied=false` 的 `round_ended(limit)` 仍触发时间线重拉」。该窗口正是 review 延迟 + 用户立刻发新消息的组合，靠人工验证不可靠。
- **失败场景**: 实现者把「迟到终态整体丢弃」理解成连 timeline 重拉也跳过；现有测试全绿，用户达上限后看不到「本轮因达上限结束」。
- **证据**: `design.md:271-275`、`:640-654`；`tasks.md:48-66`、`:121-127`。
- **建议修法**: 在浏览器群聊 fixture（或可注入 reload 计数器的 JS 测试）中构造「先应用新轮高 seq 状态，再喂旧轮 limit 终态」，断言 `applied=false` 但 timeline reload 被调用一次。

### L4（severity: nit）N1 的 gate 应明确为一次性，并给测试加有界等待

- **问题**: `design.md:624-626` / `tasks.md:42-44` 说「阻塞 `_flush_status_emits`」。若在同一实例上无差别阻塞该方法，新轮的 `_finish_member` 也会调用它；测试若在放行前 `await` 新一轮的 `submit_user_message`，会死锁。变异为「pop 移回 flush 之后」时，消息走排队分支，测试若在无超时地等待「新一轮启动」也会挂起而不是干净变红。
- **建议修法**: 用只对首次调用生效的 gate（或按 room/任务区分），并给所有 `await` 加 `asyncio.wait_for`；变异验证要求「断言失败」而不是「CI 超时」。同时按 X1 增加认领存活断言。

### L5（severity: nit）N2 修复后 design 4.3 的叙述仍写「递增 seq」无条件

- **问题**: `design.md:283-284` 写「服务端在 pop 之前同步重置状态并递增 seq」；严格不等式结论仍成立（空表时新轮 `slot_started` 仍会 +1），但与 1.3/5.2 的「表实际变化才递增」措辞不一致。
- **建议修法**: 改为「表实际变化时递增；空表时保持当前 seq，新轮首个状态仍严格更大」。

## 已确认站得住的部分

- **N1 修复的核心时序本身正确，且 seq/表读取没有新错配**。`_flush_status_emits` 不自行构造 payload；发射器在**同一同步段**读取当前完整表与当前 `status_seq`（`design.md:293-295`），终态使用 reset 时捕获的 `teardown_seq`（`design.md:335`）。因此旧轮 flush 期间即使新一轮已发出状态，也不会出现「旧 seq 配新表」；flush 可能顺手排空新轮的 dirty 变化，但那会用新 seq 发出，语义正确。唯一的新增副作用是房间认领被 `finally` 抢走（X1）。
- **「旧终态 seq < 新轮首个状态 seq」在幂等重置下仍成立**。空表时 `reset_room_statuses` 返回当前 seq 且不递增；新轮的 `slot_started`（idle→running）必然使 seq +1，因此旧 `round_ended` 的 seq 严格更小。若新轮首个 slot 被 `slot_skipped` 跳过而没有任何状态变化，则**不存在**新状态事件，旧终态按 `>=` 规则应用、清空房间是正确结果。
- **N2 的相等场景客户端规则正确**。`member_status` 用 `<=` 丢弃相等序号（幂等重复无副作用），终态用 `<` 丢弃、相等则应用；同一个 reset 产生的空表状态与终态同 seq，终态应在其后被应用；跨轮新状态严格更大，不会被旧终态误清。空表取消时终态携带当前 seq（`spec.md:126`），客户端按 `>=` 应用，正确。
- **迟到 limit 终态的 timeline 重拉不会丢「尚未落日志」的新轮内容**。`user_message` 与 `member_post` 都是先写房间日志、再发事件（`orchestrator.py:354-359`、`:468-473`）；整体重拉只可能包含已落日志的条目，尚未落日志的内容客户端本来也没显示；状态不在 timeline。唯一窄窗口是「重拉响应在服务端已构造后、客户端应用前，新条目事件先到」——该竞态基线已有，设计已用 seq 幂等追加防重复（`design.md:477-479`、`tasks.md:127`），未因本轮修改恶化。不构成 medium。
- **N1 回归测试在当前编排器/FakeRunner 上可实现**：用 gated `on_event` sink 卡住状态广播（`RoomEventBus` 逐连接 await 的形态可在编排器测试里用 sink 模拟），或 monkeypatch `_flush_status_emits`；FakeRunner 只需新增 `on_progress` 形参（`tasks.md:45-47`）。注意 L4 的 gate 问题。
- **握手、快照与旧端兼容仍然成立**：锁内同步构造快照 → 订阅 → 首帧、整段 try/finally、订阅后所有发送同一把锁（`design.md:395-427`）；旧前端未知事件落 `default: break`（`web/static/group.js:289-290`）；`round_ended` 新 termination 走既有「本轮结束」分支（`group.js:276-288`）。
- **reducer 与代码事实一致**：工具开始/结束用 `before_tool_execute` / `after_tool_execute`（`agent/loop.py:1417`、`:1447`）；`iteration_started` 清空在途工具覆盖非 Bash 异常跳过 after（`:1420-1439`、`:1500-1513`）；resume 无 `run_started`、`before_iteration` 为 thinking 权威（`:709-743` vs `:790`）；非流式无 `assistant_delta`（`:1389-1395`）；空文本在生产 `WebSessionRunner` 已归一为 silent（`web/session.py:2226-2227`）。
- **Hook/生命周期**：完整 7 方法、逐 run 新实例、覆盖整个 run 的 try/finally 按身份摘除、进度回调不抛出、三处 `SessionRunner` 实现（`web/session.py:2178`、`web/team.py:222`、`tests/agent/team/test_orchestrator.py:35`）均在设计与 tasks 中列全。
- **门禁与文档自洽**：OpenSpec strict 29/29 通过；瘦 checker exit 0；RIR `full` 字段完整；backlog 已登记 #307 并有 `backlog_updated` 事件；benchmark smoke 触发口径与 tasks 6.6 一致；MODIFIED Requirement 保留既有三个场景并新增取消 teardown 场景；归档门禁所需的 `grill-adversarial.md` 尚待 R3 收口后落盘（`design.md:838-839`），当前 active 阶段不拦。
- **需求对齐**：issue #307 的五档状态、真实事件驱动、工具名、出口回 idle、移动端 390px、不可观测不假装均在设计与规格中有落点；Q1（移动端形态）、Q2（失败标记）、Q3（多成员并发的解释）仍是真实用户取舍，`reviews/grill-design.md:87-95` 与 `design.md:750-790` 仍保留停轮确认，未被本轮修改误标为已确认。

## Verdict

CHANGES_REQUESTED

- 理由: N1–N6 本轮要求均已落实（N1 顺序、N2 三处 spec、N3 行为、N4 测试文案、N5 返回契约、N6 路径清理），F1/F2/F4/F5 等关键项未被破坏，门禁通过；但 N1 的修法引入了一个新的 **high**（X1）：`design.md:350` 的 `finally` 兜底 pop 没有身份判断，会在收尾窗口内把已经重新认领房间的新一轮从 `_rounds` 删掉，进而允许第三条消息开启并行轮次，违反「同一房间同一时刻至多一个进行中的轮次」的核心规格。修法是局部且明确的（两处 pop 加 `is state` 身份判断 + 回归断言），不构成需要推倒重开的设计根本矛盾，因此判 `CHANGES_REQUESTED` 而非 `BLOCKED`。修完 X1（并建议顺手处理 L1）后，本报告可作为收口轮重新核验；在此之前不能作为写码许可。
