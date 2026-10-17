# dev-workflow-gate 规格 delta

## MODIFIED Requirements

### Requirement: review manifest 单套承载：本仓形态退役

接入 witnessloop 后，review manifest SHALL 只有一套要求：witnessloop 形态（`reviews/<stage>.manifest.json`，schema `witnessloop/review-manifest@v1`），由 `witnessloop manifest build` 产出并供 required 的 `gate / check` 消费。asterwynd 形态（`reviews/<phase>-review-manifest.json`，schema `review-manifest/v1`）SHALL NOT 再被要求、产出或由本仓 checker 校验；历史文件 SHALL 保持原样，不迁移、不重算、不删除。`evidence.review_manifest_glob` SHALL 保持 witnessloop 默认的 `reviews/*.manifest.json`，SHALL NOT 放宽为 `*-manifest.json`。本仓 checker 对 building review 的终结 `## 闭环出口` PASS 判据 SHALL 保留（见 `dev-workflow-state-machine` 的 `Review evidence 与终结 verdict`），该判据不是 manifest 字段校验。`agent/workflow/review_manifest.py` 与其写通道 SHALL 在第二刀之前保留，SHALL NOT 被新 change 的流程要求使用。

#### Scenario: 本仓形态退役的边界

- **WHEN** 一个实现完成的 change 准备审阅与收尾
- **THEN** `/review-loop` SHALL 只产 witnessloop 形态 manifest（`reviews/<stage>.manifest.json`）
- **AND** 本仓 checker SHALL NOT 因缺少 `reviews/<phase>-review-manifest.json` 报错
- **AND** `agent/workflow/review_manifest.py` SHALL 由第二刀处置，本 change SHALL NOT 修改它

#### Scenario: 历史 manifest 保持冻结

- **WHEN** 本 change 之后的 checker 扫描 `openspec/changes/archive/**`
- **THEN** 它 SHALL NOT 校验历史 asterwynd 形态 manifest 的字段、hash 或 git span
- **AND** 历史文件 SHALL 保持原样，SHALL NOT 被迁移、重算或删除

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

