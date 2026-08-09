# Grill Design Review — fix-issue-110

## Reviewer

- run id: `b2f6a4d0-1c8e-4b7a-9f3d-5e2a8c6b7d1f`
- 时间: 2026-08-09
- 范围: 独立零记忆审问。只读 `proposal.md` / `diagnosis.md` / 相关实现代码，仅产出本决策记录，未修改任何其他文件。
- 约束: 本 change 为 bugfix（primary: bugfix），设计目标是"最小修复复用既有基础设施"。审问区分"必须修的问题"与"可留给 feature #117 的问题"。

## Confirmed Decisions

- **决策**: 复用 CLI 既有 `SessionStore`/`SessionSnapshot`/`AgentLoop.resume_snapshot` 作为 Web session 持久化/恢复基座是正确且最小的方向。
  理由: 三个断点（不落盘/不记忆/不恢复）全部有现成机制可接：落盘靠 `AgentLoop._save_session`（`agent/loop.py:1391-1416`，在 `run` 的 `finally` 中调用 `agent/loop.py:530-534`），恢复靠 `resume_snapshot`（`agent/loop.py:557-584`），存储靠 `SessionStore`（`agent/session.py:81-228`）。Web 侧此前唯一缺的是接线。
  来源: `agent/loop.py:530-534, 557-584, 1391-1416`；`agent/session.py:81-228`。

- **决策**: 方案必须同时包含"前端 localStorage 记忆 session id"与"服务端持久化+按 id 恢复"两个半场，缺一不可。
  理由: 前端不记忆 id → 刷新必然重连 `/ws/new`（`chat.js:5` 置 null、`chat.js:102` 拼 `/ws/${sessionId||'new'}`）→ 即使服务端能恢复也拿不到目标 id；只做前端记忆、不落盘 → 服务端进程重启后内存全丢（`web/session.py:226` 纯内存 dict）仍无法恢复。localStorage-only 或 server-restore-only 都只覆盖一半症状。
  来源: `web/static/chat.js:5, 102, 1430-1434`；`web/session.py:226`；`diagnosis.md:26-32`。

- **决策**: 落盘接线方式（`_create_session` 把 `session_store` 传给 `AgentLoop`）正确，run 结束自动持久化覆盖 messages/mode/todos/skills/system prompt，不覆盖 memory 是合理裁剪。
  理由: `_create_session` 已传 `session_store=self.session_store`（`web/session.py:355`），`AgentLoop.run` 的 `finally` 自动 `_save_session`。快照字段（`agent/loop.py:1402-1415`）与 proposal 声明的持久化范围一致；Web 当前用内存 `MemoryManager`（`web/session.py:346`），memory 持久化归 #117 属明确非目标。
  来源: `web/session.py:346, 355`；`agent/loop.py:1402-1415`；`proposal.md:48`。

- **决策**: 恢复路径事件序列（`session_resumed` + `session_history`，失败回退 `session_created`）正确，且同进程二次重连（内存命中）与跨进程恢复（快照重建）行为一致。
  理由: WS 端点 `get_session` 未命中 → `resume_session_async`（内存命中复用，否则 `SessionStore.load` 重建并持 `resume_snapshot`）→ 仍无则 `create_session_async` 新建（`web/server.py:169-194`）；`session_history` 由 `build_history_payload` 序列化（`web/session.py:33-53`），快照恢复的会话在首次 run 前 `session.messages` 为空时回退用 `resume_snapshot.messages` 渲染历史。unknown id 回退新建后回发新 id，前端据此更新 localStorage，自愈成立（`chat.js:140-144`）。
  来源: `web/server.py:169-194`；`web/session.py:268-295, 33-53`；`chat.js:140-144`。

- **决策**: 历史水合用 `extract_text` 丢图片 block 对 agent 上下文无损，仅前端展示丢图，可接受为本 fix 的已知边界。
  理由: `extract_text` 只取 `TextBlock.text`（`agent/message.py:68-74`），`session_history` 丢图；恢复后的 `session.messages` 在首次 run 后由 `_run` 从 `resume_snapshot` 重建为完整 block 列表（`web/session.py:435-446, 461-464` 传 `resume_snapshot` 并消费后清空；`agent/loop.py:570-575` 重建），下一次 run 时 LLM 仍拿到图片。rich 历史序列化可归 #117。
  来源: `agent/message.py:68-74`；`web/session.py:33-53, 435-446`；`agent/loop.py:570-575`。

