# Diagnosis: test_mode_ceiling 在负载下偶发读到旧 mode（fix-issue-261-mode-ceiling-flake）

关联跟踪 issue：[#261](https://github.com/Xingkai98/asterwynd/issues/261)。

> **本 diagnosis 的结论（两轮修订）**
>
> 1. 否证了 issue 正文的**测试侧同步**假设（「断言太早」）——断言点**已经**等到 mode
>    冻结（§2）。
> 2. **机制已钉死**（§4，最小可复现 + 真实代码路径 5/5 确定性复现）：根因是
>    `AgentLoop.run` 挂载 A 的恢复用**普通 `set(previous)`**（`agent/loop.py:598`）；
>    当某个**被遗留的 pending run task** 在**后续用例的上下文里**被 GC 终结时，
>    `Task.__del__ → coro.close()` 会把 `GeneratorExit` 抛进该协程，触发其
>    **所有嵌套 `finally`**——包括 `AgentLoop.run` 的这句 `set(previous)`。由于
>    `coro.close()` 是**普通方法调用**、不安装 task 自己的 Context，这个恢复
>    **运行在当前活跃的上下文里**，把后续用例正在使用的只读上限**清成 `None`**。
> 3. 过程中曾两次自我更正：早期「跨上下文污染」结论一度被主 session 的最小探针
>    证伪（其探针用 `cancel()` 终结 task，走的是 task 自己的上下文，不污染）；
>    真正的触发条件是**遗留 task 被 GC 终结**（`coro.close()` 语义），见 §4 的
>    对照实验。

## Symptom

PR #260 的 CI 首跑 `validate` 失败，**重跑即通过**（`run 36461765239` attempt 1，
job `109061796061`；attempt 2 success）：

```
FAILED tests/agent/subagent/test_mode_ceiling.py::test_next_run_after_switch_uses_new_mode
E       AssertionError: assert 'build' == 'read_only'
1 failed, 3406 passed, 8 skipped
```

同一次日志伴随：

```
ERROR asyncio:base_events.py:1785 Task was destroyed but it is pending!
task: <Task pending name='Task-4115' coro=<SubAgentManager._execute_run_in_context() running at agent/subagent/manager.py:1011>
      cb=[SubAgentManager._start_task.<locals>.<lambda>() at manager.py:971]>
ERROR asyncio:base_events.py:1785 Task was destroyed but it is pending!
task: <Task pending name='Task-4121' ... manager.py:1011 ...>
```

CI 环境：Python 3.11、全量 `pytest -q`、多 job 并行负载。本机单人全量此前三配置均未复现
（与 issue 记录一致）。

## Reproduction

### 最小可复现脚本（确定性，两个 Python 版本都成立）

```python
"""Minimal deterministic reproduction of issue #261."""
import asyncio, gc, sys, weakref
from agent.run_config import AgentMode
from agent.subagent.context import current_mode_ceiling, set_mode_ceiling

async def agent_loop_run_shape(tag):
    # 精确复刻 AgentLoop.run 的挂载 A（agent/loop.py:563-598）
    previous = current_mode_ceiling()
    set_mode_ceiling(AgentMode.BUILD)              # loop.py:570
    try:
        await asyncio.sleep(9999)                  # 真实 run 在此（LLM await）挂起
    finally:
        set_mode_ceiling(previous)                 # loop.py:598 —— 普通 set

def create_abandoned_task():
    # 测试的常见形态：子 run 被派发后从未 await 到终态（遗留 pending task）
    loop = asyncio.new_event_loop()
    task = loop.create_task(agent_loop_run_shape("abandoned-run"))
    loop.run_until_complete(asyncio.sleep(0.01))   # 让挂载 A 装上，然后挂起
    ref = weakref.ref(task)
    loop.close()                                   # 事件循环关闭；task 仍 pending
    del task                                       # manager 的引用也丢掉
    return ref

async def later_test():
    set_mode_ceiling(AgentMode.READ_ONLY)          # 后续用例的挂载 A：只读
    gc.collect()                                   # 在【当前上下文】里终结遗留 task
    await asyncio.sleep(0)
    ceiling = current_mode_ceiling()
    effective = ceiling if ceiling is not None else AgentMode.BUILD  # _parent_mode() 回落
    print("node would freeze as:", effective.value)   # 期望 read_only，实际 build

ref = create_abandoned_task()
asyncio.run(later_test())
```

实测输出（Python 3.11 **与** 3.12 均稳定复现）：

```
[abandoned] finally ran; ceiling here = <AgentMode.READ_ONLY: 'read_only'> -> writing None
[later test] ceiling now     : None
[later test] node would freeze as: build      <-- 期望 read_only
>>> REPRODUCED
```

注意 `finally` 里打印的 `ceiling here = read_only`——那是**后续用例的活跃上限**，
证明这段恢复代码**跑在后续用例的上下文里**（而非它自己的 `build`）。

### 真实代码路径复现（确定性，5/5）

用真实的 `AgentLoop` / `SubAgentManager` / `WorkflowScheduler` 构造（脚本见
`reviews/`），把「遗留一个 pending 子 run task → 关掉它的事件循环 → 在后续只读 run 的
调度器派发点 `gc.collect()`」串起来，得到**与 CI 完全一致**的症状：

```
Task was destroyed but it is pending!
task: <Task pending name='Task-2' coro=<SubAgentManager._execute_run_in_context()
      running at .../agent/subagent/manager.py:1011> ... cb=[..._start_task.<locals>.<lambda>()]>
Python 3.11.15  node 'bw' frozen as: 'build'  (expected 'read_only')
>>> REPRODUCED
```

对照（同一脚本、同一机器条件）：

| 树 | 5 次结果 |
|----|---------|
| `ee06df7`（现状，`set(previous)`） | **5/5 REPRODUCED** |
| 守护式 `reset(token)`（方案 A） | **5/5 CLEAN** |

> 早先一版报告里的「并发全目录 21/120 vs 0/120」A/B **作废**：两次批次在不同机器负载下
> 跑、且未验证每轮真跑了测试，属被混淆的读数。**上表的确定性 A/B 才是结论依据。**

### 为何单测/单文件隔离跑不复现

- 单测跑时，`_execute_run_in_context` 的遗留 task 尚未积累到足以在目标用例窗口内被终结；
- 单个测试进程里 pytest-asyncio 用 `asyncio.Runner` 管理循环，**`Runner.__exit__` 会
  cancel 掉 pending task**——`cancel()` 走的是 task **自己的**上下文，因此**不污染**
  （见 §4 对照）。只有在**跨进程/跨循环**、task 所属循环已关闭而 task 被 GC 终结时，
  才走 `coro.close()` 这条「污染」路径。
- CI 全量 + 多 job 负载让这种跨用例的 GC 终结窗口显著变大，故「负载相关、低频、重跑即过」。

## Evidence

### 证据 1：断言点**已经**等待 run 跑到 mode 冻结点（证伪 issue 的假设）

在 `_execute_run_in_context` 顶部注入 `await asyncio.sleep(0.3)`（放大 run 启动窗口）、
在 `create_subagent` 前注入 `time.sleep(0.2)`（放大冻结窗口），测试**仍然通过**且
**耗时随之变长**（0.83s → 2.37s）。若真是「断言太早」，注入延迟必须让它更易失败；
实测相反 ⇒ 断言点已经等到冻结。

### 证据 2：真实失败的探针时序（v5 探针，逐事件带上下文归属）

失败用例的执行窗口内，本用例的 root run 之外的 run 对象在收尾：

```
RUN-ENTER Task-3474  mode=read_only  ceil=None       <- 本用例 root run
SET       ->read_only  (loop.py:570)                 <- 挂载 A 装上只读
SET       ->None       (loop.py:598)                 <- !!! 立刻被清成 None
RUN-EXIT  ceil=None
SET       ->None       (loop.py:598)
RUN-EXIT  ceil=None
SCHED-ENTER ceil=None                                <- 钩子派发：上限已丢
DISPATCH node=bw  ceil=None
CREATE   bw  ceiling=build  static=build  frozen=build   <- 回落静态 -> 断言失败
```

### 证据 3：GC 终结在**调用方上下文**里执行 `finally`（对照实验）

| 终结方式 | `finally` 运行所在上下文 | 是否污染活跃上下文 |
|---------|----------------------|-----------------|
| `task.cancel(); await task`（pytest-asyncio `Runner.__exit__` 走这条） | task **自己的**上下文 | **否** |
| task 所属循环关闭后、task 被 GC 终结 | **当前正在运行的**上下文 | **是** |
| 裸 coroutine `.close()`（同步调用） | 调用 `.close()` 的那个上下文 | 是 |

后两行是同一机制：协程 finalize 并不安装 task 的 Context，而 `ContextVar.set` 写当前上下文。

> **这解释了主 session 探针为何没能复现**：其探针用 `cancel()`（或让 task 在自身循环
> 关闭时被该循环正常 cancel）终结 task——那走 task 自己的上下文，天然不污染。只有在
> **task 所属循环已关闭、随后被 GC 终结**时，才落到「写当前上下文」这条路径。

### 证据 4：`Task.__del__` → `coro.close()` 的载体栈

在最小的确定性脚本里捕获遗留 run 的 `finally` 栈，可见它是被**后续用例里的
`gc.collect()`** 触发的（`_run_once → handle._run → gc.collect`），而非它自己的循环。

### 证据 5：真实 subagent 测试确实会留下被 GC 终结的 run task

对 `tests/agent/subagent/test_mode_ceiling.py` 做 weakref 统计：一次会话创建 20 个
run task，**20 个最终 dead**（`created=20 dead=20 alive=0`）——即「遗留 task 迟后终结」
在真实测试里确实发生（只是未必每次恰好落在脆弱窗口）。

## Root Cause

**生产侧 task 生命周期缺陷**：

1. `AgentLoop.run` 用挂载 A 在 run 起点 `set_mode_ceiling(mode)`，`finally` 用
   **`set_mode_ceiling(previous)`** 恢复（`agent/loop.py:570` / `:598`）。
2. 子 run 是**独立 Task**（`SubAgentManager._start_task`，`manager.py:967`）。测试会
   **遗留**这类 task（未 await 到终态）。
3. 遗留 task 在其**所属事件循环已关闭**后，会被 GC 终结。终结时 task 释放它持有的
   挂起协程（`Task` 的 dealloc），协程被 finalize（对挂起点抛 `GeneratorExit`），
   于是**它的所有嵌套 `finally` 都被展开**——包括 `AgentLoop.run` 的恢复语句。
   （对照：正常路径 `task.cancel(); await task` 是把取消**投递进 task 自己的上下文**；
   GC 终结没有这一步。）
4. 协程的 finalize **不安装** task 自己的 Context；`ContextVar.set` 写入**当前正在运行的
   上下文**。若此刻运行的是**后续用例**的 root run（其挂载 A = `read_only`），这句
   `set(None)` 就把它的上限清空。
5. 后续用例派发节点时，`SubAgentManager._parent_mode()` 读到 `current_mode_ceiling() is
   None`，**回落静态 `parent_mode`**（失败用例里是 `AgentMode.BUILD`）⇒ 节点冻结为
   `build` ⇒ `assert 'build' == 'read_only'` 失败。

**与 CI 症状一致**：`Task was destroyed but it is pending!`（`_execute_run_in_context`）
正是「遗留 pending task 迟后终结」本身，不是无关噪声。

## Fix

**方案 A（推荐）= 守护式 `reset(token)`**：

```diff
--- a/agent/loop.py
+++ b/agent/loop.py
@@
-from agent.subagent.context import current_mode_ceiling, set_mode_ceiling
+from agent.subagent.context import (
+    current_mode_ceiling,
+    reset_mode_ceiling,
+    set_mode_ceiling,
+)
@@ class AgentLoop:
-        previous_ceiling = current_mode_ceiling()
-        set_mode_ceiling(self.runtime_state.current_mode)
+        ceiling_token = set_mode_ceiling(self.runtime_state.current_mode)
@@ finally:
             set_sandbox_sink(previous_sandbox_sink)
-            set_mode_ceiling(previous_ceiling)
+            try:
+                reset_mode_ceiling(ceiling_token)
+            except ValueError:
+                # token 属于另一个 Context（遗留 task 的迟后终结）：
+                # 那个上限随该 task 的上下文一起消亡，不得污染活跃上下文。
+                pass
```

**为什么它能修，而不只是「不写」**：`ContextVar.reset(token)` 的语义是**恢复 token
记录的那次 set 之前的上下文值**。当 token 来自**另一个 Context** 时，`reset` 主动抛
`ValueError`（CPython 的 `_contextvars` 强制此约束）——这个异常**恰好编码了**「这次恢复
不该作用于当前上下文」这一事实。跳过它，既让**同上下文**的正常 run 正确复原（#255 的
4.10 / 4.8 仍绿），又让**跨上下文**的迟后恢复不再污染。

**验证**：

- 真实代码路径确定性 A/B：现状 5/5 REPRODUCED → 方案 A 5/5 CLEAN（上表）。
- 最小脚本对照：`reset(token)` 分支打印 `ValueError: skipped`，活跃上限保持 `read_only`。
- 回归安全：`tests/agent/subagent/` 全量 **639 passed**；`test_mode_ceiling.py` +
  `test_subagent_manager.py` **31 passed**。
- 实现清理（非语义）：改用 token 后 `previous_ceiling = current_mode_ceiling()` 不再被
  使用，应一并删除（`current_mode_ceiling` 的 import 若因此无消费者可收窄）。

## `set_sandbox_sink`：**能复现且可观测**（实证缺陷；本 change 不修，建议单独立项）

`agent/loop.py:601` 的 `set_sandbox_sink(previous_sandbox_sink)` 与挂载 A 形态**完全相同**：
`agent/sandbox_events.py:46` 的 `set_sandbox_sink(sink)` 是**普通 `ContextVar.set`**、**没有**
`reset(token)` 版本，且它在同一个 `finally` 里、由同一个迟后终结路径执行。

**已写复现脚本并实测（两种故障形态都确定性复现）**：

| 脚本 | 形态 | 结果 |
|------|------|------|
| `repro/sandbox_sink_repro.py` | 遗留子 run 的 sink 上下文 = 默认 `_NOOP`（无 recorder 的父子链） | 后续 run 的 sink 被清成 `_NOOP` → 其 sandbox 事件**静默丢失**（LIVE trace 收 0 条） |
| `repro/sandbox_sink_misroute.py` | 遗留子 run 的上下文携带**旧 run 的真实 recorder sink** | 后续 run 的 sink 被换成**过期真 sink** → 事件**串写进旧 run 的 trace**（LIVE 0 条 / OLD 1 条） |

**可观测性判定 = 是（既有真实故障）**：不是「理论隐患」。

- 形态 A 让后续 run 的 sandbox 事件（`denied`/`kill`/`oom`/`degraded`）**静默丢失**，任何
  trace 里都查不到；
- 形态 B 更严重：事件被**记进另一个 run 的 trace**，可观测性数据**张冠李戴**。

**对照（证明归因）**：`sandbox_sink_misroute.py` 置 `PLANT_ABANDONED = False`（不派生遗留
子 run）后，LIVE 事件正确落入 LIVE trace —— 串写确由遗留子 run 的跨上下文收尾引起。

**与本 change 的关系**：两者是**独立载体**——本 change 只改了 `reset_mode_ceiling` 那一路；
实测在**已应用本 change 修复**的树上，两个 sandbox 脚本**仍然复现**（`set_sandbox_sink`
未被本 change 触碰）。

**修复建议（独立 change）**：给 `set_sandbox_sink` 增加 token 返回 / `reset_sandbox_sink`，
在 `AgentLoop.run` 的 `finally` 用守护式 `try: reset_sandbox_sink(token) except ValueError: pass`
（与挂载 A 同形）；注意 `AgentLoop.run` 里 `set_sandbox_sink` 在 `if trace_recorder:` 门控内、
而恢复是**无条件**的，改造时需一并处理「未 set 过却要 reset」的分支。

## Regression Requirements

1. **迟后终结不污染活跃上限**（新增，核心）：构造「遗留 pending run task（其循环已关）
   + 活跃只读 run 上下文」，在活跃 run 期间 `gc.collect()`，断言活跃上限保持 `read_only`、
   `create_subagent` 冻结为 `read_only`。**变异验证**：把 `finally` 改回 `set(previous)`
   必须变红（本 diagnosis 的确定性脚本已证明该变异会复现）。
2. **同上下文恢复仍正确**（既有 4.10 保持）：`test_run_exit_restores_ceiling_so_later_direct_drive_stays_conservative` 必须继续绿。
3. **取消路径不抛**（既有 4.8 保持）：`test_cancelled_run_does_not_raise_and_restores_ceiling`。
4. **`set_sandbox_sink` 同源隐患**：建议在新的独立 change 里补同类回归（本 change 不覆盖）。
