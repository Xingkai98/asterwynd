# Design: 浏览器测试的时序 flake 根治（fix-issue-226-browser-test-flake）

## Context

issue #226 记录 `tests/web_tests/test_workflow_graph_browser.py` 在**全量跑**时成片失败、**隔离跑全绿**，失败数逐次波动（同 commit 上观测到 10 / 6 / 1 / 0 failed）。issue 自陈**根因未定位**，并给出两条方法论约束：先拿到失败正文；**不要**先验假设是纯测试时序问题（#191 的先例是「测试偶发失败**真的**抓到了生产 bug」）。

本次定位已从 CI 日志取到失败正文并**用注入延迟（而非人为加压）确定性复现**，得出**两个独立根因**（详见 `proposal.md` 的 Why）：

- **根因 A**（`test_multi_session_browser.py` 3 条，2026-09-24 master CI）：新 tab 的 WebSocket 尚未 OPEN 就点发送，`sendMessage` 命中 `web/static/chat.js:1680-1685` 守卫，消息**从未发出**。
- **根因 B**（`test_workflow_graph_browser.py` 15 条，2026-09-22 master CI）：`chat.js` 的异步 `init()` 在测试派发 workflow 事件**之后**跑完，`showHub()` 把 `#workflow-view` 的 `active` 摘掉；`showHub()` 不清 canvas，svg 永久留 DOM 但 hidden。

两者**均为测试侧缺陷**，判据是「修复方向只落在测试就绪 choreography，生产行为逐条经证实为正确」（A：未就绪时明确报错是防御行为；B：init 决定初始视图是正确的，只是测试没等它）。**A 与 B 不是同一根因**，只是同属「负载下异步时序漂移 + 测试缺屏障」这一类；**B 与 #226 标题点名的文件一致**，**A 是 issue #226 未记录、但在 master 上实际发生的另一处**。

本次定位还发现一个次生问题：`_wait_app_ready`（`test_workflow_graph_browser.py:123-138`）在此 fixture 里是**死等**（等 `.tab-pane.active .user-input`，而 `fake_web_server` 从不建 tab pane）——实测 5.01s 超时、`tabPanes: 0`。这是 #215 被迫新增 `_ensure_workflow_view` 的直接原因，**不修死等则 B 的修复不成立**。

## Goals / Non-Goals

### Goals

1. 消除根因 A 与根因 B 的 flake：3 + 15 条用例在负载下不再因时序漂移而失败。
2. 把 `_wait_app_ready` 换成在此 fixture 里**真能成立**的就绪判据。
3. 把本次的确定性复现固化为**回归测试**（每个 bug fix 必须新增回归测试，仓库硬规则）。
4. 不改变任何生产**行为**（方案 B 的 1–2 行只读就绪信号也不改变既有分支）。

### Non-Goals

- 不重构 `chat.js` 的 `init()` 结构（fetch 顺序、`showHub`/`showView` 语义均不动）。
- 不引入测试重试插件，不使用「加重试 / 放宽 timeout / 加大固定等待」。
- 不使用 `page.clock` 假时钟（被等的是真实网络握手与异步 fetch）。
- 不覆盖 `test_browser.py` / `test_reconnect_pending_interaction_browser.py`（已核实不受影响）。
- 不引入统一的浏览器测试基建框架（超出 issue #226 范围；如需要另案）。

## Decisions

### D1（**已由用户拍板：采用方案 B**）就绪信号怎么落

**共同目标**：给 `_wait_app_ready` 一个在本 fixture 里真能成立的判据 —— 判据必须蕴含「`chat.js` 的 `init()` 已越过 `showHub()`」，因为该调用正是抢走 workflow 视图的唯一来源。

