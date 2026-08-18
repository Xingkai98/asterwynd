# Bullet 7: 全链路可观测体系与 Benchmark 评测闭环 — 代码走读

> 简历原文：建立全链路可观测体系与 Benchmark 评测闭环：TraceRecorder 全链轨迹记录 + CostLedger 三层成本归因 + ErrorClassifier 错误类型自动打标；72 个 coding 任务（34 本地 = 22 A 轨回归基线 + 12 B 轨当前演进 + 38 SWE-bench Verified 子集）在 git worktree / Docker 隔离执行，pass@1/pass^k/成本（cache-aware）与 fault_owner 归因统计，场景×难度分层覆盖矩阵，支持跨 Agent 配对比较与 CI 回归门禁

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

时间戳打在 `TraceStep` 层，而非 data 载荷内部（line 52-61 注释说明），保持事件数据清洁且向后兼容。`schema_version` 固定为 `"1.1"`（line 242）。

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
| `benchmark_preflight` | `record()` 内联调用 | runner.py:330-335 | Benchmark 预检（docker 环境探测） |

### 1.4 序列化与持久化

- `to_dict()`（line 236）：产出完整 trace dict，含 task_id、mode、duration_seconds、steps 数组
- `to_json()`（line 251）：JSON 字符串，`ensure_ascii=False`
- `write_to_file(path)`（line 254）：`errors="replace"` 写出文件

### 1.5 SandboxSink 适配器

`TraceRecorderSandboxSink`（line 258-269）将沙箱事件桥接到 TraceRecorder 的 `record_sandbox_event`，非阻塞追加。

### 1.6 集成点

在 `benchmarks/runner.py` 中，每个 task 启动时创建独立的 `TraceRecorder` 实例（line 296-301）：

```python
trace = TraceRecorder(
    task_id=loaded.task.id,
    mode=self.run_config.mode.value,
    run_id=agent_run_id,
)
```

runner 通过 `trace.record_diff()`（line 368）、`trace.record_test()`（line 504）、`trace.record_completion()`（line 335, 399, 469, 553, 560）打点，最终 `trace.write_to_file()` 写入 `trace.json`（line 575），存放在每个 task 的输出目录 `tasks/<task_id>/trace.json`（`TaskArtifacts`，line 286-288）。

---

## 2. CostLedger — 三层成本归因 + cache-aware 定价

**文件**：`agent/cost_tracker.py`

### 2.1 模型定价表（cache-aware 四档）

`MODEL_PRICES`（line 15-33）包含 17 个模型的四档价格（USD / 1M tokens，fresh input / cache read / cache write / output 的顺序）：

| 模型 | Input ($/1M) | Cache Read | Cache Write | Output ($/1M) |
|------|-------------|-----------|-------------|---------------|
| gpt-4o | 2.50 | 0.25 | 3.125 | 10.00 |
| gpt-4o-mini | 0.15 | 0.015 | 0.1875 | 0.60 |
| gpt-5 | 3.75 | 0.375 | 4.6875 | 15.00 |
| claude-sonnet-4 / -4-6 / -5 | 3.00 | 0.30 | 3.75 | 15.00 |
| claude-opus-4 | 15.00 | 1.50 | 18.75 | 75.00 |
| claude-opus-4-6 / -4-7 / -4-8 / -5 | 5.00 | 0.50 | 6.25 | 25.00 |
| claude-fable-5 | 10.00 | 1.00 | 12.50 | 50.00 |
| claude-haiku-3.5 | 0.80 | 0.08 | 1.00 | 4.00 |
| claude-haiku-4-5 | 1.00 | 0.10 | 1.25 | 5.00 |
| deepseek-chat | 0.27 | 0.027 | 0.3375 | 1.10 |
| deepseek-reasoner | 0.55 | 0.055 | 0.6875 | 2.19 |
| deepseek-v4-flash | 0.0 | 0.0 | 0.0 | 0.0（自托管近零成本档） |

**关键升级（评测升级）**：定价从两档（input/output）升级为 **cache-aware 四档**。cache read = 0.1× fresh input，cache write = 1.25× fresh input（Anthropic prompt-caching 经济模型，5 分钟 TTL），注释见 line 9-12。`PRICING_TABLE_VERSION = "2026-08-17"`（line 13）随报告披露。未知模型 fallback 用表内平均价估算（`_AVG_INPUT_PRICE` / `_AVG_OUTPUT_PRICE`，line 37-38），永不为 0 静默少计。

**注意**：定价是写死在代码中的常量表。如需支持新模型或价格变动，需修改源码。这不是运行时可配置的。

### 2.2 按前缀匹配的成本计算

- `compute_cost(model, input_tokens, output_tokens)`（line 58-63）：两档（无 cache）成本，按 `MODEL_PRICES` 的 key 长度降序做 `startswith` 前缀匹配，避免短前缀误命中（如 `gpt-4o` 匹配 `gpt-4o-mini` 之前）。CostLedger 的 `record()` 走这条路径。
- `compute_cost_cached(model, input_tokens, cache_read_tokens, cache_write_tokens, output_tokens)`（line 66-100）：**四档 cache-aware** 成本，返回 `CostEstimate(cost, known)`；unknown 模型用表内平均价估算并记 `known=False`。
- `cache_hit_rate(cache_read_tokens, fresh_input_tokens)`（line 103-112）：cache 命中率 = cache_read / (cache_read + fresh)，cache-write 是一次性写成本不算命中。
- `format_cost(cost)`（line 115-120）：小额成本显示 6 位小数。

### 2.3 CostLedger 三层归因（"三层"的出处）

`CostLedger` 类（line 123-227）是成本的财务记账，与 trace（过程记录）解耦。

