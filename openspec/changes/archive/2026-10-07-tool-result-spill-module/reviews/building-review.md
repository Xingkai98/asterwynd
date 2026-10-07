# Building Review: tool-result-spill-module

- **change**: `tool-result-spill-module`（issue [#300](https://github.com/Xingkai98/asterwynd/issues/300)）
- **repo**: Xingkai98/asterwynd
- **branch**: `tool-result-spill-module/2026-10-07`
- **base_sha**: `97b0370`（master 分支点） · **head_sha**: `2b58f74`
- **reviewer**: 独立零记忆 building 审阅者（/review-loop 闭环）
- **审阅日期**: 2026-10-07

## Verdict

- **PASS**

本 change 是纯结构重构：把有界工具结果生命周期（`tool-result-lifecycle` / #282 已落地）从横跨 `tool_result_policy.py` + `manager.py` + `loop.py` 的浅实现内聚为单一深模块 `ToolResultSpiller`。逐项核对：剪枝循环逐字等价迁移、可观测契约（事件/trace/日志/`PruneStats`/ref）未动、头号风险 D2 counter 缝经「延迟闭包 + 经 manager 触发的回归测试」正确保住、import 方向无环、NF2 死代码清干净。无 MUST-FIX 级问题（仅 1 条 SHOULD-FIX 文档陈旧 + 2 条 NIT），故判 **PASS**。

## Task Verification

### 第 2 节：测试

- **2.1**（新测试 `test_tool_result_spiller.py`）：**通过**。新增 `tests/agent/memory/test_tool_result_spiller.py`（11 条测试，隔离运行 `11 passed`），覆盖 `mark` 后剪陈旧 / 未标记不剪（`test_unmarked_result_is_not_pruned_conservative`）、`reset` 预置 `-1`（`test_reset_presets_history_consumed`）、`spill` 幂等（`test_spill_is_idempotent`）、`PruneStats` 数值（`test_spill_stats_report_counts_and_released_bytes`）、**counter 注入**（`test_counter_injection_via_manager_controls_threshold`，见下 D2 专节）。任务描述逐项命中。
- **2.2**（跨模块行为 `loop → spiller → policy`）：**通过**。既有 `tests/agent/test_tool_result_lifecycle_loop.py` 未作语义修改即全绿（目标集 `178 passed`，该文件含 `tool_result_spill` 事件 + `trace.steps[].type == "tool_result_spill"` + ref 回读 + resume 历史被剪 + arguments bounded 场景），真实路径不变。
- **2.3**（入口层 `scripts/e0_tool_result_lifecycle.py` A/B 冒烟）：**通过**。实跑输出 `[bounded] N=30 常驻文本=303KB` vs `[legacy] N=30 常驻文本=11075KB`——bounded 路径生效、量级与设计一致；`--mode unbounded` 的 monkeypatch 目标已同步（`scripts/e0_tool_result_lifecycle.py:110` 改为 `loop.memory.tool_result_spiller.spill`），未破。
- **2.4**（负向路径与回归）：**通过**。未标记不剪 / 无 ref 不谎称（`test_prune_without_ref_marks_truncated_not_fake_ref`）/ 幂等 / resume 历史被剪 / `_tokens` 重置（`test_prune_resets_token_cache`）均由既有 + 新增测试覆盖，全绿。

### 第 3 节：实现

- **3.1**（新增 spiller 模块）：**通过**。`agent/memory/tool_result_spiller.py` 定义 `ToolResultSpiller`（`mark` `:72` / `reset` `:76` / `spill` `:90`，构造期注入 `max_tokens` / `recent_window` / `counter`）+ `PruneStats`（`:40`）。
- **3.2**（迁循环主体 + 删除 `prune_tool_results` + manager 持有 spiller + `PruneStats` 迁出 + 保留 `is_oversized_result`）：**通过**。全仓 grep `prune_tool_results` 已无代码调用方（仅剩注释引用）；`PruneStats` 唯一定义在 `tool_result_spiller.py:40`，无重导出，e0 import 已改 spiller（`scripts/e0_tool_result_lifecycle.py:108`）；`MemoryManager` 构造持有（`agent/memory/manager.py:136-140`）；`is_oversized_result` 保留（`manager.py:180`，唯一调用方 `agent/loop.py:1579` 的 `_bound_ledger_result`）。
- **3.3**（接入 loop + 同步 e0 patch 目标 + 事件/trace 发射点不动）：**通过**。`mark` 两处（`loop.py:897` / `:1091`）、`reset` 两处（`loop.py:604` / `:725`）、`spill`（`loop.py:1619`）；`_reset_tool_result_iterations` 方法与其 `self._tool_result_iterations` dict 已彻底删除（`grep` 零命中）；发射点 `loop.py:1626-1638`（`record_tool_result_spill` + `on_event("tool_result_spill", ...)`）逐字未动。
- **3.4**（更新文档）：**通过（但 tasks.md 未勾，见 NIT-3）**。`CONTEXT.md` 新增 `Tool Result Spill` / `ToolResultSpiller` 词条、`docs/architecture.md` 收敛 `MemoryManager` 行并新增 `ToolResultSpiller` 行——均已落地；README 关键词扫描（`spill` / `tool.result`）无与本次变更相关的待改段落。
- **3.5 / 3.6**（条件任务：若发现新影响面/调研结论变化则回写）：**通过（空真）**。实现中未发现新影响面，`## Reference Implementation Research` 结论未变，两条件均未触发，未勾选属正确。

### 第 4 节：验证

- **4.1 / 4.2 / 4.3 / 4.4 / 4.6 / 4.7**：**通过**。见「CI 完整性」节。
- **4.5**（baseline CI 本地通过）：**通过（未勾，属收尾勾选）**。三条 baseline 命令已由本审阅者实跑：全量 pytest / openspec strict validate / artifact checker，结论见下。

### 第 5 / 6 节（同步 spec / PR 收尾）

- **5.1 / 6.1–6.6**：**未勾属预期**——change 尚未归档、PR 未发起；`6.6` 已正确标注 `(post-merge)`。归档点由完成度门禁统一校验。

## Issues

- **NIT-1（SHOULD-FIX）**：`agent/memory/tool_result_policy.py:10` 的模块 docstring 仍写「`MemoryManager.prune_tool_results` 判『哪些 messages 该剪』时调用 `exceeds_single_threshold`」——该方法已删除，实际调用方是 `ToolResultSpiller.spill`（`agent/memory/tool_result_spiller.py:135`）。该文件本 change 声明「不改」，故此陈旧引用是本次迁移的副产物。纯文档、不影响行为；建议后续一并订正（或归档时顺手改）。
- **NIT-2（NIT）**：`tests/agent/memory/test_tool_result_lifecycle.py:6` 模块 docstring 仍以 `` `prune_tool_results` `` 命名被测对象——13 处调用已全部迁到 `manager.tool_result_spiller.spill`（`grep -c` = 13，与 design「13 处」一致），docstring 表述略陈旧。建议顺手改成新入口名。
- **NIT-3（NIT）**：`tasks.md` 第 3.4 条文档工作**已实际完成**（`CONTEXT.md` / `docs/architecture.md` 均已改），但仍为未勾状态。属复选框卫生问题，非实现缺失；归档前勾选即可（注意：**本审阅报告定稿后不应再改 `tasks.md`**，否则 review manifest 的 `tasks_hash` 会漂移——见文末 manifest 纪律）。

无 MUST-FIX 级问题。

## D2 counter 缝专项核对（头号风险）

- **spiller 无静态 import `_count_tokens`**：`agent/memory/tool_result_spiller.py` 全文对 `_count_tokens` 仅有 docstring 说明（`:13`），无任何 import 语句——grep 零命中。
- **经 MemoryManager 构造、延迟闭包**：`agent/memory/manager.py:136-140` 以 `counter=lambda text: _count_tokens(text)` 注入；闭包体在**调用时**解析 `manager` 模块全局 `_count_tokens`（`manager.py:53`）⇒ 与今日 `prune_tool_results` / `is_oversized_result`（`manager.py:188`）体内裸引用同源，`monkeypatch.setattr(_manager_mod, "_count_tokens", ...)` 缝保住。
- **测试确经 manager 触发**：`test_counter_injection_via_manager_controls_threshold` 全程走 `manager.tool_result_spiller.spill(...)`（非直接 `ToolResultSpiller(counter=<自建>)` 构造），并显式 `monkeypatch.setattr(_manager_mod, "_count_tokens", lambda text: 10**9)` 断言剪 / `lambda text: 1` 断言不剪——**若 spiller 静态 import 了 `_count_tokens`，此测试必红**，是真正的 D2 回归判据，非假通过。
- 额外确认：`test_is_oversized_result_shares_same_counter_seam` 断言 `is_oversized_result` 与 spiller 受同一 monkeypatch 影响，落实 spec「单一判据来源」。

## F5 防循环 import 专项核对

- spiller import 的是 `policy.flatten_content as _flatten`（`agent/memory/tool_result_spiller.py:30`），**非** `manager._flatten`（原 `manager._flatten` 已删，见 NF2）；`_flatten(message.content)` 调用点 `:141`。
- 依赖方向：`manager → tool_result_spiller → tool_result_policy`——`manager.py:13` import spiller，`policy.py` 不 import manager/spiller（grep 零命中），`agent/message.py` 不 import memory。**无环**。
- 实跑 `import agent.memory.manager` 与 `import agent.memory.tool_result_spiller` 均成功（`ast.parse` + 既有测试导入路径验证）。

## Spec Alignment

spec delta（`openspec/changes/tool-result-spill-module/specs/context-engineering/spec.md`）的 ADDED Requirement「工具结果有界化的单一内聚宿主与单一判据来源」，逐句核对：

| spec 要求 | 满足情况 | 证据 |
|---|---|---|
| 判据与剪枝循环内聚于单一模块、单一对外接口 | ✅ | `tool_result_spiller.py` 三方法（`mark:72` / `reset:76` / `spill:90`） |
| 单入口覆盖「标记消费 / 重置预置 / 执行剪枝并返回统计」 | ✅ | 三方法一一对应 |
| AgentLoop 经该入口触达、SHALL NOT 内联维护迭代状态副本 | ✅ | loop 无 `_tool_result_iterations`（grep 零命中）；经 `self.memory.tool_result_spiller.*` 触达 |
| 阈值判定单一来源：内部剪枝循环与对外单条阈判定共用同一 counter 解析点 + 同一判据纯函数模块 | ✅ | spiller `self._counter` 与 `is_oversized_result`（`manager.py:188`）同一 `manager._count_tokens`；两者均调 `tool_result_policy.exceeds_single_threshold` |
| 替换计数器实现后二者判定一致随之改变 | ✅ | `test_is_oversized_result_shares_same_counter_seam` + `test_counter_injection_via_manager_controls_threshold` |
| SHALL NOT 改变可观测/语义契约（事件、trace、标记、ref、`_tokens` 失效、剪枝结果） | ✅ | 发射点 `loop.py:1626-1638` 未动；既有两测试文件仅改调用目标未改断言；`_tokens=None` 保留（`tool_result_spiller.py:147`）；e0 A/B 量级一致 |
| SHALL NOT 持有事件发射/轨迹记录器 | ✅ | spiller 无 `on_event` / `trace_recorder`，只返回 `PruneStats`（D7） |
| SHALL NOT 并入账本有界化关注点 | ✅ | `_bound_ledger_result` / `_bound_arguments` 原地留 loop（D6）；`is_oversized_result` 仅被账本路径调用（`loop.py:1579`） |

**结论**：spec 每条 Requirement 均满足。

## Correctness（逐字等价核对）

对照 base `97b0370` 的 `manager.py:208-272` 循环体与本 change 的 `spiller.spill`（`:90-155`），逐行差异只有四类、均语义等价：

1. `msgs = messages if messages is not None else self.messages` → 直接 `messages`（positional，非 Optional）——spiller 无 `self.messages`；唯一生产调用方 loop 恒显式传 `messages`，无 `None` 入径（grep 确认无其他调用方）。
2. `counter=_count_tokens` → `counter=self._counter`——注入的延迟闭包，见 D2 专节。
3. `added_iterations.get(...)` → `marks.get(...)`，`marks = self._iterations if added_iterations is None else added_iterations`（`:119`）——**`None` 走自身 `mark` 状态、非 `None` 覆盖注入**，与 design D1「覆盖注入」定义一致，并有 `test_added_iterations_override_uses_external_map` / `test_added_iterations_none_falls_back_to_mark_state` 双向覆盖。
4. `_flatten`（原 manager 的懒包装，内部即 `policy.flatten_content`）→ 直接 `policy.flatten_content`（`:30`）——同一函数。

其余（幂等 `_is_spilled_preview`、`slid_out`/`oversized` 判据、`save` 异常时 `ref=None` 不谎称、`_tokens=None`、`PruneStats` 的 `max(0, before - after)` 计数字节、`logger.info` 文案、frozen dataclass 的 `to_metadata`）均逐字一致。

- `reset` 预置 `-1` 语义保留：`tool_result_spiller.py:84-88` 与 base `loop._reset_tool_result_iterations` 的 `{m.tool_call_id: -1 for m in messages if m.role == "tool" and m.tool_call_id}` 逐字一致。
- **无 `max_tokens`/`recent_window` 事后变更风险**：全仓 grep 无对 `MemoryManager.max_tokens` / `.recent_window` 的 post-construction 赋值（命中的均为无关的 `workflow_budget` / `run` 对象）⇒ spiller 构造期捕获的副本不会与 `is_oversized_result` 的实时读取漂移。
- 新增 `added_iterations=None` 默认值是既有 required 关键字的**超集**，不改变任何既有调用语义。

## Redundancy（NF2 死代码清理）

- `manager.py`：`_flatten`（原 `:54-58`）**已删**、`is_spilled_preview as _is_spilled_preview` 与 `make_preview as _make_preview` 导入**已删**、无用 `Callable` 导入**已删**（`from typing import Literal, Optional, TYPE_CHECKING`）；`prune_tool_results` 整方法删除、无转发浅方法；`PruneStats` 迁出、无重导出。保留的 `_content_bytes`（`:45` 仍用）、`_exceeds_single_threshold`（`:187`）、`_READ_PROGRESS_RE`（`:567`）均仍有唯一使用者。
- `loop.py`：`_tool_result_iterations` dict 与 `_reset_tool_result_iterations` 方法彻底删除（grep 零命中）。
- spiller 无死 import，未引入转发方法。

## Coverage

**新增覆盖**（`test_tool_result_spiller.py`，11 条）：`mark`→剪陈旧 / 未标记不剪 / `reset` 预置 `-1` / `reset` 覆盖既有标记 / 幂等 / `PruneStats` 数值 + `to_metadata` / 无 `save` 不谎称 ref / `added_iterations` 覆盖注入（新鲜不剪 + 陈旧剪）/ `added_iterations=None` 回退 `mark` 状态 / counter 经 manager 注入（D2）/ `is_oversized_result` 共享 counter 缝（R2）。

**既有回归**：`test_tool_result_lifecycle.py` 13 处调用**仅改调用目标**（`manager.prune_tool_results` → `manager.tool_result_spiller.spill`），断言与语义零改；`test_tool_result_lifecycle_loop.py` 未动，覆盖事件 + trace + ref 回读 + resume + arguments bounded 的端到端路径。

**未单独新增**对 `tool_result_policy.py` 的测试——该文件本 change 不改，符合 design 的测试策略。

**覆盖盲区**：无明显遗漏。spiller 的 `spill` 的 `messages=None` 分支被有意移除（非 Optional），无路径需覆盖。

## Security

无新增风险面：不引新依赖 / 新协议，不改权限判定、不改工具协议、不改 ref 存储形态；`save` 回调的异常路径沿用既有 try/except（`tool_result_spiller.py:142-144`）。

## Maintainability

spiller 是窄接口深模块（3 方法 + 1 dataclass），docstring 解释了「为何」——模块级 docstring（`:13-20`）交代 D2 counter 缝与 F5 依赖方向两个坑，`reset` docstring（`:78-82`）交代保留 `-1` 预置语义的原因（resume M2），`spill` docstring 交代判据/覆盖注入/`_tokens=None` 纪律。`logger` 名复用 `"asterwynd.memory"`（`:35`），日志语义不漂移。

## CI 完整性

- **全量 `uv run pytest -q`**：`2 failed, 4110 passed, 9 skipped`（431s）。唯一 2 条失败为 `tests/agent/memory/test_persistent.py::TestFindScopeRoot::{test_returns_none_for_non_git_dir, test_malformed_git_file_falls_back_to_scan}`——**已核实与本 diff 无关**：(a) `agent/memory/persistent.py` 与 `tests/agent/memory/test_persistent.py` 均**不在**本 diff（`git diff --stat` 空）；(b) 在**未改动的 base master `97b0370`**（`/home/happy/my-agent`）上同样 2 条以相同 `AssertionError: assert PosixPath('/tmp') is None` 复现。根因为本机环境 `/tmp` 下存在游离 `.git` 目录（`/tmp/.git` 存在），`_find_scope_root` 向上扫描误判 `/tmp` 为 scope root——本机环境坑，非实现引入。
- **`npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`**：`Totals: 29 passed, 0 failed`（含 `change/tool-result-spill-module` ✓）。
- **`PYTHONPATH=. python3 scripts/check_openspec_artifacts.py`**：`OpenSpec artifact checks passed`（exit 0）。active change 未归档，building-review 门此时不拦截，如实报通过。
- **benchmark smoke**（task 4.6）：本 change 侧 `Tasks: 72 | passed: 5 | unsupported: 38 | failed: 29`，base `97b0370` 侧**逐数相同**（5/38/29）——29 条 `test_failure` 是 `--agent fake`（不解题）的预期结果、38 条 `docker_unavailable` 为环境不支持，均非崩溃、且与 base 等价，纯重构未改变 benchmark 行为。

## 结论

全部审阅维度通过，无 MUST-FIX。判 **PASS**。列出的 NIT-1（SHOULD-FIX）为文档陈旧、NIT-2/NIT-3 为措辞/勾选卫生，均不阻断合入，建议在归档收尾时一并处理。
