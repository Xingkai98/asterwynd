# platform-gate 规格 delta

## ADDED Requirements

### Requirement: 合入平台闸门

`master` 分支的合入 SHALL 受平台闸门约束：CI required status checks 全绿（`validate` + `benchmark-gate`，strict 模式）、PR conversations 全部 resolve 后才能合入。required approving reviews 当前 SHALL 为 0（单人仓暂缓 approve=1，GitHub 硬限制 PR 作者不能 approve 自己的 PR）；当仓库出现第二个有权限 reviewer（人或独立 bot 身份）时 SHALL 开启并文档化触发条件。

#### Scenario: benchmark-gate 为 required check

- **WHEN** 查看 `master` 分支保护配置
- **THEN** `required_status_checks.strict` SHALL 为 true
- **AND** `required_status_checks.contexts` SHALL 包含 `validate` 与 `benchmark-gate`

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
