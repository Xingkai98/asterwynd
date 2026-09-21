# Building Review — fix-issue-199-handoff-prereq

- **Reviewer**: 独立零记忆 subagent（`/review-loop`，issue #90 闭环第 1 轮）
- **审阅对象**：`git diff origin/master...HEAD`（`5fa99aa` 立项 + `3a13ec9` 实现）
- **base / head**：`origin/master` (abdcedf) / `3a13ec9`
- **审阅时间**：2026-09-21

## Verdict

**CHANGES_REQUESTED**

实现本身正确、判别力充分、spec delta 的「整段替换」风险已正确处理并通过实跑验证；但存在两个中等问题需修复后再进第 2 轮：

1. `docs/known-debt.md` 的改动**没有属于本 change 的** `protected_artifact_explained` 事件（唯一事件是 `backlog_updated`）。当前 checker 之所以 PASS，是因为 `openspec/changes/archive/2026-09-20-fix-issue-191/workflow-events.jsonl` 里一条恰好覆盖同路径的旧事件，属**偶然通过**——这恰是本 change 要修复的「证据链断裂」问题本身。
2. `tasks.md` 28 条任务 **0 条勾选**，导致所有以 `_tasks_all_complete` 为前提的机械门禁（grill Open Question 确认覆盖、building-review + PASS manifest）**全部处于关闭状态**（实测删掉 `reviews/building-review.md` 后 checker 仍 PASS），已完成范围的任务项未落勾。

两项都不是阻塞性缺陷（核心功能已可用、测试全绿），定性为 CHANGES_REQUESTED。

## Tasks Verification

`tasks.md` 当前 `- [x]` 计数 = **0**，`- [ ]` 计数 = **28**。逐条按实现事实核验如下（`[x]` 表示我核验为「实现已完成」）。

### 实现

| # | 任务 | 状态 | 证据 |
|---|---|---|---|
| 1 | `cmd_artifact_event` 移除 `handoff.json` 硬前置，改「目录存在 且（`proposal.md` 或 `handoff.json`）」；不存在/两者皆缺 exit 1 | 已完成 | `scripts/workflow_state.py:963` 调 `_require_change_target`；判定体 `:859-869`（目录存在 `:860-862`，两锚点或分支 `:863-868`） |
| 2 | `cmd_review_manifest` 同上 | 已完成 | `scripts/workflow_state.py:992`；同一 `_require_change_target` |
| 3 | 抽出共用前置检查函数，两条命令复用 | 已完成 | `scripts/workflow_state.py:847-869`，两处调用点 `:963` / `:992`，文案单点定义 |
| 4 | 前置检查保持 `is_workflow_enabled` 之后、原 `handoff.json` 检查同一位置 | 已完成 | `:957`（enabled）→ `:963`（target）；`:986` → `:992`。替换位置即原 `handoff.json` 检查处，分支序未变（D5） |
| 5 | 两条命令成功后调 `_flow_refresh_after_event(change_dir)`（D7） | 已完成 | `scripts/workflow_state.py:980`（artifact-event）、`:1016`（review-manifest） |
| 6 | 其余四处 `handoff.json` 引用按 D3 保留 + 记 known-debt | 已完成（保留部分）／**事件缺失** | 四处均未改动、未删除：`cmd_current` `:539-542`、`cmd_spawn` `:904-906`、`cmd_validate` `:1022-1024`、`discover` `:367-368`（text）/`:405-406`（json）。`docs/known-debt.md` 新增三段债务文本（diff `+59` 行）。**但 `protected_artifact_explained` 事件缺失 → 见 Issue 1** |

### 测试

