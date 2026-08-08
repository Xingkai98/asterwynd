# Q13: Benchmark 评测体系——怎么量化 agent 能力

## 讲稿

Benchmark 解决"agent 到底行不行，用什么数字说话"。Asterwynd 的评测体系分四层（`docs/benchmark-plan.md`）。

**任务层**。任务有统一 schema（`task_schema.py`）：任务描述、工作区准备、验证命令、hidden test patch、评测指标。任务分两类：本地 worktree 任务（内置）+ 外部 SWE-bench 风格任务。

**执行层**。`BenchmarkRunner` 跑完整流程：准备 worktree（`git worktree add`）→ 跑 agent → 保存 trace/runner log/result → 应用 hidden test patch → 跑验证命令 → 保存 test output → 汇总报告。支持 fake agent（无 LLM 冒烟）、真实 agent 对比。

**指标层**。`statistics.py` 做统计，`models.py` 定义 TaskResult / RunMetadata，`report.py` 生成 summary。分层指标（`resolve_layer`）：不同类别任务用不同评测标准。

**对比层**。`compare.py` 对比多次 run 的 baseline；`gate.py` 是 CI 回归门禁——benchmark 对比基线，劣化超阈值拦截。`swebench_*` 工具对接 SWE-bench：pull 数据集、convert 格式、analyze 结果，本地 Docker harness 跑真实 SWE-bench 实例。

面试重点：被问"怎么证明 agent 变强了"——答案是有可复现 benchmark：同一任务、同一 harness、量化指标（pass 率、耗时、trace），还能和 Aider/OpenCode 对比（Claw-SWE-Bench 统一 harness）。而且 **benchmark-gate 接 CI**，P95 延迟/成功率劣化超阈值自动拦截。

## 代码走读

### 入口与调用链

```
benchmarks/runner.py BenchmarkRunner.run_all (122 行)
  → run_task (187 行) → _create_worktree / _apply_test_patch / _run_test_command
  → models.TaskResult → statistics / report → summary
  gate.py：CI 回归门禁 → 对比 baseline
```

### 关键文件逐段

**`benchmarks/runner.py` `class BenchmarkRunner`**
- `run_all`（122 行）：跑所有任务，并发 `run_one`。
- `run_task`（187 行）：单个任务完整流程。
- `_create_worktree`（473 行）：用 `git worktree add` 建独立工作区（隔离 agent 改动）。
- `_clone_external_repo`（485 行）：SWE-bench 等外部 repo 克隆。
- `_apply_test_patch`（678 行）：应用 hidden test patch。
- `_run_test_command`（782 行）：跑验证命令。
- `_write_final_diff`（651 行）：agent diff capture 后保存 final diff。
- Docker preflight：`_get_docker_preflight_result`（90 行）探测 docker 可用性。

**`benchmarks/adapters.py`** — agent adapter：fake（无 LLM）/ shell / Asterwynd 等。

**`benchmarks/models.py`**
- `TaskResult`（59 行）：单任务结果（pass/fail + 指标）。
- `RunMetadata`（102 行）：run 级元数据。
- `render_summary`（122 行）：summary 渲染。

**`benchmarks/statistics.py`** — 统计（平均值/百分位等）。

**`benchmarks/compare.py`** — 多次 run 对比 baseline。

**`benchmarks/gate.py`** — CI 回归门禁：对比 baseline，劣化拦截。

**`benchmarks/task_schema.py`** — 任务 schema 定义。

**`benchmarks/swebench_*`** — SWE-bench 对接：pull（拉数据集）、convert（格式转换）、analyze（结果分析）。

**`docs/benchmark-plan.md`** — 评测方案：目标、行业参考（SWE-bench/Terminal-Bench/Aider）、任务结构、runner 设计、指标。

### 设计理由

- **可复现优先**：同一任务同一 harness，用 `git worktree add` 隔离工作区，结果可对比。
- **分层指标**：不同任务类型用不同评测标准（`resolve_layer`），不搞一刀切 pass/fail。
- **接 CI 回归门禁**：benchmark 不只离线评测，还接 CI 自动拦截劣化（#78 第二批）——"怎么保证不衰退"的量化答案。
- **对比真实 agent**：Claw-SWE-Bench 统一 harness 对比 Aider/OpenCode，面试能说"我们和业界工具在同一数据集上对比"。
