# Building Review: workflow-asset-persistence（issue #245）

## Verdict

**CHANGES_REQUESTED**

实现主体质量高：资产 store、四工具、加载期闸值钳制（Q8 方案 C）、可发现面（Q4/Q9）、
深度闸（D7）、#255 通道消费（Q11）均已落地并被测试覆盖，钳制与注入面两项经独立探针
复验成立，全量测试通过（仅 3 个与本 change 无关的失败）。**未 PASS 的原因**：一处中等
健壮性缺陷（`_apply_asset_overrides` 在「覆盖面声明了 spec 中不存在的节点」时抛未捕获的
`KeyError`，正是本 change 自定的信任边界输入），外加任务 `1.3` 标了 `[x]` 但其交付物
（delta 同步进 `openspec/specs/`）当前不存在。两项均不阻塞整体设计，修复后即可 PASS。

- **审阅轮次**: Round 1
- **审阅基线**: base `bab8e72`（与 `origin/master` 的 merge-base）→ HEAD `2bb4d4f`
- **审阅者**: 独立零记忆 subagent（`/review-loop`），未修改任何实现/测试代码
- **工作区**: `/home/happy/.paseo/worktrees/0frj3kg8/workflow-asset-persistence-2026-09-28`，分支 `workflow-asset-persistence/2026-09-28`

## 复审范围与方法

- `git diff bab8e72...HEAD`（22 文件 / +3443 −29）逐文件读码：`agent/subagent/workflow_assets.py`（新，488 行）、`agent/context/workflow_asset_source.py`（新，65 行）、`agent/subagent/{scheduler,manager,patterns}.py`、`agent/tools/builtin/subagents.py`、`agent/loop.py`。
- change 文档：`proposal.md` / `design.md` / `tasks.md` / `specs/multi-agent-collaboration/spec.md` / `specs/subagents/spec.md` / `reviews/grill-design.md`。
- 4 个新测试文件 + 2 个被改的既有测试逐条核对。
- **独立探针**（全部落 `/tmp`，未进仓库）：钳制 min 双向 + hash 不回写（`/tmp/probe_review_clamp.py`）、注入面单行化/截断/防伪标题（`/tmp/probe_review_inject.py`）、覆盖面边界（`/tmp/probe_override_edge.py`、`/tmp/probe_stale_override.py`）、`wait=False` 报值（`/tmp/probe_wait_false.py`）。
- 机械门禁实跑：`openspec validate --strict`、`scripts/check_openspec_artifacts.py`、`pytest tests/agent/subagent`、全量 `pytest`。

## 逐条任务验证

### 1. 规格与设计

| 任务 | 结论 | 证据 |
|------|------|------|
| 1.1 spec delta（可寻址性/显式保存/两类载体/加载期钳制/命名语义） | ✅ 真实 | `specs/multi-agent-collaboration/spec.md` 6 条 ADDED Requirement |
| 1.2 subagents delta（工具枚举含 `RunWorkflowAsset`） | ✅ 真实 | `specs/subagents/spec.md:7`（MODIFIED，逐字列出 `StartWorkflow`/`RunWorkflow`/`RunWorkflowAsset`） |
| 1.3 delta 同步进 current spec | ❌ **未落地** | `grep -rn "asset_schema_version\|RunWorkflowAsset\|可发现面" openspec/specs/` **零命中**；见 Issue M2 |
| 1.4 范围/非目标界定 | ✅ 真实 | design Non-Goals 与实现一致（未做共享路径、未改 `workflow_id`/per-run 落点、未合并 `workflow_record.json`） |
| 1.5 batch-grill 设计追问 + 停轮确认 | ✅ 真实 | `reviews/grill-design.md` 两轮（r1/r2），Q1–Q11 + 2 条实现期确认项均有 `## User Confirmation` 记录 |
| 1.6 Impact Analysis 结论化 | ✅ 真实 | proposal `## Impact Analysis` 5 项均为明确结论，无 `unknown`/`TBD` 残留 |
| 1.7b/1.7c/1.7/1.8 回写订正 | ✅ 真实 | design 有「实现期订正（2026-09-28）」块；引用行号漂移已按 grill 风险 9 订正 |
| 1.7 RIR | ✅ 真实 | proposal `## Reference Implementation Research`（`research_tier: full`，两层调研） |

### 2. 测试

