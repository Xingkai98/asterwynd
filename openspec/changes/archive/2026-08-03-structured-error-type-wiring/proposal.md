# Proposal: 结构化 error_type 全链路接入 — 工具错误在产生点打标而非文本猜测

## Change Type

primary: feature
secondary:
  - agent-runtime
  - tool-system
  - observability

## 需求

1. **工具错误在产生点打结构化标记**：Bash 超时、registry deny、approval required/denied、MCP 错误、LLM 错误等关键错误产生点直接携带 `error_type`，而不是把异常类型转成字符串后由 loop 从文本猜测。
2. **Tool 执行结果携带结构化错误码**：设计 Tool 执行结果的传递方式（从纯字符串到「字符串 + 可选错误码」），保持向后兼容——未参与打标的工具仍返回纯字符串/ContentBlock，行为不变。
3. **loop 的 record_tool_result 使用结构化 error_type**：替代文本前缀猜测 status；文本分类降级为对未打标工具的兜底。
4. **覆盖对应层级测试**：工具协议变更 + AgentLoop 集成 + 回归测试（含 Bash 超时 JSON 被误判为 ok 的缺陷）。

## 背景

#78 第一批已交付 `ErrorClassifier` + `TraceRecorder.record_tool_result(error_type=...)` 字段能力，但**数据源未接入**：错误类型在从工具层传到 loop 时被转成字符串丢失，loop 只能从文本猜 status 和 error_type。

代码证据（当前 `agent/loop.py`）：

- `_execute_single_tool`（loop.py:1132-1162）：Bash 异常分支 `except Exception as e: result = f"[Error: {e}]"`——异常类型被转成字符串丢失；非 Bash 走 `RetryHook.execute_with_retry`，同样只返回字符串。
- registry deny 分支（`agent/tools/registry.py:140-145`）：返回 `"[Permission denied: ...]"` 字符串，无结构化 error_type。
- loop Phase 3（loop.py:831-839）：用 `result_text.startswith("[Error"/"[Permission denied"/"[MCP tool error")` 从文本猜 status；`error_type` 用 `ErrorClassifier().classify(text=result_text)` 文本兜底推导。
- `record_tool_result` 已支持 `error_type` 参数（trace_recorder.py:103-129），但调用点传的是文本猜测结果。

**文本猜测的确定性缺陷**（本次要修的 bug）：

- **Bash 超时被误判为 ok**：`BashTool.execute` 返回 `SandboxResult.to_json()`（JSON 字符串，以 `{` 开头），其中 `timed_out=true` 是结构化字段，但 loop 的 status 前缀检查匹配不到 `[Error`/`[Permission denied`/`[MCP tool error` → status="ok"。结构化信号在 JSON 里却完全丢失。
- **approval denied/unavailable 被误判为 ok**：loop Phase 1 预拒绝结果 `"[Approval denied: ...]"` / `"[Approval unavailable: ...]"` 不匹配任何错误前缀 → status="ok"。
- **registry 的 approval required 兜底被误判为 ok**：`"[Approval required: ...]"` 不匹配错误前缀。

## 核心难点

错误发生在具体工具层（Bash 超时/registry deny/MCP 错误/LLM 错误），但 `record_tool_result` 在 loop 统一调用。让 error_type 结构化需要**错误信息从工具层一路传到 loop**——改变 Tool 执行结果的传递方式（从纯字符串到「字符串 + 可选错误码」），涉及 `Tool`/`ToolRegistry` 接口设计，属「工具协议变更」。

## 非目标

- 不重做 #78 已交付的 ErrorClassifier 分类逻辑（保留文本兜底）。
- 不改变 Tool.execute 的成功路径返回语义（成功仍返回字符串/ContentBlock）。
- 不引入外部错误追踪后端；只做本地结构化事件。
- 不重做 quality store 的成功/审批语义（`executed=False` 已有）。

## Impact Analysis