- **决策**: store 根路径 `(workspace_root or cwd)/.asterwynd/sessions` 与 CLI 一致，未显式指定 workspace 时以 cwd 为根符合预期。
  理由: 与 CLI `_sessions_root`（`agent/main.py:214-215`）完全同语义；CLI `session resume`/交互也按 `workspace_root or cwd` 解析（`agent/main.py:219-220, 395`）。跨目录启动找不到旧 session 属既有 workspace 作用域语义，非本 fix 引入。
  来源: `web/session.py:254-257`；`agent/main.py:214-215, 219-220, 395`。

- **决策**: `--resume` 的"静默替换"风险主要被 CLI 启动校验消解，WS 层回退新建只是兜底；但代码与文档存在一处语义偏差需要修正。
  理由: `asterwynd web --resume <id>` 在启动时已 `_load_resume_snapshot` 校验，id 缺失即 `SystemExit(1)`（`agent/main.py:684-689, 218-228`），因此 WS 端 `resume_session_async` 失败的"静默新建"只在直接调用 `create_app(resume=...)` 的嵌入场景触发。但 `app.state.resume_session_id` 消费后未清空，实际是"每次 `/ws/new` 都命中"而非 diagnosis.md 所述"首次连接"——行为无害但措辞需与代码对齐。
  来源: `agent/main.py:218-228, 684-689`；`web/server.py:46, 173-177`；`diagnosis.md:41`。

- **决策**: 替代方案（只做 localStorage / 只做服务端恢复）均不成立，当前双半场方案是能覆盖 issue #110 全部症状的最小改动。
  理由: 见 Confirmed Decisions 第 2 条。localStorage-only 无法覆盖诊断中列出的进程重启场景（`diagnosis.md:14`），server-restore-only 无法覆盖前端刷新忘 id 的主症状（`chat.js:5,102`）。复用既有基础设施的改动面集中在 `web/session.py`、`web/server.py`、`chat.js`，无新依赖（`proposal.md:34`）。
  来源: `chat.js:5, 102`；`diagnosis.md:14, 28-32`；`proposal.md:34-35`。

- **决策**: session_id 路径安全性由 `SessionStore._validate_session_id` 保证，WS URL 传入的 id 同样受保护；unknown id 自愈为新 session 不回退错误是合理行为。
  理由: `_validate_session_id` 拒绝绝对路径与路径穿越（`agent/session.py:196-203`），`load`/`save`/`remove`/`list_sessions` 均经它校验；`/ws/{session_id}` 单段路由 + 校验双重防护。unknown id 直接新建并回发 `session_created`（`web/server.py:179-185`）符合"刷新不丢会话"主目标。
  来源: `agent/session.py:196-203`；`web/server.py:179-185`。

## Open Questions

- **Q1（并发运行）**: 两个同源标签页共享 `localStorage` 的 session id，本 fix 后两标签页都会重连同一 `/ws/<id>`（此前各标签页独立 session，无此暴露面）。`run_session` 无锁（`web/session.py:382-543` 直接 `create_task(run_agent)`），`AgentLoop` 无 running guard（`agent/loop.py` 未见锁/忙标志），两连接并发 `chat` 会并发跑同一 AgentLoop，污染共享可变状态（todos、iteration、`_active_on_event`、hooks）。是否需要在本 fix 内加 per-session 互斥（如 `asyncio.Lock` 拒绝并发 run 并回发 error 事件），还是接受该风险留给 #117 多 session 入口统一处理？推荐: 本 fix 内加轻量互斥，因为这是本 fix 新引入的暴露面，且实现成本低（run_session 入口一个 lock）。

- **Q2（进程重启恢复是否为本 fix 硬验收）**: 诊断把"服务端进程重启"列为主症状之一（`diagnosis.md:14`），但 issue #110 标题与复现步骤聚焦"刷新后丢失"。Store 接线 + `resume_snapshot` 是复杂度主体。是否确认"进程重启后经 `/ws/<id>` 可恢复"是本 fix 的验收标准（推荐: 是，与 diagnosis 一致），还是可将 Store 落盘/恢复裁到 #117，本 fix 只做 localStorage + 同进程内存复用？

