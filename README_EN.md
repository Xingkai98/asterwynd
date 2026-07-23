<p align="center">
  <img src="./docs/assets/asterwynd-wordmark.svg?v=20260628-centered" alt="Asterwynd" width="760" />
</p>

<p align="center">
  <a href="./README.md">简体中文</a>
  ·
  <a href="./README_EN.md">English</a>
</p>

<p align="center">
  <strong>Navigate by stars. Prove with traces.</strong>
</p>

**Asterwynd** is a local coding agent system for turning repository tasks into traceable, test-backed software changes. It reads your codebase, finds the path from issue to fix, runs tools and validation, and leaves a trail of evidence--diffs, logs, tool traces, and benchmark results--so every change is provable, not just plausible.

Stars guide direction. Wind carries motion. Traces prove the journey.

## Features

| Module | Description |
|------|------|
| **AgentLoop** | Core loop of about 100 lines. Messages are the only state, and capabilities are delegated to plugins. |
| **ToolRegistry** | Dynamic tool registration with the `@tool_parameters` decorator. Includes file, command, code intelligence, and web research tools. |
| **Code Intelligence** | Tree-sitter multi-language symbol extraction, Repo Map, Python AST symbol extraction, and LSP semantic tools such as definition, references, hover, and diagnostics. |
| **WorkspacePolicy** | Workspace safety boundary that rejects path traversal, sensitive file writes, and dangerous commands. |
| **SandboxExecutor** | Subprocess sandbox with structured output: exit_code, stdout, stderr, duration, and timed_out. |
| **HookManager** | 6 lifecycle extension points with built-in logging, retry, tracing, and token budget hooks. |
| **MemoryManager** | 90%-threshold AutoCompact with pluggable Summarizer (LLM four-section summary / truncation fallback). |
| **ContextBuilder** | Context injection pipeline that orchestrates ASTER.md, memory index, skills, plans, todos, and other ContextSources. |
| **Browser** | Controlled read-only browser: navigation, screenshots, content extraction, and tab management with safety policy. |
| **SkillRuntime** | Directory-style Markdown skills with index injection, always/on-demand activation, and explicit `/skill args` invocation. |
| **MCP Adapter** | Connects stdio / Streamable HTTP MCP servers, registers MCP tools, and injects prompt/resource context through `/mcp-prompt` and `/mcp-resource`. |
| **SubAgentManager** | Sub-session runtime with independent transcripts, multiple sub-sessions, repeated runs per sub-session, and explicit inspect. |
| **TraceRecorder** | Full trace recording for iterations, tool calls, edits, and tests. |
| **Benchmark** | 34 local coding-agent tasks, SWE-bench Docker harness tasks, and a Claw-SWE-Bench multi-agent comparison entry point. |

## Quick Start

```bash
# Install dependencies with uv
uv sync --extra dev              # runtime + development/test dependencies

# Configure API key and model
cp .env.example .env
# Edit .env and set OPENAI_API_KEY or ANTHROPIC_API_KEY
# Optional: set OPENAI_BASE_URL for another OpenAI-compatible API, such as DeepSeek
# Optional: set ASTERWYND_PROVIDER (openai / anthropic) and ASTERWYND_MODEL as defaults

# Run CLI (OpenAI by default, using ASTERWYND_MODEL from .env)
uv run asterwynd run "Hello"

# Or override model/provider
uv run asterwynd run --model gpt-4o-mini "Hello"
uv run asterwynd run --provider anthropic --model claude-sonnet-4-20250514 "Hello"

# Interactive mode
uv run asterwynd

# Start Web UI (using .env config)
uv run asterwynd web --port 8000

# Web UI with verbose logging
ASTERWYND_LOG_LEVEL=DEBUG uv run asterwynd web --port 8000 --model deepseek-v4-pro

# Run tests
uv run pytest -q

# Run local coding-agent benchmark (fake runner smoke)
uv run asterwynd benchmark benchmarks/tasks \
  --agent fake \
  --source-repo . \
  --runs-dir /tmp/asterwynd-benchmark-smoke \
  --fake-edit-file README.md \
  --fake-old-string '# Asterwynd' \
  --fake-new-string '# Asterwynd Coding Agent'

# Run the Claw-SWE-Bench unified harness (requires Docker images and env vars first)
cd claw-swe-bench
uv run python run_infer.py \
  --claw asterwynd \
  --dataset verified \
  --instance_file config/verified_mini_50.txt \
  --run_id asterwynd-lite \
  --model deepseek-v4-pro
```

