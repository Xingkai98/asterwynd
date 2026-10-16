# dev-workflow-gate 规格 delta

> ⚠️ **本文件是「待施加的输入」，不是已同步的结果。** `openspec/specs/dev-workflow-gate/spec.md` 的改写（含 `## Purpose` / 「阶段划分」段的**人手就地改写**，那段无 delta 载体）由本 change 的收尾步骤执行（见 `tasks.md` 的 1.3 / 1.5）。在那一刻之前，当前规格里仍是阶段 A 的口径——**不要**据本文件的存在推断同步已完成。

## REMOVED Requirements

### Requirement: 影子接入阶段不改变任何既有强制

**Reason**: 该 Requirement 的正文与三个 Scenario 全部是**阶段 A 的过渡态约束**，其中第三条 Scenario（「合入之后新 PR 会跑但不拦」）在阶段 C 之后**已被证伪**——`gate / check` 现在是唯一 required，它会拦；第二条 Scenario（「既有 in-flight PR 不受影响」）描述的也是「caller 只存在于 feature 分支」这一已不存在的状态。继续保留它等于让规格描述一个不存在的世界。阶段 C 的形态由本 delta 新增的 `### Requirement: 阶段 C 翻开关后的 required 形态` 承载。

**Migration**: ③ 「新增 job 不进 required」→ 由 `platform-gate` 规格的 `### Requirement: 合入平台闸门`（唯一 required = `gate / check`）与本 delta 的新增条目共同承载；② 「既有 in-flight PR 不受影响」→ 无迁移（该过渡态一次性，已随阶段 A 合入结束）；① 关于 `ci.yml` 逐字节不变的约束 → 由本 delta 新增条目的「三个 job 照跑、不得删除」承接（语义更强：不只是「阶段 A 期间不变」，而是「降级之后仍须运行」）。

## MODIFIED Requirements

### Requirement: 已知红如实记录且不放宽判据

接入前已存在的 in-flight change（当前为 `add-minimal-tui-runtime-view`，无 `reviews/` 目录）在 witnessloop 契约下的报错 SHALL 被如实记录为**已知红**，SHALL NOT 通过放宽判据、开豁免或删减 `required_artifacts` 的方式使其变绿。阶段 C 之后该红 SHALL 被理解为**拦合入的红**而不再是日志红：任何触达该 change 目录的改动都会被它挡住，收尾它是解除阻塞的前提。

#### Scenario: in-flight change 的证据缺失不被豁免

- **WHEN** 阶段 A 之后对既有 active change 求值
- **THEN** 缺少 review manifest、缺少 `stage=grill` 证据的 change SHALL 照常判红
- **AND** 该红 SHALL 记入阶段 B 的验收报告，作为「真打开」决策的输入
- **AND** policy 的 `required_artifacts` SHALL 保持与 asterwynd 现有 change 目录必需件同形

#### Scenario: 阶段 C 之后已知红的性质发生迁移

- **WHEN** 阶段 C 把 `gate / check` 勾成 required 之后，评估同一条已知红
- **THEN** 该红 SHALL 从「不挡合入的日志红」变为「**会挡合入的红**」
- **AND** 该迁移 SHALL 被显式记录，SHALL NOT 让「已知红」被读成「可以放着不管」
- **AND** 处置 SHALL 仍是「收尾它」而不是「为它放宽判据或开豁免」

### Requirement: grill 报告正文判据的已知不兼容

接入 witnessloop SHALL 把「grill 决策记录的**格式**决定它能不能判绿」记为已知前置依赖，并 SHALL NOT 把它写成结构性阻塞。判据的**逐条契约**（witnessloop v1.7.0 实测）SHALL 为：① `## Confirmed Decisions` SHALL **至少 3 条**决策块；② 每条决策块内 SHALL 含 `来源:`（`_SOURCE_RE = 来源\s*[:：]`）——**同行裸写法 `来源: x` 命中，加粗的 `- **来源**: x` 不命中**，故这是**写法选择**而非结构性不兼容（阶段 B 实测：63 份归档 `grill-design.md` 中 39 份零 finding）；③ `## User Confirmation` 小节 SHALL **无条件存在**，与「有没有 Open Question」无关（`user_confirmation is None` 即判「缺少 `## User Confirmation` 小节」）；④ 候选 Open Questions 小节 SHALL 存在，且其中出现的每个 `Q<n>` SHALL 在 `## User Confirmation` 里有非占位确认。该组判据 SHALL NOT 成为放宽本仓或 witnessloop 任何判据的理由；改记录格式 SHALL 优先于改判据。这四条契约的可审计载体 SHALL 是版本控制内的文档（本规格与 `docs/development-guide.md`），SHALL NOT 指向 `.claude/` 下被 gitignore 的命令文件。

#### Scenario: 四条判据逐条可复核

- **WHEN** 核对一份本仓 grill 决策记录与 witnessloop v1.7.0 的正文判据
- **THEN** 决策块的 `来源:` 写法 SHALL 决定该条是否命中（加粗写法判红、同行裸写法判绿）
- **AND** 即使**一条 Open Question 都没有**，缺 `## User Confirmation` 小节 SHALL 照样判红
- **AND** 候选 Open Questions 小节缺失 SHALL 判红（含近义标题的诊断）

#### Scenario: 处置为「改记录格式」，不是改判据

