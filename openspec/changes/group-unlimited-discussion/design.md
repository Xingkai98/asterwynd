# Design: 群聊 everyone 模式无限讨论链（讨论链 + 停止按钮 + 安全阀）

> 修订记录：v2（2026-10-24）按 `reviews/grill-design.md` 的 C1–C22 修正；四个用户裁决点（Q1–Q4）在 `## Open Questions (pending user ruling)` 登记，裁决后回填 `## User Rulings`。

## Context

当前群聊的轮次语义全部钉死在「一次用户消息 = 一轮」：

| 事实 | 证据 |
| --- | --- |
| 唯一开轮入口是用户消息 | `agent/team/orchestrator.py:315-341` `submit_user_message`；`_rounds` 空闲才开轮 |
| 一轮 = 走完 slot 序列即结束 | `:347-407` `_run_round`；`:428-434` `_drive` |
| `everyone` 无 `@` 时开局 slot = 全体成员各一次 | `:153-182` `opening_slots` |
| 房间互斥只覆盖单轮；且「`_drive` 返回 → 释放认领」是**无 await 同步区** | `:309-310`、`:369-385`（既有并发用例依赖此不变量） |
| 规格明确「用户再发言前不得自行开新一轮」 | `openspec/specs/multi-agent-collaboration/spec.md:1304,1311` |
| 首版刻意不允许成员自开轮次 | `openspec/changes/archive/2026-10-13-web-agent-group-chat/design.md:131`（参照实现允许、上限 3） |

本轮用户诉求：保留「单轮」形态，另加「无限轮」形态——成员之间自动连续多轮讨论，直到**某轮全员静默**自然收敛、或用户点**停止讨论**；安全阀参数可配置（默认 200 轮 / 600 回合 / 6000 秒，均为用户确认的 10 倍档）；仅 `everyone` 模式生效。

## Goals / Non-Goals

**Goals**

- 房间级 `discussion_mode`（`single` 默认 / `unlimited`），仅 `everyone` 合法；单轮模式行为与事件**逐字段不变**。
- 讨论链：`unlimited` 下一轮正常结束后自动续下一轮；每成员每轮各得一次机会、可 `[PASS]`；**0 条成员发言且无未消费用户消息 = 收敛**。
- 「停止讨论」：优雅停止（当前成员回合跑完后结束当前轮、不再续轮），幂等；REST + WS 双通道，workspace 回退口径与发消息一致。
- 安全阀：轮数 / 成员回合 / 墙钟三档，来自 `team:` 配置节；任一到达即停并写 `system`。
- 用户插话不打断讨论链；`@` 语义沿用（进日志 + 插当前位次 / 下一轮开局）。
- 事件带 `chain_id`，轮终态与链终态可区分、可防交错；链内 `system` 条目实时可见。

**Non-Goals**

- 不做 `admin` 模式的无限轮（`unlimited` + `admin` 为非法配置）。
- 不做成员真正并发发言（仍串行）。
- 不做"成员自行决定要不要开下一轮"的二次 LLM 判定。
- 不改成员会话 / 记忆 review / 上下文切片游标语义；不改单轮模式的任何事件与返回值。
- 不做跨房间讨论、不做动态成员加入讨论链（链内被移出仍按 `left` 跳过）。
- 不引入新依赖；房间 WS 仍是唯一实时通道。

## 数据与配置模型

### Decision 1：`Room.discussion_mode` 与 API 白名单

- `Room.discussion_mode: str = "single"`；取值 `("single", "unlimited")`；`to_dict`/`from_dict` 成对写入，缺字段按 `single`（先例：`reply_mode` 的 `agent/team/models.py:134-147`）。
- 校验（创建与更新房间，按**合并后的生效值**）：
  - 非法值 → `400 {"error": "invalid_discussion_mode"}`（同 `invalid_reply_mode` 形态）。
  - `discussion_mode == "unlimited"` 且 `reply_mode != "everyone"` → `400 {"error": "discussion_mode_requires_everyone"}`。
  - 只把 `reply_mode` 改成 `admin`、而房间 `discussion_mode` 仍是 `unlimited` 且本次未给 `single` → 同上 400（不静默改写用户数据）。
