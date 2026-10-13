# dev-workflow-gate 规格 delta

## REMOVED Requirements

### Requirement: dev-workflow-gate 当前为预留能力域

**Reason**: 该 Requirement 以「**尚未接入**」为规范对象（`系统 SHALL NOT 声称已经接入 witnessloop`、`仓库中 SHALL NOT 存在 .witnessloop/policy.json …`、`.github/workflows/ 下 SHALL 只有 ci.yml`）。阶段 A 的实现**恰好创建** `.witnessloop/policy.json` 与 `.github/workflows/witnessloop.yml` ⇒ 该 Requirement 会被本 change 自己的实现**直接证伪**；若只做 `## ADDED` 合并，占位条目会存活并与实现自相矛盾。

**Migration**: 阶段 A 结束时按 `platform-gate` 先例（实现 commit `f7e912b` 的「同步 current spec（**覆盖占位**，SHALL 目标语言）」）**覆盖重写** `openspec/specs/dev-workflow-gate/spec.md`：删除本占位 Requirement，把其 Purpose 段从「尚未接入」改写为接入后的实际承载形态，并把本 delta 的 Requirements 合并进去。重写后追加 `current_spec_synced` 解释事件（`tasks.md` 的 Z.2）。

## ADDED Requirements

### Requirement: 接入 witnessloop 前的定制 policy 前置

向本仓接入 witnessloop 时，接入命令 SHALL 通过 `witnessloop init --policy <seed>` 提供一份**完整**的定制 policy，SHALL NOT 使用 witnessloop 出厂 policy 直接接入。理由：出厂 `require_change_for` 对 `agent/`、`scripts/`、`web/` 零命中，而 witnessloop 的 `building` 门禁与 `grill-adversarial` 门禁**共用同一条 `code_hits` 触发**，用出厂 policy 接入会使这两个核心门禁静默不触发。policy seed SHALL 是仓外临时文件、SHALL NOT 进入版本控制；入库的产物 SHALL 是 init 写出的 `.witnessloop/policy.json`。

#### Scenario: 用出厂 policy 接入会被判不合规

- **WHEN** 以出厂 `require_change_for`（`src` / `lib` / `app` / `apps` / `packages` / `server` / `cmd` / `internal`）接入本仓
- **THEN** 触达 `agent/**`、`scripts/**`、`web/**` 的 PR SHALL 不产生 `code_hits`
- **AND** `building` 与 `grill-adversarial` 两条 stage 判定 SHALL NOT 被触发（接入名存实亡）

#### Scenario: 定制 policy 的四个字段落定

- **WHEN** 定稿 policy seed
- **THEN** `evidence.review_manifest_glob` SHALL 保持 witnessloop 默认的 `reviews/*.manifest.json`（**不放宽**成 `*-manifest.json`——字段 schema 差异才是真问题，放宽会把本仓 schema 的 manifest 卷进候选集，见 ADDED 的「review manifest 两套并存」Requirement）
- **AND** `evidence.protected_write_event_types` SHALL 覆盖本仓 `scripts/flow-policy.json` 实际使用的事件类型名
- **AND** `require_change_for` SHALL 至少覆盖 `agent/**`、`scripts/**`、`web/**`
- **AND** `protected_paths` SHALL NOT 包含 `openspec/changes/archive/**`

### Requirement: 影子接入阶段不改变任何既有强制

第一阶段（阶段 A）SHALL 只新增 witnessloop 的接入产物，SHALL NOT 改变本仓现有的任何强制：`master` 的 required status checks SHALL 保持 `["validate", "benchmark-gate"]`，`.github/workflows/ci.yml` 的 `validate` 与 `benchmark-gate` 两个 job SHALL 逐字节不变，`scripts/` 下的现有 checker 与守卫 SHALL 一行不改。

#### Scenario: 新增 job 不进 required

- **WHEN** 阶段 A 的 caller workflow 随分支合入前检查
- **THEN** `gh api repos/Xingkai98/asterwynd/branches/master/protection` 的 `required_status_checks.contexts` SHALL 仍为 `["validate", "benchmark-gate"]`
- **AND** witnessloop 的 `gate / check` job SHALL **不**出现在 required 列表中

#### Scenario: 既有 in-flight PR 不受影响

- **WHEN** caller workflow 只存在于 feature 分支而尚未合入 `master`
- **THEN** 该分支之外**既有 in-flight PR** SHALL 不运行 witnessloop 的 `gate / check` job（GitHub 只对 head 含该 workflow 的 PR 运行它）
- **AND** 它们的门禁行为 SHALL 与本 change 前一致