| | 方案 A：等 hub 列表渲染 | **方案 B（选定）**：暴露显式就绪信号 |
|---|---|---|
| 判据 | `#hub-session-list` 的静态占位「加载中…」被替换 | `window.AsterwyndChatTest.initDone === true` |
| 为何成立 | `showHub() = showView('hub') + loadHub()`，是 `init()` **最后一步**；`loadHub()` 完成 ⟹ init 已越过 `showHub()` | 信号在 `init()` resolve 后置位 ⟹ 语义直接可读 |
| 实测 | 已验证：延迟注入下正确等 2.54s / 4.86s，之后视图稳定不回抢 | 实现后以同一延迟注入验证（见 Testing Strategy） |
| 生产改动 | 0 行 | 1–2 行，**只增不改**（见 D1.1） |
| spec delta | 可不加 | 追加一条测试接缝 Requirement（见 D1.3） |
| 主要风险 | **耦合中文 UI 文案**：日后改 hub 文案（如「加载中…」→「Loading」）会**静默击穿依赖它的用例**（屏障恒真或恒假，测试变绿/变红都不再反映真实就绪） | 需改生产 JS；但改动面极小且不改行为 |

**决策依据（用户拍板）**：方案 B 的屏障语义显式、不依赖会漂移的 UI 文案；方案 A 的失败模式是「**静默失效**」—— 正是 issue #226 这类问题最难排查的形态（改文案后相关用例一起退回 flake 状态，且没有任何测试会变红提示）。本 change 本就要写 web-ui spec delta，覆盖测试接缝的边际成本小；仓库亦已有同构先例。

#### D1.1 信号形态与命名（`window.AsterwyndChatTest.initDone`）

**选定**：把布尔标志挂在**既有测试接缝命名空间** `window.AsterwyndChatTest`（`web/static/chat.js:2105-2117`）上，而非新造 `window.AsterwyndReady` 全局。

**理由**：
1. **单一入口**：该命名空间已被注释定义为「测试接缝：暴露给浏览器契约测试…只暴露入口本身，不改变任何生产行为」。测试相关的钩子集中在一处，后人找接缝只看一个地方。
2. **布尔标志而非 Promise**：测试侧用 `page.wait_for_function` 轮询（仓库既有惯例，见 `test_browser.py:155-157`、`test_workflow_graph_browser.py` 全线）。布尔标志可直接在内联谓词里读，语义自解释、失败时也便于人工在 devtools 里核对；Promise 需要跨 Playwright 桥 await，调试期看不出「卡在哪一步」。

**实现形态**（`init()` 调用点，`web/static/chat.js:2119`）：

```js
// 测试接缝：应用异步初始化是否已完成（issue #226 根因 B）。
// init() 的完成时刻决定初始激活视图：后到的 showHub() 会摘掉被测视图的 active。
// 只置位、不改变任何既有分支。init 失败/挂住时**不**置位 —— 屏障失守要 fail-loud。
window.AsterwyndChatTest.initDone = false;
init().then(() => { window.AsterwyndChatTest.initDone = true; });
```

**注意：不传 `onRejected` 第二参数**（grill 修正）。今天 `init();`（`chat.js:2119`）若 reject 会冒成 unhandled rejection；`test_workflow_graph_browser.py` 的 `page` fixture 用 `pageerror` 收集器（`:62`、`:65-66`）把它记成测试失败。传了 `onRejected` 会**吞掉**这个既有的响亮失败、改成 15s 超时 —— 那既不是「只增不改」（改变了既有失败模式），也与 D1.2 的 fail-loud 精神相悖。带一个参数的 `.then` 同时满足：成功置位、失败保持 `false` 且保留今天的响亮报错。

**为什么挂在 `AsterwyndChatTest` 上仍然「只增不改」**：`window.AsterwyndChatTest = {...}` 的赋值在 `chat.js:2105`，`init()` 调用在 `:2119`，即**接缝对象先于 init 存在**（已核实）。新增两个语句均在文件末尾、`init()` 调用点处，不触碰任何既有函数体、分支或渲染路径。

#### D1.2 失败路径语义：宁可超时，不可假置位

**决定**：`init()` 抛错或在任一 fetch 上挂住时，`initDone` **永不置位**，测试以超时收场。

**理由**：这是 **fail-loud**。若在失败分支也置位，屏障就退化成方案 A 同款的「静默失效」—— 初始化根本没跑完，测试却认为可以派发事件了。宁可红得慢（超时），也不要绿得假。

