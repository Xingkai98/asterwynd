# 设计阶段审阅（grill-review）

- **审阅者**: 独立零记忆设计审阅 subagent（不继承开发上下文）
- **时间**: 2026-10-07
- **对象**: `openspec/changes/grill-flow-hardening/{proposal.md, design.md, tasks.md, specs/*/spec.md}` 与 `reviews/grill-design.md`
- **方法**: 默认设计有错，逐条尝试证伪 `design.md` D1–D5 与 `grill-design.md` Confirmed Decisions；阅读被改代码（`scripts/check_openspec_artifacts.py`、`scripts/workflow_guard.py`、`agent/workflow/review_manifest.py`）+ 全仓 `grep` + **对 checker 做真实运行实验**。凡标「证据」者均为本机真实读取/命令结果。

## Verdict

**CHANGES_REQUESTED**

设计方向（grill 加固 + 上游改名对齐 + 设计阶段对抗闭环 + code-resolved 语义）**成立且动机充分**，但三处**机械落点事实错误**会在实现阶段直接炸掉本 change 自身的 CI，必须在停轮前修：

- **F1（阻断）**：产物名 `grill-review.md` 命中 checker 既有 `*-review.md` glob，会在**两个 CI 步骤**上强制要求不存在的 `grill-review-manifest.json`。已实测复现。
- **F2（阻断）**：D3 把机械门触发点指到 `_check_review_manifests`，但那不是「归档点」——building-review 的归档点强制在另一个函数 `_check_archived_completion_gate` 里，且触发口径**不同**（后者不要求 tasks 全勾）。按 design 现在的写法实现会同时破坏「触发点=归档点」与「不误伤在途」两条自我承诺。
- **F3（阻断）**：R1 / task 6.1 的验收「`grep batch-grill-me` 应为空（除 archive）」**结构上不可达**——本 change 自己的 `proposal.md`/`design.md`/`tasks.md`/`grill-design.md` 就合法引用旧名（描述这次改名），且 Q1 的在途 change 也仍引用。验收口径必须先收窄。

## Decision Challenge

### design.md D1 — skill 引用名 = `grilling` → **survives**

- 本机实装 `~/.claude/skills/grilling/SKILL.md:11-33` 的 `grilling` 恰是「design tree + rounds + frontier + 每轮整条 frontier」——与本仓「设计树逐轮追问」口径逐字吻合（证据：`~/.claude/skills/grilling/SKILL.md:1-33`）。
- 改名后 checker 兼容分支保留旧名（`scripts/check_openspec_artifacts.py:672-678` 现存 `batch-grill` 子串已能匹配 `batch-grill-me`；新增 `grilling` 不误匹配任何旧串）。
- 关于 `/grill`（harness 命令）与 `grilling`（skill）并存的轻微混淆：design 已声明二者解耦，且 `.gitignore:9` 证明 `/grill` 命令不进 git。**判 survives**（建议见 F4，非阻断）。
- 证据缺口（不影响结论）：`grill-design.md:13` 引用的上游 `docs/productivity/grilling.md:54-55/16/41/87` 在本机**不存在**（`find / -name grilling.md` 无结果），无法独立复核那几行逐字引用；但 D1 的**实质**（`grilling` 是 round-based 追问原语、`grill-with-docs` 额外承诺产 GLOSSARY/ADR）由本机 `grilling` skill 正文 + design.md:14 一致支撑，结论不依赖那几行。

### design.md D2 — 设计阶段审阅闭环「与 `/review-loop` 完全同构」，产物 `reviews/grill-review.md` → **refuted**

