# Design: 群聊 everyone 模式无限讨论链（讨论链 + 停止按钮 + 安全阀）

## Context

当前群聊的轮次语义全部钉死在「一次用户消息 = 一轮」：

| 事实 | 证据 |
| --- | --- |
| 唯一开轮入口是用户消息 | `agent/team/orchestrator.py:315-341` `submit_user_message`；`_rounds` 空闲才开轮 |
| 一轮 = 走完 slot 序列即结束 | `:347-407` `_run_round`；`:428-434` `_drive` |
| `everyone` 无 `@` 时开局 slot = 全体成员各一次 | `:153-182` `opening_slots` |
| 房间互斥只覆盖单轮 | `:309-310` `is_round_active`；`web/server.py:729-738` 轮次在后台 task 里跑 |
| 规格明确「用户再发言前不得自行开新一轮」 | `openspec/specs/multi-agent-collaboration/spec.md:1304,1311` |
| 首版刻意不允许成员自开轮次 | `openspec/changes/archive/2026-10-13-web-agent-group-chat/design.md:131`（参照实现允许、上限 3） |

本轮用户诉求：保留「单轮」形态，另加「无限轮」形态——成员之间自动连续多轮讨论，直到**某轮全员静默**自然收敛、或用户点**停止讨论**；安全阀参数可配置（默认 200 轮 / 600 回合 / 6000 秒，均为用户确认的 10 倍档）；仅 `everyone` 模式生效。

## Goals / Non-Goals

**Goals**

- 房间级 `discussion_mode`（`single` 默认 / `unlimited`），仅 `everyone` 合法；单轮模式行为与事件**完全不变**。
- 讨论链：`unlimited` 下一轮正常结束后自动续下一轮；每成员每轮各得一次机会、可 `[PASS]`；**0 条成员发言即收敛结束**。
- 「停止讨论」：优雅停止（当前成员回合跑完后结束当前轮、不再续轮），幂等；REST + WS 双通道。
- 安全阀：轮数 / 成员回合 / 墙钟三档，来自 `team:` 配置节；任一到达即停并写 `system`。
- 用户插话不打断讨论链；`@` 语义沿用（进日志 + 插当前位次后）。
- 事件与状态可区分「一轮结束」与「整条讨论结束」。

**Non-Goals**

- 不做 `admin` 模式的无限轮（`unlimited` + `admin` 为非法配置）。
- 不做成员真正并发发言（仍串行，沿用现状）。
- 不做"成员自行决定要不要开下一轮"的二次 LLM 判定（用全员静默 + 安全阀 + 用户停止三出口，不额外付费一次判定调用）。
- 不改成员会话 / 记忆 review / 上下文切片游标语义；不改单轮模式的任何事件与返回值。
- 不做跨房间讨论、不做动态成员加入讨论链（讨论链内成员被移出仍按现有 `left` 跳过）。
- 不引入新依赖、不改协议层以外的传输（房间 WS 仍是唯一实时通道）。

## Decision 1：`Room.discussion_mode` 的取值、校验与持久化

- 模型：`Room.discussion_mode: str = "single"`；取值集合 `("single", "unlimited")`；`to_dict`/`from_dict` 成对写入；**旧房间 JSON 缺字段 → `single`**（向后兼容）。
- 有效性：`unlimited` 仅在 `reply_mode == "everyone"` 时合法。
  - 创建/更新房间时按**合并后的生效值**校验：若 `discussion_mode == "unlimited"` 且 `reply_mode != "everyone"` → REST `400 {"error": "discussion_mode_requires_everyone"}`。
  - 把 `reply_mode` 从 `everyone` 改为 `admin` 时若 `discussion_mode` 仍为 `unlimited` 且本次未同时给出 `single` → 同样 400（不静默改写用户数据）。
  - 两个字段本身非法值（不在枚举内）→ 400 `{"error": "invalid_discussion_mode"}`（与既有 `invalid_reply_mode` 同形）。
- 理由：`admin` 模式下"无限轮"= 单个 admin 反复自答，无讨论价值且纯增成本；用配置非法直接拒绝，比"静默忽略/自动回退"更可测、更不易误解。

## Decision 2：讨论链（discussion chain）与房间互斥

- `_rounds: dict[room_id, _ChainState]`：房间认领从「一轮」提升为「一条讨论链」，链内轮与轮之间**不释放**认领。
  - 因此 `is_round_active(room_id)` 语义扩展为「该房间有进行中的讨论/轮次」，`room_state.round_active` 保持同名同义。
