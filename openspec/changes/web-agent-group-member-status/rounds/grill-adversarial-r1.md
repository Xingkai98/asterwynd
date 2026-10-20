# 设计对抗 R1: web-agent-group-member-status

## Reviewer

- run id: adversarial-agent-paseo
- 时间: 2026-10-20
- 零记忆: 是
- 方法: 完整读 `AGENTS.md`、本 change 的 proposal/design/tasks/两份 spec delta/`reviews/grill-design.md`、issue #307 正文与 2026-10-20 调研 comment；独立核对 `agent/team/orchestrator.py`、`agent/team/runner.py`、`agent/hooks/manager.py`、`agent/loop.py`（run/resume、`_call_llm`、`_execute_single_tool`/`_execute_tool_calls`、max_iterations 出口）、`web/session.py`（`run_session`/`_run_session_locked`/`WebSessionRunner`）、`web/team.py`（`RoomEventBus`/`_WorkspaceRunner`/`TeamService`）、`web/server.py`（房间 WS 握手/断开）、`web/static/group.js`、`web/static/index.html`、`web/static/style.css`、既有规格、相关测试与 `.witnessloop/policy.json`；只读运行 `npx @fission-ai/openspec@1.4.1 validate --all --strict`（29/29 通过）与 `uv run python scripts/check_openspec_artifacts.py --base-ref origin/master --require-base`（通过）。未写实现/测试代码。所有行号相对基线 `48d25f0`。

## C1–C27 核对表

| 条目 | 当前证据（文件:行号） | 判定 |
|---|---|---|
| C1 | `design.md:220-245`（完整非空闲表 + 房间级 `status_seq`，显式拒绝「每成员一条 + 房间级水位」）；`design.md:258-271`（客户端整表替换）；`specs/multi-agent-collaboration/spec.md:5` | 已落实 |
| C2 | `design.md:273-277`（终态按 seq 守卫的跨轮理由）；`design.md:316-340`（同步重置先于 pop/await）；`design.md:344-348` | 已落实（服务端；客户端测试覆盖见 F2） |
| C3 | `design.md:258-264`（新连接 epoch++、水位归零、快照即使 seq 更小也接受）；`specs/multi-agent-collaboration/spec.md:100-105` | 已落实 |
| C4 | `specs/multi-agent-collaboration/spec.md:5`（SHALL/M- MAY 合并）；`design.md:577-579`（断言最终表 + 关键子序列） | 已落实 |
| C5 | `design.md:40-43`、`:536`（防御性契约，生产 `WebSessionRunner` 已归一）；`specs/multi-agent-collaboration/spec.md:44-49` | 已落实 |
| C6 | `design.md:136-140`（按 id 记账、`iteration_started` 清空）；`design.md:543`；`specs/multi-agent-collaboration/spec.md:29-35` | 已落实 |
| C7 | `design.md:249-252`（终态带重置后 seq）、`:304-306`（统一 helper）已修；但 `design.md:300-302` 建会话失败分支仍写「发 `member_failed`（带 `status_seq`）+ 重置该成员」，即先发后重置，且未走 helper | **部分**（见 F3） |
| C8 | `design.md:330-335`（`except Exception` → 同步重置 + `round_ended(error)`）；`:539-540` | 已落实 |
| C9 | `design.md:349-351`（强引用后台 task + `wait_for(..., 2)`）；`specs/multi-agent-collaboration/spec.md:107-113` | 已落实 |
| C10 | `design.md:381-411`（锁内构造快照 → 订阅 → 首帧，整段 try/finally） | 已落实（确定性回归测试见 F2） |
| C11 | `design.md:283-285`（仅 `on_event is None` 才不调度；无人订阅交给 broadcast 返回 0） | 已落实 |
| C12 | `design.md:85-87`（resume 无 `run_started`，`before_iteration` 权威）；`:549`；`:585` | 已落实 |
| C13 | `design.md:442-444`（不复用 `#group-room-status` 作 presence 摘要） | 已落实（头部 speaking 文案的生命周期是另一个问题，见 F1） |
| C14 | `design.md:440-441`（独立 `#group-room-notice` / `renderNotice()`）；`:425-428`（DOM） | 已落实 |
| C15 | `design.md:417-437`（presence 放进 `#group-room`、头部之后、`.group-room-body` 内） | 已落实 |
| C16 | `specs/multi-agent-collaboration/spec.md:122-156`（MODIFIED 既有「房间级互斥与轮次终止」，明确 teardown 非第四出口） | 已落实 |
| C17 | `design.md:504-506`（断线保留最后状态并标过期，重连快照整体替换）；`specs/multi-agent-collaboration/spec.md:76` 末句；`specs/web-ui/spec.md:5` | 已落实 |
| C18 | `design.md:512-514`（`member_failed` 增 `name`，语义扩到建会话失败）；`specs/multi-agent-collaboration/spec.md:5`、`:55` | 已落实 |
| C19 | `design.md:202-207` 已改为仓库名 + 相对路径；但 `reviews/grill-design.md:45` 仍含本地参考仓库绝对路径 | 已落实（记录文件残留，见 F9） |
| C20 | `design.md:457-459`（`group_status.js` 先于 `group.js`，两个 `?v=` 递增）；`tasks.md:109-110` | 已落实 |
| C21 | `design.md:192-193`（Hook 全 7 方法）；`tasks.md:64-65` | 已落实 |
| C22 | `design.md:172-174`（`WebSessionRunner` / `_WorkspaceRunner` / `FakeRunner` 三处） | 已落实 |
| C23 | `design.md:588-590`（on_progress 契约测试放 `test_group_chat_team.py` 或 `test_orchestrator.py`） | 已落实 |
| C24 | `design.md:357-367`（`status_snapshot()` 一次返回表与 seq） | 已落实 |
| C25 | `design.md:228-232`（条目仅 `persona_id/phase/tools/tool_count`，无成员级 seq；房间级 seq 唯一） | 已落实 |
| C26 | `design.md:269-270`（兜底仅 idle/未知时置 running，不降级） | 已落实 |
| C27 | `design.md:604-605`（按收集到 `round_ended` + 安全上限，不硬编码 12）；`tasks.md:39-45` | 已落实 |

