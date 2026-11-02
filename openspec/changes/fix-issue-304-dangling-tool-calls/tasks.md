# Tasks: 被打断 run 的悬空 tool_calls 自愈与 LLM 错误诊断

> **结算次序（收尾）**：本文件在最后一个内容提交上落定 → backlog 移除 → 归档 move（独立提交）
> → 本地复验 → **结算 `tasks.md`（未勾且未标 `(post-merge)` 必须为 0）** → **用归档目录名**
> 重建 witnessloop 三份 manifest → `gate / check` 机械复核 → 发起 PR。PR 创建与合入不写回
> `tasks.md`；closeout 类任务（合入后动作）标 `(post-merge)`。

## 0. 设计追问与对抗收敛（前置门，不完成不开工）

- [x] 0.1 用 paseo 托管的独立零记忆 grill agent 执行设计追问，产出 `reviews/grill-design.md`
      （`## Confirmed Decisions` ≥ 3 条，每条含同行裸 `来源:`；`## Open Questions` 与
      `## User Confirmation` 无条件存在）。
- [x] 0.2 逐项确认：修在 run 边界（非 load/resume-only/序列化）、合成 vs 丢弃、
      并行/连续多个悬空、幂等与确定性、finally best-effort、Chat/群聊/spill/summarizer/
      压缩边界、400 body 传播、测试策略、Non-Goals。
- [x] 0.3 独立零记忆对抗闭环 → `reviews/grill-adversarial.md`，按批次模型收敛到 PASS。
      **用户 2026-11-02 明确指示本 change 的设计对抗环无轮数上限**（U1，覆盖 AGENTS.md 的
      默认 20 轮上限）；出口仍只有 `PASS` / `BLOCKED` + 成因。裁决记录在 design 的
      `## User Rulings` 与 `workflow-events.jsonl` 的 `user_ruling` 事件（seq 3）。
- [x] 0.4 停轮检查：整理真正需要用户拍板的 Open Questions（每条带本 change 真实场景
      例子 + 推荐）；设计环出口 PASS 或 BLOCKED + 成因。
- [x] 0.5 回填 `design.md` 的 `## Pre-Implementation Review` 与 `## Open Questions`。

## 1. 测试（TDD）

### 1.1 纯函数 `repair_tool_call_pairing`

- [x] 1.1.1 末尾单个悬空 → 一条合成 tool 消息；id/name/固定前缀/确定性文案断言。
- [x] 1.1.2 同一 assistant 三个 `tool_calls`、只有一个结果 → 只补两个，顺序与插入位置正确。
- [x] 1.1.3 两个连续 assistant 各自悬空 → 各自补，顺序/位置正确（不复用失效索引）。
- [x] 1.1.4 悬空 assistant 后跟 user 文本 → 合成结果插在 assistant 与 user 之间。
- [x] 1.1.5 有效链 → 原列表/消息对象/`to_dict` 字节不变，`changed=False`。
- [x] 1.1.6 幂等：`repair(repair(x))` 第二次 `changed=False`，序列化字节一致。
- [x] 1.1.7 结果在调用之前（orphan-before）或出现在非相邻位置（misplaced-after）→
      **不合成**、不删除原结果，记录 warning；断言同一 `tool_call_id` 只有一条结果。
- [x] 1.1.8 空 `tool_call_id` → 不合成，记录 warning；重复 id 按 open-call 语义处理并
      记录「不宣称已自愈」的畸形输入用例。
- [x] 1.1.9 spilled preview 结果（`role=tool` + `tool_call_id` + preview）→ 视为已解决。
- [x] 1.1.10 assistant 文本与 reasoning 在修复后保留。
- [x] 1.1.11 misplaced-after：`[assistant(tool_calls=[x]), user("u"), tool(x)]` →
      不合成、只 warning、同一 id 仍只有一条结果；另加一条 loop/序列化断言，记录该
      畸形链**不承诺**被自愈。
