# Building Review — fix-issue-110 (Round 2)

- reviewer run: 独立零记忆 subagent（本报告由 review-loop Round 2 产出，覆盖 Round 1 报告）
- base: `12f6cdf4ac3e9a97492ae7aeda6aa215b4072ded`（origin/master）
- head: `d28688feb82e1b40be09d26f0eca4d904412544b`（当前 HEAD）
- 范围: `git diff origin/master...HEAD`（4 个提交：43aa236 实现 + 008d3ea 文档 + 9ead6e0 Round1 修复 + d28688f tasks.md 审阅日志），仅审阅本 change 改动范围。
- 本轮重点: 验证 Round 1 的 Issue 1（resume 恢复后首次 run 快照历史重复入参，中）与 Issue 2（reset 后磁盘快照成孤儿，低）是否真正修复。

## Verdict

**PASS**

Round 1 的 2 个问题均确认修复：

1. **Issue 1（中）已修复**：`web/session.py` 的 `resume_session_async` 不再把快照历史预填进 `session.messages`；恢复历史由 `AgentLoop._run` 的 resume 分支从 `resume_snapshot` 重建；`build_history_payload` 在 `session.messages` 为空且 `resume_snapshot` 存在时回退用快照历史渲染。已用独立脚本端到端验证：resume 后首次 run，LLM 实际收到的 user 消息为 `[恢复我]`（快照历史）出现 **1 次**，无重复。
2. **Issue 2（低）已修复**：`remove_session` 现在同步调用 `self.session_store.remove(session_id)` 删除磁盘快照。已端到端验证 reset 后磁盘快照被删除。
3. **回归测试有效**：`test_websocket_resumes_from_store_after_process_restart` 新增断言 `texts.count("恢复我") == 1`（`tests/web_tests/test_server.py:937`），直接检查 LLM 实际收到的消息内容；还原预填逻辑后该断言会失败（count=2）。

全量测试通过（1813 passed, 7 skipped），OpenSpec strict validate 30/30，web 三层测试 75 passed。剩余问题均为低严重级（URL `?session=` stale 优先级的 UX 边界、remove_session 磁盘删除无独立回归测试），不阻塞合入。

## Tasks Verification

逐条对照 `openspec/changes/fix-issue-110/tasks.md`：

### 规格

- [x] `diagnosis.md` — 存在，含 Symptom / Reproduction / Evidence（带行号）/ Root Cause / Recommended Direction / Regression Tests。✓
- [x] `proposal.md` — 存在，Impact Analysis 明确不涉及 #117，memory 持久化列入已知边界（`proposal.md:48`）。✓
- [x] spec delta — `openspec/changes/fix-issue-110/specs/web-ui/spec.md` 新增 "Web session 本地持久化与恢复" Requirement（5 个 Scenario），与 `openspec/specs/web-ui/spec.md:291-326` 同步一致。✓
- [x] Reference Implementation Research — `status: disabled` + 原因（内部接线，无外部参考实现，`proposal.md:50-53`）。✓

### 测试

- [x] `test_websocket_reuses_inmemory_session_with_same_id` — `tests/web_tests/test_server.py:866-884`。同 id 二次连接复用内存 session，发 `session_resumed`。通过。✓
- [x] `test_websocket_resumes_from_store_after_process_restart` — `tests/web_tests/test_server.py:898-938`。预置快照 + 新 app 恢复，`session_resumed` + `session_history` 非空 + mode 正确 + 续跑 + **LLM 消息内容无重复断言**（`:937`）。通过。✓
- [x] `test_web_run_persists_session_to_store` — `tests/web_tests/test_server.py:940-962`。run 后 `SessionStore.list_sessions()` 含该 session 且 message_count == 2。通过。✓
- [x] `test_websocket_unknown_session_creates_new` — `tests/web_tests/test_server.py:886-896`。未知 id 回退新建并发 `session_created`。通过。✓
- [x] `test_resume_route_returns_html` — `tests/web_tests/test_server.py:981-987`。`GET /resume` 返回 200 HTML。通过。✓
- [x] 有效性验证 — Round 1 修复 commit 声称还原预填逻辑后 `count=2` 测试失败；逻辑推演确认（预填 + resume 分支叠加 → `"恢复我"` 出现 2 次 → `:937` 断言失败）。独立验证脚本（/tmp/verify_resume_r2.py）确认修复后 count=1。✓
- [x] 相关测试全绿 — 实测 `tests/web_tests/test_server.py test_session.py test_timeline.py` 75 passed；`tests/web_tests/` 76 passed, 7 skipped。✓

