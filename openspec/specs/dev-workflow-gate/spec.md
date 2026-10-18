# dev-workflow-gate 规格

## Purpose

定义开发流程门禁的**承载边界**：哪些门禁由本仓自建脚本承载、哪些由外部工具 witnessloop 承载、以及从自建切换到接入 witnessloop 的三阶段（A 影子接入 / B 真实小需求验证 / C 真打开）各自的约束。

**本仓已走到阶段 C（真打开，2026-10-17）**：接入产物已落进仓库——`.witnessloop/policy.json`（定制 policy）、`.witnessloop/init-manifest.json`（init 台账）、`.github/workflows/witnessloop.yml`（caller，钉 `@v1.7.0`）、`.github/witnessloop-tests.txt`（测试执行点）。**当前形态是「required 只有 witnessloop 的 `gate / check`，本仓自建门禁照跑但不拦」**：`scripts/check_openspec_artifacts.py`（change 契约、building review 的 `## 闭环出口` PASS 判据、grill / grill-adversarial / building 证据、受保护写入解释事件、tasks 与归档点完成度）、`scripts/workflow_guard.py`（本地写码前守卫，含 Bash 命令解析）、`scripts/workflow_state.py` 与 `agent/workflow/*`（流程事件投影）、`scripts/platform_gate.py`（合入平台闸门，见 `platform-gate` 能力域）**全部继续照跑**，只是不再决定能否合入。`master` 的 required 集合与其「降级不关闭」不变量由 `platform-gate` 能力域规定，本规格不重复。

**阶段划分**：A 影子接入（只跑不拦）→ B 用一个真实小需求在新流程上跑一遍（取得「值不值得真打开」的判断依据）→ C 真打开（勾 required，由独立 change 承载）。**下掉旧件不在 A/B/C 任何一阶段内**。阶段 A 的实测证据见已归档 change `openspec/changes/archive/2026-10-13-witnessloop-adoption/reviews/acceptance-stage-a.md`。

本规格用规范性语言描述**目标与边界**。

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
- **THEN** `evidence.review_manifest_glob` SHALL 保持 witnessloop 默认的 `reviews/*.manifest.json`（**不放宽**成 `*-manifest.json`——字段 schema 差异才是真问题，放宽会把本仓 schema 的 manifest 卷进候选集，见「review manifest 单套承载：本仓形态退役」Requirement）
- **AND** `evidence.protected_write_event_types` SHALL 为本仓现有类型名 `["current_spec_synced", "backlog_updated", "change_archived", "protected_artifact_explained"]`（本仓 `scripts/flow-policy.json` 与 78 份历史事件日志 SHALL 零改动）
- **AND** `require_change_for` SHALL 为 `["agent/**", "scripts/**", "web/**"]`，SHALL NOT 包含 benchmark 目录、`tests/**`、`docs/**`
- **AND** `protected_paths` SHALL 为 `["openspec/specs/**", ".witnessloop/**", "docs/known-issues.md", "docs/known-debt.md", "docs/openspec-change-backlog.md"]`（补齐三条文档路径，使 `backlog_updated` / `protected_artifact_explained` 不成为死配置）
- **AND** `protected_paths` SHALL NOT 包含 `openspec/changes/archive/**`
- **AND** 测试执行点 SHALL 为 `uv run --extra dev pytest -q` 一条命令（`ci.yml` 的编码 warn-as-error 变体、`openspec validate`、artifact checker SHALL NOT 并入执行点）

### Requirement: 影子接入阶段的验收判据

阶段 A SHALL 用可机械复核的判据收口，SHALL NOT 以「产物已落盘」代替验收。判据 SHALL 至少包含：`init --dry-run` 待建文件为零冲突的四个新文件；本分支 PR 的 CI 出现 `gate / check` 并跑出结果；本分支 diff 下 `check` 确实触发 `building` 与 `grill-adversarial` 两条 stage 判定；**负向对照**（换成出厂 policy 后这两条判定消失）；`validate` 与 `benchmark-gate` 的行为及 branch protection 实况未变。

#### Scenario: 用负向对照证明定制 policy 必要

- **WHEN** 在同一段 diff 上分别以定制 policy 与出厂 policy 跑 `witnessloop check`
- **THEN** 定制 policy 下 SHALL 出现 `building` 与 `grill-adversarial` 的 stage 判定
- **AND** 出厂 policy 下这两条判定 SHALL 消失
- **AND** 两次原始输出 SHALL 并列记入阶段 A 验收报告

### Requirement: 已知红如实记录且不放宽判据

