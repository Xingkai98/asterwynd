# Building Review: fix-issue-235-completion-gate

## Reviewer

- run id: 3ce1e878-4c98-4067-ade5-acfc48b5c9c8（独立零记忆 subagent，未继承开发上下文）
- 时间: 2026-09-23
- base: `4424f54882179ef1ec53d2eaa1a7d373280b91fb`（origin/master） head: `2c9cef062436f3ffda2c020165627e5d3b02bd26`
- 审阅方法（全部为实跑/实读，作者自述一律不作依据）：
  - 6 个 `git init` 探针仓库（`/tmp/probe235*`、`/tmp/e2e3`、`/tmp/edge235`）复现 `--diff-filter=A` vs `AR`、纯 rename / rename 破裂 / 旧归档补文件 / 非规范目录
  - 4 个端到端 CLI 探针（`/tmp/e2e2`、`/tmp/e2e11`~`/tmp/e2e14`）用 **CI 第一步与第二步的真实命令行参数** 跑 `scripts/check_openspec_artifacts.py`
  - 变异测试 4 条（`cp` 备份 → 改码 → 跑测试 → 还原，`diff -q` 核对还原）
  - 正则参数化探针（tag 13 正例 / 5 反例，checkbox 8 变体）
  - 实跑 `pytest tests/test_openspec_artifact_checker.py`（111 passed）、`tests/agent/workflow/ + test_workflow_guard.py + test_flow_policy.py`（165 passed）、全量 `uv run pytest -q`、`openspec validate --all --strict`（30 passed）、`--check-archived`（93 归档）
  - 在 pristine master（`/tmp/pristine-235`，detached `4424f54`）复现已知环境失败
  - 逐行核对 `scripts/check_openspec_artifacts.py`、`agent/workflow/review_manifest.py`、`.github/workflows/ci.yml` 与 change 文档引用的行号

## Verdict

**CHANGES_REQUESTED**

理由：8 个审阅维度中 7 个通过，issue #235 的**两条绕开路径都已被实测堵住**（见下），4 条变异全部只让对应用例转红。但新门在**它自己新增的那一维度**（未勾任务）留了一个 fail-open 面：归档目录缺 `tasks.md`（或被写成无 checkbox 的散文 / 空文件）时，门**静默返回空**，CI 第一步绿。该面当前语料触发数为 0（93/93 归档都有带 checkbox 的 tasks.md），但它与本 change 要消灭的「留一条 `- [ ]` 自我关闸」是**同一类结构性绕开**（靠「不写 checkbox」而非「不勾 checkbox」），且未进 D7 残余面清单。修复成本极小（见 Issues M1）。

> 明确记录：**核心功能成立**。以下均已实测通过，不构成 CHANGES_REQUESTED 的理由：
> - 问题一（留一条 `- [ ]` 关掉四道门）已堵：`/tmp/e2e2` 端到端——新归档 + 无 `reviews/` + 一条无 tag 未勾任务 → CI 第一步红，同时报 `grill-design.md missing`、`building-review.md missing`、未勾任务三条 ERROR。
> - 问题二（归档路径完全不查）已堵：同上；补齐证据 + 打 tag 后 → `OpenSpec artifact checks passed`（exit 0）。
> - 不追溯既有归档：`--check-archived --skip-protected-paths --skip-backlog` 在真实仓库上 exit 0（93 个归档目录）；新门误挂到该路径时的红海未出现。

## Tasks Verification

### 已勾选任务（2/2 真实存在）

