# Building Review: retire-manifest-check

## Reviewer

- run id: `review-retire-manifest-check-2026-10-17-r0`（独立零记忆审阅侧，初次开批）
- 零记忆: 是
- 审阅基线: `origin/master` = `1d6cfee`；HEAD = `b9f1b93a68c9dca2f897709366268ab509ab44d3`
- 依据（亲自读取 / 实跑）:
  - change 文档：`proposal.md` / `design.md` / `tasks.md` / `reviews/grill-design.md` /
    `reviews/grill-adversarial.md` / 三份 `specs/*/spec.md` delta；
  - 实现：`git diff origin/master...HEAD`（26 文件，+1999/−311）、
    `scripts/check_openspec_artifacts.py:1089-1220,1632-1761,1764-1845`、
    `tests/test_retire_manifest_check.py`、`tests/test_openspec_artifact_checker.py` 的 diff；
  - 规格 / 文档：`openspec/specs/{dev-workflow-gate,dev-workflow-state-machine,platform-gate}/spec.md`、
    `AGENTS.md`、`README.md`/`README_EN.md`、`docs/development-guide.md`、
    `docs/requirements-process.md`、`docs/known-debt.md`、
    `docs/adr/ADR-0004-retire-duplicate-review-manifest-check.md`、`.github/workflows/ci.yml`；
  - 只读基准：`agent/workflow/review_manifest.py`（diff 为空，未修改）。
- 实跑命令与原始输出（摘要）:

```text
$ git rev-parse HEAD && git rev-parse origin/master
b9f1b93a68c9dca2f897709366268ab509ab44d3
1d6cfee2f34478732607fa542bb7ba0c07137b17

$ uv run pytest -q tests/test_retire_manifest_check.py \
    tests/test_openspec_artifact_checker.py tests/agent/workflow/test_review_manifest.py \
    tests/test_workflow_state_cli.py tests/test_workflow_archive_write_channel.py \
    tests/test_workflow_protected_write_channel.py
205 passed in 85.52s

$ PYTHONPATH=. python3 scripts/check_openspec_artifacts.py --change retire-manifest-check
OpenSpec artifact checks passed          (EXIT=0)

$ PYTHONPATH=. python3 scripts/check_openspec_artifacts.py \
    --check-archived --skip-protected-paths --skip-backlog
OpenSpec artifact checks passed          (EXIT=0；stderr 无 tasks_hash 汇总)

$ npx --yes @fission-ai/openspec@1.4.1 validate --all --strict
Totals: 30 passed, 0 failed (30 items)   (EXIT=0)

$ git diff origin/master...HEAD -- agent/workflow/review_manifest.py | wc -l
0

$ grep -c '两套并存' openspec/specs/dev-workflow-gate/spec.md
0
```

- 补充实跑（任务 5.2 复核，见 R0-1）:

```text
$ git rev-parse master
3c7196b2531f41bd6c559c678a3101d2d6342a09      # 落后 origin/master 79 个提交
$ PYTHONPATH=. python3 scripts/check_openspec_artifacts.py
ERROR: 2026-10-13-web-agent-group-chat: reviews/building-review.md 缺少 `## 闭环出口` ……
ERROR: 2026-10-13-witnessloop-adoption: reviews/building-review.md 缺少 `## 闭环出口` ……
ERROR: 2026-10-14-guard-write-allowlist: reviews/building-review.md 缺少 `## 闭环出口` ……
ERROR: 2026-10-17-review-loop-no-round-cap: reviews/building-review.md 缺少 `## 闭环出口` ……
ERROR: 2026-10-17-stage-c-required-switch: reviews/building-review.md 缺少 `## 闭环出口` ……
(5 条 ERROR；EXIT=1)

