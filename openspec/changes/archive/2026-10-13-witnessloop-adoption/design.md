# Design: witnessloop 影子接入（阶段 A）

## Context

asterwynd 自建了一整套「开发流程门禁」：change 契约、review manifest 的 hash/revision 绑定、grill 证据、grill-adversarial 门禁、building 门禁、受保护写入的结构化解释事件、本地写码前 guard、CI required check、测试执行点门禁。这套东西在 issue #305 里被盘点、被判定为「与本仓流程工具化抽取出的独立工具 **witnessloop** 高度重合」。

本 change 只做**接入的第一阶段（影子接入）**：把 witnessloop 的接入产物落进一条分支，让新门禁**只跑不拦**，用一个真实小需求验证它，然后停下来等验收结论。**下掉旧件、改 `AGENTS.md`、勾 required 都不在本 change 内。**

三条来自 #305 探测的硬事实决定了本设计的形状：

1. **出厂 policy 对 asterwynd 零命中**（`require_change_for` 出厂值是 `src/lib/app/apps/packages/server/cmd/internal`）⇒ witnessloop 的 `building` 与 `grill-adversarial` 门禁挂在 `code_hits` 上，用出厂 policy 接入 = 这两个门禁静默不触发 ⇒ **必须 `init --policy <seed>` 一次写成**。
2. **并存是加法**：`master` 现有 required = `["validate", "benchmark-gate"]`（本分支 `gh api` 实测）不动；新 job 阶段 A 不勾 required。
3. **`.claude/` 被 gitignore**（`.gitignore:9`）⇒ plugin 安装（交互层）是**本地动作**、不进 PR；CI 层（caller workflow）才是进 PR 的那一半。**两者是独立开关。**

第四条来自**独立 grill 的实测**（`reviews/grill-design.md`），它改写了本设计的一处定性：

4. **两套 manifest 的差异是 schema，不是文件名**：asterwynd 的生成器写 `phase`，witnessloop 要 `stage` / `author_run_id` / `report_path` ⇒ 阶段 A/B **不迁 schema**，改成**两套并存**（Decision 2）。

第五条是原设计**完全没覆盖**的缺口，由 grill 补出：

5. **接入会多一个 PreToolUse 守卫**：本仓已有 `scripts/workflow_guard.py`（matcher `Write|Edit|Bash`），plugin 再加一个 `witnessloop guard`（matcher `Write|Edit`）⇒ 同一 `Write` 上两个 block 源，合并语义未实测（Decision 8）。

第六条来自**独立对抗轮**（`reviews/grill-adversarial-v1.md`，CHANGES_REQUESTED），它证伪了整合稿的三处核心判断：

6. **grill 报告正文判据不兼容**：witnessloop 的 `_SOURCE_RE` **不认加粗的 `- **来源**: x`**，而本仓记录通篇如此 ⇒ **一旦建了 witnessloop 形态的 grill 证据，grill stage 就结构性不可能判绿**（Decision 2 末段、**U7**、R11）。⚠️ **阶段 A 不会遇到这条**：默认不落 manifest ⇒ 正文判据不被触发（U7）；它是**将来**（阶段 B/C 建 witnessloop 形态证据时）的前置。连带地，「样板 manifest = 验收里第一次绿的一侧」（B1）与「manifest 一建就 stale」（B3）两条也已按实测改写（Decision 7 / R13）。

## Goals / Non-Goals

**Goals:**

- 在一条分支上落齐 witnessloop 的接入产物：定制 policy + caller workflow + 测试执行点 + （本地）CC plugin。
- 让 witnessloop 的 `gate / check` job 在 CI 里**跑起来**且**不拦任何合入**。
- 用一个**真实小需求**在新流程上跑一遍，拿到「值不值得真打开」的判断依据。
- 把七条 Open Question 摆到台面上（每条带推荐值 + 具体例子），由用户拍板——**已完成**：2026-10-13 全部按推荐值裁定，见 `## User Rulings`（U1–U7）。
- 保证回退路径干净：`witnessloop uninit` 或手工删 `.witnessloop/` + caller，旧门禁原封不动。

**Non-Goals:**

- 不下掉任何现有件（`check_openspec_artifacts.py` / `workflow_guard.py` / `workflow_state.py` / `flow-policy.json` / `platform_gate.py` / `agent/workflow/*` 在本 change 内**一行不改**）。
- **不改 `agent/**`**（这条边界要写准）：阶段 A/B **不迁 manifest schema**，所以**不需要**动 `agent/workflow/review_manifest.py` 与它的测试——「不改 `agent/**`」是本 change 的**结论**，不是需要绕开的约束。**schema 统一（会改 `agent/**`）是阶段 C 之后的独立 change**，见 Decision 2 与 tasks 的「后续候选」。
- 不修已知红（见 Decision 7）：不为了让 in-flight change 或本 change 自己变绿而放宽任何判据。
- 不改 `validate` job、不动 `.github/workflows/ci.yml`、不动 branch protection 的既有两项。
- 不勾 required（那是阶段 C）。
- 不迁 RIR / Impact Analysis / benchmark 门禁 / tasks 完成度 / 归档点完成度进 witnessloop。
- 不给 witnessloop 加新能力（缺什么 → 去 witnessloop 立 issue）。
- 不为 in-flight 的 `add-minimal-tui-runtime-view` 放宽任何判据。

## Decisions

### Decision 1: 用 `init --policy <seed>` 一次写成，seed 是仓外临时文件、不入库

**选择**：接入命令形如 `witnessloop init --root . --policy /tmp/witnessloop-asterwynd-policy.json --test-command "<命令>"`。seed 文件放仓外临时路径，**不 commit**；产物 `.witnessloop/policy.json` 才入库。

**理由**：
- 出厂 `require_change_for`（`src/witnessloop/constants.py:43-52` 的 `DEFAULT_REQUIRE_CHANGE_FOR`，**8 条目录 glob 的元组**）对 asterwynd 的 `agent/` / `scripts/` / `web/` **全不命中**；而 `building` 与 `grill-adversarial` 两个门禁**共用同一条 `code_hits` 触发**（`src/witnessloop/checkcmd.py:77` + `:96`）⇒ 用出厂 policy 接入，这两个核心门禁**完全不触发**，接入会退化成「只有一个 check 壳」。
- `--policy` 是**整份替换**而非增量 patch（`cli.py:49-54`：轻校验，只要求可解析为 JSON 对象）⇒ seed 必须是完整 policy。
- seed 不入库与 witnessloop 自己的做法一致（witnessloop 仓把 policy 直接放在 `.witnessloop/policy.json`，没有独立的 seed 文件概念）；把「生成 policy 的那份输入」留在仓外，避免两个真相源。

**落地形态（policy 的最终内容——四项配置值已由 U1/U2/U3/U6 裁定，本 JSON 即定稿）**：