- **WHEN** 决定怎么消除该组红
- **THEN** 处置 SHALL 为「按上述四条契约**写** grill 决策记录」——本仓版本控制内的文档（本规格与 `docs/development-guide.md`）随之承载这组格式要求
- **AND** SHALL NOT 通过放宽 witnessloop 的判据、或回填历史归档来消除它
- **AND** 该组红 SHALL NOT 被列为**阶段 A 的已知红**——阶段 A 默认一份 witnessloop 形态 manifest 都不落 ⇒ 正文判据**不会被触发**，先报的是「无 stage=grill 的 manifest」

## ADDED Requirements

### Requirement: 阶段 C 翻开关后的 required 形态

接入 witnessloop 的三个阶段（A 影子接入 / B 真实小需求验证 / C 真打开）SHALL 以阶段 C 的形态为**当前**形态。caller workflow SHALL 钉住 witnessloop 的**具体发版 ref**（当前 `v1.7.0`），且 SHALL NOT 依赖 `with: witnessloop-ref:` 另行钉包版本——包 ref 由被复用的 `gate.yml` 自身的 commit 决定。

> **required 集合与其「降级不关闭」不变量不在本规格重复**：`master` 的 required 是哪些、以及「降级为非必过的检查仍须运行」这条约束，SHALL 由 `platform-gate` 能力域规定（该能力域是本仓平台面的唯一规格源）。本规格只规定**接入形态**本身（caller 怎么钉、受管路径的后果、证据如何并存）。**理由**：同一条规范写两处是未来的漂移点——改一处漏一处不会被任何门禁发现。

#### Scenario: required 只剩 witnessloop 的 gate / check

- **WHEN** 查看阶段 C 之后 `master` 的分支保护配置
- **THEN** `required_status_checks.contexts` SHALL 为 `["gate / check"]`（该取值与其不变量由 `platform-gate` 能力域规定，本规格只断言阶段 C 之后的形态）
- **AND** 本仓自建门禁 SHALL 全部退出 required（降级，不是关闭）

#### Scenario: caller 钉住的 ref 同时决定包版本

- **WHEN** 检查 `.github/workflows/witnessloop.yml`
- **THEN** 该文件的 `uses:` SHALL 钉住具体发版 ref（形如 `Xingkai98/witnessloop/.github/workflows/gate.yml@v1.7.0`），SHALL NOT 用滚动 tag（`@v1`）或分支名
- **AND** caller SHALL NOT 出现 `with: witnessloop-ref:`——包 ref 的缺省由 `job.workflow_sha` 推导（上游 issue #30 的修复），升级动作 SHALL 是 `witnessloop init --gate-ref <新 ref>` 一处改动
- **AND** 升级 SHALL 同时重写 caller 与同步 `.witnessloop/init-manifest.json` 台账（该动作幂等）

#### Scenario: 阶段 C 之后的改动受 require_change_for 约束

- **WHEN** 一个 PR 触达 `agent/**` / `scripts/**` / `web/**`
- **THEN** 该 PR SHALL 挂一个 change 目录（`openspec/changes/<id>/`），或包含一条把该 change 归档进来的 `git mv`
- **AND** 缺少 change 目录时 `gate / check` SHALL 判红并阻止合入
- **AND** 该约束 SHALL 被如实记录为翻开关的**代价**，SHALL NOT 通过把受管路径移出 `require_change_for` 来规避

#### Scenario: 归档产物的证据形态在本仓并存两套

- **WHEN** 一个 change 归档
- **THEN** `reviews/` 下 SHALL 同时存在本仓形态（`reviews/<phase>-review-manifest.json`，字段 `phase`）与 witnessloop 形态（`reviews/<stage>.manifest.json`，字段 `stage`）两套证据
- **AND** witnessloop 形态的证据 SHALL 在归档 move **之后**、用**归档目录名**（`<YYYY-MM-DD>-<change-id>`）重建——否则 manifest 里的 `change_id` 与目录名不符
- **AND** `reviews/` 下每一份 `.md` SHALL 被某份 witnessloop 形态 manifest 的 `report_path` 绑定（否则触发孤儿规则）

### Requirement: 翻开关这一动作自身必须具备 change 记录

关闭某个接入阶段的动作 SHALL 由一条 OpenSpec change 承载并归档，SHALL NOT 以「改一个平台配置文件」的形式裸奔。该 change 的 `proposal.md` SHALL 如实写明「行为已先落地」这一事实与其实现凭据（PR / merge sha）。理由：翻开关之后任何触达受管路径的改动都必须挂 change；若翻开关自身的动作不挂 change，则它是在**用自己的豁免**把新规则挡在门外，且会让「哪些检查被降级、每个还在不在跑」失去可追溯的记录。本条 SHALL 有三条边界：① **时效**——记录 SHALL 在行为落地后的**同一收尾批**内归档，未归档前该阶段 SHALL 视为未闭合；② **非先例**——它只约束「关闭接入阶段 / 切换门禁」这类治理动作，SHALL NOT 被类推为常规功能 change 的工作流；③ **不豁免需求先行**——本仓「需求先行」规则要求的是**需求讨论与需求文档**先于实现，本条只承认「记录形态的落地可以滞后」，SHALL NOT 被读成「需求没聊清楚就可以先写实现」。

#### Scenario: 翻开关的记录与落地是两件事

- **WHEN** 阶段 C 的行为先落地、记录后补
- **THEN** 行为落地 SHALL NOT 被读成「记录不必要」——记录 SHALL 仍以独立 change 补齐并归档
- **AND** 该 change 的 `proposal.md` SHALL 如实写明「行为已先落地（含 PR 与 merge sha）、本 change 只做记录与规格对账」，SHALL NOT 把已落地的事实伪装成待实现的需求
