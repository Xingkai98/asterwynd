# Design: sandbox sink 改守护式 reset，修跨上下文收尾污染后续 run 的事件归属（fix-issue-264-sandbox-sink-context）

关联 issue：[#264](https://github.com/Xingkai98/asterwynd/issues/264)。根因与实测证据见 `diagnosis.md`。

## Context

`AgentLoop.run`（`agent/loop.py`）在同一个 `finally` 里有**两句**「恢复前值」：

```python
previous_sandbox_sink = current_sandbox_sink()          # :560
...
if trace_recorder:
    set_sandbox_sink(TraceRecorderSandboxSink(trace_recorder))   # :580（门控）
try:
    return await self._run(...)
finally:
    ...
    set_sandbox_sink(previous_sandbox_sink)             # :600（**无条件**）
    try:
        reset_mode_ceiling(ceiling_token)               # :602（#261 已改守护式）
    except ValueError:
        pass
```

两句恢复的**触发路径完全相同**（同一次遗留 task 的 `coro.close()` 展开同一个 `finally`），
但恢复**方式不同**：#261 把 mode_ceiling 改成了守护式 `reset(token)`，sandbox sink 仍是
裸 `set(previous)`。`agent/sandbox_events.py` **没有** `reset_sandbox_sink` —— 这是本 change
要补的缺口。

#261 的 `design.md` D1 已完整论证「为什么守护式 `reset(token)` 而不是普通 `set(previous)`」
（token 的 `ValueError` 恰好编码「本次恢复不该作用于当前上下文」）。本 change 不再重复论证，
只把它**复制到 sandbox sink 通道**，并回答 sandbox sink 特有的三个问题（见 Decisions D2–D4）。

## Goals / Non-Goals

- **Goal**：遗留 run 的迟后终结**不得**改变活跃 run 的 sandbox sink；同上下文恢复语义不变
  （嵌套子 run 仍回落到父 sink、run 退出后 sink 复原、取消路径不抛）。
- **Non-Goal**：不改 `_NOOP` 默认哨兵、不改事件分发语义、不改 trace schema。
- **Non-Goal**：不改 `_active_on_event` / `_active_trace_recorder`（实例属性，非 contextvar）。
- **Non-Goal**：不改 `manager._execute_run_in_context` 的「不 reset」决策（刻意的私有 context 副本）。
- **Non-Goal**：不做泛化的「统一所有 contextvar 恢复模式」重构。

## Decisions

### D1：恢复方式用「守护式 `reset_sandbox_sink(token)`」而非普通 `set(previous)`

与 #261 的 D1 同形（论证见 `openspec/changes/archive/2026-09-29-fix-issue-261-mode-ceiling-flake/design.md`），
此处只记录 sandbox 侧的落点：

```python
sink_token = None
if trace_recorder:
    sink_token = set_sandbox_sink(TraceRecorderSandboxSink(trace_recorder))
...
finally:
    if sink_token is not None:
        try:
            reset_sandbox_sink(sink_token)
        except ValueError:
            # token 属于另一个 Context（遗留 task 的迟后终结，issue #264）：
            # 那个 sink 随该 task 的上下文一起消亡；在此写入会改写活跃 run
            # 的事件归属，故跳过。
            pass
```

- **同上下文**（正常 run 退出、取消路径）：token 有效 → 恢复 run 起点之前的值（嵌套子 run
  回落到父 sink，与现状逐字一致）。
- **跨上下文**（遗留 task 的迟后终结）：token 失效 → `ValueError` → 跳过，**不写入当前上下文**。

**被否的替代**：

| 方案 | 为何不选 |
|------|---------|
| 保留 `set(previous)` + 记录创建时的 Context、恢复前比对 | 自己复刻 token 已做的事，且 `Context` 身份比较易错；token 是语言原生机制（#261 已否决同一方案） |
| 什么都不做（删掉恢复） | 泄漏 sink：嵌套子 run 退出后父 run 的后续事件会落进子 run 的 trace（`test_sink_restored_after_run` 会红） |
| 改成 task-local 的其它机制 | 过度设计；contextvar 通道是既有设计 |
| 只改测试「别留 pending task」 | 治标：遗留 pending run 是 `SubAgentManager` 的正常产物（`wait=False` + 队列），生产路径同样会留 |

### D2：`_NOOP` 哨兵**保持不动**——默认值语义不受守护式 reset 影响

issue 明确标注的待确认点：`_current_sink` 的默认值是 `_NOOP`（丢弃事件），而 `mode_ceiling`
的默认是 `None`（无上限）。**结论：这个差异不会让守护式 reset 在 sandbox sink 上产生与
mode_ceiling 不同的行为，哨兵值保持 `_NOOP` 不变。**

**理由（实测，`repro/design_points_probe.py` 的 D2 段）**：`ContextVar.reset(token)` 的跨
上下文判据是 **Context 身份**，与 `default=` 的取值**无关**——两种默认值都抛 `ValueError`：

```
D2: 跨上下文 reset —— _NOOP-defaulted vs None-defaulted
  sandbox sink (default _NOOP): ValueError -> 跳过，未写入
  mode_ceiling (default None): ValueError -> 跳过，未写入
```

`_NOOP` 的「丢弃事件」语义也不受影响：`reset(token)` 恢复的是**那次 set 之前**生效的值
（未 set 过时即 `default`），即同一个 `_NOOP` 单例。

**为什么**不**顺手把 `_NOOP` 改成 `None`**：`_NOOP` 承载的是**行为**（丢弃事件、`emit` 是
空实现），而 `None` 只表达「没有值」。引入 `None` 会新造一层「`None` 是『无 sink』还是
『某个真 sink 被误设为 None』」的歧义，且 `current_sandbox_sink()` 的既有调用方（含
`test_emit_noops_without_explicit_sink`）要跟着改。**收益为零、破坏面为正**。

### D3：`set_sandbox_sink` 改为返回 token —— 运行期兼容，无需保留旧签名

issue 的第二问：`set_sandbox_sink` 是公开函数，改签名会不会影响调用方？

**结论：改为「返回 token」是运行期兼容的增量变更，无需兼容 shim、无需双签名。**
现有调用方**全部忽略返回值**（已逐个核对，见 `proposal.md` 的调用点表）；`context.py` 的
同类函数本就返回 token（`set_mode_ceiling(mode) -> Any` / `set_spawn_depth(depth) -> Any`），
本 change 只是与既有约定对齐。**不引入**「`set_sandbox_sink(sink, *, return_token=...)`」这类
双形态参数——那会给唯一的内部调用点增加一个无消费者的分叉。

### D4：token 门控在「是否 set 过」上——`sink_token = None` 而非无条件 set

**这是本 change 唯一真正的实现选择**，因为现有代码里 `set` 是**门控**的（`if trace_recorder:`）
而恢复是**无条件**的，两者不对称。

- **选定**：`sink_token = None` 起步，仅在有 recorder 时 set 并捕获 token；`finally` 用
  `if sink_token is not None` 门控 reset。
- **理由（两条）**：
  1. **结构上被迫**：改用 token 后，`reset` 只能恢复**本 run 自己创建过的** token。没 set 过
     就没有 token 可 reset——旧写法的「恢复」在**无 recorder** 的 run 上本质是把
     `current_sandbox_sink()` 读到的值原样写回（in-context 纯无操作），本就没有东西需要恢复。
  2. **顺带消除一条污染载体**：这条「自我无操作写」在**跨上下文**收尾时并不无害——被遗留的
     无 recorder run 收敛尾时会把 `_NOOP`（或从派生上下文继承来的旧真 sink）写进活跃上下文，
     与形态 A/B 是同一句写、同一个后果。门控掉它即同时消除「自我无操作写」与「跨上下文污染写」。
- **附带清理**：`previous_sandbox_sink = current_sandbox_sink()`（`:560`）随之不再被使用，
  删除；`current_sandbox_sink` 在本文件无其它消费者，import 收窄为
  `reset_sandbox_sink, set_sandbox_sink`（与 #261 的 D2 清理同形，**非语义**）。
- **被否的替代**：把 `set` 提到门控外、无条件
  `sink_token = set_sandbox_sink(TraceRecorderSandboxSink(trace_recorder) if trace_recorder else previous)`。
  它同样能让 token 恢复正确，但会**凭空加一次无意义的 contextvar 写**，并使「没 recorder」
  与「有 recorder」两条路径的语义变得不必要地隐晦。

### D5：回归测试用真实代码路径 + 确定性 GC 触发，并做变异验证

测试构造与 `repro/sandbox_sink_repro.py` 同源：在**独立 event loop** 上跑一个会挂住的
子 run → 关闭该 loop（task 保持 pending）→ 活跃 run 的轮次里 `gc.collect()` 终结它 →
断言活跃 run 的 sink 未被改写、其 sandbox 事件仍落入自己的 trace。
**变异验证**：把 `finally` 改回 `set_sandbox_sink(previous_sandbox_sink)` 该用例必须变红。

选择它而非「并发加压碰运气」的原因与 #261 相同：后者不可复现，确定性构造让回归在**任何**
机器上都有效。

### D6：补一条 MODIFIED spec delta

既有 Requirement「沙箱事件入 trace」只约束**如何发事件**（类型 / `tool_call_id` / 截断 /
schema 兼容），**未**表达本 issue 的核心不变量——**已死 run 的收尾不得改写另一个活跃 run
的事件归属**。故以 MODIFIED 补齐该 Requirement（正文追加「sink 只对其所属执行上下文生效」）
并新增 Scenario「被遗留 run 的迟后收尾不改变活跃 run 的事件归属」。这不改变实现，只是把新
确立的行为约束写进规格（与 #261 的 D4 同形）。

## Pre-Implementation Review

本 change **不单独跑 `batch-grill-me`**，理由（与 #261 的 tasks.md 顶部论证同形）：
本 change 是 **bugfix**，机制已由 #261 **钉死并有确定性实测**，设计空间已被上游
（#255 的 contextvar 通道 + #261 的守护式 reset）**完全锁定**——三个设计点（D2/D3/D4）各有
**一手实测结论**（`repro/design_points_probe.py`），无待用户拍板的真实分叉点
（详见 `tasks.md` 顶部的论证段）。该判断与 #261 的先例一致。

## Risks / Trade-offs

- `reset(token)` 在 token 已被消费时抛 **`RuntimeError`**（不是 `ValueError`）——本 token 由本
  coroutine 自己创建、至多消费一次，`if sink_token is not None` 门控保证只在 set 过时 reset，
  `except ValueError` 吸收跨上下文分支。实测确认无路径可触发二次 reset
  （`repro/design_points_probe.py` D1 段）。
- `except ValueError: pass` 可能掩盖同上下文的意外失效——但该分支只在 Context 不同或 token
  已用时才触发，两者在此均为预期路径。已就地注释说明语义。
- 门控 reset（D4）改变了「无 recorder 的 run 结尾会写一次同值」这一 **in-context 无操作**副作用
  （它在跨上下文收尾时并不无害，见 D4）；已核对无测试依赖该写入
  （`test_sink_restored_after_run` 走的是**有 recorder** 的路径）。

## Migration / Testing

- 无迁移（无 schema / 配置 / 产物变化）。
- 测试：新增 1 条确定性回归（含变异验证）；`tests/agent/test_sandbox_events.py` +
  `tests/agent/test_loop_sandbox_events.py` 保持绿；全量 `uv run pytest -q`。
