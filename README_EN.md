# MyAgent

A local Coding Agent system built with Python. It focuses on agent runtime, tool calling, repository understanding, code editing and validation, observability, and benchmark feedback loops.

## Features

| Module | Description |
|------|------|
| **AgentLoop** | Core loop of about 100 lines. Messages are the only state, and capabilities are delegated to plugins. |
| **ToolRegistry** | Dynamic tool registration with the `@tool_parameters` decorator. Includes file, command, code intelligence, and web research tools. |
| **Code Intelligence** | Tree-sitter multi-language symbol extraction, Repo Map, Python AST symbol extraction, and LSP semantic tools such as definition, references, hover, and diagnostics. |
| **WorkspacePolicy** | Workspace safety boundary that rejects path traversal, sensitive file writes, and dangerous commands. |
| **SandboxExecutor** | Subprocess sandbox with structured output: exit_code, stdout, stderr, duration, and timed_out. |
| **HookManager** | 6 lifecycle extension points with built-in logging, retry, tracing, and token budget hooks. |
| **MemoryManager** | AutoCompact token compression. When over budget, it asks the LLM to summarize older context. |
| **SkillLoader** | Markdown skill files with YAML frontmatter and prompt body, loaded always or on demand. |
| **SubAgentManager** | Sub-session runtime with independent transcripts, multiple sub-sessions, repeated runs per sub-session, and explicit inspect. |
| **TraceRecorder** | Full trace recording for iterations, tool calls, edits, and tests. |
| **Benchmark** | 23 local coding-agent tasks, SWE-bench Docker harness tasks, and a Claw-SWE-Bench multi-agent comparison entry point. |

## Quick Start

```bash
# Install dependencies with uv
uv sync --extra dev              # runtime + development/test dependencies

# Configure API key and model
cp .env.example .env
# Edit .env and set OPENAI_API_KEY or ANTHROPIC_API_KEY
# Optional: set OPENAI_BASE_URL for another OpenAI-compatible API, such as DeepSeek
# Optional: set MYAGENT_PROVIDER (openai / anthropic) and MYAGENT_MODEL as defaults

# Run CLI (OpenAI by default, using MYAGENT_MODEL from .env)
uv run python cli.py main "Hello"

# Or override model/provider
uv run python cli.py main --model gpt-4o-mini "Hello"
uv run python cli.py main --provider anthropic --model claude-sonnet-4-20250514 "Hello"

# Interactive mode
uv run python cli.py main --interactive

# Start Web UI (using .env config)
uv run python cli.py web --port 8000

# Web UI with verbose logging
MYAGENT_LOG_LEVEL=DEBUG uv run python cli.py web --port 8000 --model deepseek-v4-pro

# Run tests
uv run pytest -q

# Run local coding-agent benchmark (fake runner smoke)
uv run python cli.py benchmark benchmarks/tasks \
  --agent fake \
  --source-repo . \
  --runs-dir /tmp/myagent-benchmark-smoke \
  --fake-edit-file README.md \
  --fake-old-string '# MyAgent' \
  --fake-new-string '# MyAgent Coding Agent'

# Run the Claw-SWE-Bench unified harness (requires Docker images and env vars first)
cd claw-swe-bench
uv run python run_infer.py \
  --claw myagent \
  --dataset verified \
  --instance_file config/verified_mini_50.txt \
  --run_id myagent-lite \
  --model deepseek-v4-pro
```

`uv run` is not required by the application itself. It is the recommended environment isolation method because it uses the project virtual environment managed by `uv`, making dependency resolution more reproducible. If your current shell Python environment already has the dependencies installed, equivalent commands such as `python3 cli.py main "Hello"` or `pytest -q` also work.

## Built-In Tools

