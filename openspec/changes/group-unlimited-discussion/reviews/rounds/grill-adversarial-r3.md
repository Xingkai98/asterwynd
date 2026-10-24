# 设计对抗审阅 r3（修复验证）：group-unlimited-discussion

## 基线

- 修复提交（本轮验证对象）：`086bc57c`（`group-unlimited-discussion：对抗 r2 修正（I10 delta 两处 + N1–N10 low）`）；分支 `group-unlimited-discussion/2026-10-24`。报告落定后主 agent 以 `fe83ac82`（`设计对抗闭环收口 r3 PASS（证据归档 + N13/N14/N15 收口）`）收口；增量复核见文末，本文对 `086bc57c` 的全部判定在 `fe83ac82` 上仍成立（I10 两处未再改动）。
- 差分范围（`git show --stat 086bc57c`）：6 文件，**全部为 change 文档**（`design.md`、`proposal.md`、`tasks.md`、`specs/multi-agent-collaboration/spec.md`、`specs/web-ui/spec.md`，外加提交带入的 r2 报告）；**未改实现代码与测试**，因此本轮验证对象是「r2 的两处 medium 是否清、修复是否引入新 medium+」，不涉及代码回归。
- 上一轮基线：r2 = CHANGES_REQUESTED，剩余 medium 仅 1 条（I10 的 delta 两处，r2 `:83-88` 给出最小补丁）+ low N1–N13。
- 方法：逐条对照 r2 `:83-88` 的最小补丁与 HEAD 文档；对 r1 的 I1–I12 原修复做锚点回归抽查（本轮差分未触及其落点）；对修复涉及的代码前提做只读核对：`agent/team/orchestrator.py:347-426`（既有单轮收尾/teardown/finally 形态）、`web/server.py:741-750`（房间 WS 断线 cancel 轮次 task）。
- 结构校验复跑：`npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` → **29 passed, 0 failed (29 items)**。该工具不做跨句语义一致性检查，I10 结论来自逐字对照。
- 工作树：审阅 `086bc57c` 时除本报告外，仅 r2 报告有一处未提交的文字微调（`覆盖性结论` 补 N13、`闭环出口` 措辞），不涉及本轮验证对象；收口提交 `fe83ac82` 已把三份逐轮报告归档到 `reviews/rounds/` 并在 `reviews/grill-adversarial.md` 保留索引。本次回填只改本报告，未改动其它文件。

## Verdict

**PASS**

I10-a、I10-b 两处 medium 均已按 r2 的最小补丁清除，且与 `design.md` Decision 8 / User Rulings Q2 / MODIFIED 正文逐字一致；N1–N10 全部落地；本轮改动未破坏 r1 I1–I12 的任何原修复；未引入新的 medium+（新增 3 条 low/nit：N14–N16，按批次冻结规则登记不阻塞；其中 N14/N15 与 r2 遗留 N13 已在收口提交 `fe83ac82` 落地并经增量复核）。

## 逐条验证