- **Q3（恢复历史丢图展示）**: 恢复后的 `session_history` 用 `extract_text` 只含文本，历史图片在前端不再显示（agent 上下文不丢）。是否接受"恢复视图不显示历史图片"（推荐: 接受，rich 历史归 #117），还是需要在 `session_history` 里带上图片 URL/file_path 供前端渲染缩略图？

- **Q4（"[Session resumed]" marker 跨重启累积）**: `resume_snapshot` 每次被消费时 `_run` 都会追加一条 `[Session resumed...]` user message（`agent/loop.py:574`），该 marker 随会话落盘成为历史；同进程内刷新不重复（消费后 `finally` 置 None，`web/session.py:455`），但每次服务端重启 + 首次 run 都会新增一条 marker。是否接受累积（推荐: 接受，属既有 CLI 共享行为，改动会触碰共享 `resume_snapshot` 逻辑，不纳入本 fix），还是要在共享恢复逻辑里"末条已是 marker 则跳过"？

- **Q5（`--resume` 语义与静默回退）**: 需确认两点：(a) `app.state.resume_session_id` 消费后未清空，实际每次 `/ws/new` 都会命中，与 diagnosis.md"首次连接"措辞不符——接受"每次命中"并改文档措辞，还是改成"消费后清空"？(b) 直接 `create_app(resume=<不存在id>)` 时静默新建新 session 且无提示，是否可接受，还是要回发一个 `resume_failed`/警告事件？（CLI 入口已启动校验不会走到此路径，仅影响嵌入/测试用法。）

## User Confirmation

- **Q1**: 用户答复：接受风险留给 #117，本 fix 不加 per-session run 互斥；确认时间: 2026-08-09
- **Q2**: 用户答复：保留为验收项——进程重启后经 `/ws/<id>` 恢复原 session 是本 fix 验收标准；确认时间: 2026-08-09
- **Q3**: 用户答复：接受恢复视图纯文本历史（历史图片不显示，agent 上下文不丢）；确认时间: 2026-08-09
- **Q4**: 用户答复：接受 "[Session resumed]" marker 跨重启累积；确认时间: 2026-08-09
- **Q5**: 用户答复：接受"每次 `/ws/new` 连接都命中 resume id"并修正文档措辞为与代码一致；静默新建可接受（CLI 启动已校验 id 存在）；确认时间: 2026-08-09

## 风险

- **中**: 并发 run 同一 AgentLoop（两标签页共享 localStorage id）。若不在本 fix 加互斥，可能导致工具执行/todo/mode 状态互相覆盖。缓解：本 fix 加 per-session `asyncio.Lock`（拒绝并发）或前端用 `sessionStorage`（per-tab）替代 `localStorage` 记忆 id（后者会牺牲跨标签页恢复）。需 Q1 拍板。
- **中**: 恢复视图历史图片不显示。纯前端展示问题，agent 上下文不丢。缓解：Q3 确认接受即闭环。
- **低**: `resume_session_async` 调用 `SessionStore.load(session_id)` 未传 `current_runtime_fingerprint`（`web/session.py:282`），Web resume 不会像 CLI 那样对 model/provider/cwd 指纹不匹配告警（`agent/session.py:136-138`）。恢复出的 session 可能沿用不同 runtime 配置的工具链而用户无感知。
- **低**: `reset` 只 `remove_session`（内存 pop，`web/session.py:372-373`），不从 store 删除快照（`web/server.py:424-433`），磁盘孤儿快照会累积，无 GC 机制。
- **低**: `session_history` 每次重连全量重发文本历史，超长会话存在 payload 体积问题（前端 `MAX_CHAT_PAYLOAD_CHARS` 12MB）。
- **低**: `--resume` 每次 `/ws/new` 命中的实际行为与文档"首次连接"不符，属文档口径问题，需 Q5 对齐。
- **低**: "[Session resumed]" marker 跨重启累积，恢复历史中会出现多条重复 marker，观感不干净（Q4）。
