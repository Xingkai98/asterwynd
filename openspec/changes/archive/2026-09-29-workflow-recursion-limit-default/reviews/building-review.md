# Building Review: workflow 图级 recursion_limit 默认值调大（25 → 100）

- **Change**: `workflow-recursion-limit-default`（issue #262）
- **审阅范围**: `git diff ef60ed8009bce0602231461c103317571ac4b483...HEAD`（base=origin/master 合并基点，head=`f51a8ec`）
- **审阅方式**: 独立零记忆审阅者（**Round 2**，Round 1 判 CHANGES_REQUESTED 后复审）；逐条读代码核实、独立跑探针实测标定、独立重算 `spec_hash`、独立跑门禁
- **审阅时间**: 2026-09-29

---

## Verdict

**PASS**

Round 1 的 5 项问题（Issue 1–5）**逐条确认已修好**，且修复质量经独立探针复验（非仅凭自述）。实现层与 Round 1 结论一致：四处默认值全部为 100、无第五处、三路径一致、核心回归**非恒真**（探针独立复现 `superstep = 3N + 2`，N=12 → 38 严格落在 (25,100)）、spec 同步未丢 #246 诊断句；测试与门禁全绿（`check_openspec_artifacts.py` 的唯一报错是**预期在途**的 review manifest 缺失，非缺陷）。工作区 `git status --porcelain` 为空，审阅目标无漂移。残留仅 1 条 low/nit 级文档陈旧（`tasks.md:3` 状态行仍写「尚未进入实现」），不影响归档门禁、不阻塞 PASS。

---

## Tasks Verification

### 实现类任务（第 1、2 节）—— 全部真实落实且已回填 ✅

| 任务 | 勾选 | 状态 | 证据（`文件:行号`） |
|---|---|---|---|
| 1.1 `WorkflowLimitsConfig.recursion_limit` 默认 100 + docstring | `[x]` | ✅ 真实实现 | `agent/config.py:341`（`recursion_limit: int = 100`）；docstring `agent/config.py:333-340` 写明「25 调到 100 + 结构后盾定位」 |
| 1.2 `_parse_workflow_limits` 的 `mapping.get` 默认 100 | `[x]` | ✅ 真实实现 | `agent/config.py:1663`（`mapping.get("recursion_limit", 100)`）；`_validate_positive_int` 调用未变（`agent/config.py:1662-1666`） |
| 1.3 `_spec_bounds` 的 `getattr` 兜底 100 | `[x]` | ✅ 真实实现 | `agent/tools/builtin/subagents.py:435`（`getattr(limits, "recursion_limit", 100)`） |
| 1.4 `DEFAULT_RECURSION_LIMIT = 100` + 模块 docstring | `[x]` | ✅ 真实实现 | `agent/subagent/workflow.py:39`（常量，含哨兵语义注释 `:38`）；docstring `agent/subagent/workflow.py:13-16` |
| 1.5 核实「无第五处」 | `[x]` | ✅ 已核实（本轮独立复查） | 全仓 grep 无第五处默认值字面量；`agent/subagent/scheduler.py:2005,2937` 的「25」确为 `_dispatch_capacity() = max_active + max_queued_runs`；`_FANOUT_CAP` 与 `max_nodes`/`max_runs` 均未受影响 |
| 2.1 更新默认值断言 25 → 100 | `[x]` | ✅ 真实实现 | `tests/agent/subagent/test_workflow_tools.py:235`（`== 100`） |
| 2.2 三路径一致性断言 | `[x]` | ✅ 真实实现 | `tests/agent/subagent/test_workflow_tools.py:240-262`（直构 `:252` / yaml `:255` / getattr 兜底 `:260` / 常量同源 `:262`） |
| 2.3 核心回归 + 对照组（**非恒真**） | `[x]` | ✅ 真实实现且经独立探针复验 | 主组 `tests/agent/subagent/test_recursion_limit_default.py:94-107`；对照组 `:111-127`。见下方「探针实测」 |
| 2.4 spec 级回归（两条 Scenario） | `[x]` | ✅ 真实实现 | `:132-139`（默认不掐断）、`:142-165`（显式 7 精确生效，走真实 `load_config` + `parse_spec_for_manager`） |
| 2.5 序列化面（锁 D3） | `[x]` | ✅ 真实实现且冻结值经独立重算 | `tests/agent/subagent/test_workflow_spec.py:340-368`（未声明键省略 + 指纹钉 `9cee33da95470fbc`；显式 25 开始序列化；显式 100 反向）。指纹见「探针实测」 |
| 2.6 兼容回归保持绿 | `[x]` | ✅ 已验证 | `tests/agent/subagent/` 710 passed（含 `test_scheduler.py` / `test_terminal_honesty.py` / `test_workflow_asset_limits.py` 等） |

