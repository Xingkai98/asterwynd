# Building Review: subagent-concurrency-queue

- Reviewer（Round 1）: 独立零记忆 building 审阅员（/review-loop）
- 审阅时间: 2026-09-13
- base sha: `bdd0eda`（本分支真实 fork 点）
- head sha（Round 1）: `5342382`；Round 2 复审 head: `ea22b65`（修复 commit `d868184`）
- 审阅范围: `git diff bdd0eda` — 15 files, +1784/-92（agent/config.py、agent/loop.py、agent/subagent/context.py、agent/subagent/manager.py、agent/tools/builtin/subagents.py、4 个测试文件、6 个 OpenSpec 文档）

## Verdict

**PASS**（Round 2 复审，2026-09-14）

Round 1 的三个 issue 已由修复 commit `d868184` 全部修复，Round 2 独立核验通过。Round 1 的详细判定与证据保留在下方，Round 2 的核验过程、falsifiability 结果与门禁复跑见文末「Round 2 复审」节。

Round 1 verdict（历史）: **CHANGES_REQUESTED** — 并发许可在「任务已创建但尚未进入首步就被取消」的路径上永久泄漏，导致整个并发池永久停滞；另有 2 个中等问题。

---

## 任务逐项验证

| Task | 状态 | 证据 |
|------|------|------|
| 0.1 grill 产出 | ✅ | `reviews/grill-design.md` 存在，8 条 Confirmed Decisions + 8 条 Open Questions + 8 条 User Confirmation（含时间戳，无占位文本） |
| 1.1 config 三字段 + 解析 | ✅ | `agent/config.py:265-267` 三字段；`config.py:1356-1372` `_parse_subagents_config` 显式解析；legacy alias `config.py:273-275` |
| 1.2 queued 态 + 入队即返回 | ✅ | `manager.py:531` 初始 `status="queued"`；`run_subagent` 经 `_enqueue_run` 返回 envelope（`manager.py:450-451`） |
| 1.3 身份字段 | ✅ | `SubagentSessionRecord` 四字段 `manager.py:126-129`；`to_summary_dict` 暴露 `:140-143` |
| 2.1 准入层/排队层拆分 | ✅ | `_check_admission` `manager.py:1136-1156`（depth + spawn 预算 fail-fast，无并发检查）；排队 `_pending` + `_pump_queue` `:611-629` |
| 2.2 有界队列 + queue_full | ✅ | `_take_back_if_queue_full` `manager.py:674-713`；实测 `test_queue_full_returns_signal_without_creating_run_record` 通过 |
| 2.3 `_active_tasks` 只记执行任务 | ✅ | `manager.py:646` 仅在 `_start_task`（已持许可）时登记；实测排队 run 不入 `_active_tasks` |
| 3.1 许可绑执行 | ⚠️ | acquire 在 `_pump_queue` `:626`，release 在 `_execute_run` finally `:825` — **release 位置有缺口**，见 Issue 1 |
| 3.2 父等子不自我饥饿 | ✅ | `_wait_for_run` `manager.py:583-609` suspend/resume 语义正确；`test_parent_run_releases_permit_while_waiting_on_child` 通过。**注**：该测试只覆盖"子已启动执行"的场景，未覆盖"子尚未启动父已返回"（见 Issue 1） |
| 4.1 深度撤 4 个 spawn 工具 | ✅ | `SPAWN_TOOL_NAMES` `manager.py:282-287`；`_build_subagent_loop` 判据读显式 `depth`（非 contextvar）`:930-933`；`unregistered_subagent_tools` 部分注册通道 `loop.py:359-388`；实测保留 6 个读/bus 工具 |
| 4.2 累计 spawn 计数 | ✅ | `_spawn_count` `manager.py:344`；`create_subagent` `:404` 与 `_enqueue_run` `:568` 各 +1；超限 `_check_spawn_budget` `:1158-1163` |
| 4.3 max_depth 程序性 fail-fast | ✅ | `_check_admission` `manager.py:1150-1155` 保留；`test_depth_guard_rejects_without_run_record` 通过 |
| 5.1 parallelizable | ✅ | `subagents.py:73`（RunSubagent）、`:133`（GetSubagentRun）`= True`；RunPattern 未标（默认 False）；端到端 `test_run_subagent_calls_in_one_turn_execute_as_one_parallel_group` 通过 |
| 6.1 回归测试 7 条 | ✅ | `test_concurrency_queue.py` 20 个用例覆盖 7 条；三个严重风险均有对应测试（见"测试覆盖"节） |
| 6.2 既有测试适配 | ✅ | test_guardrails 4 处改写（fail-fast→queued）、test_config 3 处迁移 + 2 处新增、`_build_subagent_loop` 加 `depth=None` 默认值兼容 |
| 6.3 benchmark smoke | ✅ | 实测 `Benchmark run ... Tasks: 72 | passed: 5 | warnings: 0 | unsupported: 38 | failed: 29`，exit 0 |
| 6.4 spec sync | ⏸️ | 按 tasks 声明归 closing，不计缺 |
| 6.5 全量 pytest + 门禁 | ✅ | 实测 2225 passed, 8 skipped in 172.59s；artifact checker passed；validate --all --strict 30 passed |

