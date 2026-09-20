# Building Review — fix-issue-191（Round 2）

我是独立零记忆代码审阅者：本会话未读取任何先前对话、计划或推理，事实来源仅为下方列出的
change 文档、仓库代码、git 历史与我**自建的 playwright 探针 / ORIG 对照 / 变异实验**实测输出。
本轮重点是**独立复现或证伪 Round 1 的 5 条 Issue 修复声称**，不采信开发者与新注释的自我描述。
探针脚本全部写在 `/tmp/review_191_r2/`；ORIG/变异对照时短暂改仓库文件（`chat.js`、`test_*.py`），
每次都用 `git checkout` / 备份还原，结束时 `git status --short` 为空（另有 `diff` 与 HEAD 逐字节比对）。

## Reviewer

- run id: review-fix-issue-191-2026-09-20-r2
- 时间: 2026-09-20
- 审阅对象: `git diff origin/master...HEAD`（`web/static/chat.js`、`web/static/index.html`、
  `tests/web_tests/test_multi_session_browser.py`、`docs/openspec-change-backlog.md`）+
  `openspec/changes/fix-issue-191/{proposal,design,diagnosis,tasks}.md` +
  `specs/web-ui/spec.md` + `reviews/grill-design.md` + R1 报告 + R1 修复提交 `74d2cef`
- 基线: `eb50f8a04c818c46146b525950c7ad5effb81fde` → `74d2cefacd7c064d4578aec15c44198c0391964a`
- 审阅方法（实跑命令）:
  - `git diff origin/master...HEAD` / `git show eb50f8a:web/static/chat.js`（ORIG 源码对照）
  - `uv run pytest tests/web_tests/test_multi_session_browser.py -k "<7 个 slash/focus 测试>"` × 固定版 8 次 / ORIG 3 次 / M1·M2·M3·M4 各 1–2 次
  - `git show eb50f8a:web/static/chat.js > web/static/chat.js` → pytest → `git checkout` 还原（ORIG 对照）
  - `uv run python /tmp/review_191_r2/mutate.py {M1,M2,M4,restore}`（变异注入）
  - `uv run python /tmp/review_191_r2/probe_clock{,2,3}.py` —— playwright 假时钟语义探针
  - `uv run python /tmp/review_191_r2/probe_realtiming.py` —— **真墙钟**（不装假时钟）下 ORIG/固定版对照
  - `uv run python /tmp/review_191_r2/probe_escape_switchback.py`、`probe_escape_after_close{,2}.py` —— Escape/Enter 跨路径
  - `uv run python /tmp/review_191_r2/probe_issue4{,b,c,d}.py` —— R1 Issue 4（activeTabId 残留）复现与影响面
  - `PYTHONPATH=. uv run python scripts/check_openspec_artifacts.py` —— artifact checker
  - `npx --yes @fission-ai/openspec@1.4.1 validate fix-issue-191 --strict` —— OpenSpec 校验

## Verdict

**CHANGES_REQUESTED**

R1 的 5 条 Issue **全部被实质修复**，且 R1 的核心 blocker（isolation 测试对坏实现只有 1/3 概率
变红）经独立复跑已**确定性**收敛：ORIG 下 6 个测试组 3 次得到**完全相同的红灯集合**，isolation
单测 6/6 确定性红、固定版 6/6 确定性绿（变异验证也全部重新成立）。假时钟虽被证实**不暂停墙钟**
（见 Issue 3，文档描述失实），但 `fast_forward` 确实是判别力的承重点，且我另用**真墙钟**探针独立
确认生产逻辑本身在真实时序下也是 ORIG 红 / 固定版绿，判别力不是假象。

**但**：本轮新发现一条**确定性、可复现的功能回归**（Issue 1，major）——**「Escape 收起建议 →
切走 → 切回 → 按 Enter」，消息被静默吞掉**（固定版 0 条发出，ORIG 正常发出）。这与该 change
**自己 spec 的 Scenario 4 与 Requirement 第 3 段直接冲突**，且其新增的
`test_escape_then_enter_still_sends_message` 恰好**绕开了这条路径**而未能捕获它（只测「不经切换
的同 tab Escape→Enter」）。因 spec 与实现对撞、且无测试覆盖该路径，判定 CHANGES_REQUESTED。

