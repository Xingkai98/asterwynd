# Diagnosis: 浏览器测试的时序 flake（fix-issue-226-browser-test-flake）

## Symptom

issue #226：全量 `pytest -q` 时 `tests/web_tests/test_workflow_graph_browser.py` **整文件成片失败**（一次观测 10 failed），**隔离跑全绿**；失败数在同一 commit 上逐次波动（10 / 6 / 1 / 0）。

2026-09-24 master CI（run `35949416936`，job `107474509631`）另观测到**另一个文件**失败：

```
FAILED tests/web_tests/test_multi_session_browser.py::test_multi_tab_independent_messages
  playwright TimeoutError: Page.wait_for_selector: Timeout 30000ms exceeded.
    waiting for locator(".tab-pane.active .message.assistant") to be visible
FAILED tests/web_tests/test_multi_session_browser.py::test_multi_tab_exit_does_not_affect_other_tab_reconnect
  playwright TimeoutError: Page.wait_for_function: Timeout 30000ms exceeded.
FAILED tests/web_tests/test_multi_session_browser.py::test_multi_tab_approval_isolation
  playwright TimeoutError: Page.wait_for_selector: Timeout 15000ms exceeded.
    waiting for locator(".tab-pane.active .approval-card") to be visible
3 failed, 3022 passed, 8 skipped in 308.47s
```

2026-09-22 master CI（run `35694867631`，job `106639412053`）命中的是 #226 点名的文件：

```
FAILED tests/web_tests/test_workflow_graph_browser.py::test_collapsed_group_shows_aggregated_status
  playwright TimeoutError: Page.wait_for_selector: Timeout 30000ms exceeded.
  Call log:
    - waiting for locator("#workflow-canvas svg.workflow-svg") to be visible
      63 × locator resolved to hidden <svg class="workflow-svg" viewBox="0 0 802.222 4486.111" …>
1 failed, 3048 passed, 8 skipped in 253.67s
```

两次失败形态不同：前者是「元素**从不出现**」，后者是「元素**在 DOM 里但永远 hidden**」。

## Reproduction

**未使用人为加压**（禁止项）。用「注入延迟」把负载下才偶发的时序变成确定性输入：

- **根因 A**：`BrowserContext` CDP `Network.emulateNetworkConditions(latency=800ms)` 拉长握手往返。
- **根因 B**：`page.route` 延迟 `chat.js` `init()` 依赖的两个 fetch（`/api/slash-commands`、`/api/debug-status`）。

两条均在**常规负载**下 100% 复现，且加屏障后 100% 转绿 —— 见 Evidence 的对照实验。

## Evidence

### 根因 A（`test_multi_session_browser.py` 3 条）

机制链（`文件:行号`）：

1. `web/static/chat.js:2039-2051` —— 点 `#hub-new-btn` 后 `setupHub()` **同步**建 pane、切 tab；`.session-tab` 立刻变 2、`.user-input` 立刻可见（测试等的两条屏障**在 DOM 层立刻满足**），随后才**异步** `connectTab()`。
2. `web/static/chat.js:418`（定义）/`:430`（`onopen`）—— `connectTab()` 建 socket 时为 `CONNECTING`，仅 `onopen` 置 `connected`。
3. `web/static/chat.js:1680-1685` —— `sendMessage()` 守卫：`readyState !== OPEN` 则 `addMessage('error', 'Connection is not ready. Reconnect and try again.')` 并 **return**，消息不发出。

实测（注入 800ms 延迟，复刻失败用例正文）：

```
=== independent_messages ===   LLM calls: 0   paneText: 'Connection is not ready. Reconnect and try again.'
=== approval_isolation  ===   LLM calls: 0   approval-card 不出现
```

**对照实验（关键）**：同一延迟下，仅在发送前补一条「连接就绪」屏障 →

```
=== with 'connected' barrier ===  barrier wait 1.41s  LLM calls: 1   paneText: '第二条消息\n\nFake browser response'
=== with rekey barrier    ===    barrier wait 1.47s  LLM calls: 1
```

