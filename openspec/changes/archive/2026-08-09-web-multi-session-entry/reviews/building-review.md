# Building Review: web-multi-session-entry (Round 1)

## Reviewer

- run id: building-review-r1-0frj3kg8
- 时间: 2026-08-09
- 范围: 独立零记忆实现审阅。审阅对象 `git diff origin/master...HEAD`（实现提交 eaf58f0 为主要改动），已逐文件读取 `web/session.py`、`web/server.py`、`agent/config.py`、`agent/main.py`、`web/static/chat.js`、`web/static/index.html`、`web/static/style.css`、`web/static/debug.js`、`tests/web_tests/test_multi_session.py`、`tests/web_tests/test_multi_session_browser.py` 及 change 文档。未修改任何文件（仅产出本审阅报告，`reviews/**` 豁免路径）。

## Verdict

**CHANGES_REQUESTED**

核心功能真实实现且主路径测试通过，但存在 3 个需修复的中等问题：(1) tasks 2.2/2.3 勾选的测试覆盖存在过度声明——design review I5 明确要求的 per-tab 隔离 Playwright（审批/图片/reconnect/slash）在 `test_multi_session_browser.py` 中完全缺失，负向边界矩阵（符号链接/尾部斜杠/大小写）也仅部分覆盖；(2) `chat.js` `handleTabEvent` 在 `session_created` rekey 后 `activeTabId` 残留旧值 'new'，产生跨 tab 污染窗口与 tab 按钮标签错误；(3) artifact checker 当前报 `tasks hash mismatch`（design 阶段 manifest 的 tasks_hash 在 eaf58f0 勾选 tasks 后失效），PR 前必须清理。不构成 BLOCKED（无核心功能缺失、无安全漏洞、测试大面积通过）。

## Tasks Verification