## Findings

### F1（severity: medium）头部 `#group-room-status` 的「正在发言…」没有生命周期，与 presence 产生同视图矛盾状态

- **问题**: 设计保留 `member_speaking -> setStatus("X 正在发言...")`（`design.md:442-444` 的调用点清单明确包含 `group.js:254` 这一处），并声明「presence 自身就是状态展示；连接/操作提示继续留在头部，两者不互相覆盖」。但 `member_silent` / `member_failed` / `member_post` 都只清 `state.speaking`，**不清头部文案**（`web/static/group.js:255-267`），`member_speaking` 的文案只会在下一个 `member_speaking`、`round_ended`、发送失败或重连时被覆盖。结果：甲静默或失败后，头部仍写「甲 正在发言...」，presence 已把甲显示为「空闲」。
- **失败场景**: 3 人房间，甲先发言后静默 → `member_silent` 到达（`group.js:255-259` 只改 chip/speaking），随后轮次轮到乙长时间思考 → 头部仍是「甲 正在发言...」，presence 显示「甲 空闲 / 乙 正在思考」。这直接违反 `specs/web-ui/spec.md:7-13` 的「SHALL NOT 在同一视图对同一成员显示互相矛盾的状态」，而设计列出的「状态栏与提示区域互不覆盖」场景（`specs/web-ui/spec.md:35-40`）只覆盖 `member_status` 对「已连接」的覆盖，测不到静默/失败路径。另一条时序：旧轮 `round_ended` 在新轮尚无状态事件时到达（`lastStatusSeq` 相等，不会被丢弃），头部被写成「本轮结束」，而 presence 已显示新轮成员忙。
- **证据**: `web/static/group.js:249-254`（speaking 写 setStatus）、`:255-259`（silent 不写）、`:260-267`（failed 不写）、`:369-372`（setStatus）；`design.md:442-444`（保留该调用点且声称两者不互覆盖）；`specs/web-ui/spec.md:5`、`:7-13`、`:35-40`。
- **建议修法**: 在设计与 tasks 4.3 明确头部文案的单一归属与生命周期：推荐删除 `member_speaking` 的 `setStatus`，成员状态完全交给 presence（头部只保留连接/错误以及中性的轮次提示）；或定义「终态清空 speaking 文案、`round_ended` 仅在无更新状态时更新头部」。补一条纯 JS/浏览器回归：`member_speaking → member_silent` 后头部不再出现「正在发言」，且任一时点头部与 presence 对同一成员不矛盾。

