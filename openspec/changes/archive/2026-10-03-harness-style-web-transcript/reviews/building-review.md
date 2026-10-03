# Building Review: harness-style-web-transcript（Round 2，终稿 PASS）

| 项 | 值 |
|---|---|
| change | `harness-style-web-transcript`（Web 对话区改为 harness 式 transcript：正文成文 + 工具执行单行折叠） |
| 分支 / worktree | `harness-style-web-transcript/2026-10-03` @ `D:\code\asterwynd-worktrees\harness-style-web-transcript` |
| base / head | base `master` = `3b484076f10fa295ce05bb53a01ef53c56c2cc17`；HEAD 同值（**全部改动尚未提交**，审阅对象是工作区改动；`git diff master...HEAD` 为空） |
| round | **Round 2**（零记忆独立审阅；两遍：第一遍判 `CHANGES_REQUESTED`（1 MEDIUM），实现方修完后第二遍**聚焦复验**通过并签发 PASS。跨轮次口径见 `tasks.md` §6=Round 1、§7=Round 2、§8=Round 3、§9=Round 4、§10=Round 5） |
| reviewer run id | `building-review-harness-style-web-transcript-20261003-r2` |
| 审阅修订（最终冻结锚点，全部由本人重算） | `web/static/tool_rows.js` `8030C9511DE11AAFA2326302F3B56DD0DBFCB0810D5AF043DE4D3824C5245E43` · `web/static/chat.js` `CEF0043D4D421289750B4BD1295A48C6F98F806E602D1EF7B685D7E6F8EBC813` · `web/static/style.css` `9A036E3E58BD4AFBB327CC8FA40B781E5C48A16BC82AC68A83245DDDE0383735` · `web/static/workflow_transcript.js` `4D37ED9C7CF1E143EFF226F685DC2B3EBDCDFAF15352B0D069F7E4C18EA44089` · `web/static/index.html` `2C65A7E994D8482C72C9A7440BB469AEEA0BA5A98D67E006A2C27BDA7CD44733` · `web/session.py` `830014E35AB561C8AB7D158D3A6D655286D81DBA62614DBE588D1F21058D8CEF` · `tests/web_tests/test_transcript_js.py` `1A1AA7C1BC38DC05842C43F1FB0F81A1803A0337934AD3BD7E44D68BF9491D16` · `tests/web_tests/test_transcript_view_browser.py` `8889906A7710776B857736DBDC2797F38FAC7CD6CD08720E3243B26F0AD4EBB5` · `tests/web_tests/test_multi_session_browser.py` `3DC0957FBC6F9E47DB166D7174654D1EB4D1AFFB2B64DC788156D6BE35DEEDEC` · `tests/web_tests/test_server.py` `9602B44DAC5CADAFD54DE9EB340FCC606AC4CF7833E1FAD6938BA97A594806CF` · `tests/web_tests/test_session.py` `F4E1DBBA83CD7E79818A0439E692EC23C2C500081BB560E059E9205608906E38` · `tests/web_tests/test_workflow_graph_browser.py` `177D21AF42AB1CCC03FDEEE38FA3FD526D41BD18D32843EEF02C24757B29648A` · `tests/web_tests/test_browser.py` `46833864B4C58B29024FF3C23B8F9EAE124E0F8068CE6703FE643FD6F95686E3`（与 master 同内容，未被本 change 修改） · `tasks.md` `0AA8BCBCCF147336199CB39AA7C55C0C3F7A470D6F0CF862F68C6AE5E39F870B` · spec delta `2514ED5BF2A5D61E9E3C11D1F0BF758C844E21490C0A8AE637DBEB7398FEA4D3` · `proposal.md` `13016335E17094C33F5ACBA0CB840C127344F9CE63E412A3A330EB4BF2EB7F48` · `design.md` `027B474F564D2AE8CC6CB90D3AED358475A053E4D4B3F9EF016CE40BA20D4F00` · `reviews/acceptance-evidence.md` `EDF8468B236E0F96067380DEDD2D1931B1B7768A7CF2CEDBB865329B33F6B8B0` · `reviews/grill-design.md` `2A29A9D34A004005FC3AD846E2EA500F54D5250DEE1D0EBF12B1D1056B786703` · `docs/known-debt.md` `4E84C514EC8FC0DC3579CBC967CFB1CACFA467E28C7E98D12AC8C26045FB9C18` |
| method | **零记忆独立审阅**，不采信文档自述，全部结论由本会话取证：① 通读 proposal / design / tasks（§6–§10）/ spec delta / grill-design（含 `## User Confirmation`）/ acceptance-evidence；② 逐行读 `tool_rows.js` 全文与 `chat.js`/`style.css`/`workflow_transcript.js`/`web/session.py` 的改动、两个新增测试文件全文；③ 后端交叉核对 `agent/loop.py`（`_text_prefix_guess`、两处事件发射点、审批分支、`_format_task_output`、`_wait_task_output`）、`agent/tools/registry.py`、`agent/tools/builtin/{bash,browser_*,tasks}.py`、`agent/tools/sandbox/base.py`、`agent/background.py`、`agent/mcp/manager.py`、`agent/message.py`、`web/session.py`（含 resume 快照路径）；④ 实跑 8 文件官方套件（多轮）+ 单文件计数 + `check_openspec_artifacts.py` + `openspec validate --all --strict`；⑤ 仓库外写 node 探针（8 组失败判定输入）+ 3 个 Playwright 探针（任务形状 / `/clear` 残留对照 / 提示裁剪）；⑥ **16 组变异实验**（11 组在仓库内、5 组在仓库外 TEMP 镜像；仓库内每条都按 sha256 还原并用冻结基线复核 `drift=0`）；⑦ 在 pristine `D:\code\asterwynd`（HEAD `3b48407`，`web.__file__`/`agent.__file__` 已确认为 pristine）复现全部「环境性失败」声明。**本报告只对上表最终冻结哈希负责。** |
| 关于本文件 | 本路径的审阅历史：16:50 的 Round 1 报告（249 行）→ 17:05 的 Round 3 报告（221 行，另一审阅者）→ 本人 17:43 的 Round 2 第一遍报告（270 行，`CHANGES_REQUESTED`）→ **本文件（终稿，PASS）**。前三份均已整份备份到 `%TEMP%\aw-backup2\building-review-r1.md`、`%TEMP%\aw-backup3\building-review-other-r2.md`、`%TEMP%\aw-backup2\building-review-r2-changes-requested.md`（sha256 `A6C6BEBD…`）。**未生成 manifest**（按仓库纪律在归档 move 之后由主 agent 生成）。 |
| 并发修改说明 | 审阅期间工作区被实现方多次落盘（16:50–16:54、17:14–17:25、17:48–17:55）。本人每轮都先以 sha256 冻结基线再做实验；本终稿对应 17:59 冻结的修订，写报告前复核 **drift=0**（24 个受控文件与基线逐字节一致），`git status --short` 无新增行。 |

