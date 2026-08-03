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

### Decision 2: 向后兼容 — registry 自动包装 + loop 边界解包（grill Q7 修正）

- `ToolRegistry.execute` 对普通返回 `result` 自动 `ToolResult(text=result)`；`ToolResult` 原样透传。因此**未打标的工具行为完全不变**。
- `RetryHook.execute_with_retry` 的返回类型同步为 `ToolResult | str | list[ContentBlock]`，成功路径透传 `execute_fn` 的结果，错误路径构造 `ToolResult(text=f"[Error: ...]", error_type=...)`。
- 测试中直接调 `registry.execute` 的 ~11 处需要解包 `.text`（协议变更的测试更新）。

**解包边界（grill Q7 修正，消除原设计矛盾）**：`_execute_single_tool` 在 execute/retry 返回后**立即解包**为 `(text, error_type, duration_ms)` 三元组并存入 entry 字段——**不把 `ToolResult` 传回 loop 调用方**：

```python
# _execute_single_tool 内部
result = await self.tool_registry.execute(...)   # 或 retry 结果
text = result.text if isinstance(result, ToolResult) else result
error_type = result.error_type if isinstance(result, ToolResult) else None
await self.hooks.after_tool_execute(observed_tool_call, text)   # hook 收到解包 text
return text, error_type, duration_ms
```

- `hooks.after_tool_execute(tool_call, result)` 收到**解包后的 text**（`str | list`）——避免 `TracingHook` 因 `ToolResult` 非 str 而 `isinstance(result, str)` False 全判 success（tracing.py:42 回归）。
- Phase 3 消费者（`extract_text`/`summarize_tool_result`/`record_tool_result`/`tool_result_message`/`ToolCallMade`）也只接触 text，`error_type` 通过 entry 的独立字段传到 `record_tool_result`——不泄漏 ToolResult 对象，杜绝 TypeError 与 trace JSON 序列化失败。
- **预拒绝条目**（unknown tool / approval denied/unavailable）同样带 error_type 字段：pre_denied 分支在构造 entry 时把 `error_type` 一并存入（approval_denied/unavailable/unknown_tool），Phase 3 读取统一。
- **gather 异常解包**（loop.py:1221-1225）同样产出 `(text, error_type)`，error_type 按异常类型（`asyncio.TimeoutError` → `timeout`，其他留 None）。
- 补一个协议级测试：**「ToolResult 不得泄漏到 hook/record_tool_result」**——hook 收到 str/list，record_tool_result 收到 error_type 独立参数。

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

### Decision 4: MCP 错误 — 类型化异常 `McpCallError`（grill 修正）

`McpManager.call_tool` 目前捕获所有异常并返回格式化错误字符串（异常类型名已嵌入文本，但非结构化）。改为：

- 新增 `McpCallError(Exception)`（放 `agent/mcp/types.py` 或 `manager.py`），字段 `error_type: str` 和 `text: str`，**定义 `__str__` 返回 `text`**（grill R4：`RetryHook._is_retryable` 依赖 `str(e)` 含 timeout/connection 等 token；同时 `__str__` 保证 repr/log 可读）。
- `McpManager.call_tool` 在异常分支**抛出** `McpCallError`：
  - `asyncio.TimeoutError` → `error_type="timeout"`
  - `ConnectionError`/httpx 连接类 → `error_type="network_error"`
  - 其他 → `error_type="mcp_error"`
  - **`_record_call(server_name, False)` 在 raise 之前执行**（grill R2：health 语义不回归）。
- `McpTool.execute` 捕获 `McpCallError` → 返回 `ToolResult(text=e.text, error_type=e.error_type)`。
- `manager.call_tool` 的既有错误返回字符串行为**不再存在**（协议变更）；`tests/agent/mcp/test_mcp_manager.py` **与 `test_mcp_health.py`**（grill R2：`test_failure_rate_from_call_outcomes`/`test_auto_recovers_when_window_slides` 在无 try/except 循环里调 `call_tool`，改抛后崩溃）中依赖错误字符串/抛异常的断言更新。
- **isError 结果纳入范围（grill Q3 推荐）**：`call_tool` 对 `result.isError=true` 的结果返回 `ToolResult(text=_format_call_tool_result(...), error_type="mcp_error")`；`McpTool.execute` 原样透传。这要求 `call_tool` 返回类型统一为 `ToolResult | str`（isError 分支返回 ToolResult，正常分支返回 str 由 McpTool 包装）。

备选（已否决）：在 `McpTool.execute` 里解析错误字符串里的 `ExType` 再映射——脆弱、双重解析；保持 manager 返回字符串则 error_type 无法结构化。

### Decision 5: LLM 错误 — 最小可观测化（record + re-raise）

当前 `_call_llm` 异常直接向上传播，trace 无任何记录。设计：

