# Building Review R1: web-agent-group-member-status

## Reviewer

- run id: building-review-agent-paseo
- 时间: 2026-10-20
- 零记忆: 是（reviewer ≠ author；只读代码/测试/规格，不继承开发上下文，未写实现或测试代码）
- 审阅范围: `7b6994d` vs `48d25f0`（`git diff origin/master...HEAD`），含设计提交 `557bfdd`
- **工作区状态注记**：review 开始时工作区 clean；review 期间 `agent/team/orchestrator.py`
  出现一处**未提交**改动（`status_snapshot` 增加按 `room.members` 过滤，见 L1），文件
  mtime 12:10:23，晚于实现提交 12:09:40。下文所有 `文件:行号` 除 L1 外均指 HEAD
  (`7b6994d`)；验证命令运行在含该未提交改动的树上（该改动只影响快照过滤，不影响测试结论）。

## 任务逐项验证

| 任务 | 判定 | 证据 |
|---|---|---|
| 0.1–0.5 设计门 | 通过 | `reviews/grill-design.md`（8 条 Confirmed Decisions、Q1/Q2/Q3 `User Confirmation`）；`reviews/grill-adversarial.md`（R1–R6，R6 PASS）；`design.md:901-941` |
| 1.1 reducer 单测 | 通过 | `tests/agent/team/test_member_status.py:29-155` 覆盖优先级、按 id 记账、同名工具、`iteration_started` 清理、显式降级、无变化返回 None |
| 1.2 编排器测试 | **部分** | 正常/空产出/建会话失败/取消/意外异常/只在变化时发/跨轮见 `test_orchestrator.py:655-796`；**缺 resume 回合测试**（grep `resume` 零命中）；"无重复空表"无显式断言 |
| 1.2.1 跨轮迟到终态 | 通过（变异验证不可复核） | `test_orchestrator.py:763-796`（review gate 阻塞 R1 终态）+ `test_group_status_js.py:97-101`（JS 丢弃旧终态） |
| 1.2.2 N1/X1 收尾窗口 | **未完成** | tasks 要求 gate 阻塞 `_flush_status_emits`、断言 M3 queued 进 R2；测试中无 `_flush_status_emits` 引用，`test_orchestrator.py:798-824` 只覆盖"取消已释放认领的轮次"，不覆盖 flush 窗口内新消息的行为 |
| 1.3 `on_progress` 契约 | 通过（"不传不变"为隐式覆盖） | `FakeRunner` 签名 `test_orchestrator.py:38-53`；回调异常 `test_group_chat_team.py:888-904` |
| 1.3.1 web 层映射（T1） | 通过 | `test_group_chat_team.py:848-886`：真实 `WebSessionRunner` + `ScriptedLLM(stream=True)` + 工具，断言 2 次 delta / 2 次 stream_complete / tool id+name |
| 1.4 WS/集成测试 | **部分** | 快照 `test_group_chat_server.py:289-330`、握手顺序/失败 `:334-384` 已在；**缺** WS 层 tool 状态断言、非流式无 typing、双标签页断线 `round_ended(cancelled)`；"12 条上限改 64"未做（`:246` 仍是 `for _ in range(12)`） |
| 1.5 JS 纯函数测试 | 通过 | `test_group_status_js.py:60-160` |
| 1.6 浏览器测试 | **部分** | 桌面/390px 主路径、反定时器、公告、新一轮清提示、纵向滚动不变、横条自动滚入见 `test_group_status_browser.py:133-313`；**缺** 迟到 limit 重拉、发送失败提示清除、断线 stale 断言、presence 横向滚动保持、reduced-motion、桌面三列几何（详见 M3） |
| 1.7 红绿/变异记录 | 不可机械复核 | 无产物；实现与测试存在，无法从仓库验证变异过程 |
| 2.1–2.10 后端状态模型 | 通过 | `agent/team/member_status.py:51-157`；`orchestrator.py:294-300,372-435,566-724`；`runner.py:63-80`；`session.py:458-520,2166-2225` |
| 3.1–3.3 房间 WS/快照 | 通过 | `web/server.py:104-132,682-752` |
| 4.1–4.3 前端纯函数/DOM/分发 | 通过 | `group_status.js:1-171`；`group.js:318-449`；`index.html:180-241` |
| 4.4 CSS | **部分** | 桌面 208px/1000px 抽屉/≤720 Q1 56px 均在 `style.css:2186-2345`；**无** `prefers-reduced-motion` 规则（当前也没有状态动效，故行为上为空满足，但 task 声称的项未落地） |
| 4.5–4.8 移动端/脚本/可访问性/Q2 | 通过 | `style.css:2280-2345`；`index.html:238-240`；`group.js:309-317,470-530`；失败即回 idle、`member_failed.name` 均在 |
| 5.1–5.3 规格 | 通过 | 两份 delta 与 current（`openspec/specs/.../spec.md:1336,1407,1622`）；strict validate 29/29 |
| 5.4 backlog | 未勾合理 | backlog 已登记（`docs/openspec-change-backlog.md:120-122`）+ `workflow-events.jsonl` seq 2/3；剩余动作是归档前移除，未勾与文件头结算次序一致 |
| 5.5 文档影响 | 通过 | `docs/architecture.md:110-115`、`Q08-multi-agent.md:81` |
| 6.1–6.6 验证 | 通过 | 本 reviewer 重跑：目标测试 **252 passed**；OpenSpec **29/29**；瘦 checker **EXIT=0**；benchmark smoke **EXIT=0**；全量结果与 `/tmp/pytest-full2.log`（4430 passed / 3 known failed / 9 skipped）一致 |
| 7.x / 8.x | 进行中 / post-merge | 本轮 = 7.1；8.x 标注 `(post-merge)` 合理 |