## Verdict

**PASS**

**判据（全部在最终冻结修订上复核）**：

1. 调用方点名的 4 条 Round 1 发现（MEDIUM-1 `TaskOutput` 多行失败漏判、MEDIUM-2 历史摘要与投影互斥、MEDIUM-3 提示可见性无断言、HIGH-1 tasks 假勾选）**全部真实修复**，且每条都有变异反证（M1–M11）。
2. 第一遍审阅给出的**唯一 MUST-FIX**（`spec.md:139` 的两条重绘清空路径零覆盖，M3/M4 变异存活）已闭环：新增 `test_clear_command_drops_pending_tool_rows` 与 `test_history_redraw_drops_pending_tool_rows`，我**独立**分两处变异复核，**各只让对应用例变红、互不冒充**（M12/M13）。
3. 我第一遍提的 7 条 LOW 全部处理并在盘上验证（计数 57/21/106、27 项环境失败口径、`acceptance-evidence.md:43` 改为 exit 1 说明、与 `tasks.md:72` 的措辞统一、5.7/5.8 改回未勾 `(closeout)`、`[Task <id> timeout]` 包装判失败、前导空行取首个非空行、`aria-controls`、grill 文件名注记）。
4. 我第一遍自做的 11 组变异所钉的行为在最终修订上**无回归**：8 组输入级探针 + 57 条 node 用例合跑 **65 passed**（第一遍时其中 2 条为 RED）；浏览器探针 3 passed；`/clear` 残留对照表现为规格要求的「结果先到自建一行」。
5. 未引入新阻断：8 文件官方套件 `1 failed（环境性 printf，pristine 同样失败）/ 222 passed / 7 skipped`；`openspec validate --all --strict` 29/29；`spec.md` 与实现在新增条款上逐条对齐（`:102` 前缀清单含浏览器族、`:103` 含 `stdout:` 收尾 / 裸 `Error` 单行 / **首个非空行**、`:104` 等待超时包装）。
6. 残余项只有 1 条**不阻塞的观察**（`aria-controls` 实现无断言）与 2 条环境/流程事实（manifest 按契约缺席、全量 pytest 计数无法在本机产出），均记录在 `## Issues` 的「非阻断观察」与 `## Test Results`。

**归档前不需要再改任何代码或测试。**

## Round 1 Findings Verification

调用方点名的 4 条（= `tasks.md` §6.1–6.4）。每条都做了「读实现 → 跑用例 → 变异反证」三步。

