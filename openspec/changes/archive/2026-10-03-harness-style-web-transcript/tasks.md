# Tasks: Web 对话区改为 harness 式 transcript

## 1. 立项与调研

- [x] 1.1 写 `proposal.md`（Change Type / Why / What Changes / Capabilities / 验收 L0–L5 / RIR / Impact Analysis / Non-Goals）
- [x] 1.2 写 `design.md`（Context / Goals-Non-Goals / Decisions D1–D12 / 参考实现对照与偏离 / Risks / Testing Strategy / Pre-Implementation Review）
- [x] 1.3 `research_tier: full` 调研：逐文件读本地参考仓库 `D:\code\deepseek-harness` 的 `ui-tool`（`ToolRow.tsx` + `ToolRow.module.css` + `tool-call-model.ts` + `primitive-labels.ts` + `ToolCallTree`）、`ui-conversation`（`ConversationRoot/Content/MainPanel`、`ConversationRoot.module.css`）、`ui-chat`（`ChatView`）、`ui-primitives`（`DisclosureRow`/`TextShimmer`）——产出「折叠行 24px 尺寸链」「bodyRaw 仅展开时格式化」「失败首行替换摘要且不自动展开」「body 是头部兄弟节点」「keepContentWhenOpen」等可落地事实，并逐条记下采纳/偏离及理由（见 design.md `## 参考实现对照与偏离记录`）
- [x] 1.4 同步 `docs/openspec-change-backlog.md` 入队（受保护路径，需结构化事件）

## 2. grill 与确认

- [x] 2.1 用独立零记忆 subagent 按 `batch-grill-me` 逐轮追问 `design.md`，产出 `reviews/grill-design.md`（12 条 `- **决策**:` + 6 条 Open Questions，每条配具体例子）
- [x] 2.2 把 `## Open Questions` 逐项处理并写进 `grill-design.md` 的 `## User Confirmation`
- [x] 2.3 按 grill 订正回写 design/proposal（D2 导出清单、D4 失败前缀集、D5 配对方向、D9 分段导轨、D11 顺序因果、L2 预算口径）
- [x] 2.4 落地 grill MUST-FIX 4 条：①失败前缀集对齐后端 canonical 错误通道 + 收紧未锚定模式 ②结构化失败保留参数摘要、失败信号进行尾 meta ③args 套展示上限 + 「参数已截断」提示移到可见处 ④`done`/`error` 收尾未配对行 + 补配对顺序回归

## 3. 实现（测试先行）

- [x] 3.1 先写失败测试 `tests/web_tests/test_transcript_js.py`（node + `vm` 纯函数层：摘要生成逐工具族、失败前缀集、结构化 Bash JSON、误报防线、截断、元数据单位）
- [x] 3.2 新增 `web/static/tool_rows.js`（`window.AsterwyndToolRows`）：`firstLine`/`truncate`/`compactJson`/`toolTitle`/`summarizeToolCall`/`summarizeToolResult`/`formatCharMeta`/`formatBodyText`/`prettyArgs` + `createToolRow`/`updateToolRow`
- [x] 3.3 `chat.js`：per-tab `pendingToolRows`（含 `createTab`/`bindActiveTab`/`syncActiveTab` 三处归属）；`addToolCallBlock` 建折叠行；`addToolResultMessage` 原地补全；`settleOrphanToolRows` 在 `done`/`error` 收尾；`/clear` 与 `renderHistory` 清队列
- [x] 3.4 `chat.js`：`addMessage` 保留 `.message` 骨架 + user 轮角色微标签；`renderHistory` 把 `role:"tool"` 渲染为折叠行（G3）
- [x] 3.5 `web/session.py`：`build_history_payload` 增 `tool_call_id` 与 `tool_calls`（仅 id/name）投影，让历史工具行拿回真名（grill Q6）
- [x] 3.6 `web/static/style.css`：`.message*` 去气泡改单列文档流；`.message-reasoning*` 改单行；新增 `.tool-row*` 家族（24px 行高 / 可截断摘要 / 兄弟 body）；补 `--panel`/`--muted`/`--transcript-max-width` 定义；`@media 600px` 与 `720px` 两个断点同步（`.tab-messages` 在文件内**重复定义两处**，已同步改）
- [x] 3.7 `workflow_transcript.js`：抽屉「对话」tab 改用同一行组件，截断提示走可见的 `note`
- [x] 3.8 `index.html`：新增 `/static/tool_rows.js?v=1`，bump `style.css?v=21` / `chat.js?v=25` / `workflow_transcript.js?v=4`；**不动** wordmark `?v=3`
- [x] 3.9 先写失败测试 `tests/web_tests/test_transcript_view_browser.py`（L0 折叠零正文 / L1 展开 / L3 历史 / L4 失败 / 配对顺序 / run 结束收尾 / 参数缩进 JSON）

