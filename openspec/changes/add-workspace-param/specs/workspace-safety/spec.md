## ADDED Requirements

### Requirement: Additional workspace security validation
The `add_root` method SHALL validate paths before adding them as additional workspaces.

#### Scenario: System directory rejected
- **WHEN** an additional workspace `/etc` is requested
- **THEN** the request is rejected with a security error

#### Scenario: Ancestor directory rejected
- **GIVEN** the primary workspace is `/home/user/project`
- **WHEN** an additional workspace `/home/user` is requested
- **THEN** the request is rejected because it would expose the primary workspace's parent

#### Scenario: Primary workspace subdirectory rejected
- **GIVEN** the primary workspace is `/home/user/project`
- **WHEN** an additional workspace `/home/user/project/subdir` is requested
- **THEN** the request is rejected because it is already within scope