- [x] `tasks.md:5` 跑 grill 产出 `reviews/grill-design.md`（≥3 决策 + User Confirmation）— **真实**。`reviews/grill-design.md` 存在，`## Confirmed Decisions` 9 条、`## Open Questions` 7 条 + 3 条风险，`## User Confirmation` 11 条逐项答复（含 Q1–Q7、风险②、小a/b/c、风险③），无占位文本。
- [x] `tasks.md:6` grill 必答 7 项观察项全部落地 — **逐条核实，7/7 与文档声明一致**：
  - O3 → A′：`assume_implemented` 参数落在 `scripts/check_openspec_artifacts.py:520` / `:734`，三处判据 `:608` / `:759` / `:778`。实跑确认 `check_change` 的调用点 `:1286` / `:1314` **不传参**。
  - O5 → 报错 + debt 双写：`_new_archive_dirs_since_base` 的 `non_conforming` 分支 `:1495-1500` + `docs/known-debt.md` 新增「完成度门禁的残余面（issue #235）」节。
  - O1 → 两条测试：Q1a = `tests/test_openspec_artifact_checker.py:2358`（docs-only 归档豁免）、Q1b = `:2291`（无 `reviews/` 非 docs 归档报 grill 缺失）。
  - O4 → spec delta 展开两个子检查：`specs/dev-workflow-state-machine/spec.md:81` 明写 (1) 自认未完成短语 + (2) `research_tier`↔`status` 闭环与 exempt 证据。
  - O6 → O6a 保留（`:1937` 锁定「有 review 无 manifest → 第二步报」）、O6b 换命题（`:2110` 旧归档新增文件不评估）。
  - O7 → `proposal.md:21` 已更正为 9/3/23 并注明「12 有误，实测为 3」。
  - 风险② → base 树不存在条件 `:1489`；小a → `:2473`；小b → `:2493`；小c → spec delta `:65-70` Scenario「归档点门与 manifest 校验模式互斥」。

### 未勾但已实现（本 change 处于「实现完成、收尾未做」阶段，未勾属正常；逐条核对实现**确实存在**）

- [ ] `tasks.md:17` main() 新增归档点求值（块外 + 显式守卫）— 存在：`:1691-1698`，守卫 `not args.check_archived and not args.change`，**在 `if not args.skip_protected_paths:` 块（`:1701`）之外**。
- [ ] `tasks.md:18` `new_archived_ids` 解析（AR + 正则 + base 树不存在）— 存在：`_new_archive_dirs_since_base:1440`，`ARCHIVE_PATH_RE:102`，`_archive_dir_names_in_base:1510`。
- [ ] `tasks.md:19` 非规范归档目录进 errors — 存在：`:1495-1500`（分类）+ `:1610-1614`（进 errors）。
- [ ] `tasks.md:20` 新门消费 `--require-base` — 存在：`:1598-1603`（`require_base` → 进 errors，否则 stderr WARNING）。
- [ ] `tasks.md:21` 归档点门评估（四道门 + 未勾任务）— 存在：`_check_archived_completion_gate:1518`。
- [ ] `tasks.md:22` building-review 只做存在性 — 存在：`:1573-1581`，未调用 `_check_review_manifests`。
- [ ] `tasks.md:23` A′ 参数化 — 存在：`:520` / `:734` 的关键字参数 + `:608` / `:759` / `:778` 三处判据。
- [ ] `tasks.md:24` 四道门复用现有判定函数（继承豁免）— 存在，且**豁免经实跑断言**（`test_archived_gate_docs_only_archive_is_exempt` / `_bugfix_archive_is_exempt_from_grill` / `_no_spec_delta_does_not_require_building_review` 三条全绿）。
- [ ] `tasks.md:25` `_tasks_all_complete` 扫描放宽 — 存在：`CHECKBOX_RE:105`，`-`/`*`/`+` + `[ ]`/`[x]`/`[X]`。
- [ ] `tasks.md:26` `(post-merge)` tag 解析 — 存在：`POST_MERGE_TAG_RE:108-112`。
- [ ] `tasks.md:27` 未勾任务判定 — 存在：`_untagged_unchecked_tasks:1030`（注意 M1）。
- [ ] `tasks.md:28` `check_change` 一行不动 — **实证**：`git diff origin/master...HEAD -- scripts/check_openspec_artifacts.py | grep check_change` 只命中一处**注释**（`:230` 的 docstring），无代码改动。
- [ ] `tasks.md:32-47` 测试项 — 全部存在（逐条核对测试名，见下「测试覆盖」）。
- [ ] `tasks.md:52-53` AGENTS.md / development-guide.md — 存在，两处均已改（含 `(post-merge)` 语法、归档目录命名、触发点改挂归档点）。
- [ ] `tasks.md:55` spec delta MODIFIED 2 条 — 存在，`specs/dev-workflow-state-machine/spec.md` 完整正文（2 条 MODIFIED Requirement + 10 条 Scenario）。
- [ ] `tasks.md:57` backlog 登记 — 存在（`workflow-events.jsonl` 的 `backlog_updated` 事件 + backlog diff）。