---

## Issues

### Issue 1（严重 · 新增回归）— 并发许可在「已创建任务但未进入首步即被取消」路径上永久泄漏，导致并发池永久停滞

**证据（文件:行号）**

- `manager.py:643-647`：`_start_task` 用 `asyncio.create_task` 创建 `_execute_run_in_context`，并只把 `_active_tasks` 的清理挂在 `add_done_callback`：
  ```python
  bg_task = asyncio.create_task(self._execute_run_in_context(item), context=item.context)
  self._active_tasks[run.run_id] = bg_task
  bg_task.add_done_callback(lambda _: self._active_tasks.pop(run.run_id, None))
  ```
- `manager.py:825`：许可释放唯一落在 `_execute_run` 的 `finally`。
- `manager.py:760`：`cancel_subagent_run` 对运行中的 run 调 `task.cancel()` 后 `await task`。

**根因**：`_execute_run` 的 `finally` 只有在协程**至少执行过一次 `await`** 后才会被取消触发。若 run 的 task 建好后尚未跑到第一个挂起点就被 `task.cancel()`（经典 asyncio 语义：cancelled-before-first-step），协程体从未进入，`finally` **不会执行** → `self._permits.release(run.run_id)` 被跳过 → 该 run 的许可永久占用。`add_done_callback` 仍会触发（我在隔离环境实测确认：done-callback 触发、`finally` 不触发），但回调只清 `_active_tasks`，不释放许可。

**触发路径（真实，可经 AgentLoop 工具调用）**：模型一轮内先 `RunSubagent(wait=false)` 再 `CancelSubagentRun`。关键在于 `_enqueue_run` 的 `wait=false` 分支（`manager.py:550-581`）**全程不 await 到挂起点**（`_pump_queue`、`_take_back_if_queue_full` 都是同步函数），所以 `await self._enqueue_run(...)` 返回时事件循环根本没被让出 → `create_task` 建出的 task 尚未跑到首步；紧接着同一轮里 `CancelSubagentRun` 调 `task.cancel()` → cancelled-before-first-step → 泄漏。**注**：`CancelSubagentRunTool` 并未标 `parallelizable`（`subagents.py:161`），所以两个工具在 `_execute_tool_calls` 里分属不同组（serial），但这**不影响**触发——因为中间没有任何让出点。我构造了该真实路径的复现（`AgentLoop` + 脚本化 LLM 在同一轮发这两个工具调用），实测 `permits in_use = 1 holders = {cancelled_run_id}`，即 `LEAKED`；并单独实测 `enqueue(wait=false)` 返回后 task 已在 `_active_tasks`、却未被执行（无 yield），确认机制。跨轮的 Run→Cancel 通常不会触发（轮间 LLM await 会让出，task 已跑过首步）；**同轮**是触发窗口。

**影响（严重）**：许可池是 manager 作用域的全局物理并发上限，泄漏一个许可就永久降低有效并发；把 `max_active` 个许可耗光后，**队列永不排空**：后续所有 `run_subagent(wait=true)` 会抛 `TimeoutError`、`wait=false` 永远返回 `queued`，即使队列远未满。实测：泄漏 1 个许可（`max_active=1`）后，新建 run 无论 `wait=true`（TimeoutError）还是 `wait=false`（永久 queued）都永远拿不到执行，队列深度持续增长。这是单调、不可自愈的（无许可回收通道）。

**是新增回归（非既有缺陷）**：我在 fork 点 `bdd0eda`（master 等价）的独立 worktree 跑了同一场景——master 用 `_active_tasks` 记并发、无许可池，取消后 `b` 正确进入 `running`，无泄漏。master 的任务注册模型不会出现该失效模式；许可池是本 change 引入的，故 release 覆盖缺口也是本 change 新引入。