| # | 状态 | 证据（文件:行号） | 备注 |
|---|---|---|---|
| I10-a | ✅ | `specs/multi-agent-collaboration/spec.md:55`：改为「`single` 取消 SHALL NOT 写房间日志；`unlimited` 链因断线取消 SHALL 在房间日志写 `system`「讨论因页面断开而中止」并 SHALL 尽力发布 `discussion_ended`（`reason = "cancelled"`）；意外异常（`error`）SHALL NOT 写房间日志」；`:54`：「该通知 SHALL NOT 产生 `RoundResult`、SHALL NOT 被解释为新增的轮次出口」 | r2 要求的四项要素齐全：写日志对象（`unlimited` 链断线取消）、原因文案（与 `design.md:108/:171/:214`、`spec.md:5/:90` 同字）、`error` 排除、不产生 `RoundResult`/不作为新出口。`:54` 的「该通知」字面仅指 `round_ended`，「两条通知」的完整口径由 `:5` 承载（见 N16，nit，不构成语义冲突）。 |
| I10-b | ✅ | `specs/multi-agent-collaboration/spec.md:90`：链结束 `system` 例外改为「（`error`、`single` 取消与"房间已无成员"退化路径除外；`unlimited` 链因断线取消 SHALL 写 `system`「讨论因页面断开而中止」，见「房间级互斥与轮次终止」）」 | 断线取消已从例外清单移除并显式反向声明；与 `:5`（MODIFIED 正文）、`design.md:108`（文案表）、`design.md:171`（Decision 8）、`design.md:214`（Q2）、`reviews/grill-design.md:89`（Q2 用户答复）一致，无「取消/异常除外」旧句残留（全目录 grep 仅命中历史评审报告）。 |
| 三处逐字一致 | ✅ | 写日志对象 = `unlimited` 链因断线取消（`design.md:171`、`spec.md:5`、`:55`、`:90`）；原因文案「讨论因页面断开而中止」6 处同字（`design.md:108`、`:171`、`:214`；`spec.md:5`、`:55`、`:90`）；「不产生 `RoundResult` / 不被解释为新增轮次出口」——`spec.md:5` 明写两个通知（`round_ended`/`discussion_ended`）均不构成新出口、不产生 `RoundResult`（另见 `design.md:168`「取消/异常优先于一切快照条件」、`:170`「不产生 `RoundResult`」）；`single` 取消不写、`error` 不写三处一致（`design.md:171`、`spec.md:55`、`:90`） | 与 Q2 裁决（`design.md:214`、`reviews/grill-design.md:89`）逐项一致：只对断线取消写日志，`error` 与 `single` 取消不写，且都不得被读成新增出口。 |
| N1 | ✅ | `proposal.md:74`：「每轮回合数 ≥ 成员数、且可被成员互相 `@` 接力放大到「成员数 + extra_turns + admin_extra_turns」；`max_turns` 在绑定意义通常先到，但上报 reason 时多被 `round_limit` 吸收，见 design Decision 6」 | 与 `design.md:138` 修正后的算术与 reason 归属一致；旧口径「每轮 = 成员数回合，通常 turns 档先触发」已删。 |
| N2 | ✅ | `design.md:152`：宿主改为 `self._discussion_state: dict[room_id, {"round": int, "reason": str|None}]`——「进入第 k 轮时更新 `round=k`，链释放时置 `round=0` 并写 `reason`；读取方法 `discussion_snapshot(room_id)`」；`:152` 同时写明 `discussion_round`「无链与 `single` 恒 0」 | `discussion_round/2` 笔误已删；链释放归 0 已明写，`:155` 的恢复规则（`round_active && unlimited && round > 0` 才显示「讨论中（第 k 轮）」，否则按 `discussion_reason`）不再会把已结束链显示成进行中。 |
| N3 | ✅ | `design.md:62`：「…链结束随链丢弃、不跨链）」 | 括号已闭合。 |
| N4 | ✅ | `design.md:107`：「不执行链级结束判定（Decision 3 表）」；`design.md:89-102` 即该决策表 | `_decide_chain_end` 在 `design.md` 中已 0 命中（仅历史评审报告仍引用）。 |
| N5 | ✅ | `design.md:65`：`terminal_sent: bool`「本轮的终态事件已发出；**在发出本轮 `round_ended` 之前置位**」（并由 `:170` teardown 守卫、`:172` 幂等引用） | 置位点已钉死，与 r2 建议的「发前置位」一致。残留固有窗口（置位后、发送完成前取消 ⇒ 客户端收不到该终态）由 `design.md:172` 的幂等语义与 `room_state.discussion_reason` 恢复兜底，r2 已接受该取舍，非本轮新问题。 |
| N6 | ✅ | `design.md:152`（`single` 恒 0）+ `design.md:155`（`room_state` 分支以 `round_active && room.discussion_mode === "unlimited" && discussion_round > 0` 门控，并注明「`single` 不做该恢复，`discussion_round` 恒 0」） | 门控与 `specs/web-ui/spec.md:45` 的恢复句（依据 `room.discussion_mode`/`discussion_round`/`discussion_reason`）一致。 |
| N7 | ✅ | `specs/multi-agent-collaboration/spec.md:90`：「对进行中的 `unlimited` 链首次请求停止时 SHALL 发布 `discussion_stop_requested`（无活动链、链已 `closing` 或 `single` 房间不发布）」 | 与 `design.md:127`（三类返回 False、幂等 no-op）、`:128`（首次才发）一致。 |
| N8 | ✅ | `design.md:108`：`mode_changed`「讨论已结束（模式已变更）」；`specs/multi-agent-collaboration/spec.md:170` 同步；`specs/web-ui/spec.md:45` 的 `mode_changed` UI 文案同步 | 三处同字；旧文案「讨论模式已切换为单轮」在 change 文档中 0 命中（仅历史评审报告引用）。`mode_changed` 与 `completed` 的「讨论已结束」已可区分。 |
| N9 | ✅ | `tasks.md:32` 已删重复的「`round_limit` 路径（`extra_turns=0` 注入）」；`round_limit` 仍由 `tasks.md:28`（安全阀四路含 `round_limit`）、`design.md:95`（优先级 4）、`design.md:188` ⑦ 覆盖 | 无覆盖缺口。 |
| N10 | ✅ | `design.md:156`：「`round_ended(termination="stopped")` 的文案 SHALL 为「讨论已停止」（不得显示「本轮结束」；随后 `discussion_ended(stopped)` 覆盖为同一文案）」；`specs/web-ui/spec.md:45`：「`unlimited` 下 `round_ended(termination = "stopped")` SHALL 显示「讨论已停止」（不得显示「本轮结束」）」 | 两处一致；与 `:157`（`chain_continues=true` 时不显示「本轮结束」）不冲突。 |