- **字段穿透点（grill C13，必须一起改）**：
  - `web/server.py:489-497` 的 `_room_payload` 增 `discussion_mode` 键（`_team_state.rooms` 与 `room_state.room` 自动带上）；
  - `web/server.py:604-605` 的 `api_update_room` 硬编码白名单增 `discussion_mode`（否则 PATCH 静默丢字段）；
  - `web/team.py:627-689` 的 `create_room`/`update_room` 增参数与归一化函数 `_normalize_discussion_mode`；
  - 不新增 `discussion_active`（冗余），前端用 `round_active && room.discussion_mode === "unlimited"` 推导。

### Decision 2：讨论链状态模型（`chain_id`、`closed` 标记、await 纪律）

- `_rounds: dict[room_id, _ChainState]`：房间认领从「一轮」提升为「整条讨论链」；`is_round_active` 语义 = 该房间有进行中的讨论/轮次（`room_state.round_active` 同名同义）。
- `_ChainState` 钉死字段：
  - `room_id`；`chain_id: str`（房间内单调，形如 `"<room_id>:<n>"`，由 `self._chain_seq: dict[room_id,int]` 同步自增）；
  - `discussion_mode`（链启动快照）；`started_at: float`（`clock()`，构造函数注入 `clock: Callable[[], float] = time.monotonic`）；
  - `rounds: list[_RoundState]`（**已完成**的轮，含被停止打断的轮）；`round_index: int`（当前轮 1-based，无轮为 0）；`turns: int`（链内已完成成员回合数）；
  - `stop_requested: bool`；`closing: bool`（结束决定已做出，用于身份判断与 `discussion_ended` 一次性发送）；
  - `current: _RoundState`（**始终持有最近一轮**；轮间窗口靠 `_RoundState.closed` 判定，grill C8）；
  - `pending_mentions: list[str]`（轮间窗口到达的用户行首 `@`；**被某轮开局 slot 消费后立即清空**，链结束随链丢弃，不跨链）；
  - `pending_user_seqs: list[int]`（本链中「尚无任何成员回合切片看到」的用户条目 `seq`；用于 Q1 收敛判定）；
  - `limits`（链启动时从 `TeamConfig` 快照的 `max_rounds/max_turns/max_seconds`）。
- `_RoundState` 增字段：`closed: bool`（在本轮收尾**同步区**内置 `True`）。
- **生命周期与 `await` 纪律（grill C1）**：沿用现有单轮不变量（`orchestrator.py:369-385`）——
  1. 链认领在任何 `await` 之前（同步）；
  2. 每轮收尾的「轮终止判定 → `system` 追加 → `rounds.append` → `round_index` 推进 → 续轮/结束决定」全在**一段无 await 的同步区**内完成；
  3. **结束路径**：同步区继续执行「置 `chain.closing` → `_reset_room_statuses` → `_release_round`（身份判断）」，之后才 `await` 发 `system_entry` / `round_ended` / review / `discussion_ended`。⇒ 收尾 await 期间到达的用户消息看到房间**已释放**，会开**新链**（不会排队进将死链）；旧链终态事件与新链事件靠 `chain_id` 守卫区分；
  4. **续轮路径**：同步区只推进到「决定继续 + 置 `closed`」，随后 `await` 发 `round_ended(chain_continues=true)` / review，再进入下一轮；此期间到达的用户消息看到 `current.closed == True` ⇒ 只记 `pending_mentions`（不再往已关闭轮追加 slot），下一轮开局应用。
- 用户消息在链内的契约（grill C16，Q1 裁决后定稿）：
  - 唯一保证 = **进房间日志 + 行首 `@` 排入当前/下一轮 slot**；SHALL NOT 保证必有成员回合消费它。
  - 若在成员回合切片构造之后到达（无任何回合看到）→ 记入 `chain.pending_user_seqs`；收敛判定时按 Q1 裁决处理（推荐：**不得以 `converged` 结束**，有余量则强制再开一轮）。
- 用户消息消费判定：`_run_slot` 内 `view = log.build_injection(...)` 后，把 `view` 覆盖到的最大 `seq` 之前的所有 `pending_user_seqs` 移除（切片构造即视为本轮看到）。

### Decision 3：轮次推进与续轮判定（同步区算法，钉死）

