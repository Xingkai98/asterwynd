# Building Review: workflow-limit-visibility (#275)

- reviewer: 独立零记忆 subagent（与实现方无共享上下文）
- 时间: 2026-10-01
- base: `origin/master`（`af81217` 为 HEAD）
- 审阅对象: `git diff origin/master...HEAD`、`openspec/changes/workflow-limit-visibility/{proposal,design,tasks,specs/}`、`reviews/grill-design.md`、`research/*.py`

## Verdict

**CHANGES_REQUESTED**

核心功能（撞闸图 `headroom < 0`、无条件 `diagnostics`、route `gate_count`、唯一数据源）**实现正确且被真锁测试覆盖**——4 次手动变异全部被测试变红捕获。但报告在**自动插层撞闸**这一条已实现且已测的路径上，对模型可见的口径**自相矛盾**：`expanded_nodes` 与其 `notes` 声明的算术关系、以及 spec delta 的一条 Scenario 等式，在 `max_nodes=3`/`2`（自动插层即超限）时**不成立**。这是本 change 自己要消灭的「模型误读面」的一个新实例，需修复或明确限定后再合入（不阻塞整体，见 Issue 1）。

## Tasks Verification

逐条核对 `tasks.md` 的每个 `[x]`，均确认实现真实存在：

| task | 断言内容 | 实现位置 | 结论 |
|---|---|---|---|
| 1.1 | proposal 含 Change Type/Why/…/RIR/Impact/Non-Goals | `proposal.md:7-141` 各节齐备 | ✓ |
| 1.2 | design.md 含全部要求节 | `design.md:1-189`（Context/Goals/Risks/Testing/Pre-Impl Review/Impact） | ✓ |
| 1.3 | spec delta MODIFIED 2 条 | `specs/multi-agent-collaboration/spec.md:5,156` | ✓ |
| 1.4 | 三个侦察脚本落 `research/` | `research/gap_probe.py`、`gate_trip_probe.py`、`node_budget_probe.py`（实测输出见 `## Test Results`） | ✓ |
| 1.5 | RIR findings + design impact | `proposal.md:87-104`（RQ1–RQ5 + design impact） | ✓ |
| 1.6 | backlog 入队 + 结构化事件 | `docs/openspec-change-backlog.md:111-117`；`openspec/changes/…/workflow-events.jsonl`（`backlog_updated` seq 1） | ✓ |
| 2.1 | grill 产出 `reviews/grill-design.md` | 该文件存在，含 Confirmed Decisions/Open Questions/风险/结论 | ✓ |
| 2.2 | 停轮抛 Open Questions | `grill-design.md:17-33`（Q1–Q6，每条配实测例子） | ✓ |
| 2.3 | 用户答复写回 `## User Confirmation` | `grill-design.md:35-42`（Q1–Q6 逐条 `确认时间: 2026-10-01`，无占位文本） | ✓ |
| 2.4 | 按实测订正回写 design/proposal/spec delta（D2/D3/D4/D6/L0） | `design.md:56-132,170-188`（D2 改口径、D3 恒 0、D4 无条件、D6 调用级锁）；`proposal.md:49-52,74-81`；`spec.md:39,41` | ✓ |
| 3.1 | 先写失败测试（limits/node_budget/route/diagnostics） | `tests/agent/subagent/test_workflow_limit_visibility.py`（25 项，四组） | ✓ |
| 3.2 | `_build_dry_run_report` 增 `limits`（复用 `_limits_report`） | `agent/tools/builtin/subagents.py:1661,1683` | ✓ |
| 3.3 | scheduler 增投影记录（判定**前**、只增字段） | `agent/subagent/scheduler.py:2180-2186` | ✓ |
| 3.4 | `node_budget`（graph_nodes/expanded/auto_inserted/limit/headroom） | `subagents.py:1668-1675` | ✓ |
| 3.5 | route 增 `max_routes` + `gate_count`（同源 `_route_counts`） | `subagents.py:1585-1586` | ✓ |
| 3.6 | `diagnostics` 无条件挂载 | `subagents.py:1688` | ✓ |
| 3.7 | notes 补 4 段口径说明 | `subagents.py:1796-1818` | ✓ |
| 3.8 | `DeclareWorkflow` 描述补图级三闸模块默认值句 | `subagents.py:786-789` | ✓ |
| 3.9 | 扩展 `test_workflow_tool_discoverability.py`（宽松匹配 + 长度守卫） | `tests/agent/subagent/test_workflow_tool_discoverability.py:318-336` | ✓ |
| 3.10 | 调用级同源锁（哨兵） | `test_workflow_limit_visibility.py:306,328,345`（3 个哨兵测试） | ✓ |
| 3.11 | scheduler 侧：投影 == 图节点 + Σitems；判定逐字不变 | `test_workflow_limit_visibility.py:373,393` | ✓ |
| 3.12 | 既有 dry run 测试不失效 | `tests/agent/subagent/test_workflow_dry_run.py` 42 passed | ✓ |
| 4.2 | 全量 pytest | 实跑见 `## Test Results` | ✓ |
| 4.4 | benchmark smoke 与 pristine 逐项相同 | 未独立复跑（见 Issue 3，证据在 tasks.md 自述） | ⚠ |

