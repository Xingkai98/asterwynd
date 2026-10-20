# Tasks: 群聊成员运行状态栏（真实事件驱动的 per-member 状态）

> **结算次序（收尾）**：本文件在最后一个内容提交上落定 → backlog 移除 → 归档 move（独立提交）
> → 本地复验 → **结算 `tasks.md`（未勾且未标 `(post-merge)` 必须为 0）** → **用归档目录名**
> 重建 witnessloop 三份 manifest → `gate / check` 机械复核 → 发起 PR。PR 创建与合入不写回
> `tasks.md`；closeout 类任务（合入后动作）标 `(post-merge)`。

## 0. 设计追问与对抗收敛（前置门，不完成不开工）

- [x] 0.1 用 `grilling`（独立零记忆 subagent）执行设计追问，产出 `reviews/grill-design.md`
  （`## Confirmed Decisions` ≥ 3 条，每条含同行裸 `来源:`；`## Open Questions` 与
  `## User Confirmation` 无条件存在）。
- [x] 0.2 逐项落实 grill 的 Design Corrections（C1–C27）：全量表 + 房间 seq、终态按 seq 守卫、
  重连水位重置、合并语义、空产出叙事、工具异常清理、终态顺序、意外异常/取消 teardown、
  握手 try/finally、UI DOM/公告/提示区、RIR 本地路径、脚本顺序、Hook 全方法、快照单一读。
- [x] 0.3 设计阶段对抗闭环 → `reviews/grill-adversarial.md`，按批次模型收敛到 `PASS`
  （R1–R6，R6 PASS；逐轮证据见 `reviews/grill-adversarial-r1..r6.md`）。
  轮数口径：按用户 2026-10-20 的明确指示「跑到收敛（无轮数上限）」执行；仓库
  `AGENTS.md:18` / `:104` 目前仍写「最多 20 个已收口轮」，本 change 不单方面修改仓库规则，
  若达到 20 轮仍未收敛，在停轮报告中登记差异并上报用户裁决。
- [x] 0.4 停轮确认：2026-10-20 用户确认 **Q1 = A**（390px 顶部 56px 横向条，每项 104px，
  约 3 人可见、可滑动，时间线让出 56px）、**Q2 = A**（超时/失败立即回空闲，错误只在时间线）、
  **Q3 = A**（接受每人独立一行、串行执行，真正并发另立 change）。答复已写入
  `reviews/grill-design.md` 的 `## User Confirmation`，生效口径见 `design.md` 的
  `## User Rulings (2026-10-20)`。
- [x] 0.5 回填 `design.md` 的 `## Pre-Implementation Review`（grill 决策、对抗轮次、修复项、
  出口；R1–R6 与最终 PASS 已记录）。

## 1. 测试（TDD，先红后绿）

- [x] 1.1 新增 `tests/agent/team/test_member_status.py`：纯 reducer 的优先级
  （`tool > typing > thinking > running > idle`）、按 `tool_call.id` 记账的并发/同名工具、
  `iteration_started` 清空残留工具（模拟非 Bash 异常跳过 after）、
  `stream_complete`/`run_completed` 显式降级、无变化返回 None、terminal reset。
- [x] 1.2 扩展 `tests/agent/team/test_orchestrator.py`：正常回合的**终态快照（表为空 / 与
  `status_snapshot()` 一致）**与关键子序列（事件流中曾出现 thinking/tool；不要求每个迁移
  单独发，允许合并）、`member_status` 只在变化时发且无重复空表、`status_seq`
  单调、空产出防御性 `member_silent`、建会话失败 `member_failed`（带 name、走统一 helper）、
  取消 `round_ended(cancelled)`、`_run_round` 意外异常 `round_ended(error)`、并行工具聚合、
  resume 回合（首个 thinking 来自 `iteration_started`）、`status_snapshot()` 快照、
  记忆 review 语义不变。
