# Bullet 7: 全链路可观测体系与 Benchmark 评测闭环 — 代码走读

> 简历原文：建立全链路可观测体系与 Benchmark 评测闭环：TraceRecorder 全链轨迹记录 + CostLedger 三层成本归因 + ErrorClassifier 错误类型自动打标；36+ 个 coding 任务（26 本地 + 10 SWE-bench 外部）在 git worktree 隔离执行，bootstrap 95% CI 统计，支持 SWE-bench 跨 Agent 对比和 CI 回归门禁

---

## 1. TraceRecorder — 全链轨迹记录

**文件**：`agent/trace_recorder.py`

### 1.1 数据结构

`TraceRecorder`（line 23）是所有运行时事件的结构化记录器。每个事件被编码为一个 `TraceStep`（line 16）：

```python
@dataclass
class TraceStep:
    step: int                       # 自增序号
    type: str                       # 事件类型（18 种，见下文）
    data: dict[str, Any]            # 事件载荷
    timestamp: float                # 挂钟时间戳 (line 20)
```

时间戳打在 `TraceStep` 层，而非 data 载荷内部（line 52-61 注释说明），保持事件数据清洁且向后兼容。`schema_version` 固定为 `"1.1"`（line 243）。

### 1.2 run identity 体系

构造函数参数（line 24-38）：

| 参数 | 类型 | 说明 |
|------|------|------|
| `task_id` | str | 任务标识（benchmark 场景下由 runner 注入） |
| `full_trace` | bool | 全量追踪开关，**默认 `False`**（line 27，保留为序列化兼容用途） |
| `mode` | str | 运行模式，默认 `"build"`（line 28） |
| `session_id` | str \| None | 会话标识，**默认 `None`**（line 29，由外部注入） |
| `run_id` | str \| None | 运行标识，**默认 `None`**（line 30，由外部注入） |

`set_run_identity()`（line 40-48）允许运行时补充注入 `session_id` / `run_id`。

### 1.3 事件类型清单（共 18 种）

所有记录事件通过 `record(step_type, **data)` 统一入口（line 51-61），具体事件类型包装为命名方法：

| 事件类型 | 方法 | 行号 | 说明 |
|----------|------|------|------|
| `run_started` | `record_run_started()` | 63 | 运行开始，携带 mode / session_id / run_id |
| `mode_changed` | `record_mode_changed()` | 73 | 模式切换（如 build → plan） |
| `llm_iteration` | `record_iteration()` | 79 | 每次 LLM 调用：iteration 序号、preview、tool_calls、输入/输出 token、model、finish_reason |
| `tool_call` | `record_tool_call()` | 100 | 工具调用发起（tool_name + arguments） |
| `tool_result` | `record_tool_result()` | 103 | 工具调用结果（tool_name, status, duration_ms, observation, error_type） |
| `sandbox` | `record_sandbox_event()` | 145 | 沙箱事件（denied/kill/oom/degraded） |
| `approval_request` | `record_approval_request()` | 155 | 权限审批请求 |
| `approval_response` | `record_approval_response()` | 158 | 权限审批响应 |
| `edit` | `record_edit()` | 161 | 文件编辑操作（path, status, summary） |
| `memory_compaction` | `record_compaction()` | 164 | 上下文压缩统计（before/after messages + tokens + tiers） |
| `parallel_execution_start` | `record_parallel_execution()` | 182 | 并行工具执行组 |
| `diff` | `record_diff()` | 185 | diff 快照（path + summary） |
| `test` | `record_test()` | 188 | 测试执行记录（command, exit_code, duration_ms, output） |
| `planning_state_updated` | `record_planning_state()` | 203 | 计划状态快照更新 |
| `plan_document` | `record_plan_document()` | 206 | 计划文档事件（事件类型 + document dict） |
| `llm_error` | `record_llm_error()` | 220 | 结构化 LLM 调用失败（error_type + message） |
| `completion` | `record_completion()` | 228 | 运行完成（status, content, duration_seconds） |
| `benchmark_preflight` | `record()` 内联调用 | runner.py:233 | Benchmark 预检（docker 环境探测） |

