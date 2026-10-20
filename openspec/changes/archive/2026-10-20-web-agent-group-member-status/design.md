# Design: 群聊成员运行状态栏（真实事件驱动的 per-member 状态）

## Context

群聊视图当前的实时信息只有两种：

1. 编排器的房间级事件：`user_message` / `member_speaking` / `member_silent` / `member_post` /
   `member_failed` / `round_ended` / `slot_skipped`（`agent/team/orchestrator.py:440-474`、
   `:378-382`、`:403-409`），经 `web/server.py:146-149` 的 sink 进入 `RoomEventBus`
   （`web/team.py:86-121`），再由房间 WS 转发。
2. 连接建立时的 `room_state` 快照（`web/server.py:651-661`）：`workspace` / `room` /
   `members` / `timeline` / `round_active`，**没有 per-member 状态**。

成员会话内部的事件与钩子其实足够细分：

| 信号 | 时机 | 证据 |
|---|---|---|
| `run_started` | run 开始（**resume 分支不触发**） | `agent/loop.py:758-762`；钩子 `agent/hooks/manager.py:33-37`；resume 分支 `:709-743` |
| `before_iteration` | 每次 LLM 调用前 | `agent/loop.py:790`；`agent/hooks/manager.py:39-41` |
| `reasoning_delta` | 思维链增量（若 provider 返回） | `agent/loop.py:1272-1280` |
| `assistant_delta` | 可见回复流式增量 | `agent/loop.py:1282-1289` |
| `assistant_stream_complete` | 一次生成结束 | `agent/loop.py:1297-1309` |
| `before_tool_execute` | **工具真正开始**，带 `ToolCall.id` / `name` | `agent/loop.py:1417`；`agent/hooks/manager.py:47-49` |
| `after_tool_execute` | 工具结束 | `agent/loop.py:1447`；`agent/hooks/manager.py:51-58` |
| `on_completion` | run 正常完成 | `agent/loop.py:838-847`、`:1148`；`agent/hooks/manager.py:64-66` |
| `done` / `error` | run 终态 | `agent/loop.py:848-852`、`:1149-1153`；`web/session.py:2061-2073` |

但群聊 runner 没有连接：`WebSessionRunner.run` 调 `manager.run_session(session, message)` 时不传
`handle`（`web/session.py:2178-2228`，具体在 `:2203-2206`），`_run_session_locked` 的 drain 循环把
事件交给 `SessionEventChannel.broadcast`，没有订阅者时直接返回 0（`web/session.py:2125`、
`:420-437`）。所以这些信号当前全部被丢弃。

现状中与状态正确性直接相关的缺口（经 grill 独立核实后的准确口径）：

- **建会话失败没有成员终态事件**：`ensure_room_session` 抛异常时只写 system 日志并 `return`
  （`agent/team/orchestrator.py:415-423`），不发 `member_failed`；活动标签页会停在「忙」。
- **轮次取消没有 `round_ended`**：`_run_round` 的 `finally` 只 `self._rounds.pop(...)`
  （`:361-362`），`round_ended` 在正常路径 `:378-382`；取消（房间 WS 断开，
  `web/server.py:695-699`）会跳过它。
- **空产出不是生产路径缺口**：`WebSessionRunner.run` 已在返回前把空文本归一为 `silent`
  （`web/session.py:2226-2227`；`is_silent("")` 为真，`agent/team/runner.py:85-88`）。编排器
  `:475-477` 的空文本分支只对自定义 runner 可达。本 change 在编排器层补一条**防御性契约**
  （合成 `member_silent`），不把它当用户可见 bug。
- **`room_state` 没有 per-member 快照**：轮次中重连只能看到 `round_active`，看不到谁在忙
  （`web/server.py:651-661`）。

本 change 只增加**状态可观测性与展示**，不改变轮次/会话语义。

## Goals / Non-Goals

**Goals**

- 每个成员有独立、实时、由真实事件驱动的五档状态；工具状态带工具名；并发/同名工具正确聚合。
- 所有出口（发言/静默/失败/超时/回合结束/建会话失败/取消/意外异常）都能回到 `idle`；
  重连/第二标签页靠快照恢复，且跨轮/跨重连不乱序。
- 桌面左侧状态栏；移动端在 390px 视口下时间线仍可用；状态更新不重绘时间线。
- 旧服务端/旧前端双向兼容；不可观测的信号不假装。

**Non-Goals**

- 不做多成员真正并发（Q3 已确认 = A；当前编排器串行
  `agent/team/orchestrator.py:393-399`，规格 `openspec/specs/multi-agent-collaboration/spec.md:1267`）。
  本 change 的 per-member 模型为未来并发留出接口，但实现仍串行。
- 不做用户打断/轮次取消协议（`web/server.py:678-690`、`spec.md:1304`）。
- 不展示子 agent/workflow 内部阶段；不把子图内部事件回流到父会话。
- 非流式 provider 不显示 `typing`。
- 不转发 token 增量；不持久化状态；不写房间日志；不改记忆 review 与轮次终止判定。
- 不修「断线取消整轮」的既有语义（只保证状态正确 teardown）。

## Decision 1：五档状态模型与纯 reducer

状态：`idle` / `running` / `thinking` / `typing` / `tool`。优先级（高 → 低）：
**`tool` > `typing` > `thinking` > `running` > `idle`**。

### 1.1 每个状态的含义（只描述可观测事实）

| 状态 | 含义（可观测事实） | 进入信号 |
|---|---|---|
| `idle` | 无进行中的 slot，或本回合已收到终态 | 终态事件、轮次 teardown、快照缺失 |
| `running` | 成员在回合中，但当前没有更细的信号 | slot 认领（`ensure_room_session` 前）、工具集合清空后、`stream_complete` 后、`run_completed` |
| `thinking` | 有一次 LLM 调用在途，且尚未收到可见流式增量 | `run_started` / `before_iteration` / `reasoning_delta` |
| `typing` | 已收到本次生成的第一个可见流式增量 | 第一个 `assistant_delta`（每次 LLM 调用一次） |
| `tool` | 至少一个工具在执行 | `before_tool_execute` |

- `thinking` **不承诺**模型在「推理」：对非 reasoning 模型它表示「LLM 请求在途、还没出可见
  token」。resume 分支不触发 `run_started`，因此 `before_iteration` 是 `thinking` 的权威信号；
  resume 回合的首个状态可以是 `running → thinking`（`agent/loop.py:709-743` vs `:755`）。
- `typing` 表示「模型正在流式产出可见文本」，**不保证这段文本最终会发布**（可能先流「我查一下」
  再调工具）；UI 文案用「正在输入」而不是「正在发布」。

### 1.2 reducer 输入信号

web 层只产生**无内容**的信号（不含 delta 文本）：

```
slot_started            # 编排器内部，不进 runner
run_started             # 钩子；resume 时缺失
iteration_started       # before_iteration
reasoning_delta         # 每次 LLM 调用最多一个
assistant_delta         # 每次 LLM 调用最多一个
stream_complete
tool_started  {tool_id, tool_name}
tool_finished {tool_id, tool_name}
run_completed
```

`on_error` 钩子**不映射**为 run 错误：它在参数解析错误、Bash 异常/超时时触发
（`agent/loop.py:877`、`:1427`、`:1431`），且非 Bash 工具异常可能根本不触发它
（`:1434-1439` 的通用分支没有 try）。run 级失败由 runner 四态出口兜底（`agent/team/runner.py:8-16`）。

### 1.3 迁移规则（reducer 纯函数）

```text
reduce(current, signal):
  terminal/reset                 -> idle（清空在途工具）
  slot_started                   -> running（仅当前为 idle 时）
  iteration_started              -> 清空 active_tools；thinking（新 LLM 调用意味着上一批工具已结束）
  run_started / reasoning_delta  -> if active_tools non-empty: 保持 tool
                                    elif current in (typing, thinking): 保持
                                    else: thinking
  assistant_delta                -> if active_tools non-empty: 保持 tool
                                    elif current == typing: 保持
                                    else: typing
  stream_complete                -> if active_tools non-empty: 保持 tool
                                    elif current in (typing, thinking): running
                                    else: 保持
  tool_started(id, name)         -> active_tools[id] = name; tool
  tool_finished(id, name)        -> active_tools.pop(id, None)
                                    if active_tools non-empty: tool
                                    else: running
  run_completed                  -> if active_tools non-empty: 保持 tool
                                    else: running
  no change -> 返回 None（不产生事件）
```

- **工具按 `tool_call.id` 记账**（`name` 只用于展示）：同名并发工具不会互相抵消；
  预拒绝工具没有开始/结束钩子，不会进入集合。
