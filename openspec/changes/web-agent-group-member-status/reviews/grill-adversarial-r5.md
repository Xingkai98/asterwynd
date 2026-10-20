# 设计对抗 R5（收口）: web-agent-group-member-status

## Reviewer

- run id: adversarial-agent-paseo-r5
- 时间: 2026-10-20
- 零记忆: 是
- 方法: 完整读 `AGENTS.md`、proposal / design / tasks / 两份 spec delta、
  `reviews/grill-design.md`、`grill-adversarial-r1.md` … `r4.md`；用 `gh api` 读 issue #307
  正文与全部评论；独立核对 `agent/team/orchestrator.py`（`submit_user_message` / `_run_round`
  / `_drive` / `_run_slot` / `_append_called_slots` / `_emit`）、`agent/team/runner.py`、
  `agent/hooks/manager.py`、`agent/loop.py`（run/resume、`before_iteration`、`_call_llm`
  流式事件、工具钩子、`on_completion` / `on_error`）、`web/session.py`（`SessionEventChannel`
  / `_run_session_locked` / `WebSessionRunner`）、`web/team.py`（`RoomEventBus` /
  `_WorkspaceRunner` / `team_for` / `submit_room_message`）、`web/server.py`（房间 WS 握手与
  断线取消）、`web/static/group.js`、`web/static/index.html`、`web/static/style.css`、
  `tests/support/llm_harness.py`、`tests/agent/team/test_orchestrator.py`、
  `tests/web_tests/test_group_chat_server.py`、`test_group_chat_team.py`、
  `.witnessloop/policy.json`；只读运行 OpenSpec strict validate（29/29 通过，exit 0）与
  `uv run python scripts/check_openspec_artifacts.py --base-ref origin/master --require-base`
  （exit 0）。未写实现/测试代码。所有代码行号相对基线 `48d25f0`。

### 审阅版本

- `design.md` sha256 `f7293e55cff78fa77b10316dd9a18028078ab55a2d0d84f0028dd617fbaf16b6`
- `tasks.md` sha256 `605ec7094947bdd458f310455978ec25e9cb5f40cb2f236e772c487a6029b429`
- `specs/multi-agent-collaboration/spec.md` sha256
  `526e80e0fcde00361a0c5a6da0504316cb15b07a6d2e8023413fdf9dc9adb357`
- `specs/web-ui/spec.md` sha256
  `ca0e72e89f9ac883609dd5212eabe85908fbeb3aa6b0825aacad0f4311625cc2`

## M1/M2/R4-low 修复验证

| 条目 | 当前证据（文件:行号） | 判定 | 备注 |
|---|---|---|---|
| M1（WS 层中间态测试可执行性） | `design.md:677-683`（WS 层只断言最终表 / 关键状态，thinking→typing 下移到编排器/FakeRunner 层，每个 `on_progress` 后 `asyncio.sleep(0)`；慢速脚本 LLM 必须带让出点/gate）；`design.md:764-766`（合并可见性风险进 Risks）；`tasks.md:51-55`（同口径）；`design.md:643-644`、`tasks.md:32-37`（编排器层关键子序列，允许合并） | 已按 R4 口径修复 | `StreamScript` 连续 yield 无让出点（`tests/support/llm_harness.py:88-90`）与 FakeRunner 直调 `on_progress`（`tests/agent/team/test_orchestrator.py:35-58`）的事实均被正确承认；WS 层不再要求不可确定性的 thinking/typing。**但分层后 web 层映射出现新的测试空洞，见 T1。** |
| M2（头部轮次提示生命周期） | `design.md:491-495`（`setStatus(text, kind)`，kind ∈ {conn, round, op}；`user_message(queued=false)` 或首个非空闲 `member_status` 调 `clearRoundStatus()`，只清 round）；`design.md:481-490`（删除 `member_speaking` 头部文案、头部单一归属）；`design.md:271-275`（迟到 limit 终态不改状态）；`tasks.md:133-138`（4.3 同口径）；`tasks.md:69-70`（1.6 浏览器回归：新一轮清除「本轮结束」）；`specs/web-ui/spec.md:50-55`（新场景）；`specs/web-ui/spec.md:35-40`（提示区互不覆盖） | 已修复 | 新一轮开始清除「本轮结束 / 本轮因达上限结束」；`conn`/`op` 不被轮次清除；被 seq 丢弃的 `round_ended(limit)` 不改头部但保留重拉。旧服务端降级路径也有 `user_message(queued=false)`，清除规则不依赖 `member_status` 存在。残余 `op` 生命周期见 L5（low）。 |
| R4-low（认领已释放时不复位/不发旧终态） | `design.md:336-347`（Cancelled/Exception 分支先做 `is state` 身份判断）；`design.md:355-361`（`release_round` 仅当仍持有认领）；`design.md:369-374`（已释放则不动房间、不发旧 teardown）；`design.md:387-391`（后台 task 生命期）；`tasks.md:96-103`（2.7 同口径）；`design.md:376-377`（仍写「任何位置的意外异常都走 error teardown」） | 已修复（tasks/伪代码一致）；残余措辞 low | 所有释放点（正常路径、except、finally）均身份判断；`tasks.md` 2.7 已与设计一致；已释放认领的收尾任务被取消不重置 R2、不发旧终态。`design.md:376-377` 的总结性 bullet 仍未加身份限定，且 R4 L1 的「released-claim flush 窗口内 limit 终态不实时送达」未写进 Edge cases/Risks，见 L2（low）。 |