### 1.4 序列化与持久化

- `to_dict()`（line 236）：产出完整 trace dict，含 task_id、mode、duration_seconds、steps 数组
- `to_json()`（line 251）：JSON 字符串，`ensure_ascii=False`
- `write_to_file(path)`（line 254）：`errors="replace"` 写出文件

### 1.5 SandboxSink 适配器

`TraceRecorderSandboxSink`（line 258-269）将沙箱事件桥接到 TraceRecorder 的 `record_sandbox_event`，非阻塞追加。

### 1.6 集成点

在 `benchmarks/runner.py` 中，每个 task 启动时创建独立的 `TraceRecorder` 实例（line 206-210）：

```python
trace = TraceRecorder(
    task_id=loaded.task.id,
    mode=self.run_config.mode.value,
    run_id=agent_run_id,
)
```

runner 通过 `trace.record_diff()`（line 276-279）、`trace.record_test()`（line 401-406）、`trace.record_completion()`（line 366, 446, 453）打点，最终 `trace.write_to_file()` 写入 `trace.json`（line 468），存放在每个 task 的输出目录 `tasks/<task_id>/trace.json`（line 198）。

---

## 2. CostLedger — 三层成本归因

**文件**：`agent/cost_tracker.py`

### 2.1 模型定价表

`MODEL_PRICES`（line 5-14）包含 8 个模型的价格（USD / 1M tokens，input 在前，output 在后）：

| 模型 | Input ($/1M) | Output ($/1M) |
|------|-------------|---------------|
| gpt-4o | 2.50 | 10.00 |
| gpt-4o-mini | 0.15 | 0.60 |
| gpt-5 | 3.75 | 15.00 |
| claude-sonnet-4 | 3.00 | 15.00 |
| claude-opus-4 | 15.00 | 75.00 |
| claude-haiku-3.5 | 0.80 | 4.00 |
| deepseek-chat | 0.27 | 1.10 |
| deepseek-reasoner | 0.55 | 2.19 |

**注意**：定价是写死在代码中的常量表。如需支持新模型或价格变动，需修改源码。这不是运行时可配置的。

### 2.2 按前缀匹配的成本计算

`compute_cost(model, input_tokens, output_tokens)`（line 18-25）：按 `MODEL_PRICES` 的 key 长度降序排序后做 `startswith` 前缀匹配，避免短前缀误命中（如 `gpt-4o` 匹配 `gpt-4o-mini` 之前）。

### 2.3 CostLedger 三层归因（"三层"的出处）

`CostLedger` 类（line 36-139）是成本的财务记账，与 trace（过程记录）解耦。

- **`record()`**（line 54-76）：记录单次 LLM 调用的成本，入参携带三个归因维度：
  - `session_id`：按会话归因
  - `phase`：按运行阶段归因（building / review / planning / bypass，由 `observability.py:PHASE_BY_MODE` 映射）
  - `tool_name`：按工具归因（可为 None）
- **`bill()`**（line 81-100）：返回三个维度的聚合结果，这就是简历中"**三层成本归因**"的来源：

```python
return {
    "by_session": by_session,   # 第一层：按 session
    "by_phase": by_phase,       # 第二层：按 phase
    "by_tool": by_tool,         # 第三层：按 tool
}
```

每层的每个 bucket 包含 `tokens`（总 token 数）和 `cost`（累计费用）两个字段。

### 2.4 持久化

- **`flush(path)`**（line 102-119）：将新增条目追加为 JSONL 文件，使用 `_flushed_count` 游标防止重复写入。同一个 Ledger 实例可被父 agent 和子 agent 共享，各自在 run end 时 flush。
- **`load(path)`**（line 121-139）：从 JSONL 恢复条目。加载后 `_flushed_count` 已推进，后续 flush 只写新条目。

**注意**：`CostLedger` 的持久化是**显式**的——调用方决定何时 flush（通常是 run 结束）。没有自动 flush 机制。

