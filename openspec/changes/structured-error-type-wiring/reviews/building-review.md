# Building Review: structured-error-type-wiring

## Reviewer

- run id: review-run-structured-error-type-wiring-2026-08-03-001
- 时间: 2026-08-03
- 审阅范围: origin/master...HEAD（实现提交 `3c852ae`，含 4 个提交）

## Verdict

- **CHANGES_REQUESTED**

## Tasks Verification

逐条对照 tasks.md，核实 `[x]` 任务的真实实现（读代码，不只读文件名）。

- **0.1** `[x]` ✓ `reviews/grill-design.md` 存在，含 6 条 `## Confirmed Decisions`（半角冒号前缀，checker 可机械解析），来源 grill-run-...-001。
- **0.2** `[x]` ✓ `## User Confirmation` 中 Q1-Q8 全部有实质答复 + 确认时间（2026-08-03），无占位文本。
- **1.1** `[x]` ✓ `agent/tools/base.py:97-107` 新增 `ToolResult` dataclass（`text: str | list[ContentBlock]` + `error_type: str | None = None`）。
- **1.2** `[x]` ✓ `agent/tools/base.py:49` `Tool.execute` 返回类型拓宽为 `str | list[ContentBlock] | "ToolResult"`。
- **1.3** `[x]` ✓ `agent/tools/registry.py:137-160` `execute` 返回 `ToolResult`；普通 `str|list` 自动包装（:160），`ToolResult` 原样透传（:158-159）。
- **1.4** `[x]` ✓ `agent/tools/registry.py:140-148` deny 分支打标 `permission_denied`；:149-156 `REQUIRE_APPROVAL and not approval_granted` 兜底打标 `approval_required`。
- **1.5** `[x]` ✓ 协议层测试：`test_registry.py`（包装/透传/deny/approval）、`test_mcp_manager.py:85/152`、`test_plan_mode_tools.py:147/177`、`test_code_intelligence_tools.py:88` 均解包 `.text`。
- **1.6** `[x]` ✓ `tests/agent/test_error_type_wiring.py:101-128` 泄漏测试：hook 收到 str（非 ToolResult）+ error_type 独立参数；`record_tool_result` 收到 error_type 字段。
- **2.1** `[x]` ✓ `agent/tools/builtin/bash.py:68-79` workspace policy `PermissionError` → `permission_denied`；command guard DENY → `permission_denied`。
- **2.2** `[x]` ✓ `bash.py:92-95` `timed_out` → `timeout`；:96-97 `oom_killed` → `resource_exhausted`；:100-105 后台不可用 → `unavailable`。实现存在，但后两者**无测试**（见 N1）。
- **2.3** `[x]` ✓ `agent/mcp/types.py:28-44` `McpCallError(error_type, text, __str__→text)`；`agent/mcp/manager.py:308-323` 异常分支抛 `McpCallError`，`_record_call(server_name, False)` 在 raise 前执行（:309/:315）；`agent/mcp/tools.py:22-26` `McpTool.execute` 捕获转 `ToolResult`。
- **2.4** `[x]` ✓ `manager.py:326-328` `isError=true` 返回 `ToolResult(text=_format_call_tool_result(...), error_type="mcp_error")`；`McpTool.execute` 原样透传。
- **2.5** `[x]` ✓ `agent/hooks/builtin/retry.py:60-73` 非可重试/重试耗尽返回 `ToolResult`（timeout/network_error 带 error_type，其他 None）。
- **2.6** `[x]` **部分未完成**：timeout/policy/guard 分支有测试（`test_bash_tool_events.py`/`test_bash_tool_workspace.py`/`test_bash_tool_structured_output.py`）；但任务声称的 **oom 分支无任何测试**，后台不可用分支亦无测试（见 N1）。MCP（`test_mcp_manager.py` 抛错/`__str__`/isError/转换）与 RetryHook（`test_retry_budget.py`）测试存在。
- **2.7** `[x]` ✓ `test_mcp_health.py:65-69/78-84` 循环调用改接 `pytest.raises(McpCallError)`；`test_retry_budget.py:56/77` 断言改接 ToolResult。
- **3.1** `[x]` ✓ `agent/loop.py:1182-1223` `_execute_single_tool` 返回 `(text, error_type, duration_ms)`；execute/retry 返回后立即解包（:1215-1216）；hook 收到解包 text + error_type（:1222）；Bash 异常兜底 `asyncio.TimeoutError → timeout`（:1200-1203）、其他留 None（:1204-1207）。
- **3.2** `[x]` ✓ `loop.py:1225-1301` gather 异常解包（:1281-1287，error_type 按 `_exception_error_type`）；预拒绝条目带 error_type（Phase 1 存入，Phase 2 经 `**item` 透传）。
- **3.3** `[x]` ✓ `loop.py:1217-1220` retry-exhausted 日志改判解包后 text（`isinstance(text, str) and text.startswith("[Error")`）。
- **3.4** `[x]` ✓ `loop.py:875-883` `entry["error_type"]` 非 None → status="error"；否则 `_text_prefix_guess` + `ErrorClassifier` 兜底。
- **3.5** `[x]` ✓ `loop.py:895-903` `record_tool_result(..., error_type=error_type)` 传结构化 error_type。
- **3.6** `[x]` ✓ `test_error_type_wiring.py:152-298`：Bash 超时回归（timed_out JSON → error/timeout）、Bash 正常 JSON 仍 ok、approval_denied、mcp_error。
- **4.1** `[x]` ✓ `agent/trace_recorder.py:220-226` `record_llm_error(error_type, message)`（additive `llm_error` step）。
- **4.2** `[x]` ✓ `loop.py:1046-1095` `_call_llm` 外层 catch → `_llm_exception_error_type` 分类 → `record_llm_error` → `raise`（re-raise 语义保留，:1095）。
- **4.3** `[x]` ✓ `test_error_type_wiring.py:304-341`：ConnectionError → network_timeout + re-raise；RuntimeError → model_error。
- **5.1** `[x]` **部分完成**：`agent/observability.py:44-61` 新增 approval_*/network_error/unknown_tool/mcp_error/resource_exhausted/unavailable 映射；但 design Decision 7 声称已存在的 `model_error` 映射缺失（见 N2）。
- **5.2** `[x]` ✓ `agent/hooks/manager.py:20-25,51-58` `after_tool_execute` 加 `error_type` 可选参数；`tracing.py:35-58` 用 `error_type is not None` 判失败、无 signal 回退文本前缀；logging/token_budget/debug_hook/parent_channel/budget 签名全部同步。
- **5.3** `[x]` ✓ `test_error_type_wiring.py:346-376`：error_type→category 映射 + TracingHook approval/timeout/Bash JSON 区分。
- **6.1** `[x]` ✓ `specs/tool-system/spec.md`：ADDED「工具执行结果携带结构化错误码」+ 4 scenarios。
- **6.2** `[x]` ✓ `specs/observability/spec.md`：ADDED「error_type 在产生点打标」+「LLM 错误可观测化」；文本兜底词汇对齐 `network_timeout`（grill Q8）。
- **7.3** `[x]` ✓ benchmark smoke 已声明跑通（0/10/26，与基线一致）。未重跑（耗时），benchmark 测试套件 `tests/benchmark/` 通过。