- [x] 1.2.1 **跨轮迟到终态（对抗 F2）**：注入阻塞 `review_sink`，round 1 reset+pop 后、旧
  `round_ended` 发出前启动 round 2 并等首个 `member_status`；放行后断言旧终态 `status_seq`
  严格小于新轮首个 status；JS 侧先应用新状态再喂旧终态，断言旧终态被丢弃。做变异验证
  （去掉 reset-before-pop / 去掉 JS seq 守卫 → 变红）。
- [x] 1.2.2 **收尾窗口不吞新消息 + 认领身份（对抗 N1 / X1）**：用一次性、有界等待的 gate
  阻塞 `_flush_status_emits`；在 round 1 已 reset+pop、flush 未完成时提交 M2，断言它开启
  R2 且新轮 status_seq 更高；放行 R1 的 flush 后断言 R2 仍 active（`round_active=true`），
  M3 被 queued 进 R2 而不是开启 R3；再取消 R1 的收尾任务，断言 R2 状态/认领与
  `round_active` 不受影响、没有旧 `round_ended(cancelled)`；把 pop 移回 flush 之后、或去掉
  except/finally 的身份判断 → 变红。
- [x] 1.3 更新 `FakeRunner.run` 签名接受 `on_progress`；`on_progress` 的「不传行为不变」
  「回调抛异常不影响 turn」放到 `test_group_chat_team.py` 或 `test_orchestrator.py`
  （`test_runner_contract.py` 保持四态/常量/哨兵口径）。
- [x] 1.3.1 **web 层映射（对抗 T1）**：在 `test_group_chat_team.py` 用真实
  `WebSessionRunner`（真实 `AgentSession` + `ScriptedLLM(stream=True)` + 一次工具调用）+
  `on_progress` collector，断言 `iteration_started`、**两次** LLM 调用各一个
  `assistant_delta`（第一次 `content + tool_calls`，第二次流式文本）、`stream_complete`、
  `run_completed`、`tool_started/finished` 的 id/name；FakeRunner 直调 `on_progress` 不能
  替代。删掉 `before_iteration`、`assistant_delta` 接线，或删掉 `before_iteration` 里的
  `saw_delta` 复位 → 测试变红（变异验证）。
- [x] 1.4 扩展 `tests/web_tests/test_group_chat_server.py` / `test_group_chat_team.py`：
  - 流式 `ScriptedLLM` 下 WS 层断言事件流中至少出现过 `tool` 状态，且回合结束后的状态
    （最后一条完整表 / `status_snapshot()`）与快照一致（不要求最后一条表仍含 tool）；
    thinking/typing 的
    中间态放在编排器/FakeRunner 层（每个 `on_progress` 后 `await asyncio.sleep(0)`），或用
    带让出点/gate 的慢速脚本 LLM；不要用无让出点的 `StreamScript` 断言中间态；非流式无 typing；
  - 脚本化工具调用下含 `tool` + 工具名，工具结束回落；
  - run 中打开第二条房间 WS：首帧 `room_state`，`member_statuses` 含忙成员与 `status_seq`；
  - **握手顺序（对抗 F2）**：把「取锁 → 锁内构造快照 → 订阅 → 发首帧」抽成可单测 async
    helper（或可阻塞 send 的 fake）；首帧发送阻塞期间调用 `room_bus.broadcast`，断言广播被
    锁挡住、首帧先到；改回先订阅后发/去掉锁 → 变红；
  - 双标签页 + 关闭发起连接：另一连接收到 `round_ended(cancelled)`（或重连快照 idle）；
  - 握手失败（monkeypatch 发送抛异常）：订阅被清理（`subscriber_count == 0`）；
  - 现有「最多 12 条事件」循环改为「收集到 `round_ended` 为止」并设安全上限（如 64）。
- [x] 1.5 新增 `tests/web_tests/test_group_status_js.py`（node + vm，复用
  `test_workflow_graph_js.py` harness）：全量表按 seq 替换、迟到 seq 丢弃、终态按 seq 删除、
  快照重置水位（含 seq 变小）、旧服务端降级（仅 idle 时 running）、`formatPhase` 文案、
  **迟到的 `round_ended(limit)` 返回 `applied=false`**（「仍重拉时间线」是 group.js/浏览器
  层动作，在 1.6 断言）。