### 2.5 与 TraceRecorder 的关联

TraceRecorder 的 `record_iteration()` 携带 `input_tokens` / `output_tokens` / `model` 字段（line 84-87），但 TraceRecorder 本身不计算成本。CostLedger 是独立的财务记录，二者通过 AgentLoop 的 Hook 层协同——`TracingHook` 打 trace 点，`TokenBudgetHook` / 调用方同步记入 Ledger。

---

## 3. ErrorClassifier — 错误类型自动打标

**文件**：`agent/observability.py`

### 3.1 错误分类体系

`ErrorCategory` 枚举（line 20-27）定义了 5 个结构化错误类别：

| 类别 | 值 | 说明 |
|------|-----|------|
| PERMISSION_DENIED | `"permission_denied"` | 权限拒绝 |
| NETWORK_TIMEOUT | `"network_timeout"` | 网络超时/限流 |
| MODEL_ERROR | `"model_error"` | 模型侧错误 |
| PARAMETER_ERROR | `"parameter_error"` | 参数/工具错误 |
| UNKNOWN | `"unknown"` | 兜底未知 |

### 3.2 三级分类优先级

`ErrorClassifier.classify()`（line 106-133）采用确定性三级优先级：

**优先级 1: 结构化 `error_type` 字段**（line 114-117）

`_ERROR_TYPE_TO_CATEGORY` 字典（line 45-63）包含 **17 条映射**：

| error_type | 类别 |
|------------|------|
| `permission_denied` | PERMISSION_DENIED |
| `permission` | PERMISSION_DENIED |
| `approval_required` | PERMISSION_DENIED |
| `approval_denied` | PERMISSION_DENIED |
| `approval_unavailable` | PERMISSION_DENIED |
| `timeout` | NETWORK_TIMEOUT |
| `network_timeout` | NETWORK_TIMEOUT |
| `network_error` | NETWORK_TIMEOUT |
| `rate_limit` | NETWORK_TIMEOUT |
| `parse_error` | PARAMETER_ERROR |
| `parameter_error` | PARAMETER_ERROR |
| `invalid_argument` | PARAMETER_ERROR |
| `unknown_tool` | PARAMETER_ERROR |
| `model_error` | MODEL_ERROR |
| `mcp_error` | UNKNOWN |
| `resource_exhausted` | UNKNOWN |
| `unavailable` | UNKNOWN |

**优先级 2: `finish_reason` 字段**（line 119-123）

- `max_tokens` / `length` / `content_filter` → MODEL_ERROR
- `error` → PARAMETER_ERROR

**优先级 3: 文本 fallback**（line 125-132）

仅在无结构化信号命中时使用。`_TEXT_PATTERNS`（line 66-69）包含两个 pattern 组：

- 权限相关关键词 → PERMISSION_DENIED
- 超时/网络关键词 → NETWORK_TIMEOUT

额外规则（line 131-132）：`[error:` 或 `error:` 前缀 → PARAMETER_ERROR。

### 3.3 Alert 级别

`_ALERT_LEVEL`（line 72-78）按类别定义了告警策略：

| 类别 | Alert 级别 |
|------|-----------|
| PERMISSION_DENIED | `"immediate"` |
| NETWORK_TIMEOUT | `"warn"` |
| MODEL_ERROR | `"warn"` |
| PARAMETER_ERROR | `"record"` |
| UNKNOWN | `"record"` |

`ErrorClassifier.alert_level()` 静态方法（line 135-138）返回对应告警级别。

### 3.4 异常 → error_type 映射

`exception_error_type()`（line 86-97）：从 Python 异常对象提取结构化 error_type：
- `asyncio.TimeoutError` → `"timeout"`
- `ConnectionError` / `TimeoutError` → `"network_error"`
- 其他 → `None`（交由文本 fallback 路径分类）

### 3.5 Mode → Phase 映射

`PHASE_BY_MODE`（line 31-36）将 AgentMode 映射为运行时 phase 标签，供 CostLedger 的 phase 维度使用：

