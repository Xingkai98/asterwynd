# Tasks: 节点 transcript 的终态补取（修「跑完后对话 tab 停在运行中那一帧」）

## 1. 立项与定位

- [x] 1.1 写 `diagnosis.md`（Symptom / Reproduction / Evidence / Root Cause / Recommended Direction / Regression Tests）
- [x] 1.2 写 `proposal.md`（Change Type / Why / What Changes / Capabilities / RIR `light` / Impact Analysis / 非目标）
- [x] 1.3 实测取证：同一节点 `producer` 在终态后重新取数 = 19 条消息 / 20 个工具行 / `failure_evidence.state=present`（4 条 `permission_denied`），而抽屉那一帧 = 3 条 / 2 行 / `state=running`
- [x] 1.4 同步 `docs/openspec-change-backlog.md` 入队（受保护路径，需结构化事件）
## 2. 实现（测试先行）

- [x] 2.1 先写失败测试：`tests/web_tests/test_workflow_graph_ux_js.py` 补 `transcriptRefreshDue` 的终态补取矩阵
- [x] 2.2 `web/static/workflow_graph.js`：`transcriptRefreshDue(node, opts)` 增补 `fetchedStatus` —— 终态 + 缓存非终态 → `true`；终态 + 缓存终态 → `false`；暂停优先 → `false`
- [x] 2.3 `web/static/workflow_transcript.js`：取数时记录节点状态（`statusAtFetch`）；`render()` 命中缓存前判补取（命中即 `force`），使补取不必等 10s tick
- [x] 2.4 `web/static/workflow_transcript.js`：对话区工具条新增「刷新」按钮（清该节点缓存 + 重取），与「暂停/继续实时更新」并列；`aria-label`/`data-action` 齐备
- [x] 2.5 `web/static/index.html`：bump `workflow_graph.js?v=4`、`workflow_transcript.js?v=4`（两者原本都是 `?v=3`；`3→4` 已构成缓存击穿）

## 3. 测试与验收

- [x] 3.1 浏览器回归（`test_workflow_graph_browser.py`）：「运行中打开对话 tab（首帧只有 2 行）→ 推终态快照 → 自动补取到完整内容」；断言请求次数 **`== 2`**（不是 `>= 2`——只写 `>=` 时「每次重绘都反复补取」的坏实现也能过）、面板出现终态帧才有的标记串与失败证据条目、**再推一张终态快照请求数仍为 2**（自收敛）
- [x] 3.2 浏览器回归：「刷新」按钮清缓存重取（请求次数 +1、内容为最新帧）
- [x] 3.3 既有抽屉用例（三态 union / 候选下钻 / `.tool-call-block` / 截断提示 / 失败证据 / 簇虚拟化）保持绿
- [x] 3.4 变异验证：去掉补取条件 → 3.1 必须变红；把补取改成「无条件重取」→ 终态+缓存终态的用例必须变红（防「靠多轮询兜住」的假修复）
- [x] 3.5 `uv run pytest tests/web_tests -q`（对照 pristine 的既有环境性失败集）——最终 `11 failed / 423 passed / 8 skipped`，**11 条与 pristine master 逐条相同**（复核方式：在干净的 `D:\code\asterwynd`（master）用同一 venv 跑**这 20 条所在的那三个文件** `test_multi_session.py` + `test_server.py` + `test_terminal_honesty_js.py`，为 `20 failed / 90 passed`；这 20 条是本 change 动手前的全部环境性红灯）。本 change 让其中 **36 条**转绿，逐文件账：`test_workflow_graph_ux_js.py` 26 + `test_workflow_graph_js.py` 1 + `test_terminal_honesty_js.py` 9 = 36（另有 `call_many` 一处补编码，当前无红可降）。剩下的 11 条集中在 `test_multi_session.py`（9，Windows 路径语义）与 `test_server.py`（2：Unix `printf` / 未指定编码的既有读法），与本次改动无关
- [x] 3.6 `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`（29/29）与 `scripts/check_openspec_artifacts.py --change fix-node-transcript-stale-refresh`（passed）

## 4. 收尾

> 下列 closeout 项在 `/review-loop` 终审 PASS 之后执行（归档目录一旦建立，change 即不再是 active，
> backlog 条目与归档目录必须同时翻转）；归档前重新勾选时逐项确认**真实完成**，不做「先勾后做」。