**具体边界**：
- `init()` 的两个 fetch 已在既有 `try/catch` 内（`:2064-2075`），fetch 失败**不**导致 init reject，init 照常走完 `showHub()` → `initDone` 正常置位。这是既有语义，本 change 不改。
- `init()` 真正 reject 只可能来自 try/catch 之外的语句（**不止 `setupHub()`**：`localStorage.getItem`(`:2061`)、`document.querySelectorAll(...).forEach`(`:2078-2084`)、`createTab`/`buildTabPane`/`switchTab`(`:2090-2092`) 同样在 try/catch 之外，都可能是拒绝源）。此时标志保持 `false`，**且保留既有的 unhandled rejection 报错**（见 D1.1 的「不传 `onRejected`」）。
- 挂住（fetch 永不 settle）：`init()` 永不 resolve → `initDone` 恒 `false` → `wait_for_function` 超时。**这是期望行为**。

#### D1.3 spec delta

给 `web-ui` 追加 Requirement「Web UI 暴露应用初始化完成的测试接缝」，写明它是**测试专用、零生产行为**，并显式声明「SHALL NOT 因未在生产路径读取而被当作死代码移除」—— 否则后人会当死代码删掉。

**否决的备选**：
- **方案 A（等 hub 列表渲染）**：可行且零生产改动，但屏障耦合中文 UI 文案、失效模式为静默。用户已在知晓两条路线实测与取舍后选择方案 B。
- **新造 `window.AsterwyndReady` 全局**：与既有接缝风格不一致，多一个命名空间要维护。
- **等 `.hub-empty` 出现**：实测**在 0.02s 就误命中** —— `web/static/index.html:82` 静态就有 `<div class="hub-empty">加载中…</div>`，不能区分「静态初始」与「loadHub 完成」。
- **等 `.tab-pane.active .user-input`**（现状）：死等，已验证 5.01s 超时。
- **`page.wait_for_timeout(固定值)`**：issue #226 明确反对，且正是 flake 成因。
- **`page.clock` 假时钟**：适用面是页面定时器，不含真实 WS 握手与 fetch 时序（见 RIR findings）。

### D2 根因 A 的屏障选择：复用 `_open_two_tabs` 还是 `#status === 'connected'`

**决定**：优先复用 `_open_two_tabs`（`test_multi_session_browser.py:94-121`）—— 它已同时覆盖「WS 握手完成（rekey 发生）」与「rekey 完成」两层，且这 3 条本就是「开两个 tab + 在第二个 tab 发消息」的场景，语义完全吻合。

**例外**：若某条用例的流程与 helper 差异较大（如需要 hub 中间态、或用例自己管理第一个 tab 的 session id），改用 `#status === 'connected'` 屏障，并在 tasks/代码注释里**写明为何没复用 helper**。理由：同仓库已有该惯例（`test_browser.py:155-157`、`test_reconnect_pending_interaction_browser.py:168-174`），语义直白且不依赖 rekey 细节。

**否决**：把 `_open_two_tabs` 强改成能覆盖所有形态（会增加 helper 参数与分支，得不偿失）。

### D3 根因 B 的屏障：`_wait_app_ready`（修后）**为主**，`_ensure_workflow_view` 为补充

**决定**：**15 条**零屏障用例统一采用**已验证的 3 条**（`test_workflow_graph_browser.py:487`/`:1039`/`:1084`）的写法 —— 派发前 `_wait_app_ready`、派发后 `_ensure_workflow_view`。（暴露面由 grill 修正为 15 条而非初稿的 13 条，见 D6。）

**修后的 `_wait_app_ready`（grill 修正，关键）**：判据由「等 `.tab-pane.active .user-input`（在本 fixture 恒不出现）」改为等 `window.AsterwyndChatTest && window.AsterwyndChatTest.initDone === true`（D1.1），**并删除 `except Exception: await page.wait_for_timeout(300)` 这个吞异常降级**。

