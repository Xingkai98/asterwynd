# 设计对抗审阅 r2（修复验证）：group-unlimited-discussion

## 基线

- 修复提交：`3a2ca57c`（`group-unlimited-discussion：对抗 r1 修正（design v4 + delta/tasks 对齐 I1–I12/L1–L18）`）；分支 `group-unlimited-discussion/2026-10-24`；design v4；审阅开始时工作树干净（本轮唯一新增文件即本报告）。
- 修复提交只动文档（design.md / 三份 delta / tasks.md / r1 报告），未动实现代码与测试；因此本轮验证对象是“文档是否真的把 I1–I12 钉死”，不涉及代码回归。
- 方法：逐条对照 r1 的 I1–I12 原文与 HEAD 版本文档，并对每处引用的代码结构做只读核对；不重审 grill C1–C22 主体，只判修复是否成立、是否引入新问题。新发现按严重度登记，不并入修复判定。
- 结构校验本轮复跑：`npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` → **29 passed, 0 failed**（只证明结构合法，不覆盖本报告 I10 的语义冲突）。
- 抽样核对为真的代码断言（供后续轮次复用）：`agent/team/orchestrator.py:326-341`（submit active 分支）、`:347-360`（认领先于任何 await）、`:371-384`（终止判定 + reset + release，无 await）、`:387-398`（review 先于 `round_ended`）、`:408-426`（取消/异常 teardown + finally）、`:428-434`（`_drive` 顶检查）、`:470-471`（`build_injection` 后 `advance_seen`）、`:676-679`（`_release_round` 身份判断）、`:699-725`（`_schedule_teardown`）、`:773-779`（`_emit` 吞异常）；`tests/agent/team/test_orchestrator.py:467-501`（可挂起 sink 下并发提交）、`:837-869`（收尾 flush 窗口新消息开新轮）；`web/server.py:489-497`（6 键 `_room_payload`）、`:604-605`（PATCH 白名单 5 键）、`:663-750`（房间 WS）、`:691-704`（`room_state`）、`:700`（`round_active`）、`:734-738`（create_task）、`:748-750`（断线 cancel）、`:641-661`（REST 挂到轮/链结束）；`web/team.py:201-212`（懒构造注入 orchestrator）、`:304-313`（`team_for` 缓存）、`:473-482`（`submit_room_message` 的 workspace 回落）、`:627-689`（房间 create/update）、`:691-710`（`delete_room` 不取消链）；`agent/config.py:1572-1582`（正整数 + 拒 bool helper）、`:1677-1713`（`_parse_team_config`）；`agent/team/models.py:134-147`（`from_dict` 缺省先例）；`agent/team/roomlog.py:110-140`（`build_injection` 返回 `current`）；`web/static/group.js:418-453`（`round_ended` 前端分档）、`:604-625`（`openDialog` 的 select 无 `disabled`）；`web/static/group_status.js:60-65`（严格小于守卫）、`:84-95`（`applySnapshot` 只在 `round_active=false` 清表）。

## Verdict

**CHANGES_REQUESTED**（轮内状态，非终态出口；进入批次 II，仅 I10 残余 1 条 medium）。I1–I9、I11–I12 共 11 条 ✅；**I10 部分修复（medium 未清）**：Q2 裁决在 design / MODIFIED 正文已改对，但同一 delta 的场景与 ADDED 例外清单仍写“不写房间日志”，构成 1 条 medium 规格矛盾。修复未引入新的 medium+。

## 逐条修复验证