| 任务 | 结论 | 证据 |
|------|------|------|
| 2.1 round-trip | ✅ | `test_workflow_assets.py:112,126`（DSL/pattern 往返） |
| 2.2 负向与安全 + 对照 | ✅ | slug 越界 `:89`、symlink `:200,:213`、版本 `:228,:238`、保留名 `:193`；每条配「合法路径必须成功」（如 `test_workflow_asset_tools.py:161-167`） |
| 2.3 钳制双向 + 报告 | ✅ | `test_workflow_asset_limits.py:82`（低于配置不被抬高）、`:91`（无 ceiling 逐字不变）、`:100`（不回写 spec/hash）、`:116`（envelope 报生效值） |
| 2.3b mode 六条回归锁 | ⚠️ 由 #255 交付 | 六条锁在 `tests/agent/subagent/test_mode_ceiling.py`（`git log` 证实由 `291ed7c` 即 #255 引入，本 change **未**改该文件）；本 change 的净新增是消费侧 `test_workflow_asset_tools.py:246,262`。与任务原文「若 #255 尚未合入，本任务先在 #255 侧落测试」口径自洽，但**六条锁非本 change 交付物**，见 Issue L2 |
| 2.4 容错三态 | ✅ | `test_workflow_assets.py:257,265,279`（无资产 diagnostics 空 / 全损坏非空含计数 / 有健康资产） |
| 2.4b 报生效值一致性 | ✅ | 三出口逐条：`test_workflow_asset_limits.py:116,126,134` |
| 2.5 跨会话集成（字节不变） | ✅ | `test_workflow_asset_context.py:159`（新 manager+store，`read_bytes()` 断言 fork 语义） |
| 2.5b 仓库级作用域 | ✅ | `test_workflow_assets.py:154`（伪造 `.git` 文件 + `commondir`）、`:173`（跨仓库隔离） |
| 2.5c pattern 溯源往返 | ✅ | `test_workflow_asset_tools.py:106`（dsl）、`:125`（pattern recipe 保留） |
| 2.6 工具面与深度闸 | ✅ | `test_workflow_asset_tools.py:367,371,377`（`RunWorkflowAsset` ∈ spawn；深度到限子 agent 保留 Save/List/Get） |
| 2.6b `run_pattern` 键集锁 | ✅ | `test_workflow_asset_context.py:195`（13 键集锁）、`:221`（`asset_source` 不泄漏） |
| 2.7 列表有界性 | ✅ | `test_workflow_assets.py:298` |
| 2.8 索引一致性 | ✅ | `test_workflow_assets.py:319`（unchanged 不重写）、`:330`（updated + previous_spec_hash）、`:339`（事件日志） |
| 2.9 注入面 | ✅ | `test_workflow_assets.py:352,374,383,387` |
| 2.9b 注入范围 + cacheable | ✅ | `test_workflow_asset_context.py:103,110,127` |
| 2.10 手动重放绕过（钉为预期） | ✅ | `test_workflow_asset_context.py:236` |

### 3. 实现

| 任务 | 结论 | 证据 |
|------|------|------|
| 3.1 资产 store（落点/slug/原子写/symlink/索引/容错） | ✅ | `workflow_assets.py:254-457`；复用 `WorkflowStore._atomic_write`（`:392`）、`_find_scope_root`/`_compute_project_hash`（`:269-271`） |
| 3.2 SaveWorkflowAsset（spec 不穿模型输出） | ✅ | `subagents.py:997-1030`（`manager.get_workflow` 取 spec） |
| 3.2b pattern 溯源（纯附加） | ✅ | `scheduler.py:467`（默认 `{"kind":"dsl"}`）、`patterns.py:457`（覆盖为 pattern）；键集锁证明不改返回结构 |
| 3.3 List/Get | ✅ | `subagents.py:1042,1080` |
| 3.4 RunWorkflowAsset（消费 #255） | ✅ | `subagents.py:1197-1230`；消费 `manager.effective_mode`（`subagents.py:1094` → `manager.py:1633`）。#255 已合入：`manager.py:1623 mode_ceiling()` / `:1633 effective_mode()` 存在 |
| 3.5 闸值钳制（读取处取 min，9 处穷举） | ✅ | `scheduler.py:563 _eff_limit` 统一访问器；`grep 'spec\.\(max_runs\|max_nodes\|recursion_limit\)' agent/subagent/scheduler.py` **零命中**（独立复核） |
| 3.6 pattern 可序列化描述 | ✅ | `subagents.py:919-955`（复用 `PATTERNS` 经 `compile_pattern`） |
| 3.7 工具注册 + SPAWN 扩展 | ✅ | `loop.py:406-413`（注册）、`loop.py:1488`（注入源）；`manager.py:434`（`RunWorkflowAsset` 入闸） |
| 3.8 工具描述行为引导 | ✅ | `subagents.py:417-420,560,840-843` |
| 3.9 受限可发现面 | ✅ | `workflow_asset_source.py`、`workflow_assets.py:223-251`；`cacheable=False`（`:35`）；只 root（`manager.py:1323`） |
| 3.10 配置接入 | ✅（无需） | `git diff bab8e72...HEAD -- agent/config.py` 为空，与 proposal「无改动」一致 |
| 3.11 入口层/artifact | ✅（不适用） | 资产未在 CLI 暴露，无 artifact 记录需求 |
| 3.12/3.13 影响面/调研回写 | ✅ | design 实现期订正块 |
| 3.14 文档更新 | ✅ | `docs/architecture.md:58` 新增资产工具行；`.gitignore:11` 已含 `.asterwynd/`（复核）。README 未列工具清单，无需改 |
| 3.15 前置 #255 确认 | ✅ | #255 已合入（PR #259，base `bab8e72`）；通道 `mode_ceiling()`/`effective_mode()` 存在 |
| 3.16 阶段 1 裁剪（Q10/Q11 归 #255 spec） | ✅ | delta 无 mode 机制复述：`:150` 明写「由既有机制保证…SHALL NOT 复述」；跨图继承 Scenario 在主 spec `openspec/specs/multi-agent-collaboration/spec.md:404` |