### F2（severity: medium）核心顺序不变量没有确定性回归测试：`room_state` 首帧与跨轮迟到终态

- **问题**: 本 change 的协议安全性建立在两个顺序不变量上：(a) 订阅后的事件不得先于 `room_state`（send_lock + 锁内构造快照）；(b) 旧轮 `round_ended` 的 seq 必须小于新一轮首个状态 seq，客户端据此丢弃迟到终态。设计的测试清单只列了「run 中打开第二条房间 WS：首帧是 `room_state`」（`design.md:600-601`）和 JS 的「迟到 seq 丢弃」（`:609-613`），但**没有**一个测试强制在握手 `await ws.send_json(snapshot)` 期间发生 broadcast，也没有测试强制在 `review` await 窗口内开新轮再让旧 `round_ended` 到达。按当前 `tests/web_tests/test_group_chat_server.py:230-251` 的写法，旧实现（先 subscribe 后发快照，`web/server.py:651-661`）在这条测试里**通常也能通过**——race 只是概率性的；而客户端 `applySnapshot` 接受更小 seq（`design.md:262-264`），一旦竞态回归，会把先到的状态事件用更旧的快照覆盖，静默回退且无测试报警。
- **失败场景**: 开发把握手改回「sync subscribe → await send room_state」；普通第二条连接测试执行时恰好没有 broadcast 落在该 await 上 → 测试绿。线上当 emitter 任务在该窗口读到表并 broadcast 时，客户端先收 `member_status(seq=17, 甲 tool)` 再收 `room_state(seq=16, 甲 idle)` → 甲的 presence 显示空闲直至下一次变化。跨轮同理：去掉「reset 先于 pop」或客户端终态 seq 守卫后，现有用例不会稳定变红。
- **证据**: `design.md:381-413`（不变量与实现）、`:594-627`（测试清单没有强制 race）；`web/server.py:651-661`（现状无锁窗口）、`:695-699`（现状 finally）；`specs/multi-agent-collaboration/spec.md:76`（「订阅后的状态事件 SHALL NOT 先于快照到达」）、`:93-98`（跨轮终态）；`tests/web_tests/test_group_chat_server.py:230-251`。
- **建议修法**: 增加确定性测试：把 `ws.send_json`（快照首帧）替换为可阻塞的 fake，在阻塞期间调用 `room_bus.broadcast`，断言客户端先收 `room_state`；以及编排器测试用 gated review/review sink 在 `_rounds` 已 pop 后启动新一轮并发出状态，再放行旧 `round_ended`，断言（i）旧终态 seq 更小、（ii）JS 纯函数丢弃它后新轮状态不被清空。两项都应做变异验证（移除锁/守卫 → 变红）。

### F3（severity: low）C7 残留：建会话失败出口仍是「先发 `member_failed` 再重置」

- **问题**: `design.md:300-302` 的建会话失败分支与 `design.md:249-252`「终态携带**重置后**的 `status_seq`」、`:304-306` 的统一 helper 矛盾；该出口也没有写明走 `_finish_member`。
- **失败场景**: 实现者照 5.1 第 2 条字面实现：先 `await _emit(member_failed, status_seq=当前N)`，再 reset 到 `N+1` 并让发射器发空表 `N+1`。用户态通常仍正确（终态 N 先到、空表 N+1 后到），但终态 seq 不是规格要求的「重置后」值；若发射器在终态之前发出空表 `N+1`，客户端会按 seq 丢弃终态（状态已被空表清空，恰好无感），测试若断言「终态 seq == 重置后 seq」则变红。该分支还是唯一没有复用统一 helper 的终态出口。
- **证据**: `design.md:300-302`、`:304-306`；`specs/multi-agent-collaboration/spec.md:5`（「SHALL 携带重置后的 `status_seq`」）。
- **建议修法**: 第 2 条改为「写 system 日志 + `_finish_member(persona_id, "member_failed", ...)`」，并在 `_finish_member` 内统一「同步重置 → seq++ → flush → 用新 seq 发终态」；回归测试断言该路径终态 seq 与 `status_snapshot()` 一致。

