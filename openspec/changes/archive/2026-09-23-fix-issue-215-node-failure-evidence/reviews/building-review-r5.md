# Building Review: fix-issue-215-node-failure-evidence（Round 5 —— post-PASS 定向确认）

## Reviewer
- run id: review-subagent-215-r5
- 时间: 2026-09-24
- 审阅范围: `e892e00..05882d9`（head = `05882d99552f11232be1db7f6e9dbbe23a797049`）
- 前情: R4（`reviews/building-review-r4.md`）判 **PASS**，报 4 条低危；本轮只确认 R4 之后的两笔 post-PASS 改动（`63b098d` 四项修复 + `05882d9` 纯注释），不重做全量审阅。

## Verdict
**PASS**

本批改动**功能正确**（措辞、spec delta、注释订正、JSDoc 同步四项逐条成立），**新增/修改测试均可失败**（9 个变异检查点全部变红，见下），**未破坏 R4 的既有防线**（抽查 4 条核心不变式 + 2 条 R4 已杀变异仍全部变红）。无中等及以上问题。5 条低危见 `## Issues`，均不阻塞。

## 本批改动逐项验证

### 1. 「任务」tab 线索措辞（`web/static/workflow_graph.js:1186-1187` + `design.md:207` 同步）→ **正确**
- 计数口径核实属实：`agent/trace_recorder.py:281` 的 `count_failures` = `iter_failure_steps`，后者收 `llm_error` **加** `status != "ok"` 的 `tool_result`（`:275-278`）；只写「工具失败」确实漏掉 LLM 错误。
- 两分支都已改：`count===1` 分支与默认分支均为「N 次工具/LLM 失败」（`:1186`、`:1187`）。
- 兄弟出口 `web/static/workflow_transcript.js:312` 早已用「N 条工具/LLM 失败（点进去看）」——本批与其对齐，口径统一，无打架。
- `design.md:207` 同步为「（措辞覆盖两种失败口径）」，与实现逐字一致。
- 新增 `test_failure_count_hint_wording_covers_llm_errors_too`（`test_workflow_graph_ux_js.py:528`）对 `count ∈ {1, 3}` 都断言 `工具/LLM 失败`——正好锁住两个分支（M2b 证实）。

### 2. spec delta 首段（`specs/web-ui/spec.md:5`）→ **正确**
- 新增半句「`candidates` 容器形态下该键 SHALL 挂在**每个候选**上而不是容器顶层（容器没有单一的 run，见下方该 Scenario）」与同文件下方 Scenario「候选集形态只带轻量证据」（`:81-88`，「每个候选 SHALL 各自携带 `failure_evidence`」）自洽，且与实现一致（`web/static/workflow_transcript.js:305-315` 逐候选取 `candidate.failure_evidence`）。
- 未破坏 strict validate：`npx @fission-ai/openspec@1.4.1 validate --all --strict` → **30 passed, 0 failed**。

### 3. 浏览器用例补 `_wait_app_ready` 守卫（`test_workflow_graph_browser.py`）→ **有效，但描写不实/覆盖不全**（见 Issues 1–4）
- **有效性成立**：两条改动用例隔离重跑各 3 次 → **6/6 全绿**（`test_task_tab_shows_failure_clue_from_snapshot` 3/3、`test_convo_tab_falls_back_when_backend_message_is_missing` 3/3）。
- **修法本身可证**：R4 实测失败率最高的兄弟用例 `test_convo_tab_lazily_fetches_transcript` 无守卫时我重跑 6 次 → **2 次红**（52.5s / 32.6s，报错落在 `Page.wait_for_selector("…svg.workflow-svg")` 可见性超时）；给它补上同一守卫后 → **8/8 全绿**。故「补守卫能治这个 flake」成立，但本批**没给这条补**（Issues 3）。
- **`state="visible"` 是 no-op**（Issues 2）：实证隐藏元素下 `wait_for_selector` 默认行为与显式 `state="visible"` 同样超时，只有 `state="attached"` 立即解析——该参数是 playwright 默认值，不构成「修法的一半」。

