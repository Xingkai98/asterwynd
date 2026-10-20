# Building Review: repin-v1.7.1 — Round 2

## Reviewer

- run id: `building-review-repin-v1.7.1-2026-10-20-r2`
- 时间: 2026-10-20
- 零记忆: 是（未参与实现或 Round 1 审阅，不继承开发上下文；本报告全部结论来自本次在 `/home/happy/ax-wt/repin-v171` 的实测）
- 被审 revision: HEAD = `44def6274a67ef68d6c4f481bfcf34f8fb29db16`（分支 `repin-v1.7.1/2026-10-20`，base = `origin/master` = `1526efc75e7c7ea14e290fcd2db22a261d4987ce`）。
- 审阅开始时 `git status --short` 为空。本报告写入后，工作区唯一新增文件是本报告（`?? openspec/changes/archive/2026-10-20-repin-v1.7.1/reviews/building-review.md`）。
- 实际执行的关键命令（非只读文字）：
  - `uvx --from "git+https://github.com/Xingkai98/witnessloop@refs/tags/v1.7.1" witnessloop check --root . --base origin/master --head HEAD`（写报告前）：输出 `requested_revision=refs/tags/v1.7.1，commit_id=07bf23b38dfe19c1e0b9590732e6c5699f3b5e79`、`14 个变更文件，1 个 change 目录`、`change：2026-10-20-repin-v1.7.1（归档）`、`check：通过 ✓`，exit 0
  - `uvx --from "git+https://github.com/Xingkai98/witnessloop@refs/tags/v1.7.1" witnessloop init --root . --gate-ref "Xingkai98/witnessloop/.github/workflows/gate.yml@v1.7.1" --policy .witnessloop/policy.json --dry-run`：`init：已接入 witnessloop（幂等，无改动）。`，exit 0
  - `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`：28 passed, 0 failed，exit 0
  - `uv run python scripts/check_openspec_artifacts.py --base-ref origin/master --require-base`：写报告前 1 条 ERROR（building-review.md missing），写报告后实测见「M2」与「CI 完整性」小节
  - `sha256sum`、`git diff`、`git ls-remote`、`gh pr list`、Python 逐字节/hash 比对

## Round 1 处置

### M1 [medium] `tasks.md` 2.5 未勾选且未标 `(post-merge)` — **已修**

- 现状：`openspec/changes/archive/2026-10-20-repin-v1.7.1/tasks.md:32` 已是 `- [x] 2.5 关键词扫描…`，并记录了扫描命令、当前态零残留的结论与历史命中 allowlist（`:33-34`）。`tasks.md:50`（5.1）「除第 6/7 节外全部勾选」的自述现在与事实一致。
- 独立复跑扫描：
  `rg -n 'v1\.7\.0|c9b2811|/home/happy/wl170' .github/workflows/witnessloop.yml .witnessloop/init-manifest.json openspec/specs/dev-workflow-gate/spec.md docs/development-guide.md docs/interview-script/questions/Q12-ci-testing.md`
  命中只有 allowlist 内的历史记录：`openspec/specs/dev-workflow-gate/spec.md:73/:191/:195`、`docs/development-guide.md:385/:443`。当前态（caller、台账、spec Purpose/Requirement、dev-guide 当前态段、Q12）零残留。
- 纪律后果已按 Round 1 建议处理：`tasks.md` 的字节变化后，两份 grill manifest 已重建（提交 `44def62`），`tasks_hash` 与当前 `tasks.md` 一致（见下）。
- 瘦 checker 不再存在完成度门错误：写报告前实跑只剩 1 条 `building-review.md missing`，没有 `未勾且未标 (post-merge)` 报错。

### M2 [medium] building review / manifest 在归档 revision 上无产物 — **本轮可闭合部分已修，manifest 为明确的下一机械步骤**