| # | 任务 | 状态 | 证据 |
|---|---|---|---|
| 7 | 无 `handoff.json` + `proposal.md` + `change_created` → `artifact-event` exit 0 且事件写入 | 已完成 | `tests/test_workflow_protected_write_channel.py:146-156`（断言 `handoff.json` 不存在 `:149`，断言事件确实落在 `workflow-events.jsonl` `:154-156`） |
| 8 | 同条件 → `review-manifest` exit 0 且 manifest 写入 | 已完成 | `:159-169`（`verify_review_manifest == []` `:169`） |
| 9 | 老世代（`initialized` + `handoff.json` + `proposal.md`）→ 两命令 exit 0 | 已完成 | `:187-206`（种子 `_seed_gen1_change:60-90`，`initialized` 首事件内嵌 handoff 载荷 `:79`） |
| 10 | 无 `proposal.md` 但有 `handoff.json` → 两命令 exit 0 | 部分完成 | `:209-220` 只覆盖了 `artifact-event`；`review-manifest` 在 spawn 形态目标上没有对应用例（属重复路径，可接受，记为观察项不记缺陷） |
| 11 | 不存在的 change → 两命令 exit 1 | 已完成 | `:226-239`；且断言错误文案来自目标检查本身（`:231` / `:238` 注释即为此意图），保证「前置被删」有判别力 |
| 12 | 存在目录但两锚点皆无 → 两命令 exit 1 | 已完成 | `:242-261`，附「不写任何文件」断言（`:250` / `:261`） |
| 13 | 写入后 `verify_projection` 为空（D7） | 已完成 | `:172-181`（`workflow-state.json` 存在 `:180` + `verify_projection == []` `:181`） |
| 14 | 变异验证（改回硬前置 / 整个去掉 / 还原变绿） | 已完成 | 我独立复跑，见下方 Test Results「变异验证」表，4 组变异全部变红、还原后全绿 |
| 15 | 回归 `tests/test_workflow_state_cli.py` + 全量 pytest | 已完成 | 53 passed（三文件）；全量 3000 passed / 3 failed（3 例均与本 change 无关，见 Test Results） |

### 文档

| # | 任务 | 状态 | 证据 |
|---|---|---|---|
| 16 | `diagnosis.md` 6 章 | 已完成 | `diagnosis.md`：Symptom / Reproduction / Evidence / Root Cause / Recommended Direction / Regression Tests（`grep '^## '` 命中 6 节） |
| 17 | spec delta 正文补全为变更后完整正文，保留既有 8 条 Scenario | 已完成 | 逐条比对见下方「Spec delta 独立核验」；退役 2 条（非 5 条）在 `design.md:114-126` 显式列清单 |
| 18 | `docs/known-debt.md` 新增债务条目（配 `protected_artifact_explained` 事件） | **未完成** | 文本已完成；事件缺失 → **Issue 1** |
| 19 | 当前规格同步（`current_spec_synced` ×2） | 未执行（属收尾） | `openspec/specs/{change-documentation,dev-workflow-state-machine}/spec.md` 尚未修改；`workflow-events.jsonl` 中无 `current_spec_synced`。收尾归档时才做，本轮不作为缺陷 |
| 20 | 关键词扫描 `docs/`、`AGENTS.md`、`docs/development-guide.md` | 已完成 | `grep -rn handoff AGENTS.md docs/development-guide.md` 仅命中 `AGENTS.md:89` 的「旧的四阶段状态机仪式（… handoff.json …）已停用」，本就与实现口径一致，无需改；无本次造成的事实变化 |
| 21 | backlog 移除本 change 条目（`backlog_updated` 事件） | 未执行（属收尾） | 本 change 已作为第 5 号条目加入「未实现队列」`docs/openspec-change-backlog.md`（diff `+20`），归档时移除。收尾项，非缺陷 |

### 审阅闭环 / 验证

| # | 任务 | 状态 | 说明 |
|---|---|---|---|
| 22 | 独立 subagent 审阅 → verdict | 进行中 | 即本报告（第 1 轮）→ CHANGES_REQUESTED |
| 23 | 生成 review manifest 绑定各 hash | 待第 2 轮 PASS 后 | 未生成 |
| 24 | 全量 pytest | 已完成 | 3000 passed / 3 failed（3 例与本 change 无关，见下） |
| 25 | OpenSpec strict validate | 已完成 | 30 passed / 0 failed |
| 26 | artifact checker | 已完成 | PASS（但 known-debt 一项是偶然通过，见 Issue 1） |
| 27 | 端到端验收（issue #199 验收原文） | 已完成 | 我独立复现，见下方「冷状态端到端验收」 |
| 28 | `flow status --change fix-issue-199-handoff-prereq` 反映投影 | 已完成 | 见 Test Results |

**结论**：可落勾的已完成项共 **22** 条（实现 5 条：1-5，第 6 项因缺事件未闭环；测试 9 条：7-15；文档 3 条：16/17/20；验证 5 条：24-28），除任务 18（缺事件）外均有真实实现。任务 19（当前规格同步）/21（backlog 移除）属归档收尾、任务 23（manifest）属第 2 轮 PASS 之后，本轮不计缺陷但归档前必须完成。

## Issues

### Issue 1 — `docs/known-debt.md` 缺本 change 的 `protected_artifact_explained` 事件（严重程度：中）

