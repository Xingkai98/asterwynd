# Building Review: fix-issue-226-browser-test-flake

## Reviewer

- run id: `review-fix-issue-226-browser-test-flake-r1`（独立零记忆 subagent，未继承开发上下文；结论只来自实读代码 / 实跑输出 / change 文档）
- 时间: 2026-09-24
- base: `d757683`（origin/master） head: `a3d1ae8`（3 commit）
- 审阅方法：逐条核对 tasks 的 `[x]` 与代码实际状态；**两条回归测试各做一次变异验证**（改测试侧屏障 → 实跑 → 恢复，`git status` 干净）；实跑相关子集、checker 与 strict validate；独立重算暴露面（不采信 D6 的 15/6/3，自建口径重数）；对 15 条改造用例逐 hunk 核对「只加屏障、未改断言」（`git diff -U0 | grep '^-'` 全量过一遍删除行）
- 资源纪律：全程单进程、串行、无并发；未跑全量

## Verdict

**CHANGES_REQUESTED**

核心结论我**独立复现并确认成立**：两条回归测试都有真实判别力（变异后**都实跑转红**，见 Test Results），15 条用例**只加屏障、未改断言**（删除行全量核对），`initDone` 接缝**只增不改且不改变失败模式**（不带 `onRejected`，与 `init()` 裸调用的 unhandled rejection 语义等价），delta 与权威 spec **逐字节一致**，checker / strict validate 均通过，无 CI 弱化。

请求修改的原因是 **1 条 major + 若干 minor**，均小而具体：新引入的 `test_ready_barrier_fails_loudly_when_signal_is_absent` 存在**仍在生效的竞态窗口**（实测证据见 I1 —— 一个「消灭 flake」的 change 不该自己带进一条可能间歇红的用例，且改法只有两行）；其余为文档与拍板口径不一致（I2/I3/I4/I7）。没有 blocker：不存在生产行为漂移、spec 错位、安全检查缺失或 CI 弱化。

## Tasks Verification

逐条核对 `tasks.md` 的 `[x]`（只列有实质内容者；「真实存在/与描述不符」是结论）：

