# Diagnosis: 流式 tool call 参数被截断时的崩溃（issue #249）

## Symptom

会话 `edd3b6ded5eb`（workspace `/home/shared/code/temp`）在 `iteration=3` 时整个 run 崩溃，落到用户的报错文本是：

```
JSONDecodeError: Unterminated string starting at: line 1 column 7811 (char 7810)
```

- provider 走 DeepSeek 的 **Anthropic 兼容端点**（`AnthropicLLM`，`stream` 默认开启，`main.py:110`），`model=deepseek-v4-flash`。
- 会话最后一次动作是模型正在生成一个较大的 `DeclareWorkflow` spec，而**上一轮已经因输出上限触发过一次续接**（会话最后一条消息是 `loop.py:718` 的 `Please continue from where you left off.`）。
- 崩溃点不在应用可见的工具层，而在 **LLM 响应构造层**——用户看到的是一条 Python 栈错误，run 直接终止。

## Reproduction

### 环境

- 会话目录 `/home/shared/code/temp/.asterwynd/sessions/edd3b6ded5eb/{messages.json,snapshot.json}`，54 条消息，`mode=bypass`，`run_id=b204f284ec99`，`iteration=3`。
- 代码版本 `/home/happy/my-agent` master `369d99d`（与本 change 的 base 一致）。

### 最小复现（用仓库自身代码）

**链路 A — `_build_response` 的流式 block 参数被截断**：

```python
import sys; sys.path.insert(0, '.')
from agent.anthropic_llm import AnthropicLLM
llm = AnthropicLLM(api_key="k")

# 让未闭合字符串的起始引号恰好落在 index 7810（= 用户报错的 char 7810）
prefix = '{"pad":"' + 'x' * 7793 + '","goal":"'   # len == 7811，最后引号在 index 7810
blocks = {0: {"type": "tool_use", "id": "t1", "name": "DeclareWorkflow",
              "text_parts": [], "json_parts": [prefix]}}
llm._build_response(blocks, "max_tokens", usage=None)
# 修复前 => JSONDecodeError: Unterminated string starting at: line 1 column 7811 (char 7810)
```

该构造的报错列号与用户报错**逐字节一致**（`column 7811 (char 7810)`），确认机制：`input_json_delta` 分片拼出的 JSON 在字符串中间断掉。

> 注：列号一致是**构造出来的**——原始会话里具体断在哪个字符由模型输出与截断点决定，不可复得。这里只证明「同样的报错可由同一条代码路径产生」，不声称构造的字节内容与原始响应相同。

**链路 B — `_build_payload` 重放无效 arguments**：

```python
from agent.message import Message
from agent.llm import ToolCallDelta
msg = Message(role="assistant", content="hi", tool_calls=[
    ToolCallDelta(id="c1", name="DeclareWorkflow", arguments='{"spec": {"goal": "aaa')])
llm._build_payload([msg], None, "m", force_vision=False)
# 修复前 => JSONDecodeError: Unterminated string starting at: line 1 column 19 (char 18)
```

两条链路均已固化为回归测试（见 `## Regression Tests` 与 `tasks.md` 的测试项）；另有真实 SSE 路径（`stream_chat`）与 AgentLoop 端到端两条集成复现。

## Evidence

### 1. 会话每条已落盘数据都是合法的 —— 崩溃发生在运行时新响应

扫描 `/home/shared/code/temp` 与 `/home/happy/my-agent` 下全部 `.json/.jsonl`：

- 会话 `messages.json`、`snapshot.json` **可被 `json.load` 正常解析**，无错。
- 全部已落盘 tool_call 参数（最大 5861 字符）**均可解析**，远小于报错的 char 7810。
- 唯二报 `Extra data:` 的是各 workflow 的 `events.jsonl` 与 ledger —— 属**正常 JSONL**（多行），非本错。

→ 排除「已落盘文件损坏」，确认为**运行时解析新响应**时崩溃。

### 2. 定位到唯一报错点

全仓 grep：只有 `agent/anthropic_llm.py` 的 `_build_response` 是**裸 `json.loads` 且无保护**：

```python
# _build_response（修复前）
elif blk["type"] == "tool_use":
    json_str = "".join(blk["json_parts"])           # 流式累积的 partial_json
    args = json.loads(json_str) if json_str else {} # ← 无 try/except
```

对照另两条路径的不对称：