## Round 1 Issue 验证

| R1 Issue | 声称的修复 | 我的独立验证结果 |
|---|---|---|
| **Issue 1 (major)** isolation 测试对坏实现只 ~1/3 变红；断言跑在 100ms 定时器之前 | 改用 playwright 假时钟（`page.clock.install()` + `fast_forward`），断言点落在宽限窗之后 | **成立（已修复）**。ORIG 下 3 次全量复跑得到**逐次相同**的 6 灯红灯集（`isolation/cross_tab_blur/focus_returned/reopened_tab/slow_click/closing_active_tab`）；isolation 单测 6/6 确定性红（R1 时 1/3）。固定版 8 次全绿。**断言落点确认在宽限窗之后**：`_open_two_tabs_frozen` → `_install_fake_clock` 在 `_open_two_tabs` 的 `page.goto` **之前**调用（`test_...browser.py:49-56`、`:81-88`），断言前显式 `fast_forward(500)`。`fast_forward` 是承重的：临时把它改成空操作后，ORIG 下 isolation 重新退化为「红/绿/红」且另 3 个测试全部失去判别力（见 Test Results）。 |
| **Issue 2 (minor)** 原「关闭标签页」Scenario 不可证伪 | 改写为「关闭当前活跃标签页后被切到的标签页按输入内容收敛」+ 新测试 `test_closing_active_tab_converges_remaining_tab` | **成立（已修复）**。spec delta `specs/web-ui/spec.md:44-51` 已改写；新测试 `:530-555` 前置条件「tab2 建议已显式收起」经 `_dismiss_suggestions(frozen=True)` 真实达成（`assert not await _suggestions_visible(page)`，`:542`），非恒真。ORIG 下该测试红（`:552` 判别断言），M2 下亦红。 |
| **Issue 3 (minor)** `test_focus_returned_*` 用两次 `page.click`，墙钟裕度仅 ~26–60ms | 改为同一 JS turn 的 `el.blur(); el.focus();` | **成立（已修复）**，但**测试文档描述失实**（见 Issue 3）。`test_...browser.py:418-421` 确为同一 `page.evaluate` 内的 `blur()`+`focus()`，墙钟依赖已消除；M4（去 `activeElement` 守卫）仍被它确定性杀死。**但**其 docstring 与 `_install_fake_clock`/`_advance_past_grace_window` 声称「装好后页面定时器不会自行触发」——探针证伪：`Date.now()` 随墙钟前进、`setTimeout(100)` 在墙上 400ms 后**照常触发**（见 Test Results）。测试仍绿，但理由与文档所述不符。 |
| **Issue 4 (minor, 非阻塞)** `closeTab` 后 `activeTabId` 可能仍指向已删除 tab | R1 建议「另记 debt」 | **未被处理**。`docs/known-debt.md` 本 branch 未改（`git diff origin/master...HEAD --stat -- docs/` 仅 `openspec-change-backlog.md`）；change 自身文档亦无该 debt 条目——该问题只存在于 R1 报告，而本文件即将被覆盖。我独立复现了残留（见下）；但结论与 R1 不同：**这不是功能缺陷**——固定版与 ORIG 在该状态下表现**完全一致**（唯一差异的 `getActiveTab() !== tab` 守卫在 ORIG 的等价路径上也等价命中），故它确应记 debt 而非阻塞；问题只在「**没有把 debt 落到任何持久位置**」。 |
| **Issue 5 (minor)** Scenario 1「两档一致」子句无测试覆盖 | 断言点改为宽限窗之后 | **成立（已修复）**。spec `:13-21` 已把「间隔取任意值」子句改写为「结果 SHALL 在切走时挂起的延迟收起动作**已经执行之后**仍然成立」，正好对应固定版在 `fast_forward` 之后的断言（`:365-370`）。5 条 Scenario 现均有能机械杀死坏实现的测试（见 Tasks Verification）。 |

