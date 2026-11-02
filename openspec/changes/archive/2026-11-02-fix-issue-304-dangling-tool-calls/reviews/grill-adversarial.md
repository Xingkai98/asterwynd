# Grill Adversarial: fix-issue-304-dangling-tool-calls

## Reviewer
- run id: pending-main-session
- 时间: 2026-11-02

## 第 1 轮

### 开批（medium+）

- **ADV-1** [high]: orphan / misplaced 的处置在 design、spec、tasks、proposal 之间互相矛盾，按 tasks 实现会直接违反 spec 并可能制造同一 id 的两条 `tool_result`。证据：`tasks.md:34`（1.1.7「结果在调用之前（orphan）→ 不当作配对，仍补合成」）与 `design.md:363`（Decision 9 测试 7 同文）要求补合成；但 `design.md:155-159`（Decision 3）和 `specs/agent-runtime/spec.md:16` 明确「只在该 id 于整条历史中都没有任何 role=tool 消息时才合成」，位置错误时 `SHALL NOT 再合成`，`specs/agent-runtime/spec.md:66-72` 的场景也要求不重复合成。另 `proposal.md:104-106` 的「需求 1」和 `design.md:47` 的 Goals 仍承诺任意历史每个 `tool_use` 都有配对，而 `design.md:58` 的 Non-Goals 与 `specs/agent-runtime/spec.md:18` 的「范围」已把 misplaced/orphan 排除；`proposal.md:51` 的 What Changes 又写了全局存在性条件，proposal 内部也不一致。反例：输入 `[tool(x)="real", assistant A(tool_calls=[x])]`（orphan 在调用之前），按 tasks 1.1.7 会在 A 后补一条合成 `tool(x)`，payload 出现同一 `tool_use_id` 的两条 `tool_result`，与 spec 冲突；输入 `[assistant A(tool_calls=[x]), user("u"), tool(x)]`（misplaced 在调用之后），Decision 3 要求只 warning，但 tasks 1.1.7 / Decision 9 测试 7 没有覆盖这个方向，测试无法证明该分支不会被错误合成，且该链仍可能 400。要求：把 tasks 1.1.7、design Decision 9 测试 7 改成与 Decision 3/spec 一致（orphan-before 与 misplaced-after 都不合成、只 warning、并断言不产生重复结果）；补 misplaced-after 的纯函数/loop 测试；把 proposal 需求 1 与 design Goals 收敛到可观测判据「该 id 在整条历史中不存在任何 role=tool 消息」，并明确 Case B 的 payload 可能仍不合法；同时修正 `design.md:482` Pre-Implementation Review 中「该 High 已整合」的表述。

- **ADV-2** [medium]: `finally` 修复路径没有任何结构化可观测出口，和 proposal 的「trace SHALL 可记录修复 step」不一致。证据：`proposal.md:114-115`（要求 5）写明 trace SHALL 可记录修复 step；`design.md:330` 只为 run 起点修复记录 `tool_pairing_repaired` trace step；`design.md:481` 与 `specs/agent-runtime/spec.md:20` 明确 finally 修复只写 warning 日志、不 await 事件。`TraceRecorder.record` 本身是同步的（`agent/trace_recorder.py:81-91`），finally 中记录 trace 不需要 await。反例：run 在工具执行中被 cancel，`agent/loop.py:655-662` 的 finally 修复并落盘；这是唯一修复点，下一次 run 起点 `changed=False`，因此既没有 `tool_pairing_repaired` 事件也没有 trace step，运维/benchmark 只能在自由文本日志里看到修复。要求：在 finally 中同步、异常隔离地写一条 `tool_pairing_repaired` trace step（带 `source: "finally"`、count、bounded ids），或把 proposal/规格显式收敛为「只有 run 起点修复进 trace，finally 仅日志」并写测试；不能两边都保持现状。

