# Grill: structured-error-type-wiring 设计追问

## Reviewer

- run id: grill-run-structured-error-type-wiring-2026-08-03-001
- 时间: 2026-08-03
- 角色: 独立零记忆设计评审（issue #95 机械门禁），挑战而非确认设计

## Confirmed Decisions

- **决策**: 采用结构化 `ToolResult` 结果对象（`text: str | list[ContentBlock]` + `error_type: str | None = None`）作为错误传递通道，否决 contextvar 隐藏通道。理由: 与 repo 既有 `SandboxResult` 结构化结果 dataclass 模式一致（agent/tools/sandbox/base.py:99-118）；`ToolRegistry.execute` 是天然汇聚点（agent/tools/registry.py:137-151），且 grep 全仓验证 loop.py:1142/1152 是唯一生产调用方（web/subagent/benchmark 无直接调用）；contextvar 有读取时机脆弱、易漏 reset、难单测的缺点；LangChain ToolMessage 同为「结构化结果对象」方向。来源: grill-run-structured-error-type-wiring-2026-08-03-001
- **决策**: registry 对 `str | list` 自动包装为 `ToolResult(text=...)`、对已打标 ToolResult 原样透传，未打标工具行为完全不变，文本兜底保留为降级路径。理由: 验证了 tests/agent/test_loop.py:2151（工具返回 `[Permission denied: ...]` 文本）与 :2193（工具返回 `[MCP tool error: ...]` 文本）两个回归测试完全依赖文本兜底——未打标工具返回文本错误 → Phase 3 classify 出 error_type；设计保留兜底则两测试继续通过，向后兼容声明成立。来源: grill-run-structured-error-type-wiring-2026-08-03-001
- **决策**: approval 预拒绝 / registry deny 的 status 定为 "error"，并确认 `executed=False` 豁免确实覆盖 quality store，不污染统计。理由: loop.py:879 已传 `executed=entry.get("pre_denied_result") is None`——approval 预拒绝时 pre_denied_result 非 None → executed=False；agent/tools/governance/quality.py:80 `score()` 只用 executed=True 的记录算 success/duration，approval-denied 记录被排除。当前 status="ok"（success=True）也因 executed=False 不参与统计，改为 "error" 后仍不参与，quality 语义不变。来源: grill-run-structured-error-type-wiring-2026-08-03-001
- **决策**: Bash 超时在产生点（`BashTool.execute`）按 `SandboxResult.timed_out` 打标 `timeout`，修复 loop 从 JSON 文本误判 ok 的缺陷；同时只对 timed_out/oom_killed 打标，不把所有非 ok JSON 当 error。理由: 实证当前 loop.py:831-839 的 status 前缀检查只匹配 `[Error`/`Error`/`[Permission denied`/`[MCP tool error`，Bash 返回 `SandboxResult.to_json()`（bash.py:89，以 `{` 开头）无法命中 → status="ok"，结构化 `timed_out=true` 字段在 JSON 里完全丢失；在 BashTool.execute 检查结构化字段是唯一可靠来源。设计风险节「注意不要把所有非 ok JSON 都当 error」判断正确。来源: grill-run-structured-error-type-wiring-2026-08-03-001
- **决策**: MCP 错误用类型化异常 `McpCallError(error_type, text)` 替代错误字符串返回，`McpTool.execute` 捕获转 ToolResult；isError（协议层 success 但 isError=true）与异常路径分开处理。理由: manager.py:306-308 当前把 `type(exc).__name__` 嵌入文本，非结构化；`_format_call_tool_result` 对 isError 返回 `[MCP tool error: ...]` 字符串（manager.py:429-430），是独立的第二错误源，Q3 框架正确。但破坏面 audit 不完整——test_mcp_health.py 被遗漏（见风险 R2）。来源: grill-run-structured-error-type-wiring-2026-08-03-001
- **决策**: LLM 错误最小落地为 `record_llm_error` + re-raise，不改变 run 失败语义。理由: 当前 `_call_llm` 异常直接上抛（loop.py:604 调用点），trace 无任何记录；在调用点外层 catch → record → re-raise 保持 CLI/Web 既有错误处理——web/session.py:371 catch 后发 error 事件，benchmarks/runner.py:448 catch + finally:468 仍写 trace 文件，故异常路径 trace 不丢失。来源: grill-run-structured-error-type-wiring-2026-08-03-001