$ PYTHONPATH=. python3 scripts/check_openspec_artifacts.py --base-ref origin/master
OpenSpec artifact checks passed          (EXIT=0)
```

## 本轮判定（verdict）

CHANGES_REQUESTED

### 任务逐项验证

| 任务 | 结果 | 证据（文件:行 / 命令输出） |
|---|---|---|
| 0.1 grill 证据 ≥3 决策、Open Questions/User Confirmation 无条件存在 | ✓ | `reviews/grill-design.md:3-36`（D1–D8）、`:30-36`（无 Open Question，User Confirmation 在场） |
| 0.2 删除面 / 保留面 / 历史边界 / 第二刀边界逐项确认 | ✓ | `grill-design.md:5-12`；`design.md:54-66,116-139,141-152` |
| 0.3 设计对抗闭环收敛到 PASS | ✓ | `reviews/grill-adversarial.md:162-204`（R0-1..R0-5 全修，0 条 medium+ ⇒ PASS） |
| 0.4 停轮检查 | ✓ | `grill-design.md:30-36`；`design.md:191-225` |
| 0.5 grill 结论回填 design | ✓ | `design.md:191-225` |
| 1.1 parser 正反用例 | ✓ | `tests/test_retire_manifest_check.py:88-124`（标题后缀 / fenced / 加粗 / `PASS（…）` / `PASSED` / 占位行 / `不是 PASS` / 未定 / 多小节） |
| 1.2 旧用例改写 + partial/docs 宽触发用例 | ✓ | `tests/test_openspec_artifact_checker.py:199-209,256-278`；`tests/test_retire_manifest_check.py:154-193` |
| 1.3 `--check-archived` 退役用例 | ✓ | `tests/test_retire_manifest_check.py:244-312` |
| 1.4 归档点门用例 | ✓ | `tests/test_retire_manifest_check.py:196-238` |
| 1.5 文档守卫测试 | ✓（弱于任务表述，见 L3） | `tests/test_retire_manifest_check.py:315-355` |
| 1.6 先红运行留痕 | 未能独立复核（无仓库留痕），测试现为绿 | `uv run pytest -q tests/test_retire_manifest_check.py` → 33 passed |
| 2.1 删除 `_check_review_manifests` / 两处调用 / 两个死代码 helper | ✓ | diff 删除 `scripts/check_openspec_artifacts.py` 旧 `:1000-1015,1105-1153`；`grep` 全仓无 `_repo_root_for_change_dir` / `_change_id_from_dir_name` 残留 |
| 2.2 新增三函数 + 四规则 | ✓ | `scripts/check_openspec_artifacts.py:1089-1186`；实测：占位行→`ambiguous`、`PASSED`/`不是 PASS`→`empty`、多小节→`duplicate`、fenced→忽略、`**PASS**（…）`/`> PASS`/`` `PASS` ``→`ok PASS` |
| 2.3 active 宽触发 + 完成面 | ✓ | `:1189-1220`；`check_change` 调用点 `:1417-1420` |
| 2.4 归档点复用 + `--check-archived` 收窄 + `change_type is None ⇒ continue` | ✓ | `:1683-1700`；`:1807-1823`（保留 skip 分支与注释） |
| 2.5 help / 注释 / docstring 同步；其它门未动 | ✓ | `:1787-1792`、`:1632-1649`、`:1702-1706`、`:1826-1833`；diff 未触及 RIR / Impact / benchmark / backlog / 受保护路径 / grill 证据逻辑 |
| 2.6 CI 仅改名称 / 注释 | ✓ | `.github/workflows/ci.yml:90-99`（命令与 flag 未变，`test_ci_validate_job_runs_check_archived` 通过） |
| 2.7 本地 review-loop 入口全文件同步 | ✓（仓外文件，gitignored） | `/home/happy/my-agent/.claude/commands/review-loop.md:99-135,153-172`；无 `write_review_manifest` / `building-review-manifest` |
| 3.1–3.5 规则文档 | ✓ | `AGENTS.md:24,108-115,203,224`；`README.md:153` 与 `README_EN.md:153` 同句；`docs/development-guide.md:292-314,361`；`docs/requirements-process.md:45,54,293`；`Q12-ci-testing.md:10,44`；`Q14-dev-process.md:13-44` |
| 3.6 known-debt 新增记录 + 标注既有四处 | ✓ | `docs/known-debt.md:25`、`:31-35`、`:161-165`、`:240-242`、`:514-537` |
| 3.7 全仓 grep 复核 | ✓ | 规范面仅剩 legacy/历史说明；当前 spec `两套并存` 计数 0 |
| 3.8 ADR | ✓ | `docs/adr/ADR-0004-retire-duplicate-review-manifest-check.md:1-68`（≥2 备选、Consequences、Revisit） |
| 4.1 gate delta（RENAMED + MODIFIED） | ✓ | `openspec/changes/.../specs/dev-workflow-gate/spec.md:3-6,10-12`；current spec `:129-144` 已改名 |
| 4.2 state-machine delta（REMOVED + ADDED + MODIFIED） | ✓ | delta `:3-9,11-125,210-281`；current spec 删除旧 Requirement、新增 `Review evidence 与终结 verdict` |
| 4.3 platform-gate delta | ✓ | delta `:3-7`；current spec `:73` 已移除 review manifest 例子 |
| 4.4 施加进 current spec + `两套并存`=0 + 事件 | ✓ | `workflow-events.jsonl` seq 3–5（`current_spec_synced` ×3）；`grep -c` = 0 |
| 4.5 strict validate | ✓ | 30 passed, 0 failed |
| 4.6 current spec 悬空交叉引用 | ✓ | `openspec/specs/dev-workflow-gate/spec.md:45` 已指向新标题 |
| 5.1 全量 pytest | 未勾（由主 agent 另跑，不属本轮强制项） | — |
| 5.2 全量 checker → 0 errors | ✗ **见 R0-1**：本工作区默认 base（`master`）落后时 exit 1（5 条历史归档误红）；仅 `--base-ref origin/master` 为 0 errors | 原始输出见上 |
| 5.3 `--check-archived` 仍 exit 0 且无 tasks_hash 汇总 | ✓ | EXIT=0；stderr 无 `tasks_hash` 行 |
| 5.4 变异验证 | 无法独立复核（无留痕）；对应回归测试在位 | `test_completed_feature_with_blocked_exit_is_rejected`（`tests/test_retire_manifest_check.py:136-139`）会在接受 BLOCKED 时变红 |
| 6.1 / 6.2 实现后审阅闭环 | 未勾（本轮即 6.1/6.2 的开批） | 本报告 |
| 7.1–7.3 witnessloop 三份 manifest / check / 归档后重建 | 未勾（内容提交后动作，预期） | — |
| 7.4 / 9.x `(post-merge)` | 未勾（post-merge，豁免） | `tasks.md:71,83-85,95` |
| 8.1–8.5 收尾 | 未勾（归档前动作，预期） | `tasks.md:75-79` |
| V1 `review_manifest.py` 未修改 | 未勾；复核成立 | `git diff … -- agent/workflow/review_manifest.py` 0 行 |
| V2 BLOCKED / 缺失 / 不唯一被拒、PASS 通过 | 未勾；复核成立 | 上述 parser / active / 归档点测试 |
| V3 `--check-archived` 只做可投影校验 | 未勾；复核成立 | `tests/test_retire_manifest_check.py:274-312`；实跑 EXIT=0 |
| V4 其它门行为不变 | 未勾；复核成立 | diff 仅触及本 change 声明的面；旧测试全绿（205 passed） |
| V5 规范面只要求 witnessloop 形态 | 未勾；复核成立 | 文档守卫测试通过；grep 无 ast 要求 |
| V6 三份 witnessloop manifest + gate/check 绿 | 未勾（见 7.x） | — |
| V7 `(post-merge)` | 未勾（豁免） | `tasks.md:95` |

### 初次开批 · 批次

| id | severity | 锚点 | 问题 |
|---|---|---|---|
| R0-1 | medium | `scripts/check_openspec_artifacts.py:1683-1700,1739-1761,1770,1832-1843`；`AGENTS.md:131`；`docs/requirements-process.md:261,290`；`openspec/changes/retire-manifest-check/tasks.md:57`；`docs/development-guide.md:363`（相关） | **本地默认 base 落后时，新 verdict 完成面会追溯打红历史归档**：`--base-ref` 默认 `master`，而本工作区 `master` 落后 `origin/master` 79 个提交，`_new_archive_dirs_since_base` 把 6 个历史归档目录当成「本 PR 新建」，新增的 `## 闭环出口` 完成面检查对其中 5 个旧格式报告报错 → 仓库文档推荐的本地全量校验命令 exit 1；与「历史归档不追溯」承诺及 task 5.2 的 `[x] → 0 errors` 证据直接矛盾。 |

