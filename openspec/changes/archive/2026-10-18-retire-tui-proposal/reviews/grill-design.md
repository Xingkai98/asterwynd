# Grill: retire-tui-proposal 设计追问

## Reviewer
- run id: dd7d7e03-8e07-4d2e-b6a5-82f71c2be212
- 时间: 2026-10-18
- 方式: 零记忆只读审阅；实读 change 全套文档、ADR-0006、backlog/development-guide/spec diff、TUI 目录树与 git 历史；实跑 artifact checker（裸跑、`--base-ref origin/master --require-base`、`--check-archived` 均 EXIT=0）与 `openspec validate --all --strict`（30 passed）；用 `check_protected_path_explanations` 模拟归档路径；核对 witnessloop v1.7.0 的 change-target / manifest / stale-span 实现。未修改任何文件。

## Confirmed Decisions
- **决策**: 采用「目录字节不变 + ADR + backlog + 规格留痕」的原地废弃，而不是删除目录或加目录内标记；理由: TUI 目录与 base 树逐字节相同（tree `cbc94fe24061c7bf2d461b858a55dd8574eaef00`，递归 sha256 一致），无 `WITHDRAWN`；删除与目录内标记都会让 witnessloop 进入 change-target 求值（实测 5 / 3 项 finding）；来源: dd7d7e03-8e07-4d2e-b6a5-82f71c2be212
- **决策**: 不为 TUI 补 `reviews/`、manifest 或勾选任务；理由: `tasks.md` 18 条全部未勾、目录内无 `reviews/`、RIR findings 自认未完成（`openspec/changes/add-minimal-tui-runtime-view/proposal.md:53`），补证据会把「未实现」伪造成「已审阅」；来源: dd7d7e03-8e07-4d2e-b6a5-82f71c2be212
- **决策**: backlog 移除三处队列引用，并保留 ADR/过去时退役记录；理由: diff 精确删除第五批条目、第十七批「已知未收尾」句、`### 3.` 小节（`docs/openspec-change-backlog.md` 旧行 45、117、145）；当前唯一保留的 id 命中是新登记的退役条目（`docs/openspec-change-backlog.md:122`），其与 proposal 需求 3 的字面冲突见 M3；来源: dd7d7e03-8e07-4d2e-b6a5-82f71c2be212
- **决策**: `dev-workflow-gate` 的 MODIFIED Requirement 与 current spec 同步一致，Requirement 计数 12 -> 12；理由: 脚本抽取两处 Requirement 块比较为逐字相同（各 1596 chars），`openspec/specs/dev-workflow-gate/spec.md:65` 与 delta `openspec/changes/retire-tui-proposal/specs/dev-workflow-gate/spec.md:5` 一致；「缺证据的 active change 照常判红」保留；来源: dd7d7e03-8e07-4d2e-b6a5-82f71c2be212
- **决策**: 本 change 作为 docs 类型归档不需要 building review / grill-adversarial，但仍需要 `reviews/grill-design.md` + `stage=grill` manifest；理由: `scripts/check_openspec_artifacts.py:1730-1732` 的 building-review 条件含 `primary != "docs"`，`:1753-1757` 的 grill-adversarial 还要求 DESIGN_TYPES；witnessloop 的 building/grill-adversarial 只在 diff 命中 `require_change_for`（`agent/scripts/web`）时触发（`/home/happy/wl170/lib/python3/site-packages/witnessloop/checkcmd.py:266-282`），而本 PR 不触这些路径；但 `grill_evidence_findings_in_change` 对每个 target 都要求 `stage=grill` manifest（`evidence.py:416-436`）；来源: dd7d7e03-8e07-4d2e-b6a5-82f71c2be212
- **决策**: witnessloop 的目标面只有 `retire-tui-proposal`（归档后为其 archive arrival），TUI 目录不会成为 target；报告必须被 manifest 绑定以避免孤儿；理由: diff 不触 `openspec/changes/add-minimal-tui-runtime-view/**`；target 以 change 目录为键（`contract.py:458-480`、`:501-545`）；`reviews/**.md` 未被任何 manifest `report_path` 绑定时触发孤儿规则；来源: dd7d7e03-8e07-4d2e-b6a5-82f71c2be212