- **闭环概念本身成立**：独立零记忆审阅者 → 对抗 → verdict → 修 → 再审、且不替代实现后 `/review-loop`——这与 `#280` 教训（`grill-conclusions-need-adversarial-review`）一致，4 个 `grill-adversarial.md` 先例真实存在（证据：`find openspec/changes -name 'grill-adversarial*.md'` → `2026-10-02-read-output-bound` / `2026-10-03-foreach-budget-truncation-visibility` / `2026-10-03-tool-result-lifecycle` / `2026-10-03-foreach-truncation-visibility`）。收敛口径「3 轮封顶」在代码里也被引用（`scripts/check_openspec_artifacts.py:1137`）。
- **但产物名 `grill-review.md` 被证伪**：checker 对 `reviews/` 下**任何** `*-review.md` 无条件做**全量 manifest 校验**（`scripts/check_openspec_artifacts.py:1148-1150` glob → `verify_review_manifest`），而 `verify_review_manifest` 要求 `<phase>-review-manifest.json` 存在 + `verdict==PASS` + `reviewer_run_id/base_sha/head_sha/tasks_hash/spec_hash/diff_hash/report_hash` 齐全（`agent/workflow/review_manifest.py:142-181`）。`grill-review.md` → phase `grill` → 需要 `grill-review-manifest.json`。
- **实测复现**（本 worktree 真跑）：

  ```
  $ printf '# 设计阶段审阅（grill-review）\n\n## Verdict\nPASS\n' > openspec/changes/grill-flow-hardening/reviews/grill-review.md
  $ PYTHONPATH=. python3 scripts/check_openspec_artifacts.py --change grill-flow-hardening
  ERROR: grill-flow-hardening: review manifest missing:
         openspec/changes/grill-flow-hardening/reviews/grill-review-manifest.json
  ```

  即：**本 change 按 design 落地后，自己的 `check_change`（CI 第一步 `ci.yml:88` 会跑到）与 `--check-archived`（`ci.yml:96`，对归档目录也 glob `*-review.md`，`check_openspec_artifacts.py:1722`）都会红**——除非同时产出 `grill-review-manifest.json`。而 design D2/D3/tasks **从未提及** grill 阶段要产 manifest（D3 明确说门是「存在性」）。对照：4 个先例用的是 `grill-adversarial.md`，**不**以 `-review.md` 结尾，故**不**触发该 glob——是本次**改名**引入了碰撞。
- **另有文档内部矛盾**：`design.md:50,55` 与 `tasks.md:10` 写 `grill-review.md`；而 `reviews/grill-design.md:15` 写 `reviews/grill-adversarial.md`。两份设计文档对同一产物给了两个名字，且其中恰有一个（`grill-adversarial.md`）**不**炸 glob。**判 refuted**——命名子决策必须二选一并声明 manifest 口径。

### design.md D3 — 机械门「触发口径与 building-review 完全一致，见 `_check_review_manifests`」→ **refuted**

- design.md:60 声称「触发口径与 `building-review.md` 完全一致，见 `_check_review_manifests`」，并把触发点定为**归档点**、承诺「不追溯历史、不误伤在途」（design.md:60,92）。三点均与代码不符：
  1. **building-review 有两个执法点，不是一个**：活动/漂移面在 `_check_review_manifests`（`scripts/check_openspec_artifacts.py:1127-1138`，条件 `not archived and primary!=docs and 有 spec delta and _tasks_all_complete`）；**归档点面在 `_check_archived_completion_gate`（`:1614-1622`，条件 `primary!=docs and 有 spec delta`，**不含** `_tasks_all_complete`**，因为归档侧传 `assume_implemented=True`，`:1609-1611`）。design 只引了前者。
  2. **后者才是「归档点」**：D3 想要「本 PR 新归档才求值」，那正是 `_check_archived_completion_gate`（经 `_check_new_archived_completion_gates`，`:1645-1667`，只对本 diff 新归档目录求值）。**只加到 `_check_review_manifests` 是错的**——它按「活动 change」逐目录求值、与 PR diff 无关，会把**任何** tasks 全勾的在途 change（例：`add-minimal-tui-runtime-view` 一旦勾完）拉进来，恰是 design 承诺要避免的「误伤在途」。
  3. **自相矛盾**：design.md:60 同时写「非 docs + 有 spec delta + **tasks 全勾**」（= `_check_review_manifests` 口径）与「触发点=归档点」（= `_check_archived_completion_gate` 口径，**不**看 tasks 全勾）。二者不是同一口径。
- 结论：D3 的**目标**（归档点、存在性、不追溯）合理，但**落点描述错误**，照写会实现到错误触发器上。**判 refuted**。

### design.md D4 — code-resolved 移出 `## Open Questions`、不要求 User Confirmation → **survives**

- checker 的「未确认」判定**只**读 `## Open Questions`：`_extract_open_question_indexes` 取 `_extract_h2_sections(text).get("Open Questions")`（`scripts/check_openspec_artifacts.py:814-820`），`_unconfirmed_open_questions` 用它（`:872-878`）。
- guard 同款：`scripts/workflow_guard.py` 的 `_extract_open_question_indexes` 用 `_h2_section(text, "Open Questions")`（证据：guard 内该函数定义处，正文注释「mirrors scripts/check_openspec_artifacts.py」），evidence-completeness 分支只在 Open Questions 有未确认项时拦（`scripts/workflow_guard.py:390-408`）。
- 故「物理移出 `## Open Questions` → 同时放松停轮队列与门禁」成立，且**无需**额外联动改造。**判 survives**。
- 残留（非阻断，= Q3 的边界）：该语义依赖实现者**真的把条目移节**；若只是节内打标签，门仍要求确认。design R2 已自认「语义约束，非机械可验」。

