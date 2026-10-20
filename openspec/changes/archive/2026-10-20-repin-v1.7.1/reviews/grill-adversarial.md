# Grill 对抗（设计阶段审阅闭环）: repin-v1.7.1 — Round 2

## Reviewer

- run id: `grill-adversarial-repin-v1.7.1-2026-10-20-r2`
- 时间: 2026-10-20
- 零记忆: 是（未参与 proposal / design / tasks 编写，也没有继承 Round 1 之外的开发上下文；本轮所有事实独立重查）
- 被审 revision: 工作区未提交。`git rev-parse HEAD` = `1526efc75e7c7ea14e290fcd2db22a261d4987ce`（= `origin/master`）；`git status --short`：
  ```
  M docs/openspec-change-backlog.md
  ?? openspec/changes/repin-v1.7.1/
  ```
- 审阅对象：`openspec/changes/repin-v1.7.1/{proposal.md,design.md,tasks.md,specs/dev-workflow-gate/spec.md,reviews/grill-design.md,workflow-events.jsonl}`
- 核验方法（不只读文字）：
  - 对主 spec 与 delta 的同一 Requirement **逐 Scenario 逐字节 diff**（标题 + 全部 WHEN/THEN/AND 行）；
  - 在临时副本上用 OpenSpec 1.4.1 的 `findSpecUpdates` + `buildUpdatedSpec`（`~/.npm/_npx/c37562604d2d088d/node_modules/@fission-ai/openspec/dist/core/specs-apply.js`）**真跑一次 delta 应用**，核对应用后的 Requirement 与 scenario 集合；
  - 读 witnessloop v1.7.1 源码 `/tmp/wl171/src/witnessloop/{initcmd,manifestcmd,contract,evidence,events,gitutil,policy}.py` 与 `/tmp/wl171/.github/workflows/gate.yml`；
  - 实跑 `npx --yes @fission-ai/openspec@1.4.1 validate repin-v1.7.1 --strict`（valid）、`validate --all --strict`（29 passed / 0 failed）、`uv run python scripts/check_openspec_artifacts.py --base-ref origin/master --require-base`（exit 0）、`uvx --from "git+https://github.com/Xingkai98/witnessloop@refs/tags/v1.7.1" witnessloop check`（未提交树复现 0 target 假绿）；
  - 用同一 `POST_MERGE_TAG_RE` 机械核对 `tasks.md` 的全部未勾项；
  - 用 `gh` 核对 issue #331、witnessloop v1.7.1 tag、witnessloop issue #42。

## Verdict

**PASS**

本轮没有 medium+。Round 1 的 M1 已按建议修好，并且用 OpenSpec 1.4.1 的真实应用函数验证：应用后目标 Requirement 恰为 **5 个 scenario**，3 个未改 scenario **逐字节保留**，`warnings: []`、未触发「current spec contains scenario(s) not present in the modified block」。L1–L8 全部落地。新发现只有 2 条 low（N2、N3）+ 4 条 nit（N1、N4、N5、N6），登记不修，不阻断。

## Round 1 处置

### M1 [medium] MODIFIED 块丢失两个现有 scenario — **已修**

- delta 现在有 5 个 scenario：`openspec/changes/repin-v1.7.1/specs/dev-workflow-gate/spec.md:11`（required 只剩）、`:17`（caller 钉 ref）、`:24`（require_change_for）、`:31`（witnessloop 单套）、`:39`（应急 commit pin）。
- 逐字节比对结果（主 spec `openspec/specs/dev-workflow-gate/spec.md:223-255` vs delta）：
  - `required 只剩 witnessloop 的 gate / check`：**完全一致**；
  - `阶段 C 之后的改动受 require_change_for 约束`（主 spec `:242-247`）：**完全一致**；
  - `归档产物的证据形态为 witnessloop 单套`（主 spec `:249-255`）：**完全一致**；
  - `caller 钉住的 ref 同时决定包版本`：**有意修改**，且 diff 只含预期条款——`@v1.7.0`→`@v1.7.1`（delta:16）、`SHALL NOT 用滚动 tag（@v1）或分支名`→`…、分支名或长期 commit pin`（同日）、包 ref 推导改为 tag/分支二分 + 上游 #30 / #42（delta:17）、升级命令补 `--policy`（同日）、追加 `SHALL NOT 只改其中一边`（delta:18）。没有意外漂移；
  - `应急 commit pin 必须回钉`：新增（delta:39-45）。
