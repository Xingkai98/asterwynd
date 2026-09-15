# workflows 端到端验证任务（**不属于**主任务集）

本目录放的是「运行机制 / 端到端」验证任务，与主任务集 `benchmarks/tasks/` **分开**：

| | `benchmarks/tasks/` | `benchmarks/tasks-e2e/`（本目录） |
|---|---|---|
| 用途 | 能力评测任务集（A 轨 / B 轨 / Verified） | 单次机制验证任务 |
| 是否进 `manifest.json` 覆盖矩阵 | 是 | **否** |
| 是否被 CI 的 `benchmark-gate` 跑到 | 是（`tasks/gate-smoke`） | **否** |
| 是否计入面试叙事里的任务数 | 是 | **否** |

主任务集的入口命令是 `benchmarks/tasks`，CI 门禁跑的是 `benchmarks/tasks/gate-smoke`——
两者都不会扫到本目录，所以这里的任务**不会**被主 benchmark 意外纳入。本目录也没有
`manifest.json`，不参与 `validate_coverage`。

## 内容

- `workflow-fanout/`：change `benchmark-workflow-replay`（C5）的端到端验证任务——
  用真实 LLM 自由生成一张 fan-out 图 → `dynamic-record` 落盘 → `dynamic-replay`
  重放 → 断言两次的 `workflow_spec_hash` 相等且都无异常完成（grill Q6 乙）。

  跑法（真实 LLM 侧，需 `--config` 指向可用 provider）：

  ```bash
  uv run asterwynd benchmark benchmarks/tasks-e2e --agent asterwynd \
      --provider anthropic --model deepseek-v4-flash \
      --workflow-mode dynamic-record --e2e-round-trip --runs-dir /tmp/e2e-fanout
  ```

  单次真实 LLM 跑约 40s，不属常规回归——按需手工跑。

## 注意：`base_commit` 的可达性

`workflow-fanout/task.json` 的 `base_commit` 指向一个**当时存在于 C5 开发分支**的
提交，它不一定在 `origin/master` 上。`runner._create_worktree` 直接
`git worktree add --detach <base_commit>`，提交不可达时任务会以
`setup_error` 失败。

**PR 若以 squash / rebase 方式合入**，这个提交不会进入 `master`，本任务随之失效——
届时需要把 `base_commit` 改成一个 `origin/master` 上必然存在的提交（例如合入后的
`master` tip）。以 merge commit 方式合入时原始提交保持可达，无需改动。

发现任务报 `setup_error` 且日志里有 `worktree add` 失败时，先按这条核对。