**R0-1 失败场景（输入 / 状态 → 错误行为）**

- 输入/状态：任意 checkout 的本地 `master` 落后于 PR base（本工作区实测 `master=3c7196b`、
  `origin/master=1d6cfee`，落后 79 个提交；`git worktree` 新建/长期未快进都会如此）。此前
  合入的 `2026-10-13-web-agent-group-chat`、`2026-10-13-witnessloop-adoption`、
  `2026-10-14-guard-write-allowlist`、`2026-10-17-review-loop-no-round-cap`、
  `2026-10-17-stage-c-required-switch` 不在 `master` 的树里。
- 错误行为：按 `AGENTS.md:131`（“验证 building 审阅完成”）、
  `docs/requirements-process.md:261,290` 与 task 5.2 的原文运行
  `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py` →
  这 5 个**冻结的历史归档**被报 `reviews/building-review.md 缺少 ## 闭环出口`，EXIT=1。
  报告是 `openspec/changes/archive/**` 下的受保护 artifact：照错误提示去补 `## 闭环出口`
  既要写 `protected_artifact_explained` 事件，又违反 proposal 需求 4「历史 SHALL 保持原样、
  不追溯」。同一命令加 `--base-ref origin/master` 则 EXIT=0，证明失败完全由 base 解析口径
  （而非报告本身）引入。
