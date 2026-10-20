# dev-workflow-gate 规格

## Purpose

定义开发流程门禁的**承载边界**：哪些门禁由外部工具 witnessloop 承载、哪些由本仓的瘦 checker / Bash guard / platform gate 承载，以及从自建切换到接入 witnessloop 的三阶段（A 影子接入 / B 真实小需求验证 / C 真打开）各自的约束。

**本仓已走到阶段 C（真打开，2026-10-17）**：接入产物已落进仓库——`.witnessloop/policy.json`（定制 policy）、`.witnessloop/init-manifest.json`（init 台账）、`.github/workflows/witnessloop.yml`（caller，钉 `@v1.7.1`）、`.github/witnessloop-tests.txt`（测试执行点）；`master` 的唯一 required check 是 `gate / check`。旧门禁主体（`workflow_state.py`、`agent/workflow/*`、`flow-policy.json`、`workflow_methods.json`、旧 `workflow_guard.py`）已删除。现行形态是：witnessloop 承载流程骨架；`scripts/check_openspec_artifacts.py` 只承载 6 条项目规则（RIR / Impact Analysis / benchmark smoke / tasks 与归档点完成度 / backlog 一致性 / building review 的 `## 闭环出口` PASS）；`scripts/bash_write_guard.py` 承载本地 Bash 写前拦截；`scripts/platform_gate.py` 保留 branch protection 的配置即代码与漂移检测（见 `platform-gate` 能力域）。`master` 的 required 集合与其「降级不关闭」不变量由 `platform-gate` 能力域规定，本规格不重复。

**阶段划分**：A 影子接入（只跑不拦）→ B 用一个真实小需求在新流程上跑一遍（取得「值不值得真打开」的判断依据）→ C 真打开（勾 required，由独立 change 承载）。阶段 A 的实测证据见已归档 change `openspec/changes/archive/2026-10-13-witnessloop-adoption/reviews/acceptance-stage-a.md`。

本规格用规范性语言描述**目标与边界**。

## Requirements

### Requirement: 流程骨架与项目规则的承载分工

接入 witnessloop 后，**流程骨架**（change 契约、review manifest 的证据绑定、grill / grill-adversarial / building 三类审阅证据、受保护路径的写入解释、本地写码前 guard、CI required check 形态、测试执行点）SHALL 由 witnessloop 承载；**项目规则**（Reference Implementation Research、Impact Analysis、benchmark smoke 任务要求、tasks 完成度、归档点完成度门、backlog 一致性、building review 的 `## 闭环出口` PASS 判据、本地 Bash 写前拦截、合入平台闸门）SHALL 保留在本仓。流程事件投影 SHALL 已退役，不再是项目规则的一部分。

项目规则的机械承载 SHALL 收敛为三个入口：`scripts/check_openspec_artifacts.py`（六条项目规则）、`scripts/bash_write_guard.py`（本地 Bash 写前拦截）与 `scripts/platform_gate.py`（branch protection 配置即代码）。`scripts/workflow_state.py`、`agent/workflow/*`、`scripts/flow-policy.json`、`scripts/workflow_methods.json` 与旧 `scripts/workflow_guard.py` SHALL NOT 存在。

#### Scenario: 项目规则不随接入外迁

- **WHEN** 完成本仓旧门禁主体退役
- **THEN** 本仓 SHALL 继续维护 `Reference Implementation Research`、`Impact Analysis`、benchmark smoke 任务、tasks / 归档点完成度、backlog 一致性与 building review `## 闭环出口` 的机械检查
- **AND** 上述检查 SHALL 由瘦 checker 承载，判据 SHALL 与退役前一致
- **AND** 缺什么能力 SHALL 去 witnessloop 仓库立 issue，而不是在本仓另起一套协议

#### Scenario: 事件投影不再是项目规则

- **WHEN** 检查本仓的开发流程能力
- **THEN** `scripts/workflow_state.py`、`agent/workflow/*` 与 `flow status` SHALL NOT 存在
- **AND** 历史 `workflow-events.jsonl` SHALL 作为只读数据保留，SHALL NOT 被重算、删除或迁移