### design.md D5 — 文档/spec 改动面「穷举」→ **refuted**

- 逐文件计数**准确**：`AGENTS.md` 4 处（`:18,72,77,96`）、`docs/requirements-process.md` 8 处（`:43,179,183,187,242,277,280,329`）、`docs/agents/domain.md` 2 处（`:11,25`）、`openspec/project.md` 2 处（`:56,62`）、`openspec/templates/tasks.md` 1 处（`:5`）；spec 3 处（`change-documentation/spec.md:71,73`、`dev-workflow-state-machine/spec.md:256`、`subagents/spec.md:278`）。
- 但表**漏**在途 change `openspec/changes/add-minimal-tui-runtime-view/`——`design.md:53` 与 `tasks.md:7` 仍写 `batch-grill-me`（证据：`grep -rn batch-grill-me openspec/changes/add-minimal-tui-runtime-view/`）。称「穷举」为时过早。**判 refuted**（= Q1）。
- 且 D5/R1 的**验收**（design.md:90,104「完成后 `grep -rn batch-grill-me`（排除 archive）应为空」= tasks.md:43 的 6.1）**不可达**：本 change 自己的 `proposal.md`（`:16,18,37,51,52`）、`design.md`（`:11,14,38,77,82,83,84,90,100,104`）、`tasks.md`（`:16,17,36`）、`reviews/grill-design.md`（`:12,13,20,35`）**合法**引用旧名（正是「描述这次改名」），排除 archive 后仍非空。见 F3。

### `grill-design.md` Confirmed Decisions 对照

- bullet 1（名 = `grilling`）= design D1 → **survives**。
- bullet 2（post-grill 作答是 grill 内部步骤、产物 `grill-adversarial.md`、≠ `/review-loop`）→ 概念 survives，但**产物名与 design.md:50,55 冲突**，且 design.md 侧的 `grill-review.md` 名称被证伪 → 见 D2 / F1。
- bullet 3（checker 同时接受新名与旧名、二者皆无仍报错）→ **survives**（`scripts/check_openspec_artifacts.py:672-678,788-794`；旧名 `batch-grill` 子串覆盖 `batch-grill-me`，101 个归档 + 1 个在途不被误伤）。
- bullet 4（code-resolved 不进停轮）→ **survives**（= D4）。
- bullet 5（process 型、零运行时改动）→ **survives**（`DESIGN_TYPES={feature,refactor,process}`，`scripts/check_openspec_artifacts.py:31-32`；本 change 不触 `agent/`/CLI/Web/benchmark。注意：**零运行时不等于零机械面**——F1 的 manifest 碰撞就是被忽略的机械面）。

**合计：survives 2（D1、D4）/ refuted 3（D2、D3、D5）。**

## Code-Resolved Questions

### Q1（原 `grill-design.md` Open Question）→ **code-resolved**

- **问题**：改名范围是否纳入**在途** change `add-minimal-tui-runtime-view`？
- **代码事实**：是，该在途 change **确实**引用旧名，共 2 处：`openspec/changes/add-minimal-tui-runtime-view/design.md:53` 与 `.../tasks.md:7`。该 change 处于 proposal 阶段（`grep -c '\- \[ \]'` = 18，`- [x]` = 0），且不在 `archive/` 下，task 6.1 的 `grep`（仅排除 archive）会命中它（证据：`grep -rn batch-grill-me openspec/changes/add-minimal-tui-runtime-view/`）。
- **结论**：取 **A（纳入改名）**。理由由代码定：① 只需改 2 处、且该 change 0/18 未实现，成本最低；② 本次 Why 的核心是「文档不得引用装不到的 skill」，留一条在途例外自相矛盾；③ 若取 B，则 task 6.1 必须把排除面从「除 archive」收窄为「除 `archive/` **与** `openspec/changes/**`」——但那样会**顺带掩盖本 change 自身**的合法引用（见 F3），语义更差。故 A 是唯一能同时满足 R1 目标的选项。
- **附带修正（必须写进设计）**：即便取 A，task 6.1 仍需**额外排除本 change 自己的目录** `openspec/changes/grill-flow-hardening/**`，因为其 `proposal/design/tasks/grill-design` 合法描述改名、必然含旧名。6.1 的验收口径应表述为「旧名仅允许出现在 `openspec/changes/archive/**` 与 `openspec/changes/grill-flow-hardening/**`」。
- 证据：`openspec/changes/add-minimal-tui-runtime-view/design.md:53`、`.../tasks.md:7`；`openspec/changes/grill-flow-hardening/{proposal.md,design.md,tasks.md,reviews/grill-design.md}` 的 `grep` 命中。

