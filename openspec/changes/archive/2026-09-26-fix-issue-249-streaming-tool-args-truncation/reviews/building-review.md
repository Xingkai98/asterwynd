# Building Review: fix-issue-249-streaming-tool-args-truncation

## Reviewer

- run id: `af6475c0-a389-4a96-bf01-97cb960cab71`（独立零记忆 subagent，未继承开发上下文；结论只来自实读代码 / 实跑输出 / change 文档）
- 时间：2026-09-26
- base: `369d99d`（master），被审 head: `497dd55`
- 审阅方法（作者自述一律不作依据）：
  - 逐条核对 `tasks.md` 的 `[x]` 是否真的完成，带 `文件:行号` 证据
  - **在 `/tmp` 建两份独立代码副本**（`/tmp/base-249` = base、`/tmp/head-249` = head），全程未写入被审 worktree（`git diff 497dd55 -- '*.py'` 实测为空）
  - **差分探针**：同一批 40+ 输入分别作用于 base/head，逐字段比对输出
  - **16 组变异验证**（M0–M16），确认测试判别力
  - 独立重跑**全量 pytest**（base + head 两棵树对跑）
  - 独立实跑 OpenSpec strict validate 与 artifact checker
  - 独立构造真实 SSE 路径与 AgentLoop 端到端场景

## Verdict

**PASS**（被审 commit `497dd55`）

代码层面无阻断问题：崩溃在全部路径上确认修掉，合法输入路径**逐字节不变**（差分实测），回归测试有真实判别力（16 组变异全部按预期被杀）。

两条 medium/low 属**文档口径失准**（spec over-claim、复现列号声明不实），审阅期间已在工作树中被并发修正；本报告基于修正后的 head `576f527` 判定。审阅新提的一条建议（补混合响应回归测试）已落实并做变异验证。

### 修复后追加（`576f527`）

审阅结论落地后，作者按 M1 建议补了一条混合响应回归测试
（`test_build_response_mixed_valid_and_truncated_under_max_tokens`），并做变异验证：
删掉 `max_tokens` 丢弃分支后该测试**变红**（判别力成立）。

## 任务逐项验证

| 任务 | 状态 | 核实方式与证据 |
|---|---|---|
| 0.1 diagnosis.md 两条链路 + 列号 | ⚠️ 部分 | 两条链路复现脚本可跑、机制正确；但「列号逐字节一致」在**被审 commit 里是错的**（见 L1，已在 `576f527` 修正） |
| 0.2–0.4 proposal/design/RIR | ✅ | `proposal.md` 有 `research_tier: light` 全字段；`design.md` D1–D6 完整 |
| 1.1 delta Requirement + 4 Scenario | ✅ | `specs/agent-runtime/spec.md` 4 个 `#### Scenario:`，与 `openspec/specs/agent-runtime/spec.md` 逐字一致（脚本核验 `body in main == True`） |
| 1.2 Impact Analysis | ✅ | `proposal.md` 的 `## Impact Analysis` 节 |
| 1.3 spec delta 落地 | ✅ | 同上，verbatim 包含 |
| 1.4 `docs/agent-internals.md` | ✅ | 新增「边界：截断发生在 tool 参数中间」段；代码路径引用正确（`_build_response`/`_build_payload`） |
| 2.1–2.5 测试 | ✅ | `tests/agent/test_anthropic_llm.py` 全部存在（5 条 RED + 2 条回归保护） |
| 2.6 变异验证 | ✅（独立复跑通过） | 16 组变异，判别力成立（见「变异验证实测」） |
| 2.7 无 sleep/墙钟依赖 | ✅ | 新增测试段无 `sleep` / 墙钟断言 |
| 3.1 `_build_response` 分流 | ✅ | `agent/anthropic_llm.py`（`max_tokens` 丢弃 / 否则保留原始串） |
| 3.2 `_build_payload` 降级 `{}` | ✅ | `_parse_replayed_arguments` + 调用点 |
| 3.3 `_stream_events` 补 warning | ✅ | `agent/llm.py`，控制流未变（差分实测 `event_pairing` SAME） |
| 3.4 成功路径零变化 | ✅ | 差分实测逐字节相同 |
| 4.1 原始复现脚本 | ✅ | 照抄 diagnosis 跑：base 两链路 CRASH，head 不崩 |
| 4.2 全量 pytest | ✅ | base + head 两棵树独立对跑（见 CI 完整性） |
| 4.3 OpenSpec strict validate | ✅ | 实跑通过 |
| 4.4 artifact checker | ✅ | 实跑 `OpenSpec artifact checks passed`（exit 0） |
| 5.1 `/review-loop` | ✅ | 本报告即其产出 |
| 5.2 文档影响检查 | ⚠️ | committed 版误写 `docs/known-issues.md`，实际落 `docs/known-debt.md`（见 L2，已在 `576f527` 更正） |
| 5.3 backlog | ✅ | `docs/openspec-change-backlog.md` 第十六批，含 `backlog_updated` 事件 |
| 5.4/5.5 归档/PR | ⬜ 未勾 | 未到阶段，合理 |