**为什么必须删降级**：保留它，判据一旦失效（信号没置位）就会被吞掉、只等 300ms，随后 `_ensure_workflow_view` 把视图强行拉回 ⇒ 15 条全绿。**这正是本 change 自己否决的方案 A 的失败模式——静默失效。** 删掉后，判据失效 = 15s 超时红，失败正文直指 `initDone`，诊断信息保留。（本 change 已给 A 类用「握手就绪」、给此处的 B 类用「init 完成」，两者都是显式信号，不再需要「无 tab pane 就短等」这条为旧判据兜底的降级。）

**`_ensure_workflow_view` 保留，并补齐 ticker（用户拍板）**：它此前只把 `#workflow-view` 的 `active` 拉回，**不恢复 ticker** —— `showView()` 对非 workflow 视图会调 `window.AsterwyndWorkflow.stopTicker()`（`chat.js:301`）。故当判据退化、后到的 `showHub()` 抢走视图时：`tick` 类用例（`:708`/`:745`）的断言是「文本没变坏」（无 `undefined`、含 M/N），停摆的 ticker 让它们**恒真**——**假保护**；`:769`（「已跑 Xs」跳秒）则会被 ticker 停摆打成**误导性正文**（说「没跳秒」，真因是视图被抢）。**用户已拍板修法**：在 `_ensure_workflow_view` 里补 `window.AsterwyndWorkflow.startTicker()`，与视图激活态一起恢复——使该后置兜底真正等价于「视图可用」，消除 `:708`/`:745` 的假保护与 `:769` 的误导正文。**结论：`_ensure_workflow_view` 是有用的补充，不能当主屏障**；主屏障仍是修好后的 `_wait_app_ready`（删掉吞异常降级后，判据失效会 fail-loud）。

**插入位置约束（grill 发现）**：`:168` 的用例在派发后、svg 等待前有 `assert await page.is_visible("#workflow-view")`（`:175`）。`_ensure_workflow_view` 会调用测试自装 stub 的 `onWorkflowStarted()`（`:108-113`）把视图设为 active ⇒ 若把 helper 插在 `:175` **之前**，该断言变恒真。故 `:168` 的 helper 必须插在 `:175` 之后（其余 14 条已逐条核对无此问题）。

### D4 回归测试的形态：确定性时序注入，而非重跑

**决定**：两条回归测试各用**延迟注入**把「负载下才偶发」变成**确定性输入**。**参数与自证风险由 grill 钉死（关键，否则回归会自证、恒绿）**：

**根因 B 回归的参数必须是「旧 helper 固定耗时」的对手方**：旧 `_wait_app_ready` 在 fixture 上固定耗时 **5.01s 超时 + 300ms 等待 ≈ 5.3s**。若注入延迟 D=1500ms，未修版在 5.3s 返回时 init 早完成 ⇒ **未修也绿**，回归无判别力。故：
- **D ≥ 6000ms**（> 5.3s）：未修版 5.3s 派发 → 6.0s 被后到的 `showHub()` 抢走视图 ⇒ **未修必红**。
- **回归 B 不得调用 `_ensure_workflow_view`**：它会把视图强行拉回 ⇒ 未修也恒绿（自证）。回归 B 只调修好后的 `_wait_app_ready`。
- **必须断言注入确实生效**：CDP `Network.emulateNetworkConditions` 在新版 Chromium 已被 `Network.emulateNetworkConditionsByRule` 取代；若 CDP 调用静默失效，注入为 0，未修也绿。故回归 B 须断言「`initDone` 在延迟窗口内确实为 `false`」（或等价地断言实测延迟 ≥ 注入值）。

**根因 A 回归同理**：诊断实测 latency=800ms 时屏障等待仅 1.41s，**余量约 0.6s** —— 满载机上四步 Playwright 往返一旦超 ~1.4s，WS 已 OPEN，「LLM calls: 0」的前置断言就会失败（**新 flake**）。故 A 的注入延迟取 **3000ms**，并断言「实测等待 ≥ 注入值的 50%」以证明注入生效。**实现期修正（审阅 I2）**：拍板原文写「实测等待 ≥ 注入值」，但实测 `handshake_ms=3095ms`（注入 3000ms）只剩约 3% 余量，满载机上反而会自造 flake —— 该断言的目的只是「证明注入生效」（区分「注入了」与「没注入」），取 50% 已有充分判别力且留出安全余量。