- **`iteration_started` 无条件清空 `active_tools`**：一次新的 LLM 调用意味着上一批工具已经结束。
  这覆盖非 Bash 工具异常跳过 `after_tool_execute`、`asyncio.gather(..., return_exceptions=True)`
  吞异常后继续的路径（`agent/loop.py:1420-1439`、`:1447`、`:1500-1513`），避免工具状态卡死。
- **优先级不是全局 max**：`stream_complete` / `tool_finished` / `run_completed` 是显式降级；
  其他低优先级信号不能把 `tool` / `typing` 降下去。
- **每次 LLM 调用只产生一个 `assistant_delta` / `reasoning_delta` 进度信号**：web 层在
  `before_iteration` 清标志，收到第一个 delta 后置位；避免每个 token 都调用回调。
- **重置是「表实际变化才计数」的幂等操作**：`reset_member` 仅当该成员当前非 idle 时移除并
  递增 `status_seq`/标脏；成员已 idle 时是 no-op（不递增、不发射）。`reset_room_statuses` 同理：
  表为空时返回当前 seq、不标脏。这样终态后的 `_run_slot` finally 重置、`slot_skipped` 的兜底
  不会产生重复的空表事件，也不会让「相同表不重复」的测试与实现打架。

### 1.4 为什么把 reducer 放编排器层

`agent/` 不得 import `web/`（`agent/team/orchestrator.py:269`、`agent/team/runner.py:1-16`）。
reducer 只依赖 `(kind, data)` 信号，放在 `agent/team/` 可被纯单测覆盖，也便于未来并发编排复用。
web 层只负责把 AgentLoop 事件/钩子归一成信号，不解释优先级。

## Decision 2：SessionRunner 进度回调（而非合成句柄）

`SessionRunner` 协议（`agent/team/runner.py:63-75`）增加可选参数：

```python
async def run(
    self,
    session_id: str,
    message: str,
    *,
    timeout: float | None = None,
    silent_marker: str | None = None,
    on_progress: Callable[[str, dict], Awaitable[None]] | None = None,
) -> TurnOutcome: ...
```

- `RoomOrchestrator._run_slot` 把 `room_id` / `persona_id` 绑定进回调；reducer 与发射都在编排器。
- `_WorkspaceRunner.run`（`web/team.py:215-230`）透传；`WebSessionRunner.run`
  （`web/session.py:2178-2228`）把回调传给 `SessionManager.run_session`。
- `SessionManager.run_session` / `_run_session_locked` 增加可选 `progress`；**不传时行为完全不变**。
- 需要同步的实现共三处：`WebSessionRunner`（基础实现，`web/session.py:2178`）、
  `_WorkspaceRunner`（子类，`web/team.py:222`）、测试 `FakeRunner`
  （`tests/agent/team/test_orchestrator.py:35`）。

**备选：web 层合成 `ConnectionHandle` 收事件**。被拒绝：需要在 web 层反查
`session_id -> (room_id, persona_id)`，且合成句柄与真正的 WS 句柄共享同一广播出口，语义隐晦；
进度回调把「成员进度」与「连接事件」两种关注点分开，接口更显式。代价是协议多一个可选参数。

## Decision 3：web 层进度观察者与生命周期

在 `web/session.py` 增加一个轻量 `ProgressObserver`（内含实现 `agent/hooks/manager.py:16-27`
协议的 `ProgressHook`）。**钩子与 `on_event` 闭包共用同一个 observer 实例**，这样
`before_iteration` 重置的 `saw_delta` 标志能被闭包看到：

- `on_run_started` → `run_started`
- `before_iteration` → 清 `saw_delta` / `saw_reasoning`，发 `iteration_started`
- `before_tool_execute` → `tool_started(tool_call.id, tool_call.name)`
- `after_tool_execute` → `tool_finished(tool_call.id, tool_call.name)`
- `after_llm_call` / `on_error` / `on_completion`：`after_llm_call` 与 `on_error` 是 **no-op**；
  `on_completion` → `run_completed`。
- **`Hook` 是完整协议**（`agent/hooks/manager.py:14-27`，`HookManager` 直接调用每个方法）：
  `ProgressHook` 必须把全部 7 个方法实现为 no-op 或实际处理，不能只实现用到的几个。

AgentLoop 的流式事件没有对应钩子，因此在 `_run_session_locked` 已有的 `on_event` 闭包
（`web/session.py:2015-2016`）里旁路：

- `assistant_delta`：若本次迭代尚未发过，发 `assistant_delta` 信号（不转发 `delta` 内容）。
- `reasoning_delta`：同理发 `reasoning_delta`。
- `assistant_stream_complete`：发 `stream_complete`。
- `run_started` 用钩子，事件不旁路（避免重复信号）。
- `done` / `error` **不产生进度信号**，但它们是 runner 出口的权威来源：
  `_run_session_locked` 据此写 `session.last_turn`（`web/session.py:2061-2073`、`:2152`），
  `WebSessionRunner` 返回四态，编排器再发 `member_post` / `member_silent` /
  `member_failed`。这条既有链路不改；`done`/`error` 不转发到房间 WS。

**生命周期（硬要求）**：

- 在 `_run_session_locked` 进入时 `session.agent.hooks.hooks.append(progress_hook)`，
  在**覆盖整个 run 的 `try/finally`** 中按身份摘除（包括超时 `asyncio.wait_for` 取消与客户端
  取消）。现有 DebugHook 的摘除在 drain 循环之后、不是 `finally`（`web/session.py:2143-2148`），
  本 change 的 hook 不得复制该形态。
- 进度回调**永不抛出**：`ProgressHook` 的每个方法用 `try/except` 包住回调并记日志；
  进度失败 SHALL NOT 影响 run 结果或工具执行。
- 每次 run 使用**新实例**，不在 session 上跨 run 共享状态；`saw_delta` 等标志是实例字段。
- 测试覆盖「连续两次 run 只看到一组信号」与「回调抛异常不影响 turn」。

## Decision 4：事件协议、序号与顺序

### 4.1 `member_status` 携带完整状态表

```json
{
  "type": "member_status",
  "data": {
    "room_id": "r-1",
    "status_seq": 17,
    "statuses": [
      {"persona_id": "p-1", "phase": "tool", "tools": ["Bash", "Read"], "tool_count": 2},
      {"persona_id": "p-2", "phase": "thinking", "tools": [], "tool_count": 0}
    ]
  }
}
```

- `statuses` 是**当前完整非空闲状态表**；缺失成员 = `idle`。成员数是个位数到几十，事件只在
  变化时发，单条 < 1KB，全量快照换来的顺序鲁棒性值得。
- 之所以不用「每条只带一个成员 + 房间级 seq」：那会让客户端用房间级水位丢弃成员级事件
  （成员 A 的 seq 10 晚于成员 B 的 seq 11 会被误丢）。全量表让每个事件自足，客户端只按
  `status_seq` 比较整表，天然支持未来并发。
- `status_seq`：每房间一个单调计数器；每次状态变更（包括终态重置）递增。短窗口内的多次变化
  **允许合并**为一次携带最新完整表的 `member_status`；跳过的中间 seq 只表示中间状态未单独
  发布，最终状态始终与 `room_state` 快照一致。
- `phase` 只会是 `running|thinking|typing|tool`；**不发送 `phase = idle` 的成员条目**。
  成员变 idle 时，完整表会在下一次 `member_status` 中缩减（或由终态事件直接清除）；
  快照缺失即空闲。重置是幂等的（见 1.3）：已 idle 的成员不会产生额外事件。

### 4.2 既有事件只增字段

- `member_speaking`：增加 `status_seq`（当前值，不递增），供前端降级时做迟到判断。
- `member_post` / `member_silent` / `member_failed`：增加 `status_seq`（**重置后**的值）；
  `member_failed` 另增 `name`（成员显示名），修复客户端合成 system 条目用 `persona_id` 的
  问题（`web/static/group.js:268-274`）。
- `round_ended`：增加 `status_seq`；新增 teardown 值 `termination = "cancelled" | "error"`。
- 原字段不改；`slot_skipped` 不增加状态字段（该成员从未被置为忙）。

### 4.3 客户端排序规则

1. 维护 `lastStatusSeq`（初始 0）、`statuses`（persona_id → status）与 `connectionEpoch`。
2. **新建/重连房间 WS 时**：`connectionEpoch += 1`，把 `lastStatusSeq` 重置为 0；
   旧状态表在重连期间标记为「连接断开/可能过期」。服务端发送锁保证新连接的 `room_state`
   是首帧。**切换/关闭房间时**清空状态表与水位（状态按房间作用域，不能把房间 A 的成员状态
   短暂沿用到房间 B；`openRoom`/`closeRoom` 都要清）。