- **`record()`**（line 141-164）：记录单次 LLM 调用的成本，入参携带三个归因维度：
  - `session_id`：按会话归因
  - `phase`：按运行阶段归因（building / review / planning / bypass，由 `observability.py:PHASE_BY_MODE` 映射）
  - `tool_name`：按工具归因（可为 None）
- **`bill()`**（line 168-187）：返回三个维度的聚合结果，这就是简历中"**三层成本归因**"的来源：

```python
return {
    "by_session": by_session,   # 第一层：按 session
    "by_phase": by_phase,       # 第二层：按 phase
    "by_tool": by_tool,         # 第三层：按 tool
}
```

每层的每个 bucket 包含 `tokens`（总 token 数）和 `cost`（累计费用）两个字段。

### 2.4 持久化

- **`flush(path)`**（line 189-206）：将新增条目追加为 JSONL 文件，使用 `_flushed_count` 游标防止重复写入。同一个 Ledger 实例可被父 agent 和子 agent 共享，各自在 run end 时 flush。
- **`load(path)`**（line 208-226）：从 JSONL 恢复条目。加载后 `_flushed_count` 已推进，后续 flush 只写新条目。

**注意**：`CostLedger` 的持久化是**显式**的——调用方决定何时 flush（通常是 run 结束）。没有自动 flush 机制。

### 2.5 与 TraceRecorder 的关联

TraceRecorder 的 `record_iteration()` 携带 `input_tokens` / `output_tokens` / `model` 字段（line 84-87），但 TraceRecorder 本身不计算成本。CostLedger 是独立的财务记录，二者通过 AgentLoop 的 Hook 层协同——`TracingHook` 打 trace 点，`TokenBudgetHook` / 调用方同步记入 Ledger。

**benchmark 侧的关联**（评测升级）：`agent/loop.py` 的 token 计数器在评测升级后记录 `cache_read` / `cache_creation`（loop.py:553-558, 640-645），`TaskResult` / `RunMetadata` 也新增了 `cache_read_tokens` / `cache_write_tokens` 字段（`benchmarks/models.py:83-84`），供 `$/resolved-task` 用 `compute_cost_cached` 精确核算。

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

`_ERROR_TYPE_TO_CATEGORY` 字典（line 45-65）包含 **17 条映射**：

| error_type | 类别 |
|------------|------|
| `permission_denied` / `permission` / `approval_required` / `approval_denied` / `approval_unavailable` | PERMISSION_DENIED |
| `timeout` / `network_timeout` / `network_error` / `rate_limit` | NETWORK_TIMEOUT |
| `parse_error` / `parameter_error` / `invalid_argument` / `unknown_tool` | PARAMETER_ERROR |
| `model_error` | MODEL_ERROR |
| `mcp_error` / `resource_exhausted` / `unavailable` | UNKNOWN |

**优先级 2: `finish_reason` 字段**（line 119-123）

- `max_tokens` / `length` / `content_filter` → MODEL_ERROR
- `error` → PARAMETER_ERROR

**优先级 3: 文本 fallback**（line 125-132）

仅在无结构化信号命中时使用。`_TEXT_PATTERNS`（line 66-71）包含权限与超时两个 pattern 组；`[error:` 或 `error:` 前缀 → PARAMETER_ERROR（line 131-132）。

### 3.3 Alert 级别

`_ALERT_LEVEL`（line 72-78）按类别定义了告警策略：

| 类别 | Alert 级别 |
|------|-----------|
| PERMISSION_DENIED | `"immediate"` |
| NETWORK_TIMEOUT | `"warn"` |
| MODEL_ERROR | `"warn"` |
| PARAMETER_ERROR | `"record"` |
| UNKNOWN | `"record"` |

`ErrorClassifier.alert_level()` 静态方法（line 136-138）返回对应告警级别。

### 3.4 异常 → error_type 映射

`exception_error_type()`（line 86-97）：从 Python 异常对象提取结构化 error_type：
- `asyncio.TimeoutError` → `"timeout"`
- `ConnectionError` / `TimeoutError` → `"network_error"`
- 其他 → `None`（交由文本 fallback 路径分类）

### 3.5 Mode → Phase 映射

`PHASE_BY_MODE`（line 31-44）将 AgentMode 映射为运行时 phase 标签，供 CostLedger 的 phase 维度使用：

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

`BenchmarkRunner`（line 76）核心设计：每个 task 在独立工作区执行。

- 本地任务：通过 `_create_worktree()`（line 580）用 `git worktree add --detach <commit>` 创建**隔离 worktree**
- 外部 repo 任务（SWE-bench）：通过 `_clone_external_repo()`（line 592）clone 到 `tasks/<task_id>/.external_repo`
- `keep_worktrees` 参数（line 86）控制是否保留 worktree：**默认 `False`**（用完即清理）
- `clone_cache_dir` 参数（line 87-109）支持共享 bare clone 缓存加速外部 repo clone

### 4.2 并行控制

`parallel` 参数（line 85，**默认 `1`**，即串行）通过 `asyncio.Semaphore` 控制并发（line 204）。所有 task 通过 `asyncio.gather` 并行调度，信号量限制并发数。

### 4.3 本地任务流程（非 Docker 任务）

`run_task()` 方法（line 276-575）的本地路径：

1. 创建 worktree（`_create_worktree` line 580）
2. 隐藏 agent 不可见的 task 文件（`_hide_agent_invisible_task_files` line 739）：将 `benchmarks/tasks/` 目录移动到 `.hidden/`，防止 agent 作弊
3. 运行 agent
4. 恢复隐藏文件（`_restore_agent_invisible_task_files` line 751）
5. 写出 diff（`trace.record_diff()` line 368）
6. 应用 test.patch（如有）（`_apply_test_patch` line 785）
7. 执行测试命令（`trace.record_test()` line 504），记录 exit_code
8. 判定结果：exit_code==0 → `passed`/`passed_with_warnings`；否则 `failed`（`trace.record_completion(status)` line 553）

