# Building Review: workflow 图级 recursion_limit 默认值调大（25 → 100）

- **Change**: `workflow-recursion-limit-default`（issue #262）
- **审阅范围**: `git diff ef60ed8009bce0602231461c103317571ac4b483...HEAD`（base=origin/master 合并基点，head=`3d3c996`）
- **审阅方式**: 独立零记忆审阅者（Round 1）；逐条读代码核实、独立跑探针实测标定、独立重算 base 版 `spec_hash`
- **审阅时间**: 2026-09-29

---

## Verdict

**CHANGES_REQUESTED**

实现代码本身**完整、正确、已实测验证**：四处默认值全部为 100、无第五处、三路径一致、核心回归**非恒真**（探针独立复现），spec 同步未丢 #246 诊断句，测试与门禁全绿。但存在一个会**硬阻塞归档门禁**的中等问题（`tasks.md` 实现类任务 1.1–2.6 全未勾，且工作区有未提交修复），外加两条 low 级文档/注释口径问题。修完即可转 PASS——改动量很小。

> **注意审阅目标状态漂移**：本审阅针对 `HEAD=3d3c996`。审阅过程中发现工作区出现**未提交**修改（`tests/agent/subagent/test_recursion_limit_default.py`，mtime 15:10 > HEAD 提交时间）。该修改修复了本报告 Issue 3 指出的问题，但**尚未提交**，故 `HEAD` 版本仍带该问题。详见 Issues 与「审阅目标状态」。

---

## Tasks Verification

### 实现类任务（第 1、2 节）—— 全部真实落实 ✅

| 任务 | 状态 | 证据（`文件:行号`） |
|---|---|---|
| 1.1 `WorkflowLimitsConfig.recursion_limit` 默认值 100 + docstring | ✅ 真实实现 | `agent/config.py:341`（`recursion_limit: int = 100`）；docstring `agent/config.py:337-339` 写明「25 调到 100 + 结构后盾定位」 |
| 1.2 `_parse_workflow_limits` 的 `mapping.get` 默认 100 | ✅ 真实实现 | `agent/config.py:1663`（`mapping.get("recursion_limit", 100)`）；`_validate_positive_int` 调用未变（`agent/config.py:1662-1666`） |
| 1.3 `_spec_bounds` 的 `getattr` 兜底 100 | ✅ 真实实现 | `agent/tools/builtin/subagents.py:435`（`getattr(limits, "recursion_limit", 100)`） |
| 1.4 `DEFAULT_RECURSION_LIMIT = 100` + 模块 docstring | ✅ 真实实现 | `agent/subagent/workflow.py:39`（常量）；`agent/subagent/workflow.py:13-16`（docstring 同步，并注明 `to_dict()` 哨兵语义） |
| 1.5 核实「无第五处」 | ✅ 已核实 | 全仓 grep（排除 tests/archive）无第五处默认值字面量；`agent/subagent/scheduler.py:2005,2937` 的「25」确为 `_dispatch_capacity() = max_active + max_queued_runs` 并发容量；`web/static/workflow_graph.js` 只读运行时 `diagnostics` |
| 2.1 更新默认值断言 25 → 100 | ✅ 真实实现 | `tests/agent/subagent/test_workflow_tools.py:235`（`== 100`） |
| 2.2 三路径一致性断言 | ✅ 真实实现 | `tests/agent/subagent/test_workflow_tools.py:240-262`（直构 `:252` / yaml `:255` / getattr 兜底 `:260` / 常量同源 `:262`） |
| 2.3 核心回归 + 对照组（**非恒真**） | ✅ 真实实现且经独立探针验证 | 主组 `tests/agent/subagent/test_recursion_limit_default.py:94-107`；对照组 `:111-127`。见下方「探针实测」 |
| 2.4 spec 级回归（两条 Scenario） | ✅ 真实实现 | `tests/agent/subagent/test_recursion_limit_default.py:132-139`（默认不掐断）、`:142-165`（显式 7 精确生效，走真实 `load_config` + `parse_spec_for_manager`） |
| 2.5 序列化面（锁 D3） | ✅ 真实实现 | `tests/agent/subagent/test_workflow_spec.py:340-368`（未声明键省略 + 指纹钉 `9cee33da95470fbc`；显式 25 开始序列化；显式 100 反向） |
| 2.6 兼容回归保持绿 | ✅ 已验证 | `tests/agent/subagent/` 710 passed（含 `test_scheduler.py` / `test_terminal_honesty.py` / `test_workflow_asset_limits.py` 等） |