- **ADV-3** [medium]: 合成 `tool_result` 在 provider 协议层仍是普通成功结果的形状，缺少 RIR 自己引用的 `is_error: true` 等错误信号，模型可能把占位当成功并重试非幂等工具。证据：`proposal.md:185` 的 Anthropic findings 明确「跳过的调用也应返回 tool_result（可用 is_error: true 说明）」；`design.md:139-141` 以「Anthropic 的 is_error 语义是工具执行失败、中断不完全等价」为由只保留文本标记；`design.md:424-428` 自己把「模型误把合成结果当真实输出 / 非幂等工具重试」列为 medium 风险。`agent/anthropic_llm.py:269-285` 构造 `tool_result` 时没有 `is_error`；`agent/openai_llm.py` 的 `role="tool"` 也没有等价错误信号。RIR 中 pydantic-ai 用 `outcome='interrupted'`、ADK 用 `Error:` 前缀，说明业界并非只靠自由文本。要求：在不新增 `Message.is_error` 字段（不违反 Non-Goal）的前提下，于 Anthropic `_build_payload` 对带合成前缀的消息写 `is_error: true`，并为 OpenAI 兼容路径定义可用的等价信号；若坚持纯文本，须给出比「语义不完全等价」更强的证据并说明为何 medium 风险可接受；补序列化断言测试。

- **ADV-4** [medium]: 群聊把有界 provider body 写进**共享房间系统日志**，只限长度、不限内容，可能把成员会话的私有上下文（system prompt、工具参数、用户输入回显）暴露给房间其他成员。证据：`web/static/group.js:410` 把 `data.reason` 渲染到房间时间线；`agent/team/orchestrator.py:508-512` 把 `outcome.message` 写成 `成员 X 运行失败：{reason}`；`design.md:302-304` 让 `TurnOutcome.message` 携带 bounded message + detail；`design.md:431-433` 只以「这是用户自己的会话内容」把泄漏风险降为 low，但群聊房间日志的读者不止该成员会话的所有者，provider 400 body 也可能回显请求中的 system prompt/tool arguments。要求：在写入房间日志前按结构化字段 allowlist（如只取 `error.type` / `error.message`）或脱敏/截断可回显内容；或把 detail 只发给成员自己的连接，不进入共享系统日志；补一条断言房间日志不含请求 payload / system prompt / 凭据的测试。

- **ADV-5** [medium]: spec delta 与测试仍只覆盖 Anthropic 的 `tool_use`/`tool_result`，而设计声称同一修复覆盖 OpenAI 的 `tool_calls`/`tool` 路径，缺少 OpenAI pairing 的规范场景与测试。证据：`specs/agent-runtime/spec.md:9-18`、`:41` 全部用 `tool_use` / `tool_result` 表述；`design.md:235-237` 声称 `_build_openai_messages` 无需改动且 `role="tool"` + `tool_call_id` 是 OpenAI 期望形态；`tasks.md` 1.4.2 只测 OpenAI 非流式 400 body，没有测配对；现有 repro fake（`tests/agent/test_issue304_dangling_tool_calls_repro.py:76-106`）只校验 Anthropic payload。反例：修复后的历史经 `agent/openai_llm.py` 的 `_build_openai_messages` 序列化，若某个 `tool_call_id` 没有对应 `role="tool"` 消息，Anthropic 测试全绿但 OpenAI 仍会 400。要求：把 agent-runtime 要求改为 provider-neutral（或明确列出 Anthropic 与 OpenAI 两种配对形态），补一条 OpenAI 序列化测试，断言每个 `tool_calls[].id` 恰有一条 `role="tool"` 消息、无 orphan、无重复。

