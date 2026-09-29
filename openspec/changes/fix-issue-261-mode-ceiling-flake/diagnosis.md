# Diagnosis: test_mode_ceiling 在负载下偶发读到旧 mode（fix-issue-261-mode-ceiling-flake）

关联跟踪 issue：[#261](https://github.com/Xingkai98/asterwynd/issues/261)。

> **重要：本 diagnosis 否证了 issue #261 正文给出的根因判断。**
> issue 认为这是**测试侧的同步缺陷**（「测试在派发后立即断言，后台 task 尚未跑到
> mode 冻结点」），修复方向定为「等目标 run 到终态再断言」。实测证明该判断**不成立**：
> 断言点**已经**等到 mode 冻结（§2 用延迟注入证伪）。真实根因在**生产侧**——
> `AgentLoop.run` 挂载 A 的恢复用的是**普通 `set(previous)`**，当该 `finally` 因
> **遗留 task 迟后终结**而在**另一个上下文**里执行时，它把**当前活跃的上限**清成了
> `None`。这属于「生产侧 task 生命周期缺陷」，按任务约定**如实报告并停轮**，
> 未擅自套用 issue 的测试侧方向。

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

**本机复现成功**（关键突破）。要点：**单文件/单测隔离跑几乎不复现**，必须让
**同一进程内的历史遗留 pending task** 有机会在**后续用例执行期间**被 GC 终结。

### 复现手段（可复现、已固化）

并发跑多份 `tests/agent/subagent/` 全目录（不是单文件），让「前序用例遗留的
pending run task」在后续用例里有足够机会被终结：

```bash
# 5 个并发 worker，每个循环把 tests/agent/subagent/ 全目录跑一遍
for w in 1 2 3 4 5; do
  ( for i in $(seq 1 24); do
      .venv/bin/pytest tests/agent/subagent/ -q -p no:randomly -p no:cacheprovider
    done ) &
done
wait
```

实测命中率（Python 3.11，4 核机器）：

| 树 | 总运行次数 | `test_mode_ceiling` 失败次数 | 命中率 |
|----|-----------|--------------------------|--------|
| **基线 master `ee06df7`** | 120 | **21** | **~17.5%** |
| 应用「守护式 `reset(token)`」修复 | 120 | **0** | **0%** |

命中的用例与断言行**与 CI 完全一致**：

- `test_next_run_after_switch_uses_new_mode`（`test_mode_ceiling.py:329`）——CI 命中的那条
- `test_readonly_session_clamps_build_node`（`test_mode_ceiling.py:131`）——与其**逐字节同形**的兄弟用例

（后者被一并复现，正好解释了为何 CI 里可能命中两条中的任意一条。）

### 为什么单文件/单测连跑不复现

早期尝试（单测 300 次 / 单文件 150+80 次 + 人为 CPU 压力）**全部绿**。原因：单测在
`list_subagents()["bw"]` 上会**先抛 `KeyError`**（session 未创建）而非 `AssertionError`；
且单文件运行时，前序用例的遗留 task 数量不足以在**恰好**目标用例执行窗口内被终结。
真实 CI 命中的 `AssertionError: 'build'`（而非 `KeyError`）反证：**session 确实被创建了、
mode 确实被冻结为 `build`**——即冻结发生了，只是读到的**上限**是错的。

### 变异/判别探针

- **延迟注入证伪「断言太早」**：在 `_execute_run_in_context` 顶部注入 `await asyncio.sleep(0.3)`
  （放大 run 启动窗口）、在 `create_subagent` 前注入 `time.sleep(0.2)`（放大冻结窗口），
  测试**仍然通过**且**耗时随之变长**（0.83s → 2.37s）。说明断言点**已经等待** run 跑到
  mode 冻结点。「立即断言、task 未跑到」的假设不成立。
- **`asyncio` 事件循环**：pytest-asyncio 1.3.0 + `asyncio_default_fixture_loop_scope = "function"`，
  每个测试项各持一个 function 作用域 `Runner`（实测：单文件 16 次 `Runner.__enter__`、
  16 个不同的 loop id）。故**不是**「跨测试共享同一事件循环」，而是**跨上下文**的
  contextvar 写入。`runner.run(coro, context=copy_context())`（`pytest_asyncio/plugin.py:463`）
  会从**主上下文**拷贝一份作为测试 task 的执行上下文——遗留 task 的终结若发生在这份
  上下文里，就会写进来。

## Evidence

### 证据 1：派发时上限读数为 `None`（探针实测）

在 `WorkflowScheduler._dispatch` / `SubAgentManager.create_subagent` 处埋探针，记录
每次调用时的 `current_mode_ceiling()`。失败用例的时序（`probe v8`，`rc8/HIT.1.2`）：

```
RUN>   task=Task-3406  loopobj=...117840  mode=read_only  ceil=None     <- 本用例的 root run 进入
SET-NONE task=Task-3406  从 loop.py:598 恢复（!!!）
RUN<   task=Task-3406  loopobj=...684816  ceil=None                     <- 退出的却是【另一个】 loop 对象
SET-NONE task=Task-3406  从 loop.py:598 恢复（!!!）
RUN<   task=Task-3406  loopobj=...113616  ceil=None
SCHED> task=Task-3406  ceil=None                                        <- 钩子派发：上限已丢失
DISPATCH node=bw  ceil=None
CREATE  name=bw  ceil=build  static=build  frozen=build                 <- 回落静态 parent_mode=BUILD -> 断言失败
```

关键异常：`RUN>` 进入的是 `loopobj=...117840`，而紧随其后的 `RUN<` 退出的却是
`...684816` / `...113616`——**本用例的执行窗口内，出现了别的 run 在收尾，并在本上下文
里写了 `set_mode_ceiling(None)`**。（注意：CPython 的 `id()` 可被复用，故不应过度解读
具体数字；此处的**决定性证据**是「退出的 run 与进入的 run 不同源」这一事实，以及
证据 2 的调用栈落在 `loop.py:598`。机制本身由证据 3 的确定性脚本独立证明，不依赖对
某个具体实例的归属判断。）

### 证据 2：`SET-NONE` 的调用栈穿过 `loop.py:598`（挂载 A 的 `finally`）

探针捕获 `set_mode_ceiling(None)` 的调用栈（`probe v8`）：

```
SET-NONE  ...  <genexpr> | importlib.metadata find_distributions | ... | loop.py:598:run
```

栈顶是 `loop.py:598`——即 `AgentLoop.run` 的 `finally` 里那句 `set_mode_ceiling(previous_ceiling)`。
其外层帧是 `importlib.metadata` 的 `find_distributions`（一次版本/入口点查询触发的分配）
——即**GC 在 importlib metadata 扫描期间终结了一个遗留 task**，把它的 `finally` 跑在了
**当前**上下文里。

### 证据 3：机制的最小确定性复现

`agent/loop.py:563-598` 的挂载 A 形状（**普通 `set` 恢复**）在「遗留 task 迟后终结」下
必然清空当前活跃上限。确定性脚本实测：

```
=== 1. current production shape (plain `set`) ===
  live mount A ceiling        : AgentMode.READ_ONLY
  after stale teardown        : None            <- 遗留 run 的 finally 把当前上限清成 None
  create_subagent freezes as  : build           <- 回落静态 parent_mode -> 复现 CI
  -> reproduces CI: 'build' != 'read_only'

=== 2. proposed shape (guarded `reset(token)`) ===
  live mount A ceiling        : AgentMode.READ_ONLY
  after stale teardown        : AgentMode.READ_ONLY
  create_subagent freezes as  : read_only
  -> ceiling preserved
```

（脚本见「复现手段」小节，可重跑。）

### 证据 4：既有设计文档已知「跨 context teardown 的 `reset` 会抛 `ValueError`」

`fix-issue-255-mode-ceiling` 的 `diagnosis.md` 明确记录：

```
cancel+await  : 无异常
coro.close()  : ValueError: <Token ...> was created in a different Context
```

并因此**刻意**改用 `set(previous)` 而非 `reset(token)`（`agent/loop.py:565-568` 的注释：
「Restoring the *previous value* via `set` (not `reset(token)`)」）。**该选择修好了
`ValueError` 崩溃，却引入了本 issue 的跨上下文清空**：`set` 永远写「当前上下文」，
而迟后终结的 `finally` 恰好在**别的**上下文里执行。

## Root Cause

**生产侧 task 生命周期缺陷**（非测试侧同步缺陷）：

1. `AgentLoop.run` 在 run 起点用挂载 A `set_mode_ceiling(mode)` 快照上限，并在 `finally`
   用 **`set_mode_ceiling(previous_ceiling)`** 恢复（`agent/loop.py:570` / `:598`）。
2. 子 run 由 `SubAgentManager._start_task` 以**独立 task** 启动（`manager.py:967-969`，
   `context=item.context`）。测试场景下这类 task 常被**遗留**（未 await 到终态），
   于是成为 **pending task**。
3. pending task 在**迟后**被终结（CPython 的 `Task.__del__` → `coro.close()`，或 GC 时机）
   时，会从其挂起点（`await`）以 `GeneratorExit` 恢复协程，**执行其 `finally`**。
   关键：该 `finally` 里的 `set_mode_ceiling(previous)` 是 `ContextVar.set`，**写入
   「当前正在运行的上下文」**——而此刻运行的可能是**另一个用例**的 root run 上下文。
4. 若那个「当前上下文」里正活跃着一个**只读 run 的挂载 A 上限**（`read_only`），
   它就被这句 `set(None)` **清空**。
5. 随后该只读 run 的钩子派发节点时，`SubAgentManager._parent_mode()` 读到
   `current_mode_ceiling() is None`，**回落到静态 `parent_mode`**（测试里
   `_manager(...)` 默认 `parent_mode=AgentMode.BUILD`）⇒ 节点被冻结为 `build` ⇒
   断言 `'build' == 'read_only'` 失败。

**与 CI 症状的一致性**：
- `Task was destroyed but it is pending!`（`_execute_run_in_context`）正是「遗留 pending
  task 迟后终结」的**同一现象**，不是无关噪声。
- 高负载（CI 全量 + 多 job）令 `pytest` 循环更易发生「迟后终结撞上后续用例执行窗口」，
  故**负载相关、低频、重跑即过**。

**结论**：上限通道（contextvar）**本身正确**；缺陷是**恢复它时用了 `set` 而非
token 化的 `reset`**，使得「迟后终结」的恢复写入错误上下文。

## Fix Options

| 方案 | 说明 | 评价 |
|------|------|------|
| **A. 守护式 `reset(token)`（推荐）** | `run` 起点 `token = set_mode_ceiling(mode)`；`finally` 用 `try: reset_mode_ceiling(token) except ValueError: pass`。同上下文正常恢复；**跨上下文终结时 `reset` 抛 `ValueError` → 静默跳过**，不再写入当前上下文。 | **最小、对症**：正式使用 contextvar 的 token 语义；跨上下文跳过正是「那个值随死掉的 task 上下文一起消亡、不该影响活跃上下文」的正确表达。已 A/B 验证（120 次 0 失败）。 |
| B. 恢复前比对上下文 | 记录 set 时的 `contextvars.copy_context()`，`finally` 里比对当前上下文是否同一份再决定是否 set。 | 比 A 冗长，语义重复造轮子（token 本身携带 context 归属）。不推荐。 |
| C. 不恢复（删除 finally 的恢复） | —— | **不可行**：会泄漏上限（`fix-issue-255` 的 4.10 用例会红）。 |
| D. 测试侧「等 run 到终态」 | issue 建议方向 | **不成立**：断言点**已**等待（§2 证伪）；且清空来自**别的**遗留 run 的终结，等待本用例的 run 无法阻止。会掩盖真实缺陷。 |
| E. 让上限彻底 task-local（换机制） | —— | 过度设计；现有 contextvar 通道在 #255 已 grill 定型。 |

**推荐：方案 A**。它同时满足 #255 的要求（「run 退出后上限复原」——同上下文 token 恢复
正确）与本 issue 的修复（跨上下文终结不再污染活跃上下文）。

方案 A 的完整改动（已 A/B 验证；`context.py` 的 `reset_mode_ceiling` 已存在，无需新增）：

```diff
--- a/agent/loop.py
+++ b/agent/loop.py
@@ -39,7 +39,11 @@ from agent.memory.manager import MemoryManager
-from agent.subagent.context import current_mode_ceiling, set_mode_ceiling
+from agent.subagent.context import (
+    current_mode_ceiling,
+    reset_mode_ceiling,
+    set_mode_ceiling,
+)
@@ class AgentLoop:
         previous_ceiling = current_mode_ceiling()
-        set_mode_ceiling(self.runtime_state.current_mode)
+        ceiling_token = set_mode_ceiling(self.runtime_state.current_mode)
@@ finally:
             set_sandbox_sink(previous_sandbox_sink)
-            set_mode_ceiling(previous_ceiling)
+            try:
+                reset_mode_ceiling(ceiling_token)
+            except ValueError:
+                pass
```

> `resume` 路径（`agent/loop.py:631`）的二次 `set_mode_ceiling(...)` 不受影响：token 记住的是
> **首次 set 之前**的值，中间再 set 不改变 `reset(token)` 的目标（ContextVar 语义），
> 故 `reset` 仍正确恢复到 run 起点之前的值。
>
> 实现清理（非语义）：改用 token 后 `previous_ceiling = current_mode_ceiling()` 变成**未使用**，
> 实现时应一并删除该行；`current_mode_ceiling` 若因此在 `loop.py` 内无其它消费者，其 import
> 也可收窄（当前仓库内它只在 `loop.py:569` 被用）。A/B 验证所用补丁**保留了**该未使用行，
> 故删除它不改变已验证的行为。

**验证记录（A/B 对照，同一并发手段，Python 3.11，4 核）**：

```
LABEL=BASELINE total_runs=120 mode_ceiling_failures=21
      7 test_next_run_after_switch_uses_new_mode
     14 test_readonly_session_clamps_build_node
LABEL=PATCHED  total_runs=120 mode_ceiling_failures=0
```

> **范围说明（需用户拍板）**：方案 A 改动**生产代码** `agent/loop.py`，与 issue 正文
> 「纯测试侧、无 spec delta」的定性**不同**。因此按任务约定**止步于此、如实报告**，
> 未擅自应用该生产改动、未进入归档与门禁收尾。

## Regression Requirements

若采纳方案 A，回归测试应覆盖：

1. **迟后终结不污染活跃上限**（新增）：构造「遗留 pending run task + 活跃只读 run 上下文」，
   在活跃 run 期间终结遗留 task，断言活跃上限**保持 `read_only`**、`create_subagent` 冻结为
   `read_only`。变异验证：把 `finally` 改回 `set(previous)` ⇒ 该用例必须变红。
2. **同上下文恢复仍正确**（既有 4.10 保持）：`test_run_exit_restores_ceiling_so_later_direct_drive_stays_conservative`
   必须继续绿（证明没有因跳过而泄漏）。
3. **取消路径不抛**（既有 4.8 保持）：`test_cancelled_run_does_not_raise_and_restores_ceiling`。
4. **负载复现**：以本 diagnosis 的并发手段跑 `tests/agent/subagent/`（基线 ~17.5% 命中）作为
   修复有效性的验收证据。
