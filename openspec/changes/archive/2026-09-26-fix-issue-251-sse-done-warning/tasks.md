# Tasks — fix-issue-251-sse-done-warning

## 0. 前置

- [x] 0.1 端到端实测复现（`asterwynd run --provider openai`，第二次 LLM 调用出现告警）
- [x] 0.2 建跟踪 issue #251 并在 proposal 关联
- [x] 0.3 写 `diagnosis.md`（症状 / 复现 / 证据 / 根因 / 方向 / 回归测试）
- [x] 0.4 写 `design.md`（D1 放行位置 / D2 判据精确度 / D4 反向守护 / D5 不做 provider 感知）
- [x] 0.5 维护 `## Reference Implementation Research`（`research_tier: exempt`，上游协议事实锁定 + #249 决策链闭合）

## 1. 规格

- [x] 1.1 维护 `specs/agent-runtime/spec.md` delta（新增 Requirement「SSE 可观测性区分协议控制帧与坏行」，3 个 Scenario）
- [x] 1.2 落地 spec delta 到 `openspec/specs/agent-runtime/spec.md`（当前规格同步）
- [x] 1.3 维护 `## Impact Analysis` 与 `## Reference Implementation Research`

## 2. 测试（TDD：先写失败测试，确认 red）

- [x] 2.1 **正向**：`test_done_sentinel_does_not_log_dropped_line_warning` —— `[DONE]` 不产生告警（修复前 RED）
- [x] 2.2 **反向守护**：`test_genuinely_bad_sse_line_still_logs_warning` —— 真实坏行仍产生**恰好 1 条**告警（修复前 RED：坏行+哨兵共 2 条）
- [x] 2.3 **变异验证**：把 `_is_sse_stream_end(data_str)` 短路为 `False` → 两条均 RED；还原 → GREEN（已实测）

## 3. 实现

- [x] 3.1 `agent/llm.py`：新增 `_SSE_STREAM_END_SENTINEL` 常量与 `_is_sse_stream_end()` 辅助
- [x] 3.2 `agent/llm.py`：`_stream_events` 的 `data:` 分支在 `json.loads` **之前**放行哨兵
- [x] 3.3 确认事件序列零变化（`[DONE]` 修复前后都不产生事件）

## 4. 验证

- [x] 4.1 `tests/agent/test_openai_llm.py` 全量通过
- [x] 4.2 全量 pytest 通过（改动在共享 LLM 层）；实测 `3 failed, 3066 passed`，3 条均为**预先存在**的环境失败（tree-sitter Java/Kotlin grammar 缺失；`tests/agent/memory/test_persistent.py::TestFindScopeRoot` 两条因本机 `/tmp` 是 git 仓库），已在独立 worktree `14f6e24` 上核验同样失败
- [x] 4.3 端到端复验：`asterwynd run --provider openai` 不再出现该告警
- [x] 4.4 OpenSpec strict validate 通过
- [x] 4.5 项目 artifact checker 通过

## 5. 收尾

- [x] 5.1 运行独立审阅闭环，产出 `reviews/building-review.md` + manifest（PASS）
- [x] 5.1a 落实审阅 Issue 1：补 `test_done_like_variant_is_not_treated_as_sentinel` 锁定 D2 精确匹配意图（变异验证：`==` 改 `startswith` 后该测试变红）
- [x] 5.1b 落实审阅 Issue 3/4/5：修正 4.2 文案、勾选 5.3、第三条测试 docstring 与 spec 举例对齐
- [x] 5.2 文档影响检查（本 change 无用户可见行为变更；确认 `docs/known-debt.md` 相邻债务条目不受影响、无需回写）
- [x] 5.3 同步 backlog（受保护路径，写 `backlog_updated` 事件）
- [x] 5.4 归档 change 到 `openspec/changes/archive/2026-09-26-fix-issue-251-sse-done-warning/`，从 backlog 移除
- [ ] 5.5 (post-merge) 发起 PR；合入时给 issue #251 添加完成说明 comment 并关闭
