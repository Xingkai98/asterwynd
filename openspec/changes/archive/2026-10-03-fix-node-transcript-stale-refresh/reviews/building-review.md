# Building Review: fix-node-transcript-stale-refresh

**PASS**

- reviewer run id: `building-review-fix-node-transcript-stale-refresh-20261003-r1`（同一 run 跑满 3 轮；manifest 绑定此 id）
- 审阅时间: Round 1 `2026-10-04 00:20~00:45`、Round 2 `01:20~02:05`、Round 3 `02:20~02:50`（+08:00）
- 审阅对象: worktree `D:\code\asterwynd-worktrees\fix-node-transcript-stale-refresh`，分支 `fix-node-transcript-stale-refresh/2026-10-03`，base `master` = `3b484076f10fa295ce05bb53a01ef53c56c2cc17`，**HEAD == base（尚无 commit，工作区即全部改动）**
- Round-3 工作区摘要: `git diff --binary | sha256` = `7f220f49e91bf3404da68db20ad987b1591702d8a92058d6b35b7ac02448b8c9`（10 文件、`472 insertions(+), 22 deletions(-)`），与实现方声明的冻结锚点**逐一相符**；Round-3 首尾摘要一致——中途只有**我**为变异验证做的临时改动（均已按字节还原，见下条），未观察到实现方改动文件
- 审阅者声明: 零记忆独立审阅；唯一落盘为本报告。三轮为验证所做的临时改动（2 个前端文件的 7 次变异 + 5 条探针用例）已全部按字节还原/删除（`test_zz_*.py` 计数 0，前端文件 sha256 回到冻结值）

| 冻结锚点 | sha256（实测 = 声明） |
|---|---|
| `web/static/workflow_graph.js` | `eacdeb61425a34d6ede92b5727255738d2e802bd54c5bce80d49f1c1942356b7`（三轮均未改） |
| `web/static/workflow_transcript.js` | `bacb9113c664b3e543776068449aa1db920b90b8a370cc8e327ec5fc33148442` |
| `tests/web_tests/test_workflow_graph_browser.py` | `369cc64e109b13e8868de9101e25c4af881c436a296f96b0cdd20b25bbedb395` |
| `openspec/changes/.../specs/web-ui/spec.md`（delta） | `f56ad2149c15733258d9468fbf30d0643ae231e030767c98d97be2ec9e00a65f` |
| `tests/web_tests/test_workflow_graph_ux_js.py` / `_js.py` / `test_terminal_honesty_js.py` | `cda387881192…` / `73800d852c26…` / `42e9f2906de9…` |
| `web/static/index.html` / `style.css` | `5439a5680135…` / `2a9ad2ced121…` |
| `tasks.md` / `docs/architecture.md` / `docs/openspec-change-backlog.md` | `070b2539f502…` / `b230a6d4d3e4…` / `f7eb69a579f2…` |

## 1. 三轮闭环总览（0 条 MUST-FIX 遗留）

| 轮次 | 发现 | 严重度 | 状态 | 独立关闭证据（我做的不变量验证） |
|---|---|---|---|---|
| R1 | 补取绕过「暂停」（`paint()` 不判 `paused`） | HIGH | ✅ 关闭 | 变异：删 `workflow_transcript.js:130` 的 `&& !paused.has(key)` → `test_terminal_catch_up_yields_to_pause` 红（`assert 2 == 1`） |
| R1 | delta 的 MODIFIED 块会静默删 3 条既有 Scenario | HIGH | ✅ 关闭 | OpenSpec `buildUpdatedSpec` 只读 apply 模拟：`LOST: []`（141→144）；3 条无关 Scenario **正文逐字节相同**（207/361/236 字符） |
| R1 | 「只补一次 / 终态不再轮询」调用方侧零覆盖 | MEDIUM | ✅ 关闭 | 变异：删 `statusAtFetch.set` → 3 条用例红；删轮询路径 `fetchedStatus:` → `stops_polling` 红（`assert 3 == 2`） |
| R2 | delta 新写的「点继续 → SHALL 立即取到终态帧」实现为假 | MEDIUM | ✅ 关闭 | 变异：删解除暂停的立即补取块 → 目标用例红（Playwright `waitForFunction` 在 3s 预算上限超时）；未变异时实测延迟 **41.8 / 55.5 ms** |
| R1 | O1 版本号 `?v=5` vs 代码 `?v=4`；O2 同类编码缺陷；O3 delta 两条断言无覆盖；O4 fail-open；O5 tasks 措辞 | LOW×5 | ✅ 全部处理 | 见 §3.4（含 47→11 红、36 条转绿独立复跑） |
| R2 | O-1 backlog 计数过时；O-2 architecture 缺「暂停优先」；O-3 tasks 分解算术；O-4 tasks 3.1 断言偏弱；O-5 观察项 | LOW×5 | ✅ O-1~O-4 已改，O-5 按建议记为「观察，不改」 | 见 §3.4 |

