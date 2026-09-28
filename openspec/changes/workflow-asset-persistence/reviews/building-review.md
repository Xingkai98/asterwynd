# Building Review: workflow-asset-persistence（issue #245）

## Verdict

**PASS**

Round 1 的四条 finding（M1 / L1 / L2 / L3）**全部经独立复现确认修复**，且修复方式与本 change
自定的信任边界、Q8 方案 C 与「对外报生效值」口径一致。本轮顺带把钳制读取与报值收敛到同一个
模块级 `clamp_limit` / `limits_report`，使「对内钳的值」与「对外报的值」在结构上不可能分叉
——这是对 Round 1 提交信息以外、由本轮审阅**独立于提交信息**核实的一处实质改进。全量测试、
OpenSpec strict validate 全绿；artifact checker 仅剩「review manifest 缺失」这一预期中间态
（报告已存在、manifest 待本 PASS 后生成），无其它报错。

- **审阅轮次**: Round 2（复审）
- **审阅基线**: base `bab8e72`（与 `origin/master` 的 merge-base）→ HEAD `6f10713`
- **上一轮**: Round 1 判 `CHANGES_REQUESTED`（M1 中 + L1/L2/L3 低，见文末「Round 1 结论摘要」）
- **审阅者**: 独立零记忆 subagent（`/review-loop`），未修改任何实现/测试代码
- **工作区**: `/home/happy/.paseo/worktrees/0frj3kg8/workflow-asset-persistence-2026-09-28`，分支 `workflow-asset-persistence/2026-09-28`

## Round 1 Finding 复核表

全部**先读代码 + 跑独立探针**，不采信提交信息。

| # | 严重度 | Round 1 结论 | 本轮复现方法 | 本轮结论 |
|---|--------|--------------|--------------|----------|
| **M1** | 中 | `_apply_asset_overrides` 对「覆盖面声明了 spec 中不存在的节点」抛未捕获 `KeyError` | 手工落 `overrides={"ghost": ["task"]}`、spec 无 `ghost` 节点的资产 → `RunWorkflowAsset` | ✅ **已修复** |
| **L1** | 低 | `RunWorkflowAsset(wait=False)` 返回体 `limits`/`limits_clamped` 均为空 | 同一资产 `wait=True` vs `wait=False` 两路对比 | ✅ **已修复**（且两路口径逐字一致） |
| **L2** | 低 | 任务 1.3 标 `[x]` 但 delta 未同步进 `openspec/specs/` | `grep` + 逐字 diff delta↔主 spec | ✅ **已修复** |
| **L3** | 整洁度 | `_spec_for_asset` / `import os` / `import uuid` / 测试 `_Ctx` 未用 | 全仓 `grep` | ✅ **已修复**（见 Issues 的 N1 尾巴） |
| I1 | 非本 change | `workflow.py` 的 `with_limits` 死代码系历史遗留 | — | 维持（不阻塞） |
| I2 | 非本 change | mode 六条回归锁由 #255 交付 | — | 维持（不阻塞） |

### M1 ✅ 详细复核

- 修复位置：`agent/tools/builtin/subagents.py:1118-1122`——在 `allowed is None` 判断之后新增
  `if node_id not in nodes:` 分支，返回结构化 `override_not_declared: node 'ghost' is declared
  as overridable but is not present in this asset's spec`。原崩溃点 `nodes[node_id][field_name]`
  （`:1131`）在节点存在性检查之后，不再可达。
- **独立复现**（`/tmp/probe_r2_m1_l1.py`，手工构造资产，未走保存工具）：
  - `overrides={"ghost": {"task": "rewritten"}}` ⇒ 返回 `{"status": "override_not_declared",
    "reason": "... node 'ghost' is declared as overridable but is not present in this asset's spec"}`，
    **未抛异常**。
  - 对照面逐条成立：合法覆盖（节点 `a` 已声明且存在）⇒ `status == "completed"`；未被声明的节点
    ⇒ `override_not_declared: node 'nope' is not declared as overridable`；已声明节点 + 未声明字段
    ⇒ `override_not_declared: field 'items' on node 'a' is not declared`。