| 编号 | 原结论 | 是否修复 | 证据（file:line，最终冻结修订） |
|---|---|---|---|
| MEDIUM-1 | `TaskOutput` 多行结果（`[Task <id>]` + `status:` + `exit_code:`）失败被判成 `ok` | **已修复 + 已加固** | 检测器 `web/static/tool_rows.js:345-368`（`taskFailure`；门 `^\[Task …\]`、状态集 `failed/timeout/orphaned/killed/error`、退出码行）；**越界误报也已修**：`:357` 在 `stdout:` 行停止扫描；**等待超时包装也已修**：`:397-401`（`[Task <id> timeout] …` → `error` / `code='timeout'`）。用例：`tests/web_tests/test_transcript_js.py:285`（failed/timeout）、`:305`（completed+非零退出）、`:312`（running/成功）、`:321`（门不成立不得误报）、`:334`（stdout 收尾）、`:377`（等待超时包装）。变异 M7/M8/M14 均变红。 |
| MEDIUM-2 | spec 要求历史行显示参数摘要，但历史投影只发 `id`/`name`，摘要恒为空 | **已修复（spec / 实现 / 断言三处一致）** | spec：`specs/web-ui/spec.md:225`「摘要 SHALL 降级为**结果首行**」；实现：`web/static/chat.js:819`（`argsSummary \|\| api.truncate(api.firstLine(text), …)`）；断言：`tests/web_tests/test_transcript_view_browser.py:398`（`title == "Bash"`、`summary == "1 failed, 12 passed"`）。变异 M1（去掉结果首行回落）→ 该用例变红。 |
| MEDIUM-3 | 「参数已截断」只有 `text_content` 断言（连 hidden 子树一起取），看不出可见性 | **已修复（断言有牙齿）** | 提示渲染在**头部行**：`tool_rows.js:552`（`head.appendChild(note)`；body `hidden` 在 `:557`）；可见性断言：`tests/web_tests/test_workflow_graph_browser.py:955-956`（`page.inner_text(".drawer-body")` + `assert "参数已截断" in visible`）。变异 M6（note 移回 hidden body）→ **只有 `inner_text` 那条变红**，旧的 `text_content` 断言（`:951`）仍绿——正是 Round 1 指出的形态。 |
| HIGH-1 | `tasks.md` 的 5.1/5.3/5.4 勾选与工作区状态矛盾 | **已修复** | `tasks.md:40` 顺序说明；`:42/:44/:45/:47/:48/:49` 六条 closeout 全部 `- [ ]` + `(closeout)`（5.1 同步 spec、5.3 归档、5.4 backlog 出队、5.6 artifact checker、5.7 审阅+manifest、5.8 发起 PR）。我实测：`openspec/specs/web-ui/spec.md` 未修改、`openspec/changes/archive/2026-10-03-harness-style-web-transcript/` 不存在、backlog 条目仍在、无 commit/PR——与未勾状态自洽。 |

补充：Round 1 **报告**（前序文件）的 8 条 issue 亦逐条复核：

| Round 1 报告 issue | 最终修订上的状态 | 证据 |
|---|---|---|
| Issue 1 队列清空不变量无回归 | 已闭环（`done`/`error` 路径） | `chat.js:857-865`（`settleOrphanToolRows` + `pendingToolRows.length = 0`）、只读探针 `chat.js:2322`（`pendingToolRowCount`）；用例 `test_transcript_view_browser.py:264`（队列深度）、`:280`（僵尸行不得认领下一轮）；变异 M2 → 两条同时变红 |
| Issue 2 tasks 假勾选 | 已闭环 | 同 HIGH-1 行 |
| Issue 3 `onclose`/`onerror` 守卫不完整 | 已闭环 | `chat.js:454-457`（`if (!tabs.has(tab.id)) { rejectWsUploadWaiters(...); return; }`）、`:475`（`onerror` 早退）；用例 `test_multi_session_browser.py:340`；变异 M5 → 变红 |
| Issue 4 `dataset.summarySource` 死代码 | 已闭环 | 全仓 grep `summarySource` 零命中 |
| Issue 5 `structured` 文档口径 / `firstLine(lines.join)` / `name` 未用 | 已闭环 | `tool_rows.js:390-401` 的 JSDoc（含 `TaskOutput` 多行形态与 `name` 保留说明） |
| Issue 6 文档计数漂移 | 已闭环 | `proposal.md:112` / `design.md:186` → 21；`acceptance-evidence.md:38/39/40` → 57/21/106；`:49` → 27 项（ux 26 + graph 1）；`tasks.md:34` → 21 |
| Issue 7 4 条条款无断言 | 已闭环（4/4） | `test_transcript_view_browser.py:426`（行高恒定）、`:451`（HTML 纯文本 + `onerror` 不执行）、`:470`（单列文档流）、`:507`（思维链折叠态单行高度） |
| Issue 8 实现先于 grill 的流程债 | 已闭环 | `docs/known-debt.md:8-10` + `workflow-events.jsonl` seq 2（`protected_artifact_explained`） |

第一遍审阅（本人）提出的 1 条 MUST-FIX + 7 条 LOW 的处置与复核：

| 编号 | 处置 | 我的复核 |
|---|---|---|
| MUST-FIX Issue 1（MEDIUM）`/clear` 与 `session_history` 清空零覆盖 | 新增两条浏览器用例（`test_clear_command_drops_pending_tool_rows` 与 `test_history_redraw_drops_pending_tool_rows`，各含「队列深度 == 0」与「清空前的行不得被重新挂回来 / 不得认领新结果」两段） | **M12/M13 独立变异**：只删 `chat.js:562` → 仅 clear 用例红；只删 `chat.js:765` → 仅 history 用例红（各 `1 failed, 1 passed`）。判据完全满足 |
| LOW-2 计数漂移 | 三处文档改实测值 | 实测 `57 / 21 / 106`、`tasks.md:34` 21、`:49` 27 项 —— 与文档一致 |
| LOW-3 `acceptance-evidence.md:43` 过期 + `:87` 与 tasks 矛盾 | `:43` 改为「当前 exit 1（唯一错误 `review manifest missing`，预期）」；`:87` 改为「该发现在其对应的 16:42:44 修订上确实成立，当前修订正确，根因是另一审阅者的过期备份还原」 | 两条已读盘核对，与 `tasks.md:72`（§8.1）一致，矛盾消除 |
| LOW-4 5.7/5.8 假勾选 | 改回 `- [ ]` + `(closeout)` | `tasks.md:48-49` 已核对 |
| LOW-5 `[Task <id> timeout]` 判 `ok` | 新增等待超时判定（`error` / `code='timeout'`）+ node 用例 | 变异 M14 → `test_result_detects_wait_timeout_wrapper` 变红 |
| LOW-6 前导空行漏判 | 新增 `firstContentLine()`，失败判定与结构化解析改用首个非空行 + node 用例 | 变异 M15（改回 `firstLine`）→ `test_result_ignores_leading_blank_lines_when_detecting_failure` 变红；我的 8 组探针在本修订上全绿 |
| LOW-7 `aria-controls` | 每行唯一 body id + 头按钮 `aria-controls` | 实现已读盘核对（`tool_rows.js:554-559`）；**无用例覆盖** → 见「观察 1」 |
| LOW-8 grill 文件名注记 | `grill-design.md` 顶部注记改名对应关系 | 已读盘核对（文件顶部注记） |

