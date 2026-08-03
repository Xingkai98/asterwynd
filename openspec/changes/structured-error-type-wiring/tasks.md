# Tasks: 结构化 error_type 全链路接入

## 0. 开发前设计追问（进入 building 前）

- [x] 0.1 运行 `/grill` 独立 subagent 设计追问（batch-grill-me 等价流程）：挑战 design.md，产出 `reviews/grill-design.md`（≥3 条 `## Confirmed Decisions`）
- [x] 0.2 停轮确认：把 `## Open Questions`（Q1-Q8）逐项抛给用户，答复记录进 `reviews/grill-design.md` 的 `## User Confirmation`（全部确认前不写实现代码）

## 1. ToolResult 协议层

- [x] 1.1 `agent/tools/base.py` 新增 `ToolResult` dataclass（`text: str | list[ContentBlock]` + `error_type: str | None = None`）
- [x] 1.2 `Tool.execute` 返回类型注解拓宽为 `str | list[ContentBlock] | ToolResult`
- [x] 1.3 `ToolRegistry.execute` 返回 `ToolResult`：普通 `str | list` 自动包装，`ToolResult` 原样透传
- [x] 1.4 `ToolRegistry.execute` deny 分支打标 `permission_denied`；REQUIRE_APPROVAL 兜底打标 `approval_required`
- [x] 1.5 协议层测试：包装/透传/deny/approval 打标 + 既有 `registry.execute` 调用方解包 `.text`（~11 处）
- [x] 1.6 协议级泄漏测试：**「ToolResult 不得泄漏到 hook/record_tool_result」**——hook 收到 str/list；record_tool_result 收到 error_type 独立参数（grill R1）

## 2. 工具层打标

- [x] 2.1 `BashTool.execute`：workspace policy deny → `permission_denied`；command guard deny → `permission_denied`
- [x] 2.2 `BashTool.execute`：`sandbox_result.timed_out` → `timeout`；`oom_killed` → `resource_exhausted`；后台不可用 → `unavailable`
- [x] 2.3 MCP：新增 `McpCallError`（`error_type` + `text` + `__str__` 返回 text）；`call_tool` 异常分支抛出（timeout/network_error/mcp_error），**`_record_call(False)` 在 raise 前执行**；`McpTool.execute` 捕获转 `ToolResult`
- [x] 2.4 MCP isError：`call_tool` 对 `isError=true` 结果返回 `ToolResult(text=格式化文本, error_type="mcp_error")`；`McpTool.execute` 原样透传（grill Q3）
- [x] 2.5 `RetryHook.execute_with_retry` 错误路径返回 `ToolResult`（超时/网络异常带 error_type，其他留 None）
- [x] 2.6 工具层测试：Bash（mock sandbox 的 timeout/policy/guard/oom 分支）、MCP（call_tool 抛错 + McpCallError.__str__ + isError 分支 + McpTool 转换）、RetryHook（重试耗尽/非可重试异常）
- [x] 2.7 破坏面回归：`test_mcp_health.py` 两处循环调用改接 McpCallError（:60-69/:72-87）；`test_retry_budget.py` 两处断言改接 ToolResult（:56/:77）（grill R2/R3）

## 3. AgentLoop 接线

- [x] 3.1 `_execute_single_tool` 在 execute/retry 返回后**立即解包**为 `(text, error_type, duration_ms)`；`hooks.after_tool_execute` 收到解包 text；Bash 异常兜底 `asyncio.TimeoutError` → `timeout`，其他留 None（grill Q7）
- [x] 3.2 `_execute_tool_calls` gather 异常解包：异常 → `(text=f"[Error: {r}]", error_type=按异常类型)`；预拒绝条目带 error_type 字段（approval_denied/unavailable/unknown_tool）
- [x] 3.3 `loop.py` retry-exhausted 日志判定改解包后 text（`isinstance(result, str)` 改判）
- [x] 3.4 Phase 3 判定：`entry["error_type"]` 存在 → status="error" 直接用；否则保留文本前缀 + ErrorClassifier 兜底
- [x] 3.5 `record_tool_result` 传结构化 error_type（替代文本猜测）
- [x] 3.6 AgentLoop 集成测试：Bash 超时（mock sandbox `timed_out=True`）→ status="error" + error_type="timeout"（回归修 JSON 误判 ok）；registry deny → `permission_denied`；approval 预拒绝 → `approval_denied`；MCP → `mcp_error`；未打标工具 → 文本兜底不回归

