# Tasks — fix-issue-226-browser-test-flake

## 0. 前置（用户已拍板：方案 B）

- [x] 0.1 **停轮等用户就 design D1 拍板** —— 用户拍板：**采用方案 B**（`init()` 后暴露显式就绪信号）
- [x] 0.2 按拍板结论回写 `design.md` D1（含 D1.1 形态/命名、D1.2 失败路径、D1.3 spec delta）与 `proposal.md` 的「待确认影响面」，非选中方案已移入「否决的备选」
- [x] 0.3 确认给 `web-ui` spec delta 追加「Web UI 暴露应用初始化完成的测试接缝」Requirement（已落，见 1.2）

## 1. 规格

- [x] 1.1 维护 `specs/web-ui/spec.md` delta（就绪屏障契约 3 个 Scenario + 测试接缝 Requirement 2 个 Scenario）
- [x] 1.2 追加 Requirement「Web UI 暴露应用初始化完成的测试接缝」——`window.AsterwyndChatTest.initDone`，`init()` resolve 后置位、失败/未完成不置位（fail-loud）、只增不改、**测试专用不得当死代码移除**；含「完成后置位」「未完成不置位」两个 Scenario
- [x] 1.3 更新受影响 capability 的 spec delta，并明确本 change 的范围、非目标和验收标准
- [x] 1.4 开发前使用 `batch-grill-me`（或等价设计追问）审视 `design.md`；逐项确认关键实现细节、依赖、风险、测试策略和文档影响；**不得把 agent 的推荐答案当作用户确认**
- [x] 1.5 维护 `## Impact Analysis`，列出影响、不影响和待确认影响面；开发前把待确认项清理为明确结论或阻塞项
- [x] 1.6 维护 `## Reference Implementation Research`（已初稿：`research_tier: exempt` + 业界依据 + 本地参考仓库不可用事实）
- [x] 1.7 在 `design.md` 的 `## Pre-Implementation Review` 记录已解决问题、备选方案、否决方案、最终确认和剩余风险
- [x] 1.8 落地 spec delta 到 `openspec/specs/web-ui/spec.md`（**当前规格同步**；见 4.9 的机械校验）

## 2. 测试（TDD：先写回归测试）

- [x] 2.1 **回归测试 A**（`test_new_tab_send_survives_slow_handshake`，落在 `tests/web_tests/test_multi_session_browser.py`）：延迟注入（CDP `Network.emulateNetworkConditions`，**注入值 3000ms**）拉长 WS 握手往返 → 先等 rekey 就绪屏障再发送，断言消息送达
      （`LLM calls ≥ 1` / assistant 回复出现）。**只保留正向半场**：Q4 原文只要求「注入 ≥3000ms + 断言实测等待 ≥ 注入值」，起草时附带的「负向半场（断言无屏障时发不出）」会与机器速度赛跑、自身即是新 flake 来源，经监督侧裁定移除（判别力不受影响：去掉屏障后发送落空 → 消息不送达 → 仍必红，见 2.4 的变异验证）
- [x] 2.2 **回归测试 B**（落在 `tests/web_tests/test_workflow_graph_browser.py`）：`page.route` 延迟 `init()` 依赖的两个 fetch（`/api/slash-commands`、`/api/debug-status`），**注入延迟 ≥6000ms**（旧 helper 固定耗时 ≈5.3s，必须显著超过）→ 断言「派发 workflow 事件后，视图最终保持 workflow 且 svg 可见」。**该测试只调修后的 `_wait_app_ready`，SHALL NOT 调 `_ensure_workflow_view`**（否则第二层把视图强行拉回 ⇒ 未修也恒绿、自证）
- [x] 2.3 **断言注入确实生效**（两条都要）：回归 A 断言「屏障实测等待 ≥ 注入值」；回归 B 断言「`initDone` 在延迟窗口内确为 `false`」或等价的路由命中/延迟证据。理由：CDP `emulateNetworkConditions` 在新版 Chromium 已被 `emulateNetworkConditionsByRule` 取代，命令若失效测试只会**总绿**、判别力静默归零
- [x] 2.4 **变异验证**（判别力证明）：去掉屏障 → 2.1/2.2 必红；还原 → 必绿。记录两向实测结果
- [x] 2.5 **`initDone` 语义验证 ×2**（对应 spec 两个 Scenario，也是「不得当死代码移除」条款的**唯一可执行守护** —— 本仓库无 JS lint/死代码检测）：①正常加载下最终 `initDone === true`；②延迟 init 的两个 fetch 时，屏障把派发推迟到 `initDone` 置位之后
- [x] 2.6 覆盖负向路径：断言「就绪判据失效时表现为失败/有边界超时，而非恒真通过」（对应 spec 的「就绪判据失效可被察觉」Scenario）
- [x] 2.7 确认新回归测试**不依赖机器负载**（用路由/CDP 拦截注入，不用墙钟 sleep 作断言）

