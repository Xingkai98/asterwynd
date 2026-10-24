# 实现后独立审阅 r1：group-unlimited-discussion

## 基线与范围

- base `604b56cc`（实现前 master）→ head `56274e13`（`group-unlimited-discussion/2026-10-24`）；改动 **38 个文件，+4846 / −177**。其中实现与测试 17 个文件（+3560 / −166），立项/评审/规格/文档 21 个文件。
- 实现面：`agent/team/orchestrator.py`（+1001，讨论链重构）、`agent/config.py`、`agent/team/models.py`、`web/team.py`、`web/server.py`、`web/static/{group,group_status}.js`、`web/static/{index.html,style.css}`、`asterwynd.example.yaml`。
- 规格面：三份 delta vs `openspec/specs/{multi-agent-collaboration,web-ui,configuration}/spec.md`（逐 requirement 比对，归一化空白后正文完全一致，详见「Spec 对齐」）。
- 方法：逐条读 diff（含 base 对照）+ 逐条走查 design Decision 1–10 / User Rulings Q1–Q4 + 运行定向测试与三个门禁命令；**未复核设计本身**（`reviews/grill-adversarial.md` r3 = PASS 已定稿）。
- 声明：任务交接提到的「9 条已申报实现口径」在本仓内没有任何 artifact（`git log` 提交正文为空、`.handoff/` 只有别的 change 的评审文件）。因此本轮不做逐条「已申报」比对，只做**可观测行为 vs design/delta** 的比对；下面登记的疑似偏差（L2/L4/L5/L6/L8/L9）都判为 low/nit，未发现需要按 medium 处理的未申报偏差。

## Verdict

**PASS**（无 medium+；0 个批次 I 问题；low/nit 共 15 条已登记不修，均写明理由）。

理由摘要：讨论链的同步区算法、`current` 恒非 None、release 身份=chain、finally 兜底、single 零变化、链级 reason 优先级、未消费消息强制续轮、墙钟/停止的 slot 间检查、取消/异常 teardown、`chain_id` 守卫与 `room_state` 恢复、配置 fail-fast 与链启动快照，均与 design Decision 2/3/5/6/7/8/9 逐项一致并有针对性用例；三份当前规格与 delta 逐段一致；既有 orchestrator 用例未被削弱（唯一删除行是 import）。

## 逐任务验证