- **2.1 后端集成测试**: 基本覆盖。`tests/web_tests/test_multi_session.py`（28 用例全过）覆盖：`/api/workspaces` 结构（`test_api_workspaces_lists_primary_and_allowlist`）、`/api/sessions` 列表结构/缺省主 workspace/403（`test_api_sessions_lists_primary_workspace`、`test_api_sessions_rejects_unauthorized_workspace`）、DELETE 内存+磁盘+冷会话+缺 workspace 400+未授权 403（4 用例）、`/ws/new` mode/workspace 创建/非法 mode/未授权 workspace/带参跳过 resume/裸 resume 语义（5 用例）、跨 workspace 互不串扰+确定性取主（`test_websocket_resume_without_workspace_searches_primary_first`）、per-session 互斥（`test_run_session_mutual_exclusion`）、进程重启恢复（`test_websocket_resume_with_workspace`，快照落盘→新 app 恢复）、恢复归属闭环（`test_websocket_resume_allowlist_rerun_stays_in_allowlist_store`，re-run 仍写 allowlist store 且主 store 不新增）、`/ws/{id}?workspace=` 未授权拒绝路径（error 事件+关闭+不创建）、reset 保留 workspace/mode。**小偏差**：task 文字写 `tests/web_tests/test_server.py`，实现把新用例放到了新文件 `test_multi_session.py`，可接受。
- **2.2 前端 Playwright smoke**: **部分覆盖（过度声明）**。已覆盖：hub 列表+点开进 tab 展示历史、多标签消息隔离、刷新回最近会话（localStorage）、删除会话关闭 tab、新建会话 mode 生效。**缺失**：task 明确列出的 per-tab 隔离（design review I5/I13）"两个 tab 各自触发审批/图片上传，卡片与预览只落各自 tab；一个 tab 结束（continue_session=false）不影响另一 tab 的 reconnect；两个 tab 的 slash 匹配状态互不串扰"——`test_multi_session_browser.py` 中没有任何审批/图片/reconnect/slash 相关用例（见 I1）。
- **2.3 负向/边界**: **部分覆盖（过度声明）**。已覆盖：`..` 穿越（`test_api_sessions_rejects_path_traversal`）、未授权路径 `/etc`（三个入口各一）、DELETE 缺 workspace 400、allowlist 空主 workspace 可用、不存在 allowlist 项启动 warning。**缺失**：符号链接拒绝、尾部斜杠、大小写变体的显式用例；`resolve_workspace()` 无直接单测（仅经端到端间接覆盖）；三个入口的负向矩阵不完整（见 I1）。
- **2.4 CLI 层级**: 覆盖。`test_cli_web_default_host_is_127_0_0_1` 断言默认 `127.0.0.1`、显式 `--host 0.0.0.0` 生效。`agent/main.py:661` 默认值已改，`display_host`（main.py:681）适配正确。
- **2.5 全量回归**: 未勾选（正常，本轮为审阅闭环非收尾）。本审阅实际跑了全量：1831 passed / 5 failed（MCP stdio fixture 环境失败，已在 origin/master 基线复现，与本次无关）/ 7 skipped。
- **3.1 `agent/config.py` WebConfig**: 真实实现。`WebConfig` frozen dataclass（config.py:261-270）+ `AsterwyndConfig.web` 字段（config.py:285）+ `_parse_web_config`（config.py:1205-1226，绝对路径校验、expandvars/expanduser、去重）。allowlist 空时有效集合={主 workspace}（SessionManager `_workspace_set`）。
- **3.2 `web/session.py`**: 真实实现。`_stores: dict[str, SessionStore]`（session.py:276）+ `_store_for`（278-289，key=`str(Path.resolve())`，None→cwd.resolve()）+ `resolve_workspace`（291-303，expanduser().resolve()+集合成员判断，None/空→主 workspace）+ `resume_session_async` workspace 参数与主→allowlist 确定性搜索（332-365，归属闭环：命中哪个 store 就用该 workspace 建 session）+ `remove_session` workspace 参数（485-495，冷会话按请求 workspace 删快照）+ `run_lock` 互斥（524-536，locked() 检查 + acquire()，无 await 间隙故原子）+ `reset` 保留 workspace/mode（server 层 532-539）。
- **3.3 `web/server.py`**: 真实实现。`GET /api/workspaces`（129-148，is_primary/exists/session_count）、`GET /api/sessions`（150-162，403 结构化拒绝）、`DELETE /api/sessions/{id}`（164-178，缺 workspace 400/未授权 403）、`/ws/new` mode/workspace 解析+校验（232-287，带显式参数跳过 resume、非法 mode/workspace 回 error+关闭）、`/ws/{id}?workspace=` 未授权拒绝（240-246）、`create_app` 启动解析有效集合+不存在 allowlist 项 warning（49-65）。
- **3.4 `agent/main.py`**: `--host` 默认 `127.0.0.1`（main.py:661），`display_host` 适配（main.py:681）。实现+CLI 测试齐备。
- **3.5 `web/static/chat.js`**: 真实实现。`tabs: Map` + `activeTabId`（5-6）、Tab 对象字段完整（9-38，含 approvalCards/questionCards/pendingImages/shouldReconnect/slashMatches/activeSlashIndex/debugIterBlocks 等）、`buildTabPane` 动态 per-tab DOM（112-164）、`bindActiveTab`/`syncActiveTab` 代理同步（166-217）、`handleTabEvent` 事件分发（392-405）、hub 视图（1683-1781）、恢复优先级 URL→localStorage→hub→新建（1784-1835）、不持久化 open_tabs。**存在 `handleTabEvent` rekey 后 activeTabId 残留 bug（见 I2）**。
- **3.6 `index.html`/`style.css`**: 真实实现。`#hub-view`（index.html:41-72）、标签栏容器 `#session-tabs`（21）、动态消息容器 `#chat-panes`（92）；style.css 补 hub/标签栏/动态容器样式。静态资产断言已更新（test_server.py）。

## Issues

