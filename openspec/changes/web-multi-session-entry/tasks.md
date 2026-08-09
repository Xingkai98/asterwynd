# Tasks: web-multi-session-entry

关联跟踪 issue：[#117](https://github.com/Xingkai98/asterwynd/issues/117)。

## 1. 规格

- [x] 1.1 更新受影响 capability 的 spec delta（web-ui）。
- [x] 1.2 明确本 change 的范围、非目标和验收标准。
- [x] 1.3 开发前使用 `batch-grill-me` 或等价设计追问审视 `design.md`，逐项确认每个关键实现细节、依赖、风险、测试策略和文档影响都有最终方案；不得把 agent 自己的推荐答案当作用户确认。重点收敛：host 默认绑定策略、uploads 归属、hub 列表范围、新建会话 API 形态、per-session run 互斥、workspace 校验入口覆盖、`--resume` 与新建冲突、reset 保留 workspace/mode、open_tabs 持久化、per-tab 状态完整性、恢复搜索确定性、spec delta 边界。
- [x] 1.4 维护 `## Impact Analysis`，列出影响、不影响和待确认影响面；开发前把待确认项清理为明确结论或阻塞项。
- [x] 1.5 维护 `## Reference Implementation Research`；记录最终调研状态、发现和设计影响。
- [x] 1.6 在 `design.md` 的 `## Pre-Implementation Review` 记录已解决问题、备选方案、否决方案、最终确认和剩余风险。
- [ ] 1.7 当前规格同步：把 web-ui spec delta 合并到 `openspec/specs/web-ui/spec.md`，确认未实现能力没有被写成已实现，并配 workflow-events.jsonl 解释事件。

## 2. 测试

- [x] 2.1 后端集成测试（`tests/web_tests/test_server.py`，fake LLM）：
  - `GET /api/workspaces` 返回主 workspace + allowlist，`is_primary`/`exists`/`session_count` 字段正确。
  - `GET /api/sessions` 返回列表结构（session_id/mode/created_at/updated_at/messages），缺省用主 workspace；未授权 workspace 返回 403 + 结构化错误。
  - `DELETE /api/sessions/{id}?workspace=` 删除内存 + 磁盘快照，hub 列表不再展示；**冷会话删除**（未打开过、不在内存的会话经 DELETE 也能按请求 workspace 定位并删除快照）。
  - `/ws/new?mode=&workspace=` 创建指定 mode/workspace 的 session；非法 mode 与未授权 workspace 分别返回 `invalid_mode` / `workspace_not_allowed` 且不创建。
  - `/ws/new` 带显式参数时不被 `--resume` 拦截（`create_app(resume=...)` 下带 workspace 参数新建出全新 session）；**裸 `/ws/new` 仍保留 `--resume` 语义**（`create_app(resume=...)` 下裸 `/ws/new` 返回 resume 会话，design review I5）。
  - 多 workspace：两个 workspace 各自创建/列出/恢复会话互不串扰；跨 workspace 同 session_id 按确定性顺序（主 → allowlist）取主。
  - per-session run 互斥：同一 session 并发 `chat` 第二个返回 `another run is already in progress`，不启动第二次 run；run 结束后可再次发送。
  - 进程重启恢复：`SessionStore` 落盘 → 新 app 实例 `/ws/<id>?workspace=` 恢复 → `session_resumed` + `session_history`。
  - 恢复归属闭环（design review I2）：无 workspace 恢复 allowlist 会话后再次 run，快照仍写入该 allowlist store、主 store 不新增。
  - `/ws/{id}?workspace=` 未授权 workspace 返回 error 事件并关闭连接，不创建/不恢复会话（design review I6）。
  - reset 保留原 workspace/mode（非主 workspace 会话 reset 后替换品仍在原 workspace）。
- [x] 2.2 前端 Playwright smoke（`tests/web_tests/test_browser.py`，fake LLM）：
  - hub 渲染会话列表；点开进入 tab 并展示历史。
  - 多标签切换：开两个 tab 各自发送消息，消息落到各自容器；切换 active tab 后 planning/plan-document/debug 面板跟随。
  - per-tab 隔离（design review I5/I13）：两个 tab 各自触发审批/图片上传，卡片与预览只落各自 tab；一个 tab 结束（continue_session=false）不影响另一 tab 的 reconnect；两个 tab 的 slash 匹配状态互不串扰。
  - 新建会话表单（mode/workspace）打开对应会话。
  - 刷新回到最近会话（localStorage 记忆 session_id + workspace）。
  - 删除会话后对应 tab 被关闭。
- [x] 2.3 负向/边界：workspace 输入 `..` 穿越、符号链接、尾部斜杠、大小写变体、不存在路径均被 `resolve_workspace()` 拒绝（覆盖 `/api/sessions`、`/ws/new`、`/ws/{id}?workspace=` 三个入口）；allowlist 为空时主 workspace 仍可用；不存在的 allowlist 项启动时打 warning；`DELETE /api/sessions/{id}` 缺 `?workspace=` 返回 400。
- [x] 2.4 CLI 层级：`web` 命令 `--host` 默认值为 `127.0.0.1`（design review I17，补 test_cli.py web 命令 host 默认断言）；显式 `--host 0.0.0.0` 才开放 LAN。
- [ ] 2.5 涉及 CLI/Web/工具协议核心路径，跑通至少一个对应层级回归（`uv run pytest -q` 全量）。

## 3. 实现

- [x] 3.1 `agent/config.py`：新增 `WebConfig`（`workspaces: tuple[Path, ...]`）+ `AsterwyndConfig.web` 字段 + YAML 解析校验；allowlist 空时有效集合 = {主 workspace}，不破坏现有用户默认行为。
- [x] 3.2 `web/session.py`：
  - `SessionManager` store 从单例改为 `_stores: dict[str, SessionStore]`（key 为 `Path.resolve()` 规范化路径）；`_store_for(workspace_root)` 惰性创建。
  - `_create_session` / `create_session_async` / `resume_session_async` 增加 workspace 参数；`AgentSession.workspace_root` 字段。
  - `resolve_workspace(input)` 统一校验（expanduser().resolve() + 有效集合成员判断），覆盖 `/api/sessions`、`/ws/new`、`/ws/{id}?workspace=`。
  - `resume_session_async` 未带 workspace 时按主 → allowlist 配置序搜索。
  - `remove_session` 按 session 的 workspace 解析 store 删除快照。
  - per-session `run_lock: asyncio.Lock`，`run_session` 入口 `acquire_nowait()`，拒绝时回 error 事件不阻塞。
  - `reset` 保留原 workspace/mode。
- [x] 3.3 `web/server.py`：新增 `GET /api/workspaces`、`GET /api/sessions`、`DELETE /api/sessions/{session_id}?workspace=`；`/ws/new` 解析 `mode`/`workspace` 查询参数并校验（非法/未授权返回结构化 error）；`/ws/new` 带显式参数时跳过 `resume_target`；`/ws/{id}?workspace=` 未授权返回 error 事件并关闭连接；`create_app` 启动时解析有效 workspace 集合存入 `app.state`，对不存在的 allowlist 项打 warning。
- [x] 3.4 `agent/main.py`：`web` 命令 `--host` 默认值改为 `127.0.0.1`；`display_host` 逻辑适配。
- [x] 3.5 `web/static/chat.js`：单例全局状态重构为 per-tab 模型（`tabs: Map` + `activeTabId`），Tab 字段完整（sessionId/workspace/mode/ws/currentAssistantMsg/approvalCards/questionCards/pendingImages/shouldReconnect/slashMatches/activeSlashIndex/debugEvents/debugIterBlocks/planningState/planDocState/messagesEl/statusEl/inFlight/uploadWaiters）；事件分发 `handleTabEvent(tab, event)`；hub 视图（workspace 选择器 + 会话列表 + 新建表单 + 删除）；恢复优先级 URL → localStorage（session_id + workspace）→ hub → 新建；不持久化 open_tabs。
- [x] 3.6 `web/static/index.html`：标签栏容器、`#hub-view`、动态消息容器模板；`web/static/style.css`：hub/标签栏/动态容器样式。
- [ ] 3.7 如果实现中发现新影响面，先回写 Impact Analysis 和本任务清单，再继续无关实现。
- [ ] 3.8 如果实现中发现参考实现调研结论需要修正，先回写 Reference Implementation Research 和本任务清单。
- [ ] 3.9 更新必要文档（架构说明、README 若涉及 Web 使用方式；`README_EN.md` 同步）。

## 4. 验证

- [ ] 4.1 运行相关单元/集成测试（`uv run pytest tests/web_tests/ -q`）。
- [ ] 4.2 运行全量测试（`uv run pytest -q`）。
- [ ] 4.3 运行 OpenSpec strict validate（`npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`）。
- [ ] 4.4 运行项目 OpenSpec artifact checker（`PYTHONPATH=. python3 scripts/check_openspec_artifacts.py`）。
- [ ] 4.5 独立审阅闭环 `/review-loop web-multi-session-entry`：逐任务验证、正确性、Spec 对齐、测试覆盖、安全性、可维护性、CI 完整性；PASS 或 3 轮封顶，产出 `reviews/building-review.md` + review manifest。
- [ ] 4.6 确认 baseline CI 命令可本地通过。

## 5. PR 收尾

- [ ] 5.1 PR 发起前，将本 change 归档到 `openspec/changes/archive/YYYY-MM-DD-<change-id>/`。
- [ ] 5.2 从 `docs/openspec-change-backlog.md` 移除或更新本 change，并同步并行开发批次。
- [ ] 5.3 确认 Impact Analysis 不再残留未解释的 `unknown`、`TBD` 或 `待确认`。
- [ ] 5.4 确认 Reference Implementation Research 已记录最终调研状态、发现和设计影响，且没有把本地参考仓库路径写成项目依赖。
- [ ] 5.5 给 issue #117 添加完成说明 comment 并关闭。
