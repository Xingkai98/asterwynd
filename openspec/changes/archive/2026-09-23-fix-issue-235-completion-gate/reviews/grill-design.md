# Grill: fix-issue-235-completion-gate 设计追问

我是独立设计评审者（零记忆）。结论来自 [实跑命令/实读代码]：本会话不继承开发上下文，design.md 里所有「实测」断言我都自己重跑过一遍；凡重跑结果与 design 不一致的，以我的实跑输出为准并写在下面。核心结论：**D1/D4/D6/D7 的机械细节基本成立；D2 的「理由」是错的（结论歪打正着）；D3 的路线 B 无法兑现需求 2「四道门全评估」，必须改；另发现 design 完全没提到的「路径级触发误伤旧归档」风险。**

## Reviewer

- run id: 7a0c0462-95a1-4fc6-9c56-3fbcec330e7b
- 时间: 2026-09-23
- 审阅对象: `openspec/changes/fix-issue-235-completion-gate/{proposal.md, design.md, tasks.md, specs/dev-workflow-state-machine/spec.md}`、issue #235、`scripts/check_openspec_artifacts.py`、`scripts/workflow_guard.py`、`agent/workflow/review_manifest.py`、`.github/workflows/ci.yml`、`openspec/specs/dev-workflow-state-machine/spec.md`、`tests/test_openspec_artifact_checker.py`
- 基线: 85e1056（分支 fix-issue-235-completion-gate/2026-09-23）
- 审阅方法:
  - `git diff --name-only --diff-filter={A,AR} <base>` 在三个独立探针仓库复现（纯 rename / rename 破裂 / 旧归档目录内新增文件）
  - 93 个归档目录的 5 项覆盖扫描（正则匹配率、proposal/specs/reviews 存在率、未勾项分布）
  - **在 89 个归档 change 上实跑四道门函数**，统计 would-fail 数与失败原因分布
  - 用真 `Change Type` 的最小仓库端到端复现 D2（写 manifest → `git mv` 归档 → post-PASS 勾选 → 分别以 `archived=True/False` 调用 `_check_review_manifests`）
  - 复用 gate 函数在「归档目录 + 未全勾」输入下的真实返回值（D3 判别性探针）
  - `_check_reference_implementation_research` 的 tier 闭环分支单测；D4 tag 正则 12 变体参数化
  - `uv run pytest tests/test_openspec_artifact_checker.py -q`（82 passed）、`npx @fission-ai/openspec@1.4.1 validate --all --strict`（30 passed）
  - 全部引用行号逐个 `sed -n` 核对

## Confirmed Decisions

