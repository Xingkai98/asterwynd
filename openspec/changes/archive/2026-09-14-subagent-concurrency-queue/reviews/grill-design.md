# Grill: subagent-concurrency-queue 设计追问

## Reviewer

- run id: grill-subagent-concurrency-queue-2026-09-13
- 时间: 2026-09-13

## Confirmed Decisions

- **决策**: 并发许可的 acquire/release 必须落在 `_execute_run` 内部（`loop.run()` 前后）并用 `finally` 兜底释放，不能落在 `_launch_run` 或队列 worker 的出队处；理由: 现有三条取消路径都会把 `CancelledError` 打进 `_execute_run` 的 try——`cancel_subagent_run` 对 bg task 调 `task.cancel()`（`agent/subagent/manager.py:384`）、`_monitor_run_timeout` 同样 `task.cancel()`（`:662`）、父 loop 被外部取消时 task 级联传播。`_execute_run` 的 `except asyncio.CancelledError`（`:462-471`）在 `_mark_cancelled` 之后**重新 `raise`**，所以 finally 块（`:475-478`）是唯一必然执行的位置；许可若在 `_launch_run` 里 acquire，这些路径会漏放导致并发槽数永久漂移。同时该 finally 里已有「pop waiter + `waiter.set()`」（`:476-478`），许可释放与 waiter 唤醒放在同一处天然一致，排队中不持许可的 run 到这步时 release 是 no-op；来源: grill-subagent-concurrency-queue-2026-09-13
- **决策**: 队列项必须在**入队线程**捕获 contextvars，worker 以该 context 执行子 loop，否则 spawn_depth 与 message bus 双双丢失；排队跑的 `depth` 必须从 run 记录读显式值（D6），但子 loop 构建的位置仍有 ContextVar 需求（Bus 工具靠 `current_bus()` 拿 bus，`agent/tools/builtin/subagents.py:204`）；理由: `_launch_run` 现在是「create_task 前 set_spawn_depth → create_task → finally reset」（`manager.py:340-346`），child task 之所以能继承到 depth（`tests/agent/subagent/test_guardrails.py:68-84` 断言 `depths == [1]`）纯靠 create_task 的 context 拷贝。改成「协程投递 → 队列 worker 稍后 await」后 contextvars 在 worker 出队时已不可靠：若 worker 是循环式长驻任务（在 T1 创建），它带的是 T1 的 context，排队项会看到 depth 0、bus None；按 asyncio 语义**每个排队项必须在其自身 task 里以捕获的 context 执行**（`asyncio.create_task(coro, context=copy_context())`，pyproject `requires-python = ">=3.11"` 支持）；来源: grill-subagent-concurrency-queue-2026-09-13
- **决策**: `parent_run_id`/`depth` 必须显式作为 `run_subagent`/`resume_subagent` 的参数（或等价 RunRequest 字段）在入队前定值，不能靠执行期 ContextVar 读取——这正是 D6 要修的 bug 本体；`parent_run_id` 的注入需要新增「current_run_id」ContextVar（在 `_launch_run` 中与 `set_spawn_depth` 同处 set）或让工具显式传参；理由: `depth = current_spawn_depth() + 1` 在 `_check_guardrails`（`manager.py:721`）是 **spawn 时刻求值**，队列延迟执行时父 run 已结束、depth contextvar 已被 reset，排队子 run 读到 0；但仓库当前**不存在任何承载「当前 run id」的 contextvar**（`agent/subagent/context.py` 仅有 `_spawn_depth`/`_bus` 两个），所以 D6 的 `parent_run_id` 不是「把 ContextVar 改成显式字段」而是「从零新增注入通道」——这点 design.md 未点破；来源: grill-subagent-concurrency-queue-2026-09-13
- **决策**: `_check_guardrails` 的准入层必须保留「同 session 已有 active run → 拒绝」，且该判断在排队层之前；`session.active_run_id` 的赋值时机（`_launch_run` 开头 `manager.py:334`）在队列化后**不变**——入队即占用该 session；理由: 本 change 的 spec delta 自己写死了「再次运行同一子 session 仍 SHALL 拒绝并等待或取消当前 run（不进入跨 session 队列）」（`openspec/changes/subagent-concurrency-queue/specs/subagents/spec.md:70`），而准入检查 `run_subagent` 入口的 `session.active_run_id is not None`（`manager.py:220`）已经是 fail-fast；若把 active_run_id 挪到「真正执行时」才设，同一 session 会在排队窗口内被重复入队，破坏「session 内 run 串行」这条**既有** spec（`openspec/specs/subagents/spec.md:20`）；来源: grill-subagent-concurrency-queue-2026-09-13
- **决策**: 队列 worker 不能在出队时**只** await 协程——取消/超时逻辑（`_active_tasks`/`_run_waiters`）要求每个 queued run 在入队时就登记进 `_run_waiters` 并拥有一个**可 acquire 许可的独立 task**；理由: `cancel_subagent_run` 的取消实现是 `task = self._active_tasks.get(run.run_id)`（`manager.py:381`），排队 run 不在 `_active_tasks`，现有代码会走「task is None → 直接 return 原状态」（`:382-383`）而**不**标记 cancelled——run 永远停在 `queued`、waiter 永不 set、`session.active_run_id` 永不清空，该 session 被永久锁死；`get_subagent_run(wait=True)` 更是直接 `self._run_waiters[run.run_id]` 下标访问（`:369`），排队 run 若无 waiter 会抛 `KeyError` 并被 `RetryHook` 转成「不可重试错误」返回给模型（`agent/hooks/builtin/retry.py:48-49`）；来源: grill-subagent-concurrency-queue-2026-09-13
- **决策**: 本 change 落地时 `declared` 态不存在，实际状态机是 `queued→running→terminal`；现有 `_new_run` 把初始 `status="running"` 写死（`manager.py:311`），队列化后 spawn 时点应是 `queued`、由 worker 执行时转 `running`；理由: `to_result_dict`（`:74-92`）/`to_summary_dict`（`:107-116`）/`_find_run`（`:683-695`）都不读 status 做分支，新增 `queued` 值本身向后兼容；但 proposal 的 What Changes 写 `declared→…`（`proposal.md:34`）而 tasks.md 1.2 只写「增加 `queued` 态」（`tasks.md:10`），两处口径不一致，spec 同步前需统一，否则 artifact checker 侧的无歧义要求会打架；来源: grill-subagent-concurrency-queue-2026-09-13
- **决策**: 本 change 会**直接破坏** 2 个既有测试文件中的 4 个用例，`tasks.md` 6.2 的「适配既有测试」必须显式覆盖它们（不能只列 test_patterns 的「4 pattern 不回归」）；理由: (1) `tests/agent/subagent/test_guardrails.py:133-153` 与 `:156-171` 用 `pytest.raises(RuntimeError, match="concurrency limit")` 断言超限抛错——队列化后同一调用返回 `queued` envelope；(2) `tests/agent/subagent/test_subagent_manager.py:85-96` 断言 `run_subagent(wait=False)` 返回 `status == "running"`——`max_active` 满时改为 `queued`（注：该测试默认 `AsterwyndConfig()`，`max_concurrent_runs`/`max_active` 默认 5，单 run 仍返回 running，故此条为**条件性**破坏，取决于新 max_active 默认值）；(3) `tests/agent/test_config.py:140` 断言 `config.subagents.max_concurrent_runs == 4`，`:119/:128` 断言解析 yaml 的 `max_concurrent_runs: 6`；来源: grill-subagent-concurrency-queue-2026-09-13
- **决策**: `_parse_subagents_config` 必须同步改（`agent/config.py:1334-1354`）——只改 dataclass 默认值不会让 `max_active`/`max_queued_runs`/`max_spawns` 从 yaml 生效，因为解析函数是显式 `mapping.get(...)` 逐字段构造 `SubagentsConfig`，不是 `**mapping` 透传；理由: 代码事实（`config.py:1339-1353` 逐字段 `_validate_positive_int` 构造）；且 `SubagentsConfig` 是 `@dataclass(frozen=True)`（`:245`），新增字段后构造点全部需要同步，`_parse_subagents_config` 是唯一的生产构造点；来源: grill-subagent-concurrency-queue-2026-09-13