## Remaining Open Questions

以下为**真正需要人拍板**的条目，本审阅保留待停轮（每条配具体例子）：

### Q2 → **user-decision**（本轮是否就上 `grill-review` 机械文件门）

- **这是范围/节奏取舍，非代码可判**。但给出代码侧硬约束以助拍板：**无论 A/B，产物名必须先按 F1 定案**——若维持 `grill-review.md`，则「存在性门」这个说法本身不成立（checker 会要求 manifest，见 F1），D3 的口径要重写为「manifest 门」；若改用 `grill-adversarial.md`（不撞 glob），才能实现 design 现在所写的「仅存在性」门。
- **具体例子**：设本轮上「仅存在性」门且产物名沿用 `grill-review.md`。下一个 `feature` change 归档时 `reviews/` 下只有 `grill-design.md` + `grill-review.md` + `building-review.md`，`check_openspec_artifacts.py --change <id>` 会报 `review manifest missing: .../grill-review-manifest.json`——门比设计者预期**严**了一档，且拦的是**每个**非 docs change。
- **建议**：**A**（本轮上），但**前提是 F1 定案**——若选 `grill-adversarial.md` 名，则「存在性门」按 design D3 措辞可原样实现。

### Q3 → **user-decision**（是否给 `## Code-Resolved Questions` 加证据形状校验）

- **这是严格度/成本取舍**，代码不能判。给出代码事实：现有 grill 证据门用「`## Confirmed Decisions` ≥ 3 条」做数量门槛（`scripts/check_openspec_artifacts.py:753-757`）；同构地加一条 `\S+:\d+` 形状门槛（要求每条 code-resolved 至少含 `文件:行号` 形态 token）在实现上可行，位置与 `_extract_grill_decisions` 平行。
- **具体例子**：某 change 的 Open Question 是「新 CLI 默认输出用 JSON 还是表格？」（**产品意图**）。作答 run 写成 `- **Q4**（code-resolved）：结论：用 JSON。证据：cli/output.py:88`，而该行只定义 `OutputFormat` 枚举、未「决定」默认值。**形状校验拦不住**它（证据形状合法），只有停轮时人的一眼核对能拦。故形状校验只保证「有证据样」，不保证「证据真」——是否值得加，属人做主的成本/收益取舍。
- **建议**：**B**（不加）。理由：形状校验的边际价值仅限于拦「完全空答」，而空答在停轮时人一眼可见；引入正则门槛只会增加机械复杂度与假阳性面（例如一条以「结论」代替 `文件:行号` 但内容扎实的合法答案会被误拦）。**此为建议，最终请用户拍板。**

## Findings

按必须修优先级排列：

- **F1（阻断 — 命名/机械面）**：`reviews/grill-review.md` 命中 `scripts/check_openspec_artifacts.py:1148-1150` 的 `*-review.md` glob，触发 `verify_review_manifest`（`agent/workflow/review_manifest.py:142-181`）强制要求 `grill-review-manifest.json`（含 PASS verdict + reviewer run + sha + 多 hash）。**已在两步 CI 路径上实测复现**（见 D2 复现块）；`ci.yml:88` 与 `ci.yml:96-97`（经 `check_openspec_artifacts.py:1722`）都会红。
  - **必须修**：二选一——(a) 产物名改为**不以 `-review.md` 结尾**（推荐保留先例名 `grill-adversarial.md`；`reviews/grill-design.md:15` 本就写它），并让 `design.md:50,55`、`tasks.md:10` 与之统一；或 (b) 明确 grill 阶段**也产 manifest**（新增 task：跑 `review` manifest CLI 生成 `grill-review-manifest.json`，绑定 reviewer run + base/head sha），并把 `design.md:50,62` 的「存在性门」改写为「manifest 门」。**注意 (b) 会让本 change 自我施加一份 grill 阶段 manifest 义务，须在 tasks 里显式列出。**
  - 附：**本次审阅的这一文件本身**（`reviews/grill-review.md`）就是这条碰撞的活证据——在该 change 自身 CI 通过前，F1 必须先解决。