- `TraceRecorder` 新增 `record_llm_error(error_type, message)`（additive，新 step 类型 `llm_error`）。
- loop 在 `_call_llm` 外层捕获异常：按异常类型分类 → `record_llm_error` → **re-raise**（保持现有控制流不变，CLI/Web 的既有错误处理不受影响）。
- 分类：连接/超时类 → `network_timeout`；API/auth/其他 → `model_error`。
- 这是「在产生点打标」在 LLM 错误上的最小落地，不改变 run 失败语义。
- **re-raise 语义保留（grill Q4 推荐）**：不引入 LLM 重试。RetryHook 只用于工具；重试会改变 run 失败语义且是额外增强，留作后续 change。
- **CLI trace 可见性确认（grill R5）**：benchmark（runner.py finally:468）与 web（session.py:371）在异常路径保 trace；CLI 若无 trace 写路径则 llm_error 仅 benchmark/程序化可见——实现时确认，无则接受并记录。

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
- **`TracingHook.after_tool_execute` 的 success 判定需要 Hook Protocol 变更（grill Q5 关键发现）**：纯文本前缀补全**无法**修复 Bash 超时误判——Bash 正常 JSON 与 timed_out JSON 的文本相同（都是 `to_json()` 结果），只有 error_type 不同，hook 只拿 text 无法区分。方案：`HookManager.after_tool_execute` 签名增加 `error_type: str | None = None` 参数（manager.py:20,46-48 同步），loop 在解包后把 error_type 传给 hook；`TracingHook` 用 `error_type is not None` 判失败、无 signal 时回退现有文本前缀判定。web timeline（web/session.py:32-72）依赖 `TracingHook.success`，随 hook 修正自动受益。

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
- **词汇混用明确接受（grill Q8 修正）**：结构化 error_type（`timeout`/`permission_denied`/`approval_denied` 等细粒度值）与文本兜底返回的 `category.value`（`network_timeout`/`parameter_error` 等粗粒度值）**不同词汇**。接受混用——trace 字段本就是「结构化优先、兜底为粗粒度 category.value」，下游用 `ErrorClassifier.classify(error_type=...)` 统一映射。但 **spec delta 措辞必须与实现一致**：observability delta「未打标工具仍走文本兜底」场景应写分类为 `"network_timeout"` 而非 `"timeout"`（修正原场景）。

**Open Question Q1**：是否保持四类 ErrorCategory 不扩（推荐），还是新增类别（如 `approval`、`tool_error`）以反映更细的告警语义？

## Pre-Implementation Review

本 change 非 docs + 有 spec delta，进入 building 前必须完成 issue #95 的独立 subagent 设计追问：`/grill` 产出 `reviews/grill-design.md`（≥3 条 `## Confirmed Decisions` + `## Open Questions`），并停轮把每个 Open Question 抛给用户确认，答复记录进 `## User Confirmation`（grill-confirmation-gate）。全部确认前不写实现代码。

## Open Questions

> 由独立 grill subagent（run grill-run-structured-error-type-wiring-2026-08-03-001）挑战产出。全部确认后进入 building（grill-confirmation-gate）。推荐答案已随题给出，用户可快速确认或另选。

- **Q1**：ErrorCategory 是否保持四类不扩（permission_denied/network_timeout/model_error/parameter_error）？推荐：保持不扩——observability spec「Error Auto-Classification」场景断言四类分类；error_type 细粒度字符串 + 映射表已能表达细粒度。
- **Q2**：`ToolRegistry.execute` 返回类型改为 `ToolResult`（非 str 子类）是破坏性协议变更，确认接受？推荐：接受显式 dataclass——str 子类继承一堆不需要的 str 方法、掩盖结构边界；显式 `.text` 让未解包处立刻 TypeError。必须全量 audit 调用方。
- **Q3**：MCP `isError` 结果（协议层 success 但 isError=true）是否纳入打标范围？推荐：纳入——否则 isError 错误仍走文本兜底，与「在产生点打标」目标不符；`call_tool` 返回类型统一为 `ToolResult | str`。
- **Q4**：LLM 错误是 re-raise（最小）还是加重试？推荐：re-raise——RetryHook 只用于工具；重试改 run 失败语义，留作后续。
- **Q5**：`TracingHook`/timeline 的 success 判定需要改 Hook Protocol 签名（`after_tool_execute` 加 `error_type` 参数）？推荐：改——纯文本补全无法修复 Bash 超时误判（正常 JSON 与 timed_out JSON 文本相同，只有 error_type 不同）；web timeline 依赖 `TracingHook.success`，随 hook 修正自动受益。
- **Q6**：approval denied/unavailable 的 status 是否定为 "error"？推荐："error"——`executed=False` 已承担「工具没跑」的区分，引入新 status 值会改 trace schema 消费方与 quality 判定。
- **Q7**：解包边界方案（`_execute_single_tool` 立即解包为 `(text, error_type, duration_ms)`，hook 收 text，error_type 随 entry 字段到 Phase 3；预拒绝/gather 异常同样带 error_type 字段）？推荐：采纳——消除原设计的 hook/Phase 3 泄漏矛盾，补「ToolResult 不得泄漏」协议测试。
- **Q8**：trace 的 error_type 词汇是否接受混用（结构化细粒度值 vs 文本兜底 category.value）？推荐：接受混用但修正 spec delta 措辞为 `network_timeout`（与实现一致），明确「结构化优先、兜底为粗粒度 category.value」。

