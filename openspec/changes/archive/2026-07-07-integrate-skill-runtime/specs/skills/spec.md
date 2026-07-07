## ADDED Requirements

### Requirement: Runtime loads configured skills

The agent runtime SHALL load skills from configured skill roots before running user prompts.

#### Scenario: Load skills from configured roots

- **GIVEN** configuration declares one or more skill roots
- **WHEN** the agent runtime starts
- **THEN** it SHALL load valid Markdown skills from those roots
- **AND** retain diagnostics for invalid skill files

#### Scenario: Missing skill root

- **GIVEN** a configured skill root does not exist
- **WHEN** skills are loaded
- **THEN** the runtime SHALL continue startup
- **AND** record a diagnostic for that root

#### Scenario: Skill directory format

- **GIVEN** a configured root contains `skills/<name>/SKILL.md` style entries
- **WHEN** skills are loaded
- **THEN** the runtime SHALL parse each `SKILL.md`
- **AND** SHALL retain each skill source path for diagnostics and slash command metadata

#### Scenario: Duplicate skill name

- **GIVEN** multiple configured roots contain the same skill name
- **WHEN** skills are loaded
- **THEN** the first loaded skill SHALL win
- **AND** subsequent duplicates SHALL be skipped with a diagnostic

### Requirement: Skill index is visible to the model

The runtime SHALL include a concise skill index in model-visible context for each run. The index SHALL list loaded skill names, descriptions, and user invocation syntax without including full skill prompts.

#### Scenario: Skill index rendered

- **GIVEN** skills are loaded
- **WHEN** AgentLoop calls the LLM
- **THEN** model-visible messages SHALL include a concise skill index
- **AND** the index SHALL NOT include full `SKILL.md` bodies

### Requirement: Always skills are injected into system context

Always skills SHALL be included in the agent system context for every run.

#### Scenario: Always skill loaded

- **GIVEN** a loaded skill has `always: true`
- **WHEN** the agent builds system context
- **THEN** the skill prompt SHALL be included with a clear skill name boundary

### Requirement: Matched skills are injected for the current run

Non-always skills SHALL be matched against the current user input and injected only for that run.

#### Scenario: User input matches a skill

- **GIVEN** a non-always skill matches the current user input
- **WHEN** the agent runs that prompt
- **THEN** the skill prompt SHALL be included in the current run context
- **AND** it SHALL NOT be permanently appended to conversation memory

#### Scenario: User input does not match a skill

- **GIVEN** no non-always skill matches the current user input
- **WHEN** the agent runs that prompt
- **THEN** no non-always skill prompt SHALL be injected

#### Scenario: User input matches trigger

- **GIVEN** a non-always skill declares a trigger phrase
- **WHEN** the current user input contains that trigger
- **THEN** the skill prompt SHALL be included in the current run context

### Requirement: LLM can activate skills with a runtime tool

The runtime SHALL expose a low-risk `ActivateSkill` tool that lets the LLM activate an already loaded skill for the current run.

#### Scenario: LLM activates known skill

- **GIVEN** the LLM calls `ActivateSkill` with a loaded skill name
- **WHEN** the tool executes
- **THEN** the skill SHALL become active for the current run
- **AND** the next LLM call in that run SHALL include the full skill prompt
- **AND** the activation SHALL be observable with source `llm_tool`

#### Scenario: LLM activates unknown skill

- **GIVEN** the LLM calls `ActivateSkill` with an unknown skill name
- **WHEN** the tool executes
- **THEN** the tool SHALL return a readable error
- **AND** no skill prompt SHALL be injected

### Requirement: Skill reload refreshes runtime skills

The runtime SHALL support manual reload of configured skill roots.

#### Scenario: Reload skills

- **GIVEN** the user requests skill reload
- **WHEN** the runtime reloads skills
- **THEN** subsequent runs SHALL use the refreshed skill set
- **AND** reload diagnostics SHALL be observable

### Requirement: 用户可调用 skill 出现在 slash command 中

Skill runtime SHALL 将用户可调用 skills 注册到 central slash command registry，使 CLI/Web command catalog 能提示并分发这些 skill commands。

#### Scenario: Skill 出现在 slash command catalog

- **GIVEN** 已加载的某个 skill 可由用户调用
- **WHEN** 请求 slash command catalog
- **THEN** catalog SHALL 包含该 skill 对应的 command
- **AND** command metadata SHALL 包含 source `skill`
- **AND** command SHALL 在可用时包含 description 和 argument hint

#### Scenario: Skill slash command 保留自然语言请求

- **GIVEN** 已加载一个名为 `review-skill` 的用户可调用 skill
- **WHEN** 用户发送 `/review-skill 帮我审一下这个 change`
- **THEN** command handler SHALL 将 `review-skill` 解析到该 skill
- **AND** SHALL 将 `帮我审一下这个 change` 作为 skill args 传给 prompt 组装逻辑
- **AND** SHALL NOT 将原始 slash command 作为普通用户消息发送给 AgentLoop

#### Scenario: Skill command 显式组装 prompt

- **GIVEN** 用户可调用 skill 包含 prompt 内容和参数占位符
- **WHEN** skill slash command 携带 args 执行
- **THEN** runtime SHALL 基于 skill prompt 和 args 组装 model-visible context
- **AND** 产生的 Agent run SHALL 标记为 slash-command-triggered，并记录 skill name
