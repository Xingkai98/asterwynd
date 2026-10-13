# Design: witnessloop 影子接入（阶段 A）

## Context

asterwynd 自建了一整套「开发流程门禁」：change 契约、review manifest 的 hash/revision 绑定、grill 证据、grill-adversarial 门禁、building 门禁、受保护写入的结构化解释事件、本地写码前 guard、CI required check、测试执行点门禁。这套东西在 issue #305 里被盘点、被判定为「与本仓流程工具化抽取出的独立工具 **witnessloop** 高度重合」。

本 change 只做**接入的第一阶段（影子接入）**：把 witnessloop 的接入产物落进一条分支，让新门禁**只跑不拦**，用一个真实小需求验证它，然后停下来等验收结论。**下掉旧件、改 `AGENTS.md`、勾 required 都不在本 change 内。**

三条来自 #305 探测的硬事实决定了本设计的形状：

1. **出厂 policy 对 asterwynd 零命中**（`require_change_for` 出厂值是 `src/lib/app/apps/packages/server/cmd/internal`）⇒ witnessloop 的 `building` 与 `grill-adversarial` 门禁挂在 `code_hits` 上，用出厂 policy 接入 = 这两个门禁静默不触发 ⇒ **必须 `init --policy <seed>` 一次写成**。
2. **并存是加法**：`master` 现有 required = `["validate", "benchmark-gate"]`（本分支 `gh api` 实测）不动；新 job 阶段 A 不勾 required。
3. **`.claude/` 被 gitignore**（`.gitignore:9`）⇒ plugin 安装（交互层）是**本地动作**、不进 PR；CI 层（caller workflow）才是进 PR 的那一半。**两者是独立开关。**

## Goals / Non-Goals

**Goals:**

- 在一条分支上落齐 witnessloop 的接入产物：定制 policy + caller workflow + 测试执行点 + （本地）CC plugin。
- 让 witnessloop 的 `gate / check` job 在 CI 里**跑起来**且**不拦任何合入**。
- 用一个**真实小需求**在新流程上跑一遍，拿到「值不值得真打开」的判断依据。
- 把三条项目配置决策**摆到台面上**（每条带推荐值 + 具体例子），由用户拍板。
- 保证回退路径干净：`witnessloop uninit` 或手工删 `.witnessloop/` + caller，旧门禁原封不动。

**Non-Goals:**

- 不下掉任何现有件（`check_openspec_artifacts.py` / `workflow_guard.py` / `workflow_state.py` / `flow-policy.json` / `platform_gate.py` / `agent/workflow/*` 在本 change 内**一行不改**）。
- 不改 `validate` job、不动 `.github/workflows/ci.yml`、不动 branch protection 的既有两项。
- 不勾 required（那是阶段 C）。
- 不迁 RIR / Impact Analysis / benchmark 门禁 / tasks 完成度 / 归档点完成度进 witnessloop。
- 不给 witnessloop 加新能力（缺什么 → 去 witnessloop 立 issue）。
- 不为 in-flight 的 `add-minimal-tui-runtime-view` 放宽任何判据。

## Decisions

### Decision 1: 用 `init --policy <seed>` 一次写成，seed 是仓外临时文件、不入库

**选择**：接入命令形如 `witnessloop init --root . --policy /tmp/witnessloop-asterwynd-policy.json --test-command "<命令>"`。seed 文件放仓外临时路径，**不 commit**；产物 `.witnessloop/policy.json` 才入库。

**理由**：
- 出厂 `require_change_for`（`src/witnessloop/constants.py:40`）对 asterwynd 的 `agent/` / `scripts/` / `web/` **全不命中**；而 `building` 与 `grill-adversarial` 两个门禁**共用同一条 `code_hits` 触发**（`src/witnessloop/checkcmd.py:77` + `:96`）⇒ 用出厂 policy 接入，这两个核心门禁**完全不触发**，接入会退化成「只有一个 check 壳」。
- `--policy` 是**整份替换**而非增量 patch（`cli.py:49-54`：轻校验，只要求可解析为 JSON 对象）⇒ seed 必须是完整 policy。
- seed 不入库与 witnessloop 自己的做法一致（witnessloop 仓把 policy 直接放在 `.witnessloop/policy.json`，没有独立的 seed 文件概念）；把「生成 policy 的那份输入」留在仓外，避免两个真相源。

