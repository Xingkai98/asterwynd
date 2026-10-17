# platform-gate 规格

## Purpose

定义合入平台闸门的能力边界：CI required checks（**唯一** required 为 witnessloop 的 `gate / check`，strict 模式）、PR conversations resolution、review 时机（approve=1 暂缓与触发条件）与平台配置即代码（`scripts/platform-gate.json` 目标状态声明 + `scripts/platform_gate.py` 幂等脚本）。本仓自建的 `validate` / `benchmark-gate` / `windows-platform` 三个 job **照跑但不再拦合并**（阶段 C 翻开关，issue #305，2026-10-17）——**降级，不是关闭**。平台配置的落地（`--apply`）需 admin 权限，在实现 PR 合入后由主 session 执行；本规格用 SHALL（规范性目标）语言描述能力目标，不把「已合入但未 apply」的中间态写成已落地。

## Requirements

### Requirement: 合入平台闸门

`master` 分支的合入 SHALL 受平台闸门约束：CI required status checks 全绿（**唯一** required 为 witnessloop 的 `gate / check`，strict 模式）、PR conversations 全部 resolve 后才能合入。required approving reviews 当前 SHALL 为 0（单人仓暂缓 approve=1，GitHub 硬限制 PR 作者不能 approve 自己的 PR）；当仓库出现第二个有权限 reviewer（人或独立 bot 身份）时 SHALL 开启并文档化触发条件。

> 「不再 required 的检查仍须运行」这条不变量**不写在本条**——它住在本文档的 `### Requirement: 降级为非必过的检查仍须运行`，避免同一条规范在两处各写一遍（那是未来的漂移点）。

#### Scenario: witnessloop 的 gate / check 为唯一 required check

- **WHEN** 查看 `master` 分支保护配置
- **THEN** `required_status_checks.strict` SHALL 为 true
- **AND** `required_status_checks.contexts` SHALL 为 `["gate / check"]`（**只有它**，SHALL NOT 再列出 `validate` 或 `benchmark-gate`）
- **AND** 该值 SHALL 由 `scripts/platform-gate.json` 的 `required_status_checks.contexts` 声明，并随 PR 经评审后由 `--apply` 落地

#### Scenario: 对话必须 resolve 才能合入

- **WHEN** PR 存在未 resolve 的 conversation
- **THEN** GitHub SHALL 阻止合入（required_conversation_resolution 开启）
- **AND** 全部 resolve 后才允许合入

#### Scenario: approve=1 暂缓与触发条件

- **WHEN** 查看 required_pull_request_reviews 配置
- **THEN** `required_approving_review_count` SHALL 为 0
- **AND** 配置声明 SHALL 记录触发条件（出现第二个有权限 reviewer 时开启，改配置 + 重新 apply）

### Requirement: 平台配置即代码

平台闸门的目标状态 SHALL 由 `scripts/platform-gate.json` 声明，并由 `scripts/platform_gate.py` 提供 `--apply`（幂等设置）与 `--verify`（漂移检测）两个命令。配置变更 SHALL 走 git PR 流程 review，不直接手工在 GitHub UI 修改。

#### Scenario: apply 幂等设置

- **WHEN** 运行 `python scripts/platform_gate.py --apply`
- **THEN** 系统 SHALL 把目标状态声明应用到 GitHub branch protection
- **AND** 系统 SHALL 执行 GET-modify-PUT：读取当前 protection，用目标声明字段覆盖，剔除只读派生字段，显式传 `restrictions: null`，构造包含四必需字段（enforce_admins / required_pull_request_reviews / required_status_checks / restrictions）的完整 payload
- **AND** 未声明的其他保护字段 SHALL 保留自 GET（不重置）
- **AND** 重复运行 SHALL 无副作用（目标状态已是当前状态时无变更）

#### Scenario: verify 检测漂移

- **WHEN** 运行 `python scripts/platform_gate.py --verify`
- **THEN** 系统 SHALL 拉取当前 protection 实况并与目标状态归一化比对
- **AND** 忽略只读派生字段（url / contexts_url / checks 数组等）
- **AND** 配置一致时 SHALL exit 0，存在漂移时 SHALL exit 1 并输出逐字段 diff
- **AND** verify SHALL 只读不写

#### Scenario: 配置错误 fail-closed

- **WHEN** 目标 JSON schema 非法，或 `gh` 不可用 / 认证失败 / API 报错
- **THEN** 脚本 SHALL 明确报错并 exit 2，不执行部分写入

### Requirement: 平台闸门复用 GitHub branch protection 语义

平台闸门 SHALL 复用 GitHub branch protection REST API 语义（required_status_checks / required_conversation_resolution / required_pull_request_reviews / enforce_admins），并遵守「PR 作者不能 approve 自己的 PR」的平台限制，不得另起一套不兼容的合入门禁协议。

#### Scenario: 平台配置走 PR review

- **GIVEN** 需要修改 `master` 分支保护配置
- **WHEN** 修改 `scripts/platform-gate.json` 并创建 PR
- **THEN** 配置变更 SHALL 随 PR 经 CI 验证后合入
- **AND** 合入后由持 admin 权限的执行者运行 `--apply` 落地，并用 `--verify` 复核
- **AND** `--apply` SHALL NOT 在同一 PR 合入**之前**执行——它是仓库级操作，会把该 PR 自身的 conversation resolution 闸门一并锁住

### Requirement: 降级为非必过的检查仍须运行

当某个检查从 required 降级为非必过时，该检查 SHALL 继续运行，SHALL NOT 被停用、删除或削弱为不产出结论的形态。降级改变的是「它的结论会不会阻止合入」，SHALL NOT 改变「它会不会跑」。具体到本仓：`validate`（pytest + OpenSpec strict validate + artifact checker）、`benchmark-gate`（gate-smoke 基准回归）与 `windows-platform` 三个 job SHALL 继续由 `.github/workflows/ci.yml` 在每个 PR 上运行。理由：这些检查承载的项目规则（Reference Implementation Research、Impact Analysis、benchmark 回归、归档点完成度门、backlog 一致性等）没有 witnessloop 侧的替代物——把它们关掉是门禁的**净损失**，而不是「切换门禁」。

#### Scenario: 降级后仍产出结论

- **WHEN** 某检查被移出 `required_status_checks.contexts`
- **THEN** 它 SHALL 仍在每个 PR 上被触发
- **AND** 它的结论 SHALL 在 PR 的 checks 列表里可见
- **AND** 它 SHALL NOT 被删除、被注释掉、或被 `if: false` / `continue-on-error` 之类的开关改成不阻塞且不产结论

#### Scenario: 三个 job 与 required 的判定源相互独立

- **WHEN** 任一 PR 触达 `master`
- **THEN** `validate` / `benchmark-gate` / `windows-platform` 三个 job SHALL 照常被触发并产出结论
- **AND** 它们的结论 SHALL NOT 决定 PR 能否合入——合入结论由 `gate / check` 单独决定

#### Scenario: 「CI 绿」不等于「项目规则已满足」

- **WHEN** 一个 PR 的 required check 判绿而某个已降级的检查判红
- **THEN** 该 PR SHALL 仍可合入（这是降级的设计后果）
- **AND** 该后果 SHALL 被文档化到 `AGENTS.md` 与 `docs/development-guide.md`，使读者不会把「CI 绿」读成「项目规则已满足」