| # | 状态 | 证据（文件:行号） | 备注 |
|---|---|---|---|
| I1 | ✅ | `design.md:61`（`current` 恒非 None）、`:67`（认领 + 第 1 轮骨架同一同步区）、`:82`（查—建—挂 current 无任何 await）、`:83`（之后才 append/await）；`design.md:187` ⑪、`tasks.md:37`；`tests/agent/team/test_orchestrator.py:467-501` | 三项要求全落地：同步区、`current` 不变量、可挂起 sink 用例。既有 `TestRoomMutexUnderSuspendingSink` 在首个 `user_message` emit 处阻塞时并发提交第二条，正是该窗口；按 v4 实现（active 分支读 `chain.current`）该用例通过，若实现成 `_RoundState` 字段则必红，回归保护成立。 |
| I2 | ✅ | `design.md:107`（single 共用链壳、跳过链级判定/事件/字段、三出口不变）、`:150`（single 零新事件、四键不变）、`:177`（`RoundResult` 新字段默认值）、`:187` ③；`tasks.md:24`、`:36`；`specs/multi-agent-collaboration/spec.md:90`（末尾 single 不触发）、`:179-184`（单轮场景负向断言） | 已显式钉死，且有“整字典四键快照 + 无 `discussion_*`/`system_entry` 负向断言”锁住；实现侧 single 仍走 `opening_slots`/三出口，与 `orchestrator.py:373-398` 现状兼容。 |
| I3 | ✅ | `design.md:58`（`rounds` 字段=已正常收尾轮）、`:88`（仅 completed/limit/all_failed 才 append）、`:109`（`rounds=len(chain.rounds)`；停止在第 3 轮中 ⇒ `rounds=2`、`rounds_started=3`）、`:187` ⑤；`specs/multi-agent-collaboration/spec.md:90`（rounds 只统计正常收尾轮）、`:119`（`rounds=2`、`rounds_started=3`） | 字段注释、决策、用例、delta 场景四处一致；被停止轮与取消中的当前轮都不进 `rounds`，“含被停止打断的轮”的旧表述已删。 |
| I4 | ✅ | `design.md:83`（`discussion_started` 发射点 + payload）、`:86`（k>1 `system_entry`）、`:103`（链结束 system 在同步区 append）、`:106` g（`system_entry` → `discussion_ended`）、`:128`（`request_stop` 首次 await 发 `discussion_stop_requested`）、`:145-148`（事件契约）；`specs/multi-agent-collaboration/spec.md:90`（新增两句发布义务） | 发射点与 delta 发布义务都补齐。备注（nit，不判 ❌）：链结束 `system_entry` 落在 `round_ended` 之后（`design.md:106`），与 r1 建议的“`round_ended` 前”顺序不同；但 delta 事件序、`tasks.md:43` 的断言序与前端处理均无冲突，属可接受实现顺序。 |
| I5 | ✅ | `design.md:63`（到达即同步写入）、`:74`（active 分支 append_user 后写 `pending_user_seqs`）、`:75`（`build_injection` 后按“注入看到的日志末条 seq”移除，显式排除窗口首条）、`:83`、`:87` c；`specs/multi-agent-collaboration/spec.md:90`（未消费消息定义）、`:157-163`（0 发言插话场景）；`agent/team/roomlog.py:110-140` | 写入/消费两端都钉死，且消费阈值取 `view["current"]` 末条可避免 24 条窗口截断误记；delta 场景在“末位成员切片构造后插话”下可达（第 11 行强制续轮，cap 耗尽时交安全阀 reason）。 |
| I6 | ✅ | `design.md:61`、`:69`（结束同步区 `_release_round(room_id, chain)`，身份对象=链）、`:71`（`finally` 兜底）、`:168`（取消同步区）、`:169`（teardown 带 `chain_id` + 每链至多一次 + `terminal_sent`）、`:171`（幂等）、`:187` ⑯；`agent/team/orchestrator.py:408-426`、`:676-679` | 身份对象、finally 兜底、teardown 链身份、取消后 `is_round_active=False` 且下一条 `queued=False` 的用例均已写。备注：`_schedule_teardown` 的“函数签名带 chain”未被点名，但 `design.md:169` 已把 payload 与一次性语义钉死，属实现细节。 |
| I7 | ✅ | `design.md:85` a（k>1 `opening_slots(room, "", ...)`，并明写“否则后续每轮只剩点名者”）、`:187` ②（开局 `@B` 房第 2 轮仍全员）；`agent/team/orchestrator.py:153-182` | 空串口径与回归用例都落地；“admin 先”由 ① 覆盖，“pending mentions 置顶/清空”由 ④ 覆盖。 |
| I8 | ✅ | `design.md:152`（宿主 `self._discussion_state` + 读取方法 `discussion_snapshot(room_id) -> {round, reason}`）、`:155`（`room_state` 恢复规则：`discussion_round>0` 显示第 k 轮，否则按 `discussion_reason` 终态）、`:189`（前端行“重连恢复状态文案”）；`specs/web-ui/spec.md:45`（恢复句列举 `room.discussion_mode`/`discussion_round`/`discussion_reason`） | 三项要求（宿主、恢复规则、重连用例）都定义。残留 low 见新发现 N2（`discussion_round/2` 笔误与链结束后 round 归 0 未明写），不影响本条成立。 |
| I9 | ✅ | `specs/multi-agent-collaboration/spec.md:90`（快照出口只列 ①–⑨，取消/异常单列并“优先于上述一切、不参与排序”）、`:176`（空成员退化的 `round_ended` 明确 SHALL NOT 携带 `chain_id`/`round_index`/`chain_continues`）；`design.md:81`、`:89-91`（决策表把取消/异常单列为“—”行）、`:150` | 两处矛盾均已修：优先级列表不再混入控制流；退化路径字段已声明。残留 low 见新发现 N13（ADDED 正文的全称句未限定，靠场景例外兜底）。 |
| I10 | ❌ | 已一致：`design.md:167-170`（Decision 8 与 Q2：断线取消写 system、error 不写、单轮不写）、`:210-215`（User Rulings Q1–Q4）、`:127-131`（Q3）、`:139`（Q4）、`specs/multi-agent-collaboration/spec.md:5`（MODIFIED 正文已写“链因断线取消 SHALL 写 system”）、`:90`（Q1 未消费消息段）、`:119`、`:142-148`（Q4 slot 间 + 越界上界）、`:157-163`（Q1 场景）、`specs/web-ui/spec.md:45`、`:82-87`（Q3 单轮零变化）；测试行 `design.md:187` ⑤⑥⑦。**仍不一致**：`specs/multi-agent-collaboration/spec.md:54-55`（取消场景两次“SHALL NOT 写房间日志”，含 unlimited 的 `discussion_ended`“同样”不写）、`:90`（链结束 system 例外仍写“取消/异常…除外”） | Q1/Q3/Q4 联动齐全；Q2 只改了决策层与 MODIFIED 正文，**delta 的同一 Requirement 场景与 ADDED 例外清单仍反**：按 `:54-55` 写测试会断言断线取消不写日志，与 `:5`、`design.md:108/:170`、Q2 裁决直接冲突。这是 r1 I10 点名要改的“delta 两处”之一未清，也是本轮唯一 medium。另有两个 low 残留（`describeRoundEnd(stopped)` 文案未定义；r1 要求的“裁决×落点”矩阵未提供，仅 `User Rulings` 摘要）。 |
| I11 | ✅ | `tasks.md:41`（`room_state`：`room.discussion_mode` + `discussion_round` + `discussion_reason`，明写不新增 `discussion_active`）、`:28`（安全阀四路拆开）；`design.md:50`（不新增 `discussion_active`）、`:152`（字段宿主） | 三处旧问题全部修正：删除 `discussion_active`、`discussion_mode` 归 `room` 对象、字段清单与 design 一致。备注：`tasks.md:32` 仍重复一次 `round_limit` 路径（与 `:28` 重叠），nit。 |
| I12 | ✅ | `design.md:95-97`（表 row 4 `round_limit` / row 6 `max_turns` 仅“轮末恰尽”）、`:138`（回合数 ≥ 成员数、`@` 接力可达 `成员数+extra+admin_extra`；截断→`round_limit`、轮末恰尽→`max_turns`；文档/测试不得混写）；`specs/multi-agent-collaboration/spec.md:128-133`（独立 `max_turns` 场景：600 额度、3 人无接力、第 2 轮恰尽）、`:135-140`（截断→`round_limit`）；`tasks.md:28` | 算术与 reason 归属已按 r1 修正，delta 有独立 `max_turns` 场景，tasks 已拆分。残留 low：`design.md:138` 未保留 r1 要求的“3 人房无接力时与 200 轮打平（此时按优先级 5 报 `max_rounds`）”这句，“通常先到”在该 tie 场景下不精确；`proposal.md:74` 仍写旧口径“每轮 = 成员数回合”，见新发现 N1。两项均不构成测试会写错的 normative 冲突。 |