### 第 4 节（Round 1 修复）

| 任务 | 勾选 | 状态 | 证据 |
|---|---|---|---|
| 4.1 勾上实现类 + 收尾任务 | `[x]` | ✅ 已完成 | `tasks.md` 24 个 `[x]`；仅剩 3.5（归档，`[ ]`）与 3.6（`[ ]`，已带 `(post-merge)`，`tasks.md:39`） |
| 4.2 提交并修正 Issue 3 测试 | `[x]` | ✅ 已完成 | 见「Round 1 修复验证」第 3 条 |
| 4.3 订正 `patterns.py` 量纲注释 | `[x]` | ✅ 已完成 | `agent/subagent/patterns.py:237-240` |
| 4.4 `proposal.md` 记录编译期接受域 | `[x]` | ✅ 已完成 | `proposal.md:41` |
| 4.5 重跑验证并再审 | `[x]` | ✅ 已完成（本轮即为 Round 2） | 见 Test Results |

### 收尾类任务（第 3 节）—— 在途，非缺陷（如实记录）

- 3.0–3.4 已 `[x]`（3.1 spec 同步实测已生效：`openspec/specs/multi-agent-collaboration/spec.md:125` + `workflow-events.jsonl` 的 `current_spec_synced` 事件）。
- 3.5（归档）保持 `[ ]`——**归档在本审阅 PASS 后的收尾步骤执行**，符合预期在途状态。
- 3.6 已正确标注 `(post-merge)`（`tasks.md:39`），归档点豁免。

---

## Round 1 修复验证

### Issue 1（medium，`tasks.md` 实现类任务全未勾，会阻塞归档门禁）— ✅ **已修好**

**验证**：`grep -c "^- \[x\]"` = 24，`grep -c "^- \[ \]"` = 2，未勾的仅 `tasks.md:38`（3.5 归档）与 `:39`（3.6，带 `(post-merge)`）。实现类 1.1–2.6 与已完成收尾 3.0–3.4 全部 `[x]`。

**归档点门禁复核**：未勾行 3.6 带括号标记 `(post-merge)`（`tasks.md:39`，全角括号，容忍编号在前），按仓库规则被豁免；3.5 归档自身在归档动作时结构上无法「已勾」——归档点评估的是**归档目录**，其时 3.5 必然处于未勾（正是该动作本身），规则约定归档点不因 tasks 未全勾而降级，故 3.5 未勾不构成门禁失败。**无标记的未勾任务为 0** ⇒ Issue 1 已解除。

### Issue 2（medium，工作区未提交修改，审阅基线漂移）— ✅ **已修好**

**验证**：`git status --porcelain` 输出为空；`git log` 显示修复已作为 `f51a8ec`（"提交 review R1-Issue3 的测试修复"）落在 HEAD 上。审阅目标 = committed HEAD（`f51a8ec`），无漂移。

### Issue 3（low，`test_declared_above_config_is_not_raised` 名实不符）— ✅ **已修好，且新版本真的在测它声称的东西**

**验证**（不只看改名，独立跑探针 `/tmp/probe_eff.py` 复现两段断言）：

新测试 `tests/agent/subagent/test_recursion_limit_default.py:168-191`，显式声明 `recursion_limit=500`（`:178` 的 `{**_raw_loop_spec(), "recursion_limit": 500}`），两段断言：

- **解析保留声明值**（`:184`，`assert spec.recursion_limit == 500`）——探针独立复现：`parse_spec_for_manager(manager, raw)` 对声明 500 返回 **500** ✅
- **读取处钳到配置值**（`:191`，`assert scheduler._eff_limit("recursion_limit") == 7`）——探针独立复现：`_eff_limit("recursion_limit")` 返回 **7** ✅

**关键点核实**：`_eff_limit`（`agent/subagent/scheduler.py:601-615`）读 `self._spec` 并经 `@spec.setter`（`:625`）写入，测试的 `scheduler.spec = spec` 走真实 setter，非绕过。该测试现在**确实**覆盖「声明高于配置 → 解析不改写 + 生效值取 min」路径，与名称/docstring 一致；对照组路径（未声明 → 取配置值）另有 `test_explicit_smaller_recursion_limit_still_applies`（`:142-165`）独立覆盖，无重复、无虚化。