3. 收到 `room_state`：以快照**整体替换** `statuses`（缺失 = idle），把 `lastStatusSeq` 设为
   `data.status_seq ?? 0`；`round_active === false` 时清空全部状态。它是新连接的权威快照，
   即使 seq 比旧连接的更小（服务端重启后序号从 0 开始）也必须接受。
4. 收到 `member_status`：若 `status_seq <= lastStatusSeq` 丢弃；否则整体替换 `statuses` 并推进。
5. 收到终态事件：若带 `status_seq` 且 `< lastStatusSeq`，视为迟到并丢弃该**状态**影响；否则
   删除对应成员（`round_ended` 清全房间），并令 `lastStatusSeq = max(lastStatusSeq, seq ?? 0)`。
   注意：迟到的 `round_ended(termination = "limit")` 即使状态被丢弃，仍 SHALL 执行既有的
   「重拉时间线」动作（不改状态），否则达上限的 system 条目不会进入实时时间线。旧服务端无
   `status_seq` 时直接按终态清除（降级路径）。
6. 收到 `member_speaking` 降级信号：仅当该成员当前为 idle/未知、且其 `status_seq` 不旧于
   `lastStatusSeq` 时置为 `running`；不得把更细的状态降级。
7. `onmessage` 只处理当前 `connectionEpoch` 对应 socket 的事件，避免旧连接尾部事件污染。

**为什么终态也要按 seq 守卫**：`_run_round` 先 `_rounds.pop`（`:361-362`），再
`await review_sink.on_round_end(...)`（`:372-376`），最后才发 `round_ended`（`:378-382`）。
pop 与终态发射之间有真实 await 窗口，同房间另一条 WS 可以在这段时间开启新一轮并先发出
`member_status`；旧终态的 seq 更低，客户端必须丢弃它，否则会抹掉新一轮状态。服务端在 pop
之前**同步**重置状态并递增 seq，保证旧终态的 seq 严格小于新一轮首个状态事件的 seq。

### 4.4 发射器（合并、非阻塞）

- 编排器持有每房间 `statuses`、`status_seq`、`dirty`（是否有未发送的变化）、`emit_task`。
- 状态变更在**同步段**内完成（无 await）：更新 dict、递增 seq、标脏。
- `on_event is None` 时不创建发射任务（仍维护快照供测试/查询）；否则调度一个
  `asyncio.create_task`。编排器**看不到订阅者数量**（`RoomEventBus.subscriber_count` 在 web 层），
  不写「没有订阅者就不发」这种不可实现的判断；无人订阅时 broadcast 自然返回 0，成本可忽略。
- 发射任务循环：清脏标记 → 在**同一同步段**读取**当前完整表与当前 `status_seq`** →
  `await self._emit("member_status", payload)`；若期间又变脏则继续。表与 seq 必须一起读，
  不能捕获旧 seq 配新表。快照已回到 idle 的成员自然不在表里。
- 发射任务异常只记日志；`finally` 清任务引用。
- 提供私有 `async def _flush_status_emits(room_id)`：等待当前发射任务结束并循环处理期间新变脏
  的变化；测试用它拿到确定性事件。
- **终态事件顺序（所有出口同构，含正常 `round_ended`）**：同步重置（见 Decision 5）→
  `await _flush_status_emits(room_id)` → `await _emit(terminal, {..., "status_seq": seq})`。
  flush 等待已读旧表的在途发射任务完成，保证终态不会先于它被发送；即使取消路径的 flush 被
  打断、仍有旧 payload 在途，客户端也会按 seq 丢弃。正常路径也必须 flush，否则「终态前先
  flush」的声明与测试确定性不成立。

## Decision 5：编排器接入点与终态缺口

### 5.1 `_run_slot`

1. 成员仍在房间后、`ensure_room_session` 之前：`slot_started` → `running`（覆盖会话构造空窗）。
2. `ensure_room_session` 抛异常：写 system 日志（既有）+ 调用
   `_finish_member(persona_id, "member_failed", {status: "failed", reason: "会话不可用", name})`。
   与其它终态出口走同一 helper：同步重置 → 递增 seq（若表实际变化）→ flush → 用新 seq 发终态。
3. 调用 `runner.run(..., on_progress=bound_callback)`。
4. 出口处理的**统一 helper** `_finish_member(persona_id, event_type, data)`：
   同步重置该成员并递增 `status_seq` → `await _flush_status_emits` → 用该 seq 发终态事件。
   - `silent` → `member_silent`。
   - `failed` / `timeout` → system 日志（既有）→ `member_failed`。
   - `text` 且非空 → `member_post`。
   - `text` 且为空 → **防御性契约**：合成 `TurnOutcome(status="silent")` 并发 `member_silent`；
     生产 `WebSessionRunner` 已归一（`web/session.py:2226-2227`），该分支只对自定义 runner
     可达；记忆 review 仍按 silent 处理（与既有 `:475-477` 的局部替换语义一致）。
5. `_run_slot` 的 `finally` 无条件重置该成员（幂等；覆盖取消/意外异常/任何遗漏出口）。

### 5.2 `_run_round`：先同步重置，再释放房间认领

```text
teardown_seq = None
try:
    ... 写 user_message, await _drive(state) ...
    termination = compute_termination(state)       # 既有计算；若达上限，先写 limit system 条目
    teardown_seq = reset_room_statuses(room.id)   # 同步；表实际变化才递增 seq
    release_round(room.id, state)                  # 仅当 _rounds[room_id] is state 才删
    await _flush_status_emits(room.id)            # 终态前先冲掉在途旧表
    ... 既有 review 调度（内部已 try/except） ...
    await _emit("round_ended", {..., "status_seq": teardown_seq})
except asyncio.CancelledError:
    if self._rounds.get(room.id) is state:          # 仍持有认领才动房间
        if teardown_seq is None:
            teardown_seq = reset_room_statuses(room.id)
        schedule_teardown(room.id, teardown_seq, "cancelled")  # 强引用后台 task
    raise
except Exception:
    if self._rounds.get(room.id) is state:
        if teardown_seq is None:
            teardown_seq = reset_room_statuses(room.id)
        schedule_teardown(room.id, teardown_seq, "error")
    logger.exception(...)
    raise
finally:
    if teardown_seq is None and self._rounds.get(room.id) is state:
        teardown_seq = reset_room_statuses(room.id)
    release_round(room.id, state)                  # 身份校验的幂等兜底
```

**`release_round` 必须按身份释放**（高优先，对抗 R3 / X1）：

```python
def release_round(self, room_id: str, state: _RoundState) -> None:
    if self._rounds.get(room_id) is state:
        del self._rounds[room_id]
```

正常路径在 flush 之前释放认领，flush 期间另一条 WS 可以开启新一轮（`_rounds` 被新一轮
`state2` 重新认领）。若 `finally` 仍无条件 `pop(room_id)`，会把新一轮的认领删掉，导致
`room_state.round_active` 变 false、且下一条用户消息再开第三轮，两轮并发驱动同一房间。
所有释放点（正常路径与 finally）都必须用 `is state` 身份判断；测试要覆盖「R1 返回后 R2 仍
active，第三条消息 queued 进 R2」。

**取消/异常路径同样必须先确认认领归属**：旧轮在 flush/review 尾部已释放认领、新一轮已
认领后，旧任务仍可能被发起连接关闭而 `cancel()`。此时旧轮的 `except CancelledError` /
`except Exception` SHALL NOT 重置房间状态、SHALL NOT 发旧 teardown（否则会清掉新一轮状态）；
只有 `self._rounds.get(room_id) is state` 时才 reset/schedule teardown。`finally` 的兜底 reset
也带同一身份判断。测试覆盖「R1 已释放、R2 active，取消 R1 的收尾任务 → R2 状态与认领不受
影响」。

- **整个轮次主体**（含 termination 计算、review 调度与正常 `round_ended`）都在同一个异常兜底
  内；任何位置的意外异常在**仍持有认领**时走 `error` teardown，而不是只清内存、客户端停在忙；
  认领已释放时只记录并 re-raise，不影响新一轮。
- 已释放认领后的收尾窗口内，旧轮 `round_ended(limit)` 可能因 seq 更旧被客户端丢弃状态影响；
  limit 的 system 条目已写入房间日志，客户端在下一次 `room_state` / 重拉时间线可见。实时
  送达是 best-effort，实时可见性不是验收条件。
