# Q02: AgentLoop 主循环——一次对话从输入到输出的完整链路

## 讲稿

Asterwynd 的核心是 `AgentLoop`，一个消息驱动的调度器，位于 `agent/loop.py`。核心循环是：`messages → LLM → tool_calls → 执行工具 → 结果回填 → 循环`，直到 LLM 不再产生 tool call 或达到最大迭代次数。

一次 run 的完整链路分四段。**第一，准备**：`run()` 进入 `_run()`，可选恢复 session 快照（多 Agent 协作/断点续跑时用），注入当前 run 的上下文（skill、计划、记忆索引）。**第二，迭代**：每个 iteration 先选工具 schema（工具治理动态选择）、构造带 run 上下文的 messages、调 LLM。LLM 返回的 `usage` 记入 token 计数器和成本账本（cost_ledger）。**第三，工具执行**：若 LLM 产生 tool call，分两阶段——Phase 1 预处理（解析参数、校验、审批），Phase 2 执行（并行执行所有工具调用），再把结果按原序回填。**第四，终止**：LLM 不再产生 tool call 时结束，返回 RunResult；若被 `max_tokens` 截断，会追加"请继续"消息续接而非直接结束。

几个关键设计：`messages` 是唯一主状态，tool-call 消息链必须合法（assistant 的 tool call 必须有对应 tool result）；工具执行是"预处理 + 并行执行"两阶段，审批在预处理做；`max_tokens` 截断有专门的续接逻辑，避免对话中断；整个循环每步都打 trace 和成本记录，支撑可观测性。

## 代码走读

### 入口与调用链

```
run() → _run() → [session resume 可选] → for iteration in range(max_iterations):
    _select_tool_schemas() → _messages_with_run_context() → _call_llm()
    → [无 tool_call → 结束] / [有 tool_call → Phase1 预处理 → Phase2 _execute_tool_calls()]
    → 结果回填 messages → 下一轮
```

### 关键文件逐段

**`agent/loop.py` `class AgentLoop`（112 行起）**
- 构造参数含 `max_iterations`（默认 20）、`llm`、`trace_recorder`、`cost_ledger` 等。
- `run()`（493 行）：公开入口，内部调 `_run()`。
- `_run()`（544 行）：核心循环。

**`_run()` 主循环（605-1010 行）**
- `for iteration in range(start_iteration, self.max_iterations)`（605 行）：迭代边界。
- **session 恢复**（557-584 行）：`resume_snapshot` 非空时恢复 mode、todos、active skills、messages，并追加一条 `[Session resumed...]` 用户消息。这是多 Agent 快照恢复/断点续跑的实现点。
- **背景任务轮询**（608-620 行）：`background_manager.check_completed()` 把完成的后台任务结果追加为 user 消息。
- **工具选择**（622 行）：`_select_tool_schemas(messages)` 做动态工具选择（工具治理）。
- **run 上下文注入**（624 行）：`_messages_with_run_context(messages)` 注入 skill/计划/记忆索引等。
- **LLM 调用**（626-630 行）：`_call_llm(messages, tools)`。
- **token 计数 + 成本**（632-643 行）：`response.usage` 累加到 `token_counters`，并 `cost_ledger.record(model, input/output tokens, session_id, phase, tool_name)`。
- **trace 记录**（644-656 行）：`trace_recorder.record_iteration(...)` 记每轮的 assistant 预览、tool calls、token、model、finish_reason。

**终止逻辑（671-701 行）**
- 无 tool_call 且 `stop_reason == "max_tokens"`（673-677 行）：追加 assistant 消息 + `"Please continue from where you left off."` 用户消息，`continue` 续接——这是踩过的坑：LLM 被 max_tokens 截断时若直接结束会丢内容。
- 无 tool_call 且正常结束（679-701 行）：调 `hooks.on_completion`、发 `done` 事件、把最终 assistant 消息追加进 messages，返回 `RunResult`。

**工具执行两阶段（706-875 行）**
- **Phase 1 预处理**（707-800 行左右）：遍历 `response.tool_calls`，逐个 `_parse_arguments` 解析参数、校验、跑审批。解析失败会记 `error_type="parse_error"`（这是 #89 结构化错误打标的点之一）。
- **Phase 2 执行**（847 行）：`executed = await self._execute_tool_calls(pending)`——并行执行所有待执行工具。
- **结果回填**（858-905 行左右）：按原序把结果构造为 `tool` 消息追加进 messages，满足"assistant tool call 必须对应 tool result"的消息链约束。

**`_execute_tool_calls`（1212 行）**：用 `asyncio.gather` 并行执行多个工具调用，每个 `_run_one` 返回工具结果 + 耗时。

### 设计理由

- **messages 是唯一主状态**：不用状态机，天然匹配 LLM 的输入输出格式，工具调用合法性靠消息链约束（`docs/architecture.md:15-17`）。这也让 session 快照/恢复变得直接——序列化 messages 即可。
- **两阶段工具执行**：审批在预处理阶段做（不执行就不该等执行后才拦），执行阶段并行提升吞吐。审批和高风险工具拦截（#76 沙箱）都在 Phase 1 生效。
- **成本账本集成在循环里**：`cost_ledger.record` 在 LLM 调用后立即执行，而非事后扫描——每轮的真实 token 消耗按 session/phase/tool 归属，这是 #78 可观测性成本归属的基础。
- **max_tokens 续接**：这是真实踩过的坑——截断直接结束会丢后半段推理，追加续接消息是低成本高价值的修复。