## Risks / Trade-offs

- **[ToolResult 变更面]**: `ToolRegistry.execute` 返回类型变更波及 `RetryHook`、loop、~11 处测试。若漏解包某处，运行时 `AttributeError: 'str' object has no attribute 'text'`。缓解：类型注解 + 全部调用方 audit + 协议层测试覆盖；benchmark gold.patch 只是历史样例不改。
- **[MCP 协议变更]**: `call_tool` 从返回错误字符串改为抛 `McpCallError`，依赖方（`McpTool`、测试）需同步；若其他外部调用方存在会破坏。已 audit：生产调用方仅 `McpTool.execute`。
- **[approval status 语义]**: approval 预拒绝记为 status="error" 会进 quality store（但 `executed=False` 已豁免 success/duration 统计），需确认 `success=status == "ok"` 的 quality 记录不会被污染——当前 loop 已传 `executed=pre_denied_result is None`，approval 预拒绝时 `executed=False`，不污染。风险低。
- **[文本兜底双路径漂移]**: 打标工具用结构化 error_type，未打标工具用文本兜底，两条路径可能在边界 case 上不一致（如某工具返回 `[Error: timeout]` 文本但未打标 → 兜底分类 network_timeout；另一工具打标 timeout）。这是可接受的降级差异，但文档需说明「结构化优先、兜底为粗粒度 category.value」。
- **[Bash JSON 结果的处理]**: Bash 正常返回 `SandboxResult.to_json()`，status 判定现在对「非错误 JSON」仍应判 ok；只有 `timed_out/oom_killed` 才打标。注意不要把所有非 ok JSON 都当 error。
- **[LLM re-raise 保留]**: `record_llm_error` 后 re-raise 保持 run 失败语义。benchmark（runner.py finally:468）与 web（session.py:371）在异常路径保 trace；CLI 若无 trace 写路径则 llm_error 仅 benchmark/程序化可见（接受并记录）。
- **[test_mcp_health.py 破坏面]**: `_FakeSession.call_tool` 抛 RuntimeError（test_mcp_health.py:34-37）；`test_failure_rate_from_call_outcomes`（:60-69）与 `test_auto_recovers_when_window_slides`（:72-87）在无 try/except 循环里调 `call_tool`，改抛 McpCallError 后崩溃。缓解：任务登记更新；`_record_call(server_name, False)` 在 raise 前仍执行（health 语义不回归）。
- **[test_retry_budget.py 破坏面]**: test_non_retryable_error_not_retried（:56 `result.startswith("[Error")`）与 test_retry_exhausted_returns_error（:77 `"Error after" in result`）在 RetryHook 错误路径改返 ToolResult 后失败；loop.py:1156 `isinstance(result, str)` retry-exhausted 日志判定失效。缓解：任务 2.5 更新 + loop.py:1156 改判。
- **[McpCallError.__str__]**: RetryHook `_is_retryable` 依赖 `str(e)` 含 timeout/connection token；McpCallError 须定义 `__str__` 返回 text。当前 MCP 错误本就不经 RetryHook（McpTool 捕获），需确认这是预期（是）。

## Testing Strategy

按 AGENTS.md「工具协议或 AgentLoop 变更必须覆盖对应层级测试」：

- **协议层（unit）**：`ToolResult` 构造/包装；`ToolRegistry.execute` 对 str/list/ToolResult 返回的包装与透传；deny/approval 分支打标；返回类型变更后既有 `registry.execute` 调用方解包。
- **协议级泄漏测试（grill R1 补）**：**「ToolResult 不得泄漏到 hook/record_tool_result」**——hook 收到 str/list；record_tool_result 收到 error_type 独立参数。
- **工具层（unit）**：Bash timeout/policy deny/guard deny/OOM/background 打标（mock sandbox）；MCP `call_tool` 抛 `McpCallError`（含 `__str__` 断言）+ `McpTool` 转 `ToolResult` + isError 分支返回 `ToolResult(mcp_error)`；RetryHook 错误路径带 error_type。
- **破坏面回归（grill R2/R3 补）**：`test_mcp_health.py` 两处循环调用改接 McpCallError；`test_retry_budget.py` 两处断言改接 ToolResult；loop.py:1156 retry-exhausted 日志改判。
- **AgentLoop 集成**：
  - Bash 超时（mock sandbox 返回 `timed_out=True`）→ trace status="error"、error_type="timeout"（**回归：修 JSON 误判 ok**）。
  - registry deny → trace error_type="permission_denied"。
  - approval 预拒绝 → trace error_type="approval_denied"，status="error"。
  - MCP 错误 → trace error_type="mcp_error"。
  - 未打标工具错误 → 文本兜底仍生效（不回归）。
- **回归**：既有 `test_tool_result_records_error_type_on_error`、`test_mcp_tool_error_marks_status_error_and_quality_failure` 等继续通过。
- **benchmark smoke**：本 change 为 coding-agent core change（改 `agent/tools/` + `agent/loop.py`），收尾需跑 benchmark smoke 验证。