### 4. 注释订正（`agent/subagent/scheduler.py:210-219`）→ **属实，三项事实主张全部实测证实**
- 探针（临时加入后已复原）实跑 foreach 容器（`_SelectiveBoomLLM(["item-1"])`，3 项 1 失败）：容器投影响应 `failure_count = None`、`items_failed = 1`、`status = completed` → 证实注释放的「容器自身没有单一 run，故恒为 `None`；容器级线索由既有的 `items_failed` 承担」。
- 全仓 grep `failure_count` 确认**生产读取方只有** `web/static/workflow.js:1140`（读 `node.failure_count`，即 `NodeState` 侧，`scheduler.py:2796` 投影）；`_ItemRunSlot.failure_count` 除测试（`test_workflow_node_transcript.py:1576`、`test_workflow_node_transcript.py` foreach 用例）外无读者 → 「当前无生产读取方、只被测试消费」属实。
- 写入点确为「`_launch_run` 的同一处埋点」（`scheduler.py:2179` → `_record_failure_count` `:2206-2211`，普通节点与展开项共用 `reuse_state` 身份槽）→ 属实。

### 5. `05882d9` JSDoc 同步（纯注释）→ **确认只动注释、不动行为，且口径一致**
- `git show 05882d9`：仅 `web/static/workflow_graph.js` 一行，位于 `/** … */` 块内（行首 ` * `），`N` 条工具失败 → `N` 条失败（工具失败 + LLM 错误）。
- 与同函数体内注释（`:1182-1183`「计数口径是『工具失败 + LLM 错误』」）及 `count_failures` 实现口径一致；**零行为改动**（函数体、导出面、字符串字面量均未动）。

## 未破坏 R4 不变式的证据

对 R4 已杀的核心变异**抽样重跑**（不采信上轮结论），全部仍变红：

| ID | 变异（行） | 跑的测试 | 结果 |
|---|---|---|---|
| M3 = R4-C1 | `web/session.py:846` `settle("clean")` → `settle("no_trace")` | `test_failure_evidence_clean_is_a_positive_statement` | **变红** ✓ |
| M4 = R4-C17 | `agent/subagent/scheduler.py:1701` 删 `state.failure_count = None` | `test_reset_subtree_clears_stale_failure_count` | **变红** ✓ |
| C15 | `agent/trace_recorder.py:291` 空 trace 返回 `0` | `test_count_failures_distinguishes_no_data_from_zero` | **变红** ✓ |
| C16 | `scheduler.py:2796` 投影写死 `0` | `test_snapshot_carries_failure_count_for_terminal_run` | **变红** ✓ |

R4 关键断言抽查（本批改动涉及的 5 条）**全绿**：
`test_convo_tab_renders_failure_evidence_body`、`test_candidate_rows_show_failure_clues`、
`test_task_tab_shows_failure_clue_from_snapshot`、`test_convo_tab_prefers_backend_message`、
`test_convo_tab_falls_back_when_backend_message_is_missing` → `5 passed`。

**结论**：本批改动没有削弱任何既有防线。

## Issues

### 1. **低**：新增测试注释里的「既有 13 条用例都走这个守卫」不实
证据: `tests/web_tests/test_workflow_graph_browser.py:1096`。
逐 commit 实测该文件守卫覆盖：base `e892e00` = **6** 条、本批 head = **8** 条（本批新增 2 条）；该文件历史上从未出现 13 条守卫用例（扫 `git log -p` 全部 13 个 commit 的 `_wait_app_ready` 计数：0/0/3/4/4/6/6/…）。
该数字**源自 R4 报告原文**（`reviews/building-review-r4.md:245` 亦写「13 条」），本批照抄。
建议: 改成「同文件既有多条用例（本批后 8 条）都走这个守卫」或直接删掉计数。

