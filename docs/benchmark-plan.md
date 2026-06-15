# MyAgent Benchmark Plan

**Status**: Revised after reference-repo review
**Date**: 2026-06-15

---

## 1. Goal

Build a reproducible benchmark system for local coding agents.

The benchmark should answer:

- Can MyAgent solve repository-level coding tasks?
- How often does it pass the validation tests?
- How many iterations, tool calls, tokens, and seconds does it use?
- What failure modes dominate?
- How does it compare with mature coding agents such as Claude Code and Codex?

The first version should evaluate MyAgent only. Later versions should add
adapters for external agents.

## 2. Industry References

### SWE-bench

SWE-bench is the closest reference for repository-level issue fixing.

Useful concepts:

| Concept | Meaning |
|---------|---------|
| `base_commit` | Git commit used as the starting point |
| `problem_statement` | Issue text shown to the agent |
| `gold_patch` | Human/reference solution patch, not shown to the agent |
| `test_patch` | Hidden evaluation tests applied by the harness |
| harness | Environment setup, patch application, test execution, reporting |

SWE-bench keeps dataset fields separate from prompt templates. Different agents
can wrap the same `problem_statement` in different prompts.

### Terminal-Bench

Terminal-Bench is useful for trace and run-metadata design.

Useful concepts:

- Task-level sandbox execution.
- Per-run duration, token, cost, and reward metrics.
- Step-level trajectory logs containing agent messages, tool calls, and
  observations.
- Human audit of trajectories to find task loopholes or invalid solutions.

### Aider Benchmark

Aider's benchmark is useful for edit-format evaluation.

Useful concepts:

- Editing format matters.
- Whole-file rewrites are simple but expensive.
- Search/replace and diff-based edits are more efficient but need stronger
  validation.
- Cost and malformed-edit failures are important metrics.

## 3. Benchmark Scope

### First Version

Build a SWE-bench-like local benchmark for this repository.

Scope:

- 20 local MyAgent tasks.
- Each task starts from a `base_commit`.
- Each task has an issue-style problem statement.
- Each task has a validation command.
- Each run saves result, trace, final diff, and test output.
- `gold.patch` and `test.patch` are supported by schema but optional.

### Later Versions

Expand to:

- 2-3 small external Python repositories.
- Hidden tests via `test.patch`.
- External agent adapters for Claude Code, Codex, and shell-based runners.
- Summary reports across agents and models.

## 4. Task Directory Structure

Use one directory per task:

```text
benchmarks/tasks/<task-id>/
  task.json
  issue.md
  gold.patch      # optional, not shown to the agent
  test.patch      # optional, applied by evaluator only
```

`issue.md` contains the task text shown to the agent.

`gold.patch` is a reference solution. It is used for analysis only and should
not be used as the grading oracle.

`test.patch` contains hidden evaluation tests. It should be applied only after
the agent finishes.

## 5. Task Schema

Minimal schema:

```json
{
  "id": "myagent-001-edit-tool",
  "repo": "local/myagent",
  "base_commit": "abc123",
  "problem_statement_file": "issue.md",
  "test_command": "pytest -q tests/agent/tools/test_edit_tool.py",
  "category": "feature",
  "difficulty": "easy",
  "timeout_seconds": 300,
  "gold_patch_file": "gold.patch",
  "test_patch_file": "test.patch",
  "hints_text": null
}
```

Required fields for the first version:

- `id`
- `repo`
- `base_commit`
- `problem_statement_file`
- `test_command`
- `timeout_seconds`

Optional but reserved fields:

- `gold_patch_file`
- `test_patch_file`
- `hints_text`
- `category`
- `difficulty`

## 6. Runner Design

The benchmark runner should not execute tasks directly in the development
working tree.

First version execution model:

```text
1. Create a temporary git worktree for the task.
2. Check out task.base_commit.
3. Read issue.md.
4. Run the selected agent in the task worktree.
5. Save the agent trace and final diff.
6. If hidden tests are enabled and test.patch exists, apply test.patch.
7. Run test_command.
8. Save result.json, test_output.txt, final.diff, and runner.log.
9. Remove or retain the worktree depending on debug mode.
```

Use `git worktree` first because it is fast and simple. Docker or stronger
container isolation can be added later.

## 7. Agent Runner Interface

The benchmark harness should depend on an adapter interface, not directly on
MyAgent internals.

Conceptual interface:

```text
AgentRunner.run(task, workspace, output_dir) -> AgentRunResult
```

Initial adapters:

| Adapter | Purpose |
|---------|---------|
| `MyAgentRunner` | Run the local MyAgent coding mode |
| `ShellCommandRunner` | Run an arbitrary shell command as a baseline or wrapper |