以下为收尾阶段任务（building 阶段未勾选，属预期）：**7.1** spec 同步到 `openspec/specs/`、**7.2** backlog 移除、**7.4** 全量 pytest + validate + checker、**7.5** 本审阅闭环、**7.6** 归档 + PR。均为 `[ ]`，符合「building 未完成」状态，checker 不拦截。

## Issues

- **N1（中）**: `agent/tools/builtin/bash.py:96-97`（`oom_killed → resource_exhausted`）与 `:100-105`（后台不可用 → `unavailable`）两个已实现分支**无测试覆盖**。tasks 2.6 声称「Bash（mock sandbox 的 timeout/policy/guard/oom 分支）」已测，但全仓 grep 无 `oom_killed=True` mock、无 `run_in_background=True` + 无 cb 的用例（`tests/agent/tools/test_bash_tool_*.py` 三个文件均未覆盖）。按 AGENTS.md「工具协议或 AgentLoop 变更必须覆盖对应层级测试」，需补 2 个单元测试（OOM mock sandbox；`run_in_background=True` 且 `_run_in_background_cb is None`）。
- **N2（中低）**: `agent/observability.py:44-61` `_ERROR_TYPE_TO_CATEGORY` **缺少 `model_error` 键**，与 design.md:164 表格「`model_error` → MODEL_ERROR 已存在」不一致。`agent/loop.py:122` `_llm_exception_error_type` 对 API/auth/未知 LLM 异常产出 `"model_error"` 并写入 llm_error 事件；若下游用 `ErrorClassifier().classify(error_type="model_error")` 分类，将返回 UNKNOWN（告警等级 `record` 而非 `warn`），偏离 spec。当前无生产调用方实际执行该分类，属潜在不一致；建议补 `"model_error": ErrorCategory.MODEL_ERROR` 并加断言测试。
- **N3（低）**: `tests/agent/hooks/test_manager.py:23` `MockHook.after_tool_execute(self, tool_call, result)` 未随 Hook Protocol 同步加 `error_type` 参数。当前测试未触发该调用（只测 `before_iteration`），无运行时报错；但与 `Hook` 协议签名不一致，一旦该 hook 被 `HookManager.after_tool_execute` 调用会 TypeError。
- **N4（低）**: `_exception_error_type` 在 `agent/loop.py:101-111` 与 `agent/hooks/builtin/retry.py:27-37` 重复定义（同一异常→error_type 映射）。建议抽公共 helper，避免两处漂移。
- **N5（低）**: `agent/tools/builtin/bash.py:100` `_execute_background` 返回类型注解为 `-> str`，但 :102-105 返回 `ToolResult`。注解应为 `str | ToolResult`。
- **N6（低）**: `loop.py:1281-1287` gather 异常解包的 error_type 映射（`asyncio.TimeoutError → timeout`、`ConnectionError → network_error`）无直接测试；`test_loop.py:1574 test_parallel_group_error_isolation` 仅覆盖 RuntimeError→None 路径。

