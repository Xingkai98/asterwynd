# Building Review: round-model-align

## Reviewer
- run id: building-review-round-model-align-2026-10-17
- 时间: 2026-10-17（UTC）
- 零记忆: 是
- 审阅基线: `origin/master` = `d0197b1`；`HEAD` = `8b5a696`（分支 `round-model-align/2026-10-17`）
- 依据: 仓库文件、`git diff origin/master...HEAD`、witnessloop 远端 `main`（`https://github.com/Xingkai98/witnessloop` 的 `templates/review-loop.md` 与 `templates/grill.md`，经 `gh api` 现场读取）、测试原始输出。本地 `/home/happy/witnessloop` 工作副本停留在旧版（`ae99256`，模板仍是 3 轮封顶），**未**作为权威依据；权威依据为远端 `main`。

## 本轮判定（verdict）
**PASS**（初次开批；medium+ 批次为空）。

### 任务逐项验证

> 5.x–7.x、V5、V7 是本 change 自己的收尾步骤，按审阅约定尚未执行，**不构成本批缺陷**；其余项逐项读文件/跑命令核验。

| 任务 | 结果 | 证据（文件:行 / 命令输出） |
|---|---|---|
| 0.1 grill 决策记录 | ✅ | `reviews/grill-design.md` 存在；`## Confirmed Decisions` 6 条，每条同行带 `来源:`（`:9-14`）；`## Open Questions` 为「（无）」（`:31-32`）；`## User Confirmation` Q1–Q4 存在（`:45-49`） |
| 0.2 witnessloop stage 核对 | ✅ | `reviews/grill-design.md:18-19` 记录 `grill` 恒要求 + `code_hits` 触发 `grill-adversarial`/`building`，带 `witnessloop/src/witnessloop/checkcmd.py` 证据；`design.md:33-35` 写三份 manifest |
| 0.3 设计阶段对抗闭环 | ✅ | `reviews/grill-adversarial.md` 存在；R1 开批 4 条 medium+（`:19-22`）、逐条验证 4/4（`:26-31`）、收口确认 0 条（`:59-63`）、闭环出口 `PASS`（`:65-66`） |
| 0.4 停轮检查 | ✅ | `grill-design.md` Open Questions 为「（无）」；`grill-adversarial.md` 出口 `PASS`；`design.md:288-326` 回填结论 |
| 0.5 结论回填 design | ✅ | `design.md:288-326` `## Pre-Implementation Review`，含 G1–G8 与设计环 R1-1–R1-4 记录 |
| 0.6 用户拍板参数 | ✅ | `reviews/grill-design.md:45-49` 记录轮定义 / 20 上限 / medium+/low / 两环共用四项 |
| 1.1 allowlist 测试 | ✅ | `tests/test_round_model_alignment.py:23-32` 八个显式 allowlist 文件 |
| 1.2 per-file 映射 | ✅ | `:36-90` 逐文件核心要素映射；`uv run pytest -q tests/test_round_model_alignment.py` = 28 passed |
| 1.3 旧口径词表 | ✅ | `:93-104` 10 个旧词；`:129-135` 断言不在场；测试通过；`git grep` 复核规范面干净 |
| 1.4 checker 提示断言 | ✅ | `:158-165` 新提示在场、旧提示不在场；AST 对比（字符串常量归一化）与 `origin/master` **完全相同**；diff 仅 3 个 hunk，均为提示字符串 |
| 1.5 先红输出记录 | ⚠️ 已达成（原记录缺失） | 测试当前 28 passed；仓库中此前无 `building-review.md`，故「先红」原始输出无落盘证据。本报告独立复核：在临时副本移除 `AGENTS.md` 的「非空 medium+ 批次」后 `1 failed, 27 passed`（见测试结果）。登记 R1-L2 |
| 1.6 变异验证 | ⚠️ 已达成（原记录缺失） | 同上；独立变异：向临时副本 `README.md` 注入「无轮数上限」后 `1 failed, 27 passed`。登记 R1-L2 |
| 2.1 AGENTS 设计环 | ✅ | `AGENTS.md:18` 已改为有界批次模型（轮定义、冻结、deferred、20、三出口、写码前置、frontier 豁免） |
| 2.2 AGENTS 实现环 | ✅ | `AGENTS.md:104` 含 20 已收口轮、三出口、「`CHANGES_REQUESTED` 不是出口」 |
| 2.3 README 双语 | ✅ | `README.md:148` 与 `README_EN.md:148` 同一句流水线图同改，语义一致 |
| 2.4 requirements-process | ✅ | `docs/requirements-process.md:45`（实现环）、`:189`（设计环）均为批次模型，含两环共用与写码前置 |
| 2.5 Q14 | ✅ | `docs/interview-script/questions/Q14-dev-process.md:13,:56` 已改；`:17` 的 #99「3 轮审阅」历史案例保留原文 |
| 2.6 checker 仅改提示 | ✅ | `scripts/check_openspec_artifacts.py` diff 3 hunk（`:1139,:1623,:1640`），全部为字符串；AST 归一化后与 base 相同 |
| 3.1 dev-workflow delta | ✅ | delta `:3-17` REMOVED、`:19-116` MODIFIED、`:118-313` ADDED；`openspec validate --all --strict` = 30 passed |
| 3.2 change-doc delta | ✅ | delta MODIFIED Requirement 与当前规格 `Pre-implementation design grilling` 正文逐字一致（脚本比对 `True`） |
| 3.3 当前规格同步 | ✅ | 当前 `dev-workflow-state-machine` Requirement 数 = 12（事件记 12→12）；`change-documentation` = 14；旧「终止条件为收敛」Requirement 不存在；ADDED Requirement 与 delta 逐字一致（比对 `True`）；事件 seq 3/4 见工作区观察 |
| 3.4 strict validate | ✅ | `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` → `Totals: 30 passed, 0 failed (30 items)` |
| 4.1 全量 pytest | ✅ | `2 failed, 4498 passed, 9 skipped in 508.16s`——与 tasks 读数完全一致；两条失败均为 `TestFindScopeRoot`，见测试结果 |
| 4.2 artifact checker | ✅ | `PYTHONPATH=. uv run python scripts/check_openspec_artifacts.py` → `OpenSpec artifact checks passed` |
| 4.3 git grep 复核 | ✅ | 全仓旧口径命中仅出现在本 change 的解释性文档/测试词表，以及 benchmark 的不相关 `per-round cap`；规范面无命中 |
| 4.4 本地入口同步 | ✅ | `/home/happy/my-agent/.claude/commands/review-loop.md`（批次模型/20/deferred/三出口）与 `grill.md`（对抗环/frontier/20/写码前置）均已改；两文件 grep 无旧口径词 |
| V1 规范面 | ✅ | 文档守卫 28 passed；per-file 映射逐项在位 |
| V2 dev-workflow 规格覆盖 | ✅ | 当前规格 `:445-643` 覆盖轮定义、批次冻结、验证禁提新问题、deferred、medium+ 全修、low/nit 理由、20 上限与收口确认、三出口、两环共用 + frontier 豁免、机械门禁不新增正文解析 |
| V3 change-doc 规格 | ✅ | 当前规格含 `bounded-batch`，不含 `no fixed round limit` / `until convergence` |
| V4 机械验证 | ✅ | validate 30/0；checker 0 errors；pytest 读数与 tasks 一致 |
| V6 本地入口 | ✅ | 同 4.4；`review-loop.md` 6 处、`grill.md` 4 处新模型要素命中，0 旧口径命中 |

