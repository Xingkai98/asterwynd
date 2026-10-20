# 设计对抗 R4（收口）: web-agent-group-member-status

## Reviewer

- run id: adversarial-agent-paseo-r4
- 时间: 2026-10-20
- 零记忆: 是
- 方法: 完整读 `AGENTS.md`、本 change 的 proposal / design / tasks / 两份 spec delta /
  `reviews/grill-design.md` / `reviews/grill-adversarial-r1.md` / `r2.md` / `r3.md`；
  用 `gh api` 读 issue #307 正文与全部评论；独立核对 `agent/team/orchestrator.py`
  （`submit_user_message` / `_run_round` / `_drive` / `_run_slot` / `_append_called_slots` /
  `_emit`）、`agent/team/runner.py`、`agent/hooks/manager.py`、`agent/loop.py`
  （run/resume、`before_iteration`、`_call_llm` 流式事件、工具钩子、`on_completion` /
  `on_error`）、`web/session.py`（`SessionEventChannel` / `run_session` /
  `_run_session_locked` / `WebSessionRunner`）、`web/team.py`（`RoomEventBus` /
  `_WorkspaceRunner` / `TeamService`）、`web/server.py`（房间 WS 握手与断线取消）、
  `web/static/group.js`、`index.html`、`style.css`、`tests/support/llm_harness.py`、
  `tests/agent/team/test_orchestrator.py`、`tests/web_tests/test_group_chat_server.py`、
  `test_group_chat_team.py`、`test_workflow_graph_browser.py`、`.witnessloop/policy.json`；
  只读运行 `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`（29/29 通过）与
  `uv run python scripts/check_openspec_artifacts.py --base-ref origin/master --require-base`
  （exit 0）。未写实现/测试代码。所有代码行号相对基线 `48d25f0`。

### 审阅版本（并行更新说明）

审阅期间 change 目录在 09:47 被并行更新（design 866→878 行、tasks 同步），X1 的
except/finally 身份判断与「释放后取消不重置/不发旧 teardown」是更新后内容。本报告以
更新后的最终内容为准：

- `design.md` sha256 `4b7f54b1df0faa30e711a85da7d0bb7a02655c72032964deab2e96b2d2857329`
- `tasks.md` sha256 `e197607a7080bc2c0d5509e0d3f23dd09008c8f40ed620839f1c032c270da566`
- `specs/multi-agent-collaboration/spec.md` sha256 `526e80e0fcde00361a0c5a6da0504316cb15b07a6d2e8023413fdf9dc9adb357`
- `specs/web-ui/spec.md` sha256 `ac00d10638ffcd4dd1588e2288d6e2026cb486d91d85ae4389089950acfacf06`

## X1/N1–N6 修复验证

| 条目 | 当前证据（文件:行号） | 判定 | 备注 |
|---|---|---|---|
| X1 | `design.md:329-333`（termination 含 limit 条目 → 同步 reset → 身份 release → flush）；`design.md:355-361`（`release_round` 仅当 `_rounds.get(room_id) is state` 才删）；`design.md:336-347`（Cancelled/Exception 分支先做身份判断才 reset/schedule）；`design.md:348-352`（finally 兜底 reset 也带身份判断，release 再校验身份）；`design.md:649-653`、`tasks.md:42-47`（R1 返回后 R2 active、M3 queued 进 R2；移回 pop 或去掉身份判断变红）；`design.md:654-656`（释放后取消 R1 收尾任务，R2 不受影响、无旧 `round_ended`） | 已修复 | 所有释放点均身份判断；正常路径 reset→身份释放→flush 顺序正确；finally 不会删除新一轮认领；termination 计算与 limit system 条目在 reset/pop 之前同步完成（`design.md:330`、`:380-381`）。「例外路径不越过认领归属动房间」是比 R3 要求更严的合理加固。 |
| N1 | `design.md:331-333`（pop 在 flush 前）；`design.md:380-386`（reset/pop 之间无 await、flush/review/终态在 pop 之后可放行新轮）；`design.md:649-653`、`tasks.md:42-47`（一次性、有界等待 gate；M2 开 R2；放行 R1 flush 后 R2 仍 active；M3 queued；变异验证） | 已修复 | 收尾窗口不再吞新消息；gate 明确一次性且有界；断言含认领存活。 |
| N2 | `specs/multi-agent-collaboration/spec.md:5`（幂等条款 + 空表终态携带当前 seq）、`:76`（表实际变化才递增）、`:111`（取消场景条件递增）、`:126`（MODIFIED 条件递增 + 先于释放认领） | 已修复 | 三处无条件递增已全部改为条件递增；与 `design.md:145-148`、`:330` 自洽；空表 no-op reset 返回当前 seq，跨轮严格不等式仍成立。 |
| N3 | `design.md:271-275`（迟到 limit 终态仍重拉时间线、不改状态）；`design.md:587-588`（`applied=false` 只抑制头部/aria-live）；`tasks.md:60-65`（1.5 明确 `applied=false` 但调用方仍重拉）；`tasks.md:127-131`（4.3 同口径） | 已修复 | 行为与回归测试都落点。 |
| N4 | `design.md:670-672`（事件流中**曾出现** thinking/typing、最终表与快照一致）；`tasks.md:51-55`（同口径） | 已修复 | 与「不发送 idle 条目」不再矛盾。 |
| N5 | `design.md:579-588`（`applyStatusEvent` / `applyTerminal` / `applySnapshot` / `applySpeakingFallback` 统一 `{state, changed, applied}`，终态另含 `clearedAll`；`applied=false` 语义固定）；`tasks.md:118-122`（4.1 同口径） | 已修复 | 四个 apply* 的返回契约与 tasks 一致。 |
| N6 | 对 change 目录全量 `grep -RnE '/home/|/Users/|/mnt/|reference-repos|agent-study'` 只命中 R3 报告自身对搜索模式的文字描述，无实际本地绝对路径 | 已修复 | design / grill-design / R1 / R2 / R3 均无本地路径。 |