- `reviews/` 现状：`grill-design.md`、`grill-adversarial.md`、本报告三份 `.md`，以及 `grill.manifest.json`、`grill-adversarial.manifest.json` 两份 manifest；Round 1 的中间轮报告已移出 `reviews/`（临时保存在 `/tmp/building-review-repin-r1.md`），不存在孤儿 `.md`。
- 4.1（`tasks.md:45`）：本报告即独立零记忆 subagent 审阅产物，因此该任务在归档 revision 上现在有对应证据。
- 4.2（`tasks.md:46`）：中间轮产物已清理，`reviews/` 下现有 `.md` 与两份 manifest 的 `report_path` 一一对应。
- 4.1 的 `## 闭环出口` 为 PASS（见文末），满足 `scripts/check_openspec_artifacts.py` 的归档点判据（`:1111-1137`）。
- 5.3（`tasks.md:52`）的三份 manifest 中，`building.manifest.json` 尚未构建。这是**结构性先后**而非遗漏：manifest 必须绑定 `building-review.md` 的 `report_hash`，只能在报告落盘之后构建。本报告写完后由主 session 构建并提交，随后必须重跑 `witnessloop check`。
- 5.6（`tasks.md:55`）的「发起 PR」同样发生在本轮 PASS 之后，属于仓库既有的「终态勾选」体例（`tasks.md:9`）；已核实同一体例先例：已归档的 `2026-10-17-stage-c-required-switch/tasks.md:61`（4.3）在归档时勾选了「PR 的 `gate / check` 判绿」，而归档时点 PR 尚不可能存在。故不计 medium，另见 L6。
- 写报告后实测：
  - `uv run python scripts/check_openspec_artifacts.py --base-ref origin/master --require-base` → **exit 0**，`Project rule checks passed`（之前的 1 条 ERROR 消失）。
  - `uvx … witnessloop check --root . --base origin/master --head HEAD` → **不再通过**，唯一 finding 是 `孤儿报告：reviews/building-review.md 未被任何 manifest 绑定`。这是「报告先落盘、manifest 后构建」的预期中间态；**在构建 `building.manifest.json` 并重跑 check 之前不得发 PR**。

## 维度检查

### 1. 任务逐项验证

- **0.x 设计前置门**：`reviews/grill-design.md` 的 `## Confirmed Decisions` 有 8 条 `- **决策**` 项，每条含同行裸 `来源:`；`## User Confirmation` 与 `## Open Questions` 小节均存在（0 条 OQ）。`reviews/grill-adversarial.md` 的 `## Verdict` 为 `PASS`，medium+ = 0（Round 1 的 M1 已按 5 Scenario 修复并被机械验证）。`design.md` 的 `## Pre-Implementation Review` 回填了 grill 与对抗 r1/r2 结论。
- **1.x 回钉实现**：`caller uses:` = `.github/workflows/witnessloop.yml:14` 的 `Xingkai98/witnessloop/.github/workflows/gate.yml@v1.7.1`；台账 `gate_ref` 同值（`.witnessloop/init-manifest.json:7`）；caller 条目 sha256 `2e8216ac…a7d523`（`:15`）与 `sha256sum .github/workflows/witnessloop.yml` 逐字一致；policy sha256 `33ee08e2…61e4bd`（`:11`）与盘上一致；`git diff origin/master -- .witnessloop/policy.json` 为 0 字节；带完整 `--gate-ref` / `--policy` 的 `init --dry-run` 报幂等，exit 0。`.github/witnessloop-tests.txt` 为 `uv run --extra dev pytest -q`，不是哨兵。
- **2.x 规格与文档**：delta `specs/dev-workflow-gate/spec.md:5` 是唯一 MODIFIED Requirement，正文与主 spec `openspec/specs/dev-workflow-gate/spec.md:225-260` 该块逐字节一致（delta 块 2990 字节；主 spec 块比 delta 块多出的唯一 1 个字节是下一 Requirement 前的分隔空行 `\n`，已有脚本断言 `main[:-1] == delta` 为 True）。Scenario 恰为 5 个：`required 只剩…`、`caller 钉住的 ref…`、`require_change_for`、`归档产物的证据形态…`、`应急 commit pin 必须回钉`（delta `:11/:17/:24/:31/:39`；主 spec `:229/:235/:242/:249/:257`）。`docs/development-guide.md:381`、`:389-399` 与 `docs/interview-script/questions/Q12-ci-testing.md:28` 已同步；历史口径（spec `:73/:191/:195`、dev-guide `:385/:443`、ADR-0006）保留未动。
- **3.x 验证**：`validate --all --strict` 28 passed / 0 failed（归档后终态计数，见 L2）；`/tmp/pytest-repin.log` 为 `3 failed, 4443 passed, 9 skipped`，3 条失败与本 diff 无关（本 diff 不含 `agent/**`、`scripts/**`、`web/**`）；3.2 的 checker 绿在本报告落盘后成立。
- **4.x 审阅闭环**：见 M2。报告已产出，清理已完成，building manifest 待建。
- **5.x 归档与证据**：backlog 无 `repin-v1.7.1` 残留；active change 目录不存在；归档目录为 `openspec/changes/archive/2026-10-20-repin-v1.7.1/`；`44def62` 只改两份 manifest（6 增 6 删）；写报告前 `witnessloop check` 命中 1 个归档 change target 并通过。
- **6.x / 7.x**：均带 `(post-merge)`，归档点豁免成立；`gh pr list --head repin-v1.7.1/2026-10-20 --state all` 返回 `[]`，故 6.1 的 CI 日志与 6.3 的 PR 号客观尚不存在，留给合入阶段。

