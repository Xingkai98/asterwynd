# Grill: fix-issue-304-dangling-tool-calls 设计追问

## Reviewer
- run id: fb029c8c-4f40-4fbc-8dfc-e1daff8bc052
- 时间: 2026-11-02

## Confirmed Decisions

> 本小节是 grill 当时的记录；后续对抗轮产生的修订见各决策行后的「后续修订」注记，最终口径以 `design.md` / `specs/` 为准。
- **决策**: 修复放在 `AgentLoop` 的 run 边界（`_run` 起点为主修，`run()` finally 落盘前 best-effort），不在 `SessionStore.load`、resume-only 或 provider 序列化层做主修；理由: load 是忠实快照层且覆盖不了同进程重试（`web/session.py:2125-2149`），resume 分支只在有快照时执行（`agent/loop.py:709`），序列化层只改临时 payload 且要同时改 Anthropic/OpenAI 两套（`agent/anthropic_llm.py:227-304`、`agent/openai_llm.py:279-317`），run 边界一次覆盖 Chat、群聊成员、CLI resume 与 subagent；来源: fb029c8c-4f40-4fbc-8dfc-e1daff8bc052
- **后续修订（ADV-8/ADV-D2，2026-11-02）**: resume 的消息重建与 todos/skills/user_system_prompt 同步恢复 SHALL 移到 `set_mode` await 之前，避免早期取消用截断历史/未恢复状态覆盖快照。
- **决策**: 为缺失 id 补一条明确标记为合成的 `tool` 消息，不丢弃悬空 assistant、不删除其 `tool_calls`；理由: 合成是加法，保留 assistant 已产出的文本/reasoning 与「中断发生」事实；丢弃会不可逆地篡改用户已看到的历史，删除 tool_calls 则丢失工具意图；理由与 RIR 中 pydantic-ai/ADK/Bernstein/OpenAI Agents 的合成方向一致；来源: fb029c8c-4f40-4fbc-8dfc-e1daff8bc052
- **决策**: 合成内容必须确定性、固定前缀 `[asterwynd:synthetic-tool-result]`、携带原 `tool_call_id`，文案包含工具名/id 且不含时间戳/随机值；理由: 幂等判据是「该 id 是否已被 assistant 后连续 tool 块覆盖」，第二次修复必须 `changed=False` 且 `Message.to_dict` 字节一致，才能钉住 prompt cache 稳定性（`agent/message.py:162-177`、`208-210`）；来源: fb029c8c-4f40-4fbc-8dfc-e1daff8bc052
- **决策**: `run()` finally 的补配对必须同步、异常隔离、只写 warning，不 await 事件，且不得吞掉原始 `CancelledError`/异常；理由: 取消状态下再次 await 可能被取消，纯内存 O(n) 操作不会引入挂起点；`run()` 的 finally 已承担 `_save_session`（`agent/loop.py:655-662`、`1744-1770`），补配对放在其前即可保证落盘快照合法；来源: fb029c8c-4f40-4fbc-8dfc-e1daff8bc052
- **后续修订（ADV-2，2026-11-02）：仍要求同步/异常隔离/不 await Web 事件，但若 `trace_recorder` 存在，SHALL 同步记录 `source="finally"` 的 `tool_pairing_repaired` trace step。**
- **决策**: 诊断性统一在 `raise_for_status()` 前提取响应体（流式 `aread()`，非流式直接读），把完整可读 body 附加到 `httpx.HTTPStatusError` 属性（trace/Web/群聊展示时才截断），异常类型与 reasoning/cache/vision 重试语义保持不变；理由: 当前流式路径在 `agent/llm.py:132-136` 直接 raise、Web 错误事件只带 `type: message`（`web/session.py:2133-2138`），body 已可由 `_http_error_text` 读取（`agent/anthropic_llm.py:68-81`），属传播缺口；来源: fb029c8c-4f40-4fbc-8dfc-e1daff8bc052
- **后续修订（ADV-D1，2026-11-02）**: 群聊共享日志不写 provider 的 `error.message`/原始 body，只用 `HTTP <status>` + allowlist 校验的 `error.type` 固定摘要；原始 bounded detail 只给成员自己的连接。
- **决策**: 不新增 `Message.is_error`，用文本标记表达中断；空 `tool_call_id` 不合成、只日志；理由: `Message` 无该字段（`agent/message.py:146-155`），Anthropic 的 `is_error` 与「中断」不完全等价且 OpenAI 无对应字段；正常 provider 不会产生空 id（`agent/llm.py:24-27`），空 id 属畸形输入，不应伪造可序列化配对；来源: fb029c8c-4f40-4fbc-8dfc-e1daff8bc052
- **后续修订（ADV-3，2026-11-02）**: 仍不新增 `Message.is_error` 字段/不改持久化 schema；但 Anthropic 序列化层按固定合成前缀写 `is_error: true`，OpenAI 兼容路径用 `Error:` 文本前缀作为等价信号。