- `_run_discussion(room, opening_text)`：
  1. **前置（同步）**：若 `room.members` 为空 → 不建链，按单轮语义走退化路径：append 用户条目、`await` 发 `user_message`、`await` 发 `round_ended(termination="completed", 无新字段)`、`await` review；返回 `RoundResult(termination="completed", rounds=0)`（grill C9：不出现误导性的 `converged`，也不发 `discussion_*`）。
  2. **认领（同步）**：`self._rounds[room.id] = chain`（查—建之间无 await）。
  3. append 用户条目（同步）；`await` 发 `user_message`。
  4. 循环 `while True`：
     a. **同步**：第 k>1 轮先 `log.append_system("讨论继续（第 k 轮）")` 并记 `next_system_entry`；`slots = opening_slots(room, opening_text_or_empty, roster, main_bot_ids)`；应用并清空 `pending_mentions`（按顺序插到队首、去重、非本群/自己忽略）；第 1 轮把开局用户条目 seq 加入 `pending_user_seqs`；建 `_RoundState(limit = min(轮预算, max_turns - chain.turns))`；`chain.current = state`；`chain.round_index += 1`。
     b. `await` 发 `system_entry`（若有，见 Decision 7）。
     c. `await self._drive(chain, state)`（每 slot 串行；停止/墙钟检查点见 Decision 5/6）。
     d. **同步收尾区**：`state.closed = True`；轮终止判定：
        - `chain.stop_requested` → `stopped`
        - `state.turns >= state.limit and state.index < len(state.slots)` → `limit`（append `system`「本轮因达上限结束」）
        - `state.posts` 空且 `state.failures > 0` → `all_failed`
        - 否则 `completed`
        `chain.rounds.append(state)`；`chain.turns += state.turns`；
        链级结束判定 `reason = _decide_chain_end(...)`（**纯同步、只看当前快照**）：
        | 优先级 | 条件 | reason | 备注 |
        |---|---|---|---|
        | 1 | `chain.stop_requested` | `stopped` | 用户停止（第四出口） |
        | 2 | 房间已不存在或无成员 | `completed` | 空房间退化语义 |
        | 3 | `room.discussion_mode != "unlimited"` 或 `reply_mode != "everyone"` | `mode_changed` | 链中被切回单轮 |
        | 4 | 本轮 `termination == "limit"` | `round_limit` | 本轮达本轮预算、链不续（grill C2） |
        | 5 | `len(chain.rounds) >= limits.max_rounds` | `max_rounds` | |
        | 6 | `chain.turns >= limits.max_turns` | `max_turns` | |
        | 7 | `elapsed >= limits.max_seconds` | `max_seconds` | |
        | 8 | 本轮 0 发言 0 失败，且 `pending_user_seqs` 为空 | `converged` | 自然收敛 |
        | 9 | 本轮 0 发言且有失败 | `all_failed` | |
        | 10 | 本轮有发言（`posts` 非空） | `None`（继续） | |
        | 11 | 本轮 0 发言 0 失败但**有未消费用户消息** | `None`（强制再开一轮，受 5–7 限制） | Q1 推荐口径 |
        若 `None` → `chain_continues = True`；否则 `chain_continues = False` 且 `chain.closing = True`，append 链结束 `system`（按 reason 文案表），`_reset_room_statuses` + `_release_round`（**同步**）。
     e. `await` 发 `round_ended`（`chain_id` / `round_index` / `chain_continues` / `termination` / `limit` / `status_seq`；单轮模式 payload 逐字段不变，见 Decision 9）。
     f. `await` review sink `on_round_end`（每轮一次，沿用）。
     g. 若 `chain_continues` → 回到 4a；否则 `await` 发 `discussion_ended`（`chain_id`、`reason`、`rounds`=已完成轮数、`rounds_started`、`turns`、`elapsed_seconds`、`status_seq`），返回 `RoundResult`。
- 链 end 的 `system` 文案（钉死）：`converged`「讨论已收敛（本轮全员静默）」；`stopped`「讨论已由用户停止」；`all_failed`「讨论已中止（本轮无人发言，存在失败）」；`round_limit`「讨论因本轮达上限结束」；`max_*`「讨论达安全上限结束」；`mode_changed`「讨论模式已切换为单轮」；`completed`（无成员）不写链级 system（退化路径已返回）。
- `rounds` 口径（grill C17）：`discussion_ended.rounds` = **已完成**轮数（含被中断的轮）；`rounds_started` = 进入过的轮数；停止发生在第 3 轮中 ⇒ `rounds=2`、`rounds_started=3`（用例断言精确值）。

