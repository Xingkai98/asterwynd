# Design: workflow 节点 mode 钳制基准修正（fix-issue-255-mode-ceiling）

## Context

Workflow DSL 的节点可声明 `mode`（`build` / `read_only` / `plan`），语义是「节点**有效** mode 不得超过当前会话 mode」。该钳制由 `SubAgentManager._clamp_mode`（`agent/subagent/manager.py:1588`）实现，形状（按权限等级取小）正确，但**输入错了**：

- `_clamp_mode` 经 `_parent_mode()` 读 `self.parent_mode_provider`（`manager.py:1600-1603`）。
- `parent_mode_provider` 是 manager 上的**共享实例字段**（`manager.py:454`），唯一写入点是 `manager.py:544-545`，由 `AgentLoop.__init__` 的 `configure_runtime(...)` 调用（`agent/loop.py:153-155`，全仓唯一调用点）。
- 子 agent 的 loop 复用同一 manager（`manager.py:1303` `subagent_manager=self`），**每构造一个子 loop 就无条件覆写该字段**。

于是「当前会话允许的能力面」= **最后被构造的那个子 loop 的 mode**，与发起运行的会话无关。三个后果（本 change 立项阶段独立探针实测，细节见 `diagnosis.md`）：时序 fail-open、并发结构性错误、静默降级 + 跨图污染。

**关键背景：本仓库已有正确先例，且已在文件注释中写明了理由。** `workflow_id` / `node_id` / `graph_distance` / `bus` 四项已在同一派发点 `_launch_run`（`scheduler.py:2112-2141`）用 `ContextVar` set + `finally reset`，`create_subagent` / 身份字段消费；`agent/subagent/context.py` 文件注释：

> asyncio 的每个 Task 各持一份 context 副本，其它节点的 run 看不到这里的 set

即仓库早已知道「共享标量在并发节点下不成立」，唯独 `mode` 还留在共享标量上。**本 change 的任务是把 mode 并入这条既有通道，而不是新造机制。**

**约束来源（已确认的设计约束，非本设计重新发明）**：issue #255 正文；#245 `reviews/grill-design.md` 的 Q7/Q11 与 `## User Confirmation`；#245 `design.md` 的 D3。用户已确认的语义：

1. 节点 mode 在**声明 workflow 时**配置，运行时**不可改变**；
2. 节点有效 mode = `min(节点声明 mode, 当前会话上限)`；
3. 机制走 **contextvar**（与 `workflow_id` 等同路）；
4. **快照语义**：workflow 启动时快照会话上限作为整轮上限，运行中途切换模式不影响本次 run；
5. **嵌套继承**：节点 A 的有效 mode `E_A = min(M_A, R)`，A 的子孙上限为 `E_A`，逐层收紧；
6. 落点必须挂**派发点**（`_launch_run`），不是 run 执行处（`_execute_run_in_context`）；
7. 执行上下文的 set **不配对** `finally reset`（跨 context teardown 会抛 `ValueError`）。
   > **grill 订正**：第 7 条的「不 reset」精确含义是「**不用 `reset(token)`**」。挂载 A 仍需在 `finally` 里把上限**恢复**（用 `set(prior)`，非 `reset`）——否则同 task 内跨会话泄漏上限（见 D3）。挂载 B 用 `finally reset(token)` 是安全的（普通协程，非跨 context 的 task 体）。

**执行顺序约束**：用户已确认 **#255 → #245 → #246**。#245 的 tasks 标注「mode 相关任务 blocked by #255」，且其验收要求本 change **必须提供一个「只由 root loop 写入的会话上限通道」**——本 change 的验收标准必须包含该通道。

## Goals / Non-Goals

**Goals:**

- 让 `_clamp_mode` 的比较基准回到**发起当前执行单元的会话/祖先的有效 mode**，消除「最后构造的 loop 覆盖」这一根因。
- 满足用户确认的 7 条语义（快照、逐层收紧、派发点落点、执行上下文不用 `reset(token)` 等），并按 grill 订正落实「挂载 A 用 `set(prior)` 恢复」。
- 修正 fail-open 方向（只读会话不得被授予写权限）与静默降级方向（build 节点不得被前面的只读节点降级），并覆盖并发与跨图污染。
- 提供一个 **scheduler 可读的会话上限通道**，供 #245 消费（#245 Q11 的硬性前置）。
- 补齐 `_clamp_mode` 的零测试覆盖，每项回归配「合法路径必须成功」的对照。

**Non-Goals:**

- 不改 `AgentMode` 枚举、权限档位排序、`ModePolicy` 判定链、工具 `deny_tools` / `allowed_modes` 语义。
- 不改 workflow DSL 语法（节点 `mode` 字段的取值与声明期校验保持不变；`WorkflowNode` 仍是 `frozen=True`）。
- 不实现 #245 的资产功能（保存 / 索引 / 按名复用 / 「列出将以声明 mode 运行的节点」）。本 change 只提供可信的基准与通道。
- 不改 `set_mode` 的入口或 UI 交互。
- 不引入运行时可变 mode（节点 mode 仍在声明期固定）。
- **不修「既有 session 重跑不重新钳制 mode」**（grill 发现的已知残留）：`_clamp_mode` 只在 `create_subagent` 调用，`RunSubagent` / `ResumeSubagent` 不经过它 ⇒ 会话建好后切 mode，重跑同一 `subagent_id` 仍用创建时冻结的 mode。这是既有设计，本 change 只覆盖「workflow 节点 / 新 spawn 的 run 起点」面；该残留登记于此并在 Risks 说明。
- **不修 `AgentLoop` 复用 `tool_registry.mode_policy.runtime_state` 的潜伏面**（同根因，当前生产不可达）：登记 `docs/known-debt.md` / follow-up issue。