- **重置与 seq 递增发生在任何 await 之前**，且先于释放房间认领；新一轮的首个状态事件因此
  一定拿到更高的 seq，旧终态会被客户端丢弃。
- **termination 计算与 limit system 条目在 reset/pop 之前完成**（都是同步写），因此它一定
  排在任何新一轮用户消息之前；不会出现「新轮 user_message 先于旧轮 limit 条目」。
- 正常路径在 termination/reset/pop 之间**没有 await**；pop 与现状同序
  （`agent/team/orchestrator.py:361-362`），因此「轮次结束后用户再发消息可立刻开新一轮」的
  既有行为不变。flush、review 与正常 `round_ended` 的发送在 pop 之后，可能放行新一轮；
  旧终态的 seq 更低，seq 守卫已经覆盖。若实现把 flush 放在 pop 之前，会短暂阻塞新一轮
  （慢客户端），不推荐；设计按「先 pop 再 flush」实现，并在测试中锁住该顺序。
- 取消/意外异常**仅在仍持有认领**（`self._rounds.get(room_id) is state`）时使用**带强引用的
  后台 task** 发 teardown（`asyncio.create_task` + 集合保活 + done 回调清理）；认领已释放时
  只记录并 re-raise，不得发旧终态。任务内部先 `await _flush_status_emits(room.id)` 再
  `await _emit(...)`，整体用 `asyncio.wait_for(..., timeout=2)` 限界并记日志。不在已被取消的
  task 里直接 await 广播——那会被二次取消打断，而其他标签页正是唯一受众。
- teardown 的 `round_ended` 是 **status-only 通知**：不写房间日志、不产生 `RoundResult`、
  不是新增轮次出口（见 spec delta 的 MODIFIED Requirement）。旧前端对任何非 `limit` 的
  `round_ended` 走「本轮结束」分支（`web/static/group.js:276-288`），可平滑降级。
- 正常 `round_ended` 的 termination 计算与 `RoundResult` 字段不变。

### 5.3 快照查询

`RoomOrchestrator` 新增单一同步方法：

```python
def status_snapshot(self, room_id: str) -> tuple[list[dict], int]:
    # (非空闲状态表副本, 当前 status_seq)
    # 每项: {persona_id, phase, tools, tool_count}
```

返回副本；一次调用同时取表与 seq，避免未来在两者之间加入 await 后快照内部不一致。

## Decision 6：`room_state` 快照与房间 WS 发送顺序

`room_state.data` 增加：

```json
"member_statuses": [{"persona_id": "p-1", "phase": "tool",
                     "tools": ["Bash"], "tool_count": 1}],
"status_seq": 17
```

`round_active` 保持既有字段；`round_active = false` 时客户端清空全部状态。

**握手结构（修正现状 `web/server.py:651-661`）**：

```python
send_lock = asyncio.Lock()
async def send(payload):
    async with send_lock:
        await ws.send_json(payload)

token = None
try:
    await send_lock.acquire()
    try:
        payload = build_room_state()      # 持锁、同步构造：快照与 seq 一致
        token = room_bus.subscribe(room_id, send)
        await ws.send_json(payload)       # 快照第一帧
    finally:
        send_lock.release()
    ... 消息循环 ...
finally:
    if token is not None:
        room_bus.unsubscribe(room_id, token)
    ... 取消 rounds ...
```

- **快照必须在持锁后、订阅前构造**：构造与订阅之间没有 await，订阅前发生的事件已经反映在
  快照里；订阅后的事件会等待发送锁，保证在快照之后到达。
- 订阅后**所有**发送（含 `pong`）SHALL 走同一个加锁 `send` 包装，避免与广播并发写同一
  WebSocket 造成帧交错。
- **订阅与快照发送都在 `try/finally` 内**：现状的 `subscribe` + 快照发送在 `try` 之前
  （`web/server.py:651-661` vs `:662`、`:695-696`），握手中途抛异常不会走既有 unsubscribe，
  会留下悬挂订阅。本 change 显式修正。
- 快照只包含当前 `room.members` 中 `phase != idle` 的成员；其他条目过滤掉。
- `room_state` 是连接首帧，客户端以它重置状态表与水位（Decision 4.3）。

## Decision 7：前端桌面形态与 DOM

- **DOM 结构**（解决「移动端出现房间头部之上」与 chip 行承载公告的问题）：

  ```html
  <main class="group-main">
    <div id="group-empty">...</div>
    <div id="group-room" hidden>
      <header class="group-room-head">...</header>
      <div id="group-room-notice" class="group-notice" hidden></div>
      <div class="group-room-body">
        <aside id="group-room-presence" class="group-presence" aria-label="成员状态"></aside>
        <div id="group-room-timeline" class="group-timeline"></div>
      </div>
      <div class="group-input-row">...</div>
    </div>
  </main>
  ```

  - presence 在 `#group-room` 内部、房间头部**之后**；桌面 `.group-room-body` 用 flex：
    presence `208px` + timeline `flex:1; min-width:0`。视觉上仍是「管理侧栏 | 成员状态 |
    时间线」三列，但 DOM 嵌套在 main 内，移动端可以自然排成「头部 → 公告 → 状态条 →
    时间线 → 输入框」。
  - ≤1000px：管理侧栏收成抽屉（`群聊/人设` 按钮）；presence 列 176px。
  - ≤720px：`.group-room-body` 改纵向；presence 按 Q1 选定形态改为横向条/抽屉/底部条。
  - **群公告**从 `renderMembers()`（`web/static/group.js:318-323`）移到独立的
    `#group-room-notice`，由 `renderNotice()` 维护；presence 取代 chip 行不能把公告弄丢。
  - **不把 `#group-room-status` 当 presence 摘要**：它已被 `setStatus()` 用于连接/错误/
    轮次提示（`group.js:369-372`，调用点 `:218`、`:230`、`:254`、`:278`、`:393`）。
    presence 自身就是状态展示；连接/操作提示继续留在头部，两者不互相覆盖。
  - **删除 `member_speaking` 的头部「X 正在发言...」文案**（现状 `group.js:252-254`）：成员
    状态完全交给 presence。否则静默/失败后头部会残留「甲 正在发言...」，与 presence 的
    「甲 空闲」直接矛盾。`member_silent` / `member_failed` / `member_post` 因此也不需要清头部；
    `round_ended` 的「本轮结束」只在终态未被 seq 守卫丢弃时更新头部（复用同一分支），避免
    旧轮终态在新轮开始后改写头部。`state.speaking` 可一并移除；旧服务端降级时 presence 仍
    通过 `member_speaking` 把成员置为 running。
  - **轮次提示的清除**：`setStatus(text, kind)` 增加 `kind ∈ {conn, round, op}`；收到新一轮的
    `user_message`（`queued=false`）或首个非空闲 `member_status` 时调用 `clearRoundStatus()`，
    只在当前 `kind === "round"` 时清空「本轮结束 / 本轮因达上限结束」；连接/错误/操作提示
    （`conn`/`op`）不被轮次清除。`op`（例如「发送失败」）在**下次成功发送或连接成功后**
    清除；`conn` 由下一次连接事件替换。否则新一轮 presence 已显示成员忙，头部仍写
    「本轮结束」，或反过来把「连接断开」误清掉，或让「发送失败」永久残留。
- 每行：28px 首字母色块头像（复用 `hueFor()`，`web/static/group.js:361-367`，与时间线
  `--group-hue` 同色）+ 名字 + 状态文案；admin 标记并入状态行。
- 状态文案：
  - `空闲`（muted）
  - `运行中`（accent）
  - `正在思考`（info）
  - `正在输入`（success）
  - `正在使用工具 · Bash`；多个：`正在使用工具 · Bash、Read（2 个）`（warning）
- presence **取代**现有成员 chip 行（`index.html:188`、`group.js:306-324`）；按
  `state.members` 顺序渲染，状态表里不在当前成员列表的条目忽略。
- 独立渲染：新增 `renderMemberPresence()`，只重建 presence 列表；状态事件**不调用**
  `renderRoom()`（该函数会重绘时间线并滚到底，`group.js:331-359`）。
- **时间线追加按 seq 幂等**：`user_message` / `member_post` 的 entry 带 `seq`；追加前若
  `state.timeline` 已有同 seq 条目则跳过。这既防止重复投递，也覆盖 `round_ended(limit)` 的
  整体重拉与随后到达的事件之间的竞态（重拉已包含的条目不会再次追加）。
- **presence 重绘不重置横向滚动**：`renderRoom()` / 时间线事件触发的 presence 重绘要保存并
  恢复状态条的 `scrollLeft`（或按成员 keyed 更新），不能把用户滑到的位置重置到最左。