| Tool | Permission Level | Description |
|------|---------|------|
| `Read` | read_only | Read files with line limits. |
| `Write` | read_write | Create new files and refuse to overwrite existing files. |
| `Edit` | read_write | Exact text replacement. Requires a unique `old_string` match and supports `replace_all`. |
| `Bash` | dangerous | Execute shell commands in the sandbox and return structured JSON: exit_code, stdout, stderr, duration, timed_out. |
| `Grep` | read_only | Regex search over files or directories. |
| `InspectGitDiff` | read_only | Inspect the current workspace git diff. |
| `ListFiles` | read_only | List directory contents and automatically ignore `.git`, `node_modules`, and similar noise. |
| `Find` | read_only | Recursively search files by glob pattern. |
| `RepoMap` | read_only | Generate repository structure and top-level symbol summaries for supported languages. |
| `SymbolSearch` | read_only | Search supported symbols by name within the repository. |
| `WebSearch` | read_only | DuckDuckGo HTML search with stable text results that include provider metadata. |
| `WebFetch` | read_only | Fetch webpage text and return status, type, and truncation diagnostics. |

The Bash tool has built-in command safety policy. It first checks regex deny patterns covering cases such as `rm -rf /`, fork bombs, and `curl | sh`, then matches allowed safe command prefixes such as `git status`, `pytest`, `uv`, and `npm`. Project-level command deny rules and ListFiles / Find ignore rules are extended through `myagent.yaml`; see `myagent.example.yaml`.

## Project Structure

```text
agent/
├── loop.py                  # AgentLoop core (~100 lines)
├── llm.py                   # LLM Protocol + ToolCallDelta
├── openai_llm.py            # OpenAI Chat Completions implementation
├── anthropic_llm.py         # Anthropic Messages API implementation
├── workspace_policy.py      # WorkspacePolicy safety boundary
├── trace_recorder.py        # TraceRecorder full trace recording
├── message.py               # Message dataclass + constructors
├── result.py                # RunResult + StopReason + ToolCallMade
├── tools/
│   ├── base.py              # Tool ABC + @tool_parameters decorator
│   ├── registry.py          # ToolRegistry
│   ├── sandbox.py           # SandboxExecutor + SandboxResult
│   └── builtin/             # Built-in tools
├── hooks/
│   ├── manager.py           # HookManager + Hook Protocol
│   └── builtin/             # 4 built-in hooks
├── memory/
│   └── manager.py           # MemoryManager + AutoCompact
├── skills/
│   └── loader.py            # SkillLoader + Skill dataclass
└── subagent/
    └── manager.py           # SubAgentManager sub-session runtime

benchmarks/                  # Local benchmark runner
├── tasks/                   # 23 coding tasks (6 categories, 3 difficulty levels)
├── runner.py                # BenchmarkRunner + SWE-bench style isolation
├── agent_runner.py          # AgentRunner adapters: fake/shell/myagent
├── models.py                # Failure taxonomy + metric models
├── prompt.py                # Coding-agent prompt builder
└── task_schema.py           # Task schema loading

claw-swe-bench/              # Claw-SWE-Bench unified harness copy and adapters
└── claw_swebench/claws/
    ├── myagent.py           # MyAgent adapter
    ├── aider.py             # Aider adapter
    └── opencode_adapter.py  # OpenCode adapter (limited by endpoint support)

skills/                      # Skill files
├── code-review.md
└── research.md
```

## Architecture

### Core Loop

```text
messages -> LLM -> tool_calls? -> [execute tools] -> append results -> repeat
                |
                v
            no tools -> return content
```

`AgentLoop.run()` is the single state manager. `messages` is the only mutable state. Subsystems such as tool execution, memory management, and sub-session runtime hold references through dependency injection.

### Tool Registration

```python
from agent.tools import Tool, tool_parameters, ToolRegistry

@tool_parameters(
    name="MyTool",
    description="What it does",
    parameters={"type": "object", "properties": {"arg": {"type": "string"}}}
)
class MyTool(Tool):
    read_only = True

    async def execute(self, arg: str, **kwargs) -> str:
        return f"result: {arg}"

registry = ToolRegistry()
registry.register(MyTool())
```

### Hook Extension

```python
from agent.hooks import HookManager, Hook

class MyHook(Hook):
    async def before_iteration(self, iteration, messages): ...
    async def after_llm_call(self, response): ...
    async def before_tool_execute(self, tool_call): ...
    async def after_tool_execute(self, tool_call, result): ...
    async def on_error(self, error): ...
    async def on_completion(self, result): ...

agent = AgentLoop(hooks=HookManager([MyHook()]), ...)
```