- `_ChainState` 字段（钉死）：
  - `room_id`；`discussion_mode`（链启动时快照）；`started_at`（`time.monotonic`，构造函数可注入 `clock` 便于测试）；
  - `rounds: list[_RoundState]`；`turns: int`（链内成员回合累计）；`stop_requested: bool`；
  - `current: _RoundState | None`（当前轮；轮间窗口为 `None` 或已关闭轮）；
  - `pending_mentions: list[str]`（轮间窗口到达的用户行首 `@`，应用到下一轮 slot 顺序）；
  - `limits`（链启动时从 `TeamConfig` 快照的 `max_rounds/max_turns/max_seconds`）。
- 用户消息在链进行中到达（`submit_user_message` 的 active 分支）：
  - 追加房间日志（现有行为）；
  - 行首 `@` 追加到 `current` 轮的 slot（沿用 `_append_called_slots`，用户口径 `leading_only=True`）；
  - 若 `current is None` 或该轮已关闭（轮间窗口），`@` 记入 `chain.pending_mentions`，由下一轮开局 slot 应用（去重、不重复插入）；
  - `SHALL NOT` 改变链的安全阀基数（上限是链级预算，链启动时固定），`SHALL NOT` 打断续轮。
- 单轮模式同样走"链"结构（链只含 1 轮），以保证只有一套房间互斥/取消逻辑；但事件与返回值与现状一致（见 Decision 7）。

## Decision 3：轮次推进与续轮判定

- 链循环：`_run_discussion(room, opening_text)`：
  1. 在任何 `await` 之前认领 `self._rounds[room.id] = chain`（沿用现有互斥论证：查—建无 await 点）；
  2. 第 1 轮：append 用户条目（`log.append_user`），`start_seq = entry.seq`；第 k>1 轮：append `system` 条目 `讨论继续（第 k 轮）`，`start_seq = entry.seq`；
  3. 每轮 slot = `opening_slots(room, opening_text_or_empty, roster, main_bot_ids)`，再应用 `chain.pending_mentions`（把被点名者按其顺序插到队首、去重、非本群/自己忽略）；
  4. 每轮预算 = `len(slots) + extra_turns + (admin ? admin_extra_turns : 0)`，但**再与链剩余回合额度取 min**（`chain.limits.max_turns - chain.turns`）；剩余 ≤ 0 → 不开始该轮，链以 `max_turns` 结束；
  5. `await self._drive(chain, state)`；
  6. 轮终止判定：`stop_requested` → `stopped`；`turns >= limit` 且仍有未走 slot → `limit`（沿用 `system` 文案「本轮因达上限结束」）；0 发言且全部失败 → `all_failed`；否则 `completed`；
  7. 追加 `system`（仅 limit 时）、`chain.rounds.append(state)`、`on_round_end` review 调度（沿用：每轮一次，不因续轮改变）；
  8. **续轮判定**（`can_continue`）全部满足才续：
     - 房间当前 `discussion_mode == "unlimited"` 且 `reply_mode == "everyone"`（实时读 room：链中改回 `single` → 本轮后结束，reason `mode_changed`）；
     - 本轮 `termination == "completed"` 且 `state.posts` 非空（有人真的发言）；
     - `not chain.stop_requested`；
     - 房间仍存在且有 ≥1 成员；
     - `len(chain.rounds) < max_rounds`、`chain.turns < max_turns`、`elapsed < max_seconds`；
  9. 每轮结束都发 `round_ended`（`chain_continues` 标记是否续轮）；不续则退出循环并收尾。
- 链结束原因枚举（钉死，`discussion_ended.reason`）：`converged`（最后一轮 0 发言、0 失败）/ `all_failed` / `stopped` / `max_rounds` / `max_turns` / `max_seconds` / `mode_changed` / `cancelled` / `error` / `single_round`（单轮模式；事件仅 unlimited 发，见 Decision 7）。
- 链结束写 `system`（仅 `unlimited`）：`converged` →「讨论已收敛（本轮全员静默）」；`stopped` →「讨论已由用户停止」；`all_failed` →「讨论已中止（本轮全员失败）」；`max_*` →「讨论达安全上限结束」；`mode_changed` →「讨论模式已切换为单轮」；`cancelled` / `error` 不写日志（沿用取消 teardown 只发事件口径）。

## Decision 4：全员静默 = 收敛（不额外调用模型判定）

