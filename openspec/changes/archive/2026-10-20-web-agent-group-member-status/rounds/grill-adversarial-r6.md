# 设计对抗 R6（收口）: web-agent-group-member-status

## Reviewer

- run id: adversarial-agent-paseo-r6
- 时间: 2026-10-20
- 零记忆: 是
- 方法: 完整读 `AGENTS.md`、proposal / design / tasks / 两份 spec delta、
  `reviews/grill-design.md`、`grill-adversarial-r1.md` … `r5.md`；用 `gh api` 读 issue #307
  正文与全部评论；独立核对 `agent/team/orchestrator.py`（`submit_user_message` / `_run_round`
  / `_drive` / `_run_slot` / `_execute_tool_calls` 相关路径）、`agent/team/runner.py`、
  `agent/hooks/manager.py`、`agent/loop.py`（run/resume、`before_iteration`、`_call_llm`
  流式事件、工具钩子、`on_completion` / `on_error`、max_iterations）、`web/session.py`
  （`SessionEventChannel` / `run_session` / `_run_session_locked` / `WebSessionRunner`）、
  `web/team.py`（`RoomEventBus` / `_WorkspaceRunner` / `clone_llm_with_model`）、
  `web/server.py`（房间 WS 握手/断线取消/多 worker 作用域）、`agent/team/roomlog.py` 与
  `agent/team/models.py`（`RoomEntry.to_dict` 的 seq）、`web/static/group.js`、
  `web/static/index.html`、`web/static/style.css`、`tests/support/llm_harness.py`、
  `tests/web_tests/test_group_chat_team.py`、`test_group_chat_server.py`、
  `.witnessloop/policy.json` 与 `scripts/check_openspec_artifacts.py`；只读运行 OpenSpec strict
  validate（29/29 通过，exit 0）与
  `uv run python scripts/check_openspec_artifacts.py --base-ref origin/master --require-base`
  （exit 0）。未写实现/测试代码。所有代码行号相对基线 `48d25f0`。

### 审阅版本

- `design.md` sha256 `a308f321901d3bf5284008f68c33f441e8fac391ca88f7dae02fc12733b0d465`
- `tasks.md` sha256 `bcdbef2352c83fcbbb6ce910c233bdd0642202c8a61f12a0ee96034fbcd49f0e`
- `proposal.md` sha256 `16ff09cf595d91fd618f95d252c2f569938aa0d81a9c23aab5d88d5c19ba5b7b`
- `specs/multi-agent-collaboration/spec.md` sha256
  `526e80e0fcde00361a0c5a6da0504316cb15b07a6d2e8023413fdf9dc9adb357`
- `specs/web-ui/spec.md` sha256
  `ca0e72e89f9ac883609dd5212eabe85908fbeb3aa6b0825aacad0f4311625cc2`

## T1/L1–L8 修复验证