**未勾且**未**实现**：无。

## Issues

- **medium** `scripts/check_openspec_artifacts.py:1030`（`_untagged_unchecked_tasks`）— **归档目录缺 `tasks.md`、或 `tasks.md` 无任何 checkbox 行（散文 / 空文件）时，`_check_archived_completion_gate` 静默返回空**，于是 CI 第一步绿。链路：`_untagged_unchecked_tasks` 在 `tasks.md` 不存在时 `return []`（`:1045-1046`），且 `CHECKBOX_RE` 一条不匹配时循环体不产出任何元素；唯一可能在无 `tasks.md` 时报错的 `_check_design_review_task` 分支（`:773-775` `missing required file: tasks.md`）只在 **grill 证据缺失**时可达（`:761-768` 有 `reviews/grill-design.md` 即提前 `return errors`），所以当 `reviews/` 齐备时它是死分支。**实测（`/tmp/e2e13`，用 CI 第一步真实参数）**：一个本 PR 新建归档的非 docs change，具备合法 RIR、合法 `reviews/grill-design.md`、`reviews/building-review.md`，**但没有 `tasks.md`** → 第一步 `OpenSpec artifact checks passed`（exit 0）；第二步 `--check-archived` 同样 exit 0（归档语境的 `tasks_hash` 已降级为 `sha256:missing` 并被跳过）。`/tmp/e2e14` 另证实「散文式 tasks.md」与「0 字节 tasks.md」两种形态同样静默。**期望**：非 docs 的新归档目录，`tasks.md` 必须存在且含 ≥1 条 checkbox 行（否则报错）——它正是「完成度」这一维度唯一的证据载体，缺了就无从评估，而同门对「无 checkbox 行」的既有口径（`_tasks_all_complete:1006`「A tasks.md with no checkbox lines is treated as incomplete」）已经承认这种输入不构成实现证据。**对照**：spec delta `:11` 明文「未标的未勾选项在归档点评估时 SHALL 报错，SHALL NOT 静默存在」——缺 `tasks.md` 是它的结构性兄弟（靠「不写 checkbox」而非「不勾 checkbox」关闸），且 D7 残余面清单只列了「实现 PR 完全不归档」与「无日期前缀归档」，未涵盖此面。当前语料触发数 **0/93**（93 个归档全部有带 checkbox 的 `tasks.md`），故非阻塞，但按本 change 自己的标准（D7「只记 debt 会留一个既不在 active 也不在任何门的静默面」）应修或至少记账。

- **low** `scripts/check_openspec_artifacts.py:1495-1500` — 非规范归档判定**过宽**：任何 `startswith("openspec/changes/archive/")` 且不匹配日期正则的路径都进 `non_conforming`，包括**归档根目录下的普通文件**。实测（`/tmp/edge235`）新增 `openspec/changes/archive/.gitkeep` → `non_conforming: ['openspec/changes/archive/.gitkeep']`，会被报成「归档目录命名不合规（应为 …<YYYY-MM-DD>-<change-id>/）」并让 CI 红。另实测：向**既有**非规范目录内新增文件（`archive/foo/reviews/building-review-manifest.json`）同样进 `non_conforming`——注意该分支**不受**「base 树不存在」条件约束，故任何触碰历史非规范目录的 PR 都会红。当前语料触发数 0（93/93 带日期前缀、`archive/` 下无普通文件），属**潜在假阳性**而非现行缺陷。期望：把判定收敛到「`archive/` 下第一段路径是非目录语义的目录名」（例如要求匹配 `^openspec/changes/archive/[^/]+/` 且该段不含 `.`），或在 known-debt 记一笔说明这是有意的严格化。