**落地形态（policy 的目标内容，具体值取决于 Open Questions 的答复）**：

```json
{
  "schema": "witnessloop/policy@v1",
  "changes_root": "openspec/changes",
  "protected_paths": ["openspec/specs/**", ".witnessloop/**"],
  "require_change_for": ["agent/**", "scripts/**", "web/**"],
  "required_artifacts": ["proposal.md", "design.md", "tasks.md", "specs", "reviews"],
  "evidence": {
    "review_manifest_glob": "reviews/*-manifest.json",
    "events_file": "workflow-events.jsonl",
    "protected_write_event_types": ["current_spec_synced", "backlog_updated",
                                   "change_archived", "protected_artifact_explained"]
  }
}
```

### Decision 2: `review_manifest_glob` 改成 `reviews/*-manifest.json`（纯机械修正，非决策）

**选择**：policy 里写 `evidence.review_manifest_glob = "reviews/*-manifest.json"`。

**理由**：asterwynd 的实际文件名是 `reviews/building-review-manifest.json`（实测），witnessloop 默认 glob 是 `reviews/*.manifest.json` ⇒ **不匹配**，不配这一条会让 manifest 存在性判定全部假红。这是**命名差异的机械对齐**，不含取舍。

**风险**：glob 放宽到 `*-manifest.json` 也会匹配到 `grill-design-manifest.json` 之类的文件。这在 witnessloop 的模型里是**无害**的——stage 名由 manifest 内部字段承载，glob 只负责「找到候选文件」。**待阶段 A 实测确认**（tasks 阶段 A 的验收项会打印 `check` 的实际判定结果）。

### Decision 3: `protected_paths` **不含** `openspec/changes/archive/**`

**选择**：归档目录**不列**进 `protected_paths`。

**理由**：asterwynd 的语义是「**归档是簿记动作、免解释**」——实现 PR 直接落 `archive/<date>-<id>/`，每个文件都配解释事件是不现实的。而 witnessloop 的 `is_archive_move` 豁免**只认纯改名**、不认「在实现 PR 里新增 archive 目录」⇒ 列上它，实测**立刻多出 12 条假红**（整个归档 change 目录每个文件一条）。

**替代方案与否决**：① 给 122 个历史归档补 manifest/事件——代价过大且不解决新归档；② 修 witnessloop 让 `is_archive_move` 认新增目录——那是**改上游**，超出本 change 范围（缺能力 → 去 witnessloop 立 issue）。⇒ 选「不列」。

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

### Decision 7: 已知红 —— `add-minimal-tui-runtime-view` **不许为它放宽判据**

**选择**：阶段 A 之后，active change `add-minimal-tui-runtime-view`（**没有 `reviews/` 目录**，实测）在 witnessloop 契约下会报「缺少 review manifest」+「无 stage=grill 的 manifest」。**记为已知红，不修，不放宽判据。**

**理由**：它是**接入前就存在的 in-flight change**，其证据缺失是历史事实。放宽判据（例如给它开豁免、或把 `required_artifacts` 里的 `reviews` 去掉）会让**新 change 也一起被放行**——正是 witnessloop 要堵的形态。阶段 A 不勾 required ⇒ 这条已知红**在阶段 A 不造成任何实际拦截**，它的作用是在阶段 B 的验收报告里被如实列出，供「真打开」决策参考。

## Pre-Implementation Review

- Questions resolved:
  - 接入形态（`init --policy` 一次写成 vs 出厂 policy + 后续手改）——**已定**：一次写成，理由见 Decision 1。
  - manifest glob 差异——**已定**（机械修正，Decision 2）。
  - 归档目录是否列 `protected_paths`——**已定：不列**（Decision 3，实测 12 条假红）。
  - 阶段划分与「只跑不拦」的实现方式——**已定**（Decision 4）。
  - 哪些留本地——**已定**（Decision 5）。
  - `handoff.json` 是否混入——**已定：不混入**（Decision 6）。
  - 已知红怎么处置——**已定：如实记录、不放宽**（Decision 7）。
