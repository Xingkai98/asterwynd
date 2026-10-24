# Design: 群聊 everyone 模式无限讨论链（讨论链 + 停止按钮 + 安全阀）

> 修订记录：v4（2026-10-24）按 `reviews/grill-design.md`（C1–C22）与 `reviews/grill-adversarial.md`（I1–I12 / L1–L18）修正，并落实用户对 Q1–Q4 的裁决（见 `## User Rulings`）。设计以本文件为准。

## Context

当前群聊的轮次语义全部钉死在「一次用户消息 = 一轮」：

| 事实 | 证据 |
| --- | --- |
| 唯一开轮入口是用户消息 | `agent/team/orchestrator.py:315-341` `submit_user_message`；`_rounds` 空闲才开轮 |
| 一轮 = 走完 slot 序列即结束 | `:347-407` `_run_round`；`:428-434` `_drive` |
| `everyone` 无 `@` 时开局 slot = 全体成员各一次 | `:153-182` `opening_slots` |
| 房间互斥只覆盖单轮；且「`_drive` 返回 → 释放认领」是**无 await 同步区** | `:309-310`、`:371-384`（既有并发用例依赖此不变量） |
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
- **字段穿透点（必须一起改）**：`web/server.py:489-497` 的 `_room_payload` 增 `discussion_mode`（`_team_state.rooms` 与 `room_state.room` 自动带上）；`web/server.py:604-605` 的 `api_update_room` 白名单增键（否则 PATCH 静默丢字段）；`web/team.py:627-689` 的 `create_room`/`update_room` 增参数与 `_normalize_discussion_mode`。
- 不新增 `discussion_active`；前端用 `round_active && room.discussion_mode === "unlimited"` 推导。

### Decision 2：讨论链状态模型（`chain_id`、`closed`、`terminal_sent`、await 纪律）

- `_rounds: dict[room_id, _ChainState]`：房间认领升为「整条讨论链」；`is_round_active` 语义 = 该房间有进行中的讨论/轮次。
- `_ChainState` 钉死字段：
  - `room_id`；`chain_id: str`（房间内单调 `"<room_id>:<n>"`，由 `self._chain_seq: dict[room_id,int]` 同步自增）；
  - `discussion_mode`（链启动快照）；`started_at: float`（`clock()` 注入，默认 `time.monotonic`）；
  - `rounds: list[_RoundState]`（**已正常收尾的轮**；被用户停止打断的当前轮与取消中的当前轮**不计入**，`rounds_started` 由 `round_index` 表达 —— grill I3/L17）；
  - `round_index: int`（当前轮 1-based；`rounds_started` 即最后一次进入的轮序号）；`turns: int`（链内已完成成员回合数）；
  - `stop_requested: bool`；`closing: bool`（结束决定已做出，用于身份判断与 `discussion_ended` 一次性发送）；
  - `current: _RoundState`（**认领后到链结束前恒非 `None`**：链认领与第 1 轮骨架在**同一无 await 同步区**建立，grill I1）；轮间窗口靠 `current.closed` 判定；
  - `pending_mentions: list[str]`（轮间窗口到达的用户行首 `@`；**被某轮开局 slot 消费后立即清空**；链结束随链丢弃、不跨链）；
  - `pending_user_seqs: list[int]`（「尚无任何成员回合切片看到」的用户条目 `seq`；**到达即同步写入**，见下）；
  - `limits`（链启动时从 `TeamConfig` 快照的 `max_rounds/max_turns/max_seconds`）。
- `_RoundState` 增字段：`closed: bool`（本轮收尾同步区置 `True`）；`terminal_sent: bool`（本轮的终态事件已发出；**在发出本轮 `round_ended` 之前置位**，取消/异常 teardown 用它避免同轮重复 `round_ended`，grill L16/N5）。
- **await 纪律（沿用单轮不变量，grill C1/I1/I6）**：
  1. 链认领与第 1 轮 `_RoundState` 骨架（`start_seq` 先占位、`limit`、slots）在**同一同步区**完成并挂到 `chain.current`；
  2. 每轮收尾的「轮终止判定 → `system` 追加 → `rounds.append`（按 I3 规则）→ 续轮/结束决定」在**无 await 同步区**完成；
  3. **结束路径**：同步区继续「置 `closing` → `_reset_room_statuses` → `_release_round(room_id, chain)`（身份比较对象 = 链，grill I6）」；之后才 `await` 发事件。收尾 await 期间到达的用户消息看到房间已释放 → 开**新链**（不会排进将死链）；新旧链事件靠 `chain_id` 区分；
  4. **续轮路径**：同步区只到「决定继续 + 置 `closed`」，随后 `await` 发事件/review，再进入下一轮；此期间用户消息看到 `current.closed == True` → 只记 `pending_mentions`；
  5. `_run_discussion` 的 `finally` SHALL 兜底释放（照搬现状 `orchestrator.py:423-426` 的 `finally` 语义）：若链仍是本房间认领者则 `_reset_room_statuses` + `_release_round(room_id, chain)`；取消/异常路径不依赖正常收尾区。