- **low** `scripts/check_openspec_artifacts.py:1090`（`_protected_artifact_explanation_errors`，**本 PR 未改动**）— 在**被审阅的 revision（HEAD = `2c9cef0`）**上，本 change 改了受保护文件 `docs/known-debt.md`，但 `openspec/changes/fix-issue-235-completion-gate/workflow-events.jsonl` **只有一条 `backlog_updated`（seq 1）**，**没有** `protected_artifact_explained`（`git show HEAD:… | wc -l` = 1）；`tasks.md:54` 承诺写该事件，仍是 `[ ]`。HEAD 上 CI 之所以绿，是因为该函数用 `changes_root.rglob("workflow-events.jsonl")` **全仓搜索**，命中了**别的** change 的陈旧事件（`openspec/changes/archive/2026-09-22-fix-issue-229-231-debt-wording/workflow-events.jsonl`，`artifact_path: "docs/known-debt.md"`）。**实测隔离**（`/tmp/pa235_False` / `_True`）：只放本 change 的事件 → 报 `protected path 'docs/known-debt.md' changed without workflow event explanation`；加上那条陈旧事件 → GREEN。二者行为逐字节复现。属**既存机制弱点**（不在本 PR 的 diff 内，`_event_covers_artifact_path` / `_validate_protected_artifact_event` 均未被改动），故不判缺陷；但必须记录：**CI 绿不等于承诺的证据存在**。
  - **审阅过程中工作区发生了并发未提交改动（`git status` 从 clean 变为 ` M workflow-events.jsonl`）**：该文件被追加了 `seq 2 protected_artifact_explained`（`artifact_path: "docs/known-debt.md"`，`reason` + `approved_by` 齐备）——正是本 issue 要求的修复，但**尚未 commit 到被审阅的 HEAD**。审阅结论以 HEAD 为准；提交后本 issue 即消解（无需再改）。提请作者注意：审阅期间有其他进程在同一 worktree 写入，最终 manifest 应以含该事件的 head 为准。

- **info** `scripts/check_openspec_artifacts.py:108-112`（`POST_MERGE_TAG_RE`）— tag 必须紧邻 checkbox（中间只允许编号/粗体），行尾追加写法不被识别。实测：`- [ ] (post-merge) 收尾` / `- [ ] 5.5 (post-merge) 收尾` / `- [ ] **6.9** (post-merge)` 豁免；但 `- [ ] 收尾：给 issue #235 添加 comment 并关闭。(post-merge)` 与 `- [ ] 5.5 收尾：关 issue (post-merge)` **不豁免**。方向是 **fail-closed**（会报错提示，不是静默放行），与 design D4 的声明语法、AGENTS.md/开发指南示例、`tasks.md:71` 的既有写法一致，故不是缺陷；仅提示这是使用者最易踩的写法差异。

## Test Results

| 命令 | 结果 |
|---|---|
| `uv run pytest -q tests/test_openspec_artifact_checker.py` | **111 passed** in 11.76s |
| `uv run pytest -q tests/agent/workflow/ tests/test_workflow_guard.py tests/test_flow_policy.py` | **165 passed** in 21.86s |
| `uv run pytest -q`（全量） | **8 failed, 2948 passed, 10 skipped** in 548.92s → 8 条全为已知环境失败（见下） |
| `npx @fission-ai/openspec@1.4.1 validate --all --strict` | **30 passed, 0 failed** |
| `uv run python scripts/check_openspec_artifacts.py --check-archived --skip-protected-paths --skip-backlog`（真实仓库 93 归档） | exit 0，stderr 一行 `tasks_hash 已按归档语境跳过（45 个 change）` |
| `uv run python scripts/check_openspec_artifacts.py`（本分支默认参数） | exit 0 |

