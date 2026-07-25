## ADDED Requirements

### Requirement: CLI --workspace parameter
The `asterwynd` CLI SHALL accept an optional `--workspace` parameter that specifies the primary working directory.

#### Scenario: User starts with explicit workspace
- **GIVEN** a directory `/home/user/project` exists
- **WHEN** the user runs `asterwynd --workspace /home/user/project run "hello"`
- **THEN** the working directory is set to `/home/user/project`
- **AND** ASTER.md and configuration are read from that directory

#### Scenario: Invalid workspace path
- **GIVEN** `/nonexistent/path` does not exist
- **WHEN** the user runs `asterwynd --workspace /nonexistent/path run "hello"`
- **THEN** the CLI exits with an error message and non-zero exit code

#### Scenario: Relative path rejected
- **WHEN** the user runs `asterwynd --workspace ./relative/path run "hello"`
- **THEN** the CLI exits with an error requiring an absolute path

#### Scenario: Tilde expansion
- **GIVEN** `~/projects/myapp` exists
- **WHEN** the user runs `asterwynd --workspace ~/projects/myapp run "hello"`
- **THEN** the tilde is expanded to the home directory and the workspace is set correctly