## Decisions

### D1：mechanism —— mode 上限并入既有 contextvar 家族

**决定**：在 `agent/subagent/context.py` 新增一个 `ContextVar`（暂名 `_mode_ceiling`，访问器 `current_mode_ceiling()` / `set_mode_ceiling(...)` / `reset_mode_ceiling(...)`），承载「当前执行上下文的 mode 上限」。

**理由**：这是 #245 grill Q7 用户拍板的方向，也是本仓库既有正确机制的沿用（`workflow_id` / `node_id` / `graph_distance` / `bus` 同路）。asyncio 每个 Task 各持一份 context 副本 ⇒ 并发兄弟天然隔离；`copy_context()` 在入队时捕获 ⇒ 嵌套天然继承。

**备选**：
- *(B) 显式参数穿过*：把节点有效 mode 作为参数穿到 `create_subagent`。排除理由：并发节点需逐次传递、易漏；嵌套需手工逐层传递；与既有身份字段机制分叉，两套口径。
- *(C) manager 上「只由 root loop 写入」的普通字段*：这能修 fail-open 与跨图污染（#245 Q11 候选 A 的形态），但**修不了并发**（并行节点仍读同一标量，见 `diagnosis.md` 症状二）与**直接 spawn 的嵌套继承**（见 D3）。作为**回落兜底**保留语义（`parent_mode` 静态构造参数的回落），不作为主机制。
- *(D) 在共享字段上补 reset / 每次重算*：并发节点仍读同一标量，根因未消。

### D2：`_clamp_mode` 的读取优先级（fail-closed 兜底）

**决定**：`_clamp_mode` 的上限来源优先级为：

1. 执行上下文 `current_mode_ceiling()`（若已 set）；
2. 回落 `self.parent_mode`（**静态构造参数**，`manager.py:441` / `agent/main.py:293`、`web/session.py:1580`、`benchmarks/agent_runner.py:377` 均以会话初始 mode 传入）；
3. 若两者皆无（`parent_mode` 有默认值 `AgentMode.BUILD`，故实际不会发生），保持既有 `BUILD` 默认。

**理由**：回落值必须是**保守**的（不得因通道缺失而放宽）。`parent_mode` 是会话初始 mode，是保守的静态下界；这正好满足 #245 Q11 的担忧「#255 只换机制而不提供通道 ⇒ #245 快照静默读不到值 ⇒ 退化成上限 None → 不收窄 → fail-open」——**本 change 的回落路径保证「读不到」不会变成「无界」**。

**关键**：为此**必须删除 `parent_mode_provider`**，否则回落路径会继续读到被覆盖的共享字段（根因未消）。删除范围：`manager.py` 的字段（`:454`）、`configure_runtime` 形参（`:536`）与赋值（`:544-545`）、`_parent_mode()` 的 provider 分支（`:1600-1602`）、`AgentLoop.__init__` 的 `lambda`（`agent/loop.py:155`）。仓库内唯一调用点是 `agent/loop.py:153`，无外部调用方。

### D3：两处挂载，各有不可替代的职责（**本设计与 #245 设计的关键差异**）

**决定**：上限在两处 set，**两处都是必须项，不是可选项**：

- **挂载 A（run 起点收紧）**：在 `_run` 中**、resume 恢复 mode 之后**（`agent/loop.py:602-605` 的 `set_mode(resume_snapshot.mode, ...)` 之后、`mode = self.runtime_state.current_mode.value` 处）快照当时会话 mode 并 `set_mode_ceiling(...)`；**run 结束时用 `set()` 恢复为 run 起点捕获的先前值**（**不得**用 `reset(token)`——跨 context teardown 会抛 `ValueError`，见「为什么挂载 A 用 set 恢复而非 reset」）。**【✅ 已确认（2026-09-27，O1）：必须实现**——它是「直接 spawn 链式嵌套」路径的唯一覆盖手段。**在 `tasks.md` 中作为独立验收项（任务 3.1 / 3.4），并在回归测试第 4 项以两条路径显式覆盖。**
  > **落点精确性（grill 复核）：** 不放 `run()` 最顶端——resume 会在 `_run` 内改 mode（`loop.py:602-605`），顶部快照会取到 resume **之前**的 mode。
- **挂载 B（派发点 `scheduler._launch_run`）**：`set_mode_ceiling(min(node.mode 或 cur, cur))`，**set + `finally reset`**（与既有 4 个身份 contextvar 并列）。**【✅ 已确认（2026-09-27，O5）：采用带 `finally reset` 的形态】**