- [x] 1.1.12 ADV-8/ADV-D2 resume 早期取消：resume 一个多消息快照（含非空
      todos/active_skills/user_system_prompt），在 `set_mode` await 点 cancel →
      `_save_session` 的 messages 仍含原历史 + 新输入，且 todos/skills/prompt 已恢复，
      不丢失；finally 修复不丢历史。

### 1.2 Loop / 恢复 / 中断

- [x] 1.2.1 改造 `tests/agent/test_issue304_dangling_tool_calls.py`：端到端断言
      （cancel → 重新加载 → 下一次请求成功、fake provider 无违规）保留；把「落盘必须仍
      悬空」的触发断言改为**中断前**断言（给 `SlowTool` 注入 `messages`，在 execute 内
      断言 assistant tool_calls 已 append 且无匹配 tool 消息），并断言取消后落盘快照已含
      合成 `tool` 消息。
- [x] 1.2.2 cancel 中途 → `AgentLoop.run` 落盘快照已配对；同进程下一次 run 成功。
- [x] 1.2.3 直接构造含悬空的快照（绕过 finally 修复）→ resume run 成功（覆盖 SIGKILL/
      旧版本快照场景）。
- [x] 1.2.4 正常 run 对照组：无合成、无 `tool_pairing_repaired` 事件、消息链不变。
- [x] 1.2.5 修复时发 `tool_pairing_repaired` 事件（source/count/bounded ids，逐 id 截断）；
      `changed=False` 不发；resume run 中该事件可为首个事件，前端忽略未知类型。
- [x] 1.2.6 修复 → `MemoryManager.compact` → 序列化仍合法（tool 链不被拆）。
- [x] 1.2.7 修复与 tool-result spill 共存：spilled 结果不触发合成；spill 前后配对不变。
- [x] 1.2.8 重启后首次连接（`session.messages` 为空、仅 `resume_snapshot`）的
      `session_history` 已包含合成结果；且该展示层修复不落盘、不发事件。
- [x] 1.2.9 finally 唯一修复点：`trace_recorder` 存在时记录 `source="finally"` 的
      `tool_pairing_repaired` step；无 recorder 时不崩；原始取消/异常传播不变。

### 1.3 Chat vs 群聊

- [x] 1.3.1 `SessionManager.run_session` 取消 → `unload_session` →
      `resume_session_async` → 再 run 成功（Web 层）。
- [x] 1.3.2 群聊成员 run 超时/取消后，下一轮成员 run 可用；房间系统日志含 `HTTP <status>` +
      已知错误类型枚举（未知写 `unknown`）固定摘要（不含 `error.message`/原始 body/payload/system
      prompt）；envelope 字段不变。
- [x] 1.3.3 OpenAI 序列化配对：干净的 Case A 修复历史经 `_build_openai_messages`，
      每个 `tool_calls[].id` 恰有一条 `role="tool"` 消息；断言修复**不新增**
      orphan/重复（输入已有的畸形结果不在承诺范围）。

### 1.4 诊断性

- [x] 1.4.1 流式 400（`httpx.MockTransport` + SSE）→ 异常带 body 属性，
      `_http_error_text` 返回原文；Web error 事件含 `detail`/`status_code`。同时强化
      协议 fake：先按 Anthropic 语义合并连续 user 轮，再断言 tool_result 在轮首、无
      orphan、无重复 `tool_use_id` 结果（不能只查紧邻消息出现 id）。
- [x] 1.4.2 非流式 400（Anthropic + OpenAI）→ 同上。
- [x] 1.4.3 body 为空/不可读 → 不崩，事件不加 `detail`，既有错误文案不变。
- [x] 1.4.4 非 HTTP 异常 → error 事件形状与现状一致（无 `detail`）。
- [x] 1.4.5 既有 reasoning / cache_control / vision 400 重试不回归。
- [x] 1.4.6 群聊 `TurnOutcome.message` 含 `HTTP <status>` + 已知错误类型枚举（未知写
      `unknown`）固定摘要，编排器系统日志可见；把哨兵分别放进 `error.message`、原始
      body 与不在枚举内的 `error.type`，断言房间日志均不含（type 落为 `unknown`）。