## X1/N1–N6 / F1–F13 关键项复核

| 条目 | 判定 | 备注 |
|---|---|---|
| X1 认领身份释放 | 未被破坏 | `design.md:332`（正常 reset→身份 release）、`:350-352`（finally 身份兜底）、`:359-361`（`release_round` 定义）、`:387-391`（异常路径只在仍持有认领时 schedule）；`tasks.md:41-47`、`:96-103`；R1 返回后 R2 仍 active、M3 queued 进 R2 的回归仍在。 |
| N1 pop 先于 flush / 收尾窗口 | 未被破坏 | `design.md:331-333`（reset → 身份 release → flush）；`:380-386`（reset/pop 之间无 await，flush/review/终态可放行新轮）；`tasks.md:42-47`（一次性有界 gate、R2 active、M3 queued）。 |
| N2 幂等 reset 与条件递增 | 未被破坏 | `specs/multi-agent-collaboration/spec.md:5`（表未变不递增、终态携带当前 seq）、`:76`、`:111`、`:126`（三处均「表实际变化才递增」）；`design.md:145-148`。 |
| N3 迟到 limit 终态仍重拉时间线 | 未被破坏 | `design.md:271-275`、`:594`（`applied=false` 只抑制头部/aria-live）；`tasks.md:66`、`:133-134`。测试可执行性见 L3（low）。 |
| N4 测试文案（合并语义） | 未被破坏（措辞仍有歧义） | `design.md:643-644`（「不要求每个迁移单独发」）、`tasks.md:32-37`；但 `design.md:679` / `tasks.md:52` 的「最终表」仍可被读成「最后一条表含 tool」，见 L4（low）。 |
| N5 `apply*` 返回契约 | 未被破坏 | `design.md:583-594`（统一 `{state, changed, applied}`，终态另含 `clearedAll`；`applied=false` 语义固定）；`tasks.md:121-127`。 |
| N6 本地绝对路径 | 未被破坏 | 对 change 目录全量 grep `/home/`、`/Users/`、`/mnt/`、`reference-repos`、`agent-study` 仅命中 R3/R4 报告对搜索模式的文字描述，无实际路径。 |
| F1 头部文案单一归属 | 未被破坏 | `design.md:481-490`（删除 `member_speaking` 头部文案；静默/失败/发言不清头部）；`specs/web-ui/spec.md:42-48`；M2 在其上补了轮次提示清除。 |
| F2 两条确定性顺序测试 | 未被破坏 | 跨轮迟到终态：`design.md:650-654`、`tasks.md:38-41`；握手首帧：`design.md:687-691`、`tasks.md:56-60`；均含变异验证。 |
| F3 建会话失败走统一 helper | 未被破坏 | `design.md:310-312`；`tasks.md:93-95`。 |
| F4 重置幂等 | 未被破坏 | `design.md:145-148`；`specs/multi-agent-collaboration/spec.md:5`；`tasks.md:85-88`。 |
| F5 正常 round_ended 前 flush | 未被破坏 | `design.md:299-303`、`:333`（reset/release 后 flush，再 review/terminal）；`tasks.md:96-99`。 |
| F6 自动滚入只动横向 | 未被破坏 | `design.md:534-535`；`tasks.md:141-142`。 |
| F7 benchmark smoke 触发口径 | 未被破坏 | `design.md:729-732`；`tasks.md:173-176`；checker 的 `agent/loop.py` 文本触发口径仍成立。 |
| F8 20 轮口径差异登记 | 未被破坏 | `design.md:894-895`；`tasks.md:16-19`。 |
| F10 不发送 idle 条目 | 未被破坏 | `design.md:248-250`。 |
| F11/F12 390px 头部与空状态 | 未被破坏 | `design.md:516-527`、`:711-713`；`specs/web-ui/spec.md:78-85`；`tasks.md:141-145`。 |
| F13 降级源清单 | 未被破坏 | `specs/web-ui/spec.md:5`（含仅降级时的 `member_speaking`）。 |

