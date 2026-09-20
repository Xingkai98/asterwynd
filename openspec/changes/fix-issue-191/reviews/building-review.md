# Building Review — fix-issue-191（Round 1）

我是独立零记忆代码审阅者：本会话未读取任何先前对话、计划或推理，事实来源仅为下方列出的
change 文档、仓库代码、git 历史与我**自建的 playwright 探针**实测输出。审阅对
`fix-issue-191` 的实现 diff、change 文档与 spec delta 做**独立验证**，对开发者的每一条
自我声称都用实跑或读码复核，不采信其描述。探针脚本全部写在 `/tmp/review_191/`，通过
`page.route` 拦截 `/static/chat.js` 注入候选／变异实现，在**不修改仓库**的前提下做对照实验
（变异验证时短暂改仓库文件，每次都 `git checkout` 还原，结束时 `git status --short` 为空）。

## Reviewer

- run id: review-fix-issue-191-2026-09-20-r1
- 时间: 2026-09-20
- 审阅对象: `git diff eb50f8a...656c4d2`（`web/static/chat.js`、`web/static/index.html`、
  `tests/web_tests/test_multi_session_browser.py`、`docs/openspec-change-backlog.md`）+
  `openspec/changes/fix-issue-191/{proposal,design,diagnosis,tasks}.md` +
  `specs/web-ui/spec.md` + `reviews/grill-design.md` + issue #191 原文
- 基线: `eb50f8a04c818c46146b525950c7ad5effb81fde` → `656c4d2d64710e24d452f77fd51c2aee52c52f80`
- 审阅方法（实跑命令）:
  - `gh api repos/Xingkai98/asterwynd/issues/191 --jq '.title,.body'` —— issue 原文
  - `uv run pytest tests/web_tests/test_multi_session_browser.py -q` —— 6 次连续稳定性复跑
  - `uv run pytest tests/web_tests/ -q --ignore=tests/web_tests/test_multi_session_browser.py` —— web 子集回归
  - `uv run python /tmp/review_191/probe_escape_enter.py` —— ORIG / B_NAIVE / B_GUARD 三变体 Escape→Enter 对照
  - `uv run python /tmp/review_191/probe_isolation_timing.py ORIG_TRACE` —— 改造后 isolation 测试的墙钟间隔测量（插桩 `performance.now()`）
  - `uv run python /tmp/review_191/probe_isolation_mechanism.py` —— 判定改造后 isolation 测试为何在 ORIG 下仍通过
  - `uv run python /tmp/review_191/probe_m2_trace.py` —— M2（归属化无收敛）如何被 cross-tab 测试杀死
  - `uv run python /tmp/review_191/probe_close_exact3.py` / `probe_close_discriminate.py` —— spec Scenario 5 可证伪性
  - `uv run python /tmp/review_191/probe_focus_interval.py`（空载 + 6 核忙循环负载）—— focus-return 测试的时序裕度
  - `uv run python /tmp/review_191/mutate.py {M1,M2,M3,M4}` + `pytest` —— 四条变异验证
  - `git show eb50f8a:web/static/chat.js` 注入 → `pytest` —— 真 ORIG 对照
  - `PYTHONPATH=. uv run python scripts/check_openspec_artifacts.py` —— artifact checker
  - `npx --yes @fission-ai/openspec@1.4.1 validate fix-issue-191 --strict` —— OpenSpec 校验
  - `uv run python /tmp/review_191/probe_load.py` —— 8 进程忙循环下重跑测试文件

## Verdict

**CHANGES_REQUESTED**

生产代码修复方向正确、变异靶子扎实、门禁全绿，**但**：核心声称「改造后的
`test_multi_tab_slash_suggestion_isolation` 覆盖原失败档位」经独立复跑**不成立**——该测试
在真 ORIG 与 M1 下均**大部分通过**（3 次里只红 1 次），其断言点跑在挂起定时器**之前**，
本质是**又一个时序相关测试**，issue #191 的验收口径（原失败档位必须确定性覆盖）未真正达成。
另有 3 条 spec Scenario 不可机械证伪。详见 Issues。

## Tasks Verification