Later adapters:

| Adapter | Purpose |
|---------|---------|
| `ClaudeCodeRunner` | Run Claude Code on the same task set |
| `CodexRunner` | Run Codex on the same task set |

This lets the benchmark compare agents without changing task definitions.

## 8. Prompt Construction

The dataset should store `problem_statement`, not a fixed prompt.

The runner should create the agent-specific prompt. For MyAgent, a first version
can be:

```text
You are a coding agent working in this repository.

Task:
<problem_statement>

Requirements:
- Modify only files inside the workspace.
- Keep the change scoped to the task.
- Run this validation command before finishing:
  <test_command>
- Report the final diff summary and test result.
```

This mirrors SWE-bench's separation between neutral task data and agent-specific
prompting.

## 9. Trace Design

Use three layers of records.

### 9.1 Runner Logs

Runner logs describe benchmark infrastructure actions:

- Worktree creation.
- Checkout result.
- Agent command invocation.
- Hidden test patch application.
- Test command execution.
- Cleanup.

Output file:

```text
runner.log
```

### 9.2 Agent Trajectory

Agent trajectory describes the agent's solving process.

Default `trace.json` should store structured summaries:

```json
{
  "task_id": "myagent-001-edit-tool",
  "full_trace": false,
  "steps": [
    {
      "step": 1,
      "type": "llm_iteration",
      "iteration": 0,
      "assistant_preview": "I will inspect the tool system first.",
      "tool_calls": [
        {
          "name": "Grep",
          "arguments_preview": {
            "pattern": "class .*Tool",
            "path": "agent/tools"
          }
        }
      ]
    },
    {
      "step": 2,
      "type": "tool_result",
      "tool_name": "Grep",
      "status": "ok",
      "duration_ms": 42,
      "observation_preview": "agent/tools/base.py:26:class Tool"
    },
    {
      "step": 3,
      "type": "edit",
      "tool_name": "Edit",
      "status": "ok",
      "path": "agent/tools/builtin/edit.py",
      "diff_summary": "1 file changed, 42 insertions"
    },
    {
      "step": 4,
      "type": "test",
      "command": "pytest -q tests/agent/tools/test_edit_tool.py",
      "exit_code": 0,
      "duration_ms": 1380,
      "output_preview": "5 passed"
    }
  ]
}
```

`--full-trace` can additionally store:

- Full messages before each LLM call.
- Raw LLM responses.
- Complete tool arguments.
- Complete tool outputs.

### 9.3 Metrics Summary

Metrics summary should be machine-readable.

Output file:

```text
result.json
```

Example:

```json
{
  "task_id": "myagent-001-edit-tool",
  "agent": "myagent",
  "model": "gpt-4.1",
  "status": "passed",
  "test_exit_code": 0,
  "duration_seconds": 82.4,
  "iterations": 5,
  "tool_calls": 17,
  "edit_count": 2,
  "test_runs": 1,
  "input_tokens": 18420,
  "output_tokens": 1320,
  "failure_category": null
}
```

## 10. Run Output Structure

Each benchmark invocation should create a timestamped run directory:

```text
benchmarks/runs/<run-id>/
  run.json
  summary.md
  tasks/
    <task-id>/
      result.json
      trace.json
      final.diff
      test_output.txt
      runner.log
```

`run.json` stores global metadata:

```json
{
  "run_id": "2026-06-14T12-30-00",
  "agent": "myagent",
  "model": "gpt-4.1",
  "started_at": "2026-06-14T12:30:00Z",
  "ended_at": "2026-06-14T12:42:11Z",
  "task_count": 20,
  "passed": 13,
  "warnings": 2,
  "failed": 7
}
```

`summary.md` should provide a readable table:

```markdown
# Benchmark Run

| Task | Status | Time | Iterations | Tool Calls | Failure |
|------|--------|------|------------|------------|---------|
| myagent-001-edit-tool | passed | 82s | 5 | 17 | - |
| myagent-002-benchmark-cli | passed_with_warnings | 104s | 20 | 29 | max_iterations |
| myagent-002-policy-deny-env | failed | 120s | 8 | 22 | edit_validation |
```

## 11. Metrics

First version metrics:

| Metric | Meaning |
|--------|---------|
| `status` | `passed`, `passed_with_warnings`, `failed`, or `error` |
| `duration_seconds` | Wall-clock runtime |
| `iterations` | LLM iterations |
| `tool_calls` | Total tool calls |
| `edit_count` | Successful edit or patch operations |
| `test_runs` | Number of validation commands run |
| `test_exit_code` | Final validation command exit code |
| `input_tokens` | Input tokens, if available |
| `output_tokens` | Output tokens, if available |
| `failure_category` | Normalized failure reason |

