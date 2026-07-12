# Asterwynd Coding Agent Roadmap

**Status**: Revised after reference-repo review
**Date**: 2026-06-15

---

## 1. New Positioning

Asterwynd should evolve from a lightweight general-purpose agent framework into a
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
| Tools | Read, Write, Edit, Bash, Grep, ListFiles, Find, InspectGitDiff, RepoMap, SymbolSearch, WebSearch, WebFetch |
| Hooks | Logging, tracing, retry, token budget hooks |
| Memory | AutoCompact-style message compaction |
| Subagents | Background delegation and parent channel injection |
| Web UI | Chat UI, debug timeline, session/run identifiers, Plan Document display, planning state display, Markdown rendering, and tool result display controls |
| Coding tools | Workspace policy, exact-match `Edit`, workspace-aware `Bash`, `InspectGitDiff`, hardened `Write` behavior, and `LspDiagnostics` feedback on Write/Edit |
| Code intelligence | Repo map, tree-sitter symbols, Python AST extraction, and LSP semantic tools (definition, references, hover, document symbols, workspace symbols, diagnostics) |
| Benchmark harness | Local task schema, detached worktree runner, fake/shell/Asterwynd adapters, hidden test patches, trace artifacts, summary reports, CLI entry point, and Claw-SWE-Bench integration for SWE-bench Verified comparison |

The remaining gap is coding-agent reliability. The project now has the P0
self-benchmark harness and basic coding tools, but real Asterwynd benchmark runs
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

Asterwynd's differentiator should be:

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
| `InspectGitDiff` | Show current repository diff |
| `ListFiles` | List directory contents with ignore rules |
| `Find` | Recursive file search by glob pattern |

`ListFiles` and `Find` share a common set of default ignore patterns
(`.git`, `node_modules`, `__pycache__`, `.venv`, etc.) distinct from
`WorkspacePolicy` denied patterns. Denied patterns are hard security
boundaries (enforced by all write tools); ignore patterns are cosmetic
noise reduction for listing/searching. Users can append custom ignore
patterns via `ASTERWYND_IGNORE_PATTERNS` in `.env`.

The first editing primitive is `Edit`, modeled after mainstream coding agents:

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

`Patch` (unified diff application) was considered and rejected after reviewing 7
reference repos. Claude Code, nanobot, and pi-mono use only exact replacement
(no Patch tool). Models produce malformed patches more often than simple exact
replacements. Asterwynd stays with Edit only.

### 4.3 BashTool with Structured Output

Rather than a dedicated `RunTestsTool`, enhance `BashTool` to return structured
output as a JSON string. All seven reference repos (claude-code, codex,
hermes-agent, nanobot, openclaw, opencode, pi-mono) use their shell/bash tool to
run tests — none has a dedicated test runner tool. The Tool interface
(`execute() -> str`) remains unchanged; BashTool returns a JSON string the LLM
can parse.

Structured output fields:

```text
exit_code: int
stdout: str
stderr: str
duration_ms: float
timed_out: bool
```

This gives benchmark reports machine-readable metrics and gives the LLM clearer
feedback than a wall of raw text.

### 4.4 Command Allowlist and Denylist

`BashTool` enforces command safety through two layers:

- **Denylist**: commands matching these regex patterns are rejected. Defaults
  cover destructive ops (`rm -rf /`, `mkfs`, `dd if=`), system control
  (`shutdown`, `reboot`), fork bombs, pipe-to-shell (`curl | sh`), and
  destructive git (`reset --hard`, `push --force`).
- **Allowlist**: commands matching these safe prefixes are allowed only after
  denylist checks pass. Defaults include read-only git commands, pytest
  invocations, common package/test commands, and file-inspection commands.

The denylist is extensible via environment variable:

```bash
ASTERWYND_COMMAND_DENYLIST="docker rm,docker system prune"
```

User deny patterns are appended to the hardcoded defaults, so the safety
baseline cannot be removed by configuration. The allowlist is intentionally
defined in code and is not user-extensible through environment variables.

### 4.5 Coding System Prompt

The default system prompt currently describes a helpful tool-using assistant.
The coding-agent mode needs a dedicated policy.

It should instruct the model to:

- Inspect the repository before editing.
- Prefer `Edit` for precise modifications.
- Use `InspectGitDiff` after meaningful edits.
- Run the provided validation command before finalizing.
- Keep changes scoped to the task.
- Report final diff summary and test status.
- Avoid modifying denied or unrelated files.

### 4.6 TraceRecorder

Trace recording is a first-class artifact for both benchmark and interactive use.

Trace stores the full record of each run:

- LLM iteration number.
- Full assistant response.
- Tool calls and arguments.
- Tool status, duration, and full observation.
- Edit count and diff summary.
- Test command, exit code, and output.
- Final diff path.