## Findings

### M1（severity: medium）tasks 1.2.2 的 N1 收尾窗口回归测试缺失
- **问题**: tasks 1.2.2 明确要求用一次性 gate 阻塞 `_flush_status_emits`，在 R1 已
  reset+pop、flush 未完成时提交 M2，断言 R2 开启且 seq 更高，并断言随后的 M3 被 queued
  进 R2 而非开启 R3。实现测试中没有任何 `_flush_status_emits` 的门控；现有
  `test_cross_round_terminal_has_lower_seq_than_new_round`（`test_orchestrator.py:763-796`）
  阻塞的是 `_GatedReview`（review 阶段），此时 round-end flush 早已完成，覆盖不到目标窗口。
- **失败场景**: 若后续有人把 `_release_round` 移回 `_flush_status_emits` 之后（或删掉
  `_release_round` 的 `is state` 身份判断），收尾窗口内到达的用户消息会被 append 进已结束
  轮次的日志（`submit_user_message` 看到 `_rounds` 仍非空），表现为「用户发的新消息被吞、
  下一轮不启动」——现有测试全绿，无法发现。
- **证据**: `tasks.md:46-51`；`agent/team/orchestrator.py:383-385`（reset → release → flush
  的正确顺序）；`test_orchestrator.py:763-824`（无 flush gate、无 M3 queued 断言）。
  注：本次 review 用只读临时脚本按 tasks 描述做了等价验证，当前实现行为**正确**
  （R1 flush 被 gate 时 M2 开 R2、M3 queued 进 R2、放行后 R2 仍 active）——因此这是
  **回归测试缺口**，不是实现 bug。
- **建议修法**: 新增 `test_flush_window_message_starts_new_round_and_m3_queues`：包装
  `orch._flush_status_emits`，在 `not orch.is_round_active(room)` 时进入 gate（即 round-end
  flush），提交 M2 后断言 `round_active is True`、seq 高于 R1 旧终态，再提交 M3 断言
  `queued is True`；放行 flush 后断言 R2 仍 active。再做一次变异验证（把 pop 移回 flush 后 /
  去掉身份判断 → 必红）。

### M2（severity: medium）tasks 1.4 与 1.2 的 WS/生命周期/resume 断言被勾为完成但不存在
- **问题**: 以下 task 明确列出的确定性测试在仓库中不存在：
  1. WS 层「流式 ScriptedLLM + 一次工具调用 → 事件流中出现 `tool` + 工具名，工具结束回落」
     （`tasks.md:62-68`；`test_group_chat_server.py` 的回合测试仍只用默认文本 LLM，`member_status`
     事件本身在 WS 层从未被断言）；
  2. 非流式 `ScriptedLLM(stream=False)` 不产生 `typing`（`tasks.md:67`；grep 无命中）；
  3. 双标签页 + 关闭发起连接 → 另一连接收到 `round_ended(cancelled)` 或重连快照为 idle
     （`tasks.md:73`；这正是 spec「取消/断线 teardown 对其他标签页可见」场景）；
  4. `ProgressObserver` 生命周期「连续两次 run 只看到一组信号」（`design.md:211-220`
     的硬要求；只测了「回调抛异常不影响 turn」）；
  5. resume 回合「首个 thinking 来自 `iteration_started`、不依赖 `run_started`」的编排器
     测试（`tasks.md:39-41`；`test_orchestrator.py` 的 progress 脚本只有含 `run_started`
     的正常路径）。
