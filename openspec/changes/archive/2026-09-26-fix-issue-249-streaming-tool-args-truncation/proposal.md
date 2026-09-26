# Proposal: 流式 tool call 参数被截断时不再崩溃（fix-issue-249-streaming-tool-args-truncation）

关联跟踪 issue：[#249](https://github.com/Xingkai98/asterwynd/issues/249)（【bugfix】流式 tool_use 参数被截断时 AnthropicLLM 裸 json.loads 直接崩溃，max_tokens 续接机制失效）。

## Change Type

- primary: bugfix
- secondary: []

## Why

会话 `edd3b6ded5eb`（workspace `/home/shared/code/temp`，`provider=anthropic` 走 DeepSeek 的 Anthropic 兼容端点，`model=deepseek-v4-flash`，`stream` 默认开启）在 `iteration=3` 时整个 run 崩溃：

```
JSONDecodeError: Unterminated string starting at: line 1 column 7811 (char 7810)
```

该会话最后一次动作是模型正在生成一个较大的 `DeclareWorkflow` spec，而**上一轮已经因输出上限触发过一次续接**（会话最后一条消息是 `loop.py:718` 的 `Please continue from where you left off.`）。

已用仓库自身代码稳定复现，**两条独立链路，修复前均崩溃**（详见 `diagnosis.md`）：

- **链路 A** — `agent/anthropic_llm.py:496`（`_build_response`）：

  ```python
  elif blk["type"] == "tool_use":
      json_str = "".join(blk["json_parts"])
      args = json.loads(json_str) if json_str else {}   # ← 裸 json.loads，无保护
  ```

  流式路径靠 `input_json_delta` 分片拼接 `partial_json`；一旦输出被 `max_tokens` 打满或流被中断，拼出的就是**不完整 JSON**，这里直接抛 `JSONDecodeError`。

- **链路 B** — `agent/anthropic_llm.py:124`（`_build_payload`）：

  ```python
  input_dict = json.loads(tc.arguments) if isinstance(tc.arguments, str) else tc.arguments
  ```

  即使链路 A 降级不崩，被截断的参数串会随 `messages.append(Message(..., tool_calls=...))`（`loop.py:750`）进入会话历史，下一轮重放时**再崩一次**。

**路径不对称是根因的结构特征**：非流式路径（`anthropic_llm.py:454`）直接取端点已解析好的 `block["input"]`（dict），天然不可能失败；OpenAI 路径（`openai_llm.py:116`）**不解析**，交给 `AgentLoop._parse_arguments`（`loop.py:1258`，**有** guard）。只有 Anthropic 流式路径在解析阶段裸奔。

**影响被一个设计缺陷放大**：`max_tokens` 续接逻辑（`loop.py:714`）藏在 `if not response.tool_calls:` 分支内，而「模型写大块 tool 参数」恰恰是最容易触发输出上限的场景 —— 此时异常在**构造 response 时**就抛出，loop 根本拿不到 `stop_reason`，续接分支永远执行不到。文档把「`max_tokens` 自动续接」当卖点（`docs/agent-internals.md:181`），但现有测试 `test_max_tokens_triggers_continuation` 只覆盖「有文本、无 tool_calls」的纯文本截断，**精确绕开了这个洞**。

## What Changes

**A. 链路 A 降级为「可恢复」而非崩溃**（`anthropic_llm.py:_build_response`）

`tool_use` block 的参数 JSON 解析失败时不再抛异常。行为按 `stop_reason` 分流：

- `stop_reason == "max_tokens"`（输出被截断）：**丢弃**该不完整 tool call，不放进 `LLMResponse.tool_calls`；`stop_reason` 原样保留为 `max_tokens`，让 loop 既有的续接分支接管。
- 其它情况（流中断/端点异常）：保留该 tool call，`arguments` 传**原始串**，交给 loop 的 `_parse_arguments` 降级为可恢复的 tool error（与 OpenAI 路径同构）。

合法输入路径**逐字节不变**：解析成功时行为与现状完全一致。

**B. 链路 B 重放时降级**（`anthropic_llm.py:_build_payload`）

重放 assistant 消息时，若某个 tool call 的 `arguments` 不是合法 JSON，降级为 `{}` 而不是抛异常。该 tool call 在 loop 中已有配对的 error tool_result（不会被真正执行），因此重放为 `{}` 不改变语义，只避免二次崩溃。

**C. SSE 单行解析失败补日志**（`llm.py:_stream_events`）

现有 `except JSONDecodeError: continue` 会**静默丢行**且不重置 `event_type`。补 `logger.warning`（含 event_type 与行长），使同类问题可观测；不改变控制流。

**D. 补回归测试**（仓库硬规则），覆盖两条链路 + 端到端「不崩且能恢复」。

## Non-Goals

- **不调大 `max_tokens`**：`max_tokens` 是模型输出上限，硬编码在 `agent/llm.py:87`，全仓无 CLI/config/env 入口。本次 bug 在任何 `max_tokens` 取值下都会发生（截断位置 7811 字符远小于 16384 token 的容量），调大只是降低概率、推迟崩溃，**不是修法**。是否参数化并调大是独立的第二个决定，不在本 change。
- **不实现 JSON 截断修复（repair）**：业界有「补齐未闭合字符串/对象」的修复型代理（如 suture-stream-repair），但那会让**被截断的 tool call 看起来完整并被执行**，属于危险的静默语义。本 change 选择「丢弃 + 续接」的保守路线。
- **不改 `max_tokens` 续接的判据**（`loop.py:714` 的 `if not response.tool_calls:` 不改）。链路 A 在 `max_tokens` 时分流掉不完整 tool call 后，该分支自然可达，无需改 loop。
- **不改 OpenAI 路径**（它本就无此问题：不解析）。
- **不重构 `_build_response` / `_build_payload` 的结构**。

## Impact Analysis

**代码影响**

| 文件 | 改动 | 风险 |
|---|---|---|
| `agent/anthropic_llm.py` | `_build_response`：`tool_use` 参数解析失败降级（按 `stop_reason` 分流）；`_build_payload`：重放解析失败降级为 `{}` | 中（触碰流式响应构造主路径，但只在解析失败分支改行为；成功路径逐字节不变） |
| `agent/llm.py` | `_stream_events` 的静默 `continue` 补 warning 日志 | 低（只增日志，不改控制流） |
| `tests/agent/test_anthropic_llm.py`（增补） | 两条链路的回归测试 + 端到端恢复 | 低（纯新增用例） |

**契约影响（对外）**

- `AnthropicLLM._build_response` 的**输出契约不变**：合法输入 → 输出逐字段不变；非法输入 → 从「抛 `JSONDecodeError`」变为「降级返回」（`max_tokens` 时丢弃该 call，否则保留原始串）。这是**把未定义行为（崩溃）收敛为已定义行为**，不构成对既有消费者的破坏。
- 不使用 `AnthropicLLM` 的路径（OpenAI provider、非流式）行为完全不变。

**不影响**

- OpenAI provider 路径（`openai_llm.py` 不解析参数）。
- Anthropic **非流式**路径（`_chat_nonstream` 用端点已解析的 `block["input"]`）。
- `AgentLoop` 的续接逻辑、tool 执行、approval、trace、session 持久化。
- 合法长度为 0 的参数（`json_str` 为空 → `{}`，现状保留）。

**待确认影响面**

- 无。降级策略（丢弃 vs 保留原始串 vs 修复）已在 design D1 定案，依据为业界实践调研（见 RIR）。

**测试影响**

- 新增回归测试覆盖：①「`max_tokens` + 截断 tool call → 不抛异常且该 call 被丢弃」；②「非 `max_tokens` + 截断 tool call → 不抛异常且原始串保留」；③「`_build_payload` 重放无效 arguments → 不抛异常」；④端到端「截断 → loop 续接/降级 → run 正常结束而非崩溃」。
- 回归：`tests/agent/test_anthropic_llm.py`、`tests/agent/test_loop.py`；因改动涉及 LLM 层，按仓库规则须跑**全量 pytest**。

**文档影响**

- `docs/agent-internals.md:181` 的「`max_tokens` 自动续接」表述需补一句边界（tool call 截断时的行为），使文档与实现一致。
- `docs/known-issues.md`：按结论**新增**一条记录（受保护路径，需 `protected_artifact_explained` 结构化事件）。
- 关键词扫描 `docs/`、`README.md`、`AGENTS.md`、`CONTEXT.md` 中与流式 / 截断 / `max_tokens` 相关的段落。

## Reference Implementation Research

- research_tier: light
- status: enabled
- reason: 属 **bugfix**（无新增能力面），但「截断时该丢弃、保留还是修复 tool call」是**有业界分歧的设计选择**（存在「修复型反向代理」这一类做法），故按 `light` 档浅调研，结论一段 + 落点，`research questions` 从略。
- findings:

  **业界共识（本 change 的设计依据）**：流式 tool call 的 arguments 是**分片到达**的（OpenAI 的 `delta.tool_calls[].function.arguments` chunked 重组、Anthropic 的 `content_block_delta` + `input_json_delta`、Responses API 的 `response.function_call_arguments.delta`），**在收到终局事件前不完整**；`max_tokens`（Anthropic）/ `length`（OpenAI Chat）/ `max_output_tokens`（Responses）截断或 socket 断开会留下未闭合的 JSON，表现为 `JSONDecodeError` / `serde_json` EOF / Pydantic 校验错。

  三条被反复给出的处理原则，与本次修法逐条对应：

  1. **不要提前解析**（"parse-early trap"）——必须缓冲到调用完整。→ 本 change 不在流中途解析（现状即是），只在**终局**解析失败时降级。
  2. **先看 stop/finish reason 再动内容** —— 截断时应「抬高上限重试 / 让模型继续 / **大声失败**」，**绝不解析 fragment**。→ 对应 design D1：`stop_reason == "max_tokens"` 时**丢弃不完整 call 并交给既有续接**（"让模型继续"路线）。
  3. **不要把半成品 tool call 回灌进 loop** —— 有 changelog 明确记录「responses cut off by `max_tokens` no longer feed half-formed tool calls back through the loop」这一修复。→ **直接印证链路 B 是公认反模式**，本 change 的 B 项正是修它。

  **被否决的「修复」路线**：存在超低延迟反向代理（suture-stream-repair 类）通过补齐未闭合字符串/对象来「修好」截断 JSON。本 change **不采纳**：把截断的 tool call 补成合法会使其**被执行**，而模型原本并未完整表达该意图（`DeclareWorkflow` 的 spec 会以残缺拓扑被注册），属危险的静默语义。保守的「丢弃 + 续接」与上述原则 2 一致。

  **本地参考仓库不可用的事实与替代依据**：本工作区**无** `.dev/reference-repos.txt`，也**无** `.codegraph/`（均已确认不存在），故无本地参考仓库可对比。替代依据为上述业界来源（LLM 流式解析与截断处理的公开实践、网关/代理侧对 tool-call frame 的缓冲策略）。

- design impact: 确认采用「按 `stop_reason` 分流 + 丢弃/降级 + 续接」而非「JSON 修复」或「调大 max_tokens」；无需新增依赖或协议变更。