接入时已存在的 in-flight change（`add-minimal-tui-runtime-view`，无 `reviews/` 目录）在 witnessloop 契约下的报错 SHALL 被如实记录为**已知红**，SHALL NOT 通过放宽判据、开豁免或删减 `required_artifacts` 的方式使其变绿。阶段 C 之后该红 SHALL 被理解为**拦合入的红**而不再是日志红：任何触达该 change 目录的改动都会被它挡住。该 change 已由 `retire-tui-proposal`（issue #319 PR B）**原地废弃**：用户决定放弃这条从未实现的 proposal，处置为保留目录原样（不删除、不写入、不加目录内标记）+ `docs/adr/ADR-0006-retire-minimal-tui-runtime-view-proposal.md` 留痕 + backlog 移除 + 本规格同步，SHALL NOT 被解释为豁免先例。原地废弃的理由 SHALL 至少包含：witnessloop v1.7.0 对「删除 active change 目录」与「目录内新增标记」都会按 change target 求值，删除在含 code_hits 的实验分支实测 5 项、纯 docs-only 为 3 项；目录内标记 3 项；不得为让其变绿伪造 reviews / manifest。未来 TUI 工作 SHALL 重新立项；任何再次触及该目录的 diff SHALL 先明确处置（重新立项或等 witnessloop 支持删除/退休）。

#### Scenario: 缺证据的 active change 不被豁免

- **WHEN** 对任一 active change（包括未来新立项的 change）求值 witnessloop 契约
- **THEN** 缺少 review manifest、缺少 `stage=grill` 证据的 change SHALL 照常判红
- **AND** policy 的 `required_artifacts` SHALL 保持与 asterwynd 现有 change 目录必需件同形
- **AND** 该红的解除 SHALL 是实现并补证据；或由用户对**该 change** 明确裁决放弃，并以 ADR + backlog 清理留痕（ADR-0006 只记录本 change，SHALL NOT 被读成无留痕豁免或可复用的豁免先例）

#### Scenario: 原地废弃不伪造证据

- **GIVEN** 一个从未实现、没有 `reviews/` 的 active change 被用户决定废弃
- **WHEN** 处置该 change
- **THEN** 处置 SHALL NOT 为它补写 grill / building review / manifest
- **AND** 若删除目录或在目录内加标记会触发 witnessloop 的 change target 求值，则 SHALL 保留目录字节不变，并把废弃决定写入 ADR + backlog + 本规格
- **AND** 未来触及该目录的 diff SHALL 先重新立项或等待 witnessloop 支持删除/退休

#### Scenario: 阶段 C 之后已知红的性质发生迁移

- **WHEN** 阶段 C 把 `gate / check` 勾成 required 之后，评估同一条已知红
- **THEN** 该红 SHALL 从「不挡合入的日志红」变为「**会挡合入的红**」
- **AND** 该迁移 SHALL 被显式记录，SHALL NOT 让「已知红」被读成「可以放着不管」
- **AND** 处置 SHALL 仍是「收尾它」（实现并补证据，或经用户决定废弃 proposal 并留痕）而不是「为它放宽判据或开豁免」

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
- **AND** 在阶段 A 的变更集内，`agent/workflow/**`（当时的模块集合）SHALL 未被修改；其中的 manifest 生成器在本 change 后被删除
- **AND** 任何下掉动作 SHALL 由阶段 C 之后的独立 change 承载

#### Scenario: 退役状态机残留另行处理

- **WHEN** 规划清理 `handoff.json` 及其相关检查（122 个归档中 5 个含 `handoff.json`）
- **THEN** 该清理 SHALL 作为独立后续 change 登记，SHALL NOT 混入影子接入的变更集

### Requirement: review manifest 单套承载：本仓形态退役

接入 witnessloop 后，review manifest SHALL 只有一套要求：witnessloop 形态（`reviews/<stage>.manifest.json`，schema `witnessloop/review-manifest@v1`），由 `witnessloop manifest build` 产出并供 required 的 `gate / check` 消费。asterwynd 形态（`reviews/<phase>-review-manifest.json`，schema `review-manifest/v1`）SHALL NOT 再被流程要求产出，也 SHALL NOT 由本仓 checker 校验；历史文件 SHALL 保持原样，不迁移、不重算、不删除。asterwynd 形态的**生产与写通道 SHALL 已删除**：`agent/workflow/review_manifest.py` SHALL NOT 存在，`workflow_state.py review-manifest` 子命令 SHALL NOT 存在（调用 SHALL 以未知子命令失败），`scripts/flow-policy.json` SHALL NOT 把 `-review-manifest.json` 列为受保护路径。`evidence.review_manifest_glob` SHALL 保持 witnessloop 默认的 `reviews/*.manifest.json`，SHALL NOT 放宽为 `*-manifest.json`。本仓 checker 对 building review 的终结 `## 闭环出口` PASS 判据 SHALL 保留（见 `dev-workflow-state-machine` 的 `Review evidence 与终结 verdict`），该判据不是 manifest 字段校验。

#### Scenario: 本仓形态退役的边界

