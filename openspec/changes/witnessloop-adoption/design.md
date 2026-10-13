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

6. **grill 报告正文判据不兼容**：witnessloop 的 `_SOURCE_RE` **不认加粗的 `- **来源**: x`**，而本仓记录通篇如此 ⇒ **grill stage 结构性不可能判绿**（Decision 2 末段、**Open Question Q7**、R11）。连带地，「样板 manifest = 验收里第一次绿的一侧」（B1）与「manifest 一建就 stale」（B3）两条也已按实测改写（Decision 7 / R13）。

## Goals / Non-Goals

**Goals:**

- 在一条分支上落齐 witnessloop 的接入产物：定制 policy + caller workflow + 测试执行点 + （本地）CC plugin。
- 让 witnessloop 的 `gate / check` job 在 CI 里**跑起来**且**不拦任何合入**。
- 用一个**真实小需求**在新流程上跑一遍，拿到「值不值得真打开」的判断依据。
- 把三条项目配置决策**摆到台面上**（每条带推荐值 + 具体例子），由用户拍板。
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

**落地形态（policy 的目标内容，具体值取决于 Open Questions 的答复）**：

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
- `protected_paths` **必须与 Q1 的事件类型表配套**：只列 `openspec/specs/**` + `.witnessloop/**`（= witnessloop 出厂默认）而把 `backlog_updated` / `protected_artifact_explained` 填进事件类型表，会让这两个类型成为**死配置**（列了也没有对应的受保护路径消费它，见 `checkcmd.py:206-215`：`_protected_writes` 先按 `protected_paths` 命中、才查事件）。⇒ 上面把 asterwynd 现有的三条受保护文档路径一并列入（最终取值待 **Q6** 拍板）。

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