## 4. LLM 错误可观测化

- [x] 4.1 `TraceRecorder` 新增 `record_llm_error(error_type, message)`（additive step 类型 `llm_error`）
- [x] 4.2 loop `_call_llm` 外层捕获异常 → 分类（连接/超时 → `network_timeout`；API/auth/其他 → `model_error`）→ `record_llm_error` → re-raise（保持控制流）
- [x] 4.3 测试：`_call_llm` 抛错时 trace 含 `llm_error` step 且 error_type 正确；re-raise 语义保留

## 5. 观测词汇与 TracingHook

- [x] 5.1 `agent/observability.py` `_ERROR_TYPE_TO_CATEGORY` 扩展（approval_* / network_error / resource_exhausted / unavailable / unknown_tool → 对应类别）
- [x] 5.2 `HookManager.after_tool_execute` 签名增加 `error_type: str | None = None`（manager.py:20,46-48 同步）；`TracingHook` success 判定用 `error_type is not None` 判失败、无 signal 回退文本前缀（grill Q5）；其余 hook 实现（logging/token_budget/debug_hook/parent_channel/budget）签名同步
- [x] 5.3 测试：新 error_type → 类别映射；TracingHook 对 approval/timeout 结果的 success 判定（Bash 正常 JSON vs timed_out JSON 区分）

## 6. spec delta

- [x] 6.1 `specs/tool-system/spec.md`：ADDED「工具执行结果携带结构化错误码」（`ToolResult` + registry 包装/透传 + deny/approval 打标）
- [x] 6.2 `specs/observability/spec.md`：ADDED「error_type 在产生点打标」（关键打标点 + 结构化优先/文本兜底；文本兜底词汇对齐 network_timeout）

## 8. 审阅修复（独立 subagent 审阅 CHANGES_REQUESTED 闭环 Round 1）

> 独立零记忆审阅（run review-run-structured-error-type-wiring-2026-08-03-001）发现 1 中 + 1 中低 + 4 低，已全部修复：

- [x] 8.1 **N1（中）** Bash OOM / 后台不可用分支补测试：`test_bash_tool_events.py` 新增 `test_oom_killed_marks_resource_exhausted` + `test_background_unavailable_marks_unavailable`
- [x] 8.2 **N2（中低）** `_ERROR_TYPE_TO_CATEGORY` 补 `model_error → MODEL_ERROR`（design 声称已存在，实际缺失）+ `test_error_type_wiring.py` 断言
- [x] 8.3 **N3（低）** `tests/agent/hooks/test_manager.py` MockHook 签名同步 error_type 参数
- [x] 8.4 **N4（低）** `_exception_error_type` 去重：抽公共 `agent/observability.py:exception_error_type`，loop.py/retry.py 共用（防两处漂移）
- [x] 8.5 **N5（低）** `BashTool._execute_background` 返回注解 `-> str` 改为 `str | ToolResult`
- [x] 8.6 **N6（低）** 并行 gather TimeoutError→timeout 直接测试：`test_error_type_wiring.py::test_parallel_gather_timeout_tags_error_type`

## 7. 收尾

- [ ] 7.1 当前规格同步：把 spec delta 合并到 `openspec/specs/tool-system/spec.md` + `openspec/specs/observability/spec.md`（受保护路径，配 workflow-events.jsonl 解释事件）
- [ ] 7.2 文档影响检查：`docs/openspec-change-backlog.md` 移除本 change（配 workflow 事件）；文档地图相关入口关键词扫描
- [x] 7.3 benchmark smoke verification：coding-agent core change（改 `agent/tools/` + `agent/loop.py`）要求——`asterwynd benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/smoke-89` 跑通（0 passed/10 unsupported/26 failed，与基线一致，无新回归）
- [ ] 7.4 全量 pytest + `openspec validate --all --strict` + artifact checker
- [ ] 7.5 `/review-loop` 独立审阅闭环至 PASS（含 building-review.md + manifest）
- [ ] 7.6 归档 `openspec/changes/archive/2026-08-03-structured-error-type-wiring/` + backlog 清理 + 提 PR
