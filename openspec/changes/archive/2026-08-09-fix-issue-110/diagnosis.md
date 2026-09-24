# Diagnosis — fix-issue-110

## Symptom

用户从 Web 切出再切回并刷新页面，当前 session 丢失，页面进入新的 session，原来的上下文无法继续。刷新或重开页面后，会话连续性不可用。

## Reproduction

1. 打开 Web UI（`uv run asterwynd web`），进行一段对话，页面显示当前 session id。
2. 刷新页面（或关闭重开浏览器标签）。
3. 前端 `chat.js` 的 `sessionId` 重置为 `null`，重连 `/ws/new`。
4. 服务端 `get_session("new")` 为 None，走 `create_session_async` 新建 session，原 session 无法恢复。

服务端进程重启场景：重启后 `SessionManager._sessions` 为空，即使前端记得旧 session id 也无法恢复（内存丢失且从未落盘）。

## Evidence

- `web/static/chat.js:5`：`let sessionId = null;` 前端不记忆 session id；`chat.js:102` 连接 `/ws/${sessionId || 'new'}`——刷新后必然 `/ws/new`。
- `web/session.py:226`：`self._sessions: dict[str, AgentSession] = {}` 纯内存，无持久化。
- `web/session.py:282-295`：构造 `AgentLoop` 未传 `session_store`（`agent/loop.py:131` 参数存在但 Web 未使用），因此 `AgentLoop.run()` 结束时不落盘（`loop.py:530-534`）。
- `web/server.py:158-165`：WebSocket 端点 `get_session(session_id)` 未命中直接 `create_session_async`，无恢复尝试。
- `web/server.py:46`：`app.state.resume_session_id = resume`——`--resume` 参数只存不读，死参数。
- `agent/session.py:81-228`：`SessionStore` 已实现 `save/load/list_sessions/remove`，落盘到 `<workspace>/.asterwynd/sessions/<id>/`，与 CLI `--resume`（`agent/main.py:1086`）同一套机制，Web 未复用。
- `agent/loop.py:557-584`：`AgentLoop._run` 已支持 `resume_snapshot` 恢复上下文（mode/todos/skills/system prompt/messages），Web 未传入。

## Root Cause

Web 层没有把 session 提升为一等公民：session 生命周期绑死进程内存与前端 JS 变量，未复用 CLI 已存在的 `SessionStore` 持久化和 `resume_snapshot` 恢复机制。具体三个断点：

1. **不落盘**：Web 的 `AgentLoop` 未接 `session_store`，run 结束不写磁盘，进程重启即全部丢失。
2. **不记忆**：前端不持久化 session id，刷新后必然新建。
3. **不恢复**：服务端 WebSocket 端点无恢复逻辑，`--resume` 参数无人消费，也无历史水合接口。

## Recommended Direction

最小修复，复用既有基础设施，不动事件协议主体：

- `SessionManager` 构造时创建 `SessionStore`（root = `workspace_root or cwd` 下的 `.asterwynd/sessions`）；`_create_session` 构造 `AgentLoop` 时传 `session_store`，run 结束自动落盘。
- 新增 `resume_session_async(session_id, llm)`：内存命中复用；否则 `SessionStore.load` 快照，用快照的 mode/messages/system prompt 重建 `AgentSession`，快照作为首次 run 的 `resume_snapshot`；无快照返回 None。
- WebSocket 端点：`session_id != "new"` 且内存未命中时先尝试恢复；恢复成功发 `session_resumed` + `session_history`（用 `agent.message.extract_text` 序列化历史为前端可渲染文本）；失败才新建。
- `app.state.resume_session_id`（`--resume`）在每次连接 `/ws/new` 时消费（消费后不清空，始终命中）：尝试恢复指定 session，成功发 `session_resumed`，失败新建。
- 前端 `chat.js`：`init()` 时 sessionId 取值优先级 URL `?session=` → `localStorage['asterwynd.session_id']` → null；收到 `session_created`/`session_resumed` 写入 localStorage；收到 `session_history` 渲染历史；reset 后更新。
- `GET /resume` 路由返回 index.html（显式恢复入口，配 `?session=`）。

## Regression Tests

- `tests/web_tests/test_server.py::test_websocket_reuses_inmemory_session_with_same_id`：先 `/ws/new` 拿 id，再连 `/ws/<id>`，断言收到 `session_resumed` 且 session id 不变、SessionManager 未新建。
- `tests/web_tests/test_server.py::test_websocket_resumes_from_store_after_process_restart`：预置 `SessionStore` 快照（模拟进程重启后的新 app），连接 `/ws/<id>`，断言 `session_resumed` + `session_history` 非空 + mode 正确。
- `tests/web_tests/test_server.py::test_web_run_persists_session_to_store`：跑一次 `run_session` 后断言 `SessionStore.list_sessions()` 含该 session 且消息数正确。
- `tests/web_tests/test_server.py::test_websocket_unknown_session_creates_new`：连接不存在 id，断言收到 `session_created`（新建）。
- `tests/web_tests/test_server.py::test_resume_route_returns_html`：`GET /resume` 返回 200 HTML。
- 有效性验证：临时注释恢复逻辑后，`test_websocket_reuses_inmemory_session_with_same_id` 与 `test_websocket_resumes_from_store_after_process_restart` 应失败；还原后通过。