| task | 状态 | 证据 |
|---|---|---|
| 1.1 模型/存储 | ✅ 完成 | `agent/team/models.py:34,36,118,139,155`；用例 `tests/agent/team/test_team_store.py:191`（缺省/roundtrip/旧 JSON 缺字段/null）。 |
| 1.2 配置 | ✅ 完成 | `agent/config.py:297-299`（默认 200/600/6000）、`:1725-1739`（`_parse_timeout_seconds` ×2 + `_parse_positive_float`，显式拒 bool/0/负数/字符串）；用例 `tests/agent/test_config.py:1014`（4 条 + 12 条非法值参数化）。 |
| 1.3 编排器测试 | ✅ 完成 | `tests/agent/team/test_orchestrator.py:1034-1969`：连开 3 轮收敛/部分静默/续轮空 opening/提示词、single 整字典四键+零事件负向断言、停止（回合中 + 轮间窗口 + 幂等）、四路安全阀、all_failed、未消费消息强制续轮+cap 优先、模式变更、空成员退化、取消/异常 teardown、delete_room、可挂起 emit 两条竞态、snapshot/timeout 生命周期、review 每轮+抛异常、chain_id 单调/elapsed 精确值。 |
| 1.4 Web 测试 | ✅ 完成 | `tests/web_tests/test_group_chat_server.py:577-911`（快照适配、create/patch 三种非法组合、REST stop 幂等/404/403/跨 workspace 回落、`room_state` 三字段、WS `stop_discussion`、single 零 `discussion_*`、真实编排器事件顺序 `849-911`）；`tests/web_tests/test_group_chat_team.py:966-1138`（归一化、合并生效值校验（含拒绝后原值不变）、TEAM 配置注入、stop 回落）。 |
| 1.5 前端测试 | ✅ 完成 | `tests/web_tests/test_group_status_js.py:182-291`（四件套纯函数 + `chain_id` 守卫 + `stopped` 文案）；`tests/web_tests/test_group_status_browser.py:509-780`（stop 按钮可见/置灰/REST 降级恢复、`system_entry` 去重追加、旧链终态不覆盖、`room_state` 恢复、旧链守卫、设置下拉 disabled + 400 展示、390px 头部不溢出）。我实跑 6 passed。 |
| 2.1 模型 | ✅ 完成 | 同 1.1。 |
| 2.2 配置 | ✅ 完成 | 同 1.2；`asterwynd.example.yaml:119-128` 加 `team:` 三键示例。 |
| 2.3 编排器 | ✅ 完成 | `agent/team/orchestrator.py`：`_RoundState/_ChainState/_DiscussionLimits`（`367-448`）、认领+第 1 轮骨架同同步区（`607-628`，无 await）、`_run_discussion` 循环（`650-679`）、`_drive` slot 前后检查（`722-736`）、`_close_round`（`883-954`）、`_chain_end_reason` 优先级表（`956-992`）、`_begin_following_round`（`994-1044`）、`_finish_chain`（`1061-1077`）、`_abort_chain`+后台 teardown（`1083-1151`）、payload 四件（`1157-1202`）、`RoundResult` 扩展（`154-178`）、unlimited 提示词（`125-151`）；`finally` 兜底（`688-693`）。 |
| 2.4 TeamService | ✅ 完成 | `web/team.py:93`（`_normalize_discussion_mode`）、`:101`（合并生效值校验）、`:511`（`stop_discussion`，workspace 回落同发消息）、`:673-707`（create 先校验后落盘）、`:709-734`（update 先校验后写）。 |
| 2.5 Web 层 | ✅ 完成 | `web/server.py:133`（`discussion_snapshot` 适配）、`:619-622`/`:634-636`（create/patch 白名单）、`:694-713`（REST stop 200/404/403）、`:743-760`（`room_state` 带 `discussion_round/reason`，无 `discussion_active`）、`:796-805`（WS `stop_discussion`，失败不摘连接）。 |
| 2.6 前端 | ✅ 完成 | `web/static/group.js:208,355,368,383,415-445,515-535,556-598,912-967`；`index.html:191,239-240`（按钮 + cache-bust）；`style.css:2185,2276-2278`。 |
| 2.7 全量回归 | ⬜ 未做 | 事实一致：本轮只跑定向套件（见「验证命令」），全量由 Lead 在跑；未勾选正确。 |
| 3.1–3.3 当前规格同步 | ✅ 完成 | 三份 `openspec/specs/**` diff 与 delta 逐 requirement 正文一致（见「Spec 对齐」）；`workflow-events.jsonl` seq 3/4/5 三条 `current_spec_synced` 分别绑定三个文件。 |
| 3.4 文档同步 | ✅ 完成 | `docs/architecture.md:85,95,97`（Room 字段 + 讨论链段）、`CONTEXT.md:111-113`（讨论链词条）、`docs/interview-script/questions/Q08-multi-agent.md:80`（成本控制改口径）。 |
| 3.5 spec_synced 事件 | ✅ 完成 | `openspec/changes/group-unlimited-discussion/workflow-events.jsonl` seq 3/4/5。 |
| 3.6 building review | ⬜ 本轮产出 | 即本文件；`## 闭环出口` = PASS，Lead 可勾选。 |
| 4.1–4.5 收尾 | ⬜ 未做 | 事实一致：backlog 条目仍在（`docs/openspec-change-backlog.md:120-122`，4.1 移除）、未归档、manifest 未重建、未发起 PR；均属收尾动作。 |
| 4.6 关闭 issue | ⬜ `(post-merge)` | 已正确标注，归档点门禁可豁免。 |

## 批次 I：medium+ 问题（本轮必须全修）

**无。** 本轮未发现 medium+ 问题，不开启批次 I；下列 low/nit 登记不阻塞。

