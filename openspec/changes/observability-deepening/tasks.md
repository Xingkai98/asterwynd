# Tasks: 可观测性做深

> **批次范围**：第一批 = 第 1-3 节（TraceRecorder token + 结构化 schema + CostLedger 成本归属 + ErrorClassifier 异常分类）；第 4 节（CI 回归门禁）与第 5 节（session timeline 看板）为后续批（回归门禁依赖 benchmark 实际跑通、受环境制约；timeline 要改 web + 事件持久化、与 TUI 共享事件协议应错开）。

## 1. TraceRecorder token + 结构化 schema ✅

- [x] 1.1 `record_iteration` 增加 token 参数（input_tokens/output_tokens，来自 LLMResponse.usage）+ model + finish_reason（可选默认 None）
- [x] 1.2 `record_tool_result` 增加 error_type（可选默认 None）
- [x] 1.3 `TraceStep` 增加 timestamp 字段（record 时自动打点，默认值兼容）
- [x] 1.4 `to_dict()` 顶层加 schema_version: "1.1"（向后兼容）
- [x] 1.5 单元测试：token 记录、timestamp、schema_version（向后兼容）

## 2. CostLedger 成本归属 ✅

- [x] 2.1 `agent/observability.py` 定义 PHASE_BY_MODE + resolve_phase（build→building/read_only→review/plan→planning/bypass→bypass）
- [x] 2.2 `cost_tracker.py` 扩展 CostLedger：record(model, input, output, *, session_id, phase, tool_name) + bill() 三维账本 + total()
- [x] 2.3 CostLedger JSONL 持久化：flush(path) append + load(path) 恢复（默认 ~/.asterwynd/ledger.jsonl）
- [x] 2.4 loop 接线：LLM 调用后 ledger.record + run 结束 flush
- [x] 2.5 单元测试：成本归属分组、持久化 roundtrip

## 3. ErrorClassifier 异常分类 ✅

- [x] 3.1 `agent/observability.py` 定义 ErrorCategory 枚举（permission_denied/network_timeout/model_error/parameter_error）+ ErrorClassifier
- [x] 3.2 分类逻辑：结构化字段优先（error_type/finish_reason）+ 文本兜底
- [x] 3.3 每类告警策略（alert_level: immediate/warn/record）
- [x] 3.4 单元测试：分类器、告警策略

## 4. CI 回归门禁（后续批）

- [ ] 4.1 基线持久化（P95 延迟/成功率）
- [ ] 4.2 CI 跑 benchmark → 对比基线 → 劣化 >5% 拦截（返回非零）
- [ ] 4.3 复用 PR #80 statistics（bootstrap CI）
- [ ] 4.4 集成测试：门禁命令

## 5. Session timeline 看板（后续批）

- [ ] 5.1 单个 session timeline 可视化（tool call 耗时排序/条形）
- [ ] 5.2 与 add-minimal-tui-runtime-view 对齐事件粒度
- [ ] 5.3 集成测试：看板渲染

## 6. 收尾

- [x] 6.1 OpenSpec spec 同步
- [x] 6.2 全量 pytest + openspec validate + artifact checker
- [ ] 6.3 benchmark 量化（session 账单、异常分类准确率）

## 7. 收尾校验（checker 要求项）

- [ ] 7.1 pre-implementation batch-grill-me 或等价设计审阅任务（进入 building 前）
- [ ] 7.2 benchmark smoke verification（coding-agent core change 要求）
- [ ] 7.3 当前规格同步：把 spec delta 合并到 `openspec/specs/<capability>/spec.md`

## 8. 审阅修复（独立 subagent 审阅 CHANGES_REQUESTED 闭环）

> 实现完成后由独立零记忆 subagent 审阅（issue #90 流程），发现 3 个中等接线问题并已修复：

- [x] 8.1 CostLedger 生产接线：main.py 构造 CostLedger 传入 AgentLoop；SubAgentManager 共享同一 ledger（`_build_subagent_loop` 传 cost_ledger + ledger_tool_name="subagent"），ledger.record 带 tool_name 使 by_tool 归属有效
- [x] 8.2 error_type 产生点打标：loop.py 两处 record_tool_result 传入 error_type（parse 失败→parse_error；工具错误→ErrorClassifier 文本兜底分类）
- [x] 8.3 回归测试：test_loop.py 新增 cost_ledger 接线 + subagent ledger 继承 + error_type 打标 3 个测试
