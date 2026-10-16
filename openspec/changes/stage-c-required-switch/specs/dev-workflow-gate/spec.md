# dev-workflow-gate 规格 delta

## REMOVED Requirements

### Requirement: 影子接入阶段不改变任何既有强制

**Reason**: 该 Requirement 的正文与三个 Scenario 全部是**阶段 A 的过渡态约束**，其中第三条 Scenario（「合入之后新 PR 会跑但不拦」）在阶段 C 之后**已被证伪**——`gate / check` 现在是唯一 required，它会拦；第二条 Scenario（「既有 in-flight PR 不受影响」）描述的也是「caller 只存在于 feature 分支」这一已不存在的状态。继续保留它等于让规格描述一个不存在的世界。阶段 C 的形态由本 delta 新增的 `### Requirement: 阶段 C 翻开关后的 required 形态` 承载。

**Migration**: ③ 「新增 job 不进 required」→ 由 `platform-gate` 规格的 `### Requirement: 合入平台闸门`（唯一 required = `gate / check`）与本 delta 的新增条目共同承载；② 「既有 in-flight PR 不受影响」→ 无迁移（该过渡态一次性，已随阶段 A 合入结束）；① 关于 `ci.yml` 逐字节不变的约束 → 由本 delta 新增条目的「三个 job 照跑、不得删除」承接（语义更强：不只是「阶段 A 期间不变」，而是「降级之后仍须运行」）。

## MODIFIED Requirements

### Requirement: grill 报告正文判据的已知不兼容

接入 witnessloop SHALL 把「grill 决策记录的**格式**决定它能不能判绿」记为已知前置依赖，并 SHALL NOT 把它写成结构性阻塞。判据的**逐条契约**（witnessloop v1.7.0 实测）SHALL 为：① `## Confirmed Decisions` 每条决策块内 SHALL 含 `来源:`（`_SOURCE_RE = 来源\s*[:：]`）——**同行裸写法 `来源: x` 命中，加粗的 `- **来源**: x` 不命中**，故这是**写法选择**而非结构性不兼容（阶段 B 实测：63 份归档 `grill-design.md` 中 39 份零 finding）；② `## User Confirmation` 小节 SHALL **无条件存在**，与「有没有 Open Question」无关（`user_confirmation is None` 即判「缺少 `## User Confirmation` 小节」）；③ 候选 Open Questions 小节 SHALL 存在，且其中出现的每个 `Q<n>` SHALL 在 `## User Confirmation` 里有非占位确认。该组判据 SHALL NOT 成为放宽本仓或 witnessloop 任何判据的理由；改记录格式 SHALL 优先于改判据。

#### Scenario: 三条判据逐条可复核

- **WHEN** 核对一份本仓 grill 决策记录与 witnessloop v1.7.0 的正文判据
- **THEN** 决策块的 `来源:` 写法 SHALL 决定该条是否命中（加粗写法判红、同行裸写法判绿）
- **AND** 即使**一条 Open Question 都没有**，缺 `## User Confirmation` 小节 SHALL 照样判红
- **AND** 候选 Open Questions 小节缺失 SHALL 判红（含近义标题的诊断）

#### Scenario: 处置为「改记录格式」，不是改判据

- **WHEN** 决定怎么消除该组红
- **THEN** 处置 SHALL 为「按上述三条契约**写** grill 决策记录」——本仓模板与 `/grill` 的产出格式随之对齐
- **AND** SHALL NOT 通过放宽 witnessloop 的判据、或回填历史归档来消除它
- **AND** 该组红 SHALL NOT 被列为**阶段 A 的已知红**——阶段 A 默认一份 witnessloop 形态 manifest 都不落 ⇒ 正文判据**不会被触发**，先报的是「无 stage=grill 的 manifest」

## ADDED Requirements

### Requirement: 阶段 C 翻开关后的 required 形态

接入 witnessloop 的三个阶段（A 影子接入 / B 真实小需求验证 / C 真打开）SHALL 以阶段 C 的形态为**当前**形态：`master` 的 required status checks SHALL 为**唯一**的 `gate / check`，本仓自建的 `validate` / `benchmark-gate` / `windows-platform` SHALL 继续照跑但不拦合并。caller workflow SHALL 钉住 witnessloop 的**具体发版 ref**（当前 `v1.7.0`），且 SHALL NOT 依赖 `with: witnessloop-ref:` 另行钉包版本——包 ref 由被复用的 `gate.yml` 自身的 commit 决定。

#### Scenario: required 只剩 witnessloop 的 gate / check

- **WHEN** 查看阶段 C 之后 `master` 的分支保护配置
- **THEN** `required_status_checks.contexts` SHALL 为 `["gate / check"]`
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

关闭阶段 C 的动作 SHALL 由一条 OpenSpec change 承载并归档，SHALL NOT 以「改一个平台配置文件」的形式裸奔。理由：翻开关之后任何触达受管路径的改动都必须挂 change；若翻开关自身的动作不挂 change，则它是在**用自己的豁免**把新规则挡在门外，且会让「哪些检查被降级、每个还在不在跑」失去可追溯的记录。

#### Scenario: 翻开关的记录与落地是两件事

- **WHEN** 阶段 C 的行为先落地、记录后补
- **THEN** 行为落地 SHALL NOT 被读成「记录不必要」——记录 SHALL 仍以独立 change 补齐并归档
- **AND** 该 change 的 `proposal.md` SHALL 如实写明「行为已先落地（含 PR 与 merge sha）、本 change 只做记录与规格对账」，SHALL NOT 把已落地的事实伪装成待实现的需求