#### Scenario: 合入之后新 PR 会跑但不拦

- **WHEN** 本 change 合入 `master` 之后新开一个 PR
- **THEN** 该 PR SHALL 运行 `gate / check` job
- **AND** 该 job 的结果 SHALL NOT 阻止合入（阶段 A 未把它勾进 required）
- **AND** 本规格 SHALL NOT 把「新 PR 不跑该 job」写成目标——那是合入前才成立的过渡态

### Requirement: 影子接入阶段的验收判据

阶段 A SHALL 用可机械复核的判据收口，SHALL NOT 以「产物已落盘」代替验收。判据 SHALL 至少包含：`init --dry-run` 待建文件为零冲突的四个新文件；本分支 PR 的 CI 出现 `gate / check` 并跑出结果；本分支 diff 下 `check` 确实触发 `building` 与 `grill-adversarial` 两条 stage 判定；**负向对照**（换成出厂 policy 后这两条判定消失）；`validate` 与 `benchmark-gate` 的行为及 branch protection 实况未变。

#### Scenario: 用负向对照证明定制 policy 必要

- **WHEN** 在同一段 diff 上分别以定制 policy 与出厂 policy 跑 `witnessloop check`
- **THEN** 定制 policy 下 SHALL 出现 `building` 与 `grill-adversarial` 的 stage 判定
- **AND** 出厂 policy 下这两条判定 SHALL 消失
- **AND** 两次原始输出 SHALL 并列记入阶段 A 验收报告

### Requirement: 已知红如实记录且不放宽判据

接入前已存在的 in-flight change（当前为 `add-minimal-tui-runtime-view`，无 `reviews/` 目录）在 witnessloop 契约下的报错 SHALL 被如实记录为**已知红**，SHALL NOT 通过放宽判据、开豁免或删减 `required_artifacts` 的方式使其变绿。

#### Scenario: in-flight change 的证据缺失不被豁免

- **WHEN** 阶段 A 之后对既有 active change 求值
- **THEN** 缺少 review manifest、缺少 `stage=grill` 证据的 change SHALL 照常判红
- **AND** 该红 SHALL 记入阶段 B 的验收报告，作为「真打开」决策的输入
- **AND** policy 的 `required_artifacts` SHALL 保持与 asterwynd 现有 change 目录必需件同形

### Requirement: 本地守卫的能力退步必须随接入写明

接入 witnessloop SHALL 被记录为一次本地拦截面的**收窄**：本仓现有守卫解析 Bash 命令，witnessloop 的 `guard` 只匹配 `Write|Edit`。阶段 A SHALL NOT 下掉现有守卫；该退步 SHALL 写进 `design.md` 与阶段 B 验收报告，SHALL NOT 因「两者都可绕过」而略去。

#### Scenario: 两个守卫并存

- **WHEN** 阶段 A 落地后本地写码
- **THEN** 本仓 `scripts/workflow_guard.py` 与 witnessloop 的 guard hook SHALL 同时存在
- **AND** witnessloop guard 漏掉的 Bash 写文件路径 SHALL 由现有守卫继续覆盖

#### Scenario: 退步写进文档

- **WHEN** 阶段 B 产出验收报告
- **THEN** 报告 SHALL 含一条实测结论：用 Bash 写受管路径是否绕过 witnessloop 的 `guard`
- **AND** `design.md` 的 `## Risks / Trade-offs` SHALL 保留该退步条目至阶段 C 决策

### Requirement: 交互层与 CI 层是两个独立开关

Claude Code plugin 的安装 SHALL 被当作**本地动作**（`.claude/` 被 `.gitignore` 忽略 ⇒ 不进 diff、不产生 PR），CI 层（caller workflow + policy）SHALL 是被评审的那一半。两层 SHALL 互不依赖：未安装 plugin 时 CI 门禁照常运行，安装 plugin SHALL NOT 自动改变 required 状态。plugin 的安装、卸载与升级步骤 SHALL 记入版本控制内的文档。

#### Scenario: 不装 plugin 的贡献者仍受门禁约束

- **WHEN** 一名未安装 witnessloop plugin 的贡献者提交 PR
- **THEN** CI 的 `gate / check` job SHALL 照常运行
- **AND** 该贡献者本地缺少的只是写码前的**防遗忘**提示，不是门禁本身

#### Scenario: 本地动作有书面记录