| 条目 | 当前证据（文件:行号） | 判定 | 备注 |
|---|---|---|---|
| T1（R5 medium）真实 `WebSessionRunner` 的 web 层映射测试 | `design.md:683-688`（真实 `WebSessionRunner` + 真实 `AgentSession` + `ScriptedLLM(stream=True)` + 一次工具调用 + `on_progress` collector；断言 `iteration_started`、每次 LLM 调用至多一个 `assistant_delta`、`stream_complete`、`run_completed`、`tool_started/finished` 的 id/name；FakeRunner 直调不能替代；删 `before_iteration` 或 `assistant_delta` 接线必须变红）；`tasks.md:51-56`（1.3.1 同口径）；`design.md:186-205`（observer/hook/on_event 旁路）；`tests/web_tests/test_group_chat_team.py:259-326`（既有真实 `AgentSession` + `ScriptedLLM` 的 `TestRunnerContract` 先例）；`tests/support/llm_harness.py:27-44`（`stream` 开关）、`:77-104`（`stream_chat` 的 delta + complete）；`agent/loop.py:790`（`before_iteration`）、`:1272-1309`（delta/`assistant_stream_complete`）、`:1417`/`:1447`（工具钩子）、`:838-847`/`:1148`（`on_completion`）；`web/session.py:2015-2016`（on_event 闭包）、`:2125`（drain） | **已修复** | 测试缝可执行：persona 不绑定 model 时 `clone_llm_with_model` 返回同一 `ScriptedLLM`（`web/team.py:39-56`），`ScriptedLLM.stream=True` 使 `_should_stream_llm` 走 `stream_chat`（`agent/loop.py:1389-1395`）；`bypass_default` 自动放行 HIGH 风险、不产生审批（`agent/tool_permissions.py:157-166`），工具钩子必触发；脚本化 tool call 有既有先例（`tests/web_tests/test_session.py:199-228`）。信号序列在 collector 中同步确定。变异点明确（删 `before_iteration` → `iteration_started` 缺失；删 `assistant_delta` 旁路 → 无 delta）。**残余 low：断言是“每调用至多一个”的上限，若只让第二次 LLM 调用出字，删掉 `before_iteration` 里的 `saw_delta` 复位不会变红；见 L-a。** |
| L1 `MemberStatus` 不含成员级 seq | `tasks.md:89-91`（phase / `id -> name` 映射；**不含成员级 seq**）；`design.md:228-244`（载荷只有房间级 `status_seq`）；`design.md:248-250`（不发送 idle 条目）；spec multi-agent `:5` | 已修复 | 与「全量表 + 房间 seq」的排序模型一致。 |
| L2 意外异常 teardown 的认领身份限定 + released-claim 实时可见性 | `design.md:336-347`（Cancelled/Exception 先做 `self._rounds.get(room.id) is state` 判断）；`:350-352`（finally 兜底 reset/release 同判断）；`:355-361`（`release_round` 定义）；`:369-374`（已释放则只记录并 re-raise，不发旧终态）；`:376-377`（总结 bullet 已加「仍持有认领」限定）；`:379-381`（已释放认领后的 limit 实时送达是 best-effort，limit 条目靠下一次 `room_state`/重拉可见）；`tasks.md:96-115`（2.7 同口径） | 已修复 | 两处残余均收敛；窄窗口的「limit 实时可见性不是验收条件」已写明。 |
| L3 limit 重拉测试移到 group.js/浏览器层 | `tasks.md:71-75`（1.5 node+vm 只断言 `applied=false`；「仍重拉时间线」明确放到 1.6）；`tasks.md:80-81`（1.6 浏览器断言迟到的 `round_ended(limit)` 仍重拉时间线）；`design.md:271-275`（行为口径）、`:594-601`（`applied=false` 只抑制头部/aria-live，不抑制 limit 重拉） | 已处置（tasks） | tasks 与 Decision 4.3 一致；**design 的 Testing Strategy 4/5 清单（`design.md:711-736`）仍没列这条，见 L-b（nit）。** |
| L4 「最终表」措辞 | `design.md:690-694`（WS 层：事件流中**至少出现过 tool**，回合结束后的状态用最后一条完整表 / `status_snapshot()` 与快照比对，**不要求最后一条表仍含 tool**）；`tasks.md:58-61`（同口径）；`design.md:651`、`tasks.md:32` 的编排器测试仍写「最终完整表」 | 基本修复 | R5 点名的 WS 层歧义已消除；编排器层「最终完整表」仍可被读成“最后一条非空表”，见 L-c（nit）。 |
| L5 `op` 提示清除规则 | `design.md:497-500`（`setStatus(text, kind)`，`kind ∈ {conn, round, op}`；新一轮 `user_message(queued=false)`/首个非空闲状态只清 `round`；**`op` 在下次成功发送或连接成功后清除**；`conn` 由下一连接事件替换）；`tasks.md:146-148`（4.3 同口径） | 已修复 | 规则完整且与 `conn`/`round` 的优先级不冲突。残余：没有对应回归测试，见 L-d（nit）。 |
| L6 presence 重绘保留 `scrollLeft` | `design.md:516-517`（`renderRoom()`/时间线事件触发的 presence 重绘保存并恢复 `scrollLeft`，或按成员 keyed 更新）；`tasks.md:141`（4.2 同口径） | 已修复 | 与 F6「自动滚入只动横向」自洽。 |
| L7 反定时器等待 3s | `design.md:732`（推送后等 **3s**，覆盖既有 2s 重连节奏与常见轮询）；`tasks.md:78`（1.6「无事件 3s 状态不变」） | 已修复 | 3s 足以覆盖 2s 级 `setInterval`；更长周期定时器不是本 change 的合理威胁面。 |
| L8 backlog 引用不悬空 | `docs/openspec-change-backlog.md:122`（改为「设计证据见 change 的 `reviews/`（grill-design.md 与 grill-adversarial 各轮；收口后落为规范的 `grill-adversarial.md`）」）；`workflow-events.jsonl` seq 3（`backlog_updated` 解释事件）；`design.md:914-915`（R6 收口后落规范文件名） | 已修复 | 不再直接引用不存在的文件。**收口动作**：R6 判 PASS 后须把本报告落为规范文件名 `reviews/grill-adversarial.md`（归档点 checker 要求），这是主 session 的收尾动作，不是设计缺陷。 |