**为什么需要挂载 A（这是相对 #245 `design.md` D3 的新增发现）**：`_execute_run_in_context`（run 执行点）只能让**孙辈**看到上限，但**节点自身**的 mode 在 `create_subagent`（派发阶段）就冻结了——这独立复现了 #245 的结论。但反方向还有一个未被 #245 覆盖的缺口：**直接 spawn 的链式嵌套**（root loop → `CreateSubagent(child, mode=build)` → 该子 agent 内再 `CreateSubagent(grand)`）。若上限只在派发点 set，而子 agent 的 run 没有把上限收紧为它**自己**的有效 mode，则孙辈会读回 root 的上限，**越过父辈的有效 mode**（fail-open）。实测（`/tmp/probe255/mine_nest_paths.py`）：

```text
路径 2（root 直接 spawn 的链式嵌套）：root=build, child=read_only, grand 请求 build
  loop-run 收紧=False child=read_only grand=build     ✗ 超过父有效 mode（fail-open）
  loop-run 收紧=True  child=read_only grand=read_only ✓ 继承父有效 mode
```

> **⚠️ grill 复核补正（2026-09-27，改变示例的「可达性」，不改变结论）**：上例中「`read_only` 子 agent 再起子 agent」在**默认权限配置下不可达**——`read_only` / `plan` 的子 loop 工具集**不含** `CreateSubagent`（`READ_ONLY_CAPABILITIES` / `PLAN_CAPABILITIES` 不含 `ToolCapability.SUBAGENT_CONTROL`，`agent/tool_permissions.py:98-107,167-178`），实测被 `[Permission denied: ... permission profile read_only_default]` 拦下。**挂载 A 的必要性仍然成立**，但回归测试须用**可达**例子：root 会话上限为 `bypass`（或 `build`），`child` 声明 `mode: build`，`grand` 不声明 mode ⇒ 只挂派发点时 `grand` 得 **`bypass`/root 上限**（新 fail-open），含挂载 A 得 `build`。实测（grill 探针 `probe_B_nest.py`）：
>
> ```text
> 挂载 A OFF（只挂派发点）: {'child': 'build', 'grand': 'bypass'}   ← 新 fail-open
> 挂载 A ON （双挂载）    : {'child': 'build', 'grand': 'build'}    ← 正确
> ```
>
> `tasks.md` 4.4 的路径 (b) 按此更正。

**注意这一缺口的严重性**：今天的**缺陷实现**在直接 spawn 链上是「碰巧正确」（子 loop 的构造把共享 provider 覆写成子 session 的 mode）。若只做派发点挂载并删掉 provider，会把这条路径从 `read_only` **变成** `build`——**引入一条新的 fail-open**。故挂载 A 是**避免回归**的必要项，不是锦上添花。

**为什么挂载 A 用 `set()` 恢复而不是 `reset(token)`**：子 agent 的 run 体 `_execute_run_in_context` 已是 `asyncio.create_task(..., context=item.context)` 的 task 体，其 context 是 task 私有的——这正是既有代码在 `manager.py:999-1002` 明写 **No tokens are reset** 的原因；在那里 `reset(token)` 会在跨 context teardown 时抛 `ValueError`（grill 独立复现：只有 `coro.close()` 在**与 token 创建不同的 context** 下才抛）。

**但「挂载 A 完全不清理」是错的（grill 发现的跨会话 fail-open，本设计据此订正）**：root loop 的 `run()` 在**调用方 task** 内被 await，而该 task 的 context 会跨越同 task 内的后续操作存续。若挂载 A 只 `set` 不清理，`run()` 返回后该 task 的 ceiling 会**残留为本次 run 的 mode**；此后同一 task 内若**不经任何 `AgentLoop.run`** 直接驱动一个别的会话的调度器（benchmark `template` / `dynamic-replay` 路径：`benchmarks/agent_runner.py:520,564` 直调 `scheduler.run(spec)`），`_clamp_mode` 会读到**上一个会话的上限**，越过 D6 承诺的保守回落。实测（`/tmp/probe255/mine_stale2.py`，我独立复现）：

```text
场景：同 task 先跑 build 会话的 loop.run，再直驱一个 parent_mode=read_only 的 scheduler
      （节点声明 build，期望 read_only）
  挂载A形态=不 reset    跑完后ceiling=build  直驱节点授予=build      ✗ 跨会话 fail-open
  挂载A形态=set 恢复     跑完后ceiling=None   直驱节点授予=read_only  ✓ 保守（回落 parent_mode=read_only）
```

**订正后的形态**：挂载 A 在 run 起点 `prior = ceiling.get()` → `set(本 run 会话 mode)`，在 `finally` 里 `set(prior)`（**不是** `reset(token)`——已验证 `set` 在跨 context close 下不抛异常，`/tmp/probe255/mine_stale2.py` 第二节）。这样 run 结束后调用方 task 的 ceiling 复原为 run 前的值（通常是 `None`），D6 的保守回落随之恢复成立。`tasks.md` 3.1 与本条同步。