```json
{
  "schema": "witnessloop/policy@v1",
  "changes_root": "openspec/changes",
  "protected_paths": ["openspec/specs/**", ".witnessloop/**",
                      "docs/known-issues.md", "docs/known-debt.md",
                      "docs/openspec-change-backlog.md"],
  "require_change_for": ["agent/**", "scripts/**", "web/**"],
  "required_artifacts": ["proposal.md", "design.md", "tasks.md", "specs", "reviews"],
  "evidence": {
    "review_manifest_glob": "reviews/*.manifest.json",
    "events_file": "workflow-events.jsonl",
    "protected_write_event_types": ["current_spec_synced", "backlog_updated",
                                   "change_archived", "protected_artifact_explained"]
  }
}
```

**注意两条自洽性**（grill 实测指出，本设计已修正）：
- `review_manifest_glob` **保持 witnessloop 默认 `reviews/*.manifest.json`**——**不要**放宽成 `*-manifest.json`。理由见 Decision 2（放宽会把 asterwynd schema 的 manifest 一起卷进来）。
- `protected_paths` **必须与 U1 的事件类型表配套**：只列 `openspec/specs/**` + `.witnessloop/**`（= witnessloop 出厂默认）而把 `backlog_updated` / `protected_artifact_explained` 填进事件类型表，会让这两个类型成为**死配置**（列了也没有对应的受保护路径消费它，见 `checkcmd.py:206-215`：`_protected_writes` 先按 `protected_paths` 命中、才查事件）。⇒ 上面把 asterwynd 现有的三条受保护文档路径一并列入（**R6 已裁定：补**）。

### Decision 2: manifest 两套并存；schema 统一留到阶段 C 之后（**原定性错，已按 grill 实测重写**）

**原设计错在哪**：原 Decision 2 把差异定性为「文件名 glob 不匹配 ⇒ 纯机械修正」，并把 glob 改成 `reviews/*-manifest.json`。grill 用**asterwynd 形态**的 manifest 在隔离副本里实跑 `check`，得 **6 条红**（该轮把它放在 glob **能匹配**的位置；对抗轮进一步钉准了红数的分档：glob 匹配 0 份时 `check` 早退、现状只有 **2 条**，见下方「孤儿」段）：
`manifest 缺字段：stage, author_run_id, report_path` · `reviews/building-review.md 孤儿报告` · `reviews/grill-design.md 孤儿报告` · `无 stage=grill 的 manifest（现有 stage：?）` · `无 stage=grill-adversarial 的 manifest` · `无 stage=building 的 manifest（现有 stage：?）`。
换成 witnessloop 形态后「缺字段」与「无 stage=building」两条消失。⇒ **glob 不是问题所在**，改它**一条红都消不掉**。

**真正的差异是 manifest 的字段 schema**：

| | asterwynd 生成器 | witnessloop 必填 |
|---|---|---|
| 字段 | `schema` / `change_id` / **`phase`** / `verdict` / `reviewer_run_id` / `base_sha` / `head_sha` / `tasks_hash` / `spec_hash` / `diff_hash` / `report_hash` | `stage` / `reviewer_run_id` / **`author_run_id`** / `base_sha` / `head_sha` / `tasks_hash` / `spec_hash` / `report_hash` / **`report_path`** |
| 出处 | `agent/workflow/review_manifest.py:93-104`（`"phase": phase`）；路径 `reviews/<phase>-review-manifest.json`（同文件 `:65-69`） | `src/witnessloop/constants.py:95-105` 的 `REVIEW_MANIFEST_REQUIRED_FIELDS` |

三处差异：① `phase` ≠ `stage`（字段名不同；witnessloop 按 `doc["stage"]` 匹配，`evidence.py:197-208`）；② 缺 `author_run_id`；③ 缺 `report_path`。

**"孤儿"的真实触发条件（对抗轮实测修正，原design的表述不准）**：`_check_orphan_reports` 挂在 `contract.py:127-148` 的 manifest 循环之后，而该循环在 **glob 匹配到 0 份时于 `:129-135` 早退**。⇒ ① 「本仓 manifest 不匹配默认 glob」本身 **不会**让 `reviews/*.md` 变孤儿（现状实测只有 2 条红：`缺少 review manifest` + `无 stage=grill 的 manifest`）；② **真正的引信是「落了任意一份 witnessloop 形态 manifest」**——从此 `reviews/**/*.md` 里**每一份**未被 `report_path` 绑定的报告都判孤儿（`contract.py:185-219`）。实测：建一份 `grill.manifest.json` 后，红数 **2 → 14**；再放入 `grill-adversarial.md`（issue #298 要求停轮前必须存在）后 **→ 16**。

⇒ 由此得到**阶段 A 的操作约束**：**要么给 `reviews/` 下每一份报告都建 manifest，要么一份都别落**——中间态（只落一部分）比不落更红。

**"并存"在 grill 线上其实是"纯新增"（对抗轮实测）**：本仓 75 份 `*-review-manifest.json` 的 `phase` 取值只有 `building`(74) / `design`(1)——**`grill` / `grill-adversarial` 从来没有过 manifest**，只有 `.md` 报告（63 份 `grill-design.md`、8 份 `grill-adversarial*.md`）。⇒ Decision 2 的「并存」在本仓侧只覆盖 `building` 一条线；grill / grill-adversarial 两条线是**从零新增** witnessloop 形态证据。

**选择（定案）**：

1. **阶段 A/B 不迁 schema**：不改 `agent/workflow/review_manifest.py`（改了就要连带改它 2874 行的测试体量，且与「阶段 A 一行不改旧件」的边界冲突）。
2. **两套 manifest 并存**：asterwynd 的 `reviews/<phase>-review-manifest.json` 继续由现有工具链产出、继续喂本地 checker；witnessloop 侧用 **`witnessloop manifest build`**（`src/witnessloop/manifestcmd.py`；`cli.py:109-140` 的 `--change` / `--stage` / `--report` / `--reviewer-run-id` / `--author-run-id`）产出 **`reviews/<stage>.manifest.json`**。
3. **glob 保持 witnessloop 默认 `reviews/*.manifest.json`**——**不要**放宽成 `*-manifest.json`。
4. **schema 统一留到阶段 C 之后**：那是会改 `agent/**` 的独立 change（写进 Non-Goal 与 tasks 的后续候选）。

**为什么不能放宽 glob**（grill 实测，原判断「无害」被证伪）：`stage_manifest_findings_in_change` 取 **`matching[0]`**（按路径字典序的第一份），而 `validate_review_manifests` 会**逐份**校验所有匹配文件（`evidence.py:197-210`；`contract.py:127-149`）。⇒ 一是「多份同 stage 时只有字典序第一份被当证据、其余静默忽略」，可**错绑**到悬空报告——实测把坏的 `aaa-manifest.json` 排在合法文件之前，坏的那份顶替了合法的；二是「任何一份坏 manifest 都独立报红」（**宁多勿漏**，不是无害）。放宽 glob 会把 asterwynd schema 的那批文件一并卷进候选集，两种症状都会踩。