**证据**

- `openspec/changes/fix-issue-199-handoff-prereq/workflow-events.jsonl` 全文仅 **1 行**，`event_type` 为 `backlog_updated`（`artifact_path: docs/openspec-change-backlog.md`）。
- 隔离验证（只把本 change 的事件日志 + `flow-policy.json` 放进临时仓库，排除其它 change 的归档事件）：

  ```
  isolated (只有本 change 的事件日志):
    docs/known-debt.md              -> ['protected path `docs/known-debt.md` changed without workflow event explanation']
    docs/openspec-change-backlog.md -> []
    本 change 事件类型: ['backlog_updated']
  ```

- 全仓库 checker 之所以 PASS，是因为**别的归档 change** 带着同路径事件兜底：

  ```
  openspec/changes/archive/2026-09-20-fix-issue-191/workflow-events.jsonl: 'docs/known-debt.md'
  openspec/changes/archive/2026-07-14-add-workflow-automation/workflow-events.jsonl: 'docs/known-debt.md'
  openspec/changes/archive/2026-08-02-long-term-memory-deepening/workflow-events.jsonl: 'docs/known-debt.md'
  openspec/changes/archive/2026-08-14-flow-policy-source/workflow-events.jsonl: 'docs/known-debt.md'
  ```

  即本 change 改了 `docs/known-debt.md`，但**没有任何属于本 change 的结构化解释事件**；门禁绿是历史事件的副作用。

**为什么是缺陷**：`tasks.md:30`（「`docs/known-debt.md` 新增债务条目（**配 `protected_artifact_explained` 事件**）」）、`design.md:61`（D3）与 `design.md:89`（D4）、以及 grill 用户确认原文（`reviews/grill-design.md:54` Q3、`:55` Q4：「统一记入 docs/known-debt.md（配 `protected_artifact_explained` 事件）」）都把它写成必须项。而 `proposal.md:33`「背景」节的核心论点正是「绕底层写通道削弱了门禁的证据链」——本 change 自己却出现了同类证据缺口，且被旧事件掩盖。

**修复方向**（前置已修好，可直接走 CLI 自证该修复生效）：

```bash
uv run python scripts/workflow_state.py artifact-event \
  --change fix-issue-199-handoff-prereq \
  --event-type protected_artifact_explained \
  --artifact-path docs/known-debt.md \
  --reason "记录 fix-issue-199 实测四处 legacy 子命令失效（issue #227）、三层 handoff.json 残留耦合（issue #228）、受保护路径解释门禁可被伪造 change 目录糊过（issue #229）" \
  --approved-by human
```

补完后请重跑隔离验证（把本 change 的事件日志单独放入 tmp 仓库跑 `check_protected_path_explanations`，返回 `[]` 才算真修）。

### Issue 2 — `tasks.md` 全未勾选，完成态门禁整体关闭（严重程度：中）

**证据**

- `tasks.md` 的 `- [x]` 计数 = 0，`- [ ]` 计数 = 28（本报告 Tasks Verification 已确认其中 22 项的实现事实已完成）。
- 后果（`scripts/check_openspec_artifacts.py` 的 `_tasks_all_complete` 门禁全部短路）：
  - `_check_review_manifests:1028-1032` 的 `requires_building_review` 为假 → **即使 `reviews/building-review.md` 不存在也不报错**。实测：删除该文件后 `check_openspec_artifacts.py` 仍输出 `OpenSpec artifact checks passed`（exit 0）。
  - `_check_design_review_task:735-742` 的 `## User Confirmation` 覆盖校验不触发（本 change 的 6 条 Q 确实都有确认记录，此处只是说明门禁未生效，不是内容缺失）。
- 因此本 change 可以在「零审阅证据」状态下合入，与 AGENTS.md 的强制审阅闭环规则冲突；同时 manifest 若在此时生成，其 `tasks_hash` 绑定的是全未勾选的 `tasks.md`，与「tasks 全勾」语义不一致。

**修复方向**：在生成 review manifest 前，把**已完成**的 22 项落勾（实现 6 + 测试 9 + 文档 3 + 验证 4），只保留确实未执行的三项不勾（任务 19 当前规格同步、任务 21 backlog 移除、任务 23 review manifest）——注意任务 19/21 必须在归档收尾时完成并勾选，否则它们不勾会让完成态门禁一直关闭。勾选后重跑 `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py` 确认完成态门禁真的打开（含 manifest 校验）。