未勾任务（4.1/4.3/5.1–5.8）均为**未到位阶段**，与分支纪律一致，非缺陷：4.1（`/review-loop`）即本报告；4.3（真实 LLM 验收）、5.x（同步 spec / 归档 / PR）属收尾阶段。无 `(post-merge)` 未勾项在归档前被误判的风险（尚未归档）。

## Issues

### Issue 1（MEDIUM，口径自洽 / 模型误读面）— 自动插层撞闸图上 `expanded_nodes` 与 `graph_nodes` 的算术在**模型可见输出**中不自洽

**证据**：`subagents.py:1803-1810` 的 notes 声明

> `graph_nodes` = the execution graph's size (declared nodes plus system-inserted merge layers, counting a foreach as ONE), `expanded_nodes` = the billing size the gate actually counts (**graph nodes PLUS each foreach item**)

但实测（`max_nodes=3`、20 项 foreach、本 worktree 复现）：

```
max_nodes=  3 status=graph_recursion_exceeded declared=2 graph=2 expanded=24 auto=0 limit=3 headroom=-21 diag_reason=max_nodes
```

按 notes 的算术 `expanded = graph_nodes + Σitems` = `2 + 20` = **22**，而报告实报 **24**。差额 2 是「**被闸门拒绝、从未落地**」的自动汇合层数（`_expand_plan` 在 `self._plan = expanded` 之前 raise，故 `plan.nodes` 停在声明值 2，`auto_inserted` 也为 0）。同样地，spec delta 的

- `Scenario: 报告暴露自动插层与 foreach 展开造成的计费放大`（`spec.md:116-123`）无条件声明「`expanded_nodes` SHALL 等于 `graph_nodes` 加该图所有 foreach 节点的展开项数之和」

在自动插层撞闸图上**不成立**（该路径正是 `test_workflow_limit_visibility.py:233-247` 显式测试的路径）。两条 Scenario 在这一点上口径冲突：Scenario「撞闸图上节点预算不报正余量」要求 `expanded` 含**被拒展开**，而「计费放大」Scenario 的等式假定 `graph_nodes` 含**已落地**自动层——两者在自动插层撞闸时不可兼得。

**影响**：模型在撞闸报告里读到 `graph_nodes=2 / items_expanded=20 / expanded_nodes=24`，按 notes 算得 22≠24，无法判断哪个数权威——正是本 change 要消灭的「新增误读面」（proposal 的 L3 负面检查项）。核心信号（`headroom=-21 < 0`、`expanded>limit`）仍正确，故不是阻塞缺陷，但属需修复的中等口径问题。

**建议**（任一即可）：
1. notes 与 spec delta 补限定：`graph_nodes`/`auto_inserted` 反映**当前已落地**的执行计划，`expanded_nodes` 反映**展开完成后**的计费投影；在闸门于自动插层处拒绝的图上，二者基线不同，`expanded ≠ graph_nodes + Σitems`（或直接点明差额为「被拒的自动层数」）；或
2. 在 `_expand_plan` 的记录里同时记「投影图规模」，使报告可选择报一个与 `expanded_nodes` 同基线的 `graph_nodes`。

### Issue 2（LOW，测试锁强度 / D6 纪律一致性）— route `gate_count` 缺少调用级同源锁