### 4.4 Docker 任务流程（SWE-bench）

1. Docker preflight 探测（`_probe_docker()` line 159，判定 line 330-336）：如果 Docker 不可用 → `unsupported`
2. Clone 外部 repo + 安装依赖（`_install_repo_deps()` line 649）
3. 运行 agent
4. 通过 `VerifierAdapter` 协议调用 SWE-bench 官方 `swebench.harness.run_evaluation`（在 `adapters.py:SwebenchAdapter.verify()` 中，line 76-155）
5. 判定结果：`resolved==True` → `passed`；否则 `failed`（adapters.py:147-155）

### 4.5 Worktree 清理

不论成功或失败，`finally` 块保证 worktree 被清理（`git worktree remove --force` + `rmtree` fallback）。

### 4.6 Clone 重试

`_git_clone_with_retry()`（line 621）：3 次重试，指数退避（60s → 120s → 240s），总计 4 次尝试。

### 4.7 本地 httpbin 启动

对 requests repo 的任务，runner 启动本地 httpbin 服务器（`_start_local_httpbin()` line 852），避免依赖远程 httpbin.org（可能返回 503）。

---

## 5. 任务 Schema 与套件级能力覆盖矩阵（评测升级）

**文件**：`benchmarks/task_schema.py` + `benchmarks/task_set.py`

### 5.1 任务级双标签：scenario × difficulty

`task_schema.py` 定义任务规格的标准化校验（`TaskSpec.from_dict` line 37-72，`validate()` line 74-104）：

| 字段 | 枚举 | 代码位置 |
|------|------|---------|
| `scenario` | bug-fix / feature-dev / refactor / debug / integration（5 枚举） | `SCENARIOS` line 8，`TaskSpec.scenario` line 27 |
| `difficulty` | easy / medium / hard（3 档） | `DIFFICULTIES` line 9，`TaskSpec.difficulty` line 26 |
| `track` | A / B / verified（任务集三来源） | `TRACKS` line 11，`TaskSpec.track` line 28 |

任务 schema 是**单一事实源**：每个 `task.json` 用 `scenario`（代码改动类型，主组织轴）+ `difficulty`（归一化难度）做双标签，`track` 标记任务来源轨。非法枚举在加载时直接抛错（line 83-90）。

当前任务集分布（已核实）：本地任务 scenario 覆盖 bug-fix 6 / feature-dev 20 / refactor 3 / debug 3 / integration 2，difficulty easy 9 / medium 17 / hard 8。

### 5.2 套件级能力覆盖矩阵（OpenHands 式）

**关键设计决策（D2）**：能力分层从"逐任务打 category 标签"升级为**套件级覆盖矩阵**——`task_set.py` 声明 7 个能力列，任务在 manifest 中登记覆盖哪些列：

```python
# task_set.py:20-28
CAPABILITIES = [
    "tool-usage", "context-planning", "multi-step-solving",
    "error-recovery", "safety-boundary", "long-term-memory", "long-context",
]
# task_set.py:31 — 场景 5 枚举规范顺序
SCENARIO_ORDER = ("bug-fix", "feature-dev", "refactor", "debug", "integration")
```

`Manifest.validate_coverage()`（task_set.py:82-135）机械校验：

- 每个能力列至少有一个**本地 A/B 任务**登记（`_LOCAL_TRACKS = {None, "A", "B"}`，line 34——verified 子集不计入矩阵，避免 bug-fix 偏置撑满场景列）
- 每个场景列（5 枚举）至少有一个本地 A/B 任务
- **按轨能力覆盖**（`REQUIRED_TRACK_COVERAGE` line 39-43）：`context-planning` / `long-term-memory` / `long-context` 三列必须分别有 **B 轨**任务登记——这是 spec delta 的机械强制

manifest 存储于 `benchmarks/tasks/manifest.json`：`coverage` 段登记 34 个本地任务的能力列覆盖，`verified` 段单独披露 Verified 子集摘要（count / by_repo / by_difficulty，`update_manifest_verified` 由 build-subset 管线维护）。

---

## 6. Benchmark Statistics — bootstrap + pass@k + pass^k + 成本 + 归因

**文件**：`benchmarks/statistics.py`

### 6.1 Bootstrap 置信区间

`bootstrap_ci()`（line 107-131）实现标准 percentile-method bootstrap：

```python
def bootstrap_ci(
    values: Sequence[float],
    seed: int = 0,           # 固定种子，结果可复现
    n_resamples: int = 2000, # 重采样次数
    ci: float = 0.95,        # 置信水平，默认 95%
) -> tuple[float, float]:
```

实现细节：
- 使用 `random.Random(seed)` 固定种子确保可复现（line 121）
- 每次重采样从原样本中有放回抽取 n 个值计算均值（line 123-126）
- 对 2000 个 bootstrap 均值排序（line 127）
- percentile method：取 2.5% 和 97.5% 分位点（line 128-131）

### 6.2 Pass@k 与 Pass^k（能力上限 vs 可靠性）

**`pass_at_k()`**（line 145-161）实现 Chen et al. 2021 的组合估计器：

> `pass@k = 1 - C(n - c, k) / C(n, k)`

其中 n = 总轮数，c = 通过轮数，k = 子集大小。用于评估"跑 k 次至少一次通过"的概率（**能力上限**）。`_comb(n, k)`（line 134-142）精确整数二项式系数计算，避免浮点误差。

**`pass_k_success_rate()`**（line 188-218）是评测升级新增的任务级 **pass^k** 聚合（**可靠性**）：

