# Building Review: fix-issue-215-node-failure-evidence（Round 1）

## Reviewer
- run id: review-subagent-215-r1b
- 时间: 2026-09-23
- 审阅范围: `1a7df92cbd90ab442342a8481d59857b8c4ebf54`..`c37c267d6fd8c874ed97494f7ff1597edfb1ac1f`
- 工作目录: `/tmp/rev-215`（隔离检出）；审阅结束已 `git checkout -- .`，除本报告与 `.venv` 外无残留

## Verdict
**CHANGES_REQUESTED**

理由：15/15 变异全部被杀、全部 `[x]` 任务有真实实现、spec 七个 Scenario 全覆盖、测试全绿，
未发现假保护、安全漏洞或 spec 承诺未实现；但发现 **1 个中等问题**（重跑复位后 `failure_count`
残留上一轮的值，与 `_reset_subtree` 自身的复位契约不一致，会显示一个不属于「本 run」的失败信号）
+ 若干低级项。中等项修掉即可 PASS。

## Tasks Verification

实现类任务逐条读代码确认（对照 `tasks.md`）：

- [x] 常量与 docstring → `web/session.py:741`（`FAILURE_EVIDENCE_LIMIT=5`）、`:745`
      （`FAILURE_EVIDENCE_PREVIEW_LIMIT=400`）、`:748`（`_TERMINAL_RUN_STATUSES`）、
      `:755`（`FAILURE_EVIDENCE_STATES` 七值）；函数 docstring 说明「为什么不是新采集」`web/session.py:768-797`
- [x] `_failure_evidence(run_or_missing, *, full)` 只遍历不复制 → `web/session.py:796-839`；
      过滤判据在 `agent/trace_recorder.py:258-284`（`iter_failure_steps`），一次 O(steps) 扫描
- [x] 七态枚举 + 各负向态可读文案 → `web/session.py:806-818`（`settle`）+ `:846-857`
      （`_FAILURE_EVIDENCE_MESSAGES`，七键互不相同，测试参数化锁定）
- [x] 条目 bounded：最近 N 条 + 时间正序 + `text_truncated`（非 `observation_truncated`）→
      `web/session.py:835-839`（`failures[-limit:]`）、`:858-881`（`_failure_item`）；
      `llm_error` 的 `status` 合成 `"error"` 在 `:880`
- [x] 三态分支挂载 → `single` `web/session.py:1161`；`candidates` `:1220`；
      `none`（route）`:1114`、`none`（collect/未派发）`:1130-1135`、`none`（state is None）`:1075-1078`；
      下钻 `:1004`
- [x] 终态判据复用既有字面量（D7）→ `web/session.py:748-751` 提为模块级常量 `_TERMINAL_RUN_STATUSES`，
      值 `{completed, failed, cancelled, budget_exceeded, queue_full}` 与 base 版本
      `origin/master:web/session.py:1020` 的 `_foreach_candidates` 字面量逐字一致（已 `git show` 比对）
- [x] `NodeState`/`_ItemRunSlot` 有界计数字段（三态）→ `agent/subagent/scheduler.py:257`、`:215`
- [x] 埋点在 `_await_run` 之后、每 run 一次、`queue_full` 早退不经过 →
      `agent/subagent/scheduler.py:2165-2172`（埋点）、`:2134-2145`（`queue_full` 早退在 `_await_run` 之前 return）
- [x] `_graph_node_projection` 投影 → `agent/subagent/scheduler.py:2787`
- [x] 前端「对话」tab 挂载（三形态共用）→ `web/static/workflow_transcript.js:116`
      （`appendFailureEvidence(host, payload)`）、实现 `:225-263`
- [x] 前端纯函数（state→文案 / 条目→摘要）→ `web/static/workflow_graph.js:1118-1174`
- [x] 「任务」tab 一行快照计数线索 → `web/static/workflow.js:1137-1147`
- [x] 样式 → `web/static/style.css:1753-1778`
- [x] 全部测试任务：逐条在 `tests/web_tests/test_workflow_node_transcript.py:989-1699`、
      `tests/web_tests/test_workflow_graph_ux_js.py:500-565` 找到对应用例，断言非恒真（见「变异验证」）