**为什么派发点（挂载 B）的 set 可以带 `finally reset`**：`_launch_run` 是调度器 task 内被 `await` 的**普通协程**，与既有 4 个身份 contextvar 完全同形态。实测两种写法（reset / 不 reset）在该点都给出正确的兄弟隔离（`/tmp/probe255/mine_noreset.py`）；采用 `finally reset` 与既有形态一致，且不依赖「每节点各自成 task」这一脆弱前提（`_execute_parallel` 在同一 task 内串行 await 多个 `_launch_run` 时也正确）。

**为什么挂载 B 仍保留**（即便有挂载 A）：
1. **显式钳节点自身**：在 `create_subagent` 之前把上限压到 `min(node.mode, cur)`，使「节点自身的有效 mode」在派发边界上被显式表达（#245 测试面正落在此边界）；
2. **兄弟隔离的显式化**：把「各节点按自己的声明 mode 与同一 run 上限取小」写在派发点；
3. **兜底**：调度器可能在不经 `AgentLoop.run` 的路径上被直接构造并 `run()`（benchmark、测试），此时挂载 A 不触发。

> **⚠️ 实现期实证（2026-09-27，变异测试）：挂载 B 在**当前代码形态**下是 outcome-idempotent 的防御性冗余，不是 load-bearing。** 论证：设会话上限 R、节点声明 m。挂载 B 把上限压到 `min(m, R)`，而 `create_subagent` 内的 `_clamp_mode(m)` 已经是 `min(m, R)`；再对它取 min 得到同一个值，故**节点自身**的有效 mode 不变。**其后代**的上限由子 loop 的挂载 A（`set(session.mode)` = `min(m, R)`）决定，也与挂载 B 无关。变异验证佐证：把挂载 B 整个删掉（M4）、或只删它的 `finally reset`（M5），16 条回归**全绿**——无任何用例能区分。
>
> **保留理由**：它是无害的一次 set/finally-reset；它把「派发即收窄」这一不变量显式化（读者不必从 `create_subagent` 内部反推）；它是 #245「scheduler 可读的会话上限通道」在调度器侧的读写点；且它对未来 `create_subagent` 钳制逻辑的改动提供纵深防御。
> **代价与诚实口径**：它是一段**无回归覆盖**的代码——按本仓库「不留假保护」的要求，此处**不声称**它已被测试保护。若审阅者认为「不可测的代码不应保留」，备选是删除挂载 B（此时 `effective_mode()` 仍作为 #245 的公共通道保留，但不再在派发点 set）——属产品/审阅取舍，记录于此待定。

**备选**：
- *(B′) 只挂派发点（#245 design.md D3 的原始口径）*：排除——直接 spawn 链会 fail-open（见上实测），是引入新缺陷。
- *(A′) 只挂 run 起点，不挂派发点*：能覆盖节点自身与嵌套（只要每个 run 都重设），但语义不显式落在「派发」边界，且调度器脱离 loop 直接 `run()` 时无兜底。排除——保留两处以满足用户已确认的「落点挂派发点」并强化鲁棒性。

### D4：快照语义的落点是「run 起点」

**决定**：上限在**每个 `AgentLoop.run` 的开头**快照为当时 `runtime_state.current_mode`；run 中途切换会话 mode **不改变**本 run 已确定的上限；该会话**下一次 run** 按新 mode 重新快照。

**理由**：用户已确认「快照语义：一次 run 的能力边界自始至终一致」。落点在 run 起点（而非 workflow 启动点）的理由：run 起点是「该 loop 的会话 mode 已确定、工具尚未执行」的唯一自然边界；且在 web/CLI 路径上，所有 workflow 都是由 root run 内的工具调用发起的，run 起点快照 = 该 run 内所有 workflow 的整轮上限。

**实测**（`/tmp/probe255/mine_snapshot.py`）：

```text
run A 中途切换后派发的节点 = build  期望 build（快照不随中途切换变）  ✓
run B（切换后新 run）的节点 = read_only  期望 read_only（新 run 用新 mode）  ✓
```

**边界说明（写入 spec 的口径）**：若一次 run 内先切换会话 mode、再启动 workflow，该 workflow 的上限取**该 run 起点**的 mode，而非切换后的 mode。这是「快照」的自然含义；用户确认的「运行途中切换不影响本次 run」与本口径一致。

### D5：嵌套与跨图一律「继承父节点的有效 mode」

**决定**：节点 A 的有效 mode `E_A`；A 的 run 起点把上限设为 `E_A`（挂载 A）；A 的子孙（含 A 内启动的**新图** B）上限为 `E_A`，逐层收紧。

**理由**：mode 是**能力面**而非配额，应只随继承链收紧、不随命名空间重置（#245 grill Q10 用户拍板「口径 1（继承）」）。这也与 #245 delta 中「跨图嵌套同样继承有效 mode」的 Scenario 一致。

**实测**（`/tmp/probe255/mine_full.py` 的 S3/S4/S6）：

```text
S3 并发 (bw,ro): {'bw': 'build', 'ro': 'read_only'}
S3 并发 (ro,bw): {'ro': 'read_only', 'bw': 'build'}     <- 构造序反转结果一致
S4 嵌套(直接 spawn) child/grand: ('read_only', 'read_only')
S6 跨图污染: [('ro', 'read_only'), ('bw', 'build')]     <- 图 2 的 build 未被图 1 污染
```

### D6：会话上限通道 = `current_mode_ceiling()`（#245 的硬性前置）

