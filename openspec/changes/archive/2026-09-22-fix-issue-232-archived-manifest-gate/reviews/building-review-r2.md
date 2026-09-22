# Building Review R2: fix-issue-232-archived-manifest-gate

## Verdict
PASS

## Reviewer
- run id: `paseo-reviewer-2026-09-22-r2`（独立零记忆 subagent，未继承开发上下文，未参与 R1）
- 审阅范围: `678347e...3222582`（增量，6 文件 / +301 −12）+ R1 结论回归确认；最终 head `32225828cb7d30323a686fcf1e8f2f9025b41e15`，base `cea1e53a521d37d5c18d23700c811909f1095d6c`
- 复核方式（全部实读 + 实跑；变异验证后已还原，`git status --porcelain` 仅剩两个既有 untracked 文件）：

  **读**
  - `AGENTS.md:111`（新措辞全文）、`docs/known-debt.md:205-232`（B-覆盖面两处上界）
  - `openspec/changes/fix-issue-232-archived-manifest-gate/design.md:94-108`（新 D6）
  - `openspec/changes/fix-issue-232-archived-manifest-gate/specs/dev-workflow-state-machine/spec.md`（delta 4 条 Scenario 全文）
  - `openspec/specs/dev-workflow-state-machine/spec.md:140-158`（正式 spec 对照）
  - `tests/test_openspec_artifact_checker.py:1943-1988`（新 helper + 重写后的测试全文）
  - `scripts/check_openspec_artifacts.py:1009-1051`（`_check_review_manifests`）、`1415-1449`（归档分支与汇总）、`1071-1165`（受保护路径事件校验）
  - `.github/workflows/ci.yml:53-73`（validate job 步骤布局）

  **实跑**
  - 回归四文件 → **118 passed**
  - `--check-archived --skip-protected-paths --skip-backlog` → **exit 1**，仅本 change 自身 `review manifest missing`（预期中间态，见下）；stderr 汇总恰 1 行
  - `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` → **30 passed, 0 failed**
  - **变异验证 ×4**（L2，详见下）
  - 归档目录普查脚本（runpy 载入 checker，复用其 `parse_change_type`）

## R1 观察项落实核对

| 项 | R1 说的问题 | 作者动作 | 你的核对结论（含证据） |
|---|---|---|---|
| **L1** | `_check_review_manifests` 在无 `reviews/` 时 `return []`，归档 change 不被要求补 manifest，AGENTS.md 全称表述「归档 change 也在校验范围内」易误读 | 改 `AGENTS.md:111` 标题为「**归档 change 的 manifest 不再脱离校验**」，并加限定句「注意这是**漂移检测**：只对已有 `reviews/*-review.md` 的归档 change 生效，不追溯要求历史归档 change 补 manifest（覆盖面隐含上界见 `docs/known-debt.md`）」；`docs/known-debt.md` 记两处上界 | ✅ **已落实，且文字与实测行为逐项吻合**。独立普查（90 个归档目录）：无 `Change Type` 跳过 **4** 个（均 `2026-06-21-*`，实测**均无 `reviews/`**）；有 `*-review.md` **43** 个（**43/43 有 manifest，零缺件**）；无 review **43** 个（**42 非 docs + 1 docs**）。known-debt.md 写的「4 个被跳过」「42 个非 docs 无 review」「只覆盖已有 `*-review.md` 的 change」**三处数字全部精确命中**。新措辞不再过度承诺：改为「漂移检测」+ 显式排除追溯，与代码 `:1024-1027` 注释、`:1040-1041` 的 `return []` 一致。**无新引入的不符事实断言**。 |
| **L2** | `test_ci_validate_job_runs_check_archived` 为整文件子串匹配，不断言同一条命令 / 同 step / 无 `continue-on-error` | 新增 `_yaml_step_containing`（`:1943-1965`，锚定 `- name:` 块 + **剥注释行**），测试重写为结构断言（`:1977-1988`） | ✅ **已落实，强度实测到位**。见下「变异验证」4 组，全部转红。关键改进点是**剥注释行**（`:1965`）——这正是 R1 指出的软肋（ci.yml 注释里含两个 skip flag 字样，若不剥注释，「flag 被从命令行删掉」探测不到）。 |
| **D6** | `design.md` D6 称 delta 保留的 2 条「逐字相同」，但第 2 条实际有意改措辞两处 | 改写 D6（`design.md:96-103`），分列「逐字相同」与「有意改措辞两处」，并注明「已按 R1 审阅结论修正」 | ✅ **新 D6 与 delta 实际内容完全一致**。逐条比对 4 条 Scenario：① `review report 缺少 manifest`（delta `:13-19` vs main `:144-151`）——**逐字相同，属实**；② `manifest 字段和 hash 校验`（delta `:21-27` vs main `:153-158`）——**恰好两处差异，与 D6 所述逐字对应**：`tasks_hash` 后加「（**已归档** change 除外，见下述归档 Scenario）」（delta `:26`）+ 删「`head_sha` 匹配当前 `HEAD`」（main `:158` 有、delta `:27` 无）；③④ 为新增 2 条（delta `:29-35`、`:37-42`），main 中不存在。**退役 0、保留 2、新增 2 = delta 4 条**，计数吻合。 |
| **L3** | 跳过计数按「有 manifest」而非「确有 `tasks_hash` 被跳过」计 | 选择记录、不改（理由：全仓 0 例实际影响） | ✅ **决定可接受**。判据代码 `:1438-1439` 仍是 `any((change_dir / "reviews").glob("*-review-manifest.json"))`；但普查证实「有 manifest 而无 `*-review.md`」为 **0 例**（43 个有 review 的 change **全部**有 manifest，反之亦然），故计数当前不可能高估。且该计数仅供一行 stderr 汇总的文案（`:1442-1447`），不进 `errors`、不影响任何判定。**无实际影响，不作为修改要求**。 |

