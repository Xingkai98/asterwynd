# Proposal: SSE 告警不再误报 OpenAI 的 [DONE] 结束哨兵（fix-issue-251-sse-done-warning）

关联跟踪 issue：[#251](https://github.com/Xingkai98/asterwynd/issues/251)（【bugfix】SSE 解析失败告警把 OpenAI 协议的 [DONE] 结束标记误报为坏行）。

## Change Type

- primary: bugfix
- secondary: []

## Why

issue #249（PR #250）给 `agent/llm.py` 的 `BaseLLM._stream_events` 补了一条「SSE 单行解析失败」的 warning 日志，用于让静默丢行可观测。该分支**没有特判 OpenAI 协议的流结束哨兵 `data: [DONE]`** —— 它按约定本就是**非 JSON**，`json.loads("[DONE]")` 必然抛 `JSONDecodeError`。

结果：**每次走 OpenAI provider 的请求结束时都刷一条误导性告警**：

```
WARNING asterwynd.llm:llm.py:134 Dropping unparseable SSE data line (event=None, 6 chars)
```

实测（`asterwynd run --provider openai --model deepseek-v4-flash`）：第二次 LLM 调用（收到 `[DONE]`）即产生该告警；而第一次调用（无 `[DONE]`）不产生。告警文案「Dropping unparseable SSE data line」会让人误以为丢了真实数据。

**影响面**：仅日志噪音，无功能影响（`[DONE]` 行本来就被 `continue` 掉，控制流不变）。但会污染生产日志、误导排查，属 PR #250 引入的回归。

**根因**：全仓无 `[DONE]` 特判（`grep DONE agent/openai_llm.py agent/llm.py` 零命中）；OpenAI 兼容端点普遍发送该哨兵，而现有测试 `test_openai_stream_chat_yields_text_delta_and_complete_response` 一直在喂 `data: [DONE]`，只是**无人断言日志**，故未暴露。

## What Changes

在 `agent/llm.py` 的 `_stream_events` 里，于 JSON 解析**之前**显式放行流结束哨兵：`data:` 行 strip 后等于 `[DONE]` 时 `continue`，不进 `json.loads`、不记 warning。

- **只加一个前置判定**，成功路径与真实坏行路径均不变。
- 抽一个模块级辅助 `_is_sse_stream_end(data_str)` 与常量 `_SSE_STREAM_END_SENTINEL`，避免在循环里写魔法字符串。

**spec delta**：`agent-runtime` 新增 Requirement「SSE 可观测性区分协议控制帧与坏行」（3 个 Scenario：哨兵不告警 / 真实坏行仍告警 / 含哨兵字面量的合法 JSON 不被误判）。

**明确不做**：

- 不改告警本身（真实坏行仍须告警，可观测性是 issue #249 的收益，不能因噎废食）。
- 不引入 provider 感知的哨兵配置（当前仅 OpenAI 协议使用该哨兵；如未来出现其它哨兵另案处理）。
- 不重构 `_stream_events`（事件类型解析等既有行为不动，含已知债务「解析失败未重置 event_type」，另记 `docs/known-debt.md`）。

## Non-Goals

- 不解决 `event_type` 未重置的相邻隐患（该债务已在 issue #249 收尾时记录，本 change 不扩大范围）。
- 不改 Anthropic 路径（它不发 `[DONE]`）。

## Impact Analysis

**代码影响**

| 文件 | 改动 | 风险 |
|---|---|---|
| `agent/llm.py` | `_stream_events` 前置放行 `[DONE]`；新增常量与辅助函数 | 低（只加一条短路判定，不改既有分支） |
| `openspec/specs/agent-runtime/spec.md` | 新增 Requirement「SSE 可观测性区分协议控制帧与坏行」（3 Scenario） | 低（纯新增规格条目） |
| `tests/agent/test_openai_llm.py`（增补） | 三条回归测试：`[DONE]` 不告警 / 真实坏行仍告警 / 含字面量的合法 JSON 不被误判 | 低（纯新增用例） |

**契约影响（对外）**

- 无 API/行为变更。`[DONE]` 行在修复前后都**不产生事件**（旧行为是解析失败 `continue`，新行为是显式 `continue`），下游消费的事件序列逐字不变。
- 唯一可观测差异：`asterwynd.llm` logger 不再对 `[DONE]` 产生 warning。

**不影响**

- Anthropic / 非流式路径（不使用该哨兵）。
- 真实坏行的告警（由反向守护测试固定）。
- 事件解析、`event_type` 状态机、调用方消费逻辑。

**待确认影响面**

- 无。

**测试影响**

- 新增 3 条回归测试（对应 spec 的 3 个 Scenario）：
  - `test_done_sentinel_does_not_log_dropped_line_warning`（正向：哨兵不告警；修复前 RED）
  - `test_genuinely_bad_sse_line_still_logs_warning`（反向守护：真实坏行仍**恰好 1 条**告警；修复前 RED——坏行与哨兵共报 2 条）
  - `test_legal_json_containing_done_literal_is_parsed_not_skipped`（含哨兵字面量的合法 JSON 不被误判）
- 回归：`tests/agent/test_openai_llm.py`；因改动在 LLM 共享层，按仓库规则跑全量 pytest。

**文档影响**

- 无需改文档：本 change 只影响一条日志的行为，不改变用户可见能力、CLI 输出或项目词汇。`docs/known-debt.md` 的相邻债务条目（`event_type` 未重置）不受影响、无需回写。

## Reference Implementation Research

- research_tier: exempt
- status: disabled
- reason: 属 **bugfix**（无新增能力面 + 回归测试），且为**上游已锁定决策**的直接收口：`[DONE]` 是 OpenAI 协议既定哨兵（官方 SSE 约定），修法无待定设计项——只需在解析前放行。缺陷由同仓库已归档 change `fix-issue-249-streaming-tool-args-truncation` 的收尾实测直接暴露（见 `openspec/changes/archive/2026-09-26-fix-issue-249-streaming-tool-args-truncation/`）：该 change 引入告警、本 change 修其误报，二者构成同一决策链的闭合。
- findings（本地参考仓库不可用的事实与替代依据）：本工作区**无** `.dev/reference-repos.txt`，也**无** `.codegraph/`（均已确认不存在），故无本地参考仓库可对比。替代依据为协议事实：OpenAI Chat Completions 的 SSE 流以 `data: [DONE]` 结束、该标记不是 JSON 对象（官方 API 文档与各兼容实现一致，DeepSeek 的 OpenAI 兼容端点实测同样发送）。因此「解析失败告警需前置放行哨兵」是协议层面的确定性结论，无需进一步调研。
- design impact: 确认采用「前置放行 + 反向守护测试」，不引入哨兵配置化或 provider 分支。
