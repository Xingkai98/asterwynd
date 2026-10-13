# dev-workflow-gate 规格

## Purpose

定义开发流程门禁的**承载边界**：哪些门禁由本仓自建脚本承载、哪些由外部工具 witnessloop 承载、以及从自建切换到接入 witnessloop 的约束。

本仓已完成 witnessloop 的**阶段 A（影子接入）**：接入产物已落进仓库——`.witnessloop/policy.json`（定制 policy）、`.witnessloop/init-manifest.json`（init 台账）、`.github/workflows/witnessloop.yml`（caller）、`.github/witnessloop-tests.txt`（测试执行点）。**影子期的形态是「并存、只跑不拦」**：witnessloop 的 `gate / check` 在 CI 里跑并输出 findings，但**不进 required**；本仓自建门禁**一行未动**——`scripts/check_openspec_artifacts.py`（change 契约、review manifest 绑定、grill / grill-adversarial / building 证据、受保护写入解释事件、tasks 与归档点完成度）、`scripts/workflow_guard.py`（本地写码前守卫，含 Bash 命令解析）、`scripts/workflow_state.py` 与 `agent/workflow/*`（流程事件投影）、`scripts/platform_gate.py`（合入平台闸门，见 `platform-gate` 能力域）**继续照跑**。`master` 的 required status checks 仍为 `["validate", "benchmark-gate"]`，分支保护语义由 `platform-gate` 能力域描述，本规格不重复。

**阶段划分**：A 影子接入（只跑不拦，本规格已落地）→ B 用一个真实小需求在新流程上跑一遍（拿到「值不值得真打开」的判断依据）→ C 真打开（勾 required、改写 `AGENTS.md` 流程段，由独立 change 承载）。**下掉旧件不在阶段 A 内**。

本规格用规范性语言描述**目标与边界**；阶段 A 的实测证据见 `openspec/changes/witnessloop-adoption/reviews/acceptance-stage-a.md`。

## Requirements

### Requirement: 流程骨架与项目规则的承载分工

接入 witnessloop 后，**流程骨架**（change 契约、review manifest 的证据绑定、grill / grill-adversarial / building 三类审阅证据、受保护路径的写入解释、本地写码前 guard、CI required check 形态、测试执行点）SHALL 由 witnessloop 承载；**项目规则**（Reference Implementation Research、Impact Analysis、benchmark 门禁、设计审阅任务、tasks 完成度、归档点完成度门、合入平台闸门、流程事件投影）SHALL 保留在本仓，SHALL NOT 迁入 witnessloop。

#### Scenario: 项目规则不随接入外迁

- **WHEN** 完成 witnessloop 接入
- **THEN** 本仓 SHALL 继续维护 `Reference Implementation Research` 与 `Impact Analysis` 的检查
- **AND** 归档点完成度门与 `platform-gate` 平台闸门 SHALL 仍由本仓脚本承载
- **AND** 缺什么能力 SHALL 去 witnessloop 仓库立 issue，而不是在本仓另起一套

#### Scenario: 局部应用成熟模式而非另立协议

- **WHEN** 决定让某个自建检查改由 witnessloop 承载
- **THEN** 该检查 SHALL 映射到 witnessloop 既有的 stage 名与事件语义（`grill` / `grill-adversarial` / `building`；`event_type` / `artifact_path` / `reason` / `approved_by`）
- **AND** SHALL NOT 引入与 witnessloop 不兼容的第二套门禁协议

### Requirement: 接入 witnessloop 前的定制 policy 前置

向本仓接入 witnessloop 时，接入命令 SHALL 通过 `witnessloop init --policy <seed>` 提供一份**完整**的定制 policy，SHALL NOT 使用 witnessloop 出厂 policy 直接接入。理由：出厂 `require_change_for` 对 `agent/`、`scripts/`、`web/` 零命中，而 witnessloop 的 `building` 门禁与 `grill-adversarial` 门禁**共用同一条 `code_hits` 触发**，用出厂 policy 接入会使这两个核心门禁静默不触发。policy seed SHALL 是仓外临时文件、SHALL NOT 进入版本控制；入库的产物 SHALL 是 init 写出的 `.witnessloop/policy.json`。