- 复现（原始输出已列在 Reviewer 节）：

```text
PYTHONPATH=. python3 scripts/check_openspec_artifacts.py                          # EXIT=1，5 条历史归档误红
PYTHONPATH=. python3 scripts/check_openspec_artifacts.py --base-ref origin/master # EXIT=0
```

- 可落地修法（任一或组合）：
  1. 把文档化本地命令统一改为 `--base-ref origin/master`（先 `git fetch`），并同步更新
     `AGENTS.md:131`、`docs/requirements-process.md:261,290` 与 `tasks.md:57`（5.2）的证据；
     `docs/development-guide.md:363` 的「旧门禁一行未动」也需一并校正（见 L2）。
  2. 或让归档点 verdict 完成面只对本 PR 相对 `origin/master`（必要时退化为 `merge-base`）
     新增的归档目录生效，并在 `_new_archive_dirs_since_base` 检测到 base 落后时给出显式
     WARNING（而非静默把历史目录当新增）。
  3. 至少补一条锁定「历史归档不追溯」的回归：在本工作区状态（base 落后）下断言历史目录
     不因缺失 `## 闭环出口` 变红。

### 下一批（deferred）

无（初次开批）。

## low/nit 登记

| id | severity | 锚点 | 处置/理由 |
|---|---|---|---|
| L1 | low | `docs/development-guide.md:303` | `--report reviews/<stage>-review.md` 只对 `building` 阶段正确；`grill` 实际报告是 `grill-design.md`、`grill-adversarial` 是 `grill-adversarial.md`。复制命令会得到 CLI 的显式报错（不会静默），且本地操作入口 `review-loop.md:115` 只跑 building 阶段，故不影响本轮；建议随 R0-1 的文档修订顺手改成逐 stage 示例。 |
| L2 | low | `docs/development-guide.md:363` | 「旧门禁一行未动：`scripts/check_openspec_artifacts.py` … 全部照旧」在本 change 后已不成立（checker 被本 change 修改）。该段落是阶段 C 的现状快照，建议改为「仍照跑」并加一句本 change 的退役说明。 |
| L3 | low | `tests/test_retire_manifest_check.py:343-355` | task 1.5 要求断言 `witnessloop manifest build` 在场；测试实际只断言 `"witnessloop"` + `"manifest"` + `"## 闭环出口"`。防旧 ast 要求的 marker 守卫是有效的，但「入口命令仍在」这一子断言较弱。 |
| L4 | nit | `docs/interview-script/questions/Q12-ci-testing.md:44` | 文案「**2016 版**的本仓 manifest 校验已退役」年份错误（应为 2026 / 旧版）。 |
| L5 | nit | `docs/known-debt.md:520-537` | 正文称「以下残余边界」后列 5 项，其中第 5 项是 legacy 资产保留而非「损失」；design/proposal 的口径是「四项残余损失」。不影响事实。 |
| L6 | nit | `scripts/check_openspec_artifacts.py:1146-1148` | 只拒绝 ASCII `|` 分隔的其它 token：`PASS ｜ BLOCKED`（全角竖线）与 `PASS BLOCKED`（无分隔符）都会判 PASS。规格只禁 `\|`，不构成违约；若想更稳可同时拒绝全角 `｜`。 |
| L7 | nit | `scripts/check_openspec_artifacts.py:1141` | 行首剥离只处理 `-*+ >` 与反引号，未处理有序列表前缀（`1. PASS`）。正式模板用裸行，属假红方向的窄边界。 |
| L8 | low | `tests/test_retire_manifest_check.py:88-124` | `ambiguous` / `duplicate` / `PASSED` 只有 parser 级断言，没有经 `_check_building_review(completion=True)` 的端到端断言；实现分支简单，风险低。 |
| L9 | nit | `tests/test_openspec_artifact_checker.py:212` | 测试名 `test_feature_change_requires_building_review_manifest` 仍带 `manifest`，实际断言的是报告存在性，易误导读者。 |

### 初次开批 · 收口确认

1 条 medium（R0-1）⇒ 本轮**未收口**；`## 闭环出口` 记 `未定`。修复后本审阅者只做 R0-1 的
修复验证，验证期新问题只进 `deferred` / low-nit。

## 闭环出口

未定
