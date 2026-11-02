# Design: 被打断 run 的悬空 tool_calls 自愈与 LLM 错误诊断

## Context

### 缺陷与复现（基线 `604b56cc`）

真实链路复现（`/tmp/repro-304.md`，测试提交 `5b3af47e`）确认：

1. `AgentLoop._run` 把 assistant `tool_calls` 追加进消息链：`agent/loop.py:867`；
2. 随后执行工具：`agent/loop.py:1014` → `_execute_tool_calls()`（`agent/loop.py:1450-1526`）；
3. 正常路径到 `agent/loop.py:1099` 才写 `tool_result`（参数解析失败分支在
   `agent/loop.py:905`）；
4. 在 2 与 3 之间 cancel/异常时，`tool_result` 未写；`AgentLoop.run()` 的 `finally`
   仍执行 `_save_session`（`agent/loop.py:655-662` → `agent/loop.py:1744-1770`），
   把半截链落盘；
5. 下次请求：`SessionStore.load`（`agent/session.py:158-197`）→ Web resume
   （`web/session.py:1673-1728`）→ `AgentLoop._run` resume 分支
   （`agent/loop.py:709-735`）原样回放；`AnthropicLLM._build_payload`
   （`agent/anthropic_llm.py:227-304`）把 assistant `tool_calls` 转成 `tool_use`
   （`:239-268`），把 `role="tool"` 转成 `tool_result`（`:269-285`），**不校验配对**；
6. 上游返回 400：`messages.1: tool_use ids were found without tool_result blocks
   immediately after ...`。`BaseLLM._stream_events` 在 `agent/llm.py:132-136` 直接
   `raise_for_status()`；`web/session.py:2133-2138` 只把
   `f"{type(exc).__name__}: {exc}"` 放进 error 事件；前端
   `web/static/chat.js:734-740` 只显示 `payload.message`。

同一进程内（未重启）的路径同样存在：`web/session.py:2120-2122` 把新 user 消息追加到
`session.messages`，`web/session.py:2127-2132` 调用 `agent.run(..., resume_snapshot=
session.resume_snapshot)`；而 `resume_snapshot` 在上一回合 `run_agent` 的 `finally`
已被清空（`web/session.py:2149`）。因此**只修 load/resume 不够**。

### 现有规格与机制

- `agent-runtime` 已有「tool-call 消息链合法」要求：
  `openspec/specs/agent-runtime/spec.md:26`（当前只覆盖运行期与 max_iterations/截断场景）。
- `context-engineering` 要求 summarizer 保留配对并给未完成调用加
  `[call#<i>: <id> pending]`：`openspec/specs/context-engineering/spec.md:29`。
- 本仓**没有**持久化/恢复期的配对校验或修复；`_annotate_pending_calls`
  （`agent/memory/manager.py:499-540`）只给摘要器加注释，不改消息链。
- 现有 400 自愈只有 reasoning / `cache_control` / 图片三类
  （`agent/anthropic_llm.py:168-205`、`382-433`），不覆盖 dangling `tool_use`。

## Goals / Non-Goals

**Goals**

- 会话历史在每次 run 开始前保证：**整条历史中不存在同 id 结果**的悬空调用
  （末尾、同一 assistant 的并行多个、连续多个 assistant）被补上合成结果；这类中断链
  serialized payload 不含未配对 `tool_use`。misplaced/orphan 畸形链只记录、不承诺修复。
- 中断（取消/异常展开）时，落盘快照尽量已是配对合法的链（best-effort）。
- 合成结果明确标记、确定性、幂等、正常链零改动、修复可观测。
- LLM HTTP 400/5xx 的响应体保留并进入用户可见错误（有界），不改变异常类型与重试语义。
- 覆盖普通 Chat、人设单聊、群聊成员会话；不改变工作流 envelope 契约。

**Non-Goals**

- SIGKILL/断电时的即时配对（进程不执行 `finally`）。
- 真实 API 逐字比对（无凭据；fake provider 按协议校验）。
- orphan `tool_result`（结果在调用之前）或 assistant 与结果之间夹杂非 tool 消息的
  畸形链的破坏性重排；只检测/记录。
- 新增 `Message.is_error` 字段或改持久化 schema。
- 让 `_build_payload` / `_build_openai_messages` 承担历史修复主责。
- 改工具执行顺序、spill 策略、压缩算法、群聊编排器 envelope。

## Decisions

### Decision 1：修在 `AgentLoop` 的 run 边界（起点 + 落盘前），不是 load / resume-only / 序列化层

**选择**：同一个纯函数 `repair_tool_call_pairing(messages)` 在两处调用：

1. **`AgentLoop._run` 起点**：在 resume 分支重建完 `messages`、进入迭代循环之前
   （`agent/loop.py:709-769` 之间，iterations 从 `:764` 开始）。这是**主修**，覆盖：
   - 重启后 resume（首轮）；
   - 同进程内被取消后的下一次 run（`web/session.py:2149` 清空 `resume_snapshot`，
     下次只传 `session.messages`）；
   - CLI `--resume`、subagent run、benchmark 直跑（都走 `AgentLoop.run`）。
2. **`AgentLoop.run()` 的 `finally`**（`agent/loop.py:655-662`）：在 `_save_session`
   之前同步调用，best-effort 保证取消/异常展开时落盘快照配对合法（见 Decision 6）。

**为什么不是 `SessionStore.load`**：

- `SessionStore` 是**忠实快照层**：`load` 只做 schema 校验与 `Message.from_dict`
  （`agent/session.py:158-197`，反序列化在 `:196`）。在 load 里修复要么不落盘（每次
  加载重复修复、UI/history 与磁盘不一致），要么让读操作产生写语义；两者都破坏存储层
  的职责边界。