| Mode | Phase |
|------|-------|
| `build` | `"building"` |
| `read_only` | `"review"` |
| `plan` | `"planning"` |
| `bypass` | `"bypass"` |

**与 dev-workflow 四阶段的区别**：文档注释（line 10-12）明确说明这套 phase 映射是**运行时**标签，不等同于 dev-workflow 的 wayfinding/planning/building/closing 四阶段。

### 3.6 语义错误的处理边界

文档注释（line 5-7）明确声明：**语义错误（hallucination）不在此处自动分类**，需要 LLM judge 判定，与 benchmark judge 决策保持一致。这符合可观测性最佳实践（OpenTelemetry GenAI / Langfuse）。

---

## 4. Benchmark Runner — git worktree 隔离执行

**文件**：`benchmarks/runner.py`

### 4.1 任务执行环境隔离

`BenchmarkRunner`（line 42-66）核心设计：每个 task 在独立工作区执行。

- 本地任务：通过 `_create_worktree()`（line 473-483）用 `git worktree add --detach <commit>` 创建**隔离 worktree**
- 外部 repo 任务（SWE-bench）：通过 `_clone_external_repo()`（line 485-512）clone 到 `tasks/<task_id>/.external_repo`
- `keep_worktrees` 参数（line 52）控制是否保留 worktree：**默认 `False`**（用完即清理）
- `clone_cache_dir` 参数（line 53-65）支持共享 bare clone 缓存加速外部 repo clone

### 4.2 并行控制

`parallel` 参数（line 51，**默认 `1`**，即串行）通过 `asyncio.Semaphore` 控制并发（line 135）。所有 task 通过 `asyncio.gather` 并行调度，信号量限制并发数。

### 4.3 本地任务流程（非 Docker 任务）

`run_task()` 方法（line 187-471）的本地路径：

1. 创建 worktree（line 254-256）
2. 隐藏 agent 不可见的 task 文件（line 258-262）：将 `benchmarks/tasks/` 目录移动到 `.hidden/`，防止 agent 作弊
3. 运行 agent（line 264）
4. 恢复隐藏文件（line 267-271）
5. 写出 diff（line 273-279）
6. 应用 test.patch（如有）（line 370-374）
7. 执行测试命令（line 388-395），记录 exit_code
8. 判定结果：exit_code==0 → `passed`/`passed_with_warnings`；否则 `failed`（line 409-425）

### 4.4 Docker 任务流程（SWE-bench）

1. Docker preflight 探测（line 232-245）：如果 Docker 不可用 → `unsupported`
2. Clone 外部 repo + 安装依赖（line 247-252）
3. 运行 agent（line 264）
4. 通过 `VerifierAdapter` 协议调用 SWE-bench 官方 `swebench.harness.run_evaluation`（line 307-368，在 `adapters.py:SwebenchAdapter.verify()` 中）
5. 判定结果：`resolved==True` → `passed`；否则 `failed`（line 132-137 in adapters.py）

### 4.5 Worktree 清理

不论成功或失败，`finally` 块（line 454-463）保证 worktree 被清理（`git worktree remove --force` + `rmtree` fallback）。

### 4.6 Clone 重试

`_git_clone_with_retry()`（line 514-540）：3 次重试，指数退避（60s → 120s → 240s），总计 4 次尝试。

---

## 5. Benchmark Statistics — bootstrap 95% CI

**文件**：`benchmarks/statistics.py`

### 5.1 Bootstrap 置信区间

`bootstrap_ci()`（line 38-62）实现标准 percentile-method bootstrap：

```python
def bootstrap_ci(
    values: Sequence[float],
    seed: int = 0,           # 固定种子，结果可复现
    n_resamples: int = 2000, # 重采样次数
    ci: float = 0.95,        # 置信水平，默认 95%
) -> tuple[float, float]:
```

实现细节：
- 使用 `random.Random(seed)` 固定种子确保可复现（line 52）
- 每次重采样从原样本中有放回抽取 n 个值计算均值（line 54-57）
- 对 2000 个 bootstrap 均值排序（line 58）
- percentile method：取 2.5% 和 97.5% 分位点（line 59-62）