## 2. Round 3 聚焦复验（本轮只验三件，全部通过）

### ① 解除暂停那条 SHALL 现在为真

- 判据：delta `specs/web-ui/spec.md:60`「点『继续实时更新』或『刷新』时，SHALL 立即取到终态帧（『继续』= 现在就跟上，SHALL NOT 让用户再等一个刷新节律）」。
- 实现：`web/static/workflow_transcript.js:173-189`（解除暂停时若 `transcriptNeedsTerminalCatchUp(ctx.itemNode || ctx.node, statusAtFetch.get(key))` 成立即 `paint(..., force)`）。
- 我的探针（已删除，测「点继续 → 终态帧出现」的墙钟耗时）：**41.8 ms / 55.5 ms**（两次独立运行），预算 3000 ms ⇒ 余量约 **55~70×**，且机制是点击同步触发（不依赖定时器）。
- 仓库自身用例 `test_terminal_catch_up_yields_to_pause` **连跑 3 次全绿**（5.40s / 5.36s / 5.35s）。
- **变异（本轮关键）**：整段删掉解除暂停的立即补取块（`workflow_transcript.js:181-188`，CRLF 精确匹配）→ `1 failed in 8.44s`，失败点正是 `wait_for_function(timeout=3000)` 超时 ⇒ 「靠 10s 节律兜住」的实现在 3s 预算下必然红，判别力成立。
- **对 `timeout=3000` 的判断：不偏紧，建议保持不动。** 3s 是**上界**且必须小于节律（10s）才能卡住假修复；实测延迟比它小两个数量级，机器慢到需要 >3s 才能完成「点击 → 本地 fetch → 重绘」的概率可忽略。你提的「断言发生时刻 < 节律」写法与现状等价（3s < 10s 已隐含该断言），不必改。

### ② delta 仍无 Scenario 丢失

```
counts {"added":0,"modified":1,"removed":0,"renamed":0}
scenarios before: 141 after: 144
LOST: []          ← 与 Round 2 相同，措辞再改也没有丢失
GAINED: [ 运行中取过数、随后节点到终态 / 暂停期间到达终态 / 手动刷新绕过缓存 ]
```

块内逐行比对（apply 前 vs apply 后）：仍只有两处**有意**改动——前端取数时机散文段、`对话内容的刷新与暂停` 最后一行（`SHALL NOT 再重取（节点到终态后同样不再重取）` → `SHALL NOT 再自动重取`）；三条与本 change 无关的既有 Scenario（读取单 subagent / foreach 候选集 / 不产生 run 降级）**正文逐字节相同**（`identical: True`，207/361/236）。`validate --all --strict` 29/29 通过（EXIT=0）。

补充核对：`spec.md:60` 的 Scenario 作用域自洽——它的 GIVEN（暂停 + 手上这一帧取自运行期）与 WHEN（节点到达终态）恰好等价于补取条件，所以「SHALL 立即取到」不会在工作区之外被读成「任何情况下点继续都立即取数」。

### ③ 无新增红

```powershell
pytest tests/web_tests -q                 # worktree → 11 failed, 423 passed, 8 skipped in 232.99s
pytest tests/web_tests -q                 # pristine master（D:\code\asterwynd）→ 47 failed, 378 passed, 8 skipped
pytest tests/web_tests/test_workflow_graph_browser.py tests/web_tests/test_workflow_graph_ux_js.py `
       tests/web_tests/test_workflow_graph_js.py tests/web_tests/test_terminal_honesty_js.py -q