- load 覆盖不了同进程重试：下一次 run 不重新 load，直接复用 `session.messages`
  （`web/session.py:2127-2132`）。

**为什么不是只修 resume 分支**：

- resume 分支只在 `resume_snapshot is not None` 时执行（`agent/loop.py:709`）；Web 在
  上一回合结束后已把 `session.resume_snapshot` 置 None（`web/session.py:2149`），
  同进程取消后的下一次 run 走**普通 run 路径**，不会被 resume 修复覆盖。
- CLI 的 `--resume` 也只首轮走该分支。

**为什么不是 provider 序列化层（`_build_payload` / `_build_openai_messages`）**：

- 修复只作用于**每次请求的临时拷贝**，不落盘：会话历史仍是非法链，UI/history、后续
  压缩、summarizer 仍看到悬空状态；每次请求重复修复。
- 必须同时改 Anthropic（`agent/anthropic_llm.py:227-304`）与 OpenAI
  （`agent/openai_llm.py:279-317`）两套序列化，容易漏；而修在 `Message` 层一次覆盖
  provider。
- 该层没有会话上下文，没有自然的可观测事件出口；把协议不合法的容忍沉到传输层会掩盖
  上游 bug。
- 结论：序列化层不承担主修；它继续假设「传入的历史已配对」。

**证据**：上述行号与 `/tmp/repro-304.md` 的实测；同进程重试路径由
`web/session.py:2127-2132` + `:2149` 钉死。

### Decision 2：补合成 `tool_result`，不丢弃悬空 assistant 消息 / 不删 `tool_calls`

**选择**：为每个缺失 id 合成一条 `Message(role="tool", content=<固定标记文案>,
tool_call_id=<id>)`。

**语义后果对比**：

| 方案 | 模型看到什么 | 上下文损失 | 用户可见性 | 主要风险 |
| --- | --- | --- | --- | --- |
| 补合成结果（采用） | assistant 的文本/推理保留；随后一条「中断未完成」结果 | 无（只增一条 small text） | 历史里多一行工具结果（明确标记） | 模型可能把占位当真实结果；需措辞与标记 |
| 丢弃整个 assistant 消息 | 该轮 assistant 的文本、推理、工具意图全部消失；后续 user 消息直接接上 | 丢失模型已产出的内容与中断事实 | 历史缺一轮 | 模型无法理解为何后续对话缺少上下文；对「用户已看到 assistant 文本」的场景是静默篡改 |
| 仅删除 assistant 的 `tool_calls`、保留文本 | assistant 文本保留，但模型/用户看不到曾尝试工具 | 丢失工具意图与中断事实 | 只剩 assistant 文本 | 同样不告诉模型「工具可能已部分执行」 |

**选择理由**：

- 业界主流（LangGraph 两种都支持；pydantic-ai / Google ADK / Bernstein / OpenAI
  Agents 在 abort 路径选合成）与本仓 RIR 一致；合成是**加法**、最不具破坏性。
- 合成结果能让模型知道「该工具没有可信结果」，从而避免基于缺失结果继续推理；同时
  保留 assistant 的 reasoning/text，不篡改已展示内容。
- 丢弃 assistant 会不可逆地改变历史（如果落盘），且 `stop_reason=tool_calls` 的 assistant
  文本可能是用户已经看到的；不做。

**文案与标记**：

- 固定前缀 `[asterwynd:synthetic-tool-result] Error:`；正文说明
  `Tool call '<name>' (<id>) did not complete because the run was interrupted before
  a result was recorded. The tool may have partially executed; inspect state before
  retrying.`
- 明确「synthetic」「interrupted」「可能已部分执行」「重试前先检查」，**绝不声称成功**。
- 不含时间戳、随机 id、调用次数；同一历史重复修复字节一致（prompt cache 稳定）。
- 合成文案中的 `name` / `id` SHALL 各自截断到有界长度（例如 128 字符），避免恶意/
  异常 provider 输入把合成消息本身撑大；这属于 content 的 bounded 处理，事件 id 列表
  另有独立截断。
- **provider 级错误信号**：不新增 `Message.is_error` 字段（`agent/message.py:146-177`
  无该字段、不改持久化 schema），但序列化层按固定合成前缀识别：
  - Anthropic `_build_payload` 的 `tool_result` SHALL 增加 `"is_error": true`
    （`tool_result` 的协议字段，`agent/anthropic_llm.py:269-285` 当前未设置）；
  - OpenAI 兼容路径无 `is_error` 字段，合成 content 的 `Error:` 前缀 + 中断说明就是
    等价信号（OpenAI `role="tool"` 只有文本）。
  这样模型收到的是 provider 能理解的错误结果，而不是普通成功结果；`Message`/持久化
  格式保持向后兼容。

### Decision 3：检测与插入算法（并行多个 / 连续多个 / 中间悬空）

**检测（有序、open-call 语义）**：

- 按消息顺序扫描；遇到 assistant 时把其 `tool_calls` 的 id 记为 open，并记录该
  assistant 的索引；
- 紧随其后的连续 `role="tool"` 消息按 `tool_call_id` 关闭对应 open id；
- 遇到下一个非 tool 消息时，仍未关闭的 id 即为该 assistant 的悬空调用；
- 「结果只能关闭当前位置仍 open 的 call」防止：结果出现在调用之前（orphan）、
  重复 id、或后续 turn 的同名结果把前一个缺失掩盖（对齐 pydantic-ai 的 ordered walk）。
- 缺少 id 的 tool call（空字符串）不合成（无法序列化成合法 `tool_use` 之外的东西），
  只记日志；正常 provider 不会给出空 id。
