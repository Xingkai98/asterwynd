# Grill: check-scope-fix 设计追问

## Reviewer
- run id: 1dcf6023-d516-4995-9c83-7332375687da
- 时间: 2026-10-18
- 方式: 零记忆只读审阅；实读 change 全套文档、checker 全文相关函数、6 条测试、ADR 与文档 diff，并实跑验证（裸跑 / 显式 base / 旧默认复现 / 两点 vs 三点对照 / 全量定向测试 / OpenSpec strict validate）

## Confirmed Decisions
- **决策**: 未显式传 `--base-ref` 时以 `HEAD` 与 `origin/master` 的 merge-base 作为 diff base，显式参数（含空字符串）原样保留两点语义；理由: 实测本工作区 `master=3c7196b` 落后 `origin/master=b0469cb` 103 个提交，旧默认（`--base-ref master`）复现 8 个归档目录中 5 条缺 `## 闭环出口`、EXIT=1，而新裸跑 EXIT=0；显式 base 分支仍走 `git diff <ref>`，未被覆盖；来源: 1dcf6023-d516-4995-9c83-7332375687da
- **决策**: 归档点门的两条过滤（`--diff-filter=AR` + base 树不存在）与 `_review_exit_*` / `_check_archived_completion_gate` 出口判据逐行未动，新建归档缺出口仍红；理由: diff 未触及这些函数，测试 3 实跑 EXIT=1 且 stderr 同时含新归档目录名与「闭环出口」；来源: 1dcf6023-d516-4995-9c83-7332375687da
- **决策**: base 只在至少一个 diff 消费者启用时解析，并把同一结果同时传给归档点门与受保护路径 diff；理由: `main()` 用 `archive_gate_enabled or protected_paths_enabled` 守卫解析，两处调用传同一 `base_ref`；测试 5 断言受保护路径函数收到的实参而非仅 exit code；来源: 1dcf6023-d516-4995-9c83-7332375687da
- **决策**: spec delta 的 MODIFIED Requirement 与 current spec 同步一致；理由: 用脚本抽取两处 Requirement 块比较为逐字相同（len=5659），`openspec validate --all --strict` 实跑 30 passed；来源: 1dcf6023-d516-4995-9c83-7332375687da
- **决策**: 测试口径成立为「3 条修复前红（helper / 裸跑不追溯 / 受保护路径接线）+ 3 条守卫（新建归档仍红 / 显式优先 / 落后分支）」，6 条实跑全绿；但 tasks 中记录的 `-k` 命令只选中 5 条（见 M2），该缺口不影响测试本身有效性；来源: 1dcf6023-d516-4995-9c83-7332375687da
- **决策**: 本 change 自身归档的四道门（RIR / grill / grill-adversarial / building review）与 tasks 完成度可按 tasks 0.3、5.1、6.x 满足；但受保护路径 `openspec/changes/archive/**` 需要的 `change_archived` 事件未被列入任何任务，会在归档点整体 checker 上卡红（见 M1）；来源: 1dcf6023-d516-4995-9c83-7332375687da

