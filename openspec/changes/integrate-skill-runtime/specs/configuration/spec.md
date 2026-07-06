## ADDED Requirements

### Requirement: Configuration declares skill roots

Configuration SHALL allow users to declare local skill roots.

#### Scenario: Skill roots configured

- **GIVEN** configuration includes `skills.roots`
- **WHEN** configuration is loaded
- **THEN** each root SHALL be parsed as a filesystem path
- **AND** `~` and environment variables SHOULD be expanded

#### Scenario: Skill roots omitted

- **GIVEN** configuration omits `skills.roots`
- **WHEN** configuration is loaded
- **THEN** the system SHOULD use a conservative default that includes repo-local skills when available

#### Scenario: Invalid skill roots config

- **GIVEN** `skills.roots` is not a list of strings
- **WHEN** configuration is loaded
- **THEN** configuration loading SHALL fail fast with a readable error