| 路径 | 行为 | 结果 |
|---|---|---|
| Anthropic **非流式**（`_chat_nonstream`） | 直接取端点已解析的 `block["input"]`（dict） | 天然不可能失败 |
| **OpenAI**（`openai_llm.py`） | 不解析，arguments 原样交给 `AgentLoop._parse_arguments` | 有 guard |
| **Anthropic 流式**（`_build_response`） | 重新拼接 `partial_json` 再 `json.loads` | **裸奔** |

### 3. 第二条链路：截断参数进入历史，下一轮再崩

截断的原始参数串会随 `loop.py:750` 进入会话历史：

```python
messages.append(Message(role="assistant", content=..., tool_calls=list(response.tool_calls)))
```

即使链路 A 降级不崩，下一轮 `_build_payload` 重放时再次 `json.loads(tc.arguments)` → 二次崩溃。

### 4. 缓释机制在最需要它的场景失效

`loop.py:714` 的 `max_tokens` 续接藏在 `if not response.tool_calls:` 内：

```python
if not response.tool_calls:
    if response.stop_reason == "max_tokens":
        ... messages.append("Please continue from where you left off.")   # 只有纯文本截断能走到
```

而「模型写大块 tool 参数」正是最容易触发输出上限的场景 —— 此时异常在**构造 response 时**抛出，loop 拿不到 `stop_reason`，续接分支不可达。

现有测试 `test_max_tokens_triggers_continuation`（`tests/agent/test_loop.py:515`）用「有部分文本、无 tool_calls」的假响应，**只覆盖纯文本截断**，精确绕开了这个洞。

### 5. 复现输出（修复前）

```
=== 链路 A: _build_response 流式 block 参数被截断 ===
  A: CRASH JSONDecodeError: Unterminated string starting at: line 1 column 7811 (char 7810)
=== 链路 B: _build_payload 重放无效 arguments ===
  B: CRASH JSONDecodeError: Unterminated string starting at: line 1 column 19 (char 18)
```

## Root Cause

**根因**：Anthropic 流式路径在**终局解析 tool call 参数**时无保护，把「输出被截断 / 流被中断」这一**可预期的运行时状态**当成了不可恢复的异常。

**放大因素**：`max_tokens` 续接逻辑的位置（`if not response.tool_calls:`）使其恰好覆盖不到 tool call 截断；且截断参数串会进入历史导致**二次崩溃**。

**非根因（明确排除）**：

- 不是「已落盘文件损坏」（Evidence §1 已证）。
- 不是「`max_tokens` 数值太小」：截断在 7811 字符处，远小于 16384 token 的容量；任何取值下该 bug 都存在（见 proposal Non-Goals）。
- 不是「模型输出不合法」：截断是运行时的正常状态，客户端有责任处理。
- 不是 OpenAI/非流式路径问题：两者均无此缺陷。

## Recommended Direction

1. **链路 A 降级**：`_build_response` 中 `tool_use` 参数解析失败不再抛异常；`stop_reason == "max_tokens"` 时**丢弃**该不完整 call（并保持 `stop_reason`），使既有续接路径可达；其它情况保留**原始串**交给 `AgentLoop._parse_arguments` 降级为可恢复的 tool error。
2. **链路 B 降级**：`_build_payload` 重放历史时解析失败降级为 `{}`（该 call 结果已在历史、不会再执行）。
3. **可观测性**：`_stream_events` 的静默 `continue` 补 warning 日志（只增日志，不改控制流）。

选型论证见 `design.md` 的 D1（为何按 `stop_reason` 分流、为何不采用 JSON 修复）；业界依据见 `proposal.md` 的 `## Reference Implementation Research`。

## Regression Tests

| 测试 | 覆盖 | 修复前 |
|---|---|---|
| `test_build_response_truncated_tool_call_max_tokens_drops_call` | 链路 A：`max_tokens` 丢弃 + `stop_reason` 保持 | RED |
| `test_build_response_truncated_tool_call_non_truncation_keeps_raw` | 链路 A：非 `max_tokens` 保留原始串 | RED |
| `test_build_response_valid_tool_call_unchanged` | 成功路径零变化（回归保护） | GREEN |
| `test_build_payload_truncated_arguments_degrades_to_empty` | 链路 B：重放降级 `{}` | RED |
| `test_build_payload_valid_arguments_unchanged` | 成功路径零变化（回归保护） | GREEN |
| `test_stream_chat_truncated_tool_json_does_not_crash` | 真实 SSE 路径端到端 | RED |
| `test_agent_loop_survives_truncated_streaming_tool_call` | AgentLoop + 真实 AnthropicLLM 端到端：不崩、续接、正常结束 | RED |

变异验证：还原修复后上述 5 条 RED 全部复现失败，恢复后全绿（见 `tasks.md` 2.6）。