### 收尾类任务（第 3 节）—— 在途，非缺陷（如实记录）

- 3.0（benchmark smoke）、3.1（spec 同步）、3.2（文档影响）、3.3（本审阅闭环）、3.4（全量验证）、3.5（归档）——`tasks.md` 均 `[ ]` 未勾。
- **3.1 实际已完成**（current spec 已同步，见 `openspec/specs/multi-agent-collaboration/spec.md:125` + `workflow-events.jsonl` 的 `current_spec_synced` 事件），但复选框未勾。
- 3.6 已正确标注 `(post-merge)`（`tasks.md:39`）。
- 依据审阅口径，第 3 节未完成属正常在途状态，**不计为缺陷**。

### ⚠️ 实现类任务复选框状态（见 Issue 1）

`tasks.md:13-29` 的 1.1–2.6 **全部为 `[ ]` 未勾**，但对应代码/测试**均已真实存在**。这是 tasks.md 未回填实现进度，非实现缺失；但会让归档点的完成度门禁判红。

---

## Issues

### Issue 1 — `tasks.md` 实现类任务 1.1–2.6 全未勾，将阻塞归档门禁 — **medium**

**证据**：`openspec/changes/workflow-recursion-limit-default/tasks.md:13-29`（1.1–2.6 均为 `- [ ]`），而上述 Tasks Verification 表已逐条证明对应实现存在（如 `agent/config.py:341`、`agent/subagent/workflow.py:39`）。

**影响**：按仓库规则，归档点 `check_openspec_artifacts.py` 对未勾任务（无 `(post-merge)` 标记）报错。1.1–2.6 是**纯实现类**任务（无 `(post-merge)` 豁免），归档时若仍未勾会**硬失败**。

**建议**：把 1.1–2.6 逐个勾上（3.6 保持 `(post-merge)` 未勾）。

---

### Issue 2 — 工作区有未提交修改；审阅对象 `HEAD` 与工作区不一致 — **medium（流程）**

**证据**：`git status --porcelain` → ` M tests/agent/subagent/test_recursion_limit_default.py`；该文件 mtime `15:10` 晚于 `HEAD`（`3d3c996`，14:49）。

**影响**：本次审阅的 diff（到 `HEAD`）**不含**该修复；PR 前必须提交，否则 PR 内容与审阅基线不符，且 Issue 3 在 `HEAD` 上仍然成立。

**建议**：提交该修改后再发 PR；若后续还有改动，需重新确认 diff 基线。

---

### Issue 3 — `HEAD` 版测试 `test_declared_above_config_is_not_raised` 名实不符（工作区已修，未提交）— **low**

**证据（`HEAD` 版）**：`tests/agent/subagent/test_recursion_limit_default.py`（HEAD）中 `test_declared_above_config_is_not_raised` 用 `_raw_loop_spec()` 构造 spec——而该 spec **未声明** `recursion_limit`（已核实：`_raw_loop_spec()` 不含该键），故断言 `spec.recursion_limit == 7` 实际测的是「**未声明 → 取配置值**」路径，而非其名称/docstring 声称的「声明高于配置 → 不抬高」。

**影响**：`low`。断言本身**恒真于错误路径**，未覆盖其声称的方向；不构成安全/正确性问题，但属测试覆盖虚化。

**现状**：工作区**已修复**——重命名为 `test_declared_above_config_is_kept_at_parse_but_clamped_at_read`，显式声明 `recursion_limit=500`，断言「解析保留 500」+「`_eff_limit` 钳到 7」两段（`tests/agent/subagent/test_recursion_limit_default.py:168-191`）。修复正确且两段断言缺一不可，切中要害。**待提交**（见 Issue 2）。

---

### Issue 4 — 生产注释仍写「peer-review 一轮约 1.9 superstep」（量纲错误，design 已订正）— **low**

**证据**：`agent/subagent/patterns.py:238`：

```
#: - ``rounds``：计数键，落到 route 的 ``max_routes``。**不做静态上界**（与图级
#:   ``recursion_limit`` 的换算比依赖模板拓扑——peer-review 一轮约 1.9 superstep）；
```

