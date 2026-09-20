# Design Grilling: 多标签页瞬态交互状态隔离 + 浏览器测试去时序依赖（fix-issue-191）

我是独立零记忆设计评审者：本会话未读取任何先前对话、计划或推理，事实来源仅为下方列出的
change 文档、仓库代码与**我自建的 playwright 探针实测输出**。审阅对象是
`openspec/changes/fix-issue-191/` 的 proposal / design / tasks / spec delta。方法以
「挑战而非确认」为准：design 的每一条根因声称与取舍理由都用独立探针复现或证伪，
不接受其自我断言。

探针全部写在 `/tmp/grill_191/`（仓库零改动），通过 `page.route` 拦截 `/static/chat.js`
注入候选实现（A/B/half/zero-delay），因此在**不修改仓库**的前提下把设计候选方案真跑起来
做了对照实验。

## Reviewer

- run id: `grill-fix-issue-191-2026-09-20-001`
- 时间: 2026-09-20
- 审阅对象: `openspec/changes/fix-issue-191/{proposal.md,design.md,tasks.md,specs/web-ui/spec.md}`
- 基线: `eb50f8a`（分支 `fix-issue-191/2026-09-20`）
- 审阅方法（实跑命令）:
  - `gh api repos/Xingkai98/asterwynd/issues/191 --jq '.body,.title'` —— issue 原文
  - `uv run python /tmp/grill_191/probe_a.py` —— 复现 100ms 竞态、测阈值（`probe_a.log`）
  - `uv run python /tmp/grill_191/probe_b.py` —— A/B/half 三候选在场景 A/B 与行为边界上的对照矩阵
  - `uv run python /tmp/grill_191/probe_c.py` —— 跨 tab 泄漏、关 tab、点击外部、apply、方向键、字面 iff
  - `uv run python /tmp/grill_191/probe_d2.py` / `probe_l.py` / `probe_m.py` / `probe_n.py` —— Scenario 3 可证伪性追踪
  - `uv run python /tmp/grill_191/probe_e.py` —— 方案 A 的 gap 扫描、blur 是否真的参与「点建议项」
  - `uv run python /tmp/grill_191/probe_p.py` —— 方案 A 反向竞态的插桩复现（BLUR-armed / TIMER-FIRED / SWITCHTAB 三时刻）
  - `uv run python /tmp/grill_191/probe_f.py` —— 判别矩阵（哪条测试杀死哪个候选）
  - `uv run python /tmp/grill_191/probe_g.py` —— switchTab 内 `slashSuggestionsEl` 重指时机
  - `uv run python /tmp/grill_191/probe_h.py` / `probe_i.py` / `probe_o.py` —— Escape→Enter、方向键、closed-tab
  - `uv run python -m pytest tests/web_tests/test_multi_session_browser.py -q` —— 基线 9 passed
  - `npx --yes @fission-ai/openspec@1.4.1 validate fix-issue-191 --strict` —— Change is valid
  - `PYTHONPATH=. uv run python scripts/check_openspec_artifacts.py` —— 当前报 2 条 ERROR（见风险 R1/R2）

## Confirmed Decisions

- **决策**: 方案 B（归属化 blur + `switchTab` 按输入内容重新求值）**确认采用**，但必须补一条 design 未列的守卫：`switchTab` 的收敛只能在「切换 tab 语义」下触发，不能因 `inputEl` 的 keydown 代理调用 `switchTab` 而触发。理由: 探针证明 B 在场景 A 的全部 gap（0/60/200ms）与场景 B 下均收敛为「可见」，是唯一同时满足 spec 两条 Scenario 的候选；但同一次探针暴露 B 引入一个新的可见回归——`/status` + Escape（收起列表）后按 Enter，ORIG 会发送消息（`userMsgs` 0→1），B 会因 keydown 先调 `switchTab` → 列表 `hidden` → 重新求值 → 列表复活 → 同一 keydown 走 `applySlashSuggestion` 分支，导致 **Enter 永远被吞、消息发不出去**（probe_h/probe_i/probe_o 稳定复现，ORIG 与 B 对照 3/3）。来源: grill-fix-issue-191-2026-09-20-001

