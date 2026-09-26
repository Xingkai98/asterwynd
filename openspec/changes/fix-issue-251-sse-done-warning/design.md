# Design: SSE 告警误报 [DONE] 结束哨兵（fix-issue-251-sse-done-warning）

## Context

见 `diagnosis.md`。issue #249 给 `BaseLLM._stream_events` 加了「SSE 单行解析失败」告警，未特判 OpenAI 协议的流结束哨兵 `[DONE]`（它按约定不是 JSON），导致每次 OpenAI 请求结束都刷一条误导性告警。

核心问题：**如何区分「协议规定的非 JSON 控制帧」与「真正损坏的数据行」？**

## Goals / Non-Goals

### Goals

1. `[DONE]` 不再产生告警。
2. 真实坏行**仍然**告警（不牺牲 issue #249 的可观测性）。
3. 事件序列零变化（`[DONE]` 修复前后都不产生事件）。

### Non-Goals

- 不解决 `event_type` 未重置的相邻债务（`docs/known-debt.md` 已记，另案）。
- 不做 provider 感知的哨兵配置。
- 不重构 `_stream_events`。

## Decisions

### D1 放行位置：`json.loads` 之前 vs 在 `except` 里判别

| | **A（选定）解析前显式放行** | B 在 except 分支里判别 |
|---|---|---|
| 写法 | `if _is_sse_stream_end(data_str): continue` 置于 `try` 之前 | 先 `json.loads`，失败后在 `except` 里判断是否哨兵 |
| 语义 | 「这不是待解析的数据，直接跳过」 | 「解析失败了，但失败原因可接受」 |
| 成本 | 每行一次字符串比较（`strip()` + `==`） | 每行照样先付一次异常构造开销 |
| 可读性 | 意图直白：哨兵不进解析 | 需要读两级嵌套才能理解 |

**选定 A**。理由：哨兵**按定义就不是 JSON**，把它放进 `json.loads` 再靠异常分类去识别，属于「先制造错误再消解错误」。前置放行既更准确，也避免每行无谓的异常路径开销（OpenAI 流每个响应至少有一条 `[DONE]`）。

### D2 判据形态：`strip()` 后精确等于

用 `data_str.strip() == "[DONE]"` 而非 `startswith`/`in`。

**理由**：SSE 规范中 `data:` 后的前导空格由规范处理，但不同实现的空格数不一；用 `strip()` 容忍空白差异，同时**保持精确匹配** —— `startswith("[DONE]")` 会误吞 `[DONE]extra` 这类（若未来出现）真坏行，`in` 更会误伤含该子串的合法 JSON（如 `{"text":"[DONE]"}`）。

**反例（必须不命中）**：`'{"choices":[...],"content":"[DONE]"}'` 是合法 JSON，`strip()` 后不等于 `[DONE]`，正常解析 —— 精确匹配保证不误伤。

### D3 常量与辅助函数的抽取

抽 `_SSE_STREAM_END_SENTINEL = "[DONE]"` 与 `_is_sse_stream_end(data_str) -> bool` 到模块级。

**理由**：哨兵值在注释、判据、未来可能的测试断言中会被引多次，抽常量避免魔法字符串散落；抽函数让判据可单测、也让后续新增哨兵有唯一落点（但**本 change 不预先支持多哨兵**，保持单一来源）。

### D4 反向守护测试是必需的，不是可选的

新增 `test_genuinely_bad_sse_line_still_logs_warning` 断言真实坏行**恰好**产生 1 条告警。

**理由**：本 change 的失败模式是「**顺手把告警一起关掉**」—— 那样测试看起来全绿、日志变安静，但 issue #249 花力气建立的可观测性被静默清零。这是典型的「用静默换安静」退化。反向守护测试是唯一能机械拦住它的东西；断言「恰好 1 条」而非「≥1 条」，还能同时锁住「哨兵不再额外贡献告警」。

### D5 不采用 provider 感知

不在 `_stream_events` 里引入 provider 分支。

**理由**：`_stream_events` 是 `BaseLLM` 的共享实现，两个 provider 共用；而 `[DONE]` 是 OpenAI SSE 的约定、Anthropic 路径不发它 —— 也就是说**该哨兵对 Anthropic 路径天然无副作用**（永不出现），无需分支。引入 provider 感知只会增加耦合而无收益。

### D6 spec delta 的落点

在 `agent-runtime` **新增 Requirement**「SSE 可观测性区分协议控制帧与坏行」，而非塞进既有 Requirement。

**理由**：既有流式 Requirement 管的是「事件发布」；本条管的是「**可观测性口径**」（哪些行该告警）——是不同关注点。3 个 Scenario 分别固定：哨兵不告警、坏行仍告警、含哨兵字面量的合法 JSON 不被误判（第三条是实现 `strip()` 精确匹配的规格依据，防止后人改成 `in`/`startswith` 时无人察觉）。

## Pre-Implementation Review

### 已解决问题

1. 放行位置 → D1 定案：解析前显式放行。
2. 判据精确度 → D2 定案：`strip()` 后精确等于，避免误伤合法 JSON。
3. 如何防止「顺手关掉告警」→ D4 定案：反向守护测试断言恰好 1 条。
4. 是否需要 provider 分支 → D5 定案：不需要（哨兵对 Anthropic 路径天然无副作用）。

### 备选方案与否决

- **否决**：删掉告警 —— 牺牲 issue #249 的可观测性收益。
- **否决**：在 `except` 里判别哨兵 —— 语义绕、且先付异常开销（D1）。
- **否决**：`startswith` / `in` 判据 —— 会误吞真坏行或误伤含该子串的合法 JSON（D2）。
- **否决**：provider 感知哨兵表 —— 过度设计（D5）。

### 剩余风险

- **其它协议的结束哨兵**：若未来接入的端点使用不同哨兵（如 Anthropic 的 `message_stop` 是事件不是 data 行，故不受影响），需另案补充。当前已实测的两个 provider（Anthropic 原生 / OpenAI 兼容）均无其它哨兵形态。
- **空格变体**：`strip()` 容忍首尾空白，但不处理 `[DONE] ` 之外的非标准变体（如 `[done]` 小写）。实测目标端点发送标准大写形式；若出现小写变体，会退化为告警（不崩溃），可按需扩展。**刻意不做大小写不敏感**：那会扩大误伤面，且尚无实测依据。

## Risks / Trade-offs

- **判定成本**：每行 `data:` 增加一次 `strip()` 比较。可忽略（字符串短、每响应数十行）。
- **`strip()` 会复制字符串**：对超大 `data:` 行有一次拷贝开销。实测 SSE 行为 KB 级，可忽略；若未来出现 MB 级单行，可改为 `len` 预筛（当前无依据，不做）。
- **测试对 logger 名的耦合**：两条测试用 `caplog.at_level(..., logger="asterwynd.llm")`，若 logger 名变更测试会失效。属可接受（logger 名是模块级常量，变更面小且会同时暴露在其它测试里）。

## Testing Strategy

TDD（先写失败测试）：

1. **正向**：喂含 `data: [DONE]` 的 SSE 序列 → 断言无 "unparseable SSE data line" 告警、且响应内容正确。
2. **反向**：喂「一条真坏行 + 一条 `[DONE]`」→ 断言恰好 1 条告警（坏行）；修复前为 2 条（RED）。
3. 回归：`tests/agent/test_openai_llm.py` 全量；因改动在共享 LLM 层，跑全量 pytest。

判别力验证：把 `_is_sse_stream_end(data_str)` 短路为 `False` → 两条测试均 RED（实测已做）。