## Tasks Verification

逐条核对 `tasks.md`（最终修订 92 行）的每一个勾选/未勾项，判据是「工作区里是否存在可指认的产物」。

| 任务 | 证据 | 判定 |
|---|---|---|
| 1.1–1.4 立项与调研 | `proposal.md`（含 RIR `research_tier: full` + questions/findings/design impact）、`design.md`、`docs/openspec-change-backlog.md` diff `+10/-0` + `workflow-events.jsonl` seq 1 | verified |
| 2.1–2.4 grill 与确认 | `reviews/grill-design.md:10-32`（12 条 `- **决策**:`）、`:36-46`（Q1–Q6 各配真实场景例子）、`:78-89`（6 条答复 + 确认时间，已如实披露为「用户整体预授权 + 主 agent 按推荐拍板」并记入 `docs/known-debt.md`）；D4/D5/D9/D11/D12 表述与实现一致 | verified |
| 3.1–3.9 实现 | `test_transcript_js.py` 57 用例跑绿（`:49` 显式 `encoding="utf-8"`）；`tool_rows.js` 纯函数层 + DOM 层导出齐备；`chat.js` per-tab 归属（`:25/222/257`）、建行入队（`:1059-1071`）、原地补全（`:1079-1092`）、收尾（`:857-865`）、`/clear`（`:562`）、`renderHistory`（`:765`）；`addMessage` 骨架（`:935-947`）；`web/session.py:43-59,88-89`；`style.css` 两处 `.tab-messages`（`:146-160`、`:1374-1388`）+ `.tool-row*`（`:401-543`）；`workflow_transcript.js:426-438`；`index.html` 接线（`tool_rows.js?v=1` 在 `chat.js?v=25` 之前、wordmark `?v=3` 未动） | verified（「先写」时序不可回溯，只验证产物有效） |
| 4.1–4.4 测试与验收 | `test_server.py` 锚点迁移 + `read_text(encoding="utf-8")`（pristine 上该用例因 GBK 解码失败，本 change 修好）；`test_session.py` 新用例；变异 M1–M11 覆盖五类形态；浏览器 21 项 + 既有四套（`test_browser.py` 与 master 同内容、`test_multi_session_browser.py` 20 项、`test_reconnect_*`、`test_workflow_graph_browser.py` 28 项）全绿 | verified |
| 4.5 全量 pytest + baseline 对照 | 8 文件套件 `1 failed / 222 passed / 7 skipped`；全量单进程计数本机无法产出（见 `## Test Results` §2）；环境性失败已在 pristine 逐项复现 | partially verified（计数缺失，非本 change 缺陷，已如实说明） |
| 4.6 benchmark smoke | 未复跑；本 change 未触及 `agent/loop.py`/`agent/tools/`/`benchmarks/`（`git status` 可证），不构成回归面 | not re-run（不做判定） |
| 5.1/5.3/5.4/5.6/5.7/5.8 closeout | 六条均为 `- [ ]` + `(closeout)`，与工作区状态自洽（spec 未同步、无 archive 目录、backlog 条目仍在、无 manifest、无 commit/PR） | 未完成（状态正确，归档时勾选） |
| 5.2 文档影响检查 | `README.md`/`README_EN.md`/`docs/architecture.md` 各一处按事实更新 | verified |
| 5.5 openspec strict validate | 实跑 `Totals: 29 passed, 0 failed` | verified |
| (post-merge) 建 issue | `tasks.md:50` 带 `(post-merge)` 标记，写法合规 | verified（标记合规） |
| 6.1–6.4 Round 1 修复 | 见 `## Round 1 Findings Verification` | verified |
| 7.1–7.8 / 8.1–8.4 / 9.1–9.5 历轮补正 | 守卫与 `length = 0` 在盘（`chat.js:454/475/864`）；思维链单行高度用例（`test_transcript_view_browser.py:507`）；三条失败判定加固在盘（`tool_rows.js:141-143/153/341/397-404`）且各有 node 用例；多 tab 状态用例（`test_multi_session_browser.py:340`）；流程根因记入 `tasks.md` §8.4/§9.5 | verified |
| 10.1–10.6 Round 5 修复（本 MUST-FIX + LOW） | 见上节「第一遍审阅…处置与复核」表；10.5 无断言（观察 1） | verified |