## L1–L18 处置摘要

| # | 处置 | 证据 / 理由 |
|---|---|---|
| L1 | 已修 | `design.md:14` 改 `:371-384`；代码 `orchestrator.py:371-384`（判定/reset/release）确无 await，`:385` 才是 `await _flush_status_emits`。 |
| L2 | 已修 | `design.md:126` 为 `async RoomOrchestrator.request_stop(room_id) -> bool`。 |
| L3 | 已修 | `design.md:108` 理由改“房间/成员已不存在，写日志无意义”。 |
| L4 | 已修 | `design.md:151` 签名为 `shouldApplyChainEvent(currentChainId, data)`。 |
| L5 | 已修 | `design.md:159` 明确 `openDialog` option schema 增 `disabled`；`group.js:604-625` 确认 select 目前无 `disabled`，需按设计扩展；新建两步已如实写明。 |
| L6 | 已修 | `design.md:187` ⑪ 点名“可挂起 emit sink（`on_event`/review 注入，照 `test_orchestrator.py:475-499`）”；`tasks.md:37` 同步登记；该接缝在 `tests/agent/team/test_orchestrator.py:467-501` 已验证。 |
| L7 | 已修 | `specs/web-ui/spec.md:45` 改 390px（与 `design.md:160`、`tasks.md:48`、既有 `openspec/specs/web-ui/spec.md:1697-1704` 的 390px 场景口径一致）。 |
| L8 | 已修 | `design.md:87` 写 `_run_slot(chain, state, persona_id)`；`tasks.md:55` 同步。 |
| L9 | 已修 | `design.md:145` 钉死 `members` 为 persona_id 列表与 `limits` 三键。 |
| L10 | 已修 | `design.md:106` 钉死 `status_seq` = 与最后一次 `round_ended` 相同的 reset 结果。 |
| L11 | 已修 | `design.md:177` single 下 `RoundResult` 新字段保持默认并测试锁定。 |
| L12 | 已修 | `design.md:104` 保持“review 在 `round_ended` 前”，与 `orchestrator.py:387-398` 现状一致。 |
| L13 | 已修 | `design.md:187` ⑮ 与 `tasks.md:37` 补“链中 `delete_room` → 收尾 `completed` 且不复活日志”；`web/team.py:691-710` 确认 `delete_room` 不取消链。 |
| L14 | 已修 | `specs/configuration/spec.md:5` 改“启动期解析；编排器 workspace 首次懒构造时注入并缓存”；`design.md:137` 同步；`web/team.py:201-212`、`:304-313` 与实现一致。 |
| L15 | 已修（留 low 残留） | `design.md:129` 与 `:87` c 明确“每个 slot 前后检查”；`tasks.md` 未单列但 design 覆盖。残留：停止落在轮间 await 时，下一轮仍会先 append/emit “讨论继续（第 k+1 轮）”再被 `_drive` 顶截住（0 回合即结束），只多一条噪声 system，见新发现 N12。 |
| L16 | 已修（留 low 精度项） | `design.md:65` 增 `terminal_sent` 字段（语义=“本轮的终态事件已发出”）、`:169` 用作 teardown 守卫、`:171` 幂等；r1 要求的“已发终态的轮不再补发 `round_ended`”已成立。置位时机未明写，见新发现 N5（low，可进 deferred）。 |
| L17 | 已修 | `specs/multi-agent-collaboration/spec.md:148` 增“越界上界 ≤ 一个 `turn_timeout`，SHALL NOT 当硬上限验收”。 |
| L18 | 已修 | `design.md:146` 明确 `system_entry` 仅链级语义，成员失败仍走 `member_failed` 合成，两条路径不重复。 |

