# Building Review R2: workflow-builtin-templates

## Reviewer

- **run id**: `review-workflow-builtin-templates-20260929-r2`；paseo agent id `551652d7-1984-420a-a90b-c8596e4e74c4`
- **时间**: 2026-09-29
- **base/head**: base `ee06df7`（= `git merge-base HEAD master`，实测 `git rev-parse master` = `ee06df7`）/ head `d2c4b90aef5dd1c02f85b363562673a279011564`
- **verdict**: **PASS**

本轮为 R1 CHANGES_REQUESTED 后的独立零记忆复检（probe 全在 `/tmp/rev246r2/`，均实际运行）。三条 R1 阻塞项**逐一核实为真修复**，未发现修复引入的新缺陷。

---

## R1 Findings Verification

### HIGH-1 — 收尾任务预勾选 + 无对应修改的事件 → **已真修（选 R1 修法 1：真做）**

R1 指出 `tasks.md` 6.5/6.6/6.6a/6.8/6.9 预勾 `[x]` 但收尾实际未执行，且 `workflow-events.jsonl` 记入 5 条描述「不存在的修改」的受保护 artifact 事件。逐条复检：

- **spec delta 真同步进现行规格**：`git diff --stat ee06df7..HEAD -- openspec/specs/` **非空**（R1 时为空）——`agent-runtime` 30、`multi-agent-collaboration` 113、`subagents` 12、`web-ui` 11 行。逐 Requirement 头核对：4 份 delta 的 **10 条 Requirement 头全部出现在合并后的现行 spec 中**（脚本 `re.findall(r'^### Requirement:')` 集合包含判定，全 OK）：
  ```
  multi-agent-collaboration: Orchestration Pattern Library / 内置编排模式降级为 DSL 模板 /
    reducer 声明与图级递归上限 / 资产保存是显式的… / 资产的两类载体与参数化复用 /
    统一 Workflow 入口的模板输入 / 编排入口返回单一的 bounded 投影   （7/7 OK）
  subagents: 深度到限撤 spawn 工具（OK）  agent-runtime: 编排结果中的 bus 快照有界（OK）
  web-ui: workflow 运行态流程图视图（OK）
  ```
- **归档真发生、active 目录已消失**：`ls openspec/changes/` 只剩 `add-minimal-tui-runtime-view` + `archive/`；`openspec/changes/archive/2026-09-29-workflow-builtin-templates/` 存在（日期前缀合规，`ARCHIVE_PATH_RE` 命中）。`git diff --name-only --diff-filter=AR ee06df7` 报该目录为**新归档**，且 `git ls-tree -d ee06df7:openspec/changes/archive` 中**不存在**（base 树无 → 满足归档点门的「新建」判定，非「往既有归档补文件」）。
- **backlog 不再列未实现**：`rg workflow-builtin-templates docs/openspec-change-backlog.md` 命中的 `:104` 现在逐字写 **「已归档 2026-09-29」**（R1 时为「未实现」）。
- **事件与真实修改对应（HEAD 口径）**：6 条事件（R1 时 5 条）artifact_path 逐条覆盖真实存在且已变更的路径——4 条 `current_spec_synced`（4 份 spec）+ 1 条 `backlog_updated`（backlog）+ 1 条 `change_archived`（归档目录）。默认 `check_openspec_artifacts.py` exit 0，受保护路径解释检查通过。
- **tasks 勾选状态**：6.5/6.6/6.6a/6.7/6.8 均 `[x]`；**6.9 `[ ] (post-merge)`**（R1 时为 `[x]`，现已撤勾并补标记）；6.10 `[x] (post-merge)`。归档点门 `_untagged_unchecked_tasks` → **空**（无「未勾且未标 post-merge」项）。

**结论：HIGH-1 真修，非表面重勾。** 唯一残留是时序细节（见 New Issues LOW-1）：4 条 `current_spec_synced` 与 `backlog_updated` 落在 `e23748a`，而对应文件变更落在下一提交 `d2c4b90`——即事件比修改早一个提交。R1 的原意是「事件不得描述不存在的修改」，在 **HEAD 处已满足**（每条事件都能在最终树里找到对应变更）；且 R1 明示推荐修法 1（真做），实现者照做。不构成阻塞。

### HIGH-2 — `openspec/specs/**` 仍宣称 `RunPattern` 存在（16 处）→ **已闭合**