**共同原则**：两条回归都要**断言注入生效**，不能只断言期望结果——否则注入失效时测试恒绿、失去守护。

- **根因 A 回归**：CDP `Network.emulateNetworkConditions(latency=3000)` 拉长握手往返；**只保留正向半场** —— 先等 rekey 就绪屏障再发送，断言消息送达。判别力来自「去掉屏障则发送落空 ⇒ 必红」（已两向实测）。**负向半场（断言「无屏障时发不出」）已移除**：它与机器速度赛跑、自身即是新 flake 来源（起草时的附带产物，非 Q4 要求）。
- **根因 B 回归**：`page.route` 延迟 `init()` 依赖的两个 fetch；断言「不管 init 何时完成，视图最终保持 workflow、svg 可见」。判别力来自「**不修 `_wait_app_ready` 则必红**」。

**为什么不用「跑 N 次逼出偶发」**：仓库环境 4 核/7GB 且需与他人共享，反复连跑属禁止行为；且概率性复现对 CI 无诊断力（失败时说不清哪一步）。确定性注入**同时**满足「一定能复现」与「不依赖机器负载」。

**否决**：`pytest.mark.flaky` / 重试插件 / 只断言「最终能出现」（会退化成放宽等待）。

### D5 两条根因的修复必须同批交付

**决定**：A 与 B 在同一 change、同一 PR 内交付。

**理由**：两者同属 issue #226 记录的「浏览器测试负载下不稳定」这一现象，且 B 的修复依赖 `_wait_app_ready` 的死等修复（D3）。拆两个 PR 会让 B 的第一个 PR 处于「屏障不成立」的中间态。

**否决**：拆成两个 change（issue #226 是一个跟踪入口；且拆开后 B 的中间态会再引入一轮误判风险）。

### D6（grill 修正）暴露面口径更正：13 → **15** 条，且总数自洽

**初稿错误**：初稿称「19 条涉 svg 用例中 13 条零屏障 / 6 条只有死等 / 3 条有真屏障」——三数之和 22 ≠ 19，**算术不自洽**。根因是初稿的 19 条只统计了「正文直接等 `#workflow-canvas svg.workflow-svg`」的用例，漏掉了同样依赖图渲染、但不以该选择器为唯一入口的用例。

**grill 独立重算（我已复核）**：以「该用例是否依赖 workflow 视图处于激活态」为口径，正确分布为 **15 条零屏障 / 6 条只有死等 / 3 条有真屏障，合计 24 条**。初稿漏掉的 **2 条**：
- `:333 test_multi_workflow_tabs_switch` —— 用 `page.click("#workflow-tabs .graph-tab:first-child")`；视图被抢时该 click 会等 30s 超时。
- `:467 test_legend_is_visible_and_collapsible` —— 用 `wait_for_selector("#workflow-legend:not([hidden])")` 与 `assert is_visible("#legend-body")`；`.view{display:none}`（`style.css:131-132`）下视图被抢则断言为假，**失败正文是 `is_visible` 为假而非 svg 超时，日志里认不出与 svg 类同源**。

**影响**：D3 的改造范围由 13 改为 **15** 条；`proposal.md` / `diagnosis.md` / backlog 中「13 条」「19 条」措辞一并更正。

**归因措辞更正（grill 发现）**：仓库**未锁 `pytest-randomly`**（`uv.lock` 无、CI 无），CI 命令是 `uv run pytest -q`（`.github/workflows/ci.yml:48`）——「随机序」不是 CI 变量。issue #226 的 10 failed 只留档 5 条：**「5 条失败全部落在零屏障用例内」对已留档者成立；其余是推断，须在文档中如实标注**（不得写成「全部落在这 13 条里」）。

## Pre-Implementation Review