- **决策**: `switchTab` 内 `updateSlashSuggestions()` 的**读取对象已由代码保证正确**，design 未写死但无需再改。理由: probe_g 在真实 `switchTab` 里插桩读到 `proxyIsIncoming=true`、`proxyPaneTabId` 恒等于 incoming tab、`userInputIsIncoming=true`——`bindActiveTab(tab)`（`web/static/chat.js:286`）先于任何求值执行，`bindActiveTab` 在 `chat.js:184-191` 把 `slashMatches`/`activeSlashIndex`/`userInput`/`slashSuggestionsEl` 一次性重指到 incoming tab；因此 D1 方案 B 的 `if (slashSuggestionsEl.hidden) updateSlashSuggestions()` 读到的确实是 B tab 的输入内容，不存在「读到 A 残留」的竞态。来源: grill-fix-issue-191-2026-09-20-001

- **决策**: design D1 对方案 A 的否决理由（「click 慢于 100ms 时定时器先于 `switchTab` 触发，此刻 active 仍是原 tab，守卫放行 → 列表被收；切回不恢复」）**确认成立且可稳定复现**。理由: probe_p 给 A 插桩后直接读到三个时刻——`hold=140ms` 与 `hold=250ms` 时 trace 为 `BLUR-armed → TIMER-FIRED(activeIsMine=true) → SWITCHTAB(tab1) → SWITCHTAB(tab2)`，返回 tab2 后 `hidden=true, n=0`；`hold=0/60ms` 时 trace 为 `BLUR-armed → SWITCHTAB → SWITCHTAB`（定时器晚于切换，被 A 的 `clearTimeout` 取消），返回后 `hidden=false, n=3`。probe_i 的「长按鼠标 >100ms 再释放」独立复核得到一致结果（A：0/60ms→可见，140/250ms→被收；B：四档全部可见）。即 A 的缺陷确实只是把「click 快就挂」翻转成「click 慢就挂」，B 的 `switchTab` 收敛点消除了这个翻转。来源: grill-fix-issue-191-2026-09-20-001

- **决策**: design D3 的第二道守卫 `document.activeElement === tab.inputEl` **是必要的，不是「一层可选防御」**；tasks.md 必须把它写成独立断言而不是附带。理由: probe_f 的 `B_no_focus_guard` 变体（保留归属化 + switchTab 收敛，**仅去掉** activeElement 守卫）在「点消息区真实失焦后 100ms 内点回输入框」（f2）场景下 `hidden=true`——列表被错误收掉；带守卫的 B 与 A 均为 `hidden=false`。该场景是用户真实操作（误点空白后马上回来继续输入），无守卫时建议列表会闪没。来源: grill-fix-issue-191-2026-09-20-001

- **决策**: 本 change 的 spec Scenario 3（「标签页关闭后其挂起的收起动作不生效」）**在 ORIG 上就无法证伪，不能作为本 change 的回归靶子**；必须改写或降级为非验收性说明。理由: probe_n 直接给 `hideSlashSuggestions()` 插桩，在「blur X → 切到 Y → 关闭 X」的单 JS turn 内记录：回调触发时 `pane=X 且 connected=false、wasHidden=true`，即定时器只写到了**已 detach 的 X 自己的列表元素**，`y_hidden_after=false`——ORIG 与 B 均不违反该 Scenario（probe_l / probe_o 的 `o1` 在 ORIG/B 下都 `yHidden=false`）。该 Scenario 描述的失败模式在当前架构下**不可达**（`hideSlashSuggestions` 走全局代理，而代理在关闭后已指向 Y，且 X 的列表元素已 detach），写成 Requirement 会产生一条永远为真的空断言。来源: grill-fix-issue-191-2026-09-20-001

- **决策**: proposal/design 声称的「跨 tab 泄漏」**在 ORIG 上真实存在且可由探针稳定复现**，根因描述（异步定时器读触发时刻以外的 active）方向正确。理由: probe_b 的 ORIG 行 `B cross-tab-blur` 得 `before.hidden=false → after.hidden=true`（列表被非本 tab 的失焦收掉）；probe_c 的 `c1_true_cross_tab` 在 ORIG 下 `tab2_t0 可见 → tab2_t400 被收掉`，A/B 下保持可见。该泄漏确实是失败测试「自称要验证的不变量」，proposal 的核心判断成立。来源: grill-fix-issue-191-2026-09-20-001