**既有测试为何没抓到**：`test_subagent_manager.py:183-200` 与 `test_budget_snapshot.py:265+` 都调 `cancel_subagent_run`，但（a）均未断言许可/并发账目、（b）`test_subagent_manager.py` 场景下 task 恰好已跑到 `await` 挂起点（SlowLLM 的 `asyncio.sleep(10)`），`finally` 正常执行，掩盖了缺口。我实测 `test_subagent_manager.py::test_cancel_subagent_run_marks_cancelled` 的等价场景：测试通过，但 `permits in_use = 1`（泄漏被静默吞掉）。`test_concurrency_queue.py` 现有的 `in_use == 0` 断言（`:239/:377/:389`）都发生在 run 正常完成或排队态惰性取消的路径，未覆盖"运行中 run 在首步前被取消"。

**期望行为 / 修复方向**：许可释放必须对"从未进入协程体"的取消也生效。最小修复：把许可释放（以及 waiter 唤醒 + `_pump_queue`）并入 `manager.py:647` 的 done-callback，利用 `_ExecutionPermits.release` 的幂等性（`manager.py:251-256` 仅在 `_holders` 命中时递减），使其对正常完成路径是 no-op：
```python
def _on_done(_):
    self._active_tasks.pop(run.run_id, None)
    self._permits.release(run.run_id)          # idempotent
    w = self._run_waiters.pop(run.run_id, None)
    if w is not None: w.set()
    self._pump_queue()
bg_task.add_done_callback(_on_done)
```
我实测该补丁：`BEFORE FIX: a leaked=True | b.status=queued | in_use=1` → `AFTER FIX: a leaked=False | b.status=running | b holds=yes`。请实现 agent 采用等价的"释放不会漏"方案（而不是只把 `release` 从 `_execute_run` 挪走——两条路径都要因幂等而安全）。

**必须补回归测试**：新增一条"运行中 run 在被取消前未进入首步 → 许可不泄漏"的测试。构造法：`run_subagent(wait=false)` 后**不** `await asyncio.sleep(0)`/不 yield，直接 `cancel_subagent_run`，断言 `manager._permits.in_use == 0` 且后续 queued run 能被泵起。现有 `test_execute_run_...` 类断言都需保证覆盖这条 never-started 路径。

---

### Issue 2（中 · 注释与行为不符 + 预算语义）— `queue_full` 的 spawn 仍消耗累计预算，与 `manager.py:567` 注释相反

**证据**：`manager.py:567` 注释写 "计数在真正接单之后（被 queue_full 拒绝的 spawn 不消耗预算）"，但 `_count_spawn()` 在 `:568` 于 `_pump_queue()`/`_take_back_if_queue_full()`（`:577-578`）之前无条件执行。实测：`max_active=1, max_queued_runs=1`，3 次 `create_subagent`（count=4）+ 1 次成功 run（count=5→6 语义略）后，被 `queue_full` 拒绝的那次调用仍使 `_spawn_count` 从 6 增到 7（`queue_full consumed budget? True`）。

**影响**：中等。① 注释与实现直接矛盾；② 语义上"被拒绝的请求不该消耗预算"，否则反复撞 `queue_full` 的模型会加速耗尽 `max_spawns`（虽然 200 的量大，但语义错误会在 C2 改成 per-orchestration 复位时放大）。`_enqueue_run` 里 `_count_spawn()` 应先判 `queue_full` 再计数，或把计数挪到 `_pump_queue` 真正接单成功后。

**期望行为**：`queue_full` 被拒的 spawn 不递增 `_spawn_count`（与注释一致），并把注释与实现对齐。

**补测试**：断言 `queue_full` 前后 `_spawn_count` 不变。

---

### Issue 3（中 · 观测量缺陷）— 队列窗口内 `max_spawns` 之外的 `inspect_transcript` summary 返回空串，无法区分"排队中"与"无输出"

**证据**：`manager.py:783` `latest = session.runs[-1].summary if session.runs else ""`；queued run 的 `summary` 为初始 `""`（dataclass 默认 `:70`）。响应体（`:784-791`）不含 `status` 字段。

**影响**：中等（可观测性）。父 agent 在 run 仍 `queued` 时调 `InspectSubagentTranscript` 会拿到空 summary，无法区分"还在排队"与"跑完了但没输出"。grill 风险清单已把它列为"低"，但队列化把这个窗口从"几乎不存在"放大成"常态"。

