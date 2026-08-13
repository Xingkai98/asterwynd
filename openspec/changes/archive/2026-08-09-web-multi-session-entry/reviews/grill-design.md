# Grill: web-multi-session-entry 设计追问

## Reviewer

- run id: `3ce55d3d-83be-49ec-9307-412f79872d9f`
- 时间: 2026-08-09
- 范围: 独立零记忆审问。只读 `proposal.md` / `design.md` / 相关实现代码，仅产出本决策记录，未修改任何其他文件。

## Confirmed Decisions

- **决策**: D1 复用 `SessionStore.list_sessions()` 作为 hub 列表数据源是正确且零新序列化层的方案。
  理由: `list_sessions`（`agent/session.py:143-182`）已返回 `session_id/created_at/updated_at/mode/messages`，按 `updated_at` 倒序，并从 `messages.json` 补算消息数；API 层只需追加 `workspace` 字段。已核实该方法对损坏快照逐条容错（`continue`），不会因单个坏快照拖垮整个列表。
  来源: `agent/session.py:143-182`；`design.md D1`。

- **决策**: D2 新建会话走 WS 查询参数（`/ws/new?mode=&workspace=`）可行且与现状"连接即创建"模型衔接。
  理由: `web/server.py:169-185` 现状就是"连接即创建"，`create_session_async` → `_create_session` 已具备 `initial_mode` kwarg（`web/session.py:316-319`），mode 参数可直接线程化；workspace 参数经 D3 的 `_create_session(workspace_root=...)` 线程化。模式校验可用 `parse_agent_mode`（`web/session.py:19` 已导入）。
  来源: `web/server.py:169-185`；`web/session.py:316-319, 20`；`design.md D2`。

- **决策**: D3 per-session workspace 与 store map（`_stores: dict[str, SessionStore]`）方向正确，`WorkspacePolicy` 与 `AgentLoop.session_store` 均已支持按 session 注入。
  理由: `WorkspacePolicy(workspace_root=...)` 本就是构造参数（`agent/workspace_policy.py:141-147`），`_create_session` 已把 `session_store` 传给 `AgentLoop`（`web/session.py:364`），`remove_session` 也已在 `store.remove` 前 pop 内存（`web/session.py:379-382`）。把单例 store 换成按 resolved workspace 的惰性 map，改动集中在 `web/session.py` 一处。
  来源: `web/session.py:264-265, 364, 379-382`；`agent/workspace_policy.py:141-147`；`design.md D3`。

- **决策**: D4 allowlist 的安全比较基准（输入侧 `Path.expanduser().resolve()` + 集合成员判断）与现有 `_resolve_workspace` 语义一致，`SessionStore._validate_session_id` 已兜底 session_id 穿越。
  理由: `_resolve_workspace`（`agent/main.py:201-211`）对 workspace 用 `expanduser().resolve()` 且要求绝对路径 + 存在；`SessionStore._validate_session_id`（`agent/session.py:196-203`）用 `realpath` + `commonpath` 拒绝绝对 id 与路径穿越。故输入侧 resolve 化能防 `..` 与尾部斜杠，store 侧防 id 穿越。**注意：该决策的校验清单不完整，见风险 R1。**
  来源: `agent/main.py:201-211`；`agent/session.py:196-203`；`design.md D4`。

- **决策**: D6 前端恢复优先级（URL `?session=` → localStorage → hub → 新建）与 issue #110 现状一致，扩展 workspace 记忆合理。
  理由: `chat.js:1430-1434` 现已是 `urlSession || localStorage.getItem('asterwynd.session_id') || null`，D6 只是在其上叠加 `?workspace=` 与 `asterwynd.session_workspace`。对齐 canonical resolution 原则无实现障碍。
  来源: `chat.js:1430-1434`；`design.md D6`。

- **决策**: D7 的 uploads 隔离机制在现状中已存在大半——`save_upload_bytes` / `create_image_message` / `create_image_message_from_upload` 均已带 `workdir` 参数。
  理由: `agent/uploads.py:92-115` 的 `save_upload_bytes(data, mime, *, workdir=None)`、`:124-156` 的 `create_image_message` / `create_image_message_from_upload` 均支持 `workdir`。D7 不需要新增"可传参"，只需要把 `session.workspace_root` 线程到调用点。**但设计漏了 HTTP `/api/uploads` 端点没有 workspace 上下文，见风险 R4。**
  来源: `agent/uploads.py:92-115, 124-156`；`design.md D7`。