### 4. 验证

| 任务 | 结论 | 证据 |
|------|------|------|
| 4.1 subagent 测试 | ✅ 实跑 | 637 passed |
| 4.2 全量测试 | ✅ 实跑 | 3401 passed / 3 failed（均与本 change 无关，见下） |
| 4.3 OpenSpec strict validate | ✅ 实跑 | `Totals: 29 passed, 0 failed`，含 `✓ change/workflow-asset-persistence` |
| 4.4 artifact checker | ✅ 实跑 | `OpenSpec artifact checks passed`（exit 0） |
| 4.5 baseline CI 三件套 | ✅ 实跑 | 同上 |
| 4.6 benchmark smoke | ⚠️ 采信 | 本次审阅未重跑（大依赖）；tasks 记录已跑，风险低 |
| 4.7 变异验证 | ⚠️ 采信 | tasks 记录 7 条；本次独立复验了其中「min 方向」与「注入面」两条的核心断言（探针），成立 |
| 4.8 不适用项记录 | ✅ | tasks:99 显式记录 Web/TUI/browser 不适用 |

## Issues（按严重度分级）

### Medium

**M1. `_apply_asset_overrides` 对「覆盖面声明了 spec 中不存在的节点」抛未捕获 `KeyError`**
- 位置：`agent/tools/builtin/subagents.py:1104-1131`，触发点 `:1130`（`nodes[node_id][field_name] = value`）。
- 现象：当资产文件的 `overrides` 声明了某个 `node_id`，而 `spec.nodes` 里没有该 id 时，`allowed = declared.get(node_id)`（`:1119`）非 `None`，流程走到 `nodes[node_id]` 直接 `KeyError`。调用点 `:1208-1216` 的 `try` 只包 `parse_spec_for_manager`（且只捕 `WorkflowValidationError`），**覆盖面应用在 try 之外**，故异常向上抛。
- 独立复现（`/tmp/probe_override_edge.py`）：手工落一份 `overrides={"ghost": ["task"]}` 而 spec 无 `ghost` 节点的资产，`RunWorkflowAsset(name="ghosty", overrides={"ghost": {...}})` ⇒ `CRASH: KeyError 'ghost'`。
- 为何是本 change 该管的面：`design.md` D3 明确把「从磁盘读回的、可能被其他工具或人改过的输入」定为信任边界，`spec` delta 也承诺「未声明的 `(node_id, field)` 组合 SHALL 拒绝（`override_not_declared`）」。当前对**越界节点**给的是裸 `KeyError`（经 `RetryHook` 变成 `[Error: 'ghost']`），既非结构化拒绝、也不自足。对照：同文件对面 `mode` 这类「不在白名单」的字段已被正确拒绝（`/tmp/probe_stale_override.py` ⇒ `override_not_declared`），说明缺的是节点存在性这一条。
- 修法建议：在 `_apply_asset_overrides` 内当 `node_id not in nodes` 时返回 `override_not_declared: node 'ghost' is not present in this asset's spec`；并在调用点把覆盖面应用纳入同一 `try` 或显式兜底 `KeyError`。配一条回归测试（「覆盖面指向不存在节点 ⇒ 结构化拒绝」，对照：合法节点覆盖必须成功——后者已有 `test_workflow_asset_tools.py:303`）。

### Low

