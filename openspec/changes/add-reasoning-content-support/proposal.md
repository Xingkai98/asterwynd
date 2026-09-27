# Proposal: 思维链（reasoning/thinking）的采集、回传与折叠展示（add-reasoning-content-support）

关联跟踪 issue：[#256](https://github.com/Xingkai98/asterwynd/issues/256)（【feature】思维链的采集、回传与折叠展示：兼容 Anthropic/OpenAI/DeepSeek 两端点）。

## Change Type

- primary: feature
- secondary: []

## Why

排查 issue #249 时发现：DeepSeek V4 系列**默认开启 thinking**（官方文档逐字："Thinking mode is enabled by default, with the default effort being `high`"），asterwynd 不传任何参数也会收到思维链内容。实测同一账号、同一模型 `deepseek-v4-flash`：

| 协议 | 暴露字段 |
|---|---|
| Anthropic 兼容端点 | `thinking` block（流式 `thinking_delta` + `signature_delta`） |
| OpenAI 兼容端点 | `reasoning_content` |

这些 token **计入 output token（已付费）**，但 asterwynd 完全不展示（前端 `grep reasoning` 零命中）。

三个具体缺陷：

**1. Anthropic 路径既不采集也不回传 → 存在 400 风险（最严重）**

`agent/anthropic_llm.py` 对 `thinking` 零处理：流式解析只认 `text_delta` / `input_json_delta`；`_build_payload` 只发 `{"type":"text"}` / `{"type":"tool_use"}`。

而端点**要求回传**（本次实测）：

```
不回传 → 400 "The content[].thinking in the thinking mode must be passed back to the API."
```

**当前之所以没炸，是碰运气**：该端点的回传校验有启发式，认 `tool_use` id 的格式——

| id 形态 | 结果 |
|---|---|
| `call_00_ET_...`（asterwynd 实际使用的） | 200，不要求回传 |
| `t1` / `toolu_...` / `call_abc` | 400，要求回传 |

受控实验（同一 payload 只改 id、同时刻对跑）确认。**一旦端点改启发式或 id 生成格式变更，多轮工具调用会立刻 400。** 这使「能用」建立在未文档化的实现细节上。

**2. OpenAI 路径采集并回传了，但同样不展示**

`agent/openai_llm.py` 采集 `reasoning_content` 存入 `Message.reasoning_content` 并回传，但前端不渲染。

**3. 现有消息模型无法表达「不可展示但必须原样回传」的载荷**

Anthropic 的 `signature` 是**不透明值**（官方明确 "should not be interpreted or parsed"），必须**原样、顺序不变**地回传；把它当普通文本存储/展示/压缩都有正确性风险。当前 `reasoning_content: Optional[str]` 承载不了它。

## What Changes

**A. 消息模型：reasoning 结构化，区分「可展示文本」与「opaque 回传载荷」**

在 `Message` 上引入结构化的 reasoning 段（一段 = 可展示文本 + 可选 opaque 载荷），使 `signature` 这类不可解析的载荷能被原样保存与回放，同时展示层只消费可读文本。

**B. Anthropic 路径：采集 thinking block 并按其规则回传**

- 流式解析新增 `thinking_delta` / `signature_delta` 的累积。
- `_build_payload` 回放 assistant 消息时带上 thinking block（含 signature）。
- 遵循官方「最新 assistant 轮必须原样带；更早轮可省略」的规则（见 Research）。

**C. OpenAI 路径：保持既有回传，接入统一消息模型**

`reasoning_content` 的采集与回传行为不变，改为经由统一模型表达。

**D. 展示：通用折叠样式，默认关闭，单击展开（用户已拍板）**

- 前端在 assistant 消息上渲染可折叠的「思考过程」区，**默认折叠**，单击展开。
- 对所有 provider 统一（有 reasoning 就显示该区，无则不显示），不按 provider 分叉样式。

**E. 流式：思维链增量实时可达前端**

思维链应在生成过程中即可见（展开状态下实时增长），而非等响应结束才出现。

## Non-Goals

- **不实现「关闭 thinking」的开关**（见 Open Questions Q3）——本 change 只做采集/回传/展示；是否提供关闭能力是独立决策。
- 不支持 OpenAI Responses API 的 `reasoning` item / `encrypted_content`（仓库当前只实现 Chat Completions 与 Anthropic Messages 两条路径；接入 Responses API 是独立 change）。
- 不改 `redacted_thinking` 的语义（DS 的 Anthropic 兼容端点不支持它；Anthropic 原生下按「原样回传」处理，不做解密或展示）。
- 不做思维链的持久化策略变更（沿用现有 session 持久化；compaction 对旧轮 reasoning 的处理见 design D6）。

## Impact Analysis

**代码影响**

| 文件 | 改动 | 风险 |
|---|---|---|
| `agent/llm.py` | `LLMResponse` 增 reasoning 结构化载荷；`LLMStreamEvent` 增 reasoning 事件类型 | 中（核心数据结构，所有 provider 共享） |
| `agent/message.py` | `Message` 的 reasoning 表达结构化 + 序列化兼容 | 中（影响会话持久化格式与所有消费方） |
| `agent/anthropic_llm.py` | 流式解析 thinking/signature；`_build_payload` 回传 thinking block | 中（触碰流式主路径） |
| `agent/openai_llm.py` | 接入统一模型（回传行为不变） | 低 |
| `agent/loop.py` | 透传 reasoning 到事件与消息 | 低 |
| `web/static/chat.js` + `style.css` | 折叠展示区 + 流式增量 | 中（新增 UI 面） |
| `web/server.py` | 转发 reasoning 事件 | 低 |
| `tests/**`（增补） | 四条路径的采集/回传/展示回归 | — |

**契约影响（对外）**

- 新增 WebSocket 事件类型（reasoning 增量），前端与任何消费者按增量协议处理。
- 会话持久化 `messages.json` 的 assistant 消息新增 reasoning 字段；**旧会话可正常加载**（缺字段按无 reasoning 处理）。
- 对外无破坏性变更；无 reasoning 的 provider 行为不变。

**不影响**

- 非流式路径、tool-call 协议、approval、trace 语义。
- OpenAI 路径的既有回传行为。
- 无 reasoning 能力的模型（不产生该字段，前端不显示该区）。

**待确认影响面**

- **Q1（消息模型形态）**、**Q2（展示的流式粒度）**、**Q3（是否提供关闭 thinking 开关）**、**Q4（compaction 对旧轮 reasoning 的处理）** —— 见 `design.md` 的 `## Open Questions`，需用户确认后定案。

**测试影响**

- 新增回归覆盖四条路径的**采集**（Anthropic thinking / DS-Anthropic thinking / DS-OpenAI reasoning_content / OpenAI 官方无该字段时不影响）、**回传**（Anthropic 带 signature 回传、OpenAI 带 reasoning_content 回传）、**展示**（折叠默认关闭、单击展开、无 reasoning 时不渲染）。
- 因改动涉及 AgentLoop 与 Web，按仓库规则跑全量 pytest + 浏览器回归。

**文档影响**

- `docs/architecture.md`：LLM provider 与 Web UI 章节若描述消息模型，需同步。
- `docs/agent-internals.md`：消息循环/流式事件章节需补 reasoning 事件。
- `docs/known-issues.md` / `docs/known-debt.md`：收尾时按结论记录（如「DS 端点 id 启发式」这一未文档化依赖）。
- 关键词扫描 `docs/`、`README.md`、`AGENTS.md`、`CONTEXT.md`。

## Reference Implementation Research

- research_tier: full
- status: enabled
- reason: 属**架构级改造**（触碰核心消息模型 `agent/message.py` 与 `agent/llm.py`，新增 WebSocket 事件类型与前端 UI 面，且需同时兼容四条 provider 路径），按门禁判据命中 `full` 档「架构级改造」。同时本 change 走 grill，命中 `full` 档「走 grill 的非平凡 change」。设计存在多个真实备选（消息模型形态 / 回传策略 / 事件拆分方式），需业界实践支撑取舍。
- research questions: (1) 各协议（Anthropic Messages / OpenAI Chat Completions / OpenAI Responses / 第三方 OpenAI 兼容端点 / DeepSeek 的两个兼容端点）如何暴露思维链（字段名、流式形态、是否计费）？(2) 多轮与 tool use 时，思维链是否必须回传、规则是否因 provider 而异？(3) `signature` / `encrypted_content` 这类 opaque 载荷的作用与约束（可否解析、可否重排、跨对话复用会怎样）？(4) 业界 agent 客户端如何处理（采集 / 持久化 / 展示 / 回传四层怎么分工）？(5) 展示形态的既有做法（折叠？默认态？与正文的关系）？
- findings: 完整调研见下方 F1–F5（官方文档 + 官方 SDK 源码 + 业界代码仓库，逐条标注可信度）。核心结论五条：① Anthropic 用 `thinking` block（流式 `thinking_delta` + `signature_delta`），OpenAI 官方 Chat Completions **不返回** reasoning 文本（`reasoning_content` 是第三方约定），Responses API 另有一套（`summary` 展示 + `encrypted_content` 回传）；② Anthropic 要求 tool use 时**最新 assistant 轮**的 thinking block 原样回传（顺序不可改），更早轮可省略；DeepSeek 的 OpenAI 兼容端点带 `tools` 时**所有历史轮**都要回传，两条路径不回传都 400；③ Anthropic 的 `signature` 是**不可解析**的 opaque 值且**绑定对话**，跨对话复用会报 `bound to a different conversation`；④ 业界共识是「采集 / 持久化 / 展示三层分离」——持久化原样存 provider 原生载荷（含签名），展示只消费可读文本，OpenAI 官方把它抽象为 SummaryText vs Opaque；⑤ 展示形态主流是**可折叠的独立 Thinking 区**，默认不与正文混排，与用户拍板一致。本地参考仓库与 codegraph 均不可用（见文末事实与替代依据）。
- design impact: 确认采用「结构化 reasoning 段（可展示文本 + opaque 载荷）」而非单字符串；回传采用「最新轮必带 + 默认全带」并配错误自愈退路；流式事件与 `assistant_delta` **隔离**（否则污染正文渲染）；压缩采用「旧轮可丢、新轮必留」；展示采用跨 provider 统一的折叠组件。否决了「存 provider 原生 dict 列表」（污染核心消息模型）与「单字符串 + 旁挂签名」（表达不了多段）。

**Findings（详细）**

*（调研渠道：官方文档 + 官方 SDK 源码 + 社区/代码仓库，逐条标注可信度。本地参考仓库与 codegraph 均不可用，见文末。）*

#### F1. 各协议的暴露形态（官方）

| 协议 | 展示用 | 回传用 |
|---|---|---|
| Anthropic Messages | `thinking` block（`{"type":"thinking","thinking":...,"signature":...}`），流式为 `thinking_delta`，**紧随 `content_block_stop` 前**一个 `signature_delta` | 同块原样回传 |
| OpenAI Chat Completions | **无**（官方模型只给 `usage.completion_tokens_details.reasoning_tokens` 计数） | 不适用 |
| OpenAI Responses API | `reasoning` item 的 `summary[]`（`summary_text`） | 同 item 的 `encrypted_content` |
| 第三方 OpenAI 兼容端点 | `reasoning_content`（DeepSeek 首开；vLLM/Grok/Qwen3 跟进，字段名有分歧：`reasoning_content` / `reasoning` / `reasoning_details`） | 同字段 |
| DeepSeek Anthropic 兼容端点 | `thinking` block | 同块 |

> 关键：`reasoning_content` **不是** OpenAI 官方字段，是第三方约定。Responses API 的 `reasoning_text` 是 raw CoT，官方定位「不应展示给终端用户」。

#### F2. 回传规则（官方，逐条）

- **Anthropic**：tool use 时**最新 assistant 轮**的 thinking block 必须原样回传（"you must pass thinking blocks back to the API for the last assistant message"；"If this is not passed in, an error occurs"）；更早轮**可省略**（API 自动过滤）；顺序**不可重排或修改**（"you cannot rearrange or modify the sequence"）。`redacted_thinking` 同样必须原样回传。
- **DeepSeek（OpenAI 兼容）**：**带 `tools` 时所有历史轮**的 `reasoning_content` 都要回传（"must be fully passed back to the API in all subsequent requests — even for turns where the model did not perform a tool call"）；不带 tools 时不要求。
- **DeepSeek（Anthropic 兼容）**：与 Anthropic 同构（要求回传 `content[].thinking`），但 `budget_tokens` 被忽略、`redacted_thinking` 不支持。

#### F3. opaque 载荷的约束（官方）

- Anthropic `signature`：不透明值，作用是证明该块由模型生成并在回传时校验完整性；官方明确 **"should not be interpreted or parsed"**。签名绑定对话，跨对话复用会报 `bound to a different conversation`；补救是移除该块（及其后所有块）重试，或设 `block_binding.prefix_mismatch_behavior: "drop_block"`（需 beta 头）。
- **反向陷阱**：禁用 thinking 后，**当轮 tool use 再传 thinking 内容会失败**（其他上下文里传会被静默忽略）。
- **计费**：thinking 按 output token 计费；Claude 4 即便只返回**摘要版**思考，也按**完整**思考 token 计费。

#### F4. 业界的处理模式（代码仓库 / 官方）

- **采集层**：解析各 provider 原生形态（`thinking_delta`+`signature_delta` / `reasoning_content` / Responses 的 `reasoning_summary_text.delta`）。
- **持久化层**：**原样保存** provider 原生 payload（含 `signature` / `encrypted_content`），不解析、不重排。OpenAI 官方把它抽象为 "SummaryText（可安全展示/记录） vs Opaque（provider 密文，必须原样回放）"。
- **展示层**：只消费「可展示」部分，渲染成**可折叠面板**，默认不与正文混排（Cline 的 `ThinkingRow`、LibreChat 的独立 Reasoning UI 均是此形态）。
- **Claude Code 的自愈策略**（官方文档）：上游 400 且文案指向 `thinking` 字段 → 关掉该能力继续；指向 **signature** → 移除历史 thinking blocks 重试并持续不带。前提是网关**逐字转发 error body**，否则匹配不上。
- **跨协议转换的教训**：多数框架在 Anthropic→OpenAI 转换时丢 thinking block，随后被 DeepSeek/Kimi 端点 400（LiteLLM / open-webui / hermes-agent 均有此类 issue，修法分「剥掉」与「缓存重注入」两派）。

#### F5. 展示形态（代码仓库）

主流做法是**可折叠的独立「Thinking」区**，位于最终回答上方；流式边收边显示（先出现占位行，再填充内容）；**默认折叠**或至少不与正文混排。

#### Design impact（见上 design impact 字段）

1. 采用「**采集 / 持久化 / 展示三层分离**」：持久化保存 provider 原生载荷（含签名），展示只消费可读文本。→ 直接决定 design D1 的消息模型形态。
2. Anthropic 的 `signature` **必须原样、顺序不可改**地回传 → 消息模型必须能承载 opaque 载荷，不能只存 `str`。
3. 「最新 assistant 轮必须带、更早轮可省」给了实现自由度：**旧轮 reasoning 可在 compaction 时丢弃**而不破坏正确性（→ design D6）。
4. 展示形态采用业界共识的**折叠面板**，与用户拍板的「默认关闭、单击展开」一致。
5. **不计费优化**：本 change 不引入「关 thinking」开关（→ Open Questions Q3）。

**本地参考仓库不可用的事实与替代依据**：本工作区**无** `.dev/reference-repos.txt`，也**无** `.codegraph/`（均已确认不存在），故无本地参考仓库可对比。替代依据为上述官方文档、官方 SDK 源码与业界代码仓库。