### Decision 4：收敛、提示词与文案

- 「全员静默」= 本轮 `state.posts == []` 且 `state.failures == 0`（`posts` 只收 `post` 条目；空文本产出已归一为 silent，见 `orchestrator.py:521-544`），且无未消费用户消息（Q1 裁决后定稿）。
- **不为"是否继续"额外调用模型判定**（多一次调用就多一份成本与延迟）。
- 成员 prompt 增强（仅 `unlimited`）：
  - 在 `ROOM_REPLY_INSTRUCTION` **之前**（即 prompt 末段）追加：
    - 第 1 轮：`Round 1 of a continuous discussion; every member speaks at most once per round.`
    - 第 k>1 轮：`Round k of a continuing discussion. There is no new user message this round; the discussion continues because the previous round produced new content.`
    - 共同句：`If the discussion has converged or you have nothing new to add, reply [PASS] — do not repeat points already made; do not speak just to fill the round.`
  - `single` 模式 prompt 逐字节不变（测试锁定：同一输入下字符串相等）。
- `all_failed` 文案改「本轮无人发言，存在失败」（grill C14），不再写"全员失败"。

### Decision 5：停止讨论 = 优雅停止（`unlimited` 的第四出口；`single` 见 Q3）

- 触发：REST `POST /api/team/rooms/{room_id}/discussion/stop` → `{"stopping": bool, "room_id": ...}`；房间 WS 消息 `{"type": "stop_discussion"}`（前端主路径）。
- `TeamService.stop_discussion(workspace, room_id)`：**workspace 口径与 `submit_room_message` 一致**（grill C19）：先按传入 workspace 找；找不到则 `workspace_of_room(room_id)` 回落，仍找不到 → `404 unknown_room`。
- `RoomOrchestrator.request_stop(room_id) -> bool`：
  - 无活动链（或链已 `closing`）→ `False`（幂等 no-op）。
  - 否则在**同步段**内完成「读 `stop_requested` → 判首次 → 置位」，`await` 发 `discussion_stop_requested`（`chain_id`）；重复请求返回 `True` 但不再发事件（grill CQ11）。
- 生效点（**不打断正在跑的成员回合**）：
  - `_drive` 每个 slot 结束后检查 `stop_requested` → 跳出（跳过本轮剩余 slot）；
  - 轮间续轮判定（Decision 3 的同步区）已含 `stopped` 优先级第 1；
  - 停止请求恰好落在「最后一个 slot 已跑完、尚未进入收尾同步区」→ 同步区仍会读到 `stop_requested`（单线程无竞态）。
- 停止后：成员状态 reset（同步、先于释放）、房间认领释放、写 `system`、发 `round_ended(stopped)` / `discussion_ended(stopped)`。
- `single` 模式：按 Q3 推荐 = **收紧**（不提供停止、`request_stop` 返回 `False`、不产生 `stopped`）；若用户裁决放开，则改为"单轮也在当前回合后结束本轮"并在 delta 让「三出口」变「四出口」。

### Decision 6：安全阀（`team:` 配置节，链启动快照）

- `TeamConfig` 新增（`agent/config.py:273-291`）：
  - `discussion_max_rounds: int = 200`
  - `discussion_max_turns: int = 600`
  - `discussion_max_seconds: float = 6000.0`
