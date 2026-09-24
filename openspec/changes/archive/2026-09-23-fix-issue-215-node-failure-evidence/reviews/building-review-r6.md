# Building Review: fix-issue-215-node-failure-evidence（Round 6 —— post-PASS 测试基础设施定向确认）

## Reviewer
- run id: review-subagent-215-r6
- 时间: 2026-09-24
- 审阅范围: `05882d9..91ce796`（head = `91ce7968583ece6bb30964de3bca9a44f64c23f2`）
- 前情: R4 / R5 均判 **PASS**。本轮只确认 R5 之后唯一一笔 post-PASS 改动 `91ce796`（浏览器测试基础设施 + 注释如实化）；不重做全量审阅，不审 R5 低 5（实现者已声明为口径残差、非本批范围）。

## Verdict
**PASS**

本批改动**功能正确**（`_ensure_workflow_view` 确实确定性消除竞态）、**不旁路产品行为**（走的是测试自身 pre-existing 的 `window.__testTab.onWorkflowStarted` harness，未新增旁路；反证：改坏真实 render/auto-open 时三条用例**仍变红**）、**未破坏既有防线**（R4/R5 两条核心变异重跑仍红）、**无常驻 flake**（涉及用例隔离 15/15、整文件两次 25 passed）。3 条低危为注释刀口指向 + 一条**既有**覆盖空白，均不阻塞。

## 本批改动逐项验证

### 1. 新增 `_ensure_workflow_view`（`tests/web_tests/test_workflow_graph_browser.py:141-152`）→ **正确，确定性成立**
- **确定性来源经产品端核实**：产品里 workflow 视图唯一的自动切换入口是 `web/static/chat.js:653-655`（`owner.onWorkflowStarted = () => switchToWorkflowView()`），而 `switchToWorkflowView`（`chat.js:308-312`）尾部调 `showView('workflow')`（`:311`）。**没有任何产品定时器/监听器会周期性地把 workflow-view 摘掉**（`showHub()` 只在 `chat.js:354`、`:2081`、`:2099` 三处触发，均为初始化/用户点击）。故竞态是「chat.js 的异步 `init()` → `showHub()` 把 active 摘到 hub，与测试派发事件的先后」一次性问题；派发之后调一次 `__testTab.onWorkflowStarted()` 把视图拉回 active，一旦拉回就**不会再被摘**。helper 名不虚传。
- **只替换了旧的 `wait_for_selector(svg, state="visible")`**：两条原调用点（`test_task_tab_shows_failure_clue_from_snapshot`、`test_convo_tab_falls_back_when_backend_message_is_missing`）里的 `wait_for_selector(..., state="visible")` 被删（见本批 diff `-` 行），helper 末行 `:152` 的 `wait_for_selector(..., state="visible")` 就是同一守卫的搬迁，故**本批没有叠加**固定等待预算。
- 未给其余 ~15 条用例补守卫，与本批范围（R5 低 3）一致，且这些用例沿用旧写法不受本批影响。

### 2. `test_convo_tab_lazily_fetches_transcript` 补 `_wait_app_ready` + 守卫（`:498`、`:500`）→ **正确**
- 该条守护的是 spec 要求的懒加载不变式（打开「任务」面板不触发 transcript 请求，切「对话」才触发），补守卫方向正确、无副作用。

### 3. 三处 `state="visible"` 前改用 `_ensure_workflow_view` → **正确**（见上文 1）

### 4. 注释如实化（`:1108-1113`）→ **「13 条」假话确已删除，但新注释刀口指向有 2 处错位**（低危，见 Issues 1-2）
- 原「既有 13 条用例都走这个守卫」已删，改为不写具体条数（`不写具体条数：它会随用例增减漂移，写死即成假话`）——方向对，符合 R5 低 1 的建议。
- 但新注释**同一段**留下两处与实际行号不符的指向，且这次的「照抄」问题从数字变成了位置（详见 Issues）。

## 是否旁路/掩盖产品行为（重点）

**结论：不旁路、不掩盖。** 这一节是本轮的核心挑战点，用三个反证实验证伪「helper 掩盖产品缺陷」的假设。

**1. helper 走的 harness 入口是 `_push_workflow_event` 里 pre-existing 的注入，本批一行未改。**
`git show 05882d9:` 与 head 的 `:104-116`（`window.__testTab` 的构造 + `onWorkflowStarted` 注入）**逐字相同**。即：本批只是**调用**了原来就存在、且原来就在每次 `_start_workflow` 里被产品路径 `handleWorkflowEvent` 回调的 harness 入口（`chat.js:654` 给真实 tab 装的就是同一个 hook），没有引入新的旁路。

