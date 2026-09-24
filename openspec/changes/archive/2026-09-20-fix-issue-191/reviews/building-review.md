# Building Review — fix-issue-191（Round 3）

我是**独立零记忆**代码审阅者：本会话未读取任何先前对话、计划或推理，事实来源仅为下方列出的
change 文档、仓库代码、git 历史，以及我**自建的 playwright UI 探针 / ORIG·变异对照 / 假时钟探针**
的实跑输出。本轮核心是**独立复现或证伪 Round 2 三条 Issue 的修复声称**（尤其 R2 Issue 1 的 D1c
修法），并复跑 R1 遗留的确定性/变异口径。所有探针写在 `/tmp/review_191_r3/`；ORIG/变异对照时
**临时**改仓库文件（`chat.js`、`test_multi_session_browser.py`），每次都用备份还原，结束时
`git status --short` 为空、`chat.js` 与备份 md5 逐字节一致。

## Reviewer

- run id: review-fix-issue-191-2026-09-20-r3
- 时间: 2026-09-20
- 审阅对象: `git diff eb50f8a...HEAD`（被审范围 `/tmp` 指令指定为 `eb50f8a...HEAD`；等价于
  `git diff origin/master...HEAD`，base 与 `origin/master` 同为 `eb50f8a`）——`web/static/chat.js`、
  `web/static/index.html`、`tests/web_tests/test_multi_session_browser.py`、`docs/known-debt.md`、
  `docs/openspec-change-backlog.md` + `openspec/changes/fix-issue-191/{proposal,design,diagnosis,tasks}.md`
  + `specs/web-ui/spec.md` + `reviews/grill-design.md` + R1/R2 报告 + 本轮修复提交 `a5e1bce`
- 基线: `eb50f8a04c818c46146b525950c7ad5effb81fde`（`origin/master`）→ `a5e1bce51144cb1e4395e0d0a6f2857b50f39bc8`（HEAD）
- 审阅方法（实跑命令）:
  - `git diff eb50f8a...HEAD` / `git show a5e1bce` / `git show a5e1bce^:web/static/chat.js`（修复前对照）
  - `git show eb50f8a:web/static/chat.js > web/static/chat.js` → pytest → `cp` 还原（ORIG 对照，3 轮）
  - `uv run pytest tests/web_tests/test_multi_session_browser.py -k "<9 个 slash/focus 测试>" -q -p no:randomly -rf`（ORIG ×3 / 固定版 ×3 / 全文件 ×1）
  - `uv run python /tmp/review_191_r3/mutate.py {M1,M2,M3,M4,restore}` —— 独立变异注入 + 还原
  - `uv run python /tmp/review_191_r3/probe_ui.py {d1c,tab_apply,enter_diff,enter_same,empty_matches}` —— D1c 与 Tab/Enter 语义
  - `uv run python /tmp/review_191_r3/probe_empty.py` / `probe_scope.py` —— 真「列表可见但匹配数组为空」边界
  - `uv run python /tmp/review_191_r3/probe_hint.py` / `probe_hint2.py` —— 带 `argument_hint` 命令的 D1c 路径（**发现残留**，见 Issue 1）
  - `uv run python /tmp/review_191_r3/probe_clock.py` —— **自建**假时钟冻结探针（install vs install+pause_at）
  - `uv run python /tmp/review_191_r3/probe_closetab.py` —— closeTab 残留 FIXED/ORIG 对照
  - `PYTHONPATH=. uv run python scripts/check_openspec_artifacts.py --base-ref origin/master --require-base`
  - `npx --yes @fission-ai/openspec@1.4.1 validate fix-issue-191 --strict`

## Verdict

**PASS**

R2 的三条 Issue **全部被实质修复**，且核心 blocker（D1c：跨 tab 收敛路径下 `Enter` 被静默吞掉）
经我独立复跑**确定性成立**：修复版 3/3 发出消息，回归测试对修复前实现 3/3 确定性红、
且落在**判别断言行**（`:572`）而非 setup。R1 的确定性/变异口径也**全部重新成立**：ORIG 下
连跑 3 次得到**逐次完全一致**的 7 个红灯，M1–M4 四条变异**全部仍被杀死**，其中 R2 担心的
「M3 不再被杀」已由新 `test_dismissed_suggestions_not_reopened_by_keypress` 重新钉住
（我独立复跑 2/2 确定性红，落在 `:525`）。假时钟经我**自建探针**证伪并证实：`install()` 单独
确实**不冻结墙钟**（真实 0.6s 漂移 605ms、`setTimeout(100)` 照常触发），而
`install()+pause_at()` 真正冻结（漂移 0ms、只能由 `fast_forward` 推进）——R2 Issue 3 的修法正确。