**已知环境失败（非本 change 引入）**——与提示清单逐项吻合，前 4 类中 2 类我另在 pristine master 复现：

- `tests/agent/memory/test_persistent.py::TestFindScopeRoot::{test_returns_none_for_non_git_dir, test_malformed_git_file_falls_back_to_scan}` — 已在 `/tmp/pristine-235`（detached `4424f54`）复现 **2 failed, 3 passed**。
- `tests/agent/tools/test_factory_sandbox_wiring.py::TestBuildSandboxFromConfig::test_docker_backend`、`tests/agent/tools/test_sandbox_backends.py::TestBackendSelection::test_docker_backend_available` — 无 docker。
- `tests/web_tests/test_workflow_graph_browser.py::{test_workflow_graph_pan_and_zoom, test_graph_recursion_exceeded_still_draws_graph_with_notice, test_click_any_node_opens_detail_drawer, test_legend_is_visible_and_collapsible}` — 浏览器 flaky（本次因无 chromium 而真跑并失败；CI 装 chromium 后路径不同）。
- 本次全量运行中 `test_tree_sitter_symbols.py::test_tree_sitter_extracts_java_and_kotlin_symbols` **未**失败（可能被 skip），不改变结论。

**判别性主张逐条实跑结果**（全部证实，无一条证伪）：

1. `--diff-filter=AR` 必要性 — **成立**。`/tmp/probe235`：`git mv` 整目录后 git 报 `R100`，`A` 侧输出 **空**、`AR` 输出完整 archive 路径（正是「A-only 会漏」）。`/tmp/probe235b`（rename 破裂：`tasks.md` 重写 400 行）：`name-status` 给 `R100 proposal.md` + `A tasks.md` + `D tasks.md`，`A` 侧只带 `tasks.md`、`AR` 侧两条都带 ⇒ AR 是唯一稳妥选择。
2. 「base 树不存在」条件 — **成立且必要**。`/tmp/probe235c`：向**既有**归档目录补 manifest（`A` 路径，正则命中）→ 模块返回 `(['2026-09-23-new-change'], [], None)`，旧 id 被排除。变异测试反证：去掉该条件 → `test_archived_gate_ignores_file_added_to_existing_archive` 转红（1 failed / 110 passed）。
3. A′ 未改变 active 行为 — **成立**。`check_change` 无代码改动（只有注释）；默认参数 `False`（`:525` / `:738`）；`test_partial_change_does_not_require_building_review` 单独实跑 **1 passed**。归档侧传 `True` 后四道门确实不降级：`/tmp/e2e2` 上「无 `reviews/` + 一条无 tag 未勾」同时报 grill 证据缺失 + building-review 缺失 + 未勾任务；`test_archived_gate_requires_grill_evidence_even_when_tasks_incomplete` 更直接对照了同一 fixture 在 `archived` 语义（`[]`，静默）与 `assume_implemented` 语义（报缺）下的分歧。
4. `(post-merge)` 正则 — **8/8 声明变体全部豁免**（含全角 `（post-merge）`、`(POST-MERGE)`、`+ [ ]`、`* [ ]`、缩进子项），另加 5 条变体（`( post-merge )`、`**6.9 (post-merge)**` 等）亦通过；**5/5 反例均正确不豁免**（无括号 / `pre-merge` / `postmerge` / `xpost-merge` / 无 tag）。**无 tag 的未勾行仍报错**（`test_archived_gate_tag_negative_cases_still_reported` 3 反例全绿，豁免未漏成 fail-open）。
5. 新门位置与守卫 — **成立**。(a) 真实 CLI 跑 `--skip-protected-paths` → exit 1（4 条 ERROR），关不掉；(b) `--check-archived` 不触发（`test_main_skips_archived_gate_in_check_archived_mode`）；(c) `--change <id>` 不触发（`test_main_skips_archived_gate_for_single_change_mode`）；(d) base 不可解析 ∧ `--require-base` → 真实 CLI **exit 1**，不带该 flag → exit 0 + stderr WARNING（不静默放行）。
6. building-review 只做存在性 / design D2 的**修正后理由** — **修正理由是对的**。把归档目录喂给 `_check_review_manifests(..., archived=False)` 实报 `review manifest missing: /tmp/probe235d/openspec/changes/demo/reviews/building-review-manifest.json`（**active 路径**，`openspec/changes/demo` 不存在），根因确在 `review_manifest.py:34-36` 的 `change_dir_for(..., archived=False)` 解析，`tasks_hash` 那行走不到。原 design 的「tasks_hash mismatch」理由确系错误。spec delta **未**固化错理由（`grep tasks_hash` 无命中）。
7. 非规范归档目录报错 — **成立**：`/tmp/probe235`/`edge235` 中 `archive/foo/proposal.md` 进 `non_conforming`，`test_archived_gate_bad_dir_path_is_reported_by_main` 端到端锁到 `main()` 的 exit 1（不是只在 helper 可见）。附带发现见 Issues low 第 2 条。
8. 不追溯既有归档 — **成立**：真实仓库 `--check-archived` exit 0（93 个归档）。