```python
def pass_k_success_rate(
    task_rounds: Sequence[Sequence[bool]],
    min_valid_rounds: int = 3,
) -> PassKSummary:
```

- 每个任务在所有**有效轮**（invalid rounds 已剔除）全部通过才算 pass
- 有效轮数 < `min_valid_rounds=3` 的任务从分子分母中排除（样本太小无统计意义）
- 返回 `PassKSummary(rate, passed_tasks, valid_tasks, excluded_tasks, min_valid_rounds)`

**指标语义（报告页 line 218-223 明确声明）**：
- **pass@1** = 有效轮经验通过率（用户实际获得）
- **pass@k** = k 次任一成功（能力上限，组合估计）
- **pass^k** = 全部有效轮成功（可靠性）

**无效轮次不进分母**（`is_valid_round()` line 60-71 + `INVALID_ROUND_REASONS` line 55-57）：`unsupported` 状态 + `docker_unavailable` / `task_family_unsupported` / `approval_unavailable` 三类 reason 的轮次既不算通过也不算失败。

### 6.3 $/resolved-task（cache-aware）

`cost_per_resolved()`（line 229-254）是评测升级新增的成本-精度指标：

```python
def cost_per_resolved(results: Sequence[TaskResult]) -> tuple[float | None, float, int]:
```

- **分子**：全部 run 的 LLM token 总成本（**含失败 run**，cache-aware 用 `compute_cost_cached` 四档定价核算）
- **分母**：resolved 数（`passed` + `passed_with_warnings`）
- **口径声明**：仅 LLM token 计费，不含沙箱 / CI / 计算成本

### 6.4 fault_owner 失败归因交叉表

`FAULT_OWNERS`（line 46）= `("agent", "task", "environment", "unknown")`，与 reason 正交的失败归因维度。

`fault_owner_cross()`（line 257-280）产出 **reason × fault_owner 交叉表**：只统计 `failed` / `error` 结果（`unsupported` 不算失败），无效/未标注的 fault_owner fallback 到 `unknown`。

### 6.5 配对比较（跨 Agent 对比的统计核心）

`paired_comparison()`（line 401-439）+ `mcnemar_exact()`（line 379-398）实现配对统计：

| 统计量 | 实现 | 代码位置 |
|--------|------|---------|
| per-task delta | 共享任务集上 A 的 pass@1 − B 的 pass@1 | `_pass1_by_task` line 320-333 |
| 差异 CI | **配对 bootstrap**（同一任务索引同时读两侧 run，保持配对性） | `_paired_delta_ci` line 351-376 |
| win-rate | A 胜 / B 胜 / 平 的任务数 | line 419-421 |
| McNemar | 在 pass^k 布尔上做 exact-binomial 检验 | `mcnemar_exact` line 379-398 |

**配对 vs 独立**（line 363-366 注释）：独立重采样会得到 Var(A)+Var(B)（高估方差、低估显著性），配对重采样得到 Var(A−B)，这才是"同一批任务换 agent"的正确推断。

### 6.6 辅助统计

| 函数 | 行号 | 说明 |
|------|------|------|
| `mean_std()` | 94 | 返回 (mean, sample stdev)，空输入返回 (0.0, 0.0) |
| `layer_pass_rate()` | 164 | 按 capability layer 计算通过率均值 |
| `valid_round_count()` | 85 | 有效轮数 N（per-task CI 小样本声明用） |
| `process_efficiency()` | 446 | time-to-first-successful-edit / exploration fraction（D10） |
| `swebench_versions()` | 496 | dataset/swebench 包版本（污染披露元组，D11） |
| `cohen_kappa()` | 283 | 标注一致性（fault_owner 校准预留） |

### 6.7 Capability Layers

`LAYERS`（`benchmarks/models.py` line 11-16）定义四个能力分层：

```
execution → tool-usage → context-planning → multi-step-solving
```

`resolve_layer()`（line 20-28）将 task 的 `category` 映射到 layer，未知 category 回退到默认层 `"execution"`。`BenchmarkReason` 枚举（line 31-42）定义 **11 类失败 reason**：setup_error / tool_error / edit_validation / test_failure / test_timeout / max_iterations / no_change / out_of_scope_change / model_failure / docker_unavailable / docker_runtime_error。

---

## 7. Benchmark Report — 评估报告生成

**文件**：`benchmarks/report.py`

### 7.1 Markdown 报告

`render_report()`（line 172-190）产出包含以下段落的 Markdown 报告：

| 章节 | 内容 | 对应代码行 |
|------|------|-----------|
| 指标语义 | pass@1 / pass@k / pass^k 定义 + 无效轮次声明 | 218-223 |
| By Capability Layer | 按 layer 聚合：Tasks / Rounds / Pass Rate / 95% CI（bootstrap）/ **Pass^k** | 227-255 |
| By Task | 逐任务：Pass@k / Passes / **Pass^k** / Mean±Std / 95% CI / p50 / p95 / p99 / Input / Output Tokens | 258-299 |
| Token Cost | Input/Output Tokens / Est. Cost（调用 `compute_cost`） | 302-312 |
| Failure Attribution | 按 reason 分类失败的 (task, round) look-back 样本 | 315-332 |
| C3 Disclosure | 披露段（报告元组 / 污染注记 / 反作弊 / 交叉表 / 成本 / f2p·p2p / 采样 / 小样本 / 过程效率 / 覆盖矩阵 / Verified） | 334-346 |

**评测升级确认**：
- **Pass^k 列**：layer 表（line 240-254）和 task 表（line 276-283）都新增 Pass^k。task 级 pass^k 需 ≥3 有效轮才显示 yes/no，否则显示 `—`。
- **预算截断轮处理**（line 206-210）：`truncated: true` 的轮次保留其真实完成的 task 结果计入 pass@1，但从 pass^k 分母剔除（Q4 确认）。
- 无效轮（unsupported / approval-unavailable / docker-unavailable）不计入任何 pass-rate 分母（`_valid_results` line 84-90）。