#                                          → 131 passed in 120.85s（实现方声明的数字）
```

`Compare-Object` 结果：worktree 的 11 条**全部落在 pristine 的 47 条之内**（无「只在 worktree 红」）；且与 Round 2 的失败集合**逐条相同**（差集 0）。逐文件账（pristine → worktree）：`test_workflow_graph_ux_js.py` 26 → 0、`test_workflow_graph_js.py` 1 → 0、`test_terminal_honesty_js.py` 9 → 0、`test_multi_session.py` 9 → 9、`test_server.py` 2 → 2（36 条转绿）。

## 3. 累积证据

### 3.1 变异验证总表（三轮，全部在冻结工作区上实跑）

| # | 变异（临时改，已按字节还原） | 轮次 | 是否被杀 | 凶手用例 |
|---|---|---|---|---|
| M1 | `transcriptNeedsTerminalCatchUp` → `return false`（去掉补取） | R1 | ✅ | 2 条 ux_js 单测 + 浏览器 `test_convo_tab_catches_up_…` |
| M2 | 改成「终态无条件重取」 | R1 | ✅ | `test_transcript_refresh_stops_for_terminal_nodes`（**证明 R1 对既有断言的修改未削弱保护**）+ 2 条新单测 |
| M3 | 删 `statusAtFetch.set(...)` | R1/R2 | ✅ | R1 只有我的探针红（当时的 MUST-FIX）；R2 起 `catches_up`（`3 != 2`）、`stops_polling`（`3 != 2`）、`refresh_button`（连带 `4 != 3`） |
| M4 | 删轮询路径的 `fetchedStatus:` | R1/R2 | ✅（R2 起） | R2 起 `test_terminal_node_stops_polling_after_the_catch_up`（`assert 3 == 2`） |
| MA | 删 `paint()` 的 `&& !paused.has(key)` | R2 | ✅ | `test_terminal_catch_up_yields_to_pause`（`assert 2 == 1`） |
| MA3 | 删解除暂停的立即补取块 | R3 | ✅ | `test_terminal_catch_up_yields_to_pause`（3s 预算内 `waitForFunction` 超时 → FAILED） |
| 对照 | 未变异基线 | R1–R3 | — | 相关用例全绿；R3 四个文件 131 passed |

### 3.2 规格对齐（逐条）

delta `specs/web-ui/spec.md:38` 的每条 SHALL 与实现对应关系：懒加载 ✅（`test_convo_tab_lazily_fetches_transcript` 绿）；运行中按 10s 节律 ✅；暂停后 SHALL NOT 自动重取（含连终态补取也不发生）✅（`paint():129-133` 的 `!paused.has(key)` + 纯函数 `paused` 优先 + R2 变异）；终态后不再周期性重取 ✅（`stops_polling` 跨 13s）；终态补取一次 ✅；补取判据基于「取数时记录的状态」✅；补取后不再触发 ✅；未记录时按非终态处理 ✅（delta 与 docstring 一致，R2 决定不改口径）；两个动作齐备（暂停/继续 + 手动刷新）✅；手动刷新绕过缓存、不改暂停状态、不影响其它节点缓存 ✅（R2 新增两条断言）；Scenario 三条：终态补取 ✅、暂停期间到达终态（含「继续」立即跟上）✅、手动刷新 ✅。

与既有 canonical spec 的关系：本 delta 是对「节点已到终态或用户暂停后 SHALL NOT 再重取」的**细化**（补上「最后一次取数早于终态」这一缺口 + 暂停优先 + 显式动作例外），未改原意；`LOST: []` 证明它不吞掉任何既有条款。

### 3.3 回归面

`?v=` 击穿齐（`index.html:174-175`，`workflow_graph.js?v=4` + `workflow_transcript.js?v=4`，两文件本轮都被改过）；`.transcript-actions` CSS（`style.css:1852-1871`）与 `toolbar()` DOM（`workflow_transcript.js:163-204`）一致；懒加载契约未破（打开面板零 transcript 请求）；既有抽屉用例（三态 union / 候选下钻 / `.tool-call-block` / 截断提示 / 失败证据 / 簇虚拟化）全绿。

### 3.4 LOW 项落实核对

O1 ✅（proposal/tasks 均 `?v=4` + tasks 5.4 记录）；O2 ✅（`test_terminal_honesty_js.py:39,212,217` + `call_many`，47→11 红）；O3 ✅（`test_convo_refresh_button_bypasses_the_cache` 两条新断言实跑绿）；O4 ✅（delta `:38` 与 docstring 写明 fail-open）；O5 ✅（tasks 3.5 写明三个文件）；O-1 ✅（backlog `:117` 改为 47→11 / 36 条 + 剩余 11 构成）；O-2 ✅（`architecture.md:108` 补「暂停优先于补取」与「点继续立即取一次」）；O-3 ✅（tasks 3.5 分解 26 + 1 + 9）；O-4 ✅（tasks 3.1 改 `== 2` 并写明另两条收紧断言）；O-5 ✅（tasks 6.6 记为「观察，不改」）。

## 4. 未验证项与残余风险（如实列出）

1. **tasks 1.3 的历史实测无法独立复现**（需要用户那次运行的内存态 session `d67875d24fe8`）。旁证成立：后端路由 `web/server.py:195-243` 无终态门禁、无缓存；`web/session.py:871` 的 `running` 文案指纹存在；`failure_evidence` 七态枚举齐备。
2. **未做人工浏览器观感验证**（三轮均为 headless 用例 + 探针）。布局/文案推进等由 DOM+CSS 静态核对与既有断言覆盖，未由人眼确认。
3. **并发响应乱序**：`fetchTranscript` 在响应返回时无条件覆盖 `cache` / `statusAtFetch`（`workflow_transcript.js:84-87`）。抽屉重绘的补取与 10s tick 同时在飞时，旧响应后到会把状态写回非终态 ⇒ 下一次重绘/节拍再补一次。最终收敛（R2 起有 `catches_up` 的「再推一张终态快照仍为 2」与 `stops_polling` 兜住），但会多一次请求。属既有设计的固有脆弱点，未判为必修。
4. 本机剩余 11 条红灯（`test_multi_session.py` 9 + `test_server.py` 2）是 Windows 环境语义差异，与 pristine 逐条一致；它们不因本 change 变化，也不在本 change 的范围内。

## 5. 无需行动的说明（观察项，非缺陷、非建议）

1. **节点仍在跑时点「继续实时更新」不会立即取数**（等下一个节律 ≤10s）。这与 delta Scenario 的作用域一致（该 Scenario 的 WHEN 是「该节点到达终态」，且 GIVEN 已限定「手上这一帧取自运行期」）；若将来想让运行中节点也「点继续就立刻刷新」，那是独立的产品决策，不属于本 delta。
2. **暂停期间抽屉仍会随快照整体重绘**（内容不变、滚动位置回顶）——既有「快照驱动重绘」行为，本 change 只做到「不再因此取数」，delta 的「面板保持用户正在读的那一帧」在内容意义上成立（已断言半途帧文案仍在）。
3. 补取判据的 fail-open 默认（状态未记录 ⇒ 允许一次补取）是**有意**口径：代价是「记录链路断掉」表现为多取而非漏取，R2 起已有端到端断言把它钉在「恰好一次」（`== 2`）。

## 6. 收尾提示

1. 本报告为最终版（verdict **PASS**，MUST-FIX 0 条）。**生成 manifest 后不要再改本文件**：`report_hash` 是报告字节哈希（`agent/workflow/review_manifest.py:166`），改动即失效。
2. **manifest 顺序**：提交分支 → 执行 tasks 4.1（spec 同步）/4.3（backlog 移除）/4.4（归档 move）→ 再 `workflow_state.py review-manifest --change fix-node-transcript-stale-refresh --phase building --verdict PASS`。原因：manifest 记录 `head_sha` 与 `git diff --binary base head` 的 `diff_hash`（`review_manifest.py:96-103,234-237`），提交前生成会绑定空 diff。
3. 本报告存在期间，active 变更的 artifact checker 会报 `review manifest missing`（`scripts/check_openspec_artifacts.py:1140-1151`：只要 `reviews/*-review.md` 存在就要求同目录 manifest），生成 manifest 后即恢复通过。
4. tasks 4.1/4.3/4.4/4.5/4.6 与 `(post-merge)` 项仍未勾选，符合「归档时同步翻转」的约定；本轮未发现「先勾后做」。

## 7. 复现命令速查

```powershell
cd D:\code\asterwynd-worktrees\fix-node-transcript-stale-refresh

# 全量 web 套件（预期 11 failed / 423 passed / 8 skipped，失败集 ⊂ pristine 的 47）
.\.venv\Scripts\python.exe -m pytest tests/web_tests -q

# 本 change 直接相关的四个文件（预期 131 passed）
.\.venv\Scripts\python.exe -m pytest tests/web_tests/test_workflow_graph_browser.py `
  tests/web_tests/test_workflow_graph_ux_js.py tests/web_tests/test_workflow_graph_js.py `
  tests/web_tests/test_terminal_honesty_js.py -q

# delta 完整性（LOST 必须为空；MODIFIED 是整块替换）
node <temp>\osapply.mjs openspec/changes/fix-node-transcript-stale-refresh/specs/web-ui/spec.md `
     openspec/specs/web-ui/spec.md <temp>\applied.md

# 规格校验 + 变更文档检查（manifest 生成后 artifact checker 才会通过）
node <openspec-1.4.1>\bin\openspec.js validate --all --strict        # → 29 passed, 0 failed
$env:PYTHONPATH="."; .\.venv\Scripts\python.exe scripts\check_openspec_artifacts.py --change fix-node-transcript-stale-refresh
```