#### Scenario: 局部应用成熟模式而非另立协议

- **WHEN** 决定让某个自建检查改由 witnessloop 承载
- **THEN** 该检查 SHALL 映射到 witnessloop 既有的 stage 名与事件语义（`grill` / `grill-adversarial` / `building`；`event_type` / `artifact_path` / `reason` / `approved_by`）
- **AND** SHALL NOT 引入与 witnessloop 不兼容的第二套门禁协议
### Requirement: 接入 witnessloop 前的定制 policy 前置

向本仓接入 witnessloop 时，接入命令 SHALL 通过 `witnessloop init --policy <seed>` 提供一份**完整**的定制 policy，SHALL NOT 使用 witnessloop 出厂 policy 直接接入。理由：出厂 `require_change_for` 对 `agent/`、`scripts/`、`web/` 零命中，而 witnessloop 的 `building` 门禁与 `grill-adversarial` 门禁**共用同一条 `code_hits` 触发**，用出厂 policy 接入会使这两个核心门禁静默不触发。policy seed SHALL 是仓外临时文件、SHALL NOT 进入版本控制；入库的产物 SHALL 是 init 写出的 `.witnessloop/policy.json`。

旧门禁退役后，`.witnessloop/policy.json` SHALL 是本仓受保护路径与受管路径的**唯一策略源**：CI 的受保护写入解释由 witnessloop 读取它，本地 Bash guard 也读取它；`scripts/flow-policy.json` SHALL NOT 存在。

#### Scenario: 用出厂 policy 接入会被判不合规

- **WHEN** 以出厂 `require_change_for`（`src` / `lib` / `app` / `apps` / `packages` / `server` / `cmd` / `internal`）接入本仓
- **THEN** 触达 `agent/**`、`scripts/**`、`web/**` 的 PR SHALL 不产生 `code_hits`
- **AND** `building` 与 `grill-adversarial` 两条 stage 判定 SHALL NOT 被触发（接入名存实亡）

#### Scenario: 定制 policy 的四个字段落定

- **WHEN** 定稿 policy seed
- **THEN** `evidence.review_manifest_glob` SHALL 保持 witnessloop 默认的 `reviews/*.manifest.json`（**不放宽**成 `*-manifest.json`）
- **AND** `evidence.protected_write_event_types` SHALL 为 `["current_spec_synced", "backlog_updated", "change_archived", "protected_artifact_explained"]`
- **AND** `require_change_for` SHALL 为 `["agent/**", "scripts/**", "web/**"]`，SHALL NOT 包含 benchmark 目录、`tests/**`、`docs/**`
- **AND** `protected_paths` SHALL 为 `["openspec/specs/**", ".witnessloop/**", "docs/known-issues.md", "docs/known-debt.md", "docs/openspec-change-backlog.md"]`
- **AND** `protected_paths` SHALL NOT 包含 `openspec/changes/archive/**`
- **AND** 测试执行点 SHALL 为 `uv run --extra dev pytest -q` 一条命令（`ci.yml` 的编码 warn-as-error 变体、`openspec validate`、瘦 checker SHALL NOT 并入执行点）
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

接入 witnessloop 时记录的「本地拦截面收窄」SHALL 已被本 change 补回 Bash 面：本地写前拦截 SHALL 由两个独立 hook 分工——witnessloop plugin 的 `guard`（matcher `Write|Edit`）负责代码写入前的 change / grill 证据检查，本仓 `scripts/bash_write_guard.py`（matcher `Bash`）负责 Bash 命令中的写操作。旧 `scripts/workflow_guard.py` 的 `Write|Edit` 面 SHALL NOT 重复实现；其 Bash 面 SHALL 由新 guard 以更窄、可测试的判据承接。

写进文档的 SHALL 包括：两个 hook 的安装方式、各自覆盖面、Bash guard 的已知残余绕过面，以及「本地 hook 是防遗忘 / 本地 checkpoint，CI `gate / check` 才是最终防线」这一定位。

