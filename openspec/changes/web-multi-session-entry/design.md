# Design: Web 多 session 入口页

关联跟踪 issue：[#117](https://github.com/Xingkai98/asterwynd/issues/117)。

## Context

issue #110（PR #118）已为 Web 补齐"本地持久化 + 按 id 恢复"：`SessionManager` 持有单例 `SessionStore`（`<workspace or cwd>/.asterwynd/sessions`），每次 run 落盘；WebSocket `/ws/<id>` 未命中内存时从快照恢复，前端 localStorage 记忆最近 session id。

但 Web 交互仍是**单会话单标签**：

- `web/session.py:247-265`：`SessionManager` 只有一个全局 `workspace_root`，所有 session 共享同一 SessionStore 根。
- `web/static/chat.js:4-29`：顶层单例全局状态（`ws`、`sessionId`、`messagesEl`、`currentAssistantMsg` 等），同一时刻一个 WebSocket、一个消息容器。
- 没有会话列表页、没有多标签切换、新建会话不能选 mode/workspace。

本 change 把会话提升为一等公民：hub 列表 + 多标签 + 按 workspace 组织 + 新建可选 mode/workspace。后端改动集中在 `web/session.py` 与 `web/server.py`（把单例 store 改成按 workspace 的 store map），前端改动集中在 `chat.js`（单例状态重构为 per-tab 模型）。

## Goals / Non-Goals

### Goals

- 提供 hub 入口页，列出已保存会话（session_id、mode、创建/更新时间、消息数），复用 `SessionStore.list_sessions()`。
- 多标签：每个会话独立 WebSocket、消息历史与运行状态；可切换、可关闭。
- 新建会话可选 mode 与 workspace；workspace 必须命中 allowlist。
- 会话按 workspace 分区存储与恢复（`<workspace>/.asterwynd/sessions/<session_id>/`），刷新/重启后可恢复。
- 保留并增强 issue #110 的恢复链路（URL 显式恢复 → localStorage 最近会话 → hub → 新建）。

### Non-Goals

- 不做多用户鉴权、登录、RBAC；workspace 边界用 allowlist + 路径校验保证。
- 不做跨浏览器/跨设备同步（无数据库，本地文件系统为准）。
- 不做 Web session memory 的磁盘持久化（`MemoryManager` 保持内存态）。
- 不改 debug 视图 / slash command / mode 切换机制本身，只让其按 active tab 数据源工作。
- 不做会话重命名/归档/导出等高级管理；删除是唯一管理操作（内存 + 磁盘快照）。
- 不做"标签页关闭后 run 继续在后台跑"（run 生命周期仍绑定发起 tab 的 WebSocket，沿用现状）。

## Decisions

### D1: Hub 数据 API

新增两个只读 HTTP 端点 + 一个删除端点：

- `GET /api/workspaces` → `{"workspaces": [{"path": "<abs>", "is_primary": bool, "exists": bool, "session_count": int}]}`。有效 workspace 集合 = 主 workspace ∪ allowlist（见 D4），按 allowlist 顺序排列，主 workspace 置顶。`exists` 在响应时对每个条目实时 `Path.exists()` 判断（集合启动时一次性解析，`exists` 反映运行期目录状态），避免恒真字段（design review I7）。
- `GET /api/sessions?workspace=<path>` → `{"workspace": "<resolved>", "sessions": SessionStore.list_sessions()}`。缺省 `workspace` 用主 workspace。workspace 不在有效集合或路径不存在 → HTTP 403 + `{"error": "workspace_not_allowed"}`。
- `DELETE /api/sessions/{session_id}?workspace=<path>` → `{"deleted": true, "session_id": <id>, "workspace": "<resolved>"}`。workspace 必须显式传入并经 `resolve_workspace()` 校验（hub 删除一个未打开过的冷会话是常态，冷会话没有内存 `session.workspace_root` 可查，必须由请求携带）；缺 `workspace` 参数 → HTTP 400 + `{"error": "missing_workspace"}`；未授权 → HTTP 403 + `{"error": "workspace_not_allowed"}`（design review I15）。删除内存中的 session（若在）与该 workspace store 下的磁盘快照。删除后若存在打开的同 id tab，前端关闭该 tab（对齐 D5）。

理由：直接复用 `SessionStore.list_sessions()`（`agent/session.py:143-182`，已返回 session_id/created_at/updated_at/mode/messages 并按 updated_at 倒序），无需新序列化层；删除沿用 `remove_session` 的"内存 pop + 快照删除"语义，但把 workspace 解析从"依赖内存 session 的 workspace_root"改为"请求显式携带 + store 定位"，使冷会话删除可落地（design review I1）。对齐 Open WebUI 侧边栏"fetch chat list"模式。

### D2: 新建会话走 WebSocket 查询参数

新建会话通过 WS 连接 URL 指定参数：`/ws/new?mode=plan&workspace=/abs/path`。服务端校验后在 `websocket_endpoint` 内创建 session 并回发 `session_created`（扩展字段含 `workspace`）。

理由：沿用现状"连接即创建"模型（`web/server.py:169-185`），新建会话不需要先 `POST` 再连 WS 的两次往返，也没有"POST 成功但 WS 连接失败导致孤儿 session"的竞态。`/ws/{session_id}` 恢复路径保持不变。

- `mode` 非法 → WS error 事件 `{"error": "invalid_mode"}`，不创建 session。
- `workspace` 不在 allowlist / 路径不存在 → WS error 事件 `{"error": "workspace_not_allowed"}`，不创建 session。
- `SessionManager.create_session_async(llm, mode=None, workspace_root=None)` 增加参数，缺省回落到 manager 初始 mode / workspace。
- **跳过 resume 拦截（grill R2/Q8）**：`/ws/new` 携带任意显式参数（mode 或 workspace）时跳过 `app.state.resume_session_id` 分支直接新建；仅裸 `/ws/new` 保留 `--resume` 语义。否则 `--resume` 启动下 hub 的"新建会话"会被 resume_target 静默拦截，永远打开 resume 会话。

### D3: per-session workspace 与 SessionStore 归属

- `AgentSession` 增加 `workspace_root: Path | None` 字段（`web/session.py:217-244`）。
- `SessionManager._create_session` 增加 `workspace_root` kwarg（缺省 `self.workspace_root`）；构造 `WorkspacePolicy(workspace_root=session_workspace, ...)` 时使用 session 的 workspace。
- `SessionManager` 的 store 从单例 `self.session_store` 改为 `self._stores: dict[str, SessionStore]`，key 为 `str(Path(workspace).resolve())` 规范化后的值（避免同一目录因写法不同产生多个 store）；`_store_for(workspace_root)` 惰性创建（`SessionStore(str((workspace_root or cwd) / ".asterwynd" / "sessions"))`，与 `web/session.py:264-265` 同语义）。**`_store_for(None)` 的 key 为 `str(Path.cwd().resolve())`**，与显式传主 workspace 时一致，避免主 workspace 出现两个 store（design review I10）。
- `_create_session` 把 `_store_for(session_workspace)` 传给 `AgentLoop.session_store`（`web/session.py:364`），保证 run 落盘到 session 所属 workspace。
- `resume_session_async(session_id, workspace=None)`：workspace 显式传入（hub 列表 / URL `?workspace=` 已知）→ 用该 workspace 的 store 恢复；未传 → 依次搜主 workspace store 与 allowlist stores（**确定性顺序：主 → allowlist 配置序**，grill R10/Q12），首个命中即恢复，全部未命中返回 None。**归属闭环（design review I2）**：命中哪个 store，就用该 workspace 创建 session——`workspace_root`、`WorkspacePolicy`、`_store_for(命中 workspace)` 全部用命中值，保证恢复后的会话下次 run 仍落盘回原 workspace，不会"漂移"到主 store；测试须断言无 workspace 恢复 allowlist 会话后 re-run 仍写原 store（tasks 2.1）。
- `remove_session(session_id, workspace=None)`：内存 pop 后删除快照。workspace 显式传入（hub `DELETE` 端点，冷会话常态）→ 用该 workspace 的 store `store.remove(session_id)`；workspace 缺省（reset 路径）→ 回退用内存 session 的 `workspace_root` 解析 store（对齐 `web/session.py:379-382`）。**错配边界（design review I16）**：请求 workspace 与内存 session 实际 workspace 不一致时（前端 bug/竞态场景），按请求 workspace 删除磁盘快照、按内存 session 的 workspace_root 移除内存——两者都可能落空，但幂等且可由前端重试自愈，不做额外错误分支。
- **恢复回退新建（design review I11）**：`/ws/{id}?workspace=X` 快照未命中时回退新建，若 URL 携带了合法 workspace，则以该 workspace 新建（而不是忽略参数建到主 workspace），与 URL 意图一致。
- **统一 workspace 解析（grill R1/Q7）**：新增 `SessionManager.resolve_workspace(input) -> Path`，对输入做 `expanduser().resolve()` 后校验落入有效集合，否则抛结构化拒绝；`/api/sessions`、`/ws/new`、`/ws/{id}?workspace=` 全部入口统一走它，杜绝 resume/open-tab 路径绕过 allowlist。
- **reset 保留 workspace/mode（grill R7/Q9）**：`reset` 前记录 `session.workspace_root` 与 `current_mode`，替换会话用同 workspace + 同 mode 创建（`web/server.py:424-433` 现状会丢非主 workspace）。

理由：Claude Code 把会话按启动目录分区（`~/.claude/projects/<encoded-cwd>/<session_id>.jsonl`），"会话归属 workspace 目录"是主流语义；本设计与其对齐。按 id 恢复时 workspace 已知（hub/URL 携带），未携带时只在小集合（主 + allowlist）内搜索，代价可控。

### D4: workspace allowlist 安全边界

- `AsterwyndConfig` 新增 `web: WebConfig` 节，`WebConfig.workspaces: tuple[Path, ...] = ()`（`agent/config.py:262-275` 增加字段 + 解析 + 校验，见 Impact）。
- 有效 workspace 集合 = `{主 workspace}` ∪ `{allowlist 中 resolve 后存在的路径}`。主 workspace = CLI `--workspace` 解析路径或 `Path.cwd()`。
- 所有用户可控 workspace 输入（`/api/sessions` query、`/ws/new` query、`/ws/{id}?workspace=`，grill R1/Q7）都必须经 `SessionManager.resolve_workspace(input)`（`expanduser().resolve()` + 集合成员判断）落入有效集合，否则结构化拒绝；防 `..` 穿越、符号链接、尾部斜杠、大小写变体。
- 集合在 `create_app` 启动时解析一次，存入 `app.state.workspaces`；`SessionManager` 持有该集合用于校验。`resolve_workspace` 只做集合成员判断，**不做运行期 `Path.exists()` 复检**（design review I14）——集合是启动时一次性解析的"操作边界"，目录被删等运行期变化在 store 操作时以 IO 错误暴露；`/api/workspaces` 的 `exists` 字段是唯一运行期存在性反映。allowlist 中不存在或不可解析的路径在启动时打 warning 日志（grill R12），避免用户拼错路径后一律 403 无从排查。
- host 绑定策略（Q1 已确认，design review I3）：默认 host 改 `127.0.0.1`（`agent/main.py:661`），显式 `--host 0.0.0.0` 才开放局域网访问。`0.0.0.0` 绑定下 allowlist 只限制"可操作的 workspace 集合"，不限制"谁能访问端口"，文档必须明示此边界。
- `/ws/{id}?workspace=` 的拒绝路径（design review I6）：workspace 不在有效集合或路径不存在 → 回发 `{"error": "workspace_not_allowed"}` 事件后关闭连接，不创建/不恢复会话（与 `/ws/new` 拒绝语义一致）；不允许静默回退主 workspace 新建——否则该入口的校验形同虚设。

理由：issue #117 明确列出"allowlist / 路径校验 / 鉴权，或默认绑定 localhost"为选项；allowlist + 严格路径校验是最小可用方案（与 `_resolve_workspace` 的绝对路径 + 存在性校验语义一致，`agent/main.py:201-210`），不引入认证复杂度。host 默认策略单独让用户拍板。

### D5: 前端 per-tab 状态模型

`chat.js` 顶层单例状态重构为 per-tab 对象：

- 新增 `Tab` 对象（字段必须完整，grill R5/Q11）：`{ sessionId, workspace, mode, ws, currentAssistantMsg, approvalCards, questionCards, pendingImages, shouldReconnect, slashMatches, activeSlashIndex, debugEvents, debugIterBlocks, planningState, planDocState, messagesEl, statusEl, inFlight, uploadWaiters }`。`approvalCards`/`questionCards`/`pendingImages`/`shouldReconnect`/`slashMatches`/`activeSlashIndex`/debug 侧 `iterBlocks`（`debug.js:6`）若保持全局会跨 tab 串扰（审批卡片更新错 tab、图片预览串 tab、一个 tab 结束禁用全 app 重连、debug 块串 tab）。
- `const tabs = new Map(); let activeTabId = null;`。每个 tab 拥有独立的消息容器 DOM（如 `#messages-<id>`）、独立输入区与图片预览区，切换 active 时显隐。
- DOM 结构（grill R13）：per-tab 动态 DOM = 消息容器、输入框、图片预览、审批/问题卡片容器（`#messages-<id>`、`#input-<id>`、`#previews-<id>`）；全局 chrome DOM = planning 面板、plan-document 面板、debug 面板、header 身份栏、标签栏——切换 active tab 时从 `tab.planningState`/`tab.planDocState`/`tab.debugEvents` 重渲染这些全局面板，并重绑输入/发送事件到 active tab。
- 事件分发 `handleEvent(event)` → `handleTabEvent(tab, event)`：`session_created` / `session_resumed` / `assistant_delta` / `planning_state_updated` / `plan_document_updated` 等全部按 tab 写入。
- 输入/发送/图片上传/审批/question/mode 切换从全局变量改为 `(tab, ...)` 参数化；`sendBtn` 只作用于 active tab。
- 全局 chrome（header 身份栏 session id / run id / mode、状态灯）随 active tab 刷新；`debug.js` 的 `renderDebug`/`renderTimeline` 从 active tab 取数据源。
- 持久化：localStorage 存 `asterwynd.session_id` + `asterwynd.session_workspace`（最近会话）；**不持久化 open_tabs**（grill R6/Q10）——tab Map 只活在当前页面，刷新仅恢复最近会话，避免刷新拉起 N 条 WS 连接；sessionStorage 存每 tab 输入草稿（可选，低优先）。
- hub 视图：新增 `#hub-view`，含 workspace 选择器（`GET /api/workspaces`）、会话列表（`GET /api/sessions?workspace=`）、新建会话表单（mode 下拉 + workspace 下拉）、删除按钮。点开会话 → 若已有 tab 则激活，否则开新 tab 连接 `/ws/<id>?workspace=`；删除会话时关闭同 id tab（grill R9/Q6），避免列表消失但 tab 悬空。
- `index.html`：标签栏容器 + `#hub-view` + 动态消息容器模板；`style.css` 补 hub/标签栏样式。

理由：对齐 Open WebUI 的 per-chat store 与 LibreChat 的 localStorage 偏好持久化；原生 JS 下用 `Map<sessionId, Tab>` 替代全局单例是增量重构（把现有函数从读全局改为读 `tab`），不引入框架。

### D6: 会话恢复优先级

启动顺序（前端）：URL `?session=<id>`（可带 `?workspace=`）→ localStorage `asterwynd.session_id`(+`asterwynd.session_workspace`) → hub 视图（存在多个最近会话或用户手动选择）→ 新建。

- 与 issue #110 现状（`chat.js:1430-1434`）一致，扩展 workspace 记忆。
- 对齐 Hermes WebUI canonical session resolution：URL 参数优先、本地状态次之、列表兜底，避免多入口显示不一致。

### D7: uploads 目录归属（推荐保持全局，见 Open Question Q2）

`agent/uploads.py` 的 `save_upload_bytes` / `create_image_message` / `create_image_message_from_upload` 已支持 `workdir` 参数（`agent/uploads.py:92-115, 124-156`），机制存在但缺线程。grill R4 指出：HTTP `/api/uploads` 端点（`web/server.py:139-162`）在发消息前、无 session/workspace 上下文；若本次做隔离，前端须在 upload 请求携带 workspace，`run_session` 的图片重建也须按 session workspace 传 workdir，读写目录才能一致。

**推荐：本次保持全局 `<cwd>/.asterwynd/uploads`，推迟隔离**（grill Q2 推荐）：(1) 上传仅图片文件、按 sha256 去重、全局归属无安全边界问题；(2) `file_path` 是绝对路径（`agent/uploads.py:115`），跨 workspace 恢复图片引用仍有效；(3) 隔离的"目录模型一致性"收益不足以覆盖本次 HTTP 上传线程化 + 回归面成本。隔离记入 backlog 后续单独做。若用户选择隔离，则补上 HTTP 上传的 workspace 线程与对应回归（见 Q2）。

### D8: per-session run 互斥

`AgentSession` 增加 `run_lock: asyncio.Lock`；`run_session` 入口用 `run_lock.acquire_nowait()` 尝试获取（grill R3/Q5），成功则包住整个 run 流程并在 `finally` 释放；失败（已锁）则回发 error 事件 `{"message": "another run is already in progress"}` 并 return，**不阻塞 WS 连接**。

> 禁用 `if run_lock.locked(): 拒绝; async with run_lock:` 的写法——check-then-act 非原子，两个并发 caller 都能通过检查，第二个会阻塞在 `async with` 上挂起其 WS 连接（首个 run 可能持续数分钟）。

理由：issue #110 grill 的 Q1（`archive/2026-08-09-fix-issue-110/reviews/grill-design.md`）已把"并发 run 同一 AgentLoop 污染共享可变状态"显式留给 #117；本 change 多标签会让"同一 session 两个 tab 并发发送"成为真实路径，必须互斥。`AgentLoop` 无 running guard，`run_session` 入口加锁是成本最低的收口点。

## Pre-Implementation Review

已完成 `batch-grill-me` 设计追问（`reviews/grill-design.md`，run `3ce55d3d-83be-49ec-9307-412f79872d9f`）。grill 确认了 D1/D2/D3/D4/D6/D7/D8 与 WebConfig 新增的方向，并发现 2 个必须修的高严重问题 + 若干中低修复项，全部已整合进本 design：

- **R1（安全，已整合进 D3/D4）**: workspace 校验收敛到单一 `resolve_workspace()`，覆盖 `/api/sessions`、`/ws/new`、`/ws/{id}?workspace=`，杜绝 resume/open-tab 路径绕过 allowlist。
- **R2（功能，已整合进 D2）**: `/ws/new` 带显式参数时跳过 `app.state.resume_session_id`，避免 `--resume` 吞掉 hub 新建。
- **R3（竞态，已整合进 D8）**: per-session 互斥改用 `acquire_nowait()`，消除 check-then-act 竞态与 WS 挂起。
- **R4（已整合进 D7）**: 采纳 grill Q2 推荐——uploads 保持全局，推迟隔离。
- **R5/R6（已整合进 D5）**: Tab 对象补齐全部 per-tab 状态字段；open_tabs 不持久化。
- **R7（已整合进 D3）**: reset 保留原 workspace/mode。
- **R9/R10/R12/R13（已整合进 D5/D3/D4）**: 删除关闭同 id tab；store key 规范化 + 搜索顺序；allowlist 启动 warning；DOM 结构说明。

剩余 13 个 Open Questions（含 grill 补充的 Q7-Q13）已停轮抛给用户确认，答复记录在 `reviews/grill-design.md` 的 `## User Confirmation` 节。全部确认前不写实现代码。

### 设计审阅闭环（/review-loop 设计阶段）

grill 之后又跑了独立零记忆设计审阅（`reviews/design-review.md`，Round 1 run `b5515634-0bdd-4c80-b10f-15c9a4d52a76`），首轮 **CHANGES_REQUESTED**，已修复：

- **I1（高）删除 API 缺失** → D1 新增 `DELETE /api/sessions/{session_id}?workspace=`，D3 的 `remove_session` 支持显式 workspace（冷会话可删）。
- **I2（高）resume 归属未闭环** → D3 明确命中哪个 store 就用该 workspace 建 session，tasks 补落盘断言。
- **I3（中）D4 host 残留矛盾** → 改为 Q1 已确认的 `127.0.0.1` 默认。
- **I4（中）spec delta 丢 scenario** → MODIFIED 补回"未知 id 回退新建""进程重启按 id 恢复"。
- **I5（中）前端回归测试盲区** → tasks 补 per-tab 隔离 Playwright + 裸 `/ws/new` resume 回归。
- **I6（中）resume 拒绝路径未定义** → D4 明确 error 事件 + 关闭，tasks/spec 补负向。
- **I7-I11（低）** → `exists` 实时判断、chat.js 行数 1451、uploads 措辞、`_store_for(None)` key、恢复回退新建用 URL workspace。

修复后进入 Round 2 再审，直到 PASS 或 3 轮封顶。

## Open Questions

全部已确认（2026-08-09，见 `reviews/grill-design.md` `## User Confirmation`）。停轮确认结果：

1. host 默认绑定 → 改 `127.0.0.1`（显式 `--host 0.0.0.0` 开放 LAN）。
2. uploads 归属 → 保持全局 `<cwd>/.asterwynd/uploads`，隔离推迟。
3. hub 列表范围 → 按当前选中 workspace。
4. 新建会话 API → WS 查询参数 `/ws/new?mode=&workspace=`。
5. per-session run 互斥 → 本次实现（`acquire_nowait()`）。
6. 会话删除 → hub 提供（内存 + 磁盘快照，关闭同 id tab）。
7. workspace 校验入口 → 单一 `resolve_workspace()` 覆盖全部入口。
8. `--resume` 拦截 → `/ws/new` 带显式参数跳过。
9. reset → 保留原 session workspace/mode。
10. open_tabs → 不持久化，tab Map 仅内存。
11. per-tab 状态 → Tab 补齐全部字段。
12. 恢复搜索 → store key `Path.resolve()` 规范化 + 主→allowlist 配置序。
13. spec delta 边界 → 按推荐清单（hub API、`/ws/new` 参数、allowlist 拒绝、互斥、多标签、删除、恢复优先级）并登记 backlog。

- **Q1（host 默认绑定策略）**: allowlist 只限制可操作的 workspace 集合，不限制端口访问者。本 change 首次把 workspace 边界 + 多会话 + mode 选择（含 bypass）暴露到 Web，`0.0.0.0` 下局域网任意访问者可在 allowlist 目录内建 bypass 会话执行免审批工具。是否 (a) 保留 `0.0.0.0` 默认 + 文档警告，(b) 改默认 `127.0.0.1`（grill 推荐：安全收益大，显式 `--host 0.0.0.0` 才开放 LAN），还是 (c) 增加可选 `--token` 鉴权？
- **Q2（uploads 归属）**: 上传图片目录是否按 workspace 隔离（`<workspace>/.asterwynd/uploads`），还是本次保持全局 `<cwd>/.asterwynd/uploads`（grill 推荐：上传是 sha256 去重图片、绝对路径跨 workspace 有效，隔离涉及 HTTP 上传端点无 workspace 上下文的缺口 R4，推迟做）？
- **Q3（hub 列表范围）**: hub 会话列表按当前选中 workspace 展示（默认主 workspace，grill 推荐），还是跨所有 allowlist workspace 聚合展示？
- **Q4（新建会话 API 形态）**: 新建会话走 WS 查询参数 `/ws/new?mode=&workspace=`（grill 推荐，但必须处理 R2：带显式参数时跳过 resume 拦截），还是独立 `POST /api/sessions` 返回 session_id 再连 WS？
- **Q5（per-session run 互斥）**: 本次实现 per-session run 互斥（grill 推荐：用 `acquire_nowait()` 修掉 check-then-act 竞态 R3），还是留给后续？
- **Q6（删除会话）**: hub 提供会话删除（内存 + 磁盘快照，grill 推荐，需补 R9：删除时关闭同 id tab），还是本 change 只做只读 hub？
- **Q7（workspace 校验入口覆盖）**: 单一 `resolve_workspace()` 覆盖 `/api/sessions`、`/ws/new`、`/ws/{id}?workspace=`（grill 新增，R1 安全绕过必须修，推荐采纳）？
- **Q8（`--resume` 与新建冲突）**: `/ws/new` 带显式参数时跳过 `resume_target`（grill 新增，R2 功能缺陷必须修，推荐采纳）？
- **Q9（reset 保留 workspace/mode）**: reset 替换会话用原 session 的 workspace/mode 创建（grill 新增，R7，推荐采纳）？
- **Q10（open_tabs 不持久化）**: tab Map 仅内存，刷新只恢复最近会话（grill 新增，R6，推荐采纳）？
- **Q11（per-tab 状态完整性）**: Tab 补齐 approvalCards/questionCards/pendingImages/shouldReconnect/slashMatches/iterBlocks（grill 新增，R5，推荐采纳）？
- **Q12（恢复搜索确定性）**: store key 用 `Path.resolve()` 规范化 + 搜索顺序主→allowlist 配置序，测试覆盖（grill 新增，R10，推荐采纳）？
- **Q13（spec delta 边界）**: delta 新增 hub 列表 API、`/ws/new` mode/workspace、allowlist 拒绝、per-session 互斥、多标签、删除、恢复优先级扩展，并登记 backlog（grill 新增，R11，推荐采纳）？

## Risks / Trade-offs

- **网络暴露（严重）**：`0.0.0.0` 显式绑定下端口访问者可浏览/操作 allowlist 内 workspace 的会话。缓解：默认 host 已改 `127.0.0.1`（Q1 确认）；allowlist 限制 workspace 集合；`0.0.0.0` 下文档明示安全边界。
- **前端重构回归（高）**：`chat.js`（1451 行）从全局单例重构为 per-tab，事件分发/上传/审批路径都改，回归面大。缓解：Playwright smoke 覆盖 hub/多标签/新建/刷新恢复，并补 per-tab 隔离用例（审批卡片、图片预览、reconnect、slash 匹配各落各 tab，design review I5）；后端不变量由集成测试保护；尽量增量（提取函数改签名，不重写渲染逻辑）。
- **恢复路径歧义（中）**：`/ws/<id>` 未带 workspace 时需在多个 store 中搜索。缓解：hub/URL 显式带 workspace；未带时按主 → allowlist 顺序搜索，命中即返回且会话归属命中 workspace；仍不命中回退新建（与 #110 一致，若 URL 带合法 workspace 则用该 workspace 新建）。
- **session_history 全量重发（低，承接 #110）**：恢复连接全量重发文本历史，超长会话 payload 大。缓解：沿用现状，超长会话的增量/分页归后续。
- **uploads 全局 vs workspace（低，Q2 已确认保持全局）**：图片归属全局而会话归属 workspace，但绝对路径引用跨 workspace 有效，无功能问题；若后续隔离，需补 HTTP 上传 workspace 线程与回归。
- **run 生命周期绑定发起 tab（低）**：tab 关闭取消 run（沿用现状）。多 tab 下"换 tab 后 run 被关"是已知边界，非目标。
- **替代方案权衡**：
  - `POST /api/sessions` 先建后连：两次往返 + 孤儿 session 竞态，拒绝。
  - 引入前端框架（React/Vue）做 store：重构面远超原生 JS per-tab 对象，拒绝。
  - 后端数据库 + 用户体系：超出现有本地文件系统模型，拒绝。
  - 不做 workspace 隔离只做多标签：回避 issue 明确的 workspace 需求与安全开放问题，拒绝。

## Testing Strategy

- 后端集成测试（`tests/web_tests/test_server.py`，fake LLM `ScriptedLLM`）：
  - `GET /api/workspaces` / `GET /api/sessions` 结构与 allowlist 拒绝；`DELETE /api/sessions/{id}?workspace=` 删除内存 + 磁盘快照（含未打开过的冷会话）。
  - `/ws/new?mode=&workspace=` 创建指定 mode/workspace；非法 mode / 未授权 workspace 拒绝。
  - 多 session 并行（各自 run 互不串扰）；per-session run 互斥（并发 chat 第二个被拒）。
  - 进程重启恢复（`SessionStore` 落盘 → 新 app `/ws/<id>` 恢复 → `session_resumed` + `session_history`）。
  - 恢复归属闭环（design review I2）：无 workspace 恢复 allowlist 会话后再次 run，快照仍写入该 allowlist store、主 store 不新增。
  - 裸 `/ws/new` 保留 `--resume` 语义回归（`create_app(resume=...)` 下裸 `/ws/new` 返回 resume 会话，design review I5）。
  - `/ws/{id}?workspace=` 未授权 workspace 拒绝路径（error 事件 + 关闭，design review I6）。
  - 删除会话（内存 + 磁盘快照移除）；跨 workspace：两个 workspace 各自创建/列出/恢复会话，互不串扰。
- 前端 Playwright smoke（`tests/web_tests/test_browser.py`，fake LLM）：
  - hub 渲染会话列表；点开进入 tab 展示历史。
  - 多标签切换与消息隔离。
  - per-tab 隔离（design review I5）：两个 tab 各自触发审批/图片上传，卡片与预览只落各自 tab；一个 tab 结束（continue_session=false）不影响另一 tab 的 reconnect。
  - 新建会话（mode/workspace）打开对应会话。
  - 刷新回到上次会话；删除会话后对应 tab 被关闭。
- 回归：全量 pytest + OpenSpec strict validate + artifact checker（`scripts/check_openspec_artifacts.py`）。
