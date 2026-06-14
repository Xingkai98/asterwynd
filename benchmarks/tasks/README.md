# MyAgent Local Benchmark Tasks

This task set is designed to validate the P0 coding-agent benchmark loop.

Recommended fake-runner artifact smoke:

```bash
uv run python cli.py benchmark benchmarks/tasks \
  --agent fake \
  --source-repo . \
  --runs-dir /tmp/myagent-task-pack-smoke \
  --fake-edit-file README.md \
  --fake-old-string '# MyAgent' \
  --fake-new-string '# MyAgent Coding Agent'
```

This runs the full task directory. The fake runner is only expected to solve the
README title task; the purpose is to verify that the benchmark harness writes
artifacts for passed and failed tasks.

Recommended real MyAgent command:

```bash
uv run python cli.py benchmark benchmarks/tasks \
  --agent myagent \
  --source-repo . \
  --runs-dir /tmp/myagent-task-pack-myagent \
  --max-iterations 30
```

Each task contains:

- `task.json`: task metadata, base commit, and validation command.
- `issue.md`: the only problem statement shown to the agent.
- `test.patch`: evaluator-only tests applied after the agent finishes.
- `gold.patch`: reference implementation for analysis only.

The benchmark grades by `test_command`, not by exact patch equality.