#### Scenario: 两个守卫分工而不重复

- **WHEN** Agent 使用 Write/Edit 写代码路径
- **THEN** witnessloop plugin guard SHALL 负责 change / grill 证据检查
- **AND** `scripts/bash_write_guard.py` SHALL NOT 处理该工具调用

#### Scenario: Bash 面的退步已被补回

- **WHEN** Agent 使用 Bash 重定向写入 `agent/**`、`scripts/**`、`web/**` 或受保护 artifact
- **THEN** 本仓 Bash guard SHALL 在命令执行前阻断
- **AND** 普通只读命令 SHALL 放行
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

以下检查 SHALL 保留在本仓、SHALL NOT 迁入 witnessloop：RIR、Impact Analysis、benchmark smoke 任务要求、tasks 完成度、归档点完成度门、backlog 一致性、building review 的 `## 闭环出口` PASS 判据、`scripts/platform_gate.py` 平台闸门，以及 Bash 写前拦截。witnessloop 承载的是**流程骨架**（change 契约 / 证据绑定 / grill / grill-adversarial / building / 受保护写入 / 本地 `Write|Edit` guard / 测试执行点）；本仓保留的是**项目规则**。流程事件投影 SHALL 已退役，不属于保留项。

#### Scenario: 六条项目规则仍有机械实现

- **WHEN** 检查本仓现行 checker
- **THEN** `scripts/check_openspec_artifacts.py` SHALL 实现 RIR、Impact Analysis、benchmark smoke、tasks / 归档点完成度、backlog 一致性与 building review `## 闭环出口` 六条规则
- **AND** 判据 SHALL 与退役前实现一致，SHALL NOT 因重写而放宽

#### Scenario: 下掉旧件由独立 change 承载

- **WHEN** 下掉与 witnessloop 重合的旧件
- **THEN** 该动作 SHALL 由独立 change 承载，并保留 witnessloop 未覆盖的项目规则
- **AND** SHALL NOT 把「删除重复实现」扩大为「删除项目规则」
### Requirement: review manifest 单套承载：本仓形态退役

接入 witnessloop 后，review manifest SHALL 只有一套要求：witnessloop 形态（`reviews/<stage>.manifest.json`，schema `witnessloop/review-manifest@v1`），由 `witnessloop manifest build` 产出并供 required 的 `gate / check` 消费。asterwynd 形态（`reviews/<phase>-review-manifest.json`，schema `review-manifest/v1`）SHALL NOT 再被流程要求产出，也 SHALL NOT 由本仓 checker 校验；历史文件 SHALL 保持原样，不迁移、不重算、不删除。

asterwynd 形态的**生产与写通道 SHALL 已删除**：`agent/workflow/review_manifest.py` SHALL NOT 存在，`workflow_state.py review-manifest` 子命令 SHALL NOT 存在，`scripts/flow-policy.json` SHALL NOT 存在。`evidence.review_manifest_glob` SHALL 保持 witnessloop 默认的 `reviews/*.manifest.json`，SHALL NOT 放宽为 `*-manifest.json`。瘦 checker 对 building review 的终结 `## 闭环出口` PASS 判据 SHALL 保留，该判据不是 manifest 字段校验。

#### Scenario: 本仓形态退役的边界

- **WHEN** 一个实现完成的 change 准备审阅与收尾
- **THEN** `/review-loop` SHALL 只产 witnessloop 形态 manifest（`reviews/<stage>.manifest.json`）
- **AND** 瘦 checker SHALL NOT 因缺少 `reviews/<phase>-review-manifest.json` 报错
- **AND** 本仓 SHALL NOT 提供任何生成或校验 asterwynd 形态 manifest 的活通道

#### Scenario: 历史 manifest 冻结

- **WHEN** 检查历史归档中的 `*-review-manifest.json`
- **THEN** 它们 SHALL 保持原样，不迁移、不重算、不删除
- **AND** 本仓 checker SHALL NOT 校验它们的字段、hash 或 git span

