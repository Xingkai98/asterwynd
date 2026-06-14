# MyAgent Coding Agent Roadmap

**Status**: Draft, P0 benchmark harness implemented
**Date**: 2026-06-14

---

## 1. New Positioning

MyAgent should evolve from a lightweight general-purpose agent framework into a
local, benchmarkable coding agent framework.

The target workflow is:

```text
understand repository -> modify code -> run tests -> record trace -> report result
```

The goal is not to clone Claude Code or Codex feature-for-feature. The goal is to
build a smaller but explainable coding agent runtime whose behavior can be
measured, debugged, and compared.

## 2. Current State

The current system already has useful agent infrastructure:

| Area | Current Capability |
|------|--------------------|
| Agent loop | LLM -> tool calls -> tool results -> repeat |
| LLM adapters | OpenAI-compatible and Anthropic providers |
| Tools | Read, Write, Bash, Grep, WebSearch, WebFetch |
| Hooks | Logging, tracing, retry, token budget hooks |
| Memory | AutoCompact-style message compaction |
| Subagents | Background delegation and parent channel injection |
| Web UI | Chat UI and debug timeline support |
| Coding tools | Workspace policy, exact-match `Edit`, workspace-aware `Bash`, `InspectGitDiff`, and hardened `Write` behavior |
| Benchmark harness | Local task schema, detached worktree runner, fake/shell/MyAgent adapters, hidden test patches, trace artifacts, summary reports, and CLI entry point |

The remaining gap is coding-agent reliability. The project now has the P0
self-benchmark harness and basic coding tools, but real MyAgent benchmark runs
still show failures on multi-file tasks and trace propagation tasks.

Recent real-agent benchmark signal:

| Run | Max Iterations | Result | Notes |
|-----|----------------|--------|-------|
| `2026-06-14T15-12-53` | 20 | 2 passed, 2 failed | Two failed tasks produced no code changes before the iteration limit. |
| `2026-06-14T16-57-13` | 50 | 2 passed, 2 failed | The agent began implementing the failed tasks, but one task exposed async-test environment assumptions and one missed required cross-file trace propagation. |

This suggests the benchmark infrastructure is usable now, while the agent needs
better task decomposition, test command discipline, dependency handling, and
cross-file completion checks.

## 3. Core Product Thesis

MyAgent's differentiator should be:

> An explainable, reproducible, benchmarkable local coding agent.

That means each run should produce enough evidence to answer:

- What task was the agent solving?
- Which files did it inspect?
- What edits did it make?
- Which tests did it run?
- Why did it fail, if it failed?
- How many iterations, tool calls, tokens, and seconds did it use?

## 4. Core Modules

### 4.1 WorkspacePolicy

`WorkspacePolicy` defines the safe operating boundary for coding tasks.

Responsibilities:

- Track the active workspace root.
- Reject reads and writes outside the workspace.
- Deny sensitive paths such as `.git/`, `.env*`, secrets, caches, logs, and
  generated benchmark artifacts.
- Provide command policy checks for shell and test commands.
- Provide git diff snapshot helpers.
- Support benchmark isolation by running tasks in temporary worktrees.

This should be a first-class runtime module, not duplicated inside each tool.

Minimal first version:

```text
workspace_root
denied_patterns
assert_read_allowed(path)
assert_write_allowed(path)
assert_command_allowed(command)
snapshot_git_diff()
```

### 4.2 Coding Tools

The default general-purpose tools are not enough for coding-agent behavior.

Required coding tools:

| Tool | Purpose |
|------|---------|
| `Edit` | Exact old/new string replacement in a file |
| `Patch` | Apply structured or unified diff changes |
| `InspectGitDiff` | Show current repository diff |
| `RunTests` | Run configured test commands and capture structured results |
| `ListFiles` | Discover files with workspace-aware ignore rules |

The first editing primitive should be `Edit`, modeled after mainstream coding
agents:

```json
{
  "path": "agent/loop.py",
  "old_string": "exact text from the file",
  "new_string": "replacement text",
  "replace_all": false
}
```

Important semantics:

- The old string must match exactly.
- By default, exactly one match is required.
- Multiple matches should fail unless `replace_all` is explicitly true.
- Edits must pass `WorkspacePolicy`.
- Each successful edit should be traceable and diffable.

`Patch` should be added after `Edit` is stable. It is useful for larger
multi-file changes, but models produce malformed patches more often than simple
exact replacements.

### 4.3 Coding System Prompt

The default system prompt currently describes a helpful tool-using assistant.
The coding-agent mode needs a dedicated policy.

It should instruct the model to:

- Inspect the repository before editing.
- Prefer `Edit` for precise modifications.
- Use `InspectGitDiff` after meaningful edits.
- Run relevant tests before finalizing when possible.
- Keep changes scoped to the task.
- Report final diff summary and test status.
- Avoid modifying denied or unrelated files.

### 4.4 TraceRecorder

Trace recording is now a first-class benchmark artifact and should continue to
become a first-class interactive coding-agent capability.

Default trace should store structured summaries:

- LLM iteration number.
- Assistant response preview.
- Tool calls and arguments, with sensitive fields redacted if needed.
- Tool status, duration, and observation preview.
- Edit count and diff summary.
- Test command, exit code, and output summary.
- Final diff path.

A `--full-trace` mode can store full messages, raw LLM responses, and complete
tool observations for debugging.

### 4.5 Test Feedback Loop

The agent should be able to move through this loop:

```text
edit -> inspect diff -> run tests -> read failure -> edit again
```

`RunTests` should not just return raw stdout. It should capture:

- Command.
- Exit code.
- Duration.
- Truncated stdout/stderr.
- Whether the command timed out.
- Optional parsed failure summary.

This gives the model better feedback and gives benchmark reports better metrics.

### 4.6 Failure Taxonomy

Failures should be classified so benchmark results can guide development.

Initial categories:

| Category | Meaning |
|----------|---------|
| `setup_error` | Benchmark or workspace setup failed |
| `tool_error` | Tool execution failed unexpectedly |
| `edit_validation` | Edit/Patch could not be applied |
| `test_failure` | Tests ran but failed |
| `test_timeout` | Tests timed out |
| `max_iterations` | Agent hit iteration limit |
| `no_change` | Agent produced no useful diff |
| `out_of_scope_change` | Agent modified denied or unrelated files |
| `model_failure` | Agent response did not make actionable progress |

The benchmark system uses this taxonomy in `result.json` and `summary.md`.
`passed_with_warnings` is used when hidden validation passes but the agent run
still reports a non-clean outcome such as `max_iterations`.

## 5. Implementation Phases

### P0: Minimum Coding-Agent Loop

Goal: make MyAgent safely edit code in a local repository and record what it did.

Deliverables:

- `WorkspacePolicy` minimal implementation. Done.
- `EditTool` with exact replacement semantics. Done.
- `InspectGitDiffTool`. Done.
- Coding-agent system prompt. Done for benchmark runs.
- TraceRecorder summary trace. Done for benchmark artifacts.
- Tests for path policy, edit semantics, and diff inspection. Done.
- Local benchmark task pack and CLI runner. Done.
- `passed_with_warnings` status for test-passing but non-clean agent runs. Done.

Interview talking point:

> I moved from direct file writes to a controlled edit protocol. The model
> proposes exact replacements, while the runtime validates workspace boundaries,
> applies changes, and records diffs.

### P1: Test-Aware Coding Agent

Goal: close the edit/test/fix loop.

Deliverables:

- `RunTestsTool`.
- Structured test result model.
- Better command allowlist and timeout policy.
- Test failure feedback loop in the prompt.
- Trace entries for test runs.

Current priority:

- Standardize benchmark validation commands so async tests consistently use the
  project environment.
- Teach the agent to verify hidden-test-like requirements by running the exact
  visible `test_command`, not nearby test suites only.
- Improve completion checks so the agent stops after a clean pass and continues
  when required files were not edited.

Interview talking point:

> The agent is not only generating patches; it can run the same validation loop
> a developer would run and use failures as feedback.

### P2: Patch and Multi-File Changes

Goal: support larger edits and stronger workflow ergonomics.