## 新发现（deferred / low-nit）

| # | 严重度 | 位置 | 问题 | 处置 |
|---|---|---|---|---|
| N1 | low | `proposal.md:74` | RIR 仍写“每轮 = 成员数回合，通常 turns 档先触发”，与 `design.md:138` 修正后的“≥ 成员数、可被 `@` 接力放大”相反；`design.md:138` 又说“文档/测试 SHALL NOT 把两者混写”。 | 顺手把 proposal 该句改成与 v4 一致（下一批或收尾前）。 |
| N2 | low | `design.md:152` | “由 `discussion_round/2` 与结束原因更新”疑为笔误；且未写链结束/释放时 `discussion_round` 归 0。若宿主字典保留最后轮序号，`design.md:155` 的恢复规则会把已结束链显示成“讨论中（第 k 轮）”。 | 改为“进入轮时更新 round；链释放时置 0、写 reason；无链时 round=0”，或让 `discussion_snapshot` 直接由 `_rounds` 推导 round。 |
| N3 | low | `design.md:62` | `pending_mentions` 条目括号未闭合（`（...不跨链；`）。 | 补 `）`。 |
| N4 | low | `design.md:107` | 引用 `_decide_chain_end`，全文仅此一处、无定义；实际是 `design.md:89-102` 的决策表。 | 改为“不执行链级判定（Decision 3 表）”。 |
| N5 | low | `design.md:65`、`:169`、`:171` | `terminal_sent` 只定义语义与读取，未写“发 `round_ended` 前/后置位”。若在 await 之后置位，取消落在 `await round_ended` 窗口内仍会由 teardown 重发同轮终态（front-end 同 `status_seq` 会应用，覆盖文案）。 | 钉死“发 `round_ended` 前置位”（发前更稳），或明确该窗口允许重复。 |
| N6 | low | `design.md:155`；`specs/web-ui/spec.md:45` | 前端恢复规则未用 `room.discussion_mode` 门控，而 single 也共用 `_ChainState` 外壳；若 `discussion_round` 对 single 填 1，重连会显示“讨论中（第 1 轮）”，违反 single“既有状态文案不变”。 | 明确 single 的 `discussion_round` 恒 0（规范句已列 `room.discussion_mode`，实现按它门控即可）。 |
| N7 | low | `specs/multi-agent-collaboration/spec.md:90` | “用户请求停止讨论时 SHALL 发布 `discussion_stop_requested`”未限定“对进行中的 unlimited 链”，与 `design.md:127` 的无活动链/`closing`/single 均返回 False 且不发事件存在张力。 | 加“对进行中的 `unlimited` 链首次请求”。 |
| N8 | low | `design.md:108` | `mode_changed` 文案“讨论模式已切换为单轮”在该原因由 `reply_mode` 改为 `admin` 触发时不准。 | 文案改“讨论已结束（模式已变更）”或按子原因分文案。 |
| N9 | low | `tasks.md:32` | `round_limit` 路径与 `tasks.md:28` 重复登记（`extra_turns=0` 截断），易让测试作者重复实现。 | 删除其一或合并。 |
| N10 | low | `design.md:154`；`specs/web-ui/spec.md:45`；`group.js:418-431` | `round_ended(stopped)` 的文案映射未定义；现状会短暂显示“本轮结束”再到 `discussion_ended(stopped)` 的“讨论已停止”。 | 补 `describeRoundEnd(stopped)` 为“讨论已停止”或显式抑制该瞬态。 |
| N11 | deferred（low） | `design.md:69`、`:169`；`orchestrator.py:408-426` | 终局收尾 await 窗口内取消：链已在同步区 `_release_round`，except/finally 身份判断失败 ⇒ 本轮 `round_ended`/`discussion_ended` 不发；客户端只能靠 `room_state` 的 `discussion_reason` 恢复。与既有单轮同形窗口一致，非本次引入。 | deferred；下一批决定是否补“已释放链的终态保底”。 |
| N12 | deferred（low） | `design.md:85` a–`:86`、`:87` c、`:129` | 停止请求落在轮间 await 时，下一轮仍先 append/emit“讨论继续（第 k+1 轮）”再被 `_drive` 顶的 stop 检查截住（0 回合即结束），日志多一条误导性的“继续”。 | deferred；把 `stop_requested` 检查前置到 4a 之前即可（不影响正确性）。 |
| N13 | low | `specs/multi-agent-collaboration/spec.md:90` | ADDED 正文全称句“每轮结束 SHALL 发布 `round_ended`，携带 `chain_id`、`round_index` 与 `chain_continues`”未限定“链内”，与同文件 `:176` 空成员退化场景“SHALL NOT 携带这三键”在字面上冲突（场景已例外，但正文仍是全称）。 | 把全称句改为“链内每轮结束…”，或加“空成员退化路径除外”。 |

