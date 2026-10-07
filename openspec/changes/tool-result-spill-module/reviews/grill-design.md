# Grill Design Review: tool-result-spill-module

> 独立零记忆设计追问者产出。基线 master @ 97b0370（worktree 分支 `tool-result-spill-module/2026-10-07`）。
> 本文所有行号以该基线为准，均经亲自读源码核验。**指出的事实错误/遗漏见 `## Findings`。**
> 本记录只审设计，不写实现；停轮确认由主 session 依 `## Open Questions` 执行。

## Confirmed Decisions

- **决策**：**D2 counter 单一注入点方案成立**——`lambda text: _count_tokens(text)` 逐字等价于今日语义。今日 `is_oversized_result`（`manager.py:201`）与 `prune_tool_results`（`manager.py:250`）都在方法体内裸引用模块全局 `_count_tokens`（`manager.py:62`），是 call-time 解析；闭包体内引用 `manager` 命名空间全局，亦在调用时解析，二者同源。**实测反证**：静态导入后 `monkeypatch.setattr(mod, "_count_tokens", repl)` 不生效（仍返旧值），延迟闭包则跟随替换值。无默认参数绑定（`lambda text, _c=_count_tokens: ...`）那种固化陷阱。
- **决策**：**D3 迭代状态归 spiller 所有成立**——`_tool_result_iterations`（`loop.py:206`）除剪枝外无其他读者：唯一消费点是 `loop.py:1643` 传给 `prune_tool_results(added_iterations=...)`，两处写入（`loop.py:898`/`:1092`）与重置（`loop.py:1573`）都在 loop 内且不导出。迁入 spiller 不破任何外部面。
- **决策**：**D4 `PruneStats` 迁出 + `manager` 重导出不破既有 import 且无循环 import（附一前提）**——`PruneStats` 唯一定义在 `manager.py:92-103`，仓库内唯一外部 import 是 `scripts/e0_tool_result_lifecycle.py:108`；`manager` 重导出即兼容。依赖方向为 `manager → spiller → policy`，`spiller` 不反向 import `manager`，故无环——**前提是 spiller 用 `policy.flatten_content` 而非 `manager._flatten`**（见 Finding 5）。
- **决策**：**D5 `is_oversized_result` 保留成立**——其唯一调用方是 `loop.py:1600` 的 `_bound_ledger_result`（账本路径），确非剪枝循环；保留在 `MemoryManager` 并以 D2 的同一解析点共享 counter，符合既有「traffic through the manager so there is one counter」原则。
- **决策**：**D7 事件/trace 发射留 loop 成立**——可观测契约钉在 `loop.py:1646-1658`（`record_tool_result_spill` + `on_event("tool_result_spill", ...)`），无测试要求 spiller 持有 `on_event`/`trace_recorder`；`spill` 只产 `PruneStats` 即可满足 `tests/agent/test_tool_result_lifecycle_loop.py:329-346` 的断言。
- **决策**：**D8 纯重构等价的可机械判据成立**——既有两测试文件（`test_tool_result_lifecycle.py` + `test_tool_result_lifecycle_loop.py`）确实覆盖事件名/payload（`:342-345`）、trace step（`:346`）、ref 无损回读（`:186-198`）、resume 历史被剪（`:252-279`）、`_tokens` 失效（`:200-212`）、幂等（`:242-254`），足以作为「行为逐字不变」的回归基线。

## Code-Resolved Questions

- **Q（原 OQ3，reset 转发）**：`loop._reset_tool_result_iterations` 保留薄转发还是两处调用点直接调 `spiller.reset`？
  - 结论：**行为完全等价，二者任选；无任何外部 seam 约束**，可按 OQ/最小转发自由定（推荐直接调，少一层转发）。
  - 证据：全仓无 tests/scripts patch 或引用 `_reset_tool_result_iterations`（`grep` 仅命中 `agent/loop.py` 的 `:604` 注释 / `:605` / `:726` / `:1559` 定义）；两处调用点都在 loop 内部。删除 loop 转发不破任何测试或脚本。
- **Q（原 OQ5，命名）**：`tool_result_spiller.py` / `ToolResultSpiller` / `mark`/`reset`/`spill` 是否符合 `CONTEXT.md` 词汇？
  - 结论：**命名已被 `CONTEXT.md`（词汇权威）锁定，OQ5 无需用户再裁决**——立项 commit `54a775e` 已把 `Tool Result Spill`（`CONTEXT.md:103`）与 `ToolResultSpiller`（`CONTEXT.md:107-108`，含模块路径与三类操作）写入。保持与 `CONTEXT.md` 一致即为正确；`tool_result_policy.py` 同族风格亦印证。
  - 证据：`CONTEXT.md:103-108`；`git log -- CONTEXT.md` 显示条目由 `54a775e` 引入。