**影响**：`low`。这正是 grill 标为 **high** 的量纲错误（design `## Testing Strategy` 与 `design.md:149` 已订正为「**3 superstep/轮**」；「1.9」实为 **run/轮**）。本 change 恰以该换算比为核心，且已同步 `agent/subagent/workflow.py:13` 的 docstring，却漏了同主题的 `patterns.py:238`，形成「同一仓内两个换算比对不上」。

**备注**：该行**不在本 change diff 内**（`git diff ... -- agent/subagent/patterns.py` 无输出），属 pre-existing，不归本 change 引入，故记 low 而非 medium。

**建议**：顺手订正为「约 3 superstep/轮」，或记为债务单独立项。

---

### Issue 5 — 编译期 `max_rounds` 接受域随常量隐含放宽（25→100），change 文档未记录 — **low**

**证据（探针实测）**：

```
max_rounds=  26 -> COMPILES, gate.max_routes=26     (改前被拒)
max_rounds=  50 -> COMPILES, gate.max_routes=50     (改前被拒)
max_rounds= 100 -> COMPILES, gate.max_routes=100    (改前被拒)
max_rounds= 101 -> REJECTED: ... exceeds recursion_limit
```

`agent/subagent/patterns.py:332` 的 guards 绑定 `DEFAULT_RECURSION_LIMIT`，故该常量改 100 后，`compile_pattern` 对 `max_rounds` 的接受域由 `≤25` 变为 `≤100`。

**影响**：`low`。这是「只改默认值」之外的一处**可观察行为变化**（`max_rounds∈[26,100]` 从编译期拒绝变为接受），方向与 change 目标一致（属收益），且新测试 docstring（`tests/agent/subagent/test_recursion_limit_default.py:26`）提及该编译期约束，但 change 的 `Impact Analysis` / `Non-Goals` **未列此项**。已核实 spec delta 中「SHALL NOT 因 `max_rounds` 大于图级上限而在编译期拒绝」的语义未被破坏（该句本就要求不静态拒绝，今更宽松）。

**建议**：在 `proposal.md` 的 Impact Analysis 补一句「编译期 `max_rounds` 接受域随之由 25 放宽到 100（绑定同一常量，自动跟随）」。

---

### 其余维度——无问题

- **正确性**：四处默认值均为 100，无遗漏第五处，无语义分叉（三路径测试锁定）。见「探针实测」。
- **Spec 对齐**：delta 四条 Scenario 全部落在 current spec（`openspec/specs/multi-agent-collaboration/spec.md:127,134,142,149`）；`gre` 核实 `declared_max_rounds` 计数 = 3（诊断句完整保留），`默认 25` 零命中，`默认 100` 命中 `:125,:136`；delta 与 current spec 的 Requirement 段落 `diff` 逐字一致。**#246 诊断句未被 sync 覆盖删除 ✅**（`workflow-events.jsonl` 的 `current_spec_synced` 事件已说明手工合并原因）。
- **冗余度**：四处字面量重复为**已知且用户已拍板（Q1）接受**的取舍，本 change 不引入新重复。测试无重复实现。
- **安全性**：无注入/越权/信息泄露面（纯数值默认值调整）。
- **可维护性**：`agent/config.py:337-339` 与 `agent/subagent/workflow.py:13-16` docstring 均已同步口径、明确「结构后盾而非成本软闸」定位，并注明 `to_dict()` 哨兵副作用。除 Issue 4 外无其他漂移。
- **CI 完整性**：本 change diff **不含任何 CI 配置文件**（`.github/` 等），未弱化 CI。

---

## 探针实测（独立复现，非照抄 design/tasks 估算）

审阅者用 `/tmp/probe_recursion.py` 独立跑 `peer-review` 拓扑（`compile_pattern` + `AlwaysCritiqueLLM`，route 常回 producer），核实换算关系：

| N（`max_rounds`） | 默认 limit=100 下 reason | steps | 显式 limit=25 下 reason | steps |
|---|---|---|---|---|
| 7 | `max_routes` | 23 | `max_routes` | 23 |
| 8 | `max_routes` | 26 | **`recursion_limit`** | 25 |
| 12 | **`max_routes`** | **38** | **`recursion_limit`** | 25 |
| 32 | `max_routes` | 98 | — | — |
| 33 | **`recursion_limit`** | 100 | — | — |