- **只在该 id 于整条历史中都不存在任何 `role="tool"` 消息时才合成**。若结果存在但
  位置不对（在 assistant 之后但被文本隔开，或在 assistant 之前），归类为 misplaced /
  orphan：SHALL NOT 再合成（否则同一 `tool_use_id` 会出现两条 `tool_result`，上游可能
  直接 400）；只记录 warning，不做破坏性重排（Non-Goal）。这保证修复只做加法、不会把
  一个畸形链变成另一个畸形链。

**插入位置**：

- 对该 assistant，把合成消息插到**紧随其后的连续 tool 消息块末尾**（没有 tool 块则紧接
  assistant）。
- 同一 assistant 的多个缺失按 `tool_calls` 原顺序插入；`_build_payload` 会把连续 tool
  消息合并成**一条** user 消息的 `tool_result` blocks（`agent/anthropic_llm.py:275-285`），
  满足 Anthropic「同一轮所有 results 在一条 user 消息且在最前」。
- 悬空 assistant 后跟 user 文本时，合成结果落在 assistant 与 user 文本之间，serialized
  顺序为 assistant(tool_use) → user(tool_result) → user(text)。**该形态合法**：
  Anthropic 官方 Messages API reference/SDK 文档明确「Consecutive user or assistant
  turns in your request will be combined into a single turn」，API 会把连续 user
  消息合并为一轮，等价于 tool_result 在前、文本随后；本仓 resume 路径本来就产生连续
  user 消息，issue #304 的真实 400 是缺 `tool_result` 而非角色交替。部分第三方严格
  转换器会在客户端先合并，但不是服务器要求（RIR 已记录来源与区域阻断说明）。
- 连续多个 assistant 各自悬空：从左到右构建新列表，每个 assistant 的插入局部完成；
  不使用会失效的原地索引。
- 末尾 assistant 悬空：合成结果追加在末尾，保证历史以 tool 结果结束；随后 resume 的
  `[Session resumed...]` / 新用户消息自然成为下一轮 user。

**不处理（与「纯中断」区分）**：

- **纯中断**：assistant 的某个 id 在**整条历史中都没有任何 `role="tool"` 消息**，
  即使其后紧跟 user 文本（例如「连续多个 assistant 各自悬空，中间隔着 user 文本」），
  仍是本 issue 的产物；SHALL 在 assistant 之后、该 user 文本之前插入合成结果。
  `_build_payload` 会产出 assistant → user(tool_result) → user(text) 的序列，Anthropic
  接受连续 user 消息（本仓 resume 路径已产生连续 user 消息）。
- **位置错误（misplaced / orphan）**：该 id 的 tool 消息存在，但不紧邻 assistant
  （在后续 user 文本之后，或在 assistant 之前）。这类畸形链不是本 issue 的取消产物；
  为避免同一 `tool_use_id` 出现两条 `tool_result`，SHALL NOT 再合成，只记录 warning，
  不做破坏性重排（Non-Goal）。此时原始畸形链可能仍不合法，但不会被本修复进一步恶化。
- orphan tool result（结果无对应 call）：不删除、不重排；只记录 warning（超出
  issue #304 的中断路径）。

### Decision 4：幂等与确定性

- **幂等判据**：某 `tool_call_id` 是否已被其 assistant 之后连续 tool 块中的任意
  `tool` 消息覆盖。合成消息携带原 id，因此第二次调用扫描时视为已解决，不再追加。
- **重复点**：`run()` finally 的 best-effort 修复 → 下一次 `_run` 起点修复 →
  重启 resume 修复。三处都调用同一函数，第二/三次必须是 no-op。
- **确定性**：文案只依赖 `tool_call.name` / `tool_call.id`，不依赖时间/随机/进程状态；
  `repair(repair(x))` 的 `to_dict()` 序列化字节一致。这样：
  - 重复加载不会因为文案变化导致 prompt cache 失效；
  - 测试可用「两次调用后 `messages.json` 字节一致」钉住。
- **报告**：`RepairReport(changed: bool, repaired: list[RepairedCall])`；
  `changed=False` 时**不修改原列表、不发事件**。

### Decision 5：边界——Chat / 群聊 / spill / summarizer / 压缩 / subagent / OpenAI

- **普通 Chat / 人设单聊 / 群聊成员**：三者都是 `AgentSession` + 一个 `AgentLoop`；
  Web 的 `_run_session_locked` 对所有 kind 走同一路径（`web/session.py:2120-2132`）。
  修复在 `AgentLoop.run` 边界，因此三者同时覆盖。群聊成员回合超时/取消会把
  `CancelledError` 传进 `_run_session_locked` 的 `finally` 并 cancel agent task
  （`web/session.py:2210-2215`），下次成员 run 的起点修复兜底。
- **重启后首次连接、尚未发新消息**：`build_history_payload` 在 `session.messages`
  为空时回退到 `session.resume_snapshot.messages`（`web/session.py:76-108`），此时
  run 起点修复尚未发生。为了让「历史里能看到合成结果」在首次连接就成立，展示层 SHALL
  对该快照历史的**副本**调用同一修复函数后再投影（不落盘、不发事件），run 起点仍是
  权威修复点。
- **群聊 envelope**：编排器只消费 `TurnOutcome`（`agent/team/runner.py:45-60`）与成员
  文本/状态；不读成员原始 tool 链（`web/session.py:2242-2300`）。合成结果只存在于成员
  自己的 `messages`，不进入父/房间 envelope。诊断性只把成员失败 `message` 带进
  `TurnOutcome.message`（`agent/team/orchestrator.py:508-512`），不改 envelope schema。
- **tool_result spill/ref**：spill 只替换 `content` 为 bounded preview + ref，保留
  `role="tool"` 与 `tool_call_id`（`agent/memory/tool_result_spiller.py:123-149`），
  配对判据只看 id，因此 spilled 结果仍算已解决。合成结果是小文本，不需要且不会被
  spill（未在 `_iterations` 标记时 `spill` 不剪，见 `:128-130`）；即使 rescan 后标记，
  也远低于阈值。**不会**把 ref 误当缺失。