- [x] 回归 `tests/web_tests/` + `tests/agent/subagent/` → 941 passed, 7 skipped（见 Test Results）
- [ ] 文档 / 验证 / 收尾任务：`tasks.md:96-124` 未勾。核对后**标记诚实**——
      `openspec/specs/**` 本次确实零改动（`git diff --name-only` 空），与「当前规格同步」「快照加法字段」
      两条未勾一致；`known-debt.md` 与 `backlog.md` 的改动已有 `workflow-events.jsonl` seq 1/2 解释事件。
      唯一问题见 Issue 3。

## Issues

- **中**：`failure_count` 未被 `_reset_subtree` 复位，重跑窗口会残留上一轮的失败信号。
  证据：`agent/subagent/scheduler.py:1664-1696` 的复位清单清了
  `status`/`activations`/`verdict`/`targets`/`reason`/`error`/`summary`/`finished_at`（`:1684-1692`），
  **唯独没有 `failure_count`**；该字段定义在 `:257`。该复位函数的 docstring（`:1665-1678`）自述目的正是
  「否则重跑期间前端会显示上一轮的失败因由」——`failure_count` 属于同一类「上一轮的失败因由」。
  实测（隔离检出内直接探针，已还原）：手工置 `state.status="completed"`、`state.failure_count=7` 后调
  `_reset_subtree` → 复位后 `status=pending`、`reason=None`、`summary=""`、`finished_at=None`，
  而 `failure_count` 仍为 `7`；`_graph_node_projection` 据此产出
  `{'id': 'body', 'status': 'pending', 'failure_count': 7}`。
  端到端也观测到该窗口：跑 `route 回边 + body 首轮失败` 的图，逐帧捕获到
  `(status=pending, failure_count=1)` 的帧——「任务」tab 此时会渲染
  `⚠ 本 run 内 1 次工具失败 →「对话」tab 查看`，而该节点本轮**尚未派发**，不存在「本 run」。
  **可达范围如实标注**：该残留是**瞬态**的（重派发后 run 终态时 `:2165-2172` 会覆盖为新值，
  终态快照计数正确）；我**未能**构造出「快照计数与同节点 transcript 相互矛盾」的更强形态
  （需要被复位的节点再次派发且在跑——在我构造的 spin/foreach 图里未触发），故不按阻塞计。
  影响面是普通 `NodeState` 重跑路径；foreach 展开项的 `_ItemRunSlot` 每轮在
  `:1806` 整体重建，不受影响。
  建议：在 `_reset_subtree` 的复位清单里加 `state.failure_count = None`（一行），并补一条断言
  「复位后 `failure_count is None`」的回归测试（现有快照用例都走单轮图，覆盖不到这条路径）。

- **低**：`_failure_evidence(state=X)` 对**未知** state 不报错，而是静默落回 trace 判定。
  证据：`web/session.py:818` 只对 `("not_applicable","unavailable","running")` 三个显式值提前落定，
  其余未知值会继续往下走 `run`/`trace` 分支（实测 `_failure_evidence(None, state="some_new_state")`
  返回 `no_trace`，而非 KeyError 或报错）。当前 5 个调用点全部传字面量、不可达，属健壮性瑕疵。
  建议：在函数开头对 `state is not None and state not in FAILURE_EVIDENCE_STATES` 显式抛
  `ValueError`，或把该集合作为白名单校验（与前端「未知 state 给可读降级」的取舍方向相反，
  但后端这里是**内**部调用面，fail-fast 更合适）。

