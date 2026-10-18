# change-documentation 规格 delta

## MODIFIED Requirements

### Requirement: Pre-implementation design grilling

Every non-trivial OpenSpec change SHALL complete a pre-implementation design
grilling pass before tests or implementation begin. The grilling pass SHALL be
performed by an independent zero-memory subagent (not self-attested by the
implementing agent) — using the `grilling` skill, or an equivalent independent
design interview where the environment does not provide it — SHALL produce a
structured decision record at `openspec/changes/<id>/reviews/grill-design.md`,
and SHALL be mechanically enforced by witnessloop: its plugin `guard` blocks
code writes for a change whose grilling evidence is missing, and `gate / check`
verifies the `grill` / `grill-adversarial` / `building` stage manifests and
report evidence. The slim project-rule checker SHALL NOT duplicate active-stage grill evidence checks; it SHALL check the archive-point grill evidence required by `dev-workflow-gate` rule 4.

Following the grilling pass and **before** the stop-turn user confirmation, the
change SHALL run a **design-phase review loop**: an independent zero-memory
reviewer that performs **adversarial analysis** (defaulting to the assumption
that the design is wrong, attempting to refute each Confirmed Decision and the
design's assumptions), returns a **verdict** (`PASS` / `CHANGES_REQUESTED` /
`BLOCKED`), and on `CHANGES_REQUESTED` the design SHALL be revised and re-verified under the
**bounded-batch round model** defined by the project review rules in
`AGENTS.md`: a round is one non-empty
medium+ batch closure (open batch -> fix all -> verify only -> close), at most
20 closed rounds apply, new medium+ issues found during verification SHALL be
deferred to the next batch rather than raised as current blockers, and the exits
are `PASS` / `BLOCKED` + cause / over-limit `BLOCKED` with "revise the design".
`CHANGES_REQUESTED` is an in-round state, not an exit. If round 20 itself
reaches the verification-retry termination point, or the closing check after
round 20 still finds medium+ issues, the exit SHALL be over-limit `BLOCKED` with
"revise the design". The loop SHALL produce a structured record at
`openspec/changes/<id>/reviews/grill-adversarial.md`. This loop is
**isomorphic to the implementation-phase `/review-loop`** — same bounded-batch
model (independent zero-memory reviewer -> open batch -> fix all -> verify only
-> close; deferred issues enter the next batch), not an open-ended loop — but
reviews the **design**, not code. The implementation-phase `/review-loop` (which
reviews code and produces `building-review.md`) SHALL continue to exist as a
separate implementation-phase loop; **both loops SHALL use the same bounded-batch
round model**, and neither loop SHALL replace the other.

Within the design-phase review loop, for every Open Question the grilling raised
the reviewer SHALL either resolve it from the codebase when the answer is
**code-decidable**, or classify it as a **user decision** when it is not.
**Code-decidable** Open Questions SHALL be answered with evidence
(`file:line`), recorded under a `## Code-Resolved Questions` section in
`grill-design.md`, and SHALL NOT be carried into `## Open Questions` or the
stop-turn queue. Only **user decisions** SHALL remain in `## Open Questions`.

The grilling pass SHALL NOT be considered complete until every Open Question
remaining in `## Open Questions` has been answered by a human user, with the
answers recorded in a `## User Confirmation` section. A change whose Open
Questions are not all confirmed SHALL be blocked from code writes by the
witnessloop guard and SHALL NOT be archived; witnessloop's report checks SHALL
require the `## User Confirmation` section.

The design-phase review loop's exit SHALL be a precondition for implementation:
a `BLOCKED` exit SHALL NOT be treated as permission to write code. Only `PASS`,
or `BLOCKED` + cause + **an explicit user ruling to continue**, SHALL allow
implementation to start; the ruling SHALL be recorded in
`grill-design.md`'s `## User Confirmation` (or a `## Blocked Ruling` section).

#### Scenario: grill evidence passes design review

- **GIVEN** a non-trivial change with a `reviews/grill-design.md`
- **WHEN** the record has at least 3 confirmed decisions
- **AND** either the Open Questions section is empty, or every listed Open
  Question has a matching `## User Confirmation` entry
- **THEN** the design review is satisfied and code writes are allowed