**L1. `RunWorkflowAsset(wait=False)` 返回体既不报生效值也不报声明值（`limits`/`limits_clamped` 均为空）**
- 位置：`agent/tools/builtin/subagents.py:1223-1230`。
- 现象：`wait=False` 时先 `asyncio.ensure_future(scheduler.run(spec))` 再 `scheduler.status()`，而此刻协程尚未被执行、`scheduler._spec` 仍为 `None`，故 `_limits_report()` 返回 `{}`（`scheduler.py:581-583` 对 `_spec is None` 直接返回空）。
- 独立复现（`/tmp/probe_wait_false.py`）：`wait=False ⇒ limits_clamped={} / limits={} / status=declared`；`wait=True ⇒ limits_clamped={'max_runs': {...}}`。
- 影响：delta spec 的 Scenario「文件内声明的闸值被当前配置钳制」写的是「返回体 SHALL 报告 `limits_clamped`」，未区分 `wait`；工具描述也称「the response reports the effective values plus limits_clamped」，对 `wait=False` 不成立。默认 `wait=True`，故影响面小，但属规格与实现的措辞缺口。
- 修法建议：`wait=False` 分支在 `status()` 前先算 `scheduler._limits_report()`，或直接用构造期的 `ceiling` 与 `spec` 组装 `limits`/`limits_clamped`。

**L2. 任务 1.3 标 `[x]`，但 delta 尚未同步进 `openspec/specs/`（交付物当前不存在）**
- 现象：`tasks.md:7` 标 `[x]`「实现完成后把本 change 的 delta 同步进 current spec」，但 `grep -rn "asset_schema_version\|RunWorkflowAsset\|可发现面" openspec/specs/` 零命中，`git diff bab8e72...HEAD -- openspec/specs/` 为空。
- 背景：本仓库约定 spec 同步与归档收尾同 commit（`git log` 见 `a280b83`/`3e01894` 等「收尾：spec sync + 归档」；`/opsx:archive` 第 4 步负责同步），而 `tasks.md:103-108` 的 5.1–5.6 仍未勾选。因此**归档点位门禁会因 5.x 未勾选而挡住合入**，1.3 的假勾选不会真正逃逸。但按 AGENTS.md「所有 `[x]` 必须有真实实现」的口径，当前时点 1.3 不成立。
- 修法建议：在收尾 commit 完成 spec 同步后保持 `[x]`（推荐），或在此之前先撤销 `1.3` 的勾选。二者其一即可，无功能影响。

**L3. 死代码与未用导入（整洁度，非 CI 门禁项）**
- `agent/tools/builtin/subagents.py:905` `_spec_for_asset` 定义后**无任何调用方**（`grep` 全仓仅命中定义行）。
- `agent/subagent/workflow_assets.py:23-24` `import os` / `import uuid` 未使用（`ruff check` F401，2 处，均可自动修）。
- `tests/agent/subagent/test_workflow_asset_tools.py:74` `_Ctx` 类定义后未使用。
- 说明：仓库未配置 ruff/flake8（`pyproject.toml` 无 lint 段、`.github/workflows/` 无 lint 步骤），故这些不影响 CI；列为整洁度建议。

### Info（非本 change 责任，避免误读）

- **I1. `agent/subagent/workflow.py:1112` 的 `with_limits` 疑似死代码，但系历史遗留**：`git log -S "def with_limits"` 指向 `4923883`（`workflow-dsl-scheduler`），`git show bab8e72:agent/subagent/workflow.py` 亦已存在 ⇒ **非本 change 引入**，不在本次审阅责任面内（可作为独立清理项）。
- **I2. 「mode 六条回归锁」由 #255 交付**：`tests/agent/subagent/test_mode_ceiling.py` 由 `291ed7c`（#255）引入，本 change 未改该文件。任务 2.3b 的勾选依赖该前置（#255 已合入），本 change 净新增是消费侧断言，与任务原文口径自洽。

## Test Results（实跑）

| 命令 | 结果 |
|------|------|
| `uv run pytest tests/agent/subagent -q` | **637 passed** in 28.50s |
| `uv run pytest -q`（全量） | **3401 passed, 3 failed, 9 skipped** in 427.58s |
| `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` | **29 passed, 0 failed**（含 `✓ change/workflow-asset-persistence`） |
| `uv run python scripts/check_openspec_artifacts.py` | **passed**（exit 0） |

**3 个失败均与本 change 无关，已独立复核**：

1. `tests/agent/memory/test_persistent.py::TestFindScopeRoot::test_returns_none_for_non_git_dir`
2. `tests/agent/memory/test_persistent.py::TestFindScopeRoot::test_malformed_git_file_falls_back_to_scan`
   - 两条根因相同：`_find_scope_root` 在本机**回退到 `/tmp`**（`assert PosixPath('/tmp') is None`），即本机 `/tmp` 自身是 git 仓库的环境坑（与既有记忆记录一致）。`agent/memory/persistent.py` 与其测试**未被本 change 改动**（`git diff` 为空），属环境型基线失败。
