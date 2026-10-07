# Proposal: 工具结果 spill 生命周期内聚为单一 ToolResultSpiller 模块（tool-result-spill-module）

关联跟踪 issue：[#300](https://github.com/Xingkai98/asterwynd/issues/300)（【feature】tool-result spill 生命周期内聚为单一 ToolResultSpiller 模块）。

前置：本 change 是已归档 `tool-result-lifecycle`（[#282](https://github.com/Xingkai98/asterwynd/issues/282)，PR #284）的**结构性深化**——不新增能力，只把该 change 落地的有界工具结果生命周期从「横跨三个文件的浅实现」内聚为「单一深模块」。

## Change Type

- primary: refactor
- secondary: []

## Why

### 问题：有界工具结果生命周期的实现横跨三个文件

`tool-result-lifecycle` 落地的判定与剪枝逻辑，今天分布在三处，各自的职责边界要靠人读三份文件才能拼出来：

| 位置 | 内容 | 现状 |
|---|---|---|
| `agent/memory/tool_result_policy.py` | 判定/预览**纯函数**（`make_preview` / `exceeds_single_threshold` / `is_spilled_preview` / `content_bytes` / `value_bytes` / `READ_PROGRESS_RE` …） | 干净：无状态、不碰 I/O |
| `agent/memory/manager.py` | `MemoryManager.prune_tool_results`（约 65 行剪枝 `for` 循环：幂等判据 + 「已消费一轮」+ 「滑出窗口 ∪ 单条超阈」+ `_tokens=None` 重置 + 注入 `save` 回调）；`MemoryManager.is_oversized_result`（单条阈判定） | `MemoryManager` 同时承担「消息历史 + 摘要/压缩」与「工具结果剪枝」两类职责 |
| `agent/loop.py` | 迭代标记 `_tool_result_iterations` 的两次写入（错误路径 / 正常路径）+ `_reset_tool_result_iterations`（含 resume 重扫）+ `_spill_and_prune` 的 `save` 闭包与 `tool_result_spill` 事件 / trace 发射 | 剪枝的**状态**（迭代标记）在 loop、**算法**在 manager，语义被切开 |

**这是「浅实现摊开在多处」**：要理解「什么结果在什么时机被剪、剪完怎么记」必须同时读 `manager.py` 与 `loop.py`；迭代标记的生命周期（何时写、何时 reset、resume 怎么处理）与剪枝算法分居两文件，任何一侧改动都要跨文件核对。

### 目标：内聚为单一深模块

把一个「窄接口 + 厚实现」的深模块立起来：对外只暴露 `mark` / `reset` / `spill` 三个方法，把剪枝算法、迭代状态、判据调用、`_tokens` 重置全部隐藏进去。调用方（`AgentLoop`）只需知道「标记一个结果已被消费」和「把陈旧结果剪掉」，不再需要知道判据细节或状态存储形态。

**这是纯重构**：可观测行为（`tool_result_spill` 事件、trace step、日志语义、剪枝结果）零变化。既有的两个测试文件是回归判据。

## What Changes

1. **新增深模块** `agent/memory/tool_result_spiller.py`：`ToolResultSpiller` 类 + `PruneStats` 数据类（自 `manager.py` 迁入；删除委托后唯一外部引用者 e0 脚本的 import 一并改到 spiller，`manager.py` 无需重导出）。
2. **对外接口**：
   - `mark(tool_call_id: str, iteration: int) -> None` —— 记一个工具结果入库时的 iteration（取代 loop 内联写 `self._tool_result_iterations[id] = self._iteration`）。
   - `reset(messages: list[Message]) -> None` —— 清空本 spiller 的标记，并把给定 `messages` 中**已存在**的 `role == "tool"` 消息预置为「已消费」（`-1`）；语义等价于今日 `_reset_tool_result_iterations`。
   - `spill(messages, *, current_iteration: int, added_iterations: dict[str, int] | None = None, save: Callable[[str], str] | None = None) -> PruneStats` —— 执行剪枝循环（今日 `prune_tool_results` 主体）。`added_iterations=None` 时走 spiller 自身的 `mark` 状态，非 `None` 时以传入的外部映射为准（覆盖注入），供既有测试面的显式 `added_iterations=` 调用兼容。
3. **剪枝循环主体**自 `MemoryManager` 迁入 spiller；`MemoryManager` 组合并持有 spiller（`self.tool_result_spiller`），构造期注入 `max_tokens` / `recent_window` / **counter**。
4. **`MemoryManager.is_oversized_result` 保留**（唯一调用方是 loop 的 `_bound_ledger_result`，不属剪枝循环）。
5. **`agent/loop.py`**：迭代标记写入改经 `self.memory.tool_result_spiller.mark(...)`；`_reset_tool_result_iterations` 改经 `self.memory.tool_result_spiller.reset(...)`；`_spill_and_prune` 改调 `self.memory.tool_result_spiller.spill(...)`（**删除** manager 委托，e0 monkeypatch 目标同步改 `loop.memory.tool_result_spiller.spill`）。**事件与 trace 发射仍留 loop**——spiller 只返回 `PruneStats`，不持有 `on_event` / `trace_recorder`。
6. **账本有界路径**（`_bound_ledger_result` / `_bound_arguments`）**本轮不动**（留在 loop）；design 记录该 seam 边界与后续演进方向。
7. **新词条记入 `CONTEXT.md`**（本仓库词汇权威；无 GLOSSARY.md）。

**不变**：`tool_result_spill` 事件名与 payload、trace step 结构、日志语义、剪枝判据与结果、`PruneStats` 字段、`artifact://agent/...` ref 形态、压缩硬顶行为、context-engineering spec 已钉的可观测契约（本 change 只**新增**结构内聚要求，不修改既有行为契约）。

## Capabilities

### New Capabilities

无新能力域。

### Modified Capabilities

- `context-engineering`：**ADDED** 新 Requirement「工具结果有界化的单一内聚宿主与单一判据来源」——工具结果有界化（spill）的判据与剪枝循环 SHALL 内聚于单一模块并提供单一入口；`AgentLoop` SHALL 经该入口触达 spill，SHALL NOT 自带剪枝编辑/迭代状态管理副本；判定阈 SHALL 有单一来源（SHALL NOT 多处各持一份判据而漂移）；内聚 SHALL NOT 改变既有可观测契约（事件、标记、回读语义）。

## 验收（本 change 的验收口径，**只进 proposal、不进 spec**）

| # | 指标 | 主/辅 |
|---|---|---|
| **R0** | **纯重构等价**：既有 `tests/agent/memory/test_tool_result_lifecycle.py` 与 `tests/agent/test_tool_result_lifecycle_loop.py` **不作语义修改**即全绿（`tool_result_spill` 事件 + trace step + 剪枝结果不变） | **主指标** |
| **R1** | **接口内聚**：`ToolResultSpiller` 对外仅 `mark` / `reset` / `spill` 三个方法（+ 数据类），剪枝算法/迭代状态/`_tokens` 重置全部隐藏 | **主指标** |
| **R2** | **单一判据来源**：阈值判据仍由 `tool_result_policy` 纯函数提供；`ToolResultSpiller` 与 `MemoryManager.is_oversized_result` 共用同一 counter 注入点（含测试的 `_count_tokens` monkeypatch 可替换） | **主指标** |
| **R3** | **调用面收窄**：`loop.py` 不再内联维护 `_tool_result_iterations` dict（写入/reset 均经 spiller） | 辅 |
| **R4** | **不退化**：全量 `uv run pytest -q` 全绿；OpenSpec strict validate 通过 | 辅 |

**通过门槛**：R0 + R1 + R2 成立（行为等价 + 接口内聚 + 判据单一来源），R3–R4 可验证。

## Reference Implementation Research

- status: enabled
- research_tier: light
- reason: 命中 `light` 判据「常规功能增强；成熟模式的局部应用」——把既有逻辑内聚为深模块（deep module / information hiding）是成熟的软件设计模式，**不引入新框架/新依赖/新协议**，无架构级改造（不改能力域边界、不改协议、不改可观测契约），故不属 `full`；本 change 有实质代码改动面（非 docs-only、非 bugfix），故不属 `exempt`。
- findings:
  1. **业界实践结论：深模块（deep module）是公认的模块设计目标。** Ousterhout《A Philosophy of Software Design》的核心论点——模块的**接口应远窄于其实现**（deep module），「浅模块」（接口体量与实现相当）与「信息泄漏」（实现细节跨模块可见）是复杂度的主要来源。本 change 正是把一个「判定纯函数 + 剪枝循环 + 迭代状态」摊在三处的形态，收拢为「三方法接口 + 全隐藏实现」的深模块。本仓库 `codebase-design` skill 提供的共享词汇（deep module / seam / interface）与本结论同源。
  2. **本地参考仓库不可用**：本工作区 `.dev/reference-repos.txt` **不存在**（已核验），故不做参考仓库对比。改用依据为上述业界实践结论 + 本仓库既有同族先例——`tool-result-lifecycle` 已把**判定纯函数**抽为 `agent/memory/tool_result_policy.py`（无状态、可单测），本 change 延续同一「按职责分层」方向，把**有状态的剪枝循环**也内聚到 `agent/memory/` 下的单一模块。「本地参考仓库不可用」**不构成 exempt 理由**，故如实按 `light` 档完成调研并记录。
  3. **同族先例（本仓库内）**：`agent/memory/` 已按「策略/纯函数 vs 状态/管理器」分层（`tool_result_policy.py` / `manager.py`）。本 change 把 spiller 放进同目录，与 policy 同层——即「工具结果生命周期」这一关注点在 `agent/memory/` 下自成一组，不与 `MemoryManager` 的摘要/压缩职责混居。
- design impact: 见 design **D1**（深模块形状与三方法接口）、**D2**（counter 单一注入点，保住测试 monkeypatch 缝）、**D3**（迭代状态归 spiller 所有）、**D6**（账本有界路径的 seam 边界——本轮不收，记录演进方向）。**调研对设计的主要影响**：finding 1 把「接口窄于实现」立为接口设计的硬判据（三方法、无 getter 泄漏内部 dict）；finding 3 把放置位置定为 `agent/memory/tool_result_spiller.py`（与 policy 同层同组）。

## Impact Analysis

- **能力域**: `context-engineering`（工具结果生命周期——只新增结构内聚要求，不改行为契约）。
- **代码**:
  - **新增** `agent/memory/tool_result_spiller.py` —— `ToolResultSpiller`（`mark` / `reset` / `spill`）+ `PruneStats`；持有 `max_tokens` / `recent_window` / counter 与迭代标记 dict。
  - `agent/memory/manager.py` —— `prune_tool_results` **删除**（Q1 定案，主体迁入 spiller）；`PruneStats` 迁出（无需重导出，e0 import 一并改 spiller）；`MemoryManager` 构造 spiller；`is_oversized_result` 保留。
  - `agent/loop.py` —— 两处 `self._tool_result_iterations[...] = self._iteration`（约 `:898` / `:1092`）改经 `self.memory.tool_result_spiller.mark(...)`；`_reset_tool_result_iterations`（约 `:1559`）改经 `self.memory.tool_result_spiller.reset(...)`；`_spill_and_prune`（约 `:1616`）改调 `self.memory.tool_result_spiller.spill(...)`。**事件/trace 发射（`:1646-1658`）不动**。
  - `agent/memory/tool_result_policy.py` —— **不改**（判据纯函数原地不动）。
- **测试**:
  - **必须保留**（作为纯重构回归判据，**不作语义修改**）：`tests/agent/memory/test_tool_result_lifecycle.py`（判定纯函数 + `prune_tool_results` 13 处直调）、`tests/agent/test_tool_result_lifecycle_loop.py`（`tool_result_spill` 事件 + trace step）。
  - **必须新增**：`ToolResultSpiller` 的直接单测（三方法各自语义、迭代状态隔离、counter 注入）；`mark` / `reset` 的边界（未标记不剪、reset 预置 `-1`、resume 重扫后仍可剪）。
  - **必须回归**：`agent/memory` 既有压缩/摘要测试；`tests/agent/test_trace_recorder_bounded.py`；全量 `uv run pytest -q`。
- **脚本**: `scripts/e0_tool_result_lifecycle.py` 第 110 行 `loop.memory.prune_tool_results = lambda *a, **k: PruneStats()` 的 monkeypatch 依赖 `MemoryManager.prune_tool_results` 的**存在**（OQ1 的约束条件）与 `from agent.memory.manager import PruneStats` 的**兼容重导出**。
- **文档**:
  - `openspec/specs/context-engineering/spec.md`（current spec 同步，受保护路径——本 change 归档时随 delta 合入）。
  - `CONTEXT.md`（新增词条）。
  - `docs/architecture.md`（`MemoryManager` 行与新增 `ToolResultSpiller` 行的职责描述）。
  - `docs/openspec-change-backlog.md`（受保护路径）。
  - `README.md` / `README_EN.md` 关键词扫描（预计无影响——不涉用户可见行为）。
- **流程（process）**: change type = refactor（属 `DESIGN_TYPES`）→ 实现前必须走 `grilling` + 停轮确认 Open Questions；grill 后、停轮前跑设计阶段审阅闭环（`reviews/grill-adversarial.md`）；实现完成后走 `/review-loop`（`reviews/building-review.md` + manifest）。实现须独立 worktree、`tool-result-spill-module/2026-10-07` 分支。
- **与既有 change / issue 的边界**:
  - **`tool-result-lifecycle`（#282，已归档）**：本 change 是其实现的**结构深化**，不新增能力；其落地的可观测契约是本 change 的回归基线。
  - **`read-output-bound`（#280，已归档）**：治单条峰值（源头），本 change 不碰。
  - **账本有界路径（`_bound_ledger_result` / `_bound_arguments`）**：不同目标（会话消息 vs 可观测账本），**本轮不收进 spiller**（见 design D6）。
- **代价权衡**: 迁移引入一次性的机械 churn（移动 65 行 + 改若干调用点），换来「工具结果生命周期」关注点的单一定位与后续改动的局部性。无运行时行为变化，无性能影响。
- **可回滚性**: 改动集中在 `agent/memory/` + `agent/loop.py`；回滚 = revert，无数据迁移。

## Non-Goals（摘要）

- **不改**任何可观测行为：`tool_result_spill` 事件名/payload、trace step、日志语义、剪枝判据与结果、`PruneStats` 字段。
- **不改** `tool_result_policy.py` 的纯函数（判据与预览形态原地不动）。
- **不引入**新框架 / 新依赖 / 新协议 / 新持久化。
- **不改**默认数值（`max_tokens` / `recent_window` / 阈值常量）。
- **不收进**账本有界路径（`_bound_ledger_result` / `_bound_arguments`）——不同目标，另议（design D6 记录演进方向）。
- **不做** `_workflows` slots / 跨图壳清理等 #283 族残余项。