- [x] 1.6 新增 `tests/web_tests/test_group_status_browser.py`（群聊专用 fixture）：
  桌面 1200px 三列、手机 390px 主区可用与 **Q1=A 形态**（横向条高 56px、每项约 104px、
  5 人时 `scrollWidth > clientWidth` 可横向滑动、可见约 3 人、时间线让出 56px）、
  **390px 无横向溢出**、移动端空状态
  有抽屉入口、真实 WS 事件驱动状态变化、**无事件 3s 状态不变**（反定时器，覆盖 2s 重连节奏）、
  群公告仍可见、
  静默/失败后头部不残留「正在发言」、新一轮开始清除「本轮结束」、**迟到的
  `round_ended(limit)` 仍重拉时间线**、发送失败提示在下一次成功后清除、断线时状态标记为
  过期、presence 在时间线重绘后保持横向滚动位置、自动滚入前后时间线 `scrollTop` 不变、
  独立 `aria-live` 只写单条文案、`window.AsterwyndGroupStatus` 存在、reduced-motion。
- [x] 1.7 记录修复前红/绿：reducer 与 WS 新断言在未实现时红，实现后绿；关键断言做变异验证
  （改坏优先级/漏发终态/忽略 seq → 测试变红 → 还原）。

## 2. 后端：状态模型与事件

- [x] 2.1 新增 `MemberStatus`（phase / 在途工具 `id -> name` 映射；**不含成员级 seq**）与
  纯 reducer；在 `agent/team/orchestrator.py` 维护每房间完整状态表、房间级 `status_seq`、
  dirty 与发射任务。
- [x] 2.2 `SessionRunner.run`（`agent/team/runner.py`）增加可选 `on_progress`；
  `WebSessionRunner`（`web/session.py`）、`_WorkspaceRunner`（`web/team.py`）与测试
  `FakeRunner` 三处同步。
- [x] 2.3 `SessionManager.run_session` / `_run_session_locked` 增加可选进度观察者；新增
  `ProgressObserver`/`ProgressHook`（实现**全部 7 个** Hook 方法，未用的为 no-op），在覆盖
  整个 run 的 `try/finally` 中按身份挂/摘；回调异常只记日志，不影响 run。
- [x] 2.4 在 `_run_session_locked` 的 `on_event` 闭包旁路 `assistant_delta` / `reasoning_delta`
  / `assistant_stream_complete`，每次 LLM 调用只发首个 delta 信号，不携带文本内容；
  `run_started` 用钩子，`on_completion` → `run_completed`，`on_error` 不映射。
- [x] 2.5 编排器合并发射器：状态变更同步更新完整表 + 递增 seq + 标脏；至多一个在途发射任务；
  发射时在同一同步段读取当前完整表与 seq；`on_event is None` 才跳过调度；提供
  `_flush_status_emits()`；**所有**终态（含正常 `round_ended`）前先同步重置再 flush 再用新
  seq 发终态；重置幂等（表未变不递增/不标脏），避免重复空表事件。
- [x] 2.6 接入点：`_run_slot` 在 `ensure_room_session` 前发 `running`；把进度回调绑定到
  `(room_id, persona_id)`；每个出口走统一 `_finish_member` helper。
- [x] 2.7 终态缺口/teardown：建会话失败走统一 `_finish_member(..., "member_failed", ...)`
  （带 name）；空产出防御性发 `member_silent`；`_run_round` 先**同步**计算 termination
  （含 limit system 条目）→ 同步重置（表实际变化才递增 seq）→ **按身份释放认领**
  （`if _rounds.get(room_id) is state`）→ flush → review → 发正常 `round_ended`；reset/pop
  之间不得有 await。**所有释放点（正常路径与 finally）都必须做身份判断**，否则 flush 期间
  开启的新轮会被旧轮 finally 误删（对抗 R3 / X1）。**仅在仍持有认领时**才对取消发
  `round_ended(cancelled)`、对意外异常发 `round_ended(error)`；认领已释放时只记录并 re-raise。
  用强引用后台 task（内部 flush + emit，整体 `wait_for` 2s 限界），不写日志、不产生
  `RoundResult`。