**2. 反证实验 M-A：把"图永远画不出来"变成真值，helper 不救。**
将 `web/static/workflow.js:614` 的 `svg.setAttribute('class', 'workflow-svg')` 改为 `'workflow-svg-MUTANT'`（真实渲染路径仍在，只是测试选择的 class 永不匹配）：
→ 三条 helper 用例 **全部变红**（`3 failed in 139.83s`）。**未掩盖「svg 真的不可见」**——helper 只在「已被渲染但被 hub 摘了 active」时修复，对「从未渲染」一律超时报警。

**3. 反证实验 M-B：把产品自动打开回调关掉。**
将 `workflow.js:83` 的 `if (tab === activeTab && typeof tab.onWorkflowStarted === 'function')` 改为 `if (false)`：
→ 三条 helper 用例（head）**全部变红**；`test_workflow_view_auto_opens_and_draws_svg` **变红**；**且把 base 版本 `05882d9` 的同样三条拿来跑，同样全红**。
- 说明：本批**没有**削弱这三条对「产品先把视图打开」的依赖——base 与 head 在该变异下行为一致。本批只是把原来在 A 点（事件后等待）检测到的断裂，移到 B 点（`_ensure_workflow_view` 调用）检测，检测能力**等价**。
- 因此对审阅提示里担心的「helper 会不会让 `test_workflow_view_auto_opens_and_draws_svg` 这类产品行为断言失去意义」：**不会**。该条**根本没走 helper**（它走 `_push_workflow_event` → 产品 `handleWorkflowEvent` → 产品 `tab.onWorkflowStarted()` 回调 → 产品 `switchToWorkflowView()` → `showView('workflow')`），M-B 下它照红。它是**唯一**端到端锁「事件 → 产品自动跳视图」的用例，本批未触碰。

**4. 对 R5 低 3/低 4 口径的呼应（上下文，非本批缺陷）**：`_ensure_workflow_view` 引入的 `window.__testTab.onWorkflowStarted` 走的是 harness 直接可见性操作，而**非**真实产品的 `switchToWorkflowView`。但这是本文件**既有**的测试设计（R5 低 4 已记 `_wait_app_ready` 在本 fixture 走降级路径），本批沿用，未扩大旁路面。真实产品的自动跳转由 `test_workflow_view_auto_opens_and_draws_svg` 覆盖（M-B 下变红），分工清晰。

## 未破坏既有防线的证据

对 R4/R5 已杀的两条核心变异**抽样重跑**（不采信上轮结论），均仍变红：

| ID | 变异（行） | 跑的测试 | 结果 |
|---|---|---|---|
| M3 = R4-C1 | `web/session.py:846` `settle("clean")` → `settle("no_trace")` | `test_workflow_node_transcript.py::test_failure_evidence_clean_is_a_positive_statement` | **变红** ✓ |
| M4 = R4-C17 | `agent/subagent/scheduler.py:1701` 删 `state.failure_count = None` | `test_terminal_honesty.py::test_reset_subtree_clears_stale_failure_count` | **变红** ✓ |

两条基线先确认绿（`2 passed`），加变异后 `2 failed` — 既有防线未削弱。

## Issues

### 1. **低**：新注释的 `state="visible"` 刀口指向悬空（被描述的行已删）
证据: `tests/web_tests/test_workflow_graph_browser.py:1108`。
注释写「注：**本行末尾**的 `state="visible"` 是 playwright 的**默认值**（no-op）」，但该 `state="visible"` 那行在本批**已被删除**（本批 diff 里 `-    await page.wait_for_selector("#workflow-canvas svg.workflow-svg", state="visible")`）。全文件 `state="visible"` 仅剩 `:152`（helper 内）、`:842`、`:891`、`:1006`、`:1110`（本条注释自身）——**本条用例正文里没有任何 `state="visible"` 行**。建议: 删掉这条注释，或改为泛化表述（「本文件多处 `state="visible"` 是 playwright 默认值 no-op，治竞态的是 `_wait_app_ready` + `_ensure_workflow_view`」）。

### 2. **低**：同段注释「上一行的 `_wait_app_ready`」指向错行
证据: `tests/web_tests/test_workflow_graph_browser.py:1109`。
注释说「真正治竞态的是上一行的 `_wait_app_ready`」，但 `_wait_app_ready` 在 `:1116`（下方第 7 行），它「上一行」（`:1107`）是 `wait_for_function`。建议改为「下方 `_wait_app_ready(page)` + `_ensure_workflow_view(page)` 两道」。