## 覆盖性结论

- **修复完整度**：I1–I9、I11–I12 的修法均在现有代码结构上可落地，且已写进算法/契约/测试策略——同步区（`design.md:67,82`）、`current` 不变量（`:61`）、release 身份=链（`:69,71`）、k>1 空 opening（`:85`）、`pending_user_seqs` 两端（`:74-75`）、双恢复字段宿主（`:152`）、四路安全阀与 reason 归属（`:95-97,138`）都有明确落点，没有“design 说了但代码无法表达”的点。
- **是否引入新的 medium+**：无。新发现最高为 low（N1–N10 为 nit/精度项，N11–N12 为 deferred low）；**唯一 medium 是 I10 的未清残余**，不是新问题——“Q2 断线写 system”在 `design.md:170` 与 `specs/multi-agent-collaboration/spec.md:5` 已改对，但同一 delta 的场景 `:54-55` 与 ADDED 例外 `:90` 未同步。按 r1 的 I10 原文，这正是“接受 Q2 就必须改的两条 delta”之一。
- **L 表**：18/18 均已“已修”或“可接受（留 low 残留）”。L15/L16 的残留（轮间停止的噪声 system、`terminal_sent` 置位点）不阻塞；其余 L 项逐条有证据。
- **Q1–Q4**：Q1（`design.md:76/102`；delta `:90,157-163`）、Q3（`design.md:127,131,157`；delta `:5,46`；web-ui `:45,82-87`）、Q4（`design.md:139`；delta `:142-148`；`design.md:187` ⑦；`tasks.md:28`）联动一致；Q2 只在 delta 两处失配，见上。
- **结构校验**：`openspec validate --all --strict` 29/29 通过；该结果不覆盖 I10 的语义矛盾（strict validate 不做跨句一致性）。