- **Q（D2 是否真「单一来源」）**：D5 说「counter 与 spiller 共享同一解析点」，会不会变成两处各一份？
  - 结论：**只要 spiller 由 `MemoryManager` 构造并注入指向 `manager._count_tokens` 的闭包，即真单一来源**。**附硬条件**：R2/D2 的验收单测（`test_tool_result_spiller.py`）若直接 `ToolResultSpiller(counter=<自建函数>)` 构造，测的是测试自己的闭包、**不覆盖生产注入点**——该用例必须经 `MemoryManager`（如 `manager.tool_result_spiller` 或 `manager.prune_tool_results`）触发，否则「monkeypatch 后阈值随之变化」是假通过。
  - 证据：`manager.py:201`/`:250` 裸全局引用；`tests/agent/memory/test_tool_result_lifecycle.py:42` 与 `tests/agent/test_tool_result_lifecycle_loop.py:40` 的 `monkeypatch.setattr(_manager_mod, "_count_tokens", ...)` 只替换 `manager` 全局。
- **Q（e0 monkeypatch 缝在什么条件下才保住）**：OQ1「保留委托即保住 e0 缝」是否充分？
  - 结论：**不充分**。e0 在 `scripts/e0_tool_result_lifecycle.py:110` patch 的是 `loop.memory.prune_tool_results`；patch 生效的**必要条件**是 loop 运行时**确实经该属性**发起剪枝。若重构后 loop 改调 `self.memory.tool_result_spiller.spill(...)` 或 loop 自持 `self._spiller.spill(...)`（D3 的示例正是 `self._spiller`），该 patch **静默 no-op（不报错）**，`--mode unbounded` 不再关闭剪枝 ⇒ 真 A/B 失真。故选「保留委托」时，loop 的剪枝调用必须落在 `self.memory.prune_tool_results`（而非直调 spiller）；或改 e0 的 patch 目标为 spiller。
  - 证据：`scripts/e0_tool_result_lifecycle.py:110`；`agent/loop.py:1640`（今日唯一生产调用点）。
- **Q（迁移后 `save` 前的 flatten 从哪来）**：剪枝循环体的 `ref = save(_flatten(message.content))`（`manager.py:258`）依赖 manager 私有 `_flatten`（`manager.py:54-58`）。
  - 结论：**spiller 必须改 import `agent.memory.tool_result_policy.flatten_content`（`tool_result_policy.py:140` 已导出），不得 import `manager._flatten`**，否则构成 `manager ↔ spiller` 循环 import，D4 的「无环」结论被推翻。
  - 证据：`agent/memory/manager.py:54`（`_flatten` 定义）、`:258`（唯一使用）；`agent/memory/tool_result_policy.py:140`（`flatten_content`）。
- **Q（`spill` 签名与 `added_iterations`）**：D1 给的 `spill(messages, *, current_iteration, save=None)` 是否完整？
  - 结论：**不完整**。既有 `tests/agent/memory/test_tool_result_lifecycle.py` 的 **13 处直调**（`:144/162/180/192/207/219/233/245/249/261/275/288/304`）**每一处都显式传 `added_iterations=`**，且 R0 要求「不作语义修改即全绿」。故保留委托时 `MemoryManager.prune_tool_results` 必须**保留 `added_iterations` 形参**并把它注入 spiller 的标记状态——「薄委托 = `return self.tool_result_spiller.spill(...)`」这条 D1/OC1 的字面描述**不成立**。注意不能用 `reset(messages)` 顶替：`test_prune_skips_fresh_unconsumed_result`（`:140-150`）传 `added_iterations={"c1":3}, current_iteration=3`（=3 未过 `current-1`，**不剪**），而 `reset` 会把 c1 预置 `-1`（**剪**）⇒ 语义相反、测试失败。这是 Q1 待用户拍板的核心张力（接口是否扩张）。
  - 证据：13 处 `added_iterations=` 全部命中；`manager.py:208-215` 签名；`loop.py:1573` 的 `-1` 预置语义。
- **Q（设计事实 6 的 PruneStats 引用面）**：design 称「loop（`from agent.memory.manager import ...`）与 e0 都从 manager 引用 `PruneStats`」。
  - 结论：**设计事实 6 有误**——`agent/loop.py` 全文**不含** `PruneStats`（`grep` 零命中）；唯一外部引用者是 e0。重导出仍需保留（为 e0），但「loop 也依赖」不成立。
  - 证据：`grep -n "PruneStats" agent/loop.py` 无输出；`agent/loop.py:39-47` 的 import 块无 PruneStats。