## Tasks Verification

注：`tasks.md` 全部条目仍为 `- [ ]`（仅 2 处 `[x]` 是审阅闭环小节）。按
`scripts/check_openspec_artifacts.py:982-1000`（`_tasks_all_complete` 要求 `unchecked == 0`），
**building-review 强制门禁当前不触发**；勾选动作按流程属审阅通过后。逐条核对实现真实性：

| tasks.md 条目 | 状态 | 证据（文件:行号 或 命令输出） |
|---|---|---|
| `chat.js` blur 归属化 + 两道守卫 | 存在 | `web/static/chat.js:165-173`（`getActiveTab() !== tab` @169；`document.activeElement === tab.inputEl` @170） |
| `switchTab` 记 `wasActive`，仅 `!wasActive` 收敛 | 存在 | `web/static/chat.js:303`、`:309-314` |
| `createTab` 初始化 `blurHideTimer: null` | 存在 | `web/static/chat.js:28` |
| `closeTab` 清理挂起定时器 | 存在 | `web/static/chat.js:324` |
| 测试装 playwright 假时钟 | 存在 | `test_...browser.py:32-46`；`_open_two_tabs_frozen:49-56` 在导航前调用 |
| 改造 isolation 断言落宽限窗之后、对旧实现确定性变红 | 成立 | ORIG：isolation 6/6 red；全量组 3 次相同 6 灯 |
| t_b 非活跃标签页失焦不干扰 | 存在且可杀 | `:373-400`；ORIG 红（`:397`）、M1 红、M2 红 |
| t_c 收起后切回按输入内容重判 | 存在且可杀 | `:430-456`；ORIG 红（`:453`）、M2 红 |
| t_d 按住标签按钮越过宽限窗再切走切回 | 存在且可杀 | `:494-526`；ORIG 红（`:522`）、M2 红 |
| 「关闭当前活跃标签页」判别测试 | 存在且可杀 | `:530-555`；ORIG 红（`:552`）、M2 红 |
| Escape→Enter 回归 | 存在、可杀 M3，**但覆盖不全** | `:459-491`；M3（无条件收敛）红。**未覆盖「Escape→切走→切回→Enter」**，该路径实测被吞（Issue 1） |
| 宽限窗测试用同 turn `blur()+focus()` | 存在 | `:418-421` |
| fixture 处理 tab id rekey | 存在 | `:101-105`（`wait_for_function` 等 `.dataset.tabId` 不再以 `new-` 开头） |
| 浏览器等待显式超时 + 可读失败信息 | 存在 | `BROWSER_TIMEOUT_MS` @29；`_dismiss_suggestions`/`_show_slash_suggestions` 带上下文失败信息 |
| 变异验证（4 条） | **全部复现** | 见 Test Results：M1 杀 3、M2 杀 3、M3 杀 1、M4 杀 1 |
| 确定性验证：旧实现同一组红灯 | 成立 | ORIG 3 次全量跑 → 每次相同 6 灯（见 Test Results） |
| 去 flake 验证：固定版重复跑全绿 | 成立 | 固定版 7 测 ×8 次全绿；全文件另 1 次 14/15（唯一红为负载诱发的既存测试，见 Issue 4 环境说明） |
| `diagnosis.md` 6 章 | 存在 | Symptom/Reproduction/Evidence/Root Cause/Recommended Direction/Regression Tests 六节齐全（`:3/10/33/65/76/92`） |
| spec delta 新增 Requirement | 存在 | `specs/web-ui/spec.md:3-11` |
| 当前规格同步（受保护路径） | 未执行（属归档阶段） | `openspec/specs/` 本 branch 未改 |
| 关键词扫描 docs/ | 未执行（无 diff 证据） | 收尾阶段任务，非 blocker |
| backlog 登记 | 存在 | `docs/openspec-change-backlog.md` 第十六批；`workflow-events.jsonl` seq=1 `backlog_updated` |
| RIR（业界调研门禁） | 存在 | `proposal.md:172-184`，`research_tier: light`（bugfix + 局部模式应用，档位合理） |
| 全量 pytest / OpenSpec validate / artifact checker | validate 通过；checker 报 manifest 缺失（**预期**） | 见 Test Results |