- **低**：候选行只在 `total > 0` 时显示线索（`web/static/workflow_transcript.js:293-297`），
  候选处于 `running`/`no_trace`/`unavailable` 时该行**什么都不显示**。这与 Q3「负向态也必须各显示
  一行自己的文案，不得退化成『不显示 = 没事』」的**精神**有落差（设计 D6 对 candidates 只要求
  「计数线索」，故与 design 一致，仅记为落差）。建议：确认这是有意收窄；若是，在 design/spec 里
  补一句「candidates 行的负向态不显示线索」以免后续被当成 bug 反复翻修。

- **低**：`tasks.md:96` 是 `- [ ]` 但正文自称「（已完成，含实测探针输出）」。`diagnosis.md` 确实
  有 6 章（Symptom/Reproduction/Evidence/Root Cause/Recommended Direction/Regression Tests）。
  该行未勾且无 `(post-merge)` 标记，归档完成度门禁会判红。建议：勾上（或若确有未完成部分，
  改写文案再说清）。

- **记录（非 issue）**：`_resolve_run` 直接访问 `manager._sessions`（`web/session.py:895-897`）。
  可接受：docstring 给出了理由（`find_run` 对 `run_id=None` 恒返回 None，而前端只在 truthy 时带
  `run_id`），且回落语义与既有 `inspect_transcript` 的 `session.runs[-1]`
  （`agent/subagent/manager.py:1117`）逐字同口径；本模块同层已有 `manager._sessions[...]` 的既有用法。
- **记录（非 issue）**：foreach 容器节点自身的快照 `failure_count` 恒为 `None`（实测），因为埋点写的是
  `_ItemRunSlot` 而容器没有单一 run——符合 Q6 设计（容器级已有 `items_failed` 承担该线索）。

## Test Results

| 命令 | 结果 |
|---|---|
| `uv run pytest tests/web_tests/ tests/agent/subagent/ -q` | **941 passed, 7 skipped, 75 warnings**（193s） |
| `uv run pytest tests/web_tests/test_workflow_graph_browser.py -q` | **20 passed**（懒加载用例 `test_convo_tab_lazily_fetches_transcript` 在内，未变红） |
| `uv run pytest tests/agent/test_trace_recorder.py tests/agent/test_trace_recorder_metrics.py tests/agent/test_error_type_wiring.py tests/agent/test_loop.py -q` | **92 passed**（新增的 `iter_failure_steps`/`count_failures` 未破坏 trace 生产者契约） |
| `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py` | **OpenSpec artifact checks passed** |
| 全部变异 | 15/15 变红（见下） |

无既有用例因新增键变红；未观察到需要隔离重跑的偶发浏览器 flake。

## Spec Scenario 对齐

spec delta（`openspec/changes/.../specs/web-ui/spec.md`）逐条 → 覆盖它的测试/代码：