- Options considered:
  - **A. 直接替换**：接入的同时下掉旧 checker 并把 `gate / check` 勾成 required。**否决**：会打开「一段没有任何强制（或换成没验证过的强制）的窗口」，且不可逆动作发生在验证之前。
  - **B. 影子接入（本方案）**：只跑不拦 → 真需求验证 → 再真打开。
  - **C. 出厂 policy 直接接入**：**否决**——`building` / `grill-adversarial` 门禁静默不触发，接入名存实亡。
- Rejected alternatives:
  - 选 A 或 C 的理由如上。另否决「在本 change 内顺手清理 `handoff.json`」（见 Decision 6，会污染影子接入的 diff 可评估性）。
- Final confirmations:
  - 开发前必须使用 `grilling` 做设计追问，把三条 Open Question 逐项抛给用户并等待明确答复；答复记录进 `reviews/grill-design.md` 的 `## User Confirmation`。**本 change 的 `## Open Questions` 未全部确认前不得写实现产物**（不跑 `init`、不建 caller、不装 plugin）。
- Remaining risks:
  - `--policy` 的语义合法性由 `check` 兜底 ⇒ seed 写错只会在**跑 `check` 时**暴露，不会在 `init` 时报错（见 Risks R2）。

## Open Questions

> 三条都是**项目配置**决策（不是 witnessloop 缺能力）：更正后的 issue #305 明确「三条决策全部是『项目配置』，没有一条需要改 witnessloop 的代码或逻辑」。每条附推荐值与**具体例子**，请逐条拍板。推荐值**不是**已确认结论。

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

## Risks / Trade-offs

- **[R1] 影子期的「假安全感」**：`gate / check` 在 CI 里是绿的（或红的）但**不拦合入** ⇒ 有人可能误以为它已经在管。**Mitigation**：阶段 A 的 PR 描述与 `docs/development-guide.md` 新节都显式写明「本 job 阶段 A 不 required，只跑不拦」；阶段 B 报告里也重申。
- **[R2] policy seed 写错的暴露延迟**：`--policy` 只做「可解析为 JSON 对象」的轻校验，**语义合法性由 `check` 兜底**（witnessloop `cli.py:49-54`）⇒ seed 写错不会在 `init` 时报错，只会在第一次跑 `check` 时暴露。**Mitigation**：阶段 A 的第一个验收项就是**在本分支 PR 上跑一次 `check` 并读取 findings**，而不是等「真需求」时才第一次跑。
- **[R3] 本地守卫能力退步**：asterwynd 解析 Bash 命令（`workflow_guard.py`，677 行），witnessloop `guard` 只看 `Write|Edit`（上游 `guardcmd.py:16-17` 自陈）。⇒ 本地拦截面变窄。**Mitigation**：(i) 阶段 A **不下掉**旧守卫，两条并存；(ii) 把退步写进本 proposal 的 Impact Analysis 与阶段 B 报告，作为「真打开」决策的输入；(iii) 真锚始终是 CI required check。
- **[R4] 已知红：`add-minimal-tui-runtime-view`**（无 `reviews/`）。**Mitigation**：阶段 A 不勾 required ⇒ 不造成实际拦截；在阶段 B 报告里如实列出；**不为它放宽判据**（Decision 7）。阶段 C 决策时必须把「它怎么收尾」一并考虑。
- **[R5] `.claude/` 被 gitignore ⇒ plugin 装/卸没有评审与回滚记录**（`.gitignore:9`）。**Mitigation**：把 plugin 安装步骤写进 tasks 与 `docs/development-guide.md`（**文档在版本控制里**），使「本地动作」至少有可复现的书面记录；plugin 来自 witnessloop 仓的 `plugin/` 目录（`commands/` + `hooks/`），升级靠重装。
- **[R6] 上游 reusable workflow 的版本面**：caller 钉 `@v1`（witnessloop `constants.py:11 DEFAULT_GATE_REF`），`@v1` 是**移动 tag** ⇒ 上游 `v1` 分支前进会改变本仓门禁行为。**Mitigation**：登记为后续观察项；若需要钉死，走 `--gate-ref` 指向 commit sha（**本阶段不引入**，避免过早固化）。**建议主 session 复核这条口径。**
- **[R7] 两组门禁的判定漂移**：并存期本地 checker 与 witnessloop **各判各的**，可能出现「一边绿一边红」。**Mitigation**：这是并存的**预期形态**（不是缺陷）——阶段 B 的报告要把所有分叉逐条列出，它们正是「迁移清单」的输入。
- **[R8] 阶段 B 的「真实小需求」选得不好**：若选的需求太琐碎，跑不出 intake 的真实摩擦。**Mitigation**：阶段 B 的任务里给出选择标准（必须触达 `require_change_for`、必须能产生 spec delta 或受保护写入、规模在一到两个文件）。