`rg -n 'RunPattern|run_pattern' openspec/specs/` 从 **16 处降至 6 处**。逐条枚举并分类（含大小写不敏感 `run.?pattern` 复核，同为 6 条，无遗漏写成其它拼写）：

| # | 位置 | 原文要点 | 分类 |
|---|---|---|---|
| 1 | `multi-agent-collaboration/spec.md:70` | 「…a separate `RunPattern` tool and its `run_pattern()` adapter **SHALL NOT exist**」 | **否定**（要求其不存在） |
| 2 | `multi-agent-collaboration/spec.md:143` | 「系统 **SHALL NOT 保留** `run_pattern()` 兼容 adapter…历史 `RunPattern` 返回体的 `workflow_spec_hash` 命名**随该返回体一并退役**」 | **否定 + 退役说明** |
| 3 | `agent-runtime/spec.md:286` | 「历史 `RunPattern` 返回体中的 `workers[]`…**不在本 Requirement 范围内**（随该返回体**退役**一并消失）」 | **退役说明** |
| 4 | `web-ui/spec.md:549` | 「`RunPattern` **SHALL NOT 再作为触发来源出现**（该工具**已退役**）」 | **否定 + 退役** |
| 5 | `subagents/spec.md:70` | 「`RunPattern` **SHALL NOT 再出现在该枚举中**（该工具…**退役**）」 | **否定 + 退役** |
| 6 | `subagents/spec.md:77` | 「**SHALL NOT 包含** `RunPattern`（该工具**已不存在**）」 | **否定** |

**零正向断言**。另跑 `rg -ni 'pattern tool|RunPatternTool|run_pattern\(' openspec/specs/ | rg -vi 'SHALL NOT|已退役|已不存在|退役|not exist'`，唯一命中是 `multi-agent-collaboration/spec.md:78` 的 Scenario「…reaches it through `RunWorkflow(template="bidding", ...)`, **not through** a dedicated pattern tool」——同属否定（且 R1 点名的三处代表性正向断言 `:70` 兼容 adapter、`agent-runtime:278/288`、`subagents:70`、`web-ui:535` 均已消失）。**仓库不再自相矛盾。**

### MED-1 — `GetWorkflow` 描述缺 run 口径 → **已真修 + 有判别力测试钉住**

四出口 `tool.description` 实测（`/tmp/rev246r2/probe_med1.py`）：

```
RunWorkflowTool       run-note=True  recursion_limit=True  declared=True  actual=True
StartWorkflowTool     run-note=True  recursion_limit=True  declared=True  actual=True
GetWorkflowTool       run-note=True  recursion_limit=False declared=False actual=False   ← R1 时 run-note=False
RunWorkflowAssetTool  run-note=True  recursion_limit=True  declared=True  actual=True
```

- `RunWorkflow`/`StartWorkflow`/`GetWorkflow`/`RunWorkflowAsset` 四者描述均含 **"RUNS, not subagents"**（task 2.2b 的 4 出口义务达成）。`GetWorkflowTool.description`（`agent/tools/builtin/subagents.py:709-713`）新增「`` `completed`/`failed` count RUNS, not subagents (a node that runs twice contributes two)``」。
- `StartWorkflow` 描述补 `recursion_limit` 量纲措辞（`subagents.py:593-601`）：把「exceeds the graph recursion limit」改为「recursion_limit」，并新增「`max_rounds` is a DESIRED round count — actual rounds are capped by the graph-level recursion_limit」。
- 新版量口径只加在三个「能收 template/params」的出口上（`GetWorkflow` 不收 template/params，故无 `declared_max_rounds`——与测试的 `_MAX_ROUNDS_EXITS` 白名单一致，设计正当）。
- **变异测试（判别力实测）**：从 `GetWorkflowTool` 描述删去该句（其余三处保留）后跑 `tests/agent/subagent/test_tool_description_contracts.py` → **1 failed**（`test_run_count_semantics_documented[GetWorkflowTool]`，断言 `'RUNS, not subagents' in …` 失败），其余 6 passed；`cp` 还原后 **7 passed**。测试非空转，能抓住「某出口漏口径」这类回归。

---

## Regression Check