#### Scenario: glob 不放宽的理由可复核

- **WHEN** 决定 `review_manifest_glob` 取值
- **THEN** 该值 SHALL 为 `reviews/*.manifest.json`
- **AND** 放宽为 `*-manifest.json` SHALL 被拒绝——它会把本仓 schema 的 manifest 卷入候选集：witnessloop 按路径字典序取第一份同 stage manifest 作证据（可错绑悬空报告），同时逐份校验所有匹配文件（任一坏文件独立报红）

#### Scenario: `reviews/` 必须处于一致状态（孤儿规则的激活条件）

- **WHEN** 决定是否在 change 的 `reviews/` 下落 witnessloop 形态 manifest
- **THEN** SHALL 遵守「**要么给每份报告都建 manifest，要么一份都别落**」
- **AND** 依据 SHALL 是实测的激活条件：glob 匹配 0 份时 witnessloop 的 manifest 循环早退、孤儿规则不执行；一旦落了任意一份 witnessloop 形态 manifest，`reviews/**/*.md` 里每一份未绑定 `report_path` 的报告都判孤儿
- **AND** 只落一部分 manifest 的中间态 SHALL 被拒绝——它比不落更红

#### Scenario: 证据的 stale 顺序约束

- **WHEN** 产出 witnessloop 形态 review manifest 或其它 `reviews/` 证据
- **THEN** SHALL 在**所有内容提交之后**产出（witnessloop 的 stale 判定只豁免 `.witnessloop/**`、`<changes_root>/*/reviews/**`、`<changes_root>/*/workflow-events.jsonl`、`archive/**`）
- **AND** 触碰 `docs/**` 与 `openspec/specs/**` 的收尾步骤 SHALL 排在证据产出之前
- **AND** 证据 SHALL 由人在本地产出——CI 的 caller workflow 只做 `check`、不产证据

#### Scenario: building review 的终结判据仍被机械检查

- **WHEN** 一个非 docs + 有 spec delta 的 change 任务全勾或到达归档点
- **THEN** `reviews/building-review.md` SHALL 存在，其 `## 闭环出口` 首个非空行 SHALL 为 PASS
- **AND** terminal `BLOCKED` / `CHANGES_REQUESTED` SHALL 始终判红
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

本仓 SHALL 允许两个 PreToolUse 守卫并存：witnessloop plugin 的 `guard`（`Write|Edit`）与 `scripts/bash_write_guard.py`（`Bash`）。两者在同一工具调用上 SHALL NOT 重叠；hook 的合并/串行语义与拦截提示归属 SHALL 在安装文档中写明，并至少用一次本地实测确认「两个 hook 同时启用时，Write/Edit 走 witnessloop、Bash 走本仓 guard」。

#### Scenario: 两 hook 同时启用

- **WHEN** 两个 PreToolUse hook 都安装在同一 Claude Code 环境中
- **THEN** `Write|Edit` 调用 SHALL 由 witnessloop guard 求值
- **AND** `Bash` 调用 SHALL 由本仓 Bash guard 求值
- **AND** 任一 hook 的阻断 SHALL 阻止对应工具调用

#### Scenario: 未知语义不靠推理

- **WHEN** 维护者安装或升级任一 hook
- **THEN** 合并/串行语义与提示归属 SHALL 有本地实测记录
- **AND** SHALL NOT 仅以「两个 guard 都生效」的推理代替实测
### Requirement: 阶段 C 翻开关后的 required 形态

接入 witnessloop 的三个阶段（A 影子接入 / B 真实小需求验证 / C 真打开）SHALL 以阶段 C 的形态为**当前**形态。caller workflow SHALL 钉住 witnessloop 的**具体发版 ref**（当前 `v1.7.1`），且 SHALL NOT 依赖 `with: witnessloop-ref:` 另行钉包版本——包 ref 由被复用的 `gate.yml` 按 ref 形态推导：**tag** 取 `job.workflow_ref` 的 `refs/tags/<tag>`（annotated tag 的 `job.workflow_sha` 是 tag object，不是 commit，uv 的新版本会拒绝；精确阈值见上游 issue #42）；**分支 / commit pin** 取 `job.workflow_sha`。应急 commit pin SHALL NOT 构成稳态：它 SHALL 在同一收尾批内由正规 change 回钉到已发布的 tag ref，并同步 `.witnessloop/init-manifest.json` 台账。