## F1–F13 关键项复核

| 条目 | 判定 | 备注 |
|---|---|---|
| F1 头部文案单一归属 | 修复仍在，但**引入新的头部生命周期缺口**（M2） | `design.md:481-488` 仍删除 `member_speaking` 头部文案、终态不清头部、`round_ended` 仅未被 seq 丢弃时更新；但新轮开始时没有清「本轮结束」的规则。 |
| F2 两条确定性顺序测试 | 未被破坏 | 跨轮迟到终态：`design.md:644-648`、`tasks.md:38-41`；握手首帧：`design.md:677-681`、`tasks.md:56-59`；均含变异验证。 |
| F3 建会话失败走统一 helper | 未被破坏 | `design.md:310-312`；`tasks.md:93-95`。 |
| F4 重置幂等 | 未被破坏 | `design.md:145-148`；`tasks.md:85-88`；`spec.md:5`。 |
| F5 正常 `round_ended` 前 flush | 未被破坏 | `design.md:300-303`、`:333`；flush 在 pop 之后、终态之前。 |
| F6 自动滚入只动横向 | 未被破坏 | `design.md:528-529`；`tasks.md:134-135`。 |
| F7 benchmark smoke 触发口径 | 未被破坏 | `design.md:718-721`；`tasks.md:166-169`；checker 存在 `agent/loop.py` 模式命中。 |
| F8 20 轮口径差异登记 | 未被破坏 | `design.md:863-864`；`tasks.md:16-19`。 |
| F9/R1 记录路径清理 | 未被破坏 | R1/R2/R3 与 grill-design 均无本地路径。 |
| F10 idle 条目不发送 | 未被破坏 | `design.md:248-250`。 |
| F11/F12 390px 头部与空状态 | 未被破坏 | `design.md:516-519`、`:699-704`；`specs/web-ui/spec.md:71-78`；`tasks.md:136-138`。 |
| F13 降级源清单 | 未被破坏 | `specs/web-ui/spec.md:5`（含 `member_speaking` 降级）。 |

## 新 Findings

### M1（severity: medium）WS 级「thinking/typing 曾出现」集成测试按指定 harness 不可确定性通过

- **问题**: `design.md:664-672` 与 `tasks.md:49-55` 规定用 `ScriptedLLM(stream=True)` +
  `StreamScript`（`tests/support/llm_harness.py:77-105`）让成员先思考再流式出字，并断言房间
  事件流中**曾出现**含 thinking 的表、随后出现含 typing 的表。但该 harness 在一个
  `async for` 里连续 yield，事件之间**没有事件循环让出点**；AgentLoop 的
  `before_iteration`（`agent/loop.py:790`）、流式事件（`:1282-1309`）到 `on_event` 闭包
  （`web/session.py:2015-2016` 的 `queue.put`）以及进度回调都是不挂起的同步路径。设计要求
  状态变更在同步段内完成、发射器是独立 task 且在同一同步段读取**当前**完整表
  （`design.md:293-295`、`:289-292`）。因此在这个脚本下，从 `iteration_started` 到
  `assistant_stream_complete` 之间发射器没有机会运行；等它真正运行时，表已经变成
  `running`（`stream_complete`/`run_completed`）甚至被终态 reset 清空——thinking/typing
  根本不会出现在房间 WS 事件流里。
