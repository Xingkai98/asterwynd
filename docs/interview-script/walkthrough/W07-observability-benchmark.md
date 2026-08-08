# W07 · 可观测体系 + Benchmark 评测闭环

**对应简历 bullet 7**：*"建立全链路可观测体系与 Benchmark 评测闭环：TraceRecorder 全链轨迹记录 + CostLedger 三层成本归因 + ErrorClassifier 错误类型自动打标；36+ 个 coding 任务（26 本地 + 10 SWE-bench 外部）在 git worktree 隔离执行，bootstrap 95% CI 统计，支持 SWE-bench 跨 Agent 对比和 CI 回归门禁"*

## 代码入口

```
可观测：
agent/
├── trace_recorder.py   ← TraceRecorder（全链轨迹）
├── cost_tracker.py     ← CostLedger（三层成本归因）
└── observability.py    ← ErrorClassifier（错误分类）+ resolve_phase

Benchmark：
benchmarks/
├── runner.py         ← BenchmarkRunner（worktree 隔离 + Semaphore 并发 + 评测）
├── agent_runner.py   ← 多 Agent Runner（Asterwynd/ClaudeCode/Fake/ShellCommand）
├── task_schema.py    ← task.json schema 校验
├── statistics.py     ← bootstrap 95% CI + pass@k + 分层通过率
├── gate.py           ← CI 回归门禁（对比 baseline）
├── compare.py        ← 跨 Agent 对比（comparison.html/md）
├── swebench_*        ← SWE-bench 拉取/转换/分析
└── baseline.json     ← gate-smoke 基线
```

## 核心逻辑

### 可观测三件套

#### TraceRecorder（trace_recorder.py）

- **全链 step 流**：run_started → llm_iteration → tool_call → tool_result → approval_request/response → sandbox(event) → memory_compaction → edit → completion，每 step 带 (step, type, data, timestamp)。
- **step 类型开放扩展**（trace_recorder.py:145-152）：新增 sandbox 事件（denied/kill/oom/degraded）"additive 且向后兼容，不 bump schema_version"。
- **LLM 错误结构化打标**（record_llm_error，trace_recorder.py:220）：失败源头先 record_llm_error 再 re-raise——异常控制流不变，trace 拿结构化信号。
- **审批上下文入 trace**（record_tool_result 的 approval_required/granted）：供 tool-governance 质量评分消费。
- **sink 适配器**（TraceRecorderSandboxSink）：sandbox 事件经 contextvar sink 写入 run 的 trace，嵌套 subagent 不串扰。

#### CostLedger 三层成本归因（cost_tracker.py）

- 每个 record 用 compute_cost（模型前缀匹配价格表）算调用成本，**按 session / phase / tool 三维聚合**（bill()，cost_tracker.py:81-100）。
- 价格表 MODEL_PRICES（gpt-4o/gpt-5/claude-sonnet-4/claude-opus-4/deepseek-chat 等），前缀匹配**按长度降序**防 gpt-4o 误匹配 gpt-4o-mini（cost_tracker.py:20-22）。
- **与 trace 解耦**：ledger 是财务记录，trace 是过程记录。flush 用 _flushed_count 游标防共享实例重复追加。

#### ErrorClassifier（observability.py）

- **4 类结构化错误 + UNKNOWN 兜底**（不是 5）：PERMISSION_DENIED / NETWORK_TIMEOUT / MODEL_ERROR / PARAMETER_ERROR / UNKNOWN。
- **分类优先级**（classify）：结构化 error_type → finish_reason（max_tokens/length/content_filter → MODEL_ERROR）→ 文本 fallback。
- **error_type → category 映射**（observability.py:45-63）：审批拒绝系（approval_required/denied/unavailable）全部映射 PERMISSION_DENIED。
- **每类告警策略**（_ALERT_LEVEL）：PERMISSION_DENIED→immediate，NETWORK_TIMEOUT/MODEL_ERROR→warn，PARAMETER_ERROR/UNKNOWN→record。
- **语义错误不自动分类**（observability.py:6-7）：幻觉类需 LLM judge，诚实边界。