- **迟到重拉不覆盖已切换房间**：`round_ended(limit)` 的异步时间线重拉在 `.then` 里应用前
  校验 `state.activeRoom.id`（或 `connectionEpoch`）仍是发起时的房间；否则丢弃响应。
- **脚本加载顺序/缓存**：`group_status.js` 必须在 `group.js` 之前加载，两个 `?v=` 都递增
  （现状 `web/static/index.html:223` 是 `group.js?v=2`）；浏览器 smoke 断言
  `window.AsterwyndGroupStatus` 存在。

## Decision 8：移动端形态（Q1 已确认 = A）

前置（三个方案共同）：≤720px 时管理侧栏变成 off-canvas 抽屉（房间头部/视图顶部一个
`群聊 / 人设` 按钮，遮罩关闭）；主区占满宽度（390px 下约 366px）。presence 在
`#group-room` 内部、房间头部之后，因此移动端顺序天然是「头部 → 公告 → 状态 → 时间线 →
输入框」。

- **头部收纳**：390px 下头部已有群名、`#group-room-status`（`flex:1`）、设置、删除
  （`index.html:181-187`、`style.css:2141`），再加抽屉按钮会溢出。设置/删除 SHALL 收进
  图标按钮或「更多」菜单；群名可截断；浏览器测试断言
  `document.documentElement.scrollWidth <= window.innerWidth`（无横向溢出）。
- **空状态**：侧栏抽屉化后 `#group-empty` 的「从左侧选择或新建一个群聊」（`index.html:180`）
  不再成立；移动端改为「点左上角「群聊」打开列表」或在该区域直接提供抽屉入口。

### 方案 A：顶部横向成员条（推荐）

- 位置：房间头部/公告下方、时间线上方；`height: 56px`；`overflow-x: auto`，
  `scroll-snap-type: x proximity`；每项 `min-width: 104px`，头像 28px + 名字/状态两行
  （12px / 11px）；触控目标 ≥44px。
- 交互：横向滑动查看全部成员；当前非空闲成员变化时**只调整状态条容器自身的 `scrollLeft`**
  （或 `scrollIntoView({inline:"nearest", block:"nearest"})`），且仅在目标项超出可视区时滚动；
  不得纵向滚动页面/时间线（默认 `block:"start"` 会打断用户阅读）。只在 phase 变化时触发，
  不是定时器；点击成员项可展开小浮层显示完整工具名。
- 390px 下约 3 个成员可见（5 人房间需滑动一次）；时间线剩余高度约减少 56px。
- 优点：所有成员始终可见、无需额外点击、最接近「真实聊天室成员列表」。
- 缺点：占 56px 垂直空间；成员多时要横向滑动；名字/状态需截断。

### 方案 B：可折叠抽屉

- 位置：房间头部下方一条 36px 摘要条（`5 名成员 · 甲 正在使用工具 Bash`），点击展开
  bottom sheet（`max-height: 60vh`，拖拽把手，遮罩关闭）；sheet 内每成员一行。
- 交互：摘要条始终显示最高优先级的非空闲成员（全空闲时显示 `全部空闲`）；展开后实时更新。
- 优点：时间线获得最大垂直空间；成员多时列表完整。
- 缺点：默认看不到每个人，需要一次点击；折叠态只能看到摘要。

### 方案 C：底部助理条

- 位置：输入框上方，`height: 44px`；只显示非空闲成员（头像 + 名字 + 状态），全空闲时显示
  28px 的 `全部空闲`；右侧 `全部成员` 按钮打开完整列表。
- 优点：最省空间；只呈现「正在发生的事」。
- 缺点：默认不满足「每个成员一行」；空闲成员不可见；需要第二次交互才能看全。

**用户已确认 A**：本 change 的核心价值是「每个成员实时可见」，A 以最小交互成本满足它；
56px 在 390×844 的视口里可接受，且与桌面 presence 共享同一套渲染/排序逻辑。实现与浏览器
smoke 必须按 A 落地：横向条可见约 3 人、可滑动、时间线让出 56px。

## Decision 9：旧服务端降级、断线与可访问性

- **新前端 + 旧服务端**：没有 `member_status` 时，`member_speaking` 把该成员置为 `running`
  （仅当 idle/未知），终态事件回 `idle`；头部提示仍可用。`status_seq` 缺失时按 0 处理。
- **旧前端 + 新服务端**：`group.js` 的 switch 对未知类型落 `default: break`
  （`web/static/group.js:289-290`），新事件被忽略；既有事件新增字段也被忽略；`round_ended`
  的 teardown 值走既有「本轮结束」分支（`:276-288`）。
- **断线**：`onclose` 后保留最后已知状态但标记为过期/灰显，并显示「连接断开，重连中...」；
  重连成功后以 `room_state` 快照整体替换（Decision 4.3）。既有 2s `setTimeout`
  （`group.js:228-235`）只用于连接重试，不是状态定时器。
- **可访问性**：状态用文字 + 颜色 + 形状（不要只靠颜色）；新增一个视觉隐藏的
  `#group-presence-live`（`aria-live="polite"`），只在某成员 phase 变化时写入单条文案
  （例如「甲 正在使用工具 Bash」）；**不要**把 `aria-live` 挂在会整体重绘的列表容器上。
  动效（脉冲/省略号）仅在 `prefers-reduced-motion: no-preference` 下启用；头像色块
  `aria-hidden`，名字是文本；长工具名 `text-overflow: ellipsis` + `title`。
- **`member_failed` 文案**：服务端新增 `name` 字段；前端合成 system 条目优先用
  `data.name`，否则用 `speakerName(data.persona_id)`。明确 `member_failed` 的语义已扩展到
  「回合失败/超时」与「建会话失败」两类。

## Decision 10：前端纯函数模块与测试缝

新增 `web/static/group_status.js`，暴露 `window.AsterwyndGroupStatus`：

```js
createStatusState()                    // {statuses:{}, seq:0}
applyStatusEvent(state, data)          // member_status：按 seq 整体替换 → {state, changed, applied}
applyTerminal(state, data)             // 终态：按 seq 删除/清空 → {state, changed, applied, clearedAll}
applySnapshot(state, data)             // room_state：整体替换并重置 seq → {state, changed, applied:true}
applySpeakingFallback(state, data)     // 旧服务端降级，仅 idle/未知时 running → {state, changed, applied}
formatPhase(phase, tools, count)       // 中文文案
describeChange(prev, next)             // aria-live 单条文案或 null
```

返回契约固定：apply* 不原地修改入参；`applied=false` 表示事件因 seq 过期被丢弃，调用方据此
**不**更新头部/aria-live（但 `round_ended(limit)` 的时间线重拉仍执行，见 Decision 4.3）。
`group.js` 只负责 DOM 渲染与 WS 分发；纯函数可在 node + vm 中单测（复用
`tests/web_tests/test_workflow_graph_js.py` 的 harness），不依赖浏览器。

## Edge cases

| 场景 | 期望 |
|---|---|
| 空产出回合 | 生产 runner 已归一为 silent；编排器防御性发 `member_silent`，状态 idle |
| 建会话失败 | 发 `member_failed`（带 name），状态 idle；system 日志照旧 |
| 单轮超时（240s） | runner 返回 `timeout` → `member_failed` → idle |
| 轮次取消/房间 WS 断开 | 同步重置 + seq++ → 后台 task 发 `round_ended(cancelled)` |
| 意外异常（`_run_round` 内） | 同步重置 + seq++ → 后台 task 发 `round_ended(error)` → 异常上报 |
| 并行工具 | 按 `tool_call.id` 记账；`tools` 去重 + `tool_count`；全部结束才回落 |
| 同名工具并发 | 两个 id 各自记账，互不抵消 |
| 非 Bash 工具异常跳过 after 钩子 | 下一次 `iteration_started` 清空 active_tools，不会卡在 tool |
| 工具错误后继续 | 正常 `after_tool_execute` 回落；`on_error` 不改变状态 |
| 工具被预拒绝 | 不触发开始钩子，状态可能停在 thinking 到下一次迭代（事实，不假装） |
| 记忆压缩 | 工具结束后到下一次 `before_iteration` 之间显示 running |
| 非流式 | 无 typing；thinking 直到下一个信号/终态 |
| 流式文本后调工具 | typing → tool（工具优先） |
| resume 回合 | 无 `run_started`；`before_iteration` → thinking |
| 重连/第二标签页 | `room_state.member_statuses` 恢复；重置水位；缺失 = idle |
| 服务端重启 | 新快照 seq 从 0 开始；客户端接受并重置水位 |
| 多标签页订阅 | 同一事件广播给所有连接；每连接独立发送锁 |
| 旧服务端 | `member_speaking` 兜底 running；终态 idle |
| 成员中途被移出 | 不启动 slot（`slot_skipped`）；渲染按当前 members 过滤 |
| 房间被删 | 状态表随 round finally 清理；视图隐藏 |
| 进程重启 | 状态为空；`round_active=false` → 全部 idle |
| 握手失败 | try/finally 保证 unsubscribe；无悬挂订阅 |