**变异测试抽验 4/4（超过要求的 2 条）**，每条只让对应用例转红，修改后均已 `cp` 还原并 `diff -q` 核对（`scripts/` 工作树干净，`git status --porcelain scripts/` 无输出）：

| 变异 | 结果 |
|---|---|
| `--diff-filter=AR` → `A` | `test_archived_gate_ar_catches_pure_rename_where_a_only_misses` 红；1 failed / 110 passed |
| 去掉 `POST_MERGE_TAG_RE.match` 分支 | 9 条 tag 豁免用例红；9 failed / 102 passed |
| 去掉「base 树不存在」条件 | `test_archived_gate_ignores_file_added_to_existing_archive` 红；1 failed / 110 passed |
| 把新门挂到 `--check-archived`（去掉 `not args.check_archived`）| `test_main_skips_archived_gate_in_check_archived_mode` 红；1 failed / 110 passed |

## 结论

**CHANGES_REQUESTED**，一条中等项（Issues M1）需修或至少记账，其余全部通过。

这个 change 的**核心主张经得起独立复核**：`--diff-filter=AR` 是必要的（纯 rename 实测 A 侧为空）、「base 树不存在」条件真实排除了旧归档误伤、A′ 参数化确实一行没动 `check_change`（只改了注释）且归档侧四道门不因未勾项降级、`--skip-protected-paths` 关不掉新门、base 不可解析时 fail-closed、既有 93 个归档不被追溯、design 里那处理由修正（active 路径解析而非 `tasks_hash`）经实跑证实是对的、spec delta 也没把错理由写进去。4 条变异各只打红对应用例，说明测试对实现有真实判别力而不是同义反复。issue #235 记录的两条绕开路径在端到端探针上都被堵死。

唯一的保留意见是新门在「未勾任务」这一维度自己留了一个静默面：把 `tasks.md` 整个删掉、或写成不含任何 checkbox 的散文/空文件，门就无从评估完成度并直接放行（`/tmp/e2e13` 用 CI 第一步真实参数实测 exit 0）。它当前触发数 0/93，不是已发生的危害，但它与「留一条 `- [ ]` 自我关闸」属于同一类结构性绕开，而 D7 的残余面清单没有涵盖它——按本 change 自己立的标准（静默无门必须消灭或显式记账），应补一个「非 docs 新归档必须存在含 checkbox 的 `tasks.md`」的检查，或在 known-debt 里显式记一笔。次要项：非规范归档判定会把 `archive/` 下的普通文件（如 `.gitkeep`）也报成命名不合规（潜在假阳性，当前语料 0 命中）；以及 HEAD 上 `docs/known-debt.md` 的受保护证据事件尚未 commit（CI 之所以绿是命中了旧 change 的陈旧事件——审阅期间已出现补写该事件的未提交改动，提交即消解）。