### F4（severity: low）幂等重置与「只在变化时发 / 相同表不重复」冲突，可能多发空表事件

- **问题**: `_finish_member` 已重置一次（seq N → 终态），`_run_slot` 的 finally「无条件重置（幂等）」（`design.md:312`）若按「重置就递增 seq + 标脏」实现，会在终态之后再发一次同表的空表事件（seq N+1）。设计没有定义幂等重置是否递增 seq，也没有定义发射器对「表相同但 seq 不同」是否跳过；`design.md:579` 的测试要求「`member_status` 只在变化时发；相同表不重复」。
- **失败场景**: 一个正常回合约产生 2 条冗余 `member_status`（终态后的空表），实现者可能改宽测试而不是修逻辑；`slot_skipped` 路径若 finally 包得过宽，还会为从未忙过的成员递增 seq。
- **证据**: `design.md:312`、`:579`；`agent/team/orchestrator.py:401-409`（skip 在 slot_started 之前）。
- **建议修法**: 定义 `reset_member` 仅在成员当前非 idle 时递增 seq/标脏；finally 的重置按 id 幂等且不产生新 seq；发射器附带「表指纹」或在表未变时不发射。测试明确断言正常回合不产生重复表事件。

### F5（severity: low）正常 `round_ended` 路径未按 Decision 4.4 先 flush

- **问题**: `design.md:292-294` 规定终态顺序是「重置 → `await _flush_status_emits` → 发终态」，但 `design.md:316-324` 的正常路径只 reset → termination → pop → review → `await _emit("round_ended")`，没有 flush；`_finish_member`（`:304-305`）有 flush。
- **失败场景**: 在 reset 前已读到旧表的在途发射任务，其 payload 可能在 `round_ended` 之后才送达；客户端会按 seq 丢弃，用户态通常正确，但这与设计声明的顺序保证不一致，且测试拿不到确定性（flush 是测试确定性的唯一抓手）。
- **证据**: `design.md:292-294`、`:316-324`、`:304-305`。
- **建议修法**: 正常路径在 reset 后、pop 前调用 `await _flush_status_emits(room.id)`，与其它终态出口同构；或明确写出「正常路径允许在途旧 payload、由 seq 兜底」并补对应测试。

### F6（severity: low）移动端 `scrollIntoView({inline:"nearest"})` 可能纵向滚动页面，打断用户滚动

- **问题**: 方案 A 的「当前非空闲成员变化时 `scrollIntoView({inline:"nearest"})` 自动滚入」（`design.md:473-474`）没有指定 `block:"nearest"`；默认 `block:"start"` 会滚动所有可滚动祖先，把 presence 条滚到视口顶部，移动端时间线/输入区随之位移。
- **失败场景**: 390×844，用户正在向上翻看时间线，甲从 thinking 变 typing → 自动滚入把页面纵向滚到 presence，用户正在阅读的消息移出视口；违反 `specs/web-ui/spec.md:5` 的「状态更新 SHALL NOT ... 打断用户滚动」。
- **证据**: `design.md:468-474`；`specs/web-ui/spec.md:5`、`:28-33`。
- **建议修法**: 改为 `{inline:"nearest", block:"nearest"}` 或直接设置横条容器的 `scrollLeft`；只在目标项超出可视区时滚动；浏览器测试断言时间线 `scrollTop` 不变。

### F7（severity: low）「benchmark smoke 预计不触发」与 checker 实际行为不符