#### Scenario: design-phase review loop resolves code-decidable questions

- **GIVEN** a change whose `grill-design.md` lists an Open Question answerable
  from the codebase (e.g. "does `_find_scope_root` walk past a non-git tmp dir?")
- **WHEN** the design-phase review loop runs
- **THEN** the question SHALL be answered with `file:line` evidence
- **AND** it SHALL be recorded under `## Code-Resolved Questions`
- **AND** it SHALL NOT appear in `## Open Questions` or require `## User Confirmation`

#### Scenario: design-phase review loop challenges confirmed decisions under the bounded-batch model

- **GIVEN** a change whose `grill-design.md` records Confirmed Decisions
- **WHEN** the design-phase review loop runs
- **THEN** the reviewer SHALL attempt to refute each Confirmed Decision
- **AND** it SHALL record a verdict (`PASS` / `CHANGES_REQUESTED` / `BLOCKED`)
  with per-issue `file:line` evidence in `reviews/grill-adversarial.md`
- **AND** on `CHANGES_REQUESTED`, the design SHALL be revised and verified within
  the same round; the batch SHALL close only when every medium+ item in it is
  verified fixed
- **AND** new medium+ issues found during verification SHALL be deferred to the
  next batch, not raised as current blockers
- **AND** the loop SHALL stop after at most 20 closed rounds; if the closing
  check after round 20 still finds medium+ issues, the exit SHALL be over-limit
  `BLOCKED` with "revise the design"
- **AND** any refuted decision SHALL be corrected in `grill-design.md` before
  the stop-turn confirmation

#### Scenario: open question not confirmed blocks code writes

- **GIVEN** a non-trivial change with a `reviews/grill-design.md`
- **WHEN** the record has at least 3 confirmed decisions but lists Open
  Questions that lack matching `## User Confirmation` entries
- **THEN** the witnessloop plugin guard SHALL block code writes
- **AND** the change SHALL NOT be archived until the questions are confirmed

#### Scenario: completed change with unconfirmed open questions is rejected

- **GIVEN** a non-docs change with a spec delta and fully-checked tasks
- **WHEN** the change is reviewed or archived with a `reviews/grill-design.md`
  that lists Open Questions without matching `## User Confirmation` entries
- **THEN** witnessloop's report checks SHALL reject the evidence
- **AND** the change SHALL NOT be treated as complete

#### Scenario: grilling skill is unavailable

- **WHEN** the current agent environment does not provide the `grilling` skill
- **THEN** the agent performs an equivalent independent design grilling

### Requirement: Mechanical artifact checks

The project SHALL use one slim local checker for six mechanical project rules
without attempting to judge technical design quality. The six rules SHALL be:
Reference Implementation Research, Impact Analysis, benchmark smoke task,
tasks / archive-point completion, backlog consistency, and the building review
`## 闭环出口` PASS verdict. The checker SHALL NOT duplicate witnessloop's
change contract, stage manifest, protected-write event, or **active-stage**
grill-report checks. The archive-point grill evidence required by
`dev-workflow-gate` rule 4 (grill design + adversarial reports for non-code
changes) is part of the archive completion rule, not a separate seventh rule.

#### Scenario: Slim checker scope

- **WHEN** the project rule checker validates an active change or a newly
  archived change
- **THEN** it applies only the six rules listed above
- **AND** it does not score design correctness, architecture quality, or
  implementation trade-offs
- **AND** it does not check review manifests, protected-path events, or
  active-stage grill report bodies (witnessloop owns those)
- **AND** the archive-point grill evidence for non-code changes is part of the
  archive completion rule specified by `dev-workflow-gate`

#### Scenario: Type metadata is a prerequisite, not a checked rule

- **WHEN** a change declares `primary` / `secondary` types
- **THEN** the checker reads `Change Type` only to decide which rules apply
  (for example, docs changes are exempt from RIR and Impact Analysis)
- **AND** it does not independently require every declared type's design or
  diagnosis sections
- **AND** when `proposal.md` is missing or `## Change Type` cannot yield a valid
  `primary`, the checker SHALL exit 1 with a clear error instead of silently
  skipping the docs exemptions

### Requirement: CI gate for project validation