- **决策**: D8 per-session run 互斥是必要且成本最低的收口点——`AgentLoop.run` 确无 running guard，issue #110 grill Q1 已确认把并发污染留给 #117。
  理由: `agent/loop.py:493-527` 的 `run()` 直接改 `self._active_on_event` / `_active_trace_recorder` 等共享状态，无锁/忙标志；#110 grill 的 Q1 用户确认"接受风险留给 #117"。本 change 引入多标签后同一 session 并发 chat 是真实路径，须互斥。**但 D8 的"检查后加锁"写法有竞态，见风险 R3。**
  来源: `agent/loop.py:493-527`；`archive/2026-08-09-fix-issue-110/reviews/grill-design.md` Q1/Q5；`design.md D8`。

- **决策**: WebConfig 作为 `AsterwyndConfig` 新 frozen dataclass 字段（缺省 `WebConfig()`，`workspaces=()`）不会破坏现有未配置用户的行为。
  理由: `AsterwyndConfig`（`agent/config.py:262-310`）各字段均有 `default_factory`，`__post_init__` 只补 `modes`/`skills` 默认（`:275-281`）；新增字段走 `field(default_factory=WebConfig)` 即可，`_load_yaml_config`（`:373-406`）加一个 `_parse_web_config` 分支。allowlist 空时有效集合 = {主 workspace}，与现状等价。
  来源: `agent/config.py:262-310, 373-406`；`design.md D4`。

## Open Questions

设计已列 6 个（Q1-Q6）。逐一评审是否充分并给出推荐答案，再补充新发现的 7 个（Q7-Q13）。

- **Q1（host 默认绑定策略）**: 本 change 是第一个把 workspace 边界 + 多会话 + mode 选择（含 bypass）暴露到 Web 的变更，`0.0.0.0` 下局域网任意访问者可在 allowlist 目录内建 bypass 会话并执行任意工具（免审批）。推荐: **本 change 内把默认 host 改为 `127.0.0.1`**（`agent/main.py:661` `--host` 默认值），显式 `--host 0.0.0.0` 才开放 LAN；这与"最小行为变化"相比只是要求想开 LAN 的用户多传一个参数，安全收益大。若用户坚持保留 `0.0.0.0` 默认，则必须接受 (a) + 显著文档警告，且不应在本 change 引入 bypass+多 workspace 的同时不做任何收紧。

- **Q2（uploads 归属）**: 推荐: **本次保持全局 `<cwd>/.asterwynd/uploads`，推迟隔离**。理由: (1) D7 的隔离路径存在 HTTP 上传端点无 workspace 上下文的缺口（见 R4），本次实现成本高、回归面大；(2) 上传仅图片文件，按 sha256 去重，全局归属无安全边界问题；(3) `file_path` 是绝对路径（`agent/uploads.py:115`），跨 workspace 恢复图片引用仍有效。隔离的"目录模型一致性"收益不足以覆盖本次改动成本，建议记入 backlog 后续单独做。

- **Q3（hub 列表范围）**: 推荐: **按当前选中 workspace 展示（默认主 workspace）**，与设计一致。会话按 workspace 分区（D3）后，跨 workspace 聚合会模糊"会话归属"语义，删除/恢复路径也要跨 store 解释；per-workspace 列表 + workspace 选择器最清晰，且与"会话归属 workspace 目录"的主流语义（Claude Code 按启动目录分区）对齐。

- **Q4（新建会话 API 形态）**: 推荐: **WS 查询参数**，与设计一致。避免"POST 成功但 WS 失败"的孤儿 session 竞态，且衔接现状连接即创建。**但必须同时处理 R2**：`/ws/new` 带显式 mode/workspace 时不得被 `app.state.resume_session_id` 拦截（否则 `--resume` 启动下 hub 新建按钮永远打开 resume 会话）。

- **Q5（per-session run 互斥）**: 推荐: **本次实现**，但按 R3 用 `run_lock.acquire_nowait()`（或 `asyncio.wait_for(lock.acquire(), timeout=0)` 捕获超时）替代"检查后 `async with`"的竞态写法；拒绝时回发 error 事件，且拒绝路径不得让 WS 连接挂起。锁作用域应覆盖 `run_session` 全程（含 queue drain），保证共享 AgentLoop 状态不被并发触碰。