- **ADV-6** [medium]: `build_history_payload` 的只读修复是用户可见行为，但 spec delta 没有对应要求，design 的 SHALL 无法被规格/门禁追溯。证据：`design.md:214-217` 写明「展示层 SHALL 对该快照历史的副本调用同一修复函数后再投影」；`tasks.md:53-55`（1.2.8）与 `tasks.md:99-101`（2.10）把它落成实现任务；`proposal.md:259` 的用户故事要求「历史里能看到」；但 `specs/agent-runtime/spec.md:9-18` 只要求 run 起点修复，`specs/web-ui/spec.md:1-38` 的 ADDED requirement 只覆盖 LLM HTTP 错误详情，没有任何「resume 历史展示合成结果」的场景。要求：在 web-ui（或 agent-runtime）delta 增加一条 requirement/scenario：resumed session 在首次新 run 前展示合成结果，且该展示只读、不落盘、不发事件；或明确把 2.10 降为非规范实现细节并删除 design 的 SHALL；无论哪种都要有对应测试。

- **ADV-7** [medium]: 测试策略不能证明「协议形态合法」和「修复前红、修复后绿」的关键边界。证据：`tests/agent/test_issue304_dangling_tool_calls_repro.py:76-106` 的 `_violations` 只检查 assistant 的**下一条**消息里是否出现对应 `tool_use_id` 的 `tool_result`，不检查 `tool_result` 是否在 content 最前、是否与文本合并、是否出现 orphan/重复结果、是否发生 role 合并；`tasks.md:34` / `design.md:363` 只覆盖 orphan-before 且与算法矛盾，没有 misplaced-after 测试；OpenAI pairing 没有测试（见 ADV-5）；`tests/agent/test_issue304_dangling_tool_calls_repro.py:238` 的 `assert not [... role == "tool"]` 在 finally 修复落地后必然变红，而 design 说的替代方案「在 fake tool 内断言 response.tool_calls 已 append 而 result 未 append」没有说明如何注入 `messages`（当前 `SlowTool` 没有该引用）。要求：强化 fake provider，至少断言 tool_result 在合并后 user 轮的最前、无 orphan/重复；补 orphan-before 与 misplaced-after 的「不合成 + warning」测试；补 OpenAI 序列化测试；明确 trigger 断言的实现方式（给 `SlowTool` 注入 `messages` 或使用 hook），并把端到端断言改为期望出现合成 `tool` 消息。

- **ADV-8** [medium]: `finally` best-effort 在 resume 分支的早期取消会落盘**被截断的历史**，design 的「落盘前补齐配对」并不能保证快照可用。证据：`agent/loop.py:709-715` 在 resume 分支先 `await self.set_mode(...)`，之后才在 `agent/loop.py:723-730` 执行 `messages.clear()` / `extend(conversation)`；`agent/loop.py:655-662` 的 finally 直接 `_save_session(messages, ...)`。反例：resume 一个 100 条消息的会话（CLI `--resume`，或恢复后 mode 被改过，导致 `resume_snapshot.mode != current_mode`），在 `set_mode` 的 `mode_changed` 事件 await 点被 cancel；finally 看到的 `messages` 只有调用方的新 user 输入，`_save_session` 用它覆盖旧快照，下一次 load 丢失 100 条历史；run 起点修复无法恢复（快照已被覆盖）。要求：把 resume 历史重建移到任何 await 之前，或在重建未完成时跳过/合并 `_save_session`（保留 `resume_snapshot.messages`），并补一条「set_mode 期间 cancel 不丢历史」的测试；若判断超出本 change，须在 Non-Goals 明确排除并说明残留风险。

### 修复验证