| 任务 | 结论 | 证据（实读/实跑） |
|---|---|---|
| 1.1 / 1.2 spec delta | **真实存在** | `openspec/changes/.../specs/web-ui/spec.md` 两条 Requirement：接缝（2 Scenario）+ 就绪屏障（3 Scenario）齐全，首行均含 SHALL |
| 1.3 范围/非目标/验收 | **真实存在** | `proposal.md` Change Type / Why / What / Non-Goals / Impact Analysis 齐 |
| 1.4 grill 证据 | **真实存在** | `reviews/grill-design.md`：5 条 Confirmed Decisions + 5 条 Open Questions 逐条配具体例子 + `## User Confirmation` 5/5 有实质答复与时间（无占位文本） |
| 1.5 Impact Analysis | **真实存在** | `proposal.md:96-130`，「待确认影响面」已清理为「无」 |
| 1.6 RIR | **真实存在** | `proposal.md:132-138`，`research_tier: exempt` + reason 命中 `bugfix` / `#191` / `#223` / `openspec/changes/archive/`；findings 记录本地参考仓库与 `.codegraph` 不可用事实（我确认两者确实不存在） |
| 1.8 当前规格同步 | **真实存在且逐字一致** | 见下「Spec 对齐」 |
| 2.1 回归 A | **真实存在** | `test_multi_session_browser.py:851`；CDP 注入 3000ms；**正向半场**（无负向半场，与 2.1 描述一致）；但断言的阈值与 2.3 描述不符 → I2 |
| 2.2 回归 B | **真实存在** | `test_workflow_graph_browser.py:1200`；`INIT_DELAY_MS = 6000`（`:30`）；**只调 `_wait_app_ready`、不调 `_ensure_workflow_view`**（我用 grep 逐行确认，测试体内无该 helper 调用） |
| 2.3 断言注入生效 | **部分与描述不符** | 回归 B 的「`initDone` 在延迟窗口内为 `false`」真实存在（`:1226-1231`）；回归 A 的「实测等待 ≥ **注入值**」实为 `>= injection_ms * 0.5`（`test_multi_session_browser.py:888`）→ I2 |
| 2.4 变异验证 | **描述成立，但 change 内无留档** | 我独立实跑两向：见 Test Results。`tasks.md` / `design.md` / `diagnosis.md` 均未记录变异实测输出，仅 backlog 一句「均已在实现期实测两向通过」 |
| 2.5 `initDone` 语义验证 ×2 | **真实存在** | ①完成态置位：`test_chat_init_seam_reports_completion:1255`（`_wait_app_ready` + `is True`）；②未完成态 + 延迟窗口：`test_workflow_view_survives_delayed_app_init:1220-1231`（`early is False`） |
| 2.6 负向路径守护 | **真实存在** | `test_ready_barrier_fails_loudly_when_signal_is_absent:1281`（删信号 → `pytest.raises(TimeoutError)`）；实跑 8 次全过。但有竞态窗口 → I1 |
| 2.7 不依赖机器负载 | **成立** | 注入走 CDP / `page.route`，无 sleep 型断言 |
| 3.1 修 `_wait_app_ready` 死等 + 删降级 | **真实存在** | `:148-152`（原 `try/except + wait_for_timeout(300)` 已删净，全文件 grep 无残留）；`BROWSER_TIMEOUT_MS = 15000` 在本文件自有（`:26`） |
| 3.2 15 条接屏障 | **真实存在，且只加屏障** | 15 条与 tasks 清单 `:168/:198/:216/:233/:275/:333/:392/:433/:467/:573/:642/:664/:745/:905/:939` 一一对应；`git diff -U0` 的删除行**只有** `_wait_app_ready` / `_ensure_workflow_view` 两个 helper 自身的正文，**无任何断言被删改** |
| 3.2b `:168` 插入位置 | **真实存在** | `_ensure_workflow_view` 在 `assert await page.is_visible("#workflow-view")` 之后、svg 等待之后（现文件 `:198-202`） |
| 3.2c `_ensure_workflow_view` 补 `startTicker` | **真实存在** | `:170-173`（与 `onWorkflowStarted()` 同一次 evaluate，幂等性我在 `workflow.js:525-528` 核实）；副作用复核：全仓 `grep stopTicker` 在 tests/ 只命中注释，**无任何用例依赖 ticker 停摆** |
| 3.3/3.4/3.5 三条改 `_open_two_tabs` | **真实存在** | `:275`（independent_messages）/`:740`（exit_reconnect）/`:798`（approval_isolation）；删除行仅导航与旧屏障（`.session-tab`长度 / `.user-input`），断言未动 |
| 3.6 `chat.js` 只增不改 | **真实存在** | `web/static/chat.js:2125`（`initDone: false`）+ `:2128`（`init().then(...)`，无 `onRejected`）。唯一删除行是 `-init();`，语义等价（见下 Q1 复核） |
| 3.7/3.8 回写影响面/RIR | **真实存在** | `proposal.md` 的「待确认影响面」已清为「无」；RIR 未被推翻 |
| 4.1–4.4 子集/重复跑/全量 | **自述，无可核对留档** | change 内无日志或次数记录。我可复现的部分成立：子集 47 passed（见 Test Results） |
| 4.5 / 4.6 / 4.7 门禁三件套 | **真实存在（我实跑复核）** | strict validate 30/30；artifact checker `OpenSpec artifact checks passed`（exit 0）；全量 pytest 未跑（资源纪律） |
| 4.9 spec 同步 | **真实存在** | 见「Spec 对齐」 |
| 5.3 更正 known-debt | **真实存在** | `docs/known-debt.md:307-315`，有 `protected_artifact_explained` 事件（`workflow-events.jsonl` seq 5）；措辞略绝对 → I8 |
| 5.4 新增 issue #226 记录 | **只改了 known-debt.md** | `docs/known-debt.md:318-343` 新增条目；`docs/known-issues.md` **未动**——实读该文件后我判断**不动是对的**（它是 pytest pattern 豁免清单，不是 issue 台账），但 task 原文「两文件」措辞需修正 → I8 |
| 5.5 接缝注释 | **真实存在** | `chat.js:2117-2124` 写明测试专用 / 零生产行为 / 不得当死代码移除 |
| 5.6 backlog 登记 | **真实存在** | `docs/openspec-change-backlog.md:154-156`（第十六批）；`backlog_updated` 事件 seq 1/4 齐 |

**未勾任务**：6.1–6.4、7.1–7.6（审阅/归档/PR 收尾），其中 7.6 已正确标注 `(post-merge)`。归档点门禁要求除 `(post-merge)` 外全部勾选 —— 现状态符合「审阅进行中」的中间态，不是缺陷。

**Spec 对齐**：delta 与 `openspec/specs/web-ui/spec.md` 我做了字节级比对（去掉 `## ADDED Requirements` 头与尾部空行后 `diff` 为空，48 行 vs 48 行）——**逐字一致**，无「两处口径漂移」。两条 Requirement 首行均含 SHALL（满足 strict validate 的正文首行规则）。

