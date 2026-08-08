# Q11: 工具错误处理——error_type 结构化

## 讲稿

工具错误处理解决"错误类型可靠地传给下游"。问题背景（#89）：工具错误从工具层传到 loop 时被转成字符串丢失，loop 只能**从文本猜** status——`result_text.startswith("[Error")` 这种脆弱判断。面试官会问"你怎么知道这个错误是超时还是权限拒绝"。

**核心设计（#89）**：让错误在**产生点打标**结构化 `error_type`，而非事后文本猜测。关键错误点都打标：
- 工具参数解析失败 → `parse_error`
- 未知工具 → `unknown_tool`
- 审批拒绝/不可用 → `approval_denied` / `approval_unavailable`
- 预拒绝 → `pre_denied_error_type`
- Bash 超时 → `timeout`
- registry deny → `permission_denied`

**双路径兜底**。loop 先取产生点的结构化 `error_type`；没有时（未打标的工具）才 fallback 到文本前缀猜测 + `ErrorClassifier` 文本分类。`exception_error_type` 把 LLM 调用异常分类（网络超时 → `network_timeout`，其他 → `model_error`）。

**消费端**。trace 里每条 tool result 带 `error_type`，可观测性据此聚类告警（Q09）。工具结果显示用 `summarize_tool_result` 折叠长结果，保留可展开全文。

面试重点：这是"数据源接入"而非"文本猜测"的工程判断——错误类型在产生点就知道（Bash 超时、registry deny），比 loop 事后猜 status 可靠得多。

## 代码走读

### 入口与调用链

```
工具执行 (loop.py Phase1/Phase2) → 产生点打 error_type
  → record_tool_result(error_type=...) (loop.py:859-870)
    → 无打标 → _text_status_guess + ErrorClassifier.classify (loop.py:92-99)
  → trace (error_type 字段) → 可观测性聚类
```

### 关键文件逐段

**`agent/loop.py` 错误打标与兜底**
- `_text_status_guess`（92-99 行）：**fallback** 文本前缀猜测（`[Error` / `[Permission denied` / `[MCP tool error`）——只在无结构化 error_type 时用。
- `_llm_exception_error_type`（101 行）：LLM 调用异常 → `network_timeout`（Connection/timeout）或 `model_error`（API/auth/unknown）。
- Phase 1 打标点：
  - 参数解析失败 `error_type="parse_error"`（723 行）。
  - 未知工具 `error_type="unknown_tool"`（765 行）。
  - 审批拒绝/不可用 `approval_denied` / `approval_unavailable`（826/833 行）。
  - 预拒绝 `pre_denied_error_type`（842 行）。
- Phase 3 消费（859-870 行）：`error_type = entry.get("error_type")`；无则 fallback `_text_status_guess` + `ErrorClassifier().classify(text)`。

**`agent/observability.py`**
- `ErrorCategory`（20 行）：错误类别枚举。
- `ErrorClassifier.classify`：结构化 error_type → 类别（`_ERROR_TYPE_TO_CATEGORY` 映射）；无则文本模式分类（`_TEXT_PATTERNS`）。
- `exception_error_type`：异常 → error_type（LLM 层）。

**`agent/tool_result_display.py`**
- `summarize_tool_result`（41 行）：折叠长工具结果，保留可展开全文。

### 设计理由

- **产生点打标优先**：错误类型在源头最清楚（Bash 超时是 timeout、registry deny 是 permission_denied），打标后 trace/告警直接消费，无需猜测（#89）。
- **文本猜测作 fallback 而非主路径**：兼容未打标的旧工具（设计 Decision 6），但主路径是结构化打标。
- **结构化 error_type 支撑可观测性**：trace 每条 tool result 带 error_type，可聚类"哪些错误最频繁、按类别告警"（Q09 衔接）。
- **这是"工具协议变更"**：改的是错误传递方式（字符串 → 字符串+错误码），覆盖对应层级测试（AGENTS.md 要求）。