## Issues

### Issue 1（severity: major）
- 位置: `web/static/chat.js:309-314`（`switchTab` 的收敛）与 `:174-184`（`inputEl` keydown 代理）
- 描述: **确定性功能回归**：对已输入 `/s`（或任意匹配命令）的标签页，用户按 `Escape` 显式收起
  建议后，**切到另一个标签页再切回，建议列表会被收敛逻辑重新展开**；此时按 `Enter`，
  keydown 处理器（`:174-184`）先调 `switchTab(tab.id)`——因 `wasActive === true` 不触发收敛，
  但列表**已经**在上一次「切回」时被收敛展开——于是同一 keydown 落入
  `applySlashSuggestion`（`:180`）分支而非 `sendMessage`（`:183`），**消息被静默吞掉**
  （输入框内容对 `/status` 类命令保持不变，用户看不到任何反馈）。
  这与该 change **自己 spec 的 Requirement 第 3 段**（`specs/web-ui/spec.md:9`：「收敛 SHALL NOT
  覆盖用户在同一标签页内的显式收起……`Enter` SHALL 照常发送消息」）与 **Scenario 4**（`:37-42`）
  直接冲突。设计文档已承认「切回后列表按输入内容复活」（design.md 风险表、grill Q1 用户拍板
  「弹回来」），但**用户拍板的范围是「列表可见性」**，未覆盖「复活后的列表会吞掉紧随其后的
  Enter」——这是 Q1 语义与 D1b 修正之间的**缝隙**，Q2 只堵住了「同一 keydown 内复活」，
  没堵住「上一次切换已复活、下一次按键被劫持」。
- 证据（固定版 vs ORIG，同一探针 `/tmp/review_191_r2/probe_escape_switchback.py`，3 次复跑）：
  ```
  固定版：after Escape: hidden=True → after switch-back: hidden=False（被收敛重新展开）
          → Enter：USER MESSAGES 0 -> 0，remaining='/status'   *** MESSAGE SWALLOWED ***（3/3）
  ORIG  ：after Escape: hidden=True → after switch-back: hidden=True（ORIG 无收敛）
          → Enter：USER MESSAGES 0 -> 1，remaining=''           SENT OK
  ```
  另一路径（`probe_escape_after_close2.py`：Escape → 关闭活跃 tab → Enter）同样固定版吞、ORIG 发。
  而仓库内既有的 `test_escape_then_enter_still_sends_message`（`:459-491`）**只测「不切换的同
  tab Escape→Enter」**，恰好走 `wasActive === true` 分支，因此对这条路径**无覆盖**。
- 影响: 用户「先按 Esc 关掉补全、切个标签看消息、回来接着发」是常见操作序列；此路径下
  消息**永远发不出去且无报错**（对 `/status` 等命令）或**被替换成命令全文**（对 `/s` 等前缀，
  输入框被 `applySlashSuggestion` 改成完整命令）。属用户可见、静默、确定性的数据丢失。
- 建议: 二选一，并**必须补一条覆盖该路径的回归测试**（对固定版必红→修复后绿）：
  (a) 在 tab 上记 `userDismissed` 位（grill Q1 曾明确排除，但当前缝隙证明其必要），
  「切换收敛」只对**非用户显式收起**生效；或
  (b) 让 keydown 处理器对「本次按键是否由收敛引起」更保守——例如 `Enter` 分支改为
  「列表可见且未被用户显式收起时才 apply」。任一方案都要把 spec Scenario 4 扩到
  「Escape → 切换 → Enter」，否则 spec 与实现对撞。