- **ADV-1: verified** — 当前 docs 已统一到可观测判据：`proposal.md:114-119` 只在「整条历史中不存在该 id 任何 role=tool 消息」时合成，misplaced/orphan 只 warning、不承诺 payload 合法；`design.md:47-49` Goals 与 `design.md:164-167` Decision 3 同口径；`tasks.md:34-35`（1.1.7）与 `tasks.md:40-42`（1.1.11）明确 orphan-before / misplaced-after 不合成；`design.md:396-397` 测试 7 同口径；`specs/agent-runtime/spec.md:9,16,18` 的「范围」把 Case A 与 misplaced/orphan/空/重复 id 分开。未发现残留的「仍补合成」，`design.md:523-525` Pre-Implementation Review 也同步了。
- **ADV-2: verified** — `design.md:273-277` 要求 finally 同步、异常隔离记录 `source="finally"` 的 `tool_pairing_repaired` trace step，并明确 `TraceRecorder.record` 同步；`design.md:356-359` Decision 8 同口径；`specs/agent-runtime/spec.md:20,103-108` 有正文与 Scenario；`tasks.md:64-65`（1.2.9）与 `tasks.md:104-107`（2.3）落实；`proposal.md:126-128` 需求 5 同步。
- **ADV-3: verified** — `design.md:143-147` 在不新增 `Message.is_error` 的前提下要求 Anthropic `_build_payload` 对合成前缀写 `is_error: true`，OpenAI 用 `Error:` 文本；`proposal.md:56-57,144-148,208-210` 同步；`specs/agent-runtime/spec.md:12,74-80` 有 bullet + Scenario；`tasks.md:92-93`（1.4.9）与 `tasks.md:126-128`（2.11）落实。
- **ADV-4: verified** — `design.md:329-333` 要求群聊共享日志使用 `sanitize_provider_error_detail(body)` 的结构化投影（`error.type` + `error.message` 或首行 + 状态），原始 detail 只发给成员自己的连接；`design.md:471-475,481` Risks 同口径；`specs/web-ui/spec.md:22,39-45` 有 requirement + Scenario；`tasks.md:71-72`（1.3.2）、`tasks.md:86-87`（1.4.6）、`tasks.md:114-117`（2.7）落实。新残留见 ADV-D1。
- **ADV-5: verified** — `specs/agent-runtime/spec.md:9` 已 provider-neutral（Anthropic `tool_use`/`tool_result` + OpenAI `tool_calls`/`role=tool`），`:82-87` 新增 OpenAI 序列化配对 Scenario；`design.md:249` Decision 5 说明；`tasks.md:73-74`（1.3.3）落实。新残留见 ADV-D3。
- **ADV-6: verified** — `specs/web-ui/spec.md:3-13` 新增「Web session 恢复历史的只读配对展示」Requirement + Scenario；`tasks.md:138-139`（3.3）列出；`design.md:223-227` Decision 5 说明只读副本修复。
- **ADV-7: verified** — `design.md:381-385` 要求 fake 先合并连续 user 轮再断言 tool_result 在轮首、无 orphan/重复；`design.md:396-397` 覆盖 orphan-before/misplaced-after；`design.md:410-413` 覆盖 finally trace、OpenAI、resume；`tasks.md:43-45`（1.1.12/1.1.11）、`:49-53`（1.2.1 SlowTool 注入 messages）、`:78-81`（1.4.1 强化 fake）、`:86-87`（1.4.6）、`:73-74`（1.3.3）落实。
- **ADV-8: verified** — `design.md:278-285` 明确把 resume 消息重建（conversation/clear/extend/marker/spiller.reset）移到 `set_mode` await 之前；`specs/agent-runtime/spec.md:96-101` 新增 Scenario；`tasks.md:43-45`（1.1.12）与 `tasks.md:100-103`（2.2）落实。新残留见 ADV-D2。

### 下一批（deferred）

