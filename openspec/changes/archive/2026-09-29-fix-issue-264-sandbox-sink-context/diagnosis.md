# Diagnosis: `set_sandbox_sink` 跨上下文收尾污染后续 run 的事件归属（fix-issue-264-sandbox-sink-context）

关联跟踪 issue：[#264](https://github.com/Xingkai98/asterwynd/issues/264)。

> **本 diagnosis 的结论**
>
> 1. 根因与 #261 **同源同机制**，本 change 在**最新 master**（#261 已合入）上**独立重跑**复核。
> 2. **形态 A（事件静默丢失）在当前树上 5/5 确定性复现**（§Reproduction 1）。
> 3. **形态 B（串写进旧 trace）的归档脚本在本机 0/10 不复现**——经定位是**脚本的 GC 时机
>    脆弱**（不是缺陷消失）。同一份生产代码、只把 GC 时机钉死后，确定性变体
>    **10/10 复现**（§Reproduction 2）。结论：**缺陷成立**，issue 描述的实测输出可复现。
> 4. 三个设计点（token 语义 / `_NOOP` 哨兵 / 跨上下文对照）各有**一手实测**（§Evidence 4）。

## Symptom

`agent/loop.py` 的 `finally` 里 `set_sandbox_sink(previous_sandbox_sink)`（`:600`）会在**错误的
上下文**中执行，把**后续 run** 的 sandbox sink 覆盖成过期值。两个形态：

| 形态 | 覆盖成 | 后果 |
|---|---|---|
| A | `_NOOP`（默认值） | 后续 run 的 sandbox 事件**静默丢失**（不写进任何 trace） |
| B | **过期真 sink** | 后续 run 的事件**串写进旧 run 的 trace** |

形态 B 是**审计证据污染**：一条安全拒绝事件（`denied rm -rf /`）被记进了**错误的 trace**，
且不报错、不告警。

## Reproduction

复现环境：本 worktree，Python **3.12.13**（`.venv`），所有脚本以
`PYTHONPATH=<repo-root> .venv/bin/python -u <script>` 运行，脚本**只读**生产代码。

### 1. 形态 A（事件静默丢失）—— 5/5 确定性复现

脚本：`repro/sandbox_sink_repro.py`（#261 归档原版 + 路径自适应，见下文「脚本适配」）。

```
Python 3.12.13
Task was destroyed but it is pending!
task: <Task pending name='Task-2' coro=<SubAgentManager._execute_run_in_context() running at
      .../agent/subagent/manager.py:1010> wait_for=<Future pending cb=[Task.task_wakeup()]>
      cb=[SubAgentManager._start_task.<locals>.<lambda>() at .../agent/subagent/manager.py:970]>

--- observed ---
  sink_before: 'TraceRecorderSandboxSink'
  sink_after: 'NoopSandboxSink'
  sink_clobbered: True
  clobbered_to: 'NoopSandboxSink'
  LIVE trace 收到 sandbox 事件: []

>>> 复现：遗留 pending run 的跨上下文收尾覆盖了后续 run 的 sandbox sink（-> NoopSandboxSink）
    可观测性：覆盖为 _NOOP（默认值）——后续 run 之后发出的 sandbox 事件将**静默丢失**（不写进任何 trace）。
    本 run 的事件是否落入自己的 trace：False
```

**5 次连续运行 5/5 命中**（脚本退出码 1 = 复现）。`sink_before` 是 `TraceRecorderSandboxSink`
（活跃 run 自己的 recorder sink），`sink_after` 被改成 `NoopSandboxSink` —— 活跃 run 之后发出的
sandbox 事件**全部丢弃**。

### 2. 形态 B（串写进旧 trace）—— 归档脚本 0/10，确定性变体 10/10

**先诚实记录异常**：`repro/sandbox_sink_misroute.py`（#261 归档原版，仅做路径适配）在本机
**连续 10 次全部不复现**：

```
Python 3.12.13  PLANT_ABANDONED=True
  LIVE recorder sandbox steps : [{'event': 'denied', 'command': 'rm -rf /', 'reason': 'live'}]
  OLD  recorder sandbox steps : []
>>> 无串写：LIVE 事件落在 LIVE trace（对照或未触发）。
```

这与 issue 正文引用的实测输出（`LIVE [] / OLD 1 条`）**不一致**。

**定位（不是缺陷消失，是脚本的 GC 时机脆弱）**：

- 给脚本注入 `set_sandbox_sink` 调用栈探针后，**同一脚本**却能复现——差别只在探针改变了
  对象存活时序；
- 逐项排查后确认：脚本在 plant 阶段 `del loop_old, root_old, mgr_old` 之后**仍通过
  `llm.mgr` 持有旧 manager**（`llm` 一直活到 main 结束），`manager._active_tasks` → task →
  manager 的引用环因此**未变成垃圾**，遗留 task 活到了进程尾部，**从未在 LIVE 窗口内被终结**；
- 在 plant 阶段丢弃引用后**补一行 `gc.collect()`**（把遗留 task 的终结时机钉死），
  `repro/sandbox_sink_misroute_gcwindow.py` **10/10 复现**：

```
Python 3.12.13  PLANT_ABANDONED=True
  LIVE recorder sandbox steps : []
  OLD  recorder sandbox steps : [{'event': 'denied', 'command': 'rm -rf /', 'reason': 'live'}]
>>> 串写复现：LIVE run 的 sandbox 事件落进了 OLD recorder 的 trace。
    即一条安全拒绝事件被记进了**错误的 trace**（审计证据污染）。
```

**对照（control，证明归因）**：同一脚本置 `PLANT_ABANDONED = False`（不派生遗留子 run）→
**3/3 无串写**，LIVE 事件正确落入 LIVE trace：

```
Python 3.12.13  PLANT_ABANDONED=False
  LIVE recorder sandbox steps : [{'event': 'denied', 'command': 'rm -rf /', 'reason': 'live'}]
  OLD  recorder sandbox steps : []
>>> 无串写：LIVE 事件落在 LIVE trace（对照或未触发）。
```

**结论**：形态 B 的缺陷**成立且可观测**；(a)「归档脚本不复现」是**脚本**问题——它把缺陷的
**存在性**与 GC 的**时机**耦合在一起；(b) 加一行 `gc.collect()` 即恢复确定性 10/10。这也解释了
为何 #261 期间脚本能复现（不同的解释器/时序）而本机不能。**该变体脚本已随本 change 归档**，
作为「脚本脆弱 ≠ 缺陷不成立」的证据。

> **对回归测试的含义**：回归测试**不应**依赖「碰巧 GC 到」，必须像 #261 的回归那样**显式
> `gc.collect()`**，把终结时机钉在活跃 run 的窗口内（见 `tasks.md` 2.1）。

### 脚本适配（相对 #261 归档原版）

两个脚本复制到 `repro/` 时做了**最小适配**，并记录改动：

1. `REPO = pathlib.Path(__file__).resolve().parents[4]` → `_find_repo_root(...)`：归档原版用
   `parents[4]`，只在 change 处于 `openspec/changes/<id>/` 时指向仓库根；**归档后深了一层**，
   它会静默指向 `openspec/`（当时靠调用方传 `PYTHONPATH=.` 掩盖）。改为向上寻找
   `agent/loop.py` 作为标记，使脚本在 active 与 archived 两种位置都成立。
2. 标题从「issue #261 派生调查」改为「issue #264 复现（源自 #261 派生调查）」。
3. 形态 B 另存一个**确定性 GC 窗口变体** `sandbox_sink_misroute_gcwindow.py`（差异仅一行
   plant 阶段 `gc.collect()`，已在文件 docstring 注明）。

**生产代码未做任何修改。**

## Evidence

### 证据 1：形态 A 与形态 B 是**同一个**恢复语句的两种投影

`agent/loop.py:600` 的 `set_sandbox_sink(previous_sandbox_sink)` 是**唯一**载体。两个形态的
差别**不在被遗留的 run 本身**（子 run 经 `_run_loop` 一律拿到自己的 `TraceRecorder`，
`manager.py:1172` / `:1206`，所以它**总是**会 set 自己的 sink），而在**它在 run 起点快照到的
`previous_sandbox_sink`** —— 那是「**它被派生时的那个上下文**」里的 sink：

- **形态 A**：被遗留 run 的**入队上下文里没有 sink**（它在**没有 recorder** 的驱动上下文里被
  派生，例如 `_plant` 里直驱 `manager.run_subagent(wait=False)`）→ `previous` 快照 = 默认
  `_NOOP` → 收尾时把这句 `set(_NOOP)` 写进活跃上下文 → 事件静默丢失。
- **形态 B**：被遗留 run 在**带 recorder 的旧 run 内部**被派生 → 其入队上下文经
  `copy_context()` 携带**旧 run 的真 sink** → `previous` 快照 = 旧 recorder sink → 收尾时把
  过期真 sink 写进活跃上下文 → 串写。

**实测确认（注入 `set_sandbox_sink` 探针）**：形态 A 的 plant 阶段只出现
`set(TraceRecorderSandboxSink, previous=NoopSandboxSink)` —— 即被遗留的子 run **确实 set 了
自己的 recorder sink**，而它快照的 `previous` 是 `_NOOP`（继承自无 sink 的派生上下文）。
这正是两个形态的分水岭，也解释了为什么同一句话能既「静默丢失」又「串写」。

### 证据 2：`set_sandbox_sink` 没有 reset 版本

`agent/sandbox_events.py:46` 的 `set_sandbox_sink` 是裸 `ContextVar.set`、**不返回 token**；
模块内**不存在** `reset_sandbox_sink`。对照 `agent/subagent/context.py:138-143`：

```python
def set_mode_ceiling(mode: AgentMode | None) -> Any:
    return _mode_ceiling.set(mode)

def reset_mode_ceiling(token: Any) -> None:
    _mode_ceiling.reset(token)
```

即 `#255` 为 `mode_ceiling` 建了成对的 token/reset，而 `#261` 只把 **`loop.py` 的那一句调用**
改成守护式；sandbox 通道的 API 缺口未被填补。

### 证据 3：`set` 门控而恢复无条件（D4 的由来）

```python
if trace_recorder:
    set_sandbox_sink(TraceRecorderSandboxSink(trace_recorder))   # :580 门控
finally:
    set_sandbox_sink(previous_sandbox_sink)                      # :600 无条件
```

`if trace_recorder:` 门控内的 `set` 与门控外的恢复**不对称**——这正是 D4 选择
`if sink_token is not None` 门控 reset 的原因。

### 证据 4：三个设计点的一手实测（`repro/design_points_probe.py`，Python 3.12.13）

```
D1: token 可用性（default = _NOOP 哨兵）
  从未 set            -> get() is default: True
  首次 set 返回 token : True
  reset(t1)           -> get() is default again: True
  嵌套 reset(inner)   -> get() == 'B': True
  嵌套 reset(outer)   -> get() is default: True
  二次 reset          -> RuntimeError（token 已用过；注意**不是** ValueError）

D2: 跨上下文 reset —— _NOOP-defaulted vs None-defaulted
  sandbox sink (default _NOOP): ValueError -> 跳过，未写入
  mode_ceiling (default None): ValueError -> 跳过，未写入

D3: 遗留 task 终结路径 —— set(prev) 写活跃上下文；守护式 reset 跳过
  形态=set   -> 终结后活跃 sink: 'STALE-SINK'  [POLLUTED（活跃 run 的事件会串写/丢失）]
  形态=reset -> 终结后活跃 sink: 'LIVE-sink'   [clean（活跃 sink 完好）]
```

- **D1**：token 与「此前是否 set 过」**无关**，`default` 生效时同样可 `reset`，恢复的就是那次
  `set` 之前的值。另：**二次 reset 抛 `RuntimeError` 而非 `ValueError`**——本 change 的 token 由
  本协程自己创建、至多消费一次，不受影响（但值得写进实现注释）。
- **D2**：跨上下文判据是 **Context 身份**，与 `default` 取值**无关** → 守护式 reset 在
  `_NOOP` 默认的 sandbox sink 上与在 `None` 默认的 mode_ceiling 上**行为一致**；
  `_NOOP`（丢弃事件）的默认值语义**不受影响**。
- **D3**：同一条遗留终结路径，现状 `set(prev)` 污染、守护式 reset 不污染。

### 证据 5：当前树是 #261 已合入的树，缺陷仍成立

`agent/loop.py:601-609` 已是 `#261` 的守护式 `reset_mode_ceiling` + `except ValueError: pass`，
而同块的 `:600` 仍是裸 `set_sandbox_sink`。上述形态 A 的 5/5 复现即在该树上取得 ——
证明**两个载体相互独立**，#261 的修复不覆盖本 issue。

## Root Cause

与 `#261` 完全同源（原文见
`openspec/changes/archive/2026-09-29-fix-issue-261-mode-ceiling-flake/diagnosis.md` 的
`## Root Cause`），载体换到 sandbox sink：

1. `AgentLoop.run` 在 run 起点 `set_sandbox_sink(本 run 的 recorder sink)`（`:580`），
   `finally` 用 **`set_sandbox_sink(previous)`** 恢复（`:600`）。
2. 子 run 是**独立 Task**（`SubAgentManager._start_task`，`manager.py:966`）。`wait=False`
   或测试未 await 到终态会**遗留**这类 pending task。
3. 遗留 task 在其**所属事件循环已关闭**后，被 GC 终结。终结时 task 释放它持有的挂起协程
   （`Task` 的 dealloc），协程被 finalize（对挂起点抛 `GeneratorExit`），
   于是**它的所有嵌套 `finally` 都被展开**——包括 `loop.py:600` 这句恢复。
   （对照：正常路径 `task.cancel(); await task` 是把取消**投递进 task 自己的上下文**；
   GC 终结没有这一步。）
4. 协程 finalize **不安装** task 自己的 Context；`ContextVar.set` 写入**当前正在运行的**
   上下文。若此刻运行的是**另一个 run**，这句 `set(previous)` 就把它的 sink 覆盖成过期值。
5. 后果：后续 run 的 sandbox 事件**静默丢失**（覆盖成 `_NOOP`）或**串写进旧 trace**
   （覆盖成过期真 sink）。

**关键区分（沿用 #261 的对照结论）**：`task.cancel(); await task` 走 task **自己的**上下文，
**不污染**；只有「所属循环已关闭 + GC 终结」这一条路径污染。

## Recommended Direction

**方案（推荐）= 守护式 `reset_sandbox_sink(token)`**，与 #261 同形：

```diff
--- a/agent/sandbox_events.py
+++ b/agent/sandbox_events.py
-def set_sandbox_sink(sink: SandboxEventSink) -> None:
+def set_sandbox_sink(sink: SandboxEventSink) -> Any:
     """Set the active sink for the current execution context.
 
-    Callers are responsible for save/restore (mirror the loop's
-    ``_active_trace_recorder`` pattern) so nested runs and runs without a
-    recorder do not leak events into the wrong trace.
+    Returns the contextvar token; restore with ``reset_sandbox_sink`` so a
+    cross-context teardown (an abandoned Task finalised by GC) cannot clobber
+    another run's sink (issue #264).
     """
-    _current_sink.set(sink)
+    return _current_sink.set(sink)
+
+
+def reset_sandbox_sink(token: Any) -> None:
+    _current_sink.reset(token)
```

```diff
--- a/agent/loop.py
+++ b/agent/loop.py
-        previous_sandbox_sink = current_sandbox_sink()
+        sink_token = None
@@ if trace_recorder:
-            set_sandbox_sink(TraceRecorderSandboxSink(trace_recorder))
+            sink_token = set_sandbox_sink(TraceRecorderSandboxSink(trace_recorder))
@@ finally:
-            set_sandbox_sink(previous_sandbox_sink)
+            if sink_token is not None:
+                try:
+                    reset_sandbox_sink(sink_token)
+                except ValueError:
+                    # token 属于另一个 Context（遗留 task 的迟后终结，issue #264）：
+                    # 那个 sink 随该 task 的上下文一起消亡；在此写入会改写活跃
+                    # run 的事件归属，故跳过。
+                    pass
```

**为什么它能修**：`ContextVar.reset(token)` 的语义是「恢复 token 记录的那次 set 之前的值」，
且 CPython **强制** token 只能在其创建时的 Context 里 reset —— 跨 Context 时主动抛 `ValueError`。
这个异常**恰好编码了**「本次恢复不该作用于当前上下文」这一事实：

- **同上下文**（正常 run 退出、取消路径）：token 有效 → 正确恢复 run 起点之前的值。
- **跨上下文**（遗留 task 的迟后终结）：token 失效 → `ValueError` → 跳过，**不写入当前上下文**。

**验证**（实现后应满足）：

- `repro/sandbox_sink_repro.py` 与 `repro/sandbox_sink_misroute_gcwindow.py` 均应转为**未复现**。
- `tests/agent/test_sandbox_events.py`（含 `test_set_sandbox_sink_restores_previous`）
  与 `tests/agent/test_loop_sandbox_events.py`（含 `test_sink_restored_after_run`）保持绿。
- 新增回归 + 变异验证（见下）。

## Regression Tests

1. **迟后终结不污染活跃 sink**（新增，核心）：构造「遗留 pending 子 run（其循环已关）+
   活跃带 `TraceRecorder` 的 run」，在活跃 run 期间 `gc.collect()`，断言活跃 sink 未被改写、
   其 sandbox 事件仍落入自己的 trace。**变异验证**：把 `finally` 改回
   `set_sandbox_sink(previous_sandbox_sink)` 必须变红。
2. **同上下文恢复仍正确**（既有保持）：`test_sink_restored_after_run` 必须继续绿——
   run 退出后 emit 不落进已完成的 trace。
3. **嵌套恢复仍正确**（新增断言）：有 recorder 的父 run 内跑带 recorder 的子 run，
   子 run 退出后父 run 的后续 sandbox 事件仍落父 trace。
4. **API 兼容**：`set_sandbox_sink` 的既有调用点（`tests/agent/test_sandbox_events.py`、
   `tests/agent/test_background.py`、`tests/agent/tools/test_process_backend_cgroup.py`、
   `tests/agent/tools/test_bash_tool_events.py`）全部保持绿（返回 token 是增量变更）。
