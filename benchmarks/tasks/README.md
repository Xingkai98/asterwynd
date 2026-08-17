# Asterwynd Local Benchmark Tasks

27 local coding-agent tasks in a three-track task set (D3):

- **A 轨（22）**: 历史重建回归基线，base_commit 为特性引入前提交，在完整 git 历史中运行（反作弊泄漏已披露，见 `manifest.json` `anti_cheat_disclosure`）。
- **B 轨（5）**: 当前 HEAD 真实缺陷/增强（面试核心），含 `asterwynd-002-sandbox-executor`、`asterwynd-004-benchmark-cli`、`asterwynd-005-bash-workspace`、`asterwynd-021-lsp-diagnostics` 重写与 `asterwynd-b01-report-family-summary` 新增。
- **Verified（10，目标 50）**: `swebench-*` 外部精选子集，配比与 KNOWN_BAD 过滤见 `benchmarks/swebench_subset.py`。

任务按 5 场景（bug-fix/feature-dev/refactor/debug/integration）与 3 难度（easy/medium/hard）双标签组织；套件级能力覆盖矩阵见 `manifest.json` `coverage`。

Fake-runner artifact smoke:

```bash
uv run asterwynd benchmark benchmarks/tasks \
  --agent fake \
  --source-repo . \
  --runs-dir /tmp/asterwynd-task-pack-smoke \
  --fake-edit-file README.md \
  --fake-old-string '# Asterwynd' \
  --fake-new-string '# Asterwynd Coding Agent'
```

Real Asterwynd run:

```bash
uv run asterwynd benchmark benchmarks/tasks \
  --agent asterwynd \
  --source-repo . \
  --runs-dir /tmp/asterwynd-task-pack-asterwynd \
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