## Open Questions

- **Q1**: ErrorCategory 是否保持四类不扩（permission_denied/network_timeout/model_error/parameter_error），还是新增细粒度类别（approval/tool_error/resource_exhausted）以支撑更细告警？推荐：保持四类不扩——observability spec「Error Auto-Classification」场景断言四类分类（openspec/specs/observability/spec.md），扩类会改 spec 断言且扩大变更面；error_type 细粒度字符串 + `_ERROR_TYPE_TO_CATEGORY` 映射已能表达细粒度。
- **Q2**: `ToolRegistry.execute` 返回类型改为 `ToolResult` 是破坏性协议变更（~11 处 registry.execute 测试 + RetryHook + loop 需解包 `.text`；另有 test_retry_budget.py 两处、test_mcp_health.py 多处被遗漏）。确认接受显式破坏性变更，还是偏好 `ToolResult` 作为 str 的鸭子类型子类减少解包？推荐：接受显式 dataclass（非 str 子类）——str 子类会继承一堆不需要的 str 方法、掩盖结构边界；显式 `.text` 让未解包处立刻 TypeError 而不是静默。但必须全量 audit 调用方（见 Q7）。
- **Q3**: MCP `isError` 结果（协议层返回 success 但 `result.isError=true`）是否纳入本次打标范围（`call_tool` 返回 ToolResult 并标记 `mcp_error`），还是仅处理异常路径？推荐：纳入——否则 isError 的 MCP 错误仍走文本兜底，与本 change「在产生点打标」目标不一致；但需把 `call_tool` 返回类型改为 `ToolResult`，`McpTool.execute` 与测试同步。
- **Q4**: LLM 错误最小落地是 `record_llm_error` + re-raise；是否需要额外重试增强（复用 RetryHook）？推荐：re-raise（最小范围）。RetryHook 只用于工具不用于 LLM，重试是额外增强且会改变 run 失败语义，留作后续 change。
- **Q5**: `TracingHook.after_tool_execute`/timeline 的 success 判定如何改？关键发现：**纯文本前缀补全无法修复 Bash 超时误判**——Bash 正常 JSON 与 timed_out JSON 的文本相同（都是 `to_json()` 结果），只有 error_type 不同；`TracingHook`（agent/hooks/builtin/tracing.py:42-50）只能拿到结果文本时无法区分。要正确判定必须让 hook 拿到结构化 error_type（改 Hook Protocol 签名 manager.py:20,46-48）或 loop 传 ToolResult 给 hook。web timeline（web/session.py:32-72）依赖 `TracingHook.success`，当前 approval-denied/`[MCP tool error`/`[Approval required` 均被误判为 success。推荐：改 hook 签名传 error_type（或传 ToolResult），并在任务中登记 Hook Protocol 变更。
- **Q6**: approval denied/unavailable 的 status 是否定为 "error"（推荐，未执行成功），还是引入新 status 值（如 "denied"）区分「工具没跑」？推荐："error"——引入新 status 会改 trace schema 消费方与 quality 判定（`success=status == "ok"`），扩大变更面；`executed=False` 已承担「没跑」的区分。
- **Q7**: ToolResult 解包边界的具体方案未定，且 Decision 2 与 tasks 3.1/3.2 存在矛盾。Decision 2 声称「hooks.after_tool_execute 收到解包后 text」，但 hook 调用发生在 `_execute_single_tool` 内部（loop.py:1161），早于 Phase 3；tasks 3.1 又要求 `_execute_single_tool` 返回 ToolResult。若 ToolResult 到达 hook，`TracingHook` 因 `isinstance(result, str)` False 会把它全部判为 success（新回归）；若泄漏到 Phase 3 消费者——`extract_text`（agent/message.py:68-74）、`summarize_tool_result`（agent/tool_result_display.py:47）、`record_tool_result`（agent/trace_recorder.py:103-129）、`tool_result_message`（agent/message.py:145）、`ToolCallMade`——会 TypeError（ToolResult 不可迭代）或 trace JSON 序列化失败。另：预拒绝分支（loop.py:1208/1232）产出的 pre_denied 是 str，gather 异常解包（loop.py:1221-1225）是 str，Phase 3 将面对 ToolResult | str 混合类型，设计未说明预拒绝条目如何携带 error_type（approval_denied/unavailable/unknown_tool）。推荐：`_execute_single_tool` 在 execute/retry 返回后立即解包为 `(text, error_type, duration_ms)`，hook 收到 text，error_type 随 entry 独立字段传到 Phase 3；预拒绝条目同样带 error_type 字段。请确认此方案。
- **Q8**: trace 的 error_type 词汇是否接受混用？结构化 error_type（Bash timeout → `"timeout"`，Decision 3 表）与文本兜底返回的 category.value（`[Error: timed out]` → `"network_timeout"`，observability.py:52-55/97-104）词汇不一致，且 observability spec delta「未打标工具仍走文本兜底」场景写「分类为 timeout」与实现（network_timeout）不符。推荐：接受混用但修正 spec delta 措辞为 `"network_timeout"`（或让兜底路径映射回细粒度 error_type 并全局统一），并明确记录「结构化优先、兜底为粗粒度 category.value」。