### Issue 3 — `review-manifest` 的 D7 刷新调用无测试覆盖（严重程度：低）

**证据**：把 `scripts/workflow_state.py:1016` 的 `_flow_refresh_after_event(change_dir)` 单独删掉，`tests/test_workflow_protected_write_channel.py` + `tests/test_workflow_state_cli.py` **28 passed 全绿**——没有任何用例能发现这条刷新被移除。对比：删掉 `:980`（artifact-event 侧）会红 1 例。`tasks.md:9` 把这条要求写成了覆盖「两条命令」的单一任务项。

**影响**：`review-manifest` 路径下的「写完即可被 checker 校验」（D7 的收益）无回归保护，日后重构容易静默丢回顺序依赖。

**修复方向**：在 `tests/test_workflow_protected_write_channel.py:159` 的用例末尾补两行（我已实测这两行对 `:1016` 被删是判别性的——加完后跑变异 5 会红 `test_review_manifest_works_without_handoff_json`）：

```python
    assert (change_dir / "workflow-state.json").exists()
    assert verify_projection(change_dir) == []
```

（`verify_projection` 已在文件顶部 `:24` 导入，无需新增 import。）

### Issue 4 — `--change` 传绝对路径可把事件写到仓库外（严重程度：低，既有属性非本次引入）

**证据**（本 change 修复后的 CLI）：

```
PYTHONPATH=$REPO python3 $REPO/scripts/workflow_state.py artifact-event \
  --change /tmp/<ext-dir> --event-type protected_artifact_explained \
  --artifact-path docs/known-debt.md --reason x --approved-by human
-> 已记录 artifact 事件: ...   exit=0
-> /tmp/<ext-dir>/ 出现 handoff.json / workflow-events.jsonl / workflow-state.json
```

`_require_change_target:859` 的 `CHANGES_ROOT / change_id` 在 `change_id` 为绝对路径时被 `pathlib` 整体替换为 `change_id`。**该行为在修复前同样成立**（旧代码同样用 `CHANGES_ROOT / args.change` 拼路径），D1 未使其变差，故按 design 的口径记 Low 而非阻塞项。

**修复方向**（可留给后续债务，不必在本次修）：在 `_require_change_target` 内加一行 `if Path(change_id).is_absolute() or ".." in Path(change_id).parts: 拒绝`，或改用 `(CHANGES_ROOT / change_id).resolve()` 后断言 `is_relative_to(CHANGES_ROOT.resolve())`。

## Test Results

### 1. 目标测试

```
$ uv run pytest tests/test_workflow_protected_write_channel.py tests/test_workflow_state_cli.py tests/test_workflow_guard.py -q
53 passed in 40.14s
```

### 2. 变异验证（我独立复跑，每组跑完均 `cp /tmp/ws_backup.py scripts/workflow_state.py` 还原，`sha256=4cf13a492b503ccb...` 全程核对）

| # | 变异 | 变红用例 | 判定 |
|---|---|---|---|
| 1 | `_require_change_target` 改回硬要求 `handoff.json` | 7 failed / 3 passed：`test_artifact_event_works_without_handoff_json`、`test_review_manifest_works_without_handoff_json`、`test_artifact_event_refreshes_projection_without_flow_status`、`test_artifact_event_rejects_unknown_change`、`test_review_manifest_rejects_unknown_change`、`test_artifact_event_rejects_dir_without_proposal_or_handoff`、`test_review_manifest_rejects_dir_without_proposal_or_handoff` | 判别力充分——核心症状用例确实锁住旧前置 |
| 2 | 前置检查整个去掉（`return CHANGES_ROOT / change_id`） | 4 failed：两个 `rejects_unknown_change`、两个 `rejects_dir_without_proposal_or_handoff` | 判别力充分——非法目标用例锁住「不退化为任意路径可写」（D5） |
| 3 | 去掉 `handoff.json` 兼容分支（只认 `proposal.md`） | 1 failed：`test_spawn_style_child_without_proposal_still_writable` | 判别力充分——Q1 回归面被锁住 |
| 4 | 同时去掉两处 `_flow_refresh_after_event` 调用 | 1 failed：`test_artifact_event_refreshes_projection_without_flow_status` | 判别力部分（见 Issue 3） |
| 5 | 只去掉 `:1016`（review-manifest 侧刷新） | **0 failed / 28 passed** | **无判别力 → Issue 3** |
| 6 | 只去掉 `:980`（artifact-event 侧刷新） | 1 failed：`test_artifact_event_refreshes_projection_without_flow_status` | 判别力充分 |