- **I1（严重度: 中高）**: tasks 2.2/2.3 勾选的测试覆盖过度声明——per-tab 隔离与负向边界矩阵用例缺失。
  - 证据: `tasks.md:32`（2.2 明列"两个 tab 各自触发审批/图片上传……一个 tab 结束（continue_session=false）不影响另一 tab 的 reconnect；两个 tab 的 slash 匹配状态互不串扰"）；`tasks.md:36`（2.3 明列"符号链接、尾部斜杠、大小写变体……三个入口"）。`tests/web_tests/test_multi_session_browser.py` 全文件无任何 approval/image/reconnect/slash 用例（`rg` 无命中）；负向仅 `..` 穿越与 `/etc` 单点覆盖，无符号链接/尾部斜杠/大小写用例。
  - 影响: 这是 1451 行 `chat.js` 从全局单例重构为 per-tab 的最大回归面，design review I5 明确把审批/图片/reconnect 列为"必须"的 Playwright 覆盖，I13 要求 slash"building 阶段补一条"。勾选 [x] 但无对应测试 = 该任务未完成，且回归风险无兜底。实现侧 per-tab 字段已就位（`approvalCards`/`questionCards`/`pendingImages`/`shouldReconnect`/`slashMatches` 均为 Tab 字段），功能大概率正确，但缺测试证据。
  - 建议修复: 在 `test_multi_session_browser.py` 补：(a) 两个 tab 各自触发审批请求，approval 卡片只落各自 tab 的消息容器；(b) 图片上传预览跨 tab 隔离；(c) 一个 tab `/exit`（continue_session=false）后另一 tab 仍可重连/发送；(d) 两个 tab 的 slash 匹配状态互不串扰。负向补符号链接与尾部斜杠（三个入口至少各一）。
- **I2（严重度: 中）**: `chat.js` `handleTabEvent` 在 `session_created` rekey 后 `activeTabId` 残留旧值，产生跨 tab 污染窗口。
  - 证据: `web/static/chat.js:392-405`。新会话 tab 以 `'new'` 为 key 创建（`hubNewBtn` handler chat.js:1774），`session_created` 到达后 `handleTabEvent` 执行 `tabs.delete(tab.id); tab.id = sid; tabs.set(sid, tab)`，但**未同步 `activeTabId`**——若 `activeTabId === 'new'` 则此后 `getActiveTab()` 返回 null（`tabs.get('new')` 已删除）。`bindActiveTab` 内的 `renderSessionTabs`（197）在 rekey 前调用，tab 按钮停留在文本 "new"；rekey 后无重渲染。窗口期内 `syncActiveTab()`（200-217，`if (!tab) return`）空转，该 tab 的 inFlight/currentAssistantMsg 等不落回 tab 对象；若窗口期另一 tab 收到事件，`prevTab = getActiveTab()` 为 null，不 rebind 原 active tab，其 header chrome（sessionId/mode/status）被后台 tab 事件覆盖。
  - 影响: 新建会话后 tab 按钮短暂显示 "new" 而非 session id 前缀；新建会话后立刻切换 tab 会丢失该 tab 的 in-flight 状态同步；窄窗口内后台事件可污染 active tab 的 header。功能自愈（下次 switchTab/事件触发 bindActiveTab 纠正），但属真实 per-tab 状态不变量破坏。
  - 建议修复: rekey 后补 `if (activeTabId === tab.id) activeTabId = sid;`（在 `tabs.delete(tab.id)` 前记录旧 id），并调用 `renderSessionTabs()`。或在 `switchTab`/`bindActiveTab` 中对失效 activeTabId 兜底。
- **I3（严重度: 中，机械门禁）**: artifact checker 当前失败：`tasks hash mismatch`。
  - 证据: 运行 `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py` 输出 `ERROR: web-multi-session-entry: tasks hash mismatch`。`reviews/design-review-manifest.json` 的 `tasks_hash`（`sha256:8f6d7132...`）绑定的是设计阶段 tasks.md；实现提交 eaf58f0 勾选 2.x/3.x 修改了 tasks.md（`git diff 78475ae eaf58f0 -- .../tasks.md` 证实），导致 design manifest 校验失败（`agent/workflow/review_manifest.py:169-170`）。
  - 影响: PR 前 baseline CI 门禁（artifact checker）会拦截。设计阶段 manifest 在 tasks.md 因 building 合法演进后必然过期。
  - 建议修复: 审阅闭环 PASS 后生成 building-review-manifest.json 时，同步处理过期 design manifest——参照已归档 `openspec/changes/archive/2026-08-09-fix-issue-110/reviews/`（仅保留 building-review-manifest.json，无 design manifest）：删除或重算 design 阶段 review 证据，确保 artifact checker 全绿。