### 实现

- [x] `SessionManager` 构造 `SessionStore`（root = `workspace_root or cwd` 下 `.asterwynd/sessions`）+ `_create_session` 传 `session_store` — `web/session.py:262-265, 364`。✓
- [x] `resume_session_async` — `web/session.py:276-305`。内存命中复用；否则 `SessionStore.load` 重建（mode/user_system_prompt/resume_snapshot），**不预填 session.messages**（`:294-296`）；无快照返回 None。✓
- [x] WebSocket 恢复逻辑 + `session_resumed` / `session_history` 事件 — `web/server.py:169-194`。✓
- [x] `app.state.resume_session_id`（`--resume`）在 `/ws/new` 消费 — `web/server.py:173-177`；CLI 侧 `agent/main.py:696` 接线在 master 已有（本 change 未改 `agent/main.py`）。✓
- [x] `GET /resume` 路由 — `web/server.py:68-77`。✓
- [x] 前端 session id 记忆 / `session_history` 渲染 / reset 后更新 localStorage — `web/static/chat.js:139-159`（session_created/resumed/history 处理）、`:310-323`（rememberSessionId/renderHistory）、`:1430-1434`（URL ?session= → localStorage → null）；reset 后经新的 `session_created` 事件更新 localStorage。✓
- [x] 测试隔离 fixture — `tests/web_tests/conftest.py:34-45`（autouse chdir tmp）+ `tests/web_tests/test_server.py:45-46`（`app` fixture 传 `workspace_root=tmp_path`）。✓

### 文档

- [x] backlog 登记 — `docs/openspec-change-backlog.md` 新增 `### 6. fix-issue-110`，有 workflow-events seq 2 解释。✓
- [x] 当前规格同步 + workflow-events seq 3 `current_spec_synced` — `openspec/specs/web-ui/spec.md:291-326`。✓

### 审阅闭环 / 验证 / PR 收尾

- [x] Round 1 审阅（CHANGES_REQUESTED）— 已记录于本报告历史（被覆盖前）。
- [x] Round 1 修复 — `9ead6e0`：resume 不预填 + build_history_payload 回退 + remove_session 删盘 + 回归断言。已验证。
- [ ] Round 2 审阅（PASS）— 即本报告。
- [ ] 生成 review manifest — 待 review-loop PASS 后生成（当前 `check_openspec_artifacts.py` 因此报 manifest 缺失，属预期待办，非代码缺陷）。
- [x] `uv run pytest tests/web_tests/ -q` 通过（76 passed, 7 skipped）— 实测 75 passed（3 个指定文件）。
- [x] `uv run pytest -q` 全量通过（1813 passed, 7 skipped）— 本次实测复现。
- [x] `npx @fission-ai/openspec@1.4.1 validate --all --strict` 通过（30/30）— 本次实测复现。
- [ ] `uv run python scripts/check_openspec_artifacts.py` 通过 — 当前唯一报错是 `building-review-manifest.json` 缺失，待 PASS + manifest 生成后满足。
- [x] Web smoke 由回归测试覆盖 — reuses_inmemory / resume_route+URL / resumes_from_store / resume_cli 均有测试。

## Issues

### 无未解决的中等问题

Round 1 的 Issue 1（中）与 Issue 2（低）均已修复并经端到端验证（见上）。以下为本轮仍存在的低严重级问题，不阻塞合入：

### 低：URL `?session=` stale id 永优先生效（Round 1 Issue 3，未处理）

- **文件:行号**：`web/static/chat.js:1434`（`sessionId = urlSession || localStorage.getItem(...) || null`）。
- **影响**：书签 `/resume?session=<已删除id>` 时，每次刷新都重连该死 id → 服务端每次新建 session 并回发新 id，localStorage 被更新但 URL 参数下一跳仍优先指向死 id，造成「每次刷新都是新会话」。属显式恢复入口的边界 UX 问题。
- **修复建议（可选）**：收到 `session_created` 且 id 与 URL 参数不一致时，用 `history.replaceState` 清理 `?session=`。非阻塞。

