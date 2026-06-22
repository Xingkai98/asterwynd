# MyAgent

A lightweight general-purpose AI agent framework in Python. Designed for clean architecture and interview preparation — every plugin subsystem is independently explainable and benchmarkable.

## Features

| Module | Description |
|--------|-------------|
| **AgentLoop** | Core loop ~100 lines, messages as sole state, all concerns delegated to plugins |
| **ToolRegistry** | Dynamic tool registration, `@tool_parameters` decorator, 10 built-in tools |
| **WorkspacePolicy** | Workspace safety boundary: path traversal, sensitive file writes, dangerous commands |
| **SandboxExecutor** | subprocess sandbox with structured output (exit_code/stdout/stderr/duration/timed_out) |
| **HookManager** | 6 lifecycle extension points, built-in logging/retry/tracing/budget hooks |
| **MemoryManager** | AutoCompact token compression, LLM-generated summaries when over budget |
| **SkillLoader** | Markdown skill files (YAML frontmatter + prompt), on-demand/always loading |
| **SubAgentManager** | asyncio background task delegation, ParentChannel mid-turn injection |
| **TraceRecorder** | Full trace recording: iterations, tool calls, edits, tests — always complete |
| **Local Benchmark** | 23 coding-agent tasks, SWE-bench style isolation, multi-agent adapters |

## Quick Start

```bash
uv sync --extra dev
cp .env.example .env   # fill in API key
uv run python cli.py main "Hello"
uv run python cli.py main --interactive
uv run python cli.py web --port 8000
```

## Built-in Tools

| Tool | Permission | Description |
|------|-----------|-------------|
| `Read` | read_only | Read file with line limit |
| `Write` | read_write | Create new files (refuses overwrite) |
| `Edit` | read_write | Exact text replacement, unique match required, replace_all support |
| `Bash` | dangerous | Sandboxed shell commands, returns structured JSON |
| `Grep` | read_only | Regex search in files/directories |
| `InspectGitDiff` | read_only | Show current workspace git diff |
| `ListFiles` | read_only | List directory (auto-ignores .git/node_modules) |
| `Find` | read_only | Recursive glob file search |
| `WebSearch` | read_only | DuckDuckGo HTML search |
| `WebFetch` | read_only | Fetch web page content |

Bash command safety: prefix allowlist (git status, pytest, uv, npm, ...) + regex denylist. Project-level command deny rules and ListFiles / Find ignore rules are configured in `myagent.yaml`; see `myagent.example.yaml`.

## Project Structure

```
agent/
├── loop.py              # AgentLoop core (~100 lines)
├── workspace_policy.py  # WorkspacePolicy safety boundary
├── trace_recorder.py    # TraceRecorder full trace recording
├── tools/               # 10 built-in tools
├── hooks/               # HookManager + 4 built-in hooks
├── memory/              # MemoryManager + AutoCompact
├── skills/              # SkillLoader
└── subagent/            # SubAgentManager + ParentChannel

benchmarks/              # Local benchmark harness
├── tasks/               # 23 tasks (6 categories, 3 difficulties)
├── runner.py            # SWE-bench style evaluation
└── agent_runner.py      # fake/shell/myagent adapters
```

## Local Benchmark

23 tasks extracted from git history across 6 categories (tools, security, agent core, observability, benchmark infra, prompt). SWE-bench style evaluation in isolated git worktrees with hidden test patches.

```bash
# Fake agent smoke test
uv run python cli.py benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/smoke

# Real agent
uv run python cli.py benchmark benchmarks/tasks --agent myagent --source-repo . --runs-dir /tmp/bench --max-iterations 80
```

Result statuses: `passed`, `passed_with_warnings`, `failed`, `error`.

## Tech Stack

Python 3.11+ / asyncio / FastAPI / httpx / typer / tiktoken (optional)

## Design Docs

- `docs/coding-agent-roadmap.md` — Coding agent roadmap (P0 done / P1 in progress)
- `docs/benchmark-plan.md` — Benchmark design (SWE-bench reference, task structure)
- `docs/discussions/2026-06-15-p1-p3-scope-review.md` — P1 scope review decisions
- `docs/superpowers/specs/` — Architecture design and reference project analysis

> Chinese version: [README.md](./README.md)