### AutoCompact

`MemoryManager.compact_if_needed()` checks the token budget after each tool-call round. When over budget, it compacts history:

- Keep all `role=system` messages.
- Keep the most recent N messages.
- Ask the LLM to summarize the middle section.

```python
memory = MemoryManager(max_tokens=80_000, recent_window=10, llm=openai_llm)
```

### Sub-Session Runtime

```python
subagent = subagent_manager.create_subagent(
    name="research",
    description="Read-only code and document investigation",
    mode="read_only",
)

run = await subagent_manager.run_subagent(
    subagent_id=subagent["subagent_id"],
    task="Search for related information",
    wait=True,
)

print(run["status"], run["summary"])
```

## Extension Guide

### Add a New Tool

1. Create `agent/tools/builtin/my_tool.py`, inherit from the `Tool` ABC, and use `@tool_parameters`.
2. Import it in `agent/tools/__init__.py` and add it to `get_default_tools()`.
3. Register it in `ToolRegistry`.

### Add a New Hook

1. Implement the `Hook` Protocol. All 6 methods may be no-op implementations.
2. Pass it into `HookManager([MyHook()])`.

### Add a New Skill

Create a `.md` file under `skills/`:

```markdown
---
name: my-skill
description: Skill description
tools: [Read, Bash]
always: false
---

# Skill Title

Prompt instructions go here...
```

## Web UI

Start the Web UI:

```bash
# Basic startup (uses MYAGENT_PROVIDER and MYAGENT_MODEL from .env)
uv run python cli.py web --port 8000

# Override model
uv run python cli.py web --port 8000 --model deepseek-v4-pro

# Override provider
uv run python cli.py web --port 8000 --provider anthropic --model claude-sonnet-4-20250514

# Debug mode (Chat + Debug views)
MYAGENT_DEBUG=enabled uv run python cli.py web --host 127.0.0.1 --port 8000

# Verbose logs (record LLM input/output to files)
MYAGENT_LOG_LEVEL=DEBUG uv run python cli.py web --port 8000
```

- **Chat view**: Normal conversation, assistant Markdown rendering, tool-call visualization, long tool-result folding by display policy, current session id / run id / session mode, switching between `build` / `read_only` / `plan`, and Plan Document plus planning state display.
- **Debug view**: Enabled by `MYAGENT_DEBUG=enabled`; shows each round of:
  - Full message list sent to the LLM, including system prompt, history, and tool results.
  - Raw LLM response, including content, stop_reason, and tool_calls.
  - Tool-call details, including name, arguments, and result.
  - Memory compaction events sent by AgentLoop through the Web session event stream.

CLI interactive mode supports switching the current session mode with `/mode build`, `/mode read_only`, and `/mode plan`. CLI single-run mode still uses `--mode` for the initial mode.

### Logs

Each startup creates an independent log file under `logs/`, such as `myagent-20260526-123456.log`:

| Environment Variable | Default | Description |
|---------|--------|------|
| `MYAGENT_PROVIDER` | `openai` | LLM provider: `openai` or `anthropic`. |
| `MYAGENT_MODEL` | provider default | Model name. |
| `MYAGENT_LOG_LEVEL` | `INFO` | At `DEBUG`, logs LLM request payloads and raw response JSON. |
| `MYAGENT_DEBUG` | `disabled` | When `enabled`, turns on the Debug Web UI. |

Configuration precedence: explicit CLI arguments > process environment variables > `.env` loaded values > `myagent.yaml` > code defaults. API key, base URL, provider, model, debug, and log level continue to use `.env` or environment variables. Agent mode, mode deny overrides, tool policy, tool-result display thresholds, and benchmark defaults use `myagent.yaml`.

- Logs are written to both terminal and file.
- HTTP 4xx/5xx errors always log request payload and response body.
- Each log file is capped at 5 MB, keeping the latest 5 rotated files.

Browser tests:

```bash
playwright install chromium
MYAGENT_DEBUG=enabled uv run pytest tests/web_tests/test_browser.py --run-real-api -v
```

## Benchmark

MyAgent currently has two benchmark paths:

- `benchmarks/`: the built-in project runner, using 23 local tasks and a small number of `swebench-*` external tasks to validate the MyAgent coding-agent loop.
- `claw-swe-bench/`: the Claw-SWE-Bench unified harness, comparing MyAgent, Aider, OpenCode, and other external coding agents on the same SWE-bench Verified instances.

### Quick Validation (Fake Agent, Deterministic)

```bash
uv run python cli.py benchmark benchmarks/tasks \
  --agent fake \
  --source-repo . \
  --runs-dir /tmp/myagent-benchmark-smoke \
  --fake-edit-file README.md \
  --fake-old-string '# MyAgent' \
  --fake-new-string '# MyAgent Coding Agent'
```

### Real Agent Evaluation

```bash
uv run python cli.py benchmark benchmarks/tasks \
  --agent myagent \
  --source-repo . \
  --runs-dir /tmp/myagent-benchmark \
  --max-iterations 80
```

### Claw-SWE-Bench Comparison Evaluation

See [CLAW-SWE-BENCH.md](./CLAW-SWE-BENCH.md) for full environment setup. Minimal command shape:

```bash
cd claw-swe-bench
uv run python run_infer.py \
  --claw myagent \
  --dataset verified \
  --instance_file config/verified_mini_50.txt \
  --run_id myagent-lite \
  --model deepseek-v4-pro

uv run python run_eval.py --run_id myagent-lite --dataset verified
```

### Task Set

23 tasks are extracted from the project git history and cover 6 categories:

| Category | Count | Example |
|------|------|------|
| Tool implementation | 5 | ToolRegistry, SandboxExecutor, Read/Write tools, Bash workspace |
| Safety policy | 3 | Reject `.env` writes, path traversal protection, Bash command policy |
| Agent core | 7 | AgentLoop, MemoryManager, SkillLoader, SubAgent system |
| Observability | 3 | HookManager, logging/tracing hooks, retry/budget hooks |
| Benchmark infrastructure | 3 | Failure classification, runner timeout, resource leak fixes |
| Prompting | 2 | Coding system prompt, validation command injection |

### Evaluation Flow

Local `myagent-*` tasks:

1. Create an isolated git worktree at the task `base_commit`.
2. Hide `benchmarks/tasks/` so the agent cannot inspect evaluation files.
3. Run the agent in the worktree.
4. Capture the agent diff, excluding tests with `:!tests/`.
5. Reset the worktree and replay the source changes.
6. Apply `test.patch` as the hidden evaluation test.
7. Run the validation command.
8. Write `result.json`, `trace.json`, and `runner.log`; write `final.diff` after diff capture completes, and `test_output.txt` after the validation command actually runs.

External `swebench-*` tasks:

1. Clone the external repository specified by the task and check out `base_commit`.
2. The agent edits code in the benchmark workspace and produces the final git patch.
3. The runner performs a run-level Docker preflight.
4. If Docker is available, pass the patch to the SWE-bench Docker harness for validation.
5. If Docker is unavailable, write `result.json`, `trace.json`, and `runner.log`, and mark the result as `unsupported`.

Result statuses: `passed`, `passed_with_warnings`, `unsupported`, `failed`, `error`. Detailed attribution is stored in the `reason` field.

## Tech Stack

Python 3.11+ / asyncio / FastAPI / httpx / typer / tiktoken (optional)

## Design Docs

- `docs/coding-agent-roadmap.md`: Coding Agent roadmap (P0 completed / P1 in progress)
- `docs/benchmark-plan.md`: benchmark design for the local runner, SWE-bench Docker harness, and Claw-SWE-Bench comparison path
- `CLAW-SWE-BENCH.md`: Claw-SWE-Bench integration and running guide
- `docs/discussions/2026-06-15-p1-p3-scope-review.md`: P1 development discussion notes

> Chinese source: [README.md](./README.md)