- 用户消息契约（grill C16/I5）：
  - 唯一保证 = **进房间日志 + 行首 `@` 排入当前/下一轮 slot**；SHALL NOT 保证必有成员回合消费它。
  - **写入时机**：链内 active 分支在 `log.append_user(...)` 后**同步**把 `entry.seq` 追加进 `chain.pending_user_seqs`（到达即写；未来是否被看到由下一回合切片决定）。
  - **消费时机**：`_run_slot` 内 `view = log.build_injection(...)` 之后，移除 `pending_user_seqs` 中 `<= view` 覆盖到的最大 `seq` 的项；「覆盖到的最大 seq」取**本次注入看到的房间日志末条 seq**（`view["current"]` 的最后一条；不是三层窗口首条，避免窗口截断时把旧消息误记已消费，`roomlog.py:127-132`）。
  - 收敛判定按 Q1 用户裁决处理（见 Decision 3 优先级表第 11 行）。

### Decision 3：轮次推进与续轮判定（同步区算法，钉死）

- `_run_discussion(room, opening_text)`：
  1. **前置（同步）**：若 `room.members` 为空 → 不建链，退化单轮：append 用户条目、`await user_message`、`await round_ended(termination="completed", 四键不变)`、`await review`；返回 `RoundResult(termination="completed", rounds=0)`（grill C9/I9）。
  2. **认领 + 第 1 轮骨架（同一同步区）**：建 `_ChainState`；`start_seq`、`slots = opening_slots(room, opening_text, ...)`、`limit = len(slots)+extra+(admin?admin_extra:0)` 与剩余链额度取 min；建 `_RoundState`；`chain.current = state`；`chain.round_index = 1`；`self._rounds[room.id] = chain`。**查—建—挂 current 之间无任何 await**（grill I1）。
  3. append 用户条目（同步，回填 `state.start_seq` 与 `pending_user_seqs`）；`await user_message`；`unlimited` 下再 `await discussion_started`（payload 钉死：`{room_id, chain_id, discussion_mode, members:[persona_id...], round_index:1, limits:{max_rounds,max_turns,max_seconds}}`，grill I4/L9）。
  4. 循环 `while True`：
     a. **（k>1，先检查 `stop_requested`）同步建下一轮**：若 `stop_requested` 已置位则**不建新轮**——直接置 `chain.closing`、append「讨论已由用户停止」`system`、`_reset_room_statuses` + `_release_round` 并结束链（不补发 `round_ended`，`rounds`/`rounds_started`/`turns` 保持上一轮值；grill N12/N14）；否则`sys_entry = log.append_system("讨论继续（第 k 轮）")`；`slots = opening_slots(room, "", ...)`（**k>1 SHALL 传空串**，否则开局行首 `@` 会让后续每轮只剩点名者，grill I7）；应用并清空 `pending_mentions`（按顺序插队首、去重、非本群/自己忽略）；`limit = min(轮预算, max_turns - chain.turns)`；建 `_RoundState`；`chain.current = state`；`chain.round_index += 1`。
     b. `await system_entry`（k>1，payload：`{room_id, chain_id, seq, text}`）。
     c. `await self._drive(chain, state)`：**每个 slot 前后检查** `stop_requested`（跳过剩余 slot）与墙钟（`elapsed >= max_seconds` → 不再开新回合，grill L15/Q4）；`_run_slot(chain, state, persona_id)` 内消费 `pending_user_seqs`（Decision 2）。
     d. **同步收尾区**：`state.closed = True`；轮终止判定：`stop_requested` → `stopped`；`turns >= limit and index < len(slots)` → `limit`（append system「本轮因达上限结束」）；0 发言且有失败 → `all_failed`；否则 `completed`。**仅当 termination ∈ {completed, limit, all_failed} 时 `chain.rounds.append(state)`**（`stopped` 不计入，grill I3）；`chain.turns += state.turns`。链级判定见下表（纯同步快照）。
        | 优先级 | 条件 | reason | 备注 |
        |---|---|---|---|
        | — | 取消/意外异常（控制流） | `cancelled` / `error` | **不参与下表排序**，优先于一切快照条件（grill I9） |
        | 1 | `chain.stop_requested` | `stopped` | |
        | 2 | 房间已不存在或无成员 | `completed` | 退化语义，不写链级 `system` |
        | 3 | `room.discussion_mode != "unlimited"` 或 `reply_mode != "everyone"` | `mode_changed` | |
        | 4 | 本轮 `termination == "limit"` | `round_limit` | 回合额度截断也走这里（grill I12） |
        | 5 | `len(chain.rounds) >= limits.max_rounds` | `max_rounds` | |
        | 6 | `chain.turns >= limits.max_turns` | `max_turns` | 仅当本轮正常走完、额度恰尽 |
        | 7 | `elapsed >= limits.max_seconds` | `max_seconds` | |
        | 8 | 本轮 0 发言 0 失败且 `pending_user_seqs` 为空 | `converged` | |
        | 9 | 本轮 0 发言且有失败 | `all_failed` | |
        | 10 | 本轮有发言 | `None`（继续） | |
        | 11 | 本轮 0 发言 0 失败但有未消费用户消息 | `None`（强制再开一轮，受 5–7 限制） | Q1 用户裁决 |
        若 `None` → `chain_continues = True`；否则 `chain.closing = True`、append 链结束 `system`（按文案表）、`_reset_room_statuses`、`_release_round(room_id, chain)`（均同步）。
     e. `await` review sink `on_round_end`（**保持现状顺序：review 在 `round_ended` 之前**，grill L12；每轮一次）。
     f. `await round_ended`：`unlimited` payload 加 `chain_id` / `round_index` / `chain_continues`；`single` 四键不变。
     g. 若 `unlimited` 且链结束：`await system_entry`（链结束 `system` 条目，若有）→ `await discussion_ended`（`chain_id`、`reason`、`rounds`、`rounds_started=round_index`、`turns`、`elapsed_seconds`、`status_seq`=与最后一次 `round_ended` 相同的 reset 结果，grill L10）。返回 `RoundResult`。
  5. **single 分支（钉死，grill I2）**：`single` 共用 `_ChainState` 外壳（统一释放/身份语义），但：不执行链级结束判定（Decision 3 表）、不写链级 `system`、不发 `discussion_started`/`system_entry`/`discussion_ended`、`round_ended` 不附加 `chain_id`/`round_index`/`chain_continues`；每轮结束即链结束（三出口语义逐字段保持，Decision 10 ③ 用整字典快照与负向断言锁住）。