- 机械验证：在临时副本上调用 OpenSpec 1.4.1 的 `buildUpdatedSpec`，结果 `counts={added:0, modified:1, removed:0, renamed:0}`、`warnings=[]`；应用后该 Requirement 的 scenario 为上面 5 个，3 个未改 scenario 与主 spec 逐字节相同。Round 1 引用的抛弃检查（`specs-apply.js:388-389`）不再触发。
- 同步步骤：`tasks.md:29`（2.2）已增加「同步后显式断言 Scenario 标题集合 = 4 个现有 + 1 个新增」；`design.md:111`（T8）同样要求显式比对标题集合，并注明 `openspec validate` 单独不检查这一项。
- `--policy` 的规范句：已出现在**正确的位置**——delta `:21` 的「升级动作 SHALL 是 `witnessloop init --gate-ref <新 ref>` 一处改动（本仓是定制 policy 仓，命令 SHALL 同时带 `--policy .witnessloop/policy.json`）」。这是本 Requirement 里定义升级动作的那一句。
- 结论：**已修**。残留的同类问题只在别处（见 N2），不否定本项修复。

### L1–L8 — 全部已修

| 项 | 结论 | 证据 |
| --- | --- | --- |
| L1 历史 allowlist 不完整 | **已修** | `tasks.md:32` 现含 `openspec/specs/dev-workflow-gate/spec.md:73/:191/:195`、`docs/development-guide.md:385/:441`、ADR-0006 `:30/:68`；实查 `spec.md:73/:191/:195` 与 `development-guide.md:385/:441` 均为历史实测记录，正确列入 allowlist。当前态命中（caller:14、台账:7、spec:7/:225/:238/:239、dev-guide:381/:389-395、Q12:28）全部在 2.2/2.3/2.4 的更新清单内，无漏项。 |
| L2 「全为 A」是条件命题 | **已修（附 nit）** | `design.md:73-75` 已改为「可能全为 A，也可能出现 R100；无论哪种，唯一 build 点在归档后」。但「R100 可能出现」的依据不成立（见 N1），不影响 build 点结论。 |
| L3 manifest build 命令未钉 | **已修** | `tasks.md:50`（5.3）现写全 `--root . --change … --base origin/master --stage … --report …`；`--stage`/`--report` 是 CLI required（`/tmp/wl171/src/witnessloop/cli.py:118-143`）。 |
| L4 5.4 与 5.1 次序重复 | **已修** | `tasks.md:51`（5.4）现为「单独提交 manifest 证据（events 已在 5.1 结算并随 move 提交，不再编辑）」。 |
| L5 5.6 混入合入方式 | **已修** | `tasks.md:53`（5.6）以「发起 PR」收尾；merge 方式在 `tasks.md:59`（6.3）。 |
| L6 规范句缺 `--policy` | **已修（spec 主句）** | delta `:21` 已补；但新 scenario `:43`、proposal 回滚行、dev-guide:381 仍有裸命令，登记为 N2（low）。 |
| L7 7.2 未复述完整 init 命令 | **已修** | `tasks.md:64`（7.2）现复述完整 `--gate-ref` + `--policy` 命令，并注明 plain init 退 1 是既有预期。 |
| L8 回归证据口径 | **已修** | `proposal.md:48` 现写「回归证据 = PR 的 `gate / check` 日志（包 ref 来自 tag）+ init 幂等实测」，并保留全量 pytest / OpenSpec validate / 瘦 checker 的基线验证。 |