| tasks.md 条目 | 状态 | 证据（文件:行号 或 命令输出） |
|---|---|---|
| `chat.js` blur 归属化 + 两道守卫 | 存在 | `web/static/chat.js:166-171`（`getActiveTab() !== tab` + `document.activeElement === tab.inputEl`） |
| `switchTab` 记 `wasActive`，仅 `!wasActive` 收敛 | 存在 | `web/static/chat.js:303`（`const wasActive = activeTabId === tabId;`）、`:309-313` |
| `createTab` 初始化 `blurHideTimer: null` | 存在 | `web/static/chat.js:28` |
| `closeTab` 清理挂起定时器 | 存在 | `web/static/chat.js:324` |
| 改造 `test_multi_tab_slash_suggestion_isolation` 去时序依赖并覆盖「间隔短于宽限期」 | **未达成** | `test_..._browser.py:286-314`。注释（`:306`）称「不等待即取最短间隔，原实现在此失败」，实测**不成立**：真 ORIG 下 3 次仅红 1 次。见 Issue 1 |
| 新增 t_b 跨 tab 失焦回归（对旧实现 100% 失败） | 存在且可杀 | `:317-344`；M1/M2/真 ORIG 均红（见 Test Results） |
| 新增 t_c 收起后切回按内容重算 | 存在且可杀 | `:370-400`；M2 红 |
| 新增 t_d 慢 click 回归 | 存在且可杀 | `:438-466`；M2/真 ORIG 红 |
| 新增 Escape→Enter 回归 | 存在且可杀 | `:403-435`；M3 红 |
| fixture 处理 tab id rekey 陷阱 | 存在 | `:48-56`（`wait_for_function` 等 `.dataset.tabId` 不再以 `new-` 开头） |
| 浏览器等待加显式超时 + 可读失败信息 | 部分 | `BROWSER_TIMEOUT_MS` 定义 `:29`，本文件 19 处使用；但 `page.click`（如 `:322`、`:330`）无 timeout，走 Playwright 默认 30s；文件内 `wait_for_timeout` 固定数值仍构成时序依赖（见 Issue 1/3） |
| 变异验证（4 条） | **存在且全部杀死** | 见 Test Results：M1 杀 2、M2 杀 3、M3 杀 1、M4 杀 1 |
| 去 flake 验证：同机同序列重复跑 N 次全绿 | 成立 | 连续 6 次 14 passed（见 Test Results） |
| 回归 `tests/web_tests/` 全量通过 | 成立 | 331 passed, 7 skipped |
| `diagnosis.md` 6 章 | 存在 | Symptom/Reproduction/Evidence/Root Cause/Recommended Direction/Regression Tests 六节齐全 |
| spec delta 新增 Requirement | 存在 | `specs/web-ui/spec.md:3-11` |
| 当前规格同步任务（受保护路径） | 存在（尚未执行） | `tasks.md:38-39` 有该任务；`openspec/specs/web-ui/spec.md` 本 branch 未改（归档阶段执行，符合流程） |
| 关键词扫描 docs/ | 未执行（无 diff 证据） | `git diff --name-only eb50f8a...HEAD` 无 `README.md`/`AGENTS.md`/`CONTEXT.md`/`docs/`（除 backlog）。属收尾阶段任务，非本次 blocker |
| backlog 登记 | 存在 | `docs/openspec-change-backlog.md:156`；`workflow-events.jsonl` seq=1 `backlog_updated` |
| 审阅闭环 / manifest | 由本报告兑现 | 本次 |
| 全量 pytest / OpenSpec validate / artifact checker | 部分（未跑全量） | 按指令未跑全量 pytest；web 子集全绿。`validate` 与 checker 均 exit 0（见 Test Results） |

注：`tasks.md` 全部 24 条仍为 `- [ ]` 未勾选。按 `scripts/check_openspec_artifacts.py:990-1004`
（`_tasks_all_complete` 要求 `checked > 0 and unchecked == 0`），**building-review 门禁当前不会
触发**——这是「实现完成但 tasks 未勾选」的状态，勾选动作应在审阅通过后由开发流程完成。

## Issues

### Issue 1（severity: major）
- 位置: `tests/web_tests/test_multi_session_browser.py:286-314`（尤其 `:306-313` 的断言）
- 描述: 改造后的 `test_multi_tab_slash_suggestion_isolation` **自称**「去掉对两次 click 间隔的
  墙钟依赖」，且 `:306` 注释称「这里不等待，即刻意取最短间隔 —— 原实现在此失败」。独立复跑
  **证伪该声称**：真 ORIG 与 M1（无归属 blur）下该测试各 3 次跑，均为 **1 failed / 2 passed**。
  它没有确定性覆盖原失败档位，而是变成了**另一个时序敏感测试**。