- [x] 2.8 `_run_round` 与 `_run_slot` 的各 `finally` 无条件清空状态（幂等），覆盖取消/
  意外异常/断线；`RoundResult` 与 `is_round_active` 语义不变。
- [x] 2.9 新增 `status_snapshot(room_id) -> (statuses, seq)` 同步只读快照（返回副本）。
- [x] 2.10 `member_speaking` / `member_post` / `member_silent` / `member_failed` /
  `round_ended` 增加 `status_seq`；`member_failed` 增加 `name`；原字段不改。

## 3. 后端：房间 WS 与快照

- [x] 3.1 `room_state` 增加 `member_statuses`（完整非空闲表）与 `status_seq`
  （`web/server.py`）。
- [x] 3.2 房间 WS 握手改为「取锁 → 持锁同步构造快照 → 订阅 → 发首帧 → 释放锁」，整段在
  `try/finally` 内，异常也 unsubscribe；订阅后所有发送（含 pong）走同一加锁 send。
- [x] 3.3 验证旧前端兼容：未知 `member_status` 被忽略；既有事件只增字段；
  `round_ended(cancelled|error)` 走既有「本轮结束」分支。

## 4. 前端

- [x] 4.1 新增 `web/static/group_status.js`：`createStatusState` / `applyStatusEvent` /
  `applyTerminal` / `applySnapshot` / `applySpeakingFallback` / `formatPhase` /
  `describeChange` 纯函数，暴露 `window.AsterwyndGroupStatus`。返回契约固定：
  apply* 返回 `{state, changed, applied}`（`applied=false` 表示事件因 seq 过期被丢弃，
  调用方据此决定头部/时间线动作）；不原地修改入参；`describeChange` 返回单条 aria-live
  文案或 null。
- [x] 4.2 `web/static/index.html`：presence 放进 `#group-room` 内、房间头部之后；新增独立的
  `#group-room-notice`；presence 取代成员 chip 行；不把 `#group-room-status` 当作 presence
  摘要（它继续承载连接/错误/轮次提示）；presence 重绘保存/恢复 `scrollLeft`。
- [x] 4.3 `web/static/group.js`：处理 `member_status`（按 seq 整体替换全量表）、终态（按 seq
  删除/清空）、`room_state`（重置水位并替换）、`connectionEpoch`（含 onmessage/onclose/重连
  定时器的代际守卫）、`onclose` 标记过期、`round_ended(cancelled|error)` 文案（仅在终态未被
  seq 丢弃时更新头部；**迟到但 termination=limit 的终态仍重拉时间线**，不改状态）；新一轮
  `user_message(queued=false)` 或首个非空闲 `member_status` 通过 `clearRoundStatus()` 清除
  上一轮结束提示（`setStatus(text, kind)` 区分 conn/round/op；round 才被新一轮清除，
  op 在下次成功发送/连接成功后清除，conn 由下一次连接事件替换）、
  **删除 `member_speaking` 的头部「正在发言...」文案**（成员状态只由 presence 承担）、
  `member_speaking` 降级（仅 idle/未知时 running）、`member_failed` 用
  `data.name`/`speakerName`；时间线追加按 `seq` 幂等（防重拉与事件竞态产生重复条目）；
  `openRoom`/`closeRoom` 清空状态表与水位；`round_ended(limit)` 的重拉响应应用前校验
  `state.activeRoom.id` 仍是发起时的房间。
- [x] 4.4 `web/static/style.css`：桌面 `sidebar 260 | presence 208 | timeline`（presence 在
  `.group-room-body` 内）、1000px 以下侧栏抽屉 + presence 176px；≤720px **Q1=A 顶部
  56px 横向成员条**（每项 104px、横向滚动、约 3 人可见），时间线让出 56px；状态文字、颜色、
  头像色块、连接断开灰显、自动滚入只动状态条横向 `scrollLeft`（`block:"nearest"` 或不用
  scrollIntoView）、`prefers-reduced-motion`。