## 3. 实现

- [x] 3.1 修 `tests/web_tests/test_workflow_graph_browser.py:123-138` 的 `_wait_app_ready` 死等：判据改为 `window.AsterwyndChatTest && window.AsterwyndChatTest.initDone === true`（**带存在性守卫**），**并删除 `except Exception: await page.wait_for_timeout(300)` 吞异常降级**（保留则判据失效时静默退化，15 条全绿）。超时上限在**本文件定义**该常量（`BROWSER_TIMEOUT_MS` 只存在于 `test_multi_session_browser.py:30`，本文件无；跨模块 import 与 Non-Goal「不引入统一浏览器测试基建」有张力，故本文件内自有常量）
- [x] 3.2 `tests/web_tests/test_workflow_graph_browser.py`：**15 条**零屏障用例接上「派发前 `_wait_app_ready` + 派发后 `_ensure_workflow_view`」（照已验证的 `:487`/`:1039`/`:1084` 写法）；断言保持不变。清单：`:168`/`:198`/`:216`/`:233`/`:275`/`:333`/`:392`/`:433`/`:467`/`:573`/`:642`/`:664`/`:745`/`:905`/`:939`
- [x] 3.2b **`:168` 的插入位置约束**：该用例在派发后、svg 等待前有 `assert await page.is_visible("#workflow-view")`（`:175`），而 `_ensure_workflow_view` 会调用测试自装 stub 的 `onWorkflowStarted()` 把视图设为 active ⇒ **必须插在 `:175` 之后**，否则该断言恒真（其余 14 条已逐条核对无此问题）
- [x] 3.2c **tick 类用例的 ticker 依赖**（`:708`/`:745`/`:769`）：`_ensure_workflow_view` 只恢复视图激活态、**不恢复本地计时器**（`showView()` 对非 workflow 视图会 `chat.js:301` 调 `stopTicker()`）。判据退化时 `:708`/`:745` 会因「文本没变坏」而**恒真假保护**、`:769` 报误导正文。**用户已拍板：在 `_ensure_workflow_view` 里补 `window.AsterwyndWorkflow.startTicker()`**（与视图激活态一起恢复，使该后置兜底真正等价于「视图可用」），并在 docstring 写明恢复 ticker 的理由；同步记入 design D3
- [x] 3.3 `tests/web_tests/test_multi_session_browser.py`：`test_multi_tab_independent_messages`(`:253`) 改用具名就绪屏障（优先 `_open_two_tabs`；差异大则 `#status === 'connected'` 并写明理由）
- [x] 3.4 同上：`test_multi_tab_exit_does_not_affect_other_tab_reconnect`(`:728`)
- [x] 3.5 同上：`test_multi_tab_approval_isolation`(`:768`)
- [x] 3.6 `web/static/chat.js`：在 `init()` 调用点新增 `window.AsterwyndChatTest.initDone`——先置 `false`，再 `init().then(() => { window.AsterwyndChatTest.initDone = true; })`（**不带 `onRejected` 第二参数**，Q5 拍板：失败时保留今天已有的响亮报错，不吞）——**只增不改**，不触碰任何既有函数体/分支/渲染
- [x] 3.7 如实现中发现新影响面，先回写 `## Impact Analysis` 和本任务清单，再继续
- [x] 3.8 如实现中发现 RIR 结论需修正，先回写 `## Reference Implementation Research` 和本任务清单
- [x] 3.9 更新必要文档（见第 5 节）