| # | 问题 | 结论 |
|---|---|---|
| Q1 | 根因是生产 bug 还是测试脆弱？ | **测试脆弱**。A：未就绪时明确报错是正确防御；B：init 决定初始视图正确。两条均有代码级 + 注入延迟实证。 |
| Q2 | 是否与 #191 同类（=有真实跨 tab 泄漏）？ | **否**。A 的错误落在本 tab pane，无跨 tab 影响；本次未发现任何生产状态泄漏。 |
| Q3 | A 与 B 是同一根因吗？ | **否**。独立机制、独立文件、独立时序源（WS 握手 vs async init）。 |
| Q4 | issue #226 标题点名 `test_workflow_graph_browser.py`，但 09-24 失败在 `test_multi_session_browser.py` —— 谁是「本 issue 的」？ | **两者都是**。B 与 #226 记录的形态（成片失败、逐次波动、隔离全绿）逐字段吻合；A 是 #226 未记录但在 master 上实际发生的另一处同类 flake。本 change 一并覆盖。 |
| Q5 | 就绪信号方案 A 还是 B？ | **用户已拍板：方案 B**（D1）。理由 = 显式语义 + 避免方案 A 的「静默失效」失败模式；形态定为 `window.AsterwyndChatTest.initDone`（D1.1），失败路径 fail-loud（D1.2）。 |
| Q6 | 要不要用 `page.clock` 假时钟？ | **不要**。被等的是真实网络握手 / fetch 时序，非页面定时器（见 RIR findings）。 |
| Q7 | 回归测试怎么保证有判别力？ | 延迟注入 + 「未修必红、修后必绿」双向验证（D4）；**参数由 grill 钉死**（B 的 D≥6s 且禁用 `_ensure`；A 的 D≥3s；两条都断言注入生效），否则会自证恒绿。实现后须做变异验证。 |
| Q8 | `_wait_app_ready` 死等是本次新发现，算不算范围蔓延？ | **不算**。它是 B 的修复前提（D3）：不修它，15 条用例接上的就是假屏障，issue #226 会以另一种形态复发。 |
| Q9（grill） | `_wait_app_ready` 的「吞异常 + 300ms 降级」留不留？ | **必须删**。保留则判据失效时退化成 300ms 固定等待 + `_ensure` 拉回 ⇒ 15 条全绿（静默失效，与本 change 否决的方案 A 同款失败模式）。删后失效 = 15s 超时红，诊断信息保留。 |
| Q10（grill） | `_ensure_workflow_view` 的兜底覆盖面有多大？ | **不要高估**。它只恢复视图、**不恢复 ticker**（`chat.js:301` 会 `stopTicker()`）。判据退化时 `:708`/`:745` 因断言「文本没变坏」而**恒真假保护**，`:769` 会以误导正文变红。故它只是补充，主屏障必须是修好的 `_wait_app_ready`。 |
| Q11（grill） | 暴露面到底是 13 还是 15 条？ | **15 条**（详见 D6）。初稿 13 条漏了 `:333`、`:467`；且「19 条」与「13+6+3」算术不自洽（正确总数 24）。已更正，`proposal.md`/`diagnosis.md`/backlog 同步。 |
| Q12（grill） | `.then` 要不要传 `onRejected` 吞掉 init 的拒绝？ | **不要**（D1.1）。既有的 unhandled rejection 会被 `pageerror` 记成测试失败，是**既有**的响亮信号；吞掉它不是「只增不改」，也违背 fail-loud。带一参的 `.then` 即可。 |

**剩余风险**：方案 B 落地后，`initDone` 的正确性依赖「`init()` resolve ⟹ 初始视图已定」这一不变量。若未来有人把 `init()` 的 `showHub()` 挪出 resolve 路径（如改成 fire-and-forget），屏障会失效且**不报错**。缓解：D1.3 的 spec delta 显式写明该依赖；回归测试（根因 B）会在有人改动 init 结构时变红（它注入延迟并断言视图稳定）。

## Risks / Trade-offs