## 新 Findings

### T1（severity: medium）M1 分层后，真实 AgentLoop 事件到进度信号的 web 层映射没有任何确定性测试：「正在思考 / 正在输入」可在端到端静默失效

- **问题**: R4 的 M1 修法把 thinking/typing 的确定性断言下移到编排器/FakeRunner 层
  （`design.md:677-683`、`tasks.md:51-55`），这是对的；但 FakeRunner 是**直接调用
  `on_progress("iteration_started" / "assistant_delta" / ...)`**（`design.md:664-665` 的
  「并行工具聚合（FakeRunner 用 `asyncio.gather` 调 `on_progress`）」、`:665` 的 resume
  语义同理），完全绕过了真正新增的 `ProgressObserver` / `ProgressHook` 与 `on_event` 旁路
  （`design.md:186-205`，代码接缝 `web/session.py:2015-2016`、`agent/loop.py:790`、
  `:1282-1309`）。WS 层测试按修法只断言「最终表 / 关键状态（如 tool）出现」
  （`design.md:679`、`tasks.md:52`）；非流式测试只断言「没有 typing」。这两类断言都**不要求**
  正向出现 thinking/typing，也都不要求 `iteration_started` / 首个 `assistant_delta` /
  `stream_complete` / `run_completed` 的信号名与去重语义。`tasks.md:45-47`（1.3）只列了
  `on_progress` 的「不传行为不变」「回调抛异常不影响 turn」；`design.md:220` 的生命周期测试
  只要求「连续两次 run 只看到一组信号」与「回调抛异常不影响 turn」。换句话说，**web 层的翻译
  表没有任何一条测试钉住它**。
- **失败场景**: 实现按设计保留 reducer、编排器与 emitter，但 `_run_session_locked` 的映射写错：
  例如 `before_iteration` 没有发出 `iteration_started`，或 `assistant_delta` 分支只透传而不发
  进度信号，或 `before_iteration` 没有重置 `saw_delta`（导致第二次 LLM 调用不再发 typing）。
  此时：
  1. WS 层流式测试仍绿——最终表为空、tool 态在 Bash `sleep` 期间可见（`design.md:684`）；
  2. 非流式「没有 typing」测试仍绿——缺失 wiring 只会让 typing 更少；
  3. FakeRunner/编排器测试仍绿——它自己直接发正确信号；
  4. JS 纯函数测试仍绿——状态模型本身正确。
  生产表现：成员从 `slot_started` 的「运行中」直接跳到工具/终态，整轮**从不出现**「正在思考 /
  正在输入」——这正是 issue #307 的主诉求。变异「删掉 `assistant_delta` 映射」在现有测试计划下
  不会变红，属于假保护。
- **证据**: `design.md:677-683`、`:679`（WS 只断言最终表/tool）；`tasks.md:51-55`、`:52`；
  `design.md:643-644`、`:664-665`（编排器层由 FakeRunner 注入信号）；`design.md:186-205`
  （web 层映射表）；`design.md:213-220`（只列生命周期/异常测试）；`tasks.md:45-47`；
  `tests/support/llm_harness.py:88-90`（`StreamScript` 同步 yield，不能在 web 层制造让出点）；
  `tests/agent/team/test_orchestrator.py:35-58`（FakeRunner 签名与直调）；
  `web/session.py:2015-2016`（待接线的 `on_event` 闭包）；`agent/loop.py:790`、
  `:1282-1309`（真实事件源）。