| # | 严重度 | 文件:行号 | 问题 | 证据/复现 | 必须改法 |
|---|---|---|---|---|---|
| — | — | — | （空） | — | — |

## 批次 L：low / nit 登记（不阻塞，须写理由）

| # | 严重度 | 文件:行号 | 问题 | 建议 | 不阻塞理由 |
|---|---|---|---|---|---|
| L1 | nit | `openspec/specs/multi-agent-collaboration/spec.md:1354-1355`；`openspec/specs/web-ui/spec.md:1765-1766` | 场景最后一个 bullet 后直接跟 `### Requirement:`（缺空行），是 delta 合并时删掉空行留下的排版痕迹 | 各补一个空行 | 纯排版；`openspec validate --strict` 29/29 通过，ATX 标题仍被正确解析，正文与 delta 完全一致 |
| L2 | low | `agent/team/orchestrator.py:695-720` | 空成员退化路径**不再抢占房间认领**（base 在退化路径也注册 `_rounds`）：同 tick 两条消息会各跑一次退化单轮、各发一条 `round_ended`，且该路径上的取消不再发 `round_ended(cancelled)`，`is_round_active` 在退化单轮期间为 false | 在 `_run_degenerate_round` 建一个占位链（或复用 `single` 链外壳但跳过链级事件），保持「同房间至多一个进行中讨论」 | 无成员房无成员状态/会话可竞争，不产生数据损坏；delta 的「空成员退化」场景未钉并发窗口 |
| L3 | low | `agent/team/orchestrator.py:492,1252-1257` | `_discussion_state` / `_chain_seq`（以及既有 `_status_seq`）没有房间删除清理钩子；删房后残留一条 dict 项，若房间 id 复用会显示旧 `discussion_reason` | `TeamService.delete_room` 里调 `orchestrator.forget_room(room_id)`（清 `_discussion_state/_chain_seq/_statuses/_status_seq`） | 每房间一条小 dict，进程生命周期内可忽略；房间 id 由 store 生成，实际不复用；`_status_seq` 残留是既有模式 |
| L4 | low | `agent/team/orchestrator.py:633-634` vs `design.md:74-75` | design 说首轮 append 后「回填 `state.start_seq` 与 `pending_user_seqs`」，实现只回填 `start_seq`，开场用户条目没有进 `pending_user_seqs` | 补一行 `chain.pending_user_seqs.append(entry.seq)`（首个 slot 构造切片时会自然消费掉），或把 design 该处改成已实现口径 | **行为等价**：只要有一个 slot 构造切片就覆盖它；「全部 slot 被跳过/会话创建失败」时链级 reason 由 `completed`/`all_failed` 优先，Q1 强制续轮不会生效——是口径差不是行为差 |
| L5 | low | `agent/team/orchestrator.py:904` + `1083-1107` | 取消/异常路径 `chain.turns` 只累计正常收尾的轮；被取消当前轮里已完成的成员回合不计入 `discussion_ended.turns`（测试断言 0） | `_abort_chain` 补 `chain.turns += chain.current.turns`，或在文档注明异常路径该字段是下界 | teardown 是尽力而为诊断载荷；design/grill 已接受同类 await 窗口（N11 deferred low）；不影响任何规格条目 |
| L6 | low | `design.md:179`；`web/static/group.js:734` | design 承诺「REST 在长链下会挂到链结束（文档与前端降级文案注明）」，实现里只有前端注释仍写「会等整轮跑完才返回」，`docs/architecture.md` 未提 REST 语义；WS 断开时在 unlimited 房走 REST 发消息会挂到整条链结束且无提示 | `docs/architecture.md` 讨论链段补一句 + 前端降级路径加一条可见提示（或 unlimited 房禁用 REST 发消息并提示用 WS） | 行为本身是已申报的既有语义，delta spec 未要求该文案；缺陷是设计承诺的文档/文案未落地 |
| L7 | low | `agent/team/orchestrator.py:1277-1287` + `131-136`（配合 `roomlog.py:131-132`） | Q1 强制续轮时，未消费用户消息落在新轮切片的「earlier（context only）」窗口，而 k>1 提示词固定说「There is no new user message this round」；成员可能把该消息当纯上下文忽略 | 给续轮标注「本轮是否存在未消费用户消息」，有则改用「There is a new user message you have not seen; respond to it.」 | 提示词文案是 design Decision 4 钉死的；这是设计口径的后果而非实现偏差（且窗口顺序保证该消息不会被 8 条 earlier 截掉），留给设计侧决定 |
| L8 | low | `agent/team/orchestrator.py:536-541` | `request_stop` 用**房间当前** `discussion_mode` 判定，而链是 `single` 快照：单轮进行中把房间改成 unlimited 后请求停止，会对这条单轮链发 `discussion_stop_requested`，但该链不认 stop、也不会有 `discussion_ended`（前端 `stopPending` 短暂置灰，随后被 `round_ended` 隐藏按钮与下一条链重置） | 改用 `chain.discussion_mode == DISCUSSION_MODE_UNLIMITED` 判定 | 窗口极窄、按钮通常在刷新前不可见、无卡死或状态残留 |
| L9 | nit | `web/team.py:720-724` | PATCH `discussion_mode: null` 被当作「不修改」（`fields.get(...) is not None`），而 `create_room` 把 `None` 归一为 `single`；同字段两条路径语义不一致 | update 侧区分「键存在且为 null」→ 400 `invalid_discussion_mode`（或按 single 处理）并补一条用例 | 前端永远发字符串；与既有 `reply_mode` 的 `is not None` 口径一致，无数据风险 |
| L10 | nit | `web/server.py:133-160`；`tests/web_tests/test_group_chat_server.py:577-604` | `_discussion_snapshot` 的 `getattr` 兜底 + 2 元组分支是死代码（同 change 内 `RoomOrchestrator.discussion_snapshot` 已落地，design 只钉 dict），docstring 还写「agent 层尚未落地时」；测试为死代码写了 3 条用例 | 删掉 tuple/缺 API 分支（保留异常兜底），docstring 改成兼容策略；相应精简用例 | 维护性/测试冗余，不影响行为；异常兜底本身仍有价值 |
| L11 | nit | `tests/agent/team/test_orchestrator.py:645-650`；`tests/web_tests/test_group_chat_team.py:1085-1087` | 测试直读私有字段 `_teardown_tasks` / `_discussion_max_rounds` | teardown 改轮询事件或公开 await helper；limits 用已覆盖的 `discussion_started.limits` payload 断言 | 只是重命名会误伤测试，当前不会假绿 |
| L12 | nit | `agent/team/orchestrator.py:89-90,106-116` | `REASON_CANCELLED` / `REASON_ERROR` 及 `CHAIN_END_SYSTEM_TEXTS[REASON_CANCELLED]` 实际是死代码（断线文案由 `_abort_chain` 直接写 `DISCONNECTED_ENTRY_TEXT`） | 删两项或让 abort 走该表 | 仅冗余，无行为影响 |
| L13 | nit | `docs/openspec-change-backlog.md:120-122` | 条目仍写「已立项 2026-10-24，**待实现**」，而实现已完成（4.1 会整条移除） | 若本轮不立即收尾，把措辞改成「实现完成，待审阅/收尾」 | 收尾任务 4.1 会移除该条目；不影响门禁 |
| L14 | low | `tests/agent/team/test_orchestrator.py`（缺一条） | design Decision 10 表格「配置」行最后一项「两次 orchestrator 构造不同 limits ⇒ 两条链各自快照」未覆盖，只有 `tests/web_tests/test_group_chat_team.py:1075-1087` 的注入断言 | 补一条：两个 orchestrator（不同 max_rounds）各自开链，断言 `discussion_started.limits` 互不影响 | `_DiscussionLimits` 是 frozen dataclass 且每链新建，快照由 `discussion_started.limits` 用例间接锁定，风险低 |
| L15 | nit | `agent/team/orchestrator.py:1498-1504`（`_emit`）/ 全链事件 | 所有链事件都经 `await self._emit(...)` 串行广播；生产路径上某个慢客户端会阻塞讨论链推进（既有设计，非本 change 引入，但链把影响放大到数百轮） | 后续 change 可考虑 `room_bus` 侧丢弃慢订阅者或加 per-send 超时 | 既有架构决策（事件 await 注入），本 change 未改变该不变量；不属本实现偏差 |