### 5.2 Pass@k

`pass_at_k()`（line 76-92）实现 Chen et al. 2021 的组合估计器：

> `pass@k = 1 - C(n - c, k) / C(n, k)`

其中 n = 总轮数，c = 通过轮数，k = 子集大小。用于评估"跑 k 次至少一次通过"的概率。

`_comb(n, k)`（line 65-73）精确整数二项式系数计算，避免浮点误差。

### 5.3 辅助统计

| 函数 | 行号 | 说明 |
|------|------|------|
| `mean_std()` | 25 | 返回 (mean, sample stdev)，空输入返回 (0.0, 0.0) |
| `layer_pass_rate()` | 95 | 按 capability layer 计算通过率均值 |

### 5.4 Capability Layers

`LAYERS`（`benchmarks/models.py` line 11-17）定义四个能力分层：

```
execution → tool-usage → context-planning → multi-step-solving
```

`resolve_layer()`（line 20-28）将 task 的 `category` 映射到 layer，未知 category 回退到默认层 `"execution"`。

---

## 6. Benchmark Report — 评估报告生成

**文件**：`benchmarks/report.py`

### 6.1 Markdown 报告

`render_report()`（line 143-158）产出包含以下段落的 Markdown 报告：

| 章节 | 内容 | 对应代码行 |
|------|------|-----------|
| By Capability Layer | 按 layer 聚合：Tasks / Rounds / Pass Rate / 95% CI（bootstrap） | 176-193 |
| By Task | 逐任务：Pass@k / Passes / Mean±Std / 95% CI（bootstrap）/ p50 / p95 / p99 / Input Tokens / Output Tokens | 196-224 |
| Token Cost | Input/Output Tokens / Est. Cost（调用 `compute_cost`） | 228-237 |
| Failure Attribution | 按 reason 分类失败的 (task, round) look-back 样本 | 240-258 |

**统计使用确认**：
- bootstrap 95% CI 用于两个层面：(1) layer 级 Pass Rate 的 CI（line 188），(2) task 级 latency duration 的 CI（line 213）
- Pass@k 用于逐任务表格（line 209）

### 6.2 HTML 报告

`render_html()`（line 262-381）产出自包含 HTML 页面，内容与 Markdown 等价，带 CSS 样式。

### 6.3 失败归因

`failure_attribution()`（line 123-140）只统计 `failed` / `error` / `unsupported` 状态且 reason 不为 None 的结果，按 reason 分桶，返回 `{reason: [(task_id, round_index), ...]}`。

---

## 7. Benchmark Gate — CI 回归门禁

**文件**：`benchmarks/gate.py`

### 7.1 门禁语义

`compare()`（line 117-165）比较当前 run 的 metrics 与 baseline JSON：

| 指标 | 阈值 | 说明 |
|------|------|------|
| success_rate | 绝对下降不超过 **5pp**（0.05） | 严格 `>` 比较，含 epsilon 防浮点精度（line 150） |
| p95_latency_s | 相对增长不超过 **5%**，且绝对增长不超过 **1.0s** | `max(baseline * 1.05, baseline + 1.0)`（line 153），解决 sub-second baseline 的相对波动无意义问题 |

### 7.2 p95 延迟的特殊处理

- p95 仅对 **passed** 任务计算（line 64-65），避免 failed/crashed 任务（duration=0.0）拉低延迟掩盖回归
- `check_p95=False`（line 131-136）跳过 p95 检查，用于 gate-smoke 等确定性近零 IO 任务集
- `ABS_P95_FLOOR_S = 1.0`（line 32）：当 baseline p95 < 1s 时，用绝对 floor 代替相对 fraction

### 7.3 Baseline 管理

| 函数 | 行号 | 说明 |
|------|------|------|
| `load_baseline()` | 168 | 加载并校验 schema_version + metrics shape |
| `write_baseline()` | 193 | 写出 baseline JSON |
| `build_baseline()` | 200 | 组装 baseline dict（含 git_sha 追溯） |