> **required 集合与其「降级不关闭」不变量不在本规格重复**：`master` 的 required 是哪些、以及「降级为非必过的检查仍须运行」这条约束，SHALL 由 `platform-gate` 能力域规定（该能力域是本仓平台面的唯一规格源）。本规格只规定**接入形态**本身（caller 怎么钉、受管路径的后果、证据形态）。**理由**：同一条规范写两处是未来的漂移点——改一处漏一处不会被任何门禁发现。

#### Scenario: required 只剩 witnessloop 的 gate / check

- **WHEN** 查看阶段 C 之后 `master` 的分支保护配置
- **THEN** `required_status_checks.contexts` SHALL 为 `["gate / check"]`（该取值与其不变量由 `platform-gate` 能力域规定，本规格只断言阶段 C 之后的形态）
- **AND** 本仓自建门禁 SHALL 全部退出 required（降级，不是关闭）

#### Scenario: caller 钉住的 ref 同时决定包版本

- **WHEN** 检查 `.github/workflows/witnessloop.yml`
- **THEN** 该文件的 `uses:` SHALL 钉住具体发版 ref（形如 `Xingkai98/witnessloop/.github/workflows/gate.yml@v1.7.1`），SHALL NOT 用滚动 tag（`@v1`）、分支名或长期 commit pin
- **AND** caller SHALL NOT 出现 `with: witnessloop-ref:`——包 ref 的缺省由被复用 `gate.yml` 的 ref 推导（tag 用 `job.workflow_ref` 的 tag ref，分支 / commit pin 用 `job.workflow_sha`；上游 issue #30 / #42 的修复），升级动作 SHALL 是 `witnessloop init --gate-ref <新 ref>` 一处改动（本仓是定制 policy 仓，命令 SHALL 同时带 `--policy .witnessloop/policy.json`）
- **AND** 升级 SHALL 同时重写 caller 与同步 `.witnessloop/init-manifest.json` 台账（该动作幂等），SHALL NOT 只改其中一边

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

#### Scenario: 应急 commit pin 必须回钉

- **GIVEN** 上游发版出现故障，接入方为解除 `gate / check` 硬红而临时把 caller 钉到 commit
- **WHEN** 上游发布包含修复的新 tag
- **THEN** 接入方 SHALL 由正规 change 把 caller 回钉到新 tag，并用 `witnessloop init --gate-ref <新 tag> --policy .witnessloop/policy.json` 同步台账（本仓为定制 policy 仓，缺 `--policy` 会先写后失败）
- **AND** 该 change SHALL 补 `.witnessloop/**` 的受保护写入解释事件
- **AND** 合入后的 `gate / check` 日志 SHALL 证明包 ref 来自 tag ref（`refs/tags/<tag>`），不是 tag object sha 或 commit pin

### Requirement: 翻开关这一动作自身必须具备 change 记录

关闭某个接入阶段的动作 SHALL 由一条 OpenSpec change 承载并归档，SHALL NOT 以「改一个平台配置文件」的形式裸奔。该 change 的 `proposal.md` SHALL 如实写明「行为已先落地」这一事实与其实现凭据（PR / merge sha）。理由：翻开关之后任何触达受管路径的改动都必须挂 change；若翻开关自身的动作不挂 change，则它是在**用自己的豁免**把新规则挡在门外，且会让「哪些检查被降级、每个还在不在跑」失去可追溯的记录。本条 SHALL 有三条边界：① **时效**——记录 SHALL 在行为落地后的**同一收尾批**内归档，未归档前该阶段 SHALL 视为未闭合；② **非先例**——它只约束「关闭接入阶段 / 切换门禁」这类治理动作，SHALL NOT 被类推为常规功能 change 的工作流；③ **不豁免需求先行**——本仓「需求先行」规则要求的是**需求讨论与需求文档**先于实现，本条只承认「记录形态的落地可以滞后」，SHALL NOT 被读成「需求没聊清楚就可以先写实现」。