- **I4（严重度: 低）**: `DELETE /api/sessions/{id}` 对畸形/traversal session_id 未捕获 `ValueError`，返回 500 而非 4xx。
  - 证据: `web/server.py:164-178` 未 try/except；`remove_session`（web/session.py:489-491）→ `SessionStore.remove`（agent/session.py:184-191）→ `_validate_session_id`（agent/session.py:196-203）对绝对路径/穿越路径抛 `ValueError`。SessionStore 校验已阻止实际文件系统逃逸，故无安全洞，但恶意/错误 session_id 会 500。
  - 影响: 健壮性缺陷，非安全漏洞。畸形输入应返回结构化 4xx。
  - 建议修复: `api_delete_session` 捕获 `ValueError` 返回 `JSONResponse({"error": "invalid_session_id"}, status_code=400)`。
- **I5（严重度: 低）**: hub 新建会话快速连点两次时，第二个 `createTab('new', ...)` 覆盖 Map 中同 key，两个 pane 短暂同显 active。
  - 证据: `web/static/chat.js:1774`（`createTab('new', null, workspace, mode)`）与 `buildTabPane`（112-164）。tabId 固定 'new'，连点两次后 `tabs.set('new', tab2)` 覆盖 tab1，但 pane1 仍在 DOM 且未被反激活（`switchTab` 只对 Map 内 tab 切换 active 类）。
  - 影响: 快速双击"新建"时 UI 短暂显示两个 active pane，随后 session_created rekey 自愈。边缘 UX 缺陷。
  - 建议修复: 为每次新建使用唯一临时 tab id（如 `new-<counter>` 或 `crypto.randomUUID()`），rekey 时仍按 session_id 归位。
- **I6（严重度: 低，文档口径）**: spec delta 措辞"workspace SHALL 命中 allowlist 且路径存在"（specs/web-ui/spec.md:31）与 `resolve_workspace` 只做集合成员判断、不做运行期 `Path.exists()` 复检的实现存在轻微差异。
  - 证据: `web/session.py:291-303`（无 exists 复检）；design D4/I14 已明确"集合启动时一次性解析，`/api/workspaces` 的 `exists` 是唯一运行期反映"。
  - 影响: 启动后目录被删的 allowlist 项仍在有效集合，请求仍通过校验（设计已接受此口径）。属已知决策，非新缺陷；如需完全对齐可在 spec scenario 补一句"路径存在性以启动时解析为准"。
  - 建议修复: 可选——spec delta 措辞与 design D4/I14 口径对齐，避免审阅歧义。

## Test Results

- `python3 -m pytest tests/web_tests/test_multi_session.py tests/web_tests/test_multi_session_browser.py -q` → **28 passed** (8.58s)
- `python3 -m pytest tests/web_tests/test_server.py tests/web_tests/test_browser.py -q` → **46 passed, 7 skipped**（skipped 为 real_api opt-in）
- `python3 -m pytest tests/web_tests/ -q` → **105 passed, 7 skipped**
- `python3 -m pytest tests/web_tests/ tests/test_cli.py -q` → **148 passed, 7 skipped**
- 全量 `python3 -m pytest -q --ignore=tests/agent/code_intelligence/test_tree_sitter_symbols.py` → **1831 passed, 5 failed, 7 skipped**。5 个失败均为 `tests/agent/mcp/test_mcp_manager.py` stdio fixture server 无法启动（`/usr/lib/python3.12/subprocess.py: FileNotFoundError`）；已用 `git worktree add --detach /tmp/verify-master-117 origin/master` 在基线复现同一 5 个失败（5 failed, 6 passed），确认是**环境/pre-existing 失败，与本次 change 无关**（diff 未触及 agent/mcp 任何代码）。临时基线 worktree 已 `git worktree remove` 清理。
- `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py` → **ERROR: web-multi-session-entry: tasks hash mismatch**（见 I3，PR 前须清理）。

## 结论

- 实现质量总体良好：后端按 workspace 分区存储/恢复/删除/互斥/reset 保留语义均正确实现且有集成测试兜底；前端 per-tab 重构采用"全局代理 + bindActiveTab/syncActiveTab"模式，方向清晰，per-tab 字段完整；安全边界（`resolve_workspace` 三入口全覆盖 + SessionStore session_id 校验 + host 默认 127.0.0.1）无绕过。
- **不可直接 PASS**：I1（测试覆盖过度声明，design review I5 明确要求的 per-tab 隔离测试缺失）、I2（`handleTabEvent` rekey 后 activeTabId 残留，跨 tab 污染窗口）、I3（artifact checker 当前失败）三处需修复。
- 建议进入 Round 2 前修复 I1/I2/I3；I4/I5 为低项可一并处理，I6 为文档口径可选项。修复后重跑本审阅判定 PASS 或继续收敛。