- 解析（`_parse_team_config`）：`discussion_max_rounds`/`discussion_max_turns` 用 `_parse_timeout_seconds` 同形的**正整数、显式拒 bool** helper（grill C15；0 非法）；`discussion_max_seconds` 用 `float()` + `> 0`（同 `turn_timeout_seconds`）。非法值抛 `ConfigError`。
- **生效时机（grill C5）**：`TeamConfig` 只在 Web 启动期解析一次，`_WorkspaceTeam` 按 workspace 缓存并一次性构造 `RoomOrchestrator` ⇒ **改 YAML 需重启 Web 进程**才生效；链启动时快照三值（链内不变）。文档与测试按此写（两次构造、不同 limits ⇒ 两条链各自快照）。
- **两档并非独立（grill 补充）**：默认 3~5 人 everyone 房下，`max_turns` 通常先于 `max_rounds` 触发（每轮 = 成员数回合；3 人房 600/3=200 轮恰与 200 轮打平，5 人房 600/5=120 轮先触发）。design 与文档 SHALL NOT 把两档描述成互相独立；测试分别用小值单独触发。
- 判定点：
  - 续轮前（同步区，Decision 3 优先级 5–7）。
  - 轮内：`round_limit = min(轮预算, max_turns - chain.turns)` 截断本轮。
  - 墙钟检查点：**Q4 推荐 = 每个 slot 之间（`_drive` 循环顶）也检查一次**（不打断在跑回合，仅不再开新回合），最坏越界 ≤ 一个 `turn_timeout`（默认 240s）；若用户裁决只保留轮间检查，则最坏越界 = 本轮剩余 slot × `turn_timeout`（默认 3 人 everyone 屋约 44 分钟，grill C10 量级）。
- 单轮模式不使用这三个参数。

### Decision 7：事件契约、`chain_id` 守卫、链内 `system` 可见性、UI 状态

- `unlimited` 模式事件（房间总线转发，`web/server.py:663-750`）：
  - `discussion_started {room_id, chain_id, discussion_mode, members, round_index: 1, limits}`
  - `system_entry {room_id, chain_id, seq, text}`（链内新增 `system` 条目实时广播：续轮 / 收敛 / 停止 / 达上限 / 模式切换）
  - `discussion_stop_requested {room_id, chain_id}`
  - `discussion_ended {room_id, chain_id, reason, rounds, rounds_started, turns, elapsed_seconds, status_seq}`
  - `round_ended` 扩展：`chain_id`、`round_index`、`chain_continues`；`termination` 新增 `stopped`。
- **`single` 模式**：不发 `discussion_*`/`system_entry`，`round_ended` payload **逐字段不变**（`{room_id, termination, limit, status_seq}` 四键，整字典快照断言；grill CQ10）。
- **链身份守卫（grill C6）**：`round_ended` / `discussion_ended` / `system_entry` / `discussion_stop_requested` 都带 `chain_id`；`group.js` 维护 `state.chainId`（来自 `discussion_started` / `room_state` 快照），只应用与其一致的轮/链终态。`discussion_ended` 由 `chain.closing` 保证每链至多一次。
- `room_state` 快照新增：`discussion_round`（当前链已进入的轮序号，1-based；无链为 0）、`discussion_reason`（最近一次链结束原因，进程内内存）。`room` 对象带 `discussion_mode`。不新增 `discussion_active`。
- 前端（`web/static/group.js` + `group_status.js`）：
  - 纯函数放 `group_status.js` 并导出（grill C12）：`describeRoundEnd(data)`、`describeDiscussionEnd(reason)`、`shouldShowStop(snapshot)`、`shouldApplyChainEvent(state, data)`；`group.js` 只做 DOM/状态调用。
  - 状态文案：`discussion_started` / 续轮 →「讨论中（第 k 轮）」；`discussion_ended` 映射 `converged`「讨论已收敛」/ `stopped`「讨论已停止」/ `max_*`「讨论达安全上限」/ `all_failed`「讨论已中止（本轮无人发言，存在失败）」/ `mode_changed`「讨论模式已切换为单轮」/ `cancelled`「讨论已中止」/ `error`「讨论异常结束」/ `round_limit`「讨论因本轮达上限结束」/ `completed`「讨论已结束」；`chain_continues=true` 时**不**显示「本轮结束」。
  - 停止按钮：`round_active && room.discussion_mode==="unlimited"` 时可见（`shouldShowStop`），点击发 WS `stop_discussion`（WS 未连通 → REST），点击后置灰「正在停止…」，`discussion_ended` 后恢复。
  - 链内 `system` 条目经 `system_entry` 事件实时 append 到 timeline（按 `seq` 去重合并），不再只靠刷新。
  - 设置对话框：`discussion_mode` 下拉的 `unlimited` 选项在 `reply_mode != everyone` 时 `disabled`（`openDialog` 无字段联动，用静态禁用 + 服务端 400 兜底展示错误；grill C11）。
  - 头部布局：停止控件放进既有 `.group-room-actions`，390px 下沿用 wrap、SHALL NOT 横向溢出（对应 `style.css:2274,2309-2316`）。