## 闭环出口

**CHANGES_REQUESTED**。剩余 medium+ 清单（1 条，均属 I10）：

1. `specs/multi-agent-collaboration/spec.md:54-55`：取消场景两次“SHALL NOT 写房间日志”，其中 `:55` 明确覆盖 `unlimited` 的 `discussion_ended`，与同文件 `:5`、`design.md:108/:170` 和 Q2 裁决冲突。
   最小补丁：改为“`single` 取消 SHALL NOT 写房间日志；`unlimited` 链因断线取消 SHALL 写 `system`「讨论因页面断开而中止」，意外异常 `error` 不写；两条通知 SHALL NOT 产生 `RoundResult`、SHALL NOT 被解释为新增轮次出口”。
2. `specs/multi-agent-collaboration/spec.md:90`：链结束 system 的例子仍写“（取消/异常与‘房间已无成员’退化路径除外）”，把断线取消也排除了。
   最小补丁：例外改为“（`error`、`single` 取消与‘房间已无成员’退化路径除外；断线取消按「房间级互斥与轮次终止」写 `system`）”。

补完这两处即构成**批次 II**（非空 medium+ 批次，仅此 1 条）；批次 II 修完后按有界批次模型再跑一轮只做修复验证的复核（批次 II 收口），届时若 I10 转 ✅ 且无新 medium+ 才给 PASS。若同时顺手处理 N1–N10 的 low 项更佳（非 PASS 前置条件）。本轮不给 PASS。
