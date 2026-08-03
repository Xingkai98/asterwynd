# Interview Script Spec

## ADDED Requirements

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