- **WHEN** 安装或升级 plugin
- **THEN** 步骤 SHALL 写在 `docs/development-guide.md` 中（版本控制内）
- **AND** 该文档 SHALL 说明「本地动作没有评审与回滚记录」这一已知代价

### Requirement: 保留为本地规则的项目特有检查

以下检查 SHALL 保留在本仓、SHALL NOT 迁入 witnessloop：RIR、Impact Analysis、benchmark 门禁、`_check_design_review_task`、tasks 完成度、归档点完成度门（`_check_archived_completion_gate`）、`platform_gate.py` 平台闸门、以及流程事件投影（`workflow_state.py` 与 `agent/workflow/*`）。witnessloop 承载的是**流程骨架**（change 契约 / 证据绑定 / grill / grill-adversarial / building / 受保护写入 / 本地 guard / 测试执行点），本仓保留的是**项目规则**。

#### Scenario: 现有 checker 不被本 change 下掉

- **WHEN** 阶段 A 的变更集被评审
- **THEN** `scripts/check_openspec_artifacts.py`、`scripts/workflow_guard.py`、`scripts/workflow_state.py`、`scripts/flow-policy.json`、`scripts/platform_gate.py` SHALL 全部未被修改
- **AND** `agent/workflow/**`（含 manifest 生成器 `agent/workflow/review_manifest.py`）SHALL 未被修改
- **AND** 任何下掉动作 SHALL 由阶段 C 之后的独立 change 承载

#### Scenario: 退役状态机残留另行处理

- **WHEN** 规划清理 `handoff.json` 及其相关检查（122 个归档中 5 个含 `handoff.json`）
- **THEN** 该清理 SHALL 作为独立后续 change 登记，SHALL NOT 混入影子接入的变更集

### Requirement: review manifest 两套并存，schema 统一延后

影子接入阶段 SHALL NOT 修改本仓的 review manifest 生成器；两侧 manifest SHALL 并存：本仓形态（`reviews/<phase>-review-manifest.json`，字段 `phase`）继续由现有工具链产出并喂本仓 checker，witnessloop 形态（`reviews/<stage>.manifest.json`）由 `witnessloop manifest build` 产出。`evidence.review_manifest_glob` SHALL 保持 witnessloop 默认的 `reviews/*.manifest.json`，SHALL NOT 放宽为 `*-manifest.json`。schema 统一 SHALL 作为阶段 C 之后的独立 change，SHALL NOT 混入影子接入。

#### Scenario: 不迁 schema 的边界

- **WHEN** 阶段 A/B 落地接入产物
- **THEN** `agent/workflow/review_manifest.py` SHALL 未被修改
- **AND** 本仓现有 `/review-loop` 产出的 manifest SHALL 继续被本仓 checker 消费
- **AND** witnessloop 侧的 stage 证据 SHALL 由 `manifest build` 另行产出

#### Scenario: glob 不放宽的理由可复核

- **WHEN** 决定 `review_manifest_glob` 取值
- **THEN** 该值 SHALL 为 `reviews/*.manifest.json`
- **AND** 放宽为 `*-manifest.json` SHALL 被拒绝——它会把本仓 schema 的 manifest 卷入候选集：witnessloop 按路径字典序取第一份同 stage manifest 作证据（可错绑悬空报告），同时逐份校验所有匹配文件（任一坏文件独立报红）

### Requirement: 双 PreToolUse 守卫并存且未知面必须实测

接入 plugin 后，本仓现有守卫（`scripts/workflow_guard.py`，matcher `Write|Edit|Bash`）与 witnessloop plugin 的守卫（matcher `Write|Edit`）SHALL 并存，阶段 A SHALL NOT 下掉任何一个。两者在同一 `Write|Edit` 上的合并语义、拦截提示归属、plugin 命令命名空间是否冲突 SHALL 作为阶段 A 的强制实测项，SHALL NOT 由推理代替实测。

#### Scenario: 实测取代推断

- **WHEN** plugin 安装完成
- **THEN** SHALL 实测一次命中两个 matcher 的 `Write`，记录两个 hook 是否都执行、提示归属哪个守卫
- **AND** SHALL 实测 plugin 命令名与本仓 `.claude/commands/` 下同名命令是否冲突
- **AND** 结果 SHALL 写入阶段 A/B 验收报告

#### Scenario: 新增拦截面与退步分开记录

- **WHEN** 汇总本地守卫的行为变化
- **THEN** 「丢失 Bash 拦截面」（退步）与「新增『缺 grill 证据』拦截面」（新增能力）SHALL 分开记录
- **AND** 两者 SHALL NOT 互相抵消成一句「影响不大」