- **决策**: D1 的 `--diff-filter=AR` 是必要的，不能只用 `A`。理由: 最小复现——`git mv openspec/changes/my-change openspec/changes/archive/2026-09-23-my-change` 后，`--diff-filter=A` 输出为空（git 报 `R100`），`--diff-filter=AR` 输出完整 archive 路径；且 rename 破裂时（tasks.md 被重写）`git diff --name-status` 给 `R100`+`A`+`D`，`A` 侧仍带 archive 路径，`AR` 同样拿到。来源: 7a0c0462-95a1-4fc6-9c56-3fbcec330e7b
- **决策**: D1 的归档路径正则对既有语料 100% 覆盖，且当前不存在「无日期前缀」归档目录（O5 的触发面目前为空）。理由: 脚本对 `openspec/changes/archive/*/` 逐目录跑 `^openspec/changes/archive/\d{4}-\d{2}-\d{2}-([^/]+)/`，93/93 命中、0 未命中；`ls -d openspec/changes/archive/*/ | grep -vE '^[0-9]{4}-...'` 输出为空。来源: 7a0c0462-95a1-4fc6-9c56-3fbcec330e7b
- **决策**: D4 的 tag 正则语法按 design 声明的 8 个变体全部通过，且扫描放宽（`[X]`/`+ [ ]`）在现存语料上零影响。理由: 参数化跑 12 个变体，design 点名的 8 个 + 缩进子项 + 已勾带 tag 共 9 个命中、3 个负例（`post-merge` 无括号、`pre-merge`、`**5.5 post-merge**`）正确地不命中；`grep -rn '^\s*+ \[ \]'` 与 `^\s*[-*] \[X\]` 在 `openspec/ docs/ AGENTS.md` 命中数均为 0（与 design D4「零影响」一致）。来源: 7a0c0462-95a1-4fc6-9c56-3fbcec330e7b
- **决策**: D6 的「区分依据是 `--check-archived`，不是 `--base-ref`」成立。理由: `:1388` 实读为 `parser.add_argument("--base-ref", default="master")`，确实没有「不传则不算 diff」的语义；新门若按 `not args.check_archived` 守卫则与 D6 描述一致。CI 第二步 `--check-archived --skip-protected-paths --skip-backlog`（`ci.yml:70-71`）实跑在本 worktree 上是 `OpenSpec artifact checks passed`。来源: 7a0c0462-95a1-4fc6-9c56-3fbcec330e7b
- **决策**: D7 的残余面描述与代码事实一致：`iter_change_dirs:1283` 确实用 `path.name != "archive"` 排除归档，`--check-archived` 分支（`:1416-1438`）只跑 `_check_review_manifests(archived=True)` + `_check_archived_projectable`，不跑 `check_change`；`review_manifest.py:175` 确认 `archived=True` 时 `tasks_hash` 分支被短路。来源: 7a0c0462-95a1-4fc6-9c56-3fbcec330e7b
- **决策**: 爆炸半径在当前 HEAD 上为空（不追溯既有归档的前提成立）。理由: `git diff --name-only --diff-filter=AR origin/master...HEAD | grep archive/` 输出为空；`git ls-tree -d origin/master:openspec/changes/archive` 与 `HEAD:` 均为 93 个同名目录，差集为空。来源: 7a0c0462-95a1-4fc6-9c56-3fbcec330e7b
- **决策**: O6a 的「分工闭环」按现有代码结构确实成立，且不需要新增实现。理由: 端到端复现——归档 change 有 `building-review.md` 但删掉 manifest 时，第二步 `--check-archived --skip-protected-paths --skip-backlog` 精确报 `review manifest missing: openspec/changes/archive/2026-09-23-demo/reviews/building-review-manifest.json`；manifest 在时第二步通过。来源: 7a0c0462-95a1-4fc6-9c56-3fbcec330e7b
- **决策**: D5 的「`.claude/commands/opsx/archive.md` 当前不存在，需先 `npx openspec init --tools claude` 生成」属实。理由: `ls -la .claude/commands/opsx/` 返回 `No such file or directory`（整个目录不存在，不只是 archive.md），该任务的可完成性依赖网络拉取 `npx`，需在 tasks 里保留为显式前置。来源: 7a0c0462-95a1-4fc6-9c56-3fbcec330e7b
- **决策**: RIR 的结构门槛/内容门槛确实在代码里是分离的，`:585` 只守卫内容门槛。理由: 实读 `:521-580` 的 `research_tier`/`status`/`reason`/`research questions`/`findings`/`design impact` 非空校验都在 `if _tasks_all_complete(change_dir):` 之外；`:585-620` 内才是 `_self_admitted_incomplete` 短语命中与 tier↔status 闭环。单测确认 `exempt+enabled` 与 `full+disabled` 只在 tasks 全勾时报错、部分勾选时 0 错。来源: 7a0c0462-95a1-4fc6-9c56-3fbcec330e7b

## Open Questions

- **Q1（O1 继承豁免是否需显式断言）**: D2 表格说「复用函数即继承 docs 豁免 / DESIGN_TYPES 豁免 / `primary != docs` + `_changed_capabilities` 豁免」——但这只说了继承**豁免**，没说清同时继承的是**触发器**。实跑证据：把 `_check_design_review_task` 原样用在「无 `reviews/` + tasks 有一条未勾」的归档目录上，它返回 `[]`（因为 `:750` 的 `_tasks_all_complete` 为假，退回 `_has_design_review_task` 字面标记检查，tasks 里只要有「batch-grill」字样就通过）。具体例子：归档 change `demo`，`tasks.md` 为 `- [x] 跑 batch-grill-me 审视 design.md` + `- [ ] 一条未勾且无 tag 的实现任务`，`reviews/` 目录整个不存在。当前实跑 `_check_design_review_task` → `[]`（绿）；若按 D3 路线 B「复用同一判定函数」实现，**这个 change 会绿着归档**，正是本 change 要堵的问题一。所以问题不是「豁免要不要显式断言」，而是「**触发器也必须被显式覆盖**」。我的建议：在 tasks 的测试清单里补两条——(a) docs-only 归档 → 四门不报（豁免继承）；(b) **无 `reviews/` 的非 docs 归档 → 报 `reviews/grill-design.md missing`**（触发覆盖）。只做 (a) 会把「豁免继承」验证成绿的，而真正要防的 (b) 不测就漏。请确认是否两条都补。