## 风险

- **R1 解包边界（最高）**: Decision 2 与 tasks 3.1/3.2 自相矛盾（见 Q7）。若按 tasks 实现（`_execute_single_tool` 返回 ToolResult），hook 在 loop.py:1161 收到 ToolResult → `TracingHook` 全部判 success（tracing.py:42）；Phase 3 任何未解包消费者都会 TypeError。缓解：实现前必须先定 Q7，且补一个「ToolResult 不得泄漏到 hook/record_tool_result」的协议级测试。
- **R2 test_mcp_health.py 破坏面被遗漏**: `_FakeSession.call_tool` 抛 RuntimeError（tests/agent/mcp/test_mcp_health.py:34-37）；`test_failure_rate_from_call_outcomes`（:60-69）与 `test_auto_recovers_when_window_slides`（:72-87）在无 try/except 的循环里 `await m.call_tool("alpha","add",{})`。call_tool 改为抛 `McpCallError` 后这两处测试会直接崩溃。设计 Decision 4 只点名 test_mcp_manager.py。缓解：任务清单登记 test_mcp_health.py 更新，并保证 `_record_call(server_name, False)`（manager.py:307）在 raise 前仍执行（health 语义不回归）。
- **R3 test_retry_budget.py 破坏面被计入但未枚举**: test_non_retryable_error_not_retried（:56 `result.startswith("[Error")`）与 test_retry_exhausted_returns_error（:77 `"Error after" in result`）在 RetryHook 错误路径改返 ToolResult 后失败；loop.py:1156 `if isinstance(result, str) and result.startswith("[Error")` 的 retry-exhausted 日志判定也会失效。缓解：任务 2.5 覆盖 RetryHook 测试更新，并补 loop.py:1156 改判。
- **R4 McpCallError 需定义 __str__**: RetryHook `_is_retryable(last_error_msg)`（retry.py:23-24,44）依赖 `str(e)` 含 timeout/connection 等 token。若 McpCallError 未定义 __str__ 或 text 不含这些 token，MCP 超时不再可重试。注意：当前 MCP 错误本就不经 RetryHook（McpTool 捕获），需确认这是预期而非新增回归。
- **R5 LLM 错误 trace 丢失面**: record_llm_error 后 re-raise，benchmark（runner.py finally:468 写 trace）与 web（session.py:371 catch）可保住 trace；但 CLI 若不在异常路径写 trace（agent/main.py 未见 trace 写路径）则 CLI run 的 llm_error 记录不可见。缓解：实现时确认 CLI 是否有 trace 输出；无则接受「仅 benchmark/程序化可见」并记录。
- **R6 文本兜底 vs 结构化双路径漂移**: 打标工具用结构化 error_type，未打标工具用 category.value，边界 case 可能不一致（如某工具返回 `[Error: timeout]` 文本未打标 → network_timeout，另一工具打标 timeout）。design 已承认此差异，但 spec delta 场景措辞与实现不符（见 Q8），归档前必须统一口径。
- **R7 既有 spec 张力**: tool-system spec「工具执行使用 ToolCall」场景当前断言「返回工具输出字符串」，与新增「结构化结果」需求并存；7.1 同步时需显式更新或标注，避免 spec 自相矛盾。