## Spec Alignment

逐条核对 `specs/web-ui/spec.md`（最终修订）与实现、断言覆盖。「有断言」= 有真实用例；「仅实现」= 实现满足但无用例。

| Requirement / Scenario | 实现证据 | 断言覆盖 |
|---|---|---|
| MODIFIED 工具结果展示 · 一行 / 行高固定 | `tool_rows.js:486-570`；`style.css:401-437`（head 固定 24px） | 有：`test_transcript_view_browser.py:159`（行数 + 折叠 + 可见文本 <1200 + 逐行摘要 ≤90）、`:426`（`bounding_box` 行高恒定 ≤26px） |
| · 折叠态零正文（SHALL NOT 含 `preview`） | `tool_rows.js:557`（`body.hidden = true`），参数/结果只写 body | 有：`:159` |
| · 展开（缩进 JSON + 全文）+ body 是兄弟节点 | `tool_rows.js:558-560`（head/body 同级）、`:568-574`（点击只切 `aria-expanded`/`hidden`） | 有：`:322`（展开/收起/aria）、`:344`（体内点击不折叠）、`:359`（缩进 JSON） |
| · 元数据取 `display.char_count`/`line_count` | `tool_rows.js:621-628`、`:412-422` | 有：`:208`（"字符"） |
| · 纯文本（不解析 HTML） | `tool_rows.js:464`（`setText`）、`:614`（`resultPre.textContent`） | 有：`:451`（`<img onerror>` 无元素注入、`window.__pwned` 不置位、原文可见）+ `test_server.py:597-600` 源码护栏 |
| · 参数上限共用 | `tool_rows.js:439-455`（`prettyArgs` → `formatBodyText(…, BODY_LIMIT)`） | 有：`test_transcript_js.py:462-478` |
| MODIFIED 思维链折叠 · 默认关闭/单击展开/无则不渲染/与正文分离/折叠态一行 | `chat.js:888-947`；`style.css:224-247` | 有：`test_browser.py`（既有）+ `test_transcript_view_browser.py:507` |
| ADDED 失败信号可见 · 审批被拒 / 命令非零退出 / 成功不误报 / 前缀对齐 / 不误报 | `tool_rows.js:128-153`（锚定行首）、`:383-398`（结构化 JSON）、`:431`（裸 `Error` 仅单行）、`:397-401`（等待超时）、`:392`（首个非空行） | 有：`test_transcript_js.py:222/243/259/278/346/359/374/377/385/414`；浏览器 `:533/559/580` |
| · `TaskOutput` 多行形态（含 stdout 收尾） | `tool_rows.js:169-173`、`:345-368` | 有：`test_transcript_js.py:285/305/312/321/334`；变异 M7/M8 反证 |
| · 浏览器族前缀 | `tool_rows.js:141-143`（`[Browser Error`/`[Browser not available`/`[URL denied`），产生方 `agent/tools/builtin/browser_navigate.py:36,42,54`、`browser_get_content.py:34,37`、`agent/browser/session.py:45,50,69,70` | 有：`test_transcript_js.py:346`；变异 M11 反证 |
| ADDED 按到达顺序配对 · 同名多次 / 结果先到 / run 收尾 / 重绘清空 | `chat.js:838-846`（同名取最早、兜底队首）、`:1079-1092`（无待配对则自建行）、`:857-865`（收尾 + 清空）、`:562`（`/clear`）、`:765`（`session_history`） | 有：`:227`（顺序）、`:251`（结果先到）、`:264`（收尾 + 队列深度）、`:280`（僵尸行不得认领下一轮）、**`:618`（`/clear` 清空）、`:643`（重绘清空）**；变异 M2/M12/M13 反证 |
| ADDED 单列文档流 | `style.css:141-160` | 有：`test_transcript_view_browser.py:470` |
| ADDED 对话区与抽屉共享口径 · 兼容类名 / 截断提示可见 | `tool_rows.js:489`（`tool-call-block tool-row`）、`:503`（`tool-row-title tool-name`）、`:552`（note 在 head）；`workflow_transcript.js:426-438` | 有：`test_workflow_graph_browser.py:955-956`；变异 M6 反证 |
| ADDED 重连历史带工具名 · 显示真名 / 摘要降级 / 拿不到时降级 | `web/session.py:43-59,88-89`；`chat.js:808-826`、`:778-796` | 有：`test_session.py` 新用例、`test_transcript_view_browser.py:398`、`:596` |

对齐结论：**实现满足全部规格条款**，且本轮新增/订正的条款（`:102` 浏览器前缀、`:103` `stdout:` 收尾 + 裸 `Error` 单行 + 首个非空行、`:104` 等待超时包装）逐条有 node 用例支撑。另有两点**已核实为非缺陷**，供后续读者省一次排查：