- **建议修法**（局部补测试，不推翻 M1 的分层）:
  - 在 `tests/web_tests/test_group_chat_team.py` 的 `TestRunnerContract`（既有真实
    `AgentSession` + `ScriptedLLM` 先例）增加一条**不依赖 emitter/WS 时序**的映射测试：
    用 `WebSessionRunner.run(..., on_progress=collector)`（或直接
    `SessionManager.run_session(..., progress=collector)`）跑一个流式 `ScriptedLLM`；
    断言 collector 收到 `run_started`、每次 LLM 调用一个 `iteration_started`、每次调用
    **至多一个** `assistant_delta` 且不含 token 文本、`stream_complete`、`run_completed`；
    再加一个两迭代（先工具后 LLM）的脚本，断言第二次 `before_iteration` 后仍会再发
    `assistant_delta`（验证 `saw_delta` 重置），以及 `tool_started` / `tool_finished` 带
    `tool_call.id` / `name`。非流式脚本断言没有 `assistant_delta`。该测试不需要事件循环
    让出点，因为 Hook/`on_event` 到 observer 的调用是同步 await 的。
  - 或把「慢速脚本 LLM」从 tasks 1.4 的「如需」改成**必须**：用带显式让出点的脚本在 WS 层
    断言先出现含 thinking 的表、再出现含 typing 的表；但第一种做法成本更低且更直接。
  - 把上述断言写进 `tasks.md` 1.3/1.4（如 1.3.1）与 design 的 Testing Strategy 3 / Decision 3
    测试条；做变异验证（删掉 `before_iteration` 或 `assistant_delta` 映射 → 测试变红）。
    这不会把 thinking/typing 重新拉回不可确定性的 WS 断言，只是补上被 M1 分层遗漏的
    web 层翻译覆盖。

### L1（severity: low）`MemberStatus` 的 `status_seq` 措辞与「无成员级 seq」的定案不一致

- `tasks.md:78-79`（2.1）写 `MemberStatus`（phase / 在途工具映射 / `status_seq`），但
  `design.md:228-244`（4.1 载荷）与 R1 C25 明确**条目不带成员级 seq**，只有房间级
  `status_seq`。实现者可能给每个成员分配 seq 并塞进条目，与「全量表 + 房间 seq」的排序模型
  冲突。建议把 tasks 2.1 改为「`MemberStatus` 只含 phase/tools；`status_seq` 由编排器每房间
  维护」，与载荷 schema 一致。

### L2（severity: low）R4 L1 的两处残余未收敛

- ① `design.md:376-377` 仍写「任何位置的意外异常都走 `error` teardown」，未加「仅当
  `_rounds.get(room_id) is state`」；虽被 `:369-374` 与伪代码限定，总结性 bullet 仍可能被
  照字面实现。② R4 L1 的附带口径——「达上限并在 flush 期间发起连接关闭时，其他标签页不会
  实时收到 `round_ended(limit)`，limit 条目要等重连/刷新」——仍未写进 Edge cases 或 Risks。
  建议补一句，避免实现者把「不发旧终态」误当成丢 limit 提示的 bug 去修。

### L3（severity: low）tasks 1.5 的「迟到 limit 终态调用方仍重拉时间线」在 node + vm 纯函数测试中不可直接断言

- `tasks.md:66` 要求在 `test_group_status_js.py`（node + vm）断言「返回 `applied=false`
  但调用方仍重拉时间线」。前者是 `group_status.js` 纯函数可测的；后者是 `group.js` 的
  WS 分发逻辑（`web/static/group.js:276-288`），node + vm 测试不加载 `group.js`，无法观察
  fetch 调用。实现者很可能只断言 `applied=false`，造成 N3 行为的假保护。建议二选一：
  让纯函数返回 `reloadTimeline`/等价动作并在 node 测试断言；或在浏览器群聊 fixture 中用
  fetch 计数器构造「先应用新 seq 状态、再喂旧 limit 终态」，断言重拉发生一次且状态未回退。

### L4（severity: low）「最终表」措辞仍可能重蹈 N4 歧义

- `design.md:679` / `tasks.md:52` 的「WS 层断言最终表与关键状态（如 tool）出现」没有说明
  「最终表」是终态后的空表还是事件流中曾出现的表；`design.md:643-644` 的编排器测试也写
  「最终完整表」。N4 的教训是必须写「事件流中**曾出现** tool 表；回合终态后最终表为空且与
  snapshot 一致」。建议把这两处改成该口径，避免测试实现者取最后一条 `member_status` 断言
  含 tool 而假红/弱化。