- **失败场景**: 一个完全正确的实现跑该 WS 集成测试，收到的事件序列只有
  `member_status(running)` →（可能的空表）→ `member_post` / `member_silent` /
  `member_failed` → `round_ended`；`any(thinking)` / `any(typing)` 断言假红。实现者为了变绿
  要么删掉这条核心断言（失去 thinking/typing 的端到端接线覆盖），要么在 harness 里临时加
  让出点而不回写设计；这正是 R2 的 N4 同类问题（测试口径与合并语义冲突）在 WS 层的残余。
- **证据**: `design.md:664-672`；`tasks.md:49-55`；`tests/support/llm_harness.py:77-105`；
  `agent/loop.py:789-796`、`:1282-1309`；`web/session.py:2015-2016`；
  `design.md:289-295`；`reviews/grill-design.md` 的 Risks 已承认「脚本化/极快 provider 下
  thinking 可能被合并掉，必须在 spec/测试里承认」，但未落实到 design 的 Testing Strategy /
  Risks。
- **建议修法**:
  - 在测试用 LLM 包装器里给每个流事件之间加 `await asyncio.sleep(0)`（或一次显式 gate），
    让发射器在 thinking/typing 各自发出后再继续；这样 WS 级断言才真正可确定。
  - 或者把「事件流中出现 thinking/typing」下移到 FakeRunner/编排器层（测试可在
    `on_progress` 调用之间 `sleep(0)`），WS 层只断言「长工具期间 tool 态可见 + 合并语义」
    并明确允许 thinking/typing 被合并掉。
  - 同时把「极快/脚本化 provider 下中间态可能被合并」写进 `design.md` 的 Risks 与 tasks
    测试口径，避免实现者把合并当失败。

### M2（severity: medium）删除 `member_speaking` 头部文案后，`#group-room-status` 的轮次/操作提示没有生命周期：下一轮进行中头部仍显示「本轮结束」

- **问题**: `design.md:481-488` / `tasks.md:127-131` 删除 `member_speaking` 的
  「X 正在发言...」头部文案，并规定 `member_silent` / `member_failed` / `member_post`
  不需要清头部，`round_ended` 在未被 seq 丢弃时把头部写成「本轮结束」/「本轮因达上限结束」。
  但 `user_message` 处理只追加时间线（`web/static/group.js:249-252`），设计没有规定新一轮
  开始时清除这个轮次提示。现状 `member_speaking` 原本会在下一轮把该文案覆盖掉；删除后，
  第一轮结束后「本轮结束」会一直留到下一次 `round_ended`——即**整轮**都显示「本轮结束」，
  而 presence 同时显示「甲 正在思考 / 正在使用工具」。这与 F1 要消除的「同一视图矛盾状态」
  是同一类问题（轮次级而非成员级），现有 spec 场景只覆盖了成员级残留
  （`specs/web-ui/spec.md:42-48`），测试也测不到。
- **失败场景**: 第一轮正常结束 → `round_ended` 把头部写成「本轮结束」；用户发 M2 → R2 开始，
  presence 显示成员忙；头部在整个 R2 期间仍写「本轮结束」。同理，HTTP 降级路径的
  「发送失败：...」在之后成功发送/新一轮开始时也没有清除规则（WS 重连成功时
  `onopen` 会写「已连接」可自愈，但正常轮次内不会）。
- **证据**: `design.md:481-488`；`web/static/group.js:249-254`（`user_message` 不清头部）、
  `:276-288`（`round_ended` 写头部）、`:369-372`（`setStatus`）；
  `specs/web-ui/spec.md:42-48`；`tasks.md:127-131`。
