# Proposal: 多标签页瞬态交互状态隔离 + 浏览器测试去时序依赖（fix-issue-191）

## Change Type

- primary: bugfix
- secondary:
  - web-ui

## Why

issue #191 记录：全量 pytest 高负载下 `test_multi_tab_slash_suggestion_isolation`
偶发超时失败，单独跑、web 子集跑、两次完整跑均通过。issue 的根因判断是「浏览器测试在高负载下的时序问题」。

排查（探针实测，见下）确认这不是单纯的测试写法问题，而是**两层叠加**：

### 第一层：测试依赖一个 100ms 墙钟窗口

`web/static/chat.js` 的输入框 `blur` 处理器把收起动作挂在
`setTimeout(hideSlashSuggestions, 100)`——一个**100ms 的宽限窗**，本意是「点建议项时的
mousedown→blur 不该把列表收掉，留 100ms 让点击落地」。

测试的时序恰好压在这个窗口上：

```
fill(tab2, "/s")   → tab2 建议可见
click(tab1)        → tab2 输入框 blur，挂起 100ms 定时器
click(tab2)        → 切回 tab2
                     ↑ 若这两次 click 的间隔 < 100ms，定时器在「tab2 已是 active」之后才触发，
                       于是把 tab2 自己的建议收掉 → 末尾 wait_for_function 超时
```

**探针实测（`/tmp/probe191.py`，同一序列，只改两次 click 的间隔）**：

| 切走→切回间隔 | 结果 |
|---|---|
| 0ms（默认，无等待） | **FAIL 2/2** |
| 150ms | PASS 2/2 |
| 500ms | PASS |

即：**间隔短于 100ms 就必失败**。测试是否通过，取决于两次 `page.click()` 的墙钟耗时
是否超过 100ms——这正是「高负载下才偶发」的来源，也解释了为什么单独跑（机器空闲、
click 快）反而更容易踩中。

### 第二层：生产代码存在跨 tab 状态泄漏（真正该修的 bug）

`blur` 处理器是**无归属的全局函数**：

```js
tab.inputEl.addEventListener('blur', () => { setTimeout(hideSlashSuggestions, 100); });
```

`hideSlashSuggestions()` 读写的是**触发时刻的 active tab** 所绑定的全局
`slashSuggestionsEl`（`bindActiveTab` 在切 tab 时重指）。于是**「哪个 tab 失焦」与
「收掉哪个 tab 的建议」被解耦**：

```
tab2 输入 /s，建议可见
click(tab1)        → tab2 失焦，挂起定时器
在 tab1 里输入      → tab1 焦点
click(tab2)        → tab1 失焦，挂起定时器 T1
click(tab2 输入框)  → tab2 焦点，建议仍应可见
T1 在 100ms 后触发 → active 是 tab2 → 收掉 tab2 的建议   ← 泄漏：tab1 的失焦收掉了 tab2 的列表
```

**探针实测（`/tmp/probe191b.py`，场景 B：失焦发生在非 active tab）**：

| | 场景 B（跨 tab 失焦后 active tab 的建议是否还在） |
|---|---|
| 原实现 | **False（被收掉）** |
| 候选修复 | True |

这条泄漏恰好就是失败测试**自称要验证的不变量**——测试文件名与 docstring 写的是
「两个 tab 的 slash 匹配状态互不串扰」，而它用的实现恰恰会串扰。测试偶发失败并非误报，
它**偶尔真的抓到了这个 bug**，只是失败信息表现为「超时」，看不出因果。

## What Changes

**A. 生产代码：把 slash 建议的可见性变成「按 tab 归属」的确定状态**

消除「失焦事件」与「被收起的列表」之间的解耦。候选方案与取舍见 `design.md`（本 change
的核心设计决策，grill 重点）。

独立 grill 实证后，选定的 B 方案需**两处修正**（初版 design 未写，均已独立复现）：