**证据**：D6 与 spec delta（`spec.md:36`）要求 route 计数「SHALL 与调度器据以判定 `max_routes` 超限的计数同源，SHALL NOT 用另一个口径的计数」。实现正确（`subagents.py:1586` 读 `scheduler._route_counts`），但**测试只用值断言**（`test_workflow_limit_visibility.py:253,265` 断言 `gate_count==1` / `>1`），未像 `limits`/`expanded_nodes`/`limit` 那样加**哨兵锁**（`:306,328,345`）。D6 与 grill R2 明确点名「调用级同源锁（非值相等）」是防假保护的纪律；`gate_count` 未纳入。

**影响**：本次变异（把 `gate_count` 改成 `(count or 1)+100`）被值断言捕获，但若将来在报告层以另一口径重算且恰好在被覆盖的图上同值，可逃逸。**建议**：补一个 monkeypatch 哨兵锁（如断言 `gate_count` 反映被替换的 `_route_counts` 值），与同文件其余三处同源锁一致。非阻塞。

### Issue 3（LOW，证据核对）— benchmark smoke 结论未附可独立复核的原始输出

**证据**：`tasks.md:39`（4.4）声称 `Tasks: 72 | passed: 5 | ... | failed: 29` 且与 pristine 逐项相同，但该断言仅存在于自述，未附原始日志/差异。本 change **未**触及 benchmark 路径（改动仅 `scheduler.py` 投影字段 + `subagents.py` 报告/描述），PR 描述体风险低。**建议**：如收尾阶段仍要保留该结论，附上原始命令输出或对比摘要。非阻塞。

## Test Results

全部为**本 reviewer 实跑结果**（PATH 含 `/home/happy/.local/bin`，`.venv` 已 `uv sync --extra dev`）：

| 命令 | 结果 |
|---|---|
| `uv run pytest tests/agent/subagent/test_workflow_limit_visibility.py -v` | **25 passed** in 3.08s |
| `uv run pytest tests/agent/subagent/ -q` | **822 passed** in 38.61s |
| `uv run pytest -q`（全量） | **2 failed, 3855 passed, 9 skipped** in 441.83s |
| 关键三文件合跑 | **112 passed** |

**全量 2 失败均为环境噪声（pre-existing，非本 change）**：`tests/agent/memory/test_persistent.py::TestFindScopeRoot::{test_returns_none_for_non_git_dir, test_malformed_git_file_falls_back_to_scan}`——本机 `/tmp` 是 git 仓库导致 `_find_scope_root` 返回 `/tmp`。与改动文件无关（本 change 未触及 `agent/memory/`）。**无其它大批失败**。

### 变异验证（关键，均手动改坏实现后确认变红，再还原；`git status` 已确认为 clean）

| # | 变异 | 被捕获 | 捕获测试 |
|---|---|---|---|
| 1 | `expanded_nodes = scheduler._projected_expanded_nodes` → `len(plan.nodes)` | **7 failed** | 含两个撞闸回归 `…tripped_graph[5]/[23]`、`…auto_insert_layer[2]/[3]`，及哨兵锁 `…gate_projection_field` |
| 2 | `diagnostics` 无条件挂载 → 仅非空时挂载 | **1 failed** | `test_diagnostics_is_mounted_unconditionally_even_when_empty` |
| 3 | `gate_count` 取自 `_route_counts` → 报告层伪造值 | **1 failed** | `test_route_entry_exposes_max_routes_and_gate_count` |
| 4 | `limits = scheduler._limits_report()` → 报告层重算 | **1 failed** | `test_limits_are_read_from_the_shared_reporter_not_recomputed` |

✓ **同源锁是真锁**（哨兵 monkeypatch 证明「确实调用了」，非「值恰好相等」）。✓ **撞闸图回归存在**。

### 独立复跑探针（与实现同源，未调真实 LLM）

`uv run python openspec/changes/workflow-limit-visibility/research/node_budget_probe.py` 输出钉死了 D2 的核心事实——两个既有计数在**撞闸图**上都报**正**余量：

| 场景 | run_status | `len(plan.nodes)` | `_expanded_nodes` | 真值（闸门口径） |
|---|---|---|---|---|
| 20 项 / `max_nodes=200` | completed_with_failures | 4（余 196） | 24（余 176） | 24 |
| 20 项 / `max_nodes=5` | **graph_recursion_exceeded** | 4（**余 1**） | 4（**余 1**） | 24 |
| 20 项 / `max_nodes=23` | **graph_recursion_exceeded** | 4（**余 19**） | 4（**余 19**） | 24 |