#### Scenario: 用出厂 policy 接入会被判不合规

- **WHEN** 以出厂 `require_change_for`（`src` / `lib` / `app` / `apps` / `packages` / `server` / `cmd` / `internal`）接入本仓
- **THEN** 触达 `agent/**`、`scripts/**`、`web/**` 的 PR SHALL 不产生 `code_hits`
- **AND** `building` 与 `grill-adversarial` 两条 stage 判定 SHALL NOT 被触发（接入名存实亡）

#### Scenario: 定制 policy 的四个字段落定

- **WHEN** 定稿 policy seed
- **THEN** `evidence.review_manifest_glob` SHALL 保持 witnessloop 默认的 `reviews/*.manifest.json`（**不放宽**成 `*-manifest.json`——字段 schema 差异才是真问题，放宽会把本仓 schema 的 manifest 卷进候选集，见「review manifest 两套并存」Requirement）
- **AND** `evidence.protected_write_event_types` SHALL 为本仓现有类型名 `["current_spec_synced", "backlog_updated", "change_archived", "protected_artifact_explained"]`（本仓 `scripts/flow-policy.json` 与 78 份历史事件日志 SHALL 零改动）
- **AND** `require_change_for` SHALL 为 `["agent/**", "scripts/**", "web/**"]`，SHALL NOT 包含 benchmark 目录、`tests/**`、`docs/**`
- **AND** `protected_paths` SHALL 为 `["openspec/specs/**", ".witnessloop/**", "docs/known-issues.md", "docs/known-debt.md", "docs/openspec-change-backlog.md"]`（补齐三条文档路径，使 `backlog_updated` / `protected_artifact_explained` 不成为死配置）
- **AND** `protected_paths` SHALL NOT 包含 `openspec/changes/archive/**`
- **AND** 测试执行点 SHALL 为 `uv run --extra dev pytest -q` 一条命令（`ci.yml` 的编码 warn-as-error 变体、`openspec validate`、artifact checker SHALL NOT 并入执行点）

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

#### Scenario: `reviews/` 必须处于一致状态（孤儿规则的激活条件）

- **WHEN** 决定是否在 change 的 `reviews/` 下落 witnessloop 形态 manifest
- **THEN** SHALL 遵守「**要么给每份报告都建 manifest，要么一份都别落**」
- **AND** 依据 SHALL 是实测的激活条件：glob 匹配 0 份时 witnessloop 的 manifest 循环**早退**、孤儿规则**不执行**（现状 2 条红）；一旦落了任意一份 witnessloop 形态 manifest，`reviews/**/*.md` 里**每一份未绑定 `report_path` 的报告**都判孤儿（实测红数 2 → 14 → 16）
- **AND** 只落一部分 manifest 的中间态 SHALL 被拒绝——它比不落更红

#### Scenario: 证据的 stale 顺序约束

- **WHEN** 产出 review manifest 或其它 `reviews/` 证据
- **THEN** SHALL 在**所有内容提交之后**产出（witnessloop 的 stale 判定只豁免 `.witnessloop/**`、`<changes_root>/*/reviews/**`、`<changes_root>/*/workflow-events.jsonl`、`archive/**`）
- **AND** 触碰 `docs/**` 与 `openspec/specs/**` 的收尾步骤 SHALL 排在证据产出之前
- **AND** 证据 SHALL 由人在本地产出——CI 的 caller workflow **只做 `check`、不产证据**

### Requirement: grill 报告正文判据的已知不兼容

影子接入阶段 SHALL 把「witnessloop 的 grill 正文判据与本仓记录格式不兼容」记为**已知阻塞/前置依赖**：witnessloop 的 `_SOURCE_RE` **要求「来源」后直接接冒号、不接受 `- **来源**: x` 的加粗写法**，而本仓 grill 记录通篇使用加粗 ⇒ **grill stage 在现有报告格式下结构性不可能判绿**。该阻塞 SHALL NOT 成为放宽本仓或 witnessloop 任何判据的理由；其处置 SHALL 为**已拍板的 U7：等上游修谓词、本仓零改动**。