- **Q6（删除会话）**: 推荐: **hub 提供删除**，与设计及 proposal 验收一致。`remove_session` 已具备内存 pop + 磁盘快照移除（`web/session.py:379-382`），成本低。**需补充 R9**：删除会话时若存在打开的同 id tab，前端应关闭对应 tab（或服务端广播 `session_deleted` 事件），避免"列表消失但 tab 还在跑"的悬空状态。

- **Q7（resume 路径的 workspace 校验）**: 新增。D4 的校验清单只列了 `/api/sessions query` 与 `/ws/new query`，遗漏 `/ws/{id}?workspace=`（D3 resume 与 D6 前端 open-tab 都用它）。未校验时攻击者可把 workspace 指向任意目录（如其他用户项目下的 `.asterwynd/sessions`），读取/恢复其会话历史，或以该目录为 workspace_root 建会话。推荐: 把所有用户可控 workspace 输入收敛到单一 `SessionManager.resolve_workspace(input) -> Path | 拒绝`，全部入口（`/api/sessions`、`/ws/new`、`/ws/{id}`、若 D7 采纳则 `/api/uploads`）统一走它。

- **Q8（`--resume` 与 hub 新建会话冲突）**: 新增。`app.state.resume_session_id` 每次 `/ws/new` 都命中且消费后不清空（#110 grill Q5 用户确认保留该行为）。多会话下 hub"新建会话"按钮连 `/ws/new` 会被 resume_target 拦截，静默打开 resume 会话而非新建。推荐: `/ws/new` 携带任意显式参数（mode 或 workspace）时跳过 `resume_target` 分支直接新建；仅裸 `/ws/new` 保留 resume 语义。

- **Q9（reset 丢失 workspace）**: 新增。`reset`（`web/server.py:424-433`）`remove_session` 后 `create_session_async(llm)` 用 manager 默认 workspace/mode，会把非主 workspace 会话的替换品建到主 workspace。推荐: reset 前记录 `session.workspace_root` 与 `current_mode`，替换会话用同 workspace + 同 mode 创建。

- **Q10（`open_tabs` 持久化语义）**: 新增。D5 把 `asterwynd.open_tabs` 写入 localStorage，但 D6 刷新只重连最近会话，open_tabs 在刷新后成为"显示未连接 tab"的装饰数据；若刷新时重连全部 open_tabs，则一次刷新拉起 N 条 WS 连接（资源 + 服务端并发会话暴涨）。推荐: **不持久化 open_tabs**——tab Map 只活在当前页面（in-memory），刷新仅恢复最近会话（localStorage 的 `session_id` + `session_workspace`）。与 canonical resolution 原则一致。

- **Q11（per-tab 状态完整性）**: 新增。D5 的 Tab 对象列了 sessionId/workspace/mode/ws/currentAssistantMsg/debugEvents/planningState/planDocState/messagesEl/statusEl/inFlight/uploadWaiters，但遗漏：`approvalCards`、`questionCards`（`chat.js:14-15`）、`pendingImages`（`chat.js:16`）、`shouldReconnect`（`chat.js:13`）、`slashMatches`/`activeSlashIndex`（`chat.js:11-12`）、debug 侧 `iterBlocks`（`debug.js:6`）。这些保持全局会跨 tab 串扰（审批卡片更新错 tab、图片预览串 tab、`shouldReconnect=false` 全局禁用重连、debug 块串 tab）。推荐: Tab 对象补齐上述字段；`slashCommands`（全局目录）可保留全局，但匹配状态 per-tab；`debug.js` 的 `renderDebug`/`renderTimeline` 改为从 active tab 取 `debugEvents`/`iterBlocks`/`sessionId`。

- **Q12（恢复路径的 session_id 归属校验）**: 新增。D3 `resume_session_async(session_id, workspace=None)` 未带 workspace 时"依次搜主 + allowlist stores，首个命中即恢复"。session_id 为 `uuid4().hex[:12]`（`agent/run_identity.py:5-6`，48 位熵），跨 workspace 碰撞概率可忽略，误恢复风险低；但搜索顺序必须确定（主 → allowlist 配置序），且 `_store_for` 的 key 必须是 `str(Path.resolve())` 规范化后的值，避免同一目录因写法不同产生两个 store。推荐: 明确搜索顺序与 key 规范化，并在测试中覆盖"两个 workspace 都有同名 store 时按序取主"的确定性。