- **memory manager 的 `_annotate_pending_calls`**：它是**摘要器输入装饰**，把一个
  middle segment 里的未完成调用标成 `[call#i: id pending]`
  （`agent/memory/manager.py:499-540`），不改消息链。本 change 的修复发生在 LLM 调用
  前，修复后真实链已无 pending；两者不互相替代。测试要确保：
  - 修复后压缩，summarizer 不再看到 pending 标记；
  - 不因为合成结果而把 `_annotate_pending_calls` 的已有行为改坏（已有 context 测试）。
- **压缩**：`_recent_with_tool_chains` 会把 recent window 的起点向前扩到每个 tool
  结果对应的 assistant（`agent/memory/manager.py:461-479`），因此有效链在压缩后仍
  配对；修复后的合成 tool 结果与 assistant 相邻，压缩不会拆开。测试覆盖「修复 →
  compact → 再次序列化仍合法」。
- **subagent**：`AgentLoop.run` 同样修复；合成结果留在 child 上下文，父 agent 只拿到
  bounded envelope（既有 `agent/subagent/manager.py` 契约不变）。
- **OpenAI provider**：修复在 `Message` 层，`_build_openai_messages`
  （`agent/openai_llm.py:279-317`）无需改动；`role="tool"` + `tool_call_id` 是 OpenAI
  期望的配对形态。

### Decision 6：中断路径 best-effort（部分覆盖）

**选择**：`AgentLoop.run()` 的 `finally`（`agent/loop.py:655-662`）**第一条语句**同步调用
`repair_tool_call_pairing(messages)`（在 `background_manager.cleanup()` 与
`_save_session` 之前），然后照旧保存。放在 cleanup 之前是为了消除
「cleanup 抛异常导致 repair/save 不执行」的顺序依赖。

- **为什么在 finally**：取消/异常展开时 Python 仍执行 finally；把修复放在落盘前，保证
  「这次落盘的快照」就合法，而不是等下次 run 才修。它同时利好同进程下一次 run
  （`session.messages` 已被就地修复）。
- **为什么同步**：取消状态下 await 可能被再次取消；修复是纯内存 O(n) 操作，同步执行
  不会引入挂起点，也不吞 `CancelledError`。
- **异常隔离**：修复自身抛异常时只 `logger.warning`，不得掩盖原始取消/异常，也不阻止
  `_save_session` 的既有 try/except。
- **覆盖范围（如实）**：
  - 覆盖：`CancelledError`（uvicorn 优雅停机、群聊成员超时、client cancel）、普通
    `Exception` 展开、`KeyboardInterrupt`（BaseException finally 仍执行）。
  - 不覆盖：SIGKILL、断电、解释器崩溃（进程不执行 finally）。这些场景若没有中途
    落盘，快照停留在上一次成功保存（不含本次 run 的悬空）；若快照本身含悬空（例如
    中途被别的机制保存），由下次 run 起点修复兜底。
- **可观测性**：finally 中不 await `on_event`（取消中可能不可靠），但 **trace
  记录是同步的**（`TraceRecorder.record`，`agent/trace_recorder.py:81-91`）：若本次 run
  带 `trace_recorder`，SHALL 同步、异常隔离地记录一条 `tool_pairing_repaired` step
  （`source: "finally"`、count、bounded ids）；同时写 warning 日志。下一次 run 起点若
  仍需修复则发 `tool_pairing_repaired` 事件（通常不会，因为 finally 已修）。
- **resume 早期取消（ADV-8 / ADV-D2）**：当前 resume 分支先 `await self.set_mode(...)`
  （`agent/loop.py:713-717`），之后才重建 `messages`（`:725-730`）并恢复
  `_execution_todos` / skills / `_user_system_prompt`；若在 `set_mode` 的 await 点被
  取消，finally 看到的 `messages` 只有调用方的新 user 输入，且这些状态未恢复，
  `_save_session` 会用截断历史与未恢复状态覆盖旧快照。本 change SHALL 把 resume 的
  **全部同步状态恢复**移到该 await **之前**：`conversation` 计算、
  `messages.clear()/extend()`、resume marker + 新输入、`tool_result_spiller.reset`、
  `_execution_todos`/`_sync_todo_next_id`、`skill_runtime.restore_skills`、
  `_user_system_prompt`。`set_mode` 保持在其后（mode 的 runtime state 由 `set_mode`
  同步设置；若其 await 点取消，新 mode 已生效或旧 mode 仍可保存，二者都不丢历史）。
  这样在 `set_mode` 期间取消时，finally 仍保存完整历史 + 新输入 + 已恢复的同步状态
  （再补配对）。测试见 tasks 1.1.12。

### Decision 7：诊断性——HTTP body 的提取与传播

**提取（共享 helper，`agent/llm.py`）**：

- 新增 async `raise_for_status_with_body(response)`：
  - 若 `status_code < 400`：直接 `response.raise_for_status()`（no-op）；
  - 否则先 `await response.aread()`（流式响应在 `client.stream` 上下文内读取；非流式
    已读，aread 幂等），再取 `response.text`（失败则空串）；
  - 调 `response.raise_for_status()`；捕获 `httpx.HTTPStatusError`，把**完整可读
    body**（读取失败时为空串）写到属性 `HTTP_BODY_ATTRIBUTE`（字符串常量）后原样
    `raise`。属性保留完整 body 是为了不改变 `_is_reasoning_400` 的判定；**trace 与
    Web error 事件**展示原始 detail 时才截断（例如 4096 字符 + `…[truncated]`）；
    **群聊共享日志不展示原始 detail**，只展示固定 `HTTP <status>` + 已知错误类型
    枚举（未知写 `unknown`）摘要（见下）。
