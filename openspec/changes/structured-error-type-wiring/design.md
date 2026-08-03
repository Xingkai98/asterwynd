# Design: 结构化 error_type 全链路接入 — 工具错误在产生点打标而非文本猜测

## Context

让 `error_type` 在**错误产生点**被结构化打标，随工具执行结果一路传递到 loop 的 `record_tool_result`，替代「文本前缀猜 status + 文本兜底猜 error_type」。文本分类保留为对未打标工具的**降级路径**。

#78 第一批已交付 `ErrorClassifier` + `record_tool_result(error_type=...)` 字段能力，但数据源未接入。当前错误类型在工具层被转成字符串丢失，loop 只能从文本猜测。

代码证据（`agent/loop.py`）：

| 错误产生点 | 当前行为 | 当前 trace 结果 | 问题 |
|---|---|---|---|
| Bash 超时 | `BashTool.execute` 返回 `SandboxResult.to_json()`（JSON，含 `timed_out: true`） | status="ok"，error_type=None | JSON 结构化信号被丢弃，误判为 ok |
| Bash workspace policy deny | 捕获 `PermissionError`，返回 `f"Error: {e}"` | status="error"，error_type 文本兜底 | error_type 靠文本猜 |
| Bash command guard deny | 返回 `"Error: Command denied by sandbox command guard"` | status="error"，error_type 文本兜底→parameter_error | 语义应是 permission_denied，文本猜错 |
| registry deny | `ToolRegistry.execute` 返回 `"[Permission denied: ...]"` | status="error"，error_type 文本兜底→permission_denied | 文本猜对，但非结构化 |
| registry approval required 兜底 | 返回 `"[Approval required: ...]"` | status="ok" | 前缀不匹配，误判 ok |
| loop 预拒绝 approval denied/unavailable | `"[Approval denied: ...]"` / `"[Approval unavailable: ...]"` | status="ok" | 前缀不匹配，误判 ok |
| MCP 错误 | `McpManager.call_tool` 返回 `"[MCP tool error: server/tool: ExType: msg]"` | status="error"（`[MCP tool error` 前缀），error_type 文本兜底 | ExType 在字符串里，无结构化 |
| 工具抛异常（loop 兜底） | `except Exception as e: result = f"[Error: {e}]"` | status="error"，error_type 文本兜底 | 异常类型转字符串丢失 |
| 并行 gather 异常 | `f"[Error: {r}]"` | 同上 | 同上 |
| LLM 错误 | `_call_llm` 异常向上传播，无 trace 记录 | 无 | 无可观测性 |

## Goals / Non-Goals

**Goals**

1. 关键错误产生点（Bash 超时 / registry deny / approval 预拒绝 / MCP 错误 / LLM 错误）打结构化 `error_type`。
2. `ToolRegistry.execute` 返回「字符串 + 可选错误码」，向后兼容（未打标工具行为不变）。
3. loop 的 `record_tool_result` 用结构化 error_type 判定 status（替代文本前缀猜测），文本兜底降级。
4. 覆盖工具协议层 + 工具层 + AgentLoop 集成 + 回归测试（修 Bash 超时 JSON 误判 ok 缺陷）。

**Non-Goals**

- 不重做 #78 的 ErrorClassifier 分类逻辑（保留文本兜底）。
- 不改变 `Tool.execute` 成功路径返回语义（成功仍返回字符串/ContentBlock）。
- 不引入外部错误追踪后端；只做本地结构化事件。
- 不重做 quality store 的成功/审批语义（`executed=False` 已有）。

## Decisions

### Decision 1: 错误通道 — 结构化 `ToolResult`（非 contextvar 隐藏通道）

在 `agent/tools/base.py` 新增：

```python
@dataclass
class ToolResult:
    text: str | list["ContentBlock"]
    error_type: str | None = None
```

- `Tool.execute` 返回类型由 `str | list[ContentBlock]` **拓宽**为 `str | list[ContentBlock] | ToolResult`（运行时向后兼容，既有工具不改）。
- `ToolRegistry.execute` 返回 `ToolResult`：对普通 `str | list` 返回自动包装为 `ToolResult(text=...)`；对已经是 `ToolResult` 的返回原样透传。
- 拒绝的备选：**纯 contextvar 通道**（仿 `current_tool_call_id`）。理由：错误码是执行结果的组成部分，应当随结果显式传递；contextvar 是隐藏状态，易漏 reset、难单测、对调用方不可见；并行 `gather` 下虽 task-local 安全，但 loop 读取时机必须精确，脆弱。参考实现调研（LangChain ToolMessage）同样采用「结构化结果对象」而非隐藏通道。