## Code-Resolved Questions
- 根因是否确实是「默认 `master` + 本地 master 陈旧」？ → 是。旧默认值 `master`（`git diff origin/master` 中被删除的 `default="master"`；现文件 `scripts/check_openspec_artifacts.py:1814-1822`），本工作区 `master..origin/master` = 103 提交；实跑 `--base-ref master --skip-protected-paths --skip-backlog` 得到 8 个归档目录、5 条缺出口、EXIT=1，与 issue #319 列出的 5 个目录完全一致。
- merge-base 三点语义是否同时解决「历史归档误判」与「落后分支反向 diff」？ → 是。历史归档在 merge-base 树中存在，被 `_archive_dir_names_in_base` 过滤（`scripts/check_openspec_artifacts.py:1634,1651,1658-1673`）；落后分支实测：显式 `--base-ref origin/master`（两点）把上游 backlog 改动列为受保护路径 → EXIT=1，隐式 merge-base → EXIT=0。
- 显式 `--base-ref` 是否保持两点语义、不被覆盖？ → 是。`if explicit is not None: return explicit`（`scripts/check_openspec_artifacts.py:1538-1539`）；两个 diff 函数仍执行 `git diff <base_ref>`（`:1577-1582`、`:1621-1626`）；测试 4（`tests/test_openspec_artifact_checker.py:2845`）显式 `master` 仍红、`origin/master` 仍绿，测试 1（`:2772`）覆盖空字符串原样返回。
- `--require-base` / `--check-archived` / `--change` / `--skip-*` 是否自洽？ → 基本自洽。`--check-archived` / `--change` 只关闭归档门（`:1887`）；`--skip-protected-paths` 只关闭受保护路径 diff（`:1888`）；两个消费者都关闭时不解析、`base_ref` 保持 `None` 且无消费者使用（`:1891-1909`）；`--require-base` 仍在 diff 失败时 fail-closed（`:1583-1590`、`:1793-1797`）。唯一边界见风险 R3：`origin/master` 可解析但 merge-base 失败（shallow）时退回两点候选，`--require-base` 不会报错（`:1556`）。
- 归档点两条过滤与出口判据是否逐行未动？ → 是。`git diff origin/master -- scripts/check_openspec_artifacts.py` 没有触及 `_new_archive_dirs_since_base`（`:1595-1655`）、`_archive_dir_names_in_base`（`:1658-1673`）、`_check_archived_completion_gate`（`:1676-1780`）、`_review_exit_verdict/_review_exit_errors`（`:1118-1189`）。新建归档仍红由测试 3（`:2817`）与真实仓库旧默认复现共同证明。
- 六条测试是否真能区分修复前后？ → 是，但需按测试名逐条看。修复前红：测试 1（helper 不存在）、测试 2（旧默认把历史归档当新归档）、测试 5（旧默认把 `"master"` 传给受保护路径 diff，与期望 merge-base sha 不等）。修复前后均绿：测试 3（新建归档仍红）、测试 4（显式优先）、测试 6（落后分支；旧默认 `master` 恰等于分叉点 A，所以它在发行缺陷下也绿，只在「候选 ref 两点」变异下变红）。设计已如实标注测试 6 是变异守卫（`openspec/changes/check-scope-fix/design.md:119-120`），没有虚报先红。
- 是否存在假保护（ref 构造、skip flags、外层 `/tmp` git 仓库、只断言 exit code）？ → 未发现重大假保护。`_init_git_repo` 在 `tmp_path` 内新建仓库并配置 user（`tests/test_openspec_artifact_checker.py:1984-1989`）；autouse fixture 注入 `scripts/flow-policy.json`（`:17-27`），否则受保护路径门会 fail-closed；测试 2/3 的前置断言显式检查 `master != origin/master`、`rev-list` 计数、旧归档在 `master` 下是新归档、在 `origin/master` 下为空（`:2800` 附近）；测试 5 断言实参而非 exit code（`:2877`）。
- 变异验证口径是否可复现？ → 部分可复现但记录不完整。tasks 只写「恒返回 master → 1.2/1.5 红；返回候选 ref（两点）→ 1.6 红」；实际「恒返回 master」还会打红测试 1 的显式分支，「候选 ref 两点」会打红测试 1/5/6（测试 1 期望 merge-base sha，候选返回字符串），且没有给出变异补丁与命令（`openspec/changes/check-scope-fix/tasks.md:20`）。
- spec delta 是否与 current spec 兼容？ → 是。delta 的 Requirement 块与 `openspec/specs/dev-workflow-state-machine/spec.md:224` 起的内容逐字一致；delta 首行含 SHALL（`openspec/changes/check-scope-fix/specs/dev-workflow-state-machine/spec.md:11`）；strict validate 30 passed。
- 文档是否还有过期口径？ → 维护面已同步：`AGENTS.md:131`、`docs/development-guide.md:322-330`、`docs/requirements-process.md:261,290`、`docs/known-debt.md:218-221`、`.github/workflows/ci.yml:79-98`。全仓 grep 的旧口径命中只剩 `openspec/changes/archive/**` 的历史记录（应保留）。ADR-0007:9 链接的 `ADR-0006-retire-minimal-tui-runtime-view-proposal.md` 在当前树不存在（属 PR B），是唯一悬空引用。
- 本 change 自身归档点是否会被自己的门禁卡住？ → 主要证据可满足：RIR exempt + `status: disabled` + reason 引用 `#319/#316/#235`（`proposal.md:100-106`；`scripts/check_openspec_artifacts.py:635-654`）；grill / adversarial / building 由 tasks 0.3/5.1 覆盖；tasks 结算由文件头纪律覆盖。但 `openspec/changes/archive/**` 是受保护路径、要求 `change_archived` 事件（`scripts/flow-policy.json:38-43`），当前 `workflow-events.jsonl` 只有 `change_created` 与 `backlog_updated`；对假设的归档路径调用 `_protected_artifact_explanation_errors` 返回 `None`（即会报错）。另 `docs/known-debt.md` 缺本 change 的 `protected_artifact_explained` 事件，当前靠历史归档中的同路径事件通过（`scripts/check_openspec_artifacts.py:1290-1314`）。
- 仅在有消费者时解析是否正确？ → 正确。条件为 `archive_gate_enabled or protected_paths_enabled`（`:1886-1895`）；两者都关闭时 `base_ref=args.base_ref` 且无消费者调用；`--check-archived` 不带 `--skip-protected-paths` 时仍会解析（受保护路径检查仍在跑），与旧行为面一致。

## Open Questions
- 无