- 链 end `system` 文案（钉死）：`converged`「讨论已收敛（本轮全员静默）」；`stopped`「讨论已由用户停止」；`all_failed`「讨论已中止（本轮无人发言，存在失败）」；`round_limit`「讨论因本轮达上限结束」；`max_*`「讨论达安全上限结束」；`mode_changed`「讨论已结束（模式已变更）」；断线取消「讨论因页面断开而中止」；`error` 不写；`completed`（无成员）不写（理由：房间/成员已不存在，写日志无意义，grill L3）。
- `rounds` 口径（grill I3）：`rounds` = `len(chain.rounds)`（只含正常收尾的轮）；停止发生在第 3 轮中 ⇒ `rounds=2`、`rounds_started=3`（用例断言精确值）。

### Decision 4：收敛、提示词与文案

- 「全员静默」= 本轮 `state.posts == []` 且 `state.failures == 0`（`posts` 只收 `post` 条目；空文本产出已归一为 silent，`orchestrator.py:521-544`），且无未消费用户消息。
- **不为"是否继续"额外调用模型判定**。
- 成员 prompt 增强（仅 `unlimited`，在 `ROOM_REPLY_INSTRUCTION` **之前**追加）：
  - 第 1 轮：`Round 1 of a continuous discussion; every member speaks at most once per round.`
  - 第 k>1 轮：`Round k of a continuing discussion. There is no new user message this round; the discussion continues because the previous round produced new content.`
  - 共同句：`If the discussion has converged or you have nothing new to add, reply [PASS] — do not repeat points already made; do not speak just to fill the round.`
  - `single` 模式 prompt 逐字节不变（测试锁定）。