## 变异验证（L2 强度实测，4 组 + 1 组反向）

原始 `md5(.github/workflows/ci.yml) = b93be72af2985709e68bd45c5bf17638`；每组后 `cp` 还原并复验 md5 一致。

| # | 变异 | 命令 | 结果 |
|---|---|---|---|
| 1 | 从**命令行**删两个 skip flag（注释里保留字样） | `uv run pytest tests/test_openspec_artifact_checker.py -q -k ci` | **1 failed**（`:1985` `assert "--skip-protected-paths" in step`）→ **转红 ✔** |
| 2 | 给该 step 加 `continue-on-error: true` | 同上 | **1 failed**（`:1981`）→ **转红 ✔** |
| 3 | 整段删掉 `--check-archived` step | 同上 | **1 failed**（`:1977`，全文件已无 `--check-archived`）→ **转红 ✔** |
| 4 | 把命令行**整条注释掉**（flag 字样仅存于注释） | 同上 | **1 failed**（`:1985`）→ **转红 ✔**（证明「剥注释」确实生效，非装饰） |
| — | 附加对抗：命令行尾部加 `\|\| true` | 同上 | **1 failed**（`:1982`）→ **转红 ✔** |

还原后 `md5 = b93be72af2985709e68bd45c5bf17638`（与原始一致），`git status --porcelain` 仅剩 `handoff.json` / `workflow-state.json` 两个既有 untracked 文件。

## 回归确认

```
$ uv run pytest tests/agent/workflow/test_review_manifest.py tests/test_openspec_artifact_checker.py \
    tests/test_workflow_archive_write_channel.py tests/test_workflow_protected_write_channel.py -q
118 passed in 41.51s          # R1 时 93 + 25 = 118，一致，增量未破坏任何既有结论
```

```
$ PYTHONPATH=. python3 scripts/check_openspec_artifacts.py --check-archived --skip-protected-paths --skip-backlog
[stderr] [archived manifest check] tasks_hash 已按归档语境跳过（43 个 change；其余 hash 与字段仍校验）
[stderr] ERROR: fix-issue-232-archived-manifest-gate: review manifest missing: \
         openspec/changes/fix-issue-232-archived-manifest-gate/reviews/building-review-manifest.json
EXIT=1
```
- **这是预期的中间态，非缺陷**：本 change 的 `reviews/building-review.md`（R1 报告）已落盘，按 D3 纪律 manifest 须待 `tasks.md` 最终化（含归档 move）后生成，此刻尚未生成；且该 change 尚未归档，走的是 active 分支（`requires_building_review`，`check_openspec_artifacts.py:1028-1033`）。
- **其余 43 个归档 change 无新增错误** ✔（ERROR 仅 1 条且指向本 change）；**stderr 汇总恰 1 行** ✔（外加上述 1 条 ERROR，非刷屏）。