`uv run` is not required by the application itself. It is the recommended environment isolation method because it uses the project virtual environment managed by `uv`, making dependency resolution more reproducible. If your current shell Python environment already has the dependencies installed, equivalent commands such as `asterwynd run "Hello"` or `pytest -q` also work.

## Built-In Tools

| Tool | Permission Level | Description |
|------|---------|------|
| `Read` | read_only | Read files with line limits. |
| `Write` | read_write | Create new files and refuse to overwrite existing files. |
| `Edit` | read_write | Exact text replacement. Requires a unique `old_string` match and supports `replace_all`. |
| `Bash` | command_execute / high | Execute shell commands in the sandbox and return structured JSON: exit_code, stdout, stderr, duration, timed_out. |
| `Grep` | read_only | Regex search over files or directories. |
| `InspectGitDiff` | read_only | Inspect the current workspace git diff. |
| `ListFiles` | read_only | List directory contents and automatically ignore `.git`, `node_modules`, and similar noise. |
| `Find` | read_only | Recursively search files by glob pattern. |
| `RepoMap` | read_only | Generate repository structure and top-level symbol summaries for supported languages. |
| `SymbolSearch` | read_only | Search supported symbols by name within the repository. |
| `WebSearch` | read_only | DuckDuckGo HTML search with stable text results that include provider metadata. |
| `WebFetch` | read_only | Fetch webpage text and return status, type, and truncation diagnostics. |
| `BrowserNavigate` | read_only | Navigate browser to a given URL. |
| `BrowserScreenshot` | read_only | Capture the current page viewport as a screenshot. |
| `BrowserGetContent` | read_only | Extract interactive elements and text content from the page. |
| `BrowserScroll` | read_only | Scroll the page by a given number of pixels. |
| `BrowserTabs` | read_only | Manage browser tabs: new, switch, close. |

The Bash tool has built-in command safety policy. It first passes mode permission profile checks; in the default `build` mode, high-risk command execution requires approval, and unattended entry points such as single-prompt CLI and benchmark fail closed. Before actual execution it still checks regex deny patterns covering cases such as `rm -rf /`, fork bombs, and `curl | sh`, then matches allowed safe command prefixes such as `git status`, `pytest`, `uv`, and `npm`. Project-level command deny rules, permission profiles, and ListFiles / Find ignore rules are extended through `asterwynd.yaml`; see `asterwynd.example.yaml`.

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
├── config.py                # Config loader (asterwynd.yaml)
├── session.py               # SessionStore session persistence
├── approval.py              # ApprovalHandler tool approval
├── background.py            # BackgroundTaskManager background tasks
├── run_config.py            # AgentRuntimeState + mode transition
├── run_identity.py          # RunId / SessionId identifiers
├── tool_permissions.py      # ToolPermission + ModePolicy
├── tool_result_display.py   # ToolResultDisplayConfig
├── branding.py              # Asterwynd branding
├── assets/                  # Branding assets
├── commands/
│   ├── registry.py          # SlashCommandRegistry
│   └── init.py              # /init command (ASTER.md generation)
├── context/
│   ├── protocol.py          # BuildContext + ContextSource Protocol
│   ├── builder.py           # ContextBuilder pipeline
│   ├── sources.py           # 8 built-in ContextSources
│   └── summarizer.py        # Summarizer Protocol + LLMSummarizer + TruncationSummarizer
├── tools/
│   ├── base.py              # Tool ABC + @tool_parameters decorator
│   ├── registry.py          # ToolRegistry
│   ├── sandbox.py           # SandboxExecutor + SandboxResult
│   └── builtin/             # Built-in tools (file, command, browser, search, etc.)
├── hooks/
│   ├── manager.py           # HookManager + Hook Protocol
│   └── builtin/             # 4 built-in hooks
├── memory/
│   └── manager.py           # MemoryManager + AutoCompact
├── planning/
│   └── manager.py           # PlanningManager structured planning state
├── mcp/
│   ├── manager.py           # MCP server connection, discovery, and calls
│   └── tools.py             # MCP-backed Tool wrapper
├── skills/
│   ├── loader.py            # SkillLoader + Skill dataclass
│   └── runtime.py           # SkillRuntime + current-run skill activation
├── subagent/
│   └── manager.py           # SubAgentManager sub-session runtime
├── browser/
│   ├── service.py           # BrowserService process management
│   ├── session.py           # BrowserSession tab/navigation management
│   └── policy.py            # BrowserPolicy safety policy
├── code_intelligence/
│   └── ...                  # RepoMap / SymbolSearch implementations
├── lsp/
│   └── ...                  # LSP server management & semantic tools
├── workflow/
│   └── ...                  # Handoff state machine & lifecycle tracking
└── tui/
    └── ...                  # Terminal UI runtime view