The project SHALL provide a GitHub Actions CI workflow that runs the baseline
validation commands for pull requests and pushes.

#### Scenario: Baseline CI validation
- **WHEN** a pull request or push triggers the baseline CI workflow
- **THEN** the workflow runs the full pytest suite
- **AND** runs OpenSpec strict validation for all specs and active changes
- **AND** runs the slim project-rule checker

#### Scenario: Expensive validation remains change-scoped
- **WHEN** a change requires benchmark smoke, browser smoke, real API
  validation, or Docker/SWE-bench validation
- **THEN** those checks are recorded in the change tasks and final
  verification notes
- **AND** they are not required as part of the baseline CI workflow unless a
  later change explicitly adds that policy

### Requirement: Reference implementation research gate

Non-docs OpenSpec changes SHALL explicitly record whether reference
implementation research is enabled or disabled before implementation begins,
and SHALL declare the expected research tier as
`research_tier: full|light|exempt`. This requirement SHALL be checked
mechanically by the slim project-rule checker using the pre-retirement
judgments: structure fields before tasks complete, and the content threshold
once tasks are complete or the change reaches its archive point.

#### Scenario: Non-docs change records enabled research
- **WHEN** an OpenSpec change has `primary` other than `docs`
- **AND** reference implementation research is enabled
- **THEN** the change records `## Reference Implementation Research` in
  `proposal.md` or `design.md`
- **AND** the section records the research questions, findings, and design
  impact, plus a declaration of whether local reference repositories were
  available (for example, the findings note when `.dev/reference-repos.txt` is
  unavailable)
- **AND** research questions are required for `research_tier: full` but may be
  omitted for `research_tier: light`

#### Scenario: Non-docs change disables research
- **WHEN** an OpenSpec change has `primary` other than `docs`
- **AND** the change owner decides reference implementation research is not
  useful or not applicable
- **THEN** the change records `## Reference Implementation Research` in
  `proposal.md` or `design.md`
- **AND** the section records `research_tier: exempt`
- **AND** the section records `status: disabled`
- **AND** records a non-empty reason that hits a structural exemption keyword
  (for example `docs-only`, `bugfix`, `上游决策锁定`, `无设计决策`) or cites
  evidence such as a closed decision issue (`#<number>`) or a review/decision
  document path (`docs/`, `openspec/changes/archive/`, `reviews/`)

#### Scenario: Research tier is validated in proposal phase
- **WHEN** the slim project-rule checker validates a non-docs change whose tasks
  are not all complete
- **THEN** it checks that `research_tier` is present and is one of `full`,
  `light`, `exempt`
- **AND** it does not enforce tier-specific content checks yet

#### Scenario: Completed full or light research change must be finished
- **WHEN** the slim project-rule checker validates a non-docs change whose tasks
  are all complete (or a newly archived change)
- **AND** the section records `research_tier: full` or `research_tier: light`
- **THEN** the checker SHALL fail (exit 1) when findings or design impact
  contain self-admitted incomplete phrases from the checker's phrase list
- **AND** the checker SHALL fail (exit 1) when `status` is `disabled`

#### Scenario: Completed exempt research change must justify exemption
- **WHEN** the slim project-rule checker validates a non-docs change whose tasks
  are all complete (or a newly archived change)
- **AND** the section records `research_tier: exempt`
- **THEN** the checker SHALL fail (exit 1) when `status` is not `disabled`
- **AND** the checker SHALL fail (exit 1) when the reason is empty, hits a
  placeholder phrase, or neither hits a structural exemption keyword nor cites
  evidence

#### Scenario: Local reference repositories are unavailable
- **WHEN** reference implementation research is enabled
- **AND** `.dev/reference-repos.txt` is missing, empty, or points only to
  unavailable repositories in the current workspace
- **THEN** the change records that local reference repositories are unavailable
- **AND** the change records the alternative basis used for the design decision
- **AND** CI does not require those local paths to exist

#### Scenario: Docs-only change is exempt
- **WHEN** an OpenSpec change has `primary: docs`
- **THEN** the checker does not require `## Reference Implementation Research`

#### Scenario: Artifact checker enforces record shape
- **WHEN** the slim project-rule checker validates an active non-docs change
- **THEN** it checks that reference implementation research status is present
  and is either `enabled` or `disabled`