| 风险 | 影响 | 缓解 |
|---|---|---|
| 方案 A 耦合「加载中…」文案（**未被选中**） | 改 hub 文案会静默击穿依赖它的用例 | 若选 A：注释显式标注 + 记 known-debt；可选加一条「文案存在性」守卫测试尽早发现 |
| 方案 B 改生产 JS | 需 web-ui spec delta，且要确认无行为变化 | 只增不改（末尾设标志，不触碰既有函数体/分支）；spec delta 覆盖；grill 审视 |
| `initDone` 被后人当死代码删掉 | 屏障消失，flakes 复发且无提示 | D1.3 在 spec 里写明「测试专用、零生产行为、SHALL NOT 当死代码移除」；回归测试会在删除后变红 |
| `init()` 结构变更（`showHub()` 移出 resolve 路径） | 屏障失效且不报错 | spec 写明该不变量；回归测试（根因 B）对 init 结构改动敏感 |
| 新回归测试自身引入 flake | 新增不稳定测试，反噬 CI | 用路由/CDP 拦截而非墙钟 sleep 断言；判别力靠注入而非重跑 |
| 15 条用例改动面 | 可能改坏既有断言 | 只加屏障、不动断言；逐条核对 diff；跑全子集 |
| `_ensure_workflow_view` 兜底掩盖判据退化 | 屏障悄悄失效而测试仍绿 | **必须删掉 `_wait_app_ready` 的吞异常降级**（D3），否则退化即静默；`_ensure` 只作补充且**不恢复 ticker**（tick 类用例会假保护）；回归测试直接断言「不修则红」 |
| 注入载体退役（CDP `emulateNetworkConditions` 已被 `emulateNetworkConditionsByRule` 取代） | 注入静默失效 ⇒ 回归恒绿、判别力归零 | 两条回归都**断言注入生效**（D4） |
| `:168` 的 `_ensure` 插入位置 | 插错位置会让「自动打开视图」断言恒真 | 必须插在 `:175` 之后（D3） |

## Testing Strategy

- **回归测试（新增，2 条）**：各覆盖一条根因，用延迟注入构造确定性输入；须做**变异验证**（去掉屏障 → 必红；还原 → 必绿）。
  - **根因 A 回归**（`test_new_tab_send_survives_slow_handshake`）：CDP 注入 3000ms 往返延迟 → 等 rekey 就绪屏障后发送 ⇒ 送达。判别力 = **去掉屏障则发送落空、必红**（已两向实测）。只保留正向半场，理由见上。
  - **根因 B 回归**：`page.route` 延迟 `/api/slash-commands` + `/api/debug-status` → 断言「派发 workflow 事件后，视图最终保持 workflow 且 svg 可见」。判别力 = **不修 `_wait_app_ready` 必红**。
- **`initDone` 语义验证（新增，2 条）**：对应 spec 的两个 Scenario —— ①正常加载下最终 `initDone === true` 且此后派发事件不被抢视图；②延迟 init 的两个 fetch 时，屏障把派发推迟到 `initDone` 置位之后（断言「派发前 `initDone` 已为 true」）。后者同时锁住 D1.2 的 fail-loud 语义：若实现把标志在失败/未完成路径提前置位，该断言会抓到。
- **改造用例（18 条）**：3 条（A）+ 15 条（B）接上就绪屏障；断言保持原样。其中 `:168` 有插入位置约束（见 D3）、`:708`/`:745`/`:769` 有 ticker 依赖（见 D3）。
- **子集回归**：`tests/web_tests/` 全子集（含 chromium 浏览器用例），确认无新增失败。
- **重复稳定性**：改造后对两个文件做**有限次数**重复跑（遵守资源纪律：单进程、不并发、不人为加压），观察不再出现时序失败；**不以「反复跑逼出 flake」为验证手段**。
- **不跑全量**（留到收尾一次）：按仓库 baseline 要求在收尾阶段跑一次全量 `uv run pytest -q` + OpenSpec strict validate + artifact checker。
- **浏览器 smoke**：本 change 改的是浏览器测试本身，改后跑 `tests/web_tests/` 子集即为对应层级的验证。
