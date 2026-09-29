# Proposal: 挂载 A 改守护式 reset，修跨上下文收尾清空 mode 上限（fix-issue-261-mode-ceiling-flake）

关联跟踪 issue：[#261](https://github.com/Xingkai98/asterwynd/issues/261)。

## Change Type

- primary: bugfix
- secondary: []

> **生产代码 bugfix**（非测试侧）。issue 正文原判为「测试侧同步缺陷」，本 change 的
> `diagnosis.md` 已用确定性证据否证（断言点**已经**等到 mode 冻结），并钉死真实根因在
> `agent/loop.py` 的挂载 A 恢复方式。

## Why

`tests/agent/subagent/test_mode_ceiling.py::test_next_run_after_switch_uses_new_mode`
在 CI 全量负载下偶发失败（`AssertionError: assert 'build' == 'read_only'`，重跑即过），
并伴随 `Task was destroyed but it is pending!`。

**根因（详见 `diagnosis.md`）**：`AgentLoop.run` 在 run 起点用挂载 A 收紧 mode 上限
（`loop.py:570`），并在 `finally` 里用**普通 `set_mode_ceiling(previous_ceiling)`** 恢复
（`loop.py:598`，`fix-issue-255` 当年为规避跨 context `reset` 抛 `ValueError` 而选的方案）。

子 agent run 是**独立 Task**（`manager.py:967`）。测试会**遗留**这类 pending task；
当其所属事件循环已关闭、task 被 GC 终结时，协程的 finalize 会展开它**所有嵌套的
`finally`**——包括这句恢复。关键在于**协程 finalize 不安装 task 自己的 Context**，
而 `ContextVar.set` 写入**当前正在运行的上下文**：于是这句 `set(previous)` 会把
**后续用例**正在使用的只读上限**清成 `None`**，使节点回落静态 `parent_mode`（BUILD）
而被授予 `build`——正是 CI 那句 `assert 'build' == 'read_only'`。

**影响方向是安全的反面**：只读会话可能因此被授予写权限（fail-open）。且它是**间歇性**
的——会训练出「红了就重跑」的危险习惯。

**确定性证据**（`diagnosis.md` 与 `repro/`）：最小脚本 + 真实代码路径脚本均稳定复现
（现状 5/5 REPRODUCED）；对照实验证明 `task.cancel()` 路径（pytest-asyncio 的
`Runner.__exit__`）**不**污染、只有「循环已关 + GC 终结」才污染——这也解释了为何
早期最小探针未能复现。

## What Changes

- **挂载 A 改守护式 `reset(token)`**（`agent/loop.py`）：run 起点
  `ceiling_token = set_mode_ceiling(self.runtime_state.current_mode)`；`finally` 改为
  `try: reset_mode_ceiling(ceiling_token) except ValueError: pass`。
  - **同上下文**：token 正常恢复 run 起点的上限（`fix-issue-255` 的 4.10 / 4.8 行为不变）。
  - **跨上下文**（遗留 task 的迟后终结）：`reset` 主动抛 `ValueError` → 跳过，**不再写入
    当前上下文**，因而不再污染后续 run。
- 删除因此不再使用的 `previous_ceiling = current_mode_ceiling()` 行，并把
  `current_mode_ceiling` 的 import 收窄为 `reset_mode_ceiling, set_mode_ceiling`。
- **新增回归测试**（`tests/agent/subagent/test_mode_ceiling.py`）：构造「遗留 pending
  run task（其循环已关）+ 活跃只读 run 上下文 → 活跃 run 期间 GC 终结遗留 task」，
  断言活跃上限保持 `read_only`、节点冻结为 `read_only`。**变异验证**：把实现改回
  `set_mode_ceiling(previous_ceiling)` 该用例必须变红（已实测）。
- **保留复现脚本**（`repro/`）：最小脚本、真实路径 A/B、`set_sandbox_sink` 两个复现脚本，
  作为本 change 的证据链随 PR 提交。

**不在本 change 范围**（见 `diagnosis.md` 与 `## Reference Implementation Research`）：

- `set_sandbox_sink`（`agent/loop.py:601`）**同源**且经实测**能复现且可观测**（sandbox
  事件静默丢失 / 串写进别的 trace）。它是**独立载体**（本 change 的修复不覆盖它），
  建议**单独立项**。
- issue 正文的订正由主 session 处理，不在本 change 内。

## Capabilities

### New Capabilities

（无。）

### Modified Capabilities

（无 spec delta。）本 change 修的是**实现缺陷**，不改规格语义：`openspec/specs/subagents/spec.md`
既有的 Requirement「子 agent mode 上限按执行上下文继承」及其 Scenario「执行上下文上限的
set 不破坏运行收尾」（「系统 SHALL NOT 因上限的 token reset 抛出 `ValueError`」）**已经**
约束了本 change 的行为——本 change 是让实现**回到**该 Scenario 的要求（`reset` 抛
`ValueError` 时必须被吸收、不得破坏收尾）。故无 delta。

## Reference Implementation Research

- research_tier: **exempt**
- status: enabled
- reason: 本 change 属**纯 bugfix，无新增能力面**（不引入新通道 / 新依赖 / 新协议），且
  设计已被上游决策锁定——命中的是分流表 `exempt` 的「bugfix（无新增能力面 + 回归测试）」
  与「上游决策锁定」。**客观证据**：
  - 结构关键词：改动仅 `agent/loop.py` 内 `finally` 的一处恢复语句（`set` → 守护式
    `reset`），是 `openspec/changes/archive/2026-09-27-fix-issue-255-mode-ceiling/`
    已确立机制的**修正**——该 change 的 `design.md` / `diagnosis.md` 已就「上限通道」与
    「跨 context teardown」做过完整调研（`research_tier: full`）并留有记录；本 change
    不引入第二个机制。
  - 回归测试：新增确定性回归 + 变异验证（见 `## What Changes`）。
- research questions:（exempt，不适用。）
- findings: 无新增外部调研需求。相关判定依据均在本仓库既有记录内：
  `openspec/changes/archive/2026-09-27-fix-issue-255-mode-ceiling/diagnosis.md`（挂载 A 的
  set/reset 取舍与 `ValueError` 复现）、`docs/known-debt.md`（mode 相关的已知残留）。
  本机 `.dev/reference-repos.txt` 不存在（按仓库约定不提交），故未做参考仓库对比；
  但本 change 为 exempt，不做外部调研亦满足门槛。
- design impact: 无设计层面变化——只是把 `fix-issue-255` 的恢复方式换成它能满足自身
  Scenario 的写法（`reset` + 吸收 `ValueError`），不改变上限语义、快照点或传播路径。

## Impact Analysis

- **能力域**：无 spec delta；`openspec/specs/subagents/spec.md` 既有 Scenario
  「执行上下文上限的 set 不破坏运行收尾」被本 change **重新满足**（不是新约束）。
- **代码**：`agent/loop.py` 一处（挂载 A 的 set 行 + `finally` 的恢复行 + import）；
  无新增模块、无新增依赖、不改 `context.py`（`reset_mode_ceiling` 已存在）。
- **数据 / 配置**：无 schema 变化，无迁移；不写盘。
- **对外行为**：修正「遗留 run 的迟后终结把后续 run 的只读上限清空 → 节点被授予 `build`」
  这一 fail-open 间歇缺陷；同上下文恢复语义**不变**（run 退出后上限复原、取消路径不抛）。
- **测试**：`tests/agent/subagent/test_mode_ceiling.py` 新增 1 条确定性回归 + 变异验证；
  全量 `uv run pytest -q`。
- **文档**：本 change 文档（proposal / diagnosis / tasks）+ `docs/openspec-change-backlog.md`
  同步；`set_sandbox_sink` 的同源缺陷记入 `diagnosis.md` 并建议单独立项（本 change 不改
  `docs/known-debt.md`）。
- **风险面**：`reset(token)` 在**同上下文**若 token 已被消费或失效会抛 `ValueError`——
  但该 token 由本 coroutine 自己创建、至多消费一次，`except` 也已兜住；`unknown`：无。
- **并行冲突**：与 #246（`patterns.py`/`subagents.py`/`scheduler.py`）、#262（`config.py`/
  `workflow.py`）无重叠；本 change 只碰 `agent/loop.py` 与测试。