### 2. **低**：`state="visible"` 是 playwright 默认值，属 no-op，注释/说明容易被读成修法的一半
证据: `tests/web_tests/test_workflow_graph_browser.py:1041`、`:1065`。
实证（临时探针，已复原）：对 `display:none` 的 `svg.workflow-svg`，`wait_for_selector(sel)`（默认）与 `wait_for_selector(sel, state="visible")` **同样** 1.2s 超时，而 `state="attached"` **立即**解析 → 默认 state 即 `visible`。
建议: 保留（显式无害）但别在注释里把它与守卫并列；或删掉以省噪音。

### 3. **低**：本批只给 3 条中的 2 条补了守卫，**失败率最高**的那条仍未补 → 文件级间歇红未清除
证据: `tests/web_tests/test_workflow_graph_browser.py:473`（`test_convo_tab_lazily_fetches_transcript` 正文无 `_wait_app_ready`；diff 仅两处 `+ await _wait_app_ready(page)`）。
- R4 实测该条 **5/6** 单跑红，是它表里最糟的一条；我隔离重跑 6 次 → **2 次红**（52.5s、32.6s），报错正是 `svg.workflow-svg` 可见性超时（与 R4 定位的根因同一句）；补上守卫后 **8/8 绿**。
- 连续两次全量跑 `tests/web_tests/test_workflow_graph_browser.py` 各挂 **2** 条（各次不同），**全部**是无守卫用例；`tests/web_tests/ + tests/agent/subagent/` 全量为 `949 passed, 5 failed`，5 条全是浏览器 flake 且全无守卫。**本批修的两条均未出现在任何失败列表里**——即修法有效，只是覆盖面停在 R4 建议的两条。
不阻塞的理由: R4 已把该 flake 定性为**仓库既有环境性**问题、且非本批引入（`test_multi_session_browser.py`、`test_reconnect_pending_interaction_browser.py` 等其它浏览器文件同样红）。按本轮口径不报为 issue 主体，仅记事实供实现者取舍。
建议（若本轮愿一并解决）: 给该条也补同一守卫；若要根治，应把守卫换成真实就绪信号（见 Issue 4）。

### 4. **低**：`_wait_app_ready` 在本文件实际走**降级路径**（固定等待），docstring 宣称的就绪信号未达成
证据: `tests/web_tests/test_workflow_graph_browser.py:135-138`。
实证（临时探针，已复原）：在本文件 fixture 下打印 `PROBE guard: DEGRADED (no selector) after 5.005s` —— 先等满 5s 选择器超时，再睡 300ms。原因：本文件用例**直派事件 + 注入 `window.__testTab`**，不建/不激活真实 chat tab，`.tab-pane.active .user-input` 从不出现（该元素由 `web/static/chat.js:132` 动态创建）。
故真正起稳定作用的是那 **~5.3s 固定等待**，而非 docstring 说的「就绪信号取『chat 视图出现已激活的输入框』」。这是该文件**既有多条守卫用例的共同行为**（同一 `fake_web_server` fixture），非本批引入，本批只是沿用了这个约定（代价：每次调用 +5.3s）。
建议: 可留待专门清理；若要改，就绪信号应取真实可见信号（例如 workflow-view 的 active class 已稳定），否则守卫语义与注释继续不符。

### 5. **低（口径残差，非本批范围）**：同一「N 次工具失败」口径另有 3 处未同步
证据: `design.md:246`（Q1 行「本 run 内出现 N 次工具失败」）、`tasks.md:20`、`tasks.md:61`（均描述 Q1 区块标题决定）；另 `tests/agent/subagent/test_terminal_honesty.py:737` 的**断言消息**里也引用了旧措辞（仅文案，断言本身有效）。
判定: R4 的 Issue 1 只授权改 `design.md:207` + `workflow_graph.js`，本批已照改；上述 4 处是历史引用，且 `design.md:246` 描述的「区块标题」实际实现为 `失败证据（共 N 条）`（`workflow_transcript.js:258`），与措辞无直接耦合。**不构成缺陷**，仅提示如需彻底统一口径可一并扫掉。