即**瓶颈障必红、加屏障必绿** —— 反证根因是屏障缺失，而非服务端丢帧或产品 bug。

CI 日志佐证：三条失败的 captured stderr 中，teardown 时服务端打印 `WebSocket disconnected: new` —— 新建 tab 的 socket 在服务端**仍以 `new` 为键**（rekey 需收到 `session_created`），说明握手事件在该次运行里几乎没推进。

暴露面（全文件扫描，**修复前**的口径；计数经审阅 R3 校正为实测值）：

| 用例 | 同开两 tab | 在 tab 上发消息 |
|---|---|---|
| `test_multi_tab_independent_messages`（修复前 `:253`） | 否（inline preamble） | **是** |
| `test_multi_tab_exit_does_not_affect_other_tab_reconnect`（修复前 `:728`） | 否（inline preamble） | **是** |
| `test_multi_tab_approval_isolation`（修复前 `:768`） | 否（inline preamble） | **是** |

全文件 19 条用例的构成（实测）：**13 条**用 `_open_two_tabs`（含上表 3 条修复后的归属）、**3 条**用 inline preamble（`test_new_session_respects_mode` / `test_multi_tab_image_preview_isolation` / 新回归 `test_new_tab_send_survives_slow_handshake`）、**3 条**单 tab（`test_hub_lists_session_and_opens_tab` / `test_refresh_returns_to_recent_session` / `test_delete_session_closes_tab`）。

即「在新 tab 上发消息、却没等握手完成」的用例**恰好只有这 3 条**（其余 inline/单 tab 用例不发消息，或虽发消息但已等 `#status === 'connected'`）。

### 根因 B（`test_workflow_graph_browser.py` 15 条）

机制链（`文件:行号`）：

1. `web/static/chat.js:2055-2100` —— `init()` 是 async：先 await `:2065` `/api/slash-commands` 与 `:2068` `/api/debug-status`，最后才 `:2099` `showHub()`。
2. `web/static/chat.js:361-364` —— `showHub() = showView('hub') + loadHub()`；`showView('hub')` 会把 `#workflow-view` 的 `active` 摘掉，且**不清 canvas**。
3. `tests/web_tests/test_workflow_graph_browser.py:123-138` —— 既有 `_wait_app_ready` 等 `.tab-pane.active .user-input`，而该 fixture 从不建 tab pane。

实测（延迟 init 的 fetch）：

```
派发后立刻          : {svgInDom: True, svgVisible: True,  wfViewActive: True,  hubActive: False}
chat.js init 跑完后 : {svgInDom: True, svgVisible: False, wfViewActive: False, hubActive: True}
断言结果            : FAIL Page.wait_for_selector: Timeout 5000ms exceeded.
```

与 CI 失败正文 `locator resolved to hidden <svg class="workflow-svg" …>` 逐字段吻合。

**次生发现**：`_wait_app_ready` 在此 fixture 里是**死等** ——

```
==== PROBE _wait_app_ready ====
selector appeared: False (waited 5.01s)
dom: {'tabPanes': 0, 'sessionTabs': 0, 'hubActive': True, 'chatActive': False}
```

即每次都退化为「5s 超时 + 300ms 固定等待」，白等 5 秒**仍然不保证** init 跑完。这正是 #215 新增 `_ensure_workflow_view` 的原因，也是「15 条零屏障」中 6 条「只有死等」的真实状态。

**候选就绪屏障实测**（替代死等）：

```
candidate barrier A（等 .hub-empty）    : 0.02s 误命中 —— index.html:82 静态即有 <div class="hub-empty">加载中…</div>
candidate barrier B（等「加载中…」被替换）: 延迟注入下正确等 2.54s / 4.86s，之后视图稳定不回抢  ✅
```

