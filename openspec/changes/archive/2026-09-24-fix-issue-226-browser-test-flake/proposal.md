# Proposal: 浏览器测试的时序 flake 根治（fix-issue-226-browser-test-flake）

关联跟踪 issue：[#226](https://github.com/Xingkai98/asterwynd/issues/226)（【debt】test_workflow_graph_browser.py 负载下不稳定：全量跑时整文件成片失败，隔离跑全绿）。

## Change Type

- primary: bugfix
- secondary: []

## Why

issue #226 记录 `test_workflow_graph_browser.py` 在全量跑时成片失败、隔离跑全绿，失败数逐次波动，**根因未定位**（issue 自己明确「不要照抄猜测当结论」「先拿到失败正文」）。本次定位从 CI 日志取证并**用注入延迟（非人为加压）确定性复现**，结论是两个**独立**的 flake，同属「异步初始化 / WebSocket 握手的时序在负载下漂移 → 测试缺就绪屏障」，且**均为测试侧缺陷，不是生产 bug**。

### 根因 A：`test_multi_session_browser.py` 三条 —— 消息根本没发出去

2026-09-24 master CI（run `35949416936`，job `107474509631`）失败正文：

```
FAILED test_multi_tab_independent_messages                      wait_for_selector(".tab-pane.active .message.assistant") timeout 30000ms
FAILED test_multi_tab_exit_does_not_affect_other_tab_reconnect  wait_for_function timeout 30000ms
FAILED test_multi_tab_approval_isolation                        wait_for_selector(".tab-pane.active .approval-card") timeout 15000ms
```

三条的 captured stderr 里，teardown 时服务端打印 `WebSocket disconnected: new` —— 新建 tab 的 socket 在服务端**仍以 `new` 为键**，说明握手事件几乎没推进。机制链：

1. 点 `#hub-new-btn` → `setupHub()`（`web/static/chat.js:2039-2051`）**同步**建 pane 并切 tab，`.session-tab` 立刻变 2、`.user-input` 立刻可见 —— 测试等的两条屏障**在 DOM 层面立刻满足，不保证 WS 已连上**；随后才**异步**调 `connectTab()`。
2. `connectTab()`（`web/static/chat.js:418` 定义，`socket.onopen` 在 `:430`）建 socket，`readyState === CONNECTING`；只有 `onopen` 才把状态灯置 `connected`。
3. `page.fill(...)` 直接写 `textarea.value`（与 ws 无关）→ 成功；`page.click(SEND_SELECTOR)` → `sendMessage()` 命中 **`web/static/chat.js:1680-1685`** 守卫，消息**从未发给服务端**：

   ```js
   if (!ws || ws.readyState !== WebSocket.OPEN) {
     addMessage('error', 'Connection is not ready. Reconnect and try again.');
     return;
   }
   ```

**证据（未加任何 CPU 负载）**：仅用 CDP `Network.emulateNetworkConditions(latency=800ms)` 拉长握手往返，即确定性复现 —— `LLM calls: 0`、active pane 文本为 `Connection is not ready. Reconnect and try again.`；同一延迟下**只在发送前补一条就绪屏障**，两条立刻转绿（`LLM calls: 1`）。**变绿是对「屏障缺失」的反证。**

**判定：纯测试时序脆弱。** `sendMessage` 未就绪时明确报错、不静默丢消息，是**正确的**防御行为。**无**跨 tab 状态泄漏（错误落在本 tab pane），与 #191 的性质**不同**。

**暴露面精确界定**：全文件 18 条用例中，仅这 3 条「在新 tab 上发消息、却没等握手完成」；同仓库已把「等 `#status === 'connected'`」当作建新会话后的标准屏障（`tests/web_tests/test_browser.py:155-157`、`tests/web_tests/test_reconnect_pending_interaction_browser.py:168-174`），本文件 `_open_two_tabs`（`test_multi_session_browser.py:110-118`）也有 rekey 屏障 —— **只有这 3 条漏了**。

### 根因 B：`test_workflow_graph_browser.py` 15 条 —— svg 在 DOM 里但永远 hidden

2026-09-22 master CI（run `35694867631`，job `106639412053`）失败正文：

```
waiting for locator("#workflow-canvas svg.workflow-svg") to be visible
  63 × locator resolved to hidden <svg class="workflow-svg" viewBox="0 0 802.222 4486.111" …>
```

元素**在 DOM 里但不可见**，不是「元素不存在」。机制：`chat.js` 的 `init()`（`web/static/chat.js:2055-2100`）是 async —— 先 await 两个 fetch（`:2065` `/api/slash-commands`、`:2068` `/api/debug-status`），最后才 `showHub()`（`:2099`）。测试只等 `window.AsterwyndWorkflow !== undefined`（仅表示脚本加载完）就派发 `workflow_started` → 视图切到 workflow、svg 可见；**若 init 的 fetch 在派发之后才返回**，`showHub() → showView('hub')` 把 `#workflow-view` 的 `active` 摘掉；而 `showHub()`（`chat.js:361-364`）只切视图、**不清 canvas**，svg 便永久留在 DOM 里 hidden。

**证据（未加任何 CPU 负载）**：延迟 init 的两个 fetch 即确定性复现：

```
派发后立刻          : {svgInDom: True, svgVisible: True,  wfViewActive: True,  hubActive: False}
chat.js init 跑完后 : {svgInDom: True, svgVisible: False, wfViewActive: False, hubActive: True}
断言结果            : FAIL（svg 可见性超时）—— 与 CI 失败形态逐字段吻合
```

**「成片失败、逐次波动」的解释（口径经 grill 更正）**：以「用例是否依赖 workflow 视图处于激活态」为准，共 24 条相关用例中 **15 条零屏障**、**6 条只有死等**、**仅 3 条有真屏障**（初稿写「19 条中 13+6+3」，三数和 22≠19 不自洽，且 13 条口径漏掉了以 `#workflow-tabs` / `#workflow-legend` 为入口的 `:333`、`:467`）。issue #226 记录的 5 条已留档失败（`test_collapsed_group_expands_from_the_detail_drawer`、`test_click_any_node_opens_detail_drawer`、`test_foreach_candidate_drilldown_shows_that_item`、`test_collapsed_group_shows_aggregated_status`、`test_tick_keeps_foreach_progress_count`）**全部落在零屏障用例里**；该 issue 另记的 10 failed 中其余 5 条未留档，属推断。每次 run 的负载与执行顺序天然波动 → 命中「init 后到」的用例数不同（仓库未锁 `pytest-randomly`，「随机序」不是 CI 变量）。

**次生发现（关键）**：既有的 `_wait_app_ready`（`test_workflow_graph_browser.py:123-138`）在此 fixture 里**不是有效屏障** —— 它等 `.tab-pane.active .user-input`，而 `fake_web_server` fixture 从不建 tab pane。实测 **selector 5.01s 超时、`tabPanes: 0`**，即每次都退化为「5s 超时 + 300ms 固定等待」，白等 5 秒**依然不保证** init 跑完。这正是 #215 不得不新增 `_ensure_workflow_view` 的原因。**不修死等，则根因 B 的修复只是「假屏障 + 事后补救」。**

## What Changes

**A. 两条根因各自补上「真就绪屏障」，并抽出可复用 helper**

- `test_multi_session_browser.py` 三条改用本文件已有的 `_open_two_tabs`（`:94-121` 的 rekey 屏障，覆盖「握手完成 + rekey 完成」）；若个别用例流程与 helper 差异较大（如需 hub 中间态），改用 `#status === 'connected'` 屏障并说明理由。
- `test_workflow_graph_browser.py` **15 条**零屏障用例接上既有 helper 模式（`_wait_app_ready` + 派发后 `_ensure_workflow_view`），照已验证的 3 条（`:487`/`:1039`/`:1084`）写法。**并须删除 `_wait_app_ready` 的「吞异常 + 300ms 降级」**（否则判据失效时静默退化成固定等待，15 条全绿）。

**B. 修掉 `_wait_app_ready` 的死等（根因 B 的修复前提）**

让就绪判据在此 fixture 里**真能成立**。**用户已拍板采用方案 B**（见 design D1）：

- **方案 B（选定）**：在既有测试接缝命名空间 `window.AsterwyndChatTest`（`web/static/chat.js:2105`）上新增布尔标志 `initDone`，在 `init()` resolve 后置位；`init()` 失败/挂住时**不置位**（fail-loud，测试以超时收场）。改动**只增不改**，不触碰任何既有分支或渲染路径。语义显式、不耦合 UI 文案。web-ui spec delta 追加一条**测试接缝** Requirement（写明测试专用、零生产行为、不得当死代码移除）。
- 否决的**方案 A**（等 hub 列表「加载中…」被替换）：零生产改动且实测有效（延迟注入下正确等 2.54s / 4.86s），但屏障耦合中文 UI 文案，失效模式为**静默**（改文案后相关用例一起退回 flake 状态且无测试变红提示）—— 正是 issue #226 这类问题最难排查的形态。

**C. 把本次的确定性复现固化为回归测试（仓库硬规则：每个 bug fix 必须新增回归测试）**

两条根因各一条：用 CDP 网络延迟 / 路由延迟把「负载下才偶发」的时序变成**确定性输入**，断言「有屏障必绿、无屏障必红」。这是确定性的、不靠重跑碰运气 —— 与 issue #226「不要用加重试/放宽等待盖掉」的要求一致。

**D. 明确不做**

不使用「加重试 / 放宽 timeout / 加大固定等待」；不使用 `page.clock` 假时钟（被等的是**真实网络握手与异步 fetch**，不是页面定时器；假时钟反而可能让 `connectTab` 的 2s 重连退避永不触发）。

## Non-Goals

- **不改任何生产行为**（方案 A 完全不动生产代码；方案 B 只新增一个只读就绪信号，不改变任何既有分支与渲染）。
- **不重构 `chat.js` 的初始化结构**（`init()` 的 fetch 顺序、`showHub`/`showView` 语义均不动）。
- **不把 15 条用例逐条改写**：只接上统一 helper，保持各用例原有断言。
- **不覆盖 `test_browser.py` / `test_reconnect_pending_interaction_browser.py`**：它们建新会话后都等了 `#status === 'connected'`，**发送腿**（根因 A 的主要形态）已受屏障保护；但**点击腿**仍有同名竞态残留——两处 `#hub-new-btn` 点击紧跟在 `#hub-view.active` 之后，而该 class 在 `index.html:43` **静态即满足**，`setupHub()` 的处理器可能尚未挂上（审阅 I4 收窄）。该残留与 issue #226 报告的失败形态不同源、未在本 change 观察到实际失败，**记为已知残余面**（见 `docs/known-debt.md` 的 issue #226 条目），不在本 change 扩大范围。
- **不引入测试重试插件**（如 `pytest-rerunfailures`）——等于用重试掩盖缺陷。

## Impact Analysis

**代码影响**

| 文件 | 改动 | 风险 |
|---|---|---|
| `tests/web_tests/test_multi_session_browser.py` | 3 条用例改用 `_open_two_tabs`（或 `connected` 屏障） | 低（纯测试写法；断言不变） |
| `tests/web_tests/test_workflow_graph_browser.py` | 15 条补就绪屏障；`_wait_app_ready` 修死等（**并删吞异常降级**） | 低（同上）；但 helper 若仍是死等则修复无效，故 B 与 `_wait_app_ready` 必须同批落 |
| `web/static/chat.js` | `init()` 调用点新增 `AsterwyndChatTest.initDone` 标志（1–2 行，**只增不改**） | 低（不改既有分支；web-ui spec delta 覆盖该测试接缝） |
| `tests/web_tests/`（新增） | 两条回归测试（CDP/路由延迟注入 → 断言屏障有效性） | 中（新测试自带延迟注入，需确保不引入自身 flake；用确定性路由拦截而非墙钟 sleep 断言） |

**契约影响（对外）**

- Web UI 新增 `window.AsterwyndChatTest.initDone` 只读布尔标志，属**测试接缝**扩容（与既有 `window.AsterwyndChatTest.dispatch` / `.dropConnection` 同性质）。生产路径不读取它，既有消费者不受影响。

**不影响**

- 生产渲染 / 握手 / 重连逻辑；WebSocket 协议；session 生命周期；`test_browser.py`、`test_reconnect_pending_interaction_browser.py` 的既有屏障。

**待确认影响面**

- 无（方案 A/B 取舍已由用户拍板为 B，见 design D1）。

**测试影响**

- 新增 2 条回归测试（各覆盖一条根因），须满足：未修（无屏障）时**必红**、修后**必绿**，且**不依赖机器负载**。
- 改造 18 条既有用例的就绪 choreography（3 + 15）。
- 回归：`tests/web_tests/` 全子集；浏览器用例需 chromium。

**文档影响**

- `docs/known-debt.md:297-309`（fix-issue-215 审阅 R6 记的债务）：其断言「`_ensure_workflow_view` 把『渲染了但被切走』这类间歇红治住」已被本次诊断**证伪**（该 helper 只恢复视图、不恢复 ticker，且不构成有效屏障），收尾时须更正该段并写 `protected_artifact_explained` 事件。
- `docs/known-issues.md` / `docs/known-debt.md` 中**没有** issue #226 的条目（已 grep 确认零命中）——本 change 修完后按结论**新增**一条记录（受保护路径，需结构化解释事件）。
- `docs/testing-guide.md`：若记录浏览器测试就绪约定，需同步。
- 关键词扫描 `docs/`、`README.md`、`AGENTS.md`、`CONTEXT.md` 中与浏览器测试 / flake / 就绪屏障相关的段落。

## Reference Implementation Research

- research_tier: exempt
- status: disabled
- reason: 属 **bugfix**（无新增能力面：修复既有测试的时序缺陷 + 可选 1–2 行测试接缝）。修法由已关闭的 issue 与本次诊断结论锁定：issue #191（`test_multi_session_browser.py` 同类偶发超时，PR #223，`openspec/changes/archive/` 有完整决策记录）已确立「先证明是真 bug 还是纯时序问题、测试侧优先把时序变成显式输入、不用放宽等待或加重试掩盖」的方法论；issue #226 正文明确采纳该范式并排除「加重试/放宽等待」。本次诊断（见上 Why）已把两条根因确定到 `文件:行号` 并用注入延迟确定性复现，无待定设计项。
- findings（本地参考仓库不可用的事实与替代依据）：本工作区**无** `.dev/reference-repos.txt`，也**无** `.codegraph/`（均已确认不存在），故无本地参考仓库可对比。替代依据为业界明确范式：① Playwright 官方对「应用就绪」推荐**显式就绪信号**（web-first assertion / 等待应用自报 ready）而非固定 `wait_for_timeout`，与本 change 方案 B 同构；② Playwright `page.clock` 的适用面是**页面定时器**（`setTimeout`/`setInterval`/`Date`），不含真实网络往返与 fetch 时序 —— 这正是本 change 明确**不用**假时钟、而用「连接就绪 / init 完成」屏障的依据（同仓库 issue #191 已在 blur 宽限窗类用例上正确使用假时钟，两者边界不同）。
- design impact: 确认采用「显式就绪屏障 + 确定性回归测试」而非「假时钟」或「重试/放宽等待」；方案 A/B 的取舍属**实现细节选择**（见 design D1），不改变本 change 的 RIR 档位。
