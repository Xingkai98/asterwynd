# Building Review: harness-style-web-transcript（Round 7：R6 三条 MUST-FIX 的聚焦复验，终稿 PASS）

| 项 | 值 |
|---|---|
| change | `harness-style-web-transcript`（Web 对话区改为 harness 式 transcript：正文成文 + 工具执行单行折叠） |
| 分支 / worktree | `harness-style-web-transcript/2026-10-03` @ `D:\code\asterwynd-worktrees\harness-style-web-transcript` |
| 审阅对象 | **只验 R6 三条 MUST-FIX 是否关闭 + 有无新增红**：修复提交 `d85134e`（父 `8fb1dbe`）。r1–r5 的 change 主体不重审；R6 的增量结论见下「R6 三条 MUST-FIX 的关闭验证」与「非阻断残余」 |
| base / head | change 立项基线 `3b484076f10fa295ce05bb53a01ef53c56c2cc17`；上游合并 `8fb1dbe`（merge of `f4afae1` + `8f575c8`）；**审阅点 HEAD = `d85134e7b6539c932ac3425068ca596ca72463a8`**，工作区干净（`git status --porcelain` 空） |
| reviewer run id | `building-review-harness-style-web-transcript-20261003-r7` |
| 审阅修订锚点（**全部与实现方冻结声明逐字节一致**；`chat.js` 在本仓库是 CRLF，故其工作区哈希 ≠ git blob 哈希） | `web/static/tool_rows.js` `52E3F2B84D28EB5F169CD91A72CD304B4960C5D314AEFBFEC0F3DB060DB9253E`（LF，= blob）· `web/static/chat.js` 工作区 `5485DE26D84BD0260204EACA9926318A7D1869E9F67318514858DAB5BEFE7929`（CRLF 2367 行）/ blob `70D7A1E36D568E111CE77E65A26BDD2A4C7F272FF77956C502F61FD171929F83` · `tests/web_tests/test_transcript_js.py` `87A7E4B1B32B5FD1BDCCCFF206D867378C1EC4BB1F84FBD879CBA091BA53F519`（LF，= blob）· `tests/web_tests/test_transcript_view_browser.py` `77D86D3593B5CA4C393563BA25D1555A270F40A8697B0F4C70D0CF6C14644567`（LF，= blob）· `web/static/index.html` 本提交未改（仍是 `tool_rows.js?v=2` / `chat.js?v=26`） |
| method | 零记忆聚焦复验，**不采信修复说明**：① 逐行读 `d85134e` 的实现 diff（`tool_rows.js` +54/-12、`chat.js` 注释）与 6 条新用例；② 把 R6 用过的 **6 条仓库外 Playwright 探针（A/B/C/D/E/G）原样重跑**（连同 24 条既有 + 3 条新浏览器用例）；③ 我自己再下 **4 组仓库内变异（R7-M1–M4）**，其中 M4 专门打 `isSpilledPreview` 的尾部锚定；④ 17 组只读 node 边界探针打 `isSpilledPreview` 的误判面；⑤ 1 条新探针 H 打「回取在途时收起」的残余竞态；⑥ 官方套件：7 文件、**全量 `tests/web_tests`**、门禁与哈希完整性 |
| 关于本文件 | **覆盖写**。上一版是 r6（`CHANGES_REQUESTED`，sha256 `DAF0017EE689F3DFEF107B73A934E26B764DD7F98DA522F97EB51009DD5C6663`），已随 `d85134e` 提交入库，R6 的三条 MUST-FIX 与 8 条可选的完整证据可在该提交里查回。本文件是**终稿**：verdict 行是 r7 的结论。 |
| 完整性纪律 | 4 组变异全部「断言 `count(OLD)==1` → 写入 → 跑裁判 → 按字节还原 → 复核 sha256」，4/4 `match=True`，收尾 `tool_rows.js` 回到 `52E3F2B8…`、`git status --porcelain` 为空。所有探针/变异器在 `%TEMP%\aw-r6\`；未触碰 `D:\code\asterwynd` 工作区。 |

## Verdict

**PASS**

**判据（全部由本会话独立取证）**：

1. **R6-M1（HIGH）已关闭**：`tool_rows.js:704-705` 的文本依据改为一律回落 preview（`given !== '' ? given : preview`），`previewOnly` 语义保持「要不要回取」。我的 R6 探针 A/B/C 由红转绿（短结果审批拒绝 → `state='error'` + 摘要含 `[Approval denied` + 展开体含正文；成功短结果展开体含 `41 passed in 7.73s`；单行裸 `Error:` → `error`）。**独立变异 R7-M1**（把回落改回只在 `collapsed===true` 时生效）→ 我的 3 条探针 + 实现方新用例 `test_short_result_without_a_result_field_is_rendered_and_judged` 同时变红。
2. **R6-M2（MEDIUM）已关闭**：`tool_rows.js:613-628` 的头按钮 handler 分「收起→`releaseFullText`（`:634-643`）/ 展开→`loadFullText`」，收起把展开体放回「预览 + 提示」、`__fullTextLoaded=false`、`__previewOnly=true`，再展开重新回取。我的 R6 探针 G 由红转绿（收起后 DOM 不再含全文，只剩 31 字符的预览+提示）。**独立变异 R7-M2**（删掉 `releaseFullText(doc, row)` 调用）→ 探针 G + `test_collapsing_releases_the_fetched_full_text` 同时变红。
3. **R6-M3（MEDIUM）已关闭**：`tool_rows.js:44-47` 新增 `isSpilledPreview`（尾部锚定，与后端 `agent/memory/tool_result_policy.py::is_spilled_preview` 同口径）→ `:709-710` 的 `spilled` 让历史 spill 预览也走 preview-only，`:760` 在只有预览时把 meta 前置「预览 」，`:722` 记下 `__previewText` 供收起放回。我的 R6 探针 D 由红转绿（`requests=['…/tool-result/t9']`，展开体出现全文）。**独立变异 R7-M3**（`var spilled = false;`）→ 探针 D + `test_spilled_history_row_fetches_the_full_text_on_expand` 同时变红。
4. **尾部锚定不会把正文里的 `[truncated` 误判**：17 组只读 node 边界探针 **17/17 符合预期**（末尾标记带 ref/不带 ref/尾随空白 → true；出现在行中、行首、未闭合、后接文本、未知后缀、ref 含空格、非字符串 → false）。**独立变异 R7-M4**（正则退化成裸子串 `/\[truncated/`）→ node 用例 `test_spilled_preview_is_recognised_by_the_trailing_marker` 变红（反例被锁死）。
5. **无新增红**：7 文件官方套件 **`226 passed`**（R6 为 220，+6 = 3 条浏览器 + 3 条 node 新用例）；**全量 `tests/web_tests` = `45 failed / 475 passed / 8 skipped`**，失败集与 R6 及 pristine master 逐条同名（26 `test_workflow_graph_ux_js` + 1 `test_workflow_graph_js` + 9 `test_terminal_honesty_js` + 9 `test_multi_session`），passed 469 → 475（+6）⇒ **零新增红、零丢失绿**。
6. **折叠态量化承诺与「无旧渲染路径」仍成立**：`VISIBLE_TEXT_BUDGET=1200` / `SUMMARY_CHAR_LIMIT=90` 与逐行断言原样在盘（`test_transcript_view_browser.py:37-38,215,224`），226 项套件全绿；全仓 `.js/.html` 无 `.message.tool` / `tool-result-toggle` / `tool-result-controls` 产出方；`index.html` 与 `style.css` 本提交未改。
7. 残余项只有 1 条**不阻断**的窄竞态（探针 H：回取**在途**时收起，全文仍留在隐藏 DOM 里，无显示错误、再次展开行为正确）与若干不影响验收的观察，见 `## 非阻断残余`。

## R6 三条 MUST-FIX 的关闭验证

| # | 修复位置（R7） | 我的独立变异（裁判命令 → 结果） | 我的探针（R6 原样重跑） | 判定 |
|---|---|---|---|---|
| R6-M1 | `tool_rows.js:700-705`（`var preview = …; var result = given !== '' ? given : preview;`） | **R7-M1** 改回「只在 `collapsed===true` 回落」→ 探针 A/B/C `3 failed`、`test_short_result_without_a_result_field_is_rendered_and_judged` `1 failed` | A `state='error'`/摘要 `[Approval denied…]`/展开体含正文；B 展开体含 `41 passed in 7.73s`；C 单行裸 `Error:` → `error` | **closed** |
| R6-M2 | `tool_rows.js:613-628`（handler 两支）+ `:634-643`（`releaseFullText`）+ `:670-678`（重算前先存 `__previewText` 再回填） | **R7-M2** 删 `releaseFullText(doc, row);` → 探针 G `1 failed` + 实现方用例 `1 failed`（`test_collapsing_releases_the_fetched_full_text`） | G：`fetched=1` → 收起后 `body_hidden=True`、`dom_retains_full_text=False`、`dom_len=31` | **closed** |
| R6-M3 | `tool_rows.js:44-47`（`SPILLED_SUFFIX_RE` + `isSpilledPreview`，`:782` 导出）+ `:709-710`（`spilled` → `previewOnly`）+ `:760`（meta「预览 」）+ `chat.js:801-806,823-832`（JSDoc 与接线注释订正） | **R7-M3** `var spilled = false;` → 探针 D `1 failed` + 实现方用例 `1 failed`；**R7-M4** 裸子串正则 → node 反例用例 `1 failed` | D：`requests=['http://127.0.0.1:…/api/sessions/cc0051bc228c/tool-result/t9']`，展开体 `结果\n@@HISTORY-FULL@@` | **closed** |

R6 点名的零覆盖项也已补齐（我复验有牙齿）：`test_transcript_js.py:359`（`lineCount:2`→`ok`、`1`→`error`、无 hint 回退、多行文本→`ok`）、`:373`（截断信封认 `exit 1`、`exit_code:0` 不误报、同名字段出现在 200 字符之后不误报）、`:391`（尾部锚定反例）。R6 的变异 **M2**（去掉 hint 全绿）在本修订上不再成立——该 hint 现在有 4 条断言钉住。

## 回归面与门禁（R7 实测）

| # | 命令 | 结果 |
|---|---|---|
| 1 | `uv run pytest tests/web_tests/test_transcript_js.py tests/web_tests/test_transcript_view_browser.py tests/web_tests/test_tool_result_expand.py tests/web_tests/test_server.py tests/web_tests/test_session.py tests/web_tests/test_workflow_graph_browser.py tests/web_tests/test_multi_session_browser.py -q` | **`226 passed`**（188.04s）——与实现方声称一致（R6 为 220） |
| 2 | `uv run pytest tests/web_tests -q -rf --tb=no` | **`45 failed, 475 passed, 8 skipped`**（274.31s）；失败集与 R6/pristine master 逐条同名 ⇒ 全是既有 GBK/Windows 环境问题（`UnicodeDecodeError: 'gbk' codec…` + Windows 路径语义） |
| 3 | R6 的 6 条仓库外探针原样重跑（`test_r6_probe.py` A–E + `test_r6_probe2.py` G） | **`60 passed`**（A/B/C/D/E/G 全绿；R6 时其中 A/B/C/D/G 为 RED） |
| 4 | 只读 node 边界探针（17 组 `isSpilledPreview` 载荷） | **`mismatches = 0/17`** |
| 5 | 变异 R7-M1–M4（见下） | 4/4 命中的用例变红，4/4 按字节还原 `match=True` |
| 6 | `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`（本提交未改 spec，R6 复跑结论） | `Totals: 28 passed, 0 failed` |
| 7 | `PYTHONPATH=. uv run python scripts/check_openspec_artifacts.py` | `OpenSpec artifact checks passed`（exit 0） |
| 8 | 锚点核对 | `tool_rows.js 52E3F2B8…`、`chat.js 5485DE26…`（工作区 CRLF）、`test_transcript_js.py 87A7E4B1…`、`test_transcript_view_browser.py 77D86D35…` 与实现方冻结声明**逐字节一致**；`git status --porcelain` 空 |

## 非阻断残余（不要求合入前处理）

| # | 位置 | 现象 / 复现 | 为什么不阻断 | 建议 |
|---|---|---|---|---|
| N1（LOW，窄竞态） | `web/static/tool_rows.js:634-635`（`releaseFullText` 的 `if (!row.__fullTextLoaded …) return;`）与 `:656-679`（`.then` 无条件写入） | **回取在途时收起**：展开（发出请求）→ 立刻收起 → 请求落地后 `.then` 仍把全文写进**隐藏**的展开体。探针 H（路由延迟 0.6s 后 fulfill）：`body_hidden=True` 但 `dom_retains_full_text=True`（213 字符）。确定性路径（等取回后再收起）已由 M2 修好，探针 G 绿 | 无任何显示错误：行是收起的，再次展开显示全文且不重复请求（`__fullTextLoaded` 已置位）；常驻量受 `BODY_LIMIT`(200k/行) 约束 | 在 `.then` 里按当前 `aria-expanded` 判断：若此刻是收起态，写完就直接 `releaseFullText(doc, row)`（或干脆不写 body） |
| N2（观察） | `web/static/chat.js:824`（历史 `display` 只有预览的 `char_count`）+ `tool_rows.js:754-760` | 历史 spill 行展开并取回全文后，行尾 meta 仍显示**预览**的规模（探针 D：取回后 `2.1k 字符 · 2 行`，而全文只有 22 字符）。收起态的「预览 」前缀是对的（实现方用例已断言），前缀在取回后消失 | 服务端历史投影本来就不给真实总数；行体内容是正确的全文，只有规模标签偏小 | 若在意：取回成功后用 `String(text)` 重算 `char_count/line_count`（`updateToolRow` 已支持 `display` 缺省回落） |
| N3（观察） | `tool_rows.js:733-736`（previewOnly ⇒ 恒加 `PREVIEW_ONLY_NOTE`）+ `:650-653`（无 loader 时早退） | 历史 spill 行若**没有** `tool_call_id`（老载荷），展开体写「尚未取回全文，展开时按需回取」，但这条行永远取不回来（`__loadFullText` 未设） | 需要「spill 形态 + 无 id」两个条件同时成立；内容本身如实展示（预览 + 尾部 ref 标记） | 无 loader 时改用另一句提示（如「仅预览，全文不可回取」） |
| N4（承 R6-L2） | `tool_rows.js:334-343` | 截断预览兜底里 `timed_out` / `oom_killed` 两支仍不可达（信封首字段恒为 `exit_code`，`exit_code===0` 时提前 `return null`）。当前两后端超时都用 `exit_code=-1`，故线上不可达 | 只在未来新增后端/改字段序时才可能漏报；R6 已按 LOW 记录 | 把这两支提到提前返回之前，或删掉并注明「截断态只信 exit_code」 |
| N5（承 R6-L3/L4/L5/L6/L7/L8） | `docs/architecture.md:91`、`openspec/specs/web-ui/spec.md:1431,141`、归档 delta `:7/12/13`、`tool_rows.js:680-684`（`.catch` 不置 loaded）、`:655-666,705`（`content:""` 且 `missing:false` 时仍显示「尚未取回」提示） | 与 R6 报告逐条相同，本提交未触及 | 均为文档口径/极端边界，与本轮三条 MUST-FIX 无关 | 见 `d85134e` 里入库的 R6 报告「可选（LOW）」表 |
| N6（观察，非缺陷） | `web/static/index.html:177,181` | 本提交又改了 `tool_rows.js`/`chat.js`，但版本查询仍是 `?v=2` / `?v=26`（合并提交刚 bump 过） | 这两个 URL 从未在任何已部署环境发布（分支尚未合入 master，master 上甚至没有 `tool_rows.js`），不存在线上陈旧缓存 | 合入时若要保守，可在合并后的提交里统一再 bump 一次（v3/v27），顺手清掉本地验证者可能残留的旧副本 |

## Mutation Experiments（R7，全部由本人独立执行）

变异器：`%TEMP%\aw-r6\mutate_r6.py`（读原字节 → 断言 `count(OLD)==1` → 写入 → 跑裁判 → 按字节还原 → 复核 sha256）。`tool_rows.js` 为纯 LF，模式用 `\n`。

| # | 变异 | 裁判命令 | 结果 |
|---|---|---|---|
| R7-M1 | `tool_rows.js:705` 文本依据改回「仅在 `collapsed===true` 时回落 preview」 | 我的探针 A/B/C；实现方新用例 | **RED**：探针 `3 failed`；`test_short_result_without_a_result_field_is_rendered_and_judged` `1 failed` |
| R7-M2 | `tool_rows.js:621` 删 `releaseFullText(doc, row);` | 我的探针 G；`-k collapsing_releases` | **RED**：探针 G `1 failed`（DOM 保留全文）；实现方用例 `1 failed` |
| R7-M3 | `tool_rows.js:709` `var spilled = isSpilledPreview(result);` → `false` | 我的探针 D；`-k spilled_history_row` | **RED**：探针 D `1 failed`（`requests=[]`）；实现方用例 `1 failed` |
| R7-M4 | `tool_rows.js:44` 正则 → `/\[truncated/`（裸子串） | `-k spilled`（node） | **RED**：`test_spilled_preview_is_recognised_by_the_trailing_marker` `1 failed`（行内/行首反例被捕获） |

## 未验证项 / 残余风险

1. **未跑全量 `uv run pytest -q`**（本机限制同 r2/r6）。本轮覆盖 `tests/web_tests` 全量 + 6 条独立浏览器探针 + 1 条竞态探针；`d85134e` 只改 `tool_rows.js`/`chat.js`/2 个测试文件 + 报告，`agent/`、`web/*.py`、`style.css`、`index.html` 未改，影响面收敛。
2. **未做真实 LLM 端到端**：判定输入取自后端真实发射形状（`agent/loop.py:1073-1081`、`tests/web_tests/test_server.py:1290-1293`）。
3. **N1 的竞态只在人为延迟（0.6s）下复现**；真实 artifact 读盘通常更快，但窗口存在。
4. **N4 的线上可达性**依赖后端字段序（`agent/tools/sandbox/base.py:99-118`）与「超时用 `exit_code=-1`」两个前提，改动这两处需重新评估。
5. `--check-archived` 在本地仍是 CRLF 假阳性（R6 已复算证明：69 份 manifest 的 report_hash/spec_hash 与 LF 归一化字节 69/69 命中）。**报告改写后本 change 的 manifest 必然漂移**，需按下方指示重生成。

## 结论

**verdict: PASS。合入前不需要再改任何代码。** R6 的 3 条 MUST-FIX 全部关闭，且每条都有**我自己下的变异**反证（R7-M1/M2/M3），不是接受实现方的自述；`isSpilledPreview` 的尾部锚定经 17 组边界载荷 + 裸子串变异（R7-M4）确认不会被正文里的 `[truncated` 误判；R6 点名的两处零覆盖（`line_count` hint、截断 JSON 信封）已补齐并有断言。回归面 `226 passed`、全量 `45 failed / 475 passed / 8 skipped`（失败集与 R6 及 pristine master 逐条同名），**零新增红**；折叠态量化承诺与「无残留 `.message.tool` 路径」在本修订上继续成立。残余只有 1 条无显示后果的窄竞态（N1）与 5 条口径/边界观察，均不阻断。

manifest 生成（**由实现方在报告冻结后执行，本报告不再改动**）：`uv run python scripts/workflow_state.py review-manifest --change harness-style-web-transcript --phase building --reviewer-run-id building-review-harness-style-web-transcript-20261003-r7`。注意本报告是 **LF** 字节（仓库 `core.autocrlf=true` 会把签出文件物化成 CRLF，而 manifest 的 `report_hash` 按 LF 字节校验；本 change 的报告/`specs/` delta/`tasks.md` 都在签出后写入，当前均为 LF，重生成后应与 CI 一致）。