## Open Questions

- **Q1**: 队列满时 `queue_full` 的**返回形态**定哪个：`run_subagent` 返回带 `status: "queue_full"` 的 envelope（不创建 run record）、还是仍抛 `RuntimeError` 由 `RetryHook` 转成 `[Error: ...]` 文本？
  **场景**: 配 `max_active=5` / `max_queued_runs=20`。模型一轮发 25 个 `RunSubagent(wait=false)`（25 个不同 subagent）。前 5 个 acquire 许可执行，接着 20 个入队。第 26 个（第 26 次调用）到来时队列已满。
  - 选 envelope：模型看到 `{"status": "queue_full", "reason": "...queue is full (20/20)..."}`，可据此决定「先 `GetSubagentRun(wait=true)` 收几个结果再补发」。
  - 选异常：`RetryHook` 检查 `RETRYABLE_PATTERN`（`retry.py:18-21`，只匹配 timeout|connection|rate limit|429|503|temporary），`ERROR_PATTERN` 不含 `ERROR` 关键词 → 不重试、立即返回 `[Error: subagent queue is full ...]` 文本（`retry.py:48-49`）。
  - 连带问题：`queue_full` 是**瞬时**状态（等几十秒槽位就空），要不要进 `RETRYABLE_PATTERN` 让 RetryHook 自动退避重试（最多 3 次、退避 1s/2s/4s）？还是让模型自己重试？若进 RETRYABLE，`RetryHook` 的 `_is_retryable` 是按**异常消息**文本匹配（`retry.py:24-25, 48`），所以只有「选异常路径」才可能复用这一机制。