- `all_failed` 文案「本轮无人发言，存在失败」（grill C14）。

### Decision 5：停止讨论 = 优雅停止（`unlimited` 第四出口；`single` 不提供）

- 触发：REST `POST /api/team/rooms/{room_id}/discussion/stop` → `{"stopping": bool, "room_id": ...}`；房间 WS 消息 `{"type": "stop_discussion"}`（前端主路径）。
- `TeamService.stop_discussion(workspace, room_id)`：workspace 口径与 `submit_room_message` 一致（先按传入 workspace，找不到回落 `workspace_of_room`，仍无 → 404，grill C19）。
- `async RoomOrchestrator.request_stop(room_id) -> bool`（grill L2）：
  - 无活动链、链已 `closing`、或房间 `discussion_mode == "single"` → `False`（Q3 用户裁决：单轮不提供停止；幂等 no-op）。
  - 否则**同步**完成「读 `stop_requested` → 判首次 → 置位」；首次时 `await` 发 `discussion_stop_requested {room_id, chain_id}`；重复请求返回 `True` 但不重复发事件（grill CQ11）。
- 生效点（不打断在跑回合）：`_drive` 每个 slot **前后**都检查（grill L15，保证轮间窗口也最快收敛）；轮间续轮判定优先级 1。
- 停止后：若当前有进行中的轮次，则同步 reset/释放、写 `system`、发 `round_ended(stopped)` 与 `discussion_ended(stopped)`；若停止请求落在轮间窗口（没有进行中的轮次），则不补发 `round_ended`（见 4a 分支），只发 `discussion_ended(stopped)`。
- `single` 模式：`request_stop` 返回 `False`、不产生 `stopped`、按钮不显示（Q3）。

### Decision 6：安全阀（`team:` 配置节，链启动快照）

- `TeamConfig` 新增：`discussion_max_rounds: int = 200`、`discussion_max_turns: int = 600`、`discussion_max_seconds: float = 6000.0`。
- 解析：`discussion_max_rounds`/`discussion_max_turns` 用 `_parse_timeout_seconds` 同形 helper（正整数、显式拒 bool、0 非法，grill C15）；`discussion_max_seconds` 用 `float()` + `>0`（同 `turn_timeout_seconds`）。非法抛 `ConfigError`。
- **生效时机（grill C5/L14）**：配置在 Web 启动期解析一次；`_WorkspaceTeam` 首次 `team_for` 时懒构造并注入 `RoomOrchestrator`、按 workspace 缓存 ⇒ 改 YAML 需重启进程；链启动时快照。
- **两档关系（grill I12，修正算术）**：一轮的回合数 ≥ 成员数，且可被成员互相 `@` 接力放大到 `成员数 + extra_turns + admin_extra_turns`（默认 3 人 everyone 房最多 11）。因此 `max_turns` 在绑定意义上通常先到；但**上报 reason 时**：回合额度截断当前轮会让本轮 `termination=limit`，链 reason 走优先级 4 `round_limit`；只有额度恰好在轮末耗尽（本轮正常走完、`index == len(slots)` 且 `turns >= max_turns`）才报 `max_turns`。文档/测试 SHALL NOT 把两者混写。
- 判定点：续轮前（优先级 5–7）；轮内 `round_limit = min(轮预算, max_turns - chain.turns)` 截断；墙钟：**每个 slot 之间**检查（Q4 用户裁决；不打断在跑回合），越界上界 ≤ 一个 `turn_timeout`（默认 240s；`turn_timeout` 本身可配置且无上界，文档如实说明，grill L17）。
- 单轮模式不使用这三个参数。

### Decision 7：事件契约、`chain_id` 守卫、链内 `system` 可见性、UI 状态