「成片失败、逐次波动」的解释（**口径经 grill 更正**）：以「用例是否依赖 workflow 视图处于激活态」为准，共 24 条相关用例中 **15 条零屏障、6 条只有死等、仅 3 条有真屏障**（初稿误写为「19 条中 13+6+3」，三数和 22≠19 不自洽；13 条口径漏掉了以 `#workflow-tabs` / `#workflow-legend` 为入口的 `:333`、`:467`）。issue #226 的 10 failed **只留档 5 条**，这 5 条确实全部落在零屏障用例内；其余 5 条为推断，未留档。另：仓库**未锁 `pytest-randomly`**（`uv.lock`/CI 均无，CI 命令是 `uv run pytest -q`），故「随机序」不是 CI 变量，命中数差异来自负载与执行顺序的天然波动。

## Root Cause

**根因 A（`test_multi_session_browser.py` 3 条）**：测试在新 tab 的 WebSocket 尚未 OPEN 时点击发送，`sendMessage` 命中 `web/static/chat.js:1680-1685` 的守卫直接 return，消息从未到达服务端，被等的 assistant 消息 / 审批卡片永不出现。**纯测试时序脆弱** —— 生产侧「未就绪时不发、明确报错」是正确行为。

**根因 B（`test_workflow_graph_browser.py` 15 条）**：测试未等 `chat.js` 的异步 `init()` 落定就派发 workflow 事件；后到的 `showHub()` 把 workflow 视图的 `active` 摘掉，而 `showHub()` 不清 canvas，svg 永久留 DOM 但 hidden。**纯测试时序脆弱** —— `init()` 决定初始视图是正确的。

**共同结构**：负载下异步初始化（WS 握手 / `init()` fetch）完成时刻漂移，而对应测试缺少「该异步初始化已完成」的屏障。

**明确排除**：#191 式的生产状态泄漏 —— 本次未发现任何跨 tab 状态污染（A 的错误落在本 tab pane；B 的视图切换是全局单例视图的正常语义）。

## Recommended Direction

1. **根因 A**：3 条用例改用本文件已有的 `_open_two_tabs`（`:94-121` 的 rekey 屏障，覆盖「握手完成 + rekey 完成」）；流程差异较大者改用 `#status === 'connected'` 屏障并说明理由（见 design D2）。
2. **根因 B**：15 条接上「派发前 `_wait_app_ready` + 派发后 `_ensure_workflow_view`」，照已验证 3 条（`:487`/`:1039`/`:1084`）的写法（见 design D3）。
3. **修 `_wait_app_ready` 的死等**：换成在本 fixture 真能成立的判据。**用户已拍板方案 B**（见 design D1）：在既有接缝 `window.AsterwyndChatTest`（`chat.js:2105`）上新增 `initDone`，`init()` resolve 后置位、失败/挂住不置位（fail-loud）；**并删除原有的「吞异常 + 300ms 降级」**（保留会使判据失效时静默退化，15 条全绿）。否决的方案 A（等 hub 列表「加载中…」被替换，实测 2.54s/4.86s 有效）因耦合中文文案、失效模式静默而落选。
4. **回归测试**：两条根因各一条，用延迟注入构造确定性输入，做「未修必红、修后必绿」双向验证（见 design D4）。
5. **不做**：加重试 / 放宽 timeout / 加大固定等待 / `page.clock` 假时钟。

## Regression Tests

| 回归测试 | 覆盖根因 | 判别力来源 |
|---|---|---|
| CDP 注入 3000ms 握手延迟下，等 rekey 就绪屏障后发送 → 消息送达、收到 assistant 回复（**只保留正向半场**；负向半场「断言无屏障时发不出」与机器速度赛跑、自身即新 flake 来源，起草时的附带产物，经裁定移除） | A | **去掉屏障则发送落空 ⇒ 必红** |
| 延迟 `init()` 的两个 fetch 后派发 workflow 事件 → 视图最终保持 workflow、svg 可见 | B | **不修 `_wait_app_ready` 必红** |

两条均须做**变异验证**：去掉屏障 → 变红；还原 → 变绿。**不以「反复连跑逼出 flake」为验证手段**（仓库资源纪律禁止人为加压）。
