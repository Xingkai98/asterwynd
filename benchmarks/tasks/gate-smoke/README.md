# gate-smoke 任务集

供 `asterwynd benchmark-gate`（回归门禁）在 CI 使用的**近零 IO** 确定性任务集。

## 设计约束（design.md Decision 15/17）

- **近零 IO**：`test_command` 是 `python -c "import sys; sys.exit(0)"`，不依赖本 PR 或任何新代码；fake agent 不配 `edit_file` 时不做任何改动，worktree 停在 `base_commit` 上即通过。
- **base_commit**：用仓库内已存在的历史 SHA（`7c6fc3e`），CI 需 `fetch-depth: 0` 全量克隆使其可达（grill Decision 18）。
- **裸跑即绿**：任务在 base_commit 上无改动即通过，避免"依赖新代码"导致门禁永远红。

## CI 用 `--skip-p95`：p95 墙钟不可靠

gate-smoke 的 `duration_seconds` 是纯墙钟（含 `git worktree add` 等冷启动开销）。实测同机三次运行 p95 = 0.5s / 7.8s / 20.5s，方差 40×，全部由环境因素主导。因此：

- CI job 用 `benchmark-gate ... --require-baseline --skip-p95`，**以 `success_rate` 为主要确定性信号**：harness/runner/任务集破坏时任务 error → success_rate 跌破 1.0 → 门禁拦截。
- `benchmarks/baseline.json` 的 `p95_latency_s=10.0` 是保守占位（不被 CI 使用），保证人工跑 `--update-baseline` 时 schema 完整。
- 严格的 P95 相对劣化语义由 `tests/benchmark/test_gate.py` 在纯逻辑层验证，适用于真实 benchmark 工作流（默认启用 p95 检查）。