**文件名无碍、但正文判据不同构（对抗轮实测证伪了原「同构」判断）**：`report_path` 是自由字段，所以本仓的 `reviews/grill-design.md` **文件名无碍** ✓。但 witnessloop 对 grill 报告**正文**的判据与本仓写法**系统性不兼容**——`src/witnessloop/evidence.py:33` 的 `_SOURCE_RE = re.compile(r"来源\s*[:：]")` 要求「来源」后**直接**接冒号，**不接受 `- **来源**: x` 这种加粗写法**（实测：裸写法命中、加粗不命中）；而本仓记录**通篇是加粗**（本 change 自己的 `grill-design.md` 有 12 处这种行 ⇒ 7/7 条 Confirmed Decision 全判「缺 `来源:`」）。⇒ **grill stage 按现有报告格式结构性不可能判绿**，这是本 change 的**已知阻塞/前置依赖**，见 **Open Question Q7**（已去 witnessloop 立 issue [#20](https://github.com/Xingkai98/witnessloop/issues/20)）。

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
   ⇒ **K2 的红数不是「2 条」，而是随「落了几份 manifest」变化的 2 → 14 → 16**。样板**不会**带来绿：grill stage 因 `来源:` 谓词（Q7）**结构性无法判绿**。
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
  - manifest 差异的归因——**已定：不是 glob，是 schema**；处置=**两套并存、schema 统一延后到阶段 C 之后**（Decision 2；grill 实测证伪了原「机械修正」定性，对抗轮进一步钉准红数——glob 匹配 0 份时 `check` 早退、现状 **2 条红**，落任意一份 witnessloop 形态 manifest 后 **14 → 16 条**。对应 grill 的 Q5/OQ2，其推荐值保留在 **Open Question Q5**）。
  - 归档目录是否列 `protected_paths`——**已定：不列**（Decision 3，实测 12 条假红；grill 进一步实测出**归档 move 必须是独立纯改名提交**，见 tasks 的运维约束）。
  - 阶段划分与「只跑不拦」的实现方式——**已定**（Decision 4）。
  - 哪些留本地——**已定**（Decision 5）。
  - `handoff.json` 是否混入——**已定：不混入**（Decision 6）。
  - 已知红的范围与处置——**已定：含本 change 自己，如实记录 + 不放宽；本 change 自己补一份 witnessloop 形态 grill manifest 当样板**（Decision 7）。
  - 两个 PreToolUse 守卫并存——**姿态已定：两条都保留、未知面实测**（Decision 8）。
  - **对抗轮（`reviews/grill-adversarial-v1.md`）提出的 7 条阻塞全部已处置**：B1/B3（样板不是绿的一侧 + stale 顺序）→ Decision 7 / R11 / R13；B2（`来源:` 谓词不兼容）→ **Open Question Q7** + witnessloop issue [#20](https://github.com/Xingkai98/witnessloop/issues/20)；B4（Q4 推荐值不可执行）→ Q4 改为 `uv run --extra dev pytest -q`；B5（B/C/N 节未勾未标）→ 加 `(post-merge)`；B6（Decision 8 定性错 + 实测点）→ Decision 8 / R9 / R9b 重写；B7（Q5 停轮口径）→ Q5 **撤回「已定案」，改为停轮项**。
- Options considered:
  - **A. 直接替换**：接入的同时下掉旧 checker 并把 `gate / check` 勾成 required。**否决**：会打开「一段没有任何强制（或换成没验证过的强制）的窗口」，且不可逆动作发生在验证之前。
  - **B. 影子接入（本方案）**：只跑不拦 → 真需求验证 → 再真打开。
  - **C. 出厂 policy 直接接入**：**否决**——`building` / `grill-adversarial` 门禁静默不触发，接入名存实亡。
  - **D. 阶段 A 一并统一 manifest schema**（改 `agent/workflow/review_manifest.py`）：**否决**——会把影子接入的 diff 从 `docs`+ 4 个新文件扩到 `agent/**` 与 2874 行测试，无法独立评估影子接入本身；且与「阶段 A 一行不改旧件」冲突。改成 Decision 2 的「两套并存」。
  - **E. 阶段 A 直接下掉 `scripts/workflow_guard.py`**（消除双守卫）：**否决**——属「下掉旧件」，本 change 非目标；且双守卫的真实行为还没实测（Decision 8）。
- Rejected alternatives:
  - 选 A / C / D / E 的理由如上。另否决「在本 change 内顺手清理 `handoff.json`」（见 Decision 6，会污染影子接入的 diff 可评估性）。
- Final confirmations:
  - 开发前必须使用 `grilling` 做设计追问（本轮的独立 grill 已产出 `reviews/grill-design.md`），把 `## Open Questions` 逐项抛给用户并等待明确答复；答复记录进 `reviews/grill-design.md` 的 `## User Confirmation`。**本 change 的 `## Open Questions` 未全部确认前不得写实现产物**（不跑 `init`、不建 caller、不装 plugin）。
  - 按 `grill-flow-hardening`（issue #298）在停轮前跑设计阶段审阅闭环，产出 `reviews/grill-adversarial.md`。
- Remaining risks:
  - `--policy` 的语义合法性由 `check` 兜底 ⇒ seed 写错只会在**跑 `check` 时**暴露，不会在 `init` 时报错（见 Risks R2）。
  - 双守卫的**合并语义与报错归属**两项未实测（Decision 8，命名空间可静态判定）——必须在阶段 A 的验收里补实测项，且**两棵树各测一次**。
  - **grill stage 结构性判红**（Q7 / R11）：本仓 grill 记录在 witnessloop 的 `来源:` 谓词下**不可通过**，阶段 B 拿不到 grill 的绿。这条**阻塞在用户对 Q7 的拍板**上。

## Open Questions

> **停轮项共 7 条**：Q1 / Q2 / Q3（立项时提出）+ Q4 / Q5 / Q6（独立 grill `reviews/grill-design.md` 补充）+ **Q7**（对抗轮补充，`reviews/grill-adversarial-v1.md` 的 B2）。
>
> ⚠️ **Q5 必须停轮**：整合 grill 时曾把 Q5 记为「已定案、不停轮」，**已按对抗轮实测撤回**——本仓 checker 要求 `reviews/grill-design.md` 的 **每一个** Open Question 都有 `## User Confirmation` 记录（`_unconfirmed_open_questions`，归档点门以 `assume_implemented=True` 求值），而 Q5 在 `grill-design.md` 的 `## Open Questions` 里是列表项 ⇒ **Q5 不确认，归档必红**，与 witnessloop 无关。
>
> 这些**多数是项目配置/取舍**决策（Q7 是工具侧不兼容的处置面）：更正后的 issue #305 明确「三条决策全部是『项目配置』，没有一条需要改 witnessloop 的代码或逻辑」；grill 追加的两条同理。每条附推荐值与**具体例子**，请逐条拍板。推荐值**不是**已确认结论。

### Q1: 解释事件类型名的映射怎么定？

**背景**：机制**已经存在**——asterwynd 有 78 份 `workflow-events.jsonl`，事件字段（`event_type` / `artifact_path` / `reason` / `approved_by`）与 witnessloop **逐字对得上**，多出的 `schema` / `seq` / `change_id` 是 witnessloop 忽略的字段。所以这不是「要不要引入新仪式」，只是**把现有的类型名填进 witnessloop 的 policy**。

**选项**：
- (a) **把 asterwynd 现有类型名写进 policy**：`protected_write_event_types = ["current_spec_synced", "backlog_updated", "change_archived", "protected_artifact_explained"]`（多类型，现状零改动）。
- (b) **把类型名统一成 witnessloop 默认的单一 `protected_path_write`**：要改 78 份历史事件日志 + `flow-policy.json` + 本地 checker 的规则表。

**推荐：(a)**。理由：(b) 要动 78 份历史日志与受保护路径规则表（`scripts/flow-policy.json` 是 `cli_written` 治理档），收益只是「类型名好看一点」，代价是把「接入」变成「重构历史证据」。

**具体例子**：某次实现 PR 同步了当前规格，`openspec/specs/agent-runtime/spec.md` 被改写。**选 (a)** 时，该 change 的 `workflow-events.jsonl` 里这条事件

```json
{"schema":"workflow-event/v1","seq":"7","event_type":"current_spec_synced",
 "change_id":"fix-issue-251-sse-done-warning",
 "artifact_path":"openspec/specs/agent-runtime/spec.md","reason":"…","approved_by":"human"}
```

**两边都过**——本地 checker 认 `current_spec_synced`（`scripts/flow-policy.json`），witnessloop 也认（因为 policy 里列了它）。**选 (b)** 时，同一次写会被 witnessloop 判红（`event_type` 不在 `["protected_path_write"]` 里），而你必须把它改写成 `protected_path_write` 才能过——**同时**还要在本地 checker 那边接受一个不在 `flow-policy.json` 里的类型名，或者反过来改 `flow-policy.json`。

### Q2: `require_change_for` 的最终面是什么？`benchmarks/**` 要不要纳入？

**背景**：这个字段是「**什么算代码**」的**唯一**口径——`_require_change`（改代码必须挂 change 目录）、`building` 门禁、`grill-adversarial` 门禁**三者共用它**（witnessloop `checkcmd.py:169`）。纳入 = 改动必须挂 change 目录且必须补两类审阅证据。

**选项**：
- (a) **`["agent/**", "scripts/**", "web/**"]`**（推荐）：覆盖本仓三块真实代码面。
- (b) (a) + **`"benchmarks/**"`**：benchmark 数据与任务目录也纳入。

**推荐：(a)**。理由：`benchmarks/**` 有 345 个文件，其中大量是**任务数据与结果 fixture**，不是产品代码；纳入意味着「改一个 benchmark fixture 也要挂一个 change 目录 + 两类审阅证据」，大概率**过重**，会把 change 目录变成噪声。

**具体例子**：假设要修一条 benchmark 任务的坐标错误（`benchmarks/tasks/xxx/task.yaml` 里一行 path 写错了）。
- **选 (a)**：这个 PR 只改 `benchmarks/**` ⇒ `code_hits` 为空 ⇒ 不要求 change 目录、不要求 `building` / `grill-adversarial` 证据 ⇒ 直接提 PR 修掉，走现有 `benchmark-gate` 兜。
- **选 (b)**：同一个 PR 会被判「触达 `require_change_for`」⇒ 必须挂一个 `openspec/changes/<id>/` 目录、写 proposal/design/tasks/spec delta、跑 grill + grill-adversarial + building 三份审阅证据才能过。**这就是「过重」的具体样子。**

**另一面**：如果 `benchmarks/` 里也有真正会被 agent 改的**运行时代码**（runner / verifier 逻辑），(a) 会漏掉它们。**建议答复时说明：若 `benchmarks/` 下有需要门禁保护的运行时逻辑，可退到「`benchmarks/**/*.py` 之类的窄模式」而不是整目录**——这条取舍请你定。

### Q3: `openspec/specs/**` 是否列为 `protected_paths`？

**背景**：这与「本地 checker 是否继续管 spec 同步」**联动**。现状：`scripts/flow-policy.json` 里 `openspec/specs/` 是 `event_explained` 档，事件类型 `current_spec_synced`；本地 checker 的 `check_protected_path_explanations`（`check_openspec_artifacts.py:1173`）在管。witnessloop 的出厂 policy 默认把 `openspec/specs/**` 列为 protected。

**选项**：
- (a) **列为 protected**（witnessloop 侧也管）：两侧同时管，spec 写入必须有解释事件。与 `require_change_for` 独立——即使 Q2 选 (a) 漏掉的路径，改 spec 仍会被拦。
- (b) **不列**（witnessloop 侧不管，交给本地 checker）：**现阶段零风险**，因为本地 checker 仍在跑。

**推荐：(a)**。理由：**冗余但一致**——witnessloop 的判定与本地 checker 的判定在 spec 这条线上语义等价（都要求 `current_spec_synced` 类解释事件），列上不会产生新增义务，只是把这条线也搬进了新门禁；而 (b) 会让「迁移完成后本地 checker 一旦下掉，spec 就没人管了」——**这正是后续 change 要避免的静默缺口**。若 Q1 选 (b)（类型名统一），则 (a) 的配置值要跟着改。

**具体例子**：某实现 PR 归档时把 spec delta 合并进 `openspec/specs/web-ui/spec.md`，并在该 change 的 `workflow-events.jsonl` 里追加了一条 `event_type: "current_spec_synced"`、`artifact_path: "openspec/specs/web-ui/spec.md"` 的事件。
- **选 (a)**：本地 checker 绿（认这条事件，`scripts/flow-policy.json` 的 `openspec/specs/` 规则）；witnessloop 也绿（policy 的 `protected_paths` 含 `openspec/specs/**`，`protected_write_event_types` 含 `current_spec_synced`）。**两边同时绿，零额外动作。**
- **选 (b)**：结果**看起来一样**（本地 checker 照样绿），区别只在「本地 checker 下掉之后」——那时 (b) 的仓库在 spec 这条线上**没有任何强制**，而 (a) 的仓库还有 witnessloop 那条。

### Q4: `--test-command` 的测试执行点填什么命令？

**背景**：本仓 CI 的测试口径是**四件事**，不是一条命令——`uv run pytest -q`（`.github/workflows/ci.yml:48`）+ 编码 warn-as-error 变体（`:62-74`，`-W error::EncodingWarning:agent/web/benchmarks`，只跑 5 个文件）+ `openspec validate --strict`（`:77`）+ `check_openspec_artifacts.py`（`:88`）。而 witnessloop 的执行点是**一行**、在**另一个 job** 里跑（`sh -c "$CMD"`，witnessloop `.github/workflows/gate.yml:100`），那个 job 只做 checkout + `setup-uv`（`gate.yml:40-45`）——**没有** `uv sync --extra dev`、**没有** `playwright install chromium`。`tasks.md` A.3.1 原只写「取本仓现有 CI 的测试口径」，不够具体。

**⚠️ 原推荐值 (a) 不可执行（对抗轮实测证伪）**：`pytest` 在 `[project.optional-dependencies].dev`（`pyproject.toml:48-55`），而 `uv run` 只装**默认**依赖。在模拟 runner 的干净环境（仅 uv 在 PATH、无全局 pytest）实测：

```
$ uv run --project /tmp/wl-sim pytest -q --collect-only
Installed 77 packages in 1.74s
error: Failed to spawn: `pytest`   ← exit=2
```

本机之所以「看起来能跑」，是因为 PATH 上有 `/home/happy/.local/bin/pytest`（pytest 9.1.1）⇒ `uv run pytest` 回落到了它，而在项目环境里 `import pytest` 反而 `ModuleNotFoundError`。`gate.yml:40-45` 的 job 只有 checkout + `setup-uv`，**没有** `uv sync --extra dev`。

**选项（修正后）**：
- **(a′) `uv run --extra dev pytest -q`**（实测可用：116 包）。
- (b′) (a′) + 把编码变体串进去（`PYTHONWARNDEFAULTENCODING=1 uv run --extra dev pytest -q -W "error::EncodingWarning:agent" …`）。
- (c) 不启用执行点（`tests.disabled: true`）——**否决**：等于放弃 witnessloop 的测试门，与接入目的背离。

**推荐：(a′)**，一条命令、`--extra dev` 保证 pytest 装得上。**编码变体不并入**，理由三条：① 失败归因——一行里串两条命令，红的时候要人肉分辨是哪一段挂的；② 收益有限——`dev` extra 里含 `playwright` / `swebench`，装了之后浏览器用例仍因缺 `playwright install chromium` 而 skip，说明执行点**本来就不覆盖全部信号面**，多串一条并不能改变这个性质；③ 编码门在本仓 `validate` job 里**继续跑**，阶段 A 不丢信号。若用户希望执行点信号更全，可选 (b′)，代价如上。

**具体例子**：阶段 A 的 PR 里 `gate / check` job 跑 `uv run --extra dev pytest -q`。`tests/web_tests/test_workflow_graph_browser.py` 这类用例因缺 chromium 而**静默 skip**——但同一 PR 的 `validate` job 里（`.github/workflows/ci.yml:45` 有 `playwright install --with-deps chromium`）**照样真跑**。⇒ 已知边界是「witnessloop 那条不覆盖浏览器面与编码门」，写进阶段 B 报告（tasks B.7）。

### Q5（grill 编号）：manifest schema 迁移归谁？—— **必须停轮确认**

**背景**：`check` 认 `stage` / `author_run_id` / `report_path`，而本仓生成器写 `phase` 且缺后两个字段（Decision 2）⇒ 不改生成器，用本仓工具链产的 manifest **永远过不了** `check`。

**⚠️ 为什么它必须停轮（撤回整合时的「已定案、不停轮」）**：本仓 checker 要求 `grill-design.md` 的 `## Open Questions` 里**每一个**编号都有 `## User Confirmation` 记录（`_unconfirmed_open_questions`）；归档点门以 `assume_implemented=True` 求值 ⇒ **Q5 不写确认记录，归档必红**。这与 witnessloop 无关，是本仓自己的门。实测：把确认记录只写 Q1–Q4+Q6，本仓侧抽出 `['Q5']` 未确认；witnessloop 侧也多一条 `Open Question Q5 未经用户确认`。

**推荐（保留原推荐值）：阶段 C 之后的独立 change**。理由：改生成器要连带改它 2874 行的测试体量，且与「阶段 A 一行不改旧件」冲突；把 schema 统一显式排到阶段 C 之后，两条陈述就自洽了（**不迁 schema，所以不必动 `agent/workflow/review_manifest.py`**）。完整理由与字段对照表见 **Decision 2**。

**具体例子**：阶段 B 的真实小需求 change 里，`/review-loop` 仍然只产 `reviews/building-review-manifest.json`（`phase: "building"`）给本地 checker；**额外**跑 `uv run witnessloop manifest build --change <id> --stage building --report reviews/building-review.md` 产出 `reviews/building.manifest.json` 给 witnessloop。两条证据、两个消费者，互不干扰。⇒ 请确认：接受「影子期长期并存两份 manifest、schema 统一推迟」这个代价，还是宁可现在就改生成器。

### Q6: `protected_paths` 要不要补齐 asterwynd 现有的受保护集？

**背景**：Decision 1 的基线 policy 里，`protected_paths` 若照抄 witnessloop 出厂默认（只有 `openspec/specs/**` + `.witnessloop/**`），就会**缺**本仓现有的三条受保护文档路径（`docs/known-issues.md` / `docs/known-debt.md` / `docs/openspec-change-backlog.md`）⇒ Q1 推荐里填的 `backlog_updated` / `protected_artifact_explained` 两个事件类型**没有对应的受保护路径来消费**，是**死配置**。

**选项**：
- (a) **补齐**三条路径（Decision 1 基线已按此写）。
- (b) **不补**，同时把 Q1 的事件类型表砍到只留 `current_spec_synced`（否则留死配置误导后续读者）。

**推荐：(a) 补齐**。理由：与 Q3 推荐 (a) 的理由**同构**（「冗余但一致」，阶段 A 代价为零、堵住「旧 checker 下掉后这三条无人管」的静默缺口）。

**具体例子**：某 PR 改 `docs/known-debt.md`（本仓现为 `event_explained` 档，需 `protected_artifact_explained` 事件）。**选 (a)**：本地 checker 绿（认这条事件，`scripts/flow-policy.json`）+ witnessloop 也绿（policy 的 `protected_paths` 含该路径、事件类型表含该类型）——两侧一致，零额外动作。**选 (b)**：阶段 A 也没事（旧 checker 仍管），但两侧**分叉**会进阶段 B 的分叉清单，且「本地 checker 下掉后无人管」的缺口被提前埋下；若选 (b) 请**同时**把 Q1 的类型表砍到 `["current_spec_synced"]`，否则那份表里有两项永远不生效。

### Q7: grill 报告正文的 `来源:` 判据不兼容——等上游修，还是本仓改写法？

**背景（对抗轮实测，B2）**：witnessloop `src/witnessloop/evidence.py:33` 的 `_SOURCE_RE = re.compile(r"来源\s*[:：]")` 要求「来源」后**直接**接冒号，**不接受 `- **来源**: x` 的加粗写法**，也不认近期的 `- **证据**: …`。本仓记录**通篇是加粗**：
- 本 change 自己的 `reviews/grill-design.md`：**7/7 条** Confirmed Decision 判「缺 `来源:`」（同一份文件在本仓侧 `_extract_grill_decisions` 抽出 7 条、判定完全正常）；
- 逐份扫描归档里的 `grill-design.md`：**完全无 finding 仅 39 份**，13 份至少一块缺 `来源:`（其中 **11 份是「全部块都缺」**）；
- **趋势在变坏**：`2026-10-03-harness-style-web-transcript`（12/12 缺）、`2026-10-07-grill-flow-hardening`（5/5）、`2026-10-07-tool-result-spill-module`（6/6）、`2026-10-03-foreach-*`（6/6）——**当前正在用的写法基本都判红**。
- 即使把 `## User Confirmation` 补齐、Q1–Q6 全部确认，**仍报 7 条 `缺 来源:`**。

⇒ **grill stage 在现有报告格式下结构性不可能判绿**，阶段 B 拿不到「绿的一侧」（R11 的缓解失效）。

**选项**：
- ① **等 witnessloop 修谓词**（**已立 [#20](https://github.com/Xingkai98/witnessloop/issues/20)**，标题「grill 正文判据的『来源:』谓词不接受加粗写法 ⇒ 用加粗 markdown 的接入方整份记录判红」，当前 OPEN）。
- ② **本仓改记录格式 + 模板**：把 `来源:` 写成不被 `**` 包裹的形式。

**推荐：①**。理由：**零本仓改动**。②要动 `.claude/commands/grill.md`（本地、不进 PR，无评审记录）+ 文档规范 + 模板，且**历史回填代价大**——62 份归档 `grill-design.md` 若都要为了迎合外部谓词重写，收益（让一个外部工具判绿）远不抵代价；何况**上游修谓词是更对的修法**（加粗 markdown 是常见写法，谓词本该容忍）。

**具体例子**：某次 grill 产出 `reviews/grill-design.md`，里面一条决策写成
```
- **决策**: 用 `init --policy` 一次写成
  - **来源**: `src/witnessloop/checkcmd.py:77`
```
- **选 ①**：上游修好谓词后，这条**原样通过**；期间阶段 A/B 明确知道「grill stage 会红 7 条，属已知阻塞」，不误判为配置错误。
- **选 ②**：必须把全仓写法改成 `- 来源: …`（去掉加粗）**并**回填 62 份归档（否则真打开后历史 change 一被触及就红），同时 grill 的产出模板也要改——且**在上游修好之前**，①的用户已经可以正常使用，②的用户白改一轮。

**无论选哪条**，阶段 A 都必须把这条写成 **已知阻塞/前置依赖**（现状：本仓 grill 记录在 witnessloop 判据下**不可通过**），并**不得**据此放宽本仓或 witnessloop 的任何判据。

## Risks / Trade-offs

- **[R1] 影子期的「假安全感」**：`gate / check` 在 CI 里是绿的（或红的）但**不拦合入** ⇒ 有人可能误以为它已经在管。**Mitigation**：阶段 A 的 PR 描述与 `docs/development-guide.md` 新节都显式写明「本 job 阶段 A 不 required，只跑不拦」；阶段 B 报告里也重申。
- **[R2] policy seed 写错的暴露延迟**：`--policy` 只做「可解析为 JSON 对象」的轻校验，**语义合法性由 `check` 兜底**（witnessloop `cli.py:49-54`）⇒ seed 写错不会在 `init` 时报错，只会在第一次跑 `check` 时暴露。**Mitigation**：阶段 A 的第一个验收项就是**在本分支 PR 上跑一次 `check` 并读取 findings**，而不是等「真需求」时才第一次跑。
- **[R3] 本地守卫能力退步**：asterwynd 解析 Bash 命令（`workflow_guard.py`，677 行），witnessloop `guard` 只看 `Write|Edit`（上游 `guardcmd.py:16-17` 自陈）。⇒ 本地拦截面变窄。**Mitigation**：(i) 阶段 A **不下掉**旧守卫，两条并存；(ii) 把退步写进本 proposal 的 Impact Analysis 与阶段 B 报告，作为「真打开」决策的输入；(iii) 真锚始终是 CI required check。
- **[R4] 已知红（两条）**：`add-minimal-tui-runtime-view`（无 `reviews/`）+ **本 change 自己**（缺 witnessloop 形态 manifest，且 `code_hits` 为空）。**Mitigation**：阶段 A 不勾 required ⇒ 不造成实际拦截；两条都如实列进阶段 A/B 报告；**不为它们放宽判据**；本 change 自己补一份 witnessloop 形态的 grill manifest 当样板（Decision 7）。阶段 C 决策时必须把 K1 的收尾一并考虑。
- **[R5] `.claude/` 被 gitignore ⇒ plugin 装/卸没有评审与回滚记录**（`.gitignore:9`）。**Mitigation**：把 plugin 安装步骤写进 tasks 与 `docs/development-guide.md`（**文档在版本控制里**），使「本地动作」至少有可复现的书面记录；plugin 来自 witnessloop 仓的 `plugin/` 目录（`commands/` + `hooks/`），升级靠重装。
- **[R6] 上游 reusable workflow 的版本面**：caller 钉 `@v1`（witnessloop `constants.py:11 DEFAULT_GATE_REF`），`@v1` 是**移动 tag** ⇒ 上游 `v1` 分支前进会改变本仓门禁行为。**Mitigation**：登记为后续观察项；若需要钉死，走 `--gate-ref` 指向 commit sha（**本阶段不引入**，避免过早固化）。**建议主 session 复核这条口径。**
- **[R7] 两组门禁的判定漂移**：并存期本地 checker 与 witnessloop **各判各的**，可能出现「一边绿一边红」。**Mitigation**：这是并存的**预期形态**（不是缺陷）——阶段 B 的报告要把所有分叉逐条列出，它们正是「迁移清单」的输入。
- **[R8] 阶段 B 的「真实小需求」选得不好**：若选的需求太琐碎，跑不出 intake 的真实摩擦。**Mitigation**：阶段 B 的任务里给出选择标准（必须触达 `require_change_for`、必须能产生 spec delta 或受保护写入、规模在一到两个文件）。
- **[R9] 两个 PreToolUse 守卫并存的未知面**（Decision 8）：真未实测的只有**两项**——CC 对「settings hook + plugin hook 同时匹配」的**合并/串行语义**与**报错归属**；且必须**在主 checkout 与 building worktree 各测一次**（worktree 下没有 `.claude/`）。**Mitigation**：写成阶段 A 的强制实测项（A.1.1 判据 + A.4.5），结果落阶段 A/B 报告；**不靠推理填坑**。命名空间冲突**可静态判定**（`plugin.json` 的 `name: witnessloop`），不留作未知面。
- **[R9b] `guard.sh` 的前置条件（比原判「版本可能漂移」更硬）**：`guard.sh:32` 调 PATH 上的裸 `witnessloop`，退出码映射是「1 → 拦，其余 → 放行」（`:38-41`）⇒ PATH 上若是**没有 `guard` 子命令**的旧版 CLI，**整个 guard 静默空转**（实测本机 0.1.0 即是）。**Mitigation**：阶段 A 的前置核验 `command -v witnessloop` + `witnessloop --help` 含 `guard`；A.4.5 / B.5 不做这条前置就会把「放行」误读成「证据完备」。注意 design 原有的「验证一律用 `uv run witnessloop`」**覆盖不到 `guard.sh`**。
- **[R10] 本 change 会证伪新建的当前规格**：`openspec/specs/dev-workflow-gate/spec.md` 现有两条负向 Requirement（明禁 `.witnessloop/policy.json` 与「`.github/workflows/` 下只有 ci.yml」）会被阶段 A 的实现**直接证伪**，而 delta 原本只有 `## ADDED`、Z.2 原本只写「合并 ADDED」⇒ 占位 Requirement 会**存活**并自相矛盾。**Mitigation**：照 `platform-gate` 先例（实现 commit `f7e912b` 明确「同步 current spec（**覆盖占位**）」）——delta 增加 `## REMOVED Requirements`，tasks 的 Z.2 改为「**覆盖重写**当前规格」。
- **[R11] 阶段 B 结构性跑不绿**（**grill 给的缓解已失效，须换路**）：grill 的缓解是「阶段 B 用 `manifest build` 补产 witnessloop 形态 manifest ⇒ 拿到绿的一侧作对照」。**对抗轮实测证伪**：manifest 只是必要条件，不是充分条件——**`来源:` 谓词让 grill stage 结构性判红**（本 change 自己的报告 7/7 条缺 `来源:`；且补齐 `## User Confirmation` 后仍报 7 条）。⇒ **补了 manifest 也拿不到绿**。
  **Mitigation（修正后）**：① 阶段 B 的「绿的一侧」**不再建立在 grill stage 上**——改以「`check` 的 findings 从『缺证据』类收敛为『正文格式』类」作为可测的进步指标；② grill stage 的绿**阻塞在 Open Question Q7**（等上游 [#20](https://github.com/Xingkai98/witnessloop/issues/20) 或本仓改写法）；③ 阶段 B 报告必须明确写「哪些红是配置问题、哪些红是已知的工具不兼容」，否则「值不值得真打开」会被误读。
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

- **新增（阶段 A 产物）**：`.witnessloop/policy.json`、`.witnessloop/init-manifest.json`、`.github/workflows/witnessloop.yml`、`.github/witnessloop-tests.txt`；以及 `reviews/` 下 witnessloop 形态的 manifest（`manifest build` 产出，样板见 Decision 7）。
- **修改**：`docs/development-guide.md`（新增「witnessloop 影子接入」一节）；`docs/openspec-change-backlog.md`（登记本 change）；`openspec/specs/dev-workflow-gate/spec.md`（阶段 A 结束时**覆盖重写**，退休两条占位 Requirement，见 R10）。
- **明确不改**：`AGENTS.md`（流程段留阶段 C）、`.github/workflows/ci.yml`、`scripts/**`、`agent/**`（含 `agent/workflow/review_manifest.py`——schema 统一不是本阶段的事，见 Decision 2）、branch protection。
- **回退**：`witnessloop uninit`（依 `init-manifest.json` 的 hash 台账精确回滚）或手工删 `.witnessloop/` + `.github/workflows/witnessloop.yml` + `.github/witnessloop-tests.txt`。本地 plugin 单独卸。
