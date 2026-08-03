# Q07: LLM Provider——抽象、错误、成本

## 讲稿

LLM 层解决三个问题：**抽象、错误处理、成本归属**。

**抽象**。`BaseLLM` 定义统一协议（chat / stream_chat），返回统一的 `LLMResponse`（content、tool_calls、stop_reason、usage）。AnthropicLLM 和 OpenAI 兼容 provider 实现协议，AgentLoop 只依赖 `BaseLLM` 接口，不感知具体厂商。这层还处理 provider 差异——比如 Anthropic 连续 tool result 要合并为一个 user 消息的多个 `tool_result` block，assistant 的 text block 必须在 tool_use 前；provider 专有字段（如 DeepSeek 的 `reasoning_content`）要保守保留避免后续请求丢字段。

**错误处理**（#89）。工具层错误在**产生点打标**结构化 `error_type`，而非 loop 事后从文本猜。`ErrorClassifier` 对未打标的错误做兜底分类，映射到 `ErrorCategory`（timeout/permission_denied/parse_error 等）。trace 里每条 tool result 带 `error_type`，可观测性据此聚类告警。

**成本归属**（#78）。`CostLedger` 在每轮 LLM 调用后记录 token，按 **session × phase × tool** 三维记账。`compute_cost` 按模型单价算成本，`flush` 落 JSONL 文件供跨 session 历史统计。这跟 trace 分离——trace 是过程记录，ledger 是财务记录。

## 代码走读

### 入口与调用链

```
AgentLoop._call_llm (loop.py:1026) → BaseLLM.chat/stream_chat
  → AnthropicLLM/OpenAI-compatible 实现 → LLMResponse
  → cost_ledger.record (loop.py:636) → CostLedger → flush JSONL
```

### 关键文件逐段

**`agent/llm.py`**
- `BaseLLM`：抽象基类，定义 `chat`/`stream_chat` 协议 + `LLMResponse`/`Usage`/`ToolCallDelta` 数据结构。
- `LLMResponse`：统一返回（content / tool_calls / stop_reason / usage），loop 不感知厂商细节。

**`agent/anthropic_llm.py` `class AnthropicLLM`**
- `chat`（56 行）/`stream_chat`（218 行）：实现协议。
- `_build_payload`（99 行）：构造 Anthropic 请求体。
- `_apply_cache_plan`（167 行）：把 context 层的 cacheable 块打 `cache_control` breakpoint（与 Q04 稳定前缀缓存衔接）。
- `_build_response`（460 行）：流式累积 block → LLMResponse。
- 关键处理（`docs/architecture.md:121-126`）：
  - 连续 tool result 合并为一个 user 消息的多个 `tool_result` block。
  - assistant 消息 text block 在 tool_use block 前。
  - provider 专有字段保守保留（`_strip_surrogates` 处理代理/特殊字符）。

**`agent/openai_llm.py`** — OpenAI 兼容 provider，同样实现 `BaseLLM` 协议。

**`agent/loop.py` LLM 调用与打点（626-656 行）**
- `response.usage` → `token_counters`（632 行）。
- `cost_ledger.record(model, input/output tokens, session_id, phase, tool_name)`（635-643 行）。
- `trace_recorder.record_iteration(...)`（644 行）。

**`agent/cost_tracker.py` `class CostLedger`**
- `record`（54 行）：按 session/phase/tool 累计。
- `compute_cost`（18 行）：按模型单价算成本。
- `bill`（81 行）：三维账单查询。
- `flush`（102 行）：落 JSONL，`_flushed_count` 游标保证幂等（多 loop 共享 ledger 各自 flush 不重复）。

**错误分类（#89）**
- `agent/loop.py` 工具执行 error 分支（约 843-853 行）：有结构化 error_type 直接用；否则 `ErrorClassifier().classify(text)` 兜底。
- `ErrorCategory` / `ErrorClassifier`：把错误文本映射到类别（timeout/permission_denied/parse_error/llm 等），供 trace 聚类。

### 设计理由

- **协议抽象 + provider 差异隔离**：loop 不感知厂商，新 provider 只需实现 `BaseLLM`；provider 专有差异（tool_result 合并、字段透传）封装在 provider 内部。
- **成本与 trace 分离**：ledger 是财务记录（session/phase/tool 账单），trace 是过程记录（每步耗时/成败）；分开设计让成本可出账单、trace 可做时序分析，互不污染（#78）。
- **错误在产生点打标**（#89）：数据源接入而非文本猜测——错误类型在工具层就知道（Bash 超时 = timeout、registry deny = permission_denied），打标后 trace/告警直接用，比 loop 事后猜 status 可靠。
- **多 provider 可讲**：Anthropic + OpenAI 兼容（DeepSeek 走兼容路径），面试可讲"我处理过 provider 差异"。