- **ADV-D1 [medium]**: 群聊共享日志的 allowlist 仍包含 provider 控制的 `error.message`；provider 可能在 `error.message` 中回显请求 payload/system prompt/工具参数，当前 `sanitize_provider_error_detail` 只取 `error.type` + `error.message`（或首行+状态），没有对 `error.message` 内部再做脱敏，无法保证 spec 的绝对「SHALL NOT 包含 ... 工具参数或凭据」。证据：`design.md:330-332`；`specs/web-ui/spec.md:22,43-44`；`tasks.md:86-87`（1.4.6 的 sentinel 测试未规定放在 `error.message` 内）。要求：对 `error.message` 做内容脱敏/保守替换（例如只保留错误类别 + HTTP 状态，或对回显片段做 redaction），并把 sentinel 放进 `error.message` 的测试钉住。
- **ADV-D2 [medium]**: ADV-8 的修复只移动了 `messages` 重建，`_execution_todos`/skills 恢复仍留在 `await set_mode` 之后（`design.md:284` 明说「可留在 set_mode 之后」）；若在 set_mode 期间 cancel，finally 的 `_save_session` 会保存未恢复的 todos/active_skills/user_system_prompt（`agent/loop.py:709-717`、`agent/loop.py:723-730`、`agent/loop.py:1744-1770`），历史保住了但会话计划/技能/系统提示仍丢失。spec 的 resume 早期取消 Scenario（`specs/agent-runtime/spec.md:96-101`）和 tasks 1.1.12 只断言 messages。要求：把所有同步快照状态恢复移到 await 之前，或在重建未完成时用 `resume_snapshot.todos/active_skills/user_system_prompt` 合并保存；扩展测试。
- **ADV-D3 [medium]**: `specs/agent-runtime/spec.md:66-72` 的「同一 tool_use_id SHALL NOT 出现两条结果」和 `:82-87` 的 OpenAI「SHALL NOT 出现 orphan role=tool 或同一 id 的重复结果」是对**最终历史**的绝对承诺，但本 change 的 Non-Goal/范围（`:18`）明确不处理已有 orphan/重复输入，repair 不会删除它们；若输入本身含 orphan/重复，这些 Scenario / `tasks.md:73-74` 的断言会失败或诱导实现做破坏性删除。要求：把 GIVEN 限定为「输入无 orphan/重复」，或把 THEN 改为「repair SHALL NOT 新增 orphan/重复」，并补一条「已有 orphan/重复保持不承诺」的负向测试。

### low / nit 登记

- **`proposal.md:104-106` 与 `design.md:47` 的绝对承诺**：与 `specs/agent-runtime/spec.md:18` 的 Case B「范围」不一致，已并入 ADV-1 的修复要求；不单独阻塞。
- **`design.md:139-141` / `proposal.md:130-131` 的 `Message.is_error` Non-Goal**：ADV-3 建议的是序列化层 `is_error`，不是新增 `Message` 字段，因此不构成 Non-Goal 违反；若作者坚持不采用，需在 Decision 2 补证据。
- **`specs/agent-runtime/spec.md:18` 的因果限定「由 run 中断产生」**：实现无法观测「是否由中断产生」，只能观测「整条历史是否存在该 id 的 tool 消息」；建议改成纯可观测判据，避免测试/实现歧义。
- **`tasks.md:99-101` 的 2.10 排在 2.9 之前**：编号顺序 nit。
- **`docs/openspec-change-backlog.md` 新增「第二十二批」插在「第二十批」之前**：队列顺序 nit，不影响门禁。
- **`proposal.md` Change Type `secondary: []` 与 `workflow-events.jsonl` seq 1 的「secondary: observability」措辞不一致**：文档一致性 nit。
- **`design.md:431-433` 把错误 body 回显风险定为 low**：在普通 Chat 可以接受；群聊共享日志下应按 ADV-4 提升，已在 ADV-4 处理。
- **RIR 的「Anthropic 连续 user 消息会被合并」引用**：`proposal.md:194` 标注为「关键」，但 `platform.claude.com` 在本环境被 307 到 `anthropic.com/app-unavailable-in-region`，条文来自搜索摘要；建议在该条自身加置信度说明，或用一个模拟合并的 fake 测试钉住，而不是只依赖引用。
- **`design.md` 的 finally 修复位于 `background_manager.cleanup()` 之后**：`agent/tools/sandbox/base.py:86-96` 的 `force_kill_sync` 会吞掉异常，残余风险低；仍建议把修复放到 finally 第一条语句以消除顺序依赖。
- **合成消息 content 包含的 tool name/id 没有逐项长度上限**：`tasks.md` / design 只对事件 id 列表截断；异常 provider 输入可能把合成消息本身撑大，建议对 name/id 也做 bounded 处理。
- **`tasks.md:36` 的空/重复 id 用例**：已声明「不宣称已自愈」；建议在 spec 的「范围」里显式列出 empty/duplicate id 属畸形输入、不保证 payload 合法，避免读者把 ADV-1 的范围误读为覆盖它们。
- **`tests/agent/test_issue304_dangling_tool_calls_repro.py:238` 的触发断言**：已并入 ADV-7；不单独阻塞。