## Testing Strategy

本 change **不新增 Python 测试**——它的「测试」面就是**在新流程上跑一个真实需求**。分层如下：

- **阶段 A 的机械验收**（不依赖真实需求）：
  1. `witnessloop init --dry-run --policy <seed>` 在目标 worktree 上打印的待建文件清单 = 4 个新文件（`.witnessloop/policy.json` / `.witnessloop/init-manifest.json` / `.github/workflows/witnessloop.yml` / `.github/witnessloop-tests.txt`），**与既有文件零冲突**（本仓 `.github/workflows/` 下只有 `ci.yml`）。
  2. 落盘后本地跑 `witnessloop check`（或 `uv run witnessloop check --root .`）并**逐条读 findings**：确认 `building` / `grill-adversarial` 两条判定**确实被触发**（这正是 R2 的第一次暴露点；若 policy 的 `require_change_for` 没生效，这两条会**静默消失**——用本分支自身的 diff 当样本即可验证）。
  3. 本分支 PR 的 CI 上确认出现 `gate / check` job 并**跑出结果**。
  4. **回归确认**：本分支 PR 的 CI 上 `validate` / `benchmark-gate` 行为**逐字节不变**；`gh api …/protection` 的 `contexts` 仍是 `["validate", "benchmark-gate"]`。
- **阶段 A 的负向验收（必做）**：临时把 policy 换成出厂默认（`require_change_for` 不覆盖 `agent/**`）跑一次 `check`，**确认 `building` / `grill-adversarial` 判定消失**——这条用**证伪**证明「定制 policy 是必要的」，而不是靠推理。
- **阶段 B 的真实需求验收**：按「选择标准」挑一个真实小需求，走完整流程（`guard` 拦 → 写码 → grill/adversarial/审阅证据 → `check` 核 → 测试执行点在 CI 里跑），产出验收报告：findings 清单、与本地 checker 的分叉清单、已知红清单、体验摩擦清单。
- **不做的事**：不为本 change 写 witnessloop 侧的测试（上游自己的测试覆盖它）；不新增 pytest 用例；不改现有测试。

## Impact Analysis

- **新增（阶段 A 产物）**：`.witnessloop/policy.json`、`.witnessloop/init-manifest.json`、`.github/workflows/witnessloop.yml`、`.github/witnessloop-tests.txt`。
- **修改**：`docs/development-guide.md`（新增「witnessloop 影子接入」一节）；`docs/openspec-change-backlog.md`（登记本 change）。
- **明确不改**：`AGENTS.md`（流程段留阶段 C）、`.github/workflows/ci.yml`、`scripts/**`、`agent/**`、`openspec/specs/` 下除本 change 新增能力域外的既有 spec、branch protection。
- **回退**：`witnessloop uninit`（依 `init-manifest.json` 的 hash 台账精确回滚）或手工删 `.witnessloop/` + `.github/workflows/witnessloop.yml` + `.github/witnessloop-tests.txt`。本地 plugin 单独卸。