- 一轮内 `state.posts == []` 且 `state.failures == 0` → 该轮无人发言（全部 `[PASS]`/空产出）→ 链以 `converged` 结束。
- 不做"让 admin/某个成员判断是否继续"的额外 LLM 调用：多一次调用就多一份成本与延迟，且收敛信号本身已由 `[PASS]` 提供（`ROOM_REPLY_INSTRUCTION` 已要求"没有新内容回 `[PASS]`"，`:60-64`）。
- 提示词增强（仅 `unlimited` 的成员回合）：在现有成员 prompt 末尾追加两条固定句：
  - `Round {k} of a continuous discussion; every member speaks at most once per round.`
  - `If the discussion has converged or you have nothing new to add, reply [PASS] — do not repeat points already made; do not speak just to fill the round.`
  - 措辞要求：不改变 `ROOM_REPLY_INSTRUCTION` 的哨兵契约，只在它之前追加；`single` 模式 prompt 逐字节不变（测试锁定）。

## Decision 5：停止讨论 = 优雅停止（新增第四出口）

- 触发：
  - REST `POST /api/team/rooms/{room_id}/discussion/stop` → `{"stopping": bool, "room_id": ...}`；房间不存在 404；workspace 非法 403（沿用其他房间端点口径）。
  - 房间 WS 消息 `{"type": "stop_discussion"}`（前端主路径）。
  - 两者都调 `TeamService.stop_discussion(ws_path, room_id)` → `RoomOrchestrator.request_stop(room_id)`。
- `request_stop`：房间无活动链 → 返回 `False`（幂等 no-op，**不报错**）；否则置 `chain.stop_requested = True`，发 `discussion_stop_requested` 事件，返回 `True`。重复调用不重复发事件。
- 生效点（**不打断正在跑的成员回合**，避免撕裂 run/工具状态）：
  - `_drive` 每跑完一个成员回合后检查 → 直接跳出，**跳过本轮剩余 slot**；
  - 轮间续轮判定前检查；
  - 两处都命中后：轮 `termination = "stopped"`，追加 `system`「讨论已由用户停止」，链 reason `stopped`。
- 停止后状态：成员状态表重置为 idle（沿用 `_reset_room_statuses`）；房间认领释放，用户下一条消息开新链。
- 单轮模式下 `request_stop`：无"链"可续，但若当前轮正在跑，语义 = 本轮在当前成员回合后结束（`termination="stopped"`）；无活动轮 → `False`。

## Decision 6：安全阀参数（`team:` 配置节，链启动快照）

- `TeamConfig` 新增（`agent/config.py:273-291`）：
  - `discussion_max_rounds: int = 200`
  - `discussion_max_turns: int = 600`
  - `discussion_max_seconds: float = 6000.0`
- 解析：`_parse_team_config`（`:1677-1712`）校验为正整数/正数，非法抛 `ConfigError`（与既有 `turn_timeout_seconds` 同形）；缺省取上述值。
- 注入：`web/team.py:200-209` 构造 `RoomOrchestrator` 时传入；编排器以构造参数接收（默认值与 `TeamConfig` 一致，便于单测直接构造）。
- 语义：链启动时**快照**三值（链内改配置不影响在跑链；下一条链生效，记录在文档与测试）。判定点：
  - 续轮前：`rounds >= max_rounds` / `turns >= max_turns` / `elapsed >= max_seconds` → 链结束（对应 reason）；
  - 轮内回合：`round_limit = min(轮预算, max_turns - turns)`，达到即以 `limit` 收尾；
  - 墙钟：只在轮间判定（不中断正在跑的成员回合）。**已知边界**：单成员长回合可能跨过墙钟，链会在该轮结束后才停；这是有意的（不打断 run）。
- 单轮模式不使用这三个参数（单轮预算沿用现有 4/4/2/4 参数）。
- `asterwynd.example.yaml` 增加 `team:` 节（含 `turn_timeout_seconds`、既有预算参数与三个新参数的中文注释示例）。

## Decision 7：事件契约与前端状态（单轮模式零变化）

- **`unlimited` 模式新增事件**（`RoomEventBus` 转发，见 `web/server.py:663-750`）：
  - `discussion_started {room_id, discussion_mode, members:[persona_id], round_index: 1, limits:{max_rounds,max_turns,max_seconds}}`：链启动，任何成员回合之前。
  - `discussion_stop_requested {room_id}`：`request_stop` 首次生效请求时。
  - `discussion_ended {room_id, reason, rounds, turns, elapsed_seconds, status_seq}`：链结束（唯一权威终态）。
  - `round_ended` 扩展字段：`round_index`（链内 1-based）、`chain_continues: bool`；`termination` 枚举新增 `stopped`（既有 `completed/limit/all_failed` 不变）。