- 证据:
  - `git show eb50f8a:web/static/chat.js > web/static/chat.js` → 对单测 `-k multi_tab_slash_suggestion_isolation`：
    `ORIG = [passed, passed, failed]`；`M1 = [failed, passed, passed]`；`B_GUARD = [passed, passed, passed]`。
  - 机制（`/tmp/review_191/probe_isolation_mechanism.py`，插桩 `performance.now()`）：测试的断言点
    「click 切回 → `wait_for_selector(pane.active)` → `_suggestions_visible`」执行时，挂起的
    100ms 定时器**尚未触发**，故读到 `True`；250ms 后再读即为 `False`。即断言跑在竞态窗口**之前**。
  - 测得的 blur→切回 浏览器时钟间隔为 48–68ms（空载 4 rep：68/65/50/48ms），**小于** 100ms，
    但断言点仍先于定时器完成——定时器在切回后约 100ms 才触发，而断言在 ~50ms 内已完成。
  - 对照：`probe191.py` 声称的「间隔 0ms → FAIL」是在**追加了末尾 wait_for_function** 的序列下成立；
    改造后的测试把断言提前到定时器触发前，等价于把「失败档」变成了「有时通过」。
- 影响: issue #191 的直接验收口径是「原失败档位确定性覆盖（0ms 间隔必须红→绿）」。当前测试
  对坏实现（ORIG/M1）**大部分时候绿**，无法作为该缺陷的判别靶子；新引入的 `fail` 还可能被
  误读为「修复后仍有 flake」。
- 建议: 让该测试的断言真正落在宽限窗**之后**（例如断言前加 `page.wait_for_timeout(150)` 并再读，
  或直接断言「切回后 150ms 内建议始终可见」），使其对 ORIG/M1 100% 红、对 B 绿；
  或明确在 docstring 中撤回「覆盖原失败档位」的声称（但那样就该由 t_b/t_c/t_d 之外的
  一条专门测试补齐该档）。**修复后必须重跑变异验证**确认 ORIG/M1 下确定性变红。

### Issue 2（severity: minor）
- 位置: `openspec/changes/fix-issue-191/specs/web-ui/spec.md:42-47`（Scenario 5「关闭标签页不影响其余标签页的建议」）
- 描述: 该 Scenario 按现有构造**不可机械证伪**。grill（R5）已指出这点并要求改写；作者把
  前置条件从 grill 的「关闭当前活跃 tab」改成「关闭**非活跃** tab（无论其是否为当前活跃）」
  并断言「B 的建议保持由自身输入内容决定」。但独立复跑显示：在「A 失焦挂起 → 关 A（非活跃）」
  这一字面构造下，**ORIG 与 B_GUARD 均通过**（B 建议始终可见）——因为定时器触发时
  `activeTabId` 仍指向 A（`probe_close_exact3.py` trace：
  `['timer-fire', ..., 750.7] → hide 的目标 pane = 'aaaa11111111'，isConnected=false`），
  只写到**已 detach 的 A 自身元素**，碰不到 B。即该 Scenario 描述的失败模式在当前架构下
  **不可达**，是一条恒真断言。
- 证据:
  - `/tmp/review_191/probe_close_exact3.py`（ORIG + 插桩）：关 A 后 `B visible = True`。
  - `/tmp/review_191/probe_close_exact2.py`：ORIG 与 B_GUARD 各 3 rep，`B visible` 全为 `True`。
  - 反证「可证伪的等价构造存在」：`/tmp/review_191/probe_close_discriminate.py` 改用
    「A 建议**已被显式收起** → 切到 tab1 → 关闭活跃 tab1 → 检查 A」——ORIG = `False/False/False`，
    B_GUARD = `True/True/True`，**可判别**。说明问题出在 Scenario 的具体前置条件选错，
    而非「关闭 tab 语义」整体不可测。
