# Building Review: web-reconnect-pending-interaction

- reviewer run id: `review-web-reconnect-pending-interaction-20260917-r4`
- 审阅员: 独立零记忆 subagent（review-loop，issue #90）
- base sha: `9b14b5a`（与 master 的 merge-base 上、进入实现前的基线）
- head sha: `387287d`（收口验证轮的 HEAD；报告 hash 绑定见同名 manifest）
- 轮次: 4 轮（R1 CHANGES_REQUESTED → R2 PASS → R3 CHANGES_REQUESTED（R2 修复引入的 2 项）→ R4 PASS）
- verdict: **PASS**

## 结论

change `web-reconnect-pending-interaction`（issue #195）的核心链路——pending 载荷保留与原子访问器、
显式超时 fail-closed、session 级 `SessionEventChannel` 广播/定点发送、重连补发顺序
（`session_resumed → session_history → 卡片 → workflow 快照`）、前端卡片幂等与终态单调——经四轮
独立零记忆 subagent 审阅，**全部通过**。

四轮共发现 **19 个问题**（3 中 / 16 低），**全部已修复并补回归测试**；每条修复都做过变异验证
（改坏实现 → 对应测试变红 → 还原），未留下「实现坏掉测试也不报」的假保护。

| 轮次 | 发现 | 处置 |
|---|---|---|
| R1 | 10（3 中 7 低） | CHANGES_REQUESTED → 全部修复 + 回归（commit `61ad07c`）|
| R2 | 6（全低） | PASS；仍修复 6 项（commit `8373d54`）|
| R3 | 2（1 中 1 低，均由 R2 修复引入） | CHANGES_REQUESTED → 修复 + 回归（commit `387287d`）|
| R4 | 1（低，覆盖缺口） | PASS；缺口按 R4 建议用 `capfd` 闭环 |

## 逐条任务验证

42 项 tasks（0.1–6.9）逐条核验，**无假勾选**：0.x 的 grill 证据与用户确认、1.x 的载荷/超时/配置、
2.x 的 session 级出口、3.x 的重连补发、4.x 的前端幂等与反馈、5.x 的测试补齐、6.x 的收尾全部落实。
R1 报告逐条给出 `文件:行号` 证据（见 `/tmp/building-review-round1.md` 的 `## 逐条任务验证`）；
R2–R4 复核增量改动未破坏这些结论。

## 四轮 issue 汇总与处置

### 第 1 轮（10 项）

| # | 问题 | 严重度 | 位置 | 修复 |
|---|---|---|---|---|
| 1 | `reset` 换掉 session 后未把连接重绑到新出口 → 该连接永久收不到任何 run 事件（实测复现，本 change 引入的回归）| 中 | `web/server.py` reset 分支 | 补 `bind_pending_interaction_channel`；回归 `test_reset_rebinds_connection_to_new_session`（变异打红）|
| 2 | 终态非单调：落败者的 `unavailable` 回执被广播，改写胜出方已 approved 的卡片 | 中 | `web/session.py` + `chat.js` | 服务端 `_deliver_interaction_receipt`（接受广播 / 拒绝只回提交者）+ 前端终态守卫；两侧回归（变异打红）|
| 3 | M2「drain 永不退出」专项测试对实现不敏感（改回 break 仍全绿）| 中 | `tests/web_tests/test_session.py` | 用 GatedLLM 重写，变异打红 |
| 4 | YAML `true` 被当正整数接受 → 静默退化成 1 秒超时 | 低 | `agent/config.py` | `_parse_timeout_seconds` 拒绝 bool；回归（变异打红）|
| 5 | 非 JSON 帧被当断连 → 该连接本轮 run 后续事件全丢 | 低 | `web/session.py` | 畸形帧只忽略并继续；回归 |
| 6 | 断连后 run 跑完 endpoint 抛未捕获 `RuntimeError`（traceback 噪声）| 低 | `web/server.py` | 内层 `except RuntimeError: break`（R2 收窄作用域，R4 补 `capfd` 回归）|
| 7 | 提问卡片「未连接」提示在重连成功提交后不消失 | 低 | `chat.js` | 成功分支清 hint；回归（变异打红）|
| 8 | ping 分支被误判为死代码 | 低 | `web/session.py` | 复核确认**不是**死代码（run 期间主循环阻塞在 `run_session`，只有 session 级接收任务能回 pong），补 `test_ping_is_answered_while_run_is_in_progress` |
| 9 | 超时默认值双份维护 + 补发载荷多余 copy | 低 | `web/session.py` / `agent/config.py` | 引用单一来源常量；去掉一层 copy |
| 10 | 文档影响漏点（W06 讲稿未随语义更新）+ 勾选状态不一致 | 低 | `docs/interview-script/walkthrough/W06-security.md` | 补 pending 超时/fail-closed 口径；勾选 6.1–6.6 |

### 第 2 轮（6 项，全低）