- 接入点：
  - `BaseLLM._stream_events`（`agent/llm.py:132-136`）——流式 Anthropic/OpenAI 共用；
  - `AnthropicLLM._chat_nonstream`（`agent/anthropic_llm.py:595-618`）；
  - `OpenAILLM` 非流式 `response.raise_for_status()`（`agent/openai_llm.py:87`）。
- **不改异常类型**：仍是 `httpx.HTTPStatusError`；`_is_400_error`
  （`agent/llm.py:213-221`）与 reasoning/cache/vision 重试逻辑（`agent/anthropic_llm.py`
  的 `except` 分支）不受影响。body 只是附加属性。
- `_http_error_text`（`agent/anthropic_llm.py:68-81`）改为优先读 `HTTP_BODY_ATTRIBUTE`，
  再回退既有 `response.text`（实测 httpx 0.28.1 下 `_http_error_text` 已能取到 body；
  新增显式读取是为了跨 httpx 版本/流式上下文可靠，而不是修复不可读）。

**传播**：

- `AgentLoop._call_llm` 捕获异常时（`agent/loop.py:1311-1320`）调用
  `TraceRecorder.record_llm_error(error_type, message, detail=<bounded body>)`；
  `record_llm_error`（`agent/trace_recorder.py:289-295`）增加可选 `detail`，不改变
  既有 `error_type` / `message` 字段；run 仍 re-raise（失败语义不变）。
- `web/session.py:2133-2138` 的 error 事件：
  - 保留 `message` 原样；
  - 当异常带 body 时增加 `detail`（有界，例如 4096 字符，超出加 `…[truncated]`）与
    `status_code`；
  - 非 HTTP 异常、无 body 的 HTTP 错误**不增加**这两个键，既有事件形状不变（兼容
    现有测试/客户端）。
- 群聊：`_run_session_locked` **当前只有 `turn_error: bool`**（`web/session.py:2181-2199`），
  本 change 需要新增 `turn_error_message` 变量，在 drain 到 error 事件时保存失败原因，
  并在 run 结束写入
  `TurnOutcome(status="failed", text=turn_text, message=turn_error_message)`
  （当前构造点 `web/session.py:2232-2234`）。`WebSessionRunner.run` 原样返回
  （`web/session.py:2242-2300`），编排器用 `outcome.message`
  （`agent/team/orchestrator.py:508-512`）写「成员 X 运行失败：<...>」。
  **群聊房间日志是共享面，不能写入原始 provider body 或 provider 控制的自由文本**：
  `turn_error_message` SHALL 使用**保守固定摘要**——`HTTP <status>` + 一个
  **已知错误类型枚举**中的值（如 Anthropic/OpenAI 的 `invalid_request_error` /
  `authentication_error` / `permission_error` / `not_found_error` /
  `request_too_large` / `rate_limit_error` / `api_error` / `overloaded_error` /
  `billing_error`；不在枚举内一律写 `unknown`），不包含 `error.message`、首行正文、
  请求 payload、system prompt、工具参数或凭据；非 JSON 时只保留 `HTTP <status>`。
  provider 的自由文本与任意 `error.type` 字符串无法证明不含回显内容，因此不进入共享
  日志。成员**自己的** Web error 事件仍可携带 bounded 原始 `detail`（它只发给该会话
  的连接）。
- 前端：`readableErrorMessage`（`web/static/chat.js:734-740`）在 `payload.detail`
  存在时返回 `message + "\n" + detail`；`addMessage('error', ...)` 用
  `body.textContent`（`web/static/chat.js:950-976`），无 HTML 注入风险。`.message`
  基础样式已有 `white-space: pre-wrap`（`web/static/style.css:161-168`），
  `.message.error` 不覆盖它，因此换行会正常展示，**无需新增 CSS**。
  `ERROR_MESSAGES[code]` 的优先级保持不变（`run_in_progress` 等既有码仍走友好文案，
  不附加 detail）。

**不改变正常错误语义**：`_is_400_error`、reasoning/cache/vision 重试、`AgentLoop`
失败出口、Web `done(stop_reason="error")` 全部保持；body 只是新增的可观测载荷。

### Decision 8：可观测事件与 trace

- **事件**：run 起点修复发生且 `report.changed` 时，发
  `tool_pairing_repaired`（`tool_call_ids` 中每个 id 也 SHALL 截断到有界长度）：
  ```json
  {"source": "run" | "resume", "count": N,
   "tool_call_ids": ["<id>", ...], "synthetic_prefix": "[asterwynd:synthetic-tool-result] Error:"}
  ```
  `tool_call_ids` 有界（例如最多 20 个 + `truncated: true`）；`count` 是真实数。
- **正常链**：`changed=False`，不发事件、不写 warning。
- **trace**：run 起点修复通过 `TraceRecorder.record("tool_pairing_repaired",
  source="run"|"resume", ...)` 记录 step；finally 修复通过同一 API 记录
  `source="finally"`（同步、异常隔离）。step type 新增；benchmark artifact 向后兼容，
  消费方按 type 过滤；`full_trace=False` 时 id 列表有界。
- **finally 修复**：写 warning 日志 + 同步 trace step（若 recorder 存在），不 await
  事件；若它是唯一修复点，下次 run 起点 `changed=False`，因此用户不会看到 Web 事件——
  这是有意的：Web 事件是「历史在本次 run 开始时被修复」，finally 修复属于「尽量不产生
  坏历史」，但 trace/日志仍可追踪。
- 前端对未知事件类型默认忽略（现有 WebSocket handler 只 switch 已知 type），无需前端
  渲染该事件；事件主要供日志/debug/trace。

### Decision 9：测试策略

