# Q09: 可观测性——trace、metrics、成本归属、异常分类

## 讲稿

可观测性解决"怎么知道 agent 在干什么、花多少钱、为什么失败"。Asterwynd 的可观测性分四块：**trace、成本归属、异常分类、Session 看板**（#78）。

**trace**。`TraceRecorder` 记录每步：run started / iteration（assistant 预览 + tool calls + token + model + finish_reason）/ tool call / tool result（耗时 + 状态 + error_type）/ sandbox 事件 / approval 事件。trace 是**过程记录**，带 session_id + run_id，可重放完整时序。

**成本归属**。`CostLedger` 在每轮 LLM 调用后记录 token，按 **session × phase × tool** 三维记账，`compute_cost` 按模型单价算成本，flush 落 JSONL。每个 session 能出"哪个 phase、哪个工具花了多少"的账单。

**异常分类**。`ErrorClassifier` 把错误映射到 `ErrorCategory`（permission_denied / network_timeout / parameter_error / model_error / unknown）。两条路径：**产生点打标**（#89，工具层直接给结构化 error_type）+ **文本兜底分类**（对没打标的错误，按文本模式分类）。trace 里每条 tool result 带 error_type，可聚类告警。

**Session 看板**。Debug 视图展示 session 的 timeline，一眼看到哪些 tool call 耗时最长、哪里失败了。Web 层通过 DebugHook 捕获每轮 LLM 输入输出、工具调用、错误/完成事件，`memory_compaction` 事件带 before/after tokens + 压缩层级。

面试重点：被问"怎么保证改进不导致衰退"时，答案是可观测性 + CI 回归门禁——benchmark 对比基线，P95 延迟/成功率劣化超阈值自动拦截（#78 第二批）。

## 代码走读

### 入口与调用链

```
AgentLoop._run (loop.py) → trace_recorder.record_iteration/record_tool_call/record_tool_result
  → TraceRecorder (agent/trace_recorder.py)
  cost_ledger.record (loop.py:636) → CostLedger (agent/cost_tracker.py)
  错误 → ErrorClassifier.classify (agent/observability.py) → error_type 进 trace
  Web DebugHook (web/debug_hook.py) → 前端 timeline
```

### 关键文件逐段

**`agent/trace_recorder.py` `class TraceRecorder`**
- `record`（51 行）：通用 step 记录。
- `record_run_started`（63 行）：run 开始，带 session_id/run_id。
- `record_iteration`（79 行）：每轮 assistant 预览 + tool calls + token + model + finish_reason。
- `record_tool_call`（100 行）/`record_tool_result`（103 行）：工具调用与结果，`error_type` 参数（121 行）——#89 打标点。
- `record_sandbox_event`（145 行）/`record_approval_request`（155 行）：沙箱与审批事件。

**`agent/observability.py`**
- `ErrorCategory`（20 行）：错误类别枚举。
- `_ERROR_TYPE_TO_CATEGORY`（45 行）：结构化 error_type → 类别映射。
- `_TEXT_PATTERNS`（66 行）：文本模式 → 类别（兜底分类用）。
- `ErrorClassifier.classify`：先看 error_type，没有则按文本分类。

**`agent/cost_tracker.py` `class CostLedger`**
- `record`（54 行）：按 session/phase/tool 累计。
- `compute_cost`（18 行）：模型单价算成本。
- `bill`（81 行）：三维账单。
- `flush`（102 行）：JSONL 落盘，`_flushed_count` 游标幂等。

**`web/debug_hook.py` `DebugHook`**
- 捕获每轮 LLM 输入输出、工具调用、错误/完成事件。
- `memory_compaction` 事件：before/after messages·tokens + 压缩层级元数据。

**`agent/loop.py` 打点处**
- `record_iteration`（644 行）、`cost_ledger.record`（635 行）、`record_tool_call`/`record_tool_result`（717-723、878 行左右）。

### 设计理由

- **trace 与成本分离**：trace 是过程记录（每步耗时/成败/error_type），ledger 是财务记录（session/phase/tool 账单）。分离让两套消费（时序分析 vs 成本账单）互不污染（#78）。
- **error_type 双路径**：产生点打标（数据源接入，可靠）+ 文本兜底（兼容未打标旧路径）。打标优先，兜底补漏（#89）。
- **CI 回归门禁**：可观测性不只是看板，还接 CI——benchmark 对比基线自动拦截劣化，把"怎么保证不衰退"从口头变成门禁（#78 第二批）。
- **Session 看板**：Debug 视图可重放 session 时序，面试能现场展示"这条 tool call 为什么慢、哪里失败"。