**理由**：与 repo 既有 `SandboxResult`（结构化结果 dataclass）模式一致；错误码显式可见；loop 可区分「结构化 signal」与「无 signal 需兜底」。

### Decision 2: 向后兼容 — registry 自动包装 + loop 边界解包

- `ToolRegistry.execute` 对普通返回 `result` 自动 `ToolResult(text=result)`；`ToolResult` 原样透传。因此**未打标的工具行为完全不变**。
- loop 是 `ToolRegistry.execute` 的唯一生产调用方（已验证：`agent/loop.py` 两处，外加测试）。loop 在边界解包：`text = result.text` 用于 hook/message/event；`error_type = result.error_type` 用于 trace。
- `RetryHook.execute_with_retry` 的返回类型同步为 `ToolResult | str | list[ContentBlock]`，成功路径透传 `execute_fn` 的结果，错误路径构造 `ToolResult(text=f"[Error: ...]", error_type=...)`。
- 测试中直接调 `registry.execute` 的 ~11 处需要解包 `.text`（协议变更的测试更新）。

**边界**：`hooks.after_tool_execute(tool_call, result)` 与 `tool_result_message(tool_call.id, result)` 收到的是**解包后的 text**（`str | list`），不是 `ToolResult` 包装——避免 hook 链（如 `TracingHook`）因 `ToolResult` 非 str 而 `.startswith()` 崩溃。error_type 只走 loop 内部传递到 `record_tool_result`。

### Decision 3: 各错误产生点打标清单

| 位置 | 触发 | error_type |
|---|---|---|
| `ToolRegistry.execute` | `decision.type is DENY` | `permission_denied` |
| `ToolRegistry.execute` | `REQUIRE_APPROVAL and not approval_granted`（兜底） | `approval_required` |
| `BashTool.execute` | workspace policy `PermissionError` | `permission_denied` |
| `BashTool.execute` | command guard DENY | `permission_denied` |
| `BashTool.execute` | `sandbox_result.timed_out` | `timeout` |
| `BashTool.execute` | `sandbox_result.oom_killed` | `resource_exhausted` |
| `BashTool.execute` | 后台执行不可用 | `unavailable` |
| `McpTool.execute` / `McpManager.call_tool` | MCP 调用异常（见 Decision 4） | 按异常类型：`timeout`/`network_error`/`mcp_error` |
| loop 预拒绝 | 未知工具 | `unknown_tool` |
| loop 预拒绝 | approval DENIED | `approval_denied` |
| loop 预拒绝 | approval UNAVAILABLE | `approval_unavailable` |
| loop `_execute_single_tool` Bash 异常兜底 | `asyncio.TimeoutError` | `timeout` |
| loop `_execute_single_tool` 其他异常兜底 | 其他异常 | `None`（走文本兜底） |
| `RetryHook.execute_with_retry` | 重试耗尽 / 非可重试异常 | 按异常类型：`timeout`/`network_error`/`None` |
| loop `_call_llm` | LLM 调用异常（见 Decision 5） | `network_timeout`/`model_error` |

打标原则：**只在语义明确的地方打标**；不确定时留 `None` 交给文本兜底，避免虚假打标。

### Decision 4: MCP 错误 — 类型化异常 `McpCallError`

`McpManager.call_tool` 目前捕获所有异常并返回格式化错误字符串（异常类型名已嵌入文本，但非结构化）。改为：

- 新增 `McpCallError(Exception)`（放 `agent/mcp/types.py` 或 `manager.py`），字段 `error_type: str` 和 `text: str`。
- `McpManager.call_tool` 在异常分支**抛出** `McpCallError`：
  - `asyncio.TimeoutError` → `error_type="timeout"`
  - `ConnectionError`/httpx 连接类 → `error_type="network_error"`
  - 其他 → `error_type="mcp_error"`
- `McpTool.execute` 捕获 `McpCallError` → 返回 `ToolResult(text=e.text, error_type=e.error_type)`。
- `manager.call_tool` 的既有错误返回字符串行为**不再存在**（协议变更）；`tests/agent/mcp/test_mcp_manager.py` 中依赖错误字符串的断言更新。