- **问题**: `design.md:635-637` 与 `tasks.md:137-138` 称本 change 未触及 `agent/loop.py` / `agent/tools/` / `benchmarks/`、预计不触发 benchmark smoke。但 `_requires_benchmark_smoke` 扫描的是 **proposal 全文**：`proposal.md:115` 的 `agent/loop.py:1389-1395`（反引号内）命中 `scripts/check_openspec_artifacts.py:47-53` 的模式，`:419-425` 因此返回真。tasks 6.6 已写 smoke 项，所以当前 checker 通过（实测 exit 0），但设计的判断会误导实现者跳过实际执行。
- **失败场景**: 实现者信「预计不触发」而把 6.6 当作可略项；虽然机械门禁只检查任务文本，但「无触发面」的结论在评审/归档说明里是假事实。
- **证据**: `design.md:635-637`；`proposal.md:115`；`scripts/check_openspec_artifacts.py:47-53`、`:419-425`。
- **建议修法**: 改为「checker 会触发（proposal 引用了 `agent/loop.py`），tasks 6.6 已覆盖；实现期按需真跑并记录」。

### F8（severity: low）tasks 的「无轮数上限」与仓库现行规则不一致

- **问题**: `tasks.md:16-17` 写「按批次模型收敛到 `PASS`（无轮数上限；停止条件 = 收敛）」，而 `AGENTS.md:18`、`:104`、`docs/requirements-process.md:45` 与 checker 文案仍规定「最多 20 个已收口轮」。
- **失败场景**: 第 20 轮后仍未收敛时，按 tasks 继续开轮而按 AGENTS 应判超上限 `BLOCKED`；归档评审时两份文档互相打脸。
- **证据**: `tasks.md:16-17`；`AGENTS.md:18`、`:104`；`docs/requirements-process.md:45`。
- **建议修法**: 当前 change 内按 `AGENTS.md` 的 20 轮口径写（或引用明确的规则更新 change 编号），不要在本 change 里单方面改规则；若确已由 #314 取消上限，应另开 docs/process change 同步 `AGENTS.md` 与 checker 文案。

### F9（severity: nit）grill 记录仍提交了本地参考仓库绝对路径

- **问题**: C19 只清理了 `design.md`；`reviews/grill-design.md:45` 仍写了本地参考仓库的绝对路径，与「不要把参考仓库路径作为可提交项目资产」冲突。
- **证据**: `reviews/grill-design.md:45`；`AGENTS.md:43-45`。
- **建议修法**: 改为仓库名/相对路径，或删除该引用（保留「旧设计含绝对路径」的事实描述即可）。

### F10（severity: nit）「不发送 idle 的 member_status」措辞与全量表移除语义易误读

- **问题**: `design.md:244-245` 同时写「不发送 idle 的 member_status」和「全量表也会自然移除已变 idle 的成员」。后者本身就是一条携带空/缩减表的 `member_status` 事件；实现者若按字面只在表非空时发射，终态后的空表不会发出，虽然终态能清状态，但「表与快照一致」的测试口径会含糊。
- **证据**: `design.md:236-245`。
- **建议修法**: 改成「不发送 phase=idle 的成员条目；移除 idle 条目仍通过完整表事件（或终态）表达」。

### F11（severity: nit）390px 房间头部新增抽屉按钮后的挤压未纳入设计与测试

- **问题**: 移动端共同前提要求在房间头部/视图顶部新增「群聊/人设」按钮（`design.md:463-466`），但头部已有群名、`#group-room-status`（`flex:1`）、设置、删除（`web/static/index.html:181-187`、`web/static/style.css:2141`）。设计没有说明 390px 下这些按钮如何换行/收纳；浏览器测试只断言时间线宽度 > 300px（`design.md:620-622`），头部溢出不会被判红。
- **证据**: `web/static/index.html:181-187`；`web/static/style.css:2141`；`design.md:463-466`、`:620-622`。
- **建议修法**: 在移动端形态中明确头部按钮的收纳（图标化/更多菜单/换行）并加一条 390px 头部不横向溢出的断言。

### F12（severity: nit）侧栏抽屉化后空状态文案仍是「从左侧选择或新建一个群聊」