## 维度结论

- **正确性（PASS）**：逐项核对 design Decision 2/3：① 认领与第 1 轮骨架在同一无 await 同步区（`orchestrator.py:607-628`，`_rounds` 唯一写入点），`current` 由构造函数必填、续轮在 `_begin_following_round:1041` 先赋值再返；② 收尾同步区包含轮终止→system→`rounds` 记账→链判定（`:883-954`），仅 `completed/limit/all_failed` 计入 `rounds`（`:905-908`），`stopped` 不入（`rounds=2/rounds_started=3` 用例精确断言）；③ release 全部走 `_release_round(room_id, chain)` 身份比较（`:1429-1432`），`finally` 兜底（`:688-693`）；④ single 分支不写链级 system、不发 `discussion_*`、`round_ended` 四键不变（`:911-925`+`:1172-1178`，整字典断言）；⑤ reason 优先级与 design 表 1→11 完全一致（`:970-992`），取消/异常不参与排序；⑥ 未消费消息 `pending_user_seqs` 到达即同步写入（`:566`）、按切片尾 seq 消费（`:1277-1287`）、0 发言 0 失败且未消费 → 强制续轮并受 5–7 限制（`:991-992`，cap 优先用例）；⑦ 停止/墙钟在 `_drive` 每个 slot 前检查（`:722-736`），停止不打断在跑回合（GateRunner 用例）。**未发现正确性缺陷。**
- **Spec 对齐（PASS）**：三份 delta 的 6 个 requirement 正文与当前规格**逐段一致**（脚本按 `### Requirement` 切段、归一化空白后对比，全部 SAME；delta 多出的只是 `## ADDED Requirements` 分节标记）。逐条抽查事件 payload（`discussion_started` 6 键 / `system_entry` 4 键 / `discussion_stop_requested` 2 键 / `discussion_ended` 8 键 / `round_ended` +3 键）、`room_state` 口径（`discussion_round`/`discussion_reason`，无 `discussion_active`）、REST/WS 语义与错误码（`invalid_discussion_mode` / `discussion_mode_requires_everyone` / `unknown_room` / `workspace_not_allowed`）、390px 布局、安全阀解析（拒 bool/0/负/字符串）与注入快照，均与 delta 一致。唯一问题为 L1 排版。
- **测试覆盖（PASS）**：新增 34 个编排器用例（head 收集 84 − base 50）+ 33 个 web 用例（server 20 + team 13）+ 8 个前端纯函数用例 + 2 个浏览器用例 + 模型 5 + 配置 4（含 12 条非法值参数化），覆盖可挂起 emit 的首轮骨架窗口、收尾 await 窗口开新链、取消/异常 teardown、轮间停止、delete_room、未消费消息、四路安全阀；用例断言的是真实事件 payload / 房间日志 / 调用序列（无 `assert True` 类假保护，未发现 skip/xfail 掩盖）。关键竞态缺口仅 L14（limits 双实例快照）与「停止恰好落在新轮第一 slot 前」这一窄窗口（行为符合 design 4a，未单测）。既有 orchestrator 用例逐字节未动（唯一删除行是 import），`git diff` 确认只增不改。
- **安全性/健壮性（PASS）**：`discussion_mode` 三种非法组合在 create/update 都先校验后写（拒绝后原值不变，`web/team.py:709-734`）；stop 未知房间 404、未授权 workspace 403、跨 workspace 回落后按房间归属执行（与发消息同口径，`web/team.py:511-527`）；WS `stop_discussion` 失败不摘连接；删除房间不复活日志（`_append_room_system`/`_run_slot` post-run 双重守卫，`:814-817,1298-1302`）；后台 task 有强引用 + 自清理（`_teardown_tasks`/`_status_tasks`），`teardown` 有整体 2s 上限；`chain_id` 防迟交错。残留见 L2/L3/L8。
- **可维护性/冗余（PASS，含 nit）**：结构与 design 的同步区划分一一对应，注释带 decision/grill 编号，事件 payload 构造集中在 `1157-1235`；冗余为 L10/L12（死代码）、L11（私有字段测试）、L15（既有串行广播）。文案与 spec 逐字一致：`讨论已收敛（本轮全员静默）/讨论已由用户停止/讨论已中止（本轮无人发言，存在失败）/讨论因本轮达上限结束/讨论达安全上限结束/讨论已结束（模式已变更）/讨论因页面断开而中止`，前端 11 种 reason 文案与 delta 表逐字对应。
- **CI 完整性（PASS）**：`.github/witnessloop-tests.txt` 内容就是 `uv run --extra dev pytest -q`（白名单即全量），`ci.yml` 的 `validate` job 跑 `uv run pytest -q` 并在前一步 `playwright install --with-deps chromium` ⇒ 新增用例（含两个浏览器用例）默认被 CI 跑到，无需改这两个文件；`windows-platform` job 是既有平台敏感子集，不纳新浏览器用例属既有设计。全量门禁结果以 Lead 的 r1 全量 run 为准（本轮只跑定向）。
- **文档影响（PASS，含 low）**：`docs/architecture.md`/`CONTEXT.md`/Q08 已同步且与实现口径一致；`asterwynd.example.yaml` 有 `team:` 示例且与 `TeamConfig` 默认值一致；backlog 条目待 4.1 移除（L13）。唯一未落地的设计承诺是 L6（REST 长链的文档/文案注明）。