| Scenario | 覆盖 |
|---|---|
| run 完成但中途有工具失败（`present`） | 测试 `test_failure_evidence_present_on_completed_run_with_tool_failure:989`；真实 HTTP 端到端 `tests/web_tests/test_workflow_control_server.py:219`（走真路由，非直调投影） |
| trace 存在且无失败（`clean`） | `test_failure_evidence_clean_is_a_positive_statement:1050` + message 含「检查」断言 |
| run 仍在运行（`running`） | `test_failure_evidence_running_is_not_no_trace:1071`；判据代码 `web/session.py:814` |
| 终态但无 trace（`no_trace`） | `test_failure_evidence_no_trace_when_terminal_without_trace:1089` |
| trace 存在但 steps 空（`empty_trace`） | `test_failure_evidence_empty_trace_is_not_no_trace:1105` |
| 解析不到 run（`unavailable`） | `test_failure_evidence_unavailable_when_run_record_is_gone:1123`（半合成，注释写明 queue_full 在 workflow 内预期 0 次）+ `test_unknown_node_is_unavailable_not_not_applicable:1665` |
| 结构上不产生 run（`not_applicable`） | `test_failure_evidence_not_applicable_for_route_and_collect:1144` |
| 失败条目超过上限（最近 N / total / truncated） | `test_failure_evidence_returns_most_recent_n_in_time_order:1181`（显式断言 `observed == [fail-5..fail-9]`） |
| 候选集形态只带轻量证据 | `test_candidates_carry_lightweight_failure_evidence:1315`（每候选 ≤1 条 × ≤400）+ `test_item_drilldown_carries_full_failure_evidence:1353`（下钻 5 条完整） |
| 键名与字段（`failure_evidence` / `state` / `total` / `truncated` / `message` / `items`、`type`/`step`/`status`/`error_type`/`tool_name`/`text_truncated`、`llm_error.status` 合成） | `_failure_item:858-881`；测试 `test_llm_error_item_status_is_synthesised:1033`、`test_failure_evidence_tolerates_missing_and_empty_fields:1271` |
| bounded：单条不超 `content_limit` | `test_failure_evidence_truncates_long_text:1211`（输入 30000 字，**前提断言** `len(huge) > TRANSCRIPT_CONTENT_LIMIT` 防恒真）+ `test_failure_evidence_response_is_bounded_under_huge_trace:1237`（300 步 × 30000 字） |
| SHALL NOT 改变前端取数时机（懒加载） | `web/static/workflow.js:1137-1147` 的新线索只读快照 `node.failure_count`，零 `fetch`；浏览器用例 `test_workflow_graph_browser.py:472`（打开面板断言无 `/transcript` 请求）实测 20 passed |
| SHALL NOT 新增采集 / 调 LLM / 写盘 / 改执行状态 | `test_failure_evidence_projection_is_read_only:1296`（投影前后 trace 与快照 JSON 逐字相等） |

未见「spec 写了但没实现」的条款。Q1–Q7 逐项落地核对：Q1（不加 `recovered`，标题走事实表述
`web/static/workflow_transcript.js:245-247`）、Q2（`LIMIT=5` + 载荷 4000 + 前端预览 300
`workflow_transcript.js:253`）、Q3（七态各显示一行，`not_applicable` 除外并给了理由注释
`:227-232`）、Q4（七值判据 `web/session.py:1067-1136`）、Q5（candidates 轻量 / 下钻完整
`web/session.py:1220` vs `:1004`）、Q6（埋点位置 `scheduler.py:2165-2172` + 三态
None/0/N 前端 `workflow_graph.js:1160-1168`）、Q7（`docs/known-debt.md:276-292` 两条死代码，
带 `protected_artifact_explained` 事件 seq 2）。**均如实落地。**

## 变异验证

自建变异驱动（改实现 → 跑对应测试 → 记录 → `finally` 还原并断言文件逐字复原）。
**15 条全部变红，0 条存活，未发现假保护。**