## Testing Strategy

### 1. 纯函数 reducer 单测（无 provider、无 asyncio）

新增 `tests/agent/team/test_member_status.py`：

- 优先级：typing 后 tool_started → tool；tool 期间 assistant_delta/iteration_started 不降级；
- 并发工具：不同 id 的 Bash+Read、同名 Bash 两个 id、集合清空回落 running；
- `iteration_started` 清空残留 active_tools（模拟非 Bash 异常跳过 after）；
- `stream_complete` 从 typing → running；`run_completed` 在有工具时保持 tool；
- 无变化返回 None；
- 终态 reset 清空工具与 phase；
- `status_seq` 分配（编排器层测试）。

### 2. 编排器集成测试（FakeRunner 发出可控进度信号）

扩展 `tests/agent/team/test_orchestrator.py`：

- 正常回合约：`running`（slot_started）→ thinking → typing → tool(Bash) → running →
  thinking → 终态；断言**终态后的快照（表为空 / 与 `status_snapshot()` 一致）**与关键子序列
  （事件流中曾出现 thinking/tool 等），不要求每个迁移都单独发（允许合并）；
- `member_status` 只在变化时发；相同表不重复；`status_seq` 单调；
- 空产出（FakeRunner 返回 text/空）→ `member_silent` + idle（防御性契约）；
- 建会话失败 → `member_failed`（带 name）+ idle；
- 取消 gated run → `round_ended(cancelled)` + `status_snapshot` 空；
- `_run_round` 内意外异常 → `round_ended(error)` + idle（用可抛异常的 FakeRunner/日志）；
- **跨轮迟到终态（F2）**：注入阻塞的 `review_sink`，在 round 1 已 reset+pop、旧
  `round_ended` 尚未发出时启动 round 2，等其首个 `member_status`；放行 review 后断言旧
  `round_ended.status_seq` 严格小于新轮首个 status_seq。JS 侧另测：先应用新状态（seq 20）
  再喂旧终态（seq 18），断言终态被丢弃、新状态保留。两块分别做变异验证（去掉
  reset-before-pop / 去掉 JS seq 守卫 → 变红）；
- **收尾窗口不吞新消息 + 认领身份（N1 / X1）**：用一次性、有界等待的 gate 阻塞
  `_flush_status_emits`（或让在途 emitter 卡在慢 send），在 round 1 已 reset+pop、flush 未完成
  时提交 M2；断言它**开启 R2**而不是排队进已结束的轮次，且 R2 status_seq 更高；放行 R1 的
  flush 后断言 R2 仍 active（`round_active=true`），M3 被 queued 进 R2 而不是开启 R3。
  把 pop 移回 flush 之后、或去掉 `is state` 身份判断 → 测试变红；
- **旧轮收尾任务在释放后被取消（X1 延伸）**：R1 已释放认领、R2 active，取消 R1 的收尾任务；
  断言 R2 的状态表、认领与 `round_active` 不受影响，且没有旧 `round_ended(cancelled)` 发出；
  去掉 except 路径的身份判断 → 测试变红；
- **正常 path 无重复空表**：断言一个正常回合的 `member_status` 序列没有相同表重复、seq 单调；
- 并行工具聚合（FakeRunner 用 `asyncio.gather` 调 `on_progress`）；
- resume 语义：首个 thinking 来自 `iteration_started`，不依赖 `run_started`；
- 记忆 review 仍按 silent/failed/text 语义触发。

更新 `FakeRunner.run` 签名接受 `on_progress`；`test_runner_contract.py` 只保留四态/常量，
`on_progress` 的「不传行为不变」「回调抛异常不影响 turn」放到 `test_group_chat_team.py`
或 `test_orchestrator.py`（与既有 docstring 口径一致）。

### 3. WebSocket / Web 集成测试（`ScriptedLLM`，无真实 provider）

扩展 `tests/web_tests/test_group_chat_server.py` 与 `test_group_chat_team.py`：

- **web 层映射（T1，不能省）**：在 `test_group_chat_team.py` 用**真实** `WebSessionRunner`
  （真实 `AgentSession` + `ScriptedLLM(stream=True)` + 一次工具调用）加 `on_progress`
  collector，断言 `iteration_started`、**每次** LLM 调用各一个 `assistant_delta`（脚本让
  两次调用都产生可见 delta：第一次 `content + tool_calls`，第二次流式文本）、
  `stream_complete`、`run_completed`、`tool_started` / `tool_finished` 的 id/name。
  FakeRunner 直接调用 `on_progress` 绕过 `ProgressObserver` / `ProgressHook` / `on_event`
  旁路，不能替代这一层；删掉 `before_iteration`、`assistant_delta` 接线，或删掉
  `before_iteration` 里的 `saw_delta` 复位 → 测试必须变红（变异验证）。
- 用 `ScriptedLLM(stream=True)` + `StreamScript`（`tests/support/llm_harness.py:27`）让成员
  先思考再流式出字。**注意合并发射器的让出点**：`StreamScript` 连续 yield 时事件循环没有
  让出点，发射器只会在让出时读取当前表，可能只看到最终 `running`/终态后的空表。因此：
  - WS 层确定性断言事件流中**至少出现过 `tool` 状态**，且回合结束后的状态（最后一条完整表 /
    `status_snapshot()`）与快照一致；不要求「最后一条表仍含 tool」；
  - thinking → typing 的中间态断言放在**编排器/FakeRunner 层**（每个 `on_progress` 后
    `await asyncio.sleep(0)`，让发射器跑一次）；
  - 如需在 WS 层看中间态，用带 `await asyncio.sleep(0)`/显式 gate 的慢速脚本 LLM，
    不要用无让出点的 `StreamScript`。
- 脚本化 LLM 返回一次工具调用（Bash `sleep`），断言 `tool` + 工具名；工具结束后回 running；
- 非流式（`ScriptedLLM(stream=False)`）断言**没有** typing；
- 在一个成员被 gated 的 run 中打开第二条房间 WS：首帧是 `room_state`，`member_statuses` 含
  该成员的 phase；`status_seq` 与实时事件一致；
- **握手顺序（F2）**：把「取锁 → 持锁构造快照 → 订阅 → 发首帧 → 释放锁」抽成可单测的
  async helper（或用可阻塞 `send` 的 fake）：首帧发送阻塞期间调用 `room_bus.broadcast`，
  断言广播发送被锁挡住、首帧先到；把实现改回「先 subscribe 再 await 发快照」或去掉锁 →
  测试变红（变异验证）；
- 双标签页 + 关闭发起连接的 WS：另一连接收到 `round_ended(cancelled)`（或重连快照为 idle）；
- 握手失败：monkeypatch 快照发送抛异常，断言订阅被清理（`subscriber_count == 0`）；
- 现有「最多 12 条事件」循环（`test_group_chat_server.py` 的 `test_room_state_then_round_events`）
  改为「收集到 `round_ended` 为止」并设安全上限（如 64）。

### 4. 前端纯函数单测（node + vm）

新增 `tests/web_tests/test_group_status_js.py`：

- 全量表按 seq 替换、迟到 seq 丢弃、终态按 seq 删除、快照重置水位（含 seq 变小）、
  旧服务端降级（`member_speaking` 仅在 idle 时 running）、`formatPhase` 文案；
- `statuses` 中缺失成员视为 idle。

### 5. 浏览器 smoke（Playwright）

新增 `tests/web_tests/test_group_status_browser.py`（群聊专用 fixture；可复用
`test_workflow_graph_browser.py:35` 的 `fake_web_server` 模式，但需提供 `/ws/room` 与 team API）：

- 桌面 1200×800：presence 三列可见，时间线宽度 > 400px；`window.AsterwyndGroupStatus` 存在；
- 手机 390×844：管理侧栏折叠为抽屉，presence 按选定形态显示，时间线宽度 > 300px；
  **无横向溢出**（`scrollWidth <= innerWidth`），设置/删除收纳后头部不挤出屏幕；
