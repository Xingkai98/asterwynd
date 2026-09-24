# 面试讲稿 规格

## Purpose

定义 面试讲稿 能力域的规格。当前为基线状态；深化需求通过 OpenSpec change 的 spec delta 演进。

## Requirements

### Requirement: 面试讲稿 能力域基线

面试讲稿 能力域 SHALL 提供基础能力，深化需求通过 OpenSpec change 的 ADDED Requirements 合入演进。

#### Scenario: 能力域可扩展

- **GIVEN** 一个针对 面试讲稿 能力域的 OpenSpec change
- **WHEN** 该 change 的 spec delta 被接受
- **THEN** 能力域的 requirement 随 ADDED Requirements 演进

### Requirement: Layered interview script

The project SHALL maintain an interview-script documentation set under
`docs/interview-script/` organized into layered questions ordered from
high-level overview to in-depth specifics, so interviewers can walk through
the project's implementation from breadth to depth.

#### Scenario: top-level question per file

- GIVEN the interview-script documentation set
- WHEN a reader wants a single top-level interview question
- THEN the question has its own file named `Q<NN>-<slug>.md`
- AND the file contains a `## 讲稿` section and a `## 代码走读` section

#### Scenario: script covers the module landscape

- GIVEN the interview-script documentation set
- WHEN an interviewer asks about the project's overall structure
- THEN the set covers the module landscape, the AgentLoop, and how the
  project differs from Claude Code / Codex / Cursor

### Requirement: Script depth and code walkthrough

Each interview question SHALL include a spoken script of 300-500 characters
and a code walkthrough that is detailed enough to substantiate the script,
listing entry call chains, key files, key functions, and design rationale.

#### Scenario: script is spoken at interview

- GIVEN an interview question file
- WHEN the candidate narrates the answer
- THEN the `## 讲稿` section gives a 300-500 character oral narrative
  covering how it is implemented, why it is designed that way, and a trade-off
  or pitfall encountered

#### Scenario: code walkthrough substantiates the script

- GIVEN an interview question file
- WHEN the reader needs to understand the code behind the script
- THEN the `## 代码走读` section lists the entry call chain, key files with
  `file:line` references, and the design rationale for each

### Requirement: Maintenance guidance

The project SHALL record a maintenance guidance note for the interview-script
documentation set so that new design or architecture changes update the
corresponding question scripts and walkthroughs.

#### Scenario: maintenance guidance is documented

- GIVEN a new design or architecture change
- WHEN the change lands
- THEN the project documentation records that the corresponding
  interview-script question should be reviewed and updated
- AND the guidance is advisory, not a hard gate

### Requirement: 面试叙事与评测现状对齐

面试叙事文档 SHALL 将评测现状口径（任务数、测试数、工具数）与升级方向分层表述：现状数字 SHALL 与当前实现一致（任务 schema 扩展后本地任务数、测试函数数、内置工具数）；升级方向（场景×难度分层任务集、pass^k/cost@pass/fault_owner 等）SHALL 标注「设计已定、实现中」，不得把未实现写成已实现。

#### Scenario: 现状口径分层

- **GIVEN** 面试叙事文档涉及评测数字
- **WHEN** 表述评测能力
- **THEN** 现状数字 SHALL 与当前实现一致
- **AND** 升级方向 SHALL 标注「设计已定、实现中」