baseline 路径默认 `benchmarks/baseline.json`（line 26），schema_version 固定为 `1`（line 27）。

### 7.4 实际 baseline 内容

`benchmarks/baseline.json` 当前使用 `agent="fake"`（即 fake agent 记录），这是合理的——fake agent 产出的 baseline 作为门禁的绝对值参考。

---

## 8. Cross-Agent Comparison — SWE-bench 跨 Agent 对比

**文件**：`benchmarks/compare.py`

### 8.1 功能

`compare.py` 是一个独立的 CLI 脚本，比较多个 benchmark run 的结果：

```
python benchmarks/compare.py <run-dir-1> <run-dir-2> ...
```

### 8.2 对比维度

`build_summary()`（line 40-127）产出的 Markdown 对比报告包含：

| 章节 | 内容 |
|------|------|
| Task-level table | 逐任务逐 agent 的 status + duration |
| Summary | 按 agent 按 status（passed/passed_with_warnings/unsupported/failed/error）的计数分布 |
| Latency Percentiles | 每个 agent 的 p50/p95/p99/max（line 86-96） |
| Cost Estimate | 每个 agent 的 Input/Output Tokens + Est. Cost（line 109-125） |

### 8.3 HTML 对比报告

`build_html()`（line 130-230）产出带 CSS 样式的 HTML 对比页面，status 用颜色区分（passed=绿色，failed=红色，error=紫色 等）。

### 8.4 输出位置

报告输出到 `benchmarks/reports/comparison.md` 和 `benchmarks/reports/comparison.html`（line 259-268）。

---

## 9. Verifier Adapter — 评测框架插件化

**文件**：`benchmarks/adapters.py`

### 9.1 协议

`VerifierAdapter` Protocol（line 31-41）定义标准接口：

```python
class VerifierAdapter(Protocol):
    def verify(
        self, loaded: LoadedTask, task_output, patch_text: str, log=None
    ) -> Verdict: ...
```

`Verdict` dataclass（line 21-28）：标准化的验证结果（status / reason / detail / score）。

### 9.2 注册机制

- `register_verifier(task_family, adapter_cls)`（line 143-145）：把适配器类注册到全局 `_REGISTRY` 字典
- `get_verifier(task_family, **kwargs)`（line 148-153）：按 task_family 查找并实例化适配器
- 当前仅注册了 `"swebench"` → `SwebenchAdapter`（line 156）

### 9.3 SwebenchAdapter

`SwebenchAdapter.verify()`（line 61-137）实现 SWE-bench Verified 验证协议：

1. 生成 `predictions.jsonl`（agent patch + instance_id + model name）（line 70-77）
2. 调用官方 `swebench.harness.run_evaluation` Docker 验证器（line 80-105）
3. 读取 `report.json`，检查 `resolved` 字段（line 114-137）
4. 返回 `Verdict(status="passed" if resolved else "failed")`（line 133）

**注意**：SWE-bench 验证需要 Docker — `SwebenchAdapter` 通过 `subprocess.run` 调用官方 harness，harness 内部使用 Docker 容器运行测试。

---

## 10. 任务数据集 — 36+ 个 coding 任务

### 10.1 任务计数确认

`benchmarks/tasks/` 下共有 **38 个 task.json**（`benchmarks/tasks/**/task.json` glob 结果）：

**26 个本地任务**（asterwynd-* + asterwynd-readme-title）：

