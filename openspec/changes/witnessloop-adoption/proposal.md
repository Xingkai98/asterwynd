# Proposal: witnessloop 影子接入（witnessloop-adoption，阶段 A）

关联跟踪 issue：[#305](https://github.com/Xingkai98/asterwynd/issues/305)（【feature】把 asterwynd 自己的流程门禁切换成「接入 witnessloop」（盘点 + 迁移计划））。上游工具仓：[`Xingkai98/witnessloop`](https://github.com/Xingkai98/witnessloop)（本仓流程工具化抽取出的独立工具，caller 钉 `@v1`）。

## Change Type

- primary: process
- secondary: []

## 需求

1. **分阶段切换的第一步：影子接入。** 在**一条分支**上落 witnessloop 的接入产物，让新门禁**只跑不拦**；用**一个真实小需求**在新流程上跑一遍验证；验证 OK 之后**单独一步**再「真打开」（合入 + 勾 required）。
2. **接入必须走定制 policy。** witnessloop 出厂 policy 的 `require_change_for` 对 asterwynd **零命中**（见「背景」第 2 条），而 witnessloop 的 `building` 门禁与 `grill-adversarial` 门禁**共用同一条 `code_hits` 触发**——用出厂 policy 接入等于这两个核心门禁**完全不触发**。因此接入 SHALL 用 `witnessloop init --policy <seed>` 一次写成。
3. **并存，不替换。** `master` 现有 required = `["validate", "benchmark-gate"]` **不动**；witnessloop 的 caller 新增一个 `gate / check` job。阶段 A **不勾 required**。
4. **三条项目配置决策**（事件类型名映射 / `require_change_for` 最终面 / `openspec/specs/**` 是否列为 protected）**必须用户拍板**，本 change 只给推荐值与具体例子，不替用户决定——见 `design.md` 的 `## Open Questions`。
5. **明确不做**：下掉任何现有 checker、改 `validate` job、动 branch protection 的既有两项、迁 RIR 等项目特有检查、放宽任何判据。

## 背景

### 1. 现状盘点（issue #305，本分支复核）

asterwynd 把「开发流程门禁」整套自建在本仓：

| 件 | 行数 | 作用 |
|---|---|---|
| `scripts/check_openspec_artifacts.py` | 1802 | change 契约、manifest 绑定、grill/building 证据、受保护 artifact 证据、归档点完成度（12 个顶层 `_check_*`） |
| `scripts/workflow_guard.py` | 677 | 本地写码前守卫（**含 Bash 命令解析**） |
| `scripts/workflow_state.py` | 732 | 流程事件投影 |
| `scripts/flow-policy.json` | 82 | 受保护路径规则表 |
| `scripts/platform_gate.py` | 471 | branch protection 即代码 |
| `agent/workflow/*`（6 模块，含 `__init__`） | 1666 | event_log / state_machine / review_manifest / resume_audit / routing / models |

配套测试约 4744 行。规模面：27 个 spec、**122 个归档目录**（`find openspec/changes/archive -maxdepth 1 -mindepth 1 -type d | wc -l` 实测）、2 个 active change、**78 份 `workflow-events.jsonl`**（issue #305 更正评论实测；本分支 `find` 得 79，含本 change 之外的全部）。

### 2. 动态探测结论（issue #305 评论，探针 worktree `/home/happy/ax-wt/wl-adopt-probe`）

- **`init` 对 asterwynd 零冲突**：`init --dry-run` 将创建的四个文件（`.witnessloop/policy.json` / `.github/workflows/witnessloop.yml` / `.witnessloop/init-manifest.json` / `.github/witnessloop-tests.txt`）**全是新文件**——本仓 `.github/workflows/` 下只有 `ci.yml`（实测），不与 caller 撞名。**不需要为接入挪任何既有文件。**
- **⚠️ 出厂 policy 对 asterwynd 零命中**：witnessloop 出厂 `require_change_for` 是 **8 条目录 glob 的元组**（`src/**` / `lib/**` / `app/**` / `apps/**` / `packages/**` / `server/**` / `cmd/**` / `internal/**`，见 witnessloop `src/witnessloop/constants.py:43-52` 的 `DEFAULT_REQUIRE_CHANGE_FOR`），对 `agent/x.py`、`scripts/y.py`、`web/z.py`、`tests/t.py`、`docs/d.md` 以及 benchmark 目录下的 `b.py` **一个个都不命中**。后果比「少一条规则」严重：`building` 门禁（issue #13）与 `grill-adversarial` 门禁（issue #16）**都挂在 `code_hits` 上**（witnessloop `src/witnessloop/checkcmd.py:77` `code_hits = _code_hits(pol, changes)`，随后 `if code_hits:` 才追加两条 stage manifest 判定）⇒ 出厂 policy 下这两个门禁对 asterwynd **完全不触发**。
- **归档不是问题**：同一个真实 diff 下 witnessloop 报「21 个变更文件，0 个 change 目录」——`changed_change_ids` **只挑 active**，`archive/**` 被完全忽略。asterwynd 式「实现 PR 直接落 `archive/<date>-<id>/`」在 witnessloop 下**天然安全**。⚠️ **前提是别把归档目录列进 `protected_paths`**：实测列上立刻多出 12 条「受保护路径被写入但没有结构化解释事件」——asterwynd 的语义是「归档是簿记动作、免解释」，witnessloop 的 `is_archive_move` 豁免**只认纯改名**、不认「在实现 PR 里新增 archive 目录」。
- **命名/格式差异三处**：① **manifest 的 schema 不同构**（`agent/workflow/review_manifest.py:93-104` 写 `phase`，缺 `author_run_id` / `report_path`；witnessloop 要 `stage` / `author_run_id` / `report_path`）+ 文件名不匹配（本仓 `reviews/<phase>-review-manifest.json` vs witnessloop 默认 glob `reviews/*.manifest.json`）——**这是本 change 的一处设计取舍，不是「加个配置就好」**（独立 grill 实跑 `check` 得 6 条红证伪了「纯机械修正」的定性，见 `design.md` Decision 2）；② grill 记录名 `reviews/grill-design.md` vs 模板示例 `grill-review.md` ⇒ manifest 的 `report_path` 是自由字段，**无碍**（stage 名 `grill` / `grill-adversarial` / `building` 两边一致 ✓）；③ 解释事件机制**已经存在**（见下）。
- **⚠️ 已公开更正的一条错结论**：issue #305 早先一条评论称「asterwynd 没有 witnessloop 意义上的结构化解释事件（`handoff.json` 是退役状态机的产物）」——**错**。实测 `workflow-events.jsonl` **78 份**，事件字段与 witnessloop **逐字对得上**（`event_type` / `artifact_path` / `reason` / `approved_by` 四个都在，多出来的 `schema` / `seq` / `change_id` 是 witnessloop **忽略**的字段）。判据在 `scripts/check_openspec_artifacts.py:1173 check_protected_path_explanations`，规则表 `scripts/flow-policy.json`，实际用的类型名有 `current_spec_synced` / `backlog_updated` 等。**错因值得记**：用 `git ls-files | grep … | head -5` 的**截断输出**下了「不存在」的结论，而前 5 行被别的命中占满。⇒ 更正后「解释事件」**不是新仪式，只是配置**。

### 3. 双门禁实况

`gh api repos/Xingkai98/asterwynd/branches/master/protection`（本分支实测）：`required_status_checks.contexts = ["validate", "benchmark-gate"]`、`strict = true`、`required_approving_review_count = 0`、`required_conversation_resolution.enabled = true`。⇒ 并存期是**加法**：现有两项继续 required，witnessloop caller 的 `gate / check` job 阶段 A **不勾 required**。

## 非目标

- **不下掉任何现有件**：`check_openspec_artifacts.py` / `workflow_guard.py` / `workflow_state.py` / `flow-policy.json` / `platform_gate.py` / `agent/workflow/*` 在本 change 内**一行不改**。
- **不迁 manifest schema**（边界写准）：**阶段 A/B 不改 `agent/**`**——asterwynd 的 manifest 生成器（`agent/workflow/review_manifest.py`）写 `phase` 且缺 `author_run_id` / `report_path`，与 witnessloop 的必填字段表不同构；本 change 采取「**两套 manifest 并存**」（见 `design.md` Decision 2），因此**不需要**动生成器及其 2874 行测试。**schema 统一会改 `agent/**`，是阶段 C 之后另开的 change**，不在本 change 内。
- **不改 `validate` job、不动 `.github/workflows/ci.yml`**（本 change 只**新增** witnessloop 的 caller workflow）。
- **不动 branch protection 的既有两项**，也不在本 change 内勾 required（那是阶段 C）。
- **不改 RIR / Impact Analysis / benchmark 门禁 / tasks 完成度 / 归档点完成度的语义**——它们保留为 asterwynd 本地规则（见 `design.md` 决策 5）。
- **不迁项目特有检查进 witnessloop**（缺什么 → 去 witnessloop 立 issue）。
- **不碰已退役的四阶段状态机残留**（`state_machine.py` 的转移原语）。
- **不为 `add-minimal-tui-runtime-view` 放宽任何判据**（见「已知红」）。

## 用户故事

- 作为本仓维护者，我在阶段 A 落地后打开一个 PR：CI 里多出一个 `gate / check` job，它**跑**（能看见 witnessloop 的 findings），但因为没进 required，**不拦**我合入。
- 作为本仓维护者，我用一个真实小需求走一遍新流程：witnessloop 的 `guard` 在写码前拦我、`check` 在 CI 里核证据、测试执行点跑起来——我能据此判断「真打开」值不值得。
- 作为本仓维护者，我在阶段 A 结束时看到 `master` 的 required 仍是 `validate` + `benchmark-gate`——**没有任何强制窗口被打开**。
- 作为本仓维护者，我想回退时：删掉 caller workflow + `.witnessloop/` 目录（或跑 `witnessloop uninit`）即可，**旧门禁原封不动**。

## Impact Analysis

- **影响文件（新增，阶段 A 的产物）**：
  - `.witnessloop/policy.json`（定制 policy，由 `init --policy <seed>` 写入）
  - `.witnessloop/init-manifest.json`（init 台账，供 `uninit` 精确回滚）
  - `.github/workflows/witnessloop.yml`（caller，`uses: Xingkai98/witnessloop/.github/workflows/gate.yml@v1`）
  - `.github/witnessloop-tests.txt`（测试执行点：一行 shell 命令）
- **不影响（明确保持原样）**：`.github/workflows/ci.yml` 的 `validate` / `benchmark-gate` 两个 job、`master` branch protection 的两个 required context、`scripts/` 下全部现有脚本、`AGENTS.md` 的流程段。
- **影响测试**：本 change 不新增 Python 测试；「测试」面由 witnessloop 侧接管（`init --test-command` 写入的执行点 + `gate.yml` 里那一步）。**阶段 A 的验收测试就是把一个真实小需求跑通**（见 tasks 阶段 B）。
- **影响文档**：`AGENTS.md` 的流程段**本 change 不改**（留阶段 C）；`docs/development-guide.md` 增加「witnessloop 影子接入」一节（阶段 A 落地后，说明怎么本地跑、怎么读 findings）；`docs/openspec-change-backlog.md` 登记本 change。
- **新增外部依赖**：witnessloop reusable workflow `@v1` + `.witnessloop/policy.json` 的 schema `witnessloop/policy@v1`。**运行时唯一耦合点是 GitHub Actions 拉取上游 reusable workflow**；本地侧只有可选的 Claude Code plugin（不进 PR，见下）。
- **本地 vs CI 是两个独立开关**：装 plugin（交互层）是**本地动作**，因为 `.claude/` 被 gitignore（`.gitignore:9`）⇒ 不进任何 diff、不产生 PR；CI 层（caller workflow）才是进 PR 的那一半。**两者互不依赖**：不装 plugin 也能有 CI 门禁，装了 plugin 也不会自动勾 required。
- **能力退步（必须写明）**：asterwynd 现在的本地守卫**解析 Bash 命令**（`scripts/workflow_guard.py`，677 行）；witnessloop 的 `guard` **只看 `Write|Edit`**（witnessloop `src/witnessloop/guardcmd.py:16-17` 自陈边界）。⇒ 接入后**本地拦截面会变窄**。两者都可绕过，真锚是 CI required check——但这是退步，须写进迁移文档，且**在阶段 C 之前不做任何旧守卫的下掉**。
- **manifest 两套并存（本 change 的取舍）**：asterwynd 的 manifest 生成器（`agent/workflow/review_manifest.py`，写 `phase`、无 `author_run_id` / `report_path`）与 witnessloop 的必填字段表（`src/witnessloop/constants.py:95-105` 的 `REVIEW_MANIFEST_REQUIRED_FIELDS`，要 `stage` / `author_run_id` / `report_path`）**不同构**。本 change **不统一 schema**（那要改 `agent/**` 与它的 2874 行测试），而是**两套并存**：asterwynd 的 `reviews/<phase>-review-manifest.json` 给本地 checker，witnessloop 侧用 `manifest build` 产出 `reviews/<stage>.manifest.json`（见 `design.md` Decision 2）。**schema 统一是阶段 C 之后的独立 change。**
- **新门禁的已知红（预期，不改判据）**：范围**不止** in-flight change——它包含 ① 现有 active change `add-minimal-tui-runtime-view`（**没有 `reviews/` 目录**，实测）；② **本 change 自己**（阶段 A 落地后同样缺 witnessloop 形态的 manifest）。两者都**如实记为已知红**，**不为了变绿而放宽判据**（见 `design.md` Decision 7）。
- **两个 PreToolUse 守卫并存（design 原先漏掉的缺口）**：asterwynd 已有 `scripts/workflow_guard.py`（matcher `Write|Edit|Bash`，`scripts/workflow_guard.py:5`），接入 plugin 会再加一个 `witnessloop guard` hook（matcher `Write|Edit`，witnessloop `plugin/hooks/hooks.json`）⇒ 同一个 `Write|Edit` 上会有**两个 block 源**。两者的合并/串行语义、报错归属、命令命名空间是否冲突**均未实测**（见 `design.md` Decision 8 与 Risk R9，阶段 A/B 有对应实测项）。
- **自举鸡生蛋**：接入本身这一次 PR 只能靠本地 check + 人工 review 兜——这正是本 change 分「只跑不拦」的影子阶段的原因。

## Reference Implementation Research

- research_tier: full
- status: enabled
- reason: 本 change 引入**新的外部工具与新的协议面**——witnessloop CLI（`init` / `uninit` / `check` / `guard` / `build`）、reusable workflow `@v1`、以及 `witnessloop/policy@v1` 这一份**新的策略 schema**。按本仓分流判据表，「引入新框架/新依赖/新协议」与「走 grill 的非平凡 change」两条同时命中 ⇒ 判 `full`。调研对象是本仓唯一的接入目标（witnessloop 仓本身）+ issue #305 的实测盘点，二者都不是「可选的业界参考」，而是接入正确性的**判据来源**（哪些门禁存在、挂在什么触发上、policy 有哪些可配字段）。
- research questions:
  - witnessloop 的门禁面**到底覆盖了什么**，与 asterwynd 现有 checker 的重合面/缺口面各是什么？——重合面决定「以后能下掉什么」，缺口面决定「必须保留什么」。
  - 接入的正确姿势是什么：出厂 policy 能直接用吗？`init` 会写哪些文件、会不会与既有文件冲突？冲突怎么处置？
  - 现有 122 个归档、78 份事件日志、以及 manifest 的字段/文件名差异，在 witnessloop 契约下会怎样？
  - 两套门禁并存的 CI 形态是什么（job 名、required 关系、阶段顺序）？
  - 本地守卫的面会变宽还是变窄？
- findings:
  - **接入目标仓 = `/home/happy/witnessloop`**（tag `v1`，实测 `git describe` 得 `v1`；README 已诚实写明「自举鸡生蛋：接入本身那一次 PR 只能靠人工 review 兜」）。CLI 面见 `src/witnessloop/cli.py`：`init --root/--dry-run/--gate-ref/--policy/--test-command/--no-tests`、`uninit`、`guard`、`check`、`manifest build`（证据产出，`manifestcmd.py`）。
  - **门禁的触发是 `code_hits`，不是「有 change 目录」**。`src/witnessloop/checkcmd.py:77` 算出 `code_hits`（本次 diff 触达 `policy.require_change_for` 的路径），`:96 if code_hits:` 才追加 `grill-adversarial` + `building` 两条 stage manifest 判定；`_code_hits` 的 docstring（`checkcmd.py:169`）明确「**什么算代码**的唯一口径」由 `_require_change`（改代码必须挂 change）、`building` 门禁、`grill-adversarial` 门禁**三者共用**。⇒ 出厂 `require_change_for`（`src/witnessloop/constants.py:43-52` 的 `DEFAULT_REQUIRE_CHANGE_FOR`，是 **8 条目录 glob 的元组** `src/**` / `lib/**` / `app/**` / `apps/**` / `packages/**` / `server/**` / `cmd/**` / `internal/**`）对 asterwynd 零命中的直接后果就是：**两个核心门禁静默不触发**。这条是本 change 最重要的一条实现约束。
  - **`--policy` 是「替换出厂默认」的整份替换**（`cli.py:49-54`：轻校验，只要求可解析为 JSON 对象，语义合法性由 `check` 兜底）⇒ seed 必须是**完整 policy**，不是增量 patch。
  - **policy 可配字段确认**（witnessloop 自己的 `.witnessloop/policy.json` + `constants.py`）：`changes_root`（默认 `openspec/changes`，asterwynd 同形 ✓）、`protected_paths`、`require_change_for`、`required_artifacts`（默认 `proposal.md/design.md/tasks.md/specs/reviews`，asterwynd 同形 ✓）、`evidence.review_manifest_glob`（默认 `reviews/*.manifest.json`）、`evidence.events_file`（默认 `workflow-events.jsonl` ✓）、`evidence.protected_write_event_types`（默认 `["protected_path_write"]`）、`tests.disabled`。
  - **caller 的 job 名是 `gate / check`**：caller（`.github/workflows/witnessloop.yml`，`init` 生成、标「请勿手改」）只有 `jobs.gate.uses: …/gate.yml@v1`；reusable workflow `gate.yml` 里是 `jobs.check`（`gate.yml:29`），同一 job 里跑 `witnessloop check`（`:47`）+ 「adopter tests」一步（`:83`）⇒ **测试执行点与门禁同一个 job**，「测试失败 = required check 失败」。
  - **测试执行点**：`init --test-command "<cmd>"` 写 `.github/witnessloop-tests.txt`（`constants.py:27`），**总是覆盖**；不给 flag 时只在文件不存在时种哨兵 `<<REPLACE-ME>>`，含哨兵 ⇒ `check` 判红（`checkcmd.py:_tests_execution_point`）。第三条判据「非空」不可省——空文件会让 `check` 与门禁**同时判绿**而一个测试都不跑。
  - **本地守卫生效面**：`guardcmd.py:16-17` 自陈「本动词是**防遗忘**，不是防对抗——agent 可以改用 Bash 写文件（`Write|Edit` matcher 不覆盖它）、也可以不装插件。真正的锚仍是 CI required check。」⇒ 「从解析 Bash 降到只看 `Write|Edit`」是**上游已文档化的既定边界**，不是我们的用法错误。
  - **归档天然安全**：`changed_change_ids` 只挑 active change（issue #305 实测「21 个变更文件，0 个 change 目录」）；`archive/**` 被完全忽略。反过来说，**把 `archive/**` 列进 `protected_paths` 会立刻产出 12 条假红**（`is_archive_move` 只认纯改名，不认「实现 PR 里新增归档目录」）⇒ 迁移时**不要列它**。
  - **解释事件机制两边同构**（issue #305 更正评论）：asterwynd `workflow-events.jsonl` 的 `event_type` / `artifact_path` / `reason` / `approved_by` 与 witnessloop 要求**逐字对得上**；asterwynd 的规则表读法见 `scripts/check_openspec_artifacts.py:1173` + `scripts/flow-policy.json` 的 `protected_paths[].event_types`（`backlog_updated` / `current_spec_synced` / `change_archived` / `protected_artifact_explained` / `cli_written` 等治理档）。⇒ 这一条**从「要不要引入新仪式」降级为「项目配置怎么填」**。
  - **本地参考仓库不可用的诚实记录**：本 worktree 没有 `.dev/reference-repos.txt`（该文件 gitignore，工作区本地配置）⇒ 本次调研**没有走「本地参考仓库对比」这一层**，全部 findings 来自（a）issue #305 的实测数据与（b）直接阅读 witnessloop 仓源码。这不构成豁免，仅记录依据来源。
- design impact:
  - **接入形态被钉死**：`init --policy <seed>` 一次写成**完整** policy（seed 是仓外临时文件、**不入库**），因为出厂 `require_change_for` 会让 `building` / `grill-adversarial` 两个门禁静默失效。
  - **policy 的可配字段直接对应待拍板决策**：`evidence.protected_write_event_types`（事件类型名映射）、`require_change_for`（最终面）、`protected_paths`（是否含 `openspec/specs/**` 与三条文档路径）。**`evidence.review_manifest_glob` 不是决策项、但也**不是**「放宽成 `reviews/*-manifest.json` 就好」**——独立 grill 实测证明真正的差异是 manifest 的**字段 schema**（`phase` vs `stage` / `author_run_id` / `report_path`），放宽 glob 反而会把本仓 schema 的 manifest 卷进候选集（错绑 + 逐份报红）。⇒ glob **保持默认 `reviews/*.manifest.json`**，两套 manifest 并存（`design.md` Decision 2）。
  - **接入会多出一个本地守卫**：本仓已有 `scripts/workflow_guard.py`（matcher `Write|Edit|Bash`），plugin 再加 `witnessloop guard`（matcher `Write|Edit`）⇒ 同一 `Write` 上两个 block 源；合并语义/报错归属/命令命名空间三项**未实测**（`design.md` Decision 8）。
  - **新建的当前规格会被本 change 自己的实现证伪**：`openspec/specs/dev-workflow-gate/spec.md` 的负向占位 Requirement 明禁 `.witnessloop/policy.json` 与「`.github/workflows/` 下只有 ci.yml」，而阶段 A 恰好创建它们。⇒ 照 `platform-gate` 先例（实现 commit `f7e912b` 覆盖占位规格）在 change 的 spec delta 增 `## REMOVED Requirements`，并把同步步骤从「只合并 ADDED」改为「**覆盖重写**」。
  - **`protected_paths` 明确不含归档目录**（实测 12 条假红），这与「归档是簿记动作」的现有语义一致。
  - **阶段划分由「required 的勾选时机」定**：GitHub 只对「head 里含该 workflow 的 PR」跑该 workflow ⇒ **把 caller 放进分支就实现了「主线不开」**，所以「A 只跑不拦 / C 才勾 required」在平台上天然成立，不需要额外的开关机制。
  - **旧件下掉被本 change 显式排除**：findings 显示重合面（change 契约 / 证据绑定 / grill / grill-adversarial / building / 受保护写入 / 本地 guard / 测试执行点）**可以**逐步下掉，但下掉需要逐项对照缺口面（RIR / Impact Analysis / benchmark 门禁 / tasks 完成度 / 归档点完成度 / 事件投影 / `platform_gate.py`），**属于后续 change，不进阶段 A**。