## X1/N1–N6 / F1–F13 关键项复核

| 条目 | 判定 | 备注 |
|---|---|---|
| X1 认领身份释放 | 未被破坏 | `design.md:331-333`（正常 reset → 身份 release → flush）；`:336-347`（Cancelled/Exception 先身份判断）；`:350-352`（finally 兜底 reset/release 同判断）；`:355-361`（`release_round` 仅当 `_rounds.get(room_id) is state` 才删）；`tasks.md:41-47`、`:96-103`（R2 active、M3 queued 的回归与变异口径仍在）。 |
| N1 pop 先于 flush / 收尾窗口 | 未被破坏 | `design.md:331-333`（reset → release → flush）；`:380-390`（reset/pop 之间无 await，flush/review/终态在 pop 之后可放行新轮；flush 放在 pop 之前不推荐）；`tasks.md:42-47`（一次性有界 gate；R2 active、M3 queued；移回 pop 或去掉身份判断变红）。 |
| N2 幂等 reset 与条件递增 | 未被破坏 | spec multi-agent `:5`（表未变不递增；终态携带当前 seq）、`:76`、`:111`、`:126`；`design.md:145-148`（reset 幂等，表未变不递增/不标脏）；`tasks.md:85-88`。 |
| N3 迟到 limit 终态仍重拉时间线 | 未被破坏 | `design.md:271-275`（seq 丢弃状态影响但 limit 仍重拉）；`:594-601`（`applied=false` 只抑制头部/aria-live）；`tasks.md:74-75`、`:80-81`、`:145`。 |
| N4 测试文案（合并语义） | 未被破坏（编排器层措辞残余见 L-c） | `design.md:690-694`（事件流中曾出现 + 回合结束快照一致；不要求最后一条表含 tool）；`tasks.md:58-61`；`design.md:651`/`tasks.md:32` 仍写「最终完整表」。 |
| N5 `apply*` 返回契约 | 未被破坏 | `design.md:589-601`（统一 `{state, changed, applied}`，终态另含 `clearedAll`；`applied=false` 语义固定）；`tasks.md:136-139`。 |
| N6 本地绝对路径 | 未被破坏 | 对 change 目录全量 `grep -RInE '/home/|/Users/|/mnt/|reference-repos|agent-study'`（排除历轮报告自述）无实际路径命中。 |
| F1 头部文案单一归属 | 未被破坏 | `design.md:489-494`（删除 `member_speaking` 的头部文案；成员状态只归 presence；静默/失败/发言不清头部；`round_ended` 仅在未被 seq 丢弃时更新）；`specs/web-ui/spec.md:42-48`。 |
| F2 两条确定性顺序测试 | 未被破坏 | 跨轮迟到终态：`design.md:657-664`、`tasks.md:38-41`；握手首帧：`design.md:700-707`、`tasks.md:65-67`；均含变异验证。 |
| F3 建会话失败走统一 helper | 未被破坏 | `design.md:309-312`；`tasks.md:107-115`。 |
| F4 重置幂等 | 未被破坏 | `design.md:145-148`；spec multi-agent `:5`；`tasks.md:85-88`。 |
| F5 正常 `round_ended` 前 flush | 未被破坏 | `design.md:299-303`（同步重置 → flush → 终态；正常路径同构）、`:333`；`tasks.md:103-104`。 |
| F6 自动滚入只动横向 | 未被破坏 | `design.md:541-544`；`tasks.md:154-155`。 |
| F7 benchmark smoke 触发口径 | 未被破坏 | `design.md:738-747`；`tasks.md:186-189`；`scripts/check_openspec_artifacts.py:48-53` 的 `agent/loop.py` 文本模式仍会命中 proposal。 |
| F8 20 轮口径差异登记 | 未被破坏 | `design.md:916-918`；`tasks.md:16-19`。 |
| F10 不发送 idle 条目 | 未被破坏 | `design.md:248-250`；spec multi-agent `:5`。 |
| F11/F12 390px 头部与空状态 | 未被破坏 | `design.md:529-535`；`specs/web-ui/spec.md:78-85`；`tasks.md:156-157`。 |
| F13 降级源清单 | 未被破坏 | `specs/web-ui/spec.md:5`（含仅降级时的 `member_speaking`）；`design.md:569-584`。 |