- **Q13（spec delta 边界）**: 新增。当前 `openspec/changes/web-multi-session-entry/specs/` 为空，design 未描述 delta 内容。现有 `openspec/specs/web-ui/spec.md` 已有 `Requirement: Web 每个 session 维护独立状态`（两个 session 并发场景）与 `Requirement: Web session 本地持久化与恢复`。delta 需新增：hub 列表 API（`/api/workspaces`、`/api/sessions`）、`/ws/new` 的 mode/workspace 参数、workspace allowlist 拒绝、per-session run 互斥、多标签并行、删除会话、恢复优先级扩展 workspace。推荐: 把"同一 session 并发发送被拒绝"作为新 requirement 写入 delta，并同步 `docs/openspec-change-backlog.md` 登记 issue #117（当前 backlog 尚未登记，见任务 #6）。

## 风险

按严重度排序（均为本次 grill 新发现；design.md 已列的网络暴露 / 前端重构回归 / 恢复歧义 / session_history 全量重发等不再重复）。

- **R1（严重）— workspace 校验清单不完整，resume 路径可绕过 allowlist**。D4 只列 `/api/sessions` 与 `/ws/new`，但 `/ws/{id}?workspace=`（D6 open-tab 与 D3 resume 都走它）不在清单内。未校验的 workspace 输入可指向任意目录：从其他用户的 `.asterwynd/sessions` 读/恢复会话历史，或以任意目录为 workspace_root 建会话。缓解: 单一 `resolve_workspace()` 覆盖全部入口（Q7）；测试覆盖 `..`、符号链接、尾部斜杠、大小写、不存在路径、allowlist 外路径。
- **R2（严重）— `--resume` 每连必中与 hub 新建会话直接冲突**。`app.state.resume_session_id` 消费后不清空（#110 grill Q5 确认保留），多会话下所有经 `/ws/new` 的"新建"都会静默变成 resume 指定会话，hub 新建表单形同虚设。缓解: `/ws/new` 带显式参数时跳过 resume_target（Q8）。
- **R3（高）— D8 互斥存在 check-then-act 竞态**。`if run_lock.locked(): 拒绝` 与 `async with run_lock:` 之间非原子，两个并发 caller 都可通过检查，第二个阻塞在 `async with` 上导致其 WS 连接挂起（首个 run 可能持续数分钟）。缓解: `acquire_nowait()` / `wait_for(..., timeout=0)`，失败回发 error 事件且不阻塞（Q5）。
- **R4（高）— D7 的 HTTP `/api/uploads` 端点无 workspace 上下文**。`/api/uploads`（`web/server.py:139-162`，save 在 `:151`）先于消息发送，请求不带 session/workspace；若按 D7 隔离，前端须在 upload 请求携带 workspace（query/header）才能写对目录，设计未提及；而 `run_session` 的 `create_image_message_from_upload(upload_id)`（`web/session.py:430`）与 `create_image_message`（`:434`）也需按 session workspace 传 workdir，否则读写目录不一致。缓解: Q2 若选隔离则补上 HTTP 上传的 workspace 线程与对应回归；若选全局则维持现状（R4 消除）。
- **R5（中）— 前端 per-tab 重构遗漏状态字段导致跨 tab 串扰**。`approvalCards`/`questionCards`/`pendingImages`/`shouldReconnect`/`slashMatches`/`activeSlashIndex`/`iterBlocks` 若保持全局：审批/问题卡片更新可能落到非 active tab 的消息容器；图片预览跨 tab 串；一个 tab 结束（continue_session=false）会让全 app `shouldReconnect=false`；debug 块跨 tab 复用。缓解: Tab 对象补齐（Q11），Playwright 覆盖"两 tab 各自审批/上传/结束"。
- **R6（中）— `open_tabs` localStorage 语义不清**。要么刷新后显示未连接 tab（装饰数据），要么刷新拉起 N 条 WS 连接（并发会话与资源问题）。缓解: 不持久化 open_tabs，仅内存 tab Map（Q10）。
- **R7（中）— reset 替换会话丢失 workspace/mode**。非主 workspace 会话 reset 后替换品建到主 workspace、用 manager 默认 mode。缓解: reset 保留原 workspace/mode（Q9）。
- **R8（中）— 0.0.0.0 + bypass + 多 workspace 放大远程执行面**。局域网任意访问者可在 allowlist 内目录建 bypass 会话执行免审批工具（含 `Bash` 等）。缓解: Q1 改默认 `127.0.0.1` 或加 token。
- **R9（低）— 删除会话时已打开 tab 悬空**。hub 删除某 session，但该 session 的 tab 仍连接且可继续 chat；刷新后列表消失但内存 session 仍活着，行为不一致。缓解: 删除时前端关闭同 id tab（Q6）。
- **R10（低）— 恢复搜索的确定性未定义**。`resume_session_async` 未带 workspace 时按主→allowlist 搜索，key 必须用规范化 resolved 路径，否则同一目录因写法不同产生多个 store。缓解: 明确 key 规范化与搜索顺序，测试覆盖（Q12）。
- **R11（低）— hub 每次请求全量扫描磁盘**。`/api/workspaces` 对每个 workspace 调 `list_sessions()`，会话多时每次渲染都读盘。缓解: 接受现状，后续可加缓存；不在本 change 引入。
- **R12（低）— allowlist 中不存在的路径被静默排除**。用户拼错 allowlist 路径时，`/api/sessions` 与 `/ws/new` 一律 403，无启动期提示，难以排查。缓解: `create_app` 启动时对不存在的 allowlist 项打 warning 日志。
- **R13（低）— 前端 per-tab 重构的 DOM 单例**。`chat.js:31-53` 的 DOM refs（`messagesEl`、`userInput`、`planningItemsEl`、`imagePreviewsEl` 等）全部是单例元素；per-tab 需要动态消息容器（`#messages-<id>`）与 per-tab 输入/图片预览，但 planning/debug 面板是全局 chrome。设计应明确哪些 DOM 动态生成、哪些仍全局、切换 active tab 时如何重绑。缓解: D5 补一段 DOM 结构说明，Playwright 覆盖切换 tab 后 planning/plan-document 面板跟随。