未修改任何文件（仅写入本审阅报告）。

## Round 2

- run id: building-review-r2-0frj3kg8
- 时间: 2026-08-09
- 范围: 零记忆再审。审阅对象 `git diff origin/master...HEAD`（修复提交 e40a550），逐文件核对修复 diff、`web/static/chat.js`、`web/server.py`、`web/session.py`、`agent/session.py`、`tests/web_tests/test_multi_session.py`、`tests/web_tests/test_multi_session_browser.py`、`tasks.md`、`reviews/design-review-manifest.json`。仅写入本审阅报告（`reviews/**` 豁免路径），未修改其他任何文件。

### Verdict

**PASS**

Round 1 必须修 issue（I1/I2/I4/I5）均已修复并有代码+测试证据；I3 为 PASS 收尾期机械门禁（生成 building-review-manifest 时同步处理），本轮已确认 tasks.md 变更与代码一致；I6 无新问题。新发现 I7（低，pre-existing 的 pane.dataset 残留）与 I8（低，测试恒真断言）均不构成中等以上问题。目标测试文件 82 passed，全量 web_tests + CLI 157 passed / 7 skipped。

### Round 1 修复核对

- **I1（已修复）**: per-tab 隔离与负向矩阵用例已补齐且真实有效。
  - Playwright 4 用例（`test_multi_session_browser.py`）：slash 匹配隔离 `test_multi_tab_slash_suggestion_isolation`（223-255，tab1 切走后建议 hidden、切回仍在）；图片预览隔离 `test_multi_tab_image_preview_isolation`（259-288，tab2 上传 PNG 出预览、tab1 预览数 0）；/exit reconnect 隔离 `test_multi_tab_exit_does_not_affect_other_tab_reconnect`（292-327，tab2 /exit 后 tab1 仍 connected 且收发成功）；approval 卡片隔离 `test_multi_tab_approval_isolation`（331-388，tab2 触发 Bash 审批、tab1 卡片数 0）。逐个验证非空跑：均含真实操作与断言。
  - 负向 5 用例（`test_multi_session.py`）：symlink 穿越（133-144）、尾部斜杠归一化（147-157）、大小写变体（160-170）、不存在路径（173-182）、DELETE 畸形 session_id（241-249）。均通过。
  - `tasks.md:32`（2.2）与 `:36`（2.3）声明与上述测试一致，不再过度声明。小口径说明：负向矩阵全量集中在 `/api/sessions` 入口，`/ws/new` 与 `/ws/{id}?workspace=` 各有一个未授权负向用例（`test_websocket_new_rejects_unauthorized_workspace`、`test_websocket_resume_rejects_unauthorized_workspace`）——三者共用 `resolve_workspace()`，满足 Round 1 建议"三个入口至少各一"。