受保护路径事件三件齐备：`workflow-events.jsonl` 的 `current_spec_synced`（`openspec/specs/agent-runtime/spec.md`）、`backlog_updated`、`protected_artifact_explained`（`docs/known-debt.md`）。

## Issues

### 严重

无。

### 中

**M1. 被审 commit 的 spec Scenario 1 对 max_tokens 分支的描述强于实现（over-claim）｜已在 `576f527` 修正**

- 证据：committed `openspec/specs/agent-runtime/spec.md`（`git show 497dd55:...`）写的是无条件
  `- **AND** AgentLoop SHALL 走既有续接路径（追加续接消息并继续迭代），而不是终止 run`。
- 但实现只在「响应中没有别的完整 tool call」时才续接。实测混合响应（1 个合法 + 1 个截断，`stop_reason=max_tokens`）：
  合法 call 被保留执行，`response.tool_calls` 非空 → `agent/loop.py:713` 的 `if not response.tool_calls:` 为假 → **不追加续接消息**。
- 该场景**无测试覆盖**（原 `test_build_response_truncated_tool_call_max_tokens_drops_call` 只用单个截断 block）。
- 处置：`576f527` 已把 spec 改为两条并列 AND（无其它完整 call 时续接 / 有时照常执行），与实现一致；
  并按本条建议**补了混合响应回归测试**（变异验证：删丢弃分支后变红）。

### 低

**L1. 被审 commit 的 `diagnosis.md` 复现列号声明与实际输出不符｜已在 `576f527` 修正**

- committed 版用 `head[:7811]`，而 `len(head)==7726`，切片是 no-op；实跑报错为 `column 7726 (char 7725)`，
  **不是**文档写的 `column 7811 (char 7810)`，字面「逐字节一致」不成立。
- 处置：`576f527` 已把构造改为 `'{"pad":"' + 'x'*7793 + '","goal":"'`（`len==7811`），实测报错确为 `column 7811 (char 7810)`，
  并补了「列号是构造出来的、不声称与原始响应字节相同」的诚实注脚。
- 说明：受保护路径事件 reason 是 append-only，无需回改；后续勿复述旧口径。

**L2. tasks 5.2 在 committed 版引用了错误的文件｜已在 `576f527` 更正**

- `docs/known-issues.md` 是机械豁免模式表（非叙述记录处），本 change 的记录实际落在 `docs/known-debt.md`。属文档笔误，无功能影响。

**L3. 成功路径的「逐字节不变」断言弱于其声明（不阻塞）**

- `test_build_response_valid_tool_call_unchanged` 用 `_json.loads(...) == {...}` 比较，会放过序列化格式变更：
  变异 M13（`json.dumps(args, sort_keys=True, indent=1)`）**未被杀死**。
  实际行为是对的（差分实测 base/head 输出逐字节相同），仅测试未固化「逐字节」这一条。弱，可接受。

**L4. `_parse_replayed_arguments` 的返回标注 `-> dict` 名不符实（nit）**

- 对合法非 dict JSON（如 `[1,2]`、`123`）会原样返回非 dict。这与**修复前完全一致**（差分核验 base/head 相同），
  **不是回归**；仅类型标注不精确。

**L5.（既有行为，非回归）不完整 tool block 的 `blk["id"]`/`blk["name"]` 直接下标**

- 保留原始串分支用直接下标，若 `content_block_start` 缺 `id`/`name` 会 KeyError。但成功路径（base）同样直接下标，非本次引入。

## 变异验证实测

在被审 worktree 的**两份 `/tmp` 副本**上做，worktree 源码未被触碰。