**暴露面独立重算（不采信 D6）**：以「用例依赖 workflow 视图处于激活态」为口径逐函数数：

- 零屏障 = `:168/:198/:216/:233/:275/:333/:392/:433/:467/:573/:642/:664/:745/:905/:939` = **15 条** ✓
- 只有死等（调旧 `_wait_app_ready`、无 `_ensure_workflow_view`）= `:619/:708/:769/:821/:868/:983` = **6 条** ✓
- 有真屏障 = `:487/:1039/:1084` = **3 条** ✓

**24 = 15 + 6 + 3，与 D6 / proposal / diagnosis / backlog 四处口径完全一致**，且 `test_session_without_workflow_is_unaffected` 被正确排除（它断言的是「workflow-view **不** active」，与根因 B 反向，不受影响）。这一项是我最想挑的算术，结果无误。

**「未修必红」的两向验证我也重做了**（见 Test Results），判别力不是纸面声明。

## Issues

### I1（major，新增用例的竞态 → 可能间歇红）

`tests/web_tests/test_workflow_graph_browser.py:1292`：`delete window.AsterwyndChatTest.initDone` **不保证**该标志此后不再被置位——若 `init()` 尚未 resolve（`chat.js:2128` 的 `.then` 回调仍挂起），回调会在 delete **之后**把 `initDone` 重新设回 `true`，`_wait_app_ready` 立刻返回，`pytest.raises(PlaywrightTimeoutError)` 失败。

**实测证据**：我用同一 preamble 的兄弟用例插桩实测「`goto` 返回后、再一个 CDP 往返时 init 是否已完成」，3 次采样得到 `early=True / **False** / True` —— 即 `init()` 在 load 之后仍可能挂起，窗口是活的。本用例比采样点只多一次 `wait_for_function`（rAF 轮询 ≥1 帧），余量约几十毫秒。

**未复现**：本题单独实跑 8 次**全部通过**，且每次都是 ~17.4s（= 15s 超时路径 + 建环境），说明这 8 次里 init 都已在 delete 前 resolve 完。所以是**低频窗口，不是必现**——但它是「消灭 flake 的 change 自己带进一条可能间歇红的用例」，且失败正文会是 `DID NOT RAISE`（与真因无关，误导性极强）。

**建议修法（两行，确定性）**：先等信号置位再删，删除后不可能被重设——

```python
await _wait_app_ready(page)                              # 先确保 init 已 resolve（此后无人再置位）
await page.evaluate("() => { delete window.AsterwyndChatTest.initDone; }")
with pytest.raises(PlaywrightTimeoutError):
    await _wait_app_ready(page)
```

### I2（minor，与用户拍板参数不一致且 tasks 描述未同步）

`tests/web_tests/test_multi_session_browser.py:888` 实为 `handshake_ms >= injection_ms * 0.5`，而 Q4 的用户答复（`reviews/grill-design.md:40`）与 `tasks.md` 2.3 都写「断言**实测等待 ≥ 注入值**」。我实测 `handshake_ms = 3095ms`（注入 3000ms，见 Test Results）——**照拍板原文写反而只有 ~3% 余量、会自己变成新 flake**，所以 0.5 这个放宽是**技术上更优**的；问题在于它是**未记录的偏离**：tasks 2.3 勾了但描述与实际不符。建议二选一并回写 tasks/design：①保留 0.5 并把 2.3 描述改成实际口径 + 写明理由（推荐；判别力不受影响，见 Test Results 的变异实跑）；②改回 `>= injection_ms` 并接受 3% 余量。

### I3（minor，design.md 与实现不同步）

`design.md:128` 与 Testing Strategy `design.md:191` 仍写「根因 A 回归：断言『无屏障时消息发不出（前置条件），有屏障时成功发出』」——**负向半场已按 Q4/监督侧裁定移除**（`tasks.md` 2.1 有记录），design 未回写；同一段还写「断言实测等待 ≥ 注入值」（见 I2）。design 是后续实现者/审阅者的第一入口，留旧口径会让人重新加回那个已被裁定会赛跑的负向半场。

### I4（minor，Non-Goal 的「已核实不受影响」结论口径过宽）