### r1 I1–I12 回归抽查（本轮差分未破坏原修复）

- 差分只落在 N 项落点（`design.md:62`、`:65`、`:85`、`:107`、`:108`、`:152`、`:155-156`、`proposal.md:74`、`specs/multi-agent-collaboration/spec.md:54-55`、`:90`、`:170`、`specs/web-ui/spec.md:45`、`tasks.md:32`），未触及 I1–I9/I11–I12 的契约段。
- 锚点抽查全在位：I1 = `design.md:61`（`current` 恒非 None）、`:67`（认领+第 1 轮骨架同一同步区）、`:82`（查—建—挂 current 无 await）；I2 = `:107`（single 分支，仅把 `_decide_chain_end` 改写成「Decision 3 表」，语义不变）；I3 = `:58`、`:88`（仅 completed/limit/all_failed 才 `rounds.append`）、`:109`（`rounds=2`、`rounds_started=3`）；I4 = `:83`、`:86`、`:103`、`:106`、`:128`、`:145-148`；I5 = `:63`、`:74-75`、`:87` c；I6 = `:61`、`:69`、`:71`、`:169-172`；I7 = `:85`（`k>1 SHALL 传空串` 保留）；I8 = `:152`、`:155`；I9 = `:81`、`:89-91`、`:150`、`specs/multi-agent-collaboration/spec.md:90`（取消/异常不参与排序）、`:176`（空成员退化不携带三键）；I11 = `tasks.md:41`、`:28`、`design.md:50`、`:152`；I12 = `design.md:95-97`、`:138`、`specs/multi-agent-collaboration/spec.md:128-140`、`tasks.md:28`。
- Q1（`:76`、`:102`；delta `:90`、`:157-163`）、Q3（`:127`、`:131`、`:150`；delta `:5`、`:46`；`specs/web-ui/spec.md:45`、`:82-87`）、Q4（`:139`、`:188` ⑦；delta `:142-148`）联动未被本轮改动影响。
- 结论：无 r2 已修项被破坏。

## 新发现（若有）

