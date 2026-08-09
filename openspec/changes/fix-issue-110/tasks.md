# Tasks — fix-issue-110

## 规格

- [x] 根因分析与回归测试方案：`diagnosis.md`（Symptom / Reproduction / Evidence / Root Cause / Recommended Direction / Regression Tests）
- [x] 范围、非目标与验收标准：`proposal.md`（Impact Analysis 明确不涉及 #117，已知边界 memory 持久化归入 #117）
- [x] spec delta：新增 `web-ui` 能力域"Web session 本地持久化与恢复"Requirement
- [x] Reference Implementation Research：status disabled + 原因（见 proposal.md）

## 测试

- [x] 新增 `test_websocket_reuses_inmemory_session_with_same_id`：同 id 二次连接复用内存 session，发 `session_resumed`
- [x] 新增 `test_websocket_resumes_from_store_after_process_restart`：预置快照 + 新 app 恢复，`session_resumed` + `session_history` 非空 + mode 正确
- [x] 新增 `test_web_run_persists_session_to_store`：run 后 `SessionStore.list_sessions()` 含该 session
- [x] 新增 `test_websocket_unknown_session_creates_new`：未知 id 回退新建，发 `session_created`
- [x] 新增 `test_resume_route_returns_html`：`GET /resume` 返回 200 HTML
- [x] 有效性验证：临时注释恢复逻辑后两条恢复测试失败；还原后通过
- [x] 相关测试全绿：`tests/web_tests/test_server.py`、`tests/web_tests/test_session.py` 全部通过

## 实现

- [x] `web/session.py`：`SessionManager` 构造 `SessionStore`（root = `workspace_root or cwd` 下 `.asterwynd/sessions`）；`_create_session` 传 `session_store` 给 `AgentLoop`
- [x] `web/session.py`：新增 `resume_session_async`——内存命中复用；否则 `SessionStore.load` 重建 session（mode/messages/system prompt），快照作首次 run 的 `resume_snapshot`；无快照返回 None
- [x] `web/server.py`：WebSocket 端点恢复逻辑（`session_id != "new"` 先尝试恢复）+ `session_resumed` / `session_history` 事件
- [x] `web/server.py`：`app.state.resume_session_id`（`--resume`）在首次连接 `/ws/new` 时消费
- [x] `web/server.py`：`GET /resume` 路由
- [x] `web/static/chat.js`：session id 记忆（URL `?session=` → localStorage → null）、`session_history` 渲染、reset 后更新 localStorage
- [x] 测试基础设施：`tests/web_tests/test_server.py` 的 `app` fixture 传 `workspace_root=tmp_path`，避免测试污染仓库 `.asterwynd`

## 文档

- [x] `docs/openspec-change-backlog.md`：登记 `fix-issue-110`（bugfix，关联 issue #110）
- [x] 当前规格同步：将 ADDED Requirement 合入 `openspec/specs/web-ui/spec.md` 并记录 workflow-events 事件（seq 3 current_spec_synced）

## 审阅闭环

- [x] Round 1 独立 subagent 审阅（CHANGES_REQUESTED）：resume 恢复后首次 run 快照历史重复送入 LLM（web/session.py 预填 session.messages + run_session 传 resume_snapshot 与 loop.py resume 分支叠加）
- [x] Round 1 修复：resume 不预填 session.messages（由 _run 从 resume_snapshot 重建）；build_history_payload 回退用快照历史；remove_session 同步删磁盘快照；回归测试增强断言 LLM 消息无重复
- [ ] Round 2 独立 subagent 审阅（PASS）
- [ ] 生成 review manifest 绑定 reviewer run / base·head sha / tasks·spec·diff·report hash

## 验证

- [x] `uv run pytest tests/web_tests/ -q` 通过（76 passed，7 skipped）
- [x] `uv run pytest -q` 全量通过（1813 passed，7 skipped）——注意：需 `uv sync --extra dev` 后用 venv pytest，否则用户级 pytest 缺 tree_sitter_java/kotlin 导致 code_intelligence 测试误报失败
- [x] `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` 通过（30/30）
- [ ] `uv run python scripts/check_openspec_artifacts.py` 通过
- [x] Web smoke 由回归测试覆盖：刷新恢复（reuses_inmemory）、`/resume?session=`（resume_route + URL 参数）、进程重启恢复（resumes_from_store）、`--resume`（resume_cli）

## PR 收尾

- [ ] 归档到 `openspec/changes/archive/2026-08-09-fix-issue-110/`
- [ ] 从 `docs/openspec-change-backlog.md` 移除
- [ ] 发起 PR 并关联 issue #110，合入后给 issue 添加完成说明 comment 并关闭