`proposal.md:93` 声明不覆盖 `test_browser.py` / `test_reconnect_pending_interaction_browser.py`，理由「已核实它们建新会话后都等了 `connected`」。我实读：`test_browser.py:152-157`（`_open_chat`）与 `test_reconnect_pending_interaction_browser.py:158-163`（`_open_new_session`）都是 `goto → wait_for_selector("#hub-view.active") → click("#hub-new-btn")`，而 `#hub-view` 在 `index.html:43` **静态即 `class="view active"`** ⇒ 该等待不蕴含 `setupHub()`（`chat.js:2076`）已跑；`#hub-new-btn` 的处理器在 `setupHub()` 内挂（`chat.js:2039` 起），点击可能静默落空。**这两条正是新 `_wait_app_ready` docstring（`test_multi_session_browser.py:96-101`）自己点名的那个竞态**。「等了 connected」只覆盖**发送腿**，不覆盖**点击腿**。

两个可选处置（都不必扩本 change 范围）：①在这两处也接一个就绪等待（`_wait_app_ready` 等价物）；②如实把 Non-Goal 措辞收窄为「发送腿已屏障、点击腿未覆盖」，并在 `docs/known-debt.md` 记一条后续面。**不要**保持「已核实不受影响」的现状。

### I5（minor，冗余：第 4 份重复 preamble 未收敛）

`tests/web_tests/test_multi_session_browser.py:703-716`（`test_multi_tab_image_preview_isolation`）仍是 9 行 inline「开预置 tab + 新建 tab」preamble，与 `_open_two_tabs`（`:108`）逐行同构（仅少 rekey 等待）。本 change 把另 3 条收敛到 helper，却留下这第 4 份拷贝；顺带 `diagnosis.md:78` 的表格「其余 15 条｜是（`_open_two_tabs`，含 rekey 屏障）」对**这一行**不准确（全文件 19 条用例里 13 条用 helper、1 条用 inline 拷贝、5 条单 tab）。建议顺手改用 helper（该用例不发送消息、断言与 rekey 无关，属纯收敛）。

### I6（minor，改造后的残留冗余/陈旧注释）

`test_workflow_graph_browser.py:808` 在 `:807` 的 `_ensure_workflow_view(page)`（已含 `startTicker()`）之后又显式 `startTicker()`，而上方注释仍写「harness 直接派发事件…所以计时器得手动启动」。行为无害（`startTicker` 幂等），但注释现在是半陈旧的，建议保留其一。

### I7（minor，任务措辞与实际不符：5.4）

`tasks.md` 5.4 写「`docs/known-issues.md` / `docs/known-debt.md` 新增一条」。实际只改 `known-debt.md`。我实读 `docs/known-issues.md` 后认为**只改 known-debt 是正确选择**（该文件是「phase gate 机械检查豁免」的 pytest pattern 清单，不是 issue 台账），所以这是任务措辞问题，建议把 5.4 措辞改成「known-issues.md 经核实不适用（pattern 清单），只记 known-debt」。

### I8（minor，两处文档措辞/前向引用）

- `docs/known-debt.md:309` 引用 `openspec/changes/archive/2026-09-24-fix-issue-226-browser-test-flake/`，该路径**当前不存在**（归档是 tasks 7.1，未执行），且同段以「2026-09-24 归档」的完成时口吻叙述。归档 PR 执行后自洽，但请确认 7.1 必做（否则留下死链）。
- 同段「该断言不成立，已作废」略绝对：原文「把『渲染了但被切走』这一类间歇红治住」对**当时调用它的 3 条用例**其实是成立的（helper 确实拉回视图），不成立的是「这一类」的外推。建议改成「只对被覆盖的 3 条成立、不构成整类屏障」以免后人误读为「该 helper 一直无效」。

### 非问题（我主动挑战过、结论是没问题）

- **`chat.js` 是否真的「只增不改」**：diff 唯一删除行是 `-init();`，替换为 `init().then(...)`。失败模式等价（`.then` 不带第二参数 ⇒ 派生 promise 同样产生 unhandled rejection，与今天一致；带 `onRejected` 才会吞掉，Q5 已正确否决）。`window.AsterwyndChatTest` 对象在 `:2103` 先于 `:2128` 的 `init()` 调用存在 ⇒ 谓词里的存在性守卫不会因时序而 TypeError。
- **`_ensure_workflow_view` 补 `startTicker()` 是否让既有 tick 用例失真**：不会。全仓 tests 里无 `stopTicker` 调用/断言；三个 tick 用例断言的是「状态词不含 undefined」「进度不丢」「耗时跳秒」，ticker 只为后两者提供前置；`:754` / `:817` 两条根本不走本 helper。
- **回归测试自证风险**：回归 B **确实没有**调 `_ensure_workflow_view`（逐行确认），否则未修也会被强行拉回；我把它下面的 `_wait_app_ready` 退回旧实现后实跑**转红**，证明没有自证。
- **spec 中「测试专用、不得当死代码移除」是否可机械校验**：不能直接校验（无 JS lint），但 `test_chat_init_seam_reports_completion` 是**有效守护**——`early in (True, False)` 在属性被删/被改名时取到 `undefined`/`None` 而失败，`_wait_app_ready` + `is True` 再锁一次置位语义。是「间接但真实」的守护，change 与 debt 文档对此的表述（「唯一可执行守护」）准确。

