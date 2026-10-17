# dev-workflow-gate 规格 delta

## MODIFIED Requirements

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