## Test Results

- `python3 -m pytest -q tests/agent/test_error_type_wiring.py tests/agent/test_loop.py tests/agent/tools/test_registry.py tests/agent/tools/test_bash_tool_events.py tests/agent/tools/test_bash_tool_workspace.py tests/agent/hooks/test_retry_budget.py tests/agent/mcp/test_mcp_health.py tests/agent/hooks/test_logging_tracing.py tests/web_tests/test_timeline.py` → **129 passed**
- `tests/agent/tools/ + tests/agent/hooks/` → **404 passed**
- `tests/agent/mcp/` → **17 passed, 5 failed**（5 个失败均为 `test_mcp_manager.py` stdio/http 测试，根因 `FileNotFoundError: [Errno 2] No such file or directory: 'uv'`——已知环境问题，与本次变更无关）
- `tests/agent/` 全量 → **1336 passed, 6 failed**（5 个 uv 环境失败 + 1 个 `test_tree_sitter_extracts_java_and_kotlin_symbols` 版本问题，均为已知环境失败）
- `tests/web_tests/ + tests/benchmark/` → **279 passed, 7 skipped**
- `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` → **28 passed, 0 failed**
- `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py` → **OpenSpec artifact checks passed**

## 结论

实现整体质量高：ToolResult 协议、registry 包装/透传/deny/approval 打标、Bash 超时 JSON 误判修复、MCP 类型化异常、RetryHook 结构化错误、Hook Protocol 全量签名同步、LLM 错误可观测化、观测词汇扩展均按 design/grill 决策落地，核心回归测试（Bash 超时不再误判 ok）真实覆盖并通过。两个 CI 门禁（openspec validate + artifact checker）全绿。

发现 6 个问题：1 个中等问题（N1：tasks 2.6 声称已测的 Bash OOM/后台不可用分支实际无测试）+ 1 个中低（N2：`model_error` 缺失于 category 映射，design 与实际不符）+ 4 个低。无阻塞性缺陷、无安全风险、无 ToolResult 泄漏、无 CI 弱化。

建议：修复 N1/N2 后重审（补 2 个 Bash 分支测试 + `model_error` 映射与断言），N3-N6 可一并顺手处理。修复内容小，不改变架构。
