# Design: 工具结果 spill 生命周期内聚为单一 ToolResultSpiller 模块

## Context

`tool-result-lifecycle`（[#282](https://github.com/Xingkai98/asterwynd/issues/282)，PR #284）把有界工具结果生命周期落地为「判定纯函数 + 剪枝循环 + 迭代标记」三件套，但三件套散在三处：

1. **判定/预览纯函数** → `agent/memory/tool_result_policy.py`（干净：无状态、不碰 I/O）。
2. **剪枝循环** → `MemoryManager.prune_tool_results`（`manager.py` 约 L208–272，65 行 `for`）+ `MemoryManager.is_oversized_result`（约 L193）。
3. **迭代状态与编排** → `agent/loop.py`：`_tool_result_iterations` 两处写入（约 L898 错误路径 / L1092 正常路径）、`_reset_tool_result_iterations`（约 L1559，含 resume 重扫）、`_spill_and_prune`（约 L1616）的 `save` 闭包注入与 `tool_result_spill` 事件/trace 发射。

### 已核验的机制事实（本设计的地基，行号以 master @ 97b0370 为准）

1. **剪枝循环唯一**：`MemoryManager.prune_tool_results`（`manager.py:208-272`）全仓唯一调用方是 loop 的 `_spill_and_prune`（`loop.py:1640`）。生产代码无其他调用方。
2. **`is_oversized_result` 唯一调用方**：`loop.py:1600` 的 `_bound_ledger_result`。它**不属**剪枝循环（目标：可观测账本 vs 会话消息）。
3. **迭代标记**：`_tool_result_iterations: dict[str, int]` 在 loop 构造期初始化（`loop.py:206`），两处写入（`:898` / `:1092`），`_reset_tool_result_iterations`（`:1559-1577`）重置（把给定 `messages` 中 `role=="tool"` 的预置为 `-1`），resume 重扫在 `:726`（首次预置在 `:605`）。**除剪枝外无人读该 dict**——唯一读者是传给 `prune_tool_results` 的 `added_iterations` 参数（`loop.py:1643`）。
4. **账本有界计数**：`_bounded_ledger_count` 由 `_bound_ledger_result`（`:1602`）/ `_bound_arguments`（`:1612`）累加，每轮顶部 `:763` 归零，经 `_spill_and_prune` 的 `bounded_ledger` 参数（`:1104`）传给事件发射。
5. **counter 缝**：`MemoryManager.is_oversized_result`（`manager.py:200`）与 `prune_tool_results`（`:249`）都以 `counter=_count_tokens` 调用 policy 纯函数，`_count_tokens` 是 `manager.py` 的**模块级**函数（`:62`）。测试 `tests/agent/memory/test_tool_result_lifecycle.py:42` 用 `monkeypatch.setattr(_manager_mod, "_count_tokens", _counter)` 替换它——即 counter 是**模块全局、call-time 解析**的可替换缝。
6. **`PruneStats`**：定义在 `manager.py:92-103`；唯一外部引用者是 `scripts/e0_tool_result_lifecycle.py:108`（`from agent.memory.manager import PruneStats`）。**`agent/loop.py` 从不引用 `PruneStats`**（全文零命中），重导出的兼容面只为 e0 保留。
7. **事件/trace 发射**：`_spill_and_prune`（`loop.py:1646-1658`）在 `stats.messages_spilled or bounded_ledger` 时发 `record_tool_result_spill` + `on_event("tool_result_spill", ...)`。这是可观测契约，本 change **不动**。
8. **被钉住的测试面**：`tests/agent/memory/test_tool_result_lifecycle.py`（13 处直调 `manager.prune_tool_results`）+ `tests/agent/test_tool_result_lifecycle_loop.py`（断言 `tool_result_spill` 事件 + `trace.steps[].type == "tool_result_spill"`）。

## Goals / Non-Goals

### Goals

- **单一内聚宿主**：工具结果 spill 的判据调用 + 剪枝循环 + 迭代状态 SHALL 内聚于 `agent/memory/tool_result_spiller.py` 的 `ToolResultSpiller`，对外仅 `mark` / `reset` / `spill` 三方法。
- **单一判据来源**：阈值判据仍由 `tool_result_policy` 纯函数提供，counter 有单一注入点（保住测试 monkeypatch 缝）。
- **纯重构**：可观测行为零变化；既有两个测试文件不作语义修改即全绿。
- **收窄调用面**：`loop.py` 不再内联维护 `_tool_result_iterations`。

### Non-Goals

- 不改可观测契约（事件名/payload、trace step、日志语义、`PruneStats` 字段）。
- 不改 `tool_result_policy.py` 的纯函数。
- 不收进账本有界路径（`_bound_ledger_result` / `_bound_arguments`）——见 D6。
- 不改默认数值、不引新依赖、不做 #283 族残余项。

## Decisions

### D1 — 深模块形状：`ToolResultSpiller` + 三方法接口，与 policy 同层

新增 `agent/memory/tool_result_spiller.py`，与 `tool_result_policy.py` 同目录同层（「工具结果生命周期」在 `agent/memory/` 下自成一组，不与摘要/压缩混居）。

对外接口（**窄接口**，隐藏全部实现）：

| 方法 | 语义 | 取代今日 |
|---|---|---|
| `mark(tool_call_id: str, iteration: int) -> None` | 记一个工具结果入库时的 iteration | loop 内联写 `self._tool_result_iterations[id] = self._iteration`（`:898` / `:1092`） |
| `reset(messages: list[Message]) -> None` | 清空标记 + 把 `messages` 中既有 `role=="tool"` 消息预置为 `-1`（已消费） | `_reset_tool_result_iterations`（`:1559-1577`） |
| `spill(messages, *, current_iteration: int, added_iterations: dict[str, int] \| None = None, save: Callable[[str], str] \| None = None) -> PruneStats` | 执行剪枝循环；`added_iterations` 为外部标记灌入通道（见下） | `prune_tool_results`（`manager.py:208-272`） |

**判据（Ousterhout 深模块）**：接口窄于实现。三个方法名都是领域动词（mark/reset/spill），调用方无需知道判据形态、幂等判据、`_tokens` 重置、窗口语义；**不暴露**内部 dict（无 getter），**不暴露** `PruneStats` 之外的状态。这正是把「浅实现摊开在多处」改为「深模块」的落点。

**`added_iterations` 通道（外部标记灌入）**：`spill` 的 `added_iterations` 形参是外部标记灌入通道。`added_iterations=None` 时，剪枝走 spiller 自身的 `mark` 状态；非 `None` 时以传入的外部映射为准（**覆盖注入**）。这是既有测试面的硬要求：`tests/agent/memory/test_tool_result_lifecycle.py` 的 13 处直调**每一处都显式传 `added_iterations=`**（如 `manager.prune_tool_results(messages, current_iteration=4, added_iterations={"c1":3}, save=save)`），R0 要求这批用例不作语义修改即全绿。**`reset(messages)` 与外部 `added_iterations` 语义不同、不可互相顶替**：`reset` 把给定 `messages` 中既有的 `role=="tool"` 消息**一律**预置为已消费（`-1`），而 `added_iterations` 是逐条显式给定的消费轮次；例如 `test_prune_skips_fresh_unconsumed_result` 传 `added_iterations={"c1":3}, current_iteration=3`（`3` 未过 `current-1`，期望**不剪**），若改用 `reset` 会把 `c1` 预置 `-1`（**剪**），语义相反、用例转红。

**构造期注入**：`ToolResultSpiller(max_tokens, recent_window, counter)`——`max_tokens`/`recent_window` 是剪枝判据的输入，`counter` 是判定用的 token 计数器（见 D2）。

### D2 — counter 单一注入点：保住测试 monkeypatch 缝（**本 change 最敏感的技术点**）

**问题**：测试用 `monkeypatch.setattr(_manager_mod, "_count_tokens", _counter)` 替换 counter（事实 5）。今日 `is_oversized_result` / `prune_tool_results` 在方法体内裸引用模块全局 `_count_tokens` ⇒ **call-time 解析** ⇒ monkeypatch 生效。若 spiller 模块**静态导入** `_count_tokens`（`from agent.memory.manager import _count_tokens`），绑定在 import 期固化，monkeypatch 将**不再生效**，测试静默失真。

**决策**：spiller 在构造期接收 `counter: Callable[[str], int]`；`MemoryManager` 构造 spiller 时传一个**延迟解析** `manager.py` 模块全局的闭包：

```python
# manager.py（示意）
self.tool_result_spiller = ToolResultSpiller(
    max_tokens=self.max_tokens,
    recent_window=self.recent_window,
    counter=lambda text: _count_tokens(text),  # call-time 解析模块全局，保留 monkeypatch 缝
)
```

闭包体内的 `_count_tokens` 在**调用时**解析 `manager.py` 的模块命名空间 ⇒ 与今日语义逐字一致，`monkeypatch.setattr(_manager_mod, "_count_tokens", ...)` 仍生效。

**单一来源**：`is_oversized_result` 与 spiller 共用**同一** counter 解析点（同一个 `manager._count_tokens` 全局），SHALL NOT 让两侧各持一份计数逻辑而漂移（这也是 spec「单一判据来源」的落点）。

### D3 — 迭代状态归 spiller 所有（`mark` / `reset` 封装 dict）

迭代标记 dict 的唯一读者是剪枝（事实 3），故随剪枝算法一起迁入 spiller，成为其私有状态。loop 变为：

- 写入点 `:898` / `:1092` → `self.memory.tool_result_spiller.mark(tool_call.id, self._iteration)`。
- `_reset_tool_result_iterations(messages)` → `self.memory.tool_result_spiller.reset(messages)`（保留方法名作为 loop 内的薄转发，或直接调用；见 OQ3）。

**`reset` 语义必须逐字保留**今日 `_reset_tool_result_iterations` 的「预置 `-1`」行为（resume 重扫依赖它，审阅 M2 的修复点），否则 resume 后历史大结果会因 `added is None` 永不剪。

### D4 — `PruneStats` 迁入 spiller 并自 `manager` 重导出

`PruneStats` 定义迁至 `tool_result_spiller.py`（它是 spiller 的产出类型，应与产出者同居）。`manager.py` **重导出**（`from agent.memory.tool_result_spiller import PruneStats`），使既有 `from agent.memory.manager import PruneStats`（`scripts/e0_tool_result_lifecycle.py:108`）不破。

### D5 — `MemoryManager.is_oversized_result` 保留

唯一调用方是 `_bound_ledger_result`（账本路径，事实 2），不属剪枝循环。它继续留在 `MemoryManager`（「traffic through the manager so there is one counter」的既有原则），只是其 counter 与 spiller 共享同一解析点（D2）。

### D6 — seam 边界：账本有界路径**本轮不收进** spiller

`_bound_ledger_result` / `_bound_arguments`（`loop.py:1593-1614`）与剪枝**目标不同**：前者有界化**可观测账本**（`trace` / `tool_calls_made`，无消费者按 ref 回读，只需 bounded），后者有界化**会话消息**（模型当轮要用，需 spill + ref 可回读）。二者共享的只有「单条阈判定」这一层（已由 policy 纯函数提供）。

**决策**：本轮**不收进** spiller，留在 loop；理由——(a) 目标不同（两个不同的有界化关注点），强行合并会造出一个「因巧合而耦合」的模块；(b) 可回滚性与改动面更小。**演进方向**（记录，不在本 change 实施）：若未来账本有界化长出更多共享语义（如统一的可观测计数来源、统一的 ref 策略），可评估把「账本有界化」也抽为 `agent/memory/` 下的平行模块，与 spiller 并列。

### D7 — 事件/trace 发射**留 loop**

`ToolResultSpiller.spill` **只返回 `PruneStats`**，不持有 `on_event` / `trace_recorder`。理由：可观测是**编排关注点**（谁发、发给谁、payload 形态由 loop 的运行上下文决定），不是剪枝算法关注点；把 `on_event` / `trace_recorder` 注入 spiller 会让它变成「知道运行上下文」的浅模块。这与既有分层一致（今日发射就在 loop 的 `_spill_and_prune`）。

### D8 — 可观测行为不变（纯重构保证）

本 change 的**核心正确性判据**是：`tool_result_spill` 事件名/payload、`record_tool_result_spill` trace step、日志文案、剪枝结果（哪些消息被换成预览、`PruneStats` 数值）**逐字不变**。既有测试是其机械证据（R0）。

## Pre-Implementation Review

> 本节记录**决策相关摘要**，不粘贴聊天流水。本 change 的实现前 `grilling` 已完成（`reviews/grill-design.md`），设计阶段对抗审阅也已完成（`reviews/grill-adversarial.md`，verdict = CHANGES_REQUESTED，已按回改清单收敛）；下述为收敛后的决策与争议点状态，`## Open Questions` 待停轮确认。

- **已识别的关键技术争议（grill 必答）**：
  - **OQ1（接口归属）**：`MemoryManager.prune_tool_results` 是否保留为**薄委托**（`return self.tool_result_spiller.spill(...)`），还是**删除**并把 13 处测试调用迁到 `spiller.spill`？
    - 保留委托：`scripts/e0_tool_result_lifecycle.py:110` 的 monkeypatch（`loop.memory.prune_tool_results = lambda ...`）不破；13 处测试调用不动；但 `MemoryManager` 上留一个「只是转发」的浅方法（与 D1 的深模块主张有张力）。
    - 删除：接口更干净（spill 只有 spiller 一个宿主），但需改 e0 脚本的 monkeypatch 目标 + 13 处测试调用，churn 更大、且削弱「不改既有测试面」的纯重构姿态。
    - 草案倾向：**保留委托**（最小 churn + 保住 e0 缝），把「委托是否算浅方法」留 grill 判。
  - **Q2（所有权，已改判代码可定）**：**经对抗审阅改判代码可定——`MemoryManager` 组合持有（`self.memory.tool_result_spiller`），非用户决策**。三条证据：(a) `proposal.md:39` 已把它写成既成事实（`MemoryManager` 组合并持有 spiller）；(b) D2 的构造点写在本文件（`manager.py`），延迟闭包须定义在 manager 模块内才 call-time 解析 `manager._count_tokens`；(c) `scripts/e0_tool_result_lifecycle.py:110` patch 的是 `loop.memory.prune_tool_results`，需 loop 运行时经 `self.memory.*` 发起剪枝（`agent/loop.py:1640`）才生效。详见 `reviews/grill-adversarial.md` 的 `## Code-Resolved` 与 `## Refuted / Corrected`。
  - **OQ3（reset 转发）**：`loop._reset_tool_result_iterations(messages)` 是保留为 loop 内薄转发（调用 `spiller.reset`），还是让两处调用点（`:605` / `:726`）直接调 `self.memory.tool_result_spiller.reset(messages)`？草案倾向**直接调用**（少一层转发），但需确认 resume 注释（M2 语义）迁移后仍可读。
  - **OQ4（seam 边界）**：账本有界路径本轮不收进 spiller 的边界（D6）是否被认可？
  - **OQ5（命名）**：模块名 `tool_result_spiller.py` / 类名 `ToolResultSpiller` / 方法名 `mark`/`reset`/`spill` 是否符合 `CONTEXT.md` 词汇与既有命名风格（`tool_result_policy.py` 同族）？
- **已解决的问题**：counter 缝（D2）——已定位为「必须 call-time 解析，否则测试静默失真」，是本 change 的头号正确性风险。
- **备选方案与否决**：曾考虑把 spiller 做成**无状态纯函数集**（把迭代 dict 留在 loop，只迁循环体）——否决：那样迭代状态与算法仍分居两文件，正是本 change 要消除的「浅实现摊开」形态。

## Risks / Trade-offs

| 风险 | 说明 | 缓解 |
|---|---|---|
| **counter monkeypatch 失真** | 若 spiller 静态导入 `_count_tokens`，测试的 `monkeypatch.setattr(_manager_mod, "_count_tokens", ...)` 静默失效，阈值语义被掩盖（D2） | 构造期注入**延迟解析闭包**；新增单测显式断言 monkeypatch 后 spiller 用替换后的 counter |
| **可观测行为漂移** | 迁移 65 行时改动事件/payload/日志文案 | D8 + R0：既有两个测试文件不作语义修改即全绿；review-loop 逐项核对 |
| **`PruneStats` / e0 脚本 import 破** | 迁类型后既有 import 失败 | D4 重导出；跑 `scripts/e0_tool_result_lifecycle.py` 冒烟 |
| **残留浅方法** | 若 OQ1 选「保留委托」，`MemoryManager.prune_tool_results` 成转发浅方法 | grill 拍板；若判为不可接受则选删除并迁测试 |
| **churn 掩盖行为变化** | 大范围移动代码易夹带无意修改 | 纯重构纪律：先迁后测，用 diff 逐行核对 + 既有测试全绿 |

**Trade-off**：一次性机械 churn ↔ 关注点单一定位与后续改动局部性。可回滚性高（revert，无数据迁移、无协议变更）。

## Testing Strategy

**测试先行（TDD）**：先补 `ToolResultSpiller` 的直接单测（新文件 `tests/agent/memory/test_tool_result_spiller.py`），再迁实现。

1. **既有测试作为纯重构回归判据（R0，不改语义）**：
   - `tests/agent/memory/test_tool_result_lifecycle.py` —— 13 处 `manager.prune_tool_results` 直调（陈旧被替换 / 当轮保留 / 穿透窗口 / 预览保尾 / `_tokens` 重置 / 无 ref 不谎称 / 幂等 / 残余边界）+ 判定纯函数。
   - `tests/agent/test_tool_result_lifecycle_loop.py` —— `tool_result_spill` 事件 + `trace.steps[].type == "tool_result_spill"` + ref 回读 + resume 历史被剪 + arguments bounded。
2. **新增 `ToolResultSpiller` 直接单测**：
   - `mark` 后 `spill` 剪陈旧、未 `mark` 不剪（保守）；
   - `reset` 预置 `-1`（resume 历史可剪）；
   - `spill` 幂等（预览不被二次剪）；
   - counter 注入：monkeypatch 替换后阈值判定随之变化（**显式覆盖 D2 的头号风险**）；
   - `PruneStats` 数值（`messages_spilled` / `bytes_released`）。
3. **集成/入口层**：跑 `scripts/e0_tool_result_lifecycle.py`（A/B 对照脚本，验证 monkeypatch 目标未破 + 常驻字符量级不变）。
4. **全量回归**：`uv run pytest -q` 全绿。

**不新增**对 `tool_result_policy.py` 的测试（该文件不改）。

## Impact Analysis

- **能力域**: `context-engineering`（只新增结构内聚要求；行为契约不变）。
- **代码（新增/修改/不动）**:
  - **新增** `agent/memory/tool_result_spiller.py`。
  - `agent/memory/manager.py` —— `prune_tool_results` 主体迁出（薄委托见 OQ1）、`PruneStats` 迁出 + 重导出、构造 spiller、`is_oversized_result` 保留。**迁移后须清理失去唯一使用者的死代码/死 import（NF2）**：`_flatten`（`:54-58`，唯一使用点 `:258` 随循环体迁走）、`is_spilled_preview as _is_spilled_preview`（`:12`，唯一使用点 `:243`）、`make_preview as _make_preview`（`:13`，唯一使用点 `:262`）——纯重构应一并清理，避免遗留浅转发与死 import。**保留** `_content_bytes`（仍用于 `_message_bytes:46`）、`_READ_PROGRESS_RE`（仍用于 `_extract_read_progress:644`）、`_exceeds_single_threshold`（仍用于 `is_oversized_result:200`）。
  - `agent/loop.py` —— `mark`（`:898` / `:1092`）、`reset`（`:1559`）、`spill`（`:1616`）调用点；**发射点 `:1646-1658` 不动**。
  - **NF1（loop 剪枝调用点 × e0 patch 目标一致性）**：loop 的剪枝调用 SHALL 落在 `self.memory.prune_tool_results`（保持 `scripts/e0_tool_result_lifecycle.py:110` 的 patch 目标不破）。新 spec Requirement 的 Scenario「调用方（AgentLoop）SHALL 经**该入口**触达工具结果剪枝」中的「该入口」即指此路径——**`MemoryManager.prune_tool_results` 的薄委托（D1/OQ1）也算作「该入口」**，故 spec 字面与 e0 不变可同时成立。若 Q1 改选「删除委托」，则须同步把 e0 的 patch 目标改为 `loop.memory.tool_result_spiller.spill`，否则 `--mode unbounded` 静默失效、A/B 对照失真。
  - **不动**：`agent/memory/tool_result_policy.py`。
- **测试**: 保留两个既有文件（R0）；新增 `tests/agent/memory/test_tool_result_spiller.py`；回归 `agent/memory` 既有压缩测试 + `tests/agent/test_trace_recorder_bounded.py` + 全量。
- **脚本**: `scripts/e0_tool_result_lifecycle.py`（import + monkeypatch 目标兼容性）。
- **文档**:
  - `openspec/specs/context-engineering/spec.md`（受保护路径，归档时随 delta 合入）。
  - `CONTEXT.md`（新词条：`Tool Result Spill` / `ToolResultSpiller`）。
  - `docs/architecture.md`（`MemoryManager` 行职责收敛 + 新增 `ToolResultSpiller` 行）。
  - `docs/openspec-change-backlog.md`（受保护路径）。
  - `README.md` / `README_EN.md`：关键词扫描，预计无影响。
- **流程**: refactor ∈ `DESIGN_TYPES` → grill + 停轮确认 + `reviews/grill-adversarial.md`；实现后 `/review-loop` + manifest。worktree：`tool-result-spill-module/2026-10-07`。
- **不影响**: LLM provider、Web UI、benchmark runner、工具协议、workspace safety、ref 存储形态。

## Open Questions

> 以下为**经 grill（`reviews/grill-design.md`）与设计阶段对抗审阅（`reviews/grill-adversarial.md`）收敛后仍待用户停轮确认**的决策点（停轮确认前不得进入实现）。
> 原 OQ2（所有权）、OQ3（reset 转发）、OQ5（命名）经 grill 与对抗审阅判为**代码可定**、已移出待决队列，见 `reviews/grill-design.md` 的 `## Code-Resolved Questions` 与 `reviews/grill-adversarial.md` 的 `## Code-Resolved（对抗新增/修正）`。

- **OQ1（接口归属）**：`MemoryManager.prune_tool_results` 保留为薄委托还是删除并把 13 处测试调用迁到 `spiller.spill`？（草案倾向保留委托，保 e0 monkeypatch 缝 + 最小 churn）
  - **与 Q2 联立、不可独立拍**：保留委托 ⟺ spiller 由 `MemoryManager` 组合持有（`self.memory.tool_result_spiller`，见 Pre-Implementation Review 的 Q2 段）；只有选「删除」才使「loop 自持 spiller」在逻辑上可行，且此时须同步改 e0 的 patch 目标。二者是同一决策的两个面，不能分别拍板。
- **OQ4（seam 边界）**：账本有界路径本轮不收进 spiller（D6）是否被认可？