### 7.2 HTML 报告

`render_html()`（line 351-518）产出自包含 HTML 页面，内容与 Markdown 等价，带 CSS 样式 + 披露段（line 470-481）。

### 7.3 失败归因

`failure_attribution()`（line 151-169）只统计 `failed` / `error` 状态且 reason 不为 None 的结果，按 reason 分桶，返回 `{reason: [(task_id, round_index), ...]}`，与 `fault_owner_cross` 的失败集一致（`unsupported` 不算失败）。

---

## 8. Benchmark Gate — CI 回归门禁

**文件**：`benchmarks/gate.py`

### 8.1 门禁语义

`compare()`（line 117-165）比较当前 run 的 metrics 与 baseline JSON：

| 指标 | 阈值 | 说明 |
|------|------|------|
| success_rate | 绝对下降不超过 **5pp**（0.05） | 严格 `>` 比较，含 epsilon 防浮点精度 |
| p95_latency_s | 相对增长不超过 **5%**，且绝对增长不超过 **1.0s** | `max(baseline * 1.05, baseline + 1.0)`，解决 sub-second baseline 的相对波动无意义问题 |

### 8.2 p95 延迟的特殊处理

- p95 仅对 **passed** 任务计算，避免 failed/crashed 任务（duration=0.0）拉低延迟掩盖回归
- `check_p95=False` 跳过 p95 检查，用于 gate-smoke 等确定性近零 IO 任务集
- `ABS_P95_FLOOR_S = 1.0`（line 32）：当 baseline p95 < 1s 时，用绝对 floor 代替相对 fraction

### 8.3 Baseline 管理

| 函数 | 行号 | 说明 |
|------|------|------|
| `compute_run_metrics()` | 54 | 从 TaskResult 列表计算 success_rate / p95 等指标 |
| `load_baseline()` | 168 | 加载并校验 schema_version + metrics shape |
| `write_baseline()` | 193 | 写出 baseline JSON |
| `build_baseline()` | 200 | 组装 baseline dict（含 git_sha 追溯） |

baseline 路径默认 `benchmarks/baseline.json`，schema_version 固定为 `1`。

### 8.4 实际 baseline 内容

`benchmarks/baseline.json` 当前使用 `agent="fake"`（即 fake agent 记录），这是合理的——fake agent 产出的 baseline 作为门禁的绝对值参考。

---

## 9. Cross-Agent Comparison — 配对比较 + 多 run 对比

**文件**：`benchmarks/compare.py`

### 9.1 功能

`compare.py` 是一个独立的 CLI 脚本，比较多个 benchmark run 的结果：

```
python benchmarks/compare.py <run-dir-1> <run-dir-2> ...
```

### 9.2 对比维度

`build_summary()`（line 105-203）产出的 Markdown 对比报告包含：

| 章节 | 内容 |
|------|------|
| Task-level table | 逐任务逐 agent 的 status + duration |
| Summary | 按 agent 按 status（passed/passed_with_warnings/unsupported/failed/error）的计数分布 |
| Latency Percentiles | 每个 agent 的 p50/p95/p99/max |
| Cost Estimate | 每个 agent 的 Input/Output Tokens + Est. Cost |
| Run Metadata | 报告元组（agent/model/harness） |

### 9.3 配对比较段（评测升级新增）

当且仅当输入为**恰好两个** run 时，`build_paired_report()`（line 234-280）追加 `## Paired Comparison` 段，复用 `statistics.paired_comparison` 的统计量：

| 行 | 指标 | 来源 |
|----|------|------|
| 258-259 | Mean per-task delta (pass@1) + Difference 95% CI (paired bootstrap) | `_paired_data` line 215-231 |
| 262-269 | Win-rate（A/B/ties）+ McNemar (pass^k) | `paired_comparison()` |
| 273-278 | 逐任务 delta 明细表 | `comp.per_task_deltas` |

HTML 侧 `_build_paired_html()`（line 48-90）共享同一份数据，嵌入 `build_html()`（line 282-407）。

### 9.4 输出位置

报告输出到 `benchmarks/reports/comparison.md` 和 `benchmarks/reports/comparison.html`（`main()` line 411，写入 line 449-455）。

---

## 10. Verifier Adapter — 评测框架插件化

**文件**：`benchmarks/adapters.py`

### 10.1 协议

`VerifierAdapter` Protocol（line 37-44）定义标准接口：

```python
class VerifierAdapter(Protocol):
    def verify(
        self, loaded: LoadedTask, task_output, patch_text: str, log=None
    ) -> Verdict: ...
```

`Verdict` dataclass（line 22-35）：标准化的验证结果（status / reason / detail / score / **resolved**）。`resolved` 是 C2 新增的 strict-resolved 布尔，用于 `$/resolved-task` 分母。

### 10.2 注册机制

- `register_verifier(task_family, adapter_cls)`：把适配器类注册到全局注册表
- `get_verifier(task_family, **kwargs)`：按 task_family 查找并实例化适配器
- 当前注册了 `"swebench"` → `SwebenchAdapter`（并兼容 `"swebench-verified"` 等实例级 family）

### 10.3 SwebenchAdapter

`SwebenchAdapter`（line 50-155）实现 SWE-bench Verified 验证协议，`verify()` 在 line 76：

1. 生成 `predictions.jsonl`（agent patch + instance_id + model name）（line 85-92）
2. **model name 转义修复（CP-4）**：`_report_model_dir()`（line 68-74）对 model name 做 `replace("/", "__")` 转义——harness 按 `model_name_or_path` 生成报告目录，未转义会导致 report 路径找不到（该修复已合入）
3. 调用官方 `swebench.harness.run_evaluation` Docker 验证器（line 98）
4. 读取 `report.json`，检查 `resolved` 字段（line 147-155）
5. 返回 `Verdict(status="passed" if resolved else "failed")`