- **回归测试非空洞证明**（`/tmp/probe_r2_mutation.py`，独立变异）：把修复前的
  `_apply_asset_overrides`（无节点存在性检查）重新注入 ⇒ 同场景抛 `KeyError: 'ghost'`。即
  `test_run_asset_rejects_override_for_missing_node`（`test_workflow_asset_tools.py:278`）确实
  钉住了这条路径；对照用例 `test_run_asset_applies_declared_override`（`:353`）保证合法路径必须成功。
- 额外负向扫面（`/tmp/probe_r2_malformed.py`，10 种畸形资产：`nodes` 非列表 / `nodes` 缺失 /
  `spec=None` / 节点无 `id` / `overrides` 值非列表 / pattern 无 recipe 等）⇒ **全部返回结构化
  状态，零崩溃**，未发现与 M1 同族的第二个未兜底异常。

### L1 ✅ 详细复核

- 修复位置：`agent/tools/builtin/subagents.py:1226`（`limits = limits_report(spec, ceiling)`，从
  **已解析的 spec** 直接算）+ `:1228-1238`（`wait=False` 与 `wait=True` 共用同一份 `limits`）。
- **独立复现**（`/tmp/probe_r2_m1_l1.py`）：资产声明 `max_runs=5000`、配置 300：
  - `wait=False` ⇒ `limits.max_runs == {"declared": 5000, "applied": 300, "clamped": true}`、
    `limits_clamped == {"max_runs": {"declared": 5000, "applied": 300}}`；
  - `wait=True` ⇒ **逐字相同**；两路 `limits` 与 `limits_clamped` 完全一致。
- 回归测试 `test_run_asset_reports_limits_when_not_waiting`（`test_workflow_asset_tools.py:313`）。
  变异复核（`/tmp/probe_r2_mutation.py`）：修复前取值源 `scheduler._limits_report()` 在 `run()`
  前返回 `{}` ⇒ 证明旧路径确为空报告，新路径非空洞。

### L2 ✅ 详细复核

- `openspec/specs/multi-agent-collaboration/spec.md` 已含 **7 条**新 Requirement（行号）：
  `:449` 可寻址性 / `:482` 仓库级作用域 / `:500` 可发现面 / `:534` 显式保存 /
  `:558` 两类载体与覆盖面 / `:590` 加载期闸值钳制与资产能力面呈现 / `:649` 命名与同名语义。
- **同步保真（逐字）**：用脚本按 `### Requirement:` 切分 delta 与主 spec，7 条正文**全部
  `IDENTICAL`**（非仅标题存在）。
- `openspec/specs/subagents/spec.md`：`深度到限撤 spawn 工具` 已更新为含 `RunWorkflowAsset`
  （`:70`），并新增 Scenario「深度到限仍可保存与列出资产」；与 delta 的 MODIFIED 版**逐字
  `IDENTICAL`**。`grep RunWorkflowAsset openspec/specs/` 命中 3 行（`:70`/`:76`/`:85`）。
- 受保护路径事件：`workflow-events.jsonl` 新增 seq 2/3 两条 `current_spec_synced`（分别对应
  两个 spec 文件），命中 `scripts/flow-policy.json` 的 `openspec/specs/` prefix 规则
  （`event_types: ["current_spec_synced"]`）。合法。
- backlog 口径订正为「**7** 条 ADDED Requirement」，与主 spec 实际一致。

### L3 ✅ 详细复核