1. **`hidden` 与 CSS 的相互作用**：所有会被切换 `hidden` 的元素都没有冲突的 `display` 规则，两个新元素另有显式兜底（`style.css:495` `.tool-row-body[hidden]{display:none}`、`:540` `.tool-row-note[hidden]{display:none}`）；L0/L1 用例用 Playwright `is_hidden()`（真实可见性），抽屉侧用 `inner_text`。探针复核：880px 容器 + 超长 MCP 工具名 + 长摘要 + note + meta 时 note 未被 `overflow:hidden` 裁剪（head `scrollHeight == clientHeight`）。
2. **per-tab 队列引用一致性**：`settleOrphanToolRows` 用 `.length = 0`（保引用），`renderHistory`/`/clear` 用 `pendingToolRows = []`（换引用）；因 `handleTabEvent`（`chat.js:484-488`）是 `bindActiveTab` → `handleEvent` → `syncActiveTab()`，每次事件后都把全局写回 tab，故不会出现「tab 持有旧数组、切回后僵尸条目复活」。

## Issues

**无 MUST-FIX / 无阻断项**（第一遍的 1 条 MEDIUM 已闭环，见上）。以下 3 条均**不阻塞归档**，请按需处理或在 PR 描述里记为已知项：

### 观察 1（LOW，可选）`aria-controls` 实现无断言

- **位置**：`web/static/tool_rows.js:554-559`（`rowSeq` 递增 → `body.id = 'tool-row-body-' + rowSeq` → `head.setAttribute('aria-controls', body.id)`）。
- **现状**：实现正确（id 每行唯一、指向兄弟展开体，`aria-expanded` 仍在按钮上表达状态）；但全仓测试只有 `test_server.py:433/438` 断言 plan/planning 面板的 `aria-controls`，本行无覆盖。**变异 M16：删掉 `aria-controls` 那行 → 相关用例 `4 passed` 全绿**（存活变异）。
- **可选修法**：在 `test_tool_row_expands_on_click_and_collapses_again` 里加两条断言（`aria-controls` 非空、`page.locator('#' + id)` 指向的正是该行的 `.tool-row-body`）。属无障碍增强、不影响功能，故不计入 MUST-FIX。

### 观察 2（事实，非缺陷）`check_openspec_artifacts.py` 当前 exit 1

- **位置**：命令 `uv run python scripts/check_openspec_artifacts.py --change harness-style-web-transcript`。
- **现状**：唯一错误是 `review manifest missing: openspec\changes\harness-style-web-transcript\reviews\building-review-manifest.json`。按 `/review-loop` 纪律，manifest 必须在 `tasks.md` 最终化（含归档 move）之后生成，而 5.1/5.3/5.4/5.6 均已被正确标为 `(closeout)` 未勾。**这是预期信号，不是缺陷**；归档后生成 manifest 即恢复绿。

### 观察 3（事实，非缺陷）全量 pytest 计数无法在本机产出

- **现状**：`uv run pytest -q` 全量单进程三次尝试均被本机执行器终止（前台数分钟无输出；后台在进度 45% 处被杀、输出文件没有 summary）。已改为最大可完成分块取证（8 文件 web 套件 208s 完成 + 单文件计数 + pristine 对照）。`tasks.md:35` 的 4.5 因此判为 partially verified。**建议**：PR 描述里附全量计数或注明本机限制。

## Mutation Experiments

两遍共 **16 组变异**。仓库内变异每条都先把目标文件整份备份到仓库外、测完按字节还原，并用冻结基线 sha256 复核（`drift=0`）。选点刻意避开 `acceptance-evidence.md` §4/§4b 已列的五条。

### A. 第一遍（R4 修订 `tool_rows.js 2A6DC745…` / `chat.js CEF0043D…`）：11 组，9 红 2 存活

| # | 变异 | 命令 | 结果 |
|---|---|---|---|
| M1 | `chat.js:819` 去掉历史摘要的「结果首行」回落（=MEDIUM-2 回退） | `uv run pytest tests/web_tests/test_transcript_view_browser.py -q -k history_row_summary` | **RED** `1 failed`（`test_history_row_summary_falls_back_to_result_first_line`） |
| M2 | `chat.js:864` 删 `pendingToolRows.length = 0` | `… -k "settle_when_the_run_ends or zombie"` | **RED** `2 failed` |
| M3 | `chat.js:562` 删 `/clear` 的清空 | `… test_transcript_view_browser.py test_multi_session_browser.py test_reconnect_pending_interaction_browser.py -q` | **GREEN 47 passed（存活）** → 第一遍 MUST-FIX Issue 1 |
| M4 | `chat.js:765` 删 `renderHistory` 的清空 | 同 M3 | **GREEN 47 passed（存活）** → 第一遍 MUST-FIX Issue 1 |
| M5 | `chat.js:454-457` 撤销 `onclose` 早退守卫 | `… test_multi_session_browser.py -q -k closing_one_tab` | **RED** `1 failed` |
| M6 | `tool_rows.js` note 从 head 移入 hidden body（=MEDIUM-3 回退） | `… test_workflow_graph_browser.py -q -k malformed_tool_arguments` | **RED** `1 failed`（失败点是 `inner_text` `:956`，旧 `text_content` 仍绿） |
| M7 | `tool_rows.js` 删 `[Task …]` 门 | `uv run pytest tests/web_tests/test_transcript_js.py -q` | **RED** `1 failed`（`test_task_failure_requires_the_task_header_as_a_gate`） |
| M8 | TEMP 镜像：删 `TASK_STDOUT_RE` 收尾 | `uv run pytest <TEMP>/tests/web_tests/test_transcript_js.py -q` | **RED** `1 failed`（`test_task_scan_stops_at_the_stdout_body`） |
| M9 | `web/session.py:55` 投影带上 `arguments` | `… test_session.py -q -k tool_calls_for_tool_rows` | **RED** `1 failed`（精确相等断言命中） |
| M10 | TEMP 镜像：放宽裸 `Error` 单行规则 | `… <TEMP>/tests/web_tests/test_transcript_js.py -q` | **RED** `1 failed`（`test_bare_error_prefix_requires_a_single_line_result`） |
| M11 | TEMP 镜像：删三条浏览器族前缀 | 同 M10 | **RED** `1 failed`（`test_result_detects_browser_failure_prefixes`） |