唯一新发现是一条**残留（minor，非阻塞）**：D1c 的修法只覆盖「应用建议项为空操作」的子情形，
对**带 `argument_hint` 的命令**（`/mode`、`/skills`）在同一路径上仍会把输入框补全成一个字符
（`/mode` → `/mode `）而不发送，需再按一次 `Enter` 才发出（ORIG 一次即发）。该残留**不违反
spec 字面**（Scenario 5 专指 `/status`），也**不静默丢数据**（输入框变化可见、再一次 Enter
即发出），故不构成 blocker；已作为 Issue 1 记录并给出建议。

## Round 2 Issue 验证

| R2 Issue | 声称的修复 | 我的独立验证结果 |
|---|---|---|
| **Issue 1 (major)** 「Escape 收起 → 切走 → 切回（收敛重新展开）→ Enter」消息被静默吞掉；修法改为「应用是否为空操作」判定 | `web/static/chat.js:187-194` 用 `insert_text === userInput.value` 判定走 `sendMessage` | **成立（已修复）**。(a) `/tmp/review_191_r3/probe_ui.py d1c` 3/3：断言前列表**确实被收敛重新展开**（`vis=True, value='/status'`），Enter 后 `users 0→1`、`value=''` → **SENT**。(b) 把 `chat.js` 换成修复前 `a5e1bce^`（仅 D1b、无 D1c），`test_escape_switch_back_then_enter_still_sends_message` **3/3 确定性红**，失败落在判别断言 `:572`（`0 → 0`、残留 `'/status'`）。(c) 语义未被改坏——见下方「语义边界表」：`Tab`、以及「插入文本 ≠ 输入内容」的 `Enter` 仍走「应用建议项」。(d) 边界安全——见 Issue 1 与「语义边界表」末行 |
| **Issue 2 (minor)** R1 的 `closeTab`/`activeTabId` 残留未落到持久位置 | 记入 `docs/known-debt.md`（`docs/known-debt.md:39`）+ `workflow-events.jsonl` `protected_artifact_explained` | **成立（已修复）**。条目描述**准确**：我独立复现残留（`probe_closetab.py`：关闭活跃 tab 后 `activeTabId='<关闭的 id>'`、`tabs.has(activeTabId)=False`、`getActiveTab()` 非 null），并确认**在 ORIG 上逐项相同**（FIXED `activeTabId='08f848b0561d'` / ORIG `'417ca09eede3'`，其余字段一致）→ **确属既存、非本 change 引入**。结构化事件字段齐备：`schema='workflow-event/v1'`、`event_type='protected_artifact_explained'`、`change_id='fix-issue-191'`、`reason`/`approved_by` 均为非占位字符串，`artifact_path='docs/known-debt.md'` 精确覆盖；checker 的 `check_protected_path_explanations` 对该路径返回 `[]`（正例），且负例（`openspec/specs/__probe__/spec.md` 无覆盖事件）正确报错 |
| **Issue 3 (minor)** `_install_fake_clock` docstring 失实（`install()` 不冻结墙钟） | 改用 `install()+pause_at(未来时刻)`，docstring 更正 | **成立（已修复且 docstring 属实）**。`tests/web_tests/test_multi_session_browser.py:33-50` 现为 `install()` + `pause_at(datetime(2099,...))`。**自建探针** `probe_clock.py`：mode A（仅 install）`Date.now` 真实 0.6s 漂移 **605ms**、`setTimeout(100)` **已触发**；mode B（install+pause_at）漂移 **0ms**、真实 0.6s **不触发**、`fast_forward(150)` 后才触发 → 与 docstring「暂停后真实 0.6s 不触发、`fast_forward(150)` 才触发」**逐字一致**。测试不再依赖墙钟：3 路 CPU 负载下 4 个关键测试 **3/3 全绿**（见 Test Results） |
| **另：R2 指出 M3 变异改后不再被杀**，需重新钉住 | 补 `test_dismissed_suggestions_not_reopened_by_keypress` | **成立**。该测试**有真实判别力**、断言**非恒真**：M3（`if (!wasActive)` → `if (true)`）下**确定性红 2/2**，落在判别断言 `:525`；还原后绿。它确实补上了 D1c 修法掩盖的语义缝隙——我确认修复版下 `test_escape_then_enter_still_sends_message` 对 M3 变**绿**（D1c 的 Enter 判定先行返回），正是 R2 预判的现象 |