- **F2（阻断 — 触发落点）**：`design.md:60` 将机械门触发点描述为「归档点、与 building-review 完全一致，见 `_check_review_manifests`」，但归档点的 building-review 强制实际在 `_check_archived_completion_gate`（`scripts/check_openspec_artifacts.py:1614-1622`，经 `:1645-1667` 只对本 PR 新归档目录求值，且**不**要求 tasks 全勾）；`_check_review_manifests`（`:1127-1138`）是活动/漂移面，条件含 `_tasks_all_complete`、与归档点无关。
  - **必须修**：D3 明确新门加在 `_check_archived_completion_gate`（归档点、仅新归档目录、`assume_implemented=True` 口径），如需兼顾活动面再**显式**说明同步到 `_check_review_manifests`；并消除 design.md:60「tasks 全勾」与「归档点」的口径自相矛盾。

- **F3（阻断 — 验收不可达）**：R1（`design.md:90,104`）与 task 6.1（`tasks.md:43`）要求「`grep batch-grill-me` 除 archive 外为空」，但本 change 自身文档合法引用旧名（`proposal.md`/`design.md`/`tasks.md`/`reviews/grill-design.md` 共 20+ 处，见 D5）。
  - **必须修**：把 6.1 验收口径改为「旧名仅允许出现在 `openspec/changes/archive/**` 与 `openspec/changes/grill-flow-hardening/**`」；并按 Q1 结论处理 `add-minimal-tui-runtime-view/{design.md:53,tasks.md:7}`。

- **F4（建议 — 非阻断）**：改名后现状存在 **`grilling`（skill）与 `/grill`（harness 命令）同名近似**，`AGENTS.md` 将同时出现「使用 `grilling` skill」与「`/grill` 命令」。建议 3.1 的文档正文显式区分二者（skill vs 命令），避免读者把两处当成同一物。

- **F5（建议 — 非阻断）**：`design.md:62` 的 D2 风险与 `design.md:92` 的 R3 都建立在「触发点=归档点」之上；在 F2 修好前这些缓解措辞不成立，建议随 F2 一并回写。

## Round 2

- **审阅者**: 独立零记忆设计审阅 subagent（R2；不继承 R1 与开发上下文）
- **时间**: 2026-10-07
- **对象**: R1 三项阻断（F1/F2/F3）的修复复核，及修复本身是否引入新问题
- **方法**: 读修订后的 `design.md` / `tasks.md` / `specs/*/spec.md` / `reviews/grill-design.md`；读被改 checker 的精确行（`scripts/check_openspec_artifacts.py:1127-1151`、`:1614-1622`、`:1645-1667`）；**真跑** `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py` 与 `openspec validate --all --strict`；全仓 `grep -rn batch-grill-me`（排除 `archive/`）。凡标「证据」者均为本机真实命令结果。

### R2 Verdict

**CHANGES_REQUESTED**

- **F1 已修净**（产物名统一为 `grill-adversarial.md`，不撞 glob；checker 实跑通过）。
- **F2 已修净**（D3 落点改到 `_check_archived_completion_gate`，行号逐一核对无误，自相矛盾消除）。
- **F3 口径已改但验收仍不可达**：6.1 的「允许面」已加本 change 自身目录，但**在途 change `add-minimal-tui-runtime-view` 的 2 处旧名无人处理**（Q1 已判「纳入改名」，`tasks.md` 却无对应任务）→ 6.1 仍结构不可达。新增 **F6（阻断）**；另 **F7（非阻断）** 一处字面残留。

### F1 复核 — 产物名撞 `*-review.md` glob → **已修**

- 设计产物名已统一为 `grill-adversarial.md`：`design.md:21,50,55,64,66,98,109`、`tasks.md:10,30,39`、`specs/change-documentation/spec.md:24,68`、`specs/dev-workflow-state-machine/spec.md:9,28` 全部用新名。`grep -rn "grill-review"` 在**设计产物**（`proposal.md`/`design.md`/`tasks.md`/`specs/**`/`grill-design.md`）**为空**（exit 1）。
- 剩余 `grill-review` 命中**全部落在 R1 报告自身**（`reviews/grill-adversarial.md`，即本文件）——那是 R1 对旧名的**历史证伪正文**，按复核要求原样保留，不是设计产物。**关键**：本文件**文件名**是 `grill-adversarial.md`（不以 `-review.md` 结尾），故**不触发** `scripts/check_openspec_artifacts.py:1148` 的 `*-review.md` glob；其正文里出现 `grill-review.md` 字样对 checker 无影响。
- **实测（验收要求）**：`reviews/` 现为 `grill-adversarial.md` + `grill-design.md`，无任何 `*-review.md`；`PYTHONPATH=. python3 scripts/check_openspec_artifacts.py` → `OpenSpec artifact checks passed`（EXIT=0），**不再**因缺失 `grill-(...)-manifest.json` 报错。R1 的 F1 阻断消除。