## Code-Resolved Questions
- TUI 目录是否真的字节不变？ → 是。`git diff origin/master -- openspec/changes/add-minimal-tui-runtime-view` 为空，tree hash 与 base 同为 `cbc94fe24061c7bf2d461b858a55dd8574eaef00`，递归 `ls-tree` sha256 两侧一致；未发现 `WITHDRAWN` 文件（全仓搜索只命中 ADR/change 文档里的说明文字）。
- TUI 是否被伪造了评审证据或勾选？ → 否。18 条任务全为 `- [ ]`、0 条 `- [x]`；无 `reviews/`；无 manifest；RIR 自认未完成于 `openspec/changes/add-minimal-tui-runtime-view/proposal.md:53`；最后提交为 `97b037006faa4581a48eb7fcfc10894f8b7f6348`（2026-10-07）。
- backlog 的三处引用是否确实移除？ → 是。diff 删除 `:45` 第五批条目、`:117` 第十七批「已知未收尾」句、`:145` 起 `### 3. add-minimal-tui-runtime-view` 小节；当前 `rg` 只剩 `docs/openspec-change-backlog.md:122` 的退役登记（见 M3）。
- ADR 的 sha 与取回命令是否可用？ → 是。`git cat-file -t 97b0370` = commit；`git show 97b0370:openspec/changes/add-minimal-tui-runtime-view/proposal.md` 可读；`git archive 97b0370 openspec/changes/add-minimal-tui-runtime-view | tar -x` 可解出整目录（`ADR-0006:54-57`）。
- delta 与 current spec 是否一致？ → 是。抽取的 Requirement 块逐字相同（1596 chars），current spec Requirement 计数 12；`openspec validate --all --strict` 实跑 30 passed / 0 failed（与 tasks 3.5 一致）。
- 当前受保护路径事件是否齐全？ → 当前 backlog 与 spec 写入均有 `backlog_updated` / `current_spec_synced` 事件（`workflow-events.jsonl:2-3`）；但归档 move 后 `openspec/changes/archive/**` 还缺 `change_archived` 事件（`scripts/flow-policy.json:38-43`；模拟归档路径调用 checker 返回两条「changed without workflow event explanation」）→ M2。
- 本 change 归档点是否需要 building review？ → 不需要。`scripts/check_openspec_artifacts.py:1730-1732` 的触发条件是 `primary != "docs"` 且有 spec delta；本 change 为 docs。witnessloop 的 building / grill-adversarial 只在 `code_hits` 非空时要求，本 PR 的 diff 不触 `agent/`、`scripts/`、`web/`。但 `reviews/grill-design.md` + `stage=grill` manifest 仍是 witnessloop 的硬要求。
- tasks 能否结算？ → 机制上可以：`_untagged_unchecked_tasks` 返回空，4.1/4.2 已正确标 `(post-merge)`；但 0.1 与 3.6 当前是「未落盘却已勾选」，必须先纠正（M1）。
- witnessloop 是否会有其它 target / orphan？ → 无其它 target：只有 `retire-tui-proposal`，归档后是 `archive/2026-10-18-retire-tui-proposal`；不触 TUI 目录，因此不会把 TUI 拉成 target。孤儿风险仅在 `reviews/grill-design.md` 未被 `stage=grill` manifest 绑定时出现；若 `reviews/` 存在但无 manifest，witnessloop 会同时报「缺少 review manifest」与「无 stage=grill 的 manifest」。
- 5 / 3 项 finding 的证据口径是否准确？ → 数字本身可复现，但 5 项的实验分支同时改了 `scripts/check_openspec_artifacts.py`（`git show --name-status 2b1059c`），因此 `code_hits` 非空，5 项中包含 grill-adversarial 与 building 两项；纯 docs-only 删除只会得到 3 项（目录缺失 + 缺 manifest + 缺 grill manifest）。ADR/spec 未写明这个上下文（M4）。
- 本 change 是否需要 change 目录与事件？ → 需要。witnessloop 对任何被 diff 触及的 change target 都要求 `proposal/design/tasks/specs/reviews`（`.witnessloop/policy.json` 的 `required_artifacts`）；change 目录已存在，docs-only 也需要 `reviews/` 才能过 witnessloop，即使本地 checker 对 docs 跳过了 grill/building 检查（`scripts/check_openspec_artifacts.py:531`、`:725`、`:744`）。

## Open Questions
- 无

## 风险
- **R1（Medium）归档点会因缺 `change_archived` 事件判红**：`openspec/changes/archive/**` 是受保护前缀，归档 move 后 checker 会要求该事件；当前 tasks 的收尾次序未列入这一步（见 M2）。
- **R2（Medium）tasks 提前勾选破坏证据可信度**：0.1 声称 `reviews/grill-design.md` 已产出，但目录内没有 `reviews/`；3.6 声称归档后 witnessloop 已通过，但 change 未归档、manifest 不存在。虽然 TUI 任务没有被伪造，但本 change 自身的完成度记录不诚实（见 M1）。
- **R3（Medium）proposal 需求 3 与 backlog 自身条目直接冲突**：`proposal.md:54` 要求 backlog 不再引用 TUI id，`docs/openspec-change-backlog.md:122` 却又引用了它（见 M3）。
- **R4（Low）5/3 finding 的实验上下文缺失**：删除实验的 5 项包含 `code_hits` 触发的两项 stage 证据，不能直接读成「删除单独就会产生 5 项」；这会影响后续对规格理由的复核（见 M4）。
- **R5（Low）「经用户决定放弃并留痕」被写成通用解除路径**：它与 Requirement 正文「SHALL NOT 被解释为豁免先例」存在张力；未来任何缺证据的 active change 都可被引用为「用户决定放弃 + ADR」的模板（见 M5）。
- **R6（Low）manifest 的 head_sha / 提交次序仍是隐性硬约束**：witnessloop 要求 `head_sha` 之后只出现证据文件；`reviews/`、`workflow-events.jsonl`、`archive/**` 是 stale-exempt（`policy.py:77-94`），但 `tasks.md` 结算若作为独立内容提交落在 manifest 之前，必须让 manifest 的 `head_sha` 指向该结算提交，否则会被判 stale（`contract.py:679-690`）。tasks 头部只写了「结算 tasks.md -> 重建 manifest」，未写明「先提交结算，再单独提交 manifest」。
- **R7（Low）整个 diff 尚未提交**：`git rev-list --count origin/master..HEAD` = 0，全部改动在工作树；PR 前必须按「内容提交 -> 证据提交」拆分，否则 witnessloop 无法在 CI 上按预期求值。
- **R8（Nit）ADR 的 Deciders 写了「独立审阅者」**：本次审阅尚未结束，审阅者不是决策者；建议改为「主 agent / 用户」，或注明审阅者为咨询角色（`ADR-0006:5`）。
- **R9（Low）TUI 目录仍会挡住未来触及它的改动**：这是原地废弃的已接受代价，ADR/规格已写明处置路径，但 backlog 不再跟踪它，未来开发者只能从 ADR 得知；当前没有额外缓解措施。