### 语义边界表（R2 Issue 1 的 (c)/(d)：修法没有改坏原有语义）

固定版，`/tmp/review_191_r3/probe_ui.py`（`users` 不增表示未发送）：

| 场景 | 输入 | 列表首项 insert_text | 结果 | 判定 |
|---|---|---|---|---|
| `Tab` | `/s` | `/status`（≠ `/s`） | `value '/s'→'/status'`、`users 0` | **APPLIED（不发送）** ✓ 原有语义保持 |
| `Enter`（值不同） | `/s` | `/status`（≠ `/s`） | `value '/s'→'/status'`、`users 0` | **APPLIED（不发送）** ✓ 原有语义保持 |
| `Enter`（值相同） | `/status` | `/status`（= 值） | `value ''`、`users 0→1` | **SENT** ✓ D1c 目标 |
| D1c 全路径 | `/status` → Esc → 切走 → 切回 | `/status`（= 值） | `users 0→1` | **SENT** ✓ |
| 边界：列表可见但匹配数组为空 | `/status`（`slashMatches=[]`、`hidden=false`） | `undefined` → `insertText=null` | `users 0→1`、无 `pageerror` | **SENT，不抛异常** ✓ |

`insertText === null` 分支（`:188`）是**防御性**的：正常收敛路径下 `updateSlashSuggestions()` 保证
`slashMatches.length > 0`；我**强制构造**了「元素可见 + `slashMatches=[]` + `activeSlashIndex=0`」
（用页面脚本直接改脚本作用域变量，`probe_scope.py` 已确认这些变量在 `page.evaluate` 里可达），
结果 `picked === undefined → insertText === null → sendMessage()`，**不抛异常、按发送处理**，符合预期。

## Tasks Verification

`tasks.md` 现为 **4 × `[x]` / 28 × `[ ]`**（勾选的 4 条全在「审阅闭环」小节）。按
`scripts/check_openspec_artifacts.py:1019-1035`，building-review 强制门禁要求
`_tasks_all_complete`（`unchecked == 0`）——**当前不触发**，故 checker 只报 manifest 缺失
（预期）。逐条核对**实现真实性**（勾选动作按流程属审阅通过后，见 Issue 3）：