- [x] 4.5 移动端修复：≤720px 管理侧栏折叠为抽屉，390px 下主区可用；头部设置/删除收纳为图标/
  更多菜单，无横向溢出；空状态提供抽屉入口；浏览器测试锁住宽度与 `scrollWidth`。
- [x] 4.6 脚本加载：`group_status.js` 在 `group.js` 之前，两个 `?v=` 递增（现状
  `index.html` 的 `group.js?v=2`）。
- [x] 4.7 可访问性：独立视觉隐藏的 `#group-presence-live`（`aria-live="polite"`）只在 phase
  变化时写入单条文案；状态不只靠颜色；头像 `aria-hidden`。
- [x] 4.8 **Q2=A：不实现失败标记**；超时/失败只回 idle，错误由时间线承载，`member_failed`
  使用 `data.name`。

## 5. 规格与文档

- [x] 5.1 `specs/multi-agent-collaboration/spec.md` delta：2 条 ADDED（状态可观测性、快照与
  重连）+ 1 条 MODIFIED（房间级互斥与轮次终止的 teardown 口径）。
- [x] 5.2 `specs/web-ui/spec.md` delta：群聊成员状态栏（全量表事件、DOM 位置、公告保留、
  移动端可用、旧服务端降级、断线过期、独立 aria-live）。
- [x] 5.3 把 delta 施加进 `openspec/specs/multi-agent-collaboration/spec.md` 与
  `openspec/specs/web-ui/spec.md`，记录 Requirement 计数，写 `current_spec_synced` 事件；
  OpenSpec strict validate 通过。
- [x] 5.4 `docs/openspec-change-backlog.md` 登记本 change（issue #307）并写 `backlog_updated`
  事件；归档前移除。
- [x] 5.5 文档影响检查：change 自身文档、`docs/architecture.md` 群聊小节、`README.md` /
  `README_EN.md`（如需同步）、`docs/interview-script/`（建议性）、`AGENTS.md` / `CONTEXT.md`
  相关段落 grep；只改事实变化。

## 6. 验证

- [x] 6.1 `uv run pytest -q tests/agent/team tests/web_tests/test_group_chat_server.py tests/web_tests/test_group_chat_team.py tests/web_tests/test_group_status_js.py`
- [x] 6.2 `uv run pytest -q`（记录 passed/failed/skipped；区分既有环境失败）。
- [x] 6.3 `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`。
- [x] 6.4 `uv run python scripts/check_openspec_artifacts.py --base-ref origin/master --require-base`。
- [x] 6.5 浏览器 smoke（桌面 1200px / 手机 390px；有浏览器则真跑，无则记录 skip 原因）。
- [x] 6.6 benchmark smoke：**checker 会触发**（proposal 的证据引用中出现
  `` `agent/loop.py:...` ``，命中 `BENCHMARK_SMOKE_CODE_PATTERNS`），必须跑
  `uv run asterwynd benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/smoke-307`
  并记录结果；本 change 不改 `agent/loop.py`，但不做文本豁免。

## 7. 实现后独立审阅闭环

- [x] 7.1 独立零记忆审阅，产出 `reviews/building-review.md`（含 `## 闭环出口`），按批次模型
  收敛到 PASS（R1→R4；R4 最终 PASS，见 `reviews/building-review-r1..r4.md`）。
- [x] 7.2 全部 medium+ 修复并补回归测试；low/nit 复核处置记录（R1 3 medium / R2 2 medium
  与 L1–L5 / R3 1 项 false-green 均已修复；R4 无新 high/medium）。

## 8. 收尾（合入后）

> 归档 move、本地复验、`tasks.md` 结算与三份 manifest 的次序见文件头；PR 创建与合入在
> manifest 之后执行，不写回 `tasks.md`。

- [ ] (post-merge) 8.1 用 `--merge` 合入 PR；合入后确认 active 目录不存在、backlog 干净、
  本地 `master` 已快进。
- [ ] (post-merge) 8.2 给 issue #307 添加完成说明 comment（PR 号与验证结果）并关闭 issue。