- [x] 1.4.7 前端 `readableErrorMessage` 输出 message + detail；`addMessage` 用
      `textContent`（浏览器测试或等价断言）；`.message` 已有 `pre-wrap`，换行可见。
- [x] 1.4.8 `_is_reasoning_400` 使用完整 body（异常属性），而 trace/Web/群聊只展示
      有界截断；两者不互相影响。
- [x] 1.4.9 合成结果序列化：Anthropic `tool_result` 带 `is_error: true`；OpenAI
      `role="tool"` content 含 `Error:` 前缀；真实结果不带该标记。
- [x] 1.4.10 前缀碰撞记录性用例：真实工具结果恰好以合成前缀开头时会被标
      `is_error`——断言该已知限制并记录，不改变 Message schema。

## 2. 实现

- [x] 2.1 `agent/message.py` 新增 `SYNTHETIC_TOOL_RESULT_PREFIX`、`RepairReport`、
      `repair_tool_call_pairing(messages)`：有序 open-call 扫描、按 assistant 分组补合成
      tool 消息、确定性文案、幂等、正常链零改动；文案中的 name/id 各自有界。
- [x] 2.2 `agent/loop.py` `_run` 起点（resume 重建后、iterations 前）调用修复并
      `messages[:] = repaired`；`changed=True` 时发 `tool_pairing_repaired` 事件
      （count 有界、每个 id 截断到有界长度）+ warning 日志 + trace step。
      同时把 resume 消息重建**及 todos/skills/user_system_prompt 同步恢复**移到
      `set_mode` await 之前（ADV-8/ADV-D2）。
- [x] 2.3 `agent/loop.py` `run()` finally **第一条语句**同步调用修复（在
      `background_manager.cleanup()` 与 `_save_session` 之前）；异常隔离（只 warning，
      不掩盖原始异常/取消），不 await Web 事件；若 `trace_recorder` 存在，同步、异常隔离
      地记录 `source="finally"` 的 `tool_pairing_repaired` trace step。
- [x] 2.4 `agent/llm.py` 新增 `raise_for_status_with_body` + `HTTP_BODY_ATTRIBUTE`；
      `_stream_events` 接线。
- [x] 2.5 `agent/anthropic_llm.py` 非流式接线；`_http_error_text` 优先读异常属性。
      `agent/openai_llm.py` 非流式接线。
- [x] 2.6 `agent/trace_recorder.py` `record_llm_error` 增加可选 `detail`（有界）；
      新增/复用配对修复 step。
- [x] 2.7 `web/session.py` error 事件增加 `detail`/`status_code`（仅 HTTP body 可用时）；
      新增 `_run_session_locked.turn_error_message` 变量，drain 到 error 事件时保存
      **保守固定摘要**（`HTTP <status>` + 已知错误类型枚举（未知写 `unknown`），不含
      `error.message`/首行/原始 body），run 结束时传给 `TurnOutcome.message`；原始
      bounded detail 只留在成员自己的 error 事件。
- [x] 2.8 `web/static/chat.js` `readableErrorMessage` 展示 bounded detail；保持
      `ERROR_MESSAGES` 优先级与 `textContent` 渲染。`.message` 基础样式已有
      `white-space: pre-wrap`（`web/static/style.css:161-168`），不需要新增 CSS。
- [x] 2.9 `web/session.py` `build_history_payload`：当历史来自 `resume_snapshot`
      时，用**副本**调用修复后再投影，使重启后首次连接、尚未发新消息时也能看到
      合成结果（只影响展示，不落盘、不发事件；run 起点仍为权威修复点）。