## 4. 测试与验收

- [x] 4.1 更新 `tests/web_tests/test_server.py::test_web_static_assets_include_session_and_run_display`：源码断言改锚点（`tool-row-head` / `resultPre.textContent` / `tool_rows.js`），**保留** `scrollHeight` 与 `innerHTML` 两条安全护栏的意图；顺带把该测试的 `read_text()` 显式设为 `utf-8`（缺省 locale 在 Windows 中文机器上是 GBK，会解不出含中文注释的静态资源）
- [x] 4.2 新增 `tests/web_tests/test_session.py::test_build_history_payload_projects_tool_calls_for_tool_rows`
- [x] 4.3 变异验证（5 条，改坏实现必须变红）：body 默认不 hidden / 折叠行泄漏结果预览 / 失败判定失效 / 历史工具行折回 user 泡泡 / 配对改取最近——逐条实测变红后还原
- [x] 4.4 浏览器回归：`test_transcript_view_browser.py` 19 项 + 既有 `test_browser.py` / `test_multi_session_browser.py` / `test_reconnect_pending_interaction_browser.py` / `test_workflow_graph_browser.py`（抽屉 `.tool-call-block` 与新增的截断提示可见性断言）
- [x] 4.5 全量 `uv run pytest -q` 并与 pristine baseline 逐项对照失败集（本机为 Windows：既有环境性失败与本次改动无关，须逐个说明）
- [x] 4.6 **benchmark smoke**：本 change 未触及 `agent/loop.py` / `agent/tools/` / `benchmarks/`（展示层 + 一处历史载荷投影），不触发核心路径 smoke 门禁。仍实测执行 `asterwynd benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/smoke-transcript`：本机（Windows + GBK locale）在**读取任务文件的 `Path.read_text()`** 处 `UnicodeDecodeError` 失败；**pristine 仓库同命令逐字同样失败**，属既有环境缺陷（与本次改动无关，已在 PR 描述里如实说明）

## 5. 收尾

> **执行顺序**：5.1/5.3/5.4 是 **closeout**，排在 `/review-loop` 终审 PASS 之后（review round 1 的 HIGH-1 指出它们曾被提前勾选）。原因：归档目录一旦建立，change 就不再是「active」，而 artifact checker 要求 backlog 里的条目必须有对应的 active 目录（反之亦然），两者状态必须同时翻转；review manifest 也必须在 `tasks.md` 最终化（含归档 move）之后生成。**归档前这三条会重新勾上（届时已真实完成）**，以满足归档点的完成度门禁。

- [x] 5.1 (closeout) 把 spec delta 同步到 current spec（`openspec/specs/web-ui/spec.md`；受保护路径，需结构化事件）——已同步 2 条 MODIFIED + 5 条 ADDED，`npx openspec validate --all --strict` 29/29
- [x] 5.2 文档影响检查：`README.md`/`README_EN.md`/`docs/architecture.md` 关键词扫描后按事实更新
- [x] 5.3 (closeout) 归档到 `openspec/changes/archive/2026-10-03-harness-style-web-transcript/`（受保护路径，需结构化事件；与 5.4 同一步完成）
- [x] 5.4 (closeout) 从 `docs/openspec-change-backlog.md` 移除（与 5.3 同步，否则 checker 两侧都会红）
- [x] 5.5 `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`
- [x] 5.6 (closeout) `uv run python scripts/check_openspec_artifacts.py` 与 `--check-archived --skip-protected-paths --skip-backlog`
- [x] 5.7 (closeout) `/review-loop` 独立审阅至 PASS 或 3 轮封顶，报告落 `reviews/building-review.md` + review manifest（manifest 在 5.3 归档 move 之后生成）
- [x] 5.8 在分支上提交全部改动并写好 PR 描述（含验证结果与本机环境限制）
- [x] 推送分支并创建 PR、创建关联 GitHub issue（#289）并把编号回填——网络恢复后已执行（原标注 `(post-merge)` 是因实现期 `github.com:443` 连续超时不可达；实际在 PR 之前就完成了，故改为已勾）

