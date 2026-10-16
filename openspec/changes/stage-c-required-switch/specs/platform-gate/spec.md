# platform-gate 规格 delta

## MODIFIED Requirements

### Requirement: 合入平台闸门

`master` 分支的合入 SHALL 受平台闸门约束：CI required status checks 全绿（**唯一** required 为 witnessloop 的 `gate / check`，strict 模式）、PR conversations 全部 resolve 后才能合入。本仓自建的 `validate`（pytest + OpenSpec strict validate + artifact checker）、`benchmark-gate`（gate-smoke 基准回归）与 `windows-platform` 三个 job SHALL 继续由 `.github/workflows/ci.yml` 在每个 PR 上运行，SHALL NOT 因其不再是 required 而被停用、删除或改成不阻塞的形状。required approving reviews 当前 SHALL 为 0（单人仓暂缓 approve=1，GitHub 硬限制 PR 作者不能 approve 自己的 PR）；当仓库出现第二个有权限 reviewer（人或独立 bot 身份）时 SHALL 开启并文档化触发条件。

#### Scenario: witnessloop 的 gate / check 为唯一 required check

- **WHEN** 查看 `master` 分支保护配置
- **THEN** `required_status_checks.strict` SHALL 为 true
- **AND** `required_status_checks.contexts` SHALL 为 `["gate / check"]`（**只有它**，SHALL NOT 再列出 `validate` 或 `benchmark-gate`）
- **AND** 该值 SHALL 由 `scripts/platform-gate.json` 的 `required_status_checks.contexts` 声明，并随 PR 经评审后由 `--apply` 落地

#### Scenario: 不再 required 的三个 job 仍然照跑

- **WHEN** 任一 PR 触达 `master`
- **THEN** `.github/workflows/ci.yml` 的 `validate` / `benchmark-gate` / `windows-platform` 三个 job SHALL 照常被触发并产出结论
- **AND** 它们的结论 SHALL NOT 决定 PR 能否合入——合入结论由 `gate / check` 单独决定
- **AND** 该形态 SHALL 与「把 checked 关掉」区分开：关掉是门禁的**净损失**，不是切换

#### Scenario: 对话必须 resolve 才能合入

- **WHEN** PR 存在未 resolve 的 conversation
- **THEN** GitHub SHALL 阻止合入（required_conversation_resolution 开启）
- **AND** 全部 resolve 后才允许合入

#### Scenario: approve=1 暂缓与触发条件

- **WHEN** 查看 required_pull_request_reviews 配置
- **THEN** `required_approving_review_count` SHALL 为 0
- **AND** 配置声明 SHALL 记录触发条件（出现第二个有权限 reviewer 时开启，改配置 + 重新 apply）

### Requirement: 平台闸门复用 GitHub branch protection 语义

平台闸门 SHALL 复用 GitHub branch protection REST API 语义（required_status_checks / required_conversation_resolution / required_pull_request_reviews / enforce_admins），并遵守「PR 作者不能 approve 自己的 PR」的平台限制，不得另起一套不兼容的合入门禁协议。

#### Scenario: 平台配置走 PR review

- **GIVEN** 需要修改 `master` 分支保护配置
- **WHEN** 修改 `scripts/platform-gate.json` 并创建 PR
- **THEN** 配置变更 SHALL 随 PR 经 CI 验证后合入（该 PR 上 `gate / check` 与其余三个 job 都会跑）
- **AND** 合入后由持 admin 权限的执行者运行 `--apply` 落地，并用 `--verify` 复核
- **AND** `--apply` SHALL NOT 在同一 PR 合入**之前**执行——它是仓库级操作，会把该 PR 自身的 conversation resolution 闸门一并锁住

## ADDED Requirements

### Requirement: 降级为非必过的检查仍须运行

当某个检查从 required 降级为非必过时，该检查 SHALL 继续运行，SHALL NOT 被停用、删除或削弱为不产出结论的形态。降级改变的是「它的结论会不会阻止合入」，SHALL NOT 改变「它会不会跑」。理由：这些检查承载的项目规则（Reference Implementation Research、Impact Analysis、benchmark 回归、归档点完成度门、backlog 一致性、本仓形态的 review manifest 等）没有 witnessloop 侧的替代物——把它们关掉是门禁的净损失，而不是「切换门禁」。

#### Scenario: 降级后仍产出结论

- **WHEN** 某检查被移出 `required_status_checks.contexts`
- **THEN** 它 SHALL 仍在每个 PR 上被触发
- **AND** 它的结论 SHALL 在 PR 的 checks 列表里可见
- **AND** 它 SHALL NOT 被删除、被注释掉、或被 `if: false` / `continue-on-error` 之类的开关改成不阻塞且不产结论

#### Scenario: 「CI 绿」不等于「项目规则已满足」

- **WHEN** 一个 PR 的 required check 判绿而某个已降级的检查判红
- **THEN** 该 PR SHALL 仍可合入（这是降级的设计后果）
- **AND** 该后果 SHALL 被文档化到 `AGENTS.md` 与 `docs/development-guide.md`，使读者不会把「CI 绿」读成「项目规则已满足」