- **Q2**: `asyncio.Queue` 放在哪一级：**manager 单例**（`SubAgentManager.__init__` 持有）还是 per-orchestration？
  **场景**: 本仓每个 web session 各建一个 `SubAgentManager`（`web/session.py:447`），CLI/benchmark 也各一个（`agent/main.py:289`），所以「manager 单例」实际等于「per-orchestration，但嵌套 pattern 共享」——`RunPattern` 不新建 manager，pattern 内所有 worker 共享调用方那一个队列。真正的差别在**嵌套**：hierarchical pattern 的 manager 子 agent 若再 spawn 孙子，孙子与父级 worker 抢**同一个** `max_active` 名额（queue 在同一个 manager 上），此时「父 worker 占着名额等孙子」会不会重现自我饥饿？按 D1 父等待不持许可 → 不会死锁，但孙子会和同层的其他 worker 竞争名额，`max_active=5` 时一个 hierarchical(teams=4) 就吃掉 4 个名额。请确认接受「层级间共享同一名额池」还是要求「每层独立名额」（后者需要把 Queue 挂到 RunRequest/contextvar 上，是更大的改动）。
  另一子问题：`Queue` 在 `__init__` 里创建是否安全（`asyncio.Queue()` 在无 running loop 时构造不会报错，但 `SubAgentManager()` 现在在 sync 上下文被构造，见 `tests/agent/test_loop.py:145`）——请确认 queue 是 lazy 创建还是有别的约束。