#### Scenario: 翻开关的记录与落地是两件事

- **WHEN** 阶段 C 的行为先落地、记录后补
- **THEN** 行为落地 SHALL NOT 被读成「记录不必要」——记录 SHALL 仍以独立 change 补齐并归档
- **AND** 该 change 的 `proposal.md` SHALL 如实写明「行为已先落地（含 PR 与 merge sha）、本 change 只做记录与规格对账」，SHALL NOT 把已落地的事实伪装成待实现的需求

### Requirement: 瘦项目规则 checker 承载六条机械判据

`scripts/check_openspec_artifacts.py` SHALL 只实现六条项目规则，并 SHALL 保持旧实现的判据强度：

1. **RIR**：非 docs change SHALL 在 `proposal.md` 或 `design.md` 含 `## Reference Implementation Research`，且非占位；`research_tier` SHALL 为 `full|light|exempt`，`status` SHALL 为 `enabled|disabled`，`reason` SHALL 非空；enabled 时 findings 与 design impact SHALL 非空，full 档另需 research questions；tasks 全勾或归档点时 SHALL 启用内容门槛（自认未完成短语、tier 与 status 组合、exempt 理由证据）。
2. **Impact Analysis**：非 docs change SHALL 在 `proposal.md` 或 `design.md` 含非占位的 `## Impact Analysis`。
3. **benchmark smoke**：proposal 命中 `agent-runtime` / `benchmark` / `coding-tools` / `tool-system` / `workspace-safety` 能力或 `agent/loop.py` / `agent/tools/` / `agent/workspace_policy.py` / `benchmarks/` 代码模式时，`tasks.md` **文本**中 SHALL 同时出现 benchmark 与 smoke（与旧实现一致，不要求同一行或同一条目）。
4. **tasks / 归档点完成度**：本次 diff 以 `A` 或 `R` 触及的归档路径中，任何**非日期前缀**的归档目录 SHALL 判红；日期前缀目录仅在**base 树不存在**时被当作本次新归档并评估完成度（往既有归档补文件不得触发）。新归档的 `tasks.md` SHALL 至少有一条已勾选任务，未勾选任务 SHALL 标注 `(post-merge)`（容忍编号 / 粗体在前、全半角括号、大小写变体）；缺 `tasks.md`、无 checkbox 行、全部未勾选 SHALL 判红。非 docs + `DESIGN_TYPES`（feature/refactor/process）+ spec delta 的新归档 SHALL 另有 `reviews/grill-design.md`（`## Confirmed Decisions` ≥3 条，且 `## Open Questions` 每项都有非占位 `## User Confirmation`）与 `reviews/grill-adversarial.md`；该判据与 witnessloop 的 stage 触发面无关（witnessloop 只在 `code_hits` 非空时要求 stage）。
5. **backlog 一致性**：`docs/openspec-change-backlog.md` SHALL NOT 引用已归档 change，也 SHALL NOT 引用不存在的 active change。
6. **building review `## 闭环出口`**：完成面（非 docs + spec delta + tasks 全勾，或新归档的非 docs + spec delta）SHALL 要求 `reviews/building-review.md` 存在；宽触发（报告存在）SHALL 解析首个非空行的终结 token，terminal `BLOCKED` / `CHANGES_REQUESTED` SHALL 判红；`PASSED`、重复出口、`|` / `｜` 多出口歧义、fenced code block 内模板均 SHALL 按退役前判据处理。

CLI SHALL 保留 `--changes-root`、`--change`、`--backlog`、`--base-ref`、`--skip-backlog`、`--require-base`；exit 语义 SHALL 为 `0` 通过 / `1` 规则违规 / `2` 根缺失或用法错误。