### Issue 4（low，`patterns.py` 量纲注释）— ✅ **已修好**

**验证**：`agent/subagent/patterns.py:237-240` 现为「peer-review 一轮约 **3 superstep**（producer + reviewer + gate），实测 `superstep = 3N + 2`；「≈1.9」是 **run/轮**口径，量纲不同勿混用」。量纲已正确区分（superstep/轮 3.00 与 run/轮 1.9 两个口径），与 design / `workflow.py:13-16` 口径统一。探针实测 `3*12+2 = 38` 与注释公式逐字吻合。

### Issue 5（low，编译期接受域放宽未记录）— ✅ **已修好**

**验证**：`proposal.md:41` 的 `## What Changes` 新增「**附带效果（自动跟随，非额外改动）**：`compile_pattern` 对模板 `max_rounds` 的编译期接受域绑定同一常量（`patterns.py` 的 rounds 荒谬界 `> DEFAULT_RECURSION_LIMIT`），故由 `≤ 25` 放宽到 `≤ 100`（`max_rounds∈[26,100]` 从编译期拒绝变为接受，`101` 仍拒）」。探针独立实测边界：`max_rounds` 25/26/100 编译通过、**101 被拒**（`agent/subagent/patterns.py:334-338`），与文档陈述一致。

---

## Issues

### Issue 6 — `tasks.md` 顶部状态行陈旧（仍写「尚未进入实现」）— **low（nit，不阻塞）**

**证据**：`openspec/changes/workflow-recursion-limit-default/tasks.md:3`：

```
> 状态：设计阶段（proposal + design + spec delta + tasks + grill）。**尚未进入实现**。
```

**影响**：`low`。实现已完成且 tasks 已勾 24 项，状态行却仍声明「尚未进入实现」，与文件其余部分自相矛盾。不触发任何门禁（artifact checker 不读状态行），不影响归档，故不阻塞 PASS。

**建议**：顺手改为「状态：实现完成待归档」或直接删除该行。

### 其余维度——无问题

- **正确性**：四处默认值均为 100、无第五处、无语义分叉（三路径测试 + 本轮独立 grep 复查）。见「探针实测」。
- **Spec 对齐**：`grep -c declared_max_rounds openspec/specs/multi-agent-collaboration/spec.md` = **3**（#246 诊断句完整保留）；`grep -n "默认 25"` = **零命中**（exit 1）；`默认 100` 命中 `:125`；delta 与 current spec 的 Requirement 段落逐字一致。**#246 诊断句未被 sync 覆盖删除 ✅**（`workflow-events.jsonl` 的 `current_spec_synced` 事件已说明「手工合并（delta 写于 #246 合入前，原样 sync 会删掉诊断句）」）。
- **冗余度**：四处字面量重复为**已知且用户已拍板（grill Q1）接受**的取舍，本 change 不引入新重复；新增测试无重复实现。
- **测试覆盖**：核心回归**含对照组，非恒真**；序列化面三支（未声明 / 显式 25 / 显式 100）齐全；三路径一致性有独立断言。
- **安全性**：无注入/越权/信息泄露面（纯数值默认值调整）。
- **可维护性**：`agent/config.py:333-340`、`agent/subagent/workflow.py:13-16`、`agent/subagent/patterns.py:237-240` 口径已统一；除 Issue 6 外无漂移。
- **CI 完整性**：本 change diff 不含任何 CI 配置文件（`.github/` 等），未弱化 CI。

---

## 探针实测（独立复现，非照抄 design/tasks 估算）

审阅者独立跑 `peer-review` 拓扑（`compile_pattern` + `AlwaysCritiqueLLM`，route 常回 producer），复现换算关系：

| N（`max_rounds`） | 默认 limit=100 下 reason | steps | 显式 limit=25 下 reason | steps |
|---|---|---|---|---|
| 7 | `max_routes` | 23 | `max_routes` | 23 |
| 8 | `max_routes` | 26 | **`recursion_limit`** | 25 |
| 12 | **`max_routes`** | **38** | **`recursion_limit`** | 25 |

**结论**：
1. **`superstep = 3N + 2` 成立**（N=12 → 38，与 `CALIBRATED_SUPERSTEPS = 3*12+2 = 38` 逐字吻合）。
2. **N=12 严格落在 (25,100) 内**（38），两侧余量充足；且 12 ≤ 25 满足改前改后的编译期界。
3. **对照组真能触发**：N=8 起显式 limit=25 即 `reason == "recursion_limit"`；N=12 对照组稳定触发，`steps=25 < 38`。**核心回归非恒真 ✅**。N=7 两栏均 `max_routes`（docstring 自称的下界 N≥8 亦属实）。