| 影响面 | 说明 |
|---------|------|
| `agent/tools/base.py` | 新增 `ToolResult`（text + 可选 error_type）；`Tool.execute` 返回类型拓宽 |
| `agent/tools/registry.py` | `execute` 返回 `ToolResult`；deny/approval 分支打标 |
| `agent/tools/builtin/bash.py` | timeout/permission/guard/oom/background 分支打标 |
| `agent/mcp/manager.py` + `agent/mcp/tools.py` | MCP 调用错误分类打标（`McpCallError` 或等价） |
| `agent/hooks/builtin/retry.py` | `execute_with_retry` 错误路径携带 error_type |
| `agent/loop.py` | `_execute_single_tool`/`_execute_tool_calls` 返回并传递 `ToolResult`；Phase 3 status/error_type 判定改用结构化信号 + 文本兜底；预拒绝分支带 error_type；LLM 错误记录 |
| `agent/hooks/builtin/tracing.py` | `after_tool_execute` 改用结构化 error_type 判定 success（消除文本前缀猜测） |
| `agent/trace_recorder.py` | 可选：新增 `record_llm_error`（additive） |
| `agent/observability.py` | `_ERROR_TYPE_TO_CATEGORY` 扩展新 error_type 映射 |
| 测试 | 协议层（ToolResult/registry）、工具层（Bash/MCP/retry）、AgentLoop 集成、回归 |
| `openspec/specs/tool-system`、`openspec/specs/observability` | spec delta |

## Reference Implementation Research

- status: enabled
- reason: 工具错误结构化是全链路可观测性的核心能力，应参考主流 agent 框架与 LLM 观测工具的既有实现。
- research questions:
  - LangChain/LangGraph 如何处理工具执行错误的结构化传递？
  - OpenTelemetry GenAI / Langfuse 如何约定错误属性（结构化优先、文本兜底）？
  - 主流 coding agent（Claude Code 等）如何区分 permission_denied / timeout / mcp_error 等错误类别？
- findings:
  - **LangChain/LangGraph**：行业主流做法是把工具错误**转换为结构化 ToolMessage（status="error"）**而非抛出异常——工具执行失败在工具节点内捕获，转成带 `status="error"` 的消息返回给 loop，让 LLM 下一轮自纠。`ToolErrorMiddleware` 把选定异常转为 error ToolMessage；`handle_tool_error` 标志控制是否捕获。这验证了「在产生点把错误转成结构化结果对象」的方向，与我们拟议的 `ToolResult(text, error_type)` 一致。
  - **OpenTelemetry GenAI / Langfuse**：语义约定强调**结构化属性在源点捕获**（`gen_ai.operation.name`、`gen_ai.tool.name`、token/finish_reason 等），错误通过 `error_type`/`finish_reason` 等结构化字段表达；文本分类仅是兜底。Langfuse 用优先级注册表把通用 span 映射为领域类型（LLM→GENERATION、TOOL→TOOL），与我们 `ErrorClassifier` 的「结构化优先、文本兜底」设计一致。
  - **Claude Code / coding agent 生态**：结构化错误码是社区正在形成的规范——claude-sdk-rs 定义 14 类错误枚举（C003 PermissionDenied、C004 McpError、C007 Timeout、C013 RateLimitExceeded）；社区提案给失败结果加 `{type, message, file, line, suggestion}` 结构化对象，使父 agent 能按错误类型分支处理（装依赖 / 重跑测试 / 升级权限）。permission_denied 和 timeout 是最常见、最需要结构化区分的错误类别，与 issue 89 的打标清单一致。
- design impact:
  - 通道采用 **`ToolResult` 结构化结果对象**（LangChain ToolMessage 同构，而非 contextvar 隐藏通道）——错误码随结果显式传递，loop 无需猜测。
  - error_type 词汇对齐行业常见类别：`permission_denied`/`timeout`/`mcp_error`/`approval_*`/`network_error` 等（对齐 claude-sdk-rs 错误枚举）。
  - 保留文本兜底为**降级路径**（OTel GenAI 语义约定同样以结构化为主、文本兜底）。
  - 本地参考仓库不可用（`.dev/reference-repos.txt` 不存在，checker 不读取该文件）：以上结论基于公开文档调研，设计文档记录不可用事实与替代依据。

## Dependencies

- 依赖 #78（observability-deepening，已合入）：`record_tool_result(error_type=...)` 字段能力 + ErrorClassifier。
- 依赖 #77（tool-governance-deepening，已合入）：quality store 消费 status（`success=status == "ok"`）；本 change 修正 status 判定后，quality 语义自动受益。
- 与 #67（AI 标准化审阅）无关；不触碰 workflow 阶段状态机。

## 验收

- 关键错误产生点（Bash 超时 / registry deny / approval 预拒绝 / MCP 错误）的 trace `tool_result` 记录结构化 `error_type`，status 不再依赖文本前缀猜测。
- Bash 超时（JSON `timed_out=true`）在 trace 中 status="error" 且 error_type="timeout"（修复误判 ok 的缺陷）。
- 未参与打标的工具仍走文本兜底分类，既有行为不回归。
- 覆盖工具协议层 + 工具层 + AgentLoop 集成 + 回归测试。