**保留的真实链路测试**：`tests/agent/test_issue304_dangling_tool_calls_repro.py`
（提交 `5b3af47e`）。实现时改造：

- 端到端断言不变：cancel → 重新加载/恢复 → 下一次请求必须成功返回
  `"recovered ok"`，协议 fake provider 不记录未配对 `tool_use`。
- 当前「落盘快照必须是悬空、且没有 tool 消息」的**触发断言**在 finally 修复落地后会
  变红；实现时把它拆成：
  - 给 `SlowTool` 注入 `messages` 引用（测试在 run 前 `tool.messages = messages`），在
    `execute()` 内断言 assistant 的 `tool_calls` 已 append、且尚无匹配 `tool` 消息，
    证明中断窗口真实；这是**中断前**断言，不依赖落盘结果；
  - 保留端到端用例作为验收：取消后落盘快照 SHALL 已含合成 `tool` 消息，下一次请求成功。
- 另加一个**直接构造悬空快照**的恢复测试，绕过 finally 修复，专门覆盖
  `_run` 起点 resume 修复（模拟 SIGKILL 后快照含悬空、或历史由旧版本写入）。
- **强化协议 fake provider**：在 `_violations()` 前先按 Anthropic 语义**合并连续
  user 消息**（模拟 API 的「Consecutive user turns combined into a single turn」），
  再断言：(a) 每个 `tool_use` 的 id 在下一条 user 轮中恰有一条 `tool_result`；
  (b) 该 user 轮中所有 `tool_result` 位于文本/其他 block 之前；(c) 无 orphan
  `tool_result`、无重复 `tool_use_id` 结果。不能只检查「下一条消息里出现 id」。

**纯函数单测**（`tests/agent/test_message_chain_repair.py` 或并入
`tests/agent/test_message.py`）：

1. 末尾单个悬空 → 一条合成 tool 消息；id/name/前缀/确定性文案。
2. 同一 assistant 三个 tool_calls、只有一个已有结果 → 只补两个，顺序正确。
3. 两个连续 assistant 各自悬空 → 各自补，顺序/位置正确。
4. 悬空 assistant 后有 user 文本 → 合成结果插在 assistant 与 user 之间。
5. 有效链 → 原列表/消息对象/序列化字节不变，`changed=False`。
6. 幂等：`repair(repair(x))` 第二次 `changed=False`，`to_dict` 字节一致。
7. 结果在调用之前（orphan-before）或出现在非相邻位置（misplaced-after）→ **不合成**，
   只记录 warning；断言修复**不新增**同一 `tool_call_id` 的第二条 `tool_result`
   （输入本身已有的重复属畸形输入，不在承诺范围）。
8. 空 id → 不合成，记录 warning。
9. spilled preview 结果（`role=tool` + `tool_call_id` + preview 文本）→ 视为已解决。
10. assistant 文本/reasoning 保留。

**Loop/集成**：

1. cancel 中途 → `run()` finally 落盘快照已配对（无悬空）；同进程下一次 run 成功。
2. 直接构造悬空快照 → `resume_snapshot` run 成功；payload 合法。
3. 正常 run → 无合成、无事件、消息链不变（对照组）。
4. 修复时发 `tool_pairing_repaired` 事件；`changed=False` 不发。
5. 修复 → compaction → 序列化仍合法（tool 链不被拆）。
6. spill：历史中有 spilled tool 结果时，修复不重复合成，spill 前后配对不变。
7. trace `tool_pairing_repaired` step 有界；finally 唯一修复点记录
   `source="finally"`（ADV-2）。
8. OpenAI 序列化：**干净的 Case A** 修复历史每个 `tool_calls[].id` 恰一条
   `role="tool"`；修复**不新增** orphan/重复（输入已有畸形结果不承诺清理）。
9. resume 早期取消（ADV-8/D2）：在 `set_mode` await 点 cancel，快照仍含原历史 + 新
   输入，且 todos/active_skills/user_system_prompt 已恢复（不是默认/未恢复值）。

**Chat vs 群聊**：

- `SessionManager.run_session` 取消 → `unload_session` → `resume_session_async` →
  再 run 成功（沿用 `/tmp/repro-304.md` 的 web 探针）。
- 群聊：`WebSessionRunner.run` 超时/取消成员 run 后，下一轮成员 run 可用；房间系统
  日志只含 `HTTP <status>` + 已知错误类型枚举（未知写 `unknown`） 固定摘要（不含 `error.message`/
  原始 body/payload/system prompt/凭据）；envelope 字段不变（既有 group 测试）。

**诊断性**：

1. 流式 400（fake `httpx.MockTransport` + SSE）→ 异常带 body 属性，
   `_http_error_text` 返回原文；Web error 事件含 `detail`/`status_code`；前端
   `readableErrorMessage` 输出 message + detail。
2. 非流式 400（Anthropic + OpenAI）→ 同上。
3. 400 body 不可读/为空 → 不崩，事件不加 `detail`。
4. 非 HTTP 异常（例如 `RuntimeError`）→ 事件形状与现状一致（无 detail）。
5. 既有 reasoning/cache/vision 400 重试不回归。
6. 群聊 `TurnOutcome.message` 含 `HTTP <status>` + 已知错误类型枚举（未知写
   `unknown`）固定摘要，编排器系统日志可见；把哨兵分别放进 `error.message`、原始
   body 与不在枚举内的 `error.type`，断言房间日志均不含（type 落为 `unknown`）。

**正常路径不变**：有效历史 run 的 `messages.json` 与 payload（除既有时间/运行 id 外）
不变；现有 `tests/agent/test_loop.py`、`tests/agent/test_anthropic_llm.py`、
`tests/web_tests/test_session.py` 不回归。

**命令**：