## 新 Findings

**无 high/medium。**

### low / nit 登记（不阻塞）

- **L-a（nit）T1 的 `assistant_delta` 断言是上限而非“每次调用一次”的下限，未钉住 `saw_delta` 复位。**
  - 证据：`design.md:683-688`（“每次 LLM 调用至多一个”）、`:191`（`before_iteration` 清 `saw_delta`）、`:143-144`；`tasks.md:51-56`、`:98-100`；`tests/support/llm_harness.py:77-104`。
  - 失败场景：T1 脚本若让第一次（工具调用）响应不带可见文本、只让第二次响应出字，那么 `saw_delta` 在第一次从未置位；删掉 `before_iteration` 里的复位不会让测试变红。之后真实工具回合的第二次 LLM 调用若因此不再发 `assistant_delta`，成员会一直显示「正在思考」而不是「正在输入」——状态模型其余部分全绿。
  - 建议：让两次 LLM 调用都产生可见 delta（第一次 `content + tool_calls`，第二次流式文本），断言两次各收到一次 `assistant_delta`；或把「删 `saw_delta` 复位 → 变红」写进变异清单。属测试加强，不改设计结论。
- **L-b（nit）design 的 Testing Strategy 4/5 清单没有列「迟到的 `round_ended(limit)` 仍重拉时间线」。**
  - 证据：`tasks.md:74-75`、`:80-81` 已列；`design.md:711-736` 的 JS/浏览器测试清单未列；行为口径在 `design.md:271-275`、`:594-601`。
  - 影响：实现者若只按 design 的测试清单实施，仍会漏掉这条（tasks 有兜底）。建议把 1.6 的该条同步进 design Testing 5。
- **L-c（nit）编排器层测试仍写「最终完整表」。**
  - 证据：`design.md:651`、`tasks.md:32`；WS 层已在 `design.md:690-694`/`tasks.md:58-61` 改为正确口径。
  - 影响：可能被读成“最后一条非空表”。建议统一为「终态后的表为空且与 `status_snapshot()` 一致」。
- **L-d（nit）`op` 提示清除规则没有回归测试。**
  - 证据：规则在 `design.md:497-500`；`tasks.md:76-83`（1.6）没有「发送失败 → 成功发送后清除」断言。
  - 影响：L5 的行为（HTTP 发送失败提示在成功重试后消失）可能静默失效。建议在浏览器测试或 group.js 测试补一条轻量断言。
- **L-e（low）切换房间时旧房间的状态表未显式清空。**
  - 证据：`web/static/group.js:188-205`（`openRoom` 设置 `members/timeline`，但不重置状态表）；`design.md:263-269` 只规定「新建/重连房间 WS 时」重置水位与标记过期；`design.md:509-512` 的 presence 按成员渲染。
  - 失败场景：房间 A 中甲正在 `tool(Bash)`，用户切到房间 B（甲也是成员）；在 B 的 `room_state` 首帧到达前，presence 会用 A 的状态短暂把甲显示为「正在使用工具」。正常窗口是 WS 握手级（毫秒级），若握手失败则旧状态会一直显示到断线灰显/重连快照。建议在 `openRoom`/切换房间时把 status state 清空（或按 room 作用域化），与「新连接以快照为准」同构。属窄窗口 UI 问题，不损服务端状态正确性。
