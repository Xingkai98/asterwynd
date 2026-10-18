## MODIFIED Requirements

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
