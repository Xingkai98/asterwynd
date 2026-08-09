# Tasks — fix-issue-107

## 实现

- [x] 将 `agent/context/sources.py` 中 `TodoSource.priority` 从 5 提升到 2，docstring 说明 issue #107 动机
- [x] spec delta：新增 `context-engineering` 能力域"执行进度保留（Todo 层级保护）"Requirement
- [x] 当前规格同步：将 ADDED Requirement 合入 `openspec/specs/context-engineering/spec.md` 并记录 workflow-events 事件
- [x] 同步 `PlanModeSource` 预算注释（P5 5K → 4K，算术 2500+1500=4000）
- [x] `agent/loop.py` `_make_default_context_builder` 将 `TodoSource` 注册移入 P2 区块（MemoryIndex 之后）
- [x] `agent/context/builder.py` `render_layers` docstring 更正：预算先裁 P4/P5，P4/P5 裁完后可能继续裁非 cacheable 的 P2

## 测试

- [x] 新增 `test_todo_source_priority_is_p2`：断言 `TodoSource.priority == 2`
- [x] 新增 `test_real_todo_survives_after_p4_p5_trimmed`：注册真实 `TodoSource`，验证 P4/P5 被裁后 Todo 完整存活
- [x] 验证回归测试有效性：临时将 priority 改回 5，两条测试均失败；还原为 2 后通过
- [x] 相关测试全绿：`tests/agent/context/test_builder.py`、`tests/agent/test_context_cache.py`、`tests/agent/tools/test_todo_tool.py`、`tests/agent/test_loop.py` 共 109 个测试通过

## 文档

- [x] `docs/agent-internals.md`：Todo 层归属、预算示例、裁切顺序、架构图同步（P5 → P2）
- [x] `docs/interview-script/walkthrough/W04-context-engineering.md` 层表同步（TodoSource 移入 P2 行）
- [x] `docs/interview-script/walkthrough/self-test-QA.md` W04 Q1 分层答案同步
- [x] 审阅报告与 manifest：`openspec/changes/fix-issue-107/reviews/building-review.md`（Round 2 PASS）+ `building-review-manifest.json`

## 审阅闭环

- [x] Round 1 独立 subagent 审阅（CHANGES_REQUESTED）：文档 7 处陈旧引用 + 回归测试未绑定真实 TodoSource
- [x] Round 1 修复：同步文档、强化测试绑定、更正 render_layers docstring
- [x] Round 2 独立 subagent 审阅（PASS，零记忆重新审阅）
- [x] 生成 review manifest 绑定 reviewer run / base·head sha / diff·report hash

## 验证

- [x] 全量相关测试通过（109 passed，含 `tests/agent/test_loop.py` todo 注入集成测试）
- [x] benchmark smoke：fake agent 跑通 36 个任务，CLI/AgentLoop 端到端无崩溃（fake agent 为回显 stub，0 通过是预期，非回归信号）
- [x] OpenSpec artifact checker 通过