#### Scenario: 不兼容的事实可复核

- **WHEN** 核对本仓 grill 记录与 witnessloop 的正文判据
- **THEN** 本 change 自己的 `reviews/grill-design.md` SHALL 被判 7/7 条「缺 `来源:`」（同一份文件在本仓 checker 侧抽出 7 条决策、判定正常）
- **AND** 归档中的 `grill-design.md` SHALL 呈现同一趋势（完全无 finding 仅 39 份，近期写法基本全判红）
- **AND** 即使补齐全 `## User Confirmation` 记录，该 7 条 SHALL 仍然存在

#### Scenario: 处置已拍板为「等上游修谓词」

- **WHEN** 决定怎么消除该不兼容
- **THEN** 处置 SHALL 为「**等 witnessloop issue #20 修 `_SOURCE_RE`**，本仓零改动」——不改本仓 grill 记录格式、**不回填 62 份归档**
- **AND** 该组红 SHALL **NOT** 被列为**阶段 A 的已知红**——阶段 A 默认一份 witnessloop 形态 manifest 都不落 ⇒ 正文判据**不会被触发**，先报的是「无 stage=grill 的 manifest」
- **AND** 阶段 A 的已知红 SHALL 被准确描述为「**缺 manifest**」这一类（实测本 change 自身：`缺少 review manifest` + `无 stage=grill 的 manifest`）
- **AND** witnessloop issue #20 SHALL 被登记为**「建 witnessloop 形态 grill 证据之前」的前置条件**（阶段 B/C 会先碰到），SHALL NOT 被描述为阶段 A 的阻塞
- **AND** 该组红 SHALL NOT 成为放宽本仓或 witnessloop 任何判据的理由
- **AND** 阶段 B 的验收报告 SHALL 把该组红与「配置错误」分开归因

### Requirement: 双 PreToolUse 守卫并存且未知面必须实测

接入 plugin 后，本仓现有守卫（`scripts/workflow_guard.py`，matcher `Write|Edit|Bash`）与 witnessloop plugin 的守卫（matcher `Write|Edit`）SHALL 并存，阶段 A SHALL NOT 下掉任何一个。**真正未实测的只有两项**——两者在同一 `Write|Edit` 上的**合并/串行语义**与**拦截提示归属**——它们 SHALL 作为阶段 A 的强制实测项，SHALL NOT 由推理代替实测；且 SHALL 在**主 checkout 与 building worktree 两棵树各做一次**。命令命名空间 SHALL 由 `plugin/.claude-plugin/plugin.json` 的 `name` 字段静态判定，SHALL NOT 列为未实测项。

#### Scenario: 实测取代推断

- **WHEN** plugin 安装完成
- **THEN** SHALL 先做前置核验——PATH 上的 `witnessloop` 是否含 `guard` 子命令（`guard.sh` 的退出码映射为「1 → 拦、其余 → 放行」，旧版 CLI 或用法错误会**静默空转**，不做该核验就会把「放行」误读成「证据完备」）
- **AND** SHALL 实测一次命中两个 matcher 的 `Write`，记录两个 hook 是否都执行、串行还是并行、提示归属哪个守卫
- **AND** 该实测 SHALL 在**主 checkout 与 building worktree 各做一次**（worktree 下无 `.claude/`，只能观察到 plugin 那一个）
- **AND** 结果 SHALL 写入阶段 A/B 验收报告

#### Scenario: 不夸大不缩小行为变化

- **WHEN** 汇总本地守卫的行为变化
- **THEN** 只有「**丢失 Bash 拦截面**」这一条退步 SHALL 被记录
- **AND** SHALL NOT 声称 witnessloop 守卫在「本仓守卫不管的维度」上新增拦截——本仓守卫 `_grill_evidence_missing` 本来就拦「缺 grill 证据」这一维度，两侧是**同维度、不同判据**（本仓=文件 + 正文；witnessloop=manifest + 正文）