| # | 变异（改了哪一行） | 所跑测试 | 结果 |
|---|---|---|---|
| M1 | `clean` 折叠成 `no_trace`（`web/session.py:832`） | `test_failure_evidence_clean_is_a_positive_statement` | 变红 |
| M2 | `empty_trace` 折叠成 `no_trace`（`:825`） | `test_failure_evidence_empty_trace_is_not_no_trace` | 变红 |
| M3 | route 的 `not_applicable` → `unavailable`（`:1114`） | `test_failure_evidence_not_applicable_for_route_and_collect` | 变红 |
| M4 | `state is None` 的 `unavailable` → `not_applicable`（`:1075-1078`） | `test_unknown_node_is_unavailable_not_not_applicable` | 变红 |
| M5 | 最近 N 条改**最早** N 条（`:836` `failures[-limit:]`→`[:limit]`） | `test_failure_evidence_returns_most_recent_n_in_time_order` | 变红 |
| M6 | 去掉单条文本截断（`:879-880` 去 `[:text_limit]`） | `test_failure_evidence_truncates_long_text` | 变红 |
| M7 | `count_failures` 空 trace 返回 `0`（`agent/trace_recorder.py:281`） | `test_count_failures_distinguishes_no_data_from_zero` | 变红 |
| M8 | `iter_failure_steps` 判据收窄成 `status == "error"`（`trace_recorder.py:283`） | `test_iter_failure_steps_only_yields_failures` | 变红 |
| M9 | `llm_error` 的 `status` 不合成（`session.py:880`） | `test_llm_error_item_status_is_synthesised` | 变红 |
| M10 | candidates 去掉轻量上限（`:835` `limit = 1 if not full ...`） | `test_candidates_carry_lightweight_failure_evidence` | 变红 |
| M11 | 删掉 `_launch_run` 计数埋点（`scheduler.py:2165-2172`） | `test_snapshot_carries_failure_count_for_terminal_run` + `test_snapshot_failure_count_covers_foreach_items` | 2 条均变红 |
| M12 | 前端把 `None` 与 `0` 折叠（`workflow_graph.js:1161`） | `test_failure_count_hint_separates_no_data_from_zero` | 变红 |
| M13 | 删掉 `running` 判定（`session.py:814`） | `test_failure_evidence_running_is_not_no_trace` | 变红 |
| M14 | 未派发节点报 `not_applicable`（`:1134`） | `test_failure_evidence_unavailable_for_never_dispatched_node` | 变红 |
| M15 | 快照去掉 `failure_count` 投影（`scheduler.py:2787`） | `test_snapshot_carries_failure_count_for_terminal_run`（+ 快照键白名单用例） | 变红（1 failed, 1 passed——白名单用例是 `>=` 语义故未红，计数用例红，已覆盖） |

超出要求额外交付的核查：

- **bounded 真的 bounded**：`full=False` 时 `limit=1`、`text_limit=min(4000,400)=400`
  （`session.py:835-836`）；最坏响应 ≈ 候选数上限 200 × （1 条 × 400 字 + 固定字段开销）≈ 90KB 量级，
  与 design D4 的估算一致（我按上限手算 + 测试 `test_candidates_carry_lightweight_failure_evidence`
  断言每条 ≤400 字）。
- **state/message 永远成对**：`_failure_evidence` 有且仅有 5 个 `return`，**全部**走
  `settle()`（`session.py:818/822/825/832/839`），无绕过路径；`_FAILURE_EVIDENCE_MESSAGES` 七键
  互不相同并有参数化测试；`test_failure_evidence_message_always_matches_state:1439` 覆盖
  present/clean/empty_trace/no_trace/running/unavailable 六条路径。
- **`settle` 的 `message` 覆盖不会串台**：`message=` 只在「显式 state」的 3 个调用点传入
  （均为字面量），其余调用点不传，故共享闭包变量不会跨状态泄漏（已用探针确认）。
- **`_resolve_run` 回落**：`run_id` 为 `None` 时回落 `session.runs[-1]`，与
  `inspect_transcript` 同口径（`manager.py:1117`）；`test_drilldown_without_run_id_still_resolves_the_run:1381`
  锁定。
- **快照三态可达性**：`None`（未派发，`test_snapshot_failure_count_is_none_without_usable_trace:1537`）、
  `0`（`test_snapshot_failure_count_is_zero_when_checked_and_clean:1525`）、
  `N`（`test_snapshot_carries_failure_count_for_terminal_run:1509`）三条各自可达且语义正确；
  `queue_full` 早退路径确实绕过埋点（`scheduler.py:2134-2145` 在 `:2165` 之前 return），
  故计数保持 `None`。
- **安全性**：新增前端代码全部经 `el()` → `node.textContent`（`workflow_transcript.js:43-48`），
  对照组 `grep innerHTML` 在 `workflow_transcript.js`/`workflow_graph.js` 均零命中；
  证据文本是工具输出原文，不拼 HTML、不进 `innerHTML`。后端投影只读内存 trace、不落盘、不回显路径。
- **CI 完整性**：`git diff origin/master...HEAD -- .github/ scripts/` 为空——未弱化任何 CI 配置。