#### Scenario: 六条规则各有正反例

- **WHEN** 对任一规则构造一组合规输入与一组违规输入
- **THEN** 合规输入 SHALL exit 0
- **AND** 违规输入 SHALL exit 1 并输出可定位的错误

#### Scenario: 归档点与 active 的触发矩阵

- **WHEN** 一个新归档目录在本 PR 新建
- **THEN** checker SHALL 在归档目录上评估 RIR 内容门槛、building review、tasks 完成度与 grill 证据
- **AND** 往既有归档目录补文件 SHALL NOT 触发该评估
- **AND** Impact Analysis 与 benchmark smoke SHALL 只在 active change 上评估（沿用退役前矩阵）

#### Scenario: 非代码 change 的 grill 证据不被静默放宽

- **GIVEN** 一个 `primary: process` 且只修改 `openspec/specs/**` 与 `docs/**` 的 change（没有 `code_hits`）
- **WHEN** 它到达归档点且声明了 spec delta 与 `process` 类型
- **THEN** 瘦 checker SHALL 要求 `reviews/grill-design.md` 与 `reviews/grill-adversarial.md`
- **AND** witnessloop 的 `grill` / `grill-adversarial` stage 不触发 SHALL NOT 被当作豁免理由

#### Scenario: 判据不放宽

- **WHEN** 重写 checker
- **THEN** 旧实现已覆盖的边界（`PASSED`、全角符号、多出口、`(post-merge)` 变体、`AR` 重命名、base 树已有归档）SHALL 继续被测试覆盖
- **AND** SHALL NOT 以「简化」为由删掉任一判据

### Requirement: Bash 写前拦截只覆盖 Bash 面

本仓 SHALL 提供 `scripts/bash_write_guard.py` 作为 PreToolUse hook，只处理 `Bash` 工具调用。它 SHALL 以 quote-aware 的方式解析命令中的**直接文件写操作**（重定向、`cp` 目的参数、`rsync` 目的参数、`mv`、`tee`、`dd of=`、`sed -i`、`install`、`rm`、`touch`、`mkdir`、`ln`、`truncate`、`chmod`、`chown`、`python -c` 写调用、`curl -o` / `wget -O` 等），并在写目标命中以下任一路径集时以 exit 2 阻断：

- **受管路径**：`.witnessloop/policy.json` 的 `require_change_for`（当前 `agent/**`、`scripts/**`、`web/**`）；
- **受保护 artifact**：`.witnessloop/policy.json` 的 `protected_paths`。

VCS 命令 SHALL 分两类处理：
- `git rm` / `git mv` SHALL 放行——Write/Edit 无法删除或改名文件，若连它们都拦，文件和目录的
  删除就没有合法通道；
- `git checkout -- <path>` / `git restore <path>` SHALL 在显式路径命中受管/受保护时阻断；
  `git apply` SHALL 阻断，除非是 `--check` / `--stat` 等只读形态；
- `git merge` / `git rebase` / `git cherry-pick` / `git stash` / `git am` SHALL 被登记为**已知的
  内容写入绕过面**（它们可以改写受管路径，guard 无法可靠解析目标，CI 兜底），SHALL NOT 被描述为
  「簿记操作」。

普通只读命令（`ls`、`grep`、`cat`、`git status` 等）SHALL 放行。路径 SHALL 归一化（统一分隔符、去 `./`、解析 `..`、repo 内绝对路径转相对）；policy glob SHALL 按 witnessloop 同款语义匹配（`**` 跨目录、`*` 不跨 `/`、精确文件名），`scriptsfoo/` SHALL NOT 命中 `scripts/**`。guard SHALL 跟踪 `cd` 链并递归解析 `bash -c` / `sh -c` / `eval` 与命令替换。引号内的写样式文本、`cp` 的源参数、`>/dev/null`、`2>&1` 与 here-doc 数据 SHALL NOT 触发阻断。policy 缺失或损坏时 SHALL 使用内嵌默认表继续判定，SHALL NOT 因加载失败直接放行；内嵌默认表 SHALL 与 `.witnessloop/policy.json` 当前值一致。脚本内部异常 SHALL fail-open（exit 0 + stderr 警告），因为它是本地 checkpoint，最终防线是 CI。