**决定**：`agent/subagent/context.py` 的 `current_mode_ceiling()` 即 #245 Q11 要求的「**scheduler 可读的会话 mode 通道**」。scheduler / 工具层可经它读到当前执行单元的上限；未 set 时回落静态 `parent_mode`（保守，非无界）。

**理由**：`WorkflowScheduler.run()` 只持 `self.manager`（`scheduler.py:714`），而 `manager.parent_mode_provider` 正是污染源；工具层同样只持 `self.manager`（`agent/tools/builtin/subagents.py:567` 等）。`current_mode_ceiling()` 是本 change 提供的、**唯一不需要读被污染的共享字段**的通道。

**验收要求（必须写进 spec 与 tasks）**：本 change 的验收标准必须显式包含「提供一个 scheduler 可读的会话上限通道，且读不到时回落到会话初始 mode 而非无界」——否则 #245 的快照会静默读到 `None` 并退化回 fail-open。

**实现提示**：为让 scheduler 在**任意**起点都能读到值（含无 `AgentLoop.run` 的路径），`current_mode_ceiling()` 的回落链为：contextvar → `manager.parent_mode` → `AgentMode.BUILD`。scheduler 侧读值时经 `self.manager` 取回落值。

> **⚠️ grill 复核订正（2026-09-27，高危）**：D6 的「保守回落」**不是自动成立的**——它要求 contextvar 在「不属于当前执行单元」时**为未 set**。若挂载 A 只 `set` 不清理，同一 task 内会残留上一个会话的上限，此时回落链拿到的是**陈旧值**而非 `parent_mode`，产生跨会话 fail-open（实测见 D3 的订正段）。**因此 D6 的保守性依赖于 D3 订正后的「`set` 恢复」形态**；`tasks.md` 必须新增一条独立回归：`scheduler.run()` 直驱路径 + 同 task 内有其它会话 loop 运行史时，回落仍保守。

## Pre-Implementation Review

> 本节只记录决策相关摘要，不粘贴完整聊天流水。**独立零记忆 subagent 的 `batch-grill-me` 已于 2026-09-27 运行完毕**，产出见 `reviews/grill-design.md`（9 条 Confirmed Decisions、O1–O5 全部确认、0 条未确认 Open Question）；其推翻/补正的结论已回写本 design（见下方「grill 复核订正」）。

**已完成（立项阶段独立复现，非代码推断）**：

1. 三症状实测复现（`/tmp/probe255/mine_symptoms.py`）：fail-open / 并发构造序 / 跨图污染。
2. 落点对照（`/tmp/probe255/mine_landing2.py`）：`none` / `runctx` 均 FAIL-OPEN，仅 `dispatch` 收窄——**推翻**「挂 `_execute_run_in_context` 即可」的原始假设。
3. `finally reset` 的 teardown 崩溃（`/tmp/probe255/mine_teardown2.py`）：跨 context `coro.close()` 时 `reset(token)` 抛 `ValueError: ... was created in a different Context`——**支持**「执行点不 reset」。
4. 直接 spawn 嵌套缺口（`/tmp/probe255/mine_nest_paths.py`）：仅派发点挂载会让孙辈越过父辈有效 mode——**本设计相对 #245 设计的新增发现**。
5. 两处挂载的完整设计（`/tmp/probe255/mine_full.py`）通过 #255 全部六项场景；快照语义单独验证（`/tmp/probe255/mine_snapshot.py`）。
6. 测试盲区确认：`rg 'parent_mode_provider|_clamp_mode' tests/` 零命中；既有 `parent_mode=` 用例走静态路径，覆盖不到缺陷路径。
7. 横向扫描：全仓只有 `parent_mode_provider` 一处**生产可达**的同构缺陷（`configure_runtime` 另两个参数在唯一调用点传 `None`，永不覆写；`llm` 覆写同一对象、幂等无害）。grill 另发现一处**同根因潜伏面**（`loop` 复用 `tool_registry.mode_policy.runtime_state`），见下。

**grill 复核订正（2026-09-27，`reviews/grill-design.md`；下列结论已回写本文档）**：

- **【推翻 design，高危】挂载 A 「不 reset」会跨会话泄漏上限**（见 D3 订正段）。订正形态：run 起点捕获 `prior`、`finally` 用 `set(prior)` 恢复（非 `reset(token)`）。D6 的保守性依赖于此。
- **【推翻 design 的示例，非结论】O1 的原例不可达**：`read_only`/`plan` 子 loop 无 `CreateSubagent` 工具（`agent/tool_permissions.py:98-107,167-178`）。挂载 A 必要性不变，示例改用「root=`bypass`、`child` 声明 `build`、`grand` 不声明」这条**可达**路径（见 D3 与 tasks 4.4）。
- **【新增，高危】design 的并发回归（第 3 项）与第 1 项对照在单元层是假保护**：按 design 表面写法（`WorkflowScheduler.run` 直驱、单进程默认配置）构造的用例在 defect 与 fixed 下**都绿**；真正能区分的是「同会话跨图/跨 run 的构造序污染」+ **真实 `AgentLoop.run` 驱动**。已在 Testing Strategy 与 tasks 中更正。
- **【新增，中】既有 session 重跑不重新钳制**：`_clamp_mode` 只在 `create_subagent` 调用，`RunSubagent`/`ResumeSubagent` 不经过它 ⇒ 会话建好后切 mode，重跑同一 `subagent_id` 仍用冻结的旧 mode。属既有设计，**不在本 change 修**，登记为 Known Residual（见 Risks）。
- **【新增，低】benchmark 任务 `gold.patch` 含 `parent_mode_provider` 新增行**：tasks 2.6 的「全仓零命中」验收须排除 `benchmarks/tasks/**/*.patch` 与 `docs/openspec-change-backlog.md`，否则该验收项自身红。
- **【新增，低】同根因潜伏面**：`agent/loop.py:159-161` 使同一 `ToolRegistry` 被两 loop 复用时共享 `AgentRuntimeState`（实测 `loop2.runtime_state IS loop1.runtime_state`）。生产路径每 loop 各建 registry，无可达影响；登记 debt，不在本 change 修。