备选（已否决）：在 `McpTool.execute` 里解析错误字符串里的 `ExType` 再映射——脆弱、双重解析；保持 manager 返回字符串则 error_type 无法结构化。

**Open Question Q3**：MCP `isError` 结果（协议层返回 success 但 `result.isError=true`）是否纳入本次范围（要求 `call_tool` 返回类型也改为 `ToolResult`）。

### Decision 5: LLM 错误 — 最小可观测化（record + re-raise）

当前 `_call_llm` 异常直接向上传播，trace 无任何记录。设计：

- `TraceRecorder` 新增 `record_llm_error(error_type, message)`（additive，新 step 类型 `llm_error`）。
- loop 在 `_call_llm` 外层捕获异常：按异常类型分类 → `record_llm_error` → **re-raise**（保持现有控制流不变，CLI/Web 的既有错误处理不受影响）。
- 分类：连接/超时类 → `network_timeout`；API/auth/其他 → `model_error`。
- 这是「在产生点打标」在 LLM 错误上的最小落地，不改变 run 失败语义。

**Open Question Q4**：LLM 异常后是否应重试（复用 RetryHook 的重试逻辑）而不是 re-raise？——当前 `RetryHook` 只用于工具，不用于 LLM。最小范围是 re-raise；重试是额外增强。

### Decision 6: loop status/error_type 判定 — 结构化优先，文本兜底

Phase 3 判定改为：

```python
error_type = result.error_type          # ToolResult 结构化字段
if error_type is not None:
    status = "error"
else:
    status = "error" if _text_prefix_guess(result_text) else "ok"
    error_type = ErrorClassifier().classify(text=result_text).value  # 兜底（可为 UNKNOWN→None）
```

- 结构化 signal 存在时 status 直接用 `error_type` 判定（非 None 即 error），不再看文本。
- 无 signal 时保留现有文本前缀判定 + ErrorClassifier 兜底，未打标工具行为不回归。
- `TracingHook.after_tool_execute` 的 success 判定同样从文本前缀改为结构化 error_type（见 Decision 7 的 Q5）。

### Decision 7: error_type 词汇与 ErrorCategory 映射

新增 error_type 值（`agent/observability.py` `_ERROR_TYPE_TO_CATEGORY` 扩展）：

| error_type | ErrorCategory 映射 | 说明 |
|---|---|---|
| `timeout` | NETWORK_TIMEOUT | 已存在 |
| `network_error` | NETWORK_TIMEOUT | 新增映射 |
| `permission_denied` | PERMISSION_DENIED | 已存在 |
| `approval_required` / `approval_denied` / `approval_unavailable` | PERMISSION_DENIED | 新增映射（审批拒绝属权限语义） |
| `mcp_error` | UNKNOWN | 新增（无细粒度类别，保留 UNKNOWN 告警 record） |
| `resource_exhausted` | UNKNOWN | 新增（OOM） |
| `unavailable` | UNKNOWN | 新增 |
| `unknown_tool` | PARAMETER_ERROR | 新增映射（工具名不存在的参数级错误） |
| `model_error` | MODEL_ERROR | 已存在 |
| `parse_error` | PARAMETER_ERROR | 已存在 |

- **不扩 ErrorCategory 枚举**（保持 observability spec 的四类分类），error_type 是细粒度字符串，ErrorClassifier 映射到粗粒度类别。
- trace 的 `error_type` 字段记录细粒度值，category 由 ErrorClassifier 推导（下游告警策略）。

**Open Question Q1**：是否保持四类 ErrorCategory 不扩（推荐），还是新增类别（如 `approval`、`tool_error`）以反映更细的告警语义？

## Pre-Implementation Review

本 change 非 docs + 有 spec delta，进入 building 前必须完成 issue #95 的独立 subagent 设计追问：`/grill` 产出 `reviews/grill-design.md`（≥3 条 `## Confirmed Decisions` + `## Open Questions`），并停轮把每个 Open Question 抛给用户确认，答复记录进 `## User Confirmation`（grill-confirmation-gate）。全部确认前不写实现代码。

## Open Questions