### F2 复核 — 机械门落点 → **已修**

- `design.md:58-64` 已把 D3 落点改到 **`_check_archived_completion_gate`**，并显式说明**不加**到 `_check_review_manifests`（避免把 tasks 全勾的在途 change 拉进来）。
- **行号逐一核对无误**：`_check_review_manifests` 的 `requires_building_review`（含 `_tasks_all_complete`）实际在 `scripts/check_openspec_artifacts.py:1127-1132`、glob 在 `:1148`（design 写 `:1127-1150`，覆盖 ✓）；`_check_archived_completion_gate` 的 building-review **存在性**块（`primary!=docs and _changed_capabilities and not building-review.exists()`，**不含** `_tasks_all_complete`）实际在 `:1614-1622`（design 写 `:1614-1622`，精确 ✓）；`_check_new_archived_completion_gates` 在 `:1645`、其 `_check_archived_completion_gate(...)` 循环在 `:1666`（design 写 `:1645-1667` ✓）。归档侧 `assume_implemented=True` 见 `:1609-1611`，与 design 描述一致。
- **自相矛盾已消除**：design.md:60-64 现已明说归档点口径**不含** `_tasks_all_complete`，不再是 R1 指出的「tasks 全勾 + 归档点」二义。R3（design.md:98）与 D3 口径随之对齐，R1 的 F5 建议消解。

### F3 复核 — 验收不可达 → **口径已改，验收仍未达（未修净）**

- **已改部分 ✓**：`design.md:96`（R1 允许面 = `openspec/changes/archive/**` + 本 change 自身目录 `openspec/changes/grill-flow-hardening/**`）、`design.md:110`（Testing Strategy 同口径）、`tasks.md:43`（6.1 同措辞）——本 change 自身目录已排除。
- **未修净部分 ✗**：6.1 的允许面**仍不含在途 change**。实测 `grep -rn "batch-grill-me"`（除 `archive/`）在**本 change 目录之外**仍命中两处：`openspec/changes/add-minimal-tui-runtime-view/design.md:53` 与 `.../tasks.md:7`。二者既非 `archive/**`、亦非本 change 自身目录 → **6.1 按现措辞仍然不可达**。
- 而 `grill-design.md:55-58` 的 Q1 已 **code-resolved 为「纳入改名」**（含 `add-minimal-tui-runtime-view` 那 2 处），但 `tasks.md` 全篇**无任何**该在途 change 的改名任务（`grep -rn "add-minimal-tui-runtime-view" openspec/changes/grill-flow-hardening/` 仅命中 `reviews/`，任务清单零命中）。**决策落了、任务没落**——见 F6。

### 新 findings

- **F6（阻断 — F3 残留 / Q1 落空）**：Q1（`grill-design.md:56`）判「纳入在途 change 改名」，但 `tasks.md` 没有执行它的任务。按现 `tasks.md` 实现完本 change 后，6.1（`tasks.md:43`）会因 `add-minimal-tui-runtime-view/{design.md:53,tasks.md:7}` 残留旧名而**判红**——与 R1 指出的 F3 同类（验收不可达），只是从「本 change 自身引用」换成了「在途 change 引用」。
  - **必须修**（二选一）：(a) 在 §3「文档改动」补一条任务（如 3.6）：「`openspec/changes/add-minimal-tui-runtime-view/{design.md:53,tasks.md:7}` 的 `batch-grill-me` → `grilling`」——与 Q1 的「纳入」一致，**推荐**；**或** (b) 若决定本轮**不**动在途 change，则把 6.1（`tasks.md:43`）与 design.md:96/110 的允许面**再放宽**到含在途 change 目录，并同步改写 Q1 结论。R1 已论证 (b) 会顺带掩盖本 change 自身的合法引用、语义更差，故取 (a)。
  - 证据：`openspec/changes/add-minimal-tui-runtime-view/design.md:53`、`openspec/changes/add-minimal-tui-runtime-view/tasks.md:7`；`tasks.md:43`（6.1）；`grill-design.md:56`（Q1=纳入）；`grep -rn "add-minimal-tui-runtime-view" openspec/changes/grill-flow-hardening/`（仅命中 `reviews/`）。