### 2. 正确性

- caller 与台账同源回钉 `@v1.7.1`，diff 只含预期改动：`git diff origin/master --stat` 为 2 个受管文件、3 增 3 删；`init-manifest.json` 的差异仅 `gate_ref` 与 caller 条目 sha256。
- 上游 `refs/tags/v1.7.1` 实查为 annotated tag object `c4f681a7e899b5958dd51e8823b7a6dc9260c187` → commit `07bf23b38dfe19c1e0b9590732e6c5699f3b5e79`（`git ls-remote` 同时返回两行），与 design / dev-guide 的记载及 `check` 自报的 commit_id 一致；`job.workflow_sha` 是 tag object 的根因与本次改用 tag ref 的处置相符。
- `policy.json` 逐字节未变；`init` 幂等；台账 sha256 与盘上 caller 一致，不存在「只改一边」的漂移态。

### 3. Spec 对齐

- delta 的 MODIFIED 块是整块替换源文本，与主 spec 同一 Requirement 块在正文与 5 个 Scenario 上逐字节一致（见上，唯一差异是块间分隔空行）。
- 只改当前态：Purpose 的 caller 版本与「包 ref 按 ref 形态推导」正文；历史「v1.7.0 实测」证据原样保留，没有被为 grep 变绿而误改。
- `openspec validate --all --strict` 通过；MODIFIED 的 Scenario 集合没有丢项（Round 1 设计对抗的核心风险已消除）。

### 4. 冗余度

- required 集合与「降级不关闭」不变量仍只由 `platform-gate` 能力域承载，`dev-workflow-gate` 的规格正文明确声明不重复；本次只改接入形态本身。
- dev-guide 与 spec 是操作层 vs 规范层，不构成冲突性重复；没有新增第二处事实源。

### 5. 测试覆盖

- 本 change 无运行时代码（diff 不含 `agent/**` / `scripts/**` / `web/**`），无新增单测属合理。
- 回归证据由三层承载：`witnessloop check`（含目标命中断言）、`init` 幂等实测、全量 pytest 日志；全量日志的 3 条失败均已由 Round 1 归因为本机环境且与 diff 无关，本 change 之后只改了 `tasks.md` 与 manifest，不影响该结论。
- CI `gate / check` 日志要等 PR，已由 `(post-merge)` 任务 6.1 承接。

### 6. 安全性

- 受保护写入事件精确、无通配：`workflow-events.jsonl` seq 2 `backlog_updated` → `docs/openspec-change-backlog.md`；seq 3 `protected_artifact_explained` → `.witnessloop/init-manifest.json`；seq 4 `current_spec_synced` → `openspec/specs/dev-workflow-gate/spec.md`；`approved_by` 均为 `human`。这三条正对应 policy 的 `protected_paths`，且归档后仍被 witnessloop 读到（`check` 通过）。
- 未改 policy、未改上游仓 / tag、未跑 `platform_gate --apply`、未手改台账；`caller` 文件不在 protected_paths 内，无需为其补事件。
- 未发现伪造 PASS：本报告基于独立实测；当前唯一的红是预期的孤儿报告，且已如实记录。

### 7. 可维护性

- `docs/development-guide.md:389-399` 的可复现锚点 `uvx --from "git+…@refs/tags/v1.7.1" witnessloop check` 与实际执行一致；本次 `uvx` 路径自报了 `requested_revision=refs/tags/v1.7.1`（tasks `:54` 的 `<未知>` 只是本地源码安装的旁注，见 L5）。
- 回滚路径写死为完整 gate-ref + `--policy`（`proposal.md` Impact Analysis），并说明回到 `@v1.7.0` 会复发上游 #42。
- 升级命令在 dev-guide、spec 与 tasks 中均带 `--policy .witnessloop/policy.json`，消除了「plain init 先写后失败」的陷阱。

### 8. CI 完整性