## User Confirmation
无待用户拍板项。

---

## 必须修改项

- **M1 — Medium — 修正 tasks 的提前勾选**：落点 `openspec/changes/retire-tui-proposal/tasks.md:9` 与 `:30`。0.1 只有在本报告实际落盘到 `reviews/grill-design.md` 后才能保持勾选；3.6 必须取消勾选，直到归档 move + manifest 落盘后实际跑通 witnessloop 再勾。若坚持「先写 tasks 后落证据」，应把两行改为未勾并在同一提交内完成，不能留下已勾但文件不存在的状态。
- **M2 — Medium — 增加 `change_archived` 事件任务**：落点 `tasks.md` 收尾节（建议在 §2 或 §4 前新增 2.3 / 4.0）与 `workflow-events.jsonl`。归档 move 前/时写入 `event_type=change_archived`、`change_id=retire-tui-proposal`、`artifact_path=openspec/changes/archive/2026-10-18-retire-tui-proposal`、非空 `reason`/`approved_by` 的事件；归档后复跑 `check_protected_path_explanations`（或裸 checker）确认通过。依据：`scripts/flow-policy.json:38-43`、`scripts/check_openspec_artifacts.py:1290-1314`。
- **M3 — Medium — 消除 backlog 引用与 proposal 需求 3 的矛盾**：落点 `proposal.md:54`（需求 3）、`tasks.md:31`（3.7）与 `docs/openspec-change-backlog.md:122`。建议把需求 3 改为「backlog SHALL NOT 再把它列为未实现/活跃队列项；退役记录中的过去时引用除外」，并在 3.7 的 grep 白名单中显式列出 backlog 退役条目、development-guide、current spec 的过去时说明；或者从 `:122` 去掉 change id（但会损失追溯性，不推荐）。
- **M4 — Low — 补 5/3 finding 的实验上下文**：落点 `ADR-0006:34-39`、`proposal.md:18-22`、`specs/dev-workflow-gate/spec.md:65`、`docs/development-guide.md:384`。建议加一句：「5 项实验同时改动了 `scripts/check_openspec_artifacts.py`（`code_hits` 非空，含 grill-adversarial / building 两项）；纯 docs-only 删除为 3 项。无论 3 或 5，删除目录都会被判红，决策不变。」这样规格理由不会被后续实测反驳。
- **M5 — Low — 收紧「放弃并留痕」的通用解除路径**：落点 delta `openspec/changes/retire-tui-proposal/specs/dev-workflow-gate/spec.md:12` 与 current `openspec/specs/dev-workflow-gate/spec.md:72`。建议改成「该红的解除 SHALL 是实现并补证据；或由用户对**该 change** 明确裁决放弃，并以 ADR + backlog 清理留痕（ADR-0006 只记录本 change，SHALL NOT 被读成无留痕豁免或可复用的豁免先例）」，与 Requirement 正文的「不是豁免先例」保持一致。
- **M6 — Low — 明确 manifest 的提交次序**：落点 `tasks.md` 头部结算次序。建议写成「最终内容提交（含 tasks 结算与 backlog 移除）→ 归档 move 提交 → 用归档目录名重建 `reviews/grill-design.md` 的 `stage=grill` manifest → 单独提交证据」；manifest 的 `head_sha` 必须指向最后一个非证据提交，`reviews/`、`workflow-events.jsonl`、`archive/**` 之外的内容不得落在 `head_sha` 之后。依据：`/home/happy/wl170/lib/python3/site-packages/witnessloop/contract.py:679-690`、`policy.py:77-94`。
- **M7 — Nit — ADR Deciders 角色**：落点 `docs/adr/ADR-0006-retire-minimal-tui-runtime-view-proposal.md:5`。建议删掉「独立审阅者」或标为「审阅者（咨询，不参与决策）」，避免在审阅闭环完成前把它写成决策者。