## Code-Resolved Questions
- Q1 合成结果是否在 Web 历史中可见：可见，且不需要新增前端组件。`session_history` 投影包含 `role:"tool"` 的 `content` 与 `tool_call_id`（`web/session.py:76-108`），前端把非空 tool content 渲染成折叠工具行（`web/static/chat.js:781-789`、`814-841`），合成内容非空且带固定前缀，会出现在摘要/展开体。补充缺口：首次重连、尚未发起新 run 时，`build_history_payload` 回退到 `resume_snapshot.messages`（`web/session.py:82-89`），而 `_restore_snapshot` 不预填 `session.messages`（`web/session.py:1716-1718`），因此修复前显示的历史仍可能是悬空链；要满足 proposal 的「历史里能看到」需要在 history payload 做只读副本修复，或明确把可见性推迟到首次 run。
- Q2 错误详情展示形态：沿用现有错误文本出口即可。错误事件走 `addMessage('error', readableErrorMessage(...))`（`web/static/chat.js:672-675`），`addMessage` 对非 assistant 使用 `body.textContent`（`web/static/chat.js:950-976`），`.message` 已设 `white-space: pre-wrap`（`web/static/style.css:161-168`），所以 `message + "\n" + detail` 会按换行展示；不需要新增折叠组件，也不存在 HTML 注入。
- Q3 合成结果是否附带工具名/id：Decision 2 的文案已经明确包含 `'<name>' (<id>)`，且历史投影本来就带 assistant `tool_calls` 的 id/name（`web/session.py:57-73`）。结论是两者都保留；design 的 Q3 与 Decision 2 自相矛盾，应删除该 Open Question，而不是停下来问用户。
- 空 `tool_call_id`：`ToolCallDelta.id` 是普通 string（`agent/llm.py:24-27`），真实 provider 不会给空 id；design 的「不合成、只日志」可接受，但应在测试中记录该畸形输入仍可能被上游拒绝，不能宣称已自愈。
- 连续 user 消息是否合法：resume 分支本身就会把 `[Session resumed...]` 与新用户消息追加在历史之后（`agent/loop.py:725-730`），复现 payload 已出现两个连续 user 消息（`/tmp/repro-304.md`）；修复后 assistant(tool_use) → user(tool_result) → user(text) 只是沿用既有形态。官方文档在本环境不可直接访问，但既有代码与复现均依赖该形态，风险低。
- 群聊失败原因：当前 `_run_session_locked` 只有 `turn_error` 布尔，没有 `turn_error_message`；`TurnOutcome(status=..., text=turn_text)` 也没带 message（`web/session.py:2181-2199`、`2232-2234`）。design 把 `turn_error_message` 写成既有变量是行号/事实错误；实现时需新增该变量，在 drain `error` 事件时保存 `data["message"]`（含 bounded detail），再传给 `TurnOutcome.message`，并补群聊系统日志测试。
- max_iterations 与 finally 修复是否冲突：正常 max_iterations 路径在迭代内已把每个工具结果 append 后才返回（`agent/loop.py:1099`、`1136-1155`），finally 扫描应为 no-op；只有异常/取消才需要补齐，不改变 max_iterations 语义。
- 压缩是否会拆开修复后的链：`_recent_with_tool_chains` 会把 recent window 的起点向前扩到每个 tool result 对应的 assistant（`agent/memory/manager.py:461-479`），合成 tool 消息与 assistant 相邻，压缩后仍配对；`_annotate_pending_calls` 从 middle+recent 收集 `tool_call_id`（`agent/memory/manager.py:513-527`），修复后不会再把该调用标 pending。
- spill/ref 是否会让修复误判：spill 只替换 `content`、保留 `role="tool"` 与 `tool_call_id`（`agent/memory/tool_result_spiller.py:123-149`），配对判据只看 id；合成结果是小文本且只有真实结果路径会 `mark`（`agent/loop.py:1100`），不会被误剪，也不会被误当缺失。
- 事件与 trace 是否可用：`TraceRecorder.record` 接受任意 step type（`agent/trace_recorder.py:81-91`），新增 `tool_pairing_repaired` 是加法；前端 switch 没有 default 分支，未知事件会被忽略（`web/static/chat.js:672-724`），不会破坏现有 WebSocket 客户端。
- RIR 证据是否充分：pydantic-ai PR #6319 存在且 merged 2026-07-14，OpenAI Agents JS issue #1190 已 closed，ADK commit 与 LangGraph 文档 URL 均可访问；`platform.claude.com` 的最终 URL 是 `https://claude.com/app-unavailable-in-region`，佐证 proposal 的区域阻断说明。缺口是 research questions 问了 codex，findings 没有 codex 的对应结论；另外 Anthropic 官方条款只能以搜索摘要 + issue 真实错误文案交叉确认，`is_error` 部分证据强度低于其他来源。
- ADR 编号：`docs/adr/` 现有 0001-0008，`ADR-0009` 未被占用，design Decision 10 可用。
- 门禁与 protected artifact：`.witnessloop/policy.json` 把 `docs/openspec-change-backlog.md` 列为 protected；本 change 的 `workflow-events.jsonl` 已有 `backlog_updated` 事件（seq 2）；本 change 不改 checker/witnessloop。`npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` 实测 29/29 通过。
- grill 证据格式：checker 只统计 `## Confirmed Decisions` 下以 `- **决策**:` 开头的行（`scripts/check_openspec_artifacts.py:981-998`），本报告已满足 ≥3 且每条带同行 `来源:`；`## Open Questions` 为空时不会触发未确认门。
- finally 修复与 `_save_session` 的列表身份：`run()` 把同一个 `messages` 传给 `_run`（`agent/loop.py:647-654`），`_run` 用 `messages.clear()/extend()` 就地重建（`agent/loop.py:726-730`），因此在 `_run` 起点或 finally 中 `messages[:] = repaired` 都能被 `_save_session` 和同进程下一次 run 看到。
- 错误详情换行：`.message` 的 `white-space: pre-wrap`（`web/static/style.css:161-168`）已覆盖 `.message.error`；此前担心的「换行被折叠」不成立，无需新增 CSS 任务。

