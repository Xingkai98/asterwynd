# Building Review: harness-style-web-transcript（Round 8：N1 竞态修复的极轻确认，终稿 PASS）

| 项 | 值 |
|---|---|
| change | `harness-style-web-transcript`（Web 对话区改为 harness 式 transcript：正文成文 + 工具执行单行折叠） |
| 分支 / worktree | `harness-style-web-transcript/2026-10-03` @ `D:\code\asterwynd-worktrees\harness-style-web-transcript` |
| 审阅对象 | **只回答 N1 是否关闭 + 有无新增红**：修复提交 `61891af`（父 `d85134e`）。r1–r5 的 change 主体不重审；R6 的三条 MUST-FIX 与 R7 的 PASS 结论见下「历史结论的现状」 |
| base / head | change 立项基线 `3b484076f10fa295ce05bb53a01ef53c56c2cc17`；上游合并 `8fb1dbe`；R6 三条 MUST-FIX 修复 `d85134e`；**审阅点 HEAD = `61891af`**，工作区干净（`git status --porcelain` 空） |
| reviewer run id | `building-review-harness-style-web-transcript-20261003-r8` |
| 审阅修订锚点（**与实现方声明逐字节一致**；`chat.js` 在本仓库是 CRLF，故其工作区哈希 ≠ git blob 哈希） | `web/static/tool_rows.js` `122ADC265B598D60DAB6EE7BD442F73E4C6FA9C8CCE0860EC9EF05709BB77DEF`（LF，= blob）· `tests/web_tests/test_transcript_view_browser.py` `1EFCF466FCA23B680F481A39F823049FFFD680B4C878356B279B325831AF5364`（LF，= blob）· `tests/web_tests/test_transcript_js.py` `87A7E4B1B32B5FD1BDCCCFF206D867378C1EC4BB1F84FBD879CBA091BA53F519`（LF，= blob，本提交未改）· `web/static/chat.js` 工作区 `5485DE26D84BD0260204EACA9926318A7D1869E9F67318514858DAB5BEFE7929`（CRLF 2367 行）/ blob `70D7A1E36D568E111CE77E65A26BDD2A4C7F272FF77956C502F61FD171929F83`（本提交未改）· `web/static/index.html`、`web/static/style.css` 本提交未改 |
| method | 极轻确认，**只验增量**：① 逐行读 `61891af` 的 diff（`tool_rows.js` +11/-0、1 条新浏览器用例 + `import asyncio`）；② 把我 R7 用来**发现** N1 的那条探针 H（延迟 0.6s 制造「展开→立刻收起→回取才到货」）原样重跑；③ 自己下一组变异（删掉补救调用）反证；④ 把 R6/R7 用过的 6 条探针（A/B/C/D/E/G）原样重跑，确认三条旧修复未被这次改动扰动；⑤ 官方套件：7 文件 + **全量 `tests/web_tests`**；⑥ 哈希完整性 |
| 关于本文件 | **覆盖写**。上一版是 r7（`PASS`，run id `…-r7`），已随 `61891af` 提交入库（该提交的 diff 里可见 `reviews/building-review.md` 173 行变更），R7 的完整证据可在该提交里查回。本文件是**终稿**：verdict 行是 r8 的结论；**写完不再改动**（manifest 按本文件字节哈希绑定）。 |
| 完整性纪律 | 变异按「断言 `count(OLD)==1` → 写入 → 跑裁判 → 按字节还原 → 复核 sha256」执行，`match=True`，收尾 `tool_rows.js` 回到 `122ADC26…`、`git status --porcelain` 为空。探针/变异器在 `%TEMP%\aw-r6\`；未触碰 `D:\code\asterwynd` 工作区。 |

## Verdict

**PASS**

**判据（全部由本会话独立取证）**：

1. **N1 已关闭**：新增 `rowCollapsed(row)`（`tool_rows.js:635-638`，读本行头按钮的 `aria-expanded`），并在 `loadFullText` 的 `.then` 写完全文后补一句 `if (rowCollapsed(row)) releaseFullText(doc, row);`（`:689`）。我 R7 用来发现该竞态的探针 H（路由 `await asyncio.sleep(0.6)` 后 fulfill ⇒ 展开 → 立刻收起 → 回取才到货）由 **RED 转 GREEN**：`body_hidden=True`、`dom_retains_full_text=False`、`dom_len=32`（只剩预览 + 提示）。**独立变异 R8-M1**（删掉 `:689`）→ 我的探针 H + 实现方新用例 `test_collapsing_while_the_fetch_is_in_flight_still_releases` 同时变红 ⇒ 补救有牙齿。
2. **R7 三条旧修复未被扰动**：本次改动只新增 1 个判据函数 + 1 处调用（`+11/-0`），`releaseFullText` 的早退条件、`spilled` 判定、`result = given !== '' ? given : preview` 均未动。我把 A/B/C/D/E/G 六条探针原样重跑，**全部与 R7 相同**（A：`state='error'` + 摘要含 `[Approval denied` + 展开体含正文；B：展开体含 `41 passed in 7.73s`；C：单行裸 `Error:` → `error`；D：`requests=['…/tool-result/t9']` 且展开体出现全文；E：`lineCount=2` 下裸 `Error:` 不误报；G：收起后 DOM 不含全文）。
3. **无新增红**：7 文件官方套件 **`227 passed`**（R7 为 226，+1 = 本次新增的竞态用例）；**全量 `tests/web_tests` = `45 failed / 476 passed / 8 skipped`**，45 条失败与 R7 及 pristine master 8f575c8 **逐条同名**（26 `test_workflow_graph_ux_js` + 1 `test_workflow_graph_js` + 9 `test_terminal_honesty_js` + 9 `test_multi_session`），passed 475 → 476（+1）⇒ **零新增红、零丢失绿**。
4. **折叠态量化承诺与「无残留 `.message.tool` 路径」仍成立**：本轮未改 `index.html`/`style.css`/`chat.js`，`VISIBLE_TEXT_BUDGET=1200` 与逐行摘要 ≤90 的断言原样在盘且在 227 项里全绿。
5. 唯一新发现是一条**纯注释的 NIT**（见 `## 非阻断残余` N-NIT）：`tool_rows.js:633` 多了一行重复的 `releaseFullText` JSDoc 落在 `rowCollapsed` 上方；不影响任何行为，**不构成 MUST-FIX**。

## N1 关闭验证（本轮唯一目标）

| 步骤 | 证据 |
|---|---|
| R7 发现（在 `d85134e` 上） | 探针 H：路由延迟 0.6s ⇒ 展开 → 立刻收起 → 到货后 `body_hidden=True` 但 `dom_retains_full_text=True`（213 字符）⇒ 判 LOW（`releaseFullText` 在 `.then` 之前被调用时 `__fullTextLoaded` 尚未置位而早退） |
| 修复 | `tool_rows.js:635-638`（`rowCollapsed`）+ `:689`（`if (rowCollapsed(row)) releaseFullText(doc, row);`，`:684-688` 注释说明为何需要）+ 新用例 `test_transcript_view_browser.py`（路由延后 0.6s，断言展开体**不含** `@@LATE-FULL@@`） |
| R8 复验（在 `61891af` 上） | 探针 H **GREEN**：`[H] body_hidden=True dom_retains_full_text=False dom_len=32`；6 条旧探针同 R7 全绿（合计 `91 passed`） |
| 我的独立变异（R8-M1） | 删 `:689` → 探针 H `1 failed` + `test_collapsing_while_the_fetch_is_in_flight_still_releases` `1 failed`（`2 failed, 27 passed`）；还原后 `tool_rows.js` = `122ADC26…`（`match=True`） |
| 关闭后语义自洽性（代码阅读） | 释放会把 `__fullTextLoaded=false`、`__previewOnly=true`、展开体放回「预览 + 提示」⇒ 再展开会**重新回取一次**（与 M2 的契约一致）；释放需要 `__previewText !== null`，而能走到 `loadFullText` 的行必然是 preview-only 行（`:722` 已存过预览），故补救不会误伤「非预览行」 |

## 历史结论的现状（供合入读者）

| 轮次 | 结论 | 现状（本修订上） |
|---|---|---|
| R6（`8fb1dbe`） | `CHANGES_REQUESTED`：3 条 MUST-FIX（短结果文本依据不回落 preview / 收起未释放全文 / 历史 loader 死接线） | 三条均于 `d85134e` 修复，R7 用独立变异 R7-M1/M2/M3 逐条反证关闭；本轮 A/B/C/D/E/G 复跑**未回归** |
| R7（`d85134e`） | `PASS`：3 条 MUST-FIX 关闭、无新增红；残余 1 条 LOW 竞态 N1 + 5 条口径/边界观察 | N1 于 `61891af` 关闭（本轮验证）；N2–N6 由实现方按「不阻断」处理（N2/N3 拟写入 PR 描述与 change 归档说明，N4/N5 承 R6 记录，N6 确认无线上风险） |
| R8（`61891af`） | **`PASS`** | 本文件 |

## 回归面与门禁（R8 实测）

| # | 命令 | 结果 |
|---|---|---|
| 1 | `uv run pytest tests/web_tests/test_transcript_js.py tests/web_tests/test_transcript_view_browser.py tests/web_tests/test_tool_result_expand.py tests/web_tests/test_server.py tests/web_tests/test_session.py tests/web_tests/test_workflow_graph_browser.py tests/web_tests/test_multi_session_browser.py -q` | **`227 passed`**（213.94s）——与实现方声称一致（R7 为 226） |
| 2 | `uv run pytest tests/web_tests -q -rf --tb=no` | **`45 failed, 476 passed, 8 skipped`**（310.75s）；失败集与 R7/pristine master 逐条同名 ⇒ 全是既有 GBK/Windows 环境问题（`UnicodeDecodeError: 'gbk' codec…` + Windows 路径语义） |
| 3 | R6/R7 的 6 条探针 + N1 探针 H（`test_r6_probe.py` A–E、`test_r6_probe2.py` G、`test_r7_probe_h.py` H） | **`91 passed`**（A/B/C/D/E/G 与 R7 同；H 由 RED 转 GREEN） |
| 4 | 变异 R8-M1（删 `:689`） | 探针 H + 实现方新用例变红；按字节还原 `match=True` |
| 5 | 锚点核对 | `tool_rows.js 122ADC26…`（= 实现方声明）、`test_transcript_view_browser.py 1EFCF466…`、`test_transcript_js.py 87A7E4B1…`、`chat.js` 工作区 `5485DE26…`；`git status --porcelain` 空 |
| 6 | 门禁（本提交未改 spec/归档文档，R6/R7 结论沿用） | `openspec validate --all --strict` = `28 passed, 0 failed`；`check_openspec_artifacts.py` = `OpenSpec artifact checks passed` |

## 非阻断残余

| # | 位置 | 现象 | 为什么不阻断 | 处置 |
|---|---|---|---|---|
| N-NIT（新，纯注释） | `web/static/tool_rows.js:633` | 多了一行重复的 `releaseFullText` JSDoc，落在 `rowCollapsed` 上方（`:634` 才是 `rowCollapsed` 自己的注释）；新函数因此带了两行注释，其中第一行语义不符 | 零行为影响、零断言影响；`d85134e` 之前该 JSDoc 只有一份 | 建议顺手删 `:633` 一行（**不要求合入前处理**） |
| N2（观察，承 R7） | `web/static/chat.js:824` + `tool_rows.js:754-760` | 历史 spill 行取回全文后，行尾 meta 仍显示**预览**的规模（探针 D 复现：`2.1k 字符 · 2 行` vs 全文 22 字符） | 行体是正确的全文，只是规模标签偏小；服务端历史投影本来不给真实总数 | 实现方确认：写入 PR 描述与 change 归档说明，后续单独处理 |
| N3（观察，承 R7） | `tool_rows.js:733-736` + `:650-653` | 无 `tool_call_id` 的历史 spill 行，展开体提示「展开时按需回取」但永远取不回来 | 需「spill 形态 + 无 id」同时成立；内容如实展示 | 同上（记入 PR/归档说明） |
| N4（承 R6-L2） | `tool_rows.js:334-343` | 截断预览兜底里 `timed_out`/`oom_killed` 两支不可达（信封首字段恒为 `exit_code`）；当前两后端超时都用 `exit_code=-1`，线上不可达 | 仅在未来新增后端/改字段序时才有风险 | 承 R6 记录，未改 |
| N5（承 R6-L3/L4/L5/L6/L7/L8） | `docs/architecture.md:91`、`openspec/specs/web-ui/spec.md:1431,141`、归档 delta `:7/12/13`、`tool_rows.js:680-684,655-666,705` | 文档口径与极端边界，与三条 MUST-FIX 无关 | 均不影响验收 | 见 `d85134e` 入库的 R6 报告「可选（LOW）」表 |
| N6（承 R7） | `web/static/index.html:177,181` | 静态资源版本号仍是 `?v=2`/`?v=26` | 这些 URL 从未在任何已部署环境发布（分支未合入 master，master 上无 `tool_rows.js`） | 实现方确认无线上风险 |

## Mutation Experiments

变异器：`%TEMP%\aw-r6\mutate_r6.py`（读原字节 → 断言 `count(OLD)==1` → 写入 → 跑裁判 → 按字节还原 → 复核 sha256）。`tool_rows.js` 为纯 LF。

| # | 变异 | 裁判命令 | 结果 |
|---|---|---|---|
| R8-M1 | `tool_rows.js:689` 删 `if (rowCollapsed(row)) releaseFullText(doc, row);` | 我的探针 H；`-k collapsing_while_the_fetch` | **RED**：探针 H `1 failed`（DOM 保留 213 字符全文）+ 实现方新用例 `1 failed`；还原 `122ADC26…` `match=True` |

（R6/R7 的变异记录 M1–M4、R7-M1–M4 见 git 历史：`d85134e` 与 `61891af` 两个提交里的历史版报告。）

## 未验证项 / 残余风险

1. **未跑全量 `uv run pytest -q`**（本机限制同 r2/r6/r7）。`61891af` 只改 `tool_rows.js`（+11 行）与 1 个测试文件，`chat.js`/`index.html`/`style.css`/`agent/`/`web/*.py` 未动，影响面收敛。
2. **未做真实 LLM 端到端**；竞态用例依赖人为延迟（0.6s）构造在途窗口（真实 artifact 读盘通常更快，但窗口真实存在）。
3. N2–N6 均未在本次修复，属实现方按「不阻断」显式接受的观察项（N2/N3 将写入 PR 描述与 change 归档说明）。
4. 本地 `--check-archived` 仍是 CRLF 假阳性（R6 已复算证明：69 份 manifest 的 report_hash/spec_hash 与 LF 归一化字节 69/69 命中）。**本报告改写后本 change 的 manifest 会漂移**，需按下方指示、在本文件冻结后重生成。

## 结论

**verdict: PASS。合入前不需要再改任何代码。** R7 的唯一非阻断残余 N1（回取在途时收起仍把全文留在隐藏展开体）已在 `61891af` 关闭：我的探针 H 由 RED 转 GREEN，且**我自己下的变异 R8-M1**（删掉 `:689` 的补救）会让探针 H 与实现方新用例同时变红。这次改动只新增 1 个判据函数与 1 处调用，R7 已确认的三条关闭状态经 6 条探针复跑**未回归**；折叠态量化断言与「无残留 `.message.tool` 路径」继续成立。回归面 `227 passed`、全量 `45 failed / 476 passed / 8 skipped`（失败集与 R7/pristine master 逐条同名），**零新增红**。新发现只有一条纯注释 NIT（`tool_rows.js:633` 重复 JSDoc），不影响行为，不构成 MUST-FIX。

manifest 生成（**由实现方在本报告冻结后执行；报告写完后不再改动**）：`uv run python scripts/workflow_state.py review-manifest --change harness-style-web-transcript --phase building --reviewer-run-id building-review-harness-style-web-transcript-20261003-r8`。注意本报告是 **LF** 字节（仓库 `core.autocrlf=true` 会把签出文件物化成 CRLF，而 manifest 的 `report_hash` 按 LF 字节校验；本 change 的报告/`specs/` delta/`tasks.md` 均为签出后写入的 LF 文件，重生成后应与 CI 一致）。
