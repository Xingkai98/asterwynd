# Grill: industry-research-gate 设计追问

## Reviewer
- run id: e0d787b3-3a88-4a89-a677-c3e7bf9c1155
- 时间: 2026-08-14

## Confirmed Decisions

- **决策**: `research_tier` 的检查对象为「proposal.md 优先，proposal 缺省时回退 design.md」，且一次只校验一份 RIR 节；理由: 该行为与现行 checker `_find_reference_research_section` 完全一致（先查 proposal，无则查 design），design Q1 的暂定答案只是把既有行为固化为规则，不引入新检查路径，实现成本最低；来源: e0d787b3-3a88-4a89-a677-c3e7bf9c1155；证据: `scripts/check_openspec_artifacts.py:458-471`（proposal 优先 + design fallback），`design.md:98`（Q1），spec delta `openspec/changes/industry-research-gate/specs/change-documentation/spec.md:13`（"in `proposal.md` or `design.md`"）。
- **决策**: exempt 豁免采用「结构性豁免关键词 或 引用证据」双重判据 + 占位词拦截，语义充分性不做硬判、归 building-review（D5 有意粗粒度）；理由: 避免 checker 误伤合法 bugfix/文档变更，同时堵住「方案明确」一句话豁免；`#<数字>` 引用是弱代理（无法验证 issue 是否决策型/已关闭）属已知代价，由 review 维度兜底；来源: e0d787b3-3a88-4a89-a677-c3e7bf9c1155；证据: `design.md:54-57`、`design.md:71-73`，`proposal.md:17-18`，spec delta `:25`、`:45`。
- **决策**: full/light 在 tasks 全勾时 `status` 不得为 `disabled`，proposal 阶段允许 full/light + disabled 在途；理由: tier 是「预期档位」、status 是「实际状态」，完成时必调研档必须已调研，该闭环与「禁止占位文本」精神一致；proposal 阶段只查结构、不查 tier×status 组合，避免在途 change 被误伤；来源: e0d787b3-3a88-4a89-a677-c3e7bf9c1155；证据: `design.md:61`、`design.md:64-66`，`proposal.md:51`，spec delta `:33-38`（"SHALL fail (exit 2) when `status` is `disabled`"）。
- **决策**: 占位词表沿用 #123 词表（`尚未完成`/`待补充`/`待调研`/`TBD`/`todo`/`待确认`），刻意排除 `暂无`/`未完成`；「本地参考仓库不可用」不会被误判为占位，也不会单独构成合法 exempt；理由: 业界调研不依赖本地参考仓库，`暂无参考仓库可用`是 full/light 的合法 finding 表述，故不得入占位词表；同时该短语不命中任何结构性关键词、无引用证据，tasks 全勾时 exempt 证据校验会拒绝它——「显式排除」在 checker 层天然成立；来源: e0d787b3-3a88-4a89-a677-c3e7bf9c1155；证据: `scripts/check_openspec_artifacts.py:78-85`（SELF_ADMITTED_INCOMPLETE_PHRASES 不含 暂无/未完成），`design.md:56`，spec delta `:47-53`。
- **决策**: 本 change 自身 RIR 归「上游决策锁定」豁免（`research_tier: exempt` + `status: disabled`），与 flow-policy-source 归档口径一致，tasks 全勾时可通过 exempt 证据校验；理由: 决策集来自 #121 cross-cutting 规则 + 本仓库既有实现，reason 命中关键词「上游决策锁定」且含 `#121`/`#126` 引用，自洽；来源: e0d787b3-3a88-4a89-a677-c3e7bf9c1155；证据: `design.md:88-90`，`proposal.md:82-86`，归档版 `openspec/changes/archive/2026-08-14-flow-policy-source/proposal.md:108`（口径示例）。
- **决策**: 归档 change 不在 RIR/tier 检查范围（`--check-archived` 不扩展），避免历史 change 被新必填字段误伤；理由: `iter_change_dirs` 跳过 archive，`--check-archived` 仅校验 review manifest，与 #123 决策一致；来源: e0d787b3-3a88-4a89-a677-c3e7bf9c1155；证据: `scripts/check_openspec_artifacts.py:1176-1179`（跳过 archive）、`:1321-1329`（--check-archived 只跑 `_check_review_manifests`），`design.md:108`。

## Open Questions

