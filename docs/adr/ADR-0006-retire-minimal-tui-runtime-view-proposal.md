# ADR-0006: 原地废弃未实现的 `add-minimal-tui-runtime-view` proposal

- **Status**: accepted
- **Date**: 2026-10-18
- **Deciders**: 用户（2026-10-17/18 决定「先废弃；将来做 TUI 时单独重新立项」）、主 agent
  （独立审阅者仅提供咨询，不参与决策）
- **关联**: issue [#319](https://github.com/Xingkai98/asterwynd/issues/319)（PR B）、
  issue [#305](https://github.com/Xingkai98/asterwynd/issues/305)（witnessloop 接入总账）、
  issue [#316](https://github.com/Xingkai98/asterwynd/issues/316)（review manifest 退役）

## Context

`add-minimal-tui-runtime-view` 是 2026-06-22 立项的 OpenSpec proposal，目标是给 CLI/Web 之外
增加一个最小终端运行视图（复用 AgentLoop、tool events、planning state）。

它在 active change 中长期未推进：

- `tasks.md` 的 18 条任务全部未勾选；
- 没有 `reviews/` 目录，没有 grill / 设计对抗 / building review 证据；
- 其 `## Reference Implementation Research` 明确写着「仅为门禁结构迁移，尚未完成本 change 的
  针对性横向调研」；
- 最后一次修改是 `97b037006faa4581a48eb7fcfc10894f8b7f6348`（2026-10-07，流程改名时统一补
  `research_tier`），此后没有实现动作。

阶段 C（`gate / check` 是唯一 required check）之后，它缺证据的问题会实际拦合入。用户决定
**先废弃**；将来做 TUI 时**单独重新立项**。

### 为什么是「原地废弃」而不是删除或归档

本仓使用 witnessloop v1.7.0 作为 required 门禁，它的 change 契约对「diff 触及的 change
目录」会要求 `proposal.md` / `design.md` / `tasks.md` / `specs/` / `reviews/` 与
`stage=grill` manifest。两种看似更彻底的处置都会让门禁变红：

1. **删除 active 目录**：witnessloop 的 `changed_change_ids` 只排除「归档 move 的源」，
   不排除被删除的 active 目录。实测删除 8 个文件后 `check` 报 5 项
   （`change 目录不存在` + 缺 review manifest / grill / grill-adversarial / building）。
   注意该实验分支同时改了 `scripts/**`（`code_hits` 非空，故多出 grill-adversarial /
   building 两项）；纯 docs-only 删除为 3 项。无论 3 或 5，删除目录都会被判红。
2. **在目录里加 `WITHDRAWN` 标记**：任何对该目录的写入都会使它成为本次 diff 的 change
   target。实测加一个 `WITHDRAWN` 文件后 `check` 报 3 项
   （`缺少必需件 reviews` + `缺少 review manifest` + `无 stage=grill 的 manifest`）。

因此本 ADR 选择**不删除、不写入、不加标记**：目录原样保留，由 ADR + backlog +
`dev-workflow-gate` 规格记录「已废弃」。这不是「已完成」的归档，也不是新的 abandoned
目录约定；它只是在一个无法原地删除的门禁下，保持 active 目录字节不变的最小处置。

## Decision

1. **保留目录原样**：`openspec/changes/add-minimal-tui-runtime-view/` 不删除、不修改、
   不加目录内标记。
2. **从 backlog 移除全部引用**：第五批条目、第十七批「已知未收尾」句、未实现队列
   `### 3. add-minimal-tui-runtime-view` 小节。
3. **ADR 留痕**（本文件）：记录废弃决定、原因、被拒备选、marker 实测证据与取回方式。
4. **规格同步**：`openspec/specs/dev-workflow-gate/spec.md` 的「已知红」Requirement 改为
   「该 proposal 已原地废弃，不再作为 active 队列项；通用判据不变」。
5. **设计内容仍可从 git 历史取回**：最后一次提交为
   `97b037006faa4581a48eb7fcfc10894f8b7f6348`（2026-10-07）。
   - 查看：`git show 97b0370:openspec/changes/add-minimal-tui-runtime-view/proposal.md`
   - 整目录恢复/复制：`git archive 97b0370 openspec/changes/add-minimal-tui-runtime-view | tar -x`
6. **未来重新立项**：做 TUI 时新建 change id，重新完成需求讨论、业界调研、grill、
   spec delta 与实现；不复用本 proposal 的未完成状态。任何未来触及该目录的 diff 都必须先
   明确处置（重新立项或等 witnessloop 支持删除），否则 witnessloop 会把它当 change target。

## Alternatives Considered

| 备选 | 描述 | 拒绝原因 |
|------|------|---------|
| 删除 active 目录 | `git rm -r openspec/changes/add-minimal-tui-runtime-view/` | witnessloop v1.7.0 不排除被删除的 active 目录；实测 `check` 报 5 项、required 门禁红（issue #319 初版尝试即卡在这里） |
| 归档为「已完成」 | 移到 `openspec/changes/archive/YYYY-MM-DD-add-minimal-tui-runtime-view/` | 语义错误：归档点完成度门要求 building review / grill 证据 / 已勾任务；保留目录并伪造证据会污染「归档 = 已交付」口径 |
| 新建 `abandoned/` 目录 | 把 proposal 移进新的第三态目录 | 新目录需要新的 checker / guard / witnessloop 契约；用户明确不要发明 abandoned 先例 |
| 在目录内加 `WITHDRAWN` 标记 | 最醒目地声明废弃 | 实测使目录成为 change target，`check` 报 3 项（缺 reviews / manifest / grill manifest）；不能为加标记伪造证据 |
| 保持 active 且不做任何标记 | 继续挂在 active change 里 | 语义上仍是「当前工作」；backlog 的未实现队列会持续引用一个没有推进计划的条目，与用户决定不符 |
| 转成 GitHub issue 长期挂起 | 把 proposal 内容搬进 issue | issue 只适合跟踪待办；设计正文在 issue 里失去版本化审阅。ADR + git 历史 + #319 已足够追溯 |

## Consequences

- 正面：backlog 不再引用一个没有推进计划的 proposal；决策、原因、marker 实测证据与取回
  方式有 ADR 可查；required 门禁保持绿（目录未被 diff 触及）。
- 负面/边界：目录仍在 active 树中，未来的任何改动（包括删除）都会触发 witnessloop 的
  change 契约；必须先重新立项或等待 witnessloop 支持「删除/退休」语义。该边界已写入
  `dev-workflow-gate` 规格与 `docs/development-guide.md`。
- 不变：`openspec/specs/tui/spec.md` 与 TUI 能力域保留；本次不改 TUI 实现、不改
  witnessloop、不改其它门禁。
- 需要的相关变更：本 ADR、backlog 清理、`dev-workflow-gate` current spec 同步、
  `docs/development-guide.md` 已知红说明。

## Revisit Conditions

- [ ] witnessloop 支持删除/退休 active change（上游能力落地）时：改为删除目录，并更新本
      ADR 的处置与 issue #319 的完成说明。
- [ ] 决定重新启动 TUI 开发时：新建 change id，重新评估本 proposal 的设计（需重新 grill
      与调研，不能直接恢复 active 状态）。
- [ ] 仓库引入正式的「放弃 / 搁置」工作流时：把本 ADR 的处置迁移到新工作流，并保留指向
      `97b0370` 的链接。
