# Verify EnterWorktree / ExitWorktree tools are exposed and bounded

The project has two builtin tools `EnterWorktree` and `ExitWorktree`
(`agent/tools/builtin/worktree.py`) that let the agent create, enter, and
leave git worktree isolation workspaces at runtime.

## Task

Verify the tools are properly registered and their workspace-safety boundary
behaves as specified (no code changes required):

1. `EnterWorktree` and `ExitWorktree` are registered in the default and coding
   tool registries, and their schemas are available from `get_all_schemas()`.
2. The permission metadata is `dangerous=False` with a `WORKSPACE_WRITE`
   capability at `MEDIUM` risk (auto-approved in build mode, denied in
   read-only mode).
3. In an orchestration-layer worktree (one NOT created by the tool, i.e.
   outside `.asterwynd/worktrees/`), `EnterWorktree` is rejected with
   `already_in_worktree`, and `ExitWorktree` is rejected with
   `not_in_worktree` — the tool must not exit or delete worktrees it did not
   create.

The provided test verifies all of the above. The implementation already
exists; confirm the tests pass against the current checkout.