- **Q3**: 队列等待时间算不算进 `max_time_s` / `timeout_s`？
  **场景**: 子 run 带 `max_time_s=60`。它在队列里排了 70 秒才轮到执行，执行本身只跑了 10 秒。当前 `started_at` 在 `_new_run` 里于**入队时**赋值（`manager.py:313`），`_monitor_run_timeout` 也是 `run_subagent` 里无条件 `asyncio.create_task`（`:352-353`）+ `await asyncio.sleep(run.max_time_s)`（`:656`）——若照搬，该 run 一执行就被判定超预算；更糟的是 `_monitor_run_timeout` 在排队期间醒来时 `self._active_tasks.get(run.run_id)` 必然返回 None（还没执行），直接 return（`:657-658`），等于**静默放弃**这次超时保护。
  - 选「计时含排队」：需改 `_monitor_run_timeout` 在 queued 期间也强制取消（从队列移除 + 标 `budget_exceeded`），语义是「排队也算花钱」。
  - 选「计时纯执行」：需把 `started_at` 挪到 worker 真正开始执行时赋值、monitor 也在那时才启动；`SubagentRunRecord.started_at` 的既有语义（`to_result_dict` 不暴露它，但 checkpoint/snapshot 用它）需一并确认。
  另请一并拍板 `RunSubagent(wait=true, timeout_s=10)` 超时后**被等的那个 run 怎么办**：保持现状（`asyncio.wait_for` 只取消等待方，run 继续跑到终态，调用方拿到的是 `queued`/`running` envelope，与现状一致）还是要求取消该 run？

- **Q4**: `queue_full` 之外，还有哪些「瞬时资源不足」信号要走非异常通道？以及 `max_active` 满但**队列未满**时 `wait=true` 的语义是否保证阻塞到终态？
  **场景 A**: `max_active=5`、`max_queued_runs=20`，模型发第 3 个 `RunSubagent(wait=true)`，此时 5 个名额全被别的 run 占着 → 第 3 个入队。`wait=true` 下它应该一直阻塞（跨 queue + 执行）到 completed，返回 `status: "completed"` —— 与现状 `await asyncio.wait_for(waiter.wait(), timeout_s)`（`manager.py:355-356`）语义一致，确认即可。
  **场景 B**: 同一轮里模型发 30 个 `RunSubagent(wait=true)`（D7 已标 parallelizable → `_execute_tool_calls` 会 `asyncio.gather` 全部，`loop.py:1275-1278`）。第 26 个撞 `queue_full`。此时该次 `execute` 返回 `queue_full`，模型这一轮的其它 25 个仍在跑——gather 会等到全部结束（最长 = 25 个串完队列的时间）。请确认：这 25 个是否要继续跑完（不因第 26 个失败而取消）？`_execute_tool_calls` 的 `asyncio.gather` 用 `return_exceptions=True`（`:1277`），不会取消其余项，所以现状即「继续跑完」，确认即锁定。

- **Q5**: 累计计数 `max_spawns=200` 的计数语义与作用域边界：`CreateSubagent` 算不算一次 spawn？
  **场景**: 模型调 1 次 `RunPattern(orchestrator-worker, workers=3)`：pattern 内部 `_spawn` 3 次 `create_subagent` + 3 次 `run_subagent`（`agent/subagent/patterns.py:102-107`），之后又把同一批 worker 用 `run_subagent` 跑第二轮（peer-review 就是这种复用：`patterns.py:107` 的 producer/reviewer 每轮重跑）。按 `max_spawns=200`：
  - 若「每次 `run_subagent`/`resume_subagent`/`create_subagent` 各计 1」→ 一个 orchestrator-worker(workers=3) 记 6 次；peer-review(max_rounds=3) 记 2 次 create + 最多 6 次 run = 8 次。200 的上限对本 change 的实际 fan-out 规模（max_active 5 + queue 20 = 25 并发窗口）意味着约 8~33 个 pattern 批次后拒绝——需确认这个量级是否符合「防 #69206 式 218 spawned」的设计目标。
  - 若「只有 `run_subagent` 计 1，`create_subagent` 不计」→ `CreateSubagent` 可以被刷爆（模型可空建 1000 个 session 不触发任何计数），需要确认是否接受。
  - 另：spec delta 的措辞是「每次创建或运行子 agent」（`specs/subagents/spec.md:53`），两种读法都成立，需拍板一种并回写 spec。
  **作用域子问题**: per-orchestration 的「根 run 起算」用哪个载体——ContextVar 里挂一个共享可变计数器对象（child task 继承的是对象引用，`+=` 需写成 `obj.n += 1` 才能跨任务可见）还是 manager 字段 + root_run_id 键？CLI 一次 `asterwynd run` 是「一个 orchestration」，`RunPattern` 也是一次，但 pattern 结束后计数器要不要复位？请指定「一次 orchestration 的生命周期边界」。