## 验证命令与结果

1) 定向 pytest（含讨论链全部新增用例；Lead 另行跑全量）：

```
uv run pytest tests/agent/team/test_orchestrator.py tests/web_tests/test_group_chat_server.py \
  tests/web_tests/test_group_chat_team.py tests/web_tests/test_group_status_js.py \
  tests/agent/test_config.py tests/agent/team/test_team_store.py -q
→ 335 passed in 32.42s
```

2) 浏览器用例（新增 2 条 + 既有 4 条，Playwright Chromium 实跑）：

```
uv run pytest tests/web_tests/test_group_status_browser.py -q
→ 6 passed, 21 warnings in 22.94s
```

3) 团队层回归（确认没有连带破坏 `tests/agent/team` 其余模块）：

```
uv run pytest tests/agent/team tests/web_tests/test_group_chat_server.py \
  tests/web_tests/test_group_chat_team.py -q
→ 325 passed in 32.20s
```

4) OpenSpec strict validate：

```
npx --yes @fission-ai/openspec@1.4.1 validate --all --strict
→ ✓ change/group-unlimited-discussion / ✓ spec/{multi-agent-collaboration,web-ui,configuration} …
Totals: 29 passed, 0 failed (29 items)   [exit 0]
```

5) 瘦项目规则 checker：

```
uv run python scripts/check_openspec_artifacts.py --base-ref origin/master --require-base
→ Project rule checks passed   [exit 0]
```

6) 规格一致性脚本（delta vs 当前规格，按 `### Requirement` 切段归一化比对）：

```
房间级互斥与轮次终止: SAME (2893 chars)
房间应答模式:         SAME（仅 delta 多 `## ADDED Requirements` 标记）
讨论链自动续轮与收敛: SAME (5144 chars)
人设与房间的管理入口: SAME（仅分节标记差异）
群聊讨论链状态与停止讨论控件: SAME (2510 chars)
群聊讨论链安全阀可配置: SAME (1206 chars)
```

## 闭环出口

PASS —— 无 medium+（批次 I 为空，本轮不开批）；15 条 low/nit 已登记且写明不阻塞理由；实现与 design Decision 1–10 / Q1–Q4 及三份 delta 逐项对齐，三份当前规格已同步且正文与 delta 一致；定向套件 335 + 浏览器 6 + 团队层 325 全绿，`openspec validate --strict` 29/29、瘦 checker exit 0。允许进入收尾（tasks 2.7 全量回归由 Lead 完成 → 3.6 勾选 → 4.1–4.5 归档/重建 manifest/PR）。