### 低：remove_session 磁盘删除无独立回归测试

- **文件:行号**：`web/session.py:379-382`（`remove_session` 调 `self.session_store.remove(session_id)`）。
- **影响**：Issue 2 修复有实现但无专门回归测试；reset 流程（`web/server.py:424-427`）走 `remove_session`，但没有测试断言 reset 后磁盘快照消失。本次审阅已用独立脚本（/tmp/verify_remove_r2.py）人工验证。
- **修复建议（可选）**：新增一条测试——预置快照 → 连 `/ws/<id>` 恢复 → 发 `{"type":"reset"}` → 断言 `SessionStore.load(id)` 返回 None。非阻塞。

### 信息：grill-design.md 决策记录与最终实现存在一处口径漂移

- **文件:行号**：`openspec/changes/fix-issue-110/reviews/grill-design.md` 决策 4 原文称「恢复重建时 `session.messages` 来自 `snapshot.messages`」。
- **影响**：Round 1 修复后，实现改为不预填 `session.messages`（`web/session.py:294-296`），由 `_run` 的 resume 分支重建，故该决策记录的历史水合描述已过时。纯文档口径问题，代码注释已正确说明新行为。
- **修复建议（可选）**：在 grill-design.md 决策 4 加一行注记说明 Round 1 修复后的行为变更。非阻塞。

### 信息：`/ws/<session_id>` 的 session_id 未经显式校验

- **文件:行号**：`web/server.py:169-177` → `web/session.py:290`（`session_store.load(session_id)`）。
- **影响**：`SessionStore._validate_session_id` 对非法 id（绝对路径/越界）抛 `ValueError`，会向上冒泡到 WS 处理器导致该连接异常关闭。FastAPI 路径参数不含 `/`，单段 id 无法构成路径穿越；且 `_validate_session_id` 在读取前就拦截，无文件访问风险。属信息级，与 CLI 既有语义一致。
- **修复建议（可选）**：WS 端点可包一层 try/except 回退新建。非阻塞。

## Test Results

| 范围 | 结果 |
| --- | --- |
| `tests/web_tests/test_server.py test_session.py test_timeline.py` | **75 passed**（本轮实测） |
| `tests/web_tests/`（含 browser） | 76 passed, 7 skipped |
| 全量 `pytest -q` | **1813 passed, 7 skipped**（本轮实测） |
| `npx @fission-ai/openspec@1.4.1 validate --all --strict` | **30 passed, 0 failed**（本轮实测） |
| `scripts/check_openspec_artifacts.py` | 唯一报错：`building-review-manifest.json` 缺失（预期，待 PASS + manifest 生成后通过） |

均使用 `PATH="$HOME/.local/bin:$PATH" uv run python -m pytest ...`。附加独立验证（写 /tmp，未改动仓库文件）：

- `/tmp/verify_resume_r2.py`：预置快照 `[user "恢复我"]`，resume 后发 `chat "继续"`，LLM 收到 `[system, user "恢复我", user "[Session resumed...]", user "继续"]`——`"恢复我"` 出现 **1 次**（修复前为 2 次）。✓
- `/tmp/verify_remove_r2.py`：预置快照 → 连 `/ws/<id>` 恢复 → `reset` → `store.load(id)` 返回 None（磁盘快照已删）。✓

## 结论

Round 1 的核心正确性缺陷（resume 恢复后首次 run 把快照历史重复送入 LLM 并随落盘累积）已修复并通过端到端验证与 LLM 消息内容断言回归；reset 孤儿快照问题也已修复。实现复用 CLI 既有 `SessionStore`/`resume_snapshot` 基础设施，前后端接线完整，spec delta 与规格同步一致，测试与文档齐全，全量测试与 OpenSpec 校验均通过。剩余问题均为低严重级或信息级，不阻塞合入。**判定 PASS**。

审阅闭环后续待办（非本审阅范围）：review-loop 生成 building-review manifest，补跑 `check_openspec_artifacts.py`，归档 change 至 archive、清理 backlog、发起 PR 并关闭 issue #110。