### Issue 2（severity: minor）
- 位置: `openspec/changes/fix-issue-191/reviews/building-review.md`（原 R1 报告）/ `docs/known-debt.md`
- 描述: R1 Issue 4（`closeTab` 后 `activeTabId` 残留）**未落到任何持久位置**。R1 明确建议「另记
  debt」，但本 branch 的 `docs/known-debt.md` 未被修改，change 文档也无该条目——R1 报告是它
  唯一的载体，而「/review-loop 会覆盖 building-review.md」意味着 Round 2 一写，这条信息就**丢失**。
  我独立复现确认残留存在（`:~/probe_issue4*`）：关闭活跃 tab 后 `ws.onclose`（`chat.js:421-422`）
  会以**已关闭 tab 的对象**再调一次 `bindActiveTab(tab)`，把 `activeTabId` 重新写回死 id
  （trace：`bindActiveTab->死了的 aaaa11111111 @socket.onclose chat.js:422`），400ms 后
  `activeTabId` 仍指向不存在于 `tabs` 的 key。**但**——与 R1 的判断一致——这是**既存**行为而非
  本 change 引入：固定版与 ORIG 在该状态下表现**逐项相同**（我特意验证了新守卫
  `getActiveTab() !== tab` 是否把它放大成功能缺陷，结论是不会：两种实现在该序列下都表现为
  「残留 id、`getActiveTab()` 返回 null、blur 收起对存活 tab 均不生效」）。
- 证据: `probe_issue4.py` → `{"closed":"aaaa11111111","activeTabId":"aaaa11111111","tabs":["…"]}`；
  `probe_issue4c.py` 固定版与 ORIG 对照输出一致。`git diff origin/master...HEAD --stat -- docs/`
  仅 `docs/openspec-change-backlog.md`。
- 建议: 把 R1 Issue 4 的结论**显式写入** `docs/known-debt.md`（含复现序列），或写进
  `diagnosis.md` 的「归档证据」节，避免随审阅报告覆盖而蒸发。非阻塞。

### Issue 3（severity: minor）
- 位置: `tests/web_tests/test_multi_session_browser.py:32-46`（`_install_fake_clock` 与
  `_advance_past_grace_window` 的 docstring）
- 描述: docstring 声称「装好之后页面定时器**不会自行触发**，只能由 `fast_forward` 推进」——
  **与 playwright 1.60 实际语义不符**。探针实测：`page.clock.install()`（导航前调用）之后，
  `Date.now()` 仍随墙钟前进（400ms 墙钟 → +415ms），`setTimeout(100)` 在墙上 400ms 后**照常触发**。
  即 `install()` 只接管 `Date`/定时器**接口**，**不暂停时钟**（要暂停需另调 `clock.pause_at`，
  本文件未用）。测试仍能绿、判别力也真实（`fast_forward` 会**同步强制**触发挂起定时器，我实测
  它是承重的：临时置空后 ORIG 下 isolation 退化为红/绿/红、另 3 测试失去判别力），
  但**「去掉墙钟依赖」的机制说明是错的**——真实机制是「把触发时刻提前到断言之前的同一次
  `fast_forward`」，而非「墙钟被冻结」。若后续有人按 docstring 的（错误）理解增补用例，
  可能写出仍依赖墙钟的断言。
- 证据: `/tmp/review_191_r2/probe_clock3.py`（固定版、导航前 install）：
  ```
  Date.now() advanced 415 ms over 400ms WALL   (0 => PAUSED, ~400 => running)
  setTimeout(100) after 400ms WALL: fired
  ```
  `/tmp/review_191_r2/probe_clock2.py` 同结论；`Clock` 公开方法含 `pause_at/resume/run_for`
  （`install` 签名 `install(time=None)`，无 pause 参数），符合上述解释。
- 影响: 不改变当前判据（测试确定性绿/红已由我独立确认），但文档失实会在维护期误导。
- 建议: 修正两处 docstring——「`fast_forward` 把挂起定时器的触发时刻**同步提前**到断言之前，
  使断言确定性落在宽限窗之后」；若要真正冻结墙钟，补 `await page.clock.pause_at(...)`。