| 序号 | 任务 ID | task_family |
|------|---------|-------------|
| 1 | asterwynd-001-tool-registry | local |
| 2 | asterwynd-002-asterwynd-runner | local |
| 3 | asterwynd-002-sandbox-executor | local |
| 4 | asterwynd-003-agentloop-trace | local |
| 5 | asterwynd-003-read-write-tools | local |
| 6 | asterwynd-004-benchmark-cli | local |
| 7 | asterwynd-004-harden-write | local |
| 8 | asterwynd-005-bash-workspace | local |
| 9 | asterwynd-006-memory-manager | local |
| 10 | asterwynd-007-skill-loader | local |
| 11 | asterwynd-008-parent-channel | local |
| 12 | asterwynd-009-subagent-manager | local |
| 13 | asterwynd-010-agent-loop | local |
| 14 | asterwynd-011-repeater-fix | local |
| 15 | asterwynd-012-sse-streaming | local |
| 16 | asterwynd-013-hook-manager | local |
| 17 | asterwynd-014-logging-tracing | local |
| 18 | asterwynd-015-retry-budget | local |
| 19 | asterwynd-017-interactive-fix | local |
| 20 | asterwynd-018-warning-passes | local |
| 21 | asterwynd-019-runner-timeout | local |
| 22 | asterwynd-020-close-clients | local |
| 23 | asterwynd-021-lsp-diagnostics | local |
| 24 | asterwynd-022-collaborative-context-audit | local |
| 25 | asterwynd-022-long-term-memory | local |
| 26 | asterwynd-readme-title | local |

**10 个 SWE-bench 外部任务**：

| 序号 | 任务 ID | task_family | 外部 repo |
|------|---------|-------------|-----------|
| 1 | swebench-psf__requests-1142 | swebench | psf/requests |
| 2 | swebench-psf__requests-1724 | swebench | psf/requests |
| 3 | swebench-psf__requests-1766 | swebench | psf/requests |
| 4 | swebench-psf__requests-1921 | swebench | psf/requests |
| 5 | swebench-psf__requests-2317 | swebench | psf/requests |
| 6 | swebench-psf__requests-5414 | swebench | psf/requests |
| 7 | swebench-pallets__flask-5014 | swebench | pallets/flask |
| 8 | swebench-pytest-dev__pytest-7521 | swebench | pytest-dev/pytest |
| 9 | swebench-pytest-dev__pytest-5262 | swebench | pytest-dev/pytest |
| 10 | swebench-pytest-dev__pytest-7982 | swebench | pytest-dev/pytest |

**2 个 gate-smoke 任务**（CI 回归门禁专用，不计入 36）：

| 序号 | 任务 ID |
|------|---------|
| 1 | gate-smoke-001 |
| 2 | gate-smoke-002 |

**结论**：简历中"36+ 个 coding 任务（26 本地 + 10 SWE-bench 外部）"经代码确认，数字精确。36 = 26（本地） + 10（SWE-bench），另外 2 个 gate-smoke 不计入 coding 任务。

### 10.2 外部 repo 任务的依赖安装

`_install_repo_deps()`（runner.py:542-610）使用 SWE-bench 的 `MAP_REPO_VERSION_TO_SPECS` 配置（line 544）确定 Python 版本和 pip 包。使用 `uv venv` + `uv pip install` 安装依赖。对 `psf/requests` 附加 `pytest-httpbin` + `werkzeug<3.0`（line 582-584）。

### 10.3 本地 httpbin 启动

对 requests repo 的任务，runner 启动本地 httpbin 服务器（line 378-398），避免依赖远程 httpbin.org（可能返回 503）。`_start_local_httpbin()`（line 745-769）在随机端口启动，设置 `HTTPBIN_URL` 环境变量传给测试进程。

---

## 11. CI 回归门禁

**文件**：`.github/workflows/ci.yml`

### 11.1 两个 CI Job

| Job | 名称 | 触发条件 | 说明 |
|-----|------|----------|------|
| `validate` | validate | PR + push to master | pytest + OpenSpec validate + artifact checker |
| `benchmark-gate` | benchmark-gate | PR + push to master | 回归门禁 |

### 11.2 benchmark-gate Job 细节

触发的命令（line 96）：

```bash
uv run asterwynd benchmark-gate benchmarks/tasks/gate-smoke \
  --source-repo . \
  --runs-dir /tmp/benchmark-gate-runs \
  --baseline benchmarks/baseline.json \
  --require-baseline \
  --skip-p95
```