- **WHEN** 一个实现完成的 change 准备审阅与收尾
- **THEN** `/review-loop` SHALL 只产 witnessloop 形态 manifest（`reviews/<stage>.manifest.json`）
- **AND** 本仓 checker SHALL NOT 因缺少 `reviews/<phase>-review-manifest.json` 报错
- **AND** `agent/workflow/review_manifest.py` SHALL NOT 存在，`workflow_state.py review-manifest` SHALL 被视为未知子命令（非零退出、无副作用）
- **AND** 本仓 SHALL NOT 提供任何生成或校验 asterwynd 形态 manifest 的活通道

#### Scenario: 历史 manifest 保持冻结

- **WHEN** 本 change 之后的 checker 扫描 `openspec/changes/archive/**`
- **THEN** 它 SHALL NOT 校验历史 asterwynd 形态 manifest 的字段、hash 或 git span
- **AND** 历史文件 SHALL 保持原样，SHALL NOT 被迁移、重算或删除
- **AND** 若这些历史文件被修改，`resume_audit` SHALL 按普通文件改动处理（不再把它们当 workflow 管理文件忽略）

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

- **WHEN** 产出 witnessloop 形态 review manifest 或其它 `reviews/` 证据
- **THEN** SHALL 在**所有内容提交之后**产出（witnessloop 的 stale 判定只豁免 `.witnessloop/**`、`<changes_root>/*/reviews/**`、`<changes_root>/*/workflow-events.jsonl`、`archive/**`）
- **AND** 触碰 `docs/**` 与 `openspec/specs/**` 的收尾步骤 SHALL 排在证据产出之前
- **AND** 证据 SHALL 由人在本地产出——CI 的 caller workflow **只做 `check`、不产证据**

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

### Requirement: 阶段 C 翻开关后的 required 形态

接入 witnessloop 的三个阶段（A 影子接入 / B 真实小需求验证 / C 真打开）SHALL 以阶段 C 的形态为**当前**形态。caller workflow SHALL 钉住 witnessloop 的**具体发版 ref**（当前 `v1.7.0`），且 SHALL NOT 依赖 `with: witnessloop-ref:` 另行钉包版本——包 ref 由被复用的 `gate.yml` 自身的 commit 决定。

> **required 集合与其「降级不关闭」不变量不在本规格重复**：`master` 的 required 是哪些、以及「降级为非必过的检查仍须运行」这条约束，SHALL 由 `platform-gate` 能力域规定（该能力域是本仓平台面的唯一规格源）。本规格只规定**接入形态**本身（caller 怎么钉、受管路径的后果、证据形态）。**理由**：同一条规范写两处是未来的漂移点——改一处漏一处不会被任何门禁发现。

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

#### Scenario: 归档产物的证据形态为 witnessloop 单套

- **WHEN** 一个 change 归档
- **THEN** `reviews/` 下 SHALL 存在 witnessloop 形态（`reviews/<stage>.manifest.json`，字段 `stage`）的 `grill` / `grill-adversarial` / `building` 三份 stage 证据
- **AND** SHALL NOT 要求、产出或校验 asterwynd 形态（`reviews/<phase>-review-manifest.json`，字段 `phase`）
- **AND** witnessloop 形态的证据 SHALL 在归档 move **之后**、用**归档目录名**（`<YYYY-MM-DD>-<change-id>`）重建——否则 manifest 里的 `change_id` 与目录名不符
- **AND** `reviews/` 下每一份 `.md` SHALL 被某份 witnessloop 形态 manifest 的 `report_path` 绑定（否则触发孤儿规则）

### Requirement: 翻开关这一动作自身必须具备 change 记录

关闭某个接入阶段的动作 SHALL 由一条 OpenSpec change 承载并归档，SHALL NOT 以「改一个平台配置文件」的形式裸奔。该 change 的 `proposal.md` SHALL 如实写明「行为已先落地」这一事实与其实现凭据（PR / merge sha）。理由：翻开关之后任何触达受管路径的改动都必须挂 change；若翻开关自身的动作不挂 change，则它是在**用自己的豁免**把新规则挡在门外，且会让「哪些检查被降级、每个还在不在跑」失去可追溯的记录。本条 SHALL 有三条边界：① **时效**——记录 SHALL 在行为落地后的**同一收尾批**内归档，未归档前该阶段 SHALL 视为未闭合；② **非先例**——它只约束「关闭接入阶段 / 切换门禁」这类治理动作，SHALL NOT 被类推为常规功能 change 的工作流；③ **不豁免需求先行**——本仓「需求先行」规则要求的是**需求讨论与需求文档**先于实现，本条只承认「记录形态的落地可以滞后」，SHALL NOT 被读成「需求没聊清楚就可以先写实现」。

#### Scenario: 翻开关的记录与落地是两件事

- **WHEN** 阶段 C 的行为先落地、记录后补
- **THEN** 行为落地 SHALL NOT 被读成「记录不必要」——记录 SHALL 仍以独立 change 补齐并归档
- **AND** 该 change 的 `proposal.md` SHALL 如实写明「行为已先落地（含 PR 与 merge sha）、本 change 只做记录与规格对账」，SHALL NOT 把已落地的事实伪装成待实现的需求