| tasks.md 条目 | 状态 | 证据（文件:行号 / 命令输出） |
|---|---|---|
| `chat.js` blur 归属化 + 两道守卫 | 存在 | `web/static/chat.js:165-173`（`getActiveTab() !== tab` @169；`document.activeElement === tab.inputEl` @170） |
| `switchTab` 记 `wasActive`，仅 `!wasActive` 收敛 | 存在 | `web/static/chat.js:319`、`:325-330` |
| `createTab` 初始化 `blurHideTimer: null` | 存在 | `web/static/chat.js:26-28` |
| `closeTab` 清理挂起定时器 | 存在 | `web/static/chat.js:340` |
| 测试装 playwright 假时钟（`install()`+`fast_forward`） | 存在且**已升级为 pause_at** | `test_...browser.py:33-50`；`_open_two_tabs_frozen:59-66` 在 `page.goto` **之前**调用 |
| 改造 isolation 断言落宽限窗之后、对旧实现确定性变红 | 成立 | ORIG 下 isolation 3/3 红；固定版 3/3 绿（见 Test Results） |
| t_b 非活跃标签页失焦不干扰 | 存在且可杀 | `:384-410`；ORIG 红、M1 红、M2 红 |
| t_c 收起后切回按输入内容重判 | 存在且可杀 | `:441-466`；ORIG 红、M2 红 |
| t_d 按住标签按钮越过宽限窗再切走切回 | 存在且可杀 | `:581-612`；ORIG 红、M2 红 |
| 「关闭当前活跃标签页」判别测试 | 存在且可杀 | `:616-641`；ORIG 红、M2 红 |
| Escape→Enter 回归（同 tab） | 存在 | `:470-501` |
| **同标签页按键不重新展开已收起的列表**（R2 新增） | 存在且**可杀 M3** | `:505-529`；M3 下确定性红 2/2 @`:525` |
| **Escape→切走→切回→Enter 仍发送**（R2 新增） | 存在且**可杀修复前实现** | `:533-577`；`a5e1bce^` 下 3/3 红 @`:572` |
| 宽限窗测试用同 turn `blur()+focus()` | 存在 | `:414-437`（`page.evaluate` 内 `el.blur(); el.focus();`） |
| fixture 处理 tab id rekey | 存在 | `:111-115`（等 `.dataset.tabId` 不再以 `new-` 开头） |
| 浏览器等待显式超时 + 可读失败信息 | 存在 | `BROWSER_TIMEOUT_MS` @`:30`；`_dismiss_suggestions:84-88` / `_show_slash_suggestions:140-146` 带上下文 |
| 变异验证（4 条） | **全部独立复现** | M1 杀 4、M2 杀 5、M3 杀 1、M4 杀 1（见 Test Results），还原后全绿 |
| 确定性验证：旧实现同一组红灯 | 成立 | ORIG 3 次全量 → 每次**完全相同**的 7 灯 |
| 去 flake 验证：固定版重复跑全绿 | 成立 | 9 测组 3/3 全绿；全文件 1 次 17 passed；3 路负载下关键 4 测 3/3 绿 |
| `diagnosis.md` 6 章 | 存在 | Symptom/Reproduction/Evidence/Root Cause/Recommended Direction/Regression Tests（`:3/10/33/65/76/92`） |
| spec delta 新增 Requirement + 6 Scenario | 存在 | `specs/web-ui/spec.md:3-11`（Requirement）、`:15/25/32/39/46/53`（6 条 Scenario，含 R2 新增 Scenario 5 @`:46`） |
| 当前规格同步（受保护路径） | 未执行（属归档阶段） | `openspec/specs/` 本 branch 未改（`git diff origin/master --name-only` 无该路径） |
| 关键词扫描 docs/ | 未执行（无 diff 证据） | 收尾阶段任务 |
| backlog 登记 | 存在 | `docs/openspec-change-backlog.md`；`workflow-events.jsonl` seq=1 `backlog_updated` |
| RIR（业界调研门禁） | 存在 | `proposal.md` `research_tier: light`（bugfix + 局部模式应用，档位合理） |

## Spec 对齐（6 条 Scenario 逐条）

| Scenario | 测试覆盖 | 状态 |
|---|---|---|
| 1 切入再切回不丢失本标签页的建议 | `:345-380`（断言落 `fast_forward` 之后） | 覆盖，ORIG 红 |
| 2 非活跃标签页的失焦不干扰活跃标签页 | `:384-410` | 覆盖，ORIG 红 |
| 3 收起后切走再切回按输入内容重新判定 | `:441-466` | 覆盖，ORIG 红 |
| 4 同标签页内按键不触发收敛（Escape→Enter） | `:470-501`（+ R2 新增 `:505-529` 钉「按键不重开列表」） | 覆盖，M3 红 |
| 5 收敛重新展开的列表不劫持发送（R2 新增，专指 `/status`） | `:533-577` | 覆盖，修复前 3/3 红 |
| 6 关闭当前活跃标签页后被切到的标签页按输入内容收敛 | `:616-641` | 覆盖，ORIG 红 |

Requirement 第 1、2、3 段（隔离 / 收敛不依赖墙钟时序 / `Enter` 以「空操作」为准）均在实现与测试
中有对应落点。**注**：Scenario 5 与第 3 段的字面只钉住「插入文本 = 输入内容」这一子情形，
Issue 1 的残留正落在这条字面边界之外——spec 字面不违反，但 Requirement 自身的**理由**
（「列表可见本身不表示用户想选它」）对带 hint 的命令同样成立。

## Issues