- **失败场景**: 若 `ProgressObserver` 的挂/摘身份过滤被改坏，第二次 run 会重复收到上一 run
  的信号（状态乱跳）；若房间 WS 的 `finally` 不再 cancel rounds 或取消逻辑回归，发起标签页
  关闭后其它标签页会永久停在忙——两类问题都不会让现有测试变红。WS 层 `member_status` 广播
  接线（orchestrator `on_event` → `room_bus` → WS）目前也没有端到端断言。
- **证据**: `tasks.md:39-41,62-75`；`test_group_chat_server.py:232-253`（无 member_status
  断言、12 条上限未改）；`test_group_chat_team.py:848-904`（仅 runner 层）；`web/session.py:2219-2225`
  （observer 摘除逻辑无回归测试）。
- **建议修法**: 补 4–5 个测试（可用 FakeRunner/门控 LLM 保证确定性）：
  (a) 连续两次 `runner.run(..., on_progress=collect)`，第二次 signals 不包含前一次重复；
  (b) 非流式 run 断言 kinds 无 `assistant_delta`；
  (c) 真实 WS：发起连接关闭后，另一连接在超时内收到 `round_ended(cancelled)`（或重连
  `room_state.round_active=false` 且 `member_statuses=[]`）；
  (d) 用带工具调用的流式 ScriptedLLM 在 WS 层断言曾出现 `phase="tool"` 且 `tools=["Bash"]`；
  (e) resume 路径 progress 脚本不含 `run_started`，断言首个非 running 相位是 `thinking`。
  同时把 `test_room_state_then_round_events` 的 `for _ in range(12)` 改为收集到
  `round_ended` 的安全上限（如 64），避免新增状态事件后偶发超限。

### M3（severity: medium）tasks 1.6 与收口报告 L-b/L-d/L-g 声称的浏览器断言缺失
- **问题**: `grill-adversarial.md:47-52` 把以下项登记为「R6 后已收敛」，tasks 1.6
  （`tasks.md:81-90`）也勾为完成，但 `test_group_status_browser.py` 只有两个测试
  （`:133-217`、`:221-313`），未覆盖：
  - 迟到的 `round_ended(limit)`（`applied=false`）仍触发时间线重拉（L-b）；
  - 发送失败 `op` 提示在下一次成功发送/连接成功后清除（L-d）；
  - 断线后 presence 行带 `stale` class / 过期标记（L-g）；
  - presence 在时间线重绘后保持横向 `scrollLeft`；
  - `prefers-reduced-motion`；
  - 桌面 1200px 三列几何（presence 宽 208、时间线 > 400px）。
- **失败场景**: `round_ended(limit)` 的重拉条件或 `activeRoom` 校验回归时，达上限的 system
  条目不会实时出现；`setStatus(kind)` 的生命周期回归会让「发送失败」永久残留或把「连接断开」
  误清；断线 stale 视觉与横向滚动位置回归均不可见。这些正是设计对抗轮里被当作 medium/low
  专门补的验收项。
- **证据**: `test_group_status_browser.py:133-313` 只有桌面主路径与移动端 Q1 几何；
  `web/static/group.js:434-446`（limit 重拉）、`:585-600`（op 提示）、`:478-482`（stale class）
  均无对应断言。
- **建议修法**: 扩展现有两个浏览器测试或新增一个：push `round_ended(limit)` 后断言
  `#group-room-timeline` 出现 system 条目；模拟 `sendRoomMessage` 失败后成功发送断言
  `#group-room-status` 清空；断开 WS（或关闭服务端连接）断言 `.group-presence-row.stale`；
  在时间线重绘前后断言 `#group-room-presence.scrollLeft` 不变；在 1200px 断言 presence
  与 timeline 的 `getBoundingClientRect`；reduced-motion 若确无动效，则删除 tasks 1.6/4.4
  中的对应声称并写明「当前无状态动效，规则为空满足」。