- **验证后状态（原 low/nit）**：`proposal.md` 的绝对承诺、`Message.is_error`、spec 因果限定、2.9/2.10 编号、Change Type 事件一致性、群聊风险等级、finally/cleanup 顺序、name/id 有界、空/重复 id 范围、触发断言均已修复；backlog 批次顺序与 RIR 连续 user 引用仍存（见下）。
- **`is_error` 前缀识别可能是双向的**：`design.md:143-147` / `specs/agent-runtime/spec.md:74-80` 用合成前缀识别；真实工具结果若以 `[asterwynd:synthetic-tool-result] Error:` 开头会被误标 `is_error`，而 spec 说真实结果 SHALL NOT 被标记。建议加一条真实结果以该前缀开头的反例，或使用更窄的识别条件；本轮不阻塞。
- **`reviews/grill-design.md:11` 的历史决策仍写「finally ... 只写 warning」**，line 13/14 的旧文本标记也仍在；当前 design/spec/tasks 已改为 warning + trace 与序列化 `is_error`。建议像 ADV-3 一样加「后续修订（ADV-2/ADV-4/ADV-8）」注记，或明确把 Confirmed Decisions 视为历史快照。
- **`proposal.md:275` 用户故事**：「不会再永久 400」未限定 Case A；misplaced/orphan Case B 仍可能 400（spec 范围已声明不承诺）。建议加「对 run 中断产生的 Case A」限定。
- **`docs/openspec-change-backlog.md:120,124`**：第二十二批仍排在第二十批之前；队列顺序 nit，不影响门禁。
- **`proposal.md` Impact Analysis 未列 `sanitize_provider_error_detail` 新 seam**：`design.md:330` 引用该 helper，proposal 影响代码段（约 `:155-170`）只列 web/session error 事件/TurnOutcome；建议补 helper 位置（`web/session.py` 或共享模块）。
- **`proposal.md:211-219` RIR 的「Anthropic 连续 user」仍引用 blocked 页面**：已有区域阻断说明；建议把该条也标为次级证据（与 `is_error` 条一致）。
- **`tasks.md:16-22` 0.3/0.4/0.5 仍未勾**：设计环收口后需勾 0.3、完成 0.4/0.5；这是流程提醒，不是设计缺陷。

### 收口确认

- 批次项数: 8
- 全部修复验证: 是（ADV-1..ADV-8 全部 verified）
- deferred: 3（ADV-D1..ADV-D3，均 medium）
- 本轮批次收口: PASS（仅指第 1 轮 8 项）
- 设计环总出口: 未定（deferred 3 项 medium+ 未修，不能写总 PASS；下一批修复后再收口）

## 第 2 轮

### 修复验证