Later metrics:

- Cost estimate.
- Diff size.
- Files touched.
- Number of failed edit attempts.
- Hidden-test pass/fail.
- Agent self-reported confidence.

`passed_with_warnings` means the final validation command passed, but the agent
runner reported a non-clean process outcome such as `max_iterations`. It should
count separately from a clean pass when evaluating agent quality.

## 12. Failure Taxonomy

Initial categories:

| Category | Meaning |
|----------|---------|
| `setup_error` | Worktree, checkout, dependency, or environment setup failed |
| `tool_error` | Tool failed unexpectedly |
| `edit_validation` | Edit could not be applied |
| `test_failure` | Tests ran and failed |
| `test_timeout` | Validation command timed out |
| `max_iterations` | Agent hit max iteration limit |
| `no_change` | Agent produced no meaningful diff |
| `out_of_scope_change` | Agent changed denied or unrelated files |
| `model_failure` | Agent stopped without a useful solution |

## 12.1 Current Implementation Snapshot

Implemented:

- Task schema loading from `benchmarks/tasks/<task-id>/task.json`.
- Detached git worktree execution at each task's `base_commit`.
- Fake, shell, and MyAgent runner adapters.
- Coding-agent prompt builder for benchmark runs.
- Hidden `test.patch` application after the agent finishes.
- Per-task `result.json`, `trace.json`, `final.diff`, `test_output.txt`, and
  `runner.log`.
- Run-level `run.json` and `summary.md`.
- `passed_with_warnings` for test-passing but non-clean agent runs.
- P0 local task pack:
  - `myagent-readme-title`
  - `myagent-002-myagent-runner`
  - `myagent-003-agentloop-trace`
  - `myagent-004-benchmark-cli`

Recent real MyAgent benchmark results:

| Run | Max Iterations | Passed | Warnings | Failed | Main Signal |
|-----|----------------|--------|----------|--------|-------------|
| `2026-06-14T15-12-53` | 20 | 2 | 0 | 2 | Two medium tasks produced no useful diff before max iterations. |
| `2026-06-14T16-57-13` | 50 | 2 | 0 | 2 | The agent edited code for the failed tasks, but 002 exposed async-test dependency assumptions and 003 missed trace propagation through `MyAgentRunner`. |

Current interpretation: the benchmark harness is healthy enough to guide
development. The remaining failures primarily reflect MyAgent coding-agent
capability and benchmark environment sharp edges, not missing artifact capture
or task isolation.

### Recent Design Decisions (2026-06-15)

After reviewing 7 reference repos (claude-code, codex, hermes-agent, nanobot,
openclaw, opencode, pi-mono):

- **No RunTestsTool.** All 7 repos use their shell/bash tool to run tests.
  MyAgent will enhance BashTool with structured JSON output instead.
- **No PatchTool.** Claude Code, nanobot, and pi-mono use Edit-only with exact
  replacement. Models produce malformed patches more often than exact
  replacements.
- **ListFilesTool + FindTool added.** 4/7 repos provide dedicated file listing
  tools. MyAgent currently has no file discovery mechanism. Ignore patterns are
  separate from WorkspacePolicy denied patterns — user-extensible via
  `MYAGENT_IGNORE_PATTERNS`.
- **BashTool gets command allowlist/denylist.** Following hermes-agent and
  nanobot's pattern of regex-based deny patterns with user-extensible allow
  patterns via environment variables.
- **BashTool returns JSON string.** `execute() -> str` interface unchanged;
  structured fields encoded as JSON for LLM and benchmark consumption.
- **Trace always full.** No truncation, no `--full-trace` flag. Overhead is
  negligible, debugging value is high.

## 13. First Task Set

Tasks are selected from the repository's git history. Each task corresponds to
a real commit, giving a realistic problem statement from the commit message, an
automatically-generated `gold.patch` from `git diff base_commit..commit`, and a
validation command from the associated tests.

Selection criteria:

- Change size is manageable (not a full rewrite).
- A verifiable test command exists.
- Covers diverse categories: edit correctness, security, observability, file
  discovery, bash tooling.

Candidate categories (20 tasks total):

| Category | Count | Example task |
|----------|-------|-------------|
| Edit correctness | 4 | Exact replacement, ambiguous match, empty string, replace_all |
| Security / policy | 3 | Deny .env writes, path traversal, bash command deny |
| Tool capability | 4 | InspectGitDiff, ListFiles, Find, Bash structured output |
| Observability | 3 | Trace tool calls, trace edits, trace completeness |
| Benchmark infra | 4 | Task schema, single-task runner, result JSON, summary report |
| Agent prompt | 2 | Coding prompt injection, test command discipline |