### 初次开批 · 收口确认

- 审阅时间: 2026-10-17（UTC）
- 范围: `git diff origin/master...HEAD` 全部 18 个文件；`proposal.md` / `design.md` / `tasks.md` / 两份 delta / 两份当前规格 / 两份 grill 证据 / 检查器 / 新增测试；与 witnessloop 远端 `main` 两份模板逐段对照。
- **medium+ 批次：空（0 条）⇒ `PASS`，不进入修复、不消耗轮数。**
- 验证期/deferred：不适用（初次开批）；deferred 0 条。

### low / nit 登记

| id | severity | 处置（已修 / 登记不修） | 理由 |
|---|---|---|---|
| R1-L1 | low | 登记不修 | `AGENTS.md:18` 在「不计入 20。」后多了一个反引号：``；`checker 对完成 change…``，破坏该分句的行内代码/加粗渲染。属一行 typo，不影响规则语义。 |
| R1-L2 | low | 登记不修 | tasks 1.5/1.6 标 `[x]`，但其承诺的「先红原始输出 / 变异结果记入 `reviews/building-review.md`」在本报告产生前不存在（`git log --all` 无该文件）。本报告已独立复核守卫可变红：临时副本分别移除 `AGENTS.md` 必需的「非空 medium+ 批次」、向 `README.md` 注入「无轮数上限」，两次均为 `1 failed, 27 passed`。建议主 agent 收尾时引用本报告测试节，或补一条记录。 |
| R1-L3 | low | 登记不修 | `tests/test_round_model_alignment.py:168-173` 的 `test_local_entry_is_not_required_in_version_control` 实际不校验任何东西：本地文件不存在时直接通过，存在时其绝对路径天然不在 `ROOT` 下。这是一个恒真断言，且把开发者本机路径写进仓库测试；建议删除或改为真正的同步检查（例如对仓库内命令模板做断言）。 |
| R1-L4 | nit | 登记不修 | `AGENTS.md:104` 与 `docs/requirements-process.md:45` 的摘要未写「第 20 轮自身达到验证重试终止点 ⇒ 超上限 `BLOCKED`」这一条（完整口径在规格 `:143`、`:172-174` 与两份模板中）。per-file 映射有意只钉核心要素，属摘要省略，不构成规格偏离。 |
| R1-L5 | nit | 登记不修（观察） | 评审期间工作区出现 `openspec/changes/round-model-align/workflow-events.jsonl` 的未提交改动：追加 seq 3/4（两条 `current_spec_synced`，mtime 16:35:31，HEAD 中只有 seq 1/2）。内容与 tasks 7.2 要求一致，且**非本审阅者写入**；收尾生成 manifest / 最终 head 前必须提交，否则 manifest 会绑在未含事件的 revision 上。 |
| R1-L6 | nit | 登记不修 | `design.md` Decision 8（`:220`）写 `AGENTS.md` 映射为「验证禁提新问题/deferred」，实际测试只断言 `deferred`（`tests/test_round_model_alignment.py:41`）。映射粒度轻微不一致，不影响可执行性（此前设计环 R2-L5 已登记同类项）。 |

### 测试结果

1. `uv run pytest -q tests/test_round_model_alignment.py`
   ```
   28 passed in 0.11s
   ```
2. 文档守卫变红（临时目录副本，不改工作区）：
   - 移除 `AGENTS.md` 全部「非空 medium+ 批次」（原出现 2 次）：
     ```
     FAILED tests/test_round_model_alignment.py::test_normative_surface_contains_batch_model[AGENTS.md-needles0]
     1 failed, 27 passed in 0.18s
     ```
   - 向 `README.md` 追加「无轮数上限」：
     ```
     FAILED tests/test_round_model_alignment.py::test_normative_surface_drops_old_round_model[README.md]
     1 failed, 27 passed in 0.13s
     ```
3. `uv run pytest -q tests/test_openspec_artifact_checker.py`
   ```
   130 passed in 5.63s
   ```
4. `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`
   ```
   Totals: 30 passed, 0 failed (30 items)
   ```
5. `PYTHONPATH=. uv run python scripts/check_openspec_artifacts.py`
   ```
   OpenSpec artifact checks passed
   ```
6. `uv run pytest -q`（全量）
   ```
   2 failed, 4498 passed, 9 skipped, 110 warnings in 508.16s (0:08:28)
   FAILED tests/agent/memory/test_persistent.py::TestFindScopeRoot::test_returns_none_for_non_git_dir
   FAILED tests/agent/memory/test_persistent.py::TestFindScopeRoot::test_malformed_git_file_falls_back_to_scan
   ```
   两条失败为环境既有问题，与本 change 无关：
   - `tests/agent/memory/test_persistent.py` 在 diff 中完全未改（最后修改提交 `8a255b0`，早于本分支）；
   - 本机存在 `/tmp/.git`（空目录，mtime 2026-09-21），`_find_scope_root` 因而把 `/tmp` 当作 scope root，测试断言 `None` 失败。失败原因与 tasks 4.1 描述一致。

7. witnessloop 权威口径核验：远端 `main` 的 `templates/review-loop.md`（一轮 = 非空 medium+ 批次；20 个已收口轮；deferred；severity 冻结；验证重试终止点；三出口；`CHANGES_REQUESTED` 非出口；按 change/环计数；id 规则；报告 schema）与 `templates/grill.md`（两环同构、frontier 豁免、设计环 `BLOCKED` 非写码许可、修复证据三选一）逐段对照，本 change 的规格与规则面**未发现语义偏差**。

### TDD 证据（主 agent 补记，2026-10-17）

> 补记原因：tasks 1.5/1.6 承诺把先红与变异输出记入本报告，但报告此前不存在（R1-L2）。
> 以下为实施时的原始输出摘要，供复核。

- **先红（实现前）**：`uv run pytest -q tests/test_round_model_alignment.py` →
  `19 failed, 9 passed in 0.40s`（新模型要素尚未落地、旧口径仍在）。
- **变异验证**：临时把 `AGENTS.md` 的「最多 **20 个已收口轮**」改为「无轮数上限」→
  `1 failed, 27 passed in 0.12s`；恢复后 `28 passed`。

## 闭环出口
PASS（初次开批批次为空；累积 low/nit 见上表，均不阻塞收口）。