- **Q2（O2 CI 挂载理由是否成立）**: 我的裁决是**理由成立但 D6 的措辞需要收紧**。D6 说「只挂 CI 第一步；第二步不评估；区分依据是 `--check-archived`，不是 `--base-ref`」——前半句对：`:1388` 的默认值确实是 `"master"`，不传 `--base-ref` 也会算 diff，所以不能用 base-ref 的有无来区分。但要注意 CI 第二步的命令行是 `--check-archived --skip-protected-paths --skip-backlog`（`ci.yml:70-71`），**它同时也传了 `--skip-protected-paths`**。具体例子：如果把新门的代码放进 `main()` 的 `if not args.skip_protected_paths:` 块内（该块从 `:1453` 开始，包裹 `_changed_paths_since_base` + `check_protected_path_explanations` + `_validate_policy_agent_schema`），那么 CI 两步都会因为各自的原因跳过它，看起来「工作正常」，但此时 `--skip-protected-paths` 事实上成了区分开关——与 D6 明文要求「不能被 `--skip-protected-paths` 关掉」直接矛盾；一旦有人在本地跑 `check_openspec_artifacts.py --check-archived`（不加 `--skip-protected-paths`，AGENTS.md 的验证速查表就是这么推荐的），新门会在**全部 93 个归档**上求值。请确认：实现时必须把新门放在该块**之外**并用 `not args.check_archived` 显式守卫（而不是靠 `--skip-protected-paths` 的副作用）。

- **Q3（O3 解耦路线 —— design 点名要我裁，我的裁决是「两条都不行，取 A′」）**: **路线 B 按 design 的描述无法兑现需求 2「四道门全评估（不因未全勾而降级）」，必须否决。** 证据是上一条 Q1 的实跑：四道门里有两道（grill 完整性门 `:733` + RIR 内容门 `:585`）的**判据本身**就是 `_tasks_all_complete(change_dir)`。归档目录只要残留任何一条未勾任务（这正是本 change 要处理的常态——35/93 历史归档如此），这两道门就静默返回 `[]`。「复用判定函数、不复制逻辑」（design.md:115 的缓解措施）与「四门全评估」在 B 的框架下**不可兼得**：要么复制逻辑（违反 design.md:115），要么给函数加参数（那就不是 B 了）。**路线 A 按 design 描述的载体（「四处判定加显式参数」）又过宽**：`:1031` 那处（`requires_building_review`）根本不需要参数化——归档侧只做存在性、不走 `_check_review_manifests`（D2 已定），所以四处里只有三处属于本次要动的。**我的裁决是 A′**：给 `_check_reference_implementation_research` 与 `_check_design_review_task` 各加一个 `*, assume_implemented: bool = False` 关键字参数，函数内部把 `if _tasks_all_complete(change_dir):` 改成 `if assume_implemented or _tasks_all_complete(change_dir):`（`:585` / `:733` / `:750` 三处）；**`check_change` 一行不动**（它调用时不传该参数 → 默认 False → active 行为逐字节不变，`test_partial_change_does_not_require_building_review:241` 天然原样通过）；归档侧用 `assume_implemented=True` 调这两个函数。具体前后对比：归档 `demo`（`reviews/grill-design.md` 含 `- **Q1**: 未决项`、无 `## User Confirmation`、tasks 有一条无 tag 未勾）——B 的返回值 `[]`（绿）；A′ 的返回值 `['reviews/grill-design.md 存在未确认的 Open Question: Q1 ...']`（红）。A′ 同时满足「四门全评估」「不动 active 路径」「复用同一判定函数不复制逻辑」三条。请确认是否采纳 A′。