### L1（severity: low）工作区存在未提交的实现改动，且 HEAD 的快照未按房间成员过滤
- **问题**: `status_snapshot` 在 HEAD（`7b6994d`）返回房间状态表里所有非 idle 成员；
  设计 Decision 6（`design.md:457`）要求「只包含当前 `room.members` 中的成员，其他条目过滤」。
  review 期间工作区出现未提交修复（按 `room.members` 过滤），但未进入实现提交、也无测试。
- **失败场景**: 成员在忙时被移出房间，第二标签页/重连的 `room_state.member_statuses` 会
  含幽灵成员；客户端按当前 `state.members` 渲染会隐藏它，但其他消费者（测试/未来 UI）会读到
  不一致快照。未提交改动还会让 `gate / check` 的 manifest hash 与 reviewer 审到的树不一致。
- **证据**: `git status`（`M agent/team/orchestrator.py`）；HEAD `agent/team/orchestrator.py:662-670`
  vs 工作区 diff；`design.md:457`。
- **建议修法**: 在下一轮修复中提交该过滤改动，并加一个「成员中途移出后快照不含该成员」的
  编排器测试；再重建 witnessloop manifest。

### L2（severity: low）迟到 limit 重拉整体替换时间线，可能丢掉重拉期间到达的新事件
- **问题**: `round_ended(limit)` 的异步重拉 `.then` 直接 `state.timeline = body.timeline || []`
  （`web/static/group.js:438-443`）。设计 Decision 7（`design.md:514-516`）要求时间线追加
  按 `seq` 幂等，以覆盖「重拉与随后到达的事件」竞态。
- **失败场景**: 用户在达上限结束提示出现后立刻发新消息；`user_message` WS 事件先被追加，
  随后重拉响应（快照早于该消息）整体替换时间线，用户自己的新消息从视图消失，直到下一次
  重拉/重连。
- **证据**: `web/static/group.js:441`；`design.md:514-516`。
- **建议修法**: 重拉响应按 seq 合并（保留本地 `state.timeline` 中 seq 不在响应里的较新条目，
  或只 append 响应中缺失的条目），并加浏览器或 node 层回归测试。

### L3（severity: low）`tool_finished` 的 name 兜底分支不可达，注释与实现不符
- **问题**: `_tool_key` 保证 `tool_id` 非空（空时回落为 name，`member_status.py:88-91`）；
  `tool_finished` 的 `elif tools` 分支只有在 `existing_name == name and existing_id == tool_id`
  时移除（`:138-148`），而该条件等价于前面已经排除的 `key in tools`。因此注释所说的
  「id 不匹配时按 name 移除」永远不会执行。
- **失败场景**: 未来若 hook 传入的 `tool_id` 为空或 provider 更换 id，工具集合不会被清理，
  状态会卡在 `tool` 直到下一次 `iteration_started`（兜底存在，但该防御代码是假保护）。
- **证据**: `agent/team/member_status.py:88-91,133-150`。
- **建议修法**: 要么删除该分支并改注释为「只按 (id,name) 精确配对，异常路径由
  iteration_started 清理」；要么让 `_tool_key` 允许空 id 并真正按 name 匹配，同时补单测。

### L4（severity: low）两处死分支/未使用常量
- **问题**: `_set_signal` 的 `if new.is_idle` 分支不可达（`reduce_signal` 从不返回 idle，
  终态重置走 `_reset_member`/`_reset_room_statuses`）；`member_status.SIGNALS` 未被任何代码/
  测试引用。
- **失败场景**: 维护者误以为 reducer 会产出 idle 并依赖该分支；死常量增加阅读噪声。
- **证据**: `agent/team/orchestrator.py:574-577`；`agent/team/member_status.py:38-48`。
- **建议修法**: 删除死分支与未使用常量，或让测试引用 `SIGNALS` 作为 reducer 输入白名单。

### L5（severity: low）teardown 的 2s 限界实际是「每次 await 2s」而非「整体 2s」
- **问题**: `_schedule_teardown` 对 flush 和 emit 各用一次 `asyncio.wait_for(..., timeout=2.0)`
  （`orchestrator.py:706-717`），最坏耗时约 4s；设计（`design.md:393-396`）写的是「整体用
  `asyncio.wait_for(..., timeout=2)` 限界」。