## 逐条对抗结论

### 本轮重点证伪的三项

1. **5 个 scenario 与主 spec 现有 4 个的逐字一致性：通过。** 3 个应保留的 scenario（required 只剩、require_change_for、witnessloop 单套）标题与全部 AND 行逐字节相同；`caller 钉住的 ref` 是本次**必须改**的 scenario，diff 仅含预期条款（版本、推导、`--policy`、不得只改一边）；`应急 commit pin 必须回钉` 是唯一新增。机械应用（OpenSpec 1.4.1 `buildUpdatedSpec`）不抛错、无 warning、应用后恰 5 个 scenario。
2. **tasks 2.2 是否足以避免静默丢失：对 Round 1 的失败模式足够，但只覆盖 scenario 级别。** 标题集合断言能抓住「整条 scenario 被漏抄」（M1 的原始形态）；若执行者手工逐行合并、漏掉某条保留 scenario 内的一个 AND 行，标题集合断言仍会通过。delta 现在已是完整源文本，且 OpenSpec 的 MODIFIED 是整块替换，这个残余风险很低，但可以零成本消除（见 N3）。
3. **`--policy` 是否在正确的规范句：是。** delta `:21` 正是「升级动作 SHALL 是 `witnessloop init --gate-ref <新 ref>` 一处改动」那一句，补上了本仓定制 policy 的强制参数。残余的裸命令在**另外三处**（见 N2），不在该规范句里。

### 其余维度的再核验（未发现 medium+）

- **证据次序**：`design.md:59-69`（Decision 6）与 `tasks.md:7`、`:48-53`（5.1→5.5）的次序是「内容 → move → 归档目录名 build → 证据提交 → check」。`manifestcmd.py:155` 用 build 时刻的 `HEAD` 作 `head_sha`；`contract.py:734-813` 要求 `head_sha` 是被检 head 的祖先，且其后只允许证据路径。该次序自洽；本地 check 的「0 target 假绿」本轮用未提交树复现（`0 个变更文件，0 个 change 目录` + `通过 ✓`），T7 / 5.5 的 `1 个 change 目录` + 归档 target 断言是必要的，已保留。
- **归档点完成度**：用同一 `POST_MERGE_TAG_RE`（`scripts/check_openspec_artifacts.py:111-114`）机械核对 `tasks.md`：未勾项中只有 6.1–6.3、7.1–7.2 匹配 `(post-merge)`；其余未勾项（0.x–5.x）由 `tasks.md:48`（5.1）按终态结算。归档点的「≥1 已勾 + 未勾必须带标记」可满足。
- **受保护写入事件**：本 diff 触及的受保护路径是 `openspec/specs/dev-workflow-gate/spec.md`、`.witnessloop/init-manifest.json`、`docs/openspec-change-backlog.md`（`.witnessloop/policy.json` 明确不改）。事件计划为 `current_spec_synced` + `protected_artifact_explained` + `backlog_updated`（`design.md:37-49`、`tasks.md:48`）；现有事件文件已有序号 2（backlog）与 3（init-manifest），`current_spec_synced` 属实现期写入，符合计划。`events.load_all` 同时扫描 active 与归档层（`events.py:80-103`），归档后的 move 不会让事件失效。
- **manifest 绑定**：5.3 逐份 `--stage/--report` 绑定 `reviews/` 下三份 `.md`（`grill-design` / `grill-adversarial` / `building-review`），4.2 清理未绑定中间产物；归档目录内的 manifest 属于 stale 豁免集（`policy.py:83-91` 的 `archive/**`），证据提交不会触发「旧 revision」。
- **checker / RIR / Impact**：`research_tier: light` + `status: enabled` + findings/design impact 齐全（`proposal.md:53-61`），与同类 process change 的先例 `openspec/changes/archive/2026-10-17-stage-c-required-switch/` 的 light 判法一致；`## Impact Analysis` 非占位且含回滚/风险；本仓瘦 checker 实跑 exit 0，`openspec validate --all --strict` 29 passed、delta `--strict` valid。
- **外部事实**：issue #331 存在且标题为「【feature】witnessloop caller 回钉 v1.7.1 并同步 init 台账」（OPEN）；witnessloop `v1.7.1` 是 annotated tag，tag object `c4f681a7…` → commit `07bf23b3…`；witnessloop issue #42 已 CLOSED；本仓 caller 仍钉 `c9b2811…`（`.github/workflows/witnessloop.yml:14`）、台账 `gate_ref` 仍为 `@v1.7.0`（`.witnessloop/init-manifest.json:7`），与 design 的现状描述一致。