- **建议修法**:
  - 在 Decision 7 / tasks 4.3 明确 `#group-room-status` 的单一归属与生命周期：
    连接/错误提示优先级最高；轮次提示由 `round_ended` 设置，并在**新一轮开始时清除或改为
    中性**（例如处理 `user_message` 且 `queued=false` 时清空轮次提示，或在新轮首个非空闲
    `member_status` 到达时清除）；操作失败提示在成功发送/新一轮开始时清除。
  - 补一条 JS 或浏览器回归：`round_ended` → 新 `user_message` → `member_status(running)` 后，
    头部 SHALL NOT 仍显示「本轮结束」；并扩展 web-ui 场景覆盖轮次级残留。
  - 该改动不得影响「状态栏与提示区域互不覆盖」的既有场景（`specs/web-ui/spec.md:35-40`）：
    连接/错误文本仍由 `setStatus` 独占，成员状态仍只在 presence。

### L1（severity: low）`tasks.md` 2.7 与 design 的异常兜底陈述未跟上「认领丢失即不 reset/不发 teardown」的加固

- **问题**: 更新后的伪代码在 claim 已释放时抑制 reset 与 teardown
  （`design.md:336-347`、`:369-374`），但 `tasks.md:93-99` 仍写「取消发
  `round_ended(cancelled)`、意外异常发 `round_ended(error)`」无身份限定；
  `design.md:376-377` 也仍写「任何位置的意外异常都走 `error` teardown」。实现者若按 tasks
  2.7 字面实现，会在 flush/review 尾部已释放认领后仍可能 reset/发旧 teardown，与
  X1 延伸测试（`tasks.md:45-47`）直接冲突。
- **失败场景**: R1 已 reset+release、R2 已开始；R1 在 `_flush_status_emits` 被取消；实现按
  tasks 2.7 无条件 reset（清掉 R2 状态）或发旧 `round_ended(cancelled)`；测试
  `tasks.md:45-47` 变红，或实现者反过来删测试。
- **证据**: `design.md:336-352`、`:369-377`；`tasks.md:93-99`。
- **建议修法**: 把 tasks 2.7 与 design 的 bullet 改成「取消/异常 teardown 仅在
  `_rounds.get(room_id) is state` 时 reset 并调度」；并明确「已释放认领后被取消的收尾任务
  不发送旧终态」是预期行为。
- **附带口径（同条 low）**: 该抑制意味着「已达上限并写完 limit system 条目、但在 flush
  期间发起连接关闭」的轮次不会实时收到 `round_ended(limit)`，其他标签页的时间线要等重连
  才看到该条目（状态已通过 reset 事件回到 idle）。这是窄窗口且不损状态正确性，但建议在
  design 的 Edge cases 中写明，或让收尾任务以旧 seq 发一条 status-only 终态（客户端按 seq
  丢弃状态影响、但保留 limit 重拉）。

## 已确认站得住的部分

- **X1 的最终形态自洽**：正常路径 reset（同步）→ 身份 release → flush；Cancelled/Exception
  在仍持有认领时 reset + 调度 teardown；已释放认领时不动房间、不发旧终态；finally 兜底
  reset 也带身份判断。逐条核对「R1 释放 → R2 认领 → R1 收尾异常/取消」的窗口，R2 的
  `_RoundState`、`round_active` 与状态表均不会被旧轮改写。空表 no-op reset 返回当前 seq，
  配合新轮 `slot_started` 必然 +1，旧终态 seq 仍严格小于新轮首个状态；新轮首 slot 被
  `slot_skipped` 时没有新状态事件，旧终态按 `>=` 应用并清空房间也是正确结果。
- **termination 前移修复了 R3 的 L1**：limit system 条目在 reset/pop 之前同步追加，R2 的
  `user_message` 必然拿到更大的 seq；`RoomLog.build_injection(round_start=...)` 按 seq 切片，
  R2 的成员提示不会看到上一轮的 limit 条目。
- **取消/异常矩阵闭合**：claim 持有 → 同步 reset + 强引用后台 task（flush + emit，2s 限界）；
  claim 丢失 → 不做多余 reset；finally 身份 release 幂等；没有在已取消 task 里直接 await
  广播。
- **握手与快照**：取锁 → 持锁同步构造快照 → 同步 subscribe → 首帧 → 释放锁；
  `try/finally` 覆盖订阅清理；订阅后所有发送（含 pong）走同一把每连接锁；构造与订阅之间
  没有 await，不存在「订阅前事件丢失」；旧连接尾部事件由 `connectionEpoch` 隔离。
  服务端重启 seq 变小由新连接快照水位重置接受。