### Issue 4（severity: minor）
- 位置: `tests/web_tests/test_multi_session_browser.py:59-78`（`_dismiss_suggestions`）
- 描述: `frozen=True` 时先 `blur()` 再 `fast_forward(500)`；`fast_forward` **同步**触发挂起的
  收起动作，随后 `wait_for_function(... hidden, timeout=15000)` **立即**为真——该等待实际**不会
  等待**，只是自我确认。这不影响判别力（前置条件 `assert not _suggestions_visible` 在 `:442`/`:542`
  真实成立），但 `_dismiss_suggestions` 的 `wait_for_function` 属**装饰性**，若将来 `fast_forward`
  行为变化，这里不会报错而是静默通过。属可维护性提示，非缺陷。
- 证据: `:64-73`；`frozen=True` 调用点 `:441`、`:541` 后续均有独立 `assert not ...visible` 兜底。
- 建议: 可在 `_dismiss_suggestions` 去 `wait_for_function`（保留前置 assert）或在注释说明它
  在 frozen 路径下是同步复合检查。非阻塞。

### Issue 5（severity: minor，环境相关，非本 change 缺陷）
- 位置: 机器负载 / 无关测试 `test_multi_tab_independent_messages`
- 描述: 我首次跑**全文件**时，未改动的 `test_multi_tab_independent_messages` 因
  `.tab-pane.active .message.assistant` 30s 超时而红，全文件耗时 158s（R1 时 ~26s）。当时机器
  负载极高（`load average 10.6 / 4 核`，`fm_engine` 进程占 271% CPU）。隔离复跑该测试 3 次全绿。
  这是环境噪声，**非本 change 引入**，也说明「flake 治理」是全仓范围问题，本 change 只覆盖了
  slash 建议这一条线。记录在此供后续跟进，不构成本轮判据。
- 证据: `uptime` = `load average: 10.60, 6.47, 4.69`（4 核）；隔离复跑 `8 passed` ×3。
- 建议: 归档 PR 的 CI 应在正常负载下跑全量，留意其它浏览器测试是否有同类竞态
  （`tasks.md` 「该假设被其它浏览器测试共享」一条尚未展开）。

## Test Results

**确定性红（R1 Issue 1 的核心验收口径）——成立。**
以 `git show eb50f8a:web/static/chat.js` 覆盖后连跑 7 个测试，3 次得到**逐次相同**的红灯集：
```
ORIG run 1/2/3：6 failed / 1 passed，FAILED 集合三次完全一致 =
  { multi_tab_slash_suggestion_isolation, cross_tab_blur_does_not_hide_active_suggestions,
    focus_returned_within_grace_window_keeps_suggestions, reopened_tab_reevaluates_suggestions_from_input,
    slow_click_then_return_keeps_suggestions, closing_active_tab_converges_remaining_tab }
（唯一绿 = escape_then_enter：ORIG 无收敛，本就该绿）
```
isolation 单测独跑 6 次：**6/6 failed**（R1 时为 3 次中红 1 次）。
每个红都落在其**最终判别断言**（`:366/397/424/453/522/552`），非 setup/precondition 误红。

**确定性绿——成立。** 固定版同 7 测连跑 8 次：**全绿**（另全文件 1 次 14/15，唯一红为负载诱发的
无关测试，见 Issue 5）。

**`fast_forward` 是承重的（我另做对照，非采信注释）。** 临时把 `_advance_past_grace_window`
改成空操作后跑 ORIG：
```
NOOP-FF ORIG run1: 3 failed (isolation, reopened_tab, closing_active_tab)
NOOP-FF ORIG run2: 2 failed (reopened_tab, closing_active_tab)   ← isolation 变绿
NOOP-FF ORIG run3: 3 failed (isolation, reopened_tab, closing_active_tab)
```
即 isolation 退回**红/绿/红**的非确定性，`cross_tab_blur/focus_returned/slow_click` **全部失去
判别力**（变绿）。证实新测试的判别力确实来自「把定时器触发提前到断言之前」。