已知无法静态判定的绕过面（变量展开、符号链接、`find -exec` / `xargs` 路径、shell 函数 / alias、进程替换、VCS 内容写入（`git merge` / `rebase` / `cherry-pick` / `stash` / `am`））SHALL 在测试与 `docs/development-guide.md` 中如实登记，SHALL NOT 声称 guard 提供防对抗保证。

hook 示例配置 SHALL 以可提交文件提供（`scripts/bash_write_guard.example.json`），安装说明 SHALL 写入版本控制内的文档；`.claude/` SHALL 保持被 gitignore，SHALL NOT 进入版本控制。

#### Scenario: 常见写操作被拦

- **WHEN** Bash 命令是 `echo x > agent/y`、`cp x agent/y`、`tee docs/known-debt.md`、`sed -i ... agent/loop.py` 或 `rm scripts/foo.py`
- **THEN** guard SHALL exit 2 并在 stderr 给出命中的目标
- **AND** 命令 SHALL NOT 被执行

#### Scenario: 只读命令放行

- **WHEN** Bash 命令是 `ls agent`、`grep -n foo agent/loop.py`、`cat docs/known-debt.md` 或 `git status`
- **THEN** guard SHALL exit 0

#### Scenario: 写样式文本与源参数不误伤

- **WHEN** Bash 命令是 `rg 'echo > agent/y'`、`git commit -m "cp x agent/y"`、
  `cp agent/x /tmp/y`、`sed -i 's|agent/|x|' docs/y`、`echo ok >/dev/null`、`cmd 2>&1` 或
  把 `rm agent/x` 当 here-doc 数据
- **THEN** guard SHALL exit 0（不因引号内文本、源参数、fd 复制或数据内容误伤）

#### Scenario: VCS 删除/改名放行，内容改写被拦或登记

- **WHEN** Bash 命令是 `git rm scripts/old.py` 或 `git mv scripts/a.py scripts/b.py`
- **THEN** guard SHALL exit 0（删除/改名有合法通道）
- **WHEN** Bash 命令是 `git restore agent/loop.py`、`git checkout -- agent/loop.py` 或
  `git apply /tmp/patch`
- **THEN** guard SHALL exit 2
- **AND** `git merge` / `rebase` / `cherry-pick` / `stash` / `am` SHALL 被文档登记为已知内容写入
  绕过面（不是「簿记操作」）

#### Scenario: 绕过面如实登记

- **WHEN** 维护者查阅 Bash guard 的保证强度
- **THEN** 文档与测试 SHALL 列出已知残余绕过面
- **AND** SHALL NOT 把本地 guard 写成防对抗或替代 CI 的门禁

### Requirement: 流程事件投影退役且历史事件保留

本仓 SHALL NOT 再提供流程事件投影能力：`scripts/workflow_state.py`、`agent/workflow/*`、`flow status` 子命令与 `workflow-state.json` 的生产通道 SHALL 不存在。历史 `workflow-events.jsonl` SHALL 作为只读数据保留在 active 与归档 change 目录中，供 witnessloop 的受保护写入匹配与历史审计使用；SHALL NOT 重算、删除或迁移。`handoff.json` / `workflow-state.json` 既存文件 SHALL 作为历史投影保留，不再被更新。

#### Scenario: 投影 CLI 不存在

- **WHEN** 运行 `python scripts/workflow_state.py flow status`
- **THEN** 该文件 SHALL 不存在，调用失败
- **AND** 文档 SHALL NOT 再把 `flow status` 作为可用命令

#### Scenario: 历史事件文件保留

- **WHEN** 检查 `openspec/changes/**/workflow-events.jsonl`
- **THEN** 既有文件 SHALL 保持原样
- **AND** witnessloop 的受保护写入解释事件 SHALL 继续可用