- **L-f（low）迟到 limit 的重拉响应可能覆盖已切换房间的 timeline。**
  - 证据：`web/static/group.js:276-287`（`round_ended(limit)` 发起 fetch，`.then` 里直接 `state.timeline = body.timeline`，未校验当前房间）；设计保留了这一路径（`design.md:271-275`）。
  - 失败场景：房间 A 达上限 → 重拉请求在途 → 用户切到房间 B → 响应返回，用 A 的 timeline 覆盖 B 的视图。窗口窄（本地 fetch 通常极快），且属基线已有形态；建议 `.then` 里校验 `state.activeRoom.id` 仍是发起时的房间（或复用 `connectionEpoch`）。不阻塞。
- **L-g（nit）断线「可能过期」标记没有浏览器断言。**
  - 证据：要求见 `specs/web-ui/spec.md:5`；设计见 `design.md:574-576`（断线保留最后已知状态并灰显/标记过期）；Testing 5 清单（`design.md:719-736`）没有对应断言。建议补一条 class/属性断言，避免「标记过期」只停留在文字。

## 已确认站得住的部分

- **T1 的测试缝与确定性**：`WebSessionRunner` 可直接注入 `on_progress`；persona 不绑模型时 session 复用同一个 `ScriptedLLM`（`web/team.py:39-56`），`stream=True` 走 `stream_chat`（`agent/loop.py:1389-1395`）；`bypass_default` 自动放行、工具钩子必触发（`agent/tool_permissions.py:157-166`）；`ScriptedLLM` 的非 `StreamScript` 步骤会先产出 `assistant_delta`（若有正文）再产出携带 `tool_calls` 的 `complete`（`tests/support/llm_harness.py:92-104`），因此「工具调用 + 最终流式文本」的两迭代脚本可执行；collector 在 hook/on_event 的 await 链上同步追加，无需事件循环让出点。
- **X1 的最终形态自洽**：正常路径 reset（同步）→ 身份 release → flush；Cancelled/Exception 仅在仍持有认领时 reset + 调度强引用后台 teardown；已释放认领时只记录并 re-raise；finally 兜底 reset/release 都带身份判断。逐条核对「R1 已释放、R2 已认领、R1 收尾任务被取消」窗口，R2 的 `_RoundState`、`round_active` 与状态表不会被旧轮改写。
- **N1/termination/flush 顺序**：limit system 条目与 termination 在 reset/pop 之前同步完成；pop 在 flush 之前，收尾窗口内新消息开新轮而不是排队进已结束的轮次；flush 在 pop 之后、review/terminal 之前；reset/pop 之间无 await。空表 no-op reset 返回当前 seq，新轮首个 `slot_started` 仍使旧终态 seq 严格更小；新轮首 slot 被 `slot_skipped` 时不存在新状态事件，旧终态应用并清空房间是正确结果。
- **协议/时序**：全量表 + 房间级 `status_seq`；`member_status` 用 `<=` 丢弃、终态用 `<` 丢弃/相等应用；终态携带重置后 seq；`room_state` 首帧 + 锁内同步构造快照 + 订阅后所有发送同一把锁 + try/finally unsubscribe；订阅前的在途 emitter payload 即使晚到也因 seq 更旧被丢弃；双标签页/慢客户端/空表 no-op/重连快照/服务端重启逐条核对未发现新的错误丢弃或清空。`RoomEntry.to_dict` 含 `seq`（`agent/team/models.py:160-167`），时间线幂等追加可落地。
- **reducer 与代码事实**：工具按 `tool_call.id` 记账（`ToolCall.id/name` 存在）；`before_tool_execute` / `after_tool_execute`（`agent/loop.py:1417`、`:1447`）是工具起止权威；预拒绝工具在 `_execute_tool_calls` 提前返回、不触发钩子（`:1455-1468`、`:1500-1513`），与「不假装」一致；`iteration_started` 无条件清空在途工具覆盖非 Bash 异常跳过 after 的路径（`:1420-1439`）；resume 无 `run_started`、`before_iteration` 是 thinking 权威（`:709-743` vs `:790`）；非流式无 `assistant_delta`（`:1389-1395`）；`on_error` 不映射为 run 终态（`:877`、`:1427`、`:1431`）；生产 `WebSessionRunner` 已把空文本归一为 silent（`web/session.py:2226-2227`）；max_iterations 路径也会调用 `on_completion`（`:1148`），`run_completed` 不会悬空。
- **Hook 生命周期与三处实现**：`Hook` 7 方法全实现、逐 run 新实例、覆盖整个 run 的 try/finally 按身份摘除、回调不抛出；`WebSessionRunner`（`web/session.py:2178`）、`_WorkspaceRunner`（`web/team.py:222`）、`FakeRunner`（`tests/agent/team/test_orchestrator.py:35`）均在设计与 tasks 中列全。
- **规格/需求**：issue #307 的五档状态、工具名、真实事件驱动（无定时器）、出口回 idle、移动端 390px、不可观测不假装（非流式无 typing、子 agent 内部不可见、预拒绝工具无开始）在两份 spec delta 与设计中均有落点；ADDED/MODIFIED 自洽，MODIFIED 保留既有三出口与三条原场景并新增取消 teardown 非出口场景；`member_failed.name`、群公告独立元素、aria-live、prefers-reduced-motion、旧服务端/旧前端双向降级完整。
- **门禁与文档**：OpenSpec strict 29/29 通过；瘦 checker exit 0；RIR `research_tier: full` 字段与 findings 完整，无本地绝对路径；backlog 已登记 #307 且有 `backlog_updated` 事件；benchmark smoke 按 checker 文本触发口径列入 tasks 6.6；witnessloop 三份 manifest 属归档点产物，active 阶段不要求。
- **停轮状态**：`reviews/grill-design.md` 的 `## User Confirmation` 仍为「待用户答复」，Q1（移动端形态）、Q2（失败标记）、Q3（「多成员并发」的解释）仍是真实待确认项；`tasks.md` 0.4 未勾。**Q3 仍需用户确认**：issue 原文用「多成员并发」，现行规格 `openspec/specs/multi-agent-collaboration/spec.md:1267` 钉死同一时刻至多一个成员发言，设计按「每人独立一行、串行执行」解释。PASS 只表示设计对抗环收口，**不构成写实现代码或测试代码的许可**；Q1/Q2/Q3 答复写入 `grill-design.md` 前不得开工。

