# Building Review: structured-error-type-wiring

## Reviewer

- run id: review-run-structured-error-type-wiring-2026-08-03-002
- 时间: 2026-08-03
- 审阅范围: origin/master...HEAD（实现提交 `3c852ae` + Round 1 修复提交 `202f11c`）
- 性质: 第二轮审阅（Round 1 CHANGES_REQUESTED 的 N1-N6 修复核验）

## Verdict

- **PASS**

Round 1 的 6 个问题（N1-N6）已全部修复并通过测试验证；第一轮确认的架构正确性（ToolResult 不泄漏、hook 签名同步、Bash 超时 JSON 误判修复、MCP 类型化错误、LLM 错误可观测化）未回退；修复未引入新问题（无循环依赖、`import asyncio` 无副作用）。两门 CI 门禁中 OpenSpec strict validate 全绿；artifact checker 仅因 Round 2 manifest 尚未生成而报缺（review-loop 在 PASS 后写入，属流程中间态，非缺陷）。

## N1-N6 逐条验证

- **N1（中）Bash OOM / 后台不可用分支测试** ✓ 已修复。
  - `tests/agent/tools/test_bash_tool_events.py:125-144` 新增 `test_oom_killed_marks_resource_exhausted`：mock `SandboxResult(oom_killed=True)`，断言 `result.error_type == "resource_exhausted"`，对应 `agent/tools/builtin/bash.py:97` 的 `if result.oom_killed:` 分支。
  - `tests/agent/tools/test_bash_tool_events.py:146-160` 新增 `test_background_unavailable_marks_unavailable`：`BashTool` 不注入 `run_in_background_cb`，`run_in_background=True`，断言 text 含 "Background task execution is not available" 且 `error_type == "unavailable"`，对应 `bash.py:100-105` 分支。
  - 两测试实际运行通过（`4 passed`，含 N2/N6 用例）。

- **N2（中低）`model_error` 映射缺失** ✓ 已修复。
  - `agent/observability.py:61` `_ERROR_TYPE_TO_CATEGORY` 新增 `"model_error": ErrorCategory.MODEL_ERROR`，与 design Decision 7 表格一致；`_ALERT_LEVEL[MODEL_ERROR] = "warn"` 使下游 `classify(error_type="model_error")` 正确落到 warn 告警级。
  - `tests/agent/test_error_type_wiring.py:396` 新增断言 `classifier.classify(error_type="model_error") is ErrorCategory.MODEL_ERROR`，运行通过。

- **N3（低）test_manager.py MockHook 签名遗漏** ✓ 已修复。
  - `tests/agent/hooks/test_manager.py:23-28` `MockHook.after_tool_execute` 增加 `error_type: str | None = None` 可选参数，与 `agent/hooks/manager.py:20-25` Hook Protocol 签名一致。

- **N4（低）`_exception_error_type` 重复定义** ✓ 已修复。
  - `agent/observability.py:86-99` 新增公共 `exception_error_type(exc)`；`agent/loop.py:38` 与 `agent/hooks/builtin/retry.py:8` 均改为 import 该 helper（loop.py:1272、retry.py:47 调用点）。
  - grep 全仓无残留本地 `_exception_error_type` 定义；仅存的 `_llm_exception_error_type`（loop.py:101）是 LLM 错误专用分类函数，语义不同，保留正确。
  - **循环依赖检查**：`observability.py` 仅 import stdlib（`asyncio`、`enum`），loop.py/retry.py import observability 不构成环；retry.py 的 `import asyncio` 仍被 `asyncio.sleep`（retry.py:62）使用，非多余导入。

- **N5（低）`_execute_background` 返回注解** ✓ 已修复。
  - `agent/tools/builtin/bash.py:100` 注解由 `-> str` 改为 `-> str | ToolResult`，与 :102-105 的 `ToolResult` 返回路径一致。

- **N6（低）并行 gather TimeoutError 无直接测试** ✓ 已修复。
  - `tests/agent/test_error_type_wiring.py:348-384` 新增 `test_parallel_gather_timeout_tags_error_type`：`TimeoutTool` 抛 `asyncio.TimeoutError`，断言 `steps[0]["status"] == "error"` 且 `error_type == "timeout"`，覆盖 `loop.py:1269-1274` gather 异常解包路径。运行通过。

## 架构无回退确认

- **ToolResult 泄漏**：`tests/agent/test_error_type_wiring.py:103` `test_tool_result_does_not_leak_to_hook_or_record_tool_result` 通过——hook 收到解包 `str`（非 ToolResult）+ 独立 `error_type` 参数；`loop.py:1215-1216` 的立即解包逻辑未变。
- **hook 签名同步**：`rg "after_tool_execute"` 确认 manager.py、tracing/logging/token_budget/retry、parent_channel_hook、budget 以及两处测试 mock 全部带 `error_type` 参数，无遗漏。
- **Bash JSON 误判**：`test_bash_timeout_json_no_longer_judged_ok` 与 `test_bash_normal_json_still_ok` 通过——`bash.py:95` timed_out 分支返回结构化 `ToolResult(error_type="timeout")`，Phase 3 用 `entry["error_type"]` 判 status（loop.py:875-877），正常 JSON 仍判 ok。
- **MCP 路径**：`McpCallError`（types.py:28-44）+ `McpTool.execute` 捕获转 `ToolResult`（tools.py:22-26）+ isError 分支原样透传，未受影响。

## Test Results

- 指定套件：`test_error_type_wiring.py test_bash_tool_events.py test_loop.py test_retry_budget.py test_manager.py test_mcp_health.py test_observability.py test_registry.py test_plan_mode_tools.py test_code_intelligence_tools.py test_read_write_tools.py` → **165 passed**
- `tests/agent/tools/ + tests/agent/hooks/` 全量 → **406 passed**
- 修复点独立用例（N1 两例 + N2 映射 + N6 gather）→ **4 passed**
- `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` → **28 passed, 0 failed**
- `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py` → 仅报 `building-review-manifest.json` 缺失——该 manifest 由 review-loop 在 Round 2 PASS 后写入（`agent/workflow/review_manifest.py:write_review_manifest`），当前为审阅闭环中间态，非代码缺陷。

## 结论

Round 1 提出的 1 中 + 1 中低 + 4 低问题全部落实修复，测试先行且真实覆盖对应代码路径，无占位/空断言。修复方式干净：N4 抽公共 helper 消除了两处漂移风险，且无循环依赖副作用；N2 补齐映射使 design 声称与实际实现一致。架构层无回退，无新引入问题。剩余未勾选的 tasks 7.1/7.2/7.4/7.5/7.6 为收尾阶段任务（spec 同步、backlog 清理、全量验证、manifest 生成、归档），按流程在 PR 前完成，属预期状态。

建议：进入收尾流程（/review-loop 生成 PASS manifest 后执行归档收尾）。