### 新发现（按 severity）

- **N2 [low] 裸 `witnessloop init --gate-ref` 仍在三处以「当前/回滚操作」出现。**
  1. delta `:43`（新增的应急 scenario）：「用 `witnessloop init --gate-ref <新 tag>` 同步台账」——本仓不带 `--policy` 时，`initcmd.py:149-215` 会先重写 caller 与台账（不回滚），随后 `initcmd.py:494-626` 因出厂 policy 与盘上定制 policy 冲突 exit 1（本轮已读源码确认；与 Decision 2 的描述一致）。建议在该行末尾复用 `:21` 的括注，或写「按本仓命令（含 `--policy`）同步台账」。
  2. `proposal.md:51`（回滚行）：「用同一工具 `init --gate-ref <该 commit>`」。两处问题：缺 `--policy`；且 `--gate-ref` 会被原样写进 caller 的 `uses: {gate_ref}`（`initcmd.py:30-46`），只给 commit sha 会产出 `uses: c9b2811…` 这种非法 workflow 引用。回滚目标应写完整 ref `Xingkai98/witnessloop/.github/workflows/gate.yml@c9b281167ad20b63e4832ad9ab8510964a2adc60`，并带 `--policy`。
  3. `docs/development-guide.md:381` 的当前态升级句仍是 `witnessloop init --gate-ref <新 ref>`；`tasks.md:30`（2.3）只要求改版本、推导与本地 check 锚点，没有明确要求给升级命令补 `--policy`。
  以上三处都不影响本 change 的主路径，且失败是响亮、可恢复的，故登记 low、不要求本轮修；建议在 2.3 与 2.1 顺手同步。
- **N3 [low] tasks 2.2 / T8 只断言 scenario 标题集合，不覆盖 AND 行丢失。** 证据：`tasks.md:29`、`design.md:111`。既然 delta 已是完整源文本，可把断言升级为「主 spec 该 Requirement 块（正文 + 5 个 scenario）与 delta 块逐字节一致」或至少「3 个未改 scenario 与主 spec 逐字节一致」；本轮已实测后者可机械做（临时副本上 3 项均为 true）。不阻断：整块替换的自然执行方式不会触发该风险。
- **N1 [nit] Decision 7 的「也可能出现 R100（先提交 active 再 move）」事实依据不成立。** 本 change 的目录在 base 树不存在（`git ls-tree -d origin/master openspec/changes/` 无 repin 目录），`git diff base...head` 的旧侧没有可配对的 blobs，无论哪种提交次序最终都显示为 `A`。结论（唯一 build 点在归档后、用归档目录名）不受影响；只是理由句不精确，建议改成「base 树没有该目录，最终 diff 不产生 rename；即便在别的基线下出现 R100，唯一 build 点也不变」。
- **N4 [nit] 5.2/5.3 没有明写「build 必须停在已提交的内容+move HEAD 上」。** `manifestcmd.py:155` 取 build 时刻 HEAD；若此时内容/move 尚未提交，随后证据提交会把非证据内容一起带过 `head_sha`，在 `contract.py:794-813` 判「审阅的是旧 revision」（响亮红）。`tasks.md:7`/`:51` 的上下文中可推出，但建议 5.3 加一句「在已提交的内容+move 之上 build」。
- **N5 [nit] 5.3 自称「完整命令」但用 `uvx ...` 省略了 `--from` 源。** `tasks.md:50`；1.1 / 5.5 已给出完整 `uvx --from git+…@refs/tags/v1.7.1`，可复现性不受损，建议 5.3 直接重复该源。
- **N6 [nit] 2.5 的 allowlist 仍是行号清单，2.2/2.3 编辑后会漂移。** `tasks.md:32`；建议改为「当前态文件零命中 + 历史命中按文本片段 allowlist」，或把扫描命令固定下来，降低后续漏项概率（Round 1 风险 6 的同一建议，仍未落到命令级）。