Deliverables:

- `PatchTool` for unified or structured diffs.
- `ListFilesTool` with ignore rules.
- Better diff summaries.
- Optional full trace mode.
- Stronger protection for generated files and sensitive files.

Interview talking point:

> I separated editing protocols by reliability: exact replacement for stable
> local edits, patch application for larger multi-file changes.

### P3: Product Polish

Goal: make the coding agent usable outside benchmark runs.

Deliverables:

- CLI coding mode.
- Web debug timeline improvements.
- Human-readable final reports.
- Optional approval mode for risky commands or writes.

Interview talking point:

> The same runtime supports interactive use and benchmark use because workspace
> policy, trace recording, and tools are shared.

## 6. Testing Strategy

Coding-agent capabilities should be covered at three levels: unit tests for
deterministic semantics, integration tests for tool composition, and end-to-end
tests for agent behavior with fake LLMs.

### 6.1 Unit Tests

Unit tests should cover pure runtime behavior without real LLM calls.

Recommended coverage:

| Area | Test Coverage |
|------|---------------|
| `WorkspacePolicy` | Allows paths inside root, rejects `..` traversal, rejects absolute paths outside root, denies `.git/`, `.env*`, secrets, caches, and benchmark run artifacts |
| `EditTool` | Exact single replacement, missing old string, ambiguous matches, `replace_all`, empty replacement, newline preservation, permission denial through `WorkspacePolicy` |
| `PatchTool` | Valid patch application, malformed patch rejection, patch outside workspace rejection, partial failure behavior |
| `InspectGitDiffTool` | Clean diff, modified file diff, untracked file behavior, output truncation |
| `RunTestsTool` | Passing command, failing command, timeout, output truncation, structured exit code and duration |
| `TraceRecorder` | Records LLM iteration summaries, tool calls, tool results, edit summaries, test summaries, redaction and full-trace mode |
| Failure taxonomy | Maps known outcomes to stable categories |

These should live near the existing tool tests, for example:

```text
tests/agent/tools/test_edit_tool.py
tests/agent/tools/test_patch_tool.py
tests/agent/tools/test_inspect_git_diff_tool.py
tests/agent/tools/test_run_tests_tool.py
tests/agent/test_workspace_policy.py
tests/agent/test_trace_recorder.py
```

### 6.2 Integration Tests

Integration tests should use temporary git repositories or temporary directories
to verify multiple modules together.

Recommended coverage:

- `EditTool` + `WorkspacePolicy` + `InspectGitDiffTool`.
- `RunTestsTool` executing a small local pytest suite.
- TraceRecorder receiving events from a tool execution path.
- Coding prompt builder injecting task, workspace, and test command.
- Denied-path behavior across all write-capable tools.

These tests should not require network access or real API keys.

### 6.3 Agent Loop Tests

Agent-loop tests should use fake LLM responses to simulate a coding task:

```text
LLM asks to read file -> LLM asks to edit file -> LLM asks to run tests -> final answer
```

Coverage:

- Tool-call protocol remains valid after edits and test runs.
- The agent can recover from an edit validation failure.
- The agent records trace entries in the expected order.
- The agent stops with `max_iterations` without fabricating success.

### 6.4 Manual/Real-Model Tests

Real API tests should stay optional because they are slower and non-deterministic.

Suggested command shape:

```bash
MYAGENT_PROVIDER=openai MYAGENT_MODEL=<model> uv run pytest tests/agent/test_coding_agent_real.py --run-real-api -v
```

Real-model tests should focus on smoke coverage:

- Can the agent solve one tiny local edit task?
- Does it run the requested test command?
- Does it produce a trace and final diff?

## 7. Relationship to Benchmark Plan

This roadmap builds the agent capability. The benchmark plan proves whether that
capability works.

```text
build coding capability -> run benchmark -> analyze failures -> improve agent
```

The two plans should be developed together:

- Every P0/P1 coding feature should have at least one benchmark task.
- Benchmark failures should feed back into the failure taxonomy and tool design.
- External comparisons to Claude Code and Codex should happen after MyAgent has
  a stable self-benchmark harness.