- **Q（剪枝循环规模/位置）**：design 称 `manager.py:208-272`、65 行。
  - 结论：**属实**（`prune_tool_results` 定义在 `:208`，`return` 在 `:272`，区间恰好 65 行）。
  - 证据：`agent/memory/manager.py:208` / `:272`。
- **Q（spec delta 合规与冲突）**：新增 Requirement 的 SHALL 首行是否合规、是否与既有 spec 冲突/重复？
  - 结论：**合规且无冲突**。首行含 `SHALL`（`spec.md` delta 第 7 行）；`openspec validate --all --strict` 29/29 通过。既有 `openspec/specs/context-engineering/spec.md` 的 `### Requirement: 工具结果全文的单受管持有与释放`（`:153`）讲**行为**（池有界、ref 可回读），新 Requirement「单一内聚宿主与单一判据来源」讲**结构**（模块内聚、单一入口），正交不重复、不冲突。
  - 证据：`npx @fission-ai/openspec@1.4.1 validate --all --strict` → 29 passed；`openspec/specs/context-engineering/spec.md:153`。

## Open Questions

> 以下 3 条为真正的用户取舍（架构/范围），代码无法判定，停轮交用户拍板。已用带 `文件:行号` 的代码证据把选项后果钉死，供快速决断。

- **Q1**（design OQ1，接口归属 + `added_iterations` 注入）：`MemoryManager.prune_tool_results` 保留为**薄委托**还是**删除**并把 13 处测试调用迁到 `spiller.spill`？
  - 场景：既有 13 个用例（如 `test_prune_replaces_stale_result_with_preview_and_ref`）形如 `manager.prune_tool_results(messages, current_iteration=4, added_iterations={"c1":3}, save=save)`。**保留委托**要求该入口原样接受 `added_iterations` 并注入 spiller（即 spiller 需一个「外部标记灌入」通道：给 `spill` 加 `added_iterations` 形参，或加一个非公开 seed 方法）——这与 D1「对外仅 mark/reset/spill、不暴露内部 dict」有张力；**删除委托**则接口最干净，但须改 13 处测试 + 改 e0 的 patch 目标（`scripts/e0_tool_result_lifecycle.py:110`），削弱「不动既有两个测试文件」的 R0 纯重构姿态。
  - 为何代码判不了：两种形态都能让测试通过，取舍在「接口纯净 vs churn/回归姿态」，是设计偏好而非事实。
- **Q2**（design OQ2，所有权）：spiller 由 `MemoryManager` **组合持有**（`self.memory.tool_result_spiller`）还是由 `AgentLoop` **直接构造持有**（`self._spiller`）？
  - 场景：D3 的调用示例写的是 `self._spiller.mark(...)`（暗示 loop 持有），而 OQ2 草案倾向 `MemoryManager` 组合持有——设计内部两处表述冲突。若 loop 自持，loop 需自带 `max_tokens`/`recent_window` 与指向 `manager._count_tokens` 的延迟闭包（loop 已 `from agent.memory.manager import MemoryManager`，可行但把 D2 的「同一来源」复制到 loop）；若 manager 组合持有，D2 的单一来源天然成立。
  - 为何代码判不了：两者皆可运行且都能满足 D2，属架构归属偏好。
- **Q4**（design OQ4，seam 边界）：账本有界路径（`_bound_ledger_result` / `_bound_arguments`）**本轮不收进** spiller 的边界是否被认可？
  - 场景：`_bound_ledger_result`（`loop.py:1593-1603`）把**可观测账本**（trace/tool_calls_made）超阈结果换成无 ref 预览（无消费者按 ref 回读）；`spill` 把**会话消息**换成「预览 + 可回读 ref」。二者只共享 policy 的单条阈判定。若认可 D6，则本轮只迁 `prune_tool_results`，账本路径原地不动（改动面更小、可回滚）；若不认可，则本 change 范围扩张、需处理两种有界化目标的合并设计。
  - 为何代码判不了：这是范围边界决策（本 change 做什么/不做什么），非可判定事实；D6 的理由（目标不同）本身有代码支撑。

## Findings

