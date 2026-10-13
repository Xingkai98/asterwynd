# building-review（review-loop：R1 CHANGES_REQUESTED → R2 PASS）

> 本文含两轮：上半部为 **R1（第 1 轮）原文，逐字保留**；`## Verdict` 已更新为**本轮（R2）结论**，R1 结论另存于其下的折叠块；本轮的逐条核验与新增发现见文末 `## Round 2`。

- **change**: `web-agent-group-chat`（issue #302）
- **branch**: `web-agent-group-chat/2026-10-12`
- **审阅对象**: `3ed4d4a..72a321d`（设计阶段的 R6 PASS 覆盖到 `cae3401`，**本 change 的 14 个实现提交从未被审阅过**，本文为其第 1 轮）
- **审阅者**: 独立零记忆 subagent（不继承任何开发上下文）

## Verdict

**PASS**（第 2 轮，2026-10-13；审阅对象 `72a321d..3d3ea5d`）

R1 的 I1–I14 逐条复核完毕：**I1–I13 全部真修**（不是「文字上提到」——每条都读了实现、跑了测试，其中 I1/I2/I4/I8/I9/I10 还做了「把修复回退掉，回归测试是否真会红」的判别性实测）；**I14** 属工作区卫生而非实现缺陷（worktree 根仍有未跟踪 `rea/`，收尾禁止 `git add -A`）。本轮新发现 4 条 Low + 1 条 trivial，**均不构成「实现前必修」**，其中两条（N1/N2）直接记入 `## Round 2`。

CI 面复核：`uv run pytest -q` → **4331 passed / 9 skipped / 2 failed**（2 条为 `TestFindScopeRoot` 依赖「`/tmp` 不是 git 仓库」的环境前提，本机 `/tmp/.git` 存在故上溯命中 `/tmp`；该函数本 change 未改动）；`openspec validate --all --strict` → **29 passed / 0 failed**；`check_openspec_artifacts.py --base-ref 3c7196b --require-base` → 除本报告缺 manifest 外无其他错误（manifest 已在本轮生成并复跑通过）。

<details>
<summary>R1 结论（历史记录，已被本轮取代）</summary>

**CHANGES_REQUESTED** — 两条必须修的实现缺陷（I1 群记忆 review 的单聊触发路径完全没落地、I2 房间级互斥存在 TOCTOU 竞态，实测可并发起两轮），均直接违反 spec delta 的既有 Requirement 与 design Decision 5/17。其余问题为 4 条中等 + 8 条低，见下。

</details>

## 任务逐项验证（1.x–5.x）