## 11. 合入前的 master 合并（origin/master `8f575c8`）

- [x] 11.1 合并 `origin/master`（`3b48407` → `8f575c8`，含 `tool-result-lifecycle` / `foreach-budget-truncation-visibility` / `read-output-bound` 等已归档 change），解决 3 处冲突：`web/static/chat.js`、`openspec/specs/web-ui/spec.md`、`docs/architecture.md`
- [x] 11.2 **保住 master 的新语义**（`tool-result-lifecycle` D12）：`tool_result` 事件不再下发正文，只带 preview + `tool_call_id`，展开时按 `GET /api/sessions/{id}/tool-result/{id}` 回取全文；折叠行改为「有正文用正文、没有就用 preview 做判定与摘要的文本依据」，并在展开时按 id 回取全文、取不到则如实写「全文不可用」。**不这么做会让本次改版静默吃掉 master 的能力**（空正文 + 失败不可见）
- [x] 11.3 截断的 JSON 信封兜底：preview 只有前 1200 字符，长 stdout 的 Bash 结果会被切在半截、`JSON.parse` 必失败 → 用信封头部字段正则认 `exit_code` / `timed_out`（只看前 200 字符，避免 stdout 正文里的同名字段误报）
- [x] 11.4 单行判据改用事件给的 `display.line_count`（预览的换行分布不等于真实行数）
- [x] 11.5 历史路径同样接上 loader（`session_history` 里的工具结果也可能已被替换成 preview + ref）
- [x] 11.6 新增回归：preview-only 失败仍可见（含截断 JSON）、展开按 id 取全文、取不到时如实标注；**变异验证**：去掉截断 JSON 兜底 → 失败用例红；展开不取全文 → 两条用例红
- [x] 11.7 受影响套件 `220 passed`；全量 `tests/web_tests` = `45 failed / 469 passed`，45 条全部是本分支尚未带的既有环境性编码缺陷（同批修复在 `fix-node-transcript-stale-refresh` 分支上，两者合入后自然消失）

> **归档时的两处如实说明**：① 归档目录里保留了 `workflow-state.json`——事件通道在归档语境下只做校验、不重算投影（工具打印一行「归档投影与事件日志不一致，只做校验，未重算」），而归档态校验（`_check_archived_projectable`）按设计**不要求**该文件，故保留而不手工改写（受保护路径只允许 CLI 通道写）。② issue 创建与 PR 推送都被网络阻断过，合并成一条 `(post-merge)` 项；网络恢复后已实际完成（见上）。

## 6. 审阅修复（review-loop Round 1）

- [x] 6.1 **MEDIUM-1**：`TaskOutput` 失败被判成成功——其结果是**多行** `[Task <id>]` + `status:` + `exit_code:`（`agent/loop.py::_format_task_output`），既不是 JSON 信封也不匹配任何行首前缀。新增 `taskFailure()`（首行 `[Task …]` 为门 + 限定行内扫 `status`/`exit_code`），补 4 条 node 用例（failed/timeout、completed+非零退出码、running/成功、**门不成立时不得误报**）；订正 spec delta 里「TaskOutput 是单行 JSON 信封」这句事实错误
- [x] 6.2 **MEDIUM-2**：spec Scenario「重连后工具行显示真名」的 `THEN 折叠摘要 SHALL 显示该调用的参数摘要` 与「`tool_calls` 只发 id/name」互斥。改为「摘要降级为结果首行」，并让 `appendHistoryToolResult` 真的按该契约实现（原先 arguments 缺失时摘要恒为空串），补浏览器断言；同步修正 `chat.js` 的 JSDoc 形状
- [x] 6.3 **MEDIUM-3**：「参数已截断」的**可见性**断言此前只有 `text_content`（连 hidden 子树一起取，看不出可见性），用例名与断言相反。抽屉侧改加 `inner_text` 可见性断言；聊天侧那条改名为 `test_no_note_when_arguments_are_not_truncated`（它断言的是「未截断时无提示」）
- [x] 6.4 **HIGH-1**：订正 5.3/5.4 的执行顺序说明（归档与 backlog 出队必须同时、且在终审 PASS 之后），使其与本轮工作区状态自洽