- **Q4（O4 RIR 口径统一）**: 我的裁决是**口径本身一致，但 spec delta 的措辞漏了一半，需要补**。`:585` 守卫的确实不只是「自认未完成短语」，还包括 **tier↔status 闭环**：单测确认 `research_tier: exempt` + `status: enabled` 在 tasks 全勾时额外报 `research_tier: exempt 在 tasks 已全勾时 status 必须为 disabled`，`full` + `disabled` 同样报错，而部分勾选时 0 错——这三条都挂在 `:585` 那个 `if` 里面。但本 change 的 spec delta（`specs/dev-workflow-state-machine/spec.md:53`）只写了「SHALL 额外检查『自认未完成』短语级模式」，**没有提 tier↔status 闭环**。具体例子：一个归档 change 的 RIR 写 `research_tier: exempt` + `status: enabled` + `reason: 已关闭决策 issue #123`，tasks 全勾。按代码（复用时 assume_implemented=True）应报「exempt 必须 disabled」；按 delta 的字面措辞则不要求。请确认：delta 的正文要把内容门槛展开为**两个子检查**（自认未完成短语 + tier/status 闭环与 exempt 证据），否则只读 spec 的实现者会漏掉后者，而 artifact checker 对 spec 措辞没有机械校验、抓不住这个漏。

- **Q5（O5 无日期前缀归档）**: 我的裁决是**先在 known-debt 记一笔、但同一次实现里加一条「非规范归档目录即报错」的低成本守卫**（不是二选一，是都要）。现状是触发面为零：`grep -vE '^[0-9]{4}-[0-9]{2}-[0-9]{2}-'` 对 93 个归档目录输出为空。具体例子：未来某 agent 执行 `git mv openspec/changes/foo openspec/changes/archive/foo`（漏日期）。此时 `--diff-filter=AR` 给出 `openspec/changes/archive/foo/tasks.md`，正则 `^.../\d{4}-\d{2}-\d{2}-([^/]+)/` 不匹配 → 不进 `new_archived_ids`；同时 `iter_change_dirs:1283` 把 archive 整个排除 → 该 change **既不在 active 也不在任何门里**，checker 全绿。这正是本 change 要消灭的「静默无门」形态的变体。守卫实现很便宜：对 `--diff-filter=AR` 里 `startswith("openspec/changes/archive/")` 但不匹配日期正则的路径直接进 `errors`（报「归档目录命名不合规，无法评估完成度门」）。请确认是否采纳「报错 + known-debt 双写」，还是只记 known-debt。

- **Q6（O6 补 2 条测试）**: 我的裁决是**两条都补，且 O6a 的措辞要改**。O6a（有 review 无 manifest）我已端到端验证过闭环真实成立（见 Confirmed Decisions），但它的价值不在「验证代码」而在「**锁死分工不漂移**」：未来若有人图省事把 D2 的「只做存在性」改成复用 `_check_review_manifests`，这条测试会红——具体例子：归档 `demo` 有 `building-review.md`、manifest 被我 `rm` 掉，第二步精确报 `review manifest missing: .../2026-09-23-demo/reviews/building-review-manifest.json`；把这一步的断言写成测试即可。O6b（同 PR 既有 M 又有 AR）我认为**要补但覆盖的命题要换**，因为按 `--diff-filter=AR`，旧的 M 路径**根本不会进集合**（`M` 被 filter 排除），所以「只评估新 id」在 M 这一侧是同义反复、测不出东西。真正会误伤的是**A 路径**：见下面「风险」第 1 条——往**旧**归档目录里新增一个文件（例如补 manifest）会被判成「本 PR 新归档」。请确认：O6b 改成「同 PR 里对旧归档目录新增文件（`A` 路径）→ 不评估该旧 id」+「同 PR 里新归档（AR）→ 评估」，这样才有判别力。

- **Q7（O7 统计口径）**: 我的裁决是**需要在 change 文档里统一口径，因为 issue #235 的表自相矛盾**。issue 正文的表写「有未勾选任务 35 / 其中全未勾项都是「合入后」类 9 / 含「合入后」类但不全是 12 / 纯「做完了忘勾」23」，但 **9 + 12 + 23 = 44 ≠ 35**。我自己在 93 个归档上重算（用 `合入后|合入时|合并后|PR 合入|归档后|issue.*(comment|关闭)` 作 closeout 启发式）：有未勾项的 35 个（与 issue 一致），其中「全部未勾项都是 closeout 类」9 个（与 issue 一致），「无 closeout 类未勾项」23 个（与 issue 一致），**剩余 3 个（不是 12）**。也就是说 9 + 3 + 23 = 35 自洽，issue 表里的 12 是错的。影响面：本 change 的设计决策**不依赖**这三个数（门只看 tag，不做统计），所以不阻塞实现；但 issue #235 是 change 的关联跟踪入口，口径不一致会在收尾写完成 comment 时留下错误数字。请确认：是在本 change 的 proposal 里更正这三个数并注明「原 issue 表 12 有误，实测为 3」，还是另开一行 debt。