即：若照 design 原稿（或 grill 推荐的 `_expanded_nodes`）实现，一张**已撞闸**的图会报 `headroom: 1` / `19`（正数）。D2 的「闸门投影字段」取向是唯一能消除该假面的口径。本 reviewer 另写探针覆盖 `max_nodes ∈ {200,24,23,5,4,3,2}`，**所有撞闸例 `headroom` 均为负**（含 `_expand_plan` 自动插层撞闸路径），`max_runs` 撞闸例正确显示 node 余量为正且 `reason=max_runs`（未把动态闸误报为 node 余量）。

## 安全性

无新增信息泄露面（可接受）：新增的 `diagnostics`（`subagents.py:1688`）取 `dict(scheduler._diagnostics)`，其内容（`reason`/`limit`/`steps`/`current_nodes`/`truncation_diagnostics`/`route_ref_misses`）与模型经由 `RunWorkflow` 的 `parent_envelope`（`scheduler.py:3130`）**已经能看到**的完全一致，且 dry run 本就以同形挂载。未扩大暴露面到模型不该看的数据。`diagnostics` 未按 `_clip_text` 截断，但它是结构化小对象（`current_nodes` 与 `report["nodes"]` 的 id 列表重复），与既有出口同形，非新增无界文本通道。

## 冗余度

报告层**未重算**任何闸值（D6 满足）：`limits ← scheduler._limits_report()`（`subagents.py:1661`，与 `status()`/`_envelope` 同一方法）、`expanded_nodes ← scheduler._projected_expanded_nodes`（闸门记录，`:1666`）、`limit ← scheduler._eff_limit("max_nodes")`（`:1667`）、`gate_count ← scheduler._route_counts`（`:1586`）、`auto_inserted/graph_nodes ← ExecutionPlan 字段`（`:1662,1672`）。哨兵锁（变异 1/3/4 均变红）提供了机械证据。唯一「新增计算」是 `headroom = limit - expanded_nodes`，这是纯派生展示量（非闸值），符合设计。

## 可维护性

命名与注释一致、贴合模块既有风格：`_projected_expanded_nodes` 的语义、与 `_expanded_nodes` 的区别、两个记录位点（`scheduler.py:2120-2127`、`:2180-2186`）都有内联注释说明「只增只读、取历史最大、不参与判定」。字段名 `gate_count`（而非 `used`）正确消解了与既有 `runs:0` 的表观矛盾，`notes` 有对应说明句。惰性/中文注释风格与仓库一致。

## CI 完整性

**未弱化任何 CI 配置或既有测试**：`git diff --name-status` 中无 `.github/**`、无 `pyproject.toml`、无 `conftest.py`；`test_workflow_tool_discoverability.py` 仅为**新增**测试函数（无删除、无放宽既有断言），`test_workflow_dry_run.py` 零改动且 42 项全过。

## 结论

- **核心正确性成立**：D2 的「闸门投影」口径是本 change 的关键，实测证明它能在全部撞闸路径上报出**负** headroom（消除假正余量）；唯一数据源、无条件 diagnostics、字段名规避矛盾均如实落地。
- **测试是真锁**：4 次手动变异全部被变红捕获，同源锁用哨兵而非值相等。
- **需修复的中等问题一处（Issue 1）**：自动插层撞闸图上，模型可见的 `notes` 算术（`expanded = graph_nodes + Σitems`）与 spec delta 一条 Scenario 等式不成立，构成新的误读面——需在 notes/spec delta 限定基线，或调整该路径下 `graph_nodes` 的口径。不阻塞整体功能。
- **两处 LOW（Issue 2/3）**：`gate_count` 缺哨兵锁（D6 纪律未全覆盖）；benchmark smoke 结论缺可复核原始输出。
- **环境噪声已排除**：全量仅 2 失败，均为 `/tmp/.git` 导致的 `TestFindScopeRoot` pre-existing 失败。

**判定：CHANGES_REQUESTED**——修复 Issue 1（并建议顺带补 Issue 2 的哨兵锁）后可再审至 PASS。
