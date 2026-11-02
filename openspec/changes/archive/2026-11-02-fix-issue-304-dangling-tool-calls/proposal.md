# Proposal: 被打断 run 的悬空 tool_calls 自愈与 LLM 错误诊断

关联 issue：[#304](https://github.com/Xingkai98/asterwynd/issues/304)（本 change 跟踪入口）。
复现证据：`/tmp/repro-304.md`（本 worktree 的真实链路复现，基线 `604b56cc`）。

## Change Type

- primary: bugfix
- secondary: []

## Why

run 在「assistant `tool_calls` 已写入消息链、`tool_result` 尚未写回」之间被打断
（服务重启 / 进程被杀 / `cancel` / 群聊成员回合 240s 超时）时，消息链留下**悬空的
assistant `tool_calls`**。下一次请求把悬空 `tool_use` 原样序列化给 Anthropic/DeepSeek，
上游返回 **HTTP 400**（`tool_use ids were found without tool_result blocks immediately
after ...`），此后该会话的每一次请求都在同一位置失败，**会话永久不可用**。

当前基线（`604b56cc`）的真实链路复现（不是手搓 JSON）：

- 第一次 run：`AgentLoop` 在 `agent/loop.py:867` 追加 assistant `tool_calls`，随后
  `agent/loop.py:1014` 执行工具；工具执行期间 cancel，`tool_result` 的写入
  `agent/loop.py:1099` 未发生；
- `AgentLoop.run()` 的 `finally` 仍把消息链落盘（`agent/loop.py:655-662`），
  `messages.json` 里只有 user + 悬空 assistant；
- 重新加载（`SessionStore.load` → `resume_session_async` → `AgentLoop._run` 的
  resume 分支，`agent/loop.py:709-735`）后发起下一次请求，payload 含未配对
  `tool_use`；协议校验 fake provider 返回 400，run 抛 `HTTPStatusError`。

影响面（已实测/代码确认）：

- **不是群聊独有**：本次复现就是默认 `kind="chat"` 的普通 Web 会话；
  `web/session.py:2120-2132` 对所有 session kind 走同一条 `session.messages` + `agent.run` 路径。
- **群聊放大**：成员回合默认 240s 超时（`agent/team/runner.py:26`），
  `WebSessionRunner.run` 用 `asyncio.wait_for` 包住 `run_session`
  （`web/session.py:2284-2288`），超时会取消内层 run，产生同一条取消路径。
- **无自愈**：`SessionStore.load`（`agent/session.py:158-197`）与 resume 分支
  都不检查 tool-call 配对；现有 400 自愈只覆盖 reasoning / `cache_control` / 图片
  （`agent/anthropic_llm.py:168-205`、`382-433`），不覆盖 dangling `tool_use`。
- **诊断性差**：流式路径 `agent/llm.py:132-136` 直接 `raise_for_status()`，不读取/
  记录响应体；Web 错误事件只取 `f"{type(exc).__name__}: {exc}"`
  （`web/session.py:2133-2138`），前端只显示 `payload.message`
  （`web/static/chat.js:734-740`），400 body 对用户不可见。实测 body 本身是可读的
  （`_http_error_text` 能取到），属传播缺口。

## What Changes

1. **新增纯函数 `repair_tool_call_pairing(messages)`**（`agent/message.py`）：
   - 按顺序扫描，识别每个 assistant `tool_calls` 中**在紧随其后的 tool 消息块里没有
     配对结果**的 id（含末尾、同一 assistant 的并行多个、连续多个 assistant 悬空）；
     只在该 id 于整条历史中都没有任何 `role="tool"` 消息时才合成——结果存在但位置不对
     （misplaced / orphan）只记录、不合成，避免同一 `tool_use_id` 出现两条 `tool_result`；
   - 为每个缺失 id **合成一条明确标记为合成的 tool 消息**，内容确定为
     `[asterwynd:synthetic-tool-result] Error: ...`，说明「该工具调用因 run 中断
     未完成，可能已部分执行，需要时先检查状态再重试」，**不伪造成功结果**；
     Anthropic 序列化时对带该前缀的 `tool_result` 写 `is_error: true`，OpenAI 路径
     用 `Error:` 文本表达；
   - 插入位置为该 assistant 之后连续 tool 消息块的末尾（没有 tool 块则紧接 assistant），
     使 `tool_result` 紧邻 `tool_use`；并行缺失按 `tool_calls` 原顺序插入；
   - 返回 `RepairReport`（是否变更、修复的 id 列表），正常链**零改动**；
   - **幂等**：合成消息携带原 `tool_call_id`，重复调用不追加第二条；内容不含时间戳/
     随机值，重复修复字节一致（prompt cache 稳定）。
2. **run 起点自愈（主修）**：`AgentLoop._run` 在 resume 重建之后、进入迭代循环之前
   （`agent/loop.py:709-769` 之间）调用该函数并 `messages[:] = repaired`；覆盖
   - 重启后从快照 resume（首轮）；
   - 同一进程内被取消后的下一次 run（`session.resume_snapshot` 已被清空，
     `web/session.py:2149`，只靠 `session.messages`）；
   - CLI `--resume` 与 subagent run。
   修复发生时发 `tool_pairing_repaired` 事件（`source` / `count` / 有界 id 列表）并写
   warning 日志；trace 可记录同构 step。正常链不发事件。
3. **中断路径 best-effort 补 pairing**：`AgentLoop.run()` 的 `finally` **第一条语句**
   同步调用同一函数（在 cleanup 与 `_save_session` 之前），使取消/异常展开时落盘的快照
   也是配对合法的。同步、不 await Web 事件、不改变取消语义；写 warning 日志，并在
   `trace_recorder` 存在时同步记录 `source="finally"` 的 trace step。resume 分支的消息
   重建与 todos/skills/user_system_prompt 同步恢复移到 `set_mode` await 之前，避免早期
   取消用截断历史/未恢复状态覆盖旧快照。
   **不覆盖 SIGKILL / 断电**（进程不执行 `finally`）——这是明确的部分覆盖，由 run 起点
   自愈在下次启动时兜底。
4. **诊断性**：新增共享 helper（`agent/llm.py`）在 HTTP >= 400 时先读取响应体
   （流式 `aread()`，非流式直接 `text`），再 `raise_for_status()`，把**完整可读 body**
   附加到 `httpx.HTTPStatusError` 的属性上（异常类型与 run 失败语义不变；完整 body 供
   重试判定，展示时才截断）。该 helper 用于 `BaseLLM._stream_events`、
   `AnthropicLLM._chat_nonstream`、`OpenAILLM` 非流式路径；`_http_error_text` 优先读
   该属性。`AgentLoop._call_llm` 的 `llm_error` trace 增加有界 `detail`；Web error
   事件增加有界 `detail`/`status_code`；前端在基础文案后换行展示（`textContent`，
   无 XSS）；群聊成员失败经 `TurnOutcome.message` 进入房间系统日志，但共享日志只用
   保守固定摘要（`HTTP <status>` + 已知错误类型枚举（未知写 `unknown`）），不写
   `error.message`、首行正文或原始 body。非 HTTP 错误、无 body 的 400、既有错误码映射
   均保持原语义。
5. **规格同步**：`agent-runtime` 的 tool-call 消息链合法性扩展到持久化/恢复/中断路径；
   `observability` 的 `llm_error` 增加 body detail；`web-ui` 增加错误详情可见性要求。

## Capabilities

### New Capabilities

无新能力域。

### Modified Capabilities

- `agent-runtime`：`tool-call 消息链合法` 从「运行期不得生成缺失链」扩展为
  「持久化/恢复历史中**整条历史无同 id 结果**的悬空调用在每次 run 起点 SHALL 被
  自愈为带合成标记、provider-native 错误信号的 `tool_result`，SHALL 幂等、SHALL
  可观测、SHALL NOT 改动正常链」；provider-neutral 覆盖 Anthropic
  `tool_use/tool_result` 与 OpenAI `tool_calls/role=tool`；新增
  `LLM HTTP 错误保留响应体` 要求。misplaced/orphan 畸形链只记录、不承诺修复。
- `observability`：`llm_error` 在 provider HTTP 错误可读时 SHALL 记录有界
  `detail`（响应体），error_type/message 与 run 失败语义不变。
- `web-ui`：新增「Web UI 展示 LLM HTTP 错误详情」要求——error 事件携带有界
  `detail`/`status_code`；群聊共享日志只使用固定 `HTTP <status>` + 已知错误类型枚举（未知写
  `unknown`）摘要；新增
  「Web session 恢复历史的只读配对展示」要求——重启后首次连接即可看到合成结果，
  且该展示只读、不落盘、不发事件。

## 需求

1. **悬空检测与自愈**：会话消息链在每次 `AgentLoop.run` 开始时 SHALL 被扫描；
   assistant `tool_calls` 中在紧随其后的 tool 消息块里缺失结果的 id（含末尾、并行多个、
   连续多个），**且该 id 在整条历史中不存在任何 `role="tool"` 消息**时，SHALL 各补一条
   合成结果，使这类中断链序列化后不含未配对 `tool_use`；正常链 SHALL NOT 被修改。
   若结果存在但位置不合法（misplaced/orphan），只记录 warning、不重复合成，**不承诺**
   该畸形链的 payload 合法（见 Non-Goals）。
2. **合成语义**：合成结果 SHALL 明确标记为 synthetic/interrupted，SHALL NOT 声称工具
   成功，SHALL 提示「可能已部分执行、重试前先检查状态」；内容 SHALL 确定（无时间戳/
   随机值），重复修复字节一致。
3. **幂等**：第二次及以后加载/续跑/中断落盘 SHALL NOT 追加重复合成结果。
4. **中断路径 best-effort**：取消/异常展开导致 `run()` 的 `finally` 执行时，落盘前
   SHALL 补齐配对；resume 早期取消 SHALL NOT 丢历史/同步状态；SIGKILL/断电不在保证范围。
5. **可观测**：run 起点发生修复时 SHALL 发 `tool_pairing_repaired` 事件（有界）并写
   日志；finally 修复 SHALL 同步记录 `source="finally"` 的 trace step（不 await 事件）；
   正常链 SHALL NOT 发该事件；trace SHALL 可记录两类修复 step。
6. **诊断性**：provider HTTP >= 400 时 SHALL 保留可读响应体并传播到用户可见的 Web
   错误（有界）；群聊共享日志 SHALL 只使用固定 `HTTP <status>` + 已知错误类型枚举（未知写
   `unknown`）摘要（不写 `error.message`/原始 body）；异常类型、重试逻辑、非 HTTP
   错误与 run 失败语义 SHALL NOT 改变。
7. **回归测试**：保留并改造真实链路失败测试；覆盖幂等、并行/连续多个悬空、重启、
   普通 Chat vs 群聊、spill/ref、压缩、正常链不变、400 body 传播。

## Non-Goals

- **不**保证 SIGKILL/断电场景的即时配对（进程无法执行 `finally`）；仅由下次 run 起点
  自愈兜底。
- **不**做真实 Anthropic/DeepSeek API 的逐字比对（本机无凭据、按约束不花钱）；用按
  协议校验的 fake provider 覆盖。
- **不**处理「tool_result 存在但出现在 assistant 之前」的 orphan result、或
  assistant 与 tool 结果之间夹了非 tool 消息的畸形链；本 change 只治 `tool_use` 无配对
  结果（issue #304）。若扫描遇到这类结构，只记录不做破坏性重排。
- **不**为合成结果新增 `Message.is_error` 字段或改动持久化 schema；但 **Anthropic
  序列化层** SHALL 对带合成前缀的 `tool_result` 设置 `is_error: true`（协议级错误信号，
  不落盘），OpenAI 兼容路径无该字段，用明确的 `Error:` 文本前缀表达。两处都由固定
  合成前缀识别，不改变 `Message` 模型。
- **不**让 provider 序列化层（`_build_payload` / `_build_openai_messages`）承担历史
  修复主责；理由见 design Decision 1（易漏 OpenAI 路径、修复不落盘、无自然事件出口）。
- **不**改变群聊编排器/工作流 envelope 的数据契约；合成结果只存在于成员会话自己的
  消息链。
- **不**改 `max_iterations` 路径、正常工具执行顺序、工具结果 spill 策略或压缩算法。
- **不**改动 witnessloop 仓、`.witnessloop/**`、`v1.7.1` 等 tag。

## Impact Analysis

- 影响代码：
  - `agent/message.py`：新增 `repair_tool_call_pairing` / `RepairReport` / 合成标记常量。
  - `agent/loop.py`：`_run` 起点调用 + `tool_pairing_repaired` 事件；`run()` finally
    落盘前 best-effort 调用。
  - `agent/llm.py`：HTTP 错误 body 提取 helper 与 `_stream_events` 接线。
  - `agent/anthropic_llm.py`、`agent/openai_llm.py`：非流式路径接线；`_http_error_text`
    优先读异常属性。
  - `agent/trace_recorder.py`：`record_llm_error` 增加可选 `detail`；新增（或复用
    `record`）配对修复 step。
  - `web/session.py`：error 事件 `detail`/`status_code`；`TurnOutcome.message` 携带
    `HTTP <status>` + 已知错误类型枚举（未知写 `unknown`）固定摘要；新增
    `sanitize_provider_error_detail`（或等价）seam。
  - `web/static/chat.js`：错误详情展示（textContent）。
- 影响测试：
  - 保留 `tests/agent/test_issue304_dangling_tool_calls_repro.py` 的端到端场景，改造其
    「落盘必须仍是悬空」的触发断言（修复后中断路径可能已补齐）；
  - 新增纯函数单测、run 起点/恢复/同进程重试用例、spill/压缩边界、正常链不变、
    诊断性（流式/非流式 400 body、Web 事件、群聊 TurnOutcome、前端可见性）。
- 影响规格：`openspec/specs/agent-runtime/spec.md`、`observability/spec.md`、
  `web-ui/spec.md`。
- 影响文档：`docs/openspec-change-backlog.md`（登记/移除）；
  `docs/adr/ADR-0009-*.md`（层选型、合成 vs 丢弃、幂等/缓存）。
- 风险面：合成结果可能被模型当真实结果（用标记与「先检查再重试」措辞缓解）；
  对非幂等工具的重复执行风险；prompt cache 首次失配；错误 body 可能含上游回显内容
  （有界截断）；群聊系统日志长度（有界）。

## Reference Implementation Research

- research_tier: full
- status: enabled
- reason: 非平凡 bugfix，走 grill；同时涉及跨 provider 的消息协议不变量、历史自愈的
  放置层与幂等性，需要横向对照成熟 agent 框架的既有处置。`full` 档要求完整 RIR。
- research questions:
  - Anthropic Messages 协议对 `tool_use` / `tool_result` 的配对、相邻、顺序、
    `is_error` 的硬性要求是什么？未配对的实际错误是什么？
  - 成熟 agent 框架（LangGraph、pydantic-ai、OpenAI Agents SDK、Google ADK、
    Bernstein）如何处理「模型已发 tool_call、结果未写回」的中断历史：合成 vs 丢弃？
    在生命周期哪个点修？如何保证幂等与 prompt cache 稳定？
  - 合成结果的文案/标记如何避免模型把占位当成功结果？
  - provider HTTP 400 的响应体应如何保留并向上传播？
- findings:
  - **Anthropic 协议（官方文档，直接抓取被本环境区域重定向阻断；以搜索返回的官方
    文档摘要与 issue #304 的真实错误文案交叉核对）**：assistant turn 里的每个
    `tool_use` 必须由**紧邻的下一条 user 消息**中的 `tool_result` 按 `tool_use_id`
    一一配对；同一轮的所有 `tool_result` 必须放在该 user 消息 content 的**最前面**，
    文本在其后；跳过的调用也应返回 `tool_result`（可用 `is_error: true` 说明），
    而不是省略。真实错误：`400 invalid_request_error: messages.1: tool_use ids were
    found without tool_result blocks immediately after ...`。来源：
    <https://platform.claude.com/docs/en/agents-and-tools/tool-use/handle-tool-calls>、
    <https://platform.claude.com/docs/en/agents-and-tools/tool-use/parallel-tool-use>。
    **置信度说明**：直接抓取该官方页在本环境 307 到
    `anthropic.com/app-unavailable-in-region`；`is_error: true` 的具体措辞来自搜索
    返回的官方文档摘要，未直接读原文。本 change 仍采用该建议：Anthropic 序列化层对
    合成前缀写 `is_error: true`，OpenAI 用 `Error:` 文本前缀；因此该条是设计依据之一，
    但官方原文未直接读取，置信度为次级（实现与测试仍按协议字段名/文本形态钉住）。
  - **Anthropic 对连续 user 消息的官方口径（关键）**：官方 Messages API reference /
    SDK 文档明确「Consecutive user or assistant turns in your request will be combined
    into a single turn」——API 会把连续同角色消息合并为一轮，而不是拒绝。因此修复后
    payload 的 assistant(tool_use) → user(tool_result) → user(下一个用户文本) 是合法
    形态，等价于把 tool_result 放在该 user 轮 content 最前、文本随后；部分第三方严格
    转换器会在客户端先合并，但这不是 Anthropic 服务器的要求。来源：
    <https://platform.claude.com/docs/en/api/messages>（直接抓取被区域重定向，条文来自
    搜索返回的官方 API reference/SDK 摘要；本仓既有 resume 路径也长期产生连续 user
    消息，issue #304 的真实 400 是 `tool_use` 缺少 `tool_result`，不是角色交替）。
  - **LangGraph `INVALID_CHAT_HISTORY`（官方 troubleshooting 文档）**：给出两种修法：
    ① 追加匹配的 `ToolMessage` 后重新 invoke（从 START 跑）；② `graph.get_state` →
    编辑 messages（**删除未应答的 tool_calls** 或**补匹配 `tool_call_ids` 的
    `ToolMessage`**）→ `update_state` → `graph.invoke(None, config)` 真正 resume。
    来源：<https://docs.langchain.com/oss/python/langgraph/errors/INVALID_CHAT_HISTORY>。
  - **pydantic-ai PR #6319（`_repair_dangling_tool_calls`，2026）**：在每次模型请求前
    跑有序修复管线（`_drop_orphaned_tool_results` → `_repair_dangling_tool_calls` →
    `_merge_consecutive_messages`）；合成确定性 `ToolReturnPart`
    `"The tool call was interrupted before a result was produced."` +
    `outcome='interrupted'` + 元数据 `pydantic_ai_synthesized_tool_return=True`；
    匹配用「结果只能关闭当前位置仍 open 的 call」的 ordered walk，防止重复 id/结果在
    call 之前时掩盖真实缺失；重复修复字节一致（幂等、保 prompt cache）；末尾调用受
    `repair_last_response` 门控，另有 wire-level 清理。来源：
    <https://github.com/pydantic/pydantic-ai/pull/6319>。
  - **OpenAI Agents JS issue #1190**：流式 run 在模型已发 `function_call`、工具尚未执行
    时被 abort，服务端会话留下无 output 的 call，后续 400 `No tool output found`。
    修法是在 abort 分支**立刻**为每个 pending call 发送合成 output
    (`{output:'aborted', status:'incomplete'}`)，清理失败只记日志、不替换原始 abort
    错误。来源：<https://github.com/openai/openai-agents-js/issues/1190>。
  - **Google ADK commit `6b7386b`**：在 LiteLLM 请求构造前 heal；对每个未匹配
    assistant `tool_calls` id 插入 `role="tool"` 占位，内容
    `"Error: Missing tool result (tool execution may have been interrupted before a
    response was recorded)."`；若在仍有 pending id 时遇到非 tool 消息，占位插在该消息
    **之前**，循环结束仍 pending 的追加到末尾；重复执行不产生重复（占位自带匹配 id）。
    来源：<https://github.com/google/adk-python/commit/6b7386b7620bbc51cda8c1c6d9914549536640e6>。
  - **Bernstein `orphan_tool_result.py`**：`find_orphaned_tool_uses` 顺序扫描；按
    assistant 消息分组合成 user tool_result；同一 assistant 的多个 orphan 合成在**一条**
    user 消息；从后往前插入避免索引失效；固定标记
    `[synthetic_orphan_recovery]`，并带 `_synthetic` / `_orphan_recovery` 内部标志；
    用于加载持久化历史的 crash recovery，第二次修复自然无 orphan。来源：
    <https://github.com/sipyourdrink-ltd/bernstein/blob/474cfec8d635159cbe7ac1d02607051f2fbc56b8/src/bernstein/core/agents/orphan_tool_result.py>。
  - **行业共性**：主流动向是「**补一条明确标记的合成结果**」而不是删除 assistant
    （LangGraph 两种都支持；pydantic-ai / ADK / Bernstein 选合成；OpenAI Agents 在
    abort 时合成），且强调**确定性内容 + 幂等**（prompt cache）与**绝不伪造成功**。
  - **本仓现状（只读核查）**：无 tool-call 配对自愈；`SessionStore.load`
    `agent/session.py:158-197`、resume 分支 `agent/loop.py:709-735` 均原样回放；
    `_annotate_pending_calls` `agent/memory/manager.py:499-540` 只给 summarizer 加
    `pending` 注释，不改消息链；已有 `agent-runtime` 规格的 `tool-call 消息链合法`
    要求（`openspec/specs/agent-runtime/spec.md:26`）与 `context-engineering`
    的配对保留要求（`openspec/specs/context-engineering/spec.md:29`），本 change
    补的是**持久化/恢复/中断路径**的缺口。
  - **本地参考仓库不可用**：本 worktree 无 `.dev/reference-repos.txt`（`ls .dev`
    不存在），故未做本地参考仓库对比；改用上述公开实现与官方错误语义作为依据。
    直接抓取 `platform.claude.com` 官方页在本环境被 307 到
    `anthropic.com/app-unavailable-in-region`，故官方条款以搜索摘要 + issue 真实错误
    文案交叉确认；其余引用均为可访问的官方文档/PR/commit。
- design impact:
  - 采用**合成并明确标记**的方案（与 pydantic-ai/ADK/Bernstein 同向），不做删除式修复。
  - 修复放在 **AgentLoop run 起点**（覆盖 resume 与同进程重试），而不是只放
    load/resume 或 provider 序列化层；另在 `run()` finally 做 best-effort 中断补配对。
  - 合成内容确定性、带固定标记；幂等靠 `tool_call_id` 是否已被结果覆盖判定。
  - 诊断性复用 `_http_error_text` 已可取的 body，附加到异常并传播到 Web 事件/前端。

## 用户故事

- 作为 Web 用户，服务重启/取消打断 run（Case A：整条历史无该 id 结果）后，再次打开
  同一会话发消息不会再永久 400；
  历史里能看到「该工具调用因中断未完成」的明确说明，而不是会话报废。
- 作为群聊用户，某个成员回合超时/被取消后，下一轮不会因为该成员的会话链损坏而
  全员失败；成员失败原因里能看到 provider 返回的具体 400 body。
- 作为维护者，配对修复是幂等的、只在异常历史发生、正常路径字节不变，且修复事件
  可在日志/trace/Web 事件中看见。
- 作为诊断者，LLM HTTP 400 不再只剩「运行失败」，响应体在 Web 错误里可见（有界）。