- `unlimited` 事件（房间总线转发，`web/server.py:663-750`）：
  - `discussion_started {room_id, chain_id, discussion_mode, members: [persona_id...], round_index: 1, limits: {max_rounds, max_turns, max_seconds}}`
  - `system_entry {room_id, chain_id, seq, text}`（**仅链级语义**的 `system` 条目：续轮/收敛/停止/达上限/模式切换/断线中止；成员失败类 `system` 仍由现有 `member_failed` 前端合成，两条路径不重复，grill L18）
  - `discussion_stop_requested {room_id, chain_id}`
  - `discussion_ended {room_id, chain_id, reason, rounds, rounds_started, turns, elapsed_seconds, status_seq}`
  - `round_ended` 扩展：`chain_id`、`round_index`、`chain_continues`；`termination` 新增 `stopped`。
- **`single` 模式**：不发 `discussion_*`/`system_entry`；`round_ended` payload 四键不变（整字典快照断言）。
- **链身份守卫**：`round_ended` / `system_entry` / `discussion_stop_requested` / `discussion_ended` 都带 `chain_id`；`group.js` 维护 `state.chainId`，只应用与之一致的事件。守卫纯函数签名钉死：`shouldApplyChainEvent(currentChainId, data)`（grill L4）；`discussion_ended` 由 `chain.closing` 保证每链至多一次。
- `room_state` 快照：`room` 对象带 `discussion_mode`；新增 `discussion_round`（当前链已进入轮序号，1-based；无链与 `single` 恒 0）与 `discussion_reason`（最近一次链结束原因）。宿主：编排器 `self._discussion_state: dict[room_id, {"round": int, "reason": str|None}]`——进入第 k 轮时更新 `round=k`，链释放时置 `round=0` 并写 `reason`；读取方法 `discussion_snapshot(room_id)`（grill I8/N2）。
- 前端（`group.js` + `group_status.js`）：
  - 纯函数（`group_status.js` 导出、`test_group_status_js.py` 同形测试）：`describeRoundEnd(data)`、`describeDiscussionEnd(reason)`、`shouldShowStop(snapshot)`、`shouldApplyChainEvent(currentChainId, data)`。
  - `room_state` 分支：`round_active && room.discussion_mode === "unlimited" && discussion_round > 0` → 显示「讨论中（第 k 轮）」；否则若 `discussion_reason` 非空 → 显示对应终态文案（`single` 不做该恢复，`discussion_round` 恒 0）；刷新/重连据此恢复（grill I8/N6）。
  - `round_ended(termination="stopped")` 的文案 SHALL 为「讨论已停止」（不得显示「本轮结束」；随后 `discussion_ended(stopped)` 覆盖为同一文案，grill N10）。
  - 状态文案映射同 delta；`chain_continues=true` 时**不**显示「本轮结束」。
  - 停止按钮：`round_active && room.discussion_mode==="unlimited"` 可见；点击发 WS `stop_discussion`（WS 未连 → REST），置灰「正在停止…」，`discussion_ended` 后恢复。
  - `system_entry` 实时 append 时间线（按 `seq` 去重）。
  - 设置对话框：`openDialog` 的 option schema 增 `disabled` 支持（grill L5）；`reply_mode != everyone` 时 `unlimited` 置 disabled；新建房间默认 `admin` ⇒ **创建 everyone+unlimited 需两步（先建 everyone，再改讨论模式）**，对话框 UI 如实提示；服务端 400 兜底展示。
  - 头部：停止控件放 `.group-room-actions`，390px 下沿用 wrap、不横向溢出（`style.css:2274,2309-2316`）。
- `discussion_round` 口径：当前链已进入的轮序号（1-based；无链 0），文案直接用、不 +1。

### Decision 8：取消 / 异常 teardown 扩展到链

- 现状：房间 WS 断开 → cancel 轮次 task（`web/server.py:748-750`）→ `_run_round` 捕 `CancelledError` → reset + `_schedule_teardown` 尽力发 `round_ended(cancelled)`（`orchestrator.py:408-426`）。
- 新语义（Q2 用户裁决 + grill I6/I9/L16）：
  - **取消/异常优先于一切快照条件**，不参与 Decision 3 的 reason 排序；
  - 同步区：置 `closing`、`_reset_room_statuses`、`_release_round(room_id, chain)`；`finally` 兜底同上；
  - 后台 teardown 尽力发 `round_ended`（仅当 `state.terminal_sent` 为假；`termination="cancelled"|"error"`、`chain_id`、`chain_continues=false`）+ `discussion_ended`（`reason` 同名、`chain_id`、`status_seq`），每链至多一次；不产生 `RoundResult`；
  - **链因断线取消时 SHALL 在房间日志写 `system`「讨论因页面断开而中止」**（Q2 裁决；单轮取消仍不写日志）；意外异常 `error` 不写日志；
  - 迟到 teardown 靠 `_release_round` 身份判断与 `chain.closing`/`terminal_sent` 幂等。