## Verdict

PASS

- 理由: T1 已按 R5 口径修复——真实 `WebSessionRunner` + 真实 `AgentSession` + `ScriptedLLM(stream=True)` + 一次工具调用 + `on_progress` collector 的 web 层映射测试在现有 fixture 上**可执行且信号序列确定**（persona 不绑模型时复用同一 `ScriptedLLM`，bypass 模式无审批，工具钩子必触发），FakeRunner 直调被明确排除，删接线变红的变异口径与 tasks 1.3.1 / design Testing 3 一致；L1–L8 均已修复或合理处置（L3/L4 有 nit 级措辞/清单残余，L8 的规范文件名属收口动作）。X1/N1–N6/F1–F13 关键项在本轮修改中未被破坏；协议（全量表 + 房间 seq、空表 no-op、跨轮、双标签页、慢客户端、首帧、服务端重启）未发现新的错误丢弃/清空；门禁（OpenSpec strict、瘦 checker、RIR、backlog、benchmark smoke 口径）通过。新扫查**没有 high/medium**，仅有 2 条 low 与若干 nit 登记，不构成写码许可的阻断。
- 收口后动作（不属于本轮 verdict）：
  1. 把本报告落为规范文件名 `reviews/grill-adversarial.md`（归档点 grill 证据要求），并勾掉 `tasks.md` 0.3 / 0.5；
  2. 停轮把 Q1/Q2/Q3 逐项抛给用户，答复写入 `grill-design.md` 的 `## User Confirmation` 后才进入实现；
  3. L-a 建议随 T1 实施一并加强（两次 LLM 调用都产生可见 delta，断言各一次）。