**注意**：SWE-bench 验证需要 Docker — `SwebenchAdapter` 通过 `subprocess.run` 调用官方 harness，harness 内部使用 Docker 容器运行测试。

---

## 11. 任务数据集 — 72 个 coding 任务

### 11.1 任务计数确认（合并 master 后已核实）

`benchmarks/tasks/` 下共有 **74 个 task.json**（`benchmarks/tasks/*/task.json` glob 结果）：

| 类别 | 数量 | 说明 |
|------|------|------|
| 本地任务（`task_family=local`） | **34** | 22 A 轨回归基线 + 12 B 轨当前演进 |
| SWE-bench Verified 子集（`task_family=swebench`） | **38** | 全部 `track=verified`，dataset = `princeton-nlp/SWE-bench_Verified` |
| gate-smoke（CI 门禁专用） | 2 | 在 `gate-smoke/` 二级目录，不计入 coding 任务 |

**coding 任务合计 = 72**（34 本地 + 38 Verified）。`run_all()`（runner.py:192-195）对 `benchmarks/tasks` 做一层 `iterdir()`，默认加载全部 72 个；gate-smoke 在二级目录，只有 `benchmark-gate` 命令显式指定才跑。

> **数字口径**：上一版口径为 36（26 本地 + 10 SWE-bench 外部）；master 合并后本地任务经 B 轨扩展为 34（22 A + 12 B），Verified 子集经 build-subset 管线生成为 38（原 10 + 本机生成 28），合计 72。`docs/benchmark-run-protocol.md` 的协议目标口径为 82–90（A 轨 20–24 + B 轨 12–16 + Verified 50），是升级方向而非现状。

### 11.2 本地任务 34 = 22 A 轨 + 12 B 轨

**A 轨·历史重建回归基线（22）**：基于 2026-06 前合入特性的历史重建任务，作为回归基线（有答案泄漏面，结果页强制披露，非公平评测）：

| 任务 ID | 任务 ID |
|---------|---------|
| asterwynd-001-tool-registry | asterwynd-012-sse-streaming |
| asterwynd-002-asterwynd-runner | asterwynd-013-hook-manager |
| asterwynd-003-agentloop-trace | asterwynd-014-logging-tracing |
| asterwynd-003-read-write-tools | asterwynd-015-retry-budget |
| asterwynd-004-harden-write | asterwynd-017-interactive-fix |
| asterwynd-006-memory-manager | asterwynd-018-warning-passes |
| asterwynd-007-skill-loader | asterwynd-019-runner-timeout |
| asterwynd-008-parent-channel | asterwynd-020-close-clients |
| asterwynd-009-subagent-manager | asterwynd-022-long-term-memory |
| asterwynd-010-agent-loop | asterwynd-022-collaborative-context-audit |
| asterwynd-011-repeater-fix | asterwynd-readme-title |

**B 轨·当前演进（12）**：基于当前 HEAD 真实缺陷/增强构造的任务（面试核心），每个任务 issue.md 不给路径 + 确定性 test_command + base 红/gold 绿红绿可复现：

| 任务 ID | 覆盖点 |
|---------|--------|
| asterwynd-002-sandbox-executor | 沙箱执行器 |
| asterwynd-004-benchmark-cli | benchmark CLI |
| asterwynd-005-bash-workspace | Bash 工作区边界 |
| asterwynd-021-lsp-diagnostics | LSP diagnostics |
| asterwynd-b01-report-family-summary | 结果页 family 摘要（CP-3） |
| asterwynd-b02-running-benchmarks | ListRunningBenchmarks 只读工具装配链（CP-1） |
| asterwynd-b03-awaiting-grill-state | statechart 新态（CP-2） |
| asterwynd-b04-report-track-grouping | 结果页 track 分组 |
| asterwynd-b05-model-name-escaping | SwebenchAdapter model name 转义合成回归 |
| asterwynd-b06-save-memory-project-scope | LT-MEM-1 project scope 隔离 |
| asterwynd-b07-memory-context-source-split | LC-1 记忆注入归属下沉 |
| asterwynd-b08-pipe-to-absolute-shell | BF-1 绝对路径 shell 拦截修复 |

### 11.3 SWE-bench Verified 子集（38）

全部标注 `track=verified`、`dataset_name=princeton-nlp/SWE-bench_Verified`、`scenario=bug-fix`。按 repo 分布（manifest 已核实）：

| repo | 数量 |
|------|------|
| psf/requests | 8 |
| pallets/flask | 1 |
| pytest-dev/pytest | 11 |
| sympy/sympy | 8 |
| mwaskom/seaborn | 2 |
| pylint-dev/pylint | 8 |

difficulty 分布：easy 17 / medium 16 / hard 5。子集从轻量+中等池逐条过滤 KNOWN_BAD 与重实例（不含 django/sphinx），避免测试慢与权重失真。

### 11.4 gate-smoke 任务

| 任务 ID |
|---------|
| gate-smoke-001 |
| gate-smoke-002 |

CI 回归门禁专用（确定性高、IO 近零），不计入 coding 任务。

### 11.5 外部 repo 任务的依赖安装

`_install_repo_deps()`（runner.py:649）使用 SWE-bench 的 `MAP_REPO_VERSION_TO_SPECS` 配置确定 Python 版本和 pip 包。使用 `uv venv` + `uv pip install` 安装依赖。对 `psf/requests` 附加 `pytest-httpbin` + `werkzeug<3.0`。

---

## 12. Verified 子集 build-subset 管线（评测升级）