### Decision 9：兼容性与迁移

- 数据：旧 `room.json` 缺 `discussion_mode` → 读为 `single`；写回补字段，无迁移脚本。
- 事件：`single` 模式零新事件、`round_ended` 逐字段不变。
- `RoundResult` 新增带默认值字段：`discussion_mode: str = "single"`、`discussion_reason: str | None = None`、`chain_id: str | None = None`、`rounds: int = 0`、`rounds_started: int = 0`；**`single` 模式下这些字段保持默认值**（测试锁定，grill L11）；`termination` 新增 `stopped`（`single` 不产生）。
- **REST 语义备注**：`POST /api/team/rooms/{id}/messages` 会 await 到整条讨论结束（`web/server.py:641-661` 既有语义）；`unlimited` 房间请走房间 WS 发消息，REST 在长链下会挂到链结束（文档与前端降级文案注明，adversarial 覆盖性结论）。
- 不做：旧前端版本协商；`admin` 模式无限轮；固定 3 轮上限。

### Decision 10：测试策略（TDD，先红后绿；期望值写死）

| 层 | 用例 |
| --- | --- |
| 模型/存储 | `discussion_mode` 默认 `single`、roundtrip、旧 JSON 缺字段兼容 |
| 配置 | 三参数默认 200/600/6000、YAML 覆盖、非法值（0/负数/字符串/bool）抛 `ConfigError`；两次 orchestrator 构造不同 limits ⇒ 两条链各自快照 |
| 编排器（核心） | ① unlimited 连开 3 轮（R1 全员发言 → R2 部分 PASS → R3 全员 PASS）→ `converged`、`rounds=3`、`rounds_started=3`、system 文案精确；② 每轮每人一次、admin 先；续轮 k>1 传空 opening（开局 `@B` 的房第 2 轮仍全员）；③ single 只跑一轮，`round_ended` 整字典四键快照 + 无 `discussion_*`/`system_entry` 负向断言；④ 插话：链中进日志 + `@` 插当前轮；轮间进 `pending_mentions` 且下一轮生效后清空（重复 `@` 只置顶一次）、链结束不跨链；⑤ 停止：回合进行中请求 → 该回合跑完即结束、剩余 slot 不跑、`rounds=2/rounds_started=3`、`round_ended(stopped)` + `discussion_ended(stopped)` 各一次；⑥ 无活动链/`single` 房 `request_stop=False`；⑦ 安全阀：`max_rounds`、`max_turns`（额度在轮末恰好耗尽）、`max_seconds`（clock 注入 + slot 间）、`round_limit`（`extra_turns=0` 截断）四路各自期望值；⑧ 链中切回 `single` → `mode_changed`；⑨ 空成员 unlimited → 退化单轮、无 `discussion_*`；⑩ 取消/异常 → `round_ended(cancelled|error)` + `discussion_ended` 一次 + 状态 reset + 断线取消写 system；⑪ **可挂起 emit sink**（`on_event`/review 注入，照 `test_orchestrator.py:475-499` 先例）覆盖：首条消息 `user_message` emit 挂起时第二条消息到达（grill I1）→ 只开一条链、不抛异常；收尾 await 期间新消息 → 开新链；⑫ review sink 抛异常不中断链；⑬ 未消费消息：回合切片构造后插话且本轮 0 发言 → 强制再开一轮；安全阀耗尽按 cap reason；⑭ `chain_id` 单调、`rounds/rounds_started/turns/elapsed_seconds` 精确值、`single` 下 `RoundResult` 新字段为默认值；⑮ 链中 `delete_room` → 收尾 `completed` 且不复活日志（grill L13）；⑯ 取消后 `is_round_active is False` 且下一条消息 `queued=False`（grill I6） |
| Web 服务 | 房间 create/patch 三种非法组合；`_room_payload`/PATCH 白名单带 `discussion_mode`；`room_state` 含 `room.discussion_mode` + `discussion_round` + `discussion_reason`；REST stop 幂等 + 跨 workspace 回落；WS `stop_discussion`；事件顺序 `discussion_started → member_* → discussion_stop_requested → round_ended(stopped) → discussion_ended(stopped)`；单轮事件流与现状一致 |
| 前端 | 纯函数四件套（文案映射、`shouldShowStop`、`shouldApplyChainEvent` 守卫、`round_ended(chain_continues)` 不显示「本轮结束」）；`room_state` 重连恢复状态文案；设置下拉 disabled；停止按钮置灰/恢复；`system_entry` 追加时间线；390px 头部不溢出（浏览器用例） |
| 回归 | 全量 `uv run pytest -q`；`openspec validate --all --strict`；`uv run python scripts/check_openspec_artifacts.py --base-ref origin/master --require-base` |