No truncation — tool outputs and LLM responses are captured in full. The
overhead is negligible compared to the debugging value.

### 4.7 Test Feedback Loop

The agent should be able to move through this loop:

```text
edit -> inspect diff -> run tests -> read failure -> edit again
```

The enhanced `BashTool` structured output captures:

- Command.
- Exit code.
- Duration.
- Truncated stdout/stderr.
- Whether the command timed out.

This gives the model better feedback and gives benchmark reports better metrics.

### 4.8 Failure Taxonomy

Failures should be classified so benchmark results can guide development.

Initial categories:

| Category | Meaning |
|----------|---------|
| `setup_error` | Benchmark or workspace setup failed |
| `tool_error` | Tool execution failed unexpectedly |
| `edit_validation` | Edit could not be applied |
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

Goal: make Asterwynd safely edit code in a local repository and record what it did.

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

### P2: Cross-Agent Benchmark Comparison

Goal: run the same benchmark tasks with external coding agents, and compare
results side-by-side with Asterwynd.

Deliverables:

- `ClaudeCodeRunner` — subprocess adapter that invokes `claude` CLI in the
  task worktree, passes the problem statement as a prompt, and captures the
  final git diff and stdout log. Done.
- `CodexRunner` — same pattern for the `codex` CLI. Deferred (authentication
  complexity).
- Unified comparison report — `benchmarks/compare.py` generates MD + HTML
  side-by-side tables with pass rate and timing. Done.
- Contract tests — each adapter satisfies `AgentRunner.run()`, so the
  benchmark harness can treat Claude Code the same as Asterwynd. Done.
- First comparison results: Asterwynd 11/23 (48%) vs Claude Code 9/23 (39%)
  with same DeepSeek model — pass rates and failure modes overlap heavily,
  suggesting the model is the bottleneck. Done.
- Claw-SWE-Bench path — `claw-swe-bench/` registers Asterwynd, Aider, and
  OpenCode adapters for SWE-bench Verified / mini comparison under one
  orchestrator and evaluation harness. Asterwynd runs through
  `claw-swe-bench/` adapter inside the target container. Done for integration;
  full result reporting depends on benchmark runs.

Design notes:

- In the local runner path, each external agent runs as a subprocess inside the
  detached worktree, same as `ShellCommandRunner`. No internal traces are
  collected — only final git diff, stdout/stderr log, and test results from the
  harness.
- In the Claw-SWE-Bench path, each agent adapter runs inside or against the
  SWE-bench container, and the framework collects the final patch before
  evaluation.
- This mirrors SWE-bench's evaluation model: the benchmark grades the
  outcome (does the patch pass hidden tests?), not the process.
- The comparison is fair: each agent uses its own tools, its own prompt
  strategy, and the same task definition. The goal is to understand
  whether Asterwynd's framework or the underlying model is the performance
  ceiling.

Interview talking point:

> I built adapters to run Claude Code and Codex in the same benchmark
> harness as Asterwynd. Same tasks, same hidden tests, same grading — only
> the agent runtime differs. This tells us whether the gap is in our
> framework or in the model.

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
| `InspectGitDiffTool` | Clean diff, modified file diff, untracked file behavior, output truncation |
| `BashTool` | Structured output fields, command allowlist/denylist enforcement, timeout, output truncation |
| `ListFilesTool` | Directory listing, ignore rules, workspace boundary |
| `FindTool` | Pattern matching, recursive search, ignore rules |
| `TraceRecorder` | Records LLM iterations, tool calls, tool results, edit summaries, test summaries |
| Failure taxonomy | Maps known outcomes to stable categories |

These should live near the existing tool tests, for example:

```text
tests/agent/tools/test_edit_tool.py
tests/agent/tools/test_inspect_git_diff_tool.py
tests/agent/tools/test_bash_tool_structured_output.py
tests/agent/tools/test_list_files_tool.py
tests/agent/tools/test_find_tool.py
tests/agent/test_workspace_policy.py
tests/agent/test_trace_recorder.py
```

### 6.2 Integration Tests

Integration tests should use temporary git repositories or temporary directories
to verify multiple modules together.

Recommended coverage:

- `EditTool` + `WorkspacePolicy` + `InspectGitDiffTool`.
- `BashTool` executing a small local pytest suite with structured output.
- `BashTool` allowlist/denylist enforcement.
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
ASTERWYND_PROVIDER=openai ASTERWYND_MODEL=<model> uv run pytest tests/agent/test_coding_agent_real.py --run-real-api -v
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

- Every P1 feature has at least one benchmark task.
- P2 enables cross-agent comparison: same tasks, same hidden tests, same
  grading — only the agent runtime differs. This reveals whether the gap is
  in Asterwynd's framework or in the underlying model.