**文件**：`benchmarks/swebench_subset.py`

### 12.1 配比选择

`build_subset()`（line 73-125）按 repo 配比从候选实例选子集：

```python
# swebench_subset.py:20-29 — 40 条补齐配比（OQ-V1）
SUBSET_TARGETS: dict[str, int] = {
    "psf/requests": 4, "pallets/flask": 6, "pytest-dev/pytest": 8,
    "sympy/sympy": 8, "mwaskom/seaborn": 6, "pylint-dev/pylint": 8,
}
HEAVY_REPOS = {"django/django", "scikit-learn/scikit-learn", ...}  # 重实例不纳入
```

选择逻辑：逐条过滤 KNOWN_BAD 与重实例、排除既有 instance_id（OQ-V3 续跑收敛）、按配比从池中取。`SubsetPlan.summary()`（line 57-63）输出 selected / skipped 明细。

### 12.2 落盘 + 机械校验 + 金补丁自检

- `cmd_build_subset()`（line 415-505）：加载（HF_ENDPOINT 镜像）→ 字段探针 → 排除既有 → 选子集 → 落盘 fixture → `validate_fixture` 机械校验 → 抽样 gold-check
- **L3 金补丁自检**：`gold_check` 对每个 repo 抽样 1 条（`--full-gold-check` 全量），把 fixture 的 gold.patch 应用到 base_commit 并跑 test_command，验证"金补丁能通过测试"——保证 fixture 本身可解（OQ-V2①）
- **manifest 登记**：`update_manifest_verified()`（line 380-412）统计 `track=verified` 的 fixture，写入 `manifest.json` 的 `verified` 摘要段（count / by_repo / by_difficulty，OQ-V6①）

### 12.3 数据不可达降级

数据集访问不可用（如无 huggingface 网络）时，本模块仍提供选择逻辑与校验规则，实际 fixture 生成在数据可访问环境执行；生成后可用 `validate_fixture` 机械校验、`gold_check` 自检（docstring line 5-8）。

---

## 13. CI 回归门禁

**文件**：`.github/workflows/ci.yml`

### 13.1 两个 CI Job

| Job | 名称 | 触发条件 | 说明 |
|-----|------|----------|------|
| `validate` | validate | PR + push to master | pytest + OpenSpec validate + artifact checker |
| `benchmark-gate` | benchmark-gate | PR + push to master | 回归门禁（line 58-59） |

### 13.2 benchmark-gate Job 细节

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
- `--skip-p95`：跳过 p95 延迟检查（gate-smoke 任务集确定性高、IO 近零，p95 受环境因素主导，不作为可靠回归信号）——与 gate.py 的 `check_p95=False` 对应

### 13.3 关闭条件

Benchmark gate **仅在 PR 和 push to master 时触发**（line 3-7）。本地运行时需手动执行 `benchmark-gate` 命令。这不是一个自动化的 pre-commit hook。

---

## 14. 评测运行协议与预算（评测升级）

### 14.1 运行协议文档

`docs/benchmark-run-protocol.md` 是 C3 转正的评测运行协议（跟踪 issue #159）：**只定协议；是否实际跑数、预算大小由使用者按需决定**。协议内容要点：

- **任务集口径**：A 轨 20–24 + B 轨 12–16 + Verified 50 = 82–90（协议目标形态，与当前 72 现状的差异需区分）
- **采样约定**：`--repeat 5`（N≥3 才有 pass^k 意义）、固定 seed 集合 `--seeds 0 1 2 3 4`、`--temperature 0.2`（pass@1 口径）；每轮记录 `(temperature, seed, model version)`，可复现性声明限定 (model version, provider, harness) 内
- **无效轮次不进分母**：`unsupported` / `approval-unavailable` / `docker-unavailable` 不计入 pass@1 与 pass^k 分母
- **自洽性五门禁**（`scripts/self_check.py`）：同模型同 harness 复现 / seed 复现 / 失败归因闭环 / 披露段齐全 / 报告元组完整

### 14.2 预算：可配置、可取消（--budget-cap）

CLI 入口在 `agent/main.py:701`（`benchmark` 命令），预算参数在 line 735-757：

```bash
uv run asterwynd benchmark benchmarks/tasks \
  --repeat 5 --seeds 0 1 2 3 4 --temperature 0.2 \
  --budget-cap 50        # 单轮建议上限；--budget-cap 0 或 --no-cap 取消
```

预算语义（main.py:749-757 + `_run_rounds_with_budget` line 821）：

- **单轮（per-round）口径**：任一轮累计成本超过 cap 即停止剩余轮次（用户决策 2026-08-17）
- **取消**：`--budget-cap 0` / `--no-cap` / 缺省 三者等价取消；负数拒绝
- **超限行为**：停止剩余轮次；当前轮已启动的并发任务自然完成（不 cancel，避免半截 trace）；当前轮结果标 `truncated`（`run.json` 的 `truncated: true`）
- **对统计的影响**：已发生成本照常计入 $/resolved-task 分母；compare 配对剔除 truncated 轮；pass^k 分母不含 truncated 轮（report.py:206-210, 276-283）

### 14.3 结果页披露段（10 项核心 + Verified 子集）

`benchmarks/disclosure.py` 的 `markdown_disclosure_sections()`（line 294-403）渲染披露段：