还原核对：每组结束后 `sha256sum scripts/workflow_state.py` 均为 `4cf13a492b503ccb…`；最终 `git status --short` 为空（无残留改动）。

### 3. 冷状态端到端验收（issue #199 验收原文，全程**不跑 `flow status`**）

```
cold? handoff exists: NO
$ python3 scripts/workflow_state.py artifact-event --change e2e-cold --event-type protected_artifact_explained \
    --artifact-path docs/known-debt.md --reason "e2e cold repro" --approved-by human
已记录 artifact 事件: protected_artifact_explained (docs/known-debt.md)     exit=0
$ python3 scripts/workflow_state.py review-manifest --change e2e-cold --phase building \
    --reviewer-run-id r1 --base-sha deadbeef --head-sha deadbeef
已写入 review manifest: .../reviews/building-review-manifest.json            exit=0
$ verify_projection(change_dir)       -> []
$ verify_review_manifest(...)         -> []
```

隔离仓冷状态 + 真实 change 形态（含 spec delta），checker 结果：

```
$ PYTHONPATH=. python3 scripts/check_openspec_artifacts.py
OpenSpec artifact checks passed                            exit=0
（manifest verdict = PASS，全程零手写 PASS 文本、零 flow status）
```

**前后对照**（用 `git show origin/master:scripts/workflow_state.py` 的旧二进制在同一冷状态 change 上跑）：

```
cold: NO-HANDOFF
$ python3 <pre-fix> workflow_state.py artifact-event --change pre-fix-199 ...
错误：change 'pre-fix-199' 没有 handoff.json                exit=1
$ python3 <pre-fix> workflow_state.py flow status --change cold      # 自愈
handoff.json now exists? YES
$ python3 <pre-fix> workflow_state.py artifact-event --change cold ...   # 同一命令
已记录 artifact 事件: ...                                    exit=0
```

→ 复现了 `diagnosis.md` 描述的「顺序依赖掩蔽」：修复前冷状态 exit 1、`flow status` 自愈后立刻 exit 0；修复后冷状态直接 exit 0。

### 4. Spec delta 独立核验（不只看 delta 自己）

程序化逐条比对 delta 与正式 spec（`openspec/specs/dev-workflow-state-machine/spec.md`、`openspec/specs/change-documentation/spec.md`）：

```
===== dev-workflow-state-machine =====
  Requirement: 工作流事件日志与 handoff.json projection
    formal scenarios (8): [当代 change 投影为 workflow-state.json, 老世代 change 仍可投影, 任意 change 可查询状态,
                           新建 change 时初始化 workflow event log 和 handoff.json, agent 读取当前状态,
                           WorkflowEngine 更新状态, handoff.json 被手动篡改, 非状态 artifact 事件]
    delta  scenarios (11): 8 条既有（2 条按 D6 退役清单改写：新建 change 时初始化 workflow event log / 投影被手动篡改）
                           + 3 条新增（受保护写通道不要求 handoff.json / 受保护写通道拒绝非法目标 /
                             老世代 change 的受保护写通道保持可用）
    DROPPED from delta: ['新建 change 时初始化 workflow event log 和 handoff.json', 'handoff.json 被手动篡改']
===== change-documentation =====
  Requirement: Handoff state file artifact
    formal (3) / delta (4)：3 条既有全部保留（按两代口径改写）+ 1 条新增（当代 change 不要求 handoff.json）
    DROPPED from delta: []
```

- **无静默丢失**：两条「DROPPED」正是 `design.md:114-126` 退役清单显式列出的改写项（改名 + 重写正文），非缺省消失。
- **字节级核验**：`当代 change 投影为 workflow-state.json`、`老世代 change 仍可投影`、`任意 change 可查询状态`、`非状态 artifact 事件`… 逐条比对结果已记录（`非状态 artifact 事件` 保留了「支持的 artifact event type 至少含 4 类」这一本 change 依赖的清单，`design.md:122` 的承诺成立）。
- `design.md:112` 声称「现状 delta 只带 6 条、归档会静默删掉 5 条」——按正式 spec 逐条比对，实际退役数为 **2 条**（另 3 条是改名/改写后保留）。这是 design 记录里的事实偏差，但**不影响** delta 的正确性（补全是超集安全的），故不记 Issue，仅在此备注。