- **ADV-D1: 未通过** — 主体修复已落地：`design.md:333-338` 的 Decision 7 传播段、`design.md:477-482` Risks、`specs/web-ui/spec.md:22,43-44`、`proposal.md:86-88`、`tasks.md:72-74/89-90/120-124` 均已改为「`HTTP <status>` + allowlist `error.type` 固定摘要，不写 `error.message`/首行/原始 body」。但 `design.md:301-302` 的提取段仍写「只有 trace / Web 事件 / 群聊日志**展示**时才截断（例如 4096 字符 + `…[truncated]`）」，把群聊日志重新描述为原始 body 的截断展示，与 `design.md:333-338` 和 `specs/web-ui/spec.md:22` 的固定摘要直接冲突。要求：删除该句中的「群聊日志」，或明确改为「trace / Web 事件展示原始 detail；群聊日志只展示固定摘要」，并补一条 design 内一致性断言/说明。
- **ADV-D2: verified** — `design.md:278-289` 已把 `conversation`、`messages.clear()/extend()`、resume marker + 新输入、`tool_result_spiller.reset`、`_execution_todos`/`_sync_todo_next_id`、`skill_runtime.restore_skills`、`_user_system_prompt` 全部移到 `set_mode` await 之前；`specs/agent-runtime/spec.md:96-102` 的 Scenario 明确断言 todos/active skills/user_system_prompt 不丢；`proposal.md:74-76,128` 与 `tasks.md:43-46`（1.1.12）、`tasks.md:105-109`（2.2）同步。低优先残留：`design.md:420` 的 Decision 9 测试 9 仍只写「快照仍含原历史 + 新输入」，未复述 todos/skills/prompt，建议与 1.1.12 对齐，但不影响本轮 verified。
- **ADV-D3: 未通过** — `specs/agent-runtime/spec.md:66-72` 已改为「修复 SHALL NOT **新增**第二条；输入已有重复属范围外」，`:82-87` 的 OpenAI Scenario 已限定「输入无 orphan/重复的 Case A」且 THEN 为「修复 SHALL NOT **新增** orphan/重复」，`tasks.md:75-77`（1.3.3）同步。但 `design.md:419` 的 Decision 9 测试 8 仍写「OpenAI 序列化：修复后的历史每个 `tool_calls[].id` 恰一条 `role="tool"`，无 orphan/重复」，缺少「干净 Case A 输入 / repair SHALL NOT 新增」限定；若按该测试项构造含 orphan/重复的输入，会与本 change 的 Non-Goal/范围冲突。要求：把 `design.md:419` 改为与 `specs/agent-runtime/spec.md:82-87` 和 `tasks.md:75-77` 同口径。

### 下一批（deferred）

- 无（D1/D3 是第 2 轮批次项本身未通过，继续修；本轮未新增 medium+）

### low / nit 登记

- **D2 低优先残留**：`design.md:420`（Decision 9 测试 9）仍只断言「原历史 + 新输入」，未写 todos/active_skills/user_system_prompt；建议与 `tasks.md:43-46`（1.1.12）对齐。
- **`error.type` 仍由 provider 控制**：D1 的固定摘要只保留 `HTTP <status>` + 匹配 `[A-Za-z0-9_.-]{1,64}` 的 `error.type`；正则限制了形状/长度，但无法从语义上证明该字段绝不含凭据。若要求绝对无凭据，建议只展示 HTTP 状态或把已知 `error.type` 映射到固定枚举；本轮不阻塞。
- **第 1 轮 low/nit 仍保留**：`grill-design.md:11` 历史决策、`proposal.md:275` 用户故事、backlog 第二十二/二十批顺序、Impact Analysis 未列 sanitize 新 seam、RIR 连续 user 引用、tasks 0.3/0.4/0.5 待收口等，均见第 1 轮登记；本轮不重复展开。

### 收口确认

- 批次项数: 3
- 全部修复验证: 否（ADV-D1 未通过；ADV-D2 verified；ADV-D3 未通过）
- deferred: 0
- 出口: 未定（D1/D3 继续修，不开新批）

## 第 3 轮

### 修复验证