- [x] 4.1 把 spec delta 同步到 current spec（`openspec/specs/web-ui/spec.md`；受保护路径，需结构化事件）——已同步，实测 requirement 数不变（51）、Scenario **141 → 144**、`LOST = []`、新增恰为 3 条新 Scenario；`npx openspec validate --all --strict` 29/29
- [x] 4.2 文档影响检查：`README.md`/`README_EN.md`/`docs/architecture.md` 关键词扫描后按事实更新——`README.md` 无 workflow 抽屉/刷新节律相关段落（关键词扫 `抽屉`/`节点详情`/`失败证据`/`实时更新` 均无命中），`README_EN.md` 同理；`docs/architecture.md` 的 Web UI 小节新增一条「对话 tab 的取数时机」（补取判据 + 暂停优先 + 点继续立即补取 + 刷新动作），归因到本 change
- [x] 4.3 从 `docs/openspec-change-backlog.md` 移除（受保护路径，需结构化事件；与归档同步）
- [x] 4.4 归档到 `openspec/changes/archive/2026-10-03-fix-node-transcript-stale-refresh/`（受保护路径，需结构化事件）
- [x] 4.5 `/review-loop` 独立审阅至 PASS 或 3 轮封顶，报告落 `reviews/building-review.md` + manifest（manifest 在归档 move 之后生成）——3 轮：R1 `CHANGES_REQUESTED`（2 HIGH + 1 MEDIUM）→ R2 `CHANGES_REQUESTED`（新 1 MEDIUM，R1 三条全关）→ R3 **PASS**（MUST-FIX 0）
- [x] 4.6 提交分支并写好 PR 描述（PR 描述见交付说明；本机不可推送）
- [ ] (post-merge) 推送分支并创建 PR、创建关联 GitHub issue 并回填编号（本机 `github.com:443` 不可达）

## 5. 审阅修复（review-loop Round 1 → Round 2）

- [x] 5.1 **M1（HIGH）补取绕过「暂停」**：`paint()` 的补取分支加 `!paused.has(key)`（抽屉在每张快照上都会重绘，所以不看暂停就会被终态快照推动着换页）；delta 明文写「暂停优先于补取」并新增 Scenario「暂停期间到达终态」；新增浏览器回归 `test_terminal_catch_up_yields_to_pause`。**变异验证**：删掉该守卫 → 新用例红
- [x] 5.2 **M2（HIGH）spec delta 会静默删掉 3 条既有 Scenario**：MODIFIED 块补齐原 requirement 的 4 条 Scenario 正文（读取单 subagent / foreach 候选集 / 不产生 run 降级 / 对话内容的刷新与暂停），再叠加 3 条新增；块首写明「MODIFIED 是整块替换」的理由。**验证**：脚本比对 current spec 的 4 条 Scenario 名与 delta 覆盖集，缺失集为空
- [x] 5.3 **M3（MEDIUM）「只补一次/终态不再轮询」零覆盖**：`>= 2` 收紧为 `== 2`；补「再推一张终态快照仍为 2」（杀「不记录取数状态 → 反复补取」）；新增 `test_terminal_node_stops_polling_after_the_catch_up`（跨 13s > 一个刷新节律，请求数不变，杀「轮询路径漏传 fetchedStatus → 终态后继续重取」）
- [x] 5.4 LOW O1 `?v=5` → `?v=4`（proposal/tasks 与代码对齐）
- [x] 5.5 LOW O2 同类编码缺陷补完：`test_terminal_honesty_js.py` 的 `call()` 与两处 `read_text()`、`test_workflow_graph_js.py` 的 `call_many()` 各补 `encoding="utf-8"`（本机 web 套件 20 红 → 11 红，且 11 条与 pristine 逐条一致）
- [x] 5.6 LOW O3 delta 的两条无覆盖断言补上：刷新「不改暂停状态」（断言按钮仍是「继续实时更新」）+「不影响其它节点缓存」（先缓存节点 a，刷新 b 后点回 a 仍命中缓存→请求数不变）
- [x] 5.7 O4「fail-open 默认」按审阅建议**不在本 bugfix 内改口径**，已在 delta 与纯函数 docstring 写明：取数状态未记录时按非终态处理（允许一次补取、自收敛）
- [x] 5.8 LOW O5 tasks 3.5 措辞写明是哪三个文件，避免归档后被读成错误结论

## 6. 审阅修复（Round 2 → Round 3）

- [x] 6.1 **R2-1（MEDIUM）delta 里「点『继续实时更新』或『刷新』→ SHALL 立即取到终态帧」的实现为假**（原实现只靠 ≤10s 的节律 tick 兜住）。按审阅推荐的方案 A **改代码**：解除暂停时若 `transcriptNeedsTerminalCatchUp` 成立就立即 `paint(..., force)`；delta 补明「『继续』= 现在就跟上，SHALL NOT 让用户再等一个刷新节律」；`test_terminal_catch_up_yields_to_pause` 增加「点继续 → 3s 内取到终态帧（`timeout=3000` 卡住『等节律』那种实现）」+「再暂停后点刷新 → 立即取数」两段。**变异验证**：删掉解除暂停的立即补取块 → 该用例红
- [x] 6.2 LOW O-1 `docs/openspec-change-backlog.md` 的计数改为 47→11 红 / 36 条转绿
- [x] 6.3 LOW O-2 `docs/architecture.md` 补「暂停优先于补取」与「点继续立即补取」
- [x] 6.4 LOW O-3 tasks 3.5 的 36 条分解改为可核对的口径（26 + 1 + 9）
- [x] 6.5 LOW O-4 tasks 3.1 的 `>= 2` 改为 `== 2` 并写明另外两条收紧断言
- [x] 6.6 O-5（观察，不改）暂停期间抽屉仍会整体重绘、滚动位置回顶：属 `enhance-workflow-graph-ux` 既有的「快照驱动重绘」行为，与本 change 的取数时机无关，如实记录不顺手改