## Risks / Trade-offs

- **【风险：中】删除 `parent_mode_provider` 会移除「动态 provider」这条能力。** → 缓解：仓库内唯一写入点（`agent/loop.py:153`）随本 change 一并删除；`parent_mode_provider` 的全部出现点已 `rg` 枚举（`manager.py` 4 处 + `loop.py` 1 处），无外部调用方、无测试引用。回落链（D2）保留「静态 parent_mode」这一保守兜底。
- **【风险：高 → ✅ 已缓解（2026-09-27，O1 已拍板）】只做派发点挂载会让**直接 spawn 链**从「碰巧只读」变成「build」，引入新 fail-open。** → 缓解**已纳入本 change 范围**：D3 的挂载 A（run 起点收紧）**是必须项**（用户已确认 O1 = 纳入），覆盖「直接 spawn 链式嵌套」；回归测试第 4 项以**两条路径**（workflow 节点内派生 + 直接 spawn 链）显式覆盖，且**不得标为可选**（`tasks.md` 4.4）。该风险不再停留在「待确认」，已转为**已决定的实现范围**。
- **【风险：中】执行点照抄 `finally reset(token)` 会引入 teardown 崩溃。** → 缓解：D3 明确「执行点与挂载 A 均**不用 `reset(token)`**」（挂载 A 改用 `finally set(prior)` 恢复、执行点完全不清理），并在 tasks 的实现约束中禁止照抄 `reset(token)`；回归测试含取消路径。
- **【风险：中 → ✅ 已定（2026-09-27，O2）】快照落点在 run 起点，而 #245 的措辞是「workflow 启动时快照」，两者在「一次 run 内先切 mode 再起 workflow」的边界上口径不同。** → 用户已确认采用 **run 起点口径**（O2）；D4 边界说明写入 spec，快照点不再下移到 `scheduler.run()`。
- **【风险：中 → ✅ 已定（2026-09-27，O4）】本 change 与 #245 的 spec delta 在 `multi-agent-collaboration` 上存在**口径重叠**。** → 用户已确认分工：**#255 拥有机制与基准语义**，#245 保留资产面的「列出将以声明 mode 运行的节点 + diagnostics」。本 change 的 delta 只写「机制 + 基准语义」，资产面留给 #245；`tasks.md` 5.2 按此收窄 / 对齐 #245 的 delta。
- **【风险：低】回落链在 scheduler 脱离 loop 直接 `run()` 时读到静态 `parent_mode`（会话初始 mode），可能与当前 mode 不符。** → 缓解：该路径（benchmark / 测试）无动态切 mode；口径写入 spec 并在测试中锁定回落的保守性。
- **【风险：低】新增 contextvar 若忘记在新增派发点 reset，会向兄弟泄漏。** → 缓解：`set`/`reset` 成对出现在 `_launch_run`，与既有 4 个身份 contextvar 同处；回归测试覆盖并发兄弟。
- **【风险：高 → ✅ 已订正（grill，2026-09-27）】挂载 A 「不 reset」⇒ D6 保守回落跨会话失效（fail-open）。** 实测：同 task 内先跑一个会话的 `AgentLoop.run`，再直驱另一会话的 `WorkflowScheduler(...).run(...)`（benchmark `template`/`dynamic-replay` 路径），节点读到的是**上一个会话的上限**。→ 缓解**已纳入设计**：挂载 A 改「run 起点捕获 prior + `finally set(prior)`」（非 `reset(token)`），D6 保守性随之成立；新增独立回归（tasks 4.10）。
- **【风险：高 → ✅ 已订正（grill，2026-09-27）】回归测试存在假保护。** 按 design 表面写法（scheduler 直驱、单进程默认配置）构造的并发/对照用例在 defect 与 fixed 下**都绿**，不能证明修复有效。→ 缓解**已纳入 Testing Strategy**：并发重心改为「同会话跨图/跨 run 构造序污染」；所有会产生 mode 差异的用例**必须经真实 `AgentLoop.run` 驱动**，不得用 mock 手工 `set` 上限替代 run 起点。
- **【风险：中 → 已登记】既有 session 重跑不重新钳制 mode（不在本 change 修）。** `_clamp_mode` 仅在 `create_subagent` 调用；会话建好后切 mode，`RunSubagent` 重跑同一 `subagent_id` 仍用冻结的旧 mode。→ 这是「mode 在会话创建期冻结」的既有设计，与本 change 的 run 起点快照语义的边界不同。**不在本 change 修**（避免扩大爆炸半径）；在 `## Non-Goals` 登记为已知残留，并提示 #245 的资产面列表对**已存在** session 的 mode 不作保证。
- **【风险：低 → 已登记】`AgentLoop` 复用 `tool_registry.mode_policy.runtime_state` 是同根因潜伏面。** 实测 `loop2.runtime_state IS loop1.runtime_state`（同一 registry 被两 loop 复用时）。生产路径每 loop 各建 registry，无可达影响。→ **不在本 change 修**，登记 `docs/known-debt.md`（或 follow-up issue），并加注释「registry 与 loop 不得跨 mode 复用」。
- **【风险：低】worktree 内 `.claude/` 被 gitignore ⇒ workflow_guard 不生效。** → 合并前确认 CI 的 `validate` job 确实跑了 `check_openspec_artifacts.py --base-ref <PR base>`，不要只依赖本地绿色。

