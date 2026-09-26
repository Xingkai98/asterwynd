# Design: 流式 tool call 参数被截断时不再崩溃（fix-issue-249-streaming-tool-args-truncation）

## Context

见 `diagnosis.md`。两条崩溃链路（`_build_response:496` 与 `_build_payload:124`），加一个放大因素（`max_tokens` 续接覆盖不到 tool call 截断）。

本设计的核心问题是：**当流式 tool call 的 arguments 不完整时，客户端该怎么办？**

## Goals / Non-Goals

### Goals

1. 截断不再导致 run 崩溃：降级为**可恢复**事件。
2. `max_tokens` 截断能走既有续接路径（让模型重新输出完整 tool call）。
3. 合法输入的行为**逐字节不变**。
4. 补回归测试固化两条链路。

### Non-Goals

- 不调大 / 参数化 `max_tokens`（不是病因，见 proposal）。
- 不做 JSON 修复（补齐未闭合引号/括号）。理由见 D1。
- 不改 `loop.py` 的续接判据、不改 OpenAI 路径、不重构 `_build_response`/`_build_payload` 结构。

## Decisions

### D1（核心）截断的 tool call 如何处置：丢弃 vs 保留原始串 vs 修复

三种候选：

| | **A（选定）按 stop_reason 分流** | B 一律保留原始串交给 loop | C 修复 JSON（补闭合） |
|---|---|---|---|
| `max_tokens` | **丢弃**该 call，`stop_reason` 保留 `max_tokens` → loop 续接 | 保留原始串 → loop 走 `_parse_arguments` 失败 → tool error → 模型看到错误重发 | 补成合法 JSON → **call 被执行** |
| 流中断/其它 | 保留原始串 → loop 降级为 tool error | 同左 | 补成合法 → 执行 |
| 风险 | 低 | 中：`max_tokens` 场景下白白消耗一轮「报错→重发」，且重发时上下文已含半成品 call | **高：模型并未完整表达该意图，却被执行**（残缺拓扑被注册） |
| 业界依据 | 原则 2「截断时让模型继续 / 大声失败，绝不解析 fragment」 | — | 存在此类代理（suture-stream-repair），但属激进路线 |

**选定 A。依据**：

1. **原则一致**：业界对 `max_tokens`/`length` 截断的标准处置是「抬高上限重试 / 让模型继续 / 大声失败」，**绝不把 fragment 当结果**（见 proposal 的 RIR）。A 在 `max_tokens` 时正是「让模型继续」。
2. **语义诚实**：C 的致命问题是让**未完整表达的意图被执行**。以本次场景为例，被截断的 `DeclareWorkflow` spec 若被补齐，会注册一个**模型从未完整写出的拓扑**——这是危险的静默语义，直接违反仓库「不给任何编造结果」的取向。
3. **B 在 `max_tokens` 场景是浪费**：loop 会把半成品 call 当作「参数错误」反馈给模型，模型再重发一次完整 call；而 A 直接丢弃并续接，模型在续接轮自然重发，**少一轮往返且不污染上下文**。B 相对 A 唯一优势是「非 `max_tokens` 时有更多信息」，但 A 在非 `max_tokens` 分支**同样保留原始串**（两者在非截断场景行为一致）。

**分流依据为什么用 `stop_reason` 而非「JSON 是否可解析」**：`stop_reason` 是**端点给出的**截断信号（§诊断已证该会话确实触发过 `max_tokens`），语义清晰、与业界「先看 finish reason」一致。而「JSON 解析失败」本身无法区分「被截断」与「模型真的写错了 JSON」——前者该续接，后者该让模型看到错误。用 `stop_reason` 分流正是为了区分这两种意图。

**降级实现的边界（不变量）**：

- **成功路径零变化**：`json.loads(json_str)` 成功时，`args = json.dumps(parsed)` 的输出与现状**逐字节相同**（现状也是 `json.loads` 后 `json.dumps`）。
- `json_str` 为空 → `{}`（现状保留）。
- 仅在 `except JSONDecodeError` 分支改变行为。

### D2 保留原始串时用什么形态

选中方案在非 `max_tokens` 分支**保留该 tool call**，`arguments` 传**原始串**（而非 `{}`）。

**理由**：loop 的 `_parse_arguments(delta.arguments)` 会因原始串非法而抛 `ValueError`，被 `loop.py:756` 的 `except` 捕获 → 记录 `parse_error` → 返回 `[Error: invalid JSON tool arguments: ...]` 给模型。模型因此**知道自己的输出坏了**并重试，比静默丢弃（`{}`）信息量更大。这与 OpenAI 路径**完全同构**（OpenAI 也是原样传串，交给同一个 guard）。

**注意**：这与「链路 B 重放时降级为 `{}`」不矛盾——重放时该 call 已**执行过**（有配对的 error tool_result），重放只为构造合法的 API 请求体，`{}` 不会被执行，也不会误导。

### D3 链路 B 的重放降级

`_build_payload:124` 重放 assistant 消息时，若 `tc.arguments` 非法 → 降级 `{}`。

**为什么必须降级而非抛**：这是**消息历史重放**，此时该 tool call 的结果已在 `messages` 里（`tool_result` 消息按 `tool_call_id` 配对）。重放的目的只是让 API 请求体合法（Anthropic 要求 assistant 的 `tool_use` block 必须有 `input`）。降级 `{}` 让请求能发出去；**该 call 不会再被执行**（loop 只在 `response.tool_calls` 上执行，重放的是历史消息，不是新响应）。