| # | 严重度 | 位置 | 问题 | 处置 |
|---|---|---|---|---|
| N14 | low | `design.md:85`（N12 分支）；关联 `design.md:88`、`:130`、`:59` | 本轮新增的 N12 前置检查写成「若 `stop_requested` 已置位则不 append「讨论继续」、直接进入收尾」，未定义轮次记账：① 若按字面跳入 `design.md:88` 的 4d 同步收尾区，`state` 仍是**上一轮**（已 `closed`、已 `terminal_sent`），会二次执行 `chain.turns += state.turns`（`discussion_ended.turns` 双计，违反 `design.md:59` 的「链内已完成成员回合数」定义）并对同一 `round_index` 再发一次 `round_ended`；② 若实现为「不建新轮、只走链结束」，则与 `design.md:130`「停止后…发 `round_ended(stopped)`」的字面义务不一致。 | 不阻塞（无 delta 规范冲突：`specs/multi-agent-collaboration/spec.md:39-46` 的停止场景以「当前成员回合运行结束」为 WHEN，不覆盖轮间窗口；且 `design.md:61` 的 `current.closed` 不变量足以让实现者识别该窗口）。最小补丁：把 `design.md:85` 该句改为「若 `stop_requested` 已置位则不 append「讨论继续」、不再建新轮，直接置 `chain.closing`、append「讨论已由用户停止」`system`、`_reset_room_statuses` + `_release_round` 并结束链（不补发 `round_ended`；`rounds`/`rounds_started`/`turns` 保持上一轮值）」；并建议在 `tasks.md:34`（收尾同步区竞态的停止路径）注明该窗口的期望值（`round_ended` 不再补发、`turns` 不重计）。**已落地**：收口提交 `fe83ac82` 按本补丁改写 `design.md:85`，复核无新问题（残留 nit 见「增量复核」）。 |
| N15 | nit | `design.md:221`；`tasks.md:13` | 轮次状态行仍写「r2 修复验证待跑」，而 r2 已给出 CHANGES_REQUESTED、本轮为 r3。 | 由 `tasks.md:16` 的 0.5（回填 `## Pre-Implementation Review`）在 PASS 后统一写入 r3 出口，不需单独开修。**已落地**：收口提交 `fe83ac82` 回填 `design.md:221`、`tasks.md:13`/`:16`（r1→r2→r3 + PASS）。 |
| N16 | nit | `specs/multi-agent-collaboration/spec.md:5`、`:54` | `:5` 的「并 SHALL 在房间日志写一条 `system`…」主句在语法上同时覆盖 `cancelled` / `error`，只靠尾括号「（链因断线取消时…）」限定；`:54` 的「该通知」字面只指 `round_ended`，`discussion_ended` 的「不产生 `RoundResult` / 不新增出口」只由 `:5` 承载。语义已被 `:55`、`:90`、`design.md:171` 钉死，不会有测试写错。 | 可选文风收紧：`:5` 改「链因断线取消时 SHALL 另写…」；`:54` 改「上述两条通知均 SHALL NOT 产生 `RoundResult`…」。 |

- r2 遗留 low 状态：N11（收尾 await 窗口内取消导致本轮终态不发）仍为 deferred low（r2 已登记成因，与既有单轮同形窗口一致）；N13（ADDED 正文「每轮结束 SHALL 发布 `round_ended`，携带 `chain_id`…」未限定「链内」，与 `specs/multi-agent-collaboration/spec.md:176` 的空成员退化场景在字面上张力）在本轮报告落定后已由收口提交 `fe83ac82` 按建议改为「链内每轮结束 SHALL 发布 `round_ended`（空成员退化路径除外）」（`specs/multi-agent-collaboration/spec.md:90`），复核后张力解除。

### 增量复核：收口提交 `fe83ac82`