### Issue 1（severity: minor）
- 位置: `web/static/chat.js:187-194`
- 描述: D1c 的修法把 `Enter` 的意图判定收敛到「被选项插入文本 == 输入内容」，**只覆盖无
  `argument_hint` 的命令**（`insert_text == command`，如 `/status`）。对**带 `argument_hint`** 的
  命令（`insert_text = command + ' '`，如 `/mode`、`/skills`），同一路径仍会「应用建议项」：
  `Escape` 收起 → 切走 → 切回（列表按收敛重新展开）→ `Enter` → 输入框被补成 `/mode ` 并收起列表，
  **消息不发出**，需**再按一次 `Enter`**。ORIG 在该路径上一次 `Enter` 即发出。
- 证据（`/tmp/review_191_r3/probe_hint2.py`）:
  ```
  固定版：switch-back {value:'/mode', vis:True} → Enter#1 {users:0, value:'/mode '} → Enter#2 {users:1, value:''}
  ORIG  ：switch-back {value:'/mode', vis:False} → Enter#1 {users:1, value:''}
  ```
  `probe_hint.py` 对 `/skills` 同形（`Enter#1 → '/skills '`、users 0）。
- 影响: 非阻塞。**不是静默数据丢失**（输入框变化肉眼可见，再一次 Enter 即发出，且最终发出的
  内容与意图等价，仅多一个尾随空格）；也**不违反 spec 字面**（Scenario 5 专指 `/status`，
  第 3 段只在「插入文本 = 输入内容」时要求发送）。属**摩擦/不一致**：同一条「Escape → 切换 →
  回归」的用户历史，因命令是否带参数提示而给出两种结果，且与 D1c 自己的理由
  （`:182-186`「列表可见本身不表示用户想选它」）不自洽。
- 建议（三选一，均非阻塞）:
  (a) 若接受「列表可见时 Enter = 接受补全」为自动补全语义：在 `design.md` D1c 明确写出
  「带 hint 命令保留补全优先」的边界，并补一条测试钉住（`/mode` 路径：一次 Enter 补全、二次发送），
  把当前**未测**的边界变成有意识契约；
  (b) 若认为 ORIG 的「一次 Enter 即发」是应守行为：把判定从「插入文本 == 输入内容」放宽为
  「本次 `Enter` 未被用户显式选择建议项」（例如仅在「列表由本 turn 内用户按键/输入产生」时
  才 apply），或引入轻量 `userDismissed` 位（grill Q1 曾排除，若采此路需回写 spec 与 Q1 记录）；
  (c) 维持现状 + 记 debt（若判定该摩擦可接受）。**本项不影响本轮 verdict。**

### Issue 2（severity: minor）
- 位置: `tests/web_tests/test_multi_session_browser.py:84-88`（`_dismiss_suggestions` 的 `wait_for_function`）
- 描述: R2 Issue 4 的观察项（`frozen=True` 时 `fast_forward` **同步**触发挂起收起动作，其后
  `wait_for_function(...hidden, timeout=15000)` **不会真的等待**，只是自我确认）**未被处理**。
  不影响判别力（调用点 `:452`/`:628` 均有独立 `assert not _suggestions_visible` 兜底），
  属可维护性提示。
- 证据: `:77-83`（`if frozen: await _advance_past_grace_window(page)` 紧接 `wait_for_function`）；
  `:452`、`:628` 的前置 `assert`。
- 建议: 保留前置 `assert` 即可，或在注释中说明 frozen 路径下该 `wait_for_function` 是同步复合检查。

### Issue 3（severity: minor, process/CI）
- 位置: `openspec/changes/fix-issue-191/tasks.md`
- 描述: 实现类/测试类任务（如「`chat.js` blur 归属化」「`switchTab` 记 `wasActive`」「t_b/t_c/t_d」
  等）**已真实完成，但仍是 `- [ ]`**。项目约定（`AGENTS.md`「按 tasks 测试先行实现」+
  `scripts/check_openspec_artifacts.py` 的 `_tasks_all_complete`）是以勾选表示完成，且
  building-review 门禁**只在全部勾选时才触发**——当前状态会让门禁**静默不生效**。