- **Q6**: D4 的深度判据用**子 run 自己的 depth** 还是 `current_spawn_depth()`？以及深度到限的子 agent 还能不能看到 `GetSubagentRun`/`ListSubagents`？
  **场景 A**: 根 loop（depth 0）spawn 一个子 run → 该子 run depth=1，其内部 `current_spawn_depth()` 也是 1（`test_guardrails.py:68-84` 钉死了这个等价）。`max_depth=3` 时：depth=1 的子 agent 还能 spawn（生 depth=2），depth=3 的子 agent 不能再 spawn。
  - 若判据写成 `current_spawn_depth() >= max_depth`（design D4 原文，`design.md:59`），在**排队延迟执行**场景下 contextvar 已在父任务结束的 finally 里 reset（`manager.py:345-346`）→ worker 执行时读到父的旧值甚至 0 → 该撤的工具没撤，模型以为还能 spawn，一调就被准入层 fail-fast 抛错（正是 D4 要消灭的「抛错诱使重试」）。**必须**改成读 run 记录的显式 `depth` 字段（D6），请确认这条耦合。
  - 子问题：`expose_subagent_tools=False` 会**整组**不注册 10 个工具（`loop.py:358-371`：Create/Run/List/Get/Cancel/Inspect/PublishBus/ReadBus/Resume/RunPattern）。意味着到限子 agent 连 `GetSubagentRun`（读自己的孩子结果）和 `InspectSubagentTranscript` 都没了。spec delta 只说「移除 spawn 类工具（CreateSubagent/RunSubagent/RunPattern/ResumeSubagent）」（`specs/subagents/spec.md:35`），与「一刀切关 expose_subagent_tools」的实现口径不一致——请拍板：是精确移除 4 个 spawn 工具、保留 List/Get/Cancel/Inspect/Bus（需给 AgentLoop 增加一个「部分注册」通道，改动比现有 bool 开关大），还是接受粗糙的一刀切（复用现有开关、改动量最小，但超出 spec delta 的措辞，spec 需相应放宽）？

- **Q7**: `asyncio.Queue` 不支持从中移除任意元素——排队 run 被取消后怎么处理？
  **场景**: 队列里有 20 个 queued run，模型对第 7 个调 `CancelSubagentRun`。`asyncio.Queue.get()` 是 FIFO 且无 `remove` API。两种做法：
  - **惰性跳过**：标记 `run.status = "cancelled"`（同时 `session.active_run_id = None` + waiter.set()），worker 出队后检查到已终态就立刻放下一个。队列长度此时按「已取消项也占位」算，`max_queued_runs` 判定会偏保守。
  - **改用可移除容器**：`collections.deque` + `asyncio.Condition`（或自建 `_pending` dict），取消时真正摘除，队列名额立刻释放，但实现复杂度上升、且要自己实现 FIFO 唤醒。
  请拍板采用哪种，以及 `cancel_subagent_run` 对 queued run 的返回 envelope 是 `cancelled` 还是别的状态。另请一并确认：`_active_tasks` 的语义在队列化后是「只装 running 的 task」（`_check_guardrails` 的 `len(self._active_tasks)` 改为读许可计数）还是保留双用途。

- **Q8**: 同 session 拒绝时的**报错文案与 error_type**要不要改？以及 `RunSubagent` 工具 description 里 `wait` 的默认值是否要显式写清楚？
  **场景**: 模型拿 `{"status": "queued", "run_id": "abc"}` 后（`wait=false` 默认，`subagents.py:68`），它需要知道下一步该 `GetSubagentRun(wait=true)`。当前工具 description 只有一句 `"Start a new run in an existing child subagent session."`，没有任何「返回可能是 queued、需要轮询」的提示；`GetSubagentRun` 的 description 也只有 `"Get the result or current status of a child subagent run."`。若不做提示，模型可能把 `queued` 当成「已开始」而继续做别的事、忘记收敛结果（#69206 类「spawn 了不管」的失败模式）。请拍板：(a) 只改工具 description 注入「queued 语义 + 收结果建议」；(b) 在 run envelope 里加一个 `next_action` 提示字段；(c) 不改（依赖模型自己看 status）。同时确认 `run_subagent(wait=False)` 在 `max_active` 未满时仍返回 `running`（不统一改叫 queued），以保住 `tests/agent/subagent/test_subagent_manager.py:85-96` 这条既有断言。