- **F1（事实错误，计数）**：design/proposal/backlog 反复称 `prune_tool_results` 有 **「14 处」** 直调。**实为 13 处**（`test_tool_result_lifecycle.py` 第 6 行是 docstring 提及，不算调用）；真实调用点 13 个：`:144/162/180/192/207/219/233/245/249/261/275/288/304`。建议统一改为 13，避免后续 review/manifest 计数错位。
- **F2（事实错误，引用面）**：design「已核验的机制事实」第 6 条称 `PruneStats` 由 **loop** 与 e0 都从 manager 引用。**loop 从不引用 PruneStats**（`agent/loop.py` 零命中），唯一外部 import 是 `scripts/e0_tool_result_lifecycle.py:108`。重导出结论仍对，但依据描述失实。
- **F3（设计缺口，接口签名不完整）**：D1 的 `spill(messages, *, current_iteration, save=None)` 未涵盖既有测试强制的 `added_iterations` 通道（13 处全传）。「薄委托 = `return spiller.spill(...)`」不成立，委托必须把外部 `added_iterations` 注入 spiller 状态，且**不可**用 `reset` 顶替（语义相反，见 Code-Resolved）。这直接决定 Q1 的选项形态，是本次追问的头号发现。
- **F4（设计缺口，e0 缝的充分条件）**：OQ1 说「保留委托 ⇒ 不破 e0 monkeypatch」**只是必要不充分**。只有 loop 运行时真的经 `MemoryManager.prune_tool_results` 发起剪枝，`scripts/e0_tool_result_lifecycle.py:110` 的 patch 才生效；若 loop 改调 spiller（manager 或 self 持），patch 静默 no-op、`--mode unbounded` 失真。design 未点明这一充分条件。
- **F5（循环 import 风险，未记录）**：迁移循环体后 `save(_flatten(message.content))`（`manager.py:258`）依赖 manager 私有 `_flatten`（`manager.py:54`）。spiller 若 import `manager._flatten` 将构成 `manager ↔ spiller` 环，推翻 D4「无环」。正解：spiller import `policy.flatten_content`（`tool_result_policy.py:140`）。design 未提此迁移细节。
- **F6（内部不一致）**：D3（`design.md:79-80`）写 `self._spiller.mark(...)` / `self._spiller.reset(...)`（暗示 loop 持有 spiller），而 OQ2 草案（`design.md:115`）倾向 `MemoryManager` 组合持有。两处对「谁持有 spiller」的表述冲突，须在 Q2 一并收敛。
- **F7（可观测契约的盲点）**：D8 主张「日志文案逐字不变」。剪枝的 `logger` 是 `logging.getLogger("asterwynd.memory")`（`manager.py:21`），消息 `"[Memory] spilled %d tool result(s), released %d bytes"`（`manager.py:268-271`）与 `"[Memory] tool result spill failed"`（`:260`）。迁入新模块若换 logger 名（如 `asterwynd.memory.spiller`），logger **名**漂移；无测试断言日志（`grep` 全仓无 `[Memory]`/`spilled` 断言），故测试抓不到。若坚持 D8 字面成立，spiller 应复用同一 logger 名或明确「logger 名不属可观测契约」。
- **F8（Impact Analysis 遗漏面，轻）**：(a) `docs/interview-script/`（`Q02-agent-loop.md`、`Q11-error-type.md`、`W01-agent-loop.md`）提及工具结果/spill，Impact Analysis 未列（属 AGENTS.md「建议性维护约束」，非门禁）；(b) web 测试 `tests/web_tests/test_tool_result_expand.py`、`test_transcript_js.py`、`test_transcript_view_browser.py` 与 `is_spilled_preview` 同口径，未列入显式回归清单（全量 pytest 会覆盖，但不该只在「全量」里兜底）。二者均因 `tool_result_policy.py` 不改而实质无影响，建议在 Impact Analysis 补一句「同口径引用面经全量回归覆盖」。
- **F9（RIR 事实偏弱）**：proposal `## Reference Implementation Research` finding 2 称「本工作区 `.dev/reference-repos.txt` 不存在（已核验），故不做参考仓库对比」。**文件确实不存在（已复核）**，但**参考仓库本体实际可用**：`/home/shared/agent-study/reference-repos/` 存在 6 个库，其中 `codex/codex-rs/hooks/src/output_spill.rs` 定义 `HookOutputSpiller`——「超预算文本全文落盘 + 换 head/tail 预览 + 给出回读路径」，与本 change 的 spill 关注点**同族**，本可作为 light 档对比依据。RIR 结论「不可用」不准确（不构成 exempt 理由，但 finding 应更新为「`.dev` 配置缺失，改用本地参考仓库 codex `HookOutputSpiller` 佐证」）。

## User Confirmation

> 停轮确认后由主 session 逐条回填。格式：`- **Q<n>**: 用户答复：<实质内容>；确认时间: <date>`。

- **Q1**: 用户答复：待确认；确认时间: —
- **Q2**: 用户答复：待确认；确认时间: —
- **Q4**: 用户答复：待确认；确认时间: —