- `grep -rn "_spec_for_asset"` ⇒ **零命中**（定义与调用均删）。
- `agent/subagent/workflow_assets.py` 已无 `import os` / `import uuid`。
- `tests/agent/subagent/` 已无 `_Ctx`。
- 尾巴（非阻塞，见 Issues N1）：`test_workflow_asset_tools.py:406` 的 `import inspect` 未使用，
  但该导入由本 change 的首次提交 `19717a7` 引入（`git log -S` 证实），Round 1 未列；属整洁度遗留。

## 逐条任务验证

对照 `tasks.md` 的每个 `[x]` 读代码确认真实存在。Round 1 已逐条核实 1.x–4.x，本轮重点复核
**新增的 6.1 节**与 Round 1 变更点，未发现回归。

### 6. 审阅闭环修复记录

| 任务 | 结论 | 证据 |
|------|------|------|
| 6.1 四条修复记录真实 | ✅ | 子项 M1/L1/L2/L3 分别对应 `subagents.py:1118-1122`、`subagents.py:1226-1238`、`openspec/specs/**`（7+1 条逐字同步）、三项死代码删除——均经本轮独立复现，非纸面记录 |

### 1–4 节（沿用 Round 1 结论，本轮抽验未推翻）

| 区块 | 结论 | 本轮抽验 |
|------|------|----------|
| 1.1–1.8 规格与设计 | ✅ | 1.3 由假勾选转为真交付（L2） |
| 2.1–2.10 测试 | ✅ | 新增 M1/L1 两条回归；负向用例均有「合法路径必须成功」对照 |
| 3.1–3.16 实现 | ✅ | 3.5 钳制重构后读取/报值同源；3.4 消费 #255 通道不变 |
| 4.1–4.8 验证 | ✅ | 本轮实跑见下（4.1/4.2/4.3/4.4） |

## 8 维审阅结论

1. **任务逐项验证**：所有 `[x]` 均有真实实现。Round 1 唯一假勾选（1.3）已转真；新增 6.1 节
   的四条修复记录均可独立复现。5.1–5.7（归档收尾）保持未勾，属正常的 PR 后段，正确。
2. **正确性**：
   - 闸值钳制 `_eff_limit` 经模块级 `clamp_limit`（`scheduler.py:448-450`）取 `min`，`ceiling is None`
     时原样返回 ⇒ 双向语义不变。
   - `grep -n 'spec\.\(max_runs\|max_nodes\|recursion_limit\)' agent/subagent/scheduler.py` ⇒ **零命中**；
     9 处读取点全部走 `_eff_limit`。
   - **本轮重构核心核验**：`_eff_limit`（`:613`）与 `_limits_report`（`:621`）分别委托给同一个
     `clamp_limit` / `limits_report`，**读取处与报值出口同源**，不存在「对内钳 A、对外报 B」的分叉面。
   - `limits_report(None, ceiling)` 返回 `{}`（`:461-462`）；调用方 `_envelope`（`:3046`）与
     `workflow_graph_snapshot`（`:2835`）在 `_spec is None` 时**不会崩溃**——`wait=False` 路径实测
     经 `scheduler.status()` 走该分支仍返回正确 limits（探针确认）。
   - `asset_source` 纯附加：`run_pattern` 返回键集锁（13 键）+ `asset_source` 不泄漏断言通过。