```
$ grep -n "if not archived and manifest.get(\"tasks_hash\")" agent/workflow/review_manifest.py
175:    if not archived and manifest.get("tasks_hash") and manifest.get("tasks_hash") != ...
```
- **A′ 的 `not archived` 前置仍在** ✔，且增量 diff 的 6 个文件中**不含** `agent/workflow/review_manifest.py`（`git diff 678347e...3222582 --name-only`：AGENTS.md / known-debt.md / design.md / building-review.md / tasks.md / test_openspec_artifact_checker.py）——R1 已确认的核心机制（1 行前置 + `spec_hash`/`report_hash`/字段/存在性/git span 零放宽）未被 R1 修复波及。

```
$ npx --yes @fission-ai/openspec@1.4.1 validate --all --strict
Totals: 30 passed, 0 failed (30 items)
```

## Issues

无阻塞、无中等、无低危需修项。以下为纯记录性观察（**均不构成本 change 的修改要求**）：

**O1. `docs/known-debt.md:225` 仍引用被替换掉的旧措辞**

该行写「即 AGENTS.md 新增段落的**「归档 change 也在校验范围内」**应读作…」，但 `AGENTS.md:111` 的标题已在本增量中改为「归档 change 的 manifest 不再脱离校验」，被引用的短语在 AGENTS.md 中已不存在（全仓 `grep -rn "归档 change 也在校验范围内" --include=*.md` 仅命中 known-debt.md 自身这一处引用）。

- 性质：交叉引用指向一个已被改写的旧标题；论断本身仍成立（R1 语境下确为原文），且 AGENTS.md 新段落已自带「不追溯要求历史归档 change 补 manifest」限定，故 known-debt.md 的「应读作」注解现在略显冗余。
- 严重度：**极低**（不影响任何判定的正确性，不影响 CI，不缺信息——上界两处已在同节写清）。不要求本 change 处理；若顺手，可把引号内短语改为引用新标题，或直接删去对 AGENTS.md 措辞的转述（上界已在本节正文写明）。

**O2. R2 报告文件名不落入 checker 的 `*-review.md` glob**（供收尾参考，非缺陷）

`_check_review_manifests`（`check_openspec_artifacts.py:1046`）遍历 `glob("*-review.md")`。实测 `PurePath("building-review-r2.md").match("*-review.md") == False`（而 `building-review.md` 为 `True`）——R2 报告**不会**被要求配对 manifest，属惰性文件。这恰好使 R2 的落盘不额外增加收尾时序负担；仅提示收尾时 `building-review-manifest.json` 只需绑定 `building-review.md`（即 R1 报告）。

## 结论

增量 commit `3222582` 对 R1 三条观察项的落实**逐条为真、且经独立实测复核**：

1. **L1 已落实且不过度承诺**——AGENTS.md 新措辞把全称改为「漂移检测 + 只覆盖已有 `*-review.md` 的 change + 不追溯」，与代码行为一致；known-debt.md 的三处数字（4 / 42 / 43）经独立普查**全部精确命中**，文字未引入与代码不符的新断言。
2. **L2 已落实且强度经变异证明**——4 组变异（删 flag / `continue-on-error` / 删整 step / 注释掉命令行）**全部转红**，外加 `|| true` 一组亦转红；剥注释行的新逻辑确有载荷，不再是弱子串匹配。
3. **D6 已按事实改写**——保留 2 条中「逐字相同」与「有意改措辞两处」的区分，与 delta 实际 4 条 Scenario 逐条比对完全吻合。
4. **L3 的记录不改决定可接受**——全仓「有 manifest 无 report」为 0 例，计数仅供一行 stderr 文案，不进判定，无实际影响。

增量 commit 未引入新问题（改动面为纯文档 + 测试强化，未触碰任何产品代码；`agent/workflow/review_manifest.py` 零改动），R1 已确认的结论（A′ 只放宽归档、判别性对照、不静默降级、盲区 A 未破坏）全部回归通过：回归 118 passed、OpenSpec strict 30/0、`--check-archived` 除本 change 预期中间态外其余 43 个归档 change 零新增错误且 stderr 恰一行。

**Verdict: PASS**

（记录 O1 / O2 两条纯观察项，均非修改要求。收尾提醒不变：`building-review-manifest.json` 必须在本 change 的 `tasks.md` 最终化（含归档 move 与剩余收尾勾选）之后生成；本 R2 报告不落入 `*-review.md` glob，无需为其单独生成 manifest。）