## 7. 审阅修复（review-loop Round 2）

- [x] 7.1 **Issue 1（HIGH，判为误报但按加固处理）**：报告称 `settleOrphanToolRows` 丢了清空队列的赋值（`chat.js:857`），并复现「僵尸行认领下一轮结果」。**当前工作树里该行存在且行为正确**（自写 Playwright 探针：`tool_call → done → 同名 tool_call → tool_result` 后第 1 行仍 `error/未返回结果`、第 2 行 `ok` 并持有自己的结果）；报告锚定的 `chat.js` sha256（`BBCCACB1…`）与当前文件（`E195E39E…`）不一致，故其结论对应的是另一个修订。**仍按建议加固**：清空改用 `pendingToolRows.length = 0`（保持 per-tab 数组引用，避免全局代理与 tab 指向不同对象）；新增 `AsterwyndChatTest.pendingToolRowCount()` 只读探针；新增两条回归 `test_pending_rows_settle_when_the_run_ends`（加队列深度断言）与 `test_next_run_result_does_not_land_on_a_zombie_row`；变异验证：去掉清空 → 两条用例同时变红
- [x] 7.2 **Issue 2（MEDIUM）**：5.1/5.3/5.4 改回未勾并标注 `(closeout)`，在归档前重新勾上（见 §5 的顺序说明）
- [x] 7.3 **Issue 3（LOW）**：`onclose`/`onerror` 把**整段**连接结果处理纳入 `tabs.has(tab.id)` 守卫（此前只守了 `bindActiveTab`，已关闭 tab 仍会把全局状态灯改成 `ended`、把错误写进活跃 tab 的消息区、动活跃 tab 的上传 waiter）
- [x] 7.4 **Issue 4（LOW）**：删除 `tool_rows.js` 里只写不读的 `row.dataset.summarySource`
- [x] 7.5 **Issue 5（LOW）**：订正 `structured` 的 JSDoc（含 `TaskOutput` 多行形态）、`taskFailure` 内改回 `firstLine(text)`、`summarizeToolResult` 的 `name` 参数注明「保留参数位、当前不按工具分叉」
- [x] 7.6 **Issue 6（LOW）**：文档计数订正（浏览器用例 13 → 18），并把 `tests/web_tests/test_workflow_graph_browser.py` 补进改动清单（它不再是「保持绿的既有断言」——本 change 在其中新增了截断提示可见性断言）
- [x] 7.7 **Issue 7（LOW）**：补 4 条缺失断言——结果含 HTML 时按纯文本渲染（无元素注入、`onerror` 不执行）、行高不随载荷变化（`bounding_box` 恒 ≤26px）、单列文档流（`align-self` 非 `flex-end` + assistant 无底色 + 左边界对齐）、思维链折叠态单行高度（整块高度 == 标题行高度）
- [x] 7.8 **Issue 8（LOW，流程）**：把「实现先于 grill」记为流程债（`docs/known-debt.md`，受保护路径，需结构化事件）

## 8. 审阅修复（review-loop Round 3）

- [x] 8.1 **§7.3 与代码不符（MEDIUM，审阅在冻结修订上取证）**：`onclose`/`onerror` 的 `tabs.has` 早退守卫与 `settleOrphanToolRows` 的 `length = 0` **在盘上确实缺失**——独立审阅做变异实验时按自己的备份做了字节还原，覆盖掉了这两处**晚于其备份**的落盘。已重新落盘并逐条复核（`!tabs.has` 早退 + `length = 0` + 队列深度探针三者同时在场），并新增一条浏览器断言「关掉进行中的 tab 后，另一个仍连接的 tab 状态仍是 `connected`」
- [x] 8.2 **§7.7 声称 4 条实到 3 条（LOW）**：补上第 4 条「思维链折叠态单行高度」（`.message-reasoning` 整块高度 == `.message-reasoning-toggle` 高度且 ≤26px）
- [x] 8.3 **§7.1/§4.4 文字对齐（LOW）**：4.4 的用例计数改为实际值；§7.1 的描述在 8.1 重新落盘后与代码一致（`length = 0`）
- [x] 8.4 复盘并记录根因：**审阅者的变异实验用「自己开始时的备份」做字节还原，会覆盖实现方在此之后的落盘**。后续流程建议：审阅冻结窗口内实现方不再落盘（本 change 已采用），或审阅的还原改用 `git stash`/`git checkout -- <path>` 这类以仓库为源的还原方式，避免用过期的进程内备份