## 4. 验证

- [x] 4.1 运行相关测试：`uv run pytest tests/web_tests/test_multi_session_browser.py tests/web_tests/test_workflow_graph_browser.py -q`（**单进程，不并发**）
- [x] 4.2 运行 `tests/web_tests/` 子集回归，确认无新增失败
- [x] 4.3 改造后对两个文件做**有限次数**重复跑（单进程、不并发、不人为加压），观察不再出现时序失败；**不以「反复跑逼出 flake」为手段**
- [x] 4.4 运行全量测试：`uv run pytest -q`（收尾一次）
- [x] 4.5 运行 OpenSpec strict validate：`npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`
- [x] 4.6 运行项目 OpenSpec artifact checker：`uv run python scripts/check_openspec_artifacts.py`
- [x] 4.7 确认 baseline CI 命令可本地通过：`uv run pytest -q`、`npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`、`uv run python scripts/check_openspec_artifacts.py`
- [x] 4.8 若涉及 Web，运行 Web session/server 测试；必要时运行浏览器 smoke（本 change 改的就是浏览器测试，`tests/web_tests/` 子集即对应层级）
- [x] 4.9 确认 `openspec/specs/web-ui/spec.md` 已同步本 change 的 delta（当前规格同步，供 artifact checker 机械校验）

## 5. 文档影响

- [x] 5.1 关键词扫描 `docs/`、`README.md`、`AGENTS.md`、`CONTEXT.md` 中与浏览器测试 / flake / 就绪屏障相关的段落
- [x] 5.2 `docs/testing-guide.md`：已核实其**未记录**浏览器就绪约定（仅 `:87` 提 Playwright 安装），故本项为「无影响」——收尾时如实记结论，不强改
- [x] 5.3 **更正 `docs/known-debt.md:297-309`**（fix-issue-215 审阅 R6 那条）：其断言「`_ensure_workflow_view` 把『渲染了但被切走』这类间歇红治住」已被本次诊断**证伪**（该 helper 只覆盖 3 条、不恢复 ticker、不构成有效屏障），须按本 change 结论更正。受保护路径，需 `workflow-events.jsonl` 的 `protected_artifact_explained` 事件
- [x] 5.4 `docs/known-issues.md` / `docs/known-debt.md` **新增**一条 issue #226 的记录（两文件当前 grep `226` **零命中**，原 5.3 指向的「已记录的债务」不存在，照原文执行会打空/改错位置）
- [x] 5.5 `web/static/chat.js` 的接缝注释写明：`initDone` 为测试专用、零生产行为，不得当死代码移除（与 spec delta 口径一致）
- [x] 5.6 `docs/openspec-change-backlog.md` 登记本 change

## 6. 审阅闭环

- [ ] 6.1 Round 1 独立 subagent 审阅（`/review-loop fix-issue-226-browser-test-flake`）→ verdict
- [ ] 6.2 按 verdict 修复 + 补回归测试（若有 CHANGES_REQUESTED）
- [ ] 6.3 复审至 PASS（或 3 轮封顶）
- [ ] 6.4 生成 review manifest（绑定 reviewer run / base·head sha / tasks·spec·diff·report hash），**在该 change 的 `tasks.md` 最终化（含归档 move）之后生成**

## 7. PR 收尾

- [ ] 7.1 PR 发起前，将本 change 归档到 `openspec/changes/archive/YYYY-MM-DD-fix-issue-226-browser-test-flake/`（**日期前缀为硬性要求**）
- [ ] 7.2 从 `docs/openspec-change-backlog.md` 移除本 change
- [ ] 7.3 确认 Impact Analysis 不再残留未解释的 `unknown`、`TBD` 或 `待确认`（**D1 拍板后须清理**）
- [ ] 7.4 确认 RIR 已记录最终状态、发现和设计影响，且未把本地参考仓库路径写成项目依赖
- [ ] 7.5 再次运行 OpenSpec strict validate + artifact checker
- [ ] 7.6 PR 合入后给 issue #226 添加完成说明 comment 并关闭 issue **(post-merge)**