- **失败场景**: 慢客户端导致 flush 用满 2s 后，终态发送还能再等 2s，轮次取消后的清理
  窗口比设计口径翻倍；强引用 task 存活更久。
- **证据**: `agent/team/orchestrator.py:700-717`；`design.md:393-396`。
- **建议修法**: 用一个外层 `asyncio.wait_for(self._flush_then_emit(), timeout=2.0)` 包住
  两个 await；或把 design 改为「每阶段 2s」并记录理由。

### N1（nit）`_flush_status_emits` 的 10 次上限会在持续变化时静默提前返回
- **问题**: 固定 `for _ in range(10)`（`orchestrator.py:625-643`）在极端持续 dirty 时直接
  退出，终态可能先于最新状态表发出（seq 守卫可兜底，但「终态前先 flush」的声明变成 best-effort）。
- **建议**: 在返回前若仍 dirty，记一条 debug 日志或改为 while + 时间上限，避免静默。

### N2（nit）`member_failed` 的 time-line system 条目以 `seq:null` 追加，重连快照与 WS 事件并发时可能短暂重复
- **问题**: `group.js:408-412` 追加 error system 条目不带 seq，绕过了 `appendTimeline` 的
  seq 去重；若 `room_state`/limit 重拉已包含该日志条目、随后 WS `member_failed` 又到达，
  会出现短暂重复。低频且下一次重连/重拉会收敛。
- **建议**: 在 `member_failed` 载荷里带系统条目的 `seq`（或客户端按文本+speaker 去重）。

## 已确认站得住的部分

- **reducer**：优先级 `tool > typing > thinking > running > idle` 由显式迁移实现；工具按
  `tool_call.id` 记账、同名并发不互相抵消；`iteration_started` 无条件清空工具，覆盖
  after 钩子缺失的异常路径（`member_status.py:94-157`；`test_member_status.py` 全覆盖）。
- **终态顺序**：正常路径 reset → 身份 release → flush → review → 新 seq 终态
  （`orchestrator.py:372-400`）；取消/异常仅在仍持认领时 reset + 后台强引用 task teardown，
  已释放认领时只 re-raise（`:401-426`）。我用临时 gate 脚本实测收尾窗口行为正确。
- **seq 语义**：房间级单调 seq + 全量表；终态用重置后 seq；空表/已 idle 重置幂等不递增；
  `status_snapshot` 一次同步取 (表, seq)；客户端 `member_status` 用 `<=` 丢弃、终态用 `<`
  丢弃、快照重置水位（含 seq 变小）（`group_status.js:51-95`；`test_group_status_js.py`）。
- **握手**：持锁构造快照 → 订阅 → 发首帧 → 释放锁；失败 unsubscribe；订阅后 pong/广播
  共用发送锁（`server.py:104-132,682-752`；`test_group_chat_server.py:334-384`）。
- **Observer 生命周期**：完整 7 方法、逐 run 新实例、`try/finally` 身份摘除、回调异常只记日志
  （`session.py:458-520,2166-2225`）。
- **前端**：状态事件只重绘 presence；无状态定时器；`member_speaking` 仅在 idle/未知时降级；
  `member_failed` 使用 `data.name`；打开/关闭房间清空状态与水位；epoch 守卫旧 socket；
  全部文本走 `textContent`（无 XSS 注入面）；390px 56px 横条几何经真实 Chromium 验证。
- **规格/门禁**：两份 delta 与 current 规格一致，Q1/Q2/Q3 全部按 A 落地；OpenSpec strict
  29/29；瘦 checker EXIT=0；benchmark smoke EXIT=0；全量 pytest 与作者记录一致（3 条失败
  均为既有环境/计时问题）。

## 闭环出口

CHANGES_REQUESTED（轮内状态；本轮未收口——批次冻结包含 M1–M3 三条 medium，全部修复并补测试后
需另派独立验证轮；验证轮只复核本批修复，不引入新批次）
- 理由: 未发现 high，也未发现实现层面的功能 bug；三条 medium 均为**任务已勾选但回归测试
  不存在**的验证缺口，其中 M1 的 N1 收尾窗口行为已由 reviewer 实测正确，修复动作是补确定性
  测试而非改实现。low/nit（L1–L5、N1–N2）可登记不修，但 L1 的未提交改动必须在下一轮合并进
  提交并重建 manifest。
