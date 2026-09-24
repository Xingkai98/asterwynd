# Proposal — fix-issue-110

## Why

Web UI 的 session 只存在于进程内内存，刷新/重开页面后会话丢失：

1. `web/static/chat.js` 中 `sessionId` 只是 JS 内存变量，刷新后回到 `null`，重连 `/ws/new`，服务端必然新建 session，原上下文无法继续。
2. `web/session.py` 的 `SessionManager._sessions` 是内存 dict，且构造 `AgentLoop` 时未传入 `session_store`，Web session 从不落盘；服务端进程重启后内存 session 全部丢失。
3. `asterwynd web --resume <id>` 是死参数：`create_app` 只把 resume 存入 `app.state.resume_session_id`，没有任何代码消费它。
4. 服务端没有历史消息水合接口，即使恢复出 session，前端 UI 也拉不回消息历史。

CLI 侧已有完整的 session 持久化/恢复基础设施（`agent/session.py` 的 `SessionStore`/`SessionSnapshot` 与 `AgentLoop.resume_snapshot`），但 Web 从未接线。本 fix 把该基础设施接入 Web：run 后自动落盘、按 id 恢复、刷新不丢会话、补显式 `/resume` 恢复入口。

## Change Type

- primary: bugfix
- secondary: []

## What Changes

- Web session 每次 Agent run 结束后自动持久化到 `<workspace>/.asterwynd/sessions/<session_id>/`（复用 `SessionStore`，与 CLI 同一存储位置），覆盖消息、mode、todos、skills、system prompt。
- WebSocket 连接 `/ws/<session_id>` 时按 id 恢复：内存命中则复用；未命中则从 `SessionStore` 快照恢复（进程重启后可续），恢复成功推送 `session_resumed` + `session_history` 事件；快照不可用才新建 session。
- 前端用 `localStorage` 记忆最近使用的 session id，刷新/重开页面后优先重连原 session；URL `?session=<id>` 提供显式精确恢复。
- 新增 `GET /resume` 路由作为显式恢复入口（配合 `?session=` 参数），桌面端与移动端通用。
- `asterwynd web --resume <id>` 生效：每次连接 `/ws/new` 时若设置了 resume id 则从快照恢复（消费后不清空，始终命中），恢复成功发 `session_resumed`，失败回退新建。

## Capabilities

### Modified Capabilities

- `web-ui`: 新增"Web session 本地持久化与恢复"Requirement——run 后自动落盘、按 id 恢复、刷新不丢会话、显式恢复入口。

## Dependencies

- 无新依赖。复用既有 `agent/session.py`（`SessionStore`/`SessionSnapshot`）与 `AgentLoop.resume_snapshot`。

## Impact Analysis

- 影响代码：
  - `web/session.py`：`SessionManager` 接入 `SessionStore`、`_create_session` 传 `session_store`、新增 `resume_session_async`。
  - `web/server.py`：WebSocket 端点恢复逻辑、`session_history` 事件、`GET /resume` 路由。
  - `web/static/chat.js`：session id 的 localStorage/URL 记忆与历史渲染。
  - `agent/main.py`：无需改动（web 命令的 resume 参数接线在 `create_app` 内完成）。
- 影响测试：`tests/web_tests/test_server.py`、`tests/web_tests/test_session.py`（新增恢复/落盘回归测试；`app` fixture 传入 `workspace_root=tmp_path` 避免测试污染仓库）。
- 影响文档：`docs/openspec-change-backlog.md` 登记本 change；`openspec/specs/web-ui/spec.md` 同步 delta。
- 行为影响：Web run 后写 `.asterwynd/sessions/`（与 CLI 相同位置，属于受保护本地目录）；刷新后恢复会话；`--resume` 从死参数变为可用。
- 不涉及：多 session 入口页、标签页、新建 session 指定模式/workspace、按 workspace 分目录管理——属于 feature #117，另行立项。
- 已知边界：恢复不包含 persistent memory 内容（Web 当前用内存 `MemoryManager`），只恢复消息、mode、todos、skills、system prompt；memory 持久化归入 #117。

## Reference Implementation Research

- status: disabled
- reason: 本修复是项目内部 Web 层对既有 CLI session 持久化基础设施（`SessionStore`/`SessionSnapshot`/`resume_snapshot`）的接线，不引入新的 coding-agent 能力或对外协议；根因与最小修法由 issue #110 明确给出，无外部参考实现需要调研。