| # | 披露段 | 数据来源 |
|---|--------|---------|
| 1 | 报告元组 | `report_tuple_rows` line 68-108（model/harness/task_set_hash/grader/成本口径/truncated） |
| 2 | SWE-bench 污染注记 | `SWEBENCH_AUDIT_NOTE` line 30-35（138 实例中 59.4% 有实质缺陷，OpenAI 2026-02 弃用；保留条件域） |
| 3 | 反作弊泄漏披露 | `anti_cheat_rows` line 111-122（A 轨回归基线定位，非公平评测） |
| 4 | reason × fault_owner 交叉表 | `fault_owner_cross_rows` line 125-132 |
| 5 | 成本与定价 | `cost_metrics_rows` line 135-146（$/resolved-task + cache hit rate + 定价表版本 + 仅 LLM token 计费） |
| 6 | 部分成功档（f2p/p2p） | `partial_rows` line 149-162 |
| 7 | 采样参数 | `sampling_rows` line 165-177（temperature/seed/model version） |
| 8 | 小样本声明 | `small_n_note` line 191-202（N=3–5 附声明） |
| 9 | 过程效率 | `process_efficiency_rows` line 222-242（ttf-edit / exploration） |
| 10 | 能力覆盖矩阵 | `coverage_rows` line 245-257（C1 manifest 套件级展示） |
| + | Verified 子集披露 | `verified_rows` line 260-277（count/by_repo/by_difficulty，不占覆盖矩阵） |

每个披露段对旧 run.json 缺失字段渲染 fallback 占位而非抛错（docstring line 9-11 的向后兼容要求）。

---

## 15. 未覆盖或默认关闭的功能总结

| 功能 | 状态 | 位置 | 说明 |
|------|------|------|------|
| `full_trace` | 默认 `False` | `trace_recorder.py:27` | 全量追踪开关，保留为序列化兼容用途，当前不启用 |
| `session_id` / `run_id` | 默认 `None` | `trace_recorder.py:29-30` | 需外部注入，无自动生成 |
| `keep_worktrees` | 默认 `False` | `runner.py:86` | 保留 worktree 用于调试，用完即清理 |
| `clone_cache_dir` | 默认 `None` | `runner.py:87-109` | 共享 clone 缓存加速，需显式传入 |
| `parallel` | 默认 `1`（串行） | `runner.py:85` | 并发数需手动增加 |
| 预算 cap | 默认取消 | `main.py:753-757` | `--budget-cap` 显式设置，0/`--no-cap` 取消 |
| `/review-loop` | 必检门禁 | `AGENTS.md` | 由 OpenSpec artifact checker 强制，非 CI 内置步骤 |
| 语义错误分类 | 不在此处 | `observability.py:5-7` | 需要 LLM judge，与 benchmark judge 一致 |
| Verified 子集扩展 | 40 条补齐未生成 | `swebench_subset.py` | 目标 50，当前 38；剩余 12 条需数据可达环境跑 `build-subset` |
| SWE-bench 多框架支持 | 仅 swebench | `adapters.py` | 其他框架（Harbor 等）需新增适配器 |

---

## 关键文件索引

| 文件 | 内容 |
|------|------|
| `agent/trace_recorder.py` | TraceRecorder — 18 种事件类型的全链轨迹记录器 + TraceRecorderSandboxSink |
| `agent/cost_tracker.py` | CostLedger — 三层成本归因（by_session/by_phase/by_tool）+ 17 模型 cache-aware 四档定价 + compute_cost_cached |
| `agent/observability.py` | ErrorClassifier — 5 类错误分类 + 17 条 error_type 映射 + 三级优先级 |
| `agent/run_identity.py` | new_session_id() / new_run_id() — 12 位 hex 标识生成 |
| `benchmarks/runner.py` | BenchmarkRunner — worktree 隔离 + Docker preflight + local/verify/httpbin 路径 |
| `benchmarks/task_schema.py` | TaskSpec — scenario(5) × difficulty(3) × track(A/B/verified) 任务规格与校验 |
| `benchmarks/task_set.py` | 套件级能力覆盖矩阵 — 7 能力列 + 5 场景列 + per-track 覆盖机械校验 |
| `benchmarks/statistics.py` | bootstrap_ci + pass_at_k + pass_k_success_rate + cost_per_resolved + fault_owner_cross + paired_comparison |
| `benchmarks/report.py` | Markdown/HTML 报告 — layer/task 聚合 + Pass^k + cost + failure attribution + 披露段 |
| `benchmarks/disclosure.py` | 结果页披露 — 报告元组 / 污染注记 / 反作弊 / 交叉表 / 成本 / f2p·p2p / 采样 / 小样本 / 过程效率 / 覆盖矩阵 / Verified |
| `benchmarks/gate.py` | 回归门禁 — success_rate drop > 5pp 或 p95 回归 → FAIL |
| `benchmarks/compare.py` | 跨 Agent 对比 CLI — 多 run 摘要 + 配对比较（per-task delta/差异 CI/win-rate/McNemar） |
| `benchmarks/adapters.py` | VerifierAdapter Protocol + SwebenchAdapter（含 model name 转义修复）+ 注册机制 |
| `benchmarks/swebench_subset.py` | Verified 子集 build-subset 管线 — 配比选择 + 落盘 + validate + gold_check + manifest 登记 |
| `benchmarks/models.py` | TaskResult/RunMetadata/BenchmarkReason(11)/LAYERS(4) + cache token/fault_owner 字段 |
| `benchmarks/task_set.py` | Manifest 覆盖矩阵加载 + validate_coverage |
| `benchmarks/tasks/manifest.json` | 任务集 manifest — coverage 登记 + anti_cheat_disclosure + verified 摘要 |
| `benchmarks/baseline.json` | 当前 baseline（fake agent, gate-smoke, success_rate=1.0） |
| `.github/workflows/ci.yml` | CI pipeline — validate + benchmark-gate 两个 job |
| `benchmarks/tasks/` | 74 个 task.json — 34 本地 + 38 Verified + 2 gate-smoke |
| `docs/benchmark-run-protocol.md` | 评测运行协议（C3 转正）— 采样/预算/对照口径/披露段/self_check 五门禁 |