- 证据: `grep -c '^- \[x\]' tasks.md` → 4；`grep -c '^- \[ \]'` → 28；checker 因此只报 manifest
  缺失（`check_openspec_artifacts.py:1034`）。对照归档 change（如
  `archive/2026-09-19-workflow-cycle-contract` x=50 / sp=0）可见约定是完成后全部勾选。
- 建议: 生成 review manifest **之前**，把已完成的实现/测试/文档任务勾为 `[x]`（保留 Round 3
  审阅与 manifest 生成本身待勾），再跑一次 checker 让 building-review 门禁真实触发并留痕。

## Test Results

**确定性红（ORIG = `git show eb50f8a:web/static/chat.js`）——成立。** 9 测组连跑 3 次，每次
**完全一致**的 7 灯（另 2 绿为 ORIG 本就该绿的 `escape_then_enter`、`dismissed_suggestions`）：
```
ORIG run 1/2/3 均：7 failed / 2 passed，FAILED 集合逐次相同 =
  { multi_tab_slash_suggestion_isolation, cross_tab_blur_does_not_hide_active_suggestions,
    focus_returned_within_grace_window_keeps_suggestions, reopened_tab_reevaluates_suggestions_from_input,
    escape_switch_back_then_enter_still_sends_message, slow_click_then_return_keeps_suggestions,
    closing_active_tab_converges_remaining_tab }
```
（耗时 17.9s / 17.6s / 18.0s）

**确定性绿（固定版）——成立。** 同 9 测组 3 次全绿（19.1s / 19.6s / 18.1s）；**全文件** 1 次
`17 passed in 27.8s`。

**修复前对照（`a5e1bce^` = 仅 D1b、无 D1c）——** `test_escape_switch_back_then_enter_still_sends_message`
**3/3 确定性红**，失败落在判别断言 `:572`：
```
E AssertionError: ...（用户消息数 0 → 1）；实际 0 → 0，输入框残留 '/status'
tests/web_tests/test_multi_session_browser.py:572
```
（同跑的 `dismissed_suggestions_not_reopened_by_keypress` 3/3 绿——符合预期，它钉的是 absence-of-D1c
也成立的语义。）

**变异验证（独立注入，`/tmp/review_191_r3/mutate.py`）——全部复现，且与声称一致、还原后全绿：**
| 变异 | 我的复现（被杀测试） | 结果 |
|---|---|---|
| M1 去 blur 归属（回到无归属 `setTimeout(hideSlashSuggestions, 100)`） | `cross_tab_blur`、`focus_returned`、`isolation`、`escape_switch_back` | **4 failed / 5 passed** |
| M2 只归属化、去 `switchTab` 收敛 | `closing_active_tab`、`reopened_tab`、`slow_click`、`isolation`、`escape_switch_back` | **5 failed / 4 passed** |
| M3 收敛去掉 `wasActive`（`if (!wasActive)` → `if (true)`） | `dismissed_suggestions_not_reopened_by_keypress`（确定性 2/2 @`:525`） | **1 failed / 8 passed**；`escape_then_enter` **变绿**（D1c 掩盖，印证 R2 预判） |
| M4 去 `activeElement` 守卫 | `focus_returned_within_grace_window_keeps_suggestions` | **1 failed / 8 passed** |

**`fast_forward` 是承重的（自建对照，非采信注释）。** 把 `_advance_past_grace_window` 临时改成
空操作后跑 ORIG：`isolation` **变绿**（不再被杀），只剩 `{closing_active_tab, escape_switch_back,
reopened_tab}` 3 红——即新测试的判别力确实来自「把挂起定时器同步提前到断言之前」，与 R2 结论一致。

**假时钟冻结（自建探针 `probe_clock.py`，固定版、导航前安装）:**
```
mode A (install only)     : Date.now 真实 0.6s 漂移 605ms | 真实 0.6s 内 setTimeout(100) 触发 = True  | fast_forward 后 = True
mode B (install+pause_at) : Date.now 真实 0.6s 漂移   0ms | 真实 0.6s 内 setTimeout(100) 触发 = False | fast_forward(150) 后 = True
```
→ docstring「暂停后真实 0.6s 不触发、`fast_forward(150)` 才触发」**逐字属实**。

