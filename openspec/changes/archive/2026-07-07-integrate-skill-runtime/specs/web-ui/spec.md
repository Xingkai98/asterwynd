## ADDED Requirements

### Requirement: Web Chat exposes skill slash commands

Web Chat SHALL expose user-invocable skills through the slash command catalog and SHALL run `/skill-name args` as a skill-triggered Agent run.

#### Scenario: Web command catalog includes skills

- **GIVEN** Web UI has loaded user-invocable skills
- **WHEN** the browser requests `/api/slash-commands`
- **THEN** the response SHALL include those skill commands
- **AND** each skill command SHALL include source `skill` and kind `prompt`

#### Scenario: Web skill command starts agent run with args

- **GIVEN** Web Chat has loaded a user-invocable skill named `code-review`
- **WHEN** the user sends `/code-review 帮我审一下这个 change`
- **THEN** the WebSocket SHALL send a command result
- **AND** queue `code-review` activation with source `slash_command`
- **AND** start an Agent run with `帮我审一下这个 change` as the user message
- **AND** SHALL NOT send the raw slash command as a normal user message to AgentLoop
