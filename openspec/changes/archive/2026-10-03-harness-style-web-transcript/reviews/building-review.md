# Building Review: harness-style-web-transcript（Round 6：合入前合并 origin/master 的增量复验）

| 项 | 值 |
|---|---|
| change | `harness-style-web-transcript`（Web 对话区改为 harness 式 transcript：正文成文 + 工具执行单行折叠） |
| 分支 / worktree | `harness-style-web-transcript/2026-10-03` @ `D:\code\asterwynd-worktrees\harness-style-web-transcript` |
| 审阅对象 | **只审合并提交** `8fb1dbe`（parents `f4afae1` + `origin/master` `8f575c8`）的**冲突解决增量**及其回归。r1–r5 已 PASS 的 change 主体不重审，但本轮在其上复跑了全部官方套件 |
| base / head | change 立项基线 `3b484076f10fa295ce05bb53a01ef53c56c2cc17`；合并带入的上游 = `8f575c8ff5eb376e0f032b76764e3766f83587df`（已确认是 HEAD 祖先）；**审阅点 HEAD = `8fb1dbe5bfd6e3db9edb8350d0a5643d472d5580`**，工作区干净（`git status --porcelain` 空） |
| reviewer run id | `building-review-harness-style-web-transcript-20261003-r6` |
| 审阅修订锚点（HEAD 工作区字节 sha256；本仓库 CRLF/LF 混合，`crlf>0` 者另注 git blob 的 LF 哈希） | `web/static/tool_rows.js` `90823CE489105D5F445CD33EC3A43C6823101B764797FE3B8DAAD4B906738D82`（LF）· `web/static/chat.js` 工作区 `50B4E320B1D2E1B9FEA57BCF4FC78B2458F0C3B3CE95333771CB78BDF2111E44` / blob `4E8C614F3828060BDBA3BB07B0E4D4AAB6B6E5E82CACDFC7DF90E207972A3CAB`（**worktree 是 CRLF**）· `web/static/index.html` 工作区 `272A53C112290BB6ECEA72641367E26D015E6BCD4570260C576E2691F866EA78` / blob `6BFFDF9BF9F04CE126DC20972D65E8CC1BFEA00DC806EED9BF497FEEF7D596C5` · `openspec/specs/web-ui/spec.md` 工作区 `A1CA7095D999E1BE9C2DF852F193109CDC2AB2F5F935DD6407BABD0DA3BB3D14` / blob `E0A35C3564559C363B1BFF0662C884B74D55C89B9B12F53F144C3D40C76FE93B` · `docs/architecture.md` 工作区 `C000DF991CF2AA98E758822A6AF11E6C2A247CE918308385167E5CA1B164475E` / blob `D71E953C1BC3AFEECE2B3975E8AC406F1025438FB01B95C2A540E73C6300F51E` · `tests/web_tests/test_transcript_view_browser.py` `F178CBF776F6EC2C360753E49801D4C978662E8B408D5A44D130BB20270965A1`（LF）· `tests/web_tests/test_transcript_js.py` `1A1AA7C1BC38DC05842C43F1FB0F81A1803A0337934AD3BD7E44D68BF9491D16`（LF，合并未改）· `tests/web_tests/test_server.py` 工作区 `BAE266EAA66187810917DC06E9427CDF7862F291DF8E281C00B9553A0418705A` / blob `A793797DF1CAB98A8A607F77699D25934C4A86371C9BFA8D48EC391A6BC87344` · `agent/loop.py` 工作区 `137241F7E828EB533D7F4A2EDACE52EBF2BE5D798CFBA7FD5D8FF5633E83844F` / blob `8B1E8E5F3C66134CC154EC48906C91EA9CE7168BAC3BB9B62E65D9AA86EA992E` · `agent/tool_result_display.py` 工作区 `1576247375EB06062F2E34B4DA7ECC8960EA63B54682AEA5F880FAA638C3A016` / blob `AA3BE784B59C1C79D13E9C4106BC4ECAEFA2E00274F5A49B910F3C5E30E17450` · `web/session.py` 工作区 `9BD2D453831E744B684C7881CBFB20BC643617D2EA9D1D2C06625848D9C3DEEC` / blob `6EC46D48D2EA39CAEF96682F2E22B58733384E48C55A58739AAB904E2C72D1EF` · `tasks.md` `2165A1903D8AF8FB9FA0F975179F712ED9A76CA7C02ECEE5BB0BC1A8379725A3` · spec delta `2514ED5BF2A5D61E9E3C11D1F0BF758C844E21490C0A8AE637DBEB7398FEA4D3` |
| method | **零记忆独立审阅**，不采信文档自述：① `git show 8fb1dbe` 逐行读三处冲突解决（`web/static/chat.js`、`openspec/specs/web-ui/spec.md`、`docs/architecture.md`）与 3 条新增浏览器用例；② 反查后端真实事件形状（`agent/loop.py:1073-1081`、`agent/tool_result_display.py:41-61`、`web/session.py:62-94,929-978`）与 `tests/web_tests/test_server.py:1288-1293` 的端到端断言；③ 官方套件：调用方点名的 7 文件 `220 passed`、**全量 `tests/web_tests`**（`45 failed / 469 passed / 8 skipped`）并在 **pristine master 8f575c8 的 `git archive` 导出树**上复现同一批失败；④ **仓库外** 7 条 Playwright 探针（A–E、G，`exec` 复用官方 fixture，零复制）+ 1 份只读 node 探针；⑤ **4 组仓库内变异**（M1–M4，按字节还原并逐次复核 sha256）；⑥ 门禁：`openspec validate --all --strict`、`check_openspec_artifacts.py`（含 `--check-archived`）并复算 69 份归档 manifest 的哈希口径。 |
| 关于本文件 | **覆盖写**。本路径原为 r2 终稿 PASS 报告（216 行，sha256 `8FFCC8CE…`，已绑定 `building-review-manifest.json`）。r2 对 `f4afae1` 的结论仍然成立（本轮 220 项复跑全绿）；本文件只对**合并增量**追加结论，故 verdict 行是 r6 的结论。 |
| 完整性纪律 | 仓库内只改过 `web/static/tool_rows.js`（M1–M4），每次运行前 `raw.count(OLD) == 1` 断言、运行后按字节还原并复核 sha256（4/4 `match=True`）；收尾 `git status --porcelain` 为空、HEAD 仍是 `8fb1dbe`、`tool_rows.js 90823CE4…` / `chat.js 50B4E320…` 与冻结基线一致。所有探针与变异脚本都在 `%TEMP%\aw-r6\`，pristine 对照用 `%TEMP%\aw-master-8f575c8\`（`git archive` 导出，未触碰 `D:\code\asterwynd` 工作区）。 |

## Verdict

**CHANGES_REQUESTED**

**判据**：合并增量本身的方向正确（接住了 master 的 D12「preview + 按 id 回取」），但**只在 `display.collapsed === true` 这一支上接住**；线上最常见的短结果（`collapsed === false`）落回「空正文 + 失败不可见」——正是 `tasks.md:55`（§11.2）自己写下的失败模式，必须修完再合入。另有两处 master 能力/规格条款在合并中未落地（收起释放缓存、历史行按需回取）。共 **3 条 MUST-FIX（1 HIGH + 2 MEDIUM）**，另有 8 条可选与 4 条非缺陷观察。

## 增量逐项验证（调用方点名的 6 项）

| # | 项 | 结论 | 证据 |
|---|---|---|---|
| 1a | 事件不带 `result` 时落到 `display.preview` | **仅 collapsed=true 成立；collapsed=false 不成立（MUST-FIX-1）** | `tool_rows.js:673-674`；`chat.js:1092-1095` 的注释声称「没有就给空串让 `updateToolRow` 落到 preview 上」，但 `updateToolRow` 只在 `display.collapsed === true` 时回落。真实形状见 `agent/loop.py:1073-1081`（事件无 `result` 键）与 `tests/web_tests/test_server.py:1290-1293`（`"result" not in data`、`collapsed is False`）。探针 A/B/C 实测：`[Approval denied…]` 短结果 → `data-state='ok'`、展开体只有「参数」段；成功短结果展开体同样为空 |
| 1b | 失败仍可见（行首前缀） | **collapsed=true 成立 / collapsed=false 不成立（同上）** | 前缀集本身齐备且有 node 用例（`test_transcript_js.py:222-241`）；但 collapsed=false 时判定输入是空串 ⇒ `summarizeToolResult` 直接返回 `ok` |
| 1c | 被截断的 Bash JSON 信封仍能判出退出码 | **成立，且变异有牙齿** | `tool_rows.js:330-343`；变异 **M1**（删掉兜底）→ `test_preview_only_result_still_flags_the_failure` **RED**（`1 failed, 80 passed`）。附带发现兜底里 `timed_out`/`oom_killed` 两支不可达（可选 L2） |
| 1d | 裸 `Error:` 单行判据改用 `display.line_count` | **实现正确，但零用例覆盖（可选 L1）** | `tool_rows.js:409-414`；变异 **M2**（去掉 hint）→ 仓库套件 **`81 passed`（存活变异）**，只有我的仓库外探针 E 变红 ⇒ hint 有真实效果但无仓库断言 |
| 2a | 展开取到 → 展开体变全文且**重算**行状态 | **成立** | `tool_rows.js:612`（点击回落）+ `:623-649`（`loadFullText` 成功后重跑 `updateToolRow`）；`test_transcript_view_browser.py:743-775` |
| 2b | 取不到（`missing`/网络错）→ 写「全文不可用」，不拿预览冒充 | **成立** | `tool_rows.js:632-639`（`FULL_TEXT_UNAVAILABLE`）+ `:650-654`（catch）；`chat.js:1115-1131`（`resp.ok` 与非 `missing===false` 都返回 null）；`test_transcript_view_browser.py:777-803` |
| 2c | 只取一次（`__fullTextLoaded`/`__fullTextLoading` 守卫） | **成立** | `tool_rows.js:624`；点击处理器只切 `hidden`（`:604-613`），不重复触发；`.catch` 分支不置 `__fullTextLoaded`（可选 L7，当前 loader 不会 reject） |
| 2d | 变异：点击里去掉 `loadFullText(...)` → 两条用例应红 | **成立** | 变异 **M3** → `2 failed, 22 passed`，恰好是 `test_expanding_a_preview_only_row_fetches_the_full_text` 与 `test_expanding_when_the_full_text_is_gone_says_so`，互不冒充 |
| 3 | 折叠态量化承诺未被合并破坏 | **成立** | 既有断言原样在盘（`test_transcript_view_browser.py:37-38` 预算 1200 / 摘要 90，`:224-226` 逐行 + 无正文片段），7 文件套件 `220 passed`；我对候选修复（M4）也复跑了同一套件 `220 passed` |
| 4 | 历史路径 `appendHistoryToolResult` 接了 loader | **接线安全但实际是死代码（MUST-FIX-3）**；无重复请求、空 sessionId 不炸 | `chat.js:821-828`（`display` 只填字符数/行数、`result` 非空）⇒ `tool_rows.js:673` 的 `previewOnly` 恒为 false ⇒ `:624` 守卫直接返回，loader 永不调用。探针 D：`requests=[]`，展开体停在 `…[truncated; full result in result_ref: artifact://…]`，meta 把预览长度当结果规模（`2.1k 字符`）。空 sessionId 路径安全（`chat.js:1116` 返回 null，`:1120` 再守一层） |
| 5a | `chat.js` 无残留 master 旧 `.message.tool` 渲染路径 | **成立（无重复渲染）** | 全仓无 `.message.tool` / `tool-result-toggle` / `tool-result-controls` 产出方；`style.css:209-210`、`:328-329` 注记旧样式族已删；`renderHistory`（`chat.js:776-789`）对 `role:"tool"` 只有一条 `appendHistoryToolResult` 分支 |
| 5b | spec 合并文本自相矛盾 | **无矛盾（一处建议交叉引用）** | `openspec/specs/web-ui/spec.md:117-166`：`:130` 明写「例外只有**单行摘要**（工具名 / 参数摘要 / 失败首行），它不是正文」，与 `:119`（折叠态 SHALL NOT 展示结果正文）以及失败条款 `:1382-1392`（`:1389` 因由可读 / `:1392` 不误报）自洽；`:141` 场景句未回指该例外（可选 L5） |
| 5c | 冲突解决是否丢东西 | **丢了两处 master 能力：收起释放缓存（MUST-FIX-2）、历史行按需回取（MUST-FIX-3）**；缓存版本号已正确递增 | master 收起分支清 `cachedFull` 并把 body 重置为 preview（`8f575c8:web/static/chat.js:965-974`）；合并后点击只切 `hidden`（`tool_rows.js:604-613`）。`index.html` 资源版本 `tool_rows.js?v=1→2`、`chat.js?v=25→26`（两侧父提交分别是 v1/v25 与 v24），无缓存串味 |
| 6 | 回归面 | **通过** | 7 文件 `220 passed`（181.56s，与实现方声称一致）；全量 `tests/web_tests` = `45 failed / 469 passed / 8 skipped`，**45 条与 pristine master 8f575c8 逐条同名**（26 `test_workflow_graph_ux_js` + 1 `test_workflow_graph_js` + 9 `test_terminal_honesty_js` + 9 `test_multi_session`，均为 GBK/Windows 路径类），**无新增红** |

## Issues

### MUST-FIX-1（HIGH）`collapsed === false` 的真实事件形态下：展开体空正文 + 失败不可见

- **位置**：`web/static/tool_rows.js:673-674`（`var previewOnly = given === '' && !!(display && display.collapsed === true); var result = previewOnly ? String(display.preview || '') : given;`）；配套注释 `web/static/chat.js:1092-1095`。
- **判据**：合并后的真实 `tool_result` 事件**永不携带 `result`**（`agent/loop.py:1073-1081`；`tests/web_tests/test_server.py:1290-1293` 已断言 `"result" not in data`）。`agent/tool_result_display.py:50-55`：`collapsed=false` 时 `preview = text`（预览就是全文），`collapsed=true` 时才截到 1200 字符。而 `updateToolRow` 只在 `collapsed === true` 时回落 preview ⇒ 对**所有 ≤4000 字符且 ≤80 行**的结果（短 Bash/Read/Grep/Write/审批拒绝/参数解析失败……线上绝大多数），判定与展示的文本依据都是空串：`summarizeToolResult('')` 直接 `{state:'ok'}`（`:415`），`resultPre.textContent = ''`（`:699-703`）。这是**合并引入的回归**：`f4afae1:agent/loop.py` 的同一事件带 `"result": …`，合并前这条路径拿的是全文。
- **复现**（仓库外探针，真实 Chromium，载荷即 `agent/loop.py` 的发射形状）：
  - 探针 A：`tool_call(Bash, rm -rf build)` → `{name:Bash, tool_call_id:cA, display:{collapsed:false, preview:"[Approval denied: …]", char_count:58, line_count:1}}` ⇒ 实测 `data-state='ok'`、`summary='rm -rf build'`、展开体只有 `参数\n{ "cmd": … }`；期望 `error` + 摘要含 `[Approval denied` + 展开体含正文。
  - 探针 B：成功的 `41 passed in 7.73s`（`collapsed:false`）⇒ 展开体不含该文本。
  - 探针 C：`Error: no such file or directory`（单行，`collapsed:false`）⇒ `data-state='ok'`、摘要退回参数 `nope.py`。
- **建议修法（已验证）**：文本依据与取全文的门槛分离——`:674` 改为 `var result = given !== '' ? given : String((display && display.preview) || '');`（`previewOnly` 语义保持不变，仍只控制是否按 id 回取）。变异 **M4** 实测：探针 A/B/C/E `4 passed`，且 7 文件官方套件 **`220 passed`**（零回归）。
- **回归测试建议**：把探针 A/B/C 落成 3 条浏览器用例（至少 A 与 B），断言 `collapsed=false` + 无 `result` 时失败可见、展开体非空。

### MUST-FIX-2（MEDIUM）合并规格的「收起时释放已取回的全文缓存」未实现

- **位置**：规格 `openspec/specs/web-ui/spec.md:121`（「用户收起时，前端 SHALL 释放已取回的全文缓存」）、delta 场景 `openspec/changes/archive/2026-10-03-harness-style-web-transcript/specs/web-ui/spec.md:159`；实现 `web/static/tool_rows.js:604-613`（点击只切 `aria-expanded` 与 `hidden`）与 `:623-655`（无释放分支）。master 的实现位于 `8f575c8:web/static/chat.js:965-974`（收起分支 `cachedFull = null; body.textContent = display.preview;`）。
- **判据**：合并规格里的这条 SHALL 是从 master 侧原样保留的，合并后的实现不满足；`__fullTextLoaded` 守卫还使「收起后重展不重取」成为默认行为。
- **复现**：探针 G（路由 `**/tool-result/*` 返回 313 字符全文）→ 展开后收起，实测 `body_hidden=true` 而 DOM 仍保留 `@@FULL-TEXT@@…`（`document.querySelector('.tool-row-result').textContent` 长度 313）⇒ 断言失败。
- **可选修法**：① 收起时清空 `resultPre.textContent`、删除 `dataset.previewOnly` 并复位 `__fullTextLoaded`（回到「预览 + 未取回」态，重展再取一次）；或 ② 明确接受保留策略并**同步改规格**（`openspec/specs/**` 是受保护路径，需结构化事件），同时说明为什么保留与 master 的内存意图不冲突。二者选一即可闭环，但不能停在现状。

### MUST-FIX-3（MEDIUM）历史行的 loader 是死接线：preview + ref 的历史工具结果不会按 id 回取

- **位置**：`web/static/chat.js:821-828`（`result: text` + 合成 `display{char_count,line_count}` + `loadFullText: toolResultLoader(id)`）、`web/static/tool_rows.js:624`（`if (!row.__previewOnly …) return;`）与 `:673`（`previewOnly` 仅在「`result` 为空且 `collapsed===true`」时为真）。
- **判据**：历史载荷的 `content` 可能是已被 spill 的「预览 + ref」（`web/session.py:83` 直接投影 `extract_text(message.content)`；`agent/memory/tool_result_policy.py:176-191` 生成的标记形如 `…[truncated; full result in result_ref: artifact://…]`），而服务端**完全有能力**按该 id 读出全文（`web/session.py:929-978`：`extract_result_ref` → `AgentArtifactStore.load`）。但历史行传入的 `result` 非空 ⇒ `previewOnly=false` ⇒ 永不调用 loader。`chat.js:825-827` 的注释「展开时也要能按 id 回取全文」与代码行为相反。
- **复现**：探针 D —— `session_history` 带 `tool_calls:[{id:t9,name:Bash}]` + `role:"tool", content="HEAD-OF-RESULT"+1980×"x"+"\n…[truncated; full result in result_ref: artifact://agent/s1/result-9]"`，点击展开 ⇒ `requests=[]`（一次都没发），展开体停在 preview+ref，行尾 meta 显示 `2.1k 字符 · 2 行`（把预览长度当结果规模）。
- **说明与修法**：这不是相对 master 的回归（master 的 `renderHistory` 把 `role:"tool"` 直接铺成 user 气泡，同样不取），但它是本次合并**主动写下的承诺**且与合并规格 `:121`「用户展开某条结果时，前端 SHALL 按该标识按需向服务端取回全文」冲突。建议二选一：① 让历史行也能触发回取——最省的做法是服务端在历史投影里标出该消息已被 spill（例如复用 `is_spilled_preview`，投影一个 `display:{collapsed:true,…}` 或用现成的 ref 判定），前端据此把 `previewOnly` 置真；② 若刻意不做，至少**订正注释**并把该口径写进规格/`docs/known-debt.md`，避免下游把它当前能力。

### 可选（LOW，不阻断）

| # | 位置 | 判据 / 复现 | 建议 |
|---|---|---|---|
| L1 | `web/static/tool_rows.js:409-414` | 合并新增的 `display.line_count` 判据**零仓库断言**：变异 M2 去掉 hint → 仓库套件 `81 passed` 全绿（存活变异）；我的仓库外探针 E（preview 无换行但 `line_count=2`、首行 `Error: …`）在去掉 hint 后变红 ⇒ 该分支有效但无覆盖 | 在 `test_transcript_js.py` 补一条带第三参数的 node 用例：`one("summarizeToolResult", "Read", "Error: x", {"lineCount": 2})["state"] == "ok"`，并补一条 `lineCount: 1` 的反例 |
| L2 | `web/static/tool_rows.js:334-343` | 截断预览兜底里 `timed_out` / `oom_killed` 两支不可达：信封首字段恒为 `exit_code`（`agent/tools/sandbox/base.py:99-118` 的字段序 + `json.dumps(asdict(…))`），`exitMatch` 必然命中，`exit_code===0` 时提前 `return null`、非 0 时提前返回 `exit N`。node 探针：同一条 `exit_code=0 + timed_out=true` 载荷，完整时报 `timeout`（与 `test_transcript_js.py:409-413` 一致），截断后报 `ok`；`exit_code=-1 + timed_out=true` 截断后报 `exit -1`（完整时报 `timeout`）。**当前两个后端超时都用 `exit_code=-1`（`process_backend.py:217-225,283-289`、`docker_backend.py:163-169`），故线上不可达**，属潜在不一致 | 把 `timed_out`/`oom_killed` 检查提到 `exit_code===0` 的提前返回之前（或删掉这两行，并在注释里写明「截断态只信 `exit_code`」）+ 一条 node 用例 |
| L3 | `docs/architecture.md:91` | 同一段自相矛盾：前半句「`tool_call` / `tool_result` 事件不带调用 id，配对按到达顺序 FIFO」与后半句「工具结果事件带 display metadata 与 `tool_call_id`」。合并把两侧取并集造成 | 改为「`tool_call` 事件不带调用 id、`tool_result` 的 `tool_call_id` 只用于按需回读、配对仍按到达顺序 FIFO」 |
| L4 | `openspec/specs/web-ui/spec.md:1431` | 依据句「不新增协议 id 是本 change 的刻意取舍」在合并后与事实相反（`tool_result` 现在带 `tool_call_id`，只是用途是回读而非配对） | 加一句限定（「配对不新增 id；`tool_call_id` 由 `tool-result-lifecycle` 为按需回读引入」） |
| L5 | `openspec/specs/web-ui/spec.md:141` | 场景句「该行的可见文本 SHALL NOT 包含结果正文预览」未回指 `:130` 的「例外只有单行摘要」；单独读会与失败首行顶摘要（`:130`、`:1389`、delta `:100`）看似冲突 | 在 `:141` 后追加「（`#### Scenario` 的判据按 `:130` 的单行摘要例外读）」或把例外并入场景句 |
| L6 | 归档 delta `…/specs/web-ui/spec.md:7,12,13` vs 合并后 `openspec/specs/web-ui/spec.md:119,130,131` | 归档 delta 的 MODIFIED requirement 文本未随合并更新（缺 master 的 preview/回取段落与「单行摘要例外」），回放该 delta 会得到不含 master 条款的旧文本 | 无需改归档（权威文本是 `openspec/specs`）；建议在 delta 顶部留一行注记，避免后续误按 delta 回放 |
| L7 | `web/static/tool_rows.js:650-654` | `.catch` 分支不置 `__fullTextLoaded`（下次展开会重取）也不置 `pre.dataset.unavailable` | 与成功/`missing` 分支对齐；当前 loader 自带 try/catch 不会 reject，纯健壮性 |
| L8 | `web/static/tool_rows.js:642-648` + `chat.js:1126` | 服务端返回 `missing:false, content:""`（真空结果）时 `toolResultLoader` 得 `''` ⇒ `updateToolRow` 的 `given === ''` 又把它当「尚未取回」，展开体重新显示预览 + `PREVIEW_ONLY_NOTE`，且因 `__fullTextLoaded=true` 不再重取 | 用 `null` 之外再区分一次「已取回但为空」（例如传 `{text, fetched:true}` 或在 loader 内把 `''` 包成 `{empty:true}`） |

### 非缺陷观察（供后续读者省一次排查）

| # | 观察 | 证据 |
|---|---|---|
| O1 | 本地 `--check-archived --skip-protected-paths --skip-backlog` 报 `68×2` 条 mismatch，**不是仓库债也不是本 change 引入**：仓库共 **69 份**归档 manifest（68 个目录，其中一个目录两份），逐份复算其 `report_hash`/`spec_hash` 与 **LF 归一化字节**比对 → **69/69 命中**，与工作区原始字节比对只有 1 份命中（就是本 change，它的报告/delta 是签出后写入的 LF 文件）。根因是本机 `core.autocrlf=true` + 无 `.gitattributes`：已签出文件被物化成 CRLF，而 manifest 的哈希是在 LF 字节上算的。**不要**去「修」那 68 份 manifest | `git config --get core.autocrlf` = `true`；`.gitattributes` 不存在；`git show HEAD:<report>` 的 blob 为 LF 且 sha256 与该 manifest 的 `report_hash` 完全一致 |
| O2 | 本 change 的 manifest 在报告改写后必然漂移（`report_hash` 覆盖 `reviews/building-review.md`，而 `spec_hash` 只覆盖 change 自己的 `specs/` delta，不含 `openspec/specs/**`）。重生成时请确保报告仍是 **LF**（本轮报告的写入格式我已核对） | `agent/workflow/review_manifest.py:100-103`（`spec_hash=artifact_hash(change_dir/"specs")`、`report_hash=file_sha256(report_path)`） |
| O3 | 资源缓存版本已正确递增，无「浏览器拿到旧 JS」风险 | `index.html:177,181` = `tool_rows.js?v=2` / `chat.js?v=26`；两侧父提交为 `v1`/`v25`（f4afae1）与 `v24`（8f575c8） |
| O4 | 「取到全文后重算行状态」已实现，但在当前判定集下几乎不可观测（预览恒为结果头部，失败因由与规模元数据都取自已下发的 display），因此没有独立断言也不构成缺陷 | `tool_rows.js:640-648`；`test_transcript_view_browser.py:743-775` 只断言展开体文本 |

## Mutation Experiments

仓库内变异统一用 `%TEMP%\aw-r6\mutate_r6.py` 执行：读原始字节 → 断言 `count(OLD) == 1` → 写入 → 跑裁判命令 → **按字节还原** → 复核 sha256。`tool_rows.js` 为纯 LF（0 CRLF），故模式用 `\n`；`chat.js` 为纯 CRLF（2363 CRLF），本轮未改它（如需变异必须用 `\r\n`）。

| # | 变异 | 裁判命令 | 结果 |
|---|---|---|---|
| M1 | `tool_rows.js:334-342` 删掉截断 JSON 信封的字段兜底 | `pytest test_transcript_js.py test_transcript_view_browser.py -q` | **RED** `1 failed, 80 passed`（只有 `test_preview_only_result_still_flags_the_failure`）⇒ 兜底有牙齿 |
| M2 | `tool_rows.js:411-413` 去掉 `display.line_count` hint，退回「看文本换行」 | 同上 + 探针 E | **仓库套件 `81 passed`（存活变异）**；探针 E **RED** ⇒ 分支有效但零覆盖（L1） |
| M3 | `tool_rows.js:612` 删 `if (!expanded) loadFullText(doc, row);` | `pytest test_transcript_view_browser.py -q` | **RED** `2 failed, 22 passed`（两条新增展开用例，互不冒充） |
| M4 | **候选修复**：`tool_rows.js:674` 改为 `given !== '' ? given : preview` | 探针 A/B/C/E + 7 文件官方套件 | **GREEN** `4 passed` + **`220 passed`** ⇒ 修复有效且零回归 |
| 探针 A/B/C | 真实 D12 形状（无 `result`、`collapsed=false`）下的失败可见性与正文 | `pytest <TEMP>/test_r6_probe.py -q -o asyncio_mode=auto` | **3 RED**（`state='ok'` / 展开体无正文）⇒ MUST-FIX-1 |
| 探针 D | 历史路径 preview+ref 展开是否回取 | 同上 | **RED**（`requests=[]`）⇒ MUST-FIX-3 |
| 探针 E | `line_count=2` + 预览无换行 + 裸 `Error:` | 同上 | **GREEN**（当前实现判 `ok`）；M2 下 RED ⇒ hint 有牙齿 |
| 探针 G | 展开 → 收起后 DOM 是否释放全文 | `pytest <TEMP>/test_r6_probe2.py -q -o asyncio_mode=auto` | **RED**（收起后 DOM 仍保留 313 字符全文）⇒ MUST-FIX-2 |
| node 探针 | 只读调 `summarizeToolResult` 7 组载荷 | `python <TEMP>/node_probe.py` | 完整 `exit_code=0+timed_out` → `timeout`；**同一载荷截断后 → `ok`**；截断 `exit_code=-1+timed_out` → `exit -1`；截断 `exit_code=1` → `exit 1`；`lineCount` hint 有/无 → `ok` / `error` |

## Test Results

| # | 命令 | 结果 |
|---|---|---|
| 1 | `uv run pytest tests/web_tests/test_transcript_js.py tests/web_tests/test_transcript_view_browser.py tests/web_tests/test_tool_result_expand.py tests/web_tests/test_server.py tests/web_tests/test_session.py tests/web_tests/test_workflow_graph_browser.py tests/web_tests/test_multi_session_browser.py -q` | **`220 passed`**（181.56s）——与实现方声称一致 |
| 2 | `uv run pytest tests/web_tests -q -rf --tb=no` | **`45 failed, 469 passed, 8 skipped`**（275.67s）——与实现方声称一致；失败集 = `test_workflow_graph_ux_js`(26) + `test_workflow_graph_js`(1) + `test_terminal_honesty_js`(9) + `test_multi_session`(9)，traceback 均为 `UnicodeDecodeError: 'gbk' codec…`（子进程读取）与 Windows 路径语义 |
| 3 | pristine master 对照：`git archive 8f575c8` → `%TEMP%\aw-master-8f575c8`，`PYTHONPATH` 指向该树（实测 `web.__file__`/`agent.__file__` 均在该树），跑同一批 4 个文件 | **`45 failed, 102 passed`**，失败用例名与本分支**逐条相同** ⇒ 45 条全部是既有环境性失败，**零新增红** |
| 4 | `uv run pytest tests/agent/memory/test_tool_result_lifecycle.py tests/agent/test_tool_result_lifecycle_loop.py tests/agent/test_artifact_store.py tests/agent/test_read_artifact_resolver.py tests/agent/test_trace_recorder_bounded.py -q` | `58 passed`（合并带入的 master 后端语义完好） |
| 5 | `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` | `Totals: 28 passed, 0 failed`（27 spec + 1 active change `add-minimal-tui-runtime-view`；r2 时的 29 = 28 + 当时尚未归档的本 change，非回归） |
| 6 | `PYTHONPATH=. uv run python scripts/check_openspec_artifacts.py` | `OpenSpec artifact checks passed`（exit 0） |
| 7 | `… check_openspec_artifacts.py --check-archived --skip-protected-paths --skip-backlog` | 本地 exit 1（`68` 条 report + `68` 条 spec mismatch）——见 O1：**LF 归一化复算 69/69 命中**，是 Windows CRLF 假阳性；同一命令在 master 导出树上同样 exit 1（68/68）⇒ 与本 change 无关。报告改写后本 change 也会进入这一集合，重生成 manifest 即恢复（且必须用 LF 字节） |
| 8 | 仓库外探针：5（A–E）+ 1（G）浏览器探针 + 1 份 node 探针 | 见上表 |
| 9 | 完整性 | 4 次变异全部 `restore match=True`；`git status --porcelain` 空；HEAD 仍 `8fb1dbe`；`tool_rows.js`/`chat.js` 哈希与冻结基线一致 |

## 未验证项 / 残余风险

1. **未跑全量 `uv run pytest -q`**（同 r2 的本机限制）。本轮覆盖了 `tests/web_tests` 全量 + 5 个 `tool-result-lifecycle` 后端套件；合并带入的 master 侧其它改动（`agent/`、`benchmarks/`、若干归档文档）在其自身 change 的审阅中覆盖，我未逐条重审。
2. **未做真实 LLM 端到端**：判定输入取自后端真实发射形状（`test_server.py:1288-1293` 的 WebSocket 断言 + `agent/loop.py` 源码），但「真实 run 里 20 次工具调用」的浏览器路径未跑。
3. **L2 的线上可达性**：`exit_code=0 + timed_out=true` 在两个后端都不可达（超时统一 `exit_code=-1`），故按 LOW 处理；若将来新增后端或改字段序，需重新评估。
4. **O1 的结论基于字节复算**，未在 Linux/CI 上实跑一次 `--check-archived`；如需彻底确认，可在 CI 或 WSL 上复跑该命令。
5. **MUST-FIX-2/3 需要在合入前给出决定**（实现或同步改规格/记录取舍），本报告只给出证据与两条可选路径，未替实现方拍板。

## 结论

**verdict: CHANGES_REQUESTED（3 条 MUST-FIX：1 HIGH + 2 MEDIUM，0 条 BLOCKED）。**

合并的方向是对的：`tool_result` 的 D12（preview + `tool_call_id` + 按需回取）被接住，`collapsed=true` 的长结果路径「失败仍可见 + 展开取全文 + 取不到如实说」三条都有实现、有用例、且我用 M1/M3 变异反证有牙齿；折叠态的量化承诺（预算 1200 / 逐行摘要 ≤90 / 无正文片段）在合并后依然成立；`chat.js` 没有残留旧 `.message.tool` 路径，不存在重复渲染；45 条全量失败已用 pristine master 逐条对照证明是既有环境问题，**没有新增红**。

但增量在一处**关键分支上没接住**：真实事件对短结果发的是 `collapsed=false` + `preview=全文`，而新代码只在 `collapsed=true` 时回落 preview ⇒ 打开、展开都拿不到正文，失败（审批拒绝、权限拒绝、单行 `Error:`）全部显示为成功——这正是 `tasks.md:55` 自己预警的「静默吃掉 master 的能力」。M4 证明这只是 `tool_rows.js:674` 一行的事，且改完 220 项官方套件全绿。另有两处需要决定：收起释放缓存（规格 SHALL，master 有、合并丢了）与历史行的按需回取（注释承诺了、代码走不到）。

修完这三条（并在最后生成 manifest：报告与 delta 必须保持 LF 字节、在归档目录不再变动之后再跑 `workflow_state.py review-manifest --change harness-style-web-transcript --phase building --reviewer-run-id building-review-harness-style-web-transcript-20261003-r6`）即可合入；L1–L8 可另开或随手带上（L1 与 MUST-FIX-1 同批补最省事）。