- **`single` 模式**：不发上述三个新事件，`round_ended` 不携带新字段（或携带 `chain_continues=false`、`round_index=1`？——**决定：不携带**，保持旧前端与旧测试逐字节兼容；实现上用 `if chain.discussion_mode == "unlimited"` 分支）。
- `room_state` 快照新增：`discussion_active: bool`（= 有活动链）、`discussion_round: int`（当前链已完成的轮数；无链为 0）、`discussion_reason: str | null`（最近一次链结束原因，仅本进程内存；重启后为 null）。`round_active` 保留原字段与语义（有进行中的讨论/轮次）。
- 前端状态文案（`group.js` 现有 `setStatus` 机制）：
  - `discussion_started` / 续轮 →「讨论中（第 k 轮）」；
  - `discussion_ended` → `converged`「讨论已收敛」/ `stopped`「讨论已停止」/ `max_rounds|max_turns|max_seconds`「讨论达安全上限」/ `all_failed`「讨论已中止（全员失败）」/ `mode_changed`「讨论模式已切换为单轮」/ `cancelled`「讨论已中止」/ `error`「讨论异常结束」；
  - `round_ended` 且 `chain_continues=true` → **不**显示"本轮结束"（避免轮间闪错状态）；`chain_continues=false` 且 unlimited → 由 `discussion_ended` 接管；
  - `single` 模式沿用现有「本轮结束 / 本轮因达上限结束 / 本轮已中止 / 本轮异常结束」文案。
- 停止按钮：`room_state.discussion_active` 或收到 `discussion_started` 后可见；点击发 WS `stop_discussion`（WS 未连通时降级 REST），点击后置灰「正在停止…」，收到 `discussion_stop_requested` 保持置灰，`discussion_ended` 后恢复。

## Decision 8：取消 / 异常 teardown 扩展到链

- 现状：轮 task 被 cancel（房间 WS 断开 → `web/server.py:748-750`）时 `_run_round` 捕获 `CancelledError` → `_reset_room_statuses` + `_schedule_teardown` 尽力发 `round_ended(cancelled)`（`orchestrator.py:408-422`）。
- 新语义：链内取消 = 结束当前轮 + 结束链：`round_ended(termination="cancelled", chain_continues=false)` + `discussion_ended(reason="cancelled", status_seq=...)` 由同一个后台 teardown task 尽力发出；不写房间日志；不产生 `RoundResult`；状态表 reset 先于释放认领（沿用现有次序）。
- 意外异常同理：`reason="error"`；异常仍向上抛（保持调用方可见），teardown 后台尽力发事件。
- 幂等：链已结束/已被替换时，迟到 teardown 只发事件不改状态（沿用 `_schedule_teardown` 的身份判断）。
- WS 断开即取消仍是既有语义（本 change 不改）；「停止讨论」与"断线取消"的区别写进文档：前者不打断当前成员回合、写日志；后者立即 teardown、不写日志。

## Decision 9：兼容性与迁移

- 数据：旧 `room.json` 缺 `discussion_mode` → 读为 `single`；写回时补字段（无需迁移脚本）。
- 事件：仅 `unlimited` 新增事件；`single` 模式事件与 payload 与现状一致（旧前端可继续工作）。`round_ended` 的 `stopped` 只可能在用户主动停止时出现（单轮/无限都可能有）。
- RETURN：`RoundResult` 新增 `discussion_mode: str = "single"`、`discussion_reason: str | None = None`、`rounds: int = 1`（默认值保证既有构造点兼容）；`termination` 新增 `stopped`。
- 既有测试：单轮相关断言不变；仅当测试构造 `RoundResult` 面向 `unlimited` 时才用新字段。
- 不做：旧前端版本协商；`admin` 模式无限轮；把 `ROOM_BOT_ROUNDS=3` 作为上限（用户要求"直到收敛/手动停止"，固定 3 轮不满足）。

## Decision 10：测试策略（TDD，先红后绿）