| 变异 | 期望 | 实测 |
|---|---|---|
| M0 baseline | 绿 | 25 passed ✅ |
| M1 还原 `_build_response` 裸 `json.loads` | 红 | 4 failed ✅ |
| M2 还原 `_build_payload` 裸 `json.loads` | 红 | 1 failed ✅ |
| M3 删 `max_tokens` 丢弃分支 | 红 | 3 failed ✅ |
| M4 解析失败一律丢弃（删 else 分支） | 红 | 1 failed ✅ |
| M5 保留 call 但 `arguments="{}"` | 红 | 1 failed ✅ |
| M6 `stop_reason` 条件取反 | 红 | 4 failed ✅ |
| M7 删空串保护 `if json_str else {}` | 不杀（未覆盖，行为仍正确） | 25 passed（预期，非缺陷） |
| M8 重放把合法非 dict 降级 `{}` | 不杀（差分另证基线不变） | 25 passed ✅ |
| M9 静音全部新 warning | 不杀（纯日志） | 25 passed ✅（证明日志不含控制流） |
| M11 `max_tokens` 分支重新解析（不丢弃） | 红 | 3 failed ✅ |
| M12 用未映射值比较 `stop_reason` | 红 | 3 failed ✅ |
| M13 成功路径 `sort_keys+indent` | 不杀（断言弱，见 L3） | 7 passed ⚠️ |
| M14 成功路径恒序列化 `{}` | 红 | 1 failed ✅ |
| M15 重放恒返回 `{}` | 红 | 1 failed ✅ |
| M16 空 `json_str` → `None` | 不杀（无测试；行为实测 SAME） | 7 passed ⚠️ |

**最关键的判别力证据**：把 head 版测试文件原样拷到 base 树跑 → **恰好 5 条 RED**
（`test_build_response_truncated_tool_call_max_tokens_drops_call`、
`test_build_response_truncated_tool_call_non_truncation_keeps_raw`、
`test_build_payload_truncated_arguments_degrades_to_empty`、
`test_stream_chat_truncated_tool_json_does_not_crash`、
`test_agent_loop_survives_truncated_streaming_tool_call`），与 `tasks.md` 2.6 声明的「5 条 RED」吻合。

## 独立复现结果

**差分探针**（40+ 用例，同一批输入分别作用于 base/head）：

- **合法输入路径 100% SAME**，包括 `valid_dict` / 分片拼接的合法 JSON / 合法非 dict（`[1,2]`）/ `int` / `"x"` / `null` / `true` /
  空 `json_parts` / 非 str 类型 arguments —— `arguments` 输出**逐字节相同**（如 `'{"b": 2, "a": 1}'` 两侧一致，证明未做排序或重格式化）。
- **所有 DIFF 都只落在「修复前会抛 JSONDecodeError」的输入上**，无一例外。

**真实 SSE 路径**（`_chat_stream` + `_stream_events`，mock httpx）：

- `trunc + max_tokens` → 不崩，丢弃，`stop_reason=max_tokens`；
- `trunc + tool_use/end_turn`、**连接中断（无 message_delta）** → 不崩，保留原始串；
- 坏 data 行的 `event_pairing` 行为 base/head 完全相同（新增日志未污染控制流）。

**AgentLoop 端到端**（真实 `AnthropicLLM` 流式）：

- base：1/2/4/6 号场景 **run 直接崩 `JSONDecodeError`**；head：全部 `run_ok=True`。
- **Spec 关键不变量「消息历史 SHALL NOT 出现无配对 `tool_result` 的 `tool_use` block」成立**：
  全部 6 个场景无孤立 `tool_use` / `tool_result`；`max_tokens` 丢弃后历史里连 `tool_use` 都没有。
- 截断反复发生（3 轮 `max_tokens`）也不崩，正常走到 `end_turn`。
- 混合响应（1 合法 + 1 截断）配对仍闭合。

**CI 完整性（全量 pytest 独立对跑）**：

- HEAD：`10 failed, 3054 passed, 10 skipped`
- BASE：`11 failed, 3046 passed, 10 skipped`
- **HEAD 的 10 条失败是 BASE 11 条的严格子集**，无一条因本 change 新增。逐条核因：`test_mcp_manager.py` ×5（测试环境 `uv` 不在 PATH，导出后重跑 11 passed）、
  `test_sandbox_backends.py::test_contract[docker]`（本机无 docker）、`test_tree_sitter_extracts_java_and_kotlin_symbols`（缺 grammar）、
  `test_persistent.py::TestFindScopeRoot::*` ×2（本机 `/tmp` 是 git 仓库）、浏览器用例（playwright flake）。
- 提醒：全量跑时始终 `export PATH=/home/happy/.local/bin:$PATH`，否则 mcp 5 条会误报。

## 审阅自查

- 对 worktree **零写入**：变异与探针全部在 `/tmp`；`git diff 497dd55 -- '*.py'` 实测为空。
- 未使用 `AskUserQuestion`（按派发要求）。
- 结论只来自实读代码、实跑输出与 change 文档；作者自述的「5 条 RED」「逐字节不变」等均被独立复算，未采信转述。