```bash
uv run pytest -q tests/agent/test_message.py tests/agent/test_message_chain_repair.py \
  tests/agent/test_issue304_dangling_tool_calls_repro.py tests/agent/test_loop.py \
  tests/agent/test_anthropic_llm.py tests/agent/test_openai_llm.py \
  tests/agent/test_trace_recorder.py tests/web_tests/test_session.py
uv run pytest -q
npx --yes @fission-ai/openspec@1.4.1 validate --all --strict
uv run python scripts/check_openspec_artifacts.py --base-ref origin/master --require-base
```

### Decision 10：文档与 ADR

- 新增 `docs/adr/ADR-0009-resume-tool-call-pairing-repair.md`：层选型（load vs resume vs
  serialization vs run boundary）与合成 vs 丢弃两组合计 ≥ 2 个被拒备选；记录幂等/
  确定性、finally best-effort 边界、诊断性传播。
- 规格 delta 见 `specs/`。
- `docs/openspec-change-backlog.md` 登记本 change（issue #304）。
- 文档影响检查：`docs/architecture.md` 的 AgentLoop/会话恢复段、`docs/testing-guide.md`
  的回归测试要求、`README*` 是否需要提及「中断后会话自动恢复」；只改事实变化。

## Risks / Trade-offs

- **模型误把合成结果当真实输出（medium）**：固定标记 + 「synthetic/interrupted/可能
  已部分执行」+「重试前先检查状态」；测试钉住文案。仍不能 100% 阻止模型忽略标记。
- **非幂等工具重试风险（medium）**：合成结果可能促使模型重跑一个实际已部分执行的
  写/删除工具。文案刻意写「inspect state before retrying」；不自动重放工具。该风险
  低于「会话永久不可用」，且删除/丢弃方案同样无法告诉模型真实结果。
- **prompt cache 一次性失效（low）**：修复改变历史前缀一次；确定性内容保证后续 run
  稳定。若每次加载都产生不同文案会持续失效——用幂等/确定性测试钉住。
- **错误 body 含敏感/回显内容（medium，群聊共享面）**：异常属性保留完整 body 供重试
  判定；普通 Chat 的 Web 事件展示有界 4096 字符；**群聊房间系统日志只使用
  `HTTP <status>` + 已知错误类型枚举（未知写 `unknown`） 固定摘要**，不写 `error.message`、
  首行正文、原始 body、请求 payload、system prompt、工具参数或凭据。前端 textContent
  渲染。若 body 回显用户输入，普通 Chat 仍可能在 UI 可见，但这是用户自己的会话内容；
  群聊共享面由上述固定摘要隔离。
- **事件/日志噪音（low）**：只在 `changed=True` 发事件；正常链零开销（一次 O(n) 扫描）。
- **合成前缀与真实结果碰撞（low）**：真实工具结果若恰好以
  `[asterwynd:synthetic-tool-result] Error:` 开头，会被序列化层误标 `is_error`。
  前缀是保留命名空间，概率极低；实现测试加一条「真实结果以该前缀开头」的记录性用例，
  不改变 Message schema。
- **SIGKILL/断电不覆盖（已声明）**：靠 run 起点兜底；若快照本身损坏（JSON 非法）仍走
  既有 damaged 处理，不在本 change 扩张。
- **畸形链不重排（low）**：assistant 与 tool 结果之间夹文本、orphan result 只记录；
  这些不是 #304 的取消产物，避免引入破坏性重排。
- **群聊共享日志（medium）**：房间系统日志只接收 `HTTP <status>` + **已知错误类型
  枚举**（未知写 `unknown`）固定摘要；不写 `error.message`、首行正文或原始 body，
  避免 provider 自由文本/任意 type 字符串回显请求内容；长度和内容双重有界。

## Testing Strategy

见 Decision 9。补充执行纪律：

- TDD：先写纯函数/恢复/中断/诊断测试并确认在未修实现上红；再实现。
- 变异验证：把 `repair_tool_call_pairing` 改为 no-op → 恢复/中断/幂等用例变红；
  把 HTML 转义/`textContent` 改坏不适用（前端用 textContent），改为把 detail 移除 →
  诊断用例变红。
- 全量 pytest 与 OpenSpec strict validate / 瘦 checker 在收尾执行；与本机基线对照，
  既有 `/tmp` 环境失败须同因。

## User Rulings

- **U1（2026-11-02，本 change 启动指令）**：用户明确要求本 change 的**设计阶段对抗环
  无轮数上限**，覆盖 `AGENTS.md` 中「最多 20 个已收口轮、超限 BLOCKED」的默认上限；
  出口仍只有 `PASS` / `BLOCKED` + 成因。该裁决已写入 `workflow-events.jsonl` 的
  `user_ruling` 事件（seq 3）与 `tasks.md` 0.3，作为流程豁免证据。

## Open Questions

无。grill 把初稿的三个问题（合成结果 UI 可见性、错误详情展示形态、是否附带工具
name/id）全部移入 `reviews/grill-design.md` 的 `## Code-Resolved Questions` 并用代码
证据定案：合成结果在 `session.messages` 中由 `session_history` 投影为 tool 行（首次
重连的快照历史由 `build_history_payload` 的副本修复覆盖，本 change 已补）；错误详情
内联 `message + "\n" + detail`，`.message` 基础样式已 `white-space: pre-wrap`
（`web/static/style.css:161-168`），无需新组件/CSS；合成文案同时携带 name + id
（Decision 2）。因此本 change 无待用户拍板项，停轮时明确报告「无 Open Question」。

## Pre-Implementation Review