- 空状态在移动端提供可见的抽屉入口；
- 通过真实房间 WS 推送 `member_status`（`room_bus.broadcast` 需
  `asyncio.run_coroutine_threadsafe` 调度到 uvicorn loop；或慢速脚本 LLM），断言状态文字随
  事件变化；
- 迟到的 `round_ended(limit)` 即使 `applied=false` 仍触发时间线重拉；
- 发送失败提示（`op`）在下一次成功发送/连接成功后清除；断线时状态标记为过期（class/属性）；
- 自动滚入前后时间线 `scrollTop` 不变；
- **反定时器断言**：推送一条状态后等待 **3s**（覆盖既有 2s 重连节奏与常见轮询间隔），
  无新事件时状态不变；
- 群公告在 presence 取代 chip 行后仍可见；
- `aria-live` 专用区域只在 phase 变化时写入单条文案（断言其文本变化，不依赖屏幕阅读器）；
- `prefers-reduced-motion` 下无动画（断言 class/属性）。

### 6. 验收命令

- `uv run pytest -q tests/agent/team tests/web_tests/test_group_chat_server.py tests/web_tests/test_group_chat_team.py tests/web_tests/test_group_status_js.py`
- `uv run pytest -q`（全量）
- `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`
- `uv run python scripts/check_openspec_artifacts.py --base-ref origin/master --require-base`
- benchmark smoke：**checker 会触发**——proposal 的证据引用里出现了 `` `agent/loop.py:...` ``，
  命中 `scripts/check_openspec_artifacts.py` 的 `BENCHMARK_SMOKE_CODE_PATTERNS`。实现收尾必须跑
  `uv run asterwynd benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/smoke-307`
  并记录结果（本 change 不修改 `agent/loop.py`，但门禁按文本触发，不做豁免）。

## Alternatives Considered

1. **定时器/租约驱动状态**（业界 typing 的常见做法）：拒绝。用户明确禁止定时器伪造；本仓能
   观测 run 生命周期，租约只会引入「事件停了但状态还在」的假状态。业界租约用于「客户端只知道
   用户开始输入、不知道何时停」，与本场景不同。
2. **转发 `assistant_delta` 到房间 WS，由前端自行归约**：拒绝。真实流式一轮几十到上百条，
   `RoomEventBus.broadcast` 逐连接 `await`（`web/team.py:112-121`），多订阅者会放大带宽与
   回压；且状态语义会分散到前端。
3. **每条 `member_status` 只带一个成员 + 房间级 seq**：拒绝。房间级水位套成员级事件会误丢
   （见 Decision 4.1）；全量表更简单且为并发留出接口。
4. **在 web 层挂合成 `ConnectionHandle` 收会话事件**：拒绝，见 Decision 2。
5. **在 `tool_call` / `tool_result` 事件上做工具状态**：拒绝。两者都在工具**结束后**才发
   （`agent/loop.py:1013-1014` → `:1075-1089`），无法表示「工具正在跑」；必须用
   `before_tool_execute` / `after_tool_execute`。
6. **每条状态变化直接 `await room_bus.broadcast`**：拒绝作为唯一路径。钩子在工具执行路径上，
   慢客户端会拖慢工具；用合并发射器把广播移出钩子，终态事件仍走既有权威路径。
7. **把状态快照写进房间日志/持久化**：拒绝。状态是运行期投影，重启后没有意义。
8. **在成员 chip 上叠加状态而不是新增状态栏**：拒绝。用户已拍板左侧成员状态栏；chip 与状态栏
   并存会出现两处状态不一致。chip 行由 presence 取代，群公告移到独立元素。

## Risks

- **Hook 泄漏/重复触发**：必须逐 run 挂/摘，`finally` 覆盖取消；测试用「连续两次 run 只收到
  一组信号」验证。
- **回压**：合并发射器只保证状态发射不阻塞工具；终态事件仍 await 广播。若慢客户端拖慢终态，
  与既有 `member_post` 行为同源，本 change 不新增协议级超时（登记为既有风险）。
- **乱序/跨轮**：全量表 + `status_seq` + 终态按 seq 守卫；服务端在 pop 前同步重置。测试覆盖
  双标签页与跨轮到达。
- **快照竞态**：发送锁 + `room_state` 首帧 + 客户端水位重置；集成测试覆盖「run 中打开第二连接」。
- **事件量**：只在变化时发、允许合并；无工具回合约 4-6 条，每工具 +2 条；全量表单条 < 1KB。
- **中间态可能被合并掉**：发射器在事件循环让出时读当前表；若 provider/脚本 LLM 在一轮内
  没有让出点，`thinking`/`typing` 可能不会单独成事件。这是 spec 允许的合并，不是丢终态；
  测试必须按 M1 的口径分层（WS 只断言最终表/工具态，中间态下移到编排器层）。
- **取消 teardown 投递**：后台强引用 task + 2s 上限；若事件循环关闭仍可能丢失，客户端重连
  快照兜底。测试覆盖双标签页。
- **移动端改动面**：触及现有群聊布局；必须用 390px 浏览器测试锁住「主区可用」与群公告、
  输入区不被挤掉。
- **不可观测信号的误标**：非流式无 typing、预拒绝工具无开始、子 agent 内部不可见；文档与 UI
  文案都必须如实（`thinking` 是「LLM 在途」而非「模型在推理」）。
- **规格语义**：teardown 的 `round_ended` 容易误读为第四个出口；spec delta 用 MODIFIED 明确
  它只是状态通知，不写日志、不产生 `RoundResult`。
- **浏览器 fixture 成本**：群聊 WS/team API 的假服务器需要新建 fixture，工作量高于复用
  workflow 的 fixture；任务中单列，避免实现期低估。

## Impact Analysis

（与 proposal 的 Impact Analysis 同口径；此处补实现边界）

- 新增代码集中在 `agent/team/`（reducer/发射器/协议扩展/teardown）、`web/session.py`
  （进度观察者）、`web/server.py`（快照/发送锁/握手 try-finally）、
  `web/static/group_status.js`（纯函数）与 `group.js`（渲染/降级）。
- 不修改 `agent/loop.py`：工具开始/结束用既有钩子，流式用既有事件。
- 不修改房间日志 schema、记忆 review、轮次终止判定、`SessionRunner` 四态语义。
- 测试不需要真实 provider：`ScriptedLLM` + FakeRunner + Playwright fake server。
- 文档影响：backlog、architecture 群聊小节、README/README_EN（如需）、面试讲稿（建议）。

## Open Questions

> 以下三条已于 2026-10-20 停轮由用户确认，**全部选 A**；生效口径见下一节
> `## User Rulings (2026-10-20)`，逐条答复记录在 `reviews/grill-design.md` 的
> `## User Confirmation`。本节保留原始问题与选项以存证。

### Q1（必答）：移动端成员状态的呈现形态

**场景**：390×844 手机，房间 5 名成员（甲/乙/丙/丁/戊），甲正在跑一个 1.2s 的 Bash，其余空闲。
现状群聊主区约 94px；共同前提是管理侧栏折叠为抽屉、主区约 366px，presence 位于房间头部之后。

- **A（推荐）顶部横向成员条**：56px，每项 104px（头像 28 + 名字/状态两行），横向滑动，
  甲的状态变化时自动滚入；390px 下约 3 人可见，5 人需滑一次。所有成员始终可见，无需点击；
  代价是时间线少 56px。
- **B 可折叠抽屉**：默认 36px 摘要「5 名成员 · 甲 正在使用工具 Bash」，点击展开 60vh
  底部列表；折叠态看不到每个人，展开后完整。
- **C 底部助理条**：输入框上方 44px，只显示甲（非空闲），全空闲时 28px「全部空闲」；右侧
  「全部成员」打开完整列表；默认不满足「每个成员一行」。

**推荐 A**：最贴合「每个成员实时可见」，交互成本最低；B 适合更在意垂直空间的用户，C 适合
只关心「谁在忙」的用户。

### Q2：失败/超时是否在状态栏保留可见标记

**场景**：甲调用工具超时（240s），`member_failed {status: "timeout"}` 到达；时间线会新增一条
`成员 甲 运行失败：超时` 的 system 条目。状态栏怎么处理？

- **A（推荐）立即回 `空闲`**，不在状态栏保留失败标记；错误只在时间线。五档状态语义干净，
  不需要额外清除规则。
- **B 保留「上次失败」红色标记**，直到甲下一次进入运行（或用户重新进入房间）；事件驱动、
  不用定时器，但这是第六种展示态，需要定义清除与刷新规则。

**推荐 A**：issue #307 的五档状态不含失败态，错误信息已由时间线承载；B 可另立 follow-up。
选 A 时一并使用 `member_failed.name` 修正时间线条目（现状用 `persona_id`）。

