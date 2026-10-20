# dev-workflow-gate 规格 delta

## MODIFIED Requirements

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