- **问题**: `web/static/index.html:180` 的空状态提示在移动端（侧栏已折叠为抽屉）会指向看不见的左侧面板。
- **证据**: `web/static/index.html:180`；`design.md:463-466`。
- **建议修法**: 移动端改用「点左上角打开群聊/人设」之类的文案，或在空状态内提供抽屉入口。

### F13（severity: nit）web-ui spec 的事件驱动清单漏列 `member_speaking` 降级

- **问题**: `specs/web-ui/spec.md:5` 首句列「`member_status`、终态事件、`room_state` 快照」为唯一驱动源，同段末尾又要求旧服务端用 `member_speaking` 降级；清单与降级口径应一致（否则「只由这三类事件驱动」与「无 `member_status` 时用 `member_speaking`」字面冲突）。
- **证据**: `specs/web-ui/spec.md:5`。
- **建议修法**: 在首句补上 `member_speaking`（仅降级），或把降级句移入独立段落并明确其优先级。

## 已确认站得住的部分

- **全量表 + 房间级 seq 的协议在单进程单事件循环下自洽**：所有 WS 发送（快照、pong、广播）走同一把每连接锁后，同一订阅者的帧序按发起顺序 FIFO；终态 reset 先于 pop、新轮 seq 严格更大，客户端终态 `<` / 状态 `<=` 的守卫不会误清新一轮。跨成员/跨轮/多标签页/服务端重启的各条时序逐一核对未找到反例。
- **`iteration_started` 清空在途工具**确实覆盖非 Bash 异常跳过 `after_tool_execute` 的路径（`agent/loop.py:1420-1439`、`:1500-1513`），`tool_finished` 按 id 记账也避免同名工具互相抵消。
- **resume 不触发 `run_started`、`before_iteration` 作为 thinking 权威信号**与代码一致（`agent/loop.py:709-762`、`:790`）；`on_error` 不映射 run 终态的理由（`:877`、`:1427`、`:1431`）成立。
- **Hook 全 7 方法、三处 `SessionRunner` 实现、`status_snapshot()` 单一读、旧前端未知事件落 default、`member_failed.name` 文案修复**均已在设计中明确。
- **门禁自洽**：OpenSpec strict 29/29 通过；瘦 checker `--base-ref origin/master --require-base` 通过；`require_change_for` 覆盖 `agent/**`、`web/**`，本 change 存在；RIR `full` 字段完整；backlog 已登记并带 `backlog_updated` 事件；MODIFIED Requirement 与既有「三出口」规格同名，未丢失既有场景。
- **UI 的关键 DOM 结论成立**：presence 放 `#group-room` 内、头部之后，桌面 260/208/flex 与 ≤1000px/≤720px 断点在现有 `.group-layout` flex 结构上可实现；群公告移入独立元素、不复用 `#group-room-status`、脚本顺序与 `?v=` 递增都是正确的方向。

## Verdict

CHANGES_REQUESTED

- 理由: 存在 2 条 medium：F1（头部「正在发言…」与 presence 在同一视图给出矛盾状态，且静默/失败后不清理，违反 web-ui 新规格的「不得矛盾」场景）、F2（`room_state` 首帧与跨轮迟到终态这两条核心顺序不变量没有确定性回归测试，现有用例对旧实现也可能绿）。其余为 low/nit，其中 F3 是 C7 的残留、F4/F5 是发射器与终态的语义细节，建议随本轮一并收敛。
- 没有 high；没有发现协议自相矛盾或规格与实现无法同时满足的根本性冲突，因此不判 `BLOCKED`。

## 给主 session 的一句话

先修 F1（明确头部文案生命周期并补静默/失败回归）与 F2（补两条确定性顺序测试，并做变异验证），F3–F5 顺手收敛、F7/F8 改口径；修复后跑下一轮对抗验证收口即可，本轮不要停轮抛 Open Question。另：本文件只是第 1 轮工作件，归档门禁要求的是 `reviews/grill-adversarial.md`，收口时须把本文件与后续轮次合并/落为规范文件名。