- **决策**: `switchTab` 收敛点会**顺带改变一个 design D5 未列出的可见行为**——「点击页面非输入框区域（真实 blur，非切 tab）收起列表后，切走再切回，列表会重新出现」。这是**有意且与 spec 措辞一致**的，但 proposal 的「契约影响（对外）」一节只写了「切走再切回」，未提这条从「点空白收起」路径进入的变体。理由: probe_c 的 `c3_click_outside_round_trip`：ORIG `after_round_trip.hidden=true`（保持收起），B `after_round_trip.hidden=false, n=3`（按输入内容复活）；probe_c 的 `c4_apply_suggestion_round_trip` 同样：`/status` 应用后（列表收起、输入框仍是完整命令）切走切回，ORIG 保持收起，B 复活出 1 项。spec delta 的措辞（「可见性 SHALL 由该标签页自身的输入内容唯一决定」）**支持 B 的行为**，故这是 spec 与实现的正确对齐，但公告范围应补全。来源: grill-fix-issue-191-2026-09-20-001

- **决策**: 100ms 宽限窗对「点击建议项本身」**不是必需的**（D5 的理由写错了），但对「真实失焦后快速点回输入框」这一路径**是可观测的行为语义**，故保留时长仍是对的。理由: probe_e/probe_o 的 `suggestion-click` 在 ORIG/B/A 下 blur 计数均为 **0**——建议项用 `mousedown` 且 `event.preventDefault()`（`chat.js:1768-1771`），焦点从未离开输入框，blur 根本不触发；把 delay 改成 0 的 `ZERO_DELAY` 变体（probe_o `o2`）点建议项仍成功（`value=/status`）。所以 D5「删掉会让点选建议项失效」的因果链不成立；但**时长本身仍不该动**，因为它决定了「失焦后多久内点回来不算数」这一用户可感知窗口（D3 守卫的生效范围）。来源: grill-fix-issue-191-2026-09-20-001

- **决策**: 门禁侧确认本 change 当前**不会被 grill 门禁拦住**，但会被 `diagnosis.md` 与 spec-sync-task 两条 checker 规则拦住；这两条必须在 tasks/文档中补齐。理由: `parse_change_type` 实测返回 `ChangeType(primary='bugfix', secondary=())`，`all_types & DESIGN_TYPES == set()`，故 `_check_design_review_task` 直接 `return []`（不检查 grill 证据）；而 `all_types & DIAGNOSIS_TYPES == {'bugfix'}`，故 `check_openspec_artifacts.py` 要求 `diagnosis.md` 含 6 个固定章节（Symptom/Reproduction/Evidence/Root Cause/Recommended Direction/Regression Tests）。`PYTHONPATH=. uv run python scripts/check_openspec_artifacts.py` 当前输出两条 ERROR：`missing required file: diagnosis.md` 与 `tasks.md missing current spec sync task for spec delta`。来源: grill-fix-issue-191-2026-09-20-001

- **决策**: guard 的 `_is_change_doc_write` 对 `reviews/**` 与 `specs/**` 豁免 grill 门禁，写法必须是**绝对路径**（guard 收到的 `file_path` 是绝对路径）。理由: 实测 `g._is_change_doc_write('<abs>/openspec/changes/fix-issue-191/reviews/grill-design.md') == True`、`'.../design.md' == True`、`'.../web/static/chat.js' == False`、而相对路径 `'openspec/changes/.../reviews/grill-design.md' == False`。`web/static/chat.js` 不在豁免内 → 写实现前 guard 会 exit 2 直到 grill 证据齐全，这正是本 change 依赖门禁生效的路径。来源: grill-fix-issue-191-2026-09-20-001

## Open Questions

- **Q1 —— spec 的「可见性唯一由输入内容决定」要不要对「主动收起」也生效？（这条决定 B 的实现边界，也决定 c3/c4 行为变更是否算 bug）**
  具体场景（本 change 实测数据）：
  - **步骤一**：tab2 输入 `/s`，建议列表出现 3 项；
  - **步骤二**：用户**点击消息区空白处**（真实 blur，非切 tab）→ 列表收掉（ORIG 与 B 都一样）；
  - **步骤三**：用户切到 tab1，再切回 tab2。
  - **选法一（= design 选定的 B）**：切回时列表**重新出现**（`hidden=false, 3 项`，实测 B 行为）。语义是「列表永远反映输入内容，收起只是临时的」。
  - **选法二**：切回时列表**保持收起**（实测 ORIG 行为）。语义是「用户主动收起过，就尊重这个意图，直到他再次输入」。
  - **为什么必须你来拍**：spec delta 现措辞（「SHALL 由该标签页自身的输入内容唯一决定」）字面**支持选法一**；但选法一意味着「点空白收起」在切 tab 后会自动撤销——如果这不是你要的，spec 与 D1 的措辞都要改成「切换 SHALL 只把列表收敛到与该 tab 输入内容一致，但**已被用户显式收起的不重新展开**」，实现上要在 tab 上多记一个 `userDismissed` 位。探针还发现选法一会在 `/status` 应用后（输入框留着完整命令）切回时复活出 1 项（probe_c `c4_apply_suggestion_round_trip`），这是同一条语义的另一个面。

