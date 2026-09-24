# Building Review — workflow-budget-unbounded-default

- change: workflow-budget-unbounded-default (issue #196)
- 分支: workflow-budget-unbounded-default/2026-09-17
- reviewer run id: review-workflow-budget-unbounded-default-20260917-r1
- 时间: 2026-09-17
- base: `origin/master` (9f79f10)，head: `0e8f59c`
- 审阅方式: 独立零记忆 subagent；实跑测试 + **变异验证**（改坏 → 变红 → 还原）

## Verdict

**PASS**

审阅报告与 review manifest（`reviews/building-review-manifest.json`，绑定 base `9f79f10` / head `0e8f59c`、tasks/spec/diff/report hash）均已产出，artifact checker 与 openspec strict validate 复跑全绿。

> **收尾注意**：manifest 的 `tasks_hash` 绑定的是**当前** tasks.md（3.1–3.5 仍为 `[ ]`）。收尾阶段勾选这些步骤后 tasks.md 会变，须按仓库既有做法（参照 commit `5203bab`「review manifest 重绑到最终归档态」）在归档前重新生成 manifest，否则 checker 会报 `tasks hash mismatch`。

## 任务逐项验证

| 任务 | 状态 | 证据（文件:行号） |
|------|------|------------------|
| 0.1 grill 产出（≥3 决策 + Open Questions + User Confirmation） | ✅ | `reviews/grill-design.md:10-30`（10 条 Confirmed Decisions）、`:32-44`（Q1/Q2）、`:46-49`（User Confirmation 两条均含实质答复 + 确认时间 2026-09-17，无占位文本） |
| 0.2 grill 结论回写 design.md、D4 从「待拍板」改为结论 | ✅ | `design.md:55-60`（D4 状态「已由用户拍板确认（2026-09-17）：不改 CLI」）、`:62-67`（D7 新增 Decision）、`:87-109`（Pre-Implementation Review 整合 10 条 + 3 条「必须修改」） |
| 1.1 `WorkflowBudgetConfig` 四字段默认值改 0 + docstring | ✅ | `agent/config.py:297-300`（`max_total_tokens: int = 0` / `max_total_cost_usd: float = 0.0` / `max_total_runs: int = 0` / `max_wall_time_s: float = 0.0`）、`:281-296` docstring 更新 |
| 1.2 `_parse_workflow_budget` 四处 `mapping.get` 默认改 0 + docstring | ✅ | `agent/config.py:1546/1551/1556/1561` 四处 `mapping.get(..., 0)`；docstring `:1534-1541` |
| 1.3 `WorkflowBudget.__init__` 四处 `getattr` 兜底改 0 + docstring | ✅ | `agent/subagent/workflow_budget.py:66-72`（四处 `getattr(..., 0)`）+ `:66-68` 注释 |
| 1.4 CLI 不改（用户拍板） | ✅ | `agent/main.py` 无 `--workflow-budget-*`（grep 零命中）；`ConfigOverrides` 仅 3 字段；实现未新增 CLI 面 |
| 1.5 段落级 null 三级收紧为 `ConfigError` | ✅ | `_require_section` 定义 `agent/config.py:1635-1655`；三处调用 `:525-527`（subagents）、`:1502-1504`（workflow）、`:1525-1527`（budget） |
| 2.1 更新断言旧默认值的既有测试 | ✅ | `test_workflow_budget_config.py:31-37/46-51/80-93/96-100`、`test_workflow_budget.py:36-46/107-124`、`test_workflow_replay.py:170-172` |
| 2.2 改写 `test_max_total_runs_default_matches_structural_max_runs`（不删语义） | ✅ | 改名为 `test_budget_default_does_not_disable_c2_structural_max_runs`，`test_workflow_budget_config.py:46-51`：断言 `budget.max_total_runs == 0` **且** `limits.max_runs == 300`——语义覆盖保留（C4 Q14） |
| 2.3 新增回归 + 对照组（grill 构造口径） | ✅ | `test_workflow_budget.py:356-374`（默认下 completed、used > 200_000）+ `:377-388`（同图显式 200k → `budget_exceeded`、`completed < 8`）。**变异验证通过**（见下） |
| 2.4 显式上限 / 显式 0 / null / 负值仍生效 | ✅ | 显式上限：`test_workflow_budget.py:209-222/225-235`；显式 0 不限：`:260-266`、`:65-78`（`test_zero_limit_means_dimension_disabled`）；null/负值拒绝：`test_workflow_budget_config.py:136-151`（未改动，仍绿）+ 新增 `:169-190` |
| 2.5 C2 兜底 + `max_items=0` 展开容量 | ✅ | `test_dynamic_foreach.py:252-277`（新增：预算不限时 `max_items=0` 展开 11 项而非空集）；C2 兜底 `:239-266` 既有用例保持绿。**变异验证通过** |
| 2.6 段落级 null 三级参数化 + 键缺失对照组 | ✅ | `test_workflow_budget_config.py:169-190`（三级 null → `ConfigError`）+ `:193-204`（键缺失 → 正常加载为不限） |
| 3.0 benchmark smoke | ✅ | 实跑 `uv run asterwynd benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/...` exit=0；输出 72 tasks / 5 passed / 29 failed 与 **origin/master baseline 逐值一致**（已跑 baseline worktree 对照，非回归） |
| 3.1 spec 同步 current spec | ⬜ 未做 | 收尾步骤，尚未执行（预期：本 PR 归档前完成） |
| 3.2 文档影响复核 | ⬜ 未做 | 收尾步骤 |
| 3.3 `/review-loop` 审阅闭环 | 🔄 本报告 | 本次审阅即为该步骤；manifest 待生成 |
| 3.4 全量 pytest + openspec validate + artifact checker | 🔄 部分验证 | 本审阅已实跑三项全绿（见「CI 完整性」），但 tasks 3.1/3.2 未完成后需复跑 |
| 3.5 归档 | ⬜ 未做 | 收尾步骤 |

**说明**：tasks.md 中 3.1–3.5 未勾选属正常状态——它们是 closing 阶段步骤，本审阅（3.3）是其中一环。artifact checker 对「tasks 未全勾」的 change 不强制 review manifest，因此当前不受拦截；归档前必须补齐。

## 审阅维度

### 正确性

`_require_section`（`agent/config.py:1635-1655`）三种情况行为经实跑确认：

- **键缺失** → 返回 `{}`，走默认（= 不限）。实测 `subagents:\n  max_spawns: 5` 与空 yaml 均正常加载，budget 四维全 0。
- **键存在但值为 `null`** → `ConfigError`。实测三级各写 `null` 均报错，报错文案 `<path>: <field_name> must not be null` 精确指出出错层级。
- **非 mapping**（如 `subagents: []`、`workflow: 5`、`budget: 5`）→ `ConfigError`，文案与既有 `_expect_mapping` 一致（`must be a mapping`）。

三个调用点覆盖完整：顶层 `subagents`（`agent/config.py:525-527`）、`subagents.workflow`（`:1502-1504`）、`subagents.workflow.budget`（`:1525-1527`）。逐个 grep 确认这是全部 `_require_section` 调用点，无遗漏。

**`subagents.budget.*` 旧路径未被误伤**（审阅重点）：`agent/config.py:1471` 的 `_expect_mapping(mapping.get("budget", {}), path, "subagents.budget")` **保持原样**——那是**单 run 预算**（`max_tokens` / `max_time_s`），与 workflow 四维预算是两个概念。该段落的 `null` 仍走静默 `{}`（实测 `subagents:\n  budget: null` 正常加载），符合 design D7 明确划定的范围边界（`:67`「其它顶层段…不在本 change 范围」）。同理 `aggregation`（`:1503` 之外的 `:1524`）也未收紧，实测 `aggregation: null` 仍正常加载。

**既有合法配置未被打红**：仓库内三份 yaml（`configs/workflow-arm-large-n.yaml`、`configs/workflow-arm-small-k.yaml`、`asterwynd.example.yaml`）实跑 `load_config` 全部 OK，budget 均为 `(0, 0.0, 0, 0.0)`。两份 arm config 的 `subagents:` 键下有实子键（`max_active` / `max_spawns`），不是裸 null 键，不受收紧影响。

### Spec 对齐

spec delta（`specs/multi-agent-collaboration/spec.md:5-50`）与实现逐条对齐：

- 「四维度**默认均为 `0`（不限）**——只有显式配置才设上限」→ `agent/config.py:297-300` + `:1546/1551/1556/1561`。
- 「`0` SHALL 表示该维度不限，但 `max_total_runs=0` SHALL NOT 解除 C2 的 `max_runs` 结构闸」→ 真值判定未变（`workflow_budget.py:112-118` 等），实测 `test_runs_budget_zero_disables_c4_but_keeps_c2_structural_gate` 绿。
- 「段落级 null → `ConfigError`，SHALL NOT 静默视为未配置」→ `_require_section` + 三级调用点，5 个 Scenario 全部有对应测试。
- Scenario「预算不限不解除 C2 结构闸」→ `test_dynamic_foreach.py:252-277` + `test_workflow_budget_config.py:46-51` 双覆盖。

**spec delta 自身无自相矛盾**。一处**精度观察（非缺陷）**：Scenario「未配置预算时不设上限」（`:9-14`）的 WHEN 写「超过**任一**旧默认值（…300 runs…）」，结尾断言「workflow SHALL 正常跑完」。在**默认配置**下 runs 维度不可达此断言——C2 `max_runs=300` 与旧默认等值，越过即走 `graph_recursion_exceeded`（grill 决策 6 已识别并收敛了验收口径到 token 维度）。该 Scenario 在用户显式调大 C2 `max_runs` 时仍可满足，故不构成契约错误；但字面易被后续读者当作全维承诺。建议（非阻塞）在收尾时于该 Scenario 补一句「runs 维度受 C2 结构闸约束，本 Scenario 的『正常跑完』以 token 维度为主」——同 design D5「副作用（需在文档明说）」的口径。

### 冗余度 / 可维护性

- `_require_section` 与 `_expect_mapping` 关系**清晰**：前者是「取子段」语义（键缺失 ≠ null），后者是「校验已是 mapping」语义（None 视为空段）。二者对 non-dict 的拒绝行为一致，但对 `None` 的语义**刻意相反**——这正是 D7 的核心，且 docstring（`:1635-1645`）把这个差异写清楚了。
- **无死代码**：`_require_section` 三个调用点全部活跃。
- **微冗余（非阻塞 nit）**：`_require_section` 的 `if not isinstance(value, dict): raise ConfigError(... must be a mapping)` 与 `_expect_mapping` 重复。可在 null 检查后改为 `return _expect_mapping(value, path, field_name)` 消重（报错文案完全相同）。当前写法更直白、可读性不差，不构成缺陷。
- 注释密度合适：新增注释均陈述**约束与理由**（为什么收紧、为什么两级 null 语义不同），不解释代码本身在做什么。`agent/config.py:281-296` 的 docstring 保留了 C4 的 Q11/Q14 交叉引用并补上新 change 的动机，符合仓库文档纪律。

### 测试覆盖

新增/改动测试**无假保护**（全部经变异验证，见下节）。覆盖矩阵：

- 默认路径（真越过旧上限 + 对照组）：`test_workflow_budget.py:356/377`
- 账本层默认兜底：`test_workflow_budget.py:36-46`（含 `record_llm_call` 千万 token + `exceeded_dimension` 恒 None）
- 快照形状：显式配置全四维（`:107-118`）+ 未配置报 `limit: 0`（`:120-124`）
- 显式上限仍生效：`test_workflow_budget.py:209/225`；显式 0 仍不限：`:260-266`、`:65-78`
- 字段级 null/负值/非数值仍拒：`test_workflow_budget_config.py:136-151`（未改动，回归绿）
- 段落级 null 三级参数化 + 键缺失对照组：`:169-190`、`:193-204`
- C2 兜底（runs 维度）：`test_dynamic_foreach.py:252-277`、`test_workflow_budget.py:250-266`
- benchmark 记录面：`test_workflow_replay.py:170-172`（同时断言 cost 与 tokens）

**未覆盖但不构成缺陷**：runs / wall_time 维度的「默认路径回归」——grill 决策 6 已论证二者在单测中不可构造（runs 被 C2 等值顶掉、wall_time 需伪造时钟），design `Testing Strategy:124` 明确排除，属**有据排除**而非漏测。

### 安全性

- **默认不限确实放大了成本失控面**：design `Risks:113` 如实描述，且 grill 要求的修正已落实——缓解面②已改为条件句「单 run 预算**仅在用户显式配置时**才生效（默认 `None` = 不限）」。核对 `agent/config.py` 的 `default_max_tokens: int | None = None` 属实，该句诚实。
- **真正的兜底存在且已验证**：默认配置下 C2 `max_runs=300` / `max_nodes=200` / `recursion_limit=25` 仍生效（`agent/config.py:1514-1523` 未改动），`test_budget_default_does_not_disable_c2_structural_max_runs` 与 `test_max_items_zero_expands_to_c2_bound_when_budget_unlimited` 双锁。
- **静默烧钱路径已封堵**：D7 收紧的正是「写空段 → 静默四闸全无」这条缝。改动前 `budget: null` 会被静默当 `{}`，默认值改 0 后同一份配置会从「有闸」无声变「无闸」——收紧后变硬错误。这是本 change 安全性上最关键的一笔。
- **死循环风险**：design `Risks:113` 的量级估算（300 runs × 50 万 token ≈ 1.5 亿 token）已核实前提成立（单 run 无迭代上限 + 无 token 兜底），描述诚实。
- **grill 补充的失败出口变化**已记入 design D5 `:75`（runs 触顶由 `budget_exceeded`+drain 变为 C2 `graph_recursion_exceeded`+cancel），与代码路径一致。

### CI 完整性

| 门禁 | 结果 |
|------|------|
| `uv run pytest -q`（全量） | ✅ 2753 passed, 8 skipped |
| 改动面测试（5 文件） | ✅ 110 passed |
| `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` | ✅ 30 passed, 0 failed |
| `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py` | ✅ passed (exit 0) |
| benchmark fake smoke | ✅ exit 0，与 origin/master baseline 逐值一致 |

**回归面扫描（自验，非采信 grill 结论）**：全仓 grep `200000` / `1800` / `max_total_`。除本 change 自身文档与测试外，唯一命中旧默认值的是 `openspec/specs/multi-agent-collaboration/spec.md:190`（current spec，收尾 3.1 待同步）与 `docs/openspec-change-backlog.md:152`（backlog 叙述，收尾 3.5 待移除）。`benchmarks/agent_runner.py:298` 的 `timeout_seconds: int = 1800` 与 `test_factory_sandbox_wiring.py` 的 `decay_interval_seconds=1800` 是**无关概念**（进程超时 / 记忆衰减），非同一默认值。`docs/interview-bullets`、`docs/interview-script` 中的 budget 提及均指**单 run** 预算，不受影响。**grill 的「只剩 spec 与 backlog」结论经独立复核成立。**

`budget_config` 在 replay 比对中是 **report-only**（`benchmarks/workflow_e2e.py:36-40` 的 `REPORT_ONLY_FIELDS`，硬断言集只有 `workflow_spec_hash` + `OBSERVED_FIELDS`），因此历史 `workflow_record.json`（含旧默认 300）**不会**因新默认而 replay 失败——`test_workflow_modes.py:181` 的字面量改成 0 属口径对齐，非兼容性必需。

## Issues

**无阻塞性缺陷。**

非阻塞观察（可供收尾酌情处理，均不影响 verdict）：

1. **spec Scenario 精度**（`specs/multi-agent-collaboration/spec.md:9-14`）：Scenario「未配置预算时不设上限」的 WHEN 含「任一旧默认值」但 THEN 断言「正常跑完」，runs 维度在默认配置下受 C2 `max_runs` 约束不可达该断言。建议补一句口径限定。（低）
2. **微冗余**（`agent/config.py:1648-1654`）：`_require_section` 的 non-dict 分支与 `_expect_mapping` 重复，可委托以消重。当前更直白，可选。（极低）

## 变异验证记录

实际执行的「改坏 → 变红 → 还原」实验（全部还原后 `git status --porcelain` 为空，且与预变异备份逐字节 diff 一致）：

| # | 变异 | 目标 | 结果 |
|---|------|------|------|
| A | `agent/config.py:297` `max_total_tokens: int = 0` → `= 200000` | 检测 2.3 默认路径测试是否假保护 | ✅ **变红**：`test_default_budget_lets_token_heavy_workflow_finish` FAILED（`assert 'budget_exceeded' == 'completed'`）；**对照组 `test_same_graph_exceeds_when_token_budget_explicitly_set` 仍 PASS**——证明默认路径测试真能感知默认值，且对照组独立成立 |
| B | `agent/subagent/workflow_budget.py:69-72` 四处 `getattr` 兜底还原为 `200000/5.0/300/1800` | 检测 D3 兜底是否有测试锁 | ✅ **变红**：`test_defaults_are_unlimited_without_config` FAILED（`200000 == 0`）；`test_dimensions_report_zero_limit_when_unconfigured` 不受影响（该测试走显式 config 路径，符合预期） |
| C | `_require_section` 的 `value is None` 分支改为 `return {}`（即还原改动前的静默语义） | 检测 D7 收紧是否有测试锁 | ✅ **变红**：`test_section_level_null_is_rejected` 三个参数化用例全部 FAILED |
| D | `agent/subagent/scheduler.py:2092-2095` `_remaining_expansion_capacity` 在 `budget.max_runs` 为假值时提前 `return 0`（模拟 grill 标注的「静默空展开」暗雷） | 检测 2.5 的 `max_items=0` 测试是否真保护 | ✅ **变红**：`test_max_items_zero_expands_to_c2_bound_when_budget_unlimited` FAILED（`assert 0 == 11`）；既有 `test_max_items_zero_truncates_to_remaining_run_budget` 仍 PASS——证明新测试精确锁住了「预算不限 ⇒ 仍按 C2 展开」这条路径 |

变异 A 是本审阅的核心要求：**若默认路径测试是假保护（改动前后皆绿），它不会在此变异下变红**。实测变红，假保护风险排除。变异 C、D 分别覆盖本 change 的两条新增行为面（段落级 null 收紧、`max_items=0` 容量退化），均已确认有真测试锁。
