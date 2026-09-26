# Diagnosis: SSE 告警误报 [DONE] 结束哨兵（issue #251）

## Symptom

走 **OpenAI provider** 的每次请求结束时，`asterwynd.llm` logger 产生一条误导性告警：

```
WARNING asterwynd.llm:llm.py:134 Dropping unparseable SSE data line (event=None, 6 chars)
```

实测命令与输出（`asterwynd run --provider openai --model deepseek-v4-flash`）：

```
INFO [Iteration 0] messages=2
INFO HTTP Request: POST https://api.deepseek.com/v1/chat/completions "HTTP/1.1 200 OK"
INFO [Tool] Read -> 'hello-world-42\n'
INFO [Iteration 1] messages=4
INFO HTTP Request: ... "HTTP/1.1 200 OK"
WARNING asterwynd.llm Dropping unparseable SSE data line (event=None, 6 chars)   ← 本 bug
INFO [Done] reason=StopReason.END_TURN, tools=1
```

注意语义倒挂：**先有 `200 OK`、后有业务正常完成**，中间夹一条「丢弃坏行」告警 —— 实际没有任何数据被丢。

## Reproduction

最小复现（用仓库自身代码）：

```python
import json
json.loads("[DONE]")
# => json.decoder.JSONDecodeError: Expecting value: line 1 column 2 (char 1)
```

即 `[DONE]` 必然进 `except JSONDecodeError` 分支。完整路径可用现有测试的 SSE 行复现：

```python
lines = [
    'data: {"choices":[{"delta":{"content":"Hi"},"finish_reason":null}]}',
    'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}',
    "data: [DONE]",
]
# 修复前：产生 1 条 "Dropping unparseable SSE data line" 告警
```

**关键**：`tests/agent/test_openai_llm.py::test_openai_stream_chat_yields_text_delta_and_complete_response`（issue #250 之前就存在）**一直在喂 `data: [DONE]`**，只是从未断言日志，所以这个误报自 issue #249 起就潜在地存在、直到本次端到端实测才被看见。

## Evidence

### 1. 告警文案与真实情况不符

告警说「Dropping unparseable SSE data line」，但对比修复前后的事件序列：`[DONE]` 行**在修复前后都不产生事件**（旧行为是解析失败 `continue`，新行为是显式 `continue`）。所以没有任何真实数据因此丢失 —— 文案与事实不符。

### 2. 只发生在 OpenAI 路径，且只在收到 `[DONE]` 的那次调用

实测两次调用：第一次（无 `[DONE]`，只收到增量 chunk 后直接结束）**不报**；第二次（收到 `data: [DONE]`）**报一条**。与「[DONE] 触发」的假设吻合。

### 3. 全仓无 `[DONE]` 特判

```
$ grep -rn "DONE" agent/openai_llm.py agent/llm.py
（零命中）
```

`_stream_events` 对 `data: ` 行一律 `json.loads`，没有任何前置过滤。

### 4. 引入点明确

`git log -S "Dropping unparseable SSE data line"` 指向 issue #249 / PR #250 引入的告警分支（该分支本身是好意：让静默丢行可观测）。本 change 是它的**收口**，不是对它的否定。

## Root Cause

`_stream_events` 的 `data:` 行处理**把「协议规定的非 JSON 控制帧」与「真正损坏的数据行」混为一类**：两者都会让 `json.loads` 抛 `JSONDecodeError`，而 issue #249 新增的告警只看到异常、看不到语义差异，于是把 OpenAI 协议的流结束哨兵 `[DONE]` 也记成了坏行。

**非根因（明确排除）**：

- 不是端点异常：两次请求都是 `200 OK`，业务正常完成。
- 不是数据丢失：`[DONE]` 行本就不产生事件，修复前后事件序列不变。
- 不是 OpenAI 实现专有：`[DONE]` 是 OpenAI Chat Completions SSE 的通用约定，任何兼容端点（含实测的 DeepSeek OpenAI 端点）都会发送。

## Recommended Direction

在 `_stream_events` 的 `data:` 分支里，于 `json.loads` **之前**显式放行哨兵：`data_str.strip() == "[DONE]"` 时 `continue`。抽 `_is_sse_stream_end()` + 常量，避免魔法字符串。

**为什么不采用其它方向**：

- **删掉整条告警**：会让 issue #249 的可观测性收益归零（真实坏行又变静默）。已用反向守护测试固定这条边界。
- **把 `[DONE]` 当作可解析特殊情况塞进 JSON 分支**：语义更绕，且哨兵按定义就不是 JSON，前置放行更准确。
- **provider 感知的哨兵表**：当前只有 OpenAI 协议用该哨兵，过度设计；出现第二种哨兵时另案。

## Regression Tests

| 测试 | 覆盖 | 修复前 | 修复后 |
|---|---|---|---|
| `test_done_sentinel_does_not_log_dropped_line_warning` | 正向：`[DONE]` 不产生告警 | RED | GREEN |
| `test_genuinely_bad_sse_line_still_logs_warning` | 反向：真实坏行仍产生**恰好 1 条**告警 | RED（坏行+哨兵共报 2 条） | GREEN（1 条） |

反向守护是刻意的：它保证修复不会顺手把告警一起关掉（否则本 change 就退化成「用静默换安静」）。

变异验证：把 `_is_sse_stream_end(data_str)` 短路为 `False` → 两条测试均 RED；还原后 GREEN。