## User Confirmation

以下为开发主 agent 将 `## Open Questions` 停轮抛给用户的逐项确认（grill-confirmation-gate），全部答复按 grill 推荐采纳。确认时间: 2026-08-09。

- **Q1**: 用户答复：改默认 `127.0.0.1`（显式 `--host 0.0.0.0` 才开放 LAN）；确认时间: 2026-08-09
- **Q2**: 用户答复：保持全局 `<cwd>/.asterwynd/uploads`，隔离推迟到后续；确认时间: 2026-08-09
- **Q3**: 用户答复：hub 按当前选中 workspace 展示（默认主 workspace）；确认时间: 2026-08-09
- **Q4**: 用户答复：新建会话走 WS 查询参数 `/ws/new?mode=&workspace=`，带显式参数时跳过 `--resume` 拦截；确认时间: 2026-08-09
- **Q5**: 用户答复：实现 per-session run 互斥（`acquire_nowait()` 修竞态）；确认时间: 2026-08-09
- **Q6**: 用户答复：hub 提供会话删除（内存 + 磁盘快照，删除时关闭同 id tab）；确认时间: 2026-08-09
- **Q7**: 用户答复：采纳单一 `resolve_workspace()` 覆盖 `/api/sessions`、`/ws/new`、`/ws/{id}?workspace=` 全部入口；确认时间: 2026-08-09
- **Q8**: 用户答复：采纳 `/ws/new` 带显式参数时跳过 `resume_target`；确认时间: 2026-08-09
- **Q9**: 用户答复：采纳 reset 保留原 session 的 workspace/mode；确认时间: 2026-08-09
- **Q10**: 用户答复：采纳 tab Map 仅内存、刷新只恢复最近会话（open_tabs 不持久化）；确认时间: 2026-08-09
- **Q11**: 用户答复：采纳 Tab 补齐 approvalCards/questionCards/pendingImages/shouldReconnect/slashMatches/iterBlocks 字段；确认时间: 2026-08-09
- **Q12**: 用户答复：采纳 store key 用 `Path.resolve()` 规范化 + 搜索顺序主→allowlist 配置序；确认时间: 2026-08-09
- **Q13**: 用户答复：采纳 spec delta 按推荐边界（hub 列表 API、`/ws/new` mode/workspace、allowlist 拒绝、per-session 互斥、多标签、删除、恢复优先级扩展）并登记 backlog；确认时间: 2026-08-09
