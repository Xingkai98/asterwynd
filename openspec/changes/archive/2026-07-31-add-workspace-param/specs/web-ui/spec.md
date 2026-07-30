## ADDED Requirements

### Requirement: Web --workspace parameter
The `asterwynd web` subcommand SHALL forward the `--workspace` parameter to the web server.

#### Scenario: Web server starts with specified workspace
- **GIVEN** `/home/user/project` exists
- **WHEN** the user runs `asterwynd --workspace /home/user/project web`
- **THEN** the web server's SessionManager creates all sessions with that workspace root

### Requirement: Session workspace management via slash command
The web UI and interactive CLI SHALL support `/session-workspace` to manage additional workspace directories.

#### Scenario: Add additional workspace
- **WHEN** the user enters `/session-workspace add /tmp/data`
- **THEN** `/tmp/data` is added to the session's readable/writable paths
- **AND** the directory is created if it does not exist

#### Scenario: List workspaces
- **WHEN** the user enters `/session-workspace list`
- **THEN** the primary workspace and all additional workspaces are displayed

#### Scenario: Remove additional workspace
- **WHEN** the user enters `/session-workspace remove /tmp/data`
- **THEN** `/tmp/data` is removed from the session's accessible paths
