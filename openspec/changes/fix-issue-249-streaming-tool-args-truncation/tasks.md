# Tasks — fix-issue-249-streaming-tool-args-truncation

## 0. 前置

- [x] 0.1 定位根因并写 `diagnosis.md`（两条链路 + 精确复现到列号）
- [x] 0.2 建跟踪 issue #249 并在 proposal 关联
- [x] 0.3 设计决策落 `design.md`（D1 分流策略 / D3 重放降级 / D6 消息链不变量 / 剩余风险）
- [x] 0.4 维护 `## Reference Implementation Research`（`research_tier: light`，业界实践印证分流策略）

## 1. 规格

- [x] 1.1 维护 `specs/agent-runtime/spec.md` delta（追加「流式 tool call 参数不完整时降级而非崩溃」Requirement，4 个 Scenario）
- [x] 1.2 维护 `## Impact Analysis`（影响 / 不影响 / 测试与文档影响）
- [x] 1.3 落地 spec delta 到 `openspec/specs/agent-runtime/spec.md`（**当前规格同步**）
- [x] 1.4 更新 `docs/agent-internals.md` 的「max_tokens 自动续接」表述，补 tool call 截断的边界

## 2. 测试（TDD：先写回归测试，确认 red）

- [x] 2.1 **链路 A - max_tokens**（`tests/agent/test_anthropic_llm.py`）：`json_parts` 尾部截断的 `tool_use` block + `stop_reason="max_tokens"` → 断言不抛异常、该 call 被丢弃、`stop_reason` 仍为 `max_tokens`
- [x] 2.2 **链路 A - 非 max_tokens**：同上但 `stop_reason="tool_use"` → 断言不抛异常、call 保留、`arguments` 为原始串
- [x] 2.3 **链路 A - 成功路径不变**（回归保护）：合法 JSON → 断言 `arguments` 为规范化的 `json.dumps`
- [x] 2.4 **链路 B**：构造非法 `arguments` 的 assistant 消息 → `_build_payload` 不抛异常且 `input` 为 `{}`
- [x] 2.5 **端到端**（`tests/agent/test_loop.py` 或同文件）：mock LLM 返回截断 tool_call → AgentLoop 不崩、走续接/降级并结束
- [x] 2.6 **变异验证（判别力证明）**：临时还原修复 → 2.1/2.2/2.4/2.5 必红；恢复 → 必绿。记录实测
- [x] 2.7 确认测试不依赖机器负载、不使用墙钟 sleep 作断言

## 3. 实现

- [x] 3.1 `agent/anthropic_llm.py` `_build_response`：`tool_use` 参数解析失败降级（按 `stop_reason` 分流：`max_tokens` 丢弃，否则保留原始串）
- [x] 3.2 `agent/anthropic_llm.py` `_build_payload`：重放时解析失败降级为 `{}`
- [x] 3.3 `agent/llm.py` `_stream_events`：SSE 单行解析失败的静默 `continue` 补 warning 日志（只增日志，不改控制流）
- [x] 3.4 确认成功路径零变化（D1 边界不变量）

## 4. 验证

- [x] 4.1 原始复现脚本（`diagnosis.md` 的两条链路）在修复后不再崩溃
- [x] 4.2 全量 pytest 通过（改动涉及 LLM 层，按仓库规则跑全量）
- [x] 4.3 OpenSpec strict validate 通过
- [x] 4.4 项目 artifact checker 通过

## 5. 收尾

- [ ] 5.1 运行 `/review-loop` 独立审阅闭环，产出 `reviews/building-review.md` + manifest（PASS）
- [x] 5.2 文档影响检查：`docs/agent-internals.md` 已更新（补 tool call 截断的边界）；`docs/known-debt.md` 新增债务条目「SSE 解析失败时未重置 event_type（本 change 显式不做）」（受保护路径，已写 `protected_artifact_explained` 事件）；扫描 `README.md`/`AGENTS.md`/`CONTEXT.md` 无相关段落需改（本 change 不涉及用户可见行为与项目词汇）
      （更正：初稿此处误写为 `docs/known-issues.md`；该文件是机械豁免模式表、非叙述记录处，实际记录落在 `docs/known-debt.md`）
- [x] 5.3 同步 backlog（`docs/openspec-change-backlog.md`，受保护路径，写 `backlog_updated` 事件）
- [ ] 5.4 归档 change 到 `openspec/changes/archive/2026-09-26-fix-issue-249-streaming-tool-args-truncation/`，从 backlog 移除
- [ ] 5.5 发起 PR；合入时给 issue #249 添加完成说明 comment 并关闭