| 项 | 状态 | 证据 | 备注 |
|---|---|---|---|
| N14 落地 | ✅ | `design.md:85` 改为「若 `stop_requested` 已置位则**不建新轮**——直接置 `chain.closing`、append「讨论已由用户停止」`system`、`_reset_room_statuses` + `_release_round` 并结束链（不补发 `round_ended`，`rounds`/`rounds_started`/`turns` 保持上一轮值；grill N12/N14）」 | 与本报告最小补丁一致；`design.md:88` 4d 的 `chain.turns += state.turns` 不再会被二次执行，`turns` 双计与同 `round_index` 重复 `round_ended` 的歧义解除。残留 nit：`design.md:130`「停止后…发 `round_ended(stopped)`」未限定「有进行中的轮次」，与 `:85` 轮间窗口不补发的分支在字面上有张力；建议实现前补一句限定（不构成 medium）。 |
| N13 落地 | ✅ | `specs/multi-agent-collaboration/spec.md:90`：「链内每轮结束 SHALL 发布 `round_ended`（空成员退化路径除外）」 | 与 `:176` 空成员退化场景不再字面冲突；`:52` 取消 teardown 的「尽力发布 `round_ended(cancelled)`」不受影响（异常 teardown，不属「每轮结束」）。 |
| N15 落地 | ✅ | `design.md:221`（r1→r2→r3 + PASS）、`tasks.md:13`（0.3 勾选 + 轮次链）、`tasks.md:16`（0.5 勾选） | 状态行与轮次史一致。 |
| 证据归档 | ✅ | `reviews/rounds/grill-adversarial-r{1,2,3}.md` 三份逐轮报告 + `reviews/grill-adversarial.md` 改为索引 | `reviews/grill-adversarial.md` 仍存在，满足 `scripts/check_openspec_artifacts.py:1073-1076` 对归档点「`reviews/grill-adversarial.md` 存在」的路径要求；逐轮原文保留在 `rounds/`。 |
| 结构校验 | ✅ | 在 `fe83ac82` 上复跑 `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` → **29 passed, 0 failed** | 与 `086bc57c` 上结果一致；N13 的 delta 改写未破坏结构。 |
| I10 未回退 | ✅ | `specs/multi-agent-collaboration/spec.md:5`、`:54-55`、`:90` 的 I10 修复正文在 `fe83ac82` 中未再改动（`git show --stat fe83ac82` 该文件仅 1 行变更 = N13 句） | I10-a/I10-b 判定在最终 HEAD 上仍成立。 |

## 覆盖性结论

- **阻塞项**：I10-a、I10-b 两处 medium 全清，写日志对象、原因文案、排除项（`single` 取消 / `error`）、「不构成新增轮次出口 / 不产生 `RoundResult`」四要素在 `design.md`（`:108`、`:168-171`、`:214`）、MODIFIED 正文（`spec.md:5`）、场景（`:54-55`）、ADDED 例外清单（`:90`）之间一致，无旧口径残留。r2 的唯一 medium 关闭。
- **修复是否引入新 medium+**：无。本轮差分为纯文档修补（6 文件、无代码/测试），新发现最高为 low（N14），按批次冻结规则进 r3 登记表；N15/N16 为 nit。
- **回归**：r1 I1–I12 的锚点全部在位，Q1–Q4 联动未被破坏；差分未触碰实现代码与测试，故无代码回归面。
- **工具校验**：`openspec validate --all --strict` 在 `086bc57c` 与收口提交 `fe83ac82` 上均为 29/29 通过（只证明结构合法，不覆盖本轮语义判定）。
- **收口状态**：`fe83ac82` 已落地 N13/N14/N15、归档三份逐轮报告并保留 `reviews/grill-adversarial.md` 索引；I10 修复正文未再改动。剩余登记项仅 N11（deferred low）与 N16（nit）。
- **实现前提**：设计可进入实现（building 在独立 worktree、分支 `group-unlimited-discussion/2026-10-24`）；`tasks.md:16` 的 0.5 已在 `fe83ac82` 完成，`## Pre-Implementation Review` 已写入 r1→r2→r3 与本 PASS。

## 闭环出口

PASS（I10-a ✅、I10-b ✅；无新 medium+；`086bc57c` 的修复在收口提交 `fe83ac82` 上保持且 29/29 校验通过；剩余登记项 N11 = deferred low、N16 = nit，N13/N14/N15 已在 `fe83ac82` 落地；批次 I/II 收口，累计 2 个已收口轮 ≤ 20，允许进入实现）。