- **Q1**：ErrorCategory 是否保持四类不扩（推荐），还是新增细粒度类别（approval/tool_error/resource_exhausted）以支撑更细告警？——扩类别会改 observability spec 的四类断言。
- **Q2**：`ToolRegistry.execute` 返回类型改为 `ToolResult` 是**破坏性协议变更**（~11 处测试需解包 `.text`，`RetryHook`、loop 同步改）。确认接受这个变更面，还是更偏好用 `ToolResult` 作为 `str` 的鸭子类型子类减少解包？（推荐前者，显式清晰）
- **Q3**：MCP `isError` 结果（协议层错误）是否纳入本次打标范围（`call_tool` 返回 `ToolResult` 并标记 `mcp_error`），还是仅处理异常路径？
- **Q4**：LLM 错误最小落地是 `record_llm_error` + re-raise；是否需要额外重试增强（复用 RetryHook 重试逻辑）？
- **Q5**：`TracingHook.after_tool_execute`/timeline 的 success 判定是否也从文本前缀改为结构化 error_type（需要把 error_type 传进 hook 签名）？
- **Q6**：approval denied/unavailable 的 status 是否定为 "error"（推荐，未执行成功），还是引入新 status 值（如 "denied"）区分「工具没跑」？

## Risks / Trade-offs

- **[ToolResult 变更面]**: `ToolRegistry.execute` 返回类型变更波及 `RetryHook`、loop、~11 处测试。若漏解包某处，运行时 `AttributeError: 'str' object has no attribute 'text'`。缓解：类型注解 + 全部调用方 audit + 协议层测试覆盖；benchmark gold.patch 只是历史样例不改。
- **[MCP 协议变更]**: `call_tool` 从返回错误字符串改为抛 `McpCallError`，依赖方（`McpTool`、测试）需同步；若其他外部调用方存在会破坏。已 audit：生产调用方仅 `McpTool.execute`。
- **[approval status 语义]**: approval 预拒绝记为 status="error" 会进 quality store（但 `executed=False` 已豁免 success/duration 统计），需确认 `success=status == "ok"` 的 quality 记录不会被污染——当前 loop 已传 `executed=pre_denied_result is None`，approval 预拒绝时 `executed=False`，不污染。风险低。
- **[文本兜底双路径漂移]**: 打标工具用结构化 error_type，未打标工具用文本兜底，两条路径可能在边界 case 上不一致（如某工具返回 `[Error: timeout]` 文本但未打标 → 兜底分类 timeout；另一工具打标 timeout）。这是可接受的降级差异，但文档需说明「结构化优先」原则。
- **[Bash JSON 结果的处理]**: Bash 正常返回 `SandboxResult.to_json()`，status 判定现在对「非错误 JSON」仍应判 ok；只有 `timed_out/oom_killed` 才打标。注意不要把所有非 ok JSON 都当 error。
- **[LLM re-raise 保留]**: `record_llm_error` 后 re-raise 保持 run 失败语义，但 trace 文件若在异常路径未 flush 可能丢失记录。缓解：`run()` 的 finally 已有 cleanup；trace 记录在内存，异常传播到 CLI 后 CLI 写 trace 的路径需验证。

## Testing Strategy

按 AGENTS.md「工具协议或 AgentLoop 变更必须覆盖对应层级测试」：

- **协议层（unit）**：`ToolResult` 构造/包装；`ToolRegistry.execute` 对 str/list/ToolResult 返回的包装与透传；deny/approval 分支打标；返回类型变更后既有 `registry.execute` 调用方解包。
- **工具层（unit）**：Bash timeout/policy deny/guard deny/OOM/background 打标（mock sandbox）；MCP `call_tool` 抛 `McpCallError` + `McpTool` 转 `ToolResult`；RetryHook 错误路径带 error_type。
- **AgentLoop 集成**：
  - Bash 超时（mock sandbox 返回 `timed_out=True`）→ trace status="error"、error_type="timeout"（**回归：修 JSON 误判 ok**）。
  - registry deny → trace error_type="permission_denied"。
  - approval 预拒绝 → trace error_type="approval_denied"，status="error"。
  - MCP 错误 → trace error_type="mcp_error"。
  - 未打标工具错误 → 文本兜底仍生效（不回归）。
- **回归**：既有 `test_tool_result_records_error_type_on_error`、`test_mcp_tool_error_marks_status_error_and_quality_failure` 等继续通过。
- **benchmark smoke**：本 change 为 coding-agent core change（改 `agent/tools/` + `agent/loop.py`），收尾需跑 benchmark smoke 验证。