| 层 | 用例（每条先红后绿） |
| --- | --- |
| 模型/存储 | `Room.discussion_mode` 默认 `single`、roundtrip、旧 JSON 缺字段兼容；非法值读取回落 |
| 配置 | `TeamConfig` 三参数默认值（200/600/6000）、YAML 覆盖、非法值抛 `ConfigError`、`asterwynd.yaml` 解析不回归 |
| 编排器（核心） | ① `unlimited` 连开 ≥3 轮（FakeRunner 脚本第 1 轮全员发言、第 2 轮部分 PASS、第 3 轮全员 PASS → `converged`）；② 每轮每人各一次、admin 先；③ 续轮自动开轮且无需用户消息；④ `single` 模式仍只跑一轮且事件/payload 与现状完全一致（快照断言）；⑤ 用户插话：链中发消息 → 进日志、`@` 插当前轮、链继续；轮间窗口 → `pending_mentions` 应用下一轮；⑥ 停止：在成员回合进行中请求 → 当前回合完成后立即结束（剩余 slot 不跑）、`round_ended(stopped)` + `discussion_ended(stopped)`、写 system；⑦ 停止幂等（重复请求、无活动链 no-op）；⑧ 安全阀三档（`max_rounds` 用小值 + 每轮有人发言；`max_turns` 用 `round_limit` 截断；`max_seconds` 注入 clock 跨阈值）；⑨ 链中把 `discussion_mode` 改回 `single` → 本轮后 `mode_changed`；⑩ 取消（`CancelledError`）→ `round_ended(cancelled)` + `discussion_ended(cancelled)` + 状态 reset；⑪ 链结束释放房间认领（下一条消息开新链）、`round_active` 语义；⑫ review sink 每轮 `on_round_end` 仍被调用 |
| Web 服务 | 房间 create/patch：`unlimited`+`admin` → 400 `discussion_mode_requires_everyone`；改 reply_mode 冲突 → 400；非法值 → 400 `invalid_discussion_mode`；`room_state` 含 `discussion_mode/discussion_active/discussion_round`；REST stop 幂等（无链 `stopping=false`、有链 `true`）；WS `stop_discussion` 触发；WS 事件流含 `discussion_started/stop_requested/ended` 且顺序正确；单轮房间事件流与现状一致 |
| 前端 | 设置下拉仅 everyone 时可选 unlimited；提交字段；停止按钮可见性/置灰/恢复；状态文案映射全覆盖（JS 单测 + 现有浏览器测试模式） |
| 回归 | 全量 `uv run pytest -q`；`openspec validate --all --strict`；`uv run python scripts/check_openspec_artifacts.py --base-ref origin/master --require-base` |

## Risks

- **成本失控**：无限链本质是持续调用模型。缓解：默认 `single`、房间级开关、三档安全阀可配、`[PASS]` 收敛提示、停止按钮；文档明确单轮成本 = N 次调用、无限链按轮线性放大。
- **停止/取消竞态**：停止请求与成员回合完成、WS 断线取消、链间窗口三者竞争。缓解：状态机只在明确检查点读 `stop_requested`；取消走身份判断的 teardown；测试用 gate 精确覆盖回合结束瞬间。
- **事件与 UI 状态错乱**：`round_ended` 与 `discussion_ended` 双重终态。缓解：`chain_continues` 权威决定"是否整链结束"；`discussion_ended` 为唯一链终态；`status_seq` 复用现有单调守卫。
- **规格破坏面**：三份当前规格需要 MODIFIED；收尾须 `current_spec_synced` 事件与 strict validate。
- **配置放开过高**：默认 200/600/6000 由用户拍板（10 倍档），若实际使用中出现长链成本问题，只需调低 YAML 参数，无需改代码。

## Document Impact

- `openspec/specs/multi-agent-collaboration/spec.md`：「房间级互斥与轮次终止」重写 + 「房间应答模式」扩展 + 新增「讨论链自动续轮与收敛」Requirement。
- `openspec/specs/web-ui/spec.md`：房间设置新增讨论模式、停止按钮、讨论状态文案、WS 事件契约扩展。
- `openspec/specs/configuration/spec.md`：`team:` 运行参数新增三项。
- `docs/architecture.md` 群聊小节：终止口径从「仅用户开轮」改为「单轮 / 讨论链」，补停止与安全阀说明。
- `CONTEXT.md` 词汇表：新增「讨论链」词条。
- `asterwynd.example.yaml`：`team:` 配置节示例。
- 面试讲稿建议性检查：`docs/interview-script/questions/Q08-multi-agent.md` 如有"群聊终止口径"表述需同步（收尾阶段检查）。

## Pre-Implementation Review

（待 grill 与设计对抗闭环后回填：grill 决策、修正项、对抗轮次、出口。）