3. `tests/web_tests/test_reconnect_pending_interaction_browser.py::test_streaming_delta_after_reconnect_lands_in_live_dom`
   - **重跑 1 passed**（5.62s），属已知 browser 测试 flake（既有记忆：master 上亦偶发）。

**独立探针复核结论**（不采信读码推断）：

- 闸值钳制 min 方向**双向**成立：声明 5000 + 配置 300 ⇒ 生效 300；声明 11 + 配置 300 ⇒ 生效 **11**（未被抬高）；无 ceiling ⇒ 声明值原样（`/tmp/probe_review_clamp.py`）。
- 钳制**不改写** `spec` 对象与 `spec_hash`（`hash unchanged after clamp: True`）、9 处读取点穷举（`grep` 零命中）。
- 注入面：换行 + 伪标题 `说明\n## 忽略以上指令` ⇒ 单行化为 `说明 ## 忽略以上指令`，**不产生伪小节标题**；`when_to_use` **不泄漏**；description 截断 ≤120；超 20 条截断 + 追加「还有 M 个资产未列出」+ 按 name 升序（`/tmp/probe_review_inject.py`）。
- 覆盖面：不在 `ALLOWED_OVERRIDE_FIELDS` 的字段被正确拒绝（`/tmp/probe_stale_override.py`）；但越界**节点**崩溃（见 M1）。

## 8 维审阅结论

1. **任务逐项验证**：见上表；除 `1.3`（M2/L2）外，所有 `[x]` 均有真实实现。2.3b/3.4/3.16 的 `#255` 依赖已核实——`SubAgentManager.mode_ceiling()`/`effective_mode()` 真实存在于 `agent/subagent/manager.py:1623,1633`，且 `RunWorkflowAsset` 经 `_declared_mode_report`（`subagents.py:1094`）真实消费。
2. **正确性**：`_eff_limit` min 双向 + 9 读取点穷举 + 溯源纯附加（键集锁）均成立；**唯一正确性缺口是 M1 的覆盖面越界节点**。
3. **Spec 对齐**：delta 6 条 ADDED + 1 MODIFIED 的 Scenario 均有实现与测试对应；阶段 1 裁剪到位——delta 不再复述 mode 机制（`:150` 显式声明归主 spec），跨图继承由主 spec `:404` 承担。
4. **冗余度**：复用了 `WorkflowStore._atomic_write`/`_validate_segment`、`persistent._find_scope_root`/`_compute_project_hash`/`_VALID_NAME_RE`、`parse_spec_for_manager`、`compile_pattern`，未造轮子。`with_limits` 死代码非本 change 引入（I1）。
5. **测试覆盖**：负向用例普遍配「合法路径必须成功」对照（除 M1 缺越界节点对照）；三态容错、min 双向、三出口报值均有对照。
6. **安全性**：slug 越界/长度/symlink 穿透/版本拒绝/覆盖未声明拒绝均有测试；注入面仅 name + 单行截断 description、不进子 agent、`cacheable=False`，独立探针复验成立。
7. **可维护性**：模块划分清晰（store / 注入源 / 工具三分），注释解释约束（如「为何不照抄 MemoryIndexSource」）而非复述代码；命中性好。L3 的死代码/未用导入为小瑕疵。
8. **CI 完整性**：**未弱化**。两个既有测试的改动（`test_workflow_graph_snapshot.py:184-192`、`test_workflow_graph_snapshot_additions.py:38-46`）是把 `limits` 按 drift-guard 约定登记进**白名单**（原断言形如 `set(snapshot) <= {...}`，是**超集/上限**断言），属「有意识的新增键」而非放行任意键；无任何断言被删除或放宽。OpenSpec/artifact 门禁不变。

## 结论

设计承诺的六项（可寻址性 / 仓库级作用域 / 可发现面 / 显式保存 / 两类载体与覆盖面 / 加载期钳制）在代码与测试两侧均成立，四项独立探针复验通过，机械门禁全绿。**建议按 CHANGES_REQUESTED 处理**：修复 **M1**（覆盖面越界节点的结构化拒绝 + 回归测试）为首要项，顺带处理 **L1**（`wait=False` 报值）与 **L2**（`1.3` 勾选口径）；**L3/I1/I2** 为整洁度或历史遗留，不阻塞。修复后执行 Round 2 复审即可转 PASS。