**文件名无碍、但正文判据不同构（对抗轮实测证伪了原「同构」判断）**：`report_path` 是自由字段，所以本仓的 `reviews/grill-design.md` **文件名无碍** ✓。但 witnessloop 对 grill 报告**正文**的判据与本仓写法**系统性不兼容**——`src/witnessloop/evidence.py:33` 的 `_SOURCE_RE = re.compile(r"来源\s*[:：]")` 要求「来源」后**直接**接冒号，**不接受 `- **来源**: x` 这种加粗写法**（实测：裸写法命中、加粗不命中）；而本仓记录**通篇是加粗**（本 change 自己的 `grill-design.md` 有 12 处这种行 ⇒ 7/7 条 Confirmed Decision 全判「缺 `来源:`」）。⇒ **grill stage 按现有报告格式结构性不可能判绿**，这是本 change 的**已知阻塞/前置依赖**，见 **U7**（已去 witnessloop 立 issue [#20](https://github.com/Xingkai98/witnessloop/issues/20)）。

**代价（写进阶段 B 报告）**：阶段 B 的流程会与 asterwynd 现有的 `/review-loop` **分叉**——`/review-loop` 只产 asterwynd 形态的 manifest（且本仓侧**根本没有** grill / grill-adversarial 两份 manifest 的产出路径），阶段 B 必须显式多跑 `witnessloop manifest build` 才能拿到 witnessloop 形态的证据。这正是「影子期两套并存」的具体成本。

### Decision 3: `protected_paths` **不含** `openspec/changes/archive/**`

**选择**：归档目录**不列**进 `protected_paths`。

**理由**：asterwynd 的语义是「**归档是簿记动作、免解释**」——实现 PR 直接落 `archive/<date>-<id>/`，每个文件都配解释事件是不现实的。而 witnessloop 的 `is_archive_move` 豁免**只认纯改名**、不认「在实现 PR 里新增 archive 目录」⇒ 列上它，实测**立刻多出 12 条假红**（整个归档 change 目录每个文件一条）。

**替代方案与否决**：① 给 122 个历史归档补 manifest/事件——代价过大且不解决新归档；② 修 witnessloop 让 `is_archive_move` 认新增目录——那是**改上游**，超出本 change 范围（缺能力 → 去 witnessloop 立 issue）。⇒ 选「不列」。

**配套的运维约束（grill 实测，design 原先漏写）**：witnessloop 的归档豁免只认 **`R100` 纯改名**（`contract.py:38-55`，状态码 + 无内容改动）。grill 实测两种形态：**(a)** `git mv` 单独成一个 commit ⇒ `check：通过 ✓`；**(b)** `git mv` 与同一 commit 内的内容改动并用 ⇒ git 记作 `A`/`D` ⇒ `is_archive_move` 为假 ⇒ `changed_change_ids` 把**旧 active 路径**当 change id ⇒ **3 条红**（`change 目录不存在` + `缺少 review manifest` + `无 stage=grill 的 manifest`）。⇒ **归档 move 必须是独立的纯 rename 提交**，这条已写进 `tasks.md` 的 Z.5 与收尾硬约束。

### Decision 4: 阶段 A **不勾 required**；GitHub 的 workflow 触发语义天然实现「主线不开」

**选择**：caller workflow 进分支即可；`master` 的 required 保持 `["validate", "benchmark-gate"]` 不变；新增的 `gate / check` job 在阶段 A **不进 required**。

**理由**：GitHub **只对「head 里含该 workflow 文件的 PR」运行该 workflow** ⇒ 把 caller 放进 feature 分支，`master` 上的既有 PR 完全不受影响，而本分支的 PR 会多跑一个 job。**「只跑不拦」因此不需要任何额外开关机制**——「放进分支」本身就是那个开关。

**阶段顺序（A / B / C）**：

| 阶段 | 内容 | 出口条件 |
|---|---|---|
| **A 影子接入** | 落接入产物（policy + caller + 测试执行点 + 本地 plugin），旧 checker 与 `validate` job 不动 | 本分支 PR 的 CI 里出现 `gate / check` 并**跑出 findings**；`master` required 仍为两项 |
| **B 真需求验证** | 用**一个真实小需求**在新流程上跑一遍（`guard` 拦 → grill/审阅证据 → `check` 核 → 测试执行点跑） | 拿到「值不值得真打开」的判断依据（含已知红清单、findings 的可读性评估） |
| **C 真打开** | 合入 + 勾 required + `AGENTS.md` 流程段改写（**单独 change/PR**） | 本 change **不做** C |

**「真打开」为什么必须单独一步**：勾 required 是**平台动作**且是**单向门**——一旦勾上，任何在途 change 的 in-flight 状态（如已知红）都会立刻拦合入。分阶段让「值不值得」这个判断发生在不可逆动作之前。

### Decision 5: 保留为 **asterwynd 本地**（不进 witnessloop）的八项

**选择**：以下八项留在本仓，witnessloop 只接管**流程骨架**：

| 保留项 | 载体 | 为什么不迁 |
|---|---|---|
| RIR（`_check_reference_implementation_research`） | `check_openspec_artifacts.py` | 项目特有的「调研门禁」，witnessloop 无对应概念 |
| Impact Analysis | 同上 | 项目特有的 change 文档契约 |
| benchmark 门禁 | `benchmark-gate` job | 项目特有的评测面 |
| `_check_design_review_task` | 同上 | asterwynd 的 grill 证据形状（`reviews/grill-design.md` + `## Confirmed Decisions` ≥ 3 + `## User Confirmation`）比 witnessloop 的「manifest 存在性 + 正文完备性」更细 |
| tasks 完成度 | 同上 | 项目特有的任务清单语义 |
| 归档点完成度门（`_check_archived_completion_gate`） | 同上 | witnessloop **没有 archive 门禁**（issue #305 明列） |
| `platform_gate.py` + `platform-gate.json` | `scripts/` | 管的是**平台面**（branch protection），不是仓内证据 |
| 事件投影（`workflow_state.py` + `agent/workflow/*`） | `scripts/` + `agent/` | witnessloop **完全没有对应物**；且 `workflow-events.jsonl` 本身已与 witnessloop 同构，投影是本地工程 |

**理由**：issue #305 的定位是「witnessloop 接管**流程骨架**，asterwynd 保留**项目规则**」。`check_openspec_artifacts.py` 因此从「流程骨架」降级为「项目规则」，而**不是被下掉**。

### Decision 6: 顺手清理候选（`handoff.json` 残留）——**本 change 只登记，不动手**

**选择**：把「退役状态机残留（`handoff.json`，122 个归档里只有 5 个有）」记为 **Non-Goal + 独立后续任务**，**不混进阶段 A**。

**理由**：`_check_handoff_json` 相关测试量不小（issue #305 盘点：`_check_handoff_json` 6 + `_check_archived_projectable` 6 + `_check_new_archived_completion_gates` 5），但它对应的是**已经退役**的子系统 ⇒ 值得清，但清理会触碰 `check_openspec_artifacts.py` 与 5 个归档目录——**与「阶段 A 一行不改旧件」直接冲突**。混进来会让影子接入的 diff 无法被独立评估。

**交付形态**：在 `design.md` 与 `tasks.md` 里记成可执行的后续 change 候选（见 tasks 的「后续候选」节），不在本 change 的 PR 里改代码。

### Decision 7: 已知红的**范围**与处置 —— 含本 change 自己，**不许为它们放宽判据**

**原设计错在哪**：原 Decision 7 只点名 `add-minimal-tui-runtime-view` 一条。grill 指出（并由 Decision 2 的 schema 结论推出）：**范围是「所有用 asterwynd 生成器产 manifest 的 change」，而本 change 自己也在其中**。

**已知红清单（两条）**：

| # | 对象 | 红的原因 |
|---|---|---|
| K1 | active change `add-minimal-tui-runtime-view` | **没有 `reviews/` 目录**（实测）⇒「缺少 review manifest」+「无 stage=grill 的 manifest」 |
| K2 | **本 change 自己**（`witnessloop-adoption`，阶段 A 落地后的 PR） | 也缺 witnessloop 形态的 manifest（本仓现有工具链只产 `phase` 形态，见 Decision 2）；且本 change 的 diff **不触达 `agent/**` / `scripts/**` / `web/**`** ⇒ `code_hits` 为空 ⇒ `building` / `grill-adversarial` 两条 stage 判定**本来就不触发** |

**处置（选择）**：

1. **统一记为「预期红」**，如实列进阶段 A 验收报告与阶段 B 报告，**不修**（K1 是 in-flight 历史事实；K2 是影子期的结构性产物）。
2. **不放宽任何判据**：不给 change 开豁免、**不**把 `required_artifacts` 里的 `reviews` 去掉、**不**为 K1 补一份「凑数」manifest。理由：放宽判据会让**新 change 也一起被放行**——正是 witnessloop 要堵的形态。阶段 A 不勾 required ⇒ 两条预期红**在阶段 A 不造成任何实际拦截**。
3. **样板方案已按对抗轮实测改写——它不再提供「绿的一侧」**。原推荐（本 change 自己跑一次 `manifest build` 当样板，声称「阶段 A 验收里第一次出现绿的一侧」）**被实测证伪**：
   - 现状（`reviews/` 只有本仓形态报告）⇒ **2 条红**；
   - 落一份 `grill.manifest.json` 后 ⇒ **14 条红**（孤儿规则被激活，见 Decision 2 的操作约束；外加下面第 4 条的 `缺 来源:`）；
   - 再放入 `grill-adversarial.md` 后 ⇒ **16 条红**。
   ⇒ **K2 的红数不是「2 条」，而是随「落了几份 manifest」变化的 2 → 14 → 16**。样板**不会**带来绿：grill stage 因 `来源:` 谓词（**U7**）**结构性无法判绿**。
4. ⇒ **阶段 A 的默认处置改为「一份 manifest 都不落」**，K2 保持 **2 条红**（这是最干净的中间态）。若确实要落样板（例如为了验证 `manifest build` 通路），必须**同时**满足三条：① 给 `reviews/` 下**每一份** `.md` 都建 manifest（否则每份未绑定报告成孤儿）；② 在**所有内容提交之后**重建（stale 约束，见 R13）；③ 明确写下「它**不是**绿的一侧」（避免后续读者按原文档误判）。这三条已写进 `tasks.md` 的 A.5.6。
5. K1 **不按同样方式处理**：给它补证据 = 替一个 in-flight change 补历史证据，会让「它到底实现了没有」的语义漂移。**K1 就让它红**，作为「真打开」时必须一并决策的收尾项（阶段 C 的输入）。

### Decision 8: 两个 PreToolUse 守卫并存（**原设计完全没覆盖的缺口**）

**缺口**：原设计只在 Risk R3 谈了「本地守卫能力**变窄**」（丢 Bash 面），**没有覆盖相反的一面**——接入 plugin 会**多出一个 block 源**。实测两侧形态：

| | asterwynd 现有 | witnessloop plugin |
|---|---|---|
| 载体 | `scripts/workflow_guard.py`（PreToolUse hook） | `plugin/hooks/guard.sh` → Path 上的 `witnessloop guard` |
| matcher | `Write\|Edit\|Bash`（`scripts/workflow_guard.py:5`） | `Write\|Edit`（witnessloop `plugin/hooks/hooks.json`） |
| 阻断约定 | 以 `exit 2` 拦（`scripts/workflow_guard.py:615,628,638,654,667`） | `guard.sh:38-41` 把 guard 的 `1` 映射成 `exit 2` |

⇒ 同一个 `Write` 上会命中**两个** hook，两者都用 CC 的 `exit 2` 约定 ⇒ 拦截效果是**并集**（任一 exit 2 即拦）。

**选择**：**阶段 A 保留两个守卫并存**（不下掉任何一个），并把未知面作为**实测项**写进阶段 A/B，而不是靠推理填坑。

**「新增拦截面」的定性是错的（对抗轮实测证伪）**：原设计说 witnessloop 的 guard 会在「本仓现有守卫**不管**的维度」上新增拦截。**实测证伪**——本仓守卫**本来就拦这一维度**：`scripts/workflow_guard.py:640-654` + `_grill_evidence_missing`（`:364-404`）在写 `agent/**` 且该 change 缺 grill 证据时同样 `exit 2`（实测输出 `⛔ change '…' 尚未完成独立 subagent design grilling.`）。⇒ 两侧是**同一维度、不同判据**（本仓=文件 + 正文；witnessloop=manifest + 正文），**不是新增的面**。行为变化只有一条：**退步**（丢 Bash 面）。

**真正未实测的只有两项**（阶段 A/B 必须实测，不得臆断）：

1. **CC 的 hook 合并语义**：settings 的 hook 与 plugin 的 hook 同时匹配时，CC 是串行还是并行？任一 exit 2 即拦、还是首个非零即终止？
2. **报错归属**：被拦时用户看到哪个守卫的提示？两个都出还是只出一个？

两条都**只在真装 plugin 的宿主上可测**，且**必须在两棵树各做一次**——对抗轮实测 building worktree 下**没有 `.claude/` 目录**（`.gitignore:9` 忽略 + worktree 无副本），本仓守卫的 hook 只挂在主 checkout `/home/happy/my-agent/.claude/settings.json`（matcher `Write|Edit|Bash`）⇒ 在 worktree 上只能观察到 plugin 那一个。这一点已写进 `tasks.md` 的 A.4.5。

**其余三项不必列为「未实测」**（对抗轮给出可机械判定路径）：

3. **命令命名空间**——**可静态判定**：`plugin/.claude-plugin/plugin.json` 的 `"name": "witnessloop"` ⇒ 命令命名空间化，与仓内 `.claude/commands/{grill.md,review-loop.md}` 不同名。A.4.5 顺手确认即可。
4. **`guard.sh` 的前置条件（已知风险，不是"版本可能漂移"这么轻）**：`plugin/hooks/guard.sh:32` 调的是 **PATH 上的裸 `witnessloop`**，且 `:38-41` 的退出码映射是「**1 → exit 2（拦）**，**其余（含 2 = 用法错误 / 旧版 CLI 的 invalid choice）→ exit 0（放行）**」（注释自陈这是为了避免旧版 CLI 把每个 Write 都拦下）。⇒ 实测本机 PATH 上那份是 **0.1.0、没有 `guard` 子命令** ⇒ **整个 guard 静默空转**（shim 退出码 0）。**后果**：A.4.5 / B.5 若不做「PATH 上那份 CLI 是哪一个」的前置核验，会把「放行」误读成「证据完备」。⇒ 阶段 A 的前置条件是 `command -v witnessloop` + `witnessloop --help` 含 `guard`；**design 原有的「验证一律用 `uv run witnessloop`」覆盖不到 `guard.sh`**（它在 plugin 里、硬编码裸命令）。
5. **policy schema 漂移**：与上条同源（两份 CLI 的 schema 可能不同步），随第 4 条一并核验。

**为什么不在本阶段消除重复**：下掉 `scripts/workflow_guard.py` 属于「下掉旧件」，本 change 明确不做（非目标）；而改 witnessloop 的插件面是改上游。并存是影子期的**必然形态**，把它实测清楚正是本阶段的价值。

## Pre-Implementation Review

- Questions resolved:
  - 接入形态（`init --policy` 一次写成 vs 出厂 policy + 后续手改）——**已定**：一次写成，理由见 Decision 1。
  - manifest 差异的归因——**已定：不是 glob，是 schema**；处置=**两套并存、schema 统一延后到阶段 C 之后**（Decision 2；grill 实测证伪了原「机械修正」定性，对抗轮进一步钉准红数——glob 匹配 0 份时 `check` 早退、现状 **2 条红**，落任意一份 witnessloop 形态 manifest 后 **14 → 16 条**。对应 grill 的 Q5/OQ2，其生效口径见 **U5**）。
  - 归档目录是否列 `protected_paths`——**已定：不列**（Decision 3，实测 12 条假红；grill 进一步实测出**归档 move 必须是独立纯改名提交**，见 tasks 的运维约束）。
  - 阶段划分与「只跑不拦」的实现方式——**已定**（Decision 4）。
  - 哪些留本地——**已定**（Decision 5）。
  - `handoff.json` 是否混入——**已定：不混入**（Decision 6）。
  - 已知红的范围与处置——**已定：含本 change 自己，如实记录 + 不放宽；阶段 A 默认一份 witnessloop 形态 manifest 都不落**（Decision 7；**原「补一份 grill manifest 当样板」的处置已被对抗轮实测证伪并撤销**——它会激活孤儿规则把红从 2 条拉到 14/16 条）。
  - 两个 PreToolUse 守卫并存——**姿态已定：两条都保留、未知面实测**（Decision 8）。
  - **对抗轮（`reviews/grill-adversarial-v1.md`）提出的 7 条阻塞全部已处置**：B1/B3（样板不是绿的一侧 + stale 顺序）→ Decision 7 / R11 / R13；B2（`来源:` 谓词不兼容）→ **U7** + witnessloop issue [#20](https://github.com/Xingkai98/witnessloop/issues/20)；B4（Q4 推荐值不可执行）→ Q4 改为 `uv run --extra dev pytest -q`；B5（B/C/N 节未勾未标）→ 加 `(post-merge)`；B6（Decision 8 定性错 + 实测点）→ Decision 8 / R9 / R9b 重写；B7（Q5 停轮口径）→ Q5 **撤回「已定案」，改为停轮项**。
- Options considered:
  - **A. 直接替换**：接入的同时下掉旧 checker 并把 `gate / check` 勾成 required。**否决**：会打开「一段没有任何强制（或换成没验证过的强制）的窗口」，且不可逆动作发生在验证之前。
  - **B. 影子接入（本方案）**：只跑不拦 → 真需求验证 → 再真打开。
  - **C. 出厂 policy 直接接入**：**否决**——`building` / `grill-adversarial` 门禁静默不触发，接入名存实亡。
  - **D. 阶段 A 一并统一 manifest schema**（改 `agent/workflow/review_manifest.py`）：**否决**——会把影子接入的 diff 从 `docs`+ 4 个新文件扩到 `agent/**` 与 2874 行测试，无法独立评估影子接入本身；且与「阶段 A 一行不改旧件」冲突。改成 Decision 2 的「两套并存」。
  - **E. 阶段 A 直接下掉 `scripts/workflow_guard.py`**（消除双守卫）：**否决**——属「下掉旧件」，本 change 非目标；且双守卫的真实行为还没实测（Decision 8）。
- Rejected alternatives:
  - 选 A / C / D / E 的理由如上。另否决「在本 change 内顺手清理 `handoff.json`」（见 Decision 6，会污染影子接入的 diff 可评估性）。
- Final confirmations:
  - 设计追问已完成：独立 grill 产出 `reviews/grill-design.md`；`## Open Questions` 七条已**逐条抛给用户并全部确认**（答复记录进该文件的 `## User Confirmation`，另见本文件的 `## User Rulings`）。**确认门槛已满足**，可进入阶段 A 实现。
  - 设计阶段审阅闭环已收敛：**最终版** `reviews/grill-adversarial.md` **判 PASS、无阻塞项**（首轮 `grill-adversarial-v1.md` 判 CHANGES_REQUESTED、7 条阻塞已全部整合；R3 独立复核后落到规范名，见 `grill-flow-hardening` / issue #298）。
- Remaining risks:
  - `--policy` 的语义合法性由 `check` 兜底 ⇒ seed 写错只会在**跑 `check` 时**暴露，不会在 `init` 时报错（见 Risks R2）。
  - 双守卫的**合并语义与报错归属**两项未实测（Decision 8，命名空间可静态判定）——必须在阶段 A 的验收里补实测项，且**两棵树各测一次**。
  - **`来源:` 谓词不兼容**（U7 / R11）：本仓 grill 记录在 witnessloop 的正文判据下**不可通过**，阶段 B 建了 witnessloop 形态 grill manifest 后会拿不到 grill 的绿。**已拍板（U7）：等上游 witnessloop #20 修、本仓零改动。**注意它**不是**阶段 A 的已知红——阶段 A 不落 manifest ⇒ 正文判据根本不会被触发（阶段 A 的已知红是「缺 manifest」类）。

## User Rulings（原 Open Questions，2026-10-13 用户逐条裁定，无遗留）

> **本 change 的 `## Open Questions` 已全部确认**：Q1–Q7 七条（Q1–Q3 立项时提出、Q4–Q6 独立 grill 补充、Q7 独立对抗轮补充），**全部按推荐值裁定**，逐条答复记录在 `reviews/grill-design.md` 的 `## User Confirmation`。无保留项、无新增停轮项。以下直接写**生效口径**，不列备选分支（未选分支的理由各压成一句「否决的备选」）。

### U1（原 Q1）: 解释事件类型名按本仓现有名字写进 policy

**裁定**：`policy.evidence.protected_write_event_types = ["current_spec_synced", "backlog_updated", "change_archived", "protected_artifact_explained"]`。**本仓零改动**——78 份历史 `workflow-events.jsonl` 不动、`scripts/flow-policy.json` 不动。

**否决的备选**：把类型名统一成 witnessloop 默认的单一 `protected_path_write`——要改 78 份历史日志与受保护路径规则表（`cli_written` 治理档），代价大，收益只是名字好看。

**落地效果**：某次实现 PR 同步 `openspec/specs/agent-runtime/spec.md` 时，该 change 的 `workflow-events.jsonl` 里那条 `{"event_type":"current_spec_synced","artifact_path":"openspec/specs/agent-runtime/spec.md", …}` **两边都过**——本地 checker 认它（`scripts/flow-policy.json`），witnessloop 也认（policy 里列了它）。

### U2（原 Q2）: `require_change_for` = `agent/**` + `scripts/**` + `web/**`，不含 benchmark 目录

**裁定**：`require_change_for = ["agent/**", "scripts/**", "web/**"]`；benchmark 目录**不纳入**。

**否决的备选**：把 benchmark 目录一并纳入——它有 345 个文件、多为任务数据与结果 fixture，纳入后「改一个 fixture 也要挂 change 目录 + 补两类审阅证据」，过重。

**落地效果**：修一条 benchmark 任务的坐标错误（改任务数据一行）只触及 benchmark 目录 ⇒ `code_hits` 为空 ⇒ 不要求 change 目录，走现有的 `benchmark-gate` 兜。若日后发现该目录下有需要门禁保护的运行时代码，走 tasks 的 **N.3**（窄模式）另立处理，**不改本裁定**。

**边界**：`tests/**`、`docs/**` 同样不纳入（纯测试/纯文档改动不该被拦）——与 witnessloop 出厂注释的取舍一致。

### U3（原 Q3）: `openspec/specs/**` 列入 `protected_paths`

**裁定**：`protected_paths` 包含 `openspec/specs/**`。

**否决的备选**：不列（交给本地 checker）——阶段 A 看似没事，但会留下「本地 checker 一旦下掉、spec 同步就没人管」的静默缺口。

**落地效果**：某实现 PR 归档时把 spec delta 合并进 `openspec/specs/web-ui/spec.md` 并追加 `current_spec_synced` 事件 ⇒ 本地 checker 与 witnessloop **同时绿**，零额外动作（两侧判据语义等价，列上不产生新增义务）。

### U4（原 Q4）: 测试执行点只填 `uv run --extra dev pytest -q`

**裁定**：`.github/witnessloop-tests.txt` 的内容就是这一条命令：`uv run --extra dev pytest -q`。**必须带 `--extra dev`**——`pytest` 在 `[project.optional-dependencies].dev`（`pyproject.toml:48-55`），裸 `uv run pytest` 在干净 runner 里报 `Failed to spawn: pytest`（实测）。

**明确不做的（边界）**：`ci.yml:62-74` 那条「默认编码警告当错误」的变体**不进**执行点；`openspec validate` 与 artifact checker 也不进。理由三条：① 一行里串两条命令，红的时候要人肉分辨哪段挂的（失败归因变差）；② 收益有限——`dev` extra 含 `playwright` / `swebench`，浏览器用例仍因缺 `playwright install chromium` 而 skip，执行点**本来就不覆盖全部信号面**；③ 这三条在本仓 `validate` job 里**继续跑**，阶段 A 不丢信号。

**已知边界（阶段 B 报告必须记，tasks B.7）**：执行点 = 主回归面；浏览器用例、编码 warn-as-error 门、`openspec validate`、artifact checker 四条**不在**执行点内，但都在本仓 `validate` job 里照跑。

### U5（原 Q5）: 阶段 A/B 两套 manifest 并存；schema 统一留到阶段 C 之后

**裁定**：阶段 A/B **不迁 schema**（不改 `agent/workflow/review_manifest.py`）；本仓形态 `reviews/<phase>-review-manifest.json` 继续喂本地 checker，witnessloop 形态 `reviews/<stage>.manifest.json` 由 `witnessloop manifest build` 产出；`review_manifest_glob` 保持 witnessloop 默认 `reviews/*.manifest.json`。**schema 统一是阶段 C 之后的独立 change**（tasks **N.4**）。

**代价（接受）**：影子期长期并存两份 manifest；且 grill / grill-adversarial 两条线是**从零新增**（本仓 75 份 manifest 的 `phase` 只有 `building`(74) / `design`(1)，这两个 stage 从来没有过 manifest）。完整理由与字段对照表见 Decision 2。

### U6（原 Q6）: `protected_paths` 补齐三条文档路径

**裁定**：`protected_paths` = `["openspec/specs/**", ".witnessloop/**", "docs/known-issues.md", "docs/known-debt.md", "docs/openspec-change-backlog.md"]`。

**否决的备选**：不补，同时把 U1 的事件类型表砍到只留 `current_spec_synced`——否则 `backlog_updated` / `protected_artifact_explained` **没有对应的受保护路径消费**，是死配置（`_protected_writes` 先按 `protected_paths` 命中、才查事件）。

**落地效果**：某 PR 改 `docs/known-debt.md` 并带 `protected_artifact_explained` 事件 ⇒ 本地 checker 与 witnessloop 同时绿；且「旧 checker 下掉后这三条无人管」的静默缺口被提前堵住（与 R3 同构）。

### U7（原 Q7）: 等 witnessloop #20 修谓词，本仓零改动

**裁定**：**不改本仓 grill 记录格式、不回填 62 份归档**；等上游修 `_SOURCE_RE`（已立 witnessloop [#20](https://github.com/Xingkai98/witnessloop/issues/20)，当前 OPEN）。

**否决的备选**：本仓改记录格式 + 模板（把 `来源:` 写成不被 `**` 包裹）——要动 `.claude/commands/grill.md`（本地、不进 PR、无评审记录）+ 文档规范 + 模板，且要回填 62 份归档 `grill-design.md`，代价远大于收益。

**阶段 A 的已知红（按 U7 订正口径——写准「哪一条红、为什么不挡」）**：阶段 A 里 witnessloop 的 **grill 正文校验根本不会被触发**——默认一份 witnessloop 形态 manifest 都不落（Decision 7）⇒ `stage_manifest_findings_in_change` 找不到 `stage=grill` 的 manifest，先报的是「无 stage=grill 的 manifest」，**正文那组判据到不了**。⇒ 阶段 A 的已知红是「**缺 manifest**」这一类，**不是**「`来源:` 谓词判红」。实测本 change 自身（隔离副本、按 Decision 1 的 policy 跑 `check`）：`缺少 review manifest` + `无 stage=grill 的 manifest` 两条（`code_hits` 为空 ⇒ `grill-adversarial` / `building` 两条不触发）；阶段 A 落地前还会多一条「测试执行点缺失」，执行点文件写入后即消。

这组红：
- **性质**：证据尚未产出（阶段 A 是影子期，本就不该产 witnessloop 形态证据），**不是**配置错误；
- **不挡合入**：阶段 A 的 `gate / check` **不进 required**（Decision 4）⇒ 红只出现在 job 日志里；
- **不挡归档**：本文档与 tasks 都不要求产出 witnessloop 形态 manifest；
- **不据此放宽任何判据**（本仓 checker 与 witnessloop 都不动）。

**`来源:` 谓词不兼容是「将来」的前置，不是阶段 A 的阻塞**：它只在**真的去建 witnessloop 形态 grill manifest 之后**才会遇到（那时才会去跑正文判据：本 change 自己的报告 **7 块全缺 ⇒ 7 条**）。因此 [#20](https://github.com/Xingkai98/witnessloop/issues/20) 列为**建 witnessloop 形态 grill 证据之前**的前置条件（阶段 B/C 会先碰到），而不是阶段 A 的门。这是「等上游修」这一裁定的**准确事实描述**，裁定本身不变。

**后续**：上游 [#20](https://github.com/Xingkai98/witnessloop/issues/20) 关闭后，阶段 B/C 复跑确认该组红消失；若上游长期不修，再由那时的停轮项决定是否走「本仓改格式」那条路（tasks **N.7**）。

## Risks / Trade-offs

- **[R1] 影子期的「假安全感」**：`gate / check` 在 CI 里是绿的（或红的）但**不拦合入** ⇒ 有人可能误以为它已经在管。**Mitigation**：阶段 A 的 PR 描述与 `docs/development-guide.md` 新节都显式写明「本 job 阶段 A 不 required，只跑不拦」；阶段 B 报告里也重申。
- **[R2] policy seed 写错的暴露延迟**：`--policy` 只做「可解析为 JSON 对象」的轻校验，**语义合法性由 `check` 兜底**（witnessloop `cli.py:49-54`）⇒ seed 写错不会在 `init` 时报错，只会在第一次跑 `check` 时暴露。**Mitigation**：阶段 A 的第一个验收项就是**在本分支 PR 上跑一次 `check` 并读取 findings**，而不是等「真需求」时才第一次跑。
- **[R3] 本地守卫能力退步**：asterwynd 解析 Bash 命令（`workflow_guard.py`，677 行），witnessloop `guard` 只看 `Write|Edit`（上游 `guardcmd.py:16-17` 自陈）。⇒ 本地拦截面变窄。**Mitigation**：(i) 阶段 A **不下掉**旧守卫，两条并存；(ii) 把退步写进本 proposal 的 Impact Analysis 与阶段 B 报告，作为「真打开」决策的输入；(iii) 真锚始终是 CI required check。
- **[R4] 已知红（两条）**：`add-minimal-tui-runtime-view`（无 `reviews/`）+ **本 change 自己**（缺 witnessloop 形态 manifest，且 `code_hits` 为空）。**Mitigation**：阶段 A 不勾 required ⇒ 不造成实际拦截；两条都如实列进阶段 A/B 报告；**不为它们放宽判据**；**默认一份 witnessloop 形态 manifest 都不落**（Decision 7；样板方案已撤销，若确要落见 Z.7 的条件式）。阶段 C 决策时必须把 K1 的收尾一并考虑。
- **[R5] `.claude/` 被 gitignore ⇒ plugin 装/卸没有评审与回滚记录**（`.gitignore:9`）。**Mitigation**：把 plugin 安装步骤写进 tasks 与 `docs/development-guide.md`（**文档在版本控制里**），使「本地动作」至少有可复现的书面记录；plugin 来自 witnessloop 仓的 `plugin/` 目录（`commands/` + `hooks/`），升级靠重装。
- **[R6] 上游 reusable workflow 的版本面**：caller 钉 `@v1`（witnessloop `constants.py:11 DEFAULT_GATE_REF`），`@v1` 是**移动 tag** ⇒ 上游 `v1` 分支前进会改变本仓门禁行为。**Mitigation**：登记为后续观察项；若需要钉死，走 `--gate-ref` 指向 commit sha（**本阶段不引入**，避免过早固化）。**建议主 session 复核这条口径。**
- **[R7] 两组门禁的判定漂移**：并存期本地 checker 与 witnessloop **各判各的**，可能出现「一边绿一边红」。**Mitigation**：这是并存的**预期形态**（不是缺陷）——阶段 B 的报告要把所有分叉逐条列出，它们正是「迁移清单」的输入。
- **[R8] 阶段 B 的「真实小需求」选得不好**：若选的需求太琐碎，跑不出 intake 的真实摩擦。**Mitigation**：阶段 B 的任务里给出选择标准（必须触达 `require_change_for`、必须能产生 spec delta 或受保护写入、规模在一到两个文件）。
- **[R9] 两个 PreToolUse 守卫并存的未知面**（Decision 8）：真未实测的只有**两项**——CC 对「settings hook + plugin hook 同时匹配」的**合并/串行语义**与**报错归属**；且必须**在主 checkout 与 building worktree 各测一次**（worktree 下没有 `.claude/`）。**Mitigation**：写成阶段 A 的强制实测项（A.1.1 判据 + A.4.5），结果落阶段 A/B 报告；**不靠推理填坑**。命名空间冲突**可静态判定**（`plugin.json` 的 `name: witnessloop`），不留作未知面。
- **[R9b] `guard.sh` 的前置条件（比原判「版本可能漂移」更硬）**：`guard.sh:32` 调 PATH 上的裸 `witnessloop`，退出码映射是「1 → 拦，其余 → 放行」（`:38-41`）⇒ PATH 上若是**没有 `guard` 子命令**的旧版 CLI，**整个 guard 静默空转**（实测本机 0.1.0 即是）。**Mitigation**：阶段 A 的前置核验 `command -v witnessloop` + `witnessloop --help` 含 `guard`；A.4.5 / B.5 不做这条前置就会把「放行」误读成「证据完备」。注意 design 原有的「验证一律用 `uv run witnessloop`」**覆盖不到 `guard.sh`**。
- **[R10] 本 change 会证伪新建的当前规格**：`openspec/specs/dev-workflow-gate/spec.md` 现有两条负向 Requirement（明禁 `.witnessloop/policy.json` 与「`.github/workflows/` 下只有 ci.yml」）会被阶段 A 的实现**直接证伪**，而 delta 原本只有 `## ADDED`、Z.2 原本只写「合并 ADDED」⇒ 占位 Requirement 会**存活**并自相矛盾。**Mitigation**：照 `platform-gate` 先例（实现 commit `f7e912b` 明确「同步 current spec（**覆盖占位**）」）——delta 增加 `## REMOVED Requirements`，tasks 的 Z.2 改为「**覆盖重写**当前规格」。
- **[R11] 阶段 B 结构性跑不绿**（**grill 给的缓解已失效，须换路**）：grill 的缓解是「阶段 B 用 `manifest build` 补产 witnessloop 形态 manifest ⇒ 拿到绿的一侧作对照」。**对抗轮实测证伪**：manifest 只是必要条件，不是充分条件——**`来源:` 谓词让 grill stage 结构性判红**（本 change 自己的报告 7/7 条缺 `来源:`；且补齐 `## User Confirmation` 后仍报 7 条）。⇒ **补了 manifest 也拿不到绿**。
  **Mitigation（修正后）**：① 阶段 B 的「绿的一侧」**不再建立在 grill stage 上**——改以「`check` 的 findings 从『缺证据』类收敛为『正文格式』类」作为可测的进步指标；② grill stage 的绿**阻塞在 U7**（等上游 [#20](https://github.com/Xingkai98/witnessloop/issues/20) 或本仓改写法）；③ 阶段 B 报告必须明确写「哪些红是配置问题、哪些红是已知的工具不兼容」，否则「值不值得真打开」会被误读。
- **[R12] 只落部分 manifest 会激活孤儿规则**（对抗轮实测）：glob 匹配 0 份时 `check` 早退（现状 2 条红）；落**任意一份** witnessloop 形态 manifest 后，`reviews/**/*.md` 里每份未绑定报告都判孤儿（2 → 14 → 16）。**Mitigation**：**要么给每份报告都建 manifest，要么一份都别落**（Decision 2 的操作约束 / Decision 7 的默认处置 / tasks A.5.6）。
- **[R13] 证据的 stale 顺序约束**（对抗轮实测）：`_check_git_span` 只允许 `head_sha` 之后出现在 `stale_exempt_paths`（`.witnessloop/**`、`<changes_root>/*/reviews/**`、`<changes_root>/*/workflow-events.jsonl`、`archive/**`）内的改动。⇒ 本 change 的 Z.1（改 `docs/development-guide.md`）与 **Z.2（覆盖重写 `openspec/specs/**`）都是非证据路径** ⇒ **任何在其之前产出的 manifest 到 PR 时必然 stale**（实测：manifest 后再提交一处 `agent/probe.py` 即报 `审阅的是旧 revision`）。**Mitigation**：证据一律**在所有内容提交之后**重建（tasks A.5.6 与收尾顺序已写死）。

## Testing Strategy

本 change **不新增 Python 测试**——它的「测试」面就是**在新流程上跑一个真实需求**。分层如下：

- **阶段 A 的机械验收**（不依赖真实需求）：
  1. `witnessloop init --dry-run --policy <seed>` 在目标 worktree 上打印的待建文件清单 = 4 个新文件（`.witnessloop/policy.json` / `.witnessloop/init-manifest.json` / `.github/workflows/witnessloop.yml` / `.github/witnessloop-tests.txt`），**与既有文件零冲突**（本仓 `.github/workflows/` 下只有 `ci.yml`）。
  2. 落盘后本地跑 `witnessloop check`（或 `uv run witnessloop check --root .`）并**逐条读 findings**：确认 `building` / `grill-adversarial` 两条判定**确实被触发**（这正是 R2 的第一次暴露点；若 policy 的 `require_change_for` 没生效，这两条会**静默消失**——用本分支自身的 diff 当样本即可验证）。
  3. 本分支 PR 的 CI 上确认出现 `gate / check` job 并**跑出结果**。
  4. **回归确认**：本分支 PR 的 CI 上 `validate` / `benchmark-gate` 行为**逐字节不变**；`gh api …/protection` 的 `contexts` 仍是 `["validate", "benchmark-gate"]`。
  5. **双守卫实测**（Decision 8 / R9）：先做前置核验（`command -v witnessloop` + `--help` 含 `guard`，否则 guard 静默空转），再对一条 `agent/**` 路径触发一次 `Write`，记录**两个 hook 是否都执行、提示归属哪个守卫**——**必须在主 checkout 与 building worktree 各做一次**（worktree 下没有 `.claude/`，只能观察到 plugin 那一个）。命令命名空间冲突可由 `plugin.json` 静态判定，顺手确认即可。
  6. **`reviews/` 的一致状态**（替代原判据⑦「第一次出现绿的一侧」——**该断言已被对抗轮证伪**）：本 change 的 `reviews/` 下**要么每份报告都有 manifest，要么一份都没有**；默认选后者（K2 保持 2 条红）。若落样板，必须同时满足「每份都建 + 在所有内容提交之后重建 + 明确写下它不是绿的一侧」三条（tasks A.5.6）。
- **阶段 A 的负向验收（必做）**：临时把 policy 换成出厂默认（`require_change_for` 不覆盖 `agent/**`）跑一次 `check`，**确认 `building` / `grill-adversarial` 判定消失**——这条用**证伪**证明「定制 policy 是必要的」，而不是靠推理。
- **阶段 B 的真实需求验收**：按「选择标准」挑一个真实小需求，走完整流程（`guard` 拦 → 写码 → 本仓 `/review-loop` 产审阅证据 → **额外跑 `witnessloop manifest build` 产 witnessloop 形态 manifest** → `check` 核 → 测试执行点在 CI 里跑），产出验收报告：findings 清单、与本地 checker 的分叉清单、已知红清单（含 K1/K2）、体验摩擦清单、Q4 决定的「执行点覆盖到/覆盖不到什么」的已知边界，以及**按成因分类的红清单**（配置问题 vs 工具不兼容，如 Q7 的 `来源:` 谓词）。**注意**：`manifest build` 的调用必须发生在**所有内容提交之后**（R13 的 stale 约束），且**由人在本地跑**——`gate.yml` 只做 `check`、**不产证据**。
- **收尾的机械验收**：归档 move **单独成 commit**（纯 rename），确认 `check` 对归档 move 判 `通过 ✓`（Decision 3 的配套约束 / R3）。
- **不做的事**：不为本 change 写 witnessloop 侧的测试（上游自己的测试覆盖它）；不新增 pytest 用例；不改现有测试。

## Impact Analysis

- **新增（阶段 A 产物）**：`.witnessloop/policy.json`、`.witnessloop/init-manifest.json`、`.github/workflows/witnessloop.yml`、`.github/witnessloop-tests.txt`。**注意：阶段 A 默认 `reviews/` 下一份 witnessloop 形态 manifest 都不落**（Decision 7 / tasks A.5.6）——落它会让孤儿规则被激活、红数从 2 条涨到 14/16 条。仅在满足 Decision 7 第 4 条的三条件（每份报告都建 + 所有内容提交之后重建 + 写明它不是绿的一侧）时才落，见 tasks **Z.7** 的顺序约束。
- **修改**：`docs/development-guide.md`（新增「witnessloop 影子接入」一节）；`docs/openspec-change-backlog.md`（登记本 change）；`openspec/specs/dev-workflow-gate/spec.md`（阶段 A 结束时**覆盖重写**，退休两条占位 Requirement，见 R10）。
- **明确不改**：`AGENTS.md`（流程段留阶段 C）、`.github/workflows/ci.yml`、`scripts/**`、`agent/**`（含 `agent/workflow/review_manifest.py`——schema 统一不是本阶段的事，见 Decision 2）、branch protection。
- **回退**：`witnessloop uninit`（依 `init-manifest.json` 的 hash 台账精确回滚）或手工删 `.witnessloop/` + `.github/workflows/witnessloop.yml` + `.github/witnessloop-tests.txt`。本地 plugin 单独卸。