**结论**：
1. **`superstep = 3N + 2` 成立**（N=12 → 38；N=32 → 98；N=33 → 100）。docstring 公式与 design「3 superstep/轮」**实测吻合**。
2. **`N=12` 严格落在 (25,100) 内**（38），两侧余量充足；且 12 ≤ 25 满足改前改后的编译期界。
3. **对照组真能触发**：N=8 起显式 limit=25 即 `reason == "recursion_limit"`；N=12 对照组稳定触发，`steps=25 < 38`。**核心回归非恒真 ✅**。
4. `N=33` 在默认 100 下撞 `recursion_limit`（`steps=100`），印证上界 ~32 的推导。

**base 版 `spec_hash` 独立重算**：用 base commit 的 `agent/subagent/workflow.py` 逐字执行 `parse_workflow_spec(_spec())` → `spec_hash = 9cee33da95470fbc`，与 `tests/agent/subagent/test_workflow_spec.py:349` 钉的冻结字面量**逐字相同**，证实「未声明键的 spec 指纹改前改后不变」这一 D3 主张成立。

**钳制方向核验**：`parse_spec_for_manager` 对声明值 `recursion_limit=500` 解析结果为 500（**解析不改写**），钳制发生在 `_eff_limit` 读取处取 `min(declared, ceiling)`——与 spec delta「显式值精确生效 + min 钳制」一致；工作区新测试 `:168-191` 两段断言正确覆盖该路径。

---

## Test Results

### `uv run pytest tests/agent/subagent/ -q -p no:randomly`

```
710 passed in 43.15s
```

### `uv run pytest -q -p no:randomly`（全量）

```
FAILED tests/agent/browser/test_service.py::TestBrowserServiceTabIdGeneration::test_generate_tab_id_is_4_chars
FAILED tests/agent/memory/test_persistent.py::TestFindScopeRoot::test_returns_none_for_non_git_dir
FAILED tests/agent/memory/test_persistent.py::TestFindScopeRoot::test_malformed_git_file_falls_back_to_scan
3 failed, 3474 passed, 9 skipped, 80 warnings in 401.91s (0:06:41)
```

**3 条失败均与本 change 无关，已逐条定位**：
- 两条 `test_persistent.py`：**环境性**——`/tmp/.git` 存在导致 `_find_scope_root` 上溯到 `/tmp`，`assert PosixPath('/tmp') is None` 失败（`/tmp/.git` 实测存在，mtime Sep 21）。已知问题。
- 一条 `test_service.py`：**偶发**——单独重跑 2 次均 `1 passed`（`2.38s` / `0.80s`），与既有 flake 口径一致（本 change 未触及 browser 面）。

### 门禁

```
npx --yes @fission-ai/openspec@1.4.1 validate --all --strict
  → Totals: 29 passed, 0 failed (29 items)

uv run python scripts/check_openspec_artifacts.py
  → OpenSpec artifact checks passed
```

---

## Open Questions / Blockers

无阻塞性疑问。以下为供主 session 决策的非阻塞项：

1. **Issue 4（`patterns.py:238` 换算比注释）**：本 change 顺手订正，或记债务单立项？（审阅者倾向顺手订正——改动一行，且本 change 主题正是该换算比。）
2. **Issue 5（编译期接受域放宽）**：补进 Impact Analysis，或视为「收益方向」不记？（审阅者倾向补一句，保持 Impact Analysis 完整。）

---

## 结论

**实现层：PASS 级**——四处默认值调 100 完整正确、无第五处、三路径一致，核心回归**非恒真**（探针独立实测 `superstep=3N+2`，N=12 → 38 落在 (25,100)，对照组稳定撞 `recursion_limit`），spec 同步**未丢 #246 诊断句**（`declared_max_rounds` 计数 3、`默认 25` 零命中、delta 与 current 段落逐字一致），既有机制（superstep 口径 / `GraphRecursionError` / `_eff_limit` min 方向 / `max_nodes`/`max_runs` 默认值）零改动，测试与门禁全绿，无安全面、无 CI 弱化。

**流程/文档层：需修复后再归档**——`tasks.md` 1.1–2.6 未勾（Issue 1，归档门禁会硬失败）、工作区未提交修改（Issue 2）、`patterns.py:238` 量纲注释（Issue 4）、编译期接受域未记录（Issue 5）。

综合判 **CHANGES_REQUESTED**：四项均为小改动，完成并提交后即可转 PASS。