## 9. 审阅修复（review-loop Round 4 / 另一独立审阅者）

- [x] 9.1 **MEDIUM：`TaskOutput` 的 stdout 正文被当成元数据**——`_format_task_output` 把 stdout 直接拼在 `stdout: ` 之后、其内容可再带换行，于是「成功但恰好打印了 `status: failed` / `exit_code: 1`」的后台命令被判红。修法：扫描在 `^stdout:` 行收尾；补 node 用例（`[Task bg-77] status: completed / exit_code: 0 / stdout: …status: failed` → `ok`）
- [x] 9.2 **MEDIUM：浏览器族的失败文案未覆盖**——`agent/tools/builtin/browser_*.py` / `agent/browser/session.py` 产 `[Browser Error: …]`、`[Browser not available: …]`、`[URL denied: …]`，后端 `_text_prefix_guess` 同样没覆盖，漏掉会让「浏览器不可用 / URL 被拒」显示成成功。修法：并入前缀集 + node 用例 + 订正 spec 的前缀清单
- [x] 9.3 **MEDIUM：裸 `Error:` 前缀与「工具返回文件内容」不可区分**——读一个首行正好写着 `Error:` 的文件会被判成失败并顶掉路径摘要。修法：裸前缀只在**结果整体为单行**时判失败（方括号前缀与 `Traceback` 不受限）+ node 用例 + 订正 spec 的「不误报」条款
- [x] 9.4 **§8.1 的守卫补断言**：新增 `test_multi_session_browser.py::test_closing_one_tab_keeps_the_other_tab_status`（切到 tab1 后关闭 tab2，断言 `#status` 仍是 `connected`）；变异验证：去掉 `onclose` 早退守卫 → 该用例变红，还原后变绿
- [x] 9.5 **审查者环境提醒**：本轮审阅者的变异还原会覆盖实现方的落盘（§8.4 已记）。冻结窗口内实现方停止落盘，并在交付前用「标记扫描」逐文件确认所有落盘仍在盘上

## 10. 审阅修复（review-loop Round 5）

- [x] 10.1 **MUST-FIX（Issue 1 MEDIUM，只补测试）**：`/clear` 与 `session_history` 两条重绘路径的「清空未配对队列」零覆盖（审阅的 M3/M4 变异存活）。新增 `test_clear_command_drops_pending_tool_rows` 与 `test_history_redraw_drops_pending_tool_rows`（各断言队列深度 + 清空前的行不得被重新挂回来 / 不得认领新结果）。**变异验证**：用 python 按字节（UTF-8 安全）只删 `/clear` 那一处清空 → 对应用例变红、另一条仍绿；还原后 sha256 一致
- [x] 10.2 **LOW-2/3/4 文档对齐**：`proposal.md` / `design.md` 的浏览器用例计数改为实测值（21）；`acceptance-evidence.md` 的计数改为实测值；该文件的「checker passed」一行改为「当前 exit 1（manifest missing，预期，归档后生成）」；「判为误报」的措辞与 §8.1 统一为「该发现在 16:42:44 修订上确实成立（属落盘被还原），当前修订已正确」；`tasks.md` 的 5.7/5.8 改回未勾并标 `(closeout)`
- [x] 10.3 **LOW-5 `[Task <id> timeout]` 包装形态**：`_wait_task_output` 超时返回的是「包装前缀 + 正常块」，此时任务可能仍在跑但这次调用没拿到结果 → 判失败并把因由显示为 `timeout`；补 node 用例
- [x] 10.4 **LOW-6 前导空行**：失败判定与结构化解析改用**首个非空行**（结果常以空行开头，用 `firstLine` 会拿到空串漏判）；补 node 用例
- [x] 10.5 **LOW-7 `aria-controls`**：头按钮与兄弟展开体补程序化关联（每行唯一 body id）
- [x] 10.6 **LOW-8 `grill-design.md` 的文件名注记**：grill 产出时模块名为 `transcript.js`，实现期因与既有测试的 URL 拦截 glob 冲突改名为 `tool_rows.js`（命名空间同步改为 `AsterwyndToolRows`）；grill 文件里的 `transcript.js` 引用按此对应，语义未变