> 说明：另有一处需在实现期留意的既有口径冲突——本 change 修改的是 `subagents` 能力域，但「并发/深度护栏超限拒绝」这条既有 spec 要求位于**另一个**能力域 `openspec/specs/multi-agent-collaboration/spec.md:43`（"SHALL reject spawns exceeding the limits"）。本 change 的 delta 未 MODIFIED 该条，sync 归档时会留下一条与「排队而非失败」相矛盾的现行 spec。此条不需要用户拍板，但收尾阶段必须处理（改 `multi-agent-collaboration` 的 delta 或在 sync 时同步修订），建议在 tasks.md 6.4 显式加一句。

## User Confirmation

- **Q1**: 用户答复：返回带 `status: "queue_full"` 的 envelope（不创建 run record），不进 RetryHook；确认时间: 2026-09-13
- **Q2**: 用户答复：确认采用选项 A——`asyncio.Queue`/执行许可挂在 `SubAgentManager`，同一 manager 内所有 orchestration depth 共享一个 `max_active` 名额池和一个 `max_queued_runs` 队列；`max_active` 是 manager 作用域内实际 LLM/tool 执行的全局物理并发上限，D1 已保证父等子释放许可、不因 hierarchical 嵌套自我饥饿；不采用每层独立名额（会让并发上限膨胀为按 depth 倍增）；确认时间: 2026-09-13
- **Q3**: 用户答复：计时纯执行——`started_at` 挪到 worker 真正开始执行时赋值、monitor 也在那时才启动，排队不耗预算；`wait=true` 超时后 run 保持现状继续跑到终态（不取消）；确认时间: 2026-09-13
- **Q4**: 用户答复：一轮多个 `wait=true` 撞 queue_full 时其余 run 继续跑完（不因一个失败取消，gather return_exceptions 现状）；`wait=true` 跨队列+执行阻塞到终态；`max_active` 未满时 `run_subagent(wait=false)` 仍返回 running（保既有测试）；确认时间: 2026-09-13
- **Q5**: 用户答复：`create_subagent` 和 `run_subagent`/`resume_subagent` 各计 1（累计 spawn 计数含 create，防空建 session 刷爆）；确认时间: 2026-09-13
- **Q6**: 用户答复：精确移除 4 个 spawn 工具（CreateSubagent/RunSubagent/RunPattern/ResumeSubagent），保留 List/Get/Cancel/Inspect/Bus——到限子 agent 仍能读自己孩子的结果；需给 AgentLoop 增加「部分注册」通道；深度判据读 run 记录的显式 depth 字段（非 current_spawn_depth()）；确认时间: 2026-09-13
- **Q7**: 用户答复：惰性跳过——取消排队 run 时标 `status=cancelled` + 清 `active_run_id` + `waiter.set()`，worker 出队发现已终态即跳过；队列长度按已取消项也占位（偏保守）；确认时间: 2026-09-13
- **Q8**: 用户答复：改 `RunSubagent`/`GetSubagentRun` 工具 description，注入「返回可能 queued，需 GetSubagentRun(wait=true) 收敛结果」的提示；不加 next_action 字段；确认时间: 2026-09-13

## 风险