| 检查 | 命令 | 结果 |
|---|---|---|
| 新增聚焦测试 | `pytest test_tool_description_contracts test_run_workflow_template test_pattern_params test_foreach_item_refs test_truncation_diagnostics` | **68 passed** |
| 子 agent + benchmark 套件 | `pytest tests/agent/subagent/ tests/benchmark/ -q` | **1175 passed, 1 skipped**（`test_mode_ceiling` 已知 flake 未复现） |
| 全量 | `pytest -q -p no:randomly` | 3 failed, **3464 passed**, 9 skipped |
| OpenSpec strict | `npx @fission-ai/openspec@1.4.1 validate --all --strict` | **28 passed, 0 failed** |
| artifact checker（默认） | `python scripts/check_openspec_artifacts.py` | **exit 0**，`OpenSpec artifact checks passed` |
| artifact checker（CI 归档模式） | `--check-archived --skip-protected-paths --skip-backlog` | exit 1，唯一 ERROR = `review manifest missing: …/building-review-manifest.json`（**预期**：manifest 由 review-loop 在 PASS 后生成；55 个归档 change 的 `tasks_hash` 按归档语境跳过，stderr 一行汇总，符合 #232 B） |
| benchmark smoke | `asterwynd benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/smoke-r2` | exit 0（72 tasks；`template` 臂不崩） |

**全量 3 条 failure 均为既有环境问题，与本 change 无关**（在 base `ee06df7` 的 detached worktree 中复跑同样 **3 failed**）：
- `tests/agent/memory/test_persistent.py::TestFindScopeRoot::test_returns_none_for_non_git_dir`
- `tests/agent/memory/test_persistent.py::TestFindScopeRoot::test_malformed_git_file_falls_back_to_scan`
- `tests/agent/test_background.py::test_task_output_truncated`

三者所属模块（`agent/memory/`、`agent/test_background.py`、`agent/background.py`）**在本 change 的 diff 中零改动**（`git diff --name-only ee06df7..HEAD` 复核）。前两条根因是本机 `/tmp` 本身是 git 仓库（既有已知坑，见 R1）；第三条 `test_task_output_truncated` 是 `check_completed()` 空列表的时序 flake。**无回归。**

---

## R1 代码面结论复检（快速）

- `RunPattern` 在 `agent/loop.py` 命中 **0**；`SPAWN_TOOL_NAMES = ('CreateSubagent','RunSubagent','ResumeSubagent','StartWorkflow','RunWorkflow','RunWorkflowAsset')`，不含 `RunPattern`；`hasattr(patterns,'run_pattern')=False`、`hasattr(sub,'RunPatternTool')=False`、`compile_pattern` 仍在。
- `_attach_item_refs`（`subagents.py:797-846`）三条硬约束实测成立（`/tmp/rev246r2/probe_refs.py`）：成功/失败/取消/空槽混跑 → `items_total=4, len(item_refs)=3, omitted=1`，仅成功项有 `result_ref`，失败项带 `status`+有界 `reason`；210 项超限 → `len=200`（= `_PARENT_NODES_LIMIT`）、`omitted=10`，**空槽被跳过、仅成功项带 ref、自带界**。
- `asset_source` 迁移仍真实：唯一写入点在统一入口 template 分支 `subagents.py:981`（`kind="pattern"` + `pattern`/`params`/`task`），spec 分支不写（保持默认 `{"kind":"dsl"}`）。
- `_envelope` / `parent_envelope` / `_bounded_node` 对 base 做 **AST 级逐字比较 → 三者 `unchanged=True`**（`agent/subagent/scheduler.py`）。

---

## New Issues

**无阻塞项。** 两条非阻塞观察：

### LOW-1 — 受保护 artifact 事件比其描述的修改早一个提交（时序卫生）

- **位置**：`e23748a`（事件）vs `d2c4b90`（spec/backlog 修改）。
- **事实**：4 条 `current_spec_synced` + 1 条 `backlog_updated` 落在 `e23748a`；`git diff --stat ee06df7..e23748a -- openspec/specs/` 为空，实际 spec 同步在下一提交 `d2c4b90`。
- **判定**：不阻塞。R1 的核心诉状是「事件描述了**不存在**的修改」——在 HEAD 处每条事件都对应真实变更，该诉状已消解；且 R1 明示推荐「修法 1：真做」并接受事件随之落笔。checker 校验的是「变更路径有对应事件覆盖」，不校验 commit 时序（`_protected_artifact_explanation_errors`），默认门 exit 0。**建议（非强制）**：未来收尾类受保护写入尽量与文件变更同提交，保持「事件伴随修改」的字面时序。

### LOW-2 — 归档目录内 `workflow-state.json` 是 stale 投影缓存（`source_event_seq: 5` vs 6 条事件）