- **Q1**: `research_tier` 检查对象——proposal 与 design 同时存在 RIR 节时以哪份为准？现状 checker `_find_reference_research_section`（check_openspec_artifacts.py:458-471）proposal 优先、缺省回退 design，且只校验一份。这意味着：proposal 有 RIR 时 design 的 RIR 被完全忽略——若 proposal 写 `research_tier: full`、design 写 `research_tier: exempt`，冲突不会被发现，静默漂移。需要确认：(a) 接受「proposal 优先、design RIR 仅在 proposal 缺省时才是检查对象」，并在 development-guide 写明，或 (b) 增强 checker 校验两份并强制 tier 一致（增加复杂度）。推荐 (a) 简化实现。
- **Q2**: 存量 active change（add-minimal-tui-runtime-view / add-worktree-tool / update-design-review-method）补齐 `research_tier` 的时间点与方式？三个 change 的 proposal RIR 均缺 research_tier（add-minimal-tui-runtime-view `proposal.md:43-55`、add-worktree-tool `proposal.md:82-97`、update-design-review-method `proposal.md:48-51`），且 tasks 均未全勾 → 新 checker 合入后 proposal 结构门槛立即对三者报错，必须在本 change 内统一补齐（task 3.6 已列）。**连带缺陷**：update-design-review-method 按 tier=exempt 补齐时，其现有 reason「纯工具替换（流程方法名变更），不涉及实现方案选择，无需参考实现调研」不命中任何结构性关键词（无 `无设计决策`/`上游决策锁定`）、无 `#<数字>`/评审路径引用——一旦其 tasks 全勾（仅剩 3.3/4.x），新 exempt 证据校验会在它归档时拦下。因此补齐动作不能只加字段，必须同步按新证据规则审查/强化该 change 的 reason（涉及改写其他 change 文档，需注意「已有改动」纪律）。需要确认补齐范围：仅加 `research_tier`，还是连 reason 一起强化？
- **Q3**: exempt 结构性豁免关键词初始清单（`docs-only` / `bugfix` / `上游决策锁定` / `无设计决策` / `方案已由.*决策` + `#<数字>`/`docs/`/`openspec/changes/archive/`/`reviews/` 引用）是否足够？「本地参考仓库不可用」是否会被误判为合法豁免？核实结论：checker 占位词表不含 `暂无`/`未完成`，且该短语不命中关键词、无引用 → tasks 全勾时不会单独通过 exempt，设计主张在 checker 层成立；但需在 AGENTS.md/development-guide 显式写反例「本地参考仓库不可用不构成豁免理由」，防 agent 误用。**冲突点**：design D3 的判断性豁免示例「与已有模块 X 等价改造」（design.md:55）在无 `#<数字>`/`docs/`/`archive/`/`reviews/` 引用时会被自己的 checker 拒绝（代码路径如 `agent/`、`scripts/` 不在证据路径清单）——清单需扩展（含 `openspec/specs/`、`openspec/changes/`、`agent/`、`scripts/`）或该示例需带引用。需要确认清单与示例如何对齐。
- **Q4**: full/light 在 tasks 全勾时 `status` 不得为 `disabled` 的闭环要求是否可接受？核实结论：与「禁止占位文本」精神一致；proposal 阶段 full+disabled 在途合法（结构门槛不查组合）。**未决边界**：(a) `exempt` + `status: enabled`（声言豁免但实际完成调研）会被新 checker 以「exempt 必须 disabled」拦下——合法场景是作者改 tier 为 light/full，建议文档化；(b) 半途改 tier（full→exempt）但 status 未同步 → 完成时报错，错误信息（change id + 字段 + 命中短语）已足以定位。需要确认 (a) 的处理口径。
- **Q5**（新发现）: 本 change 自身 proposal.md 的 RIR 节**实际缺失 `research_tier` 字段**——`proposal.md:80-86` 只有 status/reason/research questions/findings/design impact；而 tasks 1.4 已勾选 `[x]` 声称维护了 `research_tier: exempt`，勾选与文件不符。影响：新 checker 合入后，本 change 自身在任何阶段都过不了 proposal 结构门槛（非 docs + tier 字段缺失）。这是自举一致性缺陷，必须在实现阶段把 `research_tier: exempt` 补到 proposal RIR（位于 status 之前）。需要确认：仅补字段，还是按新模板一并重写 reason？
- **Q6**（新发现）: 占位词表与阶段感知规则双写——`openspec/specs/dev-workflow-state-machine/spec.md:553-568`（#123 内容门槛）与本 change 的 spec delta `:33-45` 重述同一份「内容门槛 + 占位词表」。若 #123 词表后续变更，change-documentation 副本漂移。需要确认：delta 改为引用 #123 requirement 而非重述词表（推荐），或接受双写并加 parity/注释同步。