- **F7（建议 — 非阻断，F1 残留字面）**：`design.md:55` 的「命名说明」仍以「（最终名留 grill 定，见 Open Questions）」结尾，但产物名**已定**为 `grill-adversarial.md`（F1 已落），且现存 Open Questions（`grill-design.md` 的 Q2 = 机械门、Q3 = 证据形状）**均不含命名**。该括号现为**悬空指向**，建议删除，或改指 Q2（机械门）。

- **（信息，非 finding）**：本文件首行标题仍为「设计阶段审阅（grill-review）」——那是 **R1 历史正文**（按复核要求原样保留），非设计产物缺陷；若担心读者误读，可另起一行注明，不影响门禁。

### R2 结论

F1、F2 **已修净**；F3 **口径已改、验收未达**（F6 阻断）。**修 F6 后** R2 三项阻断即全部消解，可进停轮（停轮项仍为 Q2/Q3；Q1 已 code-resolved）。

## Round 3

- **审阅者**: 独立零记忆设计审阅 subagent（R3；不继承 R1/R2 与开发上下文）
- **时间**: 2026-10-07
- **对象**: R2 的 F3/F6（在途 change 2 处旧名无人处理）与 F7（悬空「最终名留 grill 定」）修复复核；并确认 R1 F1/F2 保持修净
- **方法**: 读修订后的 `design.md` / `tasks.md` / `reviews/grill-design.md`；真跑 `grep -rn batch-grill-me`（分类计数）、`PYTHONPATH=. python3 scripts/check_openspec_artifacts.py`、`npx @fission-ai/openspec validate --all --strict`；逐一核对 checker 精确行号。凡标「证据」者均为本机真实命令结果。

### R3 Verdict

**PASS** — 设计可进停轮。

F3/F6 已修净（task 3.6 落位正确、6.1 验收恢复可达）；F7 两处措辞已修；R1 的 F1/F2 保持修净。停轮项仍为 **Q2/Q3**（Q1 已 code-resolved）。

### F3 + F6 复核（同一根因：在途 change 的 2 处旧名）→ **已修净**

- **task 3.6 存在且落位正确**（证据：`tasks.md:26`）：「**在途 change `add-minimal-tui-runtime-view`**：改其 `design.md:53` + `tasks.md:7` 的 `batch-grill-me` → `grilling`（Q1 code-resolved 结论：纳入改名）」。实测这两处**正是**旧名所在行：`openspec/changes/add-minimal-tui-runtime-view/design.md:53`（「开发前必须重新使用 `batch-grill-me` 或等价设计追问确认…」）与 `.../tasks.md:7`（「开发前使用 `batch-grill-me` 或等价设计追问审视 `design.md`…」）。
- **6.1 验收恢复可达**（逐面核对，证据：`grep -rn batch-grill-me` 全仓分类计数）：
  - **docs/spec 面**旧名命中 = `AGENTS.md`(4) + `docs/requirements-process.md`(8) + `docs/agents/domain.md`(2) + `openspec/project.md`(2) + `openspec/templates/tasks.md`(1) + `specs/{change-documentation(2),dev-workflow-state-machine(1),subagents(1)}` → **全部**由 task 3.1–3.5 + 2.1–2.3 覆盖；
  - **在途 change 面** = `add-minimal-tui-runtime-view` 的 2 处 → 由 **3.6** 覆盖（本 change 目录外**无第三处**旧名：`find openspec/changes -maxdepth 1 -mindepth 1 -type d` 仅 2 个 active——本 change + 该在途 change）；
  - **剩余** = `openspec/changes/archive/**`（允许）+ 本 change 自身目录（允许）。
  - 结论：执行 3.1–3.6 后，6.1 的允许面（`archive/**` + `openspec/changes/grill-flow-hardening/**`）**可达**。
- **边界确认（不构成残留）**：`grep -rn batch-grill-me` 的**裸**命中还含 `.py`——`scripts/check_openspec_artifacts.py:792`（错误文案）与 4 处 `tests/test_openspec_artifact_checker.py`（向后兼容用例）。二者**不属「活跃文档/spec」**（6.1 自带该限定词），且测试那 4 处是 task 5.2 **要求保留**旧名的正当面，不算未修净。

### F7 复核（悬空「最终名留 grill 定」）→ **已修**