- **ADV-D1: verified** — `design.md:301-304` 已改为「trace / Web error 事件展示原始 detail 时才截断；群聊共享日志不展示原始 detail，只展示固定 `HTTP <status>` + 已知错误类型枚举（未知写 `unknown`）摘要」；`design.md:335-342` 的群聊 bullet 给出枚举与 unknown 回退；`design.md:484-489` Risks、`specs/web-ui/spec.md:22,43-44,52`、`proposal.md:86-88,133-135`、`tasks.md:72-74/89-91/121-125` 同步。未再发现「群聊日志展示原始 body」的残留。低优先残留：`design.md:446-447` 的诊断测试 6 只提把哨兵放进 `error.message` 与原始 body，未提「不在枚举内的 error.type」；`tasks.md:89-91`（1.4.6）已覆盖，建议 design 测试 6 同步补齐。
- **ADV-D3: verified** — `design.md:424-425` 的 Decision 9 测试 8 已改为「**干净的 Case A** 修复历史；修复**不新增** orphan/重复（输入已有畸形结果不承诺清理）」；`specs/agent-runtime/spec.md:66-72` 与 `:82-87` 分别把位置错误与 OpenAI Scenario 限定为「repair SHALL NOT 新增；输入已有畸形属范围外」，`tasks.md:75-77`（1.3.3）同口径。verified。
- **ADV-D2 low: confirmed** — `design.md:426-427` 的 Decision 9 测试 9 已补「todos/active_skills/user_system_prompt 已恢复（不是默认/未恢复值）」，与 `tasks.md:43-46`（1.1.12）和 `specs/agent-runtime/spec.md:96-102` 对齐；第 2 轮 D2 verified 结论维持。

### 下一批（deferred）

- 无（D1/D3 verified；未新增 medium+）

### low / nit 登记

- **D2 low 已确认修复**：`design.md:426-427` 已包含 todos/active_skills/user_system_prompt。
- **D1 的 `error.type` 低优先项已解决**：不再使用自由文本形状 allowlist，改为已知错误类型枚举 + `unknown` 回退。
- **新增低优先项**：`design.md:446-447`（诊断测试 6）建议补「不在枚举内的 error.type」哨兵，与 `tasks.md:89-91`（1.4.6）完全对齐；不影响本轮 verified。
- **第 1 轮 low/nit 仍保留**：`grill-design.md:11` 历史决策、`proposal.md:275` 用户故事、backlog 第二十二/二十批顺序、Impact Analysis 未列 sanitize 新 seam、RIR 连续 user 引用、tasks 0.3/0.4/0.5 待收口等，均见第 1 轮登记；本轮不重复展开。

### 收口确认

- 批次项数: 2
- 全部修复验证: 是
- deferred: 0
- 出口: PASS

## 闭环出口

PASS

第 1 轮 8 项、第 2 轮 D2、第 3 轮 D1/D3 均已 verified；deferred 0。剩余 low/nit 见登记，不阻塞。

## 累积登记

- ADV-1..ADV-8: verified（第 1 轮）。
- ADV-D1: verified（第 3 轮）— 群聊共享日志改为固定 `HTTP <status>` + 已知错误类型枚举，原始 body 只进 trace/Web 事件。
- ADV-D2: verified（第 2 轮；第 3 轮 low 确认）— resume 全部同步状态恢复移到 `set_mode` await 前，测试 9 已补 todos/active_skills/user_system_prompt。
- ADV-D3: verified（第 3 轮）— OpenAI 测试 8 已限定干净 Case A、repair SHALL NOT 新增 orphan/重复。
- 剩余 low/nit（不阻塞）：`design.md:446-447` 测试 6 可补非枚举 `error.type` 哨兵；`grill-design.md:11` 历史决策、`proposal.md:275` 用户故事、backlog 批次顺序、Impact Analysis sanitize seam、RIR blocked 引用、tasks 0.3/0.4/0.5 待收口。
- 已核对（不作为放行）：`npx @fission-ai/openspec@1.4.1 validate --all --strict` 29/29 通过；`scripts/check_openspec_artifacts.py --base-ref origin/master --require-base` exit 0。