## 风险

- **[高] 本 change 自身 proposal.md RIR 缺 `research_tier` 字段**（proposal.md:80-86 vs tasks.md:8 勾选不符）：新 checker 合入即对本 change 自身报结构门槛错误，形成自锁。必须在实现阶段（或 grill 后）补 `research_tier: exempt`，否则 `check_openspec_artifacts.py` 无法通过、无法归档。
- **[中] 存量 update-design-review-method 的 exempt reason 不满足新证据规则**：其 tasks 接近全勾（tasks.md 仅 3.3/4.x 未勾），若本 change 先合入、它后完成，新 exempt 证据校验会在它归档时拦下（reason 无关键词、无引用）。补齐动作若只加字段不强化 reason，该 change 会卡死；若强化 reason，则属改写其他 change 文档，需走「已有改动」纪律与（如涉及受保护路径）事件。
- **[中] 判断性豁免示例与 checker 规则冲突**：design.md:55 推荐的「与已有模块 X 等价改造」在无 `#<数字>`/证据路径引用时会被自己的 checker 拒绝（`agent/`、`scripts/` 代码路径不在证据路径清单）。清单需扩展（`openspec/specs/`、`openspec/changes/`、`agent/`、`scripts/`）或示例需带引用，二选一，否则文档误导 agent。
- **[中] 三处双写漂移**：triage 规则同时落在 AGENTS.md（判据表）、spec delta（Research tier triage）、development-guide（举例）；占位词表落在 dev-workflow-state-machine spec 与 change-documentation delta 两处。checker 以 spec 为权威可缓解，但词表副本漂移无机械兜底——建议 delta 引用 #123 而非重述词表，并保留 task 4.5 人工一致性核对。
- **[低] `#<数字>` 引用是弱豁免代理**：任何 issue 编号都算「引用证据」，无法验证是否决策型/已关闭——弱豁免（如「详见 #111」而非决策票）可能绕过。设计已承认粗粒度（D5），建议在 development-guide 写「引用的 issue 须为已关闭决策/架构评审」，由 building-review 兜底。
- **[低] `exempt` + `status: enabled` 边界未文档化**：声言 exempt 但实际完成调研的 change 会被「exempt 必须 disabled」拦下；正确动作是改 tier 为 light/full。建议在 AGENTS.md/guide 显式说明。
- **[低] spec delta 措辞歧义**：delta `:7` 写 `research_tier: full|light|exempt`，可能被读作字面枚举值；建议改为「one of `full`, `light`, `exempt`」，与 proposal/design 的「枚举值」语义一致。

## User Confirmation

以下为用户 2026-08-14 对 `## Open Questions` 的逐项确认（grill-confirmation-gate，Q1-Q6 全部确认）：

- **Q1**: 用户答复：接受推荐 (a)——research_tier 检查对象为 proposal 优先、design 仅 fallback，文档化固化既有 checker 行为（`_find_reference_research_section`），不增强强制两份一致；确认时间: 2026-08-14
- **Q2**: 用户答复：本 change 实现时统一给 add-minimal-tui-runtime-view / add-worktree-tool / update-design-review-method 三个存量 active change 的 proposal RIR 节补 `research_tier` 字段；update-design-review-method 的 reason 顺带强化到命中结构性豁免关键词（防其后归档时被新校验拦）；确认时间: 2026-08-14
- **Q3**: 用户答复：不扩展证据路径清单；「与已有模块 X 等价改造」类判断性豁免示例改为必须带引用（文件:行号或 issue 号），development-guide 写反例；确认时间: 2026-08-14
- **Q4**: 用户答复：exempt + status: enabled 的处理口径为——做了调研就如实改 light/full + enabled，不报 exempt；development-guide 写反例；确认时间: 2026-08-14
- **Q5**: 用户答复：仅补字段——在自身 proposal.md 的 RIR 节补 `research_tier: exempt`（status 前），reason 保持（已含 #121/#126 引用）；tasks 1.4 勾选与文件对齐；确认时间: 2026-08-14
- **Q6**: 用户答复：spec delta 改为引用 #123 requirement 的占位词表，不重述词表，避免双写漂移；确认时间: 2026-08-14