### L5（severity: low）`op`（发送失败）提示在成功重试后没有清除规则

- Design 只规定 `clearRoundStatus()` 只清 `kind === "round"`，`conn`/`op` 不被轮次清除
  （`design.md:491-495`、`tasks.md:134-136`）。这满足了「连接/错误提示优先」，但
  HTTP 降级路径的「发送失败：...」属于 `op`：用户随后重试成功（HTTP 或重连后的 WS）时，
  没有 setStatus 成功路径去清除它，头部可能长期停留「发送失败」而 presence 已正常。
  建议明确 `op` 在成功发送/新一轮开始时清除（与 `conn` 区分），或在 tasks 4.3 注明
  「`op` 只在同类成功动作时清除」；不阻塞本轮。

### L6（severity: nit）时间线事件重绘 presence 可能重置状态条横向滚动

- Design 要求 `member_status` 不调用 `renderRoom()`（`design.md:506-507`），但 `user_message`
  / `member_post` 的既有路径会 `renderRoom()`；若实现把 `renderMembers()` 替换为
  `renderMemberPresence()` 并沿用 `renderRoom()` 调用，每次新消息都会重建 presence，用户的
  横向滚动位置可能被重置。建议明确 `renderRoom` 只在 room_state/members 变化时重绘 presence，
  或重建后保留 `scrollLeft`；与 F6 的「只动横向滚动」自洽。

### L7（severity: nit）反定时器浏览器断言只有 1.5s

- `tasks.md:69` 的无事件 1.5s 停顿能抓住短周期定时器，但抓不住 2s 以上的 `setInterval`。
  建议补一个静态断言（`group.js` / `group_status.js` 中状态推进不出现定时器）或把等待
  延长到超过任何可能的展示时钟；后者成本高，静态检查更可靠。

### L8（severity: nit）backlog 已引用尚不存在的 `reviews/grill-adversarial.md`

- `docs/openspec-change-backlog.md:122` 写「设计证据见 ... `reviews/grill-adversarial.md`」，
  当前只有 `grill-design.md` 与 R1–R4；R5 通过后必须把收口报告落为规范文件名
  `reviews/grill-adversarial.md`（design `Pre-Implementation Review` 已计划），否则归档点
  checker 的 grill 证据检查会红，且 backlog 的引用暂时是悬空的。

## 已确认站得住的部分

- **取消/异常矩阵（X1/R4-low）**：正常路径 reset（同步）→ 身份 release → flush → review →
  终态；Cancelled/Exception 仅在 `_rounds.get(room_id) is state` 时 reset + 调度后台 teardown；
  已释放认领时只记录并 re-raise；finally 的兜底 reset/release 都带身份判断。逐条核对
  「R1 已释放、R2 已认领、R1 收尾任务被取消」窗口，R2 的 `_RoundState`、`round_active` 与
  状态表不会被旧轮改写；空表 no-op reset 返回当前 seq，新轮 `slot_started` 仍使旧终态 seq
  严格更小（首 slot 被 `slot_skipped` 时不存在新状态事件，旧终态应用并清空是正确的）。
- **N1/termination/flush 顺序**：limit system 条目与 termination 在 reset/pop 之前同步完成；
  pop 在 flush 之前，收尾窗口内新消息开新轮而不是排队进已结束的轮次；flush 在 pop 之后、
  review/terminal 之前；reset/pop 之间无 await。`tasks.md` 1.2.2 的 gate 是一次性、有界等待，
  含 R2 active 与 M3 queued 断言，变异口径完整。
- **协议/时序**：全量表 + 房间级 `status_seq`；客户端 `member_status` 用 `<=` 丢弃、终态用
  `<` 丢弃/相等应用；终态携带重置后 seq；快照重置水位（服务端重启 seq 变小也接受）；
  `slot_started` 使跨轮 seq 严格更大；`room_state` 首帧 + 锁内同步构造快照 + 订阅后所有发送
  同一把锁 + try/finally unsubscribe；订阅前的在途 emitter payload 即使晚到也因 seq 更旧被
  丢弃；双标签页/慢客户端/空表 no-op/重连快照逐条核对未发现新的错误丢弃或清空。客户端
  `connectionEpoch` 隔离旧 socket 尾部事件；`room_state` 的 `round_active=false` 清空全表。