## Testing Strategy

**层级**：`tests/agent/subagent/` 单元/集成层（`SubAgentManager` + `WorkflowScheduler` + `AgentLoop` 真实构造路径）。涉及 AgentLoop 与工具协议 ⇒ 必须覆盖该层（AGENTS.md 测试要求）。CLI / Web / benchmark 面**不新增**行为，但需跑既有全量回归确认未破坏。

**回归测试（#255 的 5 项 + 本 change 追加第 6 项 + 通道验收），每项配对照**：

| # | 方向 | 用例 | 对照（防假保护） |
|---|---|---|---|
| 1 | fail-open | 只读会话 + 声明 `build` 的节点 ⇒ 授予 `read_only` | build 会话 + 声明 `build` ⇒ 授予 `build`（证明不是无差别压低） |
| 2 | 静默降级 | BUILD 会话中先跑只读节点，再跑 `build` 节点 ⇒ 后者为 `build` | 该只读节点自身仍为 `read_only` |
| 3 | 并发 | 并行 `A(build)`/`B(read_only)` 各自正确，构造序 `('A','B')` 与 `('B','A')` 结果一致 | 两序下 A/B 均各得其所 |
| 4 | 嵌套 | grandchild 上限继承父节点的**有效** mode，**两条路径都必测、不得标为可选**（✅ O1）：(a) workflow 节点内派生；(b) 直接 `CreateSubagent` 链式派生 | 根会话为写时，只读节点的子孙仍只读 |
| 5 | 快照 | run 中途切换 root mode，本次 run 上限不变 | 该会话下一次 run 按新 mode 取上限 |
| 6 | 跨图污染 | 同会话顺序两张图，图 1（含只读节点）不影响图 2 起点快照 | 两图各含 build 节点时均得 `build` |
| 7 | 通道（#245 契约） | `current_mode_ceiling()` 在 scheduler 起点可读；未 set 时回落静态 `parent_mode` | 回落值**不得**是无界（`bypass`） |

**⚠️ 驱动形态硬约束（grill 复核订正，高危）**：任何**会产出 mode 差异**的用例（第 1–4、6 项）**必须经真实 `AgentLoop.run` 驱动**，**不得**用 mock / 手工 `set_mode_ceiling(...)` 包裹 `scheduler.run()` 替代——后者在 defect 与 fixed 下都返回相同值（假保护，实测 `probe_K` 的 `fixed_nowrap` 档）。唯一例外是第 7 项（通道回落），它按定义不经过 loop。

**⚠️ 假保护订正（grill 复核）**：原第 3 项（「同图并行节点」）在**默认配置**（每节点 `create_task` 各自成 task）下，defect 与 fixed **都绿**，不能区分修复与否。真正的区分点是「**同会话跨图 / 跨 run 的构造序污染**」（即第 6 项与第 1 项的方向）。因此：
- 第 3 项**保留**（作为不回归的护栏），但**不足以防假保护**，其「对照」必须扩为「同 task 内人为交错两个 `_launch_run`」的形态；
- 回归重心移到第 1、2、6 项（跨 run 污染方向），这几项才是 defect 下会红的核心。

**变异验证**：每条修复后做「改坏实现 → 测试变红 → 还原」的自检，确认测试真的在保护该行为（对齐本仓库审阅闭环惯例）。**验证判据**：把实现退回 defect（恢复 `parent_mode_provider` 路径）后，第 1/2/4/6 项**必须变红**——若某项仍绿，说明它是假保护，须重写。

**新增回归（grill 发现，高）**：
- **第 8 项｜挂载 A 的 `set` 恢复**：同 task 内先跑一个 `build` 会话的 `AgentLoop.run`，再直驱一个 `parent_mode=read_only` 的 `WorkflowScheduler.run()`（不经 loop），节点声明 `build` ⇒ 必须授予 `read_only`（证明 run 结束后 ceiling 已复原为 run 前值）。
- **第 9 项｜既有 session 重跑的边界（文档锁）**：锁定「`RunSubagent` 路径不重新钳制」这一**已知残留**的行为现状，避免将来被误当成本 change 的回归。