- **收敛只在「非 active → active」切换上发生**（D1b）。否则 `inputEl` keydown 处理器开头的
  `switchTab(tab.id)` 会复活列表，使 `Escape` 收起后按 `Enter` 被误判为「应用建议项」而
  **永久吞掉发送**（对照实测：原实现 2 条消息 / 朴素收敛 1 条 / 加守卫 2 条）。
- **`blur` 守卫的 `document.activeElement` 检查是必要的**（D3），不是可选防御：去掉它，
  「点空白失焦后 100ms 内点回输入框」会把列表错误收掉。

**B. 测试：去掉时序依赖 + 补确定性回归测试**

- `test_multi_tab_slash_suggestion_isolation` 不再依赖两次 click 的间隔；
- 新增一条**跨 tab 失焦不干扰**的确定性回归测试（对旧实现 100% 失败，见 A 的探针场景 B）；
- 按 issue #191「避免偶发失败无输出」的要求，给该文件的浏览器等待加**显式超时**与
  **可读失败信息**（当前用的是 Playwright 默认 30s，超时信息只有选择器，难以定位）。

**C. 规格：把「瞬态交互状态按 tab 隔离」写成不变量**

现有 `web-ui` spec 的「Web UI 支持多标签会话」只覆盖**消息历史与运行状态**（「一方消息与
运行状态 SHALL NOT 影响另一方」），**没有覆盖瞬态 UI 状态**（建议列表等）。本次泄漏正落在
这个空白里，补一条 Requirement 并复用既有 Scenario 结构。

## Non-Goals

- **不改 100ms 宽限窗本身**：它有正当用途（让建议项的 mousedown 点击不被 blur 抢掉）。
  本 change 改的是**它的作用域**，不是它的时长。
- **不重构 `chat.js` 的全局代理架构**：`bindActiveTab` 用全局变量代理 active tab 是本文件的
  既有设计，全量重构超出 bugfix 边界。本 change 只消除这一处的归属错配。
- **不引入测试重试插件**：`pytest-rerunfailures` 之类会把真实 flake 掩盖成「重试通过」，
  与 issue #191「定位超时点」的要求相反。
- **不做全仓浏览器测试去 flake**：只处理本文件暴露出的这一类（瞬态状态跨 tab + 等待信息不足）。

## Capabilities

### Modified Capabilities

- `web-ui`：新增「多标签页瞬态交互状态隔离」Requirement——slash 建议等按 tab 归属的瞬态
  UI 状态 SHALL NOT 被其他 tab 的事件改变；并列明活跃 tab 的建议可见性由「该 tab 自身的
  输入内容」唯一决定。既有「Web UI 支持多标签会话」Requirement 的「消息与运行状态隔离」
  不覆盖此语义，故为 ADDED 而非 MODIFIED。

## Dependencies

- 无新依赖（不引入测试重试/等待插件）。

## Impact Analysis

**代码影响**

| 文件 | 改动 | 风险 |
|---|---|---|
| `web/static/chat.js` | 输入框 `blur` 处理改为按 tab 归属；`switchTab` 同步该 tab 的建议状态 | **中**（改的是 UI 状态机的一处归属语义，会影响「切走再切回」的可见性表现） |
| `tests/web_tests/test_multi_session_browser.py` | 去时序依赖 + 新增跨 tab 回归测试 + 显式超时与可读失败信息 | 低 |

**契约影响（对外）**

- **可见行为会变**：切走再切回到某 tab 时，其 slash 建议的可见性从「受 100ms 定时器与
  切回时机共同决定」变为**由该 tab 自身的输入内容唯一决定**。这是**有意的**（现状是竞态，
  没有可依赖的语义），但属用户可见行为变更，已在 spec 写明并在 `design.md` 讨论取舍。