- **Q2 —— B 引入的「Escape 后 Enter 发不出消息」怎么处理？（这是本轮追问发现的真回归，必须选一个）**
  具体场景（probe_h / probe_i / probe_o 三处一致复现）：
  - **步骤一**：tab2 输入 `/status`，建议列表出现；
  - **步骤二**：按 `Escape` 收起列表（`hidden=true`，输入框仍是 `/status`）；
  - **步骤三**：按 `Enter`。
  - **ORIG 行为**：消息正常发出（`userMsgs` 0→1，输入框被清空）。
  - **B 行为**：`Enter` 被 `keydown` 处理器先调 `switchTab(tab.id)` → 因列表 `hidden` 而重新求值 → 列表复活 → 同一 keydown 落入 `Tab||Enter → applySlashSuggestion` 分支 → **消息永远发不出**，输入框保持 `/status`，再按多少次 Enter 都一样（实测连续 3 次 Enter，`userMsgs` 恒为 0）。
  - **选法一**：在 `switchTab` 里区分调用来源（例如给 `switchTab` 加一个 `{ reevaluate: false }` 参数，或让 `inputEl` 的 keydown 代理改调一个不做收敛的内部函数），只让「用户点 tab / 程序切 tab」走收敛。改动略大但语义干净。
  - **选法二**：收敛改为「只在列表从**无匹配**变为**有匹配**时才展示」的纯函数式判定（例如重新求值后仅当 `slashMatches` 由空变非空才展开，或仅在 `pane.classList` 从非 active 变 active 时收敛）。改动集中在 `switchTab`，但要多维护一个「上次是否匹配」的状态。
  - 无论选哪个，tasks 必须新增一条**回归测试**：`Escape` 后 `Enter` 仍能发送消息。这条测试对 B 的朴素实现 100% 失败（probe_o 实测），是必须补的变异靶子。

- **Q3 —— `diagnosis.md` 与 spec-sync task 谁来补？**
  `scripts/check_openspec_artifacts.py` 对 `primary: bugfix` 强制要求 `diagnosis.md`（6 章：Symptom / Reproduction / Evidence / Root Cause / Recommended Direction / Regression Tests），并要求 tasks.md 出现「current spec / 当前规格」+ `openspec/specs` 字样的同步任务；当前两者都缺，checker 直接报 2 条 ERROR。proposal/design 里其实**已经写满了 diagnosis 需要的内容**（两层根因、探针表格、验收口径），所以低成本做法是新建 `diagnosis.md` 从 design/proposal 抽成 6 章。
  - **选法一**：补 `diagnosis.md`（照 checker 的 6 章填，指向已有探针证据）+ 在 tasks 加 spec-sync 任务。门禁按现状通过。
  - **选法二**：主张 bugfix 已有 design.md 就够、诊断章节冗余，走结构关键词理由申请豁免。**注意**：实测 checker 对该路径**没有豁免分支**（`if all_types & DIAGNOSIS_TYPES` 无条件要求文件），选法二需要先改 checker，属于扩大本 change 范围。
  - 需要你确认的是「按选法一补文档」还是「认为门禁该松、另开 issue 治理」。

## 风险

