# Fix ExitWorktree to only exit tool-created worktrees

The project has two builtin tools `EnterWorktree` and `ExitWorktree`
(`agent/tools/builtin/worktree.py`) that let the agent create, enter, and
leave git worktree isolation workspaces at runtime.

The tools are registered and their schemas are exposed, but there is a
**workspace-safety boundary bug**: `ExitWorktree` currently exits (and with
`keep=false`, deletes) **any** linked worktree, including worktrees created
by the orchestration layer (e.g. benchmark runner task worktrees). An agent
running inside a benchmark task worktree could call `ExitWorktree` to delete
that task worktree, breaking the benchmark run.

## Task

Fix `ExitWorktree` so it only works on worktrees **created by the
`EnterWorktree` tool** — i.e. worktrees whose path is under the tool's own
directory convention `.asterwynd/worktrees/` inside the main repository.
When invoked inside any other worktree, it must return a structured error
(`error_type` `not_in_worktree`) and leave the workspace state unchanged.

## Requirements

- `ExitWorktree` must refuse to exit/delete any worktree not under
  `<main-repo>/.asterwynd/worktrees/`.
- Refusing must leave the workspace policy root and the worktree itself
  unchanged.
- `EnterWorktree` behavior must stay unchanged.
- Do not change the tool's permission metadata (must stay `dangerous=False`,
  `WORKSPACE_WRITE`, `MEDIUM`).

The provided test verifies the boundary (rejection in an orchestration
worktree, state unchanged) plus the registration/schema/permission metadata.