- `discussion_round` 口径（grill C13）：**当前链已进入的轮序号**（1-based；无链 0）。文案「第 k 轮」直接用它，不做 +1。

### Decision 8：取消 / 异常 teardown 扩展到链

- 现状：轮 task 被 cancel（房间 WS 断开 → `web/server.py:748-750`）→ `_run_round` 捕 `CancelledError` → reset + `_schedule_teardown` 尽力发 `round_ended(cancelled)`（`orchestrator.py:408-422`）。
- 新语义：链内取消 = 结束当前轮 + 结束链。同步区先 reset/置 `closing`（沿用现有次序），后台 teardown 尽力发 `round_ended(termination="cancelled", chain_id, chain_continues=false)` + `discussion_ended(reason="cancelled", chain_id, status_seq)`；不写房间日志、不产生 `RoundResult`。意外异常同理（`reason="error"`，异常仍上抛）。
- 幂等与身份：沿用 `_schedule_teardown` 的身份/一次发送判断；`chain.closing` 防止重复 `discussion_ended`。
- **Q2 待裁决**：链生命周期是否仍绑房间 WS（推荐：保持现状 + 链因断线中止时写一条 `system`「讨论因页面断开而中止」，让用户知道原因；若改服务端持有则另立设计）。

### Decision 9：兼容性与迁移

- 数据：旧 `room.json` 缺 `discussion_mode` → 读为 `single`；写回补字段，无迁移脚本。
- 事件：`single` 模式零新事件、`round_ended` 逐字段不变（整字典断言）。`unlimited` 事件均为新增。
- `RoundResult` 新增带默认值字段（grill D11）：`discussion_mode: str = "single"`、`discussion_reason: str | None = None`、`chain_id: str | None = None`、`rounds: int = 0`、`rounds_started: int = 0`；`termination` 新增 `stopped`（`single` 不产生）。
- 提示词：仅 `unlimited` 追加（Decision 4）。
- 不做：旧前端版本协商（`chain_id` 缺失/不一致时旧前端按现状显示，可接受）；`admin` 模式无限轮；固定 3 轮上限（用户要求"直到收敛/手动停止"）。

### Decision 10：测试策略（TDD，先红后绿）

| 层 | 用例（每条先红后绿；**期望值写死**：调用次数、system 文案、reason） |
| --- | --- |
| 模型/存储 | `discussion_mode` 默认 `single`、roundtrip、旧 JSON 缺字段兼容 |
| 配置 | 三参数默认 200/600/6000、YAML 覆盖、非法值（0/负数/字符串/bool）抛 `ConfigError`；`TeamConfig` 构造两次不同 limits ⇒ 两条链各自快照 |
| 编排器（核心） | ① unlimited 连开 3 轮（R1 全员发言 → R2 部分 PASS → R3 全员 PASS）→ `converged`、`rounds=3`、`rounds_started=3`、system 文案精确；② 每轮每人一次、admin 先；③ single 模式只跑一轮，`round_ended` 整字典快照与现状一致；④ 用户插话进日志 + `@` 插当前轮；轮间窗口进 `pending_mentions` 且下一轮生效后被清空（重复 `@` 只置顶一次）；链结束未消费 mentions 不跨链；⑤ 停止：回合进行中请求 → 该回合跑完即结束、剩余 slot 不跑、`rounds=2/rounds_started=3`、`round_ended(stopped)` + `discussion_ended(stopped)`、只发一次；⑥ 无活动链 `request_stop=False`；`single` 房 `request_stop=False` 且不产生 `stopped`（Q3 推荐）；⑦ `max_rounds`/`max_turns`/`max_seconds` 三档（clock 注入）+ `round_limit` 路径（`extra_turns=0` 注入）；⑧ 链中切回 `single` → `mode_changed`；⑨ 空成员房间 unlimited → 退化单轮、无 `discussion_*`（grill C9）；⑩ 取消/意外异常 → `round_ended(cancelled|error)` + `discussion_ended` 一次 + 状态 reset；⑪ 收尾同步区竞态：gate 阻塞最后一个 slot 结束后才放行，停止/取消/新消息三路各断言（grill C1）；⑫ review sink 抛异常不中断链；⑬ Q1 未消费消息：本轮 0 发言但插话无人看到 → 强制再开一轮（若 Q1 选推荐）；安全阀耗尽时以 cap reason 结束且消息留在日志；⑭ `chain_id` 递增值与事件去重 |
| Web 服务 | 房间 create/patch 校验（三种非法组合）；`_room_payload`/`PATCH` 白名单带 `discussion_mode`；`room_state` 字段（`discussion_round` 口径）；REST stop 幂等 + 跨 workspace 回落；WS `stop_discussion`；事件顺序 `discussion_started → member_* → discussion_stop_requested → round_ended(stopped) → discussion_ended(stopped)`；`single` 事件流与现状一致 |
| 前端 | `group_status.js` 纯函数（文案映射全覆盖、`shouldShowStop`、`shouldApplyChainEvent` 的 chain_id 守卫、`round_ended(chain_continues)` 不显示「本轮结束」）；设置下拉 disabled；停止按钮置灰/恢复；`system_entry` 追加时间线；390px 头部不溢出（浏览器用例） |
| 回归 | 全量 `uv run pytest -q`；`openspec validate --all --strict`；`uv run python scripts/check_openspec_artifacts.py --base-ref origin/master --require-base` |