## 风险
- **R1（Medium）`origin/master` 自身未 fetch 陈旧时，原误报会复现**：此时 merge-base 仍落在旧点。design/ADR 称其为「fail-loud」，但用户体验与本次要修的假红相同；现有缓解只有文档「裸跑前 fetch」与显式 `--base-ref`（`scripts/check_openspec_artifacts.py:1540-1561`、`design.md:148`）。
- **R2（Medium）本 change 归档会因缺 `change_archived` 事件在整体 checker 上红**：归档路径是受保护前缀（`scripts/flow-policy.json:38`），CI 第一步与本地裸跑都会走 protected-path diff；当前事件日志无该事件（见 M1）。
- **R3（Low）shallow/merge-base 失败静默退回两点候选**：`_resolve_base_ref` 在 `git merge-base` 失败时返回候选 ref，`--require-base` 不会介入（`:1556`），落后分支的反向 diff 保护在浅克隆下失效。
- **R4（Low）`origin` 指向 fork/镜像或使用 stacked PR 时，默认 base 可能不是本 PR base**：ADR 的 revisit 条件只提到 release 分支，未覆盖 stacked PR；显式 `--base-ref` 是逃生口（`ADR-0007:75-82`）。
- **R5（Low）受保护 artifact 事件按路径跨全部历史匹配**：任何历史 change 对该路径的合规事件都能满足新改动（本次 `docs/known-debt.md` 即靠旧事件通过），证据门弱于「本 change 必须解释」的口径（`scripts/check_openspec_artifacts.py:1290-1314`）。
- **R6（Low）`--check-archived` 不带 skip flags 时的受保护路径 diff 也改用 merge-base**：这是默认 base 变更的自然结果，但与 proposal「不改 `--check-archived` 语义」的措辞略有张力（`proposal.md:80`）。
- **R7（Low）ADR-0007 对尚不存在的 ADR-0006 建了相对链接**：PR A 先合入时链接悬空（`docs/adr/ADR-0007-default-base-resolution-for-archive-gate.md:9`）。

## User Confirmation
无待用户拍板项。

---

## 必须修改项

- **M1 — Medium — 补 `change_archived` 受保护事件任务（否则本 PR 归档必红）**：落点 `openspec/changes/check-scope-fix/tasks.md` §6（或 §4 归档后复验）与 `design.md` Decision 5。归档 move 后（或 move 前预写）用 `scripts/workflow_state.py artifact-event --change check-scope-fix --event-type change_archived --artifact-path openspec/changes/archive/2026-10-18-check-scope-fix --reason ... --approved-by ...` 写入事件；同时增加一条「归档 move 与 tasks 结算后，重跑裸跑与 `--base-ref origin/master --require-base`」的验证任务。依据：`scripts/flow-policy.json:38-43`、`scripts/check_openspec_artifacts.py:1290-1314`，当前事件日志仅 2 条且无该事件。
- **M2 — Medium — 修正六条测试的运行口径**：落点 `tasks.md:19` 与 `tests/test_openspec_artifact_checker.py:2877`。`-k "resolve_base_ref or ..."` 匹配不到 `test_resolved_base_ref_is_used_for_protected_path_diff`（`resolved_` 不含 `resolve_`），实跑只选 5 条、漏掉受保护路径接线这条修复前红测试。建议把函数名改为 `test_resolve_base_ref_is_used_for_protected_path_diff`，或把 `resolved_base_ref`/`protected_path_diff` 加进过滤器；同时把「1.1/1.2/1.5 红」的编号改成测试名或 T1–T6，避免与任务编号混淆。
- **M3 — Low-Medium — 为 `docs/known-debt.md` 补本 change 的 `protected_artifact_explained` 事件**：落点 `tasks.md:32`（3.3）。当前门是绿只是因为历史归档中存在同路径事件（`scripts/check_openspec_artifacts.py:1290-1314`），不满足 AGENTS.md:24「修改 `docs/known-debt.md` 时必须有结构化解释事件」的口径；应在收尾时显式写入本 change 的事件。
- **M4 — Low — 把变异验证写成可复现证据**：落点 `tasks.md:20`。记录精确变异（改哪一行、返回什么）、运行命令与预期失败集合：恒返回 `master` 预期红 1/2/5；隐式分支返回候选 ref（两点）预期红 1/5/6。当前「返回候选 ref → 仅 1.6 红」不完整。

### 建议（非阻塞）
- **S1 — Low — spec 措辞收紧**：`specs/dev-workflow-state-machine/spec.md:11` 的「该解析失败时」建议改为「两个候选 ref 都不可解析时」，避免被读成「merge-base 失败也应走 `--require-base`」（实现实际退回候选 ref）。
- **S2 — Low — ADR-0006 链接**：`docs/adr/ADR-0007-default-base-resolution-for-archive-gate.md:9` 改为纯文本引用或等 PR B 落地后再建链；在 ADR 的依赖/Revisit 段注明「ADR-0006 由 TUI 退役 PR B 提供」。
- **S3 — Low — proposal Non-Goal 措辞**：`proposal.md:80` 的「不改 `--check-archived` 语义」建议补一句「默认 base 变更同样作用于其受保护路径检查；`--check-archived` 只关闭归档点门」。
- **S4 — Nit — 补一条「无消费者时不解析」的测试**：monkeypatch `_resolve_base_ref` 为抛异常，运行 `--check-archived --skip-protected-paths --skip-backlog`，锁定「只在有消费者时解析」的优化承诺。
