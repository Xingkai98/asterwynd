# Tasks: witnessloop caller 回钉 v1.7.1 并同步 init 台账（repin-v1.7.1）

> **本 change 无代码面**：diff 只落在 `.github/workflows/witnessloop.yml`、`.witnessloop/init-manifest.json`、`openspec/**` 与 `docs/**`。没有可测的新代码对象，因此没有「测试先行」一节；验证以「工具幂等 + 归档后 manifest + 本地 check + CI gate 日志」多层证据收口。
>
> **前置门（第 0 节）不完成不得开工**：grill 由独立零记忆 subagent 执行，产出 `reviews/grill-design.md`；随后跑设计阶段对抗闭环，产出 `reviews/grill-adversarial.md`。本 change 是收尾动作，设计里**不应有需要用户拍板的 Open Question**；若确实冒出，停下来报告，不代拟答案。
>
> **次序是硬约束**（grill 6 条 medium 的修正）：所有内容（含 spec / backlog / tasks 结算）落定 → 归档 move → 在**归档目录**用**归档目录名** build 三份 manifest → 单独提交证据 → 本地 `check`（断言目标确实被检到）→ PR → CI。**本 change 出生即归档**（base 树里没有该目录，PR diff 无 rename），归档前用源 id 产的 manifest 不作数。
>
> **结算说明**：5.2–5.6 按终态勾选（与 `stage-c-required-switch` 的 5.4/5.5 同一体例）；真正只能在合入后完成的任务在第 6/7 节并标 `(post-merge)`。

## 0. 设计追问与对抗收敛（前置门，不完成不开工）

- [x] 0.1 独立零记忆 grill：对 `design.md` 做设计追问，产出 `reviews/grill-design.md`（`## Confirmed Decisions` ≥ 3 条，每条含**同行裸** `来源:`；`## User Confirmation` 无条件存在；`## Open Questions` 小节存在）。
- [x] 0.2 设计阶段对抗闭环（独立零记忆审阅者，审设计而非代码）→ `reviews/grill-adversarial.md`；medium+ 必须全修，直到 `## Verdict` 为 `PASS`。
- [x] 0.3 **停轮检查**：确认没有需要用户拍板的 Open Question；若有，停下来报告，不写实现。
- [x] 0.4 把 grill / 对抗结论回填 `design.md` 的 `## Pre-Implementation Review`。

## 1. 回钉实现（用工具，不手改台账）

- [x] 1.1 前置：`.github/witnessloop-tests.txt` 存在且内容不是 `<<REPLACE-ME>>`；确认用 `uvx --from "git+https://github.com/Xingkai98/witnessloop@refs/tags/v1.7.1" witnessloop ...`（PATH 上的 0.1.0 不支持 `--policy`；本地源码安装没有 `vcs_info`，不作为验收 CLI）。
- [x] 1.2 `init --dry-run`：`... witnessloop init --root . --gate-ref "Xingkai98/witnessloop/.github/workflows/gate.yml@v1.7.1" --policy .witnessloop/policy.json --dry-run`，确认只重写 caller + 同步台账。
- [x] 1.3 真跑同一条 `init`（去掉 `--dry-run`）。
- [x] 1.4 逐项核对：caller `uses:` = `...@v1.7.1`；台账 `gate_ref` = 同一值；caller 条目 `sha256` 与盘上文件一致；`.witnessloop/policy.json` sha256 前后一致（`33ee08e2…`）。
- [x] 1.5 幂等实测：同一条**完整** `init`（带 `--gate-ref` 与 `--policy`）再跑一次，期望 `init：已接入 witnessloop（幂等，无改动）。` 且 exit 0。plain `init` 在定制 policy 仓退 1 是既有预期，不作判据。

## 2. 规格与文档同步

- [x] 2.1 写 `specs/dev-workflow-gate/spec.md` delta（MODIFIED「阶段 C 翻开关后的 required 形态」：当前 ref → v1.7.1；tag 用 `job.workflow_ref`、分支/commit 用 `job.workflow_sha`；应急 commit pin 须在同一收尾批内回钉；normative 句不钉精确 uv minor 版本）。
- [x] 2.2 把 delta 同步进 `openspec/specs/dev-workflow-gate/spec.md`（Requirement 正文 + Purpose 段 `@v1.7.0` 现状句）；未改动的 Requirement 逐字节保留。同步时把 delta 的 MODIFIED 块**原样替换**进主 spec，并显式断言主 spec 该 Requirement 块与 delta 块逐字节一致（5 个 Scenario；`openspec validate` 单独不检查这一项）。
- [x] 2.3 `docs/development-guide.md`：caller 版本与包 ref 推导改为 v1.7.1；本地 `check` 锚点改为 `uvx --from "git+https://github.com/Xingkai98/witnessloop@refs/tags/v1.7.1" witnessloop check ...`（替换 `/home/happy/wl170/bin/witnessloop` 这类本机路径）；注明 annotated tag object 与 commit 的区别。
- [x] 2.4 `docs/interview-script/questions/Q12-ci-testing.md`：流水线图 `gate.yml@v1.7.0` → `@v1.7.1`。
- [ ] 2.5 关键词扫描：运行
  `rg -n 'v1\.7\.0|c9b2811|/home/happy/wl170' .github/workflows/witnessloop.yml .witnessloop/init-manifest.json openspec/specs/dev-workflow-gate/spec.md docs/development-guide.md docs/interview-script/questions/Q12-ci-testing.md`
  只对**当前态**命中断言零残留；历史命中 allowlist（不改）：`docs/adr/ADR-0006-…`、`openspec/specs/dev-workflow-gate/spec.md:73/:191/:195`（历史证据 / 「v1.7.0 实测」）、`docs/development-guide.md:385`（「v1.7.0 实测」）、`docs/development-guide.md:443`（2026-10-18 的 v1.7.0 实测记录）。行号以当前文件为准，扫描命令是权威。