- 建议: 按 `closeTab` 实际调 `switchTab(next)`（`chat.js:330-333`）这一路径重写 Scenario 5 为
  「关闭当前活跃 tab 后，被切到的 tab 的建议可见性 SHALL 收敛到由其自身输入内容决定的状态」，
  并配一条对 ORIG 必红的回归测试（上段探针序列即可）。

### Issue 3（severity: minor）
- 位置: `tests/web_tests/test_multi_session_browser.py:347-367`（`test_focus_returned_within_grace_window_keeps_suggestions`）
- 描述: 该测试断言「blur 后 100ms 内点回输入框 → 列表保持可见」。它隐式依赖
  `page.click(消息区)` → `page.click(输入框)` 两个 Playwright 调用的浏览器时钟间隔 **< 100ms**。
  空载实测 40–49ms，6 核忙循环负载下 51–74ms——**裕度只有 26–60ms**。负载更高或 CI 更慢时，
  间隔超过 100ms，守卫放行，测试会红。这恰是本 change 声称要根治的**同一类墙钟依赖**
  （issue #191 的形态），只是换了个位置。
- 证据: `/tmp/review_191/probe_focus_interval.py`：空载 `[42,48,46,49,40,48]ms`；
  `/tmp/review_191/probe_focus_load.py`（6 进程忙循环）`[66,51,59,66,74,57]ms`。
  另：人为在 refocus 前插 80/90ms 延迟即得 `visible=False`（`probe_focus_margin.py`），
  证实 >100ms 必红。
- 建议: 用浏览器内 `element.focus()` 直接在同一 JS turn 内完成「失焦 → 重新聚焦」
  （`page.evaluate` 而非两次 `page.click`），把间隔压到几毫秒，消除该墙钟依赖。

### Issue 4（severity: minor）
- 位置: `web/static/chat.js:330-334`（`closeTab` 中 `switchTab(next)` 之后的路径）
- 描述: 关闭当前活跃 tab 后，`activeTabId` 可能仍指向**已删除**的 tab id：`closeTab` 删掉
  `tabs.delete(tabId)` 但不重置 `activeTabId`，随后 `switchTab(next)` 因
  `wasActive = activeTabId === next` 为 **false** 而正常收敛、`bindActiveTab(next)` 会修正
  `activeTabId`——所以常规路径无碍。但独立探针在「blur 挂起 → 同 turn 关 tab」的路径下观察到
  关 tab 后瞬间 `activeTabId` 仍为旧 id（`probe_close_trace2.py`：`activeAfter` 与
  `tabs` 内容不一致）。该状态可被后续 `getActiveTab()` 守卫读到，属既存架构的脆弱点。
- 证据: 关 tab 后 `{tabs: ['9edbedbe408b'], active: 'aaaa11111111', activePane: '9edbedbe408b'}`；
  同一现象在真 ORIG 下同样出现（`VARIANT=ORIG_TRACE2`），**非本 change 引入**。
- 建议: 不阻塞本 change（既存问题）；可另记 debt：`closeTab` 删除后应立即把 `activeTabId`
  置为 `next`，避免「active 指向不存在 tab」的窗口。

### Issue 5（severity: minor）
- 位置: `openspec/changes/fix-issue-191/specs/web-ui/spec.md:13-19`（Scenario 1 的「间隔 0ms 与超过宽限期结果一致」子句）
- 描述: Scenario 1 末句要求「结果 SHALL NOT 随两次操作之间的耗时变化（间隔 0ms 与间隔超过
  内部宽限期的结果一致）」——这是**两条时序档的对照断言**，而改造后的测试（Issue 1）只跑一档
  且未覆盖宽限期之后，故该子句当前**无测试机械验证**。
- 证据: `test_multi_tab_slash_suggestion_isolation:306-313` 只测「不等待」一档；
  无第二档（>宽限期）断言。
- 建议: 若采纳 Issue 1 的修复（断言落在宽限窗之后），Scenario 1 的两档即可由
  「同一测试内先立即断言、再等 150ms 断言」覆盖；否则应在 spec 中弱化该子句。

## Test Results

**基线稳定性（声称 #4）——成立。**
```
run 1..6: 14 passed  (26.4s / 28.4s / 26.4s / 25.0s / 27.8s / 26.5s)
```
8 进程忙循环下重跑同一文件：`14 passed in 43.49s`。

**web 子集回归**：`331 passed, 7 skipped`（`tests/web_tests/` 去掉本文件）。