**既有覆盖保持**：`tests/agent/subagent/test_subagent_manager.py:57-81` 的 `test_create_subagent_*`（走 `parent_mode=` 静态路径）行为不变，作为「未改动静默路径」的回归基线。

**门禁**：`npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` + `uv run python scripts/check_openspec_artifacts.py --base-ref <PR base SHA>` + `uv run pytest -q`。

## Open Questions

> **✅ 全部已确认（2026-09-27）——本节无待定项。** O1–O5 已由用户逐条拍板，答复见下（对照记录落在 `reviews/grill-design.md` 的 `## User Confirmation`）。每条的「具体例子」保留原文，便于复查确认的语境。

- **O1【✅ 已确认（2026-09-27）：纳入】**：直接 spawn（非 workflow）的链式嵌套**纳入本 change 范围**，因此**必须实现挂载 A（run 起点收紧）**。
  **用户答复**：`CreateSubagent(mode=...)` 是常规调用，且删掉共享 provider 后该路径会从「碰巧对」变成「确定错」——不修就是我们改动引入的回归。故挂载 A 由「可选」升级为**必须**（见 D3）。
  **具体例子（grill 复核后改用可达形态）**：root 会话上限 = `bypass`（或 `build`）；root 的 run 内 `CreateSubagent(child, mode="build")`；`child` 的 run 内再 `CreateSubagent(grand)`（不声明 mode）。
  - **今天**：`grand` 得 `build`（碰巧正确——子 loop 构造覆写了共享 provider）。
  - **若只做派发点挂载并删 provider**：`grand` 得 **`bypass`/root 上限**（**新 fail-open**，实测 `probe_B_nest.py`）。
  - **若含挂载 A（已确认采纳）**：`grand` 得 `build`（正确）。
  - **⚠️ 原例（`read_only` 子 agent 再起子 agent）在默认权限下不可达**——`read_only`/`plan` 的子 loop 工具集不含 `CreateSubagent`（`agent/tool_permissions.py:98-107,167-178`），实测被 `read_only_default` 拒。故回归测试须用上方的可达形态（见 D3 补正）。
- **O2【✅ 已确认（2026-09-27）：run 起点口径】**：快照点取「run 起点」，不提为「workflow 启动点（scheduler.run）」。
  **用户答复**：采用 run 起点口径（理由见 D4）。
  **具体例子**：root loop 一次 run 起点 mode=`build`；run 执行到第 3 步时用户经 slash command 切到 `read_only`（`runtime_state.set_mode`）；第 5 步模型调 `RunWorkflow`，其节点声明 `mode: build`。run 起点口径 ⇒ 节点得 `build`；workflow 启动点口径 ⇒ 节点得 `read_only`。
- **O3【✅ 已确认（2026-09-27）：回落静态 `parent_mode`（保守），绝不回落 `None`】**：`current_mode_ceiling()` 未 set 时回落静态 `parent_mode`（会话初始 mode）。
  **用户答复**：回落静态 `parent_mode`（保守），**绝不回落 `None`**。
  **具体例子**：benchmark runner 直接构造 `WorkflowScheduler(manager).run(spec)`（不经过任何 `AgentLoop.run`）；节点声明 `mode: build`，manager 以 `parent_mode=read_only` 构造。回落口径 ⇒ 节点得 `read_only`；若回落改为 `None`（不收窄）⇒ 节点得 `build`（fail-open）。
- **O4【✅ 已确认（2026-09-27）：#255 拥有机制与基准语义】**：分工为 **#255 拥有机制与基准语义**；#245 保留资产面的「列出将以声明 mode 运行的节点 + diagnostics」。
  **用户答复**：#255 拥有机制与基准语义；#245 保留资产面的「列出将以声明 mode 运行的节点 + diagnostics」。`tasks.md` 5.2 按此对齐 / 收窄 #245 的 delta。
  **具体例子**：某节点声明 `mode: build`，会话只读。#255 的 delta 写「有效 mode = min(...)，不得放宽」；#245 的 delta 写「资产路径列出将以声明 mode 运行的节点 + 记 diagnostics」。
  **⚠️ grill 复核补正**：两 delta 的重叠不是概念性的——#245 的 `multi-agent-collaboration` delta **已含六个逐条同义的 mode Scenario**，若不删，合并时会留下重复 Requirement。**须由 #245 侧删除**（其正文已自注「mode 收窄语义依赖 #255」，本就是占位转述）；本 change 的 delta 不动。见 `tasks.md` 5.2。
- **O5【✅ 已确认（2026-09-27）：带 `finally reset`】**：挂载 B 采用 `set` + `finally reset`（与既有 4 个身份 contextvar 同形）。
  **用户答复**：带 `finally reset`（与既有 4 个身份 contextvar 同形）。
  **具体例子**：派发点 `_launch_run` 是调度器 task 内被 await 的普通协程；实测带 reset 与不带 reset 在该点都得到正确的兄弟隔离，采用带 reset 以贴合既有惯例、不依赖 task 边界假设。（执行点 `_execute_run_in_context` 仍**不带** reset，见 D3——两处形态不同，不可照抄。）