- **M2 头部生命周期**：`conn`/`round`/`op` 分类；新一轮 `user_message(queued=false)` 与首个
  非空闲 `member_status` 清 round；被 seq 丢弃的终态不改头部但 limit 仍重拉；旧服务端降级
  路径也有 `user_message` 清轮次提示；与 F1 的「成员状态只归 presence」及 web-ui 的
  「提示区互不覆盖」场景自洽。
- **reducer 与代码事实**：`tool_started`/`tool_finished` 取 `before_tool_execute` /
  `after_tool_execute`（`agent/loop.py:1417`、`:1447`）；`iteration_started` 无条件清空在途
  工具覆盖非 Bash 异常跳过 after（`:1420-1439`、`:1500-1513`）；resume 无 `run_started`、
  `before_iteration` 为 thinking 权威（`:709-743` vs `:790`）；非流式无 `assistant_delta`
  （`:1389-1395`）；`on_error` 不映射 run 终态（`:877`、`:1427`、`:1431`）；生产
  `WebSessionRunner` 已把空文本归一为 silent（`web/session.py:2226-2227`）；`Hook` 七方法
  全实现、逐 run 新实例、覆盖整个 run 的 finally 按身份摘除。三处 `SessionRunner` 实现
  （`web/session.py:2178`、`web/team.py:222`、`tests/agent/team/test_orchestrator.py:35`）
  均在设计与 tasks 中列全。
- **规格/需求**：issue #307 的五档状态、工具名、真实事件驱动（无定时器）、出口回 idle、
  移动端 390px、不可观测不假装（非流式无 typing、子 agent 内部不可见、预拒绝工具无开始）在
  两份 spec delta 与设计中均有落点；ADDED/MODIFIED 自洽，MODIFIED 保留既有三出口并新增取消
  teardown 非出口场景；`member_failed.name`、群公告独立元素、aria-live、
  prefers-reduced-motion、旧服务端/旧前端双向降级完整。
- **门禁与文档**：OpenSpec strict 29/29 通过；瘦 checker exit 0；RIR `research_tier: full`
  字段与 findings 完整，无本地绝对路径；backlog 已登记 #307 且有 `backlog_updated` 事件；
  benchmark smoke 按 checker 文本触发口径列入 tasks 6.6；witnessloop 三份 manifest 属归档点
  产物，active 阶段不要求；Q1/Q2/Q3 仍是真实待确认项，`reviews/grill-design.md` 的
  `## User Confirmation` 仍为「待用户答复」，`tasks.md` 0.4 未勾——这是正确的停轮状态，不是
  本轮缺陷。Q3（issue 原文的「多成员并发」按「每人独立一行、串行执行」解释）**仍需用户确认**。

## Verdict

CHANGES_REQUESTED

- 理由: M1/M2/R4-low 已按 R4 的口径修复；X1/N1–N6/F1–F13 关键项未被本轮修改破坏；门禁
  （OpenSpec strict、瘦 checker、RIR、backlog、benchmark smoke 口径）通过。但最后一轮扫查
  发现 **1 条新 medium（T1）**：M1 把 thinking/typing 的确定性断言下移到 FakeRunner 后，
  真实 AgentLoop 事件 → `ProgressObserver`/`Hook` → 进度信号的 web 层映射没有任何测试钉住；
  WS 层只断言最终表/tool，非流式只断言「没有 typing」，FakeRunner 直接注入信号，因此删掉
  `before_iteration` 或 `assistant_delta` 映射时整套测试仍绿，核心的「正在思考 / 正在输入」
  可在生产静默失效——这是典型的假保护。修法是局部的（在既有 `TestRunnerContract` 真跑
  `WebSessionRunner` 的路径上补信号序列断言 + 变异验证），不构成推倒重开的根本矛盾，因此
  不判 BLOCKED，但本轮不能作为写码许可。
- 另有 5 条 low（L1 `MemberStatus` seq 措辞、L2 R4 L1 残余、L3 limit 重拉测试不可在 node
  vm 直接断言、L4「最终表」措辞、L5 `op` 提示清除）与 3 条 nit（L6–L8），均不阻塞；建议随
  T1 一并收敛 L2/L3/L4。
- T1 修复并重跑一轮有界对抗（R6）确认后，才可把收口报告落为规范文件名
  `reviews/grill-adversarial.md` 并进入实现。Q1/Q2/Q3 仍受停轮约束：在用户答复写入
  `grill-design.md` 的 `## User Confirmation` 之前，不得写实现/测试代码。