## Risks

- **成本失控**：默认 `single` + 房间级开关 + 三档安全阀 + `[PASS]` 收敛提示 + 停止按钮；单轮 = N 次调用、无限链按轮线性放大；REST 长链会挂到结束（建议 WS）。
- **链收尾 await 窗口**：Decision 2 同步区纪律 + `chain_id` 守卫 + 释放后再发终态；可挂起 sink 用例锁住。
- **双终态交错**：`chain_id` + `closing` + `terminal_sent` 一次性守卫；`status_seq` 单调守卫（`group_status.js:60-65`）。
- **两档安全阀不独立**：`max_turns` 绑定上通常先到、但 reason 多为 `round_limit` 吸收（Decision 6）。
- **规格破坏面**：三份当前规格 MODIFIED/ADDED；`configuration` 为 ADDED；收尾须 `current_spec_synced` 事件。
- **断线中止**：按 Q2 写 system 说明；服务端持有方案不在范围。

## Document Impact

- `openspec/specs/multi-agent-collaboration/spec.md`：MODIFIED「房间级互斥与轮次终止」「房间应答模式」；ADDED「讨论链自动续轮与收敛」。
- `openspec/specs/web-ui/spec.md`：MODIFIED「人设与房间的管理入口」；ADDED「群聊讨论链状态与停止讨论控件」。
- `openspec/specs/configuration/spec.md`：ADDED「群聊讨论链安全阀可配置」。
- `docs/architecture.md` 群聊小节：终止口径改「单轮 / 讨论链」+ 停止 + 安全阀 + 配置需重启；`CONTEXT.md` 补「讨论链」；`docs/interview-script/` 相关表述检查。
- `asterwynd.example.yaml`：`team:` 配置节示例。
- `docs/openspec-change-backlog.md`：收尾移除本条目。

## User Rulings (2026-10-24，用户停轮裁决)

- **Q1（未消费的用户消息）**：采用推荐口径——存在未消费用户消息时不得以 `converged` 结束；安全阀仍有余量则强制再开一轮，否则按对应安全阀 reason 结束（消息保留在房间日志）。
- **Q2（链生命周期与 WS）**：保持现状——房间 WS 断开即取消链；链因断线中止时在房间日志写 `system`「讨论因页面断开而中止」（单轮取消仍不写日志）。
- **Q3（single 是否可停止）**：收紧——单轮不提供「停止讨论」、`request_stop` 返回 `False`、不产生 `stopped`；单轮保持三出口与零事件变化。
- **Q4（墙钟检查粒度）**：每个 slot 之间也检查墙钟（不打断在跑回合，仅不再开新回合），最坏越界 ≤ 一个 `turn_timeout`。

## Pre-Implementation Review

- grill（独立零记忆）：`reviews/grill-design.md` —— 12 条 Confirmed Decisions、4 条 Open Question（已由用户裁决）、22 条 Design Corrections（C1–C22，已全部回写）。
- 设计对抗闭环：`reviews/grill-adversarial.md` —— r1 = CHANGES_REQUESTED（批次 I 12 条：1 high + 11 medium）→ r2 = CHANGES_REQUESTED（I10 delta 两处，1 medium）→ r3 = **PASS**（无新 medium+；N11/N13/N14 low、N15/N16 nit 登记）。**闭环出口 PASS，允许进入实现。** 逐轮证据在 `reviews/rounds/`。
