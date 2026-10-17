# platform-gate 规格 delta

## MODIFIED Requirements

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
