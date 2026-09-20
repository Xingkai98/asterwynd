# Diagnosis — fix-issue-191

## Symptom

全量 pytest 高负载下 `tests/web_tests/test_multi_session_browser.py::test_multi_tab_slash_suggestion_isolation`
偶发超时失败；单独跑、web 子集跑、以及两次完整跑均通过（issue #191 原文）。失败表现为
Playwright 等待超时，**信息里只有选择器，看不出因果**——issue 因此把处置写成
「定位超时点，加显式等待/重试或拆分断言」+「避免偶发失败无输出」。

## Reproduction

**探针一（间隔阈值，`/tmp/probe191.py`）**：在同一次浏览器会话里跑该测试的完整序列，
只改变「切到 tab1」与「切回 tab2」两次 click 之间的等待时长。

| 切走→切回间隔 | 结果 |
|---|---|
| 0ms（测试默认，无等待） | **FAIL 2/2** |
| 150ms | PASS 2/2 |
| 500ms | PASS |

即：间隔短于约 100ms 就必失败，长于约 110ms 必通过（grill 独立复测的阈值为
「≤ ~102ms 失败、≥ ~110ms 通过」）。**测试是否通过取决于两次 `page.click()` 的墙钟耗时**——
这正是「高负载下才偶发」的来源，也解释了为什么机器空闲、click 更快时反而更容易踩中。

**探针二（跨 tab 泄漏，`/tmp/probe191b.py` 场景 B）**：让失焦发生在**非 active** 的标签页，
观察 active 标签页的建议列表：

| | active tab 的建议是否还在 |
|---|---|
| 原实现 | **False（被错误收掉）** |
| 候选修复 | True |

## Evidence

**证据一：测试的时序恰好压在 100ms 宽限窗上。**

`web/static/chat.js:156` 的 `blur` 处理器把收起动作挂在 `setTimeout(hideSlashSuggestions, 100)`。
测试序列 `fill(tab2,"/s") → click(tab1) → click(tab2)` 在两处形成竞态：

```
fill(tab2, "/s")   → tab2 建议可见
click(tab1)        → tab2 输入框 blur，挂起 100ms 定时器
click(tab2)        → 切回 tab2
                     ↑ 间隔 < 100ms 时，定时器在「tab2 已是 active」之后才触发，
                       把 tab2 自己的建议收掉 → 末尾 wait_for_function 超时
```

**证据二：这不是纯测试问题，而是生产代码的跨 tab 状态泄漏。**

`blur` 处理器是**无归属的全局函数**——`hideSlashSuggestions()` 读写的是**触发时刻的 active tab**
所绑定的全局 `slashSuggestionsEl`（`bindActiveTab` 在切 tab 时重指）。于是「哪个 tab 失焦」与
「收掉哪个 tab 的建议」被解耦：tab1 的失焦可以收掉 tab2 的列表。

**这条泄漏恰好就是失败测试自称要验证的不变量**——测试名与 docstring 写的是「两个 tab 的
slash 匹配状态互不串扰」，而它用的实现恰恰会串扰。**测试偶发失败并非误报：它偶尔真的抓到了
这个 bug，只是失败信息表现为「超时」，看不出因果。**

**证据三：独立 grill 插桩复现（`reviews/grill-design.md`，run `grill-fix-issue-191-2026-09-20-001`）。**

grill 用 `page.route` 拦截 `/static/chat.js` 注入候选实现，在不改仓库的前提下做对照实验：
确认跨 tab 泄漏在 ORIG 上稳定复现（`tab2_t0 可见 → tab2_t400 被收掉`），并测得「长按鼠标
>100ms 再释放」时定时器先于 `switchTab` 触发、此刻 active 仍是原 tab —— 这是方案 A
（仅归属化）无法消除的翻转缺陷。

## Root Cause

两层叠加，缺一不可：

1. **测试层**：断言依赖一个 100ms 墙钟窗口——是否通过取决于两次 click 的耗时，而非被测行为。
2. **实现层**：`blur` 收起动作**没有归属**。它是异步回调，却在触发时刻读「当前 active tab」
   的全局代理；而 `switchTab` 又不修复该状态，于是瞬态 UI 状态在标签页之间泄漏。

第 2 层是根因，第 1 层是它得以表现为「偶发超时」的形式。只修测试层会把真实 bug 掩盖成
「放宽等待后通过」。

## Recommended Direction

**实现**：把 `blur` 收起动作按 tab 归属（闭包捕获 `tab` + `getActiveTab()` 与
`document.activeElement` 双重守卫 + 定时器句柄挂 `tab.blurHideTimer`），并让 `switchTab`
成为该 tab 建议状态的**收敛点**。收敛**只在「非 active → active」的切换上发生**——否则
`inputEl` keydown 处理器开头的 `switchTab(tab.id)` 调用会复活列表，使 `Escape` 后的 `Enter`
被误判为「应用建议项」而**永久吞掉发送**（已独立复现：ORIG 2 条消息 / 朴素收敛 1 条 / 加守卫 2 条）。

**测试**：去掉对间隔的依赖；补两条**判别性**回归测试——「收起后切走切回按输入内容重新判定」
与「慢 click（按住 >100ms）」，它们是「归属化但无收敛」与「有收敛」的唯一区分器
（仅 Scenario 1/2 风格的断言杀不死半吊子实现）；再补 `Escape → Enter` 回归测试。
另需处理测试 fixture 的 tab id rekey 陷阱（`new-N` → 真实 session id），否则新测试自身即为新 flake 源。

**规格**：在 `web-ui` 补齐「多标签页瞬态交互状态按标签页隔离」Requirement——既有
「Web UI 支持多标签会话」只覆盖消息历史与运行状态，未覆盖瞬态 UI 状态。

## Regression Tests

- `test_multi_tab_slash_suggestion_isolation`（改造）：去掉墙钟依赖，改为断言「切回后建议可见」，
  并显式覆盖「间隔短于宽限期」这一原本失败的档位。
- 新增：**非活跃标签页的失焦不干扰活跃标签页的建议**（对旧实现 100% 失败）。
- 新增：**收起后切走再切回按输入内容重新判定**（对「归属化但无收敛」的实现失败）。
- 新增：**慢 click（mousedown 后按住 >100ms 再释放）后切回**（对「仅归属化」的实现失败）。
- 新增：**`Escape` 后 `Enter` 仍能发送消息**（对「无条件收敛」的实现 100% 失败）。
- 变异验证：逐条把实现改回对应的坏版本 → 对应测试必须变红 → 还原后变绿。

## 归档证据

- 独立 grill：`openspec/changes/fix-issue-191/reviews/grill-design.md`
  （run `grill-fix-issue-191-2026-09-20-001`，10 Confirmed Decisions + 3 Open Questions）
- 探针脚本：`/tmp/probe191.py`、`/tmp/probe191b.py`、`/tmp/verify191.py`（主 agent）；
  `/tmp/grill_191/*.py`（grill，全部在仓库外，未落盘）
- 基线：`eb50f8a`（`master`），分支 `fix-issue-191/2026-09-20`
