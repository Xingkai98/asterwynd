# Proposal: Web 多 session 入口页（多标签 + 本地持久化 + 新建指定模式/workspace）

关联跟踪 issue：[#117](https://github.com/Xingkai98/asterwynd/issues/117)（【feature】Web 多 session 入口页）。

## Change Type

- primary: feature
- secondary: []

## 需求

1. Web 增加 session 入口页（hub）：展示已保存会话列表（session_id、模式、创建/更新时间、消息数），复用 `SessionStore.list_sessions()` 元数据。
2. 每个会话一个标签页，可在标签间切换；每个标签页独立维护 WebSocket 连接、对话历史与运行状态。
3. 会话持久化保存在本地：复用 `agent/session.py` 的 `SessionStore`（`<workspace>/.asterwynd/sessions/<session_id>/`），刷新或进程重启后可恢复。
4. 新建会话时可指定模式（build / read_only / plan / bypass）与 workspace 路径。
5. 保留/增强现有恢复能力：刷新后优先回到上一次使用的会话，并提供显式恢复入口（衔接 issue #110 的 `/resume`）。

## 背景

当前 Web UI 是单会话交互模型：

- `web/session.py` 的 `SessionManager` 用内存 dict 维护 session（`web/session.py:247-265`），每个 `AgentSession` 持有一个 `AgentLoop` + 消息历史。
- issue #110（PR #118，已合入）补齐了 Web session 的本地持久化与按 id 恢复：`SessionManager` 持有 `SessionStore`（`<workspace or cwd>/.asterwynd/sessions`），每次 run 结束自动落盘；WebSocket 连接 `/ws/<id>` 未命中内存时从快照恢复（`resume_session_async`），命中失败才新建；前端用 localStorage 记忆最近 session id，URL `?session=<id>` 提供显式恢复入口。
- 但前端仍是单标签：`chat.js` 顶层是单例全局状态（`ws`、`sessionId`、`messagesEl` 等），同一时刻只有一个 WebSocket；没有会话列表页、没有多标签切换、没有新建会话的 mode/workspace 选择。
- Web session 目录与 workspace 绑定是全局唯一的：`SessionManager` 只有一个 `workspace_root`（CLI `--workspace` 或 cwd），所有 session 共享同一 SessionStore 根。

缺口：会话还不是一等公民——不可浏览、不可并行切换、不可按 workspace 组织、新建时不可选 mode/workspace。issue #117 把会话提升为可管理、可恢复、可并行切换的实体。

## 非目标

- 不做完整用户鉴权系统（多用户、登录、RBAC）。workspace 边界用 allowlist + 路径校验保证；网络暴露风险通过默认绑定策略与文档约束（见 Open Questions）。
- 不做跨浏览器/跨设备的会话同步（无后端数据库，会话仍在本地文件系统）。
- 不做 Web session 的 memory 磁盘持久化（web 侧 `MemoryManager` 保持内存态；磁盘 memory 持久化属长期记忆路线，另行立项）。
- 不重写 debug 视图（Timeline 等）与 slash command 机制；只让其按 active 标签页切换数据源。
- 不改 CLI/交互模式的 session 语义。
- 不做会话删除 UI 之外的高级管理操作（重命名、导出、归档等），仅提供删除（删除即移除内存 + 磁盘快照，沿用 `remove_session` 语义）。

## 用户故事

- 用户打开 Web UI，看到已保存的会话列表（hub），按更新时间排序，点开任意会话进入标签页继续对话。
- 用户在 hub 新建会话时选择 `plan` 模式与指定 workspace，打开即进入 plan 会话。
- 用户同时开两个标签页（一个 build、一个 read_only），各自独立 WebSocket 与历史，互不干扰。
- 用户刷新页面，回到上一次正在使用的会话（localStorage 记忆）；进程重启后经 `/ws/<id>` 或 `/resume?session=<id>` 恢复。

## 行为定义

### Session hub API

- `GET /api/workspaces`：返回允许的 workspace 列表（主 workspace + allowlist），含解析后的绝对路径、是否为主 workspace、是否存在、session 数。
- `GET /api/sessions?workspace=<path>`：返回该 workspace 的会话列表（`SessionStore.list_sessions()` 元数据 + workspace）。缺省 workspace 用主 workspace。workspace 不在 allowlist 时返回结构化错误。

### 新建会话（指定 mode / workspace）

- WebSocket `GET /ws/new?mode=<mode>&workspace=<path>`：服务端校验 mode 与 workspace（workspace 必须在 allowlist 且存在），创建 session 并回发 `session_created`（含 session_id、mode、workspace）。
- 保持既有 `/ws/{session_id}` 恢复路径不变；`/ws/new` 是新建入口的显式化（现状 `/ws/new` 直接新建，新增 mode/workspace 参数后行为扩展）。
- `--resume`（CLI 启动参数）与 `app.state.resume_session_id` 语义保留。

### 多标签前端

- 前端引入 per-tab 状态模型：每个打开的会话一个 tab 对象（sessionId、ws、mode、消息容器、运行状态、debug 事件、planning state 等），替代当前单例全局状态。
- 标签栏展示所有打开的 tab（session id + mode），可切换、可关闭；header 身份栏（session id / run id / mode）随 active tab 刷新。
- hub 视图与 Chat/Debug 视图并列；进入 hub 不关闭已打开 tab，从 hub 点开会话开新 tab 或切到已开 tab。

### 会话恢复优先级

- 前端启动：URL `?session=<id>`（显式恢复，可带 `?workspace=`）→ localStorage 记忆的最近会话 → hub 列表 → 新建。
- 与服务端配合：`/ws/<id>` 未命中内存 → 按 workspace 定位 store 并恢复快照 → 快照也不存在 → 新建。

### Workspace 归属原则

- 每个 session 持有自己的 `workspace_root`；`WorkspacePolicy`、`SessionStore` 按 session 的 workspace 解析（`<workspace>/.asterwynd/sessions/`）。
- 新建 session 时 workspace 缺省为主 workspace（CLI `--workspace` 或 cwd），与现状一致。

## 验收

- [ ] `GET /api/sessions` 返回主 workspace 会话列表，字段含 session_id、mode、created_at、updated_at、messages。
- [ ] 前端 hub 页展示会话列表，可按 workspace 切换；点开会话进入标签页并展示历史。
- [ ] 多标签并行：两个 tab 各自独立 WebSocket，发送消息互不干扰；同一 session 并发发送被拒绝（per-session run 互斥）。
- [ ] 新建会话可选择 mode 与 workspace；workspace 不在 allowlist 时服务端拒绝并回结构化错误。
- [ ] 刷新页面回到上次会话；进程重启后按 id 恢复。
- [ ] 会话删除（内存 + 磁盘快照）在 hub 提供，删除后列表消失。
- [ ] 受保护 artifact：web-ui spec delta 同步；`docs/openspec-change-backlog.md` 登记 issue #117。
- [ ] 覆盖测试：后端 API 单测/集成、WebSocket 多 session 集成、前端 Playwright smoke（多标签 + hub + 新建）。

## Impact Analysis

- `agent/config.py`：新增 `WebConfig`（`workspaces: tuple[Path, ...]` allowlist）+ 解析校验。
- `web/session.py`：`SessionManager` 支持 per-session workspace；SessionStore 改为按 workspace 的 store map；`_create_session`/`resume_session_async`/`remove_session` 适配；新增 per-session run 互斥。
- `web/server.py`：新增 `/api/workspaces`、`/api/sessions`、`DELETE /api/sessions/{session_id}`；`/ws/new` 支持 mode/workspace 查询参数；`/ws/{id}?workspace=` 校验与拒绝路径；hub 页面路由。
- `web/static/chat.js`：单例状态重构为 per-tab 模型；hub 视图渲染；会话恢复优先级逻辑。
- `web/static/index.html`：新增 hub 视图 DOM、标签栏容器。
- `web/static/style.css`：hub、标签栏样式。
- `agent/uploads.py`：不涉及（Q2 已确认：uploads 保持全局 `<cwd>/.asterwynd/uploads`，隔离推迟）。
- `docs/openspec-change-backlog.md`：登记。
- `openspec/specs/web-ui/spec.md`：delta 合并。

## Reference Implementation Research

- status: enabled
- reason: 多会话入口页是对标主流 coding-agent/chat web UI 的能力；本地参考仓库不可用（`.dev/reference-repos.txt` 不存在，已确认工作区无可用参考仓库），`codegraph` 索引也不存在。改用公开文档 + 公开代码分析作为依据（Claude Code 会话存储与恢复、Open WebUI / LibreChat 会话列表与多标签状态管理）。
- research questions:
  - 主流 coding agent（Claude Code）如何按目录组织并恢复会话？
  - 多会话 chat web UI（Open WebUI / LibreChat）如何管理会话列表、多标签状态与本地持久化？
  - 多入口（URL / localStorage / 列表 / 启动恢复）如何收敛到一个 canonical session？
- findings:
  - Claude Code 把 session 按启动目录分区存储（`~/.claude/projects/<encoded-cwd>/<session-id>.jsonl`），`/resume` 列出最近会话、`--resume <id>`/`--continue` 按 id 或最近恢复；会话只在同一启动目录下可见。这印证 Asterwynd 的 `<workspace>/.asterwynd/sessions/<session_id>/` 按 workspace 分区的设计，且"会话归属 workspace 目录"是主流语义。
  - Open WebUI / LibreChat 用全局响应式 store 管理会话列表与 active chat id；localStorage 存偏好、sessionStorage 存草稿；会话列表支持按更新时间排序与逐条管理；多标签/多窗口通过"开新 tab 连接独立会话"实现，每个 tab 独立流式状态。
  - Hermes WebUI 的 canonical session resolution RFC 明确：URL 路由、query 参数、localStorage、列表、启动恢复等多入口必须收敛到唯一可见 session；本地浏览器状态只是提示，启动恢复仍要走 canonical 解析。这支撑本设计的前端会话恢复优先级（URL → localStorage → hub → 新建）。
- design impact:
  - 会话归属 workspace 目录（`<workspace>/.asterwynd/sessions/`），hub 按 workspace 展示列表；恢复按 id + workspace 定位。
  - 前端 per-tab 状态模型对齐 Open WebUI 的 per-chat store；localStorage 只存"最近会话 + 打开标签"，草稿/瞬时态用 sessionStorage。
  - 会话恢复优先级对齐 canonical resolution：URL 参数优先，localStorage 次之，hub 列表兜底。
  - 不做 Redis/数据库级会话协调（单实例本地文件系统足够），不引入前端框架（沿用原生 JS，per-tab 对象替代全局单例）。

## 测试计划

- 后端单测/集成（`tests/web_tests/`，fake LLM）：
  - `GET /api/workspaces` 与 `GET /api/sessions` 返回结构、workspace 不在 allowlist 时 4xx 结构化错误。
  - `/ws/new?mode=&workspace=` 创建指定 mode/workspace 的 session；非法 mode、未授权 workspace 拒绝。
  - per-session run 互斥：同一 session 并发 `chat` 时第二个被拒绝并回 error 事件。
  - 多 session 并行（两个 session 各自 run 互不串扰）。
  - 进程重启恢复（`SessionStore` 落盘 → 新 app 实例 `/ws/<id>` 恢复 → `session_resumed` + `session_history`）。
  - 删除会话（内存 + 磁盘快照移除）。
- 前端 Playwright smoke（`tests/web_tests/test_browser.py`，fake LLM）：
  - hub 渲染会话列表；点开进入 tab 并展示历史。
  - 多标签切换：开两个 tab 各自发送消息，消息落到各自容器。
  - 新建会话表单（mode/workspace）打开指定会话。
  - 刷新回到上次会话。