## Risks

- **成本失控**：默认 `single` + 房间级开关 + 三档安全阀 + `[PASS]` 收敛提示 + 停止按钮；文档写明单轮 = N 次调用、无限链按轮线性放大。
- **链收尾 await 窗口**：按 Decision 2 的同步区纪律 + `chain_id` 守卫 + 释放后再发终态（与现状单轮同形），并用 gate 用例锁住。
- **双终态交错**：`round_ended` 与 `discussion_ended` 靠 `chain_id` + `chain.closing` 一次性发送守卫；`status_seq` 沿用单调守卫（`group_status.js:60-65` 是严格小于，同 seq 均会应用，grill D9）。
- **两档安全阀不独立**：`max_turns` 通常先于 `max_rounds` 触发（见 Decision 6），测试与文档不得声称互相独立。
- **规格破坏面**：三份当前规格 MODIFIED/ADDED；`configuration` 为 **ADDED**（grill CQ5/C18）；收尾须 `current_spec_synced` 事件。
- **断线中止不透明**：Q2 推荐在链因断线中止时写 system 说明；若用户选服务端持有，另立设计。

## Document Impact

- `openspec/specs/multi-agent-collaboration/spec.md`：MODIFIED「房间级互斥与轮次终止」「房间应答模式」；ADDED「讨论链自动续轮与收敛」。
- `openspec/specs/web-ui/spec.md`：MODIFIED「人设与房间的管理入口」；ADDED「群聊讨论链状态与停止讨论控件」。
- `openspec/specs/configuration/spec.md`：**ADDED**「群聊讨论链安全阀可配置」。
- `docs/architecture.md` 群聊小节：终止口径改「单轮 / 讨论链」+ 停止 + 安全阀 + 配置需重启；`CONTEXT.md` 补「讨论链」；`docs/interview-script/` 相关表述检查。
- `asterwynd.example.yaml`：`team:` 配置节示例。
- `docs/openspec-change-backlog.md`：收尾移除本条目。

## Open Questions (pending user ruling)

- **Q1**（未消费的用户消息）：见 `reviews/grill-design.md` Q1。推荐口径：**收敛优先让位于"消息必须被看到"**——存在未消费用户消息时不得以 `converged` 结束，有余量则强制再开一轮；安全阀耗尽则按 cap reason 结束（消息留在日志，下一条用户消息开新链时可见）。
- **Q2**（链生命周期与 WS）：推荐保持现状（房间 WS 断开 = 取消链），并**在链因断线中止时写 `system`「讨论因页面断开而中止」**（单轮取消仍不写日志）。
- **Q3**（single 是否可停止）：推荐**收紧**——单轮不提供停止按钮、`request_stop` 对 `single` 返回 `False`、不产生 `stopped`。
- **Q4**（墙钟检查粒度）：推荐**每个 slot 之间也检查**（不打断在跑回合，最坏越界 ≤ 一个 `turn_timeout`）。

## User Rulings (2026-10-24)

（待主 agent 停轮确认后回填 Q1–Q4 的用户答复。）

## Pre-Implementation Review

（待设计对抗闭环与用户裁决后回填：grill 决策、对抗轮次、修复项、出口。）