关键参数：
- `--source-repo .`：以当前仓库为 source repo，创建 worktree
- `--runs-dir /tmp/benchmark-gate-runs`：产出目录
- `--baseline benchmarks/baseline.json`：门禁 baseline 文件
- `--require-baseline`：强制 requirement baseline 存在
- `--skip-p95`：跳过 p95 延迟检查（gate-smoke 任务集确定性高、IO 近零，p95 受环境因素主导，不作为可靠回归信号）——这与 gate.py 的 `check_p95=False` 参数对应（line 131-136, 164）

### 11.3 关闭条件

Benchmark gate **仅在 PR 和 push to master 时触发**（line 3-7）。本地运行时需手动执行 `benchmark-gate` 命令。这不是一个自动化的 pre-commit hook。

---

## 12. 未覆盖或默认关闭的功能总结

| 功能 | 状态 | 位置 | 说明 |
|------|------|------|------|
| `full_trace` | 默认 `False` | `trace_recorder.py:27` | 全量追踪开关，保留为序列化兼容用途，当前不启用 |
| `session_id` | 默认 `None` | `trace_recorder.py:29` | 需外部注入，无自动生成 |
| `run_id` | 默认 `None` | `trace_recorder.py:30` | 需外部注入，无自动生成 |
| `keep_worktrees` | 默认 `False` | `runner.py:52` | 保留 worktree 用于调试，用完即清理 |
| `clone_cache_dir` | 默认 `None` | `runner.py:63-65` | 共享 clone 缓存加速，需显式传入 |
| `parallel` | 默认 `1`（串行） | `runner.py:51` | 并发数需手动增加 |
| `/review-loop` | 必检门禁 | `AGENTS.md` | 由 OpenSpec artifact checker 强制，非 CI 内置步骤 |
| 语义错误分类 | 不在此处 | `observability.py:5-7` | 需要 LLM judge，与 benchmark judge 一致 |
| SWE-bench 多框架支持 | 仅 swebench | `adapters.py:156` | 其他框架（Harbor 等）需新增适配器 |

---

## 关键文件索引

| 文件 | 内容 |
|------|------|
| `agent/trace_recorder.py` | TraceRecorder — 18 种事件类型的全链轨迹记录器 + TraceRecorderSandboxSink |
| `agent/cost_tracker.py` | CostLedger — 三层成本归因（by_session/by_phase/by_tool）+ 8 模型定价 |
| `agent/observability.py` | ErrorClassifier — 5 类错误分类 + 17 条 error_type 映射 + 三级优先级 |
| `agent/run_identity.py` | new_session_id() / new_run_id() — 12 位 hex 标识生成 |
| `benchmarks/runner.py` | BenchmarkRunner — worktree 隔离 + Docker preflight + local/httpbin/verify 三路径 |
| `benchmarks/statistics.py` | bootstrap_ci (95% CI, 2000 resamples, seed=0) + pass_at_k + mean_std |
| `benchmarks/report.py` | Markdown/HTML 报告渲染 — layer 聚合 + task 表 + cost + failure attribution |
| `benchmarks/gate.py` | 回归门禁 — success_rate drop > 5pp 或 p95 回归 → FAIL |
| `benchmarks/compare.py` | 跨 Agent 对比 CLI — 多 run 摘要 + 延迟分位 + 成本估算 |
| `benchmarks/adapters.py` | VerifierAdapter Protocol + SwebenchAdapter + 注册机制 |
| `benchmarks/models.py` | TaskResult / RunMetadata / BenchmarkReason / LAYERS (4 能力分层) |
| `benchmarks/task_schema.py` | TaskSpec / LoadedTask — 任务规格定义、校验、加载 |
| `benchmarks/baseline.json` | 当前 baseline（fake agent, gate-smoke, success_rate=1.0, p95=10.0s） |
| `.github/workflows/ci.yml` | CI pipeline — validate + benchmark-gate 两个 job |
| `benchmarks/tasks/` | 38 个 task.json — 26 本地 + 10 SWE-bench + 2 gate-smoke |