**期望行为**：`summary` scope 的响应带上 run 的 `status`（和/或对 queued run 返回如 `"[queued: not started]"` 的占位），让调用方能区分。

---

## 门禁复跑结果（自己跑，非信任上一轮）

```
$ uv run pytest tests/agent/subagent/test_concurrency_queue.py \
    tests/agent/subagent/test_guardrails.py tests/agent/subagent/test_patterns.py \
    tests/agent/test_config.py -q
80 passed in 1.95s
（末尾伴随 2 条 "Task was destroyed but it is pending!" 警告，指向 manager.py:672
  _execute_run_in_context —— 见下"特别核验点"）

$ uv run pytest -q
2225 passed, 8 skipped, 19 warnings in 172.59s (0:02:52)

$ PYTHONPATH=. python3 scripts/check_openspec_artifacts.py
OpenSpec artifact checks passed

$ npx --yes @fission-ai/openspec@1.4.1 validate --all --strict
Totals: 30 passed, 0 failed (30 items)

$ uv run asterwynd benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/smoke-verify
Tasks: 72 | passed: 5 | warnings: 0 | unsupported: 38 | failed: 29   (exit 0)
```

> **注（本轮 report 落盘后的门禁状态）**：以上 artifact checker 的 `passed` 是**本 report 落盘前**的状态（reviews/ 下只有 grill-design.md，不匹配 `*-review.md` glob）。本 report 落盘后 checker 会 fail-closed 报 `review manifest missing: .../building-review-manifest.json` —— 这是**预期行为**：`verify_review_manifest` 要求每个 `*-review.md` 有 verdict=PASS 的 manifest，而本轮 verdict 是 CHANGES_REQUESTED，**不应**写 PASS manifest（写了就是伪造通过）。正确闭环是：实现 agent 修 Issue 1（+回归测试）→ 重跑 `/review-loop` 得 PASS → 由审阅闭环写 `building-review-manifest.json` → checker 恢复绿。故当前 CI 红是"尚不可合入"的正确信号，非缺陷。

## 特别核验点（主 session 标的两处红旗）

**红旗 1 — `Task was destroyed but it is pending!`（`manager.py:672`）**: **不是真实泄漏/竞态**，属 pytest 收尾的正常现象。该 task 停在 `await loop.run()`（SlowLLM `asyncio.sleep(10)`）处于正常挂起态，不是死锁；测试函数已返回、fixture loop 已关闭，任务在解释器退出时被 GC，故 atexit 打印警告。判定依据：① 单个测试文件单独跑无警告，仅 queue+guardrails 合跑出现（GC 时机依赖）；② master 等价文件已用同一 `SlowLLM`/`sleep(10)` 模式，是既有测试写法；③ 信号是"pending"（挂起），与 Issue 1 的"许可泄漏"是不同性质——Issue 1 是 `finally` 未执行导致的账目永久失衡，与 GC 无关。**唯一建议**：这些单测最好 `cancel`/`await` 掉自己创建的 run（测试卫生），但这不构成 CHANGES_REQUESTED 理由。

**红旗 2 — `agent/config.py` 是否真在 diff 里**: **在**。`git log --oneline -- agent/config.py` 显示 commit `6e324c6` 修改了它；`git diff bdd0eda --stat` 明确列出 `agent/config.py | 40 +-`。（第一次 `git diff master --stat` 的困惑源于**本地 `master` ref 停在 `cb9902c`，落后 origin 两个 PR（#168/#169）**，导致 README/.env.example/OrcaRouter 等变更以噪声形式混入 diff；以真实 fork 点 `bdd0eda` 为准，diff 干净只含本 change 的 15 个文件。）

## 冗余度 / 可维护性评估

- **无该删没删的旧代码**：全仓 `max_concurrent_runs` 只剩兼容别名（`config.py:258/273/1361`、`manager.py:302/324/348`）与测试引用，无旧 fail-fast 分支残留；`grep "concurrency limit"` 仅命中注释/工具描述文本。
- **实现清晰**：`_ExecutionPermits` 的 suspend/resume/wake 语义自洽（`available` 减去 resuming 占位、herd-wake 幂等复查），`_pump_queue`/`_start_task`/`_execute_run_in_context` 职责分层清楚；D6 的显式 depth 传递（`_execute_run_in_context` 安装 `set_spawn_depth`/`set_current_run_id`）与 grill 决议 2/3 一致。**唯一 hack 感**是 Issue 1 的"许可释放只挂 `finally`"，语义上应视为"与 task 生命周期绑定"而非"与协程体绑定"。