- **R1（必须改）**: `diagnosis.md` 缺失 → `check_openspec_artifacts.py` 硬失败。这是 CI 门禁项（AGENTS.md「baseline CI 门禁包含…项目 artifact checker」），PR 前必过。处置：见 Q3。
- **R2（必须改）**: tasks.md 缺 spec-sync 任务 → 同上 checker 硬失败。注意现有 tasks 的「文档」小节只写了「spec delta：…新增 Requirement」，措辞里没有「current spec / 当前规格」+ `openspec/specs`，不满足 `_has_current_spec_sync_task`。处置：见 Q3。
- **R3（必须改）**: D1 的 `switchTab` 收敛点与 `inputEl` keydown 的 `switchTab(tab.id)` 代理耦合，导致 Escape 后 Enter 静默失效（Q2）。这是本轮追问发现的**设计缺陷**，不是实现细节，必须在 design.md 里写清调用来源区分方案，否则实现者会照 D1 直译出有缺陷的代码。
- **R4（必须改）**: design/tasks 的**变异靶子选错了**。design D4 说新增回归测试「对旧实现 100% 失败」，但没定义它必须能杀死哪种半吊子实现。probe_f 的判别矩阵实测：
  | 测试 | ORIG | half（只加 active 守卫） | A（归属化+取消，无重算） | B |
  |---|---|---|---|---|
  | t_a 切走即切回（Scenario 1 风格） | ✗ | ✗ | ✓ | ✓ |
  | t_b 跨 tab 失焦（Scenario 2 风格） | ✗ | ✓ | ✓ | ✓ |
  | t_c 收起后切走切回按内容重算（判别器） | ✗ | ✗ | ✗ | ✓ |
  解读：Scenario 1/2 两条只能把 ORIG 与「至少加了归属化」的实现区分开，**杀不死 half**（只加 active 守卫就通过 t_b），也**区分不出 A 与 B**（两者都通过 t_a/t_b）；**t_c 是 B 与 A/half 的唯一判别器**。design D4 只承诺了一条 t_b 类测试，靶子不足。补强方案：再加 **t_d「慢 click（mousedown 后按住 >100ms 再释放）」**——probe_p 实测 A 在此场景下 `hidden=true`、B 为 `hidden=false`，可用于把 A 也纳入变异靶子。
- **R5（必须改）**: spec Scenario 3 在 ORIG 上不可证伪（probe_n 插桩：关闭 tab 的回调只写到 `connected=false, wasHidden=true` 的自身 detach 元素，`y_hidden_after=false`；ORIG 与 B 均不违反）。写成 Requirement 会留下一条永远为真的断言，且会诱导实现者去写「为关闭 tab 加清理」这类无对象的防御代码。处置二选一：**（a）** 改成可证伪的等价断言——「关闭**当前活跃** tab 后，剩余 tab 的建议可见性 SHALL 等于其自身输入内容所决定的状态」，因为 `closeTab` 会调 `switchTab(next)`（`chat.js:300-306`），这条在 ORIG 的收敛缺失下是可失败的；**（b）** 直接从 spec delta 删除该 Scenario 并在 design 说明「当前架构不可达，无需约束」。两条都需要你先确认走哪条。
- **R6（建议）**: proposal「契约影响（对外）」只公告了「切走再切回」一条可见行为变更，遗漏了「点空白收起后切回会复活」与「apply 建议项后切回会复活」（probe_c c3/c4）。应补全公告范围，避免下游基于不完整的契约影响做判断。
- **R7（建议）**: proposal/design 两处把「100ms 宽限窗」说成服务于「建议项 mousedown → blur → click」的点击落地（D5、proposal Non-Goals）。探针证明点建议项**不触发 blur**（blur 计数恒为 0，`mousedown` + `preventDefault` 已阻断）。结论（保留 100ms）不变，但理由应改成「保留失焦后快速点回输入框的宽限语义（D3 守卫的生效窗口）」，否则后续维护者会基于错误因果去删/改这个常量。
- **R8（提示）**: 测试 fixture 有个隐含时序假设：新建 tab 的 id 从 `new-N` 被 rekey 成真实 session id（`chat.js:416-433` `handleTabEvent`），且 rekey 发生在 WS 握手事件到达时。探针里若提前缓存 `data-tab-id` 会拿到过期值（probe_d 首次运行即因此误判）。新写的浏览器测试应在操作前 `wait_for_function` 等到 `.session-tab` 的 id 不再以 `new-` 开头（probe_o 的 `o1` 用了这个等待），否则会随机 flake——这与本 change 想根治的 flake 是**同类但不同源**的问题。
- **R9（提示）**: 本 change 的 spec delta 是 `ADDED Requirements`，归档时需要 `current_spec_synced` 事件（`openspec/specs/` 是受保护路径，`match_type: prefix`）；`docs/openspec-change-backlog.md` 需要 `backlog_updated` 事件（已有一条 seq=1）；归档时还需要 `change_archived`。`reviews/**` 本身不在受保护路径表内（未被 `flow-policy.json` 覆盖），写入无需事件，guard 也将其视为 change doc 写而豁免 grill/awaiting 门禁。无死锁点。