- **AND** it checks that enabled research has non-empty reason, findings, and
  design impact
- **AND** it checks that research questions are non-empty when
  `research_tier: full`
- **AND** it checks that disabled research has a non-empty reason
- **AND** it does not judge research quality or verify local reference
  repository paths

### Requirement: Handoff state file artifact

老世代 OpenSpec change 的 `handoff.json` SHALL 作为**只读历史投影**保留：它记录该 change 生命周期在退役前的 state 与 transition 历史。当代 change SHALL NOT 被要求包含 `handoff.json`，SHALL NOT 产出 `handoff.json`，也 SHALL NOT 产出 `workflow-state.json`：流程事件投影能力（`scripts/workflow_state.py`、`agent/workflow/*`、`flow status`）SHALL 已退役，`workflow-events.jsonl` 仅作为只读历史数据保留。

#### Scenario: 当代 change 不要求 handoff.json

- **WHEN** 一个当代 change（首事件 `change_created`，无 `handoff.json`）被创建或推进到归档
- **THEN** 系统 SHALL NOT 要求该 change 存在 `handoff.json`
- **AND** 系统 SHALL NOT 产出 `workflow-state.json`
- **AND** 系统 SHALL NOT 提供 `flow status` 投影查询

#### Scenario: 老世代 handoff.json 作为只读历史保留

- **GIVEN** 一个既存的老世代 change（事件日志首事件为 `initialized`，含 `handoff.json`）
- **WHEN** 维护者审计历史
- **THEN** 该文件 SHALL 保持原样，SHALL NOT 被改写
- **AND** 系统 SHALL NOT 要求为它补建 `proposal.md`

### Requirement: 机械门禁的信任边界

witnessloop 的受保护路径解释门禁 SHALL 定位为**防误改**（防止改动受保护路径时漏配解释事件）而非**防伪造**。它 SHALL 只校验存在匹配的结构化解释事件（`event_type` / `artifact_path` / 必填字段齐全），SHALL NOT 尝试判定该事件是否出自真实的人类授权——`approved_by` 是自由字符串，无法被机械校验。本地 Bash 写前拦截 SHALL 同样定位为**防遗忘 / 本地 checkpoint**，SHALL NOT 被描述为防对抗或替代 CI。

相对退役前的本仓 checker，witnessloop 的事件解析 **SHALL 被如实记录为少了两项校验**：事件 `schema`（旧 checker 要求 `workflow-event/v1`）与 `change_id` 与事件日志所属目录的一致性。witnessloop 只读取 `event_type` / `artifact_path` / `reason` / `approved_by`（`events.py`），因此任意 change（含历史归档）的事件都可能覆盖本 PR 的受保护写入。该退步 SHALL 写入信任边界记录，SHALL NOT 被描述为「完全等价移交」。

文档 SHALL NOT 声称这些门禁提供了防伪造保证；其信任边界 SHALL 明文记录该边界位于仓库写权限（谁拥有 push 权限），而非门禁本身。

#### Scenario: 解释门禁只校验事件的存在与形状

- **WHEN** 一个受保护路径被改动
- **THEN** witnessloop SHALL 要求存在覆盖该路径的结构化解释事件（匹配的 `event_type` 与 `artifact_path`，且必填字段齐全）
- **AND** witnessloop SHALL NOT 校验发起事件的 change 是否真实立项、或 `approved_by` 是否对应真实身份

#### Scenario: 信任边界有明文记录

- **WHEN** 维护者查阅受保护路径门禁的保证强度
- **THEN** `docs/known-debt.md` SHALL 将其记录为「防误改而非防伪造」，并说明三条加固设想（绑定真实身份 / PR 审批背书 / 收紧锚点）均已排除
- **AND** 该边界 SHALL NOT 只以「待加固」措辞记录而暗示机械加固可行

#### Scenario: change_id / schema 绑定退步被登记

- **WHEN** 维护者对比退役前后的事件校验
- **THEN** 文档 SHALL 记录 witnessloop 不校验事件 `schema` 与 `change_id` 目录一致性
- **AND** SHALL NOT 把受保护写入检查描述为与旧 checker 完全等价