## 测试覆盖评估

7 条 grill 回归 + 三个严重风险覆盖情况：队列化 ✅、wait 语义 ✅、父等子不自我饥饿 ✅（**但只覆盖子已启动分支**）、深度撤工具 ✅（单测 + 端到端）、累计计数 ✅、queue_full ✅、depth fail-fast ✅。三个"严重"风险中：②contextvars 丢失 ✅（`test_queued_run_keeps_identity_after_spawning_context_is_gone` 实测断言 depth=3、bus 同对象）、③cancelled-queued 死路 ✅（`test_cancel_queued_run_marks_cancelled_and_frees_session`，惰性跳过 + session 可重跑）、**①`_monitor_run_timeout` 排队窗口失效** ✅（`test_queued_run_time_budget_starts_at_execution`，monitor 移到执行时启动）。**缺口**：运行中 run 的取消路径未断言许可账目（Issue 1 逃逸的根因），且 `queue_full` 的预算消耗未断言（Issue 2）。

## 结论

实现质量总体高、门禁全绿、D1–D7 与 grill 决议落地准确，但 **Issue 1 是一个可经真实工具路径触发、导致并发池永久停滞的严重回归**，且现有测试恰好绕过了它。按 verdict 规则（存在 correctness 问题）→ **CHANGES_REQUESTED**。修 Issue 1（含回归测试）后可复审；Issue 2、3 建议同轮一并修（都是低改动量、有明确期望行为）。

---

# Round 2 复审（2026-09-14）

- Reviewer（Round 2）: 独立零记忆 building 复审员，**不继承** Round 1 上下文
- Verdict: **PASS**
- base sha: `bdd0eda`（fork 点）；head sha: `ea22b65`；修复 commit: `d868184`
- reviewer run id: `review-subagent-concurrency-queue-20260914-r2`
- 核验方式: 自己读代码 + 自己构造复现（含 AgentLoop 真实工具路径）+ falsifiability（把 `manager.py` 回退到 `5342382` 重跑，确认新测试确会红）+ 门禁复跑

## Issue 逐项核验结论

### Issue 1（严重 · 许可泄漏）— **已修复 ✅**

- **修复实现**：`_start_task` 把 done-callback 由 `lambda _: self._active_tasks.pop(...)` 换为 `lambda _: self._on_run_task_done(run.run_id)`（`manager.py:653`）；`_on_run_task_done`（`manager.py:663-676`）对 task 的**每种终态**都执行 `_active_tasks.pop` + `_permits.release(run_id)` + waiter 唤醒 + `_pump_queue()`，而非只依赖协程体的 finally。`_execute_run` 的 finally（`:850-856`）保留 `release`，两条路径靠 `_ExecutionPermits.release` 的幂等性（`:251-256`，仅当 run_id 命中 `_holders` 才递减）互不冲突。
- **不双释放 / 不负计数**：正常完成路径下 finally 与 done-callback 都跑，第二次 `release` 因 run_id 已不在 `_holders` 而 no-op。我构造 `test_r2_double_release_and_negative_count`（单跑 + 4 并发 wait=true）与 `test_r2_many_iterations_no_drift`（30 轮 run+cancel 混合），post-让出 `in_use == 0`、`holders == frozenset()`，无负计数、无漂移。release 唯一递减点且被 `_holders` 命中守卫；`try_acquire`/`resume` 是唯一递增点，run_id 唯一且不会重复入 `_holders`，故 `_in_use` 不可能为负。
- **不泄漏（核心）**：我构造了与 Round 1 同款的**真实工具路径**复现 `test_r2_same_turn_run_then_cancel_through_agentloop`——`AgentLoop` + 脚本化 LLM 在同一轮发 `RunSubagent(wait=false)` → `CancelSubagentRun`（无让出点）。post-fix `in_use == 0`，后续 run 立即 running 并 completed。
- **falsifiability**：把 `manager.py` 回退到 `5342382` 重跑同一测试 → `AssertionError: LEAKED in_use=1 holders=frozenset({'98649fb31e2a'})`（并带 `Task was destroyed but it is pending!` 于 `:672`）。修复后同一测试转绿。新增的 `test_cancel_before_first_step_releases_permit`（仓库内）在 pre-fix 同样红、post-fix 绿。**机制与修复均确认有效**。
- **排空确认**：`max_active=1` 下 first 占槽 + second 排队 → never-started cancel first → second 被泵起并 completed、`in_use == 0`（`test_r2_pool_recovers...`）。saturate 探测（50 轮 ×2 run 全 never-started cancel）后 `in_use` 恒为 0。
- **补充（无新竞态）**：`_on_run_task_done` 无条件 `_pump_queue()` 是同步调用，done-callback 在 loop 上经 call_soon 执行，无重入风险；waiter pop 幂等。父 run waiting 时 suspend 语义与 done-callback 释放互不干扰（父 task 未终结，其 done-callback 尚未触发），既有 `test_parent_run_releases_permit_while_waiting_on_child` 仍绿。