### B. 第二遍聚焦复验（最终修订 `tool_rows.js 8030C951…` / `chat.js CEF0043D…`）：5 组，4 红 1 存活

| # | 变异 | 命令 | 结果 |
|---|---|---|---|
| M12 | `chat.js:562` 删 `/clear` 的清空（**只此一处**） | `uv run pytest tests/web_tests/test_transcript_view_browser.py -q -k "clear_command_drops or history_redraw_drops"` | **RED** `1 failed, 1 passed`（只有 `test_clear_command_drops_pending_tool_rows` 红，另一条仍绿 → 两条用例互不冒充） |
| M13 | `chat.js:765` 删 `renderHistory` 的清空（**只此一处**） | 同 M12 | **RED** `1 failed, 1 passed`（只有 `test_history_redraw_drops_pending_tool_rows` 红） |
| M14 | `tool_rows.js` 删等待超时分支 | `… test_transcript_js.py -q -k wait_timeout` | **RED** `1 failed`（`test_result_detects_wait_timeout_wrapper`） |
| M15 | `tool_rows.js` `firstContentLine` → `firstLine`（=LOW-6 回退） | `… test_transcript_js.py -q -k leading_blank` | **RED** `1 failed`（`test_result_ignores_leading_blank_lines_when_detecting_failure`） |
| M16 | `tool_rows.js` 删 `aria-controls` 一行 | `… test_transcript_view_browser.py test_server.py -q -k "tool_rows or static_assets"` | **GREEN 4 passed（存活）** → 观察 1（可选补断言） |

### C. 输入级探针（不改仓库，TEMP 下 node 探针 8 组 + Playwright 探针 3 个）

- 8 组 node 探针（`TaskOutput` 真实四态、`TaskOutput` stdout 含 `status: failed`/`exit_code: 1`、`[Browser Error`、`[URL denied`、`Read` 到首行 `Error:` 的文件、`[Task <id> timeout]`、前导空行、MCP 多行错误）在最终修订上**全部符合规格**（第一遍时其中 4 组为 RED）。
- 3 个 Playwright 探针：`3 passed`（成功任务不得判红、浏览器失败在折叠行可见、note 不被 `overflow:hidden` 裁剪）。
- `/clear` 残留对照探针：盘上正确实现的序列（`tool_call` → `command_result{clear}` → 同名 `tool_result`）产出**一条新行**且摘要为结果首行 `stale-output-after-clear`（规格 `### Scenario: 结果先到` 的行为）；第一遍在「删掉清空」的变异上实测到的是**清空前的行被重新挂回**（摘要仍是 `pre-clear-command`、展开体是旧参数）——这正是第一遍判阻断的实测依据，现已由 M12/M13 的新用例锁死。

## Test Results

### 1. 官方套件（最终冻结修订）

| # | 命令 | 结果 |
|---|---|---|
| 1 | `uv run pytest tests/web_tests/test_transcript_js.py tests/web_tests/test_transcript_view_browser.py tests/web_tests/test_session.py tests/web_tests/test_workflow_graph_browser.py tests/web_tests/test_multi_session_browser.py tests/web_tests/test_browser.py tests/web_tests/test_reconnect_pending_interaction_browser.py tests/web_tests/test_server.py -q` | **`1 failed, 222 passed, 7 skipped`**（唯一失败 `test_server.py::test_websocket_tool_events`，环境性，见 §3） |
| 2 | `uv run pytest tests/web_tests/test_transcript_js.py -q` | **57 passed** |
| 3 | `uv run pytest tests/web_tests/test_transcript_view_browser.py -q` | **21 passed**（真实 Chromium） |
| 4 | `uv run pytest tests/web_tests/test_transcript_js.py tests/web_tests/test_transcript_view_browser.py tests/web_tests/test_workflow_graph_browser.py -q` | **106 passed** |
| 5 | `uv run pytest <TEMP>/aw-scratch/tests/web_tests/test_transcript_js.py <TEMP>/aw-scratch/tests/web_tests/test_attack_js.py -q`（57 条官方 node 用例 + 我的 8 组探针，跑在 TEMP 镜像上） | **65 passed**（第一遍为 `2 failed, 61 passed`） |
| 6 | `uv run pytest <TEMP>/aw-scratch/test_attack_browser.py -q -o asyncio_mode=auto` | **3 passed** |
| 7 | `uv run pytest <TEMP>/aw-scratch/test_clear_residue.py -q -o asyncio_mode=auto -s` | **1 passed**（`after_clear=0`；随后新行摘要 = `stale-output-after-clear`、`args=[]`） |
| 8 | 变异 M1–M16（见上节） | 两遍合计 13 红 3 存活（存活 = 第一遍 M3/M4 已修 + M16 观察 1） |