- caller 已钉 `@v1.7.1`，PR 自身会由 v1.7.1 的 reusable workflow 跑 `gate / check`；合入必须 `--merge` 已写入 `design.md` Decision 8 与 `tasks.md:61`（6.3），并解释了 squash 会切断 manifest 的祖先链。
- 两份现有 manifest 逐项复算通过：
  - `base_sha` = `1526efc75e7c7ea14e290fcd2db22a261d4987ce` = 当前 `origin/master`；
  - `head_sha` = `b49b3ec3d458d9fa10cb3b2d7556fbadaf278df0`，是 HEAD 的祖先；
  - `tasks_hash` = `6a28217d…77e5`、`spec_hash` = `9bd6aa29…af0f`、`diff_hash` = `e6e3caea…afb0` 与当前归档内容逐项一致；
  - `grill.manifest.json` 的 `report_hash` = `e49d728f…256e`（`reviews/grill-design.md`）、`grill-adversarial.manifest.json` 的 `report_hash` = `1dbc9621…b3cd`（`reviews/grill-adversarial.md`），均与盘上文件一致。
- 待补：`building.manifest.json`（绑定本报告）→ 重跑 `witnessloop check` 至 `1 个 change 目录` + `check：通过 ✓` → 才可发起 PR。写报告后的 check 实跑结果见 M2。

## Issues

### Medium+

无。

### Low / Nit（登记不修）

- **L1 [low] `tasks.md:40` 的环境归因措辞不精确**：写「本机 `/tmp` 本身是 git 仓库」，实际是 `/tmp/.git` 目录残留；`_find_scope_root` 只看 `.git` 是否为目录，导致两条测试失败。结论（环境问题、非回归）不变。不修理由：不影响门禁、结论与证据。
- **L2 [low] `tasks.md:38` 的 29 passed 是归档前口径**：归档后 `validate --all --strict` 实测 28 passed（归档 change 不再计入）。验证本身通过。不修理由：终态计数已在本报告记录，任务结论不受影响。
- **L3 [nit] `cba55ea` 提交信息写「pure move」，但同一提交还含 backlog 删除、tasks 结算与 events 追加**：历史提交不重写，登记即可，不影响证据有效性。
- **L4 [low] 6.1 / 6.2 标 `(post-merge)` 与「合入前 CI」标题语义不完全一致**：这两项实际发生在 PR 创建后、合入前；归档时点不可达，标 `(post-merge)` 是结构性豁免。不修理由：与仓库既有体例一致，不改变门禁行为。
- **L5 [nit] `tasks.md:54` 关于 `<未知>` 的旁注已不适用于推荐路径**：本次 `uvx --from …@refs/tags/v1.7.1` 自报 `requested_revision=refs/tags/v1.7.1`；`<未知>` 只会在本地源码安装时出现。不修理由：旁注不构成错误断言，CI 日志仍是权威证据。
- **L6 [nit] `tasks.md:52`（5.3）与 `:55`（5.6）在归档 revision 上提前勾选**：building manifest 与 PR 在本轮 PASS 后才产生。已核实仓库「终态勾选」先例（`2026-10-17-stage-c-required-switch/tasks.md:61` 在归档时勾选了 PR CI 判绿）。不修理由：不影响归档点判据；若把「发起 PR」改成独立 `(post-merge)` 项会与既有体例不一致。**执行约束**：必须按 `tasks.md:7` 的次序先构建 building manifest、重跑 check 通过后再发 PR，不能把本报告的 PASS 直接当作 PR 许可。

## 结论

- Round 1 的两条 medium 均已处置：M1 的 2.5 已完成结算并有可复跑扫描证据，完成度门禁不再红；M2 的 building review 证据由本报告补齐，瘦 checker 在写报告后转绿。
- 核心改动保持正确：caller 与台账一致回钉 `@v1.7.1`、caller sha256 与盘上一致、policy 零改动、`init` 幂等、主 spec 与 delta 的 Requirement 块逐字节一致（5 个 Scenario）、受保护写入事件精确、两份现有 manifest 的 hash/base/head 全部与当前归档对得上。
- 本轮没有新的 medium+；剩余 6 条 low/nit 均不影响门禁与结论，登记不修。
- 下一步（也是 PASS 的前置执行约束）：主 session 用归档目录名构建 `reviews/building.manifest.json`、提交证据，重跑 `witnessloop check` 至通过，然后发起 PR；合入使用 merge commit。无需用户拍板，无 STOP 项。

## 闭环出口

PASS
