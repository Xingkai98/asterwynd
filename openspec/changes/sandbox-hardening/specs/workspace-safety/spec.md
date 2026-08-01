# Workspace Safety Spec

## ADDED Requirements

### Requirement: AST Command Validation

The workspace safety system SHALL validate shell commands by parsing them into an AST, SHALL allow only predefined command sentence patterns, and SHALL enforce parameter type and range constraints (e.g., timeout as int in [1,600], paths within the workspace, no wildcard/redirection/pipe combinations).

#### Scenario: blocked wildcard and pipe combination

- Given a command using a wildcard with redirection or pipe combination
- When the AST validator parses the command
- Then the command is rejected
- And a structured sandbox event with `denied` is recorded

### Requirement: cgroup Resource Limits

The sandbox SHALL enforce CPU/memory resource limits via cgroup v2, SHALL auto-kill processes exceeding limits, and SHALL record kill/oom events in the trace.

#### Scenario: memory limit exceeded

- Given a sandboxed process exceeding the memory limit
- When the cgroup v2 controller detects the overrun
- Then the process is auto-killed
- And a `kill`/`oom` event is recorded in the trace

### Requirement: Malicious Prompt Regression Suite

The sandbox SHALL maintain a regression suite of 50+ malicious prompt cases (fork bomb, pipe-to-shell, rm -rf, /etc/passwd read, exfiltration, etc.) and SHALL assert all are blocked end-to-end.

#### Scenario: rm -rf root blocked

- Given a malicious prompt attempting `rm -rf /`
- When the command is passed to the sandbox
- Then the command is rejected
- And the regression suite asserts the block

### Requirement: Sandbox Event Tracing

The sandbox SHALL record structured events (denied/reason/kill/oom) into the trace recorder with a schema aligned with the observability event model.

#### Scenario: sandbox denial recorded

- Given a command rejected by the sandbox
- When the sandbox event is recorded
- Then a structured event with `denied` and `reason` is written to the trace recorder

## MODIFIED Requirements

- `workspace-safety`: command validation SHALL use AST-based sentence validation instead of string-prefix matching, preserving the `assert_command_allowed` contract.