**真墙钟对照（不装假时钟，排除「判别力是假象」）——** `/tmp/review_191_r2/probe_realtiming.py`
（blur→切走→切回，读「切回瞬间」与「+300ms 之后」）：
```
固定版（6 rep）：immediate=True, after300=True   ×6
ORIG  （6 rep）：immediate=True, after300=False  ×6   ← 真实时序下 ORIG 确实会收掉
```
说明固定版在**真实墙钟**下也是稳定的，ORIG 在**真实墙钟**下稳定失败——判别力非假时钟产物。

**变异验证（R1 声称，独立复现）——全部成立且与声称一致。**
| 变异 | 被杀死的测试 | 我的复现 |
|---|---|---|
| M1 去 blur 归属 | `cross_tab_blur` + `focus_returned` + `isolation` | 3 failed / 4 passed ✓ |
| M2 只归属化、去 switchTab 收敛 | `closing_active_tab` + `reopened_tab` + `slow_click` | 3 failed / 4 passed ✓（2 次一致）|
| M3 收敛去掉 `wasActive` | `escape_then_enter` | 1 failed / 14 deselected ✓ |
| M4 去 `activeElement` 守卫 | `focus_returned` | 1 failed / 6 passed ✓（2 次一致）|

**Escape→Enter 既有测试（M3 目标）** 经复现对 M3 红，与声称一致；**但**其序列不覆盖
「Escape→切走→切回→Enter」，后者是本轮 Issue 1。

**门禁。**
```
npx --yes @fission-ai/openspec@1.4.1 validate fix-issue-191 --strict  → "Change 'fix-issue-191' is valid"  exit 0
PYTHONPATH=. uv run python scripts/check_openspec_artifacts.py         → exit 1
   ERROR: fix-issue-191: review manifest missing:
          openspec/changes/fix-issue-191/reviews/building-review-manifest.json
```
artifact checker 的报错**属预期**：`check_openspec_artifacts.py:1048-1050` 对**任何存在的
`*-review.md`** 都要求绑定 manifest，而 manifest 是审阅闭环**通过之后**才生成的最后一步。
本轮 verdict 非 PASS，manifest 尚不应存在；**不作为缺陷**。

**未验证项**：全量 `pytest`（按审阅指令未跑）；`openspec/specs/` 的实际同步（归档阶段）；
其它浏览器测试文件是否共享同一竞态假设。

## 结论

R1 的 5 条 Issue **修复质量高、声称基本属实**：最关键的 Issue 1 已被**确定性**解决
（ORIG 6/6 红灯集完全一致、固定版 8/8 绿），并经受住我另建的真墙钟对照（判别力非假象），
四条变异全部稳定杀死对应测试。Issue 2/3/5 的 spec 改写与去墙钟化也都落到实处，5 条
Scenario 现均有可机械证伪的测试。

**但本轮发现一条确定性、用户可见、静默的数据丢失回归（Issue 1，major）**：
「Escape 收起建议 → 切走 → 切回 → Enter」把消息吞掉，与 change **自己 spec 的 Requirement
第 3 段和 Scenario 4 直接冲突**，而既有 `test_escape_then_enter_still_sends_message` 恰好只覆盖
「不切换」的同 tab 路径，对该路径零覆盖。这是 grill Q1（「弹回来」语义）与 Q2（D1b 修正）
之间的语义缝隙——用户拍板的是「列表可见性」，没人拍板「复活后的列表劫持下一次 Enter」。

叠加两条 minor：R1 Issue 4 的 debt 未落到任何持久位置（会被本报告覆盖而丢失）、
`_install_fake_clock` 的机制说明与 playwright 真实语义不符（不暂停墙钟，仅同步提前定时器）。

判定 **CHANGES_REQUESTED**。修复 Issue 1 后（并在 spec Scenario 4 扩到「Escape → 切换 → Enter」、
补一条对该路径必红的回归测试），Round 3 只需复跑该测试 + 7 测确定性组 + ORIG/M1–M4 对照即可收敛。