### Q3（需求解释，需确认）：issue 的「多成员并发」

**场景**：房间 3 名成员，用户发「@甲 @乙 @丙 各自说说」；当前编排器严格串行
（`agent/team/orchestrator.py:393-399`），甲完整跑完（1.2s 工具 + LLM）才轮到乙，任何时刻
只有一行非空闲。issue 的需求方向 3 写「多成员并发：一轮里多个成员各自有独立状态；不是
全局只有一个人正在发言」；设计把它列为 Non-Goal（每人独立一行、串行执行），但这是对 issue
的一种解释，且规格 `openspec/specs/multi-agent-collaboration/spec.md:1267` 钉死了「同一时刻
至多一个成员在发言」。

- **A（推荐）接受「每人独立一行、串行执行」**：本 change 只做状态可观测性与展示；真正的
  并行是编排语义变更，另立 change 并修改规格 1267。
- **B 在本 change 内改编排为并行**：违反现有规格、放大成本与失败面，不建议。

## User Rulings (2026-10-20)

- **Q1 = A（移动端形态）**：采用顶部 **56px 横向成员条**，每项 104px；390px 下约 3 人可见、
  可横向滑动看全；时间线相应让出 56px。这是实现与浏览器 smoke 的生效口径。
- **Q2 = A（失败标记）**：超时/失败后**立即回空闲**，错误只在时间线显示；不新增「上次失败」
  展示态。`member_failed` 回 idle 并用 `name` 修正时间线文案。
- **Q3 = A（多成员并发的解释）**：接受「每人独立一行、但**串行执行**」；真正的并发不在本
  change，另立 change 并修改规格 1267。本 change 的实现 SHALL NOT 引入并行成员执行。

## Code-Resolved Questions

以下问题已由代码/规格定案，不占用用户时间：

- **是否转发 delta？** 否。带宽/多订阅者放大，且用户明确要求只发状态；reducer 只消费首个增量
  信号。
- **`tool_call` 能否作为工具开始？** 不能。正常执行路径在工具结束后才发
  （`agent/loop.py:1013-1014` → `:1075-1089`）；用 `before_tool_execute`（`:1417`）。
- **非流式时能否显示 typing？** 不能。无 `assistant_delta`（`agent/loop.py:1389-1395`、
  `agent/llm.py:98`）。
- **子 agent/workflow 内部能否细分？** 不能。父会话只看得到外层工具调用。
- **`room_state` 快照包含哪些成员？** 只包含 `phase != idle` 的成员；缺失 = idle；
  `round_active=false` 全 idle。
- **终态事件是否要带 seq？** 要。否则迟到状态可能越过终态复活；附加字段向后兼容。
- **取消是否要新增轮次出口？** 不。只发 teardown 用途的 `round_ended(cancelled|error)`，
  不写日志、不产生 `RoundResult`；用 MODIFIED Requirement 明确。
- **状态是否持久化？** 不。运行期投影，重启后空闲。
- **是否保留成员 chip？** 不。presence 取代 chip 行，admin 信息并入；群公告移到独立元素。
- **`on_error` 是否映射为 run 错误？** 不。工具错误也会触发该钩子；run 级失败由 runner
  四态出口兜底。
- **`run_started` 用钩子还是事件？** 用钩子；resume 分支不触发，`before_iteration` 是
  thinking 的权威信号。
- **空产出是否真的漏发终态？** 生产 `WebSessionRunner` 已归一为 silent
  （`web/session.py:2226-2227`）；编排器补防御性契约，不称其为用户可见 bug。
- **`SessionRunner` 有几个实现？** 三个需要同步：`WebSessionRunner`
  （`web/session.py:2178`）、`_WorkspaceRunner`（`web/team.py:222`）、测试 `FakeRunner`
  （`tests/agent/team/test_orchestrator.py:35`）。
- **成员被移出房间需要清状态吗？** 不需要特判：`slot_skipped` 发生在 `ensure_room_session`
  之前（`agent/team/orchestrator.py:404-409`），该成员从未被置为忙；渲染按当前 members 过滤。

## Pre-Implementation Review

- grill 证据：`reviews/grill-design.md`（8 条 Confirmed Decisions；27 条 Design Corrections，
  已逐条落实到本设计）。
- 设计对抗 R1：`rounds/grill-adversarial-r1.md`，verdict `CHANGES_REQUESTED`（无 high，
  2 medium + 11 low/nit）。已修复：F1 删除 `member_speaking` 头部文案、明确头部单一归属；
  F2 增加握手顺序与跨轮迟到终态的确定性测试（含变异验证）；F3 建会话失败走统一
  `_finish_member`；F4 重置幂等（表未变不递增/不发射）；F5 正常 `round_ended` 前 flush；
  F6 自动滚入只动横向 `scrollLeft`；F7 benchmark smoke 触发口径；F8 轮数口径登记；
  F9 评审记录路径；F10 idle 条目措辞；F11 390px 头部收纳与无溢出断言；F12 移动端空状态入口；
  F13 事件驱动清单补降级路径。
- 设计对抗 R2：`rounds/grill-adversarial-r2.md`，verdict `CHANGES_REQUESTED`（无 high，
  2 medium + 4 low）。已修复：N1 把 pop 提到 flush 之前并补「收尾窗口不吞新消息」回归
  （tasks 2.7 / 1.2.2）；N2 spec 三处「无条件递增」改为「表实际变化才递增」；N3 迟到
  `round_ended(limit)` 仍重拉时间线；N4 测试文案改为「事件流中曾出现」；N5 固定
  `group_status.js` 的 `{state, changed, applied}` 返回契约；N6 清理 R1 记录中的本地路径。
- 设计对抗 R3：`rounds/grill-adversarial-r3.md`，verdict `CHANGES_REQUESTED`（1 high + 4 low）。
  已修复：X1 所有认领释放点改为 `is state` 身份判断，补「R1 返回后 R2 仍 active、M3 queued
  进 R2」回归；limit system 条目提前到 reset/pop 之前；N1 gate 改为一次性有界等待；N3 补
  迟到 limit 终态仍重拉时间线的测试；N5 统一 `apply*` 返回 `{state, changed, applied}`；
  N2 终态 no-op 时携带当前 seq 的措辞。
- 设计对抗 R4：`rounds/grill-adversarial-r4.md`，verdict `CHANGES_REQUESTED`（无 high，
  2 medium + 1 low）。已修复：M1 WS 层中间态测试改为「最终表/工具态 + 编排器层中间态」，
  慢速脚本 LLM 必须有让出点，风险写入 Risks；M2 新一轮 `user_message`/首个非空闲状态清除
  上一轮结束提示，连接/错误提示优先；low 补齐「认领已释放则不复位、不发旧终态」的 tasks
  口径。
- 设计对抗 R5：`rounds/grill-adversarial-r5.md`，verdict `CHANGES_REQUESTED`（无 high，
  1 medium + 5 low + 3 nit）。已修复：T1 增加真实 `WebSessionRunner` + `ScriptedLLM` +
  `on_progress` collector 的 web 层映射测试与变异验证；L1 `MemberStatus` 不含成员级 seq；
  L2 意外异常 teardown 加认领身份限定并登记 released-claim 实时可见性；L3 limit 重拉测试
  移到 group.js/浏览器层；L4「最终表」措辞改为「事件流中曾出现 + 回合结束快照一致」；
  L5 `op` 提示在下次成功发送/连接成功后清除；L6 presence 重绘保留横向滚动；L7 反定时器
  等待 3s；L8 backlog 引用不再悬空。
- 设计对抗 R6：`rounds/grill-adversarial-r6.md`，verdict **PASS**（无 high/medium；T1/L1–L8
  已修复或合理处置，X1/N1–N6/F1–F13 未被破坏）。R6 后的 L-a–L-g 测试/文档口径已顺手收敛。
  收口报告已落为 `reviews/grill-adversarial.md`（逐轮证据保留在 `-r1..r6.md`）。
- **出口 = PASS**。**停轮确认已完成（2026-10-20，Q1/Q2/Q3 全部 = A）**：移动端 56px 横向条、
  失败后立即回空闲、接受串行执行；生效口径见 `## User Rulings (2026-10-20)` 与
  `reviews/grill-design.md` 的 `## User Confirmation`。设计环放行，可进入实现（TDD）。
- 轮数口径：按用户 2026-10-20 的明确指示「跑到收敛（无轮数上限）」；仓库 `AGENTS.md` 仍写
  20 个已收口轮，本 change 不单方面改仓库规则；若达到 20 轮仍未收敛，登记差异并上报用户。