- [x] 2.10 正常路径不变：不新增 schema 字段、不改 `_is_400_error`/重试/失败语义、不改
      envelope/spill/压缩/工具执行顺序。
- [x] 2.11 序列化层合成错误信号：Anthropic `_build_payload` 对带
      `[asterwynd:synthetic-tool-result] Error:` 前缀的 `tool_result` 写
      `is_error: true`；OpenAI 路径保留 `Error:` 文本前缀（无 `is_error` 字段）。

## 3. 规格与文档

- [x] 3.1 `specs/agent-runtime/spec.md` delta：MODIFIED `tool-call 消息链合法`
      （恢复/中断自愈、幂等、finally trace、provider-neutral Anthropic/OpenAI 配对、
      合成 `is_error`/Error 前缀、resume 早期取消、正常链不变）+ ADDED
      `LLM HTTP 错误保留响应体`。
- [x] 3.2 `specs/observability/spec.md` delta：MODIFIED `LLM 错误可观测化`（可选 bounded
      `detail`）。
- [x] 3.3 `specs/web-ui/spec.md` delta：ADDED `Web UI 展示 LLM HTTP 错误详情`
      （普通 Chat + 群聊成员失败原因）+ ADDED `Web session 恢复历史的只读配对展示`。
- [x] 3.4 把 delta 施加进 `openspec/specs/`，记录 Requirement 计数，写
      `current_spec_synced` 事件；OpenSpec strict validate 通过。
- [x] 3.5 `docs/openspec-change-backlog.md` 登记本 change（issue #304）并写
      `backlog_updated` 事件；收尾时移除。
- [x] 3.6 新增 `docs/adr/ADR-0009-resume-tool-call-pairing-repair.md`：层选型、合成 vs
      丢弃、幂等/确定性、finally 边界、诊断性传播；≥2 个被拒备选。
- [x] 3.7 文档影响检查：`docs/architecture.md`（AgentLoop/会话恢复）、
      `docs/testing-guide.md`（回归要求）、`README*` 相关段落；只改事实变化。

## 4. 验证（实测）

- [x] 4.1 定向测试：message / message-chain / issue #304 repro / loop / anthropic /
      openai / trace / web session 全绿。
- [x] 4.2 全量 `uv run pytest -q`；与本机基线对照，既有 `/tmp` 环境失败须同因、无新增类型。
- [x] 4.3 协议校验 fake provider 回归：恢复后 payload 无未配对 `tool_use`（保留复现证据）。
- [x] 4.4 `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` 通过。
- [x] 4.5 `uv run python scripts/check_openspec_artifacts.py --base-ref origin/master
      --require-base` EXIT=0。
- [x] 4.6 变异验证：把 `repair_tool_call_pairing` 改为 no-op → 恢复/中断/幂等用例变红；
      去掉 error detail 传播 → 诊断用例变红；恢复后全绿。
- [x] 4.7 benchmark smoke：`uv run asterwynd benchmark benchmarks/tasks --agent fake
      --source-repo . --runs-dir /tmp/smoke-304` EXIT=0（72 tasks，fake agent 4 passed /
      68 failed 属预期；验证工具接线未破）。

## 5. 实现后独立审阅闭环

- [ ] 5.1 独立零记忆审阅，产出 `reviews/building-review.md`（含 `## 闭环出口`），
      medium+ 全修，收敛到 PASS。
- [ ] 5.2 low/nit 逐条登记并写理由；修复补回归测试。

## 6. 收尾（合入后）

> 归档 move、本地复验、`tasks.md` 结算与三份 manifest 的次序见文件头；PR 创建与合入在
> manifest 之后执行，不写回 `tasks.md`。

- [ ] (post-merge) 6.1 用 `--merge` 合入 PR；合入后确认 active 目录不存在、backlog 干净、
      本地 `master` 已快进。
- [ ] (post-merge) 6.2 给 issue #304 添加完成说明 comment（PR 号与验证结果）并关闭 issue。