benchmarks/                  # Local benchmark runner
├── tasks/                   # 34 coding tasks (asterwynd-* + swebench-*)
├── runner.py                # BenchmarkRunner + SWE-bench style isolation
├── agent_runner.py          # AgentRunner adapters: fake/shell/asterwynd
├── models.py                # Failure taxonomy + metric models
├── prompt.py                # Coding-agent prompt builder
└── task_schema.py           # Task schema loading

claw-swe-bench/              # Claw-SWE-Bench unified harness copy and adapters
└── claw_swebench/claws/
    ├── asterwynd.py           # Asterwynd adapter
    ├── aider.py             # Aider adapter
    └── opencode_adapter.py  # OpenCode adapter (limited by endpoint support)

skills/                      # Skill files
├── code-review/
│   └── SKILL.md
└── research/
    └── SKILL.md
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

`MemoryManager.compact_if_needed()` checks the token budget after each tool-call round. At 90% of budget, it triggers compaction:

- Keep all `role=system` messages.
- Keep the most recent N messages (with tool-call chain integrity protection).
- Summarize the middle section via pluggable `Summarizer` (LLM four-section summary, or truncation fallback when no LLM).
- Summary is injected as a `role=user` message (semantically "prior conversation context").

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

Create a directory-style skill at `skills/<name>/SKILL.md`:

```markdown
---
name: my-skill
description: Skill description
tools: [Read, Bash]
always: false
user_invocable: true
argument_hint: <request>
triggers:
  - trigger phrase
---

# Skill Title

Prompt instructions go here...
```

Each run injects a concise skill index into model-visible context. Full skill prompts are injected only for `always: true`, local matches, explicit `/my-skill ...` calls, or `ActivateSkill` tool activation. Interactive mode provides `/skills` to inspect loaded skills and `/skills reload` to reload configured skill roots.

## Web UI

Start the Web UI:

```bash
# Basic startup (uses ASTERWYND_PROVIDER and ASTERWYND_MODEL from .env)
uv run asterwynd web --port 8000

# Override model
uv run asterwynd web --port 8000 --model deepseek-v4-pro

# Override provider
uv run asterwynd web --port 8000 --provider anthropic --model claude-sonnet-4-20250514

# Debug mode (Chat + Debug views)
ASTERWYND_DEBUG=enabled uv run asterwynd web --host 127.0.0.1 --port 8000

# Verbose logs (record LLM input/output to files)
ASTERWYND_LOG_LEVEL=DEBUG uv run asterwynd web --port 8000
```

- **Chat view**: Normal conversation, assistant Markdown rendering, tool-call visualization, long tool-result folding by display policy, current session id / run id / session mode, switching between `build` / `read_only` / `plan`, Plan Document plus planning state display, and approval cards for tools that require approval.
- **Debug view**: Enabled by `ASTERWYND_DEBUG=enabled`; shows each round of:
  - Full message list sent to the LLM, including system prompt, history, and tool results.
  - LLM response, including content, stop_reason, and tool_calls; tool arguments are displayed with approval redaction rules.
  - Tool-call details, including name, redacted arguments, and result.
  - Memory compaction events sent by AgentLoop through the Web session event stream.