### 3. **低（口径残差，**非本批引入**）**：产品 `switchToWorkflowView` 无行为级测试
证据: `web/static/chat.js:308-312`。
反证实验 M-C：把它函数体的 `showView('workflow')` 改成 `showView('chat')`（**产品自动打开到错误视图**，对头号交付物是实质回归）→ `test_workflow_view_auto_opens_and_draws_svg` **仍 pass**。原因：该函数仅在 `chat.js:654` 被引用，而全部浏览器用例都直派事件 + 用 harness 的 `onWorkflowStarted`，从不走真实 `chat.js` 的 ws→`handleTabEvent`→654 回调路径；唯一提及 `switchToWorkflowView` 的测试是 `tests/web_tests/test_server.py:454`，**只断言脚本文本含该字符串**，非行为断言。
**定性**: 这是 R5 低 4（`_wait_app_ready` 走降级路径、「真实 ws 路径无覆盖」）的**具体后果之一**，**既有且非本批引入**（base 同样如此）。本批改动经 M-B 证明**未缩小**现有覆盖，故不构成本批缺陷；仅记事实，供后续专门清理（若要根治，需一条走真实 ws 的端到端用例，或对 `switchToWorkflowView` 补行为断言）。

## Test Results

| 命令 | 结果 |
|---|---|
| 三条 helper 用例隔离重跑 ×5（`test_convo_tab_lazily_fetches_transcript` / `test_task_tab_shows_failure_clue_from_snapshot` / `test_convo_tab_falls_back_when_backend_message_is_missing`） | **15/15 PASS** |
| `uv run pytest tests/web_tests/test_workflow_graph_browser.py -q`（第 1 次） | **25 passed**（101.20s） |
| 同上（第 2 次） | **25 passed**（169.47s） |
| 未加守卫对照：`test_convo_tab_lazily_fetches_transcript` 恢复 `state="visible"` 写法单跑 ×8 | 8/8 PASS（本地复现不出该 flake，见下） |
| R4/R5 核心变异 M3 + M4（`session.py:846`、`scheduler.py:1701`） | 基线 2 passed → 变异后 **2 failed** ✓ |

## 变异验证（本批防线的反证）

基线（未变异）：三条 helper 用例绿、`auto_opens` 绿。

| # | 变异（改了哪行） | 跑的测试 | 结果 | 结论 |
|---|---|---|---|---|
| M-A | `workflow.js:614` svg class → `'workflow-svg-MUTANT'` | 三条 helper 用例 | **3 failed** ✓ | helper 不掩盖「svg 从未渲染」 |
| M-B | `workflow.js:83` 产品自动打开 `if (...)` → `if (false)` | 三条 helper 用例 + `auto_opens` | head **4 failed** ✓；base 三条同样 **3 failed** ✓ | 未削弱对产品自动打开的依赖 |
| M-C | `chat.js:311` `switchToWorkflowView` 内 `showView('workflow')` → `showView('chat')` | `auto_opens` | **pass**（既有空白，非本批引入） | 见 Issue 3 |
| M3 | `web/session.py:846` `clean`→`no_trace` | `failure_evidence_clean_is_a_positive_statement` | **变红** ✓ | R4-C1 防线仍在 |
| M4 | `scheduler.py:1701` 删 `failure_count = None` | `reset_subtree_clears_stale_failure_count` | **变红** ✓ | R4-C17 防线仍在 |

**关于 flake 的说明**（按本轮口径）：未加守卫的对照跑 8 次全绿，**本地复现不出** R4/R5 观察到的 2/6 红——该 flake 与机器负载/时序相关，属仓库既有环境性问题，本批正是其缓解手段。三条涉及用例在 head 下 **15/15 绿 + 整文件两次 25 passed**（无 flake），可判「本批治住了涉及用例的 flake」；剩余 ~15 条未补守卫用例的状态与 R5 一致（R5 低 3），不属本批范围。

## 结论

`91ce796` 这笔测试基础设施改动**正确、确定、不旁路产品行为、未破坏既有防线**，判 **PASS**。三条低危中，Issue 1/2 是本批新注释的刀口指向问题（可一并改掉，不影响合并），Issue 3 是既有覆盖空白（与本批正交）。未发现中等及以上问题。

审阅期间对 `/tmp/rev-215` 的所有临时改动（变异脚本、对照改写）已 `git checkout -- .` 复原，最终 `git status` 仅剩未跟踪的 `.venv`。