## Test Results

全部单进程串行（无并发、无加压）；命令前缀 `export PATH=/home/happy/.local/bin:$PATH`，工作目录为本 worktree。

| # | 命令 / 操作 | 结果 |
|---|---|---|
| 1 | `uv run pytest tests/web_tests/test_multi_session_browser.py tests/web_tests/test_workflow_graph_browser.py -q` | **47 passed** in 119.40s（含 3 条新用例与 18 条改造用例） |
| 2 | **变异 1（回归 B 判别力）**：把 `_wait_app_ready` 退回旧实现（`wait_for_selector(".tab-pane.active .user-input", 5000)` + `except → wait_for_timeout(300)`）→ 跑 `test_workflow_view_survives_delayed_app_init` | **FAILED**（14.67s）：`AssertionError: init 落定后派发 workflow 事件，#workflow-view 应保持激活 / assert False` — 即「未修必红」成立、无自证。随后 `git checkout --` 还原 |
| 3 | **变异 2（回归 A 判别力）**：把 fill+click 移到 rekey 屏障**之前**（复刻未修版发送时机）→ 跑 `test_new_tab_send_survives_slow_handshake` | **FAILED**（20.99s）：`wait_for_selector(".tab-pane.active .message.assistant")` 超时 — 消息确实没发出去（注入生效下的发送落空），判别力成立。随后还原 |
| 4 | 插桩实测回归 A 的注入余量（临时 `print`，已还原） | `PROBE handshake_ms=3095`（注入 3000ms），用例 6.00s 通过 → 注入**确实生效**（CDP `emulateNetworkConditions` 未被淘汰），且余量 ≈95ms ⇒ 见 I2（严格 `>= 3000` 只有 ~3% 余量） |
| 5 | 插桩实测 `init` 完成时刻（临时 `print`，已还原），3 次采样 | `early=True / False / True` ⇒ load 之后 init 仍可能挂起，I1 的窗口是活的 |
| 6 | `test_ready_barrier_fails_loudly_when_signal_is_absent` 单跑 **8 次** | **8/8 passed**，每次 ~17.4s（走满 15s 超时路径）⇒ I1 未复现，属低频窗口 |
| 7 | `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py` | `OpenSpec artifact checks passed`（exit 0） |
| 8 | `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` | **30 passed, 0 failed**（含 `spec/web-ui`） |
| 9 | delta ↔ 权威 spec 字节比对（`awk` 抽节 + `diff`） | 一致（48 行 vs 48 行，差异仅为 delta 的 `## ADDED Requirements` 头） |
| 10 | 暴露面独立重算 + 删除行全量核对 | 15/6/3=24 与 D6 一致；两测试文件的删除行只有 helper 正文与旧导航 preamble，无断言删改 |
| 11 | 全量 pytest | **未跑**（4 核/7GB、需与他人共享；按审阅指令只跑相关子集） |

变异均为临时改动且**已全部还原**：`git status --porcelain` 为空。

## 结论

修复方向与根因判定我独立复核后**认同**：两条根因都是测试侧时序缺陷（A：`chat.js:1680-1685` 的 `readyState !== OPEN` 守卫使未就绪发送静默落空；B：后到的 `init() → showHub()` 摘掉 `#workflow-view` 的 active 而 `showHub()` 不清 canvas），修法（显式 `initDone` 就绪信号 + 删吞异常降级 + 15 条接屏障）与两条回归测试的判别力**都经我实跑验证为真**，spec 同步逐字一致，门禁三件套中可本地复核的两件通过，无 CI 弱化、无生产行为变化、无安全面问题。

需要一轮修改的是三点小事：**I1**（新用例的 `delete` 早于 `init` resolve 的竞态 —— 两行确定性修法，避免「修 flake 的 change 自带 flake」）、**I2/I3**（回归 A 的注入阈值偏离用户拍板值且 tasks/design 未同步 —— 0.5 的放宽本身更优，但必须写成记录在案的口径）、**I4**（`test_browser.py` / `test_reconnect_*` 的点击腿同源竞态的「已核实不受影响」结论要么修正要么记债）。其余（I5–I8）为冗余与文档精度的整理项，可与上述一并顺手完成。

修完 I1–I4 后可直接进入复审；我不认为需要第 3 轮。