**冻结 `spec_hash` 独立重算**：`/tmp/probe_hash.py` 独立执行 `parse_workflow_spec(_spec())`：

```
undeclared to_dict has key: False
undeclared hash: 9cee33da95470fbc == literal? True
declared25  to_dict key: 25  hash: e440ec25fd907f3a
declared100 has key: False  hash: 9cee33da95470fbc
```

- 未声明 → 键省略、指纹 = **`9cee33da95470fbc`**，与 `test_workflow_spec.py` 钉的冻结字面量**逐字相同** ✅
- 显式 25 → 键**开始序列化**（25）、指纹变化 ✅
- 显式 100 → 键被省略、指纹 = 未声明值（两者语义确实相同）✅

已核对 base→HEAD 的 `to_dict()`/`spec_hash` 实现**逐字未变**（`git show <base>:agent/subagent/workflow.py` 的该段与 HEAD 一致），故冻结字面量对改前改后同值，测试主张成立。

**钳制方向核验**：`parse_spec_for_manager` 对声明值 500 解析结果为 500（**解析不改写**），`_eff_limit` 返回 7（**读取处取 min**）——与 spec delta「显式值精确生效 + min 钳制」一致。

**编译域核验**：`max_rounds` 25/26/100 编译通过、101 被拒（`WorkflowValidationError`），与 `proposal.md:41` 陈述一致。

---

## Test Results

### `uv run pytest tests/agent/subagent/ -q -p no:randomly`

```
710 passed in 27.70s
```

### `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`

```
Totals: 29 passed, 0 failed (29 items)
```

### `uv run python scripts/check_openspec_artifacts.py`

```
ERROR: workflow-recursion-limit-default: review manifest missing:
       openspec/changes/workflow-recursion-limit-default/reviews/building-review-manifest.json
REAL_EXIT=1
```

**如实说明**：该 exit 1 的**唯一**原因是 review manifest 缺失——属**预期在途状态**。按仓库审阅闭环流程，manifest 在本审阅判 **PASS 之后**才由 `/review-loop` 生成（绑定 reviewer run、base/head sha、tasks/spec/diff/report hash）。本报告即 PASS 依据，manifest 为后续产物。**不据此判 CHANGES_REQUESTED**。其余所有 artifact 检查（tasks 勾选、grill 证据、Open Question 确认、RIR 内容门槛、受保护路径事件）**均无报错**（输出中无其它行）。

---

## Open Questions / Blockers

无阻塞性疑问。以下为供主 session 决策的**非阻塞**项（不影响 PASS）：

1. **Issue 6（`tasks.md:3` 陈旧状态行）**：归档前顺手改/删，或保持现状直接归档？（审阅者倾向顺手改一行——成本极低，且归档后该行会留在 archive 里误导读者。）

---

## 结论

**PASS。**

Round 1 的 5 项问题**全部修好**，且经独立探针复验而非仅凭自述：Issue 1（tasks 勾选）未勾行仅剩归档/post-merge 两项，归档门禁解除；Issue 3（测试名实不符）新版本显式声明 500 → 解析保留 500、`_eff_limit` 钳到 7，两段断言独立复现为真；Issue 4（量纲注释）已订正为「3 superstep/轮（`superstep = 3N + 2`）」并区分 run/轮口径；Issue 5（编译域）已记录且边界实测为 ≤100；Issue 2（工作区漂移）已提交、`git status` 干净。

核心行为与 Round 1 结论一致并再次独立验证：四处默认值均为 100、无第五处、三路径一致；**核心回归非恒真**（N=12 → 38 superstep，对照组稳定撞 `recursion_limit`）；`spec_hash` 冻结字面量 `9cee33da95470fbc` 独立重算逐字相同；spec 同步**未丢 #246 诊断句**（`declared_max_rounds` 计数 3、`默认 25` 零命中、delta 与 current 段落一致）；既有机制零改动。测试全绿（710 passed / 29 passed），artifact checker 唯一报错为预期在途的 manifest 缺失。

**残留仅 1 条 low/nit 级文档陈旧（Issue 6，`tasks.md:3` 状态行），不触发任何门禁、不阻塞 PASS。** 可进入归档收尾。