- **严重: 排队 run 的 contextvars 丢失会让 D4 静默失效**（带 file:line）: `_launch_run` 的 depth 传递依赖 create_task 的 context 拷贝（`manager.py:340-346`），队列化后若 worker 用长驻任务出队 await，排队 run 会看到 depth 0 / bus None。后果不是报错而是**静默降级**：深度到限的判定失效 → 本该撤工具的子 agent 拿到 spawn 工具 → 一调就被准入层抛错。D4 与 D6 的耦合必须在实现里显式绑定（读 run 记录的 depth），仅靠 design.md 的分段描述会漏。
- **严重: 取消/超时路径在队列态下是死路**（带 file:line）: `cancel_subagent_run` 靠 `_active_tasks.get(run_id)`（`manager.py:381`）找任务，排队 run 不在其中 → 走 `:382-383` 直接 return，`session.active_run_id` 不清空 → 该 subagent_id 永久无法再 run（`run_subagent` 入口 `:220-221` 抛 "already has an active run"）。这是纯状态泄漏，测试不覆盖就会带到线上。
- **严重: `_monitor_run_timeout` 在排队窗口静默失效**（带 file:line）: monitor 在 spawn 时启动、`sleep(max_time_s)` 后查 `_active_tasks`（`:656-658`），排队期间查不到任务直接 return，超时保护彻底丢失；配 Q3 的 `started_at` 语义一起决定，否则「带 time budget 的 run 排长队后无保护执行」。
- **中: `max_concurrent_runs` → `max_active` 的配置迁移若无别名会静默改变已有部署行为**: `SubagentsConfig` 是 frozen dataclass（`config.py:245`），`_parse_subagents_config` 用显式 `mapping.get("max_concurrent_runs", 4)`（`:1339`）。若删旧键，用户 yaml 里的 `max_concurrent_runs: 6` 变成未识别字段（是否报错取决于 `_expect_mapping` 之外的未知字段策略，本仓未见未知键校验）+ 静默回落到 `max_active=5`；且 `tests/agent/test_config.py:119/128/140` 三条断言会红。
- **中: 一并合跑 `wait=true` 时的端到端延迟放大**: D7 标 parallelizable 后，一轮 25 个 `RunSubagent(wait=true)` 会被 `asyncio.gather`（`loop.py:1275`）全部并发派发，但每轮最多 5 个真执行 → 第 25 个要等前 20 个串完队列。父 loop 的 handler 阻塞时间从「最慢一个工具」变成「全部 tool-call 串完队列」，benchmark 的 timeout 阈值与 trace 的 handler 时长统计口径需对照检查（`docs/benchmark-plan.md` 未列本项）。
- **中: `GetSubagentRun(wait=true)` 的 waiter 下标访问是既有脆弱点，队列化会放大**（带 file:line）: `manager.py:369` 直接 `self._run_waiters[run.run_id]`，而 `wait` 分支只在 `run.status == "running"` 时进入（`:368`）。队列化后新增两种触发：run 在 queued 态时 `wait=true` 不进入等待分支（返回 `queued` envelope，语义可疑）；run 已终态且 waiter 已被 `_execute_run` finally pop（`:476`）时若有并发调用会 `KeyError`。建议改为 `.get()` + 状态复查。
- **低: `inspect_transcript` 的 summary scope 在 queued 期间返回空串**（带 file:line）: `manager.py:407` 取 `session.runs[-1].summary`，queued run 的 `summary` 为初始值 `""`（`:58`），调用方无法区分「还在排队」与「没有输出」；`inspect_transcript` 响应里没有 status 字段（`:404-415`）。低危但影响可观测性。
- **低: 队列满导致「声明」并非永成功，与 proposal 的叙事有落差**: proposal 写「队列化让『声明』永成功（受累计计数约束）」（`design.md:87`），但 `queue_full` 实际是**失败**信号。模型侧应被引导成「先收结果再补发」而非「重试到成功」，工具 description 若不写清楚，`queue_full` 与并发上限会以同样的方式卡住模型（与 #68110 的失败模式同源）。
- **低: `_build_subagent_loop` 的签名兼容**（带 file:line）: 现有测试直接 `manager._build_subagent_loop(AgentMode.BUILD)`（`tests/agent/subagent/test_guardrails.py:50`、`tests/agent/test_loop.py:2144`）。D4 改成「按深度决定 expose_subagent_tools」后若给该函数加必填参数，这两处会红；建议从 manager 上的显式 run 上下文取值或给默认值（`depth=None` → 沿用现状 True）。
