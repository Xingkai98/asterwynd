# change-documentation 规格

## Purpose

定义 OpenSpec change 的设计、诊断、类型元数据和机械检查规则，确保需求、设计、根因分析、任务拆分和实现验收职责清晰分离。

## Requirements

### Requirement: Detailed design artifact
Every non-trivial OpenSpec change SHALL include a `design.md` artifact that
records the implementation approach and major technical decisions before
development starts.

#### Scenario: Feature change with implementation work
- **WHEN** an OpenSpec change introduces or modifies runtime behavior,
  architecture, configuration, dependencies, or tests
- **THEN** the change includes `design.md`
- **AND** the design documents goals, non-goals, decisions, risks, and testing
  strategy

#### Scenario: Design reviewed before implementation
- **WHEN** implementation work is about to start for a non-trivial change
- **THEN** the `design.md` has been reviewed and accepted by a human reviewer
- **AND** mechanical checks are not treated as design approval

#### Scenario: Trivial documentation-only change
- **WHEN** an OpenSpec change only fixes wording, broken links, or stale
  documentation without altering project behavior or process
- **THEN** the proposal may state that no separate detailed design is required

### Requirement: Pre-implementation design grilling
Every non-trivial OpenSpec change SHALL complete a pre-implementation design
grilling pass before tests or implementation begin.

#### Scenario: grill-with-docs is available
- **WHEN** implementation work is about to start for a non-trivial change
- **THEN** the agent uses `grill-with-docs` to challenge `design.md` against
  the current codebase, project vocabulary, spec delta, dependencies, risks,
  testing strategy, and documentation impact
- **AND** unresolved decisions are written back to the change artifacts or
  stable project documentation before implementation begins

#### Scenario: grill-with-docs is unavailable
- **WHEN** the current agent environment does not provide `grill-with-docs`
- **THEN** the agent performs an equivalent design grilling process manually
- **AND** every key implementation detail, dependency, risk, test strategy, and
  documentation impact has a recorded final decision before implementation
  begins

### Requirement: Diagnosis artifact
Bug, regression, incident, and research-driven OpenSpec changes SHALL include a
`diagnosis.md` artifact before implementation begins.

#### Scenario: Bug-driven change
- **WHEN** a change is created to fix a failing tool, UI defect, regression, or
  production-like incident
- **THEN** the change includes `diagnosis.md`
- **AND** the diagnosis records symptom, reproduction, evidence, hypotheses,
  root cause, fix options, and regression test expectations

#### Scenario: Diagnosis leads to design
- **WHEN** diagnosis shows that the fix requires a new architecture or
  substantial behavior change
- **THEN** the change also includes `design.md`
- **AND** the design references the diagnosis as the reason for the chosen
  approach

### Requirement: Artifact responsibility boundaries
OpenSpec change artifacts SHALL have distinct responsibilities so that
requirements, design decisions, investigation evidence, and implementation
tasks do not overwrite each other.

#### Scenario: Change artifact separation
- **WHEN** an agent prepares an OpenSpec change
- **THEN** `proposal.md` explains why and what changes
- **AND** spec delta files define normative behavior
- **AND** `design.md` explains how the change will be implemented
- **AND** `diagnosis.md` records root-cause evidence when applicable
- **AND** `tasks.md` lists ordered implementation steps

### Requirement: Change type metadata
Every OpenSpec change SHALL declare a primary change type and a secondary type
list in `proposal.md`.

#### Scenario: Single-type change
- **WHEN** a change has one clear work type
- **THEN** `proposal.md` includes `## Change Type`
- **AND** it declares `primary` as one allowed type
- **AND** it declares `secondary: []`

#### Scenario: Multi-type change
- **WHEN** a change is triggered by one type of work and also includes other
  work qualities
- **THEN** `primary` records the trigger
- **AND** `secondary` records additional types
- **AND** the change satisfies the artifact requirements for every declared
  type

### Requirement: Mechanical artifact checks
The project SHALL use a local artifact checker for mechanical document rules
without attempting to judge technical design quality.

#### Scenario: Artifact checker scope
- **WHEN** the project artifact checker validates an active change
- **THEN** it checks valid `Change Type` metadata, required files, required
  section headings, non-empty section bodies, and template placeholders
- **AND** it does not score design correctness, architecture quality, or
  implementation trade-offs

#### Scenario: Artifact checker combines type rules
- **WHEN** a change declares both `primary` and `secondary` types
- **THEN** the artifact checker applies the requirements for the union of all
  declared types

### Requirement: Reference agent parity artifact

项目 SHALL 维护一份 reference-agent parity artifact，用于记录主流 coding agent 能力与 Asterwynd 能力、证据和后续 OpenSpec change 之间的映射关系。

#### Scenario: 记录对标能力项

- **GIVEN** 维护者新增或更新一个对标能力项
- **WHEN** 该能力项进入 reference-agent parity artifact
- **THEN** 条目 SHALL 记录参考对象、来源链接、参考能力描述、Asterwynd 状态、Asterwynd 证据、缺口优先级、后续 change 和核对日期
- **AND** Asterwynd 状态 SHALL 使用 `supported`、`equivalent`、`partial`、`gap` 或 `out_of_scope`

#### Scenario: 标记已有或等价能力

- **GIVEN** 某个对标能力项被标记为 `supported` 或 `equivalent`
- **WHEN** 维护者检查该条目
- **THEN** 条目 SHALL 链接到规格、代码、测试、benchmark、trace 或运行证据中的至少一种
- **AND** 不得只凭自然语言断言声称已支持

#### Scenario: 标记能力缺口

- **GIVEN** 某个对标能力项被标记为 `gap` 或重要 `partial`
- **WHEN** 该能力符合 Asterwynd 当前项目定位
- **THEN** 条目 SHALL 链接到已有 OpenSpec change 或记录待新增 change
- **AND** 不得在对标矩阵中直接替代需求、设计和测试策略

### Requirement: Reference agent 分层

项目 SHALL 在对标矩阵中区分主对标对象、产品能力参照、专项参照和呈现参照，避免把所有参考项目视为同等实现目标。

#### Scenario: 使用 Codex CLI 作为主对标

- **GIVEN** 对标能力来自 Codex CLI
- **WHEN** 该能力属于本地 coding agent 核心路径
- **THEN** 条目 SHOULD 标记 Codex CLI 为 `primary_reference`

#### Scenario: 使用辅参照

- **GIVEN** 对标能力来自 Claude Code、Aider、OpenCode 或 AtomCode
- **WHEN** 该能力用于判断产品边界、专项能力或指标呈现方式
- **THEN** 条目 SHALL 标记其参考角色
- **AND** SHALL 说明该能力是否需要 Asterwynd 等价覆盖