- **grill**：paseo 托管的独立零记忆 agent `fb029c8c-4f40-4fbc-8dfc-e1daff8bc052`
  （2026-11-02）产出 `reviews/grill-design.md`：6 条 Confirmed Decisions、0 Open
  Questions；核心方案（run 边界主修 + 合成结果 + finally best-effort + 诊断性传播）
  被确认，结论为「可增量修，无需推倒重写」。已整合的必须修改：
  1. **Blocker（流程）**：tasks 0.3 的「无轮数上限」与 AGENTS 默认 20 轮冲突 →
     记录用户 U1 明确豁免到 `## User Rulings`、`workflow-events.jsonl` seq 3 与 tasks 0.3；
     其余出口语义不变。
  2. **High（spec/design 事件范围）**：spec 事件条款收敛为「run 起点修复且 changed 时」；
     finally 修复只写 warning 日志 + 同步 trace step，不 await Web 事件（spec delta 已同步）。
  3. **High（畸形链判定）**：Decision 3 区分 Case A（整条历史无该 id 结果 → 在下一个
     非 tool 消息前合成）与 Case B（结果存在但位置不连续 → 不重复合成、只记录）；
     proposal 需求 1、design Goals、tasks 1.1.7 与 spec 范围已统一到可观测判据。
  4. **Medium（首次重连可见性）**：`build_history_payload` 对 `resume_snapshot.messages`
     的副本做只读修复，使重启后首次连接即可看到合成结果（tasks 1.2.8 / 2.9）。
  5. **Medium（群聊失败原因）**：新增 `_run_session_locked.turn_error_message`，drain
     error 事件时保存 **`HTTP <status>` + 已知错误类型枚举（未知写 `unknown`） 固定摘要**（不是
     `error.message`/原始 body），再传给 `TurnOutcome.message`；原始 bounded detail
     只留在成员自己的 error 事件（tasks 2.7）。
  6. **Medium（RIR）**：research questions 移除 codex；Anthropic `is_error` 证据标注为
     次级依据（官方页区域阻断），但序列化层仍按合成前缀写 `is_error: true`。
  7. **Medium（Open Questions 初稿）**：删除 Q3、将 Q1/Q2 移入 Code-Resolved，见上。
  8. **Low**：事件 id/name 逐项截断；`_is_reasoning_400` 用完整 body、展示才截断；
     群聊日志不得拼接请求 payload/凭据；补 resume 首事件顺序与空/重复 id 的记录性测试。
- **设计阶段对抗闭环**：独立零记忆审阅者 `581c8222-240e-4e85-8120-cb16810e1adc`
  （2026-11-02）第 1 轮开批 8 项（1 high + 7 medium），已全部整合：
  1. **ADV-1 high**：orphan/misplaced 在 docs 间矛盾 → 统一为「整条历史无该 id 结果才
     合成；orphan-before / misplaced-after 只 warning、不合成、不产生重复结果」，
     proposal 需求 1/Goals/tasks 1.1.7/spec 范围同步；补 misplaced-after 测试。
  2. **ADV-2 medium**：finally 修复无结构化观测 → finally 同步记录
     `source="finally"` 的 trace step（不 await 事件），spec/design/tasks 同步。
  3. **ADV-3 medium**：合成缺 provider 错误信号 → Anthropic 序列化层对合成前缀写
     `is_error: true`；OpenAI 用 `Error:` 文本前缀（无 `is_error` 字段）；不新增
     `Message` 字段/持久化 schema。
  4. **ADV-4 medium**：群聊共享日志泄漏 body → `TurnOutcome.message` 用
     `HTTP <status>` + 已知错误类型枚举（未知写 `unknown`） 固定摘要；原始 detail 只发给成员自己的连接。
  5. **ADV-5 medium**：缺 OpenAI pairing 规范/测试 → agent-runtime 改为 provider-neutral
     表述 + 新增 OpenAI 序列化配对 Scenario 与测试。
  6. **ADV-6 medium**：resume 历史只读展示无 spec → web-ui 新增
     `Web session 恢复历史的只读配对展示` 要求 + Scenario。
  7. **ADV-7 medium**：测试不足 → fake provider 先合并连续 user 轮再断言 tool_result
     在轮首、无 orphan/重复；补 misplaced-after、OpenAI pairing；触发断言改为
     `SlowTool` 注入 `messages` 的中断前断言。
  8. **ADV-8 medium**：resume 早期取消丢历史 → resume 消息重建移到 `set_mode` await
     之前；补 Scenario 与测试。
- **第 1 轮修复验证**：审阅者对 ADV-1..ADV-8 逐项判定 **8/8 verified**，
  本轮批次收口；验证期新增 3 项 deferred medium+，已全部整合：
  1. **ADV-D1 medium**：群聊摘要仍把 provider 控制的 `error.message` 原样写入
     共享日志 → 改为 `HTTP <status>` + 已知错误类型枚举（未知写 `unknown`） **固定摘要**，
     不写 `error.message`/首行/原始 body；原始 bounded detail 只给成员自己的连接。
     spec/design/tasks 与哨兵测试同步。
  2. **ADV-D2 medium**：ADV-8 只保住 `messages` → 把 `_execution_todos`、
     `_sync_todo_next_id`、`skill_runtime.restore_skills`、`_user_system_prompt` 等
     同步状态恢复也移到 `set_mode` await 之前；spec Scenario/tasks 1.1.12 同步。
  3. **ADV-D3 medium**：位置错误/OpenAI Scenario 对最终历史做绝对「无 orphan/重复」
     承诺 → 改为「修复 SHALL NOT 新增；输入已有 orphan/重复属范围外」，GIVEN 限定为
     干净的 Case A 输入；tests 1.3.3 同步。
- **设计阶段对抗闭环结果**：第 1 轮 ADV-1..ADV-8 全部 verified；第 2 轮 D2 verified、
  D1/D3 未通过并继续修；第 3 轮 D1/D3 verified，deferred 0，`## 闭环出口` = **PASS**（审阅者
  `581c8222-240e-4e85-8120-cb16810e1adc`，2026-11-02）。