## 风险

- **【新风险，design 完全未覆盖｜高】触发是「路径级」而非「目录级」，会误伤既有归档，与需求 4「不追溯」冲突。** D1 的判据是「路径匹配正则」，而不是「该归档目录在 base 不存在」。具体例子（已实测）：在 `/tmp` 探针仓库里对一个**已存在的旧归档目录**新增文件——`A openspec/changes/archive/2025-01-01-old-change/reviews/building-review-manifest.json`——`git diff --name-only --diff-filter=AR <base>` 返回该路径，正则命中，`new_archived_ids = {'old-change'}`。这个形态**不是假想**：本仓库 2026-09 连续三个 PR（`cea1e53` #234、`e252694` #236、`133ec5a` #238）就是在补归档收尾；issue #232 盲区 B 本身就是「给归档 change 补 manifest」。误伤后果量级：我在 89 个可解析的归档 change 上实跑四道门，**69/89 会失败**（41 个缺 `building-review.md`、35 个含未 tag 未勾任务、绝大多数旧 change 连 `## Reference Implementation Research` 段都没有）。缓解（已验证有效、成本极低）：追加条件「该 archive 子目录在 base 树不存在」——`git ls-tree -d <base>:openspec/changes/archive` 与 HEAD 取差集。实测该条件排除掉上面的旧 id（`old-change` 在 base 存在），同时仍包含纯 rename 案例（`2026-09-23-my-change` 在 base 不存在）。**建议把这条写进 D1 的判据重写。** 相关：`scripts/check_openspec_artifacts.py:1352`（`_changed_paths_since_base`）目前不带 `--diff-filter`，新门需要独立取 diff，别直接复用这个函数的返回值。

- **【新风险｜中】本 change 会红在自己的归档 PR 上（self-trigger / 未吃自己的狗粮）。** 实跑 `openspec/changes/fix-issue-235-completion-gate/tasks.md`：当前 40 条未勾（proposal 阶段正常），其中 `:65`「收尾：issue #235 添加完成 comment 并关闭」是**结构性 post-merge** 项且**没有 `(post-merge)` tag**。实现完成后其余行会被勾掉，这一行会留下 → 新门在本 change 自己的归档 PR 上报 untagged unchecked。这不是设计缺陷（打上 tag 即可），但它是「新约定必须一次到位」的具体证据，建议写进 tasks 的收尾清单（给 `:65` 加 tag），并在端到端验证里用本 change 自身当样例。

- **【新风险｜中】`--change <id>` 单 change 模式与新门的交互未定义。** `main()` 里 `--change` 只影响 `iter_change_dirs`（`:1382-1400`），不影响后续的 diff 计算。具体例子：本地在 worktree 里跑 `check_openspec_artifacts.py --change fix-issue-235-completion-gate`（`--base-ref` 默认 `master`，且 `--check-archived` 为假 → 新门触发），若该分支上恰好有归档 commit，checker 会**额外**评估那个归档 id——用户以为自己只查了一个 change，实际多跑了一道门并可能报不相干的错。建议：`--change` 非空时显式跳过新门（或至少在 `--skip-protected-paths` 之外的独立分支里判断），并加一条测试锁定。

- **【新风险｜中】新门必须自己兑现 `--require-base`，否则浅检出下 fail-open。** `_changed_paths_since_base`（`:1352`）在 base 不可解析时返回 `(set(), warning)`，`main()` 只在 `args.require_base` 为真时把 warning 升级成 error（`:1456-1461`）。CI 第一步传了 `--require-base`（`ci.yml:62`）所以安全；但新门的 diff 是**独立计算**的，若实现时只取 `paths` 不看 warning，那么在浅检出/`master` 不存在的环境下新门会拿到空集合→静默放行。具体例子：`git clone --depth 1` 后在功能分支上跑 checker，`master` 解析失败 → 新门 0 个 id → 全绿。建议实现时让新门复用同一个 `require_base` 语义（解析失败即报错）。