## 需要修改的设计点

无（0 条 medium+）。

## Open Questions

本 change 的 Open Question 数为 **0**。

理由：本轮全部结论均可由 OpenSpec 1.4.1 源码/机械应用、witnessloop v1.7.1 源码、本仓 policy/spec/checker、git 与 gh 事实判定；新发现的 low/nit 都有唯一推荐改法（补参数、补完整 ref、加强断言、改措辞），不涉及需要在多个合理产品/流程价值之间取舍的用户决策。grill 报告与 Round 1 的 0 条 Open Question 也不因本轮新增用户决策项。

## 风险

1. **M1 的修法已被机械验证，但验证方式本身值得保留。** 本轮的临时副本应用证明 `buildUpdatedSpec` 不抛错、无 warning、5 个 scenario 全在；这是比「人工比对标题」更强的证据。建议把「同步后与 delta 块做块级比对」写进 2.2（N3），让这个证据在实现期可重复生成。
2. **三处裸 `init --gate-ref` 命令会把已知的「半完成 + 响亮失败」陷阱留在规范/操作文档里。** 失败是 exit 1 且不回滚 caller/台账，恢复需要重跑带 `--policy` 的命令；本轮登记为 low，是因为它不在本 change 的实现路径上，但建议在 2.1/2.3 顺手消除（N2）。
3. **`current_spec_synced` 事件目前只能由实现期 5.1 补写。** 若忘记，5.5 的本地 `check` 会以「受保护路径被写入但没有结构化解释事件」判红；不要为了绕过它把 check 提前或放宽。事件读取覆盖归档层（`events.py:80-103`），归档不会让事件失效。
4. **manifest build 必须停在已提交的内容+move HEAD。** 若把 spec/backlog/docs 改动留到证据提交一起提交，`head_sha` 之后会出现非证据文件，check 判 stale（`contract.py:794-813`）。这是响亮红，不是静默错；建议按 N4 补一句任务措辞。
5. **5.3 build 时的 `origin/master` 新鲜度不会像 check 那样被强校验。** `_check_git_span` 只验证 `base_sha` 是真实提交，不要求它等于 check 使用的 base；因此 stale base 不会红，只会让 manifest 绑定一个较旧的 base。5.5 已要求 `git fetch` 并记录 `rev-parse`，建议 5.3 也先 fetch。
6. **`gate.yml` 的 fallback 也是 `v1.7.1`**（`/tmp/wl171/.github/workflows/gate.yml:72`），所以「日志里 ref=refs/tags/v1.7.1」单独不足以证明走的是 tag 分支；6.1 要求核对**来源**为「`job.workflow_ref` 的 tag ref」是正确的判别器，必须保留（fallback 时来源会是 `fail-closed：…` 并带 `::warning::`）。
7. **未提交树的 `check` 假绿可复现**：本轮实跑输出 `0 个变更文件，0 个 change 目录` + `check：通过 ✓`。5.5 的四项断言——`requested_revision=refs/tags/v1.7.1`、`1 个 change 目录`、`change：2026-10-20-repin-v1.7.1（归档）`、`check：通过 ✓`——必须同时保留，不能退化成只看 exit 0。
