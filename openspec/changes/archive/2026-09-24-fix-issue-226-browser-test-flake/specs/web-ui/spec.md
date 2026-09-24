## ADDED Requirements

### Requirement: Web UI 暴露应用初始化完成的测试接缝

Web UI SHALL 在 `chat.js` 的测试接缝命名空间 `window.AsterwyndChatTest` 上暴露布尔标志 `initDone`，表示应用的异步初始化函数 `init()` 是否已完成。该标志 SHALL 仅在 `init()` resolve 之后置为 `true`；`init()` reject 或未完成时 SHALL 保持 `false`（SHALL NOT 在失败路径置位 —— 屏障失守须 fail-loud，不得静默通过）。标志 SHALL 只增不改：SHALL NOT 改变任何既有渲染、分支或生产行为。

该接缝为**测试专用**：`initDone` 不被任何生产路径读取。SHALL NOT 因「生产代码未引用」而被当作死代码移除 —— 浏览器回归（见「浏览器回归的就绪屏障」）依赖它区分「静态初始态」与「异步初始化完成态」。依据（issue #226 根因 B）：`init()` 的完成时刻决定初始激活视图，后到的 `showHub()` 会摘掉被测视图的 `active`；缺少该信号时测试只能等一个与被测 fixture 无关的元素，退化为「超时 + 固定等待」。

#### Scenario: 初始化完成后标志置位

- **GIVEN** Web UI 页面加载且 `init()` 正常执行完毕
- **WHEN** 浏览器测试读取 `window.AsterwyndChatTest.initDone`
- **THEN** 该值 SHALL 为 `true`
- **AND** 此时初始激活视图已确定，后续派发 UI 事件 SHALL NOT 被后到的初始化改回

#### Scenario: 初始化未完成时标志不置位

- **GIVEN** Web UI 页面加载但 `init()` 依赖的请求被延迟响应（或 `init()` 失败）
- **WHEN** 浏览器测试在初始化完成前读取 `window.AsterwyndChatTest.initDone`
- **THEN** 该值 SHALL 为 `false`
- **AND** 等待该标志的测试 SHALL 在超过时限后失败，SHALL NOT 因标志被提前置位而误判就绪

### Requirement: 浏览器回归的就绪屏障

Web UI 的浏览器回归测试 SHALL 在派发 UI 事件或触发交互（发送消息、点击节点、断言渲染结果）之前，等待该交互所依赖的异步前置条件**确定就绪**。就绪判据 SHALL 能区分「静态初始态」与「异步初始化完成态」；SHALL NOT 以固定等待（`wait_for_timeout`）或「元素已存在」代替 —— 二者都不能证明异步初始化已完成。

依据（issue #226 诊断）：`chat.js` 的 `init()` 是异步的（依赖多个 fetch），WebSocket 握手亦为异步；负载下其完成时刻漂移，使「元素已存在」与「初始化已完成」之间的窗口打开，测试遂偶发失败。同一诊断实测到两种失效形态：既有的 `_wait_app_ready` 等一个**在该 fixture 中永不出现**的元素（恒退化为超时 + 固定等待），而「等 `.hub-empty` 出现」这类判据因 `index.html` 静态即含该占位而**在 0.02s 误命中**。

#### Scenario: 多标签会话测试等待连接就绪

- **GIVEN** 浏览器回归通过 hub 新建会话标签页，且该标签页的 WebSocket 尚在连接中
- **WHEN** 测试要在该标签页发送消息
- **THEN** 测试 SHALL 先等待该标签页的连接就绪（或等价的会话握手完成信号）
- **AND** 测试 SHALL NOT 在该屏障成立前点击发送
- **AND** 因连接未就绪而发送失败 SHALL NOT 被当作**被测行为**断言
  （**不适用于前置条件断言**：回归测试可以断言「未加屏障时消息发不出」以证明屏障的必要性——
  该断言证明的是缺陷可复现，与被测行为无关）

#### Scenario: Workflow 视图测试等待应用初始化落定

- **GIVEN** 浏览器回归在 Workflow 视图派发 `workflow_started` / `workflow_snapshot` 事件
- **WHEN** 应用自身的异步初始化（`chat.js` 的 `init()`）可能在该派发之后才完成
- **THEN** 测试 SHALL 在派发前等待应用初始化落定，使后到的初始化不会改动画面的激活视图
- **AND** 就绪判据 SHALL 在本测试的 fixture 下真实成立，SHALL NOT 退化为固定等待

#### Scenario: 就绪判据失效可被察觉

- **GIVEN** 某条就绪判据因被测界面变化而不再成立（元素消失、文案改写）
- **WHEN** 运行浏览器回归
- **THEN** 该失效 SHALL 表现为测试失败或有边界的时间上限，SHALL NOT 静默变成「恒真」而继续通过