- **位置**：`archive/2026-09-29-workflow-builtin-templates/workflow-state.json`（`d2c4b90` 新增）。
- **事实**：`source_event_seq=5`，而 `workflow-events.jsonl` 已有 6 条（差 `change_archived`）。
- **判定**：不阻塞。该文件是 `flow status` 的**投影缓存**（guard 明文「投影只是缓存，缺失/stale/损坏不代表状态」，`workflow_guard.py:544`）；active 路径下被 `.gitignore` 忽略（`.gitignore:27`），归档副本只是随 `git mv` 带过来的历史快照。已有 4 个历史归档同样提交了 `workflow-state.json`（本仓既有实践），且归档 change 不参与 awaiting 判定。属信息项，无需修。

R1 的 LOW-1（`item_refs` 每节点 200、`detail='nodes'` 跨节点无全局界）、LOW-2（`_FANOUT_CAP` 取 dataclass 默认值）**保持不变**，均忠实于 spec 明文、非本 change 缺陷，实现者未改亦正确。

---

## Probe Evidence

全部探针位于 `/tmp/rev246r2/`，均**实际运行**。

### 1. HIGH-2 命中枚举 — `rg -n 'RunPattern|run_pattern' openspec/specs/`

```
16 → 6 处；逐条分类：multi-agent-collaboration:70/143（否定+退役）、
agent-runtime:286（退役）、web-ui:549（否定+退役）、subagents:70/77（否定+退役）。
正向断言复核 `rg -ni 'pattern tool|RunPatternTool|run_pattern\(' … | rg -vi 'SHALL NOT|…'`
→ 仅 :78 一处「not through a dedicated pattern tool」（否定）。
```

### 2. 四出口描述 — `/tmp/rev246r2/probe_med1.py`

见上 MED-1 表。变异：删 `GetWorkflowTool` 该句 → `1 failed, 6 passed`；还原 → `7 passed`。

### 3. `item_refs` 不变量 — `/tmp/rev246r2/probe_refs.py`

```
混跑 items_total=4 len=3 omitted=1（空槽跳过）；仅成功项有 result_ref ✓
超限 210 → len=200 omitted=10（界 = _PARENT_NODES_LIMIT）✓
ALL ITEM_REFS INVARIANTS OK
```

### 4. 归档点门 + 判别力 — 直接调 `_check_archived_completion_gate()`

```
未改：[]（0 error）  _new_archive_dirs_since_base('.', 'master') → (['2026-09-29-workflow-builtin-templates'], [], None)
变异（6.9 去掉 (post-merge) 且未勾）→ 1 error「归档 change 存在未勾且未标 (post-merge) 的任务：- [ ] 6.9 …」
变异（删 building-review.md）→ R1 已验证「building-review.md missing」；本轮 6 条事件的 artifact_path 覆盖全部受保护变更路径
```

### 5. AST 逐字比较 — `_envelope` / `parent_envelope` / `_bounded_node`

```
agent/subagent/scheduler.py：三者 base_present/head_present 均 True，unchanged=True（逐字未动）
```

---

## Summary

**判 PASS。** R1 的三条阻塞项已**逐一真修**并有证据支撑：

- **HIGH-1**：spec delta 真同步进 `openspec/specs/**`（4 份文件非空 diff，delta 10 条 Requirement 头全在）、change 真归档（active 目录消失、日期前缀合规、base 树无该目录 → 归档点门视为新建）、backlog 真移除未实现措辞、6 条事件与最终树的真实变更一一对应、tasks 6.9 撤勾并标 `(post-merge)`。归档点完成度门 0 error。
- **HIGH-2**：`openspec/specs/**` 的 `RunPattern` 命中 **16→6**，逐条枚举**全为否定/退役措辞，零正向断言**，仓库自相矛盾已消解。
- **MED-1**：四出口描述齐备 `RUNS, not subagents`，`GetWorkflow` 补上、`StartWorkflow` 补 `recursion_limit` 量纲；新增测试经**变异验证有判别力**（删一句 → 精准 1 failed）。

**无回归**：子 agent + benchmark 套件 1175 passed；全量 3 条 failure 经 base 复跑确认为既有环境问题（`/tmp` 是 git 仓库 + background 时序 flake），涉事模块零改动；OpenSpec strict 28/28；artifact checker 默认 exit 0；CI 归档模式唯一 ERROR 为待 review-loop 生成的 manifest（预期）。代码面 R1 结论（`RunPattern` 删除干净、`item_refs` 三约束、`asset_source` 迁移、`_envelope`/`parent_envelope` AST 未动）复检仍成立。**可进 PR。**