| # | 问题 | 修复 |
|---|---|---|
| N1 | 二进制帧（starlette 文本模式取 `message["text"]` 抛 `KeyError`）仍被当断连 | 并入畸形帧例外清单；回归 `test_binary_frame_does_not_detach_live_connection`（变异打红）|
| N2 | `except RuntimeError` 覆盖整个主循环体，会吞掉循环内真 bug | 收窄到只包 `ws.receive_json()` 一行 |
| N3 | `reset` 只重绑 run 出口、没重绑 workflow 图出口 | 补 `bind_workflow_graph_channel`；回归 `test_reset_rebinds_workflow_graph_channel`（变异打红）|
| N4 | `test_run_completes_when_connection_drops_mid_run` 对 drain 变异不敏感 | 修正 docstring 写明覆盖边界（drain 不变量由 `test_session.py` 那条保护）|
| N5 | RuntimeError 修复与 hint 清除缺回归 | hint 改为「同卡残留提示后提交」断言（变异打红）；RuntimeError 见 R4 |
| N6 | W06 讲稿行号漂移 | 改为 `session.py:172`（审批）/`:263`（提问）/`:127`（类定义）|

### 第 3 轮（2 项，均由 R2 修复引入）

| # | 问题 | 修复 |
|---|---|---|
| R3-1 | 中：R2 新加的 hint 断言等待 `Submitted` 这个约 12ms 瞬态文案，负载下必 flaky（R3 实测 8/8 红）| 改为轮询稳定终态（`btn.disabled && hint.hidden && hint.textContent === ''`）；负载 6/6 + R3 复现命令 8/8 全绿，变异仍打红 |
| R3-2 | 低：W06 行号 `server.py:399` / `session.py:127-196` 仍不准 | 改为 `587-588` / `127-217` |

### 第 4 轮（1 项，低，覆盖缺口）

| # | 问题 | 修复 |
|---|---|---|
| R4-1 | R3 期间作者删除的 `test_no_runtime_error_escapes...` 被判「恒真」的结论过度概括——`caplog` 抓不到（uvicorn 对 `"uvicorn"` logger 设了 `propagate=False`），但 stderr 稳定可见 | 用 `capfd` 补回回归；R4 实测变异红 / 生产绿且 3/3 稳定 |

## Issues

**无遗留 issue。** 四轮发现的问题全部修复；最终轮（R4）收口验证 verdict 为 PASS，
其新发现的 1 项（覆盖缺口）已在本轮闭环。

## 变异验证记录（跨轮汇总）

每条修复都做了「改坏实现 → 确认测试变红 → 还原」的变异验证，关键结果：

| 变异 | 目标测试 | R1 | R2 | R3 | R4 |
|---|---|---|---|---|---|
| 删补发 `build_pending_interaction_payloads` | 重连补发序列断言 | 红 ✅ | | | |
| broadcast 只发单个 handle | `test_terminal_state_broadcasts_to_all_connections` | 红 ✅ | | | |
| drain 改回 `if not channel.handles: break` | `test_drain_keeps_consuming_after_all_connections_detached` | 红 ✅ | 红 ✅ | | |
| 删 `currentAssistantMsg = null` | 流式增量落 DOM | 红 ✅ | | | |
| 删 reset 分支重绑 | `test_reset_rebinds_connection_to_new_session` | | 红 ✅ | | |
| 落败者回执改回无条件广播 | `test_loser_receipt_is_not_broadcast_to_other_connections` | | 红 ✅ | | |
| 删前端终态守卫 | `test_loser_receipt_does_not_rewrite_winner_card` | | 红 ✅ | | |
| 删畸形帧例外（文本帧） | `test_malformed_frame_does_not_detach_live_connection` | | 红 ✅ | | |
| 删 bool 拒绝 | `test_parse_web_pending_interaction_timeouts_reject_bool` | | 红 ✅ | | |
| 删 `KeyError`（二进制帧） | `test_binary_frame_does_not_detach_live_connection` | | | 红 ✅ | |
| 删 reset 的图出口重绑 | `test_reset_rebinds_workflow_graph_channel` | | | 红 ✅ | |
| 删 hint 清除 | `test_question_submit_when_ws_down_shows_feedback` | | 绿 ❌→修 | 红 ✅ | |
| `except RuntimeError` 改 re-raise | stderr 断言（capfd） | | 绿 ❌ | 绿 ❌ | 红 ✅ |

末列的「绿 ❌」正是「发现测试无效 → 重写 → 再变异」的闭环：每一条最终都落到实现敏感的断言上。
所有变异均已还原；四轮报告的 `git status` 均为 clean。

## 稳定性抽查

- 浏览器契约测试（8 条）连续 3 遍：3/3 全绿（约 25s/遍）。
- 原先 flaky 的 `test_question_submit_when_ws_down_shows_feedback`：R3 的 6 路负载复现命令 **8/8 绿**（修复前 8/8 红）；
  R4 独立复跑 6 路并发 6 份 **6/6 绿**、累计 25/25 绿。
- 服务端重连测试文件（17 条）连续多轮全绿，无 flaky。

## 全量测试与门禁（最终轮复核）

- `uv run pytest -q -p no:randomly` → **2745 passed, 8 skipped, 0 failed**（约 3.4 分钟）。
- `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` → 30/30 通过。
- `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py` → 通过。
- benchmark smoke（`--agent fake`）通过；CI 的 `benchmark-gate`（`gate-smoke` 基准回归）PASS。
- 最终 `git status --porcelain` 为空，HEAD 未被审阅过程改动。