## 3. 验证（归档前）

- [x] 3.1 `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` → 29 passed, 0 failed。
- [x] 3.2 `uv run python scripts/check_openspec_artifacts.py --base-ref origin/master --require-base` → `Project rule checks passed`，exit 0。
- [x] 3.3 `uv run pytest -q` → **4443 passed, 9 skipped, 3 failed**。3 条失败均为本机环境问题，已用 `git archive origin/master` 的基线源码复跑复现（同样 3 failed）：`TestFindScopeRoot` 两条因本机 `/tmp` 本身是 git 仓库、`test_task_output_truncated` 因 0.5s 内任务未完成；本 change 不触及 `agent/**`，不是回归。
- [x] 3.4 `git diff origin/master -- .witnessloop/policy.json` 为空；`git diff origin/master -- .github/workflows/witnessloop.yml .witnessloop/init-manifest.json` 只含预期的 ref / sha 改动。

## 4. 实现后独立审阅闭环

- [x] 4.1 独立零记忆 subagent 审阅（任务逐项 / 正确性 / Spec 对齐 / 测试覆盖 / 安全性 / 可维护性 / CI 完整性），产出 `reviews/building-review.md`；medium+ 全修，直到 `## 闭环出口` 为 `PASS`。
- [x] 4.2 收敛后清理中间轮产物（任何未被 manifest `report_path` 绑定的 `.md` 都会触发孤儿规则）。

## 5. 归档与证据（严格次序）

- [x] 5.1 结算 backlog（移除 `### 1. \`repin-v1.7.1\`` 条目）与 `workflow-events.jsonl`（三条必需精确路径事件 + `change_archived` 簿记；`approved_by` 非空）；结算 `tasks.md`（除第 6/7 节外全部勾选）。
- [x] 5.2 纯 move 到 `openspec/changes/archive/2026-10-20-repin-v1.7.1/`（不用 `openspec archive`，避免 UTC 日期与原子 move）；active 目录不再存在。
- [x] 5.3 在已提交的「内容 + move」HEAD 上、归档目录里用**归档目录名**逐份 build 三份 manifest（完整命令：`uvx --from "git+https://github.com/Xingkai98/witnessloop@refs/tags/v1.7.1" witnessloop manifest build --root . --change 2026-10-20-repin-v1.7.1 --base origin/master --stage <grill|grill-adversarial|building> --report reviews/<对应报告>.md`；本地网络不可用时用 v1.7.1 tag 源码 `uv run --project <v1.7.1 源码>` 执行同一命令），绑定 `reviews/` 下每一份 `.md`；显式给不同的 `--reviewer-run-id` / `--author-run-id`（不要共享 `WITNESSLOOP_RUN_ID`）。
- [x] 5.4 单独提交**manifest 证据**（events 已在 5.1 结算并随 move 提交，不再编辑），不再改动任何内容。
- [x] 5.5 `git fetch origin master` 后用 v1.7.1 CLI 跑 `witnessloop check --root . --base origin/master --head HEAD` → 输出含 `1 个 change 目录`、归档 target、`check：通过 ✓`（不能只看 exit 0）；记录 `git rev-parse origin/master`。本地若用 tag 源码则包来源自报为 `<未知>`，包 ref 的权威证据是本 PR 的 CI 日志（6.1）。
- [x] 5.6 证据提交后复跑 OpenSpec strict validate（含 Scenario 标题块逐字节断言）与瘦 checker；发起 PR。

## 6. 合入前 CI（归档时点结构上无法勾选）

- [ ] (post-merge) 6.1 PR 的 `gate / check` 判绿；日志中包 ref 为 `refs/tags/v1.7.1`（来源 `job.workflow_ref` 的 tag ref），不是 tag object sha 或 commit pin。
- [ ] (post-merge) 6.2 记录 `validate` / `benchmark-gate` / `windows-platform` 的结论（照跑，不拦合并）。
- [ ] (post-merge) 6.3 用 merge commit 合入（禁止 squash）；记录 PR 号与 merge sha。

## 7. 合入之后（结构上无法在本 PR 内完成）

- [ ] (post-merge) 7.1 在 issue #331 追加完成说明（caller / 台账已回钉、gate 日志包 ref、归档位置）并关闭 issue。
- [ ] (post-merge) 7.2 复核 `master`：caller `@v1.7.1`、台账 `gate_ref` 一致；用完整命令 `witnessloop init --root . --gate-ref "Xingkai98/witnessloop/.github/workflows/gate.yml@v1.7.1" --policy .witnessloop/policy.json` 复核幂等（plain `init` 在定制 policy 仓会 exit 1，不作为判据）；active change 目录不存在、backlog 干净、本地 `master` 已快进到 `origin/master`。