- **`design.md:55`** 末句已改为「…（**名字已定：`grill-adversarial.md`，沿用先例**）」——原「（最终名留 grill 定，见 Open Questions）」的**悬空指向**消除（现存 Open Questions Q2/Q3 均不含命名）。
- **`design.md:39`**（D1 备选句）已改为「…**已定：取 `grilling`**（D1 经设计审阅闭环 R1 判 survives）」。
- 注：`design.md:69` 仍存「**留 grill 定**：是否本轮就上机械门…见 stop-turn Q2」——此为**门禁**取舍（Q2 真未决），非命名，措辞正确，**非残留**。

### R1 F1 / F2 保持性复核 → **未退回**

- **F1（产物名不撞 glob）**：`reviews/` 仍为 `grill-adversarial.md` + `grill-design.md`，无任何 `*-review.md`（证据：`ls openspec/changes/grill-flow-hardening/reviews/*-review.md` → 无匹配）；`grep -rn grill-review` 在设计产物（`proposal.md`/`design.md`/`tasks.md`/`specs/**`）**为空**（exit 1）；`PYTHONPATH=. python3 scripts/check_openspec_artifacts.py` → `OpenSpec artifact checks passed`（EXIT=0），不再要求 `grill-*-manifest.json`。
- **F2（门落点 = `_check_archived_completion_gate`）**：`design.md:58-64` 的 D3 落点未变；行号逐一复核无误——`_check_review_manifests` 的 `requires_building_review`（含 `_tasks_all_complete`）实为 `scripts/check_openspec_artifacts.py:1127-1132`、`*-review.md` glob 在 `:1148`（design 写 `:1127-1150`，覆盖 ✓）；`_check_archived_completion_gate` 的 building-review **存在性**块实为 `:1614-1622`（design 写 `:1614-1622`，精确 ✓），**不含** `_tasks_all_complete`，归档侧 `assume_implemented=True` 见 `:1609-1611`；`_check_new_archived_completion_gates` 在 `:1645`、其循环调用在 `:1666`（design 写 `:1645-1667` ✓）。
- `openspec validate --all --strict` → `Totals: 29 passed, 0 failed`（EXIT=0）。
- 剩余 `## Open Questions` 复核：`grill-design.md` 仅有 **Q2（机械门是否本轮上）** 与 **Q3（是否加证据形状校验）**，Q1 已在 `## Code-Resolved Questions`（`grill-design.md:53-58`）——与停轮队列一致。

### 新 findings

- **（非阻断 — D5 表「穷举」未列在途 change）**：`design.md:79` 的 D5 表仍自称「改动面（**穷举**）」，但**未列** `openspec/changes/add-minimal-tui-runtime-view/{design.md,tasks.md}`（证据：`grep -n add-minimal-tui-runtime-view design.md` 全文**零命中**），而 task 3.6 现已修改这两文件 → 表与任务清单**轻微不一致**（R1 的 D5 refuted 中「表漏在途 change」一项**未在表内**回写，R2 以补 task 3.6 的方式解掉了**可达性**、但未动**表**）。
  - **建议（非阻断）**：D5 表补一行（在途 change 2 处改名），或表题去掉「穷举」措辞。不影响停轮，可实现期顺手修。

- **（非阻断 — 分支名 ≠ change-id）**：当前分支 `grill-skill-alignment/2026-10-07`，change-id 为 `grill-flow-hardening`。`scripts/workflow_guard.py:333-357` 的 `_current_change_id` 先取 `branch.split("/")[0]` = `grill-skill-alignment` 查 `CHANGES_DIR/<head>`（不存在）→ 回落「单 active change」分支；而当前有 **2** 个 active change（本 change + 在途 change）→ 返回 `None` → grill 门**不触发**。此为**构建期分支纪律**问题（AGENTS.md 要求分支名 `<change-id>/<YYYY-MM-DD>`，门禁靠分支名推导 change-id），**非设计文档缺陷**，且为环境**既存**（建 worktree 时即如此，非本次修复引入）；另本 worktree 无 guard hook（`.claude/` 被 gitignore），实际由 CI 兜底。记此供**实现期**知悉，**不影响设计 verdict**。

### R3 结论

R2 的两项待修（F3+F6 合并计、F7）**全部修净**；R1 的 F1/F2 **保持修净**；剩余 Open Questions 仅 **Q2/Q3**。**设计可进停轮**。两条非阻断项（D5 表补行、分支名对齐 change-id）建议实现期顺手处理，**不阻塞**。