| 任务 | 判定 | 依据 / 备注 |
|------|------|-------------|
| 1.1 改 `multi-agent-collaboration` 规格 | ✅ | `specs/multi-agent-collaboration/spec.md:3-18`（MODIFIED 澄清 control plane 主语）、`:22-209`（ADDED 八条 Requirement） |
| 1.2 改 `long-term-memory` 规格 | ✅ | `specs/long-term-memory/spec.md:3-31`（MODIFIED 保留原 Scenario + 新增两 Scenario）、`:35-86`（review Requirement） |
| 1.3 改 `web-ui` 规格 | ✅ | `specs/web-ui/spec.md:3-45`、`:45-62`（两条 MODIFIED 加「群内会话除外」）、`:147-253`（ADDED 入口/保护/降级） |
| 1.4 同步 current spec | ✅ | `openspec/specs/multi-agent-collaboration/spec.md:1373`（人设运行模式）、`:1390`（房间应答模式）已随 `72a321d` 落地 |
| 1.5 开发前 grilling + 对抗闭环 | ✅ | `reviews/grill-design.md`、`reviews/grill-adversarial.md`（R1–R6）存在 |
| 1.6 停轮确认回写 | ✅ | `design.md:246-256`；`grill-design.md` 有 `## User Confirmation` |
| 2.1 CRUD / 持久化 / 级联 | ✅ | `tests/agent/team/test_team_store.py`、`tests/web_tests/test_group_chat_team.py:99-191`（含中断重试、幂等、room-id 复用不继承记忆） |
| 2.2 编排单测（slot/@/静默/上限/三出口/中途消息/**互斥**） | ⚠️ 部分 | 除互斥外全覆盖；互斥用例（`test_orchestrator.py:421-452`）在 `on_event=None` 且先等 `runner.started` 才发第二条，**构造上不可能暴露 I2 的窗口**，是「测试能过但抓不到 bug」 |
| 2.3 会话分离负向断言 | ✅ | `test_group_chat_team.py:194-236` |
| 2.4 `SessionRunner` 契约 | ✅ | `test_runner_contract.py`、`test_group_chat_team.py:239-306`（含并发被拒不复用陈旧文本） |
| 2.5 记忆 scope / 接线 / 标题 / review | ⚠️ 部分 | scope 隔离、标题、接线、review 机制均有真断言；但**单聊触发路径实测未落地**（I1），单聊缓冲只含 assistant 文本（I3） |
| 2.6 共享面声明断言 | ✅ | `test_group_chat_team.py:577-589` |
| 2.7 Web（pane/房间 WS/hub 过滤/DELETE/reset） | ✅ | `test_group_chat_server.py:143-242`（含损坏快照、`reset` 拒绝） |
| 2.8 多人设并发 run 不冲突 | ✅ | `test_group_chat_team.py:613-627` |
| 2.9 上限排队 + 懒构造 + notice | ✅ | `test_group_chat_team.py:527-574, 355-375` |
| 2.10 人设模式 / 房间应答模式 | ✅ | `test_orchestrator.py:137-203`、`test_group_chat_team.py:378-491`、`test_group_chat_server.py:96-140` |
| 3.1–3.2 模型与 workspace 级持久化 | ✅ | `agent/team/models.py`、`store.py`、`paths.py` |
| 3.3 会话标识与生命周期保护 | ✅ | `agent/session.py:15-55`；`web/server.py:378-384, 1026-1040` |
| 3.4 会话分离 | ✅ | `web/team.py:239-271` |
| 3.5 房间日志 + 三层切片 | ✅ | `agent/team/roomlog.py`；`test_roomlog.py` |
| 3.6 编排器（含房间互斥） | ❌ | 语义齐备，但**互斥有竞态**（I2） |
| 3.7 分层（`agent/` 不 import `web/`） | ✅ | 全仓 `agent/` 仅 `agent/main.py:684` 一处反向（既有），`agent/team/**` 零命中 |
| 3.8 记忆接线 + scope | ✅ | `web/session.py:1744-1756`（四参数忠实移植）、`persistent.py` 显式 `memory_dir`/`scope` |
| 3.9 群内会话 pending 降级 | ✅ | `web/session.py:457-495, 1861-1866`；`test_group_chat_team.py:494-524` |
| 3.10 Web 群聊视图 + 房间 WS + 管理入口 | ✅ | `web/static/group.js`、`index.html`、`web/server.py:437-692` |
| 3.11 会话数上限 + 排队 + 懒构造 | ✅ | `TeamSessionPool`（另见 L4 软上限说明） |
| 3.12 群共享 notice | ✅ | `orchestrator.py:212-215`；`test_orchestrator.py:474-487`、`test_group_chat_team.py:355-375` |
| 3.13 记忆 review 全项 | ⚠️ 部分 | 触发/游标/落后补齐/写回/`remove→archive`/队列/丢弃均已落地并有测试；**单聊触发未落地（I1）**、**「计入账本」在生产路径未接线（I5）** |
| 3.14 人设运行模式 | ✅ | `models.py:60-92`、`web/team.py:60-77, 351-381`；含「roster 覆盖陈旧快照 mode」的处理与测试 |
| 3.15 房间应答模式 | ✅ | `models.py:80-84, 109-148`、`orchestrator.py:172-175` |
| 4.1 `docs/architecture.md` | ✅ | 新增「长期人设与群聊编排」整节，口径与实现一致 |
| 4.2 `docs/interview-script/` | ✅ | `Q08-multi-agent.md:73-82` |
| 5.1 相关测试 | ✅ | `tests/agent/team` + `test_group_chat_*`：**200 passed** |
| 5.2 全量 pytest | ✅ | 本机实测 **4314 passed, 9 skipped, 2 failed**；2 条失败均为 `TestFindScopeRoot` 依赖「`/tmp` 不是 git 仓库」的环境前提（本机 `/tmp` 恰是 git 仓库 → 上溯命中 `/tmp`），与本 change 无关（`agent/memory/persistent.py` 的 `_find_scope_root` 未被本 change 改动） |
| 5.3 手动 Web golden path | ➖ 未能独立复核 | 本环境无浏览器；`test_group_chat_server.py:245-282` 提供了脚本化等价路径且通过 |
| 5.4 OpenSpec strict validate | ✅ | 本机实测 `29 passed, 0 failed` |
| 5.5 artifact checker | ✅ | 本机实测 `OpenSpec artifact checks passed` |
| 5.6 benchmark smoke | ➖ 未能独立复核 | 本 change 不触碰 `benchmarks/`；`agent/loop.py` 的改动是「条件注册 question 工具 + 快照加 kind」 |
| 5.7 Web session/server 测试 | ✅ | 同 5.1 |
| 5.8 关 issue | ⏳ | 已标 `(post-merge)`，符合归档门禁 |

## Issues

### I1 — [High] 人设单聊的 review 触发把 `room_id` 传成 `""`，单聊 scope 的记忆 review 完全不执行（必须修）

- `web/team.py:401-403`：`_attach_turn_listener` 的监听器对**所有**会话统一调 `on_member_turn(room_id=room_id or "", ...)`；人设单聊的 `room_id` 是 `None`，于是传成 `""`。
- `agent/team/memory_review.py:213`：`_queue(make_scope(self._project_root, persona_id, room_id))` → `make_scope(..., "")`。
- `agent/team/memory_review.py:94-95`：`is_group` 判定是 `self.room_id is not None`，**空串被判成 group**。
- `agent/team/paths.py:88-91`：`room_id=""` 走 `base / "rooms" / "" / "memory"`，pathlib 丢弃空段 ⇒ 落点变成 `personas/<pid>/rooms/memory`（一个不存在的伪 scope）。
- 结果：`run_once` 在 `memory_review.py:331-333` 的 `scope.memory_dir.parent.exists()` 处直接返回 `"dropped"`（该目录不存在），或退一步走 `_read_group_new` 读 `get_room("")` → `None` → `"empty"`；**真单聊 scope 永不入队**，而 `append_chat_message`（`web/team.py:400`）写进 `personas/<pid>/chat/memory/pending_review.jsonl` 的内容**永不被消费，无界增长**。

实测（本机复现，TeamService 级）：

```
reviewer calls: []                       # 单聊跑完一轮，review 一次都没触发
pending buffer left: ['单聊回复']        # 缓冲原样留存
```

违反：`specs/long-term-memory/spec.md:37`（Requirement「人设记忆的 review 触发与游标」）、其 Scenario「单聊回合也触发 review」（`:52-56`）、design Decision 17 第 1 条、tasks 3.13。

建议：把「无人设群面」表达成 `None`（例如 `on_member_turn(room_id: str | None)`，或监听器只对群会话调 `on_member_turn`、单聊走 `run_once(chat_scope)`），并补一条**经 `_attach_turn_listener` 的真实路径**测试（现有 `test_memory_review.py:107-114` 是绕过监听器直接 `run_once(正确 scope)`，抓不到本 bug）。

### I2 — [High] 房间级互斥存在 TOCTOU：`_rounds` 注册发生在 `await` 之后，可并发开两轮（必须修）

- `agent/team/orchestrator.py:307-333`（`submit_user_message`）的注释断言「`_rounds` 的查—建之间没有 `await` 点」——**该断言不成立**。
- 实际顺序在 `agent/team/orchestrator.py:339-354`：`log.append_user` → **`await self._emit("user_message", ...)`（`:342`）** → 才 `self._rounds[room.id] = state`（`:354`）。
- `_emit` 在生产路径**必然挂起**：`web/team.py:202-213` 注入 `on_event=service.event_sink` → `web/server.py:143-147` 的 `_team_event_sink` → `RoomEventBus.broadcast` → `await ws.send_json(...)`；而房间 WS 的连接正是用户在看这个房间时的常态。
- 触发面：房间 WS 对每条 `chat` 帧 `asyncio.create_task(submit_room_message(...))`（`web/server.py:672-681`），前端发送时**不锁输入**（`web/static/group.js:374-383`）——用户连点两次发送、或两个 tab / HTTP 与 WS 并发，即命中。

实测（注入一个会挂起的 `on_event`，同 tick 起两个 `submit_user_message`）：

```
queued flags: [False, False]     # 两条都开了新轮，没有一条走「排队进本轮」
runner calls: [('room-pA', ...第一条...), ('room-pA', ...)]   # 同一成员会话被两轮各驱动一次
```

后果正是 Decision 5 要禁止的：两轮并存 ⇒ 第二名成员 run 撞 `run_lock` ⇒ `failed(run_in_progress)` ⇒ 房间日志出现假 `system`「成员 X 运行失败」。附带第二个缺陷：`_rounds` 以 room_id 为键，第二轮会**覆盖**第一轮的 state，第一轮结束的 `finally: self._rounds.pop(...)`（`:358`）又把第二轮的 state 删掉 ⇒ `is_round_active`（`:301`，被 `web/server.py:656` 的 `room_state` 使用）在轮次进行中报 false，且此后再来一条用户消息会开**第三轮**。

违反：`specs/multi-agent-collaboration/spec.md:111`（Requirement「房间级互斥与轮次终止」）、其 Scenario「并发消息进入同一轮」（`:127-133`）、design Decision 5。

建议：把「查—建」收敛到一个**同步段**（读 room → 算 slots/limit → `self._rounds[room.id] = state` 全在首个 `await` 之前；`append_user` 与 `_emit` 移到注册之后），或用一个同步的「认领集合」。补回归测试：`on_event` 注入一个会挂起的 sink，同 tick 两个 `submit_user_message`，断言 `queued` 恰有一条为 True。

### I3 — [Medium] 单聊待 review 缓冲只写入人设自己的回复，不含用户消息（应随 I1 一并修）

`web/team.py:395-400` 只在 `outcome.spoke` 时把**助手文本**写进缓冲；用户那句（真正承载可记事实的一句）从不入缓冲。对照群 scope 的 review 输入（`agent/team/memory_review.py:481-486` 渲染 `User:` 条目）是**含用户消息**的，两个会话面的 review 输入口径因此不对称。

design Decision 17 的措辞是「运行期在**向该 scope 追加消息**时写入」（`design.md:182`），`Message` 面本来就含 user 角色 ⇒ 实现只做了半条。影响：即使 I1 修好，单聊 review 也只能读到人设的自我复述——而持久记忆的事实来源基本在用户侧。

建议：把用户消息也写入缓冲（在同一监听器里覆盖 user 角色消息，或在 `_run_session_locked` 的 user 追加点挂钩），并补断言「单聊 review 的 `new_content` 同时含 `User:` 与助手两侧内容」。

### I4 — [Medium] 房间设置里「房间 admin 选（无）」是静默 no-op，admin 无法被清空

- `web/team.py:609-610`：`if fields.get("admin") is not None: room.admin = fields["admin"] or None`。
- 前端「（无）」固定发 `admin: null`（`web/static/group.js:551`），服务端 `if k in payload` 会把它收进 `fields`（`web/server.py:574-575`），随后被上面的 `is not None` 静默丢弃。

实测：把 admin 指向 A 后，用 `admin=None` 走 `update_room`，回读仍是 A（`admin before: p44f8...` / `admin after (admin=None): p44f8...`）。用户在 UI 里把应答者改成「（无）」看起来保存成功，实际房间仍由原 admin 应答。违反 spec `web-ui`「改 admin」的管理入口口径（`specs/web-ui/spec.md:178`）。

建议：改成 `if "admin" in fields:` 判定，并补一条「PATCH `admin: null` 后回读为 None」的接口测试。

### I5 — [Medium] 记忆 review 的成本「计入账本」在生产路径未接线（tasks 3.13 该项未落地）

`TeamService(cost_ledger=None)` 的默认值在唯一的生产构造点保持默认（`web/server.py:150-155` 未传 `cost_ledger`），而 `web/` 下**根本不存在** `CostLedger`（全仓只有 `agent/main.py:298` 建账本）。因此 `agent/team/memory_review.py:159-175` 的 `record_usage` 在生产永远走 `if self._cost_ledger is None: return`，review 的 `1 + k` 次调用既不进账本也无任何出口（`cost_counter` 无人读取）。

判定：设计确实要求「需额外接线计入 `CostLedger`」（`design.md:178`），管线也接好了，但生产路径缺最后一跳 ⇒ tasks 3.13 的这一子项**未真正完成**。建议二选一：(a) 给 Web 路径提供账本并在此注入；(b) 在 `tasks.md` 把「计入账本」如实降级为「已预留 `cost_ledger` 注入口，Web 侧账本待后续 change 提供」并记入 `docs/known-debt.md`。二者皆可，但不应维持「已勾选 + 实际不可观测」的现状。

### I6 — [Low] 群内会话的 review 被**双重触发**，其中一次早于本轮发言落日志

`agent/team/orchestrator.py:477-483`（发言落日志**之后**）与 `web/team.py:401-403` 的会话级 `turn_listener`（run **之内**，早于 `append_post`）都会为同一 `(persona, room)` 排一次 review。队列按 scope key 合并（`memory_review.py:247-252`），因此不会多花一次模型调用；但**先到的那次**可能读不到本人刚发出的那条（游标推进到该条之前），把它推到下一次 review 才被读到。语义上无永久丢失（下次发言或落后补齐会补上），故记 Low。

建议：二选一保留单一路径——要么删掉 `turn_listener` 里的群分支（群侧交给 `review_sink`），要么删掉编排器的 `on_member_turn` 调用。修 I1 时顺带处理最省事。

### I7 — [Low] `unload_session` 的 docstring 声称释放「MCP 子进程」，实际只丢引用

`web/session.py:1804-1820` 只做 `_sessions.pop` + 摘 forwarder / detach 连接；没有 `mcp_manager.aclose()`（`agent/mcp/manager.py:353` 存在但 Web 路径无人调用，`grep` 确认只有 CLI/benchmark 调）。会话数上限因此是「内存里的 `AgentSession` 数」上限，不是「MCP 子进程数」上限——而 design Decision 1 的成本模型正是按这个上限论证的。既有的 `remove_session` 同样是丢引用（非本 change 引入），故只记 Low：建议要么在 `unload_session`/`remove_session` 里显式 close，要么把 docstring 的「MCP 子进程」删掉、并说明上限口径。

### I8 — [Low] 会话池上限是软上限，可短暂超额

`web/team.py:154-171` 的 `acquire` 与 `:349-382` 的 `track` 之间存在多个 `await`（`pool.acquire` 之后的 `load` / `build_mcp_manager` / `create_team_session_async`），并发的 `_ensure_session` 可同时通过 `len(self._live) < self._max` 检查。影响：上限可能被瞬时突破（构建成本正是设计想封的东西）。建议把 `track` 提前到 `acquire` 成功之后立刻执行（占位语义），失败再 `forget`。

### I9 — [Low] 同一 (persona, room/session_id) 的会话底座可被并发重复构造

`web/team.py:239-271` 与 `:339-385`：`manager.get_session(session_id)` 为 None 后要 `await team.pool.acquire(...)` + `await create_team_session_async(...)`（内含 `await build_mcp_manager`），窗口内第二个并发调用会再建一个同 id 的 `AgentSession`/`AgentLoop`，后者覆盖 `self._sessions[session_id]`，前一个被静默泄漏（连它的 MCP manager）。建议给 `_ensure_session` 按 session_id 加 asyncio 锁或 in-flight future 表。

### I10 — [Low] 房间 WS 把单条畸形帧当断连处理

`web/server.py:663-668` 内层只捕获 `RuntimeError`；客户端发一个非 JSON 文本帧时 `receive_json` 抛 `JSONDecodeError`，被外层 `except Exception`（`:686`）吞掉并 **break**，实时连接被整体摘掉。会话级 WS 对同类问题有显式口径（`web/session.py:1959-1976`：畸形帧 ≠ 断连，只记日志继续）。建议对齐：内层把 `json.JSONDecodeError` / `UnicodeDecodeError` / `KeyError` 当非致命帧。

### I11 — [Low] 死代码与未用符号

`agent/team/memory_review.py:473-478` 的 `_ZeroUsage` 全仓零引用；`agent/team/models.py:17` `ENTRY_KINDS`、`:36` `INTERNAL_KINDS`、`:20` `PERSONA_MODES` 零引用（`web/team.py:27` 还 import 了未使用的 `PERSONA_MODES`）；`agent/team/runner.py:29-32` 的 `STATUS_*` 常量只有 `STATUSES` 被用到；`agent/team/store.py:93-95` 的 `first_main_bot` 仅测试使用（生产走 `main_bot_ids()`）。建议清理，或让消费方真正用它（如 `PERSONA_MODES` 与 `AgentMode` 取值做一致性断言）。

### I12 — [Low] 测试文件 docstring 指向不存在的文件

`tests/agent/team/test_orchestrator.py:6` 与 `tests/agent/team/test_runner_contract.py:5` 都写「真实 web 层实现在 `tests/web_tests/test_group_chat_runner.py`」——该文件不存在（真实文件是 `test_group_chat_team.py`）。会误导后续维护者找错地方。

### I13 — [Low] 规格文字与 Decision 19 有轻微出入（设计增量未回灌到早期 Requirement）

`specs/multi-agent-collaboration/spec.md:74` 的 ADDED Requirement「会话式群聊轮次编排」仍写「用户消息 SHALL 默认由房间 admin（无则 roster 首个 mainBot）应答」——这在 `reply_mode = everyone` 下不成立（那条新 Requirement 在 `:196-209` 已正确限定）。同理 `specs/web-ui/spec.md` 无冲突。建议把 `:74` 的句子限定为「在 `reply_mode = admin`（缺省）下」，避免读者按字面验收时得出矛盾结论。

### I14 — [Low] 工作区卫生：`rea/` 未跟踪目录可能被误提交

worktree 根目录存在未跟踪、且**未被 `.gitignore` 覆盖**的 `rea/`（一个外来 JS 项目的完整副本，含 `package.json`/多语言 README，实测 `git check-ignore` 不匹配）。本 change 不涉及它，但收尾若用 `git add -A` 会把它一并提交。建议归档收尾前删除或加入忽略。另：`docs/openspec-change-backlog.md:114` 仍写「未实现（2026-10-12 立项）」——这是归档步骤的应有状态，不算缺陷，收尾时记得移除。

## 已核验通过

- **Spec 对齐（正向）**：房间日志 schema 与三类条目、三层有界切片、`@` 的行首/句中双口径、静默哨兵、三出口（走完 / 达上限含 `system`「本轮因达上限结束」/ 全部失败）、上限按开局 slot 数定基不因中途消息变基、notice 只进群内会话、会话分离、群内会话 pending 降级而人设单聊不降级——逐条与 `specs/*/spec.md` 对得上，且都有非平凡断言（不是只 assert 不抛）。
- **Decision 18/19（本次追加的两条设计）一致性**：实现（`models.py:19-29, 60-92`；`orchestrator.py:152-181`）、REST（`web/server.py:512-514, 574-575`）、前端对话框（`web/static/group.js:496-507, 536-542`）、规格（`openspec/specs/multi-agent-collaboration/spec.md:1373-1409`，delta 同名）四层一致；非法值 `mode`/`reply_mode` 均结构化 400；`everyone` 按「admin 先 + 其余成员顺序 + 各自可静默」实现且有断言。**设计增量未发现实现缺口**（仅 I13 的规格文字限定问题）。
- **安全面**：内部会话 `persona-` / `room-` 前缀保护同时覆盖 `DELETE /api/sessions/{id}`（`web/server.py:381-384` → 403 `internal_session_protected`，底座保留）与 WS `reset`（`web/server.py:1026-1040`，roster 映射不悬空）；hub 列表 / `session_count` / CLI `session list` 三处同口径过滤且**不读快照**（损坏快照凭目录名前缀照样被过滤，有测试 `test_group_chat_server.py:160-170`）；记忆跨人设、跨会话面无泄漏（目录级隔离 + `_scope_matches` 只做**同 store 内**的放宽，`/other/project` 仍被拒）；`to_dict`/`from_dict` 快照向后兼容（旧快照无 `kind` → `chat`）。群内会话 `AskUserQuestion` 从工具面撤除、审批 fail-closed 立即可用（`test_group_chat_team.py:494-514`）。
- **正确性细节**：`TurnOutcome.text` 只来自本次 run（`last_turn` 仅在 `_run_session_locked` 锁内刷新，被拒/超时/取消都不会读到旧值，`test_group_chat_team.py:257-274`）；空产出映射为静默而非 failed；单成员建会话失败/运行失败/超时都记 `system` 且不挂死整轮；成员中途被移出房间跳过该 slot；`everyone` 模式下每成员上限仍生效；团队存储损坏不抛（roster 回落空花名册并 warn、房间日志跳过坏行并报行号）。
- **分层与可维护性**：`agent/team/**` 零 `web/` 依赖，编排器只依赖 `SessionRunner` / `SessionResolver` 两个 Protocol（`runtime_checkable`）；`agent/loop.py` 的 question 工具注册改为按 `expose_question_tool` 条件注册，普通会话零行为变化；`PersistentMemory` 两个新入参都是 keyword-only 且不传时逐字节等价（`test_persona_memory_scope.py:42-51` 锁定了零回归）。
- **CI 面**：本机实测 `uv run pytest -q` → 4314 passed / 9 skipped / 2 failed（2 条为 `/tmp` 是 git 仓库的环境前提失败，与本 change 无关）；`openspec validate --all --strict` → 29 passed / 0 failed；`check_openspec_artifacts.py` → passed。

## Round 2

- **change**: `web-agent-group-chat`（issue #302）
- **branch**: `web-agent-group-chat/2026-10-12`
- **审阅对象**: `72a321d..3d3ea5d` —— R1 之后的 5 个修复提交（`236201a` 单聊记忆 review 链路 (I1/I3/I6) / `4ad88b8` 房间级互斥 TOCTOU (I2) / `089dee9` 房间 admin 显式清空 (I4) / `0423c88` 审阅低项收口 (I7/I8/I9/I10/I11/I12) / `3d3ea5d` I5 措辞如实 + I13 规格限定 + known-debt 登记）
- **审阅者**: 独立零记忆 subagent（第 2 轮，不继承任何开发上下文）
- **判定口径**: 只有「必须实现前修」才 CHANGES_REQUESTED；纯低风险 / 已记债 → PASS 并注明。

### 判别性实测方法（「真修」而非「文字上提到」）

对**可机械判别的**修复项，不满足于「读了实现觉得对」，而是实测「把修复回退掉，该条回归测试是否真会红」：

```
git archive HEAD | tar -x -C /tmp/r2scratch      # 导出整棵树，绝不 cp -a worktree（.git 是文件，cp -a 会改到原仓）
git show 72a321d:<file> > /tmp/r2scratch/<file>  # 只回退该修复涉及的文件到修复前版本
PYTHONPATH=/tmp/r2scratch <worktree>/.venv/bin/python -m pytest <该条回归测试>
```

该过程只在 `/tmp` 的临时副本上进行，**不触碰本 worktree、不修改任何受保护文件**。结果见下表「回退实测」列。

### 逐条核验（I1–I14）

| 项 | 判定 | 证据 / 回退实测 |
|----|------|------------------|
| **I1** 单聊 review 触发传 `room_id=""` | ✅ 真修 | 三层都改到位：`make_scope` 加 `room_id = room_id or None` 归一（`agent/team/memory_review.py:108`）；`on_member_turn` 签名放宽为 `room_id: str \| None`（`:215`）；`_attach_turn_listener` 对群内会话**直接 return**、单聊监听器显式调 `on_member_turn(room_id=None, ...)`（`web/team.py:439, 453`）。**回退实测**：把 `web/team.py` + `agent/team/memory_review.py` + `web/session.py` 回退到 `72a321d` 后，`test_single_chat_turn_triggers_review_on_the_chat_scope` 失败于 `assert [] == ['persona:p8b06da8accfe']` —— **正是 R1 记录的 bug 现象**（真单聊 scope 永不入队）。修复后该测试经**真实监听器路径**（`manager.run_session` → `_run_session_locked` → `turn_listeners`，`web/session.py:2156`）驱动并通过，不是绕过监听器直接调 `run_once`。I1 的「缓冲永不消费、无界增长」另一半由 `test_single_chat_pending_buffer_is_consumed` 覆盖（连跑两回合后 `read_pending == []`）。 |
| **I2** 房间级互斥 TOCTOU | ✅ 真修 | `_run_round` 的 `self._rounds[room.id] = state` 已前移到**任何 `await` 之前**（`agent/team/orchestrator.py:350-352` 注册；`append_user`（同步，`:354-355`）与 `await self._emit(...)`（`:356`）都排在其后），从 `submit_user_message` 的 `self._rounds.get()` 到注册之间确无挂起点。**回退实测**：把 `orchestrator.py` 回退到 `72a321d` 后，`TestRoomMutexUnderSuspendingSink::test_concurrent_submits_with_suspending_sink_open_one_round` 失败于 `assert False is True`（`is_round_active` 在轮中报 False）—— 即 R1 描述的「两轮并存 + 第二轮覆盖 state」路径。该用例确实注入了**必然挂起的 `on_event`**（`await gate.wait()`，注释明写「模拟房间 WS 的 `send_json`」），构造上能暴露原窗口。 |
| **I3** 单聊缓冲只含助手侧 | ✅ 真修 | 监听器现在两侧都写：`User: ...`（`web/team.py:449`）+ `Assistant: ...`（`:451`），与群 scope 的 `_render_entry` 的 `User:` 口径对齐（`agent/team/memory_review.py:520`）。`test_single_chat_review_input_covers_both_sides` 断言用户句与助手回复都在 `new_content` 里。 |
| **I4** admin 无法清空（静默 no-op） | ✅ 真修 | `if "admin" in fields:`（`web/team.py:663`，替代原 `is not None`）。**回退实测**：把 `web/team.py` 回退后，服务层 `test_update_room_with_explicit_none_admin_clears_it` 与 REST 层 `test_patch_admin_null_clears_it` **均红**；配套 `test_absent_admin_field_keeps_the_current_value`（缺字段保留原值）锁定「显式 null 才清空」的边界。 |
| **I5** review 成本「计入账本」未接线 | ✅ 按方案 (b) 如实收口 | 不再维持「已勾选 + 实际不可观测」：`tasks.md:37` 的 3.13 子项改写为「按 1+k 口径计数（`MemoryReviewService.record_usage` / `cost_counter`；**Web 生产路径尚未注入 `CostLedger`**，故该计数当前只在测试可观测——见 `docs/known-debt.md`）」；`docs/known-debt.md` 新增「群聊记忆 review 的两条落地缺口」节，写明现象、影响与收敛方向；`workflow-events.jsonl:2` 有对应的 `protected_artifact_explained` 事件（`approved_by` 指向本报告）。判定：设计与实现边界现在一致，属已记债。 |
| **I6** 群内 review 双重触发 | ✅ 真修（守门型测试） | 群会话不再挂 `turn_listener`（`_attach_turn_listener` 对 `room_id is not None` 直接 return，`web/team.py:439`），群 review 唯一来源是编排器在**发言落房间日志之后**的 `on_member_turn`（`orchestrator.py:483-489`）。`test_group_review_is_not_double_triggered` 断言该 (persona, room) scope 恰好 1 次、且读到的就是本人刚发出的那条。**说明**：该用例在修复前**也通过**（`_queue` 按 scope key 合并，旧路径不会多花模型调用、也不会改变「先到的那次读不到自己刚发的条目」这一点需在真实竞态下才显现）——故它是**守门测试**而非判别性回归测试，已在表中如实标注。 |
| **I7** `unload_session` docstring 失实 | ✅ 真修（文档口径） | `web/session.py:1804-1820` 的 docstring 改为「**只丢内存引用**」，并显式写明「本方法**不**调用 `mcp_manager.aclose()` ⇒ 会话数上限是『内存里活着的 `AgentSession` 数』上限，**不是** MCP 子进程数上限」，与 `docs/known-debt.md` 第 2 条同口径。代码行为未变（未新增显式 close），docstring 与实现现在一致。 |
| **I8** 会话池上限是软上限 | ✅ 修（有残留，见 N1） | `track` 前移到 `acquire` 之后立刻执行、两者之间无 `await`（`web/team.py:371-375` 的 `await team.pool.acquire` 紧随 `team.pool.track(session_id)`），构造失败走 `except → team.pool.forget(session_id)` 释放占位（`:376-379`）。`test_failed_construction_releases_the_slot` 断言失败后 `pool.live() == []`（**说明**：该用例在修复前亦通过——旧实现根本不曾提前占位，故它同样是守门测试）。**残留 N1**：`_lru_idle` 会把「构造中」的占位判成非活跃并摘除。 |
| **I9** 同 id 会话并发重复构造 | ✅ 真修 | 新增 `_session_locks`（`web/team.py:294`）+ per-session `asyncio.Lock` + 双检（`:353-364`）。**回退实测**：回退 `web/team.py` 后 `test_concurrent_ensure_builds_the_session_once` 失败于 `assert 2 == 1`（`builds["n"] == 2`，确实建了两个同 id 底座）。**残留 N2**：`_session_locks` 无回收。 |
| **I10** 房间 WS 把畸形帧当断连 | ✅ 真修 | 内层 `receive_json` 新增 `except (json.JSONDecodeError, UnicodeDecodeError, KeyError)` → 记日志 `continue`（`web/server.py:670-676`），与会话级 WS 的「畸形帧 ≠ 断连」口径对齐；`{}`（合法 JSON 但非已知类型）与 `[]`（非对象帧）仍走各自既有的宽松分支。**回退实测**：回退 `web/server.py` 后 `test_malformed_frame_does_not_kill_the_connection` 不再通过（连接被摘，后续 `pong`/`user_message` 取不到 → 5 分钟超时挂死；见 **N3**）。 |
| **I11** 死代码 / 未用符号 | ✅ 真修 | 删除 `_ZeroUsage`（`memory_review.py`）、`INTERNAL_KINDS`（`models.py`）、`first_main_bot`（`store.py`，测试改用 `main_bot_ids()`）；`ENTRY_KINDS` 由「零引用」变为被 `roomlog.py:67` 真正消费（`if kind not in ENTRY_KINDS`）；`web/team.py` 移除未用的 `PERSONA_MODES` import；新增 `TestConstantsStayInSync`（`tests/agent/team/test_runner_contract.py:40-62`）把 `PERSONA_MODES == tuple(mode.value for mode in AgentMode)`、`DEFAULT_PERSONA_MODE ∈ PERSONA_MODES`、`STATUSES` 四值等常量与真实来源钉在一起——正是 R1 建议的「让消费方真正用它」而非硬删。全仓 grep 确认无悬挂引用。 |
| **I12** docstring 指向不存在的文件 | ✅ 真修 | `tests/agent/team/test_orchestrator.py:6`、`tests/agent/team/test_runner_contract.py:5` 均改为 `tests/web_tests/test_group_chat_team.py`。 |
| **I13** 规格文本与 Decision 19 出入 | ✅ 真修 | delta 与 current 规格**两处同步**限定：`openspec/changes/web-agent-group-chat/specs/multi-agent-collaboration/spec.md:74` 与 `openspec/specs/multi-agent-collaboration/spec.md:1268` 均改为「在 `reply_mode = admin`（缺省）下，无 `@` 的用户消息 SHALL 默认由房间 admin…应答；在 `reply_mode = everyone` 下…由全体成员按序各得一次发言机会（见「房间应答模式」）」。`openspec validate --all --strict` → **29 passed / 0 failed**，本次编辑未触发 strict 校验失败。 |
| **I14** 工作区卫生 `rea/` | ⚠️ 未处理（非实现缺陷） | `git status` 仍显示 `?? rea/`（`git check-ignore` 不匹配，未被 `.gitignore` 覆盖）。修复提交未涉及它——这是**收尾动作**而非代码问题。**提醒**：归档/PR 提交禁止 `git add -A` / `git add .`，只 add 显式路径；`docs/openspec-change-backlog.md:114` 的「未实现（2026-10-12 立项）」同样是归档步骤的应有状态，收尾时移除。 |

### 本轮新发现（均为 Low / trivial，不构成必修）

**N1 — [Low] I8 的占位会被 `_lru_idle` 当「非活跃」摘除且不重挂（残留）**

- `web/team.py:371-375`：`_construct_session` 在 `acquire` 之后立刻 `track(session_id)` 占位——但此刻该 session 尚未进 `manager._sessions`（底座在 `_build_session` 里才建）。
- `web/team.py:175-183`：`_lru_idle` 遍历 `_live` 时对 `manager.get_session(sid) is None` 的处理是 `self._live.remove(session_id); continue`（本意是清理「已被外部删掉的残留」）。构造中的占位正好命中这一支 ⇒ 占位被摘掉，且构造完成后**没有任何地方把它重挂回去**。
- 后果：池已满 + 有并发构造时，`_live` 会少计，上限仍可被瞬时突破（正是 I8 想封的东西）。触发条件是「池满」这一本就少见的状态，且影响是软上限的短暂失准，故记 Low。
- 收敛方向（留给后续，不阻塞本 change）：给占位一个专门的「构造中」标记（而非复用 `get_session() is None` 这个与「已删除」共享的判据），或在 `_build_session` 成功后补一次 `track`。

**N2 — [Low] `_session_locks` 只增不减（I9 修复的新增面）**

- `web/team.py:294` 定义、`:353` 用 `setdefault` 创建，全仓无任何清理点（`forget` / `remove_session` / 级联删除都不碰它）。
- 后果：每个**曾经出现过**的 session_id 都会在 `TeamService` 生命周期内保留一个 `asyncio.Lock`（几十字节级）。上限是「进程内创建过的会话 id 总数」，随时间单调增长；有会话 id 更替（删除人设/房间后重建）时不会回收。
- 量级很小、不构成功能缺陷，但与本 change 主打的「会话数有上限、懒构造」的约束精神相反，建议在 `pool.forget` / `remove_session` 路径顺带 `pop` 掉。

**N3 — [Low] I10 的回归测试在「回归」时是 hang 而不是 fail（测试质量）**

- `tests/web_tests/test_group_chat_server.py:265` 的 `test_malformed_frame_does_not_kill_the_connection` 在修复被回退后**不抛断言失败，而是挂死**（实测跑满 5 分钟超时；进程停在 `epoll_wait`）。
- 原因：连接被服务端 `break` 摘掉后，客户端的 `receive_json()` 等不到任何帧，测试卡在阻塞读上；本仓 `pyproject.toml` 未配置 `pytest-timeout`，CI 上会表现为整个 job 超时而非一条明确红。
- 影响仅限「将来若回归，定位成本变高」，不影响当前正确性。建议给该用例加一个本地 `asyncio.wait_for` / `pytest.mark.timeout` 兜底。

**N4 — [Low] 本 change 改了 `openspec/specs/**` 但没有自己的 `current_spec_synced` 事件**

- 本分支相对基点 `3c7196b` 修改了 3 个 current spec（`long-term-memory` / `multi-agent-collaboration` / `web-ui`），但 `openspec/changes/web-agent-group-chat/workflow-events.jsonl` 只有 2 条事件（`backlog_updated`、`protected_artifact_explained`），**没有** `current_spec_synced`。
- 按 `scripts/flow-policy.json`，`openspec/specs/` 是 `event_explained` 且要求事件类型 `current_spec_synced`；AGENTS.md 亦要求「修改 `openspec/specs/**` 时必须有结构化解释事件」。本 worktree 无 `.claude/` hook（guard 在 worktree 不生效），故写入未被拦。
- **但 CI 不红**：实测 `check_openspec_artifacts.py --base-ref 3c7196b --require-base` 未就此报错——`_event_covers_artifact_path`（`scripts/check_openspec_artifacts.py:1283-1289`）是按**路径**在**全部** `openspec/changes/**/workflow-events.jsonl`（含 `archive/`）里找覆盖事件，而历史归档里已存在 `artifact_path` 恰为 `openspec/specs/multi-agent-collaboration/spec.md` 的 `current_spec_synced`（如 `enhance-workflow-graph-ux`）⇒ 门**空过**。
- 结论：不阻塞（机制上绿），但与本仓自定的口径不符。建议收尾时补一条 `current_spec_synced` 事件（本 change 的 change_id），把证据补成自洽。（`_event_covers_artifact_path` 用任意 change 的历史事件满足当前 change 的路径变更，本身是一处 checker 宽松面，另案处理。）

**N5 — [trivial] `ReviewSink` Protocol 与实现签名轻微漂移**

- `agent/team/orchestrator.py:84-86` 的 `ReviewSink.on_member_turn` 仍声明 `room_id: str`，而实现 `MemoryReviewService.on_member_turn`（`agent/team/memory_review.py:215`）接受 `str | None`。编排器永远传真实 `room_id`，故无运行时影响（Protocol 非 `runtime_checkable`，也不做 isinstance 判定）；仅类型层不一致。可顺手同步为 `str | None`。

### Decision 18 / 19 复核（本轮）

- **Decision 18（人设运行模式）**：`agent/team/models.py:20-27` 的 `PERSONA_MODES = ("build","read_only","plan","bypass")` + `DEFAULT_PERSONA_MODE = "bypass"` 与 design 的钉死一致；构造路径 `web/team.py:396-408` 用 `parse_agent_mode(persona.mode)` 并**用 roster 值规整快照**（避免 `AgentLoop` resume 分支用旧快照 mode 顶回）；非法值经 `_normalize_persona_mode` → 400（`web/server.py:755`）。本轮新增的一致性断言（`test_runner_contract.py:45-47`）把 `PERSONA_MODES` 与 `AgentMode` 取值绑死，杜绝常量再次漂移。
- **Decision 19（房间应答模式）**：`REPLY_MODES = ("admin","everyone")` + `DEFAULT_REPLY_MODE = "admin"`（`models.py:30-32`）；`opening_slots`（`orchestrator.py:152-181`）在两种模式下**都**优先行首 `@`，无 `@` 时 `everyone` 返回「admin 先 + 其余成员按序」；每轮每成员上限两模式均生效（`_append_called_slots` / `_drive`）。规格四层（delta / current spec / REST / 前端对话框）与实现一致；I13 修完后规格文字不再与 Decision 19 冲突。
- **结论**：本轮未发现 Decision 18/19 的实现缺口或新增口径漂移。

### 本轮已核验通过（增量）

- **R1 的「已核验通过」各项未被本轮修复破坏**：全量 `uv run pytest -q` → 4331 passed / 9 skipped / 2 failed（+17 tests 相对 R1 的 200 → 217，在群聊/团队子集内）；2 条失败与 R1 完全同因（`TestFindScopeRoot` 依赖 `/tmp` 非 git 仓库，本机 `/tmp/.git` 存在），已确认 `_find_scope_root` 函数体本 change 未改动（`git diff 3c7196b..HEAD -- agent/memory/persistent.py` 的改动集中在 `PersistentMemory.__init__` 的 `memory_dir`/`scope` 入参与 `archive` 前像，未触及该函数）。
- **单聊 review 在生产路径可达**：除 `ensure_persona_chat_session` 外，WS resume 走的 `adopt_internal_session`（`web/team.py:478-514`）同样经 `_ensure_session → _build_session → _attach_turn_listener` 接线，故「恢复会话后单聊 review 停摆」这一潜在缺口也不存在；LRU 淘汰后重建（`test_evicted_session_restores_from_snapshot`）同样重新挂监听器。
- **测试替身隔离说明成立**：`tests/web_tests/test_group_chat_team.py:36-52` 的 `_NoopReviewer` 默认替身避免了 `LLMMemoryReviewer` 与 `ScriptedLLM` 抢同一条脚本响应（否则会话会读到本该给 review 的那条）；真正关心 review 的用例（`TestSingleChatReview`、`test_group_review_is_not_double_triggered`）显式注入 `_RecordingReviewer`。真 reviewer 的覆盖仍在 `tests/agent/team/test_memory_review.py`（agent 层），未丢面。
- **CI 面（本轮实测）**：`openspec validate --all --strict` → 29 passed / 0 failed；`check_openspec_artifacts.py --base-ref 3c7196b --require-base` → 仅差本报告缺 manifest（已补齐并复跑通过）。