### 2. 全量 pytest（如实说明未完成的原因）

`uv run pytest -q` 全量（2000+ 用例）三次尝试均被本机执行器终止：前台运行数分钟后直接无输出 `exit 1`；后台运行输出重定向到文件后，进程在进度 **45%** 处被终止（文件无 `=== short test summary info ===`，也无我追加的 `exit=` 行）。故改为**可完成的最大分块**：#1（8 文件，208s 完成）+ 单文件计数 + pristine 对照。#1 覆盖本 change 全部影响面（对话区、抽屉、多 tab、重连、服务端静态资源、会话载荷）；`tests/agent`、`tests/benchmark` 与本 change 无共享面（`git status` 中改动文件不含任何 `agent/` 文件）。**全量计数需在更长时限/CI 环境补一次**；Round 1 报告遇到同一限制。

### 3. 环境性失败的 pristine 复核（`D:\code\asterwynd`，HEAD `3b48407`，`web.__file__`/`agent.__file__` 已确认指向 pristine）

| 命令（pristine，用 worktree 的 venv + `PYTHONPATH=D:\code\asterwynd`） | 结果 | 结论 |
|---|---|---|
| `python -m pytest tests/web_tests/test_server.py -q -k websocket_tool_events` | `1 failed`（`printf` 不存在 → `exit_code: 1`） | 与本 change 无关；worktree 同项同样失败 |
| `python -m pytest tests/web_tests/test_workflow_graph_ux_js.py -q` | `26 failed, 21 passed`（GBK 解码 node 输出） | 既有缺陷；与 `acceptance-evidence.md:49` 的「27 项（ux 26 + graph 1）」口径一致 |
| `python -m pytest tests/web_tests/test_server.py -q -k static_assets` | `1 failed`（`UnicodeDecodeError: 'gbk' codec…`） | **本 change 修好了它**（显式 `encoding="utf-8"`）；worktree 该项通过 |

### 4. CI 门禁

| 命令 | 结果 |
|---|---|
| `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` | `Totals: 29 passed, 0 failed (29 items)` |
| `$env:PYTHONPATH="."; uv run python scripts/check_openspec_artifacts.py --change harness-style-web-transcript` | **exit 1**，唯一错误 `review manifest missing`（预期：manifest 按纪律在归档 move 后生成；5.6 已标 closeout） |

### 5. 完整性与还原纪律

- 24 个受控文件在写报告前与最终冻结基线逐字节一致（`drift=0`），`git status --short` 与我冻结时一致：15 个 `M` + 4 个 `??`（change 目录、两个新测试、`tool_rows.js`），无多余改动、无提交。
- 仓库内变异只涉及 `web/static/chat.js` 与 `web/static/tool_rows.js`，每次还原后 sha256 复核：
  - `chat.js` 期望 `CEF0043D…` → 6 次还原全部 `match=True`；
  - `tool_rows.js` 期望（第一遍）`2A6DC745…` / （第二遍）`8030C951…` → 共 6 次还原全部 `match=True`。
- 仓库外资产：`%TEMP%\aw-scratch`（node/浏览器探针与变异脚本）、`%TEMP%\aw-backup2|3|5`（含三份前序审阅报告与前序代码快照）、`%TEMP%\aw-baseline-r4-hashes.txt` / `aw-baseline-r5-hashes.txt`（冻结基线）。

## 结论

**verdict: PASS。**

本 change 的实现质量高于本仓平均水平：折叠行的信息层级、失败可见性、配对顺序、共享渲染口径都做到了「有真实断言 + 有变异证据」的程度；调用方点名的 4 条 Round 1 发现（`TaskOutput` 多行失败漏判、历史摘要与投影互斥、截断提示可见性无断言、tasks 假勾选）经我逐条独立复核确认**不是纸面修复**。第一遍审阅我在攻击中新增发现并推动修掉的 3 条 MEDIUM（`TaskOutput` 扫描越过 `stdout:`、浏览器族失败文案缺失、裸 `Error:` 与文件内容不可区分）与 2 条 LOW（等待超时包装、失败首行前导空行）在最终修订上都有 node 用例且被我变异反证有牙齿；第一遍唯一的 MUST-FIX（`spec.md:139` 两条重绘清空路径零覆盖）已由两条新浏览器用例闭环，我用**分处独立变异**确认它们各只覆盖自己那条路径（M12/M13），不是互相冒充。

**归档前不需要再改任何代码或测试。** 归档时请按 `tasks.md` §5 的顺序执行 closeout（5.1 同步 spec → 5.3 归档 + 5.4 backlog 出队 → 5.6 checker → 5.7 报告 + manifest → 5.8 PR），并在 `tasks.md` 最终化（含归档 move）之后生成 review manifest（`workflow_state.py review-manifest --change harness-style-web-transcript --phase building --reviewer-run-id building-review-harness-style-web-transcript-20261003-r2`）。当前 `check_openspec_artifacts.py` 的 exit 1 是「未归档 + 无 manifest」的预期信号；残余可行的可选事项只有观察 1（为 `aria-controls` 补一条断言）。