- **【新风险｜低-中】D3 路线 B 的「两处调用不漂移」比 design 描述更严重，是结构性覆盖分歧。** design.md:115 把代价描述为「四道门判定逻辑在两处被调用」，但实际差异不止调用点：`check_change`（`:1199-1275`）跑约 10 类检查（required sections、impact analysis、diagnosis、handoff、benchmark smoke、current spec mapping、current spec sync task…），而归档侧按 D2 只跑 5 类。两条路径的**检查集合不同**，未来 `check_change` 增删检查时归档侧不会跟随，漂移是必然而非偶发。若采纳 Q3 的 A′（复用同一对函数 + 参数），这个分歧被压缩到「归档侧少调 5 类检查」这一处**有意的**差异，而不是两套独立实现的差异——这是 A′ 相对 B 的第二个优势。建议加一条测试同时断言 active 与归档两条路径对同一份 gate 输入的结论一致。

- **【低】spec delta 未覆盖 `--check-archived` 与新门「互斥」的规格化。** 当前 delta 的两个 Scenario（`specs/dev-workflow-state-machine/spec.md:32-42`）都只描述「不在本 PR 归档路径中 → 不要求」，没有一条明确写「`--check-archived` 模式 SHALL NOT 触发归档点门」。具体例子：`--check-archived --skip-backlog`（不带 `--skip-protected-paths`）跑在含归档 commit 的分支上——若实现漏了守卫，这个组合会触发新门并在 89 个历史归档上报一片错。建议在 delta 里补一条 Scenario 把它钉死，别只靠 tasks 里的 test 项。

## User Confirmation

用户于 2026-09-23 对上述全部 7 条 Open Question 与 3 条新风险逐项拍板。

- **Q1**: 用户答复：采纳建议，两条测试都补——(a) docs-only 归档 → 四门不报（验豁免继承）；(b) 无 reviews/ 的非 docs 归档 → 报需要 grill 证据（验触发覆盖，这才是真正要防的洞）。；确认时间: 2026-09-23
- **Q2**: 用户答复：采纳建议，新门放在 `if not args.skip_protected_paths:` 块之外，用 `not args.check_archived` 显式守卫，不靠 --skip-protected-paths 的副作用。；确认时间: 2026-09-23
- **Q3**: 用户答复：采纳 A′ 裁决——给 _check_reference_implementation_research 与 _check_design_review_task 各加 `*, assume_implemented: bool = False`，函数内三处判据改为 `assume_implemented or _tasks_all_complete(change_dir)`（:585 / :733 / :750）；check_change 一行不动；归档侧传 True。；确认时间: 2026-09-23
- **Q4**: 用户答复：采纳建议，spec delta 正文把内容门槛展开为两个子检查（自认未完成短语 + tier↔status 闭环与 exempt 证据），并在文档中修正 D2 的错误理由（实为 review manifest missing / active 路径解析，非 tasks_hash mismatch）。；确认时间: 2026-09-23
- **Q5**: 用户答复：采纳「报错 + known-debt 双写」——--diff-filter=AR 里 startswith("openspec/changes/archive/") 但不匹配日期正则的路径直接进 errors（报归档目录命名不合规，无法评估完成度门），同时在 docs/known-debt.md 记一笔。；确认时间: 2026-09-23
- **Q6**: 用户答复：采纳建议，O6a 保留（有 review 无 manifest → 第二步报 review manifest missing，锁死分工闭环）；O6b 命题换成「同 PR 对旧归档目录新增文件（A 路径）→ 不评估该旧 id」加「新归档（AR）→ 评估」。；确认时间: 2026-09-23
- **Q7**: 用户答复：更正为 9/3/23——在本 change 的 proposal 里改，注明原 issue #235 表 12 有误（9+12+23=44≠35），实测为 3；收尾给 #235 写完成 comment 时用更正后的数。；确认时间: 2026-09-23
- **风险②**: 用户答复：采纳修正——追加「该 archive 子目录在 base 树不存在」判定（git ls-tree -d <base>:openspec/changes/archive 与 HEAD 取差集），排除旧 id、保留纯 rename 案例，并加判别性测试。；确认时间: 2026-09-23
- **风险小a**: 用户答复：采纳——--change <id> 非空时跳过新门，并加测试锁定。；确认时间: 2026-09-23
- **风险小b**: 用户答复：采纳——新门自己兑现 --require-base 语义（复用 _changed_paths_since_base 的 warning，防浅检出 fail-open），并加测试。；确认时间: 2026-09-23
- **风险小c**: 用户答复：采纳——spec delta 补一条 Scenario 钉死「--check-archived 模式 SHALL NOT 触发归档点门」。；确认时间: 2026-09-23
- **风险③**: 用户答复：确认——给本 change 的 tasks.md:65 收尾项打 (post-merge) tag。；确认时间: 2026-09-23