## User Confirmation

> 主 agent 停轮逐项确认（grill-confirmation-gate）。用户对 Q1-Q8 的答复如下，全部实质确认。

- **Q1**: 用户答复：ErrorCategory 保持四类不扩（permission_denied/network_timeout/model_error/parameter_error），error_type 细粒度值通过映射表归入粗粒度类别；确认时间: 2026-08-03
- **Q2**: 用户答复：接受 ToolResult 显式 dataclass（非 str 子类）作为破坏性协议变更，~11 处测试 + RetryHook + loop 解包 .text，test_mcp_health.py/test_retry_budget.py 破坏面纳入任务；确认时间: 2026-08-03
- **Q3**: 用户答复：MCP isError 结果纳入本次打标范围，call_tool 对 isError=true 返回 ToolResult(error_type="mcp_error")；确认时间: 2026-08-03
- **Q4**: 用户答复：LLM 错误用 re-raise 最小范围（捕获 → record_llm_error → 同一异常继续上抛），不加重试增强，run 失败语义不变；确认时间: 2026-08-03
- **Q5**: 用户答复：接受改 Hook Protocol——after_tool_execute 签名加 error_type 可选参数，TracingHook 用 error_type is not None 判失败、无 signal 回退文本前缀；确认时间: 2026-08-03
- **Q6**: 用户答复：approval denied/unavailable 的 trace status 定为 "error"，executed=False 承担「工具没跑」区分，不引入新 status 值；确认时间: 2026-08-03
- **Q7**: 用户答复：采纳立即解包方案——_execute_single_tool 在 execute/retry 返回后立即解包为 (text, error_type, duration_ms)，hook 收到解包 text，error_type 随 entry 字段到 Phase 3，补「ToolResult 不得泄漏」协议测试；确认时间: 2026-08-03
- **Q8**: 用户答复：接受 error_type 词汇混用（结构化细粒度值 vs 文本兜底粗粒度 category.value），spec delta 措辞已对齐为 network_timeout；确认时间: 2026-08-03

## 与门禁机制的兼容性确认

- 本 change 非 docs + 有 spec delta，触发 `scripts/workflow_guard.py` grill gate（`_grill_evidence_missing`，workflow_guard.py:204-242）与 `scripts/check_openspec_artifacts.py` `_check_design_review_task`（check_openspec_artifacts.py:438-489）。
- 本 grill-design.md 写入 `reviews/`（豁免路径）：workflow_guard.py:352 `rel.startswith("reviews/")` → `_is_change_doc_write` True → 写本文件不被 gate 拦截；不匹配 `*-review.md` glob，无需 review manifest（check_openspec_artifacts.py:771）。
- Confirmed Decisions 使用 `- **决策**:` 前缀（半角冒号），`_extract_grill_decisions`（check_openspec_artifacts.py:574-591）可机械解析，≥3 条满足阈值。
- Open Questions 使用 `- **Q<n>:` 索引格式，workflow_guard `_extract_open_question_indexes`（:274-296）可解析。**一旦写入本文件，workflow_guard 会对任何 agent/*.py 代码写操作返回阻塞**（`_grill_evidence_missing` 因 open question 未确认返回 True），早于 checker 的「tasks 全勾选才校验确认」。因此主 agent 必须在 building 前停轮，把 Q1-Q8 逐项抛给用户，并将非占位答复写入 `## User Confirmation`（格式 `- **Q<n>**: 用户答复：<实质内容>；确认时间: <date>`）。占位文本（待确认/待主agent提交/pending 等 ≤20 字符 token，workflow_guard.py:249-271）不计入确认。
- 无死锁：reviews/ 写入豁免 + 文档类写操作豁免；唯一阻塞点是「代码写」，这正是 grill-confirmation-gate 的设计意图。所有 Open Question 均给出推荐默认，用户可快速确认；不存在无法由用户拍板的纯实现细节问题。
- 若用户对某个 Q 选择与推荐相反（如 Q1 扩类、Q7 采用 Phase 3 解包），需同步修订 design.md 相应 Decision 与 tasks.md 后再实现。