- **发射器与 seq**：状态变更在同一同步段完成；发射任务在同一同步段读当前完整表与当前
  `status_seq`；终态前 flush；短窗口合并允许；`status_seq <= lastStatusSeq` 丢弃状态、
  终态用 `<`、相等应用，跨轮/双标签页/慢客户端/空表终态均自洽。`status_snapshot()` 一次读
  表与 seq，`room_state` 首帧一致。
- **reducer 与代码事实**：工具按 `tool_call.id` 记账（`ToolCall.id/name` 存在，
  `agent/tools/base.py:86-94`）；`before_tool_execute` / `after_tool_execute`
  （`agent/loop.py:1417`、`:1447`）是工具起止权威；`iteration_started` 无条件清空在途工具
  覆盖非 Bash 异常跳过 after 的路径（`:1420-1439`、`:1500-1513`）；resume 无 `run_started`、
  `before_iteration` 是 thinking 权威（`:709-762` vs `:790`）；非流式无 `assistant_delta`
  （`:1389-1395`）；`on_error` 不映射 run 终态（`:877`、`:1427`、`:1431`）；生产
  `WebSessionRunner` 已把空文本归一为 silent（`web/session.py:2226-2227`）。
- **Hook 生命周期与三处实现**：`Hook` 7 方法全实现、逐 run 新实例、覆盖整个 run 的
  try/finally 按身份摘除、回调不抛出；`WebSessionRunner`（`web/session.py:2162`）、
  `_WorkspaceRunner`（`web/team.py:215`）、`FakeRunner`
  （`tests/agent/team/test_orchestrator.py:19`）已列全。
- **门禁与文档**：OpenSpec strict 29/29 通过；瘦 checker exit 0；RIR `research_tier: full`
  字段完整；backlog 已登记 #307 且有 `backlog_updated` 事件；benchmark smoke 任务
  （`tasks.md:166-169`）按 checker 文本触发口径存在；`require_change_for` 覆盖
  `agent/**`、`scripts/**`、`web/**`，本 change 存在；无本地绝对路径。
- **需求对齐**：issue #307 的五档状态、工具名、真实事件驱动（无定时器）、出口回 idle、
  移动端 390px、不可观测不假装（非流式无 typing、子 agent 内部不可见、预拒绝工具无开始）
  均在设计与两份 spec delta 有落点；`member_failed.name`、群公告独立元素、aria-live、
  prefers-reduced-motion、旧服务端/旧前端双向降级都完整。
- **停轮 Open Questions 仍然是真问题**：`reviews/grill-design.md:87-95` 的
  `## User Confirmation` 仍为「待用户答复」，`design.md:877-878` 与 `tasks.md:20-22`
  （0.4）仍保留 Q1/Q2/Q3 停轮；**Q3 仍需用户确认**（issue 原文用「多成员并发」，现行规格
  钉死同一时刻至多一个成员发言）。这是设计流程要求，不是本轮审阅缺陷；收到答复前不得写
  实现/测试代码。

## Verdict

CHANGES_REQUESTED

- 理由: X1 已按 R3 要求修复且加固到位（所有释放点身份判断、正常 reset→release→flush、
  finally 不误删新轮、termination/limit 条目前置、N1 回归含 R2 active 与 M3 queued）；
  N1–N6 全部修复/合理处置；F1–F13 关键项未被破坏；门禁全绿。但最后一轮扫查发现 **2 条新
  medium**：M1（WS 级 thinking/typing 集成测试在指定 `ScriptedLLM`+`StreamScript` 下没有
  事件循环让出点，中间态会被合并掉，断言不可确定性通过或被迫弱化——核心状态的端到端接线
  缺少可靠覆盖）与 M2（删除 `member_speaking` 头部文案后，「本轮结束」没有在新轮开始时
  清除，整个下一轮头部与 presence 矛盾）。另有 1 条 low（tasks 2.7 / design bullet 未跟上
  释放后抑制 teardown 的加固，及该窗口的 limit 实时提示口径）。
- 没有 high，也没有协议/规格的根本性矛盾；M1/M2 都是局部修法（测试让出点/断言分层；
  头部生命周期规则 + 回归），不构成推倒重开的理由，因此不判 `BLOCKED`。修完 M1/M2（建议
  顺带收敛 L1）后重跑一次有界对抗验证即可收口；在此之前不能作为写码许可。另：Q1/Q2/Q3
  仍是未知的停轮确认项，实现前必须由用户答复并写入 `grill-design.md` 的
  `## User Confirmation`。