### Issue 2（中 · queue_full 耗预算）— **已修复 ✅**

- **修复实现**：`_count_spawn()` 从 `_enqueue_run` 的 `:565`（pump 前）挪到 `_pump_queue()` + `_take_back_if_queue_full()` **之后**（`manager.py:575-579`），注释与实现一致（`manager.py:578`）。被 `queue_full` 拒绝的 spawn 在 `_take_back_if_queue_full` 内 `return True`，`_count_spawn` 被跳过。
- **核验**：`test_queue_full_rejection_does_not_consume_spawn_budget`（仓库内）通过；我另写 `test_r2_queue_full_does_not_consume_budget` 断言 `_spawn_count` 前后不变，通过；pre-fix 该断言红。接受路径仍计数（既有 D5 spawn-budget 测试全绿，`_check_spawn_budget` 由 `create_subagent` 与每次 run 接入生效）。

### Issue 3（中 · inspect summary 无 status）— **已修复 ✅**

- **修复实现**：`inspect_transcript` 的 summary scope 返回体新增 `status` 字段（`manager.py:809-817`）。三种情况覆盖：`status="queued"`（仅校验过 queued 分支）、`status="completed"` + 非空 summary、`session.runs` 为空时 `status=None` + `summary=""`（`manager.py:804/813-814`）。`recent_messages` scope 不变。
- **核验**：`test_inspect_transcript_summary_reports_run_status`（仓库内）断言 queued→`status=="queued"/summary==""`、completed→`status=="completed"/summary=="done"`，通过；我另测无 run 时 `status is None`，通过；pre-fix 该测试 `KeyError: 'status'` 红。既有 `test_inspect_transcript_summary_returns_latest_run_summary` 只需 `summary` 键，加字段不破坏。

## 回归检查（D1–D7 未被破坏）

`uv run pytest tests/agent/subagent/ tests/agent/test_config.py -q` → **130 passed**。三个修复未触及队列准入/泵/深度工具撤除/累计计数/并行组语义，仅改动终态清理与观测字段。无测试删改。

## 门禁复跑结果（Round 2，自己跑）

```
$ uv run pytest tests/agent/subagent/test_concurrency_queue.py \
    tests/agent/subagent/test_guardrails.py tests/agent/subagent/test_patterns.py \
    tests/agent/test_config.py -q
83 passed in 1.99s

$ uv run pytest -q
2228 passed, 8 skipped, 19 warnings in 129.28s (0:02:09)

$ PYTHONPATH=. python3 scripts/check_openspec_artifacts.py
ERROR: subagent-concurrency-queue: review manifest missing: .../building-review-manifest.json
（Round 1 report 落盘后、PASS manifest 落盘前的**预期**状态；本 PASS manifest 落盘后转绿。）

$ npx --yes @fission-ai/openspec@1.4.1 validate --all --strict
Totals: 30 passed, 0 failed (30 items)
```

> Round 1 提到的 `Task was destroyed but it is pending!`（`manager.py:672`）在 Round 2 单独复跑 `test_concurrency_queue.py + test_guardrails.py` 时未复现，与 Round 1 判定的「GC 时机依赖、非真实泄漏」一致。

## Round 2 结论

三个 issue 全部修复且经独立复现与 falsifiability 确认有效，无新引入的双释放/负计数/竞态，D1–D7 回归全绿，门禁全绿（artifact checker 仅剩预期中的 PASS manifest 缺失）。**PASS**。本报告落盘后由复审写入 `building-review-manifest.json`（base `bdd0eda`，head 为报告落盘 commit），artifact checker 随之恢复绿。