**变异验证（声称 #3）——四条全部被杀死，与声称一致。**
| 变异 | 被杀死的测试 | 结果 |
|---|---|---|
| M1 去 blur 归属 | `cross_tab_blur` + `focus_returned_within_grace_window` | 2 failed / 12 passed ✓ |
| M2 只归属化不去收敛 | `cross_tab_blur` + `reopened_tab_reevaluates` + `slow_click` | 3 failed / 11 passed ✓ |
| M3 收敛去掉 `wasActive` | `escape_then_enter` | 1 failed / 13 passed ✓ |
| M4 去掉 `activeElement` 守卫 | `focus_returned_within_grace_window` | 1 failed / 13 passed ✓ |

**真 ORIG 对照**：4 failed / 10 passed（`cross_tab_blur`、`focus_returned`、
`reopened_tab_reevaluates`、`slow_click` 红）——**注意**：`test_multi_tab_slash_suggestion_isolation`
在 ORIG 下**通过**（见 Issue 1）。

**声称 #2（Escape→Enter 回归）——独立复现，与声称完全一致。**
`/tmp/review_191/probe_escape_enter.py`（每变体 3 rep）：
```
ORIG    : (before=0, after=1, after2=1, remaining='')     ×3   → 消息发出
B_NAIVE : (before=0, after=0, after2=0, remaining='/status') ×3 → Enter 被永久吞掉
B_GUARD : (before=0, after=1, after2=1, remaining='')     ×3   → 消息发出
```
D1b（`wasActive` 守卫）确实是该回归的必要修正。

**声称 #1（根因：无归属全局 blur 回调）——成立。**
`git show eb50f8a:web/static/chat.js` 第 156 行确为
`tab.inputEl.addEventListener('blur', () => { setTimeout(hideSlashSuggestions, 100); });`
——回调不捕获 `tab`，`hideSlashSuggestions()`（老版 `:1795-1801`）读写的是触发时刻 active tab
绑定的全局 `slashSuggestionsEl`。跨 tab 泄漏机制成立。

**门禁（声称 #7）——均通过。**
```
PYTHONPATH=. uv run python scripts/check_openspec_artifacts.py  → "OpenSpec artifact checks passed"  exit 0
npx --yes @fission-ai/openspec@1.4.1 validate fix-issue-191 --strict → "Change 'fix-issue-191' is valid"  exit 0
```

**其它已核对声称**：tab id rekey 等待（`test_..._browser.py:48-56`）存在；`BROWSER_TIMEOUT_MS = 15000`
定义于 `:29` 并在本文件 19 处使用；`docs/openspec-change-backlog.md:156` 已登记；
`workflow-events.jsonl` 有 seq=1 `backlog_updated` 结构化事件（受保护路径要求满足）。

**未验证项**：全量 pytest（按审阅指令未跑）；`openspec/specs/web-ui/spec.md` 的实际同步（属归档阶段）；
其它浏览器测试文件是否共享同一竞态假设（本 change 未给该 tasks 条目勾选，我也未逐文件插桩）。

## 结论

生产代码修复（`chat.js` 的 blur 归属化 + `wasActive` 限定收敛 + 双守卫 + `closeTab` 清理）
**方向正确、实现干净、注释解释「为什么」**，四条变异全部被对应测试杀死，连续 6 次跑稳定，
artifact checker 与 OpenSpec strict validate 均通过；声称 #1/#2/#3/#4/#7 经独立复跑**全部成立**。
但声称 #5 中「改造后的 isolation 测试去掉时序依赖、覆盖原失败档位并经变异验证」**被证伪**：
该测试对真 ORIG 与 M1 只有约 1/3 概率变红，其断言跑在 100ms 挂起定时器**之前**，是新引入的
时序敏感测试，未达成 issue #191 的验收口径（Issue 1，major）。另有三条 spec Scenario 不可
机械证伪或无测试覆盖（Issue 2/5），一条新测试自带墙钟依赖（Issue 3）。

因核心验收档位未确定性覆盖，判定 **CHANGES_REQUESTED**。修复 Issue 1（并把其变异验证结果
写回 `reviews/`）后，Round 2 只需复跑 `test_multi_session_browser.py` 与 ORIG/M1 对照即可收敛。