### Benchmark 评测闭环

#### 评测链路（runner.py）

```
run_all(tasks) → asyncio.Semaphore(parallel) 限流
  → 本地任务：_create_worktree（git worktree add --detach <base_commit>）
  → 外部任务：_clone_external_repo（复用 bare clone cache + checkout base_commit）
  → _run_agent → AgentLoop 在 worktree 中自主执行
  → git diff → final.diff
  → 应用 test patch（只应用测试补丁，不应用 gold patch——agent 直接修 bug）
  → 跑 test_command → TaskResult(status, exit_code)
  → 产物：result.json / trace.json / final.diff / test_output.txt / runner.log
```

**评测完整性细节**：
- **隐藏 task 文件**（_hide_agent_invisible_task_files，runner.py:632）：评测前把 benchmarks/tasks 藏起来，测完恢复——防 agent 直接读 task.json 作弊。
- **gold patch 只存不应用**：agent 在 base_commit（有 bug 版本）上修，测试补丁验证。
- **外部仓库 git clone 带重试**（_git_clone_with_retry）。

#### 统计（statistics.py）

- **bootstrap 95% CI**（bootstrap_ci，statistics.py:38-62）：percentile 法，2000 次重采样，**固定 seed=0 可复现**，纯 Python 无 numpy/scipy。
- **Pass@k**（pass_at_k）：Chen et al. 2021 组合估计器 1 - C(n-c,k)/C(n,k)。
- **分层通过率**（layer_pass_rate）。

#### CI 回归门禁（gate.py）

- **成功率高线**：baseline 成功率 drop > 5pp → FAIL。
- **p95 延迟**：max(基线×1.05, 基线 + 1s)（gate.py:153）——**绝对下限 1s 防亚秒基线相对抖动误报**。
- **p95 只算通过任务**（gate.py:59）：失败/崩溃任务 duration_seconds=0.0 会拉低延迟、掩盖回归。
- **epsilon 守卫**（gate.py:148-149）：1.0-0.95 = 0.050000000000000044 不能算"超过 5pp"，边界严格 >。
- **check_p95=False**：gate-smoke（确定性近零 IO）p95 不可靠（观察方差 0.5s-20.5s），跳过 p95 只查成功率。

#### 跨 Agent 对比（compare.py + swebench_*）

- SWE-bench 任务跨 Asterwynd / Claude Code / Shell 多 Agent 对比，产出 comparison.html/md。
- swebench_pull/convert/analyze：SWE-bench 数据拉取、转换、分析。

## 简历核实

| 简历 | 核实 | 结论 |
|------|------|------|
| "TraceRecorder 全链轨迹记录" | trace_recorder.py 吻合 | ✅ |
| "CostLedger 三层成本归因" | by_session/by_phase/by_tool | ✅ |
| "ErrorClassifier 错误类型自动打标" | 4 类 + unknown，无数字 | ✅ |
| "36+ 任务（26 本地 + 10 SWE-bench）" | 26 + 10 = 36 | ✅ |
| "git worktree 隔离执行" | _create_worktree | ✅ |
| "bootstrap 95% CI 统计" | bootstrap_ci | ✅ |
| "SWE-bench 跨 Agent 对比" | compare.py + 多 runner | ✅ |
| "CI 回归门禁" | gate.py | ✅ |

## 面试加分点

1. **评测防作弊**（隐藏 task 文件）——"agent 不能直接读 task.json"，讲评测最出彩。
2. **gate 的 epsilon + p95 绝对下限**——真实工程坑。
3. **bootstrap 固定 seed 可复现**——统计严谨性。
4. **ErrorClassifier 诚实边界**——"幻觉不自动分类，需 LLM judge"。
