# Design: 挂载 A 改守护式 reset，修跨上下文收尾清空 mode 上限（fix-issue-261-mode-ceiling-flake）

关联 issue：[#261](https://github.com/Xingkai98/asterwynd/issues/261)。根因与证据见 `diagnosis.md`。

## Context

`fix-issue-255-mode-ceiling` 引入的挂载 A 在 `AgentLoop.run` 起点收紧 mode 上限，并在
`finally` 恢复。当年的 `diagnosis.md` 明确记录：**跨 context teardown 的 `reset(token)`
会抛 `ValueError`**（`coro.close()` 场景），因此**刻意**选用普通 `set(previous)`。

该取舍修好了「`ValueError` 崩溃」，却引入了本 issue：`set` 永远写「当前正在运行的
上下文」，而遗留 pending task 的迟后终结恰好会在**别人的**上下文里执行这句恢复。

## Goals / Non-Goals

- **Goal**：遗留 run 的迟后终结**不得**改变活跃 run 的 mode 上限；同上下文恢复语义不变。
- **Non-Goal**：不改上限通道（contextvar）、不改快照点、不改传播路径、不改 `context.py`。
- **Non-Goal**：不修 `set_sandbox_sink`（同源但独立载体，建议单独立项）。

## Decisions

### D1：恢复方式用「守护式 `reset(token)`」而非普通 `set(previous)`

```python
ceiling_token = set_mode_ceiling(self.runtime_state.current_mode)   # run 起点
...
finally:
    try:
        reset_mode_ceiling(ceiling_token)
    except ValueError:
        pass
```

**理由**：`ContextVar.reset(token)` 的语义是「恢复该 token 记录的那次 set 之前的值」，
且 CPython **强制** token 只能在其创建时的 Context 里 reset —— 跨 Context 时主动抛
`ValueError`。这个异常**恰好编码了**「本次恢复不该作用于当前上下文」这一事实：

- **同上下文**（正常 run 退出、取消路径）：token 有效 → 正确恢复 run 起点之前的值，
  `fix-issue-255` 的 4.10（run 退出后复原）/ 4.8（取消不抛）行为**逐字不变**。
- **跨上下文**（遗留 task 的迟后终结）：token 失效 → `ValueError` → 跳过，
  **不写入当前上下文**，因此不再污染后续 run。

**被否的替代**：

| 方案 | 为何不选 |
|------|---------|
| 保留 `set(previous)` + 记录创建时的 Context、恢复前比对 `copy_context()` | 自己复刻 token 已做的事，且 `Context` 身份比较易错；token 是语言原生机制 |
| 什么都不做（删掉恢复） | 泄漏上限，`fix-issue-255` 的 4.10 会红 |
| 把上限改为 task-local 的其它机制 | 过度设计；`fix-issue-255` 的 contextvar 通道已 grill 定型 |
| 测试侧「等 run 到终态再断言」 | 断言点**已经**等待（`diagnosis.md` §2 证伪）；且清空来自**别的**遗留 run，等待本用例的 run 无效 |

### D2：删除 `previous_ceiling` 快照行，收窄 import

改用 token 后 `previous_ceiling = current_mode_ceiling()` 不再被使用，删除以免留死代码；
`current_mode_ceiling` 在本文件无其它消费者，import 收窄为 `reset_mode_ceiling, set_mode_ceiling`。
（这是**非语义**清理，不改变 D1 的行为。）

### D3：回归测试用「真实代码路径 + 确定性 GC 触发」，不用 sleep/重试

测试构造与 `repro/realpath_ab.py` 同源：独立 event loop 上跑一个会挂住的子 run → 关闭
loop（task 保持 pending）→ 活跃只读 run 的轮次里 `gc.collect()` 终结它 → 断言节点 mode
仍为 `read_only`。**变异验证**：改回 `set(previous)` 该用例必须变红。

选择它而非「并发加压碰运气」的原因：后者不可复现（早期并发 A/B 读数被机器负载混淆，
已作废）；确定性构造让回归在**任何**机器上都有效。

### D4：补一条 MODIFIED spec delta（订正「无需 delta」的初始判断）

初始判断认为本 change 是实现缺陷、可复用既有 Scenario 而无 delta。但：(1) `openspec
validate --strict` **要求 change 至少含一个 delta**；(2) 既有 Scenario「执行上下文上限的
set 不破坏运行收尾」只约束「**该** run 自身被取消/teardown 时终态一致、reset 不抛
`ValueError`」，**未**表达本 issue 的核心不变量——**已死 run 的收尾不得改写另一个活跃
run 的上限**。故以 MODIFIED 补齐该 Requirement（正文追加「上限只对其所属执行上下文生效」）
并新增 Scenario「被遗留 run 的迟后收尾不改变活跃 run 的上限」。这不改变实现，只是把新确立
的行为约束写进规格。

### D5：`set_sandbox_sink` 不在本 change 修

经实测它是**能复现且可观测**的缺陷（`diagnosis.md` 有结论、`repro/` 有脚本），但它是
**独立载体**——本 change 的修复不覆盖它（实测在已修树上仍复现）。按范围聚焦原则单独
立項，避免把两个不同载体的修复混在一个 PR 里。

## Risks

- `reset(token)` 在 token 已被消费 / 失效时抛 `ValueError`——本 token 由本 coroutine
  自己创建、至多消费一次，`except` 亦兜住；风险可忽略。
- `except ValueError` 可能掩盖**同上下文**的意外失效——但该分支只有在 Context 不同或
  token 已用时才触发，两者在此均为预期路径。已就地注释说明语义。

## Migration / Testing

- 无迁移（无 schema / 配置 / 产物变化）。
- 测试：新增 1 条确定性回归（含变异验证）；全量 `uv run pytest -q`；既有 4.8 / 4.10 保持绿。