### 5. 其他实跑

```
$ npx --yes @fission-ai/openspec@1.4.1 validate --all --strict
Totals: 30 passed, 0 failed (30 items)                     exit=0

$ PYTHONPATH=. python3 scripts/check_openspec_artifacts.py
OpenSpec artifact checks passed                            exit=0

$ uv run python scripts/workflow_state.py flow status --change fix-issue-199-handoff-prereq
（输出该 change 的 state / milestones / source_event_seq 投影）

$ uv run pytest -q
3 failed, 3000 passed, 9 skipped in 382.66s
  FAILED tests/agent/memory/test_persistent.py::TestFindScopeRoot::test_returns_none_for_non_git_dir
  FAILED tests/agent/memory/test_persistent.py::TestFindScopeRoot::test_malformed_git_file_falls_back_to_scan
  FAILED tests/web_tests/test_multi_session_browser.py::test_multi_tab_exit_does_not_affect_other_tab_reconnect
```

- 前两例为已知环境失败（环境存在 `/tmp/.git` 导致向上扫描误判），已在 base `abdcedf` 复现，**与本 change 无关**。
- 第三例为浏览器时序 flaky：单独重跑 `uv run pytest tests/web_tests/test_multi_session_browser.py::test_multi_tab_exit_does_not_affect_other_tab_reconnect -q` → **1 passed**，与本 change 无关。
- CI/guard 面未弱化：`git diff origin/master...HEAD -- .github/ scripts/flow-policy.json scripts/workflow_guard.py AGENTS.md` 为空；`scripts/flow-policy.json` 受保护路径规则表与 `workflow_guard.py` 白名单零改动（与 `proposal.md:40` 的非目标一致）。

## 其他维度的核验结论

- **正确性**：`_require_change_target:859-869` 与 design D1 逐字一致（目录存在 `:860` + 两锚点或 `:863`）；`is_workflow_enabled` 仍在最前（`:957` / `:986`，D5）；非法目标确实不落任何文件（变异 2 下两个用例红，且用例自带「未写 `workflow-events.jsonl`」`:250` /「未建 `reviews/`」`:261` 断言）。`openspec/changes/archive` 作为目标被正确拒绝（实测 exit 1，因 `archive` 目录自身无 `proposal.md`）。
- **冗余度**：新函数与既有 `_flow_require_change:761` 有意分叉（后者以 `workflow-events.jsonl` 为前置，首次写入会自锁），`design.md:41` 已论证；未与 `_flow_is_gen1` 混用，理由见 `design.md:50`。判定逻辑单点、两命令复用，无重复实现。
- **安全性**：锚点放宽后仍拒绝不存在目录与两锚点皆无的目录；`docs/`、`openspec/changes/archive/` 等受保护路径的解释事件校验逻辑未改。Issue 4 的绝对路径缺口是既有属性。
- **可维护性**：`_require_change_target:848-858` 的 docstring 解释的是「为什么」（为何不要求事件日志、为何保留 `handoff.json` 分支），非「是什么」，符合要求。命名与文件内既有 `_flow_*` 前缀风格一致。
- **CI 完整性**：未弱化任何 CI 配置；受保护 artifact 中 `docs/openspec-change-backlog.md` 的改动有 `backlog_updated` 事件（隔离验证返回 `[]`），`docs/known-debt.md` 缺事件（Issue 1）。

## 结论

实现层面（前置判定、顺序、拒非法目标、写入后刷新）与 design D1/D5/D7 完全对齐，测试从冷状态构造、变异验证有判别力，spec delta 的「整段替换」风险已按 D6 正确处理并通过独立比对验证——**没有阻塞性缺陷**。

进第 2 轮前请修复：

1. **Issue 1（中）**：用（现已可用的）CLI 补 `protected_artifact_explained` 事件覆盖 `docs/known-debt.md`，并用隔离验证确认本 change 的事件日志单独就能让该路径通过。
2. **Issue 2（中）**：把已完成范围的 22 项任务落勾（保留任务 19/21/23 不勾，归档收尾时补），确认完成态门禁真的打开。
3. **Issue 3（低）**：给 `review-manifest` 侧补 `verify_projection` 断言（已实测判别性）。
4. **Issue 4（低）**：可留给后续债务，不必在本次修（既有属性、非回归）。

修复后重跑 `/review-loop`：再审应重点看 Issue 1 的隔离验证结果与 `tasks.md` 勾选后的 checker 输出（含 manifest 校验）。