## Open Questions
- 无

## 风险
- **Blocker/High**: `tasks.md` 0.3 写「按批次模型收敛到 PASS（无轮数上限，用户已拍板）」，与 AGENTS.md 的「最多 20 个已收口轮，第 20 轮后仍非空 ⇒ 超上限 BLOCKED」直接冲突；`workflow-events.jsonl` 没有用户豁免记录。若不放宽为 20 轮上限，设计对抗环与实现审阅环会违规。
- **High**: spec delta 写「修复发生时 SHALL 发出 `tool_pairing_repaired` 事件」，但 design Decision 8 明确 finally 修复只写 warning、不发事件；规范与设计对「修复」的触发范围不一致。必须把 spec 事件条款收敛为「run 起点修复时」，或为 finally 修复定义独立的有界日志事件，二者选一并写明。
- **High**: Decision 3 自相矛盾且与 spec 场景冲突：它先说「检测器会识别为悬空并在 assistant 之后插入」，又说「此类历史只记录 warning，不做重排」；spec 的「连续多个 assistant 悬空，中间可能隔着 user 文本」要求在每个 assistant 后补齐。更严重的是，若同一 id 的真实 tool 结果出现在 user 文本之后（非连续块），当前算法会补一条合成结果并留下后来的 orphan `tool_result`，payload 仍可能 400。必须区分 Case A（assistant 之后不存在任何匹配结果 → 在下一个非 tool 消息前合成）与 Case B（存在但位置不连续 → 不合成、只记录，或显式扩展为破坏性重排），并同步 Non-Goal 与 spec 场景。
- **Medium**: 首次重连、尚未发起新 run 时，`session_history` 从 `resume_snapshot.messages` 渲染（`web/session.py:82-89`），不会包含 run 起点才生成的合成结果；proposal 的「历史里能看到」在此时不成立。建议在 `build_history_payload` 对副本调用修复（只读、不落盘），或明确把可见性限定为「首次新 run 之后」。
- **Medium**: design 把 `_run_session_locked` 的 `turn_error_message` 当作既有变量，但当前只有 `turn_error` 布尔，`TurnOutcome` 也没带 message（`web/session.py:2181-2199`、`2232-2234`）；需在 tasks 2.7 明确新增变量、drain 时保存 error message（含 bounded detail）、传给 `TurnOutcome.message`，并补群聊系统日志断言。
- **Medium**: RIR 的 research questions 包含 codex，但 findings 没有 codex 结论；Anthropic 官方文档被区域重定向（实测最终 URL 为 `app-unavailable-in-region`），`is_error` 建议只能算次级证据。full 档应在实现前补齐 codex 对比或删除该问题，并把 Anthropic 条款的置信度写清楚。
- **Medium**: design 的 `## Open Questions` 初稿已过时：Q1/Q2 可由代码与现有产品原则定案，Q3 与 Decision 2 直接矛盾（Decision 2 已包含 name/id）。grill 后应把 Q1/Q2 移入已确认决策、删除 Q3，并回填 `## Pre-Implementation Review`（tasks 0.5）。
- **Low**: 空 `tool_call_id` 与重复 id 只日志/按 open-call 语义合并，畸形 provider 输入仍可能 400；这是明确的 Non-Goal，但测试应记录「不宣称修复」。
- **Low**: 合成文案与 `tool_pairing_repaired` 事件中的 `name`/`id` 字符串本身无长度上限；建议对事件 id 列表逐项截断，避免异常 provider 输入把日志/事件撑大。
- **Low**: `raise_for_status_with_body` 若只保留 4096 字符，`_is_reasoning_400` 对超长 body 末尾模式的判定可能变化；应保持重试判定使用完整 body，仅对 trace/Web 展示做有界截断。
- **Low**: 群聊房间系统日志会携带 provider body（有界 4096）；虽属用户自己的会话内容，仍应在实现时确保不拼接请求 payload/凭据，并有截断标记测试。
- **Low**: resume 分支当前不发 `run_started`（`agent/loop.py:709-743`），修复事件可能成为 resume run 的首个事件；前端会忽略未知类型，但事件顺序应写入测试/文档，避免后续消费者误判。

## User Confirmation
- 无 Open Question，无需用户确认；停轮报告无待拍板项。
