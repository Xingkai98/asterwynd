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

### Requirement: Skill reload refreshes runtime skills

The runtime SHALL support manual reload of configured skill roots.

#### Scenario: Reload skills

- **GIVEN** the user requests skill reload
- **WHEN** the runtime reloads skills
- **THEN** subsequent runs SHALL use the refreshed skill set
- **AND** reload diagnostics SHALL be observable