Detailed task design and commit selection deferred to implementation phase. |

## 14. Testing Strategy

The benchmark system should be tested separately from the agent's model quality.
Most tests should use fake agents and tiny local repositories so results are
deterministic.

### 14.1 Unit Tests

Recommended coverage:

| Area | Test Coverage |
|------|---------------|
| Task schema parser | Required fields, optional `gold_patch_file` and `test_patch_file`, relative file resolution, invalid JSON, missing issue file |
| Task model validation | Invalid timeout, duplicate IDs, unsupported difficulty/category values if constrained |
| Prompt builder | Converts `problem_statement` into an agent-specific prompt, includes validation command instruction |
| Result model | Serializes `result.json`, stable status values, token fields optional |
| Failure taxonomy | Maps setup, timeout, test failure, no diff, and max iteration outcomes |
| Trace writer | Writes full trace with all iterations, tool calls, and observations |
| Summary renderer | Produces deterministic `summary.md` tables |

Suggested files:

```text
tests/benchmark/test_task_schema.py
tests/benchmark/test_prompt_builder.py
tests/benchmark/test_result_model.py
tests/benchmark/test_trace_writer.py
tests/benchmark/test_summary_renderer.py
tests/benchmark/test_failure_taxonomy.py
```

### 14.2 Runner Integration Tests

Runner tests should create tiny temporary git repositories and avoid real LLM
calls.

Recommended coverage:

- Creates a task worktree at `base_commit`.
- Runs a fake agent that writes a known file.
- Captures `final.diff`.
- Runs `test_command` and records pass/fail.
- Applies `test.patch` only after the fake agent finishes.
- Does not expose `gold.patch` or `test.patch` to the agent workspace.
- Cleans up worktrees by default and preserves them in debug mode.
- Handles dirty source repositories according to policy.

Suggested files:

```text
tests/benchmark/test_worktree_runner.py
tests/benchmark/test_hidden_test_patch.py
tests/benchmark/test_benchmark_runner.py
```

### 14.3 Adapter Contract Tests

Every agent adapter should satisfy the same contract:

```text
AgentRunner.run(task, workspace, output_dir) -> AgentRunResult
```

Coverage:

- `MyAgentRunner` writes trace and returns status.
- `ShellCommandRunner` captures stdout/stderr and exit code.
- Adapter timeout is reported as `test_timeout` or `tool_error`, depending on
  phase.
- Adapter failures do not prevent the benchmark harness from writing
  `result.json`.

External adapters for Claude Code and Codex can start with contract tests using
mock shell commands before running real tools.

### 14.4 End-to-End Benchmark Smoke Tests

End-to-end tests should run a tiny benchmark with 1-2 tasks and a fake agent.

Coverage:

- Creates `benchmarks/runs/<run-id>/`.
- Writes `run.json`, `summary.md`, per-task `result.json`, `trace.json`,
  `final.diff`, `test_output.txt`, and `runner.log`.
- Correctly reports one passing and one failing task.
- Produces deterministic output except timestamps and durations.

Real-agent benchmark runs should be manual or opt-in because they depend on API
keys, model behavior, and cost.

## 15. Phases

### P0: Self-Benchmark Skeleton

- Task schema. Implemented.
- Worktree runner. Implemented.
- MyAgent runner. Implemented.
- Result files. Implemented.
- 3-5 local tasks. Implemented with the P0 local task pack.
- Warning status for test-passing but non-clean agent runs. Implemented.

### P1: Complete Benchmark (merged from former P1-P3)

- BashTool structured output (exit_code, stdout, stderr, duration, timed_out).
- Coding prompt updated to instruct running validation command before finishing.
- Command allowlist and denylist with .env extensibility.
- ListFilesTool and FindTool with ignore rules (separate from WorkspacePolicy).
- Apply `test.patch` only after agent completion with hidden test status.
- 20 local tasks total.
- ShellCommandRunner for baseline comparisons.
- Package distribution via `uv tool install` / `pip install`.

External adapters (Claude Code, Codex) and comparative reports deferred to a
future phase.

## 16. Relationship to Coding Agent Roadmap

The benchmark plan measures the coding-agent roadmap.

Recommended development rhythm:

```text
1. Build one coding-agent capability.
2. Add one or more benchmark tasks that require it.
3. Run the benchmark.
4. Classify failures.
5. Improve the agent.
```

This avoids building unmeasured features and avoids a benchmark harness that has
no capable agent to evaluate.
