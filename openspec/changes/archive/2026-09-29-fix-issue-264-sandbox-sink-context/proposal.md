# Proposal: sandbox sink 改守护式 reset，修跨上下文收尾污染后续 run 的事件归属（fix-issue-264-sandbox-sink-context）

关联跟踪 issue：[#264](https://github.com/Xingkai98/asterwynd/issues/264)。

## Change Type

- primary: bugfix
- secondary: []

> **生产代码 bugfix**（非测试侧）。与 #261 **同源同机制**：`agent/loop.py` 的同一个
> `finally` 里有**两句**「恢复前值」——`set_mode_ceiling`（#261 已改守护式 `reset`）与
> `set_sandbox_sink`（本 change）。#261 只修了前者，实测在**已应用 #261 的树上**本缺陷
> 仍确定性复现（见 `diagnosis.md`）。

## Why

`AgentLoop.run` 在 run 起点用 `set_sandbox_sink(...)` 把 sandbox 事件接到本 run 的
`TraceRecorder`（`agent/loop.py:580`，门控于 `if trace_recorder:`），并在 `finally` 里用
**普通 `set_sandbox_sink(previous_sandbox_sink)`** 恢复（`agent/loop.py:600`，**无条件**）。

`agent/sandbox_events.py` **只有 `set_sandbox_sink`，没有 reset 版本**——它是裸
`ContextVar.set`，不回 token（对比 `agent/subagent/context.py` 的
`set_mode_ceiling` / `reset_mode_ceiling` 成对，后者由 #255 建立）。

**根因（与 #261 同一机制，`diagnosis.md` 有实测）**：`SubAgentManager` 的子 run 是独立
`Task`（`manager.py:966`）。测试/编排会**遗留** pending task；当其**所属事件循环已关闭**、
task 被 GC 终结时，`Task.__del__ → coro.close()` 把 `GeneratorExit` 抛进协程，展开它
**所有嵌套的 `finally`**——包括这句恢复。**协程 finalize 不安装该 task 自己的 Context**，
而 `ContextVar.set` 写入**当前正在运行的**上下文：于是这句 `set(previous)` 落进了**后续
run** 的上下文，把它的 sink 覆盖成过期值。

**两个故障形态**（`diagnosis.md` 有原始输出）：

| 形态 | 覆盖成 | 后果 |
|---|---|---|
| A | `_NOOP`（默认值） | 后续 run 的 sandbox 事件**静默丢失**，不写进任何 trace（**可观测性缺口**） |
| B | **过期真 sink** | 后续 run 的事件**串写进旧 run 的 trace**（**审计证据污染**） |

形态 B 是最严重的一面：一条 `denied rm -rf /` 安全拒绝事件被记进了**错误的 trace**——
安全审计证据张冠李戴，且**不报错、不告警**。

**为什么必须修**：这两句恢复是「同一 `finally` 里的同一类错误」。只修 mode_ceiling 会让
读者以为该 `finally` 已被「守护式 reset」模式覆盖，而 sandbox sink 仍是裸 `set`——
一处被修好的同类缺陷会给其余同类缺陷提供**虚假的安全性**。

## What Changes

- **`agent/sandbox_events.py` 新增「token + reset」API**（与 `context.py` 的
  `set_mode_ceiling` / `reset_mode_ceiling` 同形）：
  - `set_sandbox_sink(sink)` 改为返回 token（`-> Token`，注解放宽为 `Any`）；
  - 新增 `reset_sandbox_sink(token)`，转发 `_current_sink.reset(token)`。
- **`agent/loop.py` 的 sandbox sink 恢复改守护式**：
  - run 起点：`sink_token = set_sandbox_sink(TraceRecorderSandboxSink(trace_recorder))`
    仍在 `if trace_recorder:` 门控内，但**捕获 token**（未设时 token 为 `None`）；
  - `finally`：`if sink_token is not None: try: reset_sandbox_sink(sink_token) except ValueError: pass`。
  - **同上下文**：token 正常恢复 run 起点的 sink（嵌套子 run 仍回落到父 sink，行为不变）。
  - **跨上下文**（遗留 task 的迟后终结）：`reset` 主动抛 `ValueError` → 跳过，**不再写入
    当前上下文**，因而不再污染后续 run。
  - 删除因此不再使用的 `previous_sandbox_sink = current_sandbox_sink()` 行，`current_sandbox_sink`
    的 import 收窄为 `reset_sandbox_sink, set_sandbox_sink`。
- **新增回归测试**（`tests/agent/test_loop_sandbox_events.py`）：构造「遗留 pending run
  task（其循环已关）+ 活跃带 recorder 的 run，并在活跃 run 内 GC 终结遗留 task」，断言
  活跃 run 的 sink 未被改写、其 sandbox 事件仍落入自己的 trace。**变异验证**：把实现改回
  `set_sandbox_sink(previous_sandbox_sink)` 该用例必须变红。
- **保留复现脚本**（`repro/`）：形态 A、形态 B（含确定性 GC 窗口变体与 `PLANT_ABANDONED=False`
  对照）、设计点取证脚本，作为本 change 的证据链随 PR 提交。

**不在本 change 范围**（明确排除，避免范围蔓延）：

- **不改 `_NOOP` 哨兵语义**（issue 明确标注的待确认点）：`_current_sink` 的默认值保持
  `_NOOP`（「丢弃事件」），**不**改成 `None`。实测证明 `ContextVar.reset` 的跨上下文判据是
  **Context 身份**、与 default 的值无关（`diagnosis.md` §设计点 D2），故守护式 reset 在
  `_NOOP` 默认上不会产生与 `mode_ceiling`（`None` 默认）不同的行为；改哨兵只会造出
  「`None` 是『无 sink』还是『某个真 sink』」的新歧义。
- **不改 `_active_on_event` / `_active_trace_recorder`**：它们是 `AgentLoop` 的**实例属性**，
  遗留 task 写入只影响它自己持有的对象，**不构成跨上下文污染**（与 contextvar 不同）。
  经审计无需改动。
- **不改 `agent/subagent/manager.py:_execute_run_in_context` 的「不 reset」决策**：
  该 task 持有私有 context 副本、其值随 task 消亡，`manager.py` 的就地注释已说明这是**刻
  意**设计（在 `GeneratorExit` 下 reset 反而会抛）。本 change 不触碰。
- **不重构 mode_ceiling 路径**（#261 已修）；不改 trace schema、不改事件字段、不改
  `emit_sandbox_event` 的分发语义。
- **不做「把 `AgentLoop.run` 里所有 contextvar 恢复统一成一种模式」的泛化重构**：
  本 change 只补齐 `set_sandbox_sink` 这一处同类缺陷。

## Capabilities

### New Capabilities

（无。）

### Modified Capabilities

`workspace-safety`（MODIFIED 1 条 Requirement）：

- **Requirement「沙箱事件入 trace」**：在既有正文后追加一句「该 sink SHALL 只对其所属执行
  上下文生效：一次 run 退出时对 sink 的恢复 SHALL NOT 写入任何**其它**执行上下文」，并
  **新增一个 Scenario**「被遗留 run 的迟后收尾不改变活跃 run 的事件归属」
  （见 `specs/workspace-safety/spec.md`）。

> **为何需要 delta**：既有 Requirement 只约束「沙箱**如何**向活跃 `TraceRecorder` 发事件」
> （事件类型、`tool_call_id`、命令截断、schema 兼容），**没有**表达本 issue 的核心不变量——
> **一个已死 run 的收尾不得改写另一个活跃 run 的事件归属**。这是本次新确立的行为约束，
> 值得进规格；且 `openspec validate --strict` 要求 change 至少含一个 delta。

## Reference Implementation Research

- research_tier: exempt
- status: disabled
- reason: 本 change 属**纯 bugfix，无新增能力面**——不引入新框架/新依赖/新协议、不对标业界
  产品，命中的是分流表 `exempt` 的「**bugfix**（无新增能力面 + 回归测试）」。设计空间已被
  上游决策**完全锁定**（「上游决策锁定」）：新增的 `reset_sandbox_sink(token)` 只是把
  `fix-issue-255` 建立、`fix-issue-261` 已验证的 `set_mode_ceiling` / `reset_mode_ceiling`
  同形结构**复制到 sandbox sink 通道**，不引入第二个机制。**客观证据**：
  - 结构关键词：`bugfix`、`上游决策锁定`。
  - 证据引用：issue `#264`（本 issue）、`#261`（同源缺陷已修，机制钉死）、
    `#255`（token/reset 通道的原始设计）；路径
    `openspec/changes/archive/2026-09-29-fix-issue-261-mode-ceiling-flake/diagnosis.md`
    （同源缺陷的完整根因推导与实测）、
    `openspec/changes/archive/2026-09-27-fix-issue-255-mode-ceiling/`
    （contextvar 上限通道的设计与调研记录，`research_tier: full`）。
  - 回归测试：新增确定性回归 + 变异验证（见 `## What Changes`）。
- research questions:（exempt，不适用。）
- findings: **无新增外部调研需求**。token/reset 形态是 Python `contextvars` 的标准用法，
  其语义由标准库定义、本 change 已用可执行探针逐条实测（`repro/design_points_probe.py`：
  token 在「从未 set」与「set 过」两种情况下均可 reset；跨上下文 reset 抛 `ValueError`
  与 default 取值无关）。三个设计点因此各有**一手实测结论**，不依赖外部对标。
  **本地参考仓库不可用的事实已记录**：本机 `.dev/reference-repos.txt` 不存在（按仓库约定
  该文件不提交），故未做本地参考仓库对比；**但本 change 为 exempt，不做外部调研亦满足门槛**
  ——上述不可用事实不构成本豁免的依据。
- design impact: 无设计层面变化——只是把 `fix-issue-255` 的恢复方式复制到 sandbox sink 通道
  （`reset` + 吸收 `ValueError`），不改变事件分发语义、不改变 sink 默认值、不改变 trace schema。

## Impact Analysis

- **能力域**：`workspace-safety`（MODIFIED 1 条 Requirement，新增 1 个 Scenario）。
  既有 Scenario「命令拒绝事件」「超时 kill 事件」被本 change **重新满足**（不是新约束）。
- **代码**：`agent/sandbox_events.py`（`set_sandbox_sink` 返回值 + 新增 `reset_sandbox_sink`、
  模块 docstring 的 save/restore 说明）；`agent/loop.py` 一处（`finally` 的恢复行 + token 捕获 +
  删除 `previous_sandbox_sink` + 收窄 import）；无新增模块、无新增依赖。
- **公开 API 兼容性**：`set_sandbox_sink` 是公开函数。改为**返回 token** 是**运行期兼容**的
  增量变更——现有调用方全部忽略返回值。**全部调用点已逐个核对**（见下表），无需保留旧签名、
  无需兼容 shim（与 `set_mode_ceiling -> Any` 的做法一致：同一函数返回 token + 独立的
  `reset_*` 函数，**不是**双签名）。
- **数据 / 配置**：无 schema 变化，无迁移；不写盘。
- **对外行为**：修正「遗留 run 的迟后终结把后续 run 的 sandbox sink 改写 → 事件静默丢失
  或串写进旧 trace」这一缺陷；同上下文恢复语义**不变**（run 退出后 sink 复原、取消路径不抛）。
- **测试**：`tests/agent/test_loop_sandbox_events.py` 新增 1 条确定性回归 + 变异验证；
  `tests/agent/test_sandbox_events.py`（含 `test_set_sandbox_sink_restores_previous`）保持绿；
  全量 `uv run pytest -q`。
- **文档**：本 change 文档（proposal / design / diagnosis / tasks）+ `docs/openspec-change-backlog.md`
  同步；无需改 `docs/known-debt.md` / `docs/known-issues.md`（本缺陷是**未归档**的新缺陷，
  不是既有债务条目）。
- **风险面**：`reset(token)` 若 token 已被消费会抛 `RuntimeError`（不是 `ValueError`）——
  但该 token 由本 coroutine 自己创建、至多消费一次，`if sink_token is not None` 门控与
  `except ValueError` 已覆盖实际路径（见 `diagnosis.md` 设计点 D1 的实测）；`unknown`：无。
- **并行冲突**：与 #246（`patterns.py`/`subagents.py`/`scheduler.py`）、#262（`config.py`/
  `workflow.py`）无重叠；本 change 只碰 `agent/sandbox_events.py`、`agent/loop.py` 与测试。
  **注意**：与 #261 改的是**同一个 `finally` 块**（不同行），#261 已合入，本 change 基于其后的
  master。

### `set_sandbox_sink` 全部调用点及改造影响

| 文件:行 | 上下文 | 改造影响 |
|---|---|---|
| `agent/loop.py:580` | 生产：run 起点设本 run sink | **改造点**：捕获返回值作为 token |
| `agent/loop.py:600` | 生产：`finally` 恢复 | **改造点**：改守护式 `reset_sandbox_sink(token)` |
| `agent/loop.py:76` | import | 增 `reset_sandbox_sink`，收窄 `current_sandbox_sink` |
| `tests/agent/test_sandbox_events.py:25,30,106-108` | 单测 save/restore | 兼容（忽略返回值） |
| `tests/agent/test_background.py:164,176,192,199,213,221` | 后台任务 sink | 兼容 |
| `tests/agent/tools/test_process_backend_cgroup.py:84,91,105,111` | cgroup 事件 | 兼容 |
| `tests/agent/tools/test_bash_tool_events.py:23,28` | bash 事件 | 兼容 |

`current_sandbox_sink` 的调用点：`agent/loop.py:560`（本 change 删除）与
`agent/sandbox_events.py:81`（`emit_sandbox_event` 内部，保留）；测试若干（只读，不受影响）。