3. **Spec 对齐**：实现覆盖 delta 与主 spec 的每条 Requirement/Scenario。**主 spec 7 条与 delta
   逐字一致**（脚本 `IDENTICAL` 核实）；**未重复 #255 的 mode 机制语义**——`workflow 节点 mode
   有效值受会话上限钳制` Requirement 在主 spec 仅 **1 份**（`:400`），资产面的 `:590` 以引用方式
   指向它并显式声明「SHALL NOT 复述或另立一套收窄语义」。
4. **冗余度**：本轮未引入新冗余——`clamp_limit`/`limits_report` 抽成模块级是**去重**而非增重
   （原先 `_eff_limit` 与 `_limits_report` 各写一遍 min 逻辑）。`workflow.py:1114` 的
   `{"recursion_limit", "max_nodes", "max_runs"}` 是 `with_limits` 的**校验白名单**（用途不同，
   且该文件本 change 未改），非重复。`with_limits` 死代码 = I1 历史遗留，不计本 change 责任。
5. **测试覆盖**：新增 M1 回归（`:278`，配对照 `:353`）与 L1 回归（`:313`）均经**变异验证**
   证明非空洞。负向套件（slug 越界 / symlink 穿透 / 版本拒绝 / 覆盖未声明拒绝 / 注入面）逐条配
   合法路径对照。
6. **安全性**：slug 越界（`../escape`/`a/b`/大写/空串）与长度上限、symlink 穿透（文件与目录两级，
   `test_workflow_assets.py:200,213`）、`unsupported_asset_version`、`reserved_name`、
   `override_not_declared`（含新补的越界节点）全部有测试。注入面仅 `name` + 单行截断 `description`、
   单行化防伪标题、不进子 agent（`manager.py:1323` 传 `include_workflow_asset_index=False`）、
   `cacheable=False`（`workflow_asset_source.py:35`）。畸形资产扫面（10 例）零崩溃。
7. **可维护性**：模块划分（store / 注入源 / 工具）清晰；`clamp_limit`/`limits_report` 的抽取
   把「同一语义必须两处一致」的隐式约束变成**结构保证**，并配了说明性 docstring（解释为何不能
   分叉，而非复述代码）。修复注释点明「信任边界输入」与「`_spec` 未 attach」两个真实约束。
8. **CI 完整性**：**未弱化**。两个快照测试的改动（`test_workflow_graph_snapshot.py:190`、
   `test_workflow_graph_snapshot_additions.py:42`）是把 `limits` 按既有 drift-guard 约定登记进
   **白名单**（原断言是 `set(snapshot) <= {...}` 的**上限/超集**断言），属「有意识新增键」，
   无任何断言被删除或放宽。OpenSpec/artifact 门禁不变。

## Issues

### 无阻塞项

Round 1 的 M1（中）与三条 Low 均已修复，本轮未发现新的中等及以上问题。

### Low / Info（整洁度，均不影响 CI）

**N1. `tests/agent/subagent/test_workflow_asset_tools.py:406` `import inspect` 未使用（F401，本轮新发现）**
- 位置：`test_run_asset_consumes_mode_ceiling_channel` 函数体内 `import inspect`，函数只用
  `hasattr(...)`，`inspect` 未被引用。
- 性质：**本 change 引入**（`git log -S "import inspect"` → `19717a7`），Round 1 的 L3 未列。
- 影响：仓库无 ruff/lint CI 步骤（`.github/workflows/` 无 lint job），不影响门禁；仅为整洁度。
- 建议：随下一次触及该文件时顺手删除（可 `ruff check --fix`）。

**N2. 基线失败的环境根因订正（Info，非缺陷）**
- Round 1 把 `tests/agent/memory/test_persistent.py::TestFindScopeRoot` 两条失败归因于
  「本机 `/tmp` 自身是 git 仓库」。本轮实测订正：`/tmp` **不是** git 仓库，但 `/tmp/.git` 是一个
  **空目录**（`ls -ld /tmp/.git` ⇒ `drwxr-xr-x ... Sep 21`），`_find_scope_root` 走 `git_dir.is_dir()`
  命中它并返回 `/tmp`。
- 为何测试的 monkeypatch 拦不住：用例只 patch 了 `Path.exists`，而实现用 `is_dir()`/`is_file()`
  ——补丁对实现无效，故该用例实际依赖「树上无任何 `.git`」，被 `/tmp/.git` 打破。
- 与本 change 的关系：`agent/memory/persistent.py` 与其测试**与 base 逐字相同**（`git diff` 为空），
  属环境型基线失败，**非本 change 缺陷**。本 change 复用 `_find_scope_root` 做资产桶解析，但资产
  作用域测试均**自造 `.git` 目录/文件**（`test_workflow_assets.py:154,173`），最内层 `.git` 先命中，
  不受 `/tmp/.git` 影响——本轮已验证其语义仍然成立。

## Test Results（实跑）

| 命令 | 结果 |
|------|------|
| `uv run pytest tests/agent/subagent -q` | **639 passed** in 23.77s |
| `uv run pytest -q`（全量） | **3404 passed, 2 failed, 9 skipped** in 421.59s |
| `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` | **29 passed, 0 failed**（含 `✓ change/workflow-asset-persistence`） |
| `uv run python scripts/check_openspec_artifacts.py --base-ref bab8e72` | 仅 1 条 `review manifest missing`（**预期中间态**，exit 1），**无其它报错** |

**2 个失败均与本 change 无关**（见 N2）：

1. `tests/agent/memory/test_persistent.py::TestFindScopeRoot::test_returns_none_for_non_git_dir`
2. `tests/agent/memory/test_persistent.py::TestFindScopeRoot::test_malformed_git_file_falls_back_to_scan`

根因：本机 `/tmp/.git` 为空目录，`_find_scope_root` 回退到 `/tmp`（`assert PosixPath('/tmp') is None`）；
`agent/memory/persistent.py` 与其测试与 base 逐字相同，属环境型基线失败。

**独立探针复核结论**（全部落 `/tmp`，未进仓库；不采信读码推断）：

- `/tmp/probe_r2_m1_l1.py`：M1 结构化拒绝（无异常）+ 3 条对照面（合法覆盖成功 / 未声明节点 / 未声明
  字段）+ L1 两路口径逐字一致 ⇒ **三项全 True**。
- `/tmp/probe_r2_mutation.py`：重新注入修复前 `_apply_asset_overrides` ⇒ 抛 `KeyError: 'ghost'`；
  修复前取值源 `_limits_report()` 在 `run()` 前返回 `{}` ⇒ **两条回归均非空洞**。
- `/tmp/probe_r2_malformed.py`：10 种畸形资产 ⇒ 全部结构化返回、零崩溃。

## Round 1 结论摘要（历史）

Round 1（审阅基线 base `bab8e72` → HEAD `2bb4d4f`）判 **CHANGES_REQUESTED**：

> 实现主体质量高：资产 store、四工具、加载期闸值钳制（Q8 方案 C）、可发现面（Q4/Q9）、深度闸（D7）、
> #255 通道消费（Q11）均已落地并被测试覆盖。**未 PASS 的原因**：一处中等健壮性缺陷
> （`_apply_asset_overrides` 对「覆盖面声明了 spec 中不存在的节点」抛未捕获 `KeyError`）——即 **M1**，
> 外加任务 `1.3` 假勾选——即 **L2**；另有 **L1**（`wait=False` 不报生效值）与 **L3**（死代码/未用导入）。
> Round 1 实测：`tests/agent/subagent` 637 passed；全量 3401 passed / 3 failed；OpenSpec strict 29 passed。

本轮（Round 2）已确认上述 M1/L1/L2/L3 全部修复，转 **PASS**。

## 结论

Round 1 的四条 finding 逐条修复且经独立复现成立；本轮唯一新增的实质改动（钳制读取与报值同源）
是**去重与结构保证**，不引入新冗余或新缺口。实现覆盖 delta 与主 spec 的每条 Requirement/Scenario，
主 spec 的 7 条与 delta 逐字一致且未重复 #255 的 mode 机制语义。全量测试通过（2 条环境型基线
失败无关），OpenSpec strict validate 全绿，artifact checker 仅剩 review manifest 这一**预期中间态**。

**Verdict = PASS**。可进入 `/review-loop` 的 manifest 生成步骤；**N1**（未用 `import inspect`）与
**N2**（基线失败根因订正）为非阻塞整洁度/记录项，不阻碍合入。