**为什么历史里会存在非法 arguments**：正是链路 A 在非 `max_tokens` 分支保留原始串的后果（D2）。两条链路的处理**必须配套**：A 保留原始串 → 历史里出现非法串 → B 重放时必须能容忍。这是本设计的**完整性约束**。

### D4 SSE 单行解析失败的可观测性

`llm.py:_stream_events` 的 `except JSONDecodeError: continue` 补 `logger.warning`（含 event_type 与行长）。

**只增日志，不改控制流**：现状的静默丢弃会让同类问题无声消失；补日志使其可排查。**不**在本 change 引入「重置 event_type」等行为变更（那会改变控制流，超出本 bugfix 范围，另记债务）。

### D5 spec delta 的落点

`agent-runtime` 已有一个 Requirement「Agent runtime 发布 assistant 流式输出事件」，其下已有 Scenario「streaming tool calls」。最初设想在其下**追加 Scenario**，实现时改为**新增独立 Requirement**「流式 tool call 参数不完整时降级而非崩溃」。

**改动的理由**：既有 Requirement 的主题是「**发布**流式事件」（事件时机与 payload），而本 change 的语义是「**处理不完整输入**」（截断/中断时的降级策略）——两者是不同关注点，塞进同一 Requirement 会让该条的 SHALL 主体分裂成两类不相干约束。新增独立 Requirement 后，既有 Scenario「只在 `LLMResponse.tool_calls` 完整后执行工具」保持原样（它管的是「何时执行」，本 change 管的是「不完整时怎么降级」，两者不冲突、互为补充）。

### D6 被截断的 tool call 是否要进入 messages 历史

**链路 A 在 `max_tokens` 时丢弃该 call** → 该 call **不进入** `response.tool_calls` → `loop.py:750` 的 `messages.append(Message(..., tool_calls=list(response.tool_calls)))` 自然不含它。

**这是刻意的**：进入历史的 assistant 消息若含一个**没有配对 tool_result** 的 tool_call，会违反 Anthropic 的消息链约束（每个 `tool_use` 必须有对应 `tool_result`）。丢弃正是为了维护该不变量。**反向约束由此确立**：方案 A 不能「保留 call 到 messages 但跳过执行」——那会破坏消息链合法性。

## Pre-Implementation Review

### 已解决问题

1. **截断的 tool call 该怎么办** → D1 定案：`max_tokens` 丢弃 + 续接；其它保留原始串交给既有 guard。
2. **重放历史里的非法参数** → D3 定案：降级 `{}`，且与 D2 配套（不变量闭合）。
3. **消息链合法性** → D6 定案：丢弃保证不存在孤立 `tool_use`。
4. **改动是否影响成功路径** → D1 边界声明：成功路径逐字节不变。
5. **spec 落点** → D5 定案：追加 Scenario。

### 备选方案与否决

- **否决 C（JSON 修复）**：让未完整表达的意图被执行，危险的静默语义。
- **否决「调大 max_tokens」**：非病因（诊断 §「非根因」），且无入口；只能降低概率。
- **否决「改 `loop.py:714` 的续接判据」**：链路 A 分流后该分支自然可达，改 loop 增加风险面而无必要。
- **否决「在流中途检测并提前放弃」**：需要流式增量解析的复杂状态机，收益低于在终局降级的简单方案。

## Risks / Trade-offs

- **`stop_reason` 缺失的端点在截断时不报 `max_tokens`**：此时走「保留原始串」分支，行为是「模型看到 error 后重发」而非直接续接——**仍不崩溃**，只是多一轮。可接受（降级而非崩溃是本 change 的底线）。
- **被丢弃的 call 在极少数情况下是模型「几乎写完」的**：模型在续接轮会重新输出完整版本。若模型反复在同一位置截断，需要更大的 `max_tokens`（**独立问题**，本 change 的 Non-Goal）。
- **`_build_payload` 降级 `{}` 后 API 请求体与历史不完全一致**：不影响正确性（该 call 结果已在历史），但会体现在「重放视图」里。属可接受的权衡。
- **新增的 warning 日志在极端情况下可能刷屏**（同一响应多个坏 block）：当前每条坏 block 记一次，量级受响应内 tool call 数约束（通常个位数），未做去重/限流。若后续观测到噪音，另记债务处理。
- **`stop_reason` 的取值比较依赖 `STOP_REASON_MAP` 的映射**：本 change 用 `stop_reason == "max_tokens"`（映射后的规范值）。若未来新增截断类 reason（如端点自定义），需同步扩展判据；当前只处理已知的 `max_tokens`。

## Testing Strategy

TDD（先写失败测试）：

1. **链路 A - `max_tokens`**：构造 `json_parts` 尾部截断的 `tool_use` block，`stop_reason="max_tokens"` → 断言不抛异常、该 call 被丢弃、`stop_reason` 仍为 `max_tokens`。
2. **链路 A - 非 `max_tokens`**：同上但 `stop_reason="tool_use"` → 断言不抛异常、该 call 保留、`arguments` 为原始串。
3. **链路 A - 成功路径不变**：合法 JSON → 断言行为与现状一致（回归保护）。
4. **链路 B**：构造非法 `arguments` 的 assistant 消息 → `_build_payload` 不抛异常且 `input` 为 `{}`。
5. **端到端**：mock LLM 返回截断的 tool_call → AgentLoop 不崩、能走续接/降级并结束。

判别力验证：**移除修复后 1/2/4/5 必红**（复现脚本已在 `diagnosis.md` 证明）。
