# MyAgent Local Benchmark Tasks

23 coding-agent tasks extracted from git history across 6 categories and 3
difficulty levels (easy / medium / hard).

Fake-runner artifact smoke:

```bash
uv run python cli.py benchmark benchmarks/tasks \
  --agent fake \
  --source-repo . \
  --runs-dir /tmp/myagent-task-pack-smoke \
  --fake-edit-file README.md \
  --fake-old-string '# MyAgent' \
  --fake-new-string '# MyAgent Coding Agent'
```

Real MyAgent run:

```bash
uv run python cli.py benchmark benchmarks/tasks \
  --agent myagent \
  --source-repo . \
  --runs-dir /tmp/myagent-task-pack-myagent \
  --max-iterations 80
```

Each task contains:

- `task.json`: task metadata, base commit, and validation command.
- `issue.md`: the only problem statement shown to the agent.
- `test.patch`: evaluator-only tests applied after the agent finishes.
- `gold.patch`: reference implementation for analysis only.

The benchmark grades by `test_command`, not by exact patch equality.

Task statuses:

- `passed`: hidden validation passed and the agent completed normally.
- `passed_with_warnings`: hidden validation passed, but the agent reported a
  non-fatal issue such as `max_iterations`.
- `failed`: hidden validation ran and failed.
- `error`: setup, patch application, or harness execution failed.