CLI interactive mode supports switching the current session mode with `/mode build`, `/mode read_only`, and `/mode plan`. CLI single-run mode still uses `--mode` for the initial mode.

### Logs

Each startup creates an independent log file under `logs/`, such as `asterwynd-20260526-123456.log`:

| Environment Variable | Default | Description |
|---------|--------|------|
| `ASTERWYND_PROVIDER` | `openai` | LLM provider: `openai` or `anthropic`. |
| `ASTERWYND_MODEL` | provider default | Model name. |
| `ASTERWYND_LOG_LEVEL` | `INFO` | At `DEBUG`, logs LLM request payloads and raw response JSON. |
| `ASTERWYND_DEBUG` | `disabled` | When `enabled`, turns on the Debug Web UI. |

Configuration precedence: explicit CLI arguments > process environment variables > `.env` loaded values > `asterwynd.yaml` > code defaults. API key, base URL, provider, model, debug, and log level continue to use `.env` or environment variables. Agent mode, permission profiles, mode deny overrides, tool policy, tool-result display thresholds, and benchmark defaults use `asterwynd.yaml`.

- Logs are written to both terminal and file.
- HTTP 4xx/5xx errors always log request payload and response body.
- Each log file is capped at 5 MB, keeping the latest 5 rotated files.

Browser tests:

```bash
playwright install chromium
ASTERWYND_DEBUG=enabled uv run pytest tests/web_tests/test_browser.py --run-real-api -v
```

## Benchmark

Asterwynd currently has two benchmark paths:

- `benchmarks/`: the built-in project runner, using 34 local tasks and a small number of `swebench-*` external tasks to validate the Asterwynd coding-agent loop.
- `claw-swe-bench/`: the Claw-SWE-Bench unified harness, comparing Asterwynd, Aider, OpenCode, and other external coding agents on the same SWE-bench Verified instances.

### Quick Validation (Fake Agent, Deterministic)

```bash
uv run asterwynd benchmark benchmarks/tasks \
  --agent fake \
  --source-repo . \
  --runs-dir /tmp/asterwynd-benchmark-smoke \
  --fake-edit-file README.md \
  --fake-old-string '# Asterwynd' \
  --fake-new-string '# Asterwynd Coding Agent'
```

### Real Agent Evaluation

```bash
uv run asterwynd benchmark benchmarks/tasks \
  --agent asterwynd \
  --source-repo . \
  --runs-dir /tmp/asterwynd-benchmark \
  --max-iterations 80
```

### Claw-SWE-Bench Comparison Evaluation

See [CLAW-SWE-BENCH.md](./CLAW-SWE-BENCH.md) for full environment setup. Minimal command shape:

```bash
cd claw-swe-bench
uv run python run_infer.py \
  --claw asterwynd \
  --dataset verified \
  --instance_file config/verified_mini_50.txt \
  --run_id asterwynd-lite \
  --model deepseek-v4-pro

uv run python run_eval.py --run_id asterwynd-lite --dataset verified
```

### Task Set

34 tasks are extracted from the project git history and cover several categories:

| Category | Example |
|------|------|
| Tool implementation | ToolRegistry, SandboxExecutor, Read/Write tools, Bash workspace, Browser tools |
| Safety policy | Reject `.env` writes, path traversal protection, Bash command policy, Browser safety |
| Agent core | AgentLoop, MemoryManager, SkillRuntime, SubAgent system, context injection pipeline |
| Observability | HookManager, logging/tracing hooks, retry/budget hooks |
| Benchmark infrastructure | Failure classification, runner timeout, resource leak fixes, Docker preflight |
| Prompting & input | Coding system prompt, validation command injection, multimodal input |

### Evaluation Flow

Local `asterwynd-*` tasks:

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

- `docs/coding-agent-roadmap.md`: Coding Agent roadmap
- `docs/benchmark-plan.md`: benchmark design for the local runner, SWE-bench Docker harness, and Claw-SWE-Bench comparison path
- `CLAW-SWE-BENCH.md`: Claw-SWE-Bench integration and running guide

> Chinese source: [README.md](./README.md)
