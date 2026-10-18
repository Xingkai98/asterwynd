# Proposal: 原地废弃未实现的 `add-minimal-tui-runtime-view` proposal

关联 issue：[#319](https://github.com/Xingkai98/asterwynd/issues/319)（PR B）、
[#305](https://github.com/Xingkai98/asterwynd/issues/305)（witnessloop 接入总账）、
[#316](https://github.com/Xingkai98/asterwynd/issues/316)（review manifest 退役）。
前置：PR A（`check-scope-fix`，#320 / merge `325511e3`）已合入。

## Change Type

- primary: docs
- secondary: []

## Why

`add-minimal-tui-runtime-view` 是 2026-06-22 立项、从未实现的 proposal：18 条任务全部未勾、
没有 `reviews/`、RIR 未完成。用户决定**先废弃**，将来做 TUI 时单独重新立项。

issue #319 初版尝试**删除** active 目录，但 witnessloop v1.7.0 会把被删除的 active change
当成缺失的 change target。该实验分支同时改了 `scripts/**`（`code_hits` 非空），实测 5 项
finding（目录不存在 + 缺 manifest/grill/grill-adversarial/building）；纯 docs-only 删除为
3 项。在目录内加 `WITHDRAWN` 标记同样会让目录成为本次 diff 的 change target（实测 3 项
finding：缺 `reviews` / review manifest / grill manifest）。两种处置都会红，因此本 PR 采用
**原地废弃**：目录字节不变，用 ADR + backlog + `dev-workflow-gate` 规格记录决定。

## What Changes

1. 新增 `docs/adr/ADR-0006-retire-minimal-tui-runtime-view-proposal.md`：记录废弃决定、
   原因、两种被实测否决的处置（删除 / 目录内标记）、最后提交
   `97b037006faa4581a48eb7fcfc10894f8b7f6348` 与取回命令。
2. `docs/openspec-change-backlog.md`：移除 TUI 的三处引用（第五批条目、第十七批
   「已知未收尾」句、未实现队列 `### 3.` 小节）；登记本 change。
3. `openspec/specs/dev-workflow-gate/spec.md`：MODIFIED「已知红如实记录且不放宽判据」——
   该 proposal 已原地废弃、不作为 active 队列项；新增「原地废弃不伪造证据」Scenario；
   通用判据（缺证据的 active change 照常判红）不变。
4. `docs/development-guide.md`：阶段 A 已知红条目改为「已处置：原地废弃 + ADR-0006」。
5. **不**在 TUI 目录内加任何标记、**不**删除目录、**不**为它补 reviews / manifest。

## Capabilities

### New Capabilities

无新能力域。

### Modified Capabilities

- `dev-workflow-gate`：已知红的处置口径。该 in-flight change 已原地废弃（目录保留原样），
  不是豁免先例；缺证据的 active change 照常判红；未来触及该目录的 diff 必须先明确处置。

## 需求

1. **目录原样保留**：`openspec/changes/add-minimal-tui-runtime-view/` SHALL NOT 被删除、
   修改或加入目录内标记（witnessloop 会把任何触达该目录的 diff 当 change target）。
2. **决策留痕**：`docs/adr/ADR-0006-retire-minimal-tui-runtime-view-proposal.md` SHALL
   记录废弃决定、原因、删除/标记两种处置的实测失败证据、最后提交 sha 与取回命令。
3. **backlog 清理**：`docs/openspec-change-backlog.md` SHALL NOT 再把它列为未实现/活跃队列项；退役记录中的过去时引用（本 change 自身条目、ADR 说明）除外。
4. **规格同步**：`dev-workflow-gate` 的「已知红」Requirement SHALL 改为「已原地废弃」，
   并保留「缺证据的 active change 照常判红」的通用语义。
5. **不伪造证据**：SHALL NOT 为 TUI 补写 reviews / manifest / 勾选任务。
6. **不复用未完成状态**：未来 TUI 工作 SHALL 重新立项。

## Non-Goals

- 不实现 TUI；不删除 TUI 目录；不加目录内标记。
- 不放宽 witnessloop，不改 `v1` / `v1.7.0` tag 或 `.witnessloop/**`。
- 不改任何代码 / 测试 / 其它门禁。

## Impact Analysis

- 影响文档：
  - `docs/adr/ADR-0006-retire-minimal-tui-runtime-view-proposal.md`（新增）；
  - `docs/openspec-change-backlog.md`（移除 TUI 引用，登记/移除本 change）；
  - `docs/development-guide.md`（已知红条目改为已处置）；
  - `openspec/specs/dev-workflow-gate/spec.md`（delta 同步）。
- 影响代码：无（不触 `agent/**` / `scripts/**` / `web/**`）。
- 影响测试：无。
- 风险面：TUI 目录仍是 active；未来任何触及它的 diff 会触发 witnessloop change 契约，
  必须先重新立项或等 witnessloop 支持删除/退休。该边界写入 ADR 与规格。

## Reference Implementation Research

- research_tier: exempt
- status: disabled
- reason: 上游决策锁定：issue #319 已由用户裁决「原地废弃、不删目录」；删除与目录内标记
  两种处置均已用 witnessloop v1.7.0 实测证伪（纯 docs-only 删除 3 项、目录内标记 3 项；含 code_hits 的删除实验为 5 项）。本 change 是 docs-only
  的退役记录，无新增能力面与待定设计项，不需横向调研。

## 用户故事

- 作为维护者，backlog 不再引用一个半年没有推进的 TUI proposal，但仍能从 ADR + git 历史
  找回设计。
- 作为审阅者，required 门禁保持绿，且没有为退役伪造任何 review 证据。
- 作为未来做 TUI 的开发者，我知道必须重新立项，且不能直接改这个 active 目录。