- **I2（已修复）**: `chat.js:397-407` rekey 分支补 `const oldId = tab.id; tabs.delete(oldId); ... if (activeTabId === oldId) activeTabId = sid; renderSessionTabs();`。逐分支推演正确：(a) active tab rekey（`activeTabId === 'new-N'`）→ activeTabId 同步为 sid，renderSessionTabs 修正 tab 按钮文本；(b) background tab rekey → activeTabId 不变，末尾 `if (prevTab && ...) bindActiveTab(prevTab)` 正确恢复原 active。`getActiveTab()` 不再返回 null，I2 描述的跨 tab 污染窗口已关闭。
- **I3（收尾期处理，本轮确认一致）**: `scripts/check_openspec_artifacts.py` 仍报 `tasks hash mismatch` + `review manifest missing: building-review-manifest.json`（后者为 PASS 后才生成的产物，属预期）。`reviews/design-review-manifest.json` 的 `tasks_hash`（`sha256:8f6d7132...`）绑定设计阶段 tasks.md，building 勾选 + 新增"审阅修复记录"节后必然过期。已核对 tasks.md 变更与代码一致：审阅修复记录 I1-I6 逐条对应 e40a550 实际改动；2.2/2.3 勾选与测试事实吻合。PASS 收尾生成 building-review-manifest 时按 Round 1 建议删除/重算过期 design manifest（参照 archive `fix-issue-110` 仅留 building manifest 的先例）即可全绿。
- **I4（已修复）**: `web/server.py:178-182` 捕获 `ValueError` 返回 400 `{"error":"invalid_session_id"}`。经验证可达、非死代码：`DELETE /api/sessions/%2e%2e?workspace=<tmp>` → **400** `{"error":"invalid_session_id"}`（encoded `..` 过路由但被 `agent/session.py:196-203 _validate_session_id` 拒绝）；绝对路径 → 404（路由层）。测试 `test_api_delete_rejects_invalid_session_id` 断言 `status in (400, 404)` 且非 500。小改进提示（不阻塞）：该用例 URL `..%2F..%2Fetc` 实际走 404，未直接断言 handler 400 分支，可用 `%2e%2e` 显式覆盖 400。
- **I5（已修复）**: `chat.js:7` 新增 `newTabSeq` 计数器，`chat.js:1779-1783` hub 新建改用 `new-${newTabSeq}` 唯一临时 id 并 `switchTab(tempId)`。连点两次分别生成 `new-1`/`new-2`，不再覆盖 Map 键，第二个 pane 切换时正确反激活第一个。
- **I6（无新问题）**: spec delta "路径存在"措辞与 `resolve_workspace` 集合成员判断的口径差异仍为 design D4/I14 已知决策，可接受，无新增影响。

### 新发现问题

- **I7（低，pre-existing 未覆盖）**: rekey 后 `pane.dataset.tabId` 残留临时 id。`chat.js:116` 仅在 `buildTabPane` 设置 `pane.dataset.tabId = tab.id`，rekey 分支（397-407）未同步，新建会话 tab 重键为真实 sid 后 pane 的 dataset 仍是 `new-N`。paste（`chat.js:1114`）与 drag-drop（`chat.js:1171`）经 `tabs.get(pane.dataset.tabId)` 反查 tab → 返回 undefined → 图片粘贴/拖拽在新建 tab 上静默失效（upload 按钮路径经闭包绑定 tab.id，不受影响）。该问题在 eaf58f0 即存在，非本轮修复引入；严重度低（边缘路径，主上传按钮可用）。建议 rekey 时同步 `pane.dataset.tabId = sid`，或 paste/drop 改用 pane 对象身份反查。
- **I8（低，测试质量）**: `test_multi_tab_exit_does_not_affect_other_tab_reconnect:312-314` 的 `wait_for_function("document.querySelector('#status').textContent !== 'connected' || true")` 恒真（`X || true`），是无效断言。不影响该用例整体有效性（后续切回 tab1、等待 connected、发送并收到 assistant 回复仍真实验证 reconnect 隔离），建议删除该行或改为 `=== 'ended'`。

### Test Results

- `python3 -m pytest tests/web_tests/test_multi_session.py tests/web_tests/test_multi_session_browser.py tests/web_tests/test_server.py -q` → **82 passed** (16.01s)
- `python3 -m pytest tests/web_tests/test_multi_session_browser.py -v -q` → **9 passed**（确认 4 个 per-tab 隔离 Playwright 用例实际执行，非 skip）
- `python3 -m pytest tests/web_tests/ tests/test_cli.py -q` → **157 passed, 7 skipped**（7 skip 为 real_api opt-in，与 Round 1 基线一致；157 = Round 1 148 + 新增 9）
- `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py` → 仍报 `ERROR: web-multi-session-entry: tasks hash mismatch` + `review manifest missing: building-review-manifest.json`（I3，PASS 收尾期生成 manifest 时处理）

### 结论

- **可进入 PASS**。Round 1 必须修 issue 全部修复并有证据；I3 属 PASS 收尾流程内的机械门禁（生成 building-review-manifest 时重算/删除过期 design manifest，按 archive fix-issue-110 先例）；无新中等以上问题。
- I7/I8 为低严重度跟进项，建议收尾期或后续 change 顺手修复（rekey 同步 pane.dataset + 删除恒真断言），不阻塞本 change 合入。
- 未修改任何文件（仅写入本审阅报告）。