**负载下复跑（去墙钟的验收）。** 3 路 CPU 忙循环背景下，4 个最相关测试
（`isolation` / `escape_switch_back` / `dismissed_suggestions` / `focus_returned`）**3 次全绿**：
```
UNDER LOAD run 1/2/3: 4 passed（11.6s / 10.7s / 11.1s）
```

**门禁。**
```
npx --yes @fission-ai/openspec@1.4.1 validate fix-issue-191 --strict → "Change 'fix-issue-191' is valid"  exit 0
PYTHONPATH=. uv run python scripts/check_openspec_artifacts.py --base-ref origin/master --require-base → exit 1
   ERROR: fix-issue-191: review manifest missing:
          openspec/changes/fix-issue-191/reviews/building-review-manifest.json
```
该报错**属预期**：`_check_review_manifests`（`check_openspec_artifacts.py:1040-1051`）对
`reviews/*-review.md` 的 glob 命中 `building-review.md`，而 manifest 是审阅闭环**通过后**才生成的
最后一步。我确认同目录下 `r1`/`r2` 报告**不被** glob 命中
（`glob('*-review.md') == ['building-review.md']`，因 r1/r2 文件名带 `-r1`/`-r2` 后缀），
故生成 manifest 时**不会**被迫为历史报告补 manifest。**不作为缺陷。**

受保护路径检查我另做了**正/负对照**：`check_protected_path_explanations(repo_root, changed_paths={...})`
对 `docs/known-debt.md` / `docs/openspec-change-backlog.md` / `openspec/specs/web-ui/spec.md` 返回
`[]`（正例），对无事件覆盖的 `openspec/specs/__probe__/spec.md` 返回
`['protected path ... changed without workflow event explanation']`（负例，证明检查确实生效）。

**未验证项**：全量 `pytest`（按审阅指令未跑）；`openspec/specs/` 的实际同步（归档阶段）；
`tasks.md` 承诺的「其它浏览器测试是否共享同一竞态假设」尚未展开（`tests/web_tests/` 中
`test_browser.py`、`test_reconnect_pending_interaction_browser.py`、`test_workflow_graph_browser.py`
等也操作 tab/`user-input`，本 branch 未加判据；全文件 17 passed 未暴露同类竞态）。

## 仓库完整性

对照实验全部还原，结束时：
```
git status --short          → （空）
git rev-parse HEAD          → a5e1bce51144cb1e4395e0d0a6f2857b50f39bc8
md5  web/static/chat.js     → 75172a35735d93ecf66136ec10845380（与 /tmp/review_191_r3/chat.fixed.js 逐字节一致）
reviews/ 下                  → building-review.md（本轮覆盖）+ building-review-r1.md + building-review-r2.md + grill-design.md（历史文件未改动）
```

## 结论

Round 2 的三条 Issue **全部成立且修复到位**，且都经受住了我的独立复现：D1c 让
「Escape→切走→切回→Enter」在修复版 3/3 发出、在修复前实现 3/3 确定性红于判别断言；R1 的
确定性/变异口径（ORIG 逐次同一组 7 灯、M1–M4 全杀）全部保持；新增 keypress 测试确实补上了
D1c 掩盖的 M3 缝隙；假时钟经自建探针证实真正冻结墙钟（605ms vs 0ms）；closeTab 残留经
FIXED/ORIG 对照确认既存，debt 条目与结构化事件**准确且通过 checker 的受保护路径校验**。
门禁方面 OpenSpec strict validate 通过，artifact checker 仅报预期的 manifest 缺失。

唯一新发现是一条 **minor 残留**：D1c 只覆盖「应用为空操作」的命令，带 `argument_hint` 的命令
（`/mode`、`/skills`）在同一路径上仍需二次 `Enter`（Issue 1）。它不违反 spec 字面、不静默
丢数据，且落在 D1c 已记录的「保留应用语义」边界上，**不构成阻塞**；建议按 (a)/(b)/(c) 之一
把它变成有意识契约或记 debt。另有两处 minor/流程提示：`_dismiss_suggestions` 的装饰性等待
（Issue 2）与 tasks.md 未勾选导致 building-review 门禁静默不触发（Issue 3，**生成 manifest 前
需处理**）。

判定 **PASS**。收尾前请处理 Issue 3（勾选已完成任务）再生成 review manifest。