## Test Results

| 命令 | 结果 |
|---|---|
| `uv run pytest tests/web_tests/test_workflow_graph_ux_js.py -q` | **47 passed** |
| `uv run pytest tests/web_tests/test_workflow_graph_browser.py -q` | 25 passed（单次）；另两次全量各 `2 failed, 23 passed`（flakes，见 Issue 3） |
| `uv run pytest tests/web_tests/ tests/agent/subagent/ -q` | **949 passed, 5 failed, 7 skipped**（5 failed 全为浏览器 flake） |
| 5 failed 中的 2 条隔离重跑 ×3 | **3/3 绿** ×2 → 确认环境性 flake，非本批引入 |
| 两条改动用例隔离重跑 ×3 | **6/6 绿** |
| `npx @fission-ai/openspec@1.4.1 validate --all --strict` | **30 passed, 0 failed** |

## 变异验证

基线（未变异）：新用例绿、`clean` 正向声明绿、`_reset_subtree` 清计数绿、browser 三态绿。

| # | 变异（改了哪行） | 跑的测试 | 结果 | 结论 |
|---|---|---|---|---|
| M1 | `workflow_graph.js:1186-1187` 两分支「工具/LLM 失败」→「工具失败」 | `ux_js::test_failure_count_hint_wording_covers_llm_errors_too` | **变红** ✓ | 新用例真能锁措辞 |
| M2 | 仅 `:1187` 默认分支退回「工具失败」 | 同上 | **变红** ✓ | `N>1` 分支被覆盖 |
| M2b | 仅 `:1186` `count===1` 分支改成「1 次失败」（不同措辞） | 同上 | **变红** ✓ | `count===1` 分支被覆盖 |
| M5 | `:1181` 把 `0` 档折叠成计数式线索（0/None/N 三态塌陷） | `ux_js::test_failure_count_hint_separates_no_data_from_zero` + browser 三态 | **双双变红** ✓ | 三态区分有守护 |
| M6 | `:1180` `None` 档不再返回 `null`、改为含「失败」的兜底文案 | 同上两条 | **双双变红** ✓ | 收紧后的 `assert "失败" not in body_join`（`:1065`）有效，非空断言 |
| M3 | `web/session.py:846` `clean`→`no_trace` | `::test_failure_evidence_clean_is_a_positive_statement` | **变红** ✓ | R4-C1 防线仍在 |
| M4 | `scheduler.py:1701` 删 `failure_count = None` | `::test_reset_subtree_clears_stale_failure_count` | **变红** ✓ | R4-C17 防线仍在 |
| C15 | `trace_recorder.py:291` 空 trace 返回 `0` | `::test_count_failures_distinguishes_no_data_from_zero` | **变红** ✓ | 三态口径仍在 |
| C16 | `scheduler.py:2796` 投影写死 `0` | `::test_snapshot_carries_failure_count_for_terminal_run` | **变红** ✓ | 埋点接线仍在 |

共 **9** 个变异检查点（≥ 硬要求 4 条），**无一存活**——本批没有引入假保护。

## 结论

本批 post-PASS 改动（R4 四条低危修复 + `05882d9` 注释同步）**逐项成立、可失败、未破坏既有防线**，判 **PASS**。5 条低危均为注释准确性 / 覆盖面 / 既有约定问题，不影响本 change 的交付物正确性；其中 Issue 3、4 若在归档前顺手处理，可让「浏览器 flake 已治」这条口径更站得住。

审阅期间对 `/tmp/rev-215` 的所有临时改动（探针测试、变异脚本）已 `git checkout -- .` 复原。