- **公告范围已按 grill 实测补全**（初版只写了「切走再切回」一条）：该语义还改变两条从
  **非切换路径**进入、但同样在切回时被重新判定的场景——
  (1) 用户**点击页面空白处**收起列表后切走再切回：原实现保持收起，新实现按输入内容**重新出现**；
  (2) 用户**应用了某个建议项**（输入框留下完整命令、列表收起）后切走再切回：原实现保持收起，
  新实现重新出现（命令仍匹配）。
  两条都是「可见性由输入内容决定」的直接推论，但**用户可能预期「我主动收起过就该保持收起」**——
  该语义边界列入 Open Question Q1 由用户拍板；若选「保持收起」，需在 tab 上多记一个
  `userDismissed` 位。
- **`Escape → Enter` 行为必须保持**：`Escape` 收起建议后 `Enter` SHALL 照常发送消息。
  这是新方案引入的回归风险点（见 What Changes A 的第一条修正），已由回归测试锁定。
- **保留 100ms 宽限窗**，但**理由修正**：初版称它服务于「建议项 mousedown → blur → click 的
  点击落地」——**该因果经实测不成立**（建议项用 `mousedown` + `preventDefault`，焦点从未离开，
  blur 计数恒为 0）。真实理由是它决定「失焦后多久内点回来不算数」这一可感知窗口。

**测试影响**

- 改造：`test_multi_tab_slash_suggestion_isolation`（去掉时序依赖）
- 新增：跨 tab 失焦不干扰的确定性回归测试（**对旧实现必须失败**——变异验证）
- 回归：`tests/web_tests/`（重点 `test_multi_session_browser.py`、`test_multi_session.py`；
  另需确认 `test_reconnect_pending_interaction_browser.py` 等其它浏览器测试不共享该假设）
- **变异验证**：把 `blur` 处理改回无归属版本，新回归测试必须变红；还原后变绿
- **去 flake 验证**：修复后在**同一台机器、同一序列**重复跑 N 次（探针的 0ms 间隔场景）
  必须全绿——这是 issue #191 的直接验收口径

**文档影响**

- `openspec/specs/web-ui/spec.md`（ADDED：瞬态交互状态按 tab 隔离）
- `docs/openspec-change-backlog.md`（登记 + 完成后移除）
- 关键词扫描 `docs/`、`README.md`、`AGENTS.md`、`CONTEXT.md` 中与多标签页 / slash 建议 /
  浏览器测试 flake 相关的段落

## Reference Implementation Research

- research_tier: light
- status: enabled
- reason: 属 bugfix（无新增能力面），但含**一处用户可见行为变更**（切回 tab 的建议可见性语义），
  且新增 spec 不变量；「多标签页前端如何归属瞬态 UI 状态」是有成熟先例的局部模式应用，按 `light` 档做浅调研。

- findings:
  - **多标签编辑器/终端类 UI（VS Code、iTerm2、tmux 客户端）的通行做法是「瞬态 UI 状态挂在
    tab/pane 对象上，事件回调用归属对象做守卫」**，而不是让事件回调去读「当前谁的 active」——
    后者会在异步回调（定时器、网络）里读到切换后的 active。本 change 的泄漏正是这一类的经典
    形态（异步 `setTimeout` 回调读了触发时刻以外的 active）。
  - **「失焦后延迟收起」的宽限窗（blur grace period）在 autocomplete 实现里是标准模式**
    （如 jQuery UI Autocomplete 的 `delay`、VSCode suggest 的 `blurDelay`），其实现要点是
    **定时器句柄与它所属的组件实例绑定**，并在组件重新激活时取消挂起的收起。本项目缺的正是
    句柄绑定与取消。
  - 本地参考仓库不可用（当前工作区无 `.dev/reference-repos.txt`），findings 来自业界通行实现
    模式的归纳；本 change 的具体证据以**本仓探针实测**为准（见「Why」两处表格）。

- design impact:
  - 采用「瞬态状态按 tab 归属 + 切换时以输入内容为准重新求值」的方向：让 `switchTab` 成为
    该 tab 建议状态的**唯一权威**，`blur` 只对**当前 active 且确实仍失焦**的 tab 生效。
  - 具体候选与取舍见 `design.md`。
